"""Orchestration for one read-only repository analysis."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.domain.graph import GraphBuildResult, build_graph, stable_graph_id
from app.domain.skills import FindingData, run_initial_skills
from app.infrastructure.archive import ArchiveArtifact, inspect_archive, inspect_github_tree
from app.infrastructure.github import GitHubClient, GitHubError, RepositoryAddress, parse_github_url
from app.models import (
    AnalysisEvent,
    AnalysisRun,
    Finding,
    GraphEdge,
    GraphNode,
    Repository,
    RepositorySnapshot,
    SourceFile,
)

logger = logging.getLogger("yggdrasil.analysis")
logger.setLevel(logging.INFO)
logger.propagate = True


def _configure_analysis_file_logging() -> None:
    """Write safe, rotating analysis diagnostics beside the local database.

    This logger deliberately records stack frame locations, exception classes and analysis IDs,
    but not exception messages, local variables, source lines or repository contents.
    """
    log_path = Path(__file__).resolve().parents[2] / "data" / "logs" / "analysis.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_log_path = str(log_path.resolve())
        if any(
            isinstance(handler, RotatingFileHandler)
            and str(Path(handler.baseFilename).resolve()) == resolved_log_path
            for handler in logger.handlers
        ):
            return
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setLevel(logging.ERROR)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        # Console logging remains available if the local filesystem is read-only.
        logger.warning("analysis_file_logging_unavailable")


def _safe_traceback_summary(exc: BaseException) -> str:
    """Return outer and inner stack locations without exception text or source-code lines."""
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(parts) < 5:
        seen.add(id(current))
        frames = traceback.extract_tb(current.__traceback__)
        # Keep application frames from anywhere in the stack as well as outer/inner context.
        # SQLAlchemy adds enough internal frames that truncating to the tail can hide the call site.
        app_frames = [
            frame for frame in frames
            if "/app/" in frame.filename.replace("\\", "/")
        ]
        selected = frames[:3] + app_frames + (frames[-8:] if len(frames) > 3 else [])
        frame_summaries: list[str] = []
        emitted: set[tuple[str, int, str]] = set()
        for frame in selected:
            path_parts = Path(frame.filename).parts
            safe_path = "/".join(path_parts[-3:])
            identity = (safe_path, frame.lineno, frame.name)
            if identity in emitted:
                continue
            emitted.add(identity)
            frame_summaries.append(f"{safe_path}:{frame.lineno}:{frame.name}")
        parts.append(f"{type(current).__name__}[{' > '.join(frame_summaries) or 'no_frames'}]")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)[:5000]


def _safe_integrity_summary(exc: IntegrityError) -> str:
    """Extract only constraint identifiers from DB errors, never SQL or bound values."""
    original = exc.orig
    diag = getattr(original, "diag", None)
    if diag is not None:
        values = {
            "constraint": getattr(diag, "constraint_name", None),
            "table": getattr(diag, "table_name", None),
            "column": getattr(diag, "column_name", None),
        }
        safe = {
            name: value for name, value in values.items()
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
        }
        if safe:
            return "integrity=" + ",".join(f"{name}:{value}" for name, value in safe.items())

    # SQLite exposes constraint failures as a concise identifier-only message. Parse a strict
    # allowlist of formats; never log the raw message, SQL statement or parameters.
    message = str(original)
    patterns = (
        (r"^UNIQUE constraint failed: ([A-Za-z0-9_., ]+)$", "unique_columns"),
        (r"^NOT NULL constraint failed: ([A-Za-z0-9_.]+)$", "not_null_column"),
        (r"^FOREIGN KEY constraint failed$", "foreign_key"),
        (r"^CHECK constraint failed: ([A-Za-z_][A-Za-z0-9_]*)$", "check_constraint"),
        (r'.*violates unique constraint "([A-Za-z_][A-Za-z0-9_]*)".*', "unique_constraint"),
        (r'.*violates foreign key constraint "([A-Za-z_][A-Za-z0-9_]*)".*', "foreign_key_constraint"),
        (r'.*violates not-null constraint "([A-Za-z_][A-Za-z0-9_]*)".*', "not_null_constraint"),
    )
    for pattern, label in patterns:
        match = re.fullmatch(pattern, message)
        if match:
            detail = match.group(1) if match.lastindex else "identified"
            # For SQLite's comma-delimited columns, validate every piece as an identifier.
            if label == "unique_columns":
                identifiers = [part.strip() for part in detail.split(",")]
                if not identifiers or any(
                    not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?", item)
                    for item in identifiers
                ):
                    continue
                detail = ",".join(identifiers)
            elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", detail):
                continue
            return f"integrity={label}:{detail}"
    return "integrity=unclassified"


_configure_analysis_file_logging()

TERMINAL_STATES = {"completed", "completed_with_warnings", "failed", "cancelled"}


def _id() -> str:
    return uuid4().hex


def _emit(db: Session, run: AnalysisRun, event_type: str, payload: dict[str, Any] | None = None) -> None:
    run.event_sequence += 1
    db.add(
        AnalysisEvent(
            id=_id(),
            analysis_run_id=run.id,
            sequence_number=run.event_sequence,
            event_type=event_type,
            payload=payload or {},
        )
    )


def _publish(
    db: Session,
    run: AnalysisRun,
    *,
    status: str | None = None,
    stage: str | None = None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    progress: dict[str, Any] | None = None,
) -> None:
    if status is not None:
        run.status = status
    if stage is not None:
        run.stage = stage
    if progress is not None:
        run.progress_metadata = {**(run.progress_metadata or {}), **progress}
    _emit(db, run, event_type, payload)
    db.commit()


def _source_row(snapshot_id: str, artifact: ArchiveArtifact) -> SourceFile:
    return SourceFile(
        id=_id(),
        snapshot_id=snapshot_id,
        path=artifact.path,
        size_bytes=artifact.size_bytes,
        language=artifact.language,
        eligibility_status=artifact.eligibility_status,
        parse_status=artifact.parse_status,
        content_hash=artifact.content_hash,
        metadata_json=artifact.metadata,
        redacted_content=artifact.redacted_content,
    )


def _persist_graph(
    db: Session,
    snapshot_id: str,
    graph: GraphBuildResult,
    source_ids: dict[str, str],
) -> tuple[dict[str, str], int]:
    node_ids: dict[str, str] = {}
    rows: list[GraphNode] = []
    for node in graph.nodes:
        node_id = stable_graph_id(snapshot_id, node.stable_key)
        node_ids[node.stable_key] = node_id
        rows.append(
            GraphNode(
                id=node_id,
                snapshot_id=snapshot_id,
                node_type=node.node_type,
                stable_key=node.stable_key,
                label=node.label[:500],
                source_file_id=source_ids.get(node.source_path or ""),
                start_line=node.start_line,
                end_line=node.end_line,
                properties=node.properties,
                provenance_type=node.provenance_type,
            )
        )
    db.add_all(rows)
    db.flush()

    edge_rows: list[GraphEdge] = []
    edge_keys: set[str] = set()
    for edge in graph.edges:
        source_id = node_ids.get(edge.source_key)
        target_id = node_ids.get(edge.target_key)
        if not source_id or not target_id:
            continue
        signature = json.dumps(
            [edge.source_key, edge.target_key, edge.relation_type, edge.provenance_type, edge.evidence],
            sort_keys=True,
            ensure_ascii=True,
        )
        edge_key = hashlib.sha256(f"{snapshot_id}:{signature}".encode()).hexdigest()[:32]
        if edge_key in edge_keys:
            continue
        edge_keys.add(edge_key)
        edge_rows.append(
            GraphEdge(
                id=edge_key,
                snapshot_id=snapshot_id,
                source_node_id=source_id,
                target_node_id=target_id,
                relation_type=edge.relation_type,
                provenance_type=edge.provenance_type,
                confidence_label=edge.confidence_label,
                evidence=edge.evidence,
            )
        )
    db.add_all(edge_rows)
    return node_ids, len(edge_rows)


def _persist_findings_and_graph_nodes(
    db: Session,
    run: AnalysisRun,
    snapshot_id: str,
    findings_data: list[FindingData],
    source_ids: dict[str, str],
    node_ids: dict[str, str],
) -> tuple[int, int, int]:
    finding_rows: list[Finding] = []
    node_rows: list[GraphNode] = []
    edge_rows: list[GraphEdge] = []
    for item in findings_data:
        finding_id = _id()
        finding_rows.append(
            Finding(
                id=finding_id,
                analysis_run_id=run.id,
                skill_id=item.skill_id,
                skill_version=item.skill_version,
                finding_key=item.finding_key,
                category=item.category,
                severity=item.severity,
                status=item.status,
                confidence_label=item.confidence_label,
                title=item.title,
                summary=item.summary,
                impact=item.impact,
                recommendation=item.recommendation,
                limitations=item.limitations,
                evidence=item.evidence,
            )
        )
        stable_key = f"finding:{run.id}:{item.finding_key}"
        node_id = stable_graph_id(snapshot_id, stable_key)
        path = next((str(e.get("path")) for e in item.evidence if e.get("path")), None)
        node_rows.append(
            GraphNode(
                id=node_id,
                snapshot_id=snapshot_id,
                node_type="finding",
                stable_key=stable_key,
                label=item.title[:500],
                source_file_id=source_ids.get(path or ""),
                start_line=next((e.get("start_line") for e in item.evidence if e.get("start_line")), None),
                end_line=next((e.get("end_line") for e in item.evidence if e.get("end_line")), None),
                properties={
                    "finding_key": item.finding_key,
                    "skill_id": item.skill_id,
                    "category": item.category,
                    "severity": item.severity,
                    "status": item.status,
                    "confidence_label": item.confidence_label,
                },
                provenance_type="deterministic",
            )
        )
        for evidence in item.evidence:
            path_value = evidence.get("path")
            source_node_id = node_ids.get(f"file:{path_value}") if path_value else None
            if not source_node_id:
                continue
            edge_id = hashlib.sha256(
                f"{snapshot_id}:finding-edge:{source_node_id}:{node_id}:{evidence.get('start_line')}".encode()
            ).hexdigest()[:32]
            edge_rows.append(
                GraphEdge(
                    id=edge_id,
                    snapshot_id=snapshot_id,
                    source_node_id=source_node_id,
                    target_node_id=node_id,
                    relation_type="finding_affects",
                    provenance_type="deterministic",
                    confidence_label=item.confidence_label,
                    evidence={
                        "path": path_value,
                        "start_line": evidence.get("start_line"),
                        "end_line": evidence.get("end_line"),
                        "evidence_type": evidence.get("evidence_type"),
                        "redacted": True,
                    },
                )
            )
    # Persist each dependency layer explicitly. In particular, edges may reference finding
    # nodes created in this same skill pass; flushing nodes first prevents a backend/driver
    # from attempting the edge INSERT before its target node exists.
    db.info["yggdrasil_persistence_phase"] = "skill_findings"
    db.add_all(finding_rows)
    db.flush()

    db.info["yggdrasil_persistence_phase"] = "finding_graph_nodes"
    db.add_all(node_rows)
    db.flush()

    # Verify edge endpoints within this snapshot before attempting the FK-constrained INSERT.
    # A missing endpoint is an internal graph consistency issue; omit only that relation and
    # surface a warning instead of failing the entire analysis after valid findings were saved.
    db.info["yggdrasil_persistence_phase"] = "finding_graph_edges"
    referenced_node_ids = {
        value
        for edge in edge_rows
        for value in (edge.source_node_id, edge.target_node_id)
    }
    if referenced_node_ids:
        existing_node_ids = set(
            db.scalars(
                select(GraphNode.id).where(
                    GraphNode.snapshot_id == snapshot_id,
                    GraphNode.id.in_(referenced_node_ids),
                )
            ).all()
        )
    else:
        existing_node_ids = set()
    valid_edge_rows = [
        edge for edge in edge_rows
        if edge.source_node_id in existing_node_ids and edge.target_node_id in existing_node_ids
    ]
    skipped_edge_count = len(edge_rows) - len(valid_edge_rows)
    db.add_all(valid_edge_rows)
    db.flush()
    db.info.pop("yggdrasil_persistence_phase", None)
    return len(finding_rows), len(valid_edge_rows), skipped_edge_count


def run_analysis(analysis_id: str) -> None:
    """Background-task entry point. All repository content remains data, never executable code."""
    db = SessionLocal()
    current_stage = "queued"
    try:
        run = db.get(AnalysisRun, analysis_id)
        if run is None or run.status in TERMINAL_STATES:
            return
        repository = db.get(Repository, run.repository_id)
        if repository is None:
            raise RuntimeError("analysis repository record missing")

        run.started_at = datetime.now(timezone.utc)
        current_stage = "fetching_repository"
        _publish(
            db,
            run,
            status="fetching_repository",
            stage="fetching_repository",
            event_type="repository_fetch_started",
            payload={"repository_url": repository.canonical_url},
        )
        address = RepositoryAddress(repository.owner, repository.name, repository.canonical_url)

        with GitHubClient(settings.github_token) as github:
            resolved = github.resolve(address, run.configuration.get("ref"))
            repository.default_branch = resolved.default_branch
            repository.description = resolved.description
            repository.visibility = "public"
            db.flush()

            snapshot = RepositorySnapshot(
                id=_id(),
                repository_id=repository.id,
                commit_sha=resolved.commit_sha,
                requested_ref=resolved.requested_ref,
                default_branch=resolved.default_branch,
                metadata_json=resolved.safe_metadata(),
            )
            db.add(snapshot)
            db.flush()
            run.snapshot_id = snapshot.id
            db.commit()

            _publish(
                db,
                run,
                status="inventorying",
                stage="inventorying",
                event_type="repository_metadata_loaded",
                payload={
                    "commit_sha": resolved.commit_sha,
                    "requested_ref": resolved.requested_ref,
                    "default_branch": resolved.default_branch,
                },
            )
            current_stage = "inventorying"
            tree_fallback = False
            try:
                archive_bytes = github.download_archive(resolved)
            except GitHubError as exc:
                if exc.code != "ARCHIVE_TOO_LARGE":
                    raise
                tree_fallback = True

            archive_result = None
            if not tree_fallback:
                try:
                    archive_result = inspect_archive(archive_bytes)
                except ValueError as exc:
                    if str(exc) == "archive_too_large":
                        tree_fallback = True
                    else:
                        raise GitHubError(
                            "INVALID_REPOSITORY_ARCHIVE",
                            "O conteúdo recebido não pôde ser interpretado como um arquivo compactado válido.",
                            502,
                        ) from exc

            if tree_fallback:
                _publish(
                    db,
                    run,
                    status="inventorying",
                    stage="inventorying",
                    event_type="selective_tree_fallback_started",
                    payload={
                        "reason": "archive_too_large",
                        "message": "Arquivo compactado acima do limite; iniciando leitura seletiva por commit.",
                    },
                )
                tree_payload = github.get_repository_tree(resolved)
                tree_entries = tree_payload.get("tree")
                if not isinstance(tree_entries, list):
                    raise GitHubError(
                        "GITHUB_TREE_INVALID",
                        "O GitHub retornou uma árvore de arquivos inválida.",
                        502,
                    )
                archive_result = inspect_github_tree(
                    tree_entries,
                    lambda path, max_bytes: github.download_raw_file(resolved, path, max_bytes),
                    tree_truncated=tree_payload.get("truncated") is True,
                )
                archive_result.warnings.append(
                    "O arquivo compactado excedeu o limite; foi usada leitura seletiva de arquivos elegíveis."
                )

        assert archive_result is not None
        warnings = list(archive_result.warnings)
        current_stage = "parsing"
        _publish(
            db,
            run,
            status="parsing",
            stage="parsing",
            event_type="inventory_completed",
            payload={
                "files_discovered": len(archive_result.files),
                "ingestion_method": archive_result.source_method,
                "archive_size_bytes": archive_result.archive_size_bytes or None,
                "unpacked_declared_bytes": archive_result.unpacked_declared_bytes,
            },
            progress={
                "total_files": len(archive_result.files),
                "files_processed": 0,
                "ingestion_method": archive_result.source_method,
                "archive_size_bytes": archive_result.archive_size_bytes or None,
            },
        )

        current_stage = "persisting_inventory"
        source_rows = [_source_row(snapshot.id, artifact) for artifact in archive_result.files]
        db.add_all(source_rows)
        db.commit()
        source_ids = {row.path: row.id for row in source_rows}

        current_stage = "building_graph"
        _publish(
            db,
            run,
            status="building_graph",
            stage="building_graph",
            event_type="graph_build_started",
            payload={"python_files_found": sum(1 for item in archive_result.files if item.is_python)},
        )
        graph = build_graph(resolved.owner, resolved.name, archive_result.files)
        warnings.extend(graph.warnings)

        # Persist parser outcomes and keep only redacted text for later inspection/reporting.
        by_path = {artifact.path: artifact for artifact in archive_result.files}
        for row in source_rows:
            artifact = by_path[row.path]
            row.parse_status = artifact.parse_status
            row.eligibility_status = artifact.eligibility_status
            row.metadata_json = artifact.metadata
        node_ids, edge_count = _persist_graph(db, snapshot.id, graph, source_ids)
        db.commit()

        _publish(
            db,
            run,
            status="running_skills",
            stage="running_skills",
            event_type="graph_build_completed",
            payload={
                "nodes_created": len(graph.nodes),
                "edges_created": edge_count,
                "python_files_parsed": graph.parsed_python_files,
                "python_files_failed": graph.failed_python_files,
            },
            progress={
                "files_processed": len(archive_result.files),
                "nodes_created": len(graph.nodes),
                "edges_created": edge_count,
                "python_files_parsed": graph.parsed_python_files,
                "python_files_failed": graph.failed_python_files,
            },
        )
        current_stage = "running_skills"
        _emit(db, run, "skills_started", {"skills": run.configuration.get("skills", [])})
        db.commit()
        findings_data, skill_warnings = run_initial_skills(
            archive_result.files,
            resolved.commit_sha,
            run.configuration.get("skills"),
        )
        warnings.extend(skill_warnings)
        # Raw text exists only in memory for the scan; it is not stored in the database.
        for artifact in archive_result.files:
            artifact.raw_content = None
        current_stage = "persisting_skills"
        finding_count, finding_edge_count, skipped_finding_edges = _persist_findings_and_graph_nodes(
            db, run, snapshot.id, findings_data, source_ids, node_ids
        )
        if skipped_finding_edges:
            warnings.append(
                f"{skipped_finding_edges} relação(ões) de achados foram omitidas por referência de grafo inválida."
            )
        db.commit()
        _publish(
            db,
            run,
            event_type="skills_completed",
            payload={"findings_created": finding_count},
            progress={"findings_created": finding_count},
        )
        for finding in findings_data:
            _emit(db, run, "finding_created", {
                "finding_key": finding.finding_key,
                "skill_id": finding.skill_id,
                "severity": finding.severity,
                "title": finding.title,
            })
        db.commit()

        current_stage = "finalizing_analysis"
        final_status = "completed_with_warnings" if warnings else "completed"
        run.warning_summary = list(dict.fromkeys(warnings))[:50]
        run.finished_at = datetime.now(timezone.utc)
        _publish(
            db,
            run,
            status=final_status,
            stage="completed",
            event_type="analysis_completed",
            payload={
                "status": final_status,
                "files_discovered": len(archive_result.files),
                "nodes_created": len(graph.nodes) + finding_count,
                "edges_created": edge_count + finding_edge_count,
                "findings_created": finding_count,
                "warnings_count": len(run.warning_summary),
            },
            progress={"warnings_count": len(run.warning_summary)},
        )
    except GitHubError as exc:
        db.rollback()
        run = db.get(AnalysisRun, analysis_id)
        if run is not None:
            run.status = "failed"
            run.stage = "failed"
            run.error_code = exc.code
            run.warning_summary = [exc.message]
            run.finished_at = datetime.now(timezone.utc)
            _emit(db, run, "analysis_failed", {"error_code": exc.code, "message": exc.message})
            db.commit()
    except Exception as exc:  # Keep details out of API responses and never log source content.
        failed_stage = current_stage
        safe_trace = _safe_traceback_summary(exc)
        integrity_summary = (
            _safe_integrity_summary(exc) if isinstance(exc, IntegrityError) else None
        )
        persistence_phase = db.info.pop("yggdrasil_persistence_phase", "not_applicable")
        db.rollback()
        logger.error(
            "analysis_failure analysis_id=%s stage=%s persistence_phase=%s error_type=%s %s trace=%s",
            analysis_id,
            failed_stage,
            persistence_phase,
            type(exc).__name__,
            integrity_summary or "integrity=not_applicable",
            safe_trace,
        )
        run = db.get(AnalysisRun, analysis_id)
        if run is not None:
            run.status = "failed"
            run.stage = "failed"
            run.error_code = "INTERNAL_ANALYSIS_ERROR"
            run.warning_summary = ["A análise encontrou uma falha interna. Consulte os logs locais pelo ID da análise."]
            run.finished_at = datetime.now(timezone.utc)
            _emit(db, run, "analysis_failed", {
                "error_code": run.error_code,
                "message": "A análise encontrou uma falha interna.",
            })
            db.commit()
    finally:
        db.close()

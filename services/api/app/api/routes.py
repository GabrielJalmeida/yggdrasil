"""Public API routes for repository registration, analysis, graph exploration and export."""

from __future__ import annotations

import json
import re
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.application.questions import classify_question, retrieve_evidence
from app.application.runner import _emit, run_analysis
from app.config import settings
from app.db import SessionLocal, get_db
from app.domain.report import generate_markdown
from app.infrastructure.ai_provider import AIProviderError, ai_is_configured, generate_answer
from app.infrastructure.github import GitHubError, parse_github_url, validate_git_ref
from app.models import (
    AnalysisEvent,
    AnalysisRun,
    Finding,
    GraphEdge,
    GraphNode,
    ReportExport,
    Repository,
    RepositorySnapshot,
    SourceFile,
)
from app.schemas.analysis import (
    AnalysisCreate,
    AnalysisQuestion,
    AnalysisQueued,
    FindingStatusUpdate,
)

router = APIRouter(prefix="/api/v1")
TERMINAL_STATES = {"completed", "completed_with_warnings", "failed", "cancelled"}


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "ANALYSIS_NOT_FOUND", "message": "A análise solicitada não foi encontrada."})


def _analysis_view(db: Session, run: AnalysisRun) -> dict[str, Any]:
    repository = db.get(Repository, run.repository_id)
    snapshot = db.get(RepositorySnapshot, run.snapshot_id) if run.snapshot_id else None
    node_count = db.scalar(select(func.count()).select_from(GraphNode).where(GraphNode.snapshot_id == run.snapshot_id)) if run.snapshot_id else 0
    edge_count = db.scalar(select(func.count()).select_from(GraphEdge).where(GraphEdge.snapshot_id == run.snapshot_id)) if run.snapshot_id else 0
    file_count = db.scalar(select(func.count()).select_from(SourceFile).where(SourceFile.snapshot_id == run.snapshot_id)) if run.snapshot_id else 0
    finding_count = db.scalar(select(func.count()).select_from(Finding).where(Finding.analysis_run_id == run.id)) or 0
    eligibility_counts: dict[str, int] = {}
    parse_counts: dict[str, int] = {}
    python_parse_counts: dict[str, int] = {}
    if run.snapshot_id and run.status in TERMINAL_STATES:
        eligibility_counts = {
            str(status): int(count)
            for status, count in db.execute(
                select(SourceFile.eligibility_status, func.count())
                .where(SourceFile.snapshot_id == run.snapshot_id)
                .group_by(SourceFile.eligibility_status)
            ).all()
        }
        parse_counts = {
            str(status): int(count)
            for status, count in db.execute(
                select(SourceFile.parse_status, func.count())
                .where(SourceFile.snapshot_id == run.snapshot_id)
                .group_by(SourceFile.parse_status)
            ).all()
        }
        python_parse_counts = {
            str(status): int(count)
            for status, count in db.execute(
                select(SourceFile.parse_status, func.count())
                .where(SourceFile.snapshot_id == run.snapshot_id, SourceFile.language == "Python")
                .group_by(SourceFile.parse_status)
            ).all()
        }
    # Inventory/eligibility, content parsing and graph rendering are separate dimensions.
    # Keep the source state dictionaries explicit and only label known partial states where
    # the persisted diagnostics support that conclusion.
    incomplete_reasons: list[str] = []
    partial_markers = ("parcial", "atingiu o limite", "limite total", "falha ao ler", "conteúdo textual foi atingido", "metadados incompletos")
    for warning in (run.warning_summary or []):
        warning_text = str(warning)
        if any(marker in warning_text.casefold() for marker in partial_markers):
            incomplete_reasons.append(warning_text)
    failed_reads = eligibility_counts.get("failed", 0)
    failed_parses = parse_counts.get("failed", 0)
    if failed_reads:
        incomplete_reasons.append(f"{failed_reads} arquivo(s) do inventário não puderam ser lidos.")
    if failed_parses:
        incomplete_reasons.append(f"{failed_parses} arquivo(s) não puderam ser analisados pelo parser.")
    incomplete_reasons = list(dict.fromkeys(incomplete_reasons))
    return {
        "id": run.id,
        "repository": {
            "id": repository.id if repository else run.repository_id,
            "owner": repository.owner if repository else None,
            "name": repository.name if repository else None,
            "canonical_url": repository.canonical_url if repository else None,
            "default_branch": repository.default_branch if repository else None,
        },
        "snapshot": {
            "id": snapshot.id,
            "commit_sha": snapshot.commit_sha,
            "requested_ref": snapshot.requested_ref,
            "default_branch": snapshot.default_branch,
            "metadata": snapshot.metadata_json,
        } if snapshot else None,
        "status": run.status,
        "stage": run.stage,
        "progress": run.progress_metadata,
        "configuration": run.configuration,
        "error_code": run.error_code,
        "warnings": run.warning_summary,
        "counts": {
            "files": file_count,
            "nodes": node_count,
            "edges": edge_count,
            "findings": finding_count,
        },
        "coverage": {
            "inventory_total": file_count,
            "eligible_files": eligibility_counts.get("eligible", 0),
            "ignored_by_policy": eligibility_counts.get("ignored_by_policy", 0),
            "read_failures": eligibility_counts.get("failed", 0),
            "unsupported_files": parse_counts.get("unsupported", 0),
            "not_applicable_files": parse_counts.get("not_applicable", 0),
            "python_total": sum(python_parse_counts.values()),
            "python_parsed": python_parse_counts.get("parsed", 0),
            "python_failed": python_parse_counts.get("failed", 0),
            "python_pending": python_parse_counts.get("queued", 0) + python_parse_counts.get("parsing", 0),
            "eligibility_status_counts": eligibility_counts,
            "parse_status_counts": parse_counts,
            "assessment": "pending" if run.status not in TERMINAL_STATES else ("partial" if incomplete_reasons else "observed"),
            "incomplete_reasons": incomplete_reasons,
        },
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "events_url": f"/api/v1/analyses/{run.id}/events",
    }


def _graph_node_view(node: GraphNode, file_paths: dict[str, str]) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.node_type,
        "stable_key": node.stable_key,
        "label": node.label,
        "path": file_paths.get(node.source_file_id or ""),
        "start_line": node.start_line,
        "end_line": node.end_line,
        "properties": node.properties,
        "provenance_type": node.provenance_type,
    }


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    """Readiness endpoint includes a cheap database round-trip."""
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
        "version": settings.app_version,
        "ai_enabled": ai_is_configured(),
        "ai_provider": settings.ai_provider if ai_is_configured() else "disabled",
        "ai_model": settings.ai_model if ai_is_configured() else None,
    }


@router.get("/skills")
def list_skills() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "appsec.secrets-detection",
                "name": "Detecção inicial de possíveis segredos",
                "version": "0.2.0",
                "category": "appsec",
                "mode": "deterministic",
                "status": "enabled",
                "limitations": ["Padrões estáticos; não valida credenciais."],
            },
            {
                "id": "engineering.test-inventory",
                "name": "Inventário de arquivos de teste Python",
                "version": "0.1.0",
                "category": "engineering",
                "mode": "deterministic",
                "status": "enabled",
                "limitations": ["Não mede cobertura nem executa testes."],
            },
        ],
        "ai_enabled": ai_is_configured(),
        "ai_message": (
            "Perguntas com recuperação lexical/estrutural estão habilitadas. "
            "Trechos redigidos serão enviados ao provedor configurado ao fazer uma pergunta."
            if ai_is_configured()
            else "Perguntas por IA estão disponíveis após configurar AI_PROVIDER, AI_MODEL e as credenciais necessárias no .env."
        ),
    }


@router.post("/analyses", response_model=AnalysisQueued, status_code=202)
def create_analysis(
    payload: AnalysisCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> AnalysisQueued:
    try:
        address = parse_github_url(payload.repository_url)
        ref = validate_git_ref(payload.ref)
    except GitHubError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    repository = db.scalar(
        select(Repository).where(
            Repository.provider == "github",
            func.lower(Repository.owner) == address.owner.lower(),
            func.lower(Repository.name) == address.name.lower(),
        )
    )
    if repository is None:
        repository = Repository(
            id=uuid4().hex,
            provider="github",
            owner=address.owner,
            name=address.name,
            canonical_url=address.canonical_url,
            visibility="public",
        )
        db.add(repository)
        db.flush()
    run = AnalysisRun(
        id=uuid4().hex,
        repository_id=repository.id,
        status="queued",
        stage="queued",
        progress_metadata={"files_processed": 0, "total_files": None},
        configuration={
            "profile": payload.profile,
            "ref": ref,
            "skills": payload.skills,
            "ai_questions_available": settings.ai_enabled,
            "ai_used_during_static_analysis": False,
        },
    )
    db.add(run)
    db.flush()
    _emit(db, run, "analysis_queued", {"repository_url": address.canonical_url})
    db.commit()
    db.refresh(run)
    background_tasks.add_task(run_analysis, run.id)
    return AnalysisQueued(
        id=run.id,
        repository_id=repository.id,
        status=run.status,
        stage=run.stage,
        events_url=str(request.url_for("stream_analysis_events", analysis_id=run.id)),
        analysis_url=str(request.url_for("get_analysis", analysis_id=run.id)),
    )


@router.get("/analyses")
def list_analyses(limit: int = Query(default=25, ge=1, le=100), db: Session = Depends(get_db)) -> dict[str, object]:
    runs = db.scalars(select(AnalysisRun).order_by(AnalysisRun.created_at.desc()).limit(limit)).all()
    return {"items": [_analysis_view(db, run) for run in runs]}


@router.get("/analyses/{analysis_id}", name="get_analysis")
def get_analysis(analysis_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    return _analysis_view(db, run)


@router.post("/analyses/{analysis_id}/questions")
def ask_about_analysis(
    analysis_id: str,
    payload: AnalysisQuestion,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Answer from bounded, redacted evidence belonging to the selected immutable snapshot."""
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    if run.status not in {"completed", "completed_with_warnings"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ANALYSIS_NOT_COMPLETE",
                "message": "As perguntas ficam disponíveis depois que a análise terminar com sucesso.",
            },
        )
    if not ai_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_NOT_CONFIGURED",
                "message": "A IA não está configurada. Defina AI_PROVIDER, AI_MODEL e as variáveis necessárias no .env e reinicie a API.",
            },
        )
    if payload.scope.node_ids:
        known_node_ids = set(
            db.scalars(
                select(GraphNode.id).where(
                    GraphNode.snapshot_id == run.snapshot_id,
                    GraphNode.id.in_(payload.scope.node_ids),
                )
            ).all()
        )
        if known_node_ids != set(payload.scope.node_ids):
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_NODE_SCOPE", "message": "Um ou mais nós não pertencem ao snapshot desta análise."},
            )
    if payload.scope.paths:
        all_source_paths = db.scalars(
            select(SourceFile.path).where(SourceFile.snapshot_id == run.snapshot_id).limit(20000)
        ).all()
        path_exists = {
            requested_path: any(
                source_path == requested_path or source_path.startswith(requested_path + "/")
                for source_path in all_source_paths
            )
            for requested_path in payload.scope.paths
        }
        if not all(path_exists.values()):
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_PATH_SCOPE", "message": "Os caminhos informados não pertencem ao snapshot desta análise."},
            )

    question_plan = classify_question(payload.question)
    evidence = retrieve_evidence(
        db,
        run,
        payload.question,
        node_ids=payload.scope.node_ids or None,
        paths=payload.scope.paths or None,
        intent=question_plan.intent,
    )
    if not evidence:
        return {
            "answer": "Não encontrei evidências suficientes no conteúdo persistido para responder a essa pergunta. Tente usar nomes de módulos, símbolos ou caminhos que existam no mapa.",
            "citations": [],
            "insufficient_evidence": True,
            "evidence_count": 0,
            "provider": settings.ai_provider,
            "model": settings.ai_model,
            "question_intent": question_plan.intent,
            "question_intent_label": question_plan.label,
            "retrieval_strategy": question_plan.strategy,
            "retrieved_kinds": [],
            "notice": "Nenhum trecho foi enviado ao provedor porque a recuperação não encontrou evidências relevantes. A classificação da pergunta não garante cobertura do repositório.",
        }

    context = [item.to_dict() for item in evidence]
    try:
        generated = generate_answer(
            payload.question, context, intent=question_plan.intent, intent_guidance=question_plan.guidance
        )
    except AIProviderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    by_id = {item.id: item for item in evidence}
    valid_ids: list[str] = []
    for citation_id in generated.citation_ids:
        if citation_id in by_id and citation_id not in valid_ids:
            valid_ids.append(citation_id)
    insufficient = generated.insufficient_evidence or not valid_ids
    allowed_markers = {f"[{citation_id}]" for citation_id in valid_ids}
    answer = re.sub(
        r"\[E[0-9]+\]",
        lambda match: match.group(0) if match.group(0) in allowed_markers else "",
        generated.answer,
    )
    if not valid_ids:
        answer = (
            "A resposta do provedor não trouxe referências verificáveis para as evidências recuperadas. "
            "Não vou apresentar a conclusão como confirmada; reformule a pergunta ou investigue os arquivos no inspetor."
        )
    citation_views = [by_id[item].to_dict() for item in valid_ids]
    return {
        "answer": answer,
        "citations": citation_views,
        "insufficient_evidence": insufficient,
        "evidence_count": len(evidence),
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "question_intent": question_plan.intent,
        "question_intent_label": question_plan.label,
        "retrieval_strategy": question_plan.strategy,
        "retrieved_kinds": sorted({item.kind for item in evidence}),
        "notice": "A resposta usa apenas trechos redigidos recuperados para esta pergunta. Revise se as fontes realmente sustentam cada conclusão; a existência de uma citação não garante correção semântica.",
    }


def _question_sse_frame(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _question_trace_steps(
    db: Session,
    run: AnalysisRun,
    evidence: list[Any],
    cited_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Map retrieved evidence to graph nodes without exposing source excerpts in progress events."""
    cited = cited_ids or set()
    paths = list(dict.fromkeys(item.path for item in evidence if item.path))
    if not run.snapshot_id or not paths:
        node_groups: dict[str, list[GraphNode]] = {}
    else:
        source_rows = db.scalars(
            select(SourceFile).where(
                SourceFile.snapshot_id == run.snapshot_id,
                SourceFile.path.in_(paths),
            )
        ).all()
        source_ids = [source.id for source in source_rows]
        node_rows = db.scalars(
            select(GraphNode)
            .where(
                GraphNode.snapshot_id == run.snapshot_id,
                GraphNode.source_file_id.in_(source_ids),
            )
            .order_by(GraphNode.node_type, GraphNode.start_line, GraphNode.label)
        ).all() if source_ids else []
        node_groups = {path: [] for path in paths}
        source_path_by_id = {source.id: source.path for source in source_rows}
        for node in node_rows:
            path = source_path_by_id.get(node.source_file_id or "")
            if path:
                node_groups.setdefault(path, []).append(node)

    steps: list[dict[str, Any]] = []
    for rank, item in enumerate(evidence, start=1):
        path_nodes = node_groups.get(item.path or "", [])
        file_nodes = [node for node in path_nodes if node.node_type == "file"]
        if item.start_line is not None and item.end_line is not None:
            line_nodes = [
                node for node in path_nodes
                if node.node_type != "file"
                and node.start_line is not None
                and node.end_line is not None
                and node.start_line <= item.end_line
                and node.end_line >= item.start_line
            ]
        else:
            line_nodes = [node for node in path_nodes if node.node_type != "file"][:6]
        selected_nodes = file_nodes[:1] + line_nodes[:9]
        if not selected_nodes:
            selected_nodes = path_nodes[:8]
        steps.append({
            "evidence_id": item.id,
            "rank": rank,
            "kind": item.kind,
            "path": item.path,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "node_ids": list(dict.fromkeys(node.id for node in selected_nodes))[:10],
            "cited": item.id in cited,
        })
    return steps


@router.post("/analyses/{analysis_id}/questions/stream")
def stream_question_about_analysis(
    analysis_id: str,
    payload: AnalysisQuestion,
) -> StreamingResponse:
    """Stream real retrieval steps first, then the answer; no private model reasoning is exposed."""
    def event_stream():
        yield _question_sse_frame("question_started", {"stage": "validating_and_retrieving"})
        with SessionLocal() as stream_db:
            run = stream_db.get(AnalysisRun, analysis_id)
            if run is None:
                yield _question_sse_frame("question_error", {"code": "ANALYSIS_NOT_FOUND", "message": "A análise solicitada não foi encontrada.", "status": 404})
                return
            if run.status not in {"completed", "completed_with_warnings"}:
                yield _question_sse_frame("question_error", {"code": "ANALYSIS_NOT_COMPLETE", "message": "As perguntas ficam disponíveis depois que a análise terminar com sucesso.", "status": 409})
                return
            if not ai_is_configured():
                yield _question_sse_frame("question_error", {"code": "AI_NOT_CONFIGURED", "message": "A IA não está configurada. Configure o provedor e reinicie a API.", "status": 503})
                return
            if payload.scope.node_ids:
                known_node_ids = set(stream_db.scalars(
                    select(GraphNode.id).where(
                        GraphNode.snapshot_id == run.snapshot_id,
                        GraphNode.id.in_(payload.scope.node_ids),
                    )
                ).all())
                if known_node_ids != set(payload.scope.node_ids):
                    yield _question_sse_frame("question_error", {"code": "INVALID_NODE_SCOPE", "message": "Um ou mais nós não pertencem ao snapshot desta análise.", "status": 422})
                    return
            if payload.scope.paths:
                source_paths = stream_db.scalars(
                    select(SourceFile.path).where(SourceFile.snapshot_id == run.snapshot_id).limit(20000)
                ).all()
                valid_paths = {
                    requested: any(path == requested or path.startswith(requested + "/") for path in source_paths)
                    for requested in payload.scope.paths
                }
                if not all(valid_paths.values()):
                    yield _question_sse_frame("question_error", {"code": "INVALID_PATH_SCOPE", "message": "Os caminhos informados não pertencem ao snapshot desta análise.", "status": 422})
                    return

            question_plan = classify_question(payload.question)
            evidence = retrieve_evidence(
                stream_db,
                run,
                payload.question,
                node_ids=payload.scope.node_ids or None,
                paths=payload.scope.paths or None,
                intent=question_plan.intent,
            )
            initial_trace = _question_trace_steps(stream_db, run, evidence)
            yield _question_sse_frame("question_retrieval", {
                "question_intent": question_plan.intent,
                "question_intent_label": question_plan.label,
                "retrieval_strategy": question_plan.strategy,
                "evidence_count": len(evidence),
                "steps": initial_trace,
            })

            if not evidence:
                yield _question_sse_frame("question_answer", {
                    "answer": "Não encontrei evidências suficientes no conteúdo persistido para responder a essa pergunta. Tente usar nomes de módulos, símbolos ou caminhos que existam no mapa.",
                    "citations": [],
                    "insufficient_evidence": True,
                    "evidence_count": 0,
                    "provider": settings.ai_provider,
                    "model": settings.ai_model,
                    "question_intent": question_plan.intent,
                    "question_intent_label": question_plan.label,
                    "retrieval_strategy": question_plan.strategy,
                    "retrieved_kinds": [],
                    "retrieval_trace": [],
                    "notice": "Nenhum trecho foi enviado ao provedor porque a recuperação não encontrou evidências relevantes.",
                })
                return

            context = [item.to_dict() for item in evidence]
            try:
                generated = generate_answer(
                    payload.question,
                    context,
                    intent=question_plan.intent,
                    intent_guidance=question_plan.guidance,
                )
            except AIProviderError as exc:
                yield _question_sse_frame("question_error", {"code": exc.code, "message": exc.message, "status": exc.status_code})
                return

            by_id = {item.id: item for item in evidence}
            valid_ids: list[str] = []
            for citation_id in generated.citation_ids:
                if citation_id in by_id and citation_id not in valid_ids:
                    valid_ids.append(citation_id)
            insufficient = generated.insufficient_evidence or not valid_ids
            allowed_markers = {f"[{citation_id}]" for citation_id in valid_ids}
            answer = re.sub(
                r"\[E[0-9]+\]",
                lambda match: match.group(0) if match.group(0) in allowed_markers else "",
                generated.answer,
            )
            if not valid_ids:
                answer = (
                    "A resposta do provedor não trouxe referências verificáveis para as evidências recuperadas. "
                    "Não vou apresentar a conclusão como confirmada; reformule a pergunta ou investigue os arquivos no inspetor."
                )
            trace = _question_trace_steps(stream_db, run, evidence, set(valid_ids))
            yield _question_sse_frame("question_answer", {
                "answer": answer,
                "citations": [by_id[item].to_dict() for item in valid_ids],
                "insufficient_evidence": insufficient,
                "evidence_count": len(evidence),
                "provider": settings.ai_provider,
                "model": settings.ai_model,
                "question_intent": question_plan.intent,
                "question_intent_label": question_plan.label,
                "retrieval_strategy": question_plan.strategy,
                "retrieved_kinds": sorted({item.kind for item in evidence}),
                "retrieval_trace": trace,
                "notice": "A trilha mostra as fontes recuperadas e citadas, não o raciocínio interno do modelo. A existência de uma citação não garante correção semântica.",
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/analyses/{analysis_id}/graph")
def get_graph(
    analysis_id: str,
    node_type: str | None = Query(default=None, max_length=40),
    relation_type: str | None = Query(default=None, max_length=40),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=2000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0, le=1000000),
    edge_limit: int = Query(default=4000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a bounded graph slice, with explicit counts and server-side filters."""
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    if run.snapshot_id is None:
        return {
            "nodes": [], "edges": [], "total_nodes": 0, "total_edges": 0,
            "repository_total_nodes": 0, "repository_total_edges": 0,
            "offset": offset, "page_size": limit, "has_more_nodes": False,
            "returned_nodes": 0, "returned_edges": 0,
            "eligible_edges_for_returned_nodes": 0,
            "truncated_nodes": False, "truncated_edges": False, "truncated": False,
        }

    snapshot_id = run.snapshot_id
    repository_total_nodes = db.scalar(
        select(func.count()).select_from(GraphNode).where(GraphNode.snapshot_id == snapshot_id)
    ) or 0
    repository_total_edges = db.scalar(
        select(func.count()).select_from(GraphEdge).where(GraphEdge.snapshot_id == snapshot_id)
    ) or 0

    node_query = select(GraphNode).where(GraphNode.snapshot_id == snapshot_id)
    if node_type:
        node_query = node_query.where(GraphNode.node_type == node_type)
    search_term = (q or "").strip()
    if search_term:
        # Search labels/stable keys and source paths on the server, so matches beyond the
        # first page of nodes can be returned. Parameters are escaped by SQLAlchemy.
        escaped_term = search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_term = f"%{escaped_term}%"
        matching_source_ids = select(SourceFile.id).where(
            SourceFile.snapshot_id == snapshot_id,
            SourceFile.path.ilike(like_term, escape="\\"),
        )
        node_query = node_query.where(
            or_(
                GraphNode.label.ilike(like_term, escape="\\"),
                GraphNode.stable_key.ilike(like_term, escape="\\"),
                GraphNode.source_file_id.in_(matching_source_ids),
            )
        )

    # total_nodes is the number matching the active server-side filters. Keep the complete
    # snapshot totals separately, so UI can distinguish filtered search results from coverage.
    total_nodes = db.scalar(select(func.count()).select_from(node_query.subquery())) or 0
    nodes = db.scalars(node_query.order_by(GraphNode.node_type, GraphNode.label).offset(offset).limit(limit)).all()
    selected_ids = [node.id for node in nodes]
    file_ids = {node.source_file_id for node in nodes if node.source_file_id}
    files = db.scalars(select(SourceFile).where(SourceFile.id.in_(file_ids))).all() if file_ids else []
    file_paths = {file.id: file.path for file in files}

    all_edge_query = select(GraphEdge).where(GraphEdge.snapshot_id == snapshot_id)
    if relation_type:
        all_edge_query = all_edge_query.where(GraphEdge.relation_type == relation_type)
    total_edges = db.scalar(select(func.count()).select_from(all_edge_query.subquery())) or 0

    # Only edges with both endpoints in the returned node set can be drawn in this view.
    visible_edge_query = all_edge_query
    if selected_ids:
        visible_edge_query = visible_edge_query.where(
            GraphEdge.source_node_id.in_(selected_ids),
            GraphEdge.target_node_id.in_(selected_ids),
        )
        eligible_edges = db.scalar(
            select(func.count()).select_from(visible_edge_query.subquery())
        ) or 0
        edges = db.scalars(
            visible_edge_query.order_by(GraphEdge.relation_type, GraphEdge.id).limit(edge_limit)
        ).all()
    else:
        eligible_edges = 0
        edges = []

    truncated_nodes = total_nodes > offset + len(nodes)
    truncated_edges = eligible_edges > len(edges)
    return {
        "nodes": [_graph_node_view(node, file_paths) for node in nodes],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "type": edge.relation_type,
                "provenance_type": edge.provenance_type,
                "confidence_label": edge.confidence_label,
                "evidence": edge.evidence,
            }
            for edge in edges
        ],
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "offset": offset,
        "page_size": limit,
        "has_more_nodes": truncated_nodes,
        "repository_total_nodes": repository_total_nodes,
        "repository_total_edges": repository_total_edges,
        "returned_nodes": len(nodes),
        "returned_edges": len(edges),
        "eligible_edges_for_returned_nodes": eligible_edges,
        "truncated_nodes": truncated_nodes,
        "truncated_edges": truncated_edges,
        "truncated": truncated_nodes or truncated_edges,
    }


@router.get("/analyses/{analysis_id}/nodes/{node_id}")
def get_node_detail(analysis_id: str, node_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(AnalysisRun, analysis_id)
    if run is None or run.snapshot_id is None:
        raise _not_found()
    node = db.scalar(
        select(GraphNode).where(
            GraphNode.id == node_id,
            GraphNode.snapshot_id == run.snapshot_id,
        )
    )
    if node is None:
        raise HTTPException(status_code=404, detail={"code": "NODE_NOT_FOUND", "message": "O nó não pertence a esta análise."})
    source_file = db.get(SourceFile, node.source_file_id) if node.source_file_id else None
    lines = (source_file.redacted_content or "").splitlines() if source_file else []
    if node.start_line:
        start = max(1, node.start_line - 3)
        end = min(len(lines), max(node.end_line or node.start_line, node.start_line) + 3)
    else:
        start = 1
        end = min(len(lines), 80)
    code = "\n".join(f"{line_number:>4}  {lines[line_number - 1]}" for line_number in range(start, end + 1))
    snapshot = db.get(RepositorySnapshot, run.snapshot_id)
    evidence_url = None
    if source_file and snapshot:
        evidence_url = f"https://github.com/{db.get(Repository, run.repository_id).owner}/{db.get(Repository, run.repository_id).name}/blob/{snapshot.commit_sha}/{source_file.path}"
        if node.start_line:
            evidence_url += f"#L{node.start_line}"
    return {
        "node": _graph_node_view(node, {source_file.id: source_file.path} if source_file else {}),
        "commit_sha": snapshot.commit_sha if snapshot else None,
        "evidence_url": evidence_url,
        "code": code,
        "code_start_line": start if code else None,
        "redacted": True,
        "message": None if code else "Nenhum trecho textual associado a este nó foi persistido.",
    }


@router.get("/analyses/{analysis_id}/findings")
def get_findings(
    analysis_id: str,
    severity: str | None = Query(default=None, max_length=30),
    skill_id: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    query = select(Finding).where(Finding.analysis_run_id == analysis_id)
    if severity:
        query = query.where(Finding.severity == severity.upper())
    if skill_id:
        query = query.where(Finding.skill_id == skill_id)
    if status:
        query = query.where(Finding.status == status)
    findings = db.scalars(query.order_by(Finding.created_at.desc())).all()
    return {
        "items": [
            {
                "id": item.id,
                "skill_id": item.skill_id,
                "skill_version": item.skill_version,
                "finding_key": item.finding_key,
                "category": item.category,
                "severity": item.severity,
                "status": item.status,
                "confidence_label": item.confidence_label,
                "title": item.title,
                "summary": item.summary,
                "impact": item.impact,
                "recommendation": item.recommendation,
                "limitations": item.limitations,
                "evidence": item.evidence,
            }
            for item in findings
        ],
        "total": len(findings),
    }


@router.patch("/analyses/{analysis_id}/findings/{finding_id}/status")
def update_finding_status(
    analysis_id: str,
    finding_id: str,
    payload: FindingStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Persist a human review decision for one finding in one completed analysis."""
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    if run.status not in TERMINAL_STATES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ANALYSIS_NOT_COMPLETE",
                "message": "A revisão dos achados fica disponível após o término da análise.",
            },
        )
    finding = db.scalar(
        select(Finding).where(
            Finding.id == finding_id,
            Finding.analysis_run_id == analysis_id,
        )
    )
    if finding is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "FINDING_NOT_FOUND", "message": "O achado não pertence a esta análise."},
        )

    previous_status = finding.status
    if previous_status == payload.status:
        return {
            "id": finding.id,
            "finding_key": finding.finding_key,
            "previous_status": previous_status,
            "status": finding.status,
            "changed": False,
        }

    finding.status = payload.status
    if run.snapshot_id:
        stable_key = f"finding:{run.id}:{finding.finding_key}"
        finding_node = db.scalar(
            select(GraphNode).where(
                GraphNode.snapshot_id == run.snapshot_id,
                GraphNode.stable_key == stable_key,
            )
        )
        if finding_node is not None:
            finding_node.properties = {**finding_node.properties, "status": payload.status}

    # This event is an audit trail for local review, not an assertion that the finding is fixed.
    _emit(
        db,
        run,
        "finding_status_changed",
        {
            "finding_id": finding.id,
            "finding_key": finding.finding_key,
            "previous_status": previous_status,
            "status": payload.status,
        },
    )
    db.commit()
    return {
        "id": finding.id,
        "finding_key": finding.finding_key,
        "previous_status": previous_status,
        "status": finding.status,
        "changed": True,
    }


@router.get("/analyses/{analysis_id}/events", name="stream_analysis_events")
def stream_analysis_events(
    analysis_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    if db.get(AnalysisRun, analysis_id) is None:
        raise _not_found()
    try:
        last_seen = max(after, int(last_event_id or "0"))
    except ValueError:
        last_seen = after

    def event_stream():
        nonlocal last_seen
        # Tell EventSource when to reconnect if the connection drops. The persisted
        # sequence cursor and Last-Event-ID header provide replay without guessing progress.
        yield "retry: 1500\n\n"
        started = time.monotonic()
        while time.monotonic() - started < 1800:
            with SessionLocal() as stream_db:
                run = stream_db.get(AnalysisRun, analysis_id)
                if run is None:
                    break
                events = stream_db.scalars(
                    select(AnalysisEvent)
                    .where(
                        AnalysisEvent.analysis_run_id == analysis_id,
                        AnalysisEvent.sequence_number > last_seen,
                    )
                    .order_by(AnalysisEvent.sequence_number)
                    .limit(100)
                ).all()
                terminal = run.status in TERMINAL_STATES
            if events:
                for item in events:
                    last_seen = item.sequence_number
                    payload = json.dumps(item.payload, ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {item.sequence_number}\nevent: {item.event_type}\ndata: {payload}\n\n"
            elif terminal:
                break
            else:
                yield ": keep-alive\n\n"
                time.sleep(0.75)
        yield "event: stream_end\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _report_for_analysis(db: Session, run: AnalysisRun) -> str:
    if not run.snapshot_id:
        raise HTTPException(status_code=409, detail={"code": "SNAPSHOT_NOT_READY", "message": "O snapshot ainda não está disponível para exportação."})
    repository = db.get(Repository, run.repository_id)
    snapshot = db.get(RepositorySnapshot, run.snapshot_id)
    if repository is None or snapshot is None:
        raise _not_found()
    source_files = db.scalars(select(SourceFile).where(SourceFile.snapshot_id == snapshot.id).order_by(SourceFile.path)).all()
    nodes = db.scalars(select(GraphNode).where(GraphNode.snapshot_id == snapshot.id)).all()
    edges = db.scalars(select(GraphEdge).where(GraphEdge.snapshot_id == snapshot.id)).all()
    findings = db.scalars(select(Finding).where(Finding.analysis_run_id == run.id)).all()
    return generate_markdown(
        repository=repository,
        snapshot=snapshot,
        analysis=run,
        source_files=source_files,
        nodes=nodes,
        edges=edges,
        findings=findings,
    )


@router.get("/analyses/{analysis_id}/export/markdown")
def export_markdown(analysis_id: str, db: Session = Depends(get_db)) -> Response:
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    markdown = _report_for_analysis(db, run)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="YGGDRASIL-MAP-{analysis_id[:8]}.md"'},
    )

@router.post("/analyses/{analysis_id}/exports/markdown", status_code=201)
def create_markdown_export(
    analysis_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = db.get(AnalysisRun, analysis_id)
    if run is None:
        raise _not_found()
    markdown = _report_for_analysis(db, run)
    export = ReportExport(
        id=uuid4().hex,
        analysis_run_id=run.id,
        format="markdown",
        report_version="0.7.0",
        redaction_summary={"secret_values_included": False, "source_content_redacted_before_persistence": True},
        markdown_content=markdown,
    )
    db.add(export)
    db.commit()
    return {
        "id": export.id,
        "format": export.format,
        "report_version": export.report_version,
        "created_at": export.created_at,
        "download_url": str(request.url_for("get_export", export_id=export.id)),
        "file_name": f"YGGDRASIL-MAP-{analysis_id[:8]}.md",
    }


@router.get("/exports/{export_id}", name="get_export")
def get_export(export_id: str, db: Session = Depends(get_db)) -> Response:
    export = db.get(ReportExport, export_id)
    if export is None:
        raise HTTPException(status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": "O relatório solicitado não foi encontrado."})
    return Response(
        content=export.markdown_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="YGGDRASIL-REPORT-{export.id[:8]}.md"'},
    )

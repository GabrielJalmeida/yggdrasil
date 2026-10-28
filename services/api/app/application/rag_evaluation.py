"""Offline evaluation of lexical/structural RAG retrieval against human-labelled cases.

This module measures evidence retrieval only. It never calls an AI provider, persists
conversation data, or includes source excerpts in the resulting report.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.questions import (
    INTENT_LABELS,
    RetrievedEvidence,
    classify_question,
    retrieve_evidence,
)
from app.models import AnalysisRun, Repository, RepositorySnapshot, SourceFile

_CORPUS_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")
_ALLOWED_ANSWERABILITY = {"answerable", "insufficient_evidence", "manual_review"}


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    question: str
    expected_intent: str | None
    expected_paths: tuple[str, ...]
    answerability: str = "answerable"
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationCorpus:
    corpus_id: str
    version: str
    description: str
    target_repository: str | None
    cases: tuple[EvaluationCase, ...]


def load_corpus(path: str | Path) -> EvaluationCorpus:
    """Load and validate a JSON corpus. Paths are repository-relative labels, not IO paths."""
    corpus_path = Path(path)
    try:
        raw = json.loads(corpus_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Não foi possível ler o corpus: {corpus_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no corpus (linha {exc.lineno}).") from exc

    if not isinstance(raw, dict):
        raise ValueError("O corpus precisa ser um objeto JSON.")
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version ausente ou não suportado; versão aceita: 1.")

    corpus_id = raw.get("corpus_id")
    version = raw.get("version")
    description = raw.get("description")
    cases_raw = raw.get("cases")
    target_repository = raw.get("target_repository")
    if not isinstance(corpus_id, str) or not _CORPUS_ID.fullmatch(corpus_id):
        raise ValueError("corpus_id inválido; use 2–80 caracteres alfanuméricos, ponto, hífen ou underscore.")
    if not isinstance(version, str) or not version.strip() or len(version) > 30:
        raise ValueError("version do corpus precisa ser uma string curta não vazia.")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description do corpus é obrigatória.")
    if target_repository is not None and (not isinstance(target_repository, str) or len(target_repository) > 200):
        raise ValueError("target_repository precisa ser string ou null.")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("O corpus precisa conter pelo menos um caso.")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(cases_raw):
        prefix = f"cases[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{prefix} precisa ser um objeto.")
        case_id = item.get("id")
        question = item.get("question")
        expected_intent = item.get("expected_intent")
        expected_paths_raw = item.get("expected_paths", [])
        answerability = item.get("answerability", "answerable")
        notes = item.get("notes")

        if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
            raise ValueError(f"{prefix}.id inválido.")
        if case_id in seen_ids:
            raise ValueError(f"ID de caso duplicado: {case_id}.")
        seen_ids.add(case_id)
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError(f"{prefix}.question precisa ter entre 1 e 2000 caracteres.")
        if expected_intent is not None and (not isinstance(expected_intent, str) or expected_intent not in INTENT_LABELS):
            raise ValueError(f"{prefix}.expected_intent não reconhecido.")
        if not isinstance(expected_paths_raw, list) or any(not isinstance(p, str) for p in expected_paths_raw):
            raise ValueError(f"{prefix}.expected_paths precisa ser uma lista de caminhos.")
        expected_paths = tuple(dict.fromkeys(_normalize_repo_path(p, prefix) for p in expected_paths_raw))
        if not isinstance(answerability, str) or answerability not in _ALLOWED_ANSWERABILITY:
            raise ValueError(f"{prefix}.answerability inválida.")
        if answerability == "answerable" and not expected_paths:
            raise ValueError(f"{prefix} precisa rotular ao menos um expected_path quando answerable.")
        if answerability == "insufficient_evidence" and expected_paths:
            raise ValueError(f"{prefix} não deve listar expected_paths quando insufficient_evidence.")
        if notes is not None and (not isinstance(notes, str) or len(notes) > 1000):
            raise ValueError(f"{prefix}.notes precisa ser string de até 1000 caracteres ou null.")
        cases.append(EvaluationCase(
            id=case_id,
            question=question.strip(),
            expected_intent=expected_intent,
            expected_paths=expected_paths,
            answerability=answerability,
            notes=notes,
        ))

    return EvaluationCorpus(
        corpus_id=corpus_id,
        version=version,
        description=description.strip(),
        target_repository=target_repository,
        cases=tuple(cases),
    )


def find_latest_completed_analysis(db: Session, corpus: EvaluationCorpus) -> AnalysisRun | None:
    """Find the newest completed run for the repository explicitly labelled by a corpus.

    Requiring a corpus target prevents accidentally evaluating a different repository's
    latest analysis when using the Docker CLI without an explicit analysis ID.
    """
    if not corpus.target_repository:
        raise ValueError("A opção --latest exige target_repository no corpus (formato owner/repo).")

    parts = corpus.target_repository.split("/")
    if len(parts) != 2 or any(not part or part.strip() != part or any(ch.isspace() for ch in part) for part in parts):
        raise ValueError("target_repository precisa estar no formato owner/repo para usar --latest.")
    owner, name = parts

    return db.scalar(
        select(AnalysisRun)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .where(
            func.lower(Repository.owner) == owner.casefold(),
            func.lower(Repository.name) == name.casefold(),
            AnalysisRun.status.in_(("completed", "completed_with_warnings")),
        )
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(1)
    )

def _normalize_repo_path(value: str, prefix: str) -> str:
    path = value.strip().replace("\\", "/")
    parts = path.split("/") if path else []
    if (
        not path
        or path.startswith("/")
        or path.endswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"{prefix}.expected_paths contém caminho de repositório inválido.")
    if "\x00" in path or len(path) > 1024:
        raise ValueError(f"{prefix}.expected_paths contém caminho inválido ou longo demais.")
    return path


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _metrics(results: list[dict[str, Any]], k_values: tuple[int, ...]) -> dict[str, Any]:
    labelled = [item for item in results if item["scored"]]
    metrics: dict[str, Any] = {
        "cases_total": len(results),
        "answerable_cases": sum(item["answerability"] == "answerable" for item in results),
        "scored_cases": len(labelled),
        "invalid_annotations": sum(item["annotation_status"] != "valid" for item in results if item["answerability"] == "answerable"),
        "intent_accuracy": _mean([
            1.0 if item["detected_intent"] == item["expected_intent"] else 0.0
            for item in results if item["expected_intent"] is not None
        ]),
        "mrr": _mean([item["reciprocal_rank"] for item in labelled]),
        "limitations": [
            "Mede recuperação de evidências, não a correção semântica da resposta gerada.",
            "Recall usa apenas os caminhos rotulados; caminhos relevantes não anotados não entram no denominador.",
            "Casos insufficient_evidence/manual_review não são pontuados quanto à abstinência do modelo.",
        ],
    }
    for k in k_values:
        metrics[f"hit_at_{k}"] = _mean([item[f"hit_at_{k}"] for item in labelled])
        metrics[f"recall_at_{k}"] = _mean([item[f"recall_at_{k}"] for item in labelled])
    return metrics


def evaluate_corpus(
    db: Session,
    run: AnalysisRun,
    corpus: EvaluationCorpus,
    *,
    k_values: tuple[int, ...] = (1, 3, 5),
) -> dict[str, Any]:
    """Evaluate retrieval for one analysis snapshot using only local persisted data."""
    if not run.snapshot_id:
        raise ValueError("A análise escolhida não está vinculada a um snapshot.")
    if not k_values or any(not isinstance(k, int) or k < 1 for k in k_values):
        raise ValueError("k_values precisa conter inteiros positivos.")
    k_values = tuple(sorted(set(k_values)))

    repository = db.get(Repository, run.repository_id)
    snapshot = db.get(RepositorySnapshot, run.snapshot_id)
    if snapshot is None:
        raise ValueError("O snapshot da análise não existe mais.")
    if corpus.target_repository:
        if repository is None:
            raise ValueError("A análise não está vinculada a um repositório identificável.")
        actual_slug = f"{repository.owner}/{repository.name}"
        if actual_slug.casefold() != corpus.target_repository.casefold():
            raise ValueError(
                f"O corpus está rotulado para {corpus.target_repository}, mas a análise é {actual_slug}. "
                "Escolha uma análise do repositório correto ou use um corpus sem target_repository."
            )

    source_rows = db.scalars(select(SourceFile).where(SourceFile.snapshot_id == run.snapshot_id)).all()
    existing_paths = {source.path for source in source_rows}
    available_paths = {source.path for source in source_rows if source.redacted_content is not None}
    results: list[dict[str, Any]] = []
    for case in corpus.cases:
        detected = classify_question(case.question).intent
        missing_paths = [path for path in case.expected_paths if path not in existing_paths]
        unavailable_paths = [
            path for path in case.expected_paths if path in existing_paths and path not in available_paths
        ]
        if case.answerability == "answerable" and (missing_paths or unavailable_paths):
            annotation_status = "invalid_missing_paths" if missing_paths else "invalid_unavailable_paths"
            results.append({
                "id": case.id,
                "question": case.question,
                "answerability": case.answerability,
                "expected_intent": case.expected_intent,
                "detected_intent": detected,
                "intent_match": None if case.expected_intent is None else detected == case.expected_intent,
                "annotation_status": annotation_status,
                "missing_expected_paths": missing_paths,
                "missing_from_snapshot_paths": missing_paths,
                "unavailable_expected_paths": unavailable_paths,
                "not_retrieved_expected_paths": [],
                "expected_paths": list(case.expected_paths),
                "retrieved_paths": [],
                "evidence_count": 0,
                "scored": False,
                "notes": case.notes,
            })
            continue

        evidence: list[RetrievedEvidence] = retrieve_evidence(db, run, case.question)
        path_ranks: dict[str, int] = {}
        for item in evidence:
            if item.path and item.path not in path_ranks:
                # Score unique files, not evidence chunks: repeated snippets from the
                # same file must not push other files artificially down the ranking.
                path_ranks[item.path] = len(path_ranks) + 1
        retrieved_paths = list(path_ranks)
        response: dict[str, Any] = {
            "id": case.id,
            "question": case.question,
            "answerability": case.answerability,
            "expected_intent": case.expected_intent,
            "detected_intent": detected,
            "intent_match": None if case.expected_intent is None else detected == case.expected_intent,
            "annotation_status": "valid" if case.answerability == "answerable" else "not_scored_for_retrieval_recall",
            "missing_expected_paths": [],
            "missing_from_snapshot_paths": [],
            "unavailable_expected_paths": [],
            "not_retrieved_expected_paths": [],
            "expected_paths": list(case.expected_paths),
            "retrieved_paths": retrieved_paths,
            "evidence_count": len(evidence),
            "scored": case.answerability == "answerable",
            "notes": case.notes,
        }
        if case.answerability == "answerable":
            expected = set(case.expected_paths)
            response["not_retrieved_expected_paths"] = [
                path for path in case.expected_paths if path not in path_ranks
            ]
            matched_ranks = [rank for path, rank in path_ranks.items() if path in expected]
            first_rank = min(matched_ranks) if matched_ranks else None
            response["expected_path_ranks"] = {path: path_ranks[path] for path in case.expected_paths if path in path_ranks}
            response["reciprocal_rank"] = round(1.0 / first_rank, 4) if first_rank else 0.0
            for k in k_values:
                found = {path for path, rank in path_ranks.items() if path in expected and rank <= k}
                response[f"hit_at_{k}"] = 1.0 if found else 0.0
                response[f"recall_at_{k}"] = round(len(found) / len(expected), 4)
        else:
            response["response_evaluation"] = "not_run"
        results.append(response)

    return {
        "report_schema_version": 1,
        "corpus": {
            "id": corpus.corpus_id,
            "version": corpus.version,
            "description": corpus.description,
            "target_repository": corpus.target_repository,
        },
        "analysis": {
            "id": run.id,
            "repository": f"{repository.owner}/{repository.name}" if repository else None,
            "commit_sha": snapshot.commit_sha,
            "requested_ref": snapshot.requested_ref,
        },
        "configuration": {"k_values": list(k_values), "provider_calls": 0, "source_excerpts_included": False},
        "metrics": _metrics(results, k_values),
        "warnings": [],
        "cases": results,
    }

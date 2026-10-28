#!/usr/bin/env python3
"""Run a bounded, human-reviewed quality evaluation through Yggdrasil's question API.

Unlike evaluate_rag.py, this script calls the configured model provider when
--run-provider is passed. It records answer latency, snapshot metadata, retrieval
paths, citation metadata, and review prompts without storing retrieved excerpts.
Semantic correctness remains a human review task.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from math import ceil
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.application.questions import retrieve_evidence  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.infrastructure.ai_provider import ai_is_configured  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AnalysisRun, Repository, RepositorySnapshot  # noqa: E402

_DEFAULT_CASES = API_ROOT / "evaluation" / "corpora" / "borax-answer-quality.json"
_EXPECTED_SECURITY_LIMITATION = (
    "nao prova",
    "nao comprova",
    "nao garante",
    "nao e possivel afirmar",
    "nao e possivel concluir",
    "nao demonstra ausencia",
    "nao permite afirmar",
    "nao permite concluir",
    "nao pode provar",
    "nao significa que",
    "nao e uma prova",
    "analise estatica nao",
)
_POTENTIAL_UNSAFE_CLAIMS = (
    "livre de todas as vulnerabilidades",
    "livre de vulnerabilidades",
    "sem vulnerabilidades",
    "completamente seguro",
    "totalmente seguro",
    "garante a seguranca",
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _load_cases(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Não foi possível ler o corpus: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no corpus (linha {exc.lineno}).") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("O corpus precisa ser um objeto JSON com schema_version 1.")
    if not isinstance(raw.get("cases"), list) or not raw["cases"]:
        raise ValueError("O corpus precisa ter uma lista cases não vazia.")
    ids: set[str] = set()
    for index, case in enumerate(raw["cases"]):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] precisa ser um objeto.")
        case_id = case.get("id")
        question = case.get("question")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,99}", case_id):
            raise ValueError(f"cases[{index}].id inválido.")
        if case_id in ids:
            raise ValueError(f"ID de caso duplicado: {case_id}.")
        ids.add(case_id)
        if not isinstance(question, str) or not question.strip() or len(question) > 1500:
            raise ValueError(f"cases[{index}].question precisa ter de 1 a 1500 caracteres.")
        expected_paths = case.get("expected_paths", [])
        if not isinstance(expected_paths, list) or any(not isinstance(item, str) for item in expected_paths):
            raise ValueError(f"cases[{index}].expected_paths precisa ser uma lista de strings.")
        if case.get("answerability") not in {"answerable", "answerable_with_test_defect", "insufficient_evidence"}:
            raise ValueError(f"cases[{index}].answerability inválida.")
    return raw


def _select_cases(case_definitions: list[dict[str, Any]], selected_ids: list[str] | None) -> list[dict[str, Any]]:
    """Return requested cases in CLI order, raising on unknown IDs."""
    if not selected_ids:
        return list(case_definitions)
    by_id = {case["id"]: case for case in case_definitions}
    requested = list(dict.fromkeys(selected_ids))
    missing = [case_id for case_id in requested if case_id not in by_id]
    if missing:
        raise ValueError("IDs de caso não encontrados no corpus: " + ", ".join(missing))
    return [by_id[case_id] for case_id in requested]


def _find_analysis(db, analysis_id: str | None, repository_slug: str | None) -> AnalysisRun | None:
    if analysis_id:
        run = db.get(AnalysisRun, analysis_id)
        if run is None:
            return None
        repository = db.get(Repository, run.repository_id)
        if repository_slug and repository:
            actual_slug = f"{repository.owner}/{repository.name}"
            if actual_slug.casefold() != repository_slug.casefold():
                raise ValueError(f"A análise selecionada é {actual_slug}, mas o corpus espera {repository_slug}.")
        return run

    if not repository_slug:
        raise ValueError("--latest exige target_repository no corpus.")
    parts = repository_slug.split("/")
    if len(parts) != 2 or any(not part.strip() or part.strip() != part for part in parts):
        raise ValueError("target_repository precisa estar no formato owner/repo.")
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


_BRACKETED_CITATION_RE = re.compile(r"\[([^\]]*)\]")
_CITATION_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(?:E#E\d+|E\d+)(?![A-Za-z0-9_])")
_VALID_CITATION_GROUP_RE = re.compile(r"E\d+(?:\s*,\s*E\d+)*")


def _extract_answer_citation_markers(answer: str) -> tuple[list[str], list[str]]:
    """Extract `[E1]` and grouped `[E1, E2]` citations, separately flagging malformed tokens.

    A citation group is valid only when its entire bracket content is a comma-separated list
    of evidence IDs. Marker-like tokens outside valid groups remain malformed.
    """
    valid_positions: list[tuple[int, str]] = []
    malformed_positions: list[tuple[int, str]] = []
    cursor = 0

    for match in _BRACKETED_CITATION_RE.finditer(answer):
        for token in _CITATION_TOKEN_RE.finditer(answer, cursor, match.start()):
            malformed_positions.append((token.start(), token.group(0)))

        content = match.group(1).strip()
        content_offset = match.start(1) + (len(match.group(1)) - len(match.group(1).lstrip()))
        if _VALID_CITATION_GROUP_RE.fullmatch(content):
            for token in re.finditer(r"E\d+", content):
                valid_positions.append((content_offset + token.start(), token.group(0)))
        else:
            for token in _CITATION_TOKEN_RE.finditer(content):
                malformed_positions.append((content_offset + token.start(), token.group(0)))
        cursor = match.end()

    for token in _CITATION_TOKEN_RE.finditer(answer, cursor):
        malformed_positions.append((token.start(), token.group(0)))

    valid = [value for _, value in sorted(valid_positions)]
    malformed = [value for _, value in sorted(malformed_positions)]
    return list(dict.fromkeys(valid)), list(dict.fromkeys(malformed))

def _citation_record(citation: dict[str, Any]) -> dict[str, Any]:
    """Persist citation provenance without copying repository source excerpts."""
    return {
        key: citation.get(key)
        for key in ("id", "kind", "path", "start_line", "end_line", "commit_sha", "url")
    }


def _abstention_heuristic(answer: str, answerability: str) -> dict[str, Any]:
    if answerability != "insufficient_evidence":
        return {"expected": False, "status": "not_applicable", "signals": [], "possible_overclaim_signals": []}
    folded = _fold(answer)
    limitations = [phrase for phrase in _EXPECTED_SECURITY_LIMITATION if phrase in folded]
    negation_or_qualification = (
        "nao", "nunca", "sem prova", "sem evidencias", "nao permite", "nao significa",
        "nao garante", "nao comprova", "nao prova", "nao e possivel", "nao se pode",
        "impossivel afirmar", "not ", "cannot", "does not prove", "does not guarantee",
    )
    unsafe: list[str] = []
    for phrase in _POTENTIAL_UNSAFE_CLAIMS:
        start = 0
        while True:
            position = folded.find(phrase, start)
            if position < 0:
                break
            preceding = folded[max(0, position - 65):position]
            if not any(marker in preceding for marker in negation_or_qualification):
                unsafe.append(phrase)
                break
            start = position + len(phrase)
    if unsafe:
        status = "possible_overclaim_review_required"
    elif limitations:
        status = "limitation_language_detected_review_required"
    else:
        status = "no_obvious_limitation_signal_review_required"
    return {
        "expected": True,
        "status": status,
        "signals": limitations,
        "possible_overclaim_signals": unsafe,
        "note": "Sinal lexical para triagem; não é julgamento semântico nem aprovação automática.",
    }


def _response_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(case["latency_ms"]) for case in cases if isinstance(case.get("latency_ms"), (int, float))]
    latencies.sort()
    if not latencies:
        latency_summary: dict[str, float | int | None] = {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None}
    else:
        p95_index = min(len(latencies) - 1, max(0, ceil(0.95 * len(latencies)) - 1))
        latency_summary = {
            "count": len(latencies),
            "mean_ms": round(statistics.fmean(latencies), 1),
            "median_ms": round(statistics.median(latencies), 1),
            "p95_ms": round(latencies[p95_index], 1),
            "max_ms": round(max(latencies), 1),
        }

    answerable = [case for case in cases if case.get("retrieval", {}).get("expected_path_recall") is not None]
    retrieval_recalls = [case["retrieval"]["expected_path_recall"] for case in answerable]
    citation_recalls = [case["citations"]["expected_path_recall"] for case in answerable if case.get("citations", {}).get("expected_path_recall") is not None]
    return {
        "cases_total": len(cases),
        "responses_succeeded": sum(case.get("http_status") == 200 for case in cases),
        "responses_failed": sum(case.get("http_status") != 200 for case in cases),
        "latency": latency_summary,
        "mean_expected_path_retrieval_recall": round(statistics.fmean(retrieval_recalls), 4) if retrieval_recalls else None,
        "mean_expected_path_citation_recall": round(statistics.fmean(citation_recalls), 4) if citation_recalls else None,
        "cases_with_possible_citation_marker_mismatch": sum(
            bool(case.get("citations", {}).get("markers_without_citation_record"))
            or bool(case.get("citations", {}).get("malformed_markers_in_answer"))
            for case in cases
        ),
        "cases_with_malformed_citation_markers": sum(
            bool(case.get("citations", {}).get("malformed_markers_in_answer")) for case in cases
        ),
        "cases_requiring_manual_abstention_review": sum(
            case.get("abstention_heuristic", {}).get("expected", False) for case in cases
        ),
        "automatic_semantic_quality_score": None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Avaliação de respostas RAG com latência, fontes/citações e revisão humana."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--analysis-id", help="ID de uma análise concluída e persistida.")
    selection.add_argument("--latest", action="store_true", help="Última análise concluída do repositório indicado pelo corpus.")
    parser.add_argument("--cases", default=str(_DEFAULT_CASES), help="Corpus de revisão manual (JSON).")
    parser.add_argument("--output", help="Caminho opcional para gravar o relatório JSON.")
    parser.add_argument(
        "--case-id", action="append", dest="case_ids", default=[],
        help="Executa apenas este ID de caso; pode ser repetido para selecionar vários.",
    )
    parser.add_argument(
        "--run-provider", action="store_true",
        help="Autoriza chamadas reais ao provedor configurado; pode consumir cota ou gerar custo.",
    )
    parser.add_argument(
        "--allow-snapshot-mismatch", action="store_true",
        help="Permite rodar mesmo se o SHA divergir do snapshot anotado no corpus (não recomendado para comparação).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        corpus = _load_cases(args.cases)
    except ValueError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    repository_slug = corpus.get("target_repository")
    try:
        case_definitions = _select_cases(corpus["cases"], args.case_ids)
    except ValueError as exc:
        print(f"Erro de seleção de casos: {exc}", file=sys.stderr)
        return 2
    if not args.run_provider:
        print("SIMULAÇÃO — nenhuma pergunta será enviada ao provedor.")
        print(f"Corpus: {corpus.get('corpus_id')} v{corpus.get('version')}")
        print(f"Repositório: {repository_slug or '(não especificado)'}")
        print(f"Perguntas que seriam executadas: {len(case_definitions)}")
        print("Para autorizar chamadas reais, acrescente --run-provider (pode consumir cota/custo).")

    case_results: list[dict[str, Any]] = []
    with SessionLocal() as db:
        try:
            run = _find_analysis(db, args.analysis_id, repository_slug if args.latest else repository_slug)
        except ValueError as exc:
            print(f"Erro de seleção da análise: {exc}", file=sys.stderr)
            return 2
        if run is None:
            print("Erro: análise não encontrada no banco configurado.", file=sys.stderr)
            return 2
        if run.status not in {"completed", "completed_with_warnings"} or not run.snapshot_id:
            print(f"Erro: a análise precisa estar concluída e vinculada a um snapshot (estado: {run.status}).", file=sys.stderr)
            return 2
        repository = db.get(Repository, run.repository_id)
        snapshot = db.get(RepositorySnapshot, run.snapshot_id)
        if snapshot is None:
            print("Erro: o snapshot da análise não está disponível.", file=sys.stderr)
            return 2
        actual_slug = f"{repository.owner}/{repository.name}" if repository else None
        expected_sha = corpus.get("snapshot_commit")
        if expected_sha and snapshot.commit_sha != expected_sha and not args.allow_snapshot_mismatch:
            print(
                f"Erro: o corpus espera SHA {expected_sha}, mas a análise usa {snapshot.commit_sha}. "
                "Use a análise do snapshot anotado ou passe --allow-snapshot-mismatch de forma consciente.",
                file=sys.stderr,
            )
            return 2
        analysis_metadata = {
            "id": run.id,
            "repository": actual_slug,
            "commit_sha": snapshot.commit_sha,
            "requested_ref": snapshot.requested_ref,
            "expected_corpus_commit": expected_sha,
            "snapshot_matches_corpus": expected_sha is None or snapshot.commit_sha == expected_sha,
        }

        if not args.run_provider:
            print(f"Análise selecionada: {run.id}")
            print(f"Snapshot: {actual_slug} @ {snapshot.commit_sha}")
            print("A validação de snapshot passou; nenhuma chamada de IA foi feita.")
            return 0

        if not ai_is_configured():
            print("Erro: o provedor de IA não está configurado; nenhuma pergunta foi enviada.", file=sys.stderr)
            return 2

        print(f"Análise selecionada: {run.id}", flush=True)
        print(f"Snapshot: {actual_slug} @ {snapshot.commit_sha}", flush=True)
        print(f"Provedor: {settings.ai_provider}; modelo: {settings.ai_model}; raciocínio: {settings.ai_reasoning_effort}", flush=True)
        print(
            f"Serão tentadas {len(case_definitions)} perguntas; a recuperação vazia pode evitar chamada de modelo, "
            "e o provedor pode repetir requisições em falhas transitórias.", flush=True
        )

        from app.application.questions import classify_question  # noqa: PLC0415

        with TestClient(app) as client:
            for index, case in enumerate(case_definitions, start=1):
                case_id = case["id"]
                question = case["question"].strip()
                answerability = case["answerability"]
                expected_paths = list(dict.fromkeys(case.get("expected_paths", [])))
                print(f"[{index}/{len(case_definitions)}] {case_id} ...", flush=True)

                plan = classify_question(question)
                retrieved = retrieve_evidence(db, run, question, intent=plan.intent)
                retrieved_paths: list[str] = []
                for item in retrieved:
                    if item.path and item.path not in retrieved_paths:
                        retrieved_paths.append(item.path)
                retrieved_path_set = set(retrieved_paths)
                retrieved_hits = [path for path in expected_paths if path in retrieved_path_set]
                expected_not_retrieved = [path for path in expected_paths if path not in retrieved_path_set]
                retrieval_view = {
                    "intent": plan.intent,
                    "evidence_count": len(retrieved),
                    "retrieved_paths": retrieved_paths,
                    "expected_path_ranks": {path: retrieved_paths.index(path) + 1 for path in expected_paths if path in retrieved_path_set},
                    "expected_paths_not_retrieved": expected_not_retrieved,
                    "expected_path_recall": round(len(retrieved_hits) / len(expected_paths), 4) if expected_paths else None,
                }

                started = time.perf_counter()
                try:
                    response = client.post(
                        f"/api/v1/analyses/{run.id}/questions",
                        json={"question": question, "scope": {"node_ids": [], "paths": []}},
                    )
                    latency_ms = round((time.perf_counter() - started) * 1000, 1)
                    status_code = response.status_code
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {}
                    if not isinstance(payload, dict):
                        payload = {}
                    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
                    if status_code != 200:
                        case_results.append({
                            "id": case_id,
                            "question": question,
                            "answerability": answerability,
                            "expected_paths": expected_paths,
                            "expected_facts": case.get("expected_facts", []),
                            "must_not_claim": case.get("must_not_claim", []),
                            "http_status": status_code,
                            "error_code": detail.get("code"),
                            "latency_ms": latency_ms,
                            "retrieval": retrieval_view,
                            "citations": {"count": 0, "records": [], "cited_paths": [], "expected_paths_not_cited": expected_paths, "expected_path_recall": 0.0 if expected_paths else None, "markers_in_answer": [], "markers_without_citation_record": []},
                            "answer": None,
                            "insufficient_evidence": None,
                            "abstention_heuristic": {"expected": answerability == "insufficient_evidence", "status": "not_evaluated", "signals": [], "possible_overclaim_signals": []},
                            "manual_review": {"status": "pending", "factual_correctness": None, "source_grounding": None, "citation_support": None, "abstention_calibration": None, "test_semantics": None},
                        })
                        print(f"  HTTP {status_code}; latência={latency_ms} ms; erro={detail.get('code', 'REQUEST_FAILED')}", flush=True)
                        continue

                    answer = payload.get("answer") if isinstance(payload.get("answer"), str) else ""
                    citations_raw = payload.get("citations") if isinstance(payload.get("citations"), list) else []
                    citations = [_citation_record(item) for item in citations_raw if isinstance(item, dict)]
                    citation_paths: list[str] = []
                    for citation in citations:
                        path = citation.get("path")
                        if isinstance(path, str) and path and path not in citation_paths:
                            citation_paths.append(path)
                    citation_set = set(citation_paths)
                    cited_hits = [path for path in expected_paths if path in citation_set]
                    expected_not_cited = [path for path in expected_paths if path not in citation_set]
                    answer_markers, malformed_answer_markers = _extract_answer_citation_markers(answer)
                    returned_ids = {str(item.get("id")) for item in citations if item.get("id") is not None}
                    marker_mismatch = [marker for marker in answer_markers if marker not in returned_ids]
                    citation_view = {
                        "count": len(citations),
                        "records": citations,
                        "cited_paths": citation_paths,
                        "expected_paths_not_cited": expected_not_cited,
                        "expected_path_recall": round(len(cited_hits) / len(expected_paths), 4) if expected_paths else None,
                        "citations_with_path_and_lines": sum(
                            isinstance(item.get("path"), str) and bool(item.get("path"))
                            and isinstance(item.get("start_line"), int) and item["start_line"] >= 1
                            and isinstance(item.get("end_line"), int) and item["end_line"] >= item["start_line"]
                            for item in citations
                        ),
                        "markers_in_answer": answer_markers,
                        "markers_without_citation_record": marker_mismatch,
                        "malformed_markers_in_answer": malformed_answer_markers,
                    }
                    case_results.append({
                        "id": case_id,
                        "question": question,
                        "answerability": answerability,
                        "expected_paths": expected_paths,
                        "expected_facts": case.get("expected_facts", []),
                        "must_not_claim": case.get("must_not_claim", []),
                        "http_status": status_code,
                        "latency_ms": latency_ms,
                        "provider": payload.get("provider"),
                        "model": payload.get("model"),
                        "question_intent": payload.get("question_intent"),
                        "evidence_count": payload.get("evidence_count"),
                        "insufficient_evidence": payload.get("insufficient_evidence"),
                        "answer": answer,
                        "notice": payload.get("notice"),
                        "retrieval": retrieval_view,
                        "citations": citation_view,
                        "abstention_heuristic": _abstention_heuristic(answer, answerability),
                        "manual_review": {"status": "pending", "factual_correctness": None, "source_grounding": None, "citation_support": None, "abstention_calibration": None, "test_semantics": None},
                    })
                    print(
                        f"  HTTP 200; latência={latency_ms} ms; citações={len(citations)}; "
                        f"caminhos esperados citados={len(cited_hits)}/{len(expected_paths) if expected_paths else 0}",
                        flush=True,
                    )
                except Exception as exc:  # provider/API failures are recorded without dumping exception text
                    latency_ms = round((time.perf_counter() - started) * 1000, 1)
                    case_results.append({
                        "id": case_id,
                        "question": question,
                        "answerability": answerability,
                        "expected_paths": expected_paths,
                        "expected_facts": case.get("expected_facts", []),
                        "must_not_claim": case.get("must_not_claim", []),
                        "http_status": None,
                        "error_code": "CLIENT_OR_SERVER_EXCEPTION",
                        "error_type": type(exc).__name__,
                        "latency_ms": latency_ms,
                        "retrieval": retrieval_view,
                        "citations": {"count": 0, "records": [], "cited_paths": [], "expected_paths_not_cited": expected_paths, "expected_path_recall": 0.0 if expected_paths else None, "markers_in_answer": [], "markers_without_citation_record": []},
                        "answer": None,
                        "insufficient_evidence": None,
                        "abstention_heuristic": {"expected": answerability == "insufficient_evidence", "status": "not_evaluated", "signals": [], "possible_overclaim_signals": []},
                        "manual_review": {"status": "pending", "factual_correctness": None, "source_grounding": None, "citation_support": None, "abstention_calibration": None, "test_semantics": None},
                    })
                    print(f"  Falha registrada ({type(exc).__name__}); latência={latency_ms} ms", flush=True)

    report = {
        "report_schema_version": 1,
        "evaluation_type": "model_response_quality_with_human_review",
        "corpus": {
            "id": corpus.get("corpus_id"),
            "version": corpus.get("version"),
            "description": corpus.get("description"),
            "target_repository": repository_slug,
            "snapshot_commit_expected": expected_sha,
        },
        "analysis": analysis_metadata,
        "configuration": {
            "provider": settings.ai_provider,
            "model": settings.ai_model,
            "reasoning_effort": settings.ai_reasoning_effort,
            "provider_enabled": bool(ai_is_configured()),
            "run_provider_authorized": bool(args.run_provider),
            "selected_case_ids": [case["id"] for case in case_definitions],
            "corpus_case_count": len(corpus["cases"]),
            "base_url_host": settings.ai_base_url_host,
            "source_excerpts_saved": False,
            "model_calls_max_top_level": sum(case.get("retrieval", {}).get("evidence_count", 0) > 0 for case in case_results),
        },
        "metrics": _response_metrics(case_results),
        "limitations": [
            "A correção semântica, a sustentação de cada fato e a qualidade da abstenção exigem revisão humana.",
            "Sinais de linguagem de limitação são heurísticos e não contam como aprovação automática.",
            "A cobertura por caminho compara rótulos do corpus com caminhos recuperados/citados; não prova sustentação semântica.",
            "Latência é medida pela chamada local ao endpoint com a geração incluída; não é uma medida isolada do provedor.",
            "O adaptador do provedor pode realizar novas tentativas; model_calls_max_top_level é o máximo de solicitações por caso com evidência, não o total de chamadas HTTP do provedor.",
        ],
        "cases": case_results,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded + "\n", encoding="utf-8")
        print(f"Relatório salvo em: {output_path}")
    metrics = report["metrics"]
    print("\nResumo da avaliação de respostas")
    print(f"Respostas: {metrics['responses_succeeded']} sucesso(s), {metrics['responses_failed']} falha(s)")
    print(f"Latência mediana: {metrics['latency']['median_ms']} ms; P95: {metrics['latency']['p95_ms']} ms")
    print(f"Recall médio dos caminhos esperados na recuperação: {metrics['mean_expected_path_retrieval_recall']}")
    print(f"Recall médio dos caminhos esperados nas citações: {metrics['mean_expected_path_citation_recall']}")
    print("Qualidade semântica: revisão manual pendente; nenhuma nota automática foi inventada.")
    if not args.output:
        print("\nRelatório detalhado (JSON):")
        print(encoded)
    return 1 if metrics["responses_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

from scripts.evaluate_answers import (
    _abstention_heuristic,
    _citation_record,
    _extract_answer_citation_markers,
    _load_cases,
    _response_metrics,
    _select_cases,
)


def test_seeded_answer_quality_corpus_is_loadable_and_has_fixed_snapshot() -> None:
    path = Path(__file__).parents[1] / "evaluation" / "corpora" / "borax-answer-quality.json"
    corpus = _load_cases(path)
    assert corpus["corpus_id"] == "borax-answer-quality-review"
    assert corpus["snapshot_commit"] == "01cbbbf7ce33ee22d23c462c525d07e1320e67a7"
    assert len(corpus["cases"]) == 4


def test_answer_evaluator_can_select_one_case_for_bounded_reruns() -> None:
    path = Path(__file__).parents[1] / "evaluation" / "corpora" / "borax-answer-quality.json"
    corpus = _load_cases(path)

    selected = _select_cases(corpus["cases"], ["static-analysis-security-proof"])
    assert [case["id"] for case in selected] == ["static-analysis-security-proof"]

    try:
        _select_cases(corpus["cases"], ["does-not-exist"])
    except ValueError as exc:
        assert "does-not-exist" in str(exc)
    else:
        raise AssertionError("IDs desconhecidos deveriam ser recusados")


def test_answer_evaluator_detects_malformed_citation_markers() -> None:
    valid, malformed = _extract_answer_citation_markers(
        "Individual [E2]. Grupo [E2, E3] e [ E4 , E5 ]. "
        "Inválidos: E#E6, E7 e grupo [E8; E9]."
    )
    assert valid == ["E2", "E3", "E4", "E5"]
    assert malformed == ["E#E6", "E7", "E8", "E9"]


def test_answer_metrics_counts_malformed_citation_markers_as_mismatches() -> None:
    result = _response_metrics([
        {
            "http_status": 200,
            "latency_ms": 100.0,
            "retrieval": {"expected_path_recall": 1.0},
            "citations": {
                "expected_path_recall": 1.0,
                "markers_without_citation_record": [],
                "malformed_markers_in_answer": ["E#E2"],
            },
            "abstention_heuristic": {"expected": False},
        }
    ])
    assert result["cases_with_possible_citation_marker_mismatch"] == 1
    assert result["cases_with_malformed_citation_markers"] == 1


def test_citation_record_does_not_store_source_excerpt() -> None:
    view = _citation_record({
        "id": "E1", "kind": "source", "path": "app/main.py", "start_line": 1, "end_line": 4,
        "commit_sha": "a" * 40, "url": "https://example.invalid", "excerpt": "private source snippet",
    })
    assert view["path"] == "app/main.py"
    assert "excerpt" not in view


def test_abstention_check_is_only_a_heuristic_and_never_auto_approves() -> None:
    result = _abstention_heuristic(
        "A análise estática não prova que o projeto está livre de todas as vulnerabilidades.",
        "insufficient_evidence",
    )
    assert result["status"] == "limitation_language_detected_review_required"
    assert result["expected"] is True
    assert result["possible_overclaim_signals"] == []
    assert "review_required" in result["status"]


def test_metrics_report_latency_and_never_create_automatic_semantic_score() -> None:
    result = _response_metrics([
        {
            "http_status": 200, "latency_ms": 100.0,
            "retrieval": {"expected_path_recall": 0.5},
            "citations": {"expected_path_recall": 0.5, "markers_without_citation_record": []},
            "abstention_heuristic": {"expected": False},
        },
        {
            "http_status": 502, "latency_ms": 300.0,
            "retrieval": {"expected_path_recall": 1.0},
            "citations": {"expected_path_recall": None, "markers_without_citation_record": []},
            "abstention_heuristic": {"expected": True},
        },
    ])
    assert result["responses_succeeded"] == 1
    assert result["responses_failed"] == 1
    assert result["latency"]["median_ms"] == 200.0
    assert result["mean_expected_path_retrieval_recall"] == 0.75
    assert result["automatic_semantic_quality_score"] is None

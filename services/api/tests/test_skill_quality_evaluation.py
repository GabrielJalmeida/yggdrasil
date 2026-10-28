from __future__ import annotations

from scripts.evaluate_skills import evaluate_corpus


def test_skill_quality_corpus_covers_positive_negative_and_ambiguous_cases() -> None:
    result = evaluate_corpus()
    assert result["provider_calls"] == 0
    assert result["cases_total"] >= 6
    assert result["cases_failed"] == 0
    case_ids = {item["id"] for item in result["cases"]}
    assert "appsec-literal-key-positive" in case_ids
    assert "appsec-env-reference-negative" in case_ids
    assert "appsec-placeholder-like-ambiguous" in case_ids
    assert "quality-nonstandard-test-location-ambiguous" in case_ids

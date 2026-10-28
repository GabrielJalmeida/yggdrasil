from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_questions import QuestionFixture

from app.application import rag_evaluation
from app.application.questions import RetrievedEvidence
from app.application.rag_evaluation import (
    EvaluationCase,
    EvaluationCorpus,
    evaluate_corpus,
    find_latest_completed_analysis,
    load_corpus,
)


def test_rag_evaluation_scores_retrieved_reference_paths_and_intent() -> None:
    fixture = QuestionFixture()
    try:
        corpus = EvaluationCorpus(
            corpus_id="fixture-rag",
            version="0.1.0",
            description="Fixture pequeno para teste determinístico.",
            target_repository="example-org/inventory-api",
            cases=(
                EvaluationCase(
                    id="overview",
                    question="Do que se trata o projeto?",
                    expected_intent="overview",
                    expected_paths=("README.md",),
                ),
                EvaluationCase(
                    id="route-implementation",
                    question="Investigue a implementação do endpoint get-products.",
                    expected_intent="implementation",
                    expected_paths=("app/routes.py",),
                ),
                EvaluationCase(
                    id="insufficient",
                    question="O projeto prova estar livre de todas as vulnerabilidades?",
                    expected_intent="security",
                    expected_paths=(),
                    answerability="insufficient_evidence",
                ),
            ),
        )
        report = evaluate_corpus(fixture.db, fixture.run, corpus)
        metrics = report["metrics"]

        assert report["analysis"]["commit_sha"] == "a" * 40
        assert metrics["cases_total"] == 3
        assert metrics["scored_cases"] == 2
        assert metrics["intent_accuracy"] == 1.0
        assert metrics["hit_at_5"] == 1.0
        assert report["configuration"]["provider_calls"] == 0
        assert report["configuration"]["source_excerpts_included"] is False
        assert report["cases"][2]["response_evaluation"] == "not_run"
        assert '"excerpt":' not in json.dumps(report)
    finally:
        fixture.close()


def test_stale_expected_path_is_excluded_instead_of_counted_as_retrieval_miss() -> None:
    fixture = QuestionFixture()
    try:
        corpus = EvaluationCorpus(
            corpus_id="stale-labels",
            version="0.1.0",
            description="Rótulo obsoleto.",
            target_repository=None,
            cases=(EvaluationCase(
                id="stale",
                question="Do que se trata o projeto?",
                expected_intent="overview",
                expected_paths=("docs/deleted-file.md",),
            ),),
        )
        report = evaluate_corpus(fixture.db, fixture.run, corpus)
        assert report["metrics"]["scored_cases"] == 0
        assert report["metrics"]["invalid_annotations"] == 1
        assert report["cases"][0]["annotation_status"] == "invalid_missing_paths"
        assert report["cases"][0]["missing_expected_paths"] == ["docs/deleted-file.md"]
        assert report["cases"][0]["missing_from_snapshot_paths"] == ["docs/deleted-file.md"]
        assert report["cases"][0]["not_retrieved_expected_paths"] == []
        assert report["metrics"]["mrr"] is None
    finally:
        fixture.close()


def test_present_expected_path_not_retrieved_is_reported_separately(monkeypatch) -> None:
    fixture = QuestionFixture()
    try:
        def fake_retrieve_evidence(_db, _run, _question):
            return [RetrievedEvidence(
                id="only-readme", kind="source", path="README.md", start_line=1, end_line=2,
                commit_sha="a" * 40, url=None, excerpt="redacted summary", score=1.0,
            )]

        monkeypatch.setattr(rag_evaluation, "retrieve_evidence", fake_retrieve_evidence)
        corpus = EvaluationCorpus(
            corpus_id="expected-not-retrieved", version="0.1.0",
            description="Distingue caminho ausente no snapshot de falha de ranking.",
            target_repository=None,
            cases=(EvaluationCase(
                id="docs-missed", question="Explique a documentação e a rota.",
                expected_intent="implementation", expected_paths=("README.md", "app/routes.py"),
            ),),
        )
        result = evaluate_corpus(fixture.db, fixture.run, corpus)["cases"][0]
        assert result["missing_expected_paths"] == []
        assert result["missing_from_snapshot_paths"] == []
        assert result["retrieved_paths"] == ["README.md"]
        assert result["expected_path_ranks"] == {"README.md": 1}
        assert result["not_retrieved_expected_paths"] == ["app/routes.py"]
        assert result["recall_at_5"] == 0.5
    finally:
        fixture.close()


def test_load_corpus_accepts_seeded_corpus_and_keeps_unanswerable_cases_unscored() -> None:
    corpus_path = Path(__file__).parents[1] / "evaluation" / "corpora" / "borax.json"
    corpus = load_corpus(corpus_path)
    assert corpus.corpus_id == "borax-lunar-rag"
    assert len(corpus.cases) >= 5
    assert any(case.answerability == "insufficient_evidence" for case in corpus.cases)


def test_load_corpus_rejects_path_traversal_and_duplicate_case_ids(tmp_path: Path) -> None:
    base = {
        "schema_version": 1,
        "corpus_id": "invalid-corpus",
        "version": "0.1.0",
        "description": "Corpus inválido para teste.",
        "cases": [{
            "id": "unsafe-path",
            "question": "Onde fica?",
            "expected_intent": "general",
            "expected_paths": ["../outside.txt"],
            "answerability": "answerable",
        }],
    }
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match="caminho de repositório inválido"):
        load_corpus(path)

    base["cases"] = [
        {"id": "duplicate", "question": "Pergunta A", "expected_intent": "general", "expected_paths": ["README.md"]},
        {"id": "duplicate", "question": "Pergunta B", "expected_intent": "general", "expected_paths": ["README.md"]},
    ]
    path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicado"):
        load_corpus(path)


def test_evaluator_rejects_corpus_for_a_different_repository() -> None:
    fixture = QuestionFixture()
    try:
        corpus = EvaluationCorpus(
            corpus_id="wrong-repository",
            version="0.1.0",
            description="Corpus de outro repositório.",
            target_repository="other-org/other-project",
            cases=(EvaluationCase(
                id="overview",
                question="Do que se trata o projeto?",
                expected_intent="overview",
                expected_paths=("README.md",),
            ),),
        )
        with pytest.raises(ValueError, match="Escolha uma análise do repositório correto"):
            evaluate_corpus(fixture.db, fixture.run, corpus)
    finally:
        fixture.close()


def test_expected_path_without_persisted_content_is_not_scored() -> None:
    fixture = QuestionFixture()
    try:
        fixture.files["app/routes.py"].redacted_content = None
        corpus = EvaluationCorpus(
            corpus_id="unavailable-content",
            version="0.1.0",
            description="Arquivo descoberto, mas conteúdo indisponível.",
            target_repository=None,
            cases=(EvaluationCase(
                id="route-implementation",
                question="Investigue a implementação do endpoint get-products.",
                expected_intent="implementation",
                expected_paths=("app/routes.py",),
            ),),
        )
        report = evaluate_corpus(fixture.db, fixture.run, corpus)
        result = report["cases"][0]
        assert report["metrics"]["scored_cases"] == 0
        assert report["metrics"]["invalid_annotations"] == 1
        assert result["annotation_status"] == "invalid_unavailable_paths"
        assert result["unavailable_expected_paths"] == ["app/routes.py"]
    finally:
        fixture.close()


def test_ranking_counts_unique_source_files_not_duplicate_evidence_chunks(monkeypatch) -> None:
    fixture = QuestionFixture()
    try:
        def fake_retrieve_evidence(_db, _run, _question):
            def evidence(path: str, index: int) -> RetrievedEvidence:
                return RetrievedEvidence(
                    id=f"evidence-{index}", kind="source", path=path, start_line=1, end_line=2,
                    commit_sha="a" * 40, url=None, excerpt="redacted test evidence", score=1.0 - index / 10,
                )
            return [
                evidence("README.md", 1),
                evidence("README.md", 2),
                evidence("app/routes.py", 3),
            ]

        monkeypatch.setattr(rag_evaluation, "retrieve_evidence", fake_retrieve_evidence)
        corpus = EvaluationCorpus(
            corpus_id="unique-file-ranking",
            version="0.1.0",
            description="Repetição de snippets não pode prejudicar a posição do arquivo.",
            target_repository=None,
            cases=(EvaluationCase(
                id="route-implementation",
                question="Investigue a implementação do endpoint get-products.",
                expected_intent="implementation",
                expected_paths=("app/routes.py",),
            ),),
        )
        report = evaluate_corpus(fixture.db, fixture.run, corpus, k_values=(1, 2))
        result = report["cases"][0]
        assert result["retrieved_paths"] == ["README.md", "app/routes.py"]
        assert result["expected_path_ranks"] == {"app/routes.py": 2}
        assert result["hit_at_2"] == 1.0
    finally:
        fixture.close()

def test_latest_analysis_selector_is_scoped_to_corpus_repository_and_completed_runs() -> None:
    fixture = QuestionFixture()
    try:
        corpus = EvaluationCorpus(
            corpus_id="latest-analysis",
            version="0.1.0",
            description="Seleção determinística da última análise concluída.",
            target_repository="example-org/inventory-api",
            cases=(EvaluationCase(
                id="overview", question="Do que se trata?", expected_intent="overview", expected_paths=("README.md",),
            ),),
        )
        selected = find_latest_completed_analysis(fixture.db, corpus)
        assert selected is not None
        assert selected.id == fixture.run.id

        other_repo = EvaluationCorpus(
            corpus_id="other-repository", version="0.1.0", description="Outro repositório.",
            target_repository="another-org/another-repo", cases=corpus.cases,
        )
        assert find_latest_completed_analysis(fixture.db, other_repo) is None

        unscoped = EvaluationCorpus(
            corpus_id="unscoped", version="0.1.0", description="Sem repositório alvo.",
            target_repository=None, cases=corpus.cases,
        )
        with pytest.raises(ValueError, match="target_repository"):
            find_latest_completed_analysis(fixture.db, unscoped)
    finally:
        fixture.close()

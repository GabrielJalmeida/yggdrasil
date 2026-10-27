from __future__ import annotations

import hashlib
import io
import logging
import sqlite3
import zipfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.application.questions import classify_question
from app.application import runner
from app.db import Base, get_db
from app.domain.skills import FindingData
from app.infrastructure.github import GitHubError, RepositoryAddress, ResolvedRepository
from app.main import app
from app.models import AnalysisEvent, AnalysisRun, GraphNode, SourceFile


SECRET_VALUE = "very_sensitive_demo_key_that_must_not_leave_storage"
COMMIT = "a" * 40


def create_sample_archive() -> bytes:
    contents = {
        "sample-repo-main/app/main.py": (
            "from fastapi import APIRouter\n"
            "from app.service import calculate\n"
            f'API_KEY = "{SECRET_VALUE}"\n'
            "router = APIRouter()\n\n"
            "@router.get('/health')\n"
            "def health():\n"
            "    return {'status': 'ok', 'count': calculate(1)}\n"
        ),
        "sample-repo-main/app/service.py": "def calculate(value):\n    return value + 1\n",
        "sample-repo-main/tests/test_main.py": "def test_health():\n    assert True\n",
        "sample-repo-main/pyproject.toml": '[project]\ndependencies = ["fastapi>=0.1", "sqlalchemy>=2.0"]\n',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in contents.items():
            archive.writestr(path, content)
    return buffer.getvalue()


class FakeGitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def __enter__(self) -> "FakeGitHubClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def resolve(self, address: RepositoryAddress, requested_ref: str | None) -> ResolvedRepository:
        return ResolvedRepository(
            owner=address.owner,
            name=address.name,
            canonical_url=address.canonical_url,
            default_branch="main",
            requested_ref=requested_ref or "main",
            commit_sha=COMMIT,
            tree_sha="b" * 40,
            description="Controlled test repository",
            repository_created_at="2024-01-01T00:00:00Z",
            commit_message="test fixture",
            commit_date="2026-01-01T00:00:00Z",
        )

    def download_archive(self, _repository: ResolvedRepository) -> bytes:
        return create_sample_archive()


class FakeLargeRepoGitHubClient(FakeGitHubClient):
    """Forces archive fallback while keeping every remote operation deterministic."""

    FILES = {
        "app/main.py": (
            "from app.service import calculate\n"
            f'API_KEY = "{SECRET_VALUE}"\n'
            "def run():\n    return calculate(1)\n"
        ).encode("utf-8"),
        "app/service.py": b"def calculate(value):\n    return value + 1\n",
        "tests/test_main.py": b"def test_run():\n    assert True\n",
        "pyproject.toml": b"[project]\ndependencies = []\n",
    }

    def download_archive(self, _repository: ResolvedRepository) -> bytes:
        raise GitHubError("ARCHIVE_TOO_LARGE", "archive exceeds configured limit", 413)

    def get_repository_tree(self, _repository: ResolvedRepository) -> dict[str, object]:
        entries = []
        for path, content in self.FILES.items():
            sha = hashlib.sha1(
                b"blob " + str(len(content)).encode("ascii") + b"\0" + content
            ).hexdigest()
            entries.append({
                "path": path,
                "type": "blob",
                "mode": "100644",
                "size": len(content),
                "sha": sha,
            })
        return {"truncated": False, "tree": entries}

    def download_raw_file(
        self,
        _repository: ResolvedRepository,
        path: str,
        max_bytes: int | None = None,
    ) -> bytes:
        content = self.FILES[path]
        if max_bytes is not None and len(content) > max_bytes:
            raise GitHubError("RAW_FILE_TOO_LARGE", "file too large", 413)
        return content


@pytest.fixture()
def isolated_client(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(routes, "SessionLocal", factory)
    monkeypatch.setattr(runner, "GitHubClient", FakeGitHubClient)
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_health_and_invalid_repository_url(isolated_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, _factory = isolated_client
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert health.json()["version"] == "0.7.0"

    response = client.post("/api/v1/analyses", json={"repository_url": "https://github.com.evil.example/owner/repo"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REPOSITORY_URL"


def test_graph_reports_exact_response_limits_and_server_side_filters(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = isolated_client
    created = client.post(
        "/api/v1/analyses",
        json={
            "repository_url": "https://github.com/example-org/graph-filter-repo",
            "ref": "main",
            "profile": "mvp-python",
            "skills": ["appsec.secrets-detection", "engineering.test-inventory"],
        },
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]

    base = client.get(f"/api/v1/analyses/{analysis_id}/graph?limit=1&edge_limit=1").json()
    assert base["repository_total_nodes"] > 1
    assert base["returned_nodes"] == 1
    assert base["total_nodes"] == base["repository_total_nodes"]
    assert base["truncated_nodes"] is True
    assert base["truncated"] is True

    edge_limited = client.get(
        f"/api/v1/analyses/{analysis_id}/graph?limit=1000&edge_limit=1"
    ).json()
    assert edge_limited["truncated_edges"] is True
    assert edge_limited["returned_edges"] == 1
    assert edge_limited["eligible_edges_for_returned_nodes"] > 1

    # Filtering occurs in the API before applying the response limit. It can therefore find
    # matching symbols/files that are outside the first node(s) of the unfiltered response.
    function_result = client.get(
        f"/api/v1/analyses/{analysis_id}/graph?node_type=function&q=calculate&limit=10"
    ).json()
    assert function_result["repository_total_nodes"] == base["repository_total_nodes"]
    assert function_result["total_nodes"] == function_result["returned_nodes"]
    assert function_result["returned_nodes"] >= 1
    assert all(node["type"] == "function" for node in function_result["nodes"])
    assert any("calculate" in node["label"].lower() for node in function_result["nodes"])
    assert function_result["truncated_nodes"] is False

    path_result = client.get(
        f"/api/v1/analyses/{analysis_id}/graph?q=service.py&limit=20"
    ).json()
    assert path_result["returned_nodes"] > 0
    assert any("service.py" in (node["path"] or "") for node in path_result["nodes"])


def test_analysis_pipeline_persists_graph_redacts_secrets_and_exports_markdown(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = isolated_client
    created = client.post(
        "/api/v1/analyses",
        json={
            "repository_url": "https://github.com/example-org/sample-repo",
            "ref": "main",
            "profile": "mvp-python",
            "skills": ["appsec.secrets-detection", "engineering.test-inventory"],
        },
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]

    analysis = client.get(f"/api/v1/analyses/{analysis_id}")
    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["status"] == "completed", payload
    assert payload["snapshot"]["commit_sha"] == COMMIT
    assert payload["counts"]["files"] == 4
    assert payload["counts"]["nodes"] > payload["counts"]["files"]
    assert payload["counts"]["findings"] == 1
    assert payload["coverage"]["inventory_total"] == 4
    assert payload["coverage"]["eligible_files"] == 4
    assert payload["coverage"]["python_parsed"] >= 2

    graph = client.get(f"/api/v1/analyses/{analysis_id}/graph").json()
    assert graph["returned_nodes"] == len(graph["nodes"])
    assert graph["returned_edges"] == len(graph["edges"])
    assert graph["repository_total_nodes"] == payload["counts"]["nodes"]
    assert graph["repository_total_edges"] == payload["counts"]["edges"]
    assert graph["truncated"] is False
    assert any(node["type"] == "endpoint" and node["label"] == "GET /health" for node in graph["nodes"])
    assert any(edge["type"] == "imports" for edge in graph["edges"])
    assert any(edge["provenance_type"] == "inferred" for edge in graph["edges"])

    findings = client.get(f"/api/v1/analyses/{analysis_id}/findings").json()["items"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "MEDIUM"
    assert SECRET_VALUE not in str(findings)

    secret_source = client.get(
        f"/api/v1/analyses/{analysis_id}/nodes/"
        + next(node["id"] for node in graph["nodes"] if node.get("path") == "app/main.py" and node["type"] == "file")
    )
    assert secret_source.status_code == 200
    assert SECRET_VALUE not in secret_source.text
    assert "[REDACTED]" in secret_source.text

    export = client.post(f"/api/v1/analyses/{analysis_id}/exports/markdown")
    assert export.status_code == 201
    markdown_response = client.get(export.json()["download_url"].replace("http://testserver", ""))
    assert markdown_response.status_code == 200
    assert "Yggdrasil Repository Map" in markdown_response.text
    assert COMMIT in markdown_response.text
    assert SECRET_VALUE not in markdown_response.text
    assert "app/main.py" in markdown_response.text

    # The raw credential is not written to the database, while the original line remains inspectable.
    with factory() as db:
        row = db.scalar(select(SourceFile).where(SourceFile.path == "app/main.py"))
        assert row is not None and row.redacted_content is not None
        assert SECRET_VALUE not in row.redacted_content
        run = db.get(AnalysisRun, analysis_id)
        assert run is not None
        events = db.scalars(select(AnalysisEvent).where(AnalysisEvent.analysis_run_id == analysis_id).order_by(AnalysisEvent.sequence_number)).all()
        assert [item.sequence_number for item in events] == list(range(1, len(events) + 1))
        assert db.scalar(select(GraphNode.id).where(GraphNode.snapshot_id == run.snapshot_id, GraphNode.node_type == "finding")) is not None

    event_stream = client.get(f"/api/v1/analyses/{analysis_id}/events")
    assert event_stream.status_code == 200
    assert "analysis_completed" in event_stream.text



def test_finding_review_status_persists_updates_graph_and_emits_audit_event(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = isolated_client
    created = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/review-status-repo", "ref": "main"},
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]
    findings = client.get(f"/api/v1/analyses/{analysis_id}/findings").json()["items"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["status"] == "needs_review"

    updated = client.patch(
        f"/api/v1/analyses/{analysis_id}/findings/{finding['id']}/status",
        json={"status": "false_positive"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json() == {
        "id": finding["id"],
        "finding_key": finding["finding_key"],
        "previous_status": "needs_review",
        "status": "false_positive",
        "changed": True,
    }

    listed = client.get(f"/api/v1/analyses/{analysis_id}/findings?status=false_positive").json()
    assert listed["total"] == 1
    assert listed["items"][0]["status"] == "false_positive"
    with factory() as db:
        run = db.get(AnalysisRun, analysis_id)
        assert run is not None and run.snapshot_id is not None
        node = db.scalar(
            select(GraphNode).where(
                GraphNode.snapshot_id == run.snapshot_id,
                GraphNode.stable_key == f"finding:{analysis_id}:{finding['finding_key']}",
            )
        )
        assert node is not None and node.properties["status"] == "false_positive"
        events = db.scalars(
            select(AnalysisEvent)
            .where(AnalysisEvent.analysis_run_id == analysis_id, AnalysisEvent.event_type == "finding_status_changed")
        ).all()
        assert len(events) == 1
        assert events[0].payload["previous_status"] == "needs_review"
        assert events[0].payload["status"] == "false_positive"

    repeated = client.patch(
        f"/api/v1/analyses/{analysis_id}/findings/{finding['id']}/status",
        json={"status": "false_positive"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["changed"] is False
    invalid = client.patch(
        f"/api/v1/analyses/{analysis_id}/findings/{finding['id']}/status",
        json={"status": "delete_everything"},
    )
    assert invalid.status_code == 422

    markdown = client.get(f"/api/v1/analyses/{analysis_id}/export/markdown").text
    assert "false_positive" in markdown
    assert SECRET_VALUE not in markdown


def test_finding_review_rejects_changes_while_analysis_is_running(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = isolated_client
    created = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/review-running-repo", "ref": "main"},
    )
    analysis_id = created.json()["id"]
    finding = client.get(f"/api/v1/analyses/{analysis_id}/findings").json()["items"][0]
    with factory() as db:
        run = db.get(AnalysisRun, analysis_id)
        assert run is not None
        run.status = "running_skills"
        db.commit()

    response = client.patch(
        f"/api/v1/analyses/{analysis_id}/findings/{finding['id']}/status",
        json={"status": "confirmed"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ANALYSIS_NOT_COMPLETE"


def test_finding_review_cannot_cross_analysis_boundary(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = isolated_client
    first = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/review-first-repo", "ref": "main"},
    ).json()
    second = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/review-second-repo", "ref": "main"},
    ).json()
    second_finding = client.get(f"/api/v1/analyses/{second['id']}/findings").json()["items"][0]

    response = client.patch(
        f"/api/v1/analyses/{first['id']}/findings/{second_finding['id']}/status",
        json={"status": "confirmed"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FINDING_NOT_FOUND"


def test_analysis_persists_many_skill_graph_nodes_before_edges(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = isolated_client

    def many_findings(*_args: object, **_kwargs: object) -> tuple[list[FindingData], list[str]]:
        findings = [
            FindingData(
                skill_id="test.synthetic-skill",
                skill_version="test-1",
                finding_key=f"synthetic:{index:03d}",
                category="quality",
                severity="LOW",
                status="needs_review",
                confidence_label="moderate",
                title=f"Synthetic finding {index}",
                summary="Fixture used to test SQL foreign-key ordering.",
                impact="No production impact; generated only in the test.",
                recommendation="No action.",
                evidence=[{
                    "path": "app/main.py",
                    "start_line": index + 1,
                    "end_line": index + 1,
                    "commit_sha": COMMIT,
                    "evidence_type": "test_fixture",
                }],
            )
            for index in range(120)
        ]
        return findings, []

    monkeypatch.setattr(runner, "run_initial_skills", many_findings)
    created = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/many-findings-repo", "ref": "main"},
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]
    result = client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert result["status"] == "completed", result
    assert result["counts"]["findings"] == 120

    graph = client.get(f"/api/v1/analyses/{analysis_id}/graph?limit=1000&edge_limit=1000").json()
    assert sum(node["type"] == "finding" for node in graph["nodes"]) == 120
    assert sum(edge["type"] == "finding_affects" for edge in graph["edges"]) == 120
    with factory() as db:
        run = db.get(AnalysisRun, analysis_id)
        assert run is not None and run.snapshot_id is not None
        for edge in db.query(runner.GraphEdge).filter_by(snapshot_id=run.snapshot_id).all():
            assert db.get(GraphNode, edge.source_node_id) is not None
            assert db.get(GraphNode, edge.target_node_id) is not None


def test_unexpected_analysis_failure_logs_safe_traceback_without_exception_message(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _factory = isolated_client

    def fail_skills(*_args: object, **_kwargs: object) -> tuple[list[object], list[str]]:
        raise RuntimeError("PRIVATE_EXCEPTION_MESSAGE_SHOULD_NOT_BE_LOGGED")

    monkeypatch.setattr(runner, "run_initial_skills", fail_skills)
    with caplog.at_level(logging.ERROR, logger="yggdrasil.analysis"):
        created = client.post(
            "/api/v1/analyses",
            json={"repository_url": "https://github.com/example-org/failing-repo", "ref": "main"},
        )

    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]
    failed = client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "INTERNAL_ANALYSIS_ERROR"
    assert f"analysis_id={analysis_id}" in caplog.text
    assert "fail_skills" in caplog.text
    assert "run_analysis" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "stage=running_skills" in caplog.text
    assert "PRIVATE_EXCEPTION_MESSAGE_SHOULD_NOT_BE_LOGGED" not in caplog.text


def test_integrity_error_summary_reports_constraint_without_values() -> None:
    original = sqlite3.IntegrityError(
        "UNIQUE constraint failed: findings.analysis_run_id, findings.finding_key"
    )
    exc = IntegrityError("INSERT INTO findings ...", {"secret": "must-not-appear"}, original)
    summary = runner._safe_integrity_summary(exc)
    assert summary == "integrity=unique_columns:findings.analysis_run_id,findings.finding_key"
    assert "must-not-appear" not in summary


def test_integrity_error_summary_does_not_log_unknown_database_message() -> None:
    original = sqlite3.IntegrityError("custom constraint failed with a secret value")
    exc = IntegrityError("INSERT INTO findings ...", {"secret": "sensitive"}, original)
    summary = runner._safe_integrity_summary(exc)
    assert summary == "integrity=unclassified"
    assert "secret" not in summary
    assert "sensitive" not in summary


def test_large_archive_falls_back_to_selective_tree_ingestion(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = isolated_client
    monkeypatch.setattr(runner, "GitHubClient", FakeLargeRepoGitHubClient)
    created = client.post(
        "/api/v1/analyses",
        json={
            "repository_url": "https://github.com/example-org/large-repo",
            "ref": "main",
            "profile": "mvp-python",
            "skills": ["appsec.secrets-detection", "engineering.test-inventory"],
        },
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]

    analysis = client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert analysis["status"] == "completed_with_warnings", analysis
    assert analysis["snapshot"]["commit_sha"] == COMMIT
    assert analysis["counts"]["files"] == 4
    assert any("leitura seletiva" in warning for warning in analysis["warnings"])
    assert analysis["progress"]["ingestion_method"] == "github_tree"

    events = client.get(f"/api/v1/analyses/{analysis_id}/events").text
    assert "selective_tree_fallback_started" in events
    assert "analysis_completed" in events

    findings = client.get(f"/api/v1/analyses/{analysis_id}/findings").json()["items"]
    assert len(findings) == 1
    assert SECRET_VALUE not in str(findings)
    export = client.post(f"/api/v1/analyses/{analysis_id}/exports/markdown")
    assert export.json()["report_version"] == "0.7.0"
    markdown = client.get(export.json()["download_url"].replace("http://testserver", "")).text
    assert "árvore GitHub com leitura seletiva" in markdown
    assert "Avisos da análise" in markdown
    assert "leitura seletiva" in markdown

    with factory() as db:
        main_file = db.scalar(select(SourceFile).where(SourceFile.path == "app/main.py"))
        assert main_file is not None
        assert main_file.metadata_json["source_method"] == "github_tree"
        assert SECRET_VALUE not in (main_file.redacted_content or "")


def test_database_url_credentials_are_redacted_from_storage_inspector_and_report(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = isolated_client
    password = "VeryFakeDbPassword987!tail"
    username = "service_user_demo"
    source = (
        'DATABASE_URL = "postgresql://'
        + username
        + ":"
        + password
        + '@db.example.test/app"\n'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("db-url-repo-main/app/config.py", source)

    def custom_download(_self: FakeGitHubClient, _repository: ResolvedRepository) -> bytes:
        return buffer.getvalue()

    monkeypatch.setattr(FakeGitHubClient, "download_archive", custom_download)
    created = client.post(
        "/api/v1/analyses",
        json={
            "repository_url": "https://github.com/example-org/db-url-repo",
            "ref": "main",
            "skills": ["appsec.secrets-detection"],
        },
    )

    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]
    skill_catalog = client.get("/api/v1/skills").json()["items"]
    assert next(
        skill for skill in skill_catalog if skill["id"] == "appsec.secrets-detection"
    )["version"] == "0.2.0"
    state = client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert state["status"] == "completed", state
    findings = client.get(f"/api/v1/analyses/{analysis_id}/findings").json()["items"]
    assert len(findings) == 1
    assert findings[0]["skill_version"] == "0.2.0"
    assert findings[0]["evidence"][0]["path"] == "app/config.py"
    assert password not in str(findings)
    assert username not in str(findings)

    graph = client.get(f"/api/v1/analyses/{analysis_id}/graph").json()
    file_node = next(
        node for node in graph["nodes"]
        if node["type"] == "file" and node.get("path") == "app/config.py"
    )
    detail = client.get(f"/api/v1/analyses/{analysis_id}/nodes/{file_node['id']}")
    assert detail.status_code == 200
    assert password not in detail.text
    assert username not in detail.text
    assert "[REDACTED]" in detail.text

    export = client.post(f"/api/v1/analyses/{analysis_id}/exports/markdown")
    markdown = client.get(export.json()["download_url"].replace("http://testserver", ""))
    assert markdown.status_code == 200
    assert password not in markdown.text
    assert username not in markdown.text

    with factory() as db:
        stored = db.scalar(select(SourceFile).where(SourceFile.path == "app/config.py"))
        assert stored is not None
        assert stored.redacted_content is not None
        assert password not in stored.redacted_content
        assert username not in stored.redacted_content



def test_question_endpoint_recovers_redacted_evidence_and_validates_citations(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.infrastructure.ai_provider import AIAnswer

    client, _factory = isolated_client
    created = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/qa-repo", "ref": "main"},
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["id"]

    captured: dict[str, object] = {}

    def fake_answer(question: str, evidence: list[dict[str, object]], **kwargs: object) -> AIAnswer:
        captured["question"] = question
        captured["evidence"] = evidence
        captured["intent_kwargs"] = kwargs
        return AIAnswer(
            answer="A função `calculate` está definida no arquivo de serviço. [E1]",
            citation_ids=["E1", "E999"],
            insufficient_evidence=False,
        )

    monkeypatch.setattr(routes, "ai_is_configured", lambda: True)
    monkeypatch.setattr(routes, "generate_answer", fake_answer)
    answer = client.post(
        f"/api/v1/analyses/{analysis_id}/questions",
        json={"question": "Onde a função calculate está definida?"},
    )
    assert answer.status_code == 200, answer.text
    payload = answer.json()
    assert payload["insufficient_evidence"] is False
    assert [citation["id"] for citation in payload["citations"]] == ["E1"]
    assert "[E999]" not in payload["answer"]
    assert payload["citations"][0]["path"] == "app/service.py"
    assert payload["citations"][0]["start_line"] == 1
    assert payload["citations"][0]["commit_sha"] == COMMIT
    assert "calculate" in str(captured["evidence"])
    assert captured["intent_kwargs"] == {
        "intent": "symbol",
        "intent_guidance": classify_question("Onde a função calculate está definida?").guidance,
    }
    assert payload["question_intent"] == "symbol"
    assert payload["question_intent_label"] == "Símbolo ou trecho específico"
    assert payload["retrieved_kinds"]
    assert SECRET_VALUE not in str(captured["evidence"])

    # A response without a real citation is downgraded to an explicit abstention.
    monkeypatch.setattr(
        routes,
        "generate_answer",
        lambda *_args, **_kwargs: AIAnswer(
            answer="Conclusão arbitrária.", citation_ids=["E404"], insufficient_evidence=False
        ),
    )
    ungrounded = client.post(
        f"/api/v1/analyses/{analysis_id}/questions",
        json={"question": "Onde a função calculate está definida?"},
    )
    assert ungrounded.status_code == 200
    assert ungrounded.json()["insufficient_evidence"] is True
    assert ungrounded.json()["citations"] == []
    assert "referências verificáveis" in ungrounded.json()["answer"]


def test_question_endpoint_requires_configured_ai_and_rejects_bad_scope(
    isolated_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _factory = isolated_client
    created = client.post(
        "/api/v1/analyses",
        json={"repository_url": "https://github.com/example-org/qa-disabled", "ref": "main"},
    )
    analysis_id = created.json()["id"]
    disabled = client.post(
        f"/api/v1/analyses/{analysis_id}/questions",
        json={"question": "Como funciona calculate?"},
    )
    assert disabled.status_code == 503
    assert disabled.json()["detail"]["code"] == "AI_NOT_CONFIGURED"

    monkeypatch.setattr(routes, "ai_is_configured", lambda: True)
    bad_scope = client.post(
        f"/api/v1/analyses/{analysis_id}/questions",
        json={"question": "Como funciona calculate?", "scope": {"paths": ["../outside.py"]}},
    )
    assert bad_scope.status_code == 422


def test_ai_provider_parses_structured_response_and_rejects_invalid_payload() -> None:
    from app.infrastructure.ai_provider import AIProviderError, _parse_json_response

    parsed = _parse_json_response(
        '{"answer":"A função aparece em E1.","citation_ids":["E1"],"insufficient_evidence":false}'
    )
    assert parsed["citation_ids"] == ["E1"]
    try:
        _parse_json_response('{"answer":"ok","citation_ids":"E1"}')
    except AIProviderError as exc:
        assert exc.code == "AI_INVALID_RESPONSE"
    else:
        raise AssertionError("A resposta malformada deveria ter sido rejeitada")

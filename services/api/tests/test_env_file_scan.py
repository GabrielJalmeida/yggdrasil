from __future__ import annotations

import hashlib
import io
import zipfile

from app.domain.graph import build_graph
from app.domain.skills import run_initial_skills
from app.infrastructure.archive import ArchiveArtifact, inspect_archive, inspect_github_tree

SECRET = "EnvironmentSecretValue123456"


def _make_zip(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _git_blob_entry(path: str, content: bytes) -> dict[str, object]:
    blob_sha = hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()
    return {
        "path": path,
        "type": "blob",
        "mode": "100644",
        "size": len(content),
        "sha": blob_sha,
    }


def _assert_environment_findings(files: list[ArchiveArtifact]) -> None:
    findings, warnings = run_initial_skills(
        files, "a" * 40, ["appsec.secrets-detection"]
    )
    assert not warnings
    assert sum(f.title == "Arquivo de ambiente versionado" for f in findings) == 2
    assert sum(f.title == "Possível credencial literal no código" for f in findings) == 2
    assert SECRET not in repr(findings)
    environment_paths = {
        finding.evidence[0]["path"]
        for finding in findings
        if finding.title == "Arquivo de ambiente versionado"
    }
    assert environment_paths == {".env", ".env.production"}


def test_zip_ingestion_keeps_env_files_in_graph_and_scans_redacted_content() -> None:
    archive = _make_zip({
        "owner-repo-sha/.env": f"API_KEY={SECRET}\n",
        "owner-repo-sha/.env.production": f"API_KEY={SECRET}\n",
        "owner-repo-sha/.env.example": "API_KEY=your-api-key-here\n",
    })
    result = inspect_archive(archive)
    by_path = {item.path: item for item in result.files}
    expected = {".env", ".env.production", ".env.example"}

    assert expected.issubset(by_path)
    for path in expected:
        assert by_path[path].eligibility_status == "eligible"
        assert by_path[path].redacted_content is not None
    for path in (".env", ".env.production"):
        assert by_path[path].raw_content is not None
        assert SECRET in by_path[path].raw_content
        assert SECRET not in by_path[path].redacted_content

    graph = build_graph("owner", "repo", result.files)
    file_paths = {node.source_path for node in graph.nodes if node.node_type == "file"}
    assert expected.issubset(file_paths)
    _assert_environment_findings(result.files)


def test_github_tree_ingestion_scans_env_files_and_warns_on_presence() -> None:
    contents = {
        ".env": f"API_KEY={SECRET}\n".encode(),
        ".env.production": f"API_KEY={SECRET}\n".encode(),
        ".env.example": b"API_KEY=your-api-key-here\n",
    }
    entries = [_git_blob_entry(path, content) for path, content in contents.items()]
    result = inspect_github_tree(
        entries,
        lambda path, _limit: contents[path],
    )
    by_path = {item.path: item for item in result.files}

    assert set(contents).issubset(by_path)
    assert all(by_path[path].eligibility_status == "eligible" for path in contents)
    assert all(
        SECRET not in by_path[path].redacted_content
        for path in (".env", ".env.production")
    )
    _assert_environment_findings(result.files)

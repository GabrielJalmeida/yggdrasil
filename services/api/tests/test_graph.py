from __future__ import annotations

from app.domain.graph import build_graph
from app.infrastructure.archive import ArchiveArtifact


def artifact(path: str, content: str) -> ArchiveArtifact:
    return ArchiveArtifact(
        path=path,
        size_bytes=len(content.encode()),
        language="Python",
        eligibility_status="eligible",
        parse_status="queued",
        redacted_content=content,
        raw_content=content,
    )


def test_parser_extracts_symbols_routes_imports_and_labels_calls_as_inferred() -> None:
    files = [
        artifact(
            "app/service.py",
            "def calculate(value):\n    return value + 1\n",
        ),
        artifact(
            "app/main.py",
            "from app.service import calculate\n\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return calculate(1)\n",
        ),
        artifact("tests/test_service.py", "def test_calculate():\n    assert True\n"),
    ]
    graph = build_graph("sample", "repo", files)
    types = {node.node_type for node in graph.nodes}
    relations = {(edge.relation_type, edge.provenance_type) for edge in graph.edges}
    labels = {node.label for node in graph.nodes}
    assert {"repository", "directory", "file", "module", "function", "test", "endpoint"} <= types
    assert "GET /health" in labels
    assert ("contains", "deterministic") in relations
    assert ("imports", "deterministic") in relations
    assert ("calls", "inferred") in relations
    assert all(edge.provenance_type != "deterministic" for edge in graph.edges if edge.relation_type == "calls")
    assert graph.parsed_python_files == 3
    assert graph.failed_python_files == 0


def test_syntax_error_is_partial_failure_not_execution() -> None:
    file = artifact("broken.py", "def broken(:\n    pass\n")
    graph = build_graph("sample", "repo", [file])
    assert file.parse_status == "failed"
    assert graph.failed_python_files == 1
    assert graph.warnings

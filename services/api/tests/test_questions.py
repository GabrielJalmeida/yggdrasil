from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.questions import _path_role, classify_question, retrieve_evidence
from app.db import Base
from app.models import AnalysisRun, GraphEdge, GraphNode, Repository, RepositorySnapshot, SourceFile


class QuestionFixture:
    def __init__(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.factory()
        self.repository = Repository(
            id="repo-qa-001", provider="github", owner="example-org", name="inventory-api",
            canonical_url="https://github.com/example-org/inventory-api", visibility="public",
            default_branch="main", description="API para gerenciar o inventário de produtos.",
        )
        self.snapshot = RepositorySnapshot(
            id="snapshot-qa-001", repository_id=self.repository.id, commit_sha="a" * 40,
            requested_ref="main", default_branch="main",
            metadata_json={"description": "API de inventário"},
        )
        self.run = AnalysisRun(
            id="analysis-qa-001", repository_id=self.repository.id, snapshot_id=self.snapshot.id,
            status="completed", stage="completed", progress_metadata={}, configuration={}, warning_summary=[],
        )
        self.db.add_all([self.repository, self.snapshot, self.run])
        self.db.flush()
        self.files = {
            "README.md": SourceFile(
                id="source-readme-001", snapshot_id=self.snapshot.id, path="README.md",
                size_bytes=230, language="Markdown", eligibility_status="eligible", parse_status="parsed",
                redacted_content=(
                    "# Inventory API\n\n"
                    "Serviço HTTP para gerenciar produtos e níveis de estoque.\n\n"
                    "A aplicação expõe endpoints REST em FastAPI e persiste produtos em PostgreSQL.\n"
                    "O objetivo é centralizar operações de consulta e atualização do inventário.\n"
                ), metadata_json={},
            ),
            "pyproject.toml": SourceFile(
                id="source-manifest-001", snapshot_id=self.snapshot.id, path="pyproject.toml",
                size_bytes=140, language="TOML", eligibility_status="eligible", parse_status="unsupported",
                redacted_content='[project]\nname = "inventory-api"\ndependencies = ["fastapi", "sqlalchemy", "psycopg"]\n',
                metadata_json={},
            ),
            "app/main.py": SourceFile(
                id="source-main-001", snapshot_id=self.snapshot.id, path="app/main.py",
                size_bytes=180, language="Python", eligibility_status="eligible", parse_status="parsed",
                redacted_content=(
                    "from fastapi import FastAPI\nfrom app.routes import router\n\n"
                    "app = FastAPI(title='Inventory API')\napp.include_router(router)\n"
                ), metadata_json={},
            ),
            "app/routes.py": SourceFile(
                id="source-routes-001", snapshot_id=self.snapshot.id, path="app/routes.py",
                size_bytes=190, language="Python", eligibility_status="eligible", parse_status="parsed",
                redacted_content=(
                    "from fastapi import APIRouter\nfrom app.service import list_products\n"
                    "router = APIRouter()\n@router.get('/products')\ndef get_products():\n"
                    "    return list_products()\n"
                ), metadata_json={},
            ),
            "app/service.py": SourceFile(
                id="source-service-001", snapshot_id=self.snapshot.id, path="app/service.py",
                size_bytes=100, language="Python", eligibility_status="eligible", parse_status="parsed",
                redacted_content="def list_products():\n    return []\n", metadata_json={},
            ),
            "tests/test_routes.py": SourceFile(
                id="source-test-001", snapshot_id=self.snapshot.id, path="tests/test_routes.py",
                size_bytes=100, language="Python", eligibility_status="eligible", parse_status="parsed",
                redacted_content="def test_get_products():\n    assert True\n", metadata_json={},
            ),
        }
        self.db.add_all(self.files.values())
        self.db.flush()
        self.nodes = {
            key: GraphNode(
                id=f"node-{key}", snapshot_id=self.snapshot.id, node_type=node_type,
                stable_key=key, label=label, source_file_id=source_id,
                start_line=1, end_line=4, properties={}, provenance_type="deterministic",
            )
            for key, node_type, label, source_id in [
                ("file:app/main.py", "file", "main.py", self.files["app/main.py"].id),
                ("file:app/routes.py", "file", "routes.py", self.files["app/routes.py"].id),
                ("file:app/service.py", "file", "service.py", self.files["app/service.py"].id),
                ("endpoint:get-products", "endpoint", "GET /products", self.files["app/routes.py"].id),
                ("function:list-products", "function", "list_products", self.files["app/service.py"].id),
            ]
        }
        self.db.add_all(self.nodes.values())
        self.db.flush()
        self.db.add_all([
            GraphEdge(
                id="edge-main-routes-001", snapshot_id=self.snapshot.id,
                source_node_id=self.nodes["file:app/main.py"].id,
                target_node_id=self.nodes["file:app/routes.py"].id,
                relation_type="imports", provenance_type="deterministic", evidence={"path": "app/main.py"},
            ),
            GraphEdge(
                id="edge-routes-service-001", snapshot_id=self.snapshot.id,
                source_node_id=self.nodes["file:app/routes.py"].id,
                target_node_id=self.nodes["file:app/service.py"].id,
                relation_type="imports", provenance_type="deterministic", evidence={"path": "app/routes.py"},
            ),
            GraphEdge(
                id="edge-endpoint-function-001", snapshot_id=self.snapshot.id,
                source_node_id=self.nodes["endpoint:get-products"].id,
                target_node_id=self.nodes["function:list-products"].id,
                relation_type="calls", provenance_type="inferred", evidence={"path": "app/routes.py"},
            ),
        ])
        self.db.commit()

    def close(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()


def test_question_intent_classification_handles_brazilian_portuguese() -> None:
    assert classify_question("Do que se trata o projeto?").intent == "overview"
    assert classify_question("Quais são os principais módulos e como se relacionam?").intent == "architecture"
    assert classify_question("Como os componentes do projeto se relacionam?").intent == "architecture"
    assert classify_question("Como uma requisição chega ao banco de dados?").intent == "flow"
    assert classify_question("Como funciona o sistema?").intent == "flow"
    assert classify_question("O que é o projeto?").intent == "overview"
    assert classify_question("Existem possíveis vazamentos de senha?").intent == "security"
    assert classify_question("Quais dependências o projeto usa?").intent == "dependencies"
    assert classify_question("Quais testes estão presentes?").intent == "tests"
    assert classify_question("Onde está definida a função list_products?").intent == "symbol"


def test_path_roles_prioritize_documentation_manifests_entrypoints_and_tests() -> None:
    assert _path_role("README.md") == "documentation"
    assert _path_role("docs/architecture.md") == "documentation"
    assert _path_role("pyproject.toml") == "manifest"
    assert _path_role("app/main.py") == "entrypoint"
    assert _path_role("tests/test_routes.py") == "test"
    assert _path_role("app/config.py") == "configuration"


def test_overview_retrieval_is_diverse_and_includes_repository_profile_and_graph_relations() -> None:
    fixture = QuestionFixture()
    try:
        plan = classify_question("Do que se trata o projeto?")
        evidence = retrieve_evidence(fixture.db, fixture.run, "Do que se trata o projeto?", intent=plan.intent)
        kinds = {item.kind for item in evidence}
        paths = {item.path for item in evidence if item.path}
        full_text = "\n".join(item.excerpt for item in evidence)

        assert evidence
        assert "repository_profile" in kinds
        assert "project_documentation" in kinds
        assert "manifest" in kinds
        assert "graph_relation" in kinds
        assert "README.md" in paths
        assert "pyproject.toml" in paths
        assert "FastAPI" in full_text
        assert "PostgreSQL" in full_text
        assert "inventory-api" in full_text
        assert len({item.path for item in evidence if item.path}) >= 3
        assert len(evidence) <= 8
        assert all(item.commit_sha == "a" * 40 for item in evidence)
    finally:
        fixture.close()


def test_security_question_retrieval_keeps_explicit_scope() -> None:
    fixture = QuestionFixture()
    try:
        evidence = retrieve_evidence(
            fixture.db,
            fixture.run,
            "Há riscos de segurança nesse serviço?",
            paths=["app"],
        )
        # No files outside the selected subtree may be returned.
        assert evidence
        assert all(item.path is None or item.path.startswith("app/") for item in evidence)
    finally:
        fixture.close()


def test_tests_intent_selects_relevant_chunk_instead_of_only_file_header() -> None:
    fixture = QuestionFixture()
    try:
        # Make this regression independent from the short generic test in the shared fixture.
        fixture.db.delete(fixture.files["tests/test_routes.py"])
        fixture.db.flush()
        lines = [f"# unrelated test helper {index}" for index in range(60)]
        lines.extend([
            "def test_convert_datetime():",
            "    dt2 = LunarDate.from_solar_date(2033, 10, 23)",
            "    self.assertTrue(LunarDate(2033, 10, 1, 0), dt2)",
        ])
        content = "\n".join(lines) + "\n"
        target = SourceFile(
            id="source-test-long-001", snapshot_id=fixture.snapshot.id,
            path="tests/test_aaa.py", size_bytes=len(content), language="Python",
            eligibility_status="eligible", parse_status="parsed",
            redacted_content=content, metadata_json={},
        )
        fixture.db.add(target)
        fixture.db.commit()

        question = "O que o teste test_convert_datetime comprova sobre assertTrue, dt2 e LunarDate?"
        plan = classify_question(question)
        assert plan.intent == "tests"
        evidence = retrieve_evidence(fixture.db, fixture.run, question, intent=plan.intent)
        selected = next(item for item in evidence if item.path == "tests/test_aaa.py" and item.kind == "test")

        assert selected.start_line is not None and selected.start_line > 1
        assert "self.assertTrue(LunarDate(2033, 10, 1, 0), dt2)" in selected.excerpt
    finally:
        fixture.close()


def test_test_question_adds_deterministic_unittest_assertion_note() -> None:
    fixture = QuestionFixture()
    try:
        content = (
            "import unittest\n"
            "from borax.calendars.lunardate import LunarDate\n\n"
            "class LunarDateTestCase(unittest.TestCase):\n"
            "    def test_convert_datetime(self):\n"
            "        dt2 = LunarDate.from_solar_date(2033, 10, 23)\n"
            "        self.assertTrue(LunarDate(2033, 10, 1, 0), dt2)\n"
        )
        fixture.files["tests/test_routes.py"].redacted_content = content
        fixture.db.commit()

        question = "O que o teste test_convert_datetime comprova sobre assertTrue e LunarDate?"
        plan = classify_question(question)
        evidence = retrieve_evidence(fixture.db, fixture.run, question, intent=plan.intent)
        note = next(item for item in evidence if item.kind == "static_analysis_note")

        assert plan.intent == "tests"
        assert note.path == "tests/test_routes.py"
        assert "primeiro argumento é testado por truthiness" in note.excerpt
        assert "segundo argumento posicional é uma mensagem opcional" in note.excerpt
        assert "não testa igualdade entre os dois argumentos" in note.excerpt
        assert "self.assertTrue(LunarDate(2033, 10, 1, 0), dt2)" in note.excerpt
    finally:
        fixture.close()


def test_implementation_question_prioritizes_matching_symbols_tests_docs_and_graph_edges() -> None:
    fixture = QuestionFixture()
    try:
        lunar_content = (
            "from datetime import date\n\n"
            "class LunarDate:\n"
            "    @classmethod\n"
            "    def from_solar_date(cls, year, month, day):\n"
            "        return cls(year, month, day)\n\n"
            "    def to_solar_date(self):\n"
            "        return date(self.year, self.month, self.day)\n"
        )
        lunar_source = SourceFile(
            id="source-lunardate-001", snapshot_id=fixture.snapshot.id,
            path="borax/calendars/lunardate.py", size_bytes=len(lunar_content),
            language="Python", eligibility_status="eligible", parse_status="parsed",
            redacted_content=lunar_content, metadata_json={},
        )
        test_content = (
            "from borax.calendars.lunardate import LunarDate\n\n"
            "def test_from_solar_date():\n"
            "    result = LunarDate.from_solar_date(2024, 2, 10)\n"
            "    assert result.to_solar_date().isoformat() == '2024-02-10'\n"
        )
        lunar_test = SourceFile(
            id="source-test-lunardate-001", snapshot_id=fixture.snapshot.id,
            path="tests/test_lunardate.py", size_bytes=len(test_content),
            language="Python", eligibility_status="eligible", parse_status="parsed",
            redacted_content=test_content, metadata_json={},
        )
        fixture.files["README.md"].redacted_content += (
            "\n## Lunar dates\nThe LunarDate class converts between solar dates and Chinese lunar dates.\n"
        )
        fixture.db.add_all([lunar_source, lunar_test])
        fixture.db.flush()
        lunar_class = GraphNode(
            id="node-lunar-class", snapshot_id=fixture.snapshot.id, node_type="class",
            stable_key="class:borax.calendars.lunardate.LunarDate", label="LunarDate",
            source_file_id=lunar_source.id, start_line=3, end_line=8,
            properties={}, provenance_type="deterministic",
        )
        solar_fn = GraphNode(
            id="node-lunar-solar-fn", snapshot_id=fixture.snapshot.id, node_type="method",
            stable_key="method:LunarDate.from_solar_date", label="from_solar_date",
            source_file_id=lunar_source.id, start_line=4, end_line=5,
            properties={}, provenance_type="deterministic",
        )
        test_fn = GraphNode(
            id="node-lunar-test", snapshot_id=fixture.snapshot.id, node_type="test",
            stable_key="test:test_from_solar_date", label="test_from_solar_date",
            source_file_id=lunar_test.id, start_line=3, end_line=4,
            properties={}, provenance_type="deterministic",
        )
        fixture.db.add_all([lunar_class, solar_fn, test_fn])
        fixture.db.flush()
        fixture.db.add_all([
            GraphEdge(
                id="edge-lunar-defines", snapshot_id=fixture.snapshot.id,
                source_node_id=lunar_class.id, target_node_id=solar_fn.id,
                relation_type="defines", provenance_type="deterministic",
                evidence={"path": lunar_source.path, "note": "class method"},
            ),
            GraphEdge(
                id="edge-lunar-tested-by", snapshot_id=fixture.snapshot.id,
                source_node_id=solar_fn.id, target_node_id=test_fn.id,
                relation_type="tested_by", provenance_type="deterministic",
                evidence={"path": lunar_test.path},
            ),
        ])
        fixture.db.commit()

        question = (
            "Investigue especificamente o módulo de datas lunares. Identifique as classes e funções públicas "
            "relacionadas a esse recurso e use exemplos reais do código, da documentação e dos testes."
        )
        plan = classify_question(question)
        evidence = retrieve_evidence(fixture.db, fixture.run, question, intent=plan.intent)
        paths = {item.path for item in evidence if item.path}
        kinds = {item.kind for item in evidence}
        full_text = "\n".join(item.excerpt for item in evidence)

        assert plan.intent == "implementation"
        assert any(path == "borax/calendars/lunardate.py" for path in paths)
        assert "tests/test_lunardate.py" in paths
        assert "README.md" in paths
        assert "source_definition" in kinds
        assert "test_code" in kinds
        assert "project_documentation" in kinds
        assert "LunarDate" in full_text
        assert "from_solar_date" in full_text
        assert "Relação extraída do grafo" in full_text
        assert len(evidence) <= 8
    finally:
        fixture.close()


def test_implementation_question_is_not_misclassified_as_dependencies_when_it_mentions_a_library() -> None:
    question = (
        "Investigue especificamente o módulo de datas lunares. Identifique as classes e funções públicas "
        "relacionadas a esse recurso. Use exemplos reais do código, da documentação e dos testes para mostrar "
        "quais entradas recebem e quais resultados produzem. Depois, explique a diferença entre utilizar "
        "essa biblioteca dentro de um programa e pesquisar uma data no Google. Não se limite ao README."
    )
    assert classify_question(question).intent == "implementation"


def test_identifier_matching_splits_camel_case_and_expands_portuguese_lunar_terms() -> None:
    from app.application.questions import _expand_query, _terms

    terms = _terms("LunarDate.from_solar_date")
    expanded = _expand_query("módulo de datas lunares", _terms("módulo de datas lunares"))

    assert {"lunar", "date", "solar", "from_solar_date"} <= terms
    assert {"lunar", "date", "calendar", "lunardate", "solar"} <= expanded


def test_documented_example_retrieval_uses_symbols_found_in_implementation() -> None:
    """A guide containing the exact implementation symbol should beat adjacent generic docs."""
    fixture = QuestionFixture()
    try:
        source = SourceFile(
            id="source-lunardate-implementation", snapshot_id=fixture.snapshot.id,
            path="borax/calendars/lunardate.py", size_bytes=250,
            language="Python", eligibility_status="eligible", parse_status="parsed",
            redacted_content=(
                "class LunarDate:\n"
                "    @classmethod\n"
                "    def from_solar_date(cls, year, month, day):\n"
                "        return cls.from_solar(date(year, month, day))\n"
                "\n"
                "    @classmethod\n"
                "    def from_solar(cls, solar_date):\n"
                "        offset = (solar_date - MIN_SOLAR_DATE).days\n"
                "        year, month, day, leap = offset2ymdl(offset)\n"
                "        return cls(year, month, day, leap)\n"
            ), metadata_json={},
        )
        test_source = SourceFile(
            id="source-lunardate-test", snapshot_id=fixture.snapshot.id,
            path="tests/test_lunardate.py", size_bytes=150,
            language="Python", eligibility_status="eligible", parse_status="parsed",
            redacted_content=(
                "def test_convert_datetime():\n"
                "    result = LunarDate.from_solar_date(2033, 10, 23)\n"
                "    assert result == LunarDate(2033, 10, 1, 0)\n"
            ), metadata_json={},
        )
        relevant_doc = SourceFile(
            id="source-lunardate-doc", snapshot_id=fixture.snapshot.id,
            path="docs/guides/lunardate.md", size_bytes=180,
            language="Markdown", eligibility_status="eligible", parse_status="unsupported",
            redacted_content=(
                "# LunarDate\n\n"
                "Convert a solar date to a lunar date using the documented example.\n\n"
                "```python\n"
                "ld = LunarDate.from_solar_date(2018, 8, 11)\n"
                "# LunarDate(2018, 7, 1, 0)\n"
                "```\n"
            ), metadata_json={},
        )
        distractor_doc = SourceFile(
            id="source-festivals-doc", snapshot_id=fixture.snapshot.id,
            path="docs/guides/festivals2.md", size_bytes=300,
            language="Markdown", eligibility_status="eligible", parse_status="unsupported",
            redacted_content=(
                "# Lunar calendar festivals\n\n"
                "LunarDate is used by LunarFestival, WrappedDate, Period and calendar utilities.\n"
                "These guides describe festivals, lunar dates, solar dates, holidays, dates and calendars.\n"
                "Use LunarDate to identify common Chinese calendar festivals.\n"
            ), metadata_json={},
        )
        fixture.db.add_all([source, test_source, relevant_doc, distractor_doc])
        fixture.db.flush()
        fixture.db.add_all([
            GraphNode(
                id="node-lunardate-class", snapshot_id=fixture.snapshot.id, node_type="class",
                stable_key="class:LunarDate", label="LunarDate", source_file_id=source.id,
                start_line=1, end_line=12, properties={}, provenance_type="deterministic",
            ),
            GraphNode(
                id="node-from-solar-date", snapshot_id=fixture.snapshot.id, node_type="method",
                stable_key="method:LunarDate.from_solar_date", label="from_solar_date",
                source_file_id=source.id, start_line=3, end_line=4,
                properties={}, provenance_type="deterministic",
            ),
        ])
        fixture.db.commit()

        question = (
            "Mostre um exemplo documentado de conversão de uma data solar para LunarDate "
            "e a implementação correspondente."
        )
        evidence = retrieve_evidence(fixture.db, fixture.run, question)
        paths = [item.path for item in evidence if item.path]
        relevant_items = [item for item in evidence if item.path == "docs/guides/lunardate.md"]

        assert classify_question(question).intent == "implementation"
        assert relevant_items, f"A documentação que contém o exemplo não foi recuperada: {paths}"
        assert any("from_solar_date" in item.excerpt for item in relevant_items)
        if "docs/guides/festivals2.md" in paths:
            assert paths.index("docs/guides/lunardate.md") < paths.index("docs/guides/festivals2.md")
    finally:
        fixture.close()


def test_tests_intent_prioritizes_test_files_relevant_to_the_question() -> None:
    """Relevant test paths should use curated slots before unrelated alphabetic neighbors."""
    fixture = QuestionFixture()
    try:
        lunar_source = SourceFile(
            id="source-lunardate-tests-target", snapshot_id=fixture.snapshot.id,
            path="tests/test_lunardate.py", size_bytes=180,
            language="Python", eligibility_status="eligible", parse_status="parsed",
            redacted_content=(
                "def test_convert_solar_to_lunar_date():\n"
                "    lunar_date = LunarDate.from_solar_date(2033, 10, 23)\n"
                "    assert lunar_date == LunarDate(2033, 10, 1, 0)\n"
            ), metadata_json={},
        )
        distractors = [
            SourceFile(
                id="source-test-auth", snapshot_id=fixture.snapshot.id,
                path="tests/test_auth.py", size_bytes=80, language="Python",
                eligibility_status="eligible", parse_status="parsed",
                redacted_content="def test_login_requires_session():\n    assert True\n", metadata_json={},
            ),
            SourceFile(
                id="source-test-config", snapshot_id=fixture.snapshot.id,
                path="tests/test_config.py", size_bytes=80, language="Python",
                eligibility_status="eligible", parse_status="parsed",
                redacted_content="def test_config_defaults():\n    assert True\n", metadata_json={},
            ),
            SourceFile(
                id="source-test-json", snapshot_id=fixture.snapshot.id,
                path="tests/test_json.py", size_bytes=80, language="Python",
                eligibility_status="eligible", parse_status="parsed",
                redacted_content="def test_json_roundtrip():\n    assert True\n", metadata_json={},
            ),
        ]
        fixture.db.add_all([lunar_source, *distractors])
        fixture.db.commit()

        question = "Quais testes exercitam a criação e conversão de datas lunares?"
        evidence = retrieve_evidence(fixture.db, fixture.run, question)
        paths = list(dict.fromkeys(item.path for item in evidence if item.path))

        assert classify_question(question).intent == "tests"
        assert "tests/test_lunardate.py" in paths
        if "tests/test_json.py" in paths:
            assert paths.index("tests/test_lunardate.py") < paths.index("tests/test_json.py")
    finally:
        fixture.close()

"""Question-aware, lexical/structural evidence retrieval for repository questions.

The retriever never treats repository content as instructions. All source excerpts come
from the redacted snapshot already persisted by the static analyzer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AnalysisRun,
    Finding,
    GraphEdge,
    GraphNode,
    Repository,
    RepositorySnapshot,
    SourceFile,
)

_WORD = re.compile(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]{1,}")
_STOP_WORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "dela", "dele",
    "do", "dos", "e", "ela", "ele", "em", "entre", "essa", "esse", "esta", "este",
    "eu", "foi", "for", "from", "há", "isso", "isto", "mais", "mas", "me", "minha",
    "meu", "na", "nas", "no", "nos", "o", "os", "ou", "para", "pela", "pelas",
    "pelo", "pelos", "por", "que", "se", "sem", "ser", "seu", "sua", "the", "this",
    "to", "um", "uma", "umas", "uns", "what", "when", "where", "which", "who", "why",
    "with", "and", "are", "can", "does", "how", "is", "it", "of", "on", "or", "than",
    "then", "there", "this", "was", "were", "will", "you", "your",
    # Common instruction words add little retrieval value; technical concepts are expanded separately.
    "investigue", "investigar", "especificamente", "identifique", "relacionadas", "relacionados",
    "publicas", "publicos", "entradas", "recebem", "resultados", "produzem", "explique",
    "diferencie", "vantagens", "tecnicas", "demonstraveis", "motivacoes", "autor",
    "documentadas", "documentacao", "arquivo", "arquivos", "codigo", "fonte", "fontes",
    "reais", "utilizar", "utilizada", "utilizadas", "utilizado", "implementadas",
    "implementados", "implementar", "implementacao", "modulo", "modulos", "classe", "classes",
    "funcao", "funcoes", "testes", "exemplos", "exemplo", "inclua", "mostre", "identificar",
    "quais", "qual", "sobre", "necessarias", "necessarios", "precisa", "precisam", "poderia",
    "deve", "devem", "realmente", "especifico", "especifica", "relacionado", "relacionada",
}

INTENT_LABELS = {
    "overview": "Visão geral do projeto",
    "architecture": "Arquitetura e módulos",
    "flow": "Fluxo de execução",
    "security": "Segurança e AppSec",
    "dependencies": "Dependências e configuração",
    "tests": "Testes e confiabilidade",
    "implementation": "Implementação, APIs e exemplos",
    "symbol": "Símbolo ou trecho específico",
    "general": "Pergunta geral",
}

INTENT_GUIDANCE = {
    "overview": (
        "Explique propósito, problema que o projeto parece resolver, funcionalidades observadas, "
        "tecnologias e componentes centrais. Dê prioridade à documentação do repositório, aos "
        "manifestos e a pontos de entrada reais. Separe o que a documentação declara do que o "
        "código efetivamente demonstra. Não descreva funcionalidades que as evidências não sustentam."
    ),
    "architecture": (
        "Explique a organização por camadas/módulos e as relações encontradas no grafo. Prefira "
        "imports e relações determinísticas; rotule chamadas ou relações inferidas como tais. Evite "
        "inferir arquitetura apenas a partir dos nomes das pastas."
    ),
    "flow": (
        "Reconstrua o fluxo em sequência a partir de endpoints, pontos de entrada, funções e "
        "relações disponíveis. Cite cada etapa. Se a sequência completa não estiver representada, "
        "mostre o trecho confirmado e identifique o elo ausente."
    ),
    "security": (
        "Priorize achados persistidos e trechos relevantes de configuração/código. Distinga possível "
        "exposição de segredo de credencial comprovadamente ativa; nunca revele valores redigidos. "
        "Não declare o projeto seguro nem confirme explorabilidade sem evidência suficiente."
    ),
    "dependencies": (
        "Priorize manifestos e arquivos de configuração de dependências. Informe apenas pacotes e "
        "versões observados; não deduza vulnerabilidade só por uma versão antiga."
    ),
    "tests": (
        "Priorize arquivos de teste, nomes de testes e componentes relacionados. Diferencie testes "
        "encontrados de cobertura efetivamente medida; a análise estática não executa os testes do alvo."
    ),
    "implementation": (
        "Investigue a implementação, não apenas o README. Priorize definições reais de classes, funções e métodos "
        "no código-fonte; depois procure testes e exemplos que demonstrem entradas e resultados. Use relações do grafo "
        "para conectar os componentes envolvidos. Inclua arquivos e linhas. Documentação explica a intenção, mas não "
        "comprova que uma funcionalidade esteja implementada. Se o parser não reconheceu um arquivo, diga isso; não "
        "trate a falta de nós no grafo como prova de que o código não existe."
    ),
    "symbol": (
        "Responda sobre o símbolo, arquivo ou endpoint nomeado. Prefira a definição e suas relações "
        "diretas. Inclua caminhos/linhas, e não extrapole para partes não recuperadas."
    ),
    "general": (
        "Responda à pergunta específica usando evidências diretamente relevantes e relações próximas. "
        "Se a recuperação não cobrir uma parte necessária, explique a lacuna em vez de adivinhar."
    ),
}

# Path roles are deliberately heuristic and only influence retrieval priority; they do not
# establish architectural facts.
_MANIFEST_NAMES = {
    "pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements.in",
    "pipfile", "pipfile.lock", "poetry.lock", "package.json", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "build.gradle.kts", "composer.json", "gemfile", "gemfile.lock", "docker-compose.yml",
    "docker-compose.yaml", "compose.yml", "compose.yaml",
}
_ENTRYPOINT_NAMES = {
    "main.py", "app.py", "__main__.py", "asgi.py", "wsgi.py", "server.py",
    "main.ts", "main.tsx", "index.ts", "index.tsx", "server.ts", "app.ts",
    "application.py", "manage.py",
}
_CONFIG_NAMES = {
    ".env.example", "config.py", "settings.py", "settings.toml", "config.toml",
    "config.yaml", "config.yml", "application.yml", "application.yaml", "dockerfile",
    "alembic.ini", "vite.config.ts", "tsconfig.json",
}


@dataclass(frozen=True, slots=True)
class QuestionPlan:
    intent: str
    label: str
    guidance: str
    retrieval_terms: tuple[str, ...]
    strategy: str


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def classify_question(question: str) -> QuestionPlan:
    """Classify question intent deterministically, without sending it to another model call."""
    folded = _fold(question)
    rules: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
        ("security", ("appsec", "segredo", "senha", "token", "vazamento", "vulnerabilidade", "vulnerabilidades", "injeção", "injection", "autorizacao", "autenticacao", "risco de seguranca", "seguranca"), ("finding", "configuration", "source_code", "graph_relation")),
        # Specific implementation requests take precedence over generic mentions of a library or tests.
        ("implementation", ("investigue", "investigar", "implementacao", "implementada no codigo", "implementado no codigo", "funcoes publicas", "classes e funcoes", "funcoes e metodos", "arquivos responsaveis", "onde esta implementado", "onde esta implementada", "entradas e resultados", "entradas recebem", "exemplos reais do codigo", "nao se limite ao readme", "nao se limite a documentacao", "codigo-fonte", "source implementation", "implementation details", "how is implemented"), ("source_definition", "source_code", "test", "example", "graph_relation", "documentation")),
        ("dependencies", ("dependencia", "dependencias", "quais bibliotecas usa", "qual biblioteca usa", "bibliotecas usadas", "bibliotecas utilizadas", "pacote", "pacotes", "package", "requirements", "versao do framework"), ("manifest", "configuration", "source_code", "graph_relation")),
        ("tests", ("teste", "testes", "test suite", "testes automatizados", "cobertura", "coverage", "pytest", "qualidade dos testes"), ("test", "source_code", "graph_relation", "manifest")),
        ("flow", ("fluxo", "fluxo de dados", "fluxo de execucao", "caminho de execucao", "o que acontece quando", "como uma requisicao", "como a requisicao", "request chega", "end to end", "passo a passo", "chamada passa", "como funciona", "como o sistema funciona", "como a aplicacao funciona"), ("entrypoint", "source_code", "graph_relation", "configuration")),
        ("architecture", ("arquitetura", "modulos principais", "principais modulos", "modulos e como se relacionam", "modulos se relacionam", "como os modulos se relacionam", "como os componentes se relacionam", "componentes do projeto", "como esta organizado", "como se organiza", "camadas", "componentes se relacionam", "dependem entre si", "estrutura interna", "estrutura do projeto"), ("documentation", "manifest", "entrypoint", "source_code", "graph_relation")),
        ("overview", ("do que se trata", "sobre o projeto", "o que e o projeto", "o que e esse projeto", "o que e este projeto", "o que faz esse projeto", "o que faz este projeto", "o que faz o projeto", "o que e esse sistema", "o que faz esse sistema", "sobre o que e este projeto", "objetivo do projeto", "objetivo do sistema", "proposito do projeto", "para que serve", "visao geral", "resuma o projeto", "descreva o projeto", "what is this project", "project overview"), ("documentation", "manifest", "entrypoint", "source_code", "graph_relation")),
    )
    for intent, phrases, roles in rules:
        if any(_fold(phrase) in folded for phrase in phrases):
            return QuestionPlan(
                intent=intent,
                label=INTENT_LABELS[intent],
                guidance=INTENT_GUIDANCE[intent],
                retrieval_terms=tuple(_intent_expansion(intent)),
                strategy=f"recuperação direcionada: {', '.join(roles)}",
            )

    # Symbol questions and path-shaped questions should retain lexical precision.
    if re.search(r"\b(def|class|function|funcao|funcoes|metodo|method|endpoint|rota|symbol|simbolo|linha|classe|classes)\b", folded) or re.search(r"[\w./-]+\.(?:py|tsx?|java|go|rs|toml|ya?ml|json|cpp|h)\b", question, re.IGNORECASE):
        intent = "symbol"
    else:
        intent = "general"
    return QuestionPlan(
        intent=intent,
        label=INTENT_LABELS[intent],
        guidance=INTENT_GUIDANCE[intent],
        retrieval_terms=tuple(_intent_expansion(intent)),
        strategy="busca lexical e expansão estrutural",
    )


def _intent_expansion(intent: str) -> set[str]:
    expansions = {
        "overview": {"readme", "purpose", "objetivo", "funcionalidades", "features", "application", "app", "main", "entrypoint", "project", "projeto"},
        "architecture": {"architecture", "arquitetura", "module", "modulo", "imports", "routes", "router", "service", "controller", "repository", "database", "model", "component"},
        "flow": {"endpoint", "route", "router", "request", "handler", "service", "call", "calls", "chamada", "fluxo", "entrypoint", "main", "app"},
        "security": {"secret", "secrets", "credential", "credentials", "token", "password", "auth", "authorization", "security", "vulnerability", "finding", "segredo", "credencial"},
        "dependencies": {"dependency", "dependencies", "package", "packages", "requirements", "pyproject", "package.json", "version", "imports"},
        "tests": {"test", "tests", "pytest", "assert", "coverage", "spec", "testing"},
        "implementation": set(),
        "symbol": set(),
        "general": set(),
    }
    return expansions.get(intent, set())


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    id: str
    kind: str
    path: str | None
    start_line: int | None
    end_line: int | None
    commit_sha: str
    url: str | None
    excerpt: str
    score: float

    def to_dict(self, *, include_score: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "commit_sha": self.commit_sha,
            "url": self.url,
            "excerpt": self.excerpt,
        }
        if include_score:
            result["score"] = self.score
        return result


_TERM_ALIASES: dict[str, set[str]] = {
    # Portuguese-to-source-code vocabulary bridge. This is lexical expansion, not a claim
    # that any mapped feature exists in a given repository.
    "data": {"date", "datetime", "calendar"}, "datas": {"date", "dates", "datetime", "calendar"},
    "lunar": {"lunardate", "lunar_date", "calendar", "calendars"},
    "lunares": {"lunar", "lunardate", "lunar_date", "calendar", "calendars"},
    "calendario": {"calendar", "calendars", "date", "dates"},
    "calendarios": {"calendar", "calendars", "date", "dates"},
    "feriado": {"holiday", "holidays", "festival", "festivals"},
    "feriados": {"holiday", "holidays", "festival", "festivals"},
    "funcao": {"function", "functions", "def"}, "funcoes": {"function", "functions", "def"},
    "classe": {"class", "classes"}, "classes": {"class", "classes"},
    "metodo": {"method", "methods"}, "metodos": {"method", "methods"},
    "modulo": {"module", "modules", "package"}, "modulos": {"module", "modules", "package"},
    "dependencia": {"dependency", "dependencies", "requirements"},
    "dependencias": {"dependency", "dependencies", "requirements"},
    "teste": {"test", "tests", "spec"}, "testes": {"test", "tests", "spec"},
    "exemplo": {"example", "examples", "sample"}, "exemplos": {"example", "examples", "sample"},
    "entrada": {"input", "inputs", "argument"}, "entradas": {"input", "inputs", "argument"},
    "saida": {"output", "outputs", "result"}, "resultado": {"result", "return", "output"},
    "resultados": {"result", "return", "output"},
    "documentacao": {"documentation", "readme", "docs"},
    "requisicao": {"request", "route", "endpoint", "handler"},
    "banco": {"database", "db", "repository", "model"},
    "seguranca": {"security", "auth", "authorization", "secret"},
    "arquivo": {"file", "source", "path"}, "arquivos": {"file", "files", "source", "path"},
    "numeros": {"number", "numbers", "numeral"}, "chineses": {"chinese", "zh"},
}


def _terms(text: str) -> set[str]:
    # Split CamelCase before case-folding so `LunarDate` matches both `lunar` and `date`.
    camel_split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    folded = _fold(camel_split)
    values: set[str] = set()
    for match in _WORD.findall(folded):
        values.add(match)
        values.update(part for part in re.split(r"[_./:\-]+", match) if len(part) >= 2)
    values = {value for value in values if len(value) >= 2 and value not in _STOP_WORDS}
    # Only normalize morphology here. Cross-language aliases are applied to the question
    # in _expand_query, not to every source snippet; otherwise generic words like "class"
    # make unrelated source files appear relevant.
    plural_aliases = {
        "functions": "function", "funcoes": "funcao", "classes": "class", "methods": "method",
        "metodos": "metodo", "modules": "module", "modulos": "modulo", "tests": "test",
        "testes": "teste", "examples": "example", "exemplos": "exemplo", "dates": "date",
        "datas": "data", "calendars": "calendar", "dependencies": "dependency", "dependencias": "dependencia",
        "files": "file", "arquivos": "arquivo", "inputs": "input", "entradas": "entrada",
        "outputs": "output", "resultados": "resultado", "holidays": "holiday", "feriados": "feriado",
        "festivals": "festival", "lunares": "lunar",
    }
    values.update(plural_aliases[value] for value in list(values) if value in plural_aliases)
    return {value for value in values if len(value) >= 2 and value not in _STOP_WORDS}


def _score(query_terms: set[str], text: str, path: str = "") -> float:
    content_terms = _terms(text)
    path_terms = _terms(path)
    return sum(3.0 if term in path_terms else 1.0 for term in query_terms if term in content_terms | path_terms)


def _line_excerpt(source_file: SourceFile, start_line: int | None, end_line: int | None, *, max_lines: int = 46, max_chars: int = 3600) -> tuple[int, int, str] | None:
    """Return a bounded snippet around a known symbol location rather than always taking file headers."""
    content = source_file.redacted_content
    if not content:
        return None
    lines = content.splitlines()
    if not lines:
        return None
    start = max(1, min(start_line or 1, len(lines)))
    declared_end = max(start, min(end_line or (start + max_lines - 1), len(lines)))
    if declared_end - start + 1 > max_lines:
        declared_end = start + max_lines - 1
    snippet = "\n".join(lines[start - 1:declared_end])[:max_chars]
    if not snippet.strip():
        return None
    actual_end = min(declared_end, start + snippet.count("\n"))
    return start, actual_end, snippet


def _expand_query(question: str, terms: set[str]) -> set[str]:
    """Expand semantic domain terms so Portuguese questions can find English identifiers."""
    expanded = set(terms)
    folded = _fold(question)
    for term in list(expanded):
        expanded.update(_TERM_ALIASES.get(term, set()))
    phrase_aliases: tuple[tuple[tuple[str, ...], set[str]], ...] = (
        (("data lunar", "datas lunares", "calendario lunar", "calendario chines", "lunar date", "lunar dates"),
         {"lunar", "lunardate", "lunar_date", "calendar", "calendars", "date", "dates", "solar", "from_solar_date", "to_solar_date", "festival", "festivals"}),
        (("numeros chineses", "numero chines", "numeros em chines"), {"chinese", "number", "numbers", "numeral", "numerals"}),
        (("feriados", "feriado", "festivais", "festival"), {"holiday", "holidays", "festival", "festivals", "calendar", "calendars"}),
    )
    for phrases, aliases in phrase_aliases:
        if any(_fold(phrase) in folded for phrase in phrases):
            expanded.update(_terms(" ".join(aliases)))
    # Preserve explicit code-like identifiers supplied anywhere in the question.
    for identifier in re.findall(r"[A-Z][A-Za-z0-9]*(?:[._][A-Za-z0-9_]+)*|[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+", question):
        expanded.update(_terms(identifier))
    return expanded


def _path_role(path: str) -> str:
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    name = parts[-1].casefold() if parts else ""
    if name.startswith("readme") or ("docs" in {part.casefold() for part in parts[:-1]} and name.endswith((".md", ".rst", ".txt"))):
        return "documentation"
    if name in _MANIFEST_NAMES or name.startswith("requirements") and name.endswith((".txt", ".in")):
        return "manifest"
    if "test" in {part.casefold() for part in parts[:-1]} or "tests" in {part.casefold() for part in parts[:-1]} or name.startswith("test_") or name.endswith(("_test.py", ".spec.ts", ".test.ts", ".test.tsx")):
        return "test"
    if any(part.casefold() in {"example", "examples", "sample", "samples", "demo", "demos"} for part in parts[:-1]) or name.startswith(("example_", "sample_", "demo_")):
        return "example"
    if name in _ENTRYPOINT_NAMES:
        return "entrypoint"
    if name in _CONFIG_NAMES or name.startswith(".env.") or name.endswith((".ini", ".conf")):
        return "configuration"
    if name.endswith((".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".cs", ".kt", ".rb", ".php", ".swift")):
        return "source_code"
    return "other"


def _source_url(repository: Repository, snapshot: RepositorySnapshot, path: str | None, line: int | None) -> str | None:
    if not path:
        return None
    url = f"{repository.canonical_url}/blob/{snapshot.commit_sha}/{quote(path, safe='/')}"
    if line:
        url += f"#L{line}"
    return url


def _scored_code_chunks(
    source_file: SourceFile,
    query_terms: set[str],
    *,
    intent: str = "general",
) -> list[tuple[float, int, int, str]]:
    if not source_file.redacted_content:
        return []
    lines = source_file.redacted_content.splitlines()
    if not lines:
        return []
    chunk_size = 38
    overlap = 8
    step = chunk_size - overlap
    candidates: list[tuple[float, int, int, str]] = []
    role = _path_role(source_file.path)
    role_bonus = {
        "overview": {"documentation": 14, "manifest": 9, "entrypoint": 7, "source_code": 1},
        "architecture": {"documentation": 5, "manifest": 6, "entrypoint": 10, "source_code": 5},
        "flow": {"entrypoint": 12, "source_code": 7, "configuration": 4},
        "security": {"configuration": 10, "source_code": 5, "manifest": 3},
        "dependencies": {"manifest": 18, "configuration": 4, "source_code": 2},
        "tests": {"test": 18, "source_code": 3},
        "implementation": {"source_code": 8, "entrypoint": 6, "test": 5, "example": 4, "documentation": 2},
        "symbol": {"source_code": 2, "entrypoint": 2},
        "general": {},
    }.get(intent, {})
    start = 0
    while start < len(lines):
        part = lines[start : start + chunk_size]
        excerpt = "\n".join(part)
        if excerpt.strip():
            # Text matches determine ordering within a file. Path matches contribute only a small bonus;
            # otherwise every chunk in `lunardate.py` ties and the first generic header always wins.
            score = _score(query_terms, excerpt) + 0.25 * _score(query_terms, source_file.path)
            declared_names = " ".join(
                re.findall(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", excerpt, flags=re.MULTILINE)
                + re.findall(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", excerpt, flags=re.MULTILINE)
            )
            declared_terms = _terms(declared_names)
            score += 4.0 * len(query_terms & declared_terms)
            score += role_bonus.get(role, 0)
            # Early chunks tend to contain module docstrings/imports/configuration, useful for purpose and structure.
            if start == 0 and intent in {"overview", "architecture", "flow"}:
                score += 2.0
            if score > 0:
                candidates.append((score, start + 1, start + len(part), excerpt[:4500]))
        if start + chunk_size >= len(lines):
            break
        start += step
    candidates.sort(key=lambda item: (-item[0], item[1]))
    # One strong chunk per file is usually more useful than two chunks from one file, so the caller handles diversity.
    return candidates[:3]


def _excerpt(source_file: SourceFile, *, max_chars: int, max_lines: int) -> tuple[int, int, str] | None:
    content = source_file.redacted_content
    if not content or not content.strip():
        return None
    lines = content.splitlines()
    selected = lines[:max_lines]
    text = "\n".join(selected)[:max_chars]
    if not text.strip():
        return None
    end_line = min(len(selected), text.count("\n") + 1)
    return 1, end_line, text


def _repository_profile(
    repository: Repository,
    snapshot: RepositorySnapshot,
    source_files: list[SourceFile],
    nodes: list[GraphNode],
    edges: list[GraphEdge],
) -> str:
    extension_counts: dict[str, int] = {}
    parse_counts: dict[str, int] = {}
    top_directories: dict[str, int] = {}
    for source in source_files:
        name = source.path.rsplit("/", 1)[-1]
        extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name and not name.startswith(".") else "[sem extensão]"
        extension_counts[extension] = extension_counts.get(extension, 0) + 1
        parse_counts[source.parse_status] = parse_counts.get(source.parse_status, 0) + 1
        first = source.path.split("/", 1)[0] if "/" in source.path else "[raiz]"
        top_directories[first] = top_directories.get(first, 0) + 1
    node_counts: dict[str, int] = {}
    for node in nodes:
        node_counts[node.node_type] = node_counts.get(node.node_type, 0) + 1
    relation_counts: dict[str, int] = {}
    for edge in edges:
        key = f"{edge.relation_type} ({edge.provenance_type})"
        relation_counts[key] = relation_counts.get(key, 0) + 1
    metadata = snapshot.metadata_json if isinstance(snapshot.metadata_json, dict) else {}
    description = (repository.description or metadata.get("description") or "Não informada pelo GitHub.")
    return "\n".join([
        "PERFIL DETERMINÍSTICO DO REPOSITÓRIO (contagens dos dados persistidos)",
        f"Repositório: {repository.owner}/{repository.name}",
        f"Descrição publicada no GitHub: {description}",
        f"URL canônica: {repository.canonical_url}",
        f"Commit analisado: {snapshot.commit_sha}",
        f"Referência solicitada: {snapshot.requested_ref}",
        f"Arquivos inventariados no snapshot: {len(source_files)}",
        "Extensões mais frequentes: " + (", ".join(f"{key}={value}" for key, value in sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))[:8]) or "nenhuma"),
        "Diretórios/raízes mais frequentes: " + (", ".join(f"{key}={value}" for key, value in sorted(top_directories.items(), key=lambda item: (-item[1], item[0]))[:8]) or "nenhum"),
        "Estados de parsing: " + (", ".join(f"{key}={value}" for key, value in sorted(parse_counts.items())) or "nenhum"),
        "Nós do grafo por tipo: " + (", ".join(f"{key}={value}" for key, value in sorted(node_counts.items())) or "nenhum"),
        "Relações do grafo por tipo/proveniência: " + (", ".join(f"{key}={value}" for key, value in sorted(relation_counts.items())) or "nenhuma"),
        "Limitação: o perfil resume apenas arquivos obtidos e entidades extraídas pela análise; não representa compreensão completa do repositório.",
    ])


def retrieve_evidence(
    db: Session,
    run: AnalysisRun,
    question: str,
    *,
    node_ids: list[str] | None = None,
    paths: list[str] | None = None,
    intent: str | None = None,
) -> list[RetrievedEvidence]:
    """Retrieve intent-appropriate, redacted evidence from a single immutable snapshot."""
    if not run.snapshot_id:
        return []
    snapshot = db.get(RepositorySnapshot, run.snapshot_id)
    repository = db.get(Repository, run.repository_id)
    if snapshot is None or repository is None:
        return []

    plan = classify_question(question)
    question_intent = intent or plan.intent
    query_terms = _expand_query(question, _terms(question) | set(plan.retrieval_terms))
    if not query_terms:
        query_terms = {question.strip().casefold()}

    all_source_files = db.scalars(
        select(SourceFile).where(
            SourceFile.snapshot_id == snapshot.id,
            SourceFile.redacted_content.is_not(None),
        ).order_by(SourceFile.path).limit(max(5000, settings.max_files + 1))
    ).all()
    source_by_id = {source_file.id: source_file for source_file in all_source_files}

    selected_source_ids: set[str] | None = None
    if node_ids:
        matched_nodes = db.scalars(
            select(GraphNode).where(
                GraphNode.snapshot_id == snapshot.id,
                GraphNode.id.in_(node_ids),
            )
        ).all()
        if len({node.id for node in matched_nodes}) != len(set(node_ids)):
            return []
        selected_source_ids = {node.source_file_id for node in matched_nodes if node.source_file_id}
        if not selected_source_ids:
            return []

    source_files = all_source_files
    if paths:
        normalized_paths = [path.strip().strip("/") for path in paths]
        source_files = [
            item for item in source_files
            if any(item.path == path or item.path.startswith(path + "/") for path in normalized_paths)
        ]
    if selected_source_ids:
        source_files = [item for item in source_files if item.id in selected_source_ids]
    scoped = bool(node_ids or paths)

    nodes = db.scalars(
        select(GraphNode).where(GraphNode.snapshot_id == snapshot.id)
        .order_by(GraphNode.node_type, GraphNode.label).limit(10000)
    ).all()
    node_by_id = {node.id: node for node in nodes}
    edges = db.scalars(
        select(GraphEdge).where(GraphEdge.snapshot_id == snapshot.id)
        .order_by(GraphEdge.relation_type, GraphEdge.id).limit(10000)
    ).all()

    context_char_budget = max(2500, settings.ai_max_context_chars)
    max_evidence = max(1, settings.ai_max_evidence_items)
    candidates: list[RetrievedEvidence] = []
    used_chars = 0
    seen_signatures: set[tuple[str, str, int | None, int | None]] = set()

    def add_evidence(
        *, kind: str, path: str | None, start_line: int | None, end_line: int | None,
        excerpt: str, score: float, url: str | None = None,
    ) -> bool:
        nonlocal used_chars
        if len(candidates) >= max_evidence or used_chars >= context_char_budget:
            return False
        signature = (kind, path or "", start_line, end_line)
        if signature in seen_signatures:
            return False
        remaining = context_char_budget - used_chars
        if remaining < 150:
            return False
        safe_excerpt = excerpt[: min(remaining, 4500)]
        if not safe_excerpt.strip():
            return False
        candidates.append(RetrievedEvidence(
            id=f"E{len(candidates) + 1}", kind=kind, path=path,
            start_line=start_line, end_line=end_line, commit_sha=snapshot.commit_sha,
            url=url or _source_url(repository, snapshot, path, start_line),
            excerpt=safe_excerpt, score=score,
        ))
        used_chars += len(safe_excerpt)
        seen_signatures.add(signature)
        return True

    # A repository-level profile is generated from persisted metadata and counts, never by the LLM.
    if question_intent in {"overview", "architecture", "general"} and not scoped:
        profile = _repository_profile(repository, snapshot, source_files, nodes, edges)
        add_evidence(kind="repository_profile", path=None, start_line=None, end_line=None, excerpt=profile, score=100.0, url=None)

    role_rank = {
        "overview": {"documentation": 0, "manifest": 1, "entrypoint": 2, "configuration": 3, "source_code": 4, "test": 5},
        "architecture": {"documentation": 0, "manifest": 1, "entrypoint": 2, "source_code": 3, "configuration": 4, "test": 5},
        "flow": {"entrypoint": 0, "source_code": 1, "configuration": 2, "documentation": 3, "manifest": 4, "test": 5},
        "security": {"configuration": 0, "source_code": 1, "manifest": 2, "documentation": 3, "test": 4},
        "dependencies": {"manifest": 0, "configuration": 1, "documentation": 2, "source_code": 3, "test": 4},
        "tests": {"test": 0, "source_code": 1, "manifest": 2, "documentation": 3},
        "implementation": {"source_code": 0, "test": 1, "example": 2, "documentation": 3, "entrypoint": 4, "manifest": 5},
        "symbol": {"source_code": 0, "entrypoint": 1, "configuration": 2, "documentation": 3},
        "general": {"documentation": 0, "entrypoint": 1, "source_code": 2, "manifest": 3, "configuration": 4, "test": 5},
    }.get(question_intent, {})

    # For overview questions, reserve a diverse first pass: README/docs, manifest, entrypoint.
    # This prevents a generic question from sending only whichever chunks share its words.
    if question_intent in {"overview", "architecture", "dependencies", "tests", "security"}:
        role_files: dict[str, list[SourceFile]] = {}
        for source_file in source_files:
            role_files.setdefault(_path_role(source_file.path), []).append(source_file)

        def curated_file_priority(item: SourceFile) -> tuple[int, int, int, str]:
            path = item.path.replace("\\", "/")
            name = path.rsplit("/", 1)[-1].casefold()
            root_penalty = path.count("/")
            lock_penalty = int("lock" in name or name.endswith(".lock"))
            if question_intent == "dependencies":
                lock_penalty = 0
            return lock_penalty, root_penalty, len(path), path.casefold()
        for role in sorted(role_rank, key=lambda item: role_rank.get(item, 99)):
            quota = {"documentation": 2, "manifest": 2, "entrypoint": 2, "configuration": 2, "test": 2, "source_code": 2}.get(role, 1)
            if role not in role_rank:
                continue
            for source_file in sorted(role_files.get(role, []), key=curated_file_priority)[:quota]:
                if len(candidates) >= max_evidence or used_chars >= context_char_budget:
                    break
                if question_intent == "security" and role == "documentation":
                    continue
                max_lines, max_chars = (44, 3000)
                if role == "manifest":
                    max_lines, max_chars = 90, 2500
                elif role == "entrypoint":
                    max_lines, max_chars = 68, 2600
                elif role == "configuration":
                    max_lines, max_chars = 65, 2300
                elif role == "test":
                    max_lines, max_chars = 55, 2000
                excerpt_info = _excerpt(source_file, max_chars=max_chars, max_lines=max_lines)
                if excerpt_info:
                    start_line, end_line, excerpt = excerpt_info
                    bonus = 20.0 - role_rank.get(role, 8)
                    # Prioritize lexical matches within the same role when multiple files exist.
                    bonus += _score(query_terms, excerpt, source_file.path)
                    add_evidence(
                        kind="project_documentation" if role == "documentation" else role,
                        path=source_file.path, start_line=start_line, end_line=end_line,
                        excerpt=excerpt, score=bonus,
                    )

    # Implementation questions are source-first: exact symbol definitions, related tests/examples,
    # a matching documentation passage, and graph edges are more useful than several README headers.
    implementation_anchor_paths: set[str] = set()
    implementation_anchor_node_ids: set[str] = set()
    if question_intent == "implementation" and not scoped:
        source_roles = {"source_code", "entrypoint", "example", "test"}
        ranked_symbol_nodes: list[tuple[float, GraphNode, SourceFile]] = []
        for node in nodes:
            source = source_by_id.get(node.source_file_id or "")
            if source is None or _path_role(source.path) not in source_roles:
                continue
            if node.node_type not in {"class", "function", "method", "module", "endpoint", "model", "test"}:
                continue
            label_score = _score(query_terms, node.label + " " + node.stable_key)
            path_score = _score(query_terms, source.path)
            if label_score <= 0 and path_score <= 0:
                continue
            type_bonus = 2.0 if node.node_type in {"class", "function", "method", "endpoint", "model"} else 0.0
            ranked_symbol_nodes.append((label_score * 2.0 + path_score * 3.0 + type_bonus, node, source))
        ranked_symbol_nodes.sort(key=lambda item: (-item[0], item[2].path, item[1].start_line or 0, item[1].label))
        max_symbol_evidence = max(1, min(3, max_evidence - 5))
        matched_symbol_labels: set[str] = set()
        for score, node, source in ranked_symbol_nodes:
            if len(candidates) >= max_symbol_evidence or used_chars >= context_char_budget:
                break
            if source.path in implementation_anchor_paths and node.node_type not in {"class", "function", "method"}:
                continue
            if source.path not in implementation_anchor_paths and len(implementation_anchor_paths) >= 3:
                continue
            snippet = _line_excerpt(source, node.start_line, node.end_line)
            if not snippet:
                continue
            start_line, end_line, excerpt = snippet
            if add_evidence(
                kind="source_definition", path=source.path, start_line=start_line,
                end_line=end_line, excerpt=f"Definição extraída do snapshot; tipo={node.node_type}; símbolo={node.label}.\n{excerpt}",
                score=score,
            ):
                implementation_anchor_paths.add(source.path)
                implementation_anchor_node_ids.add(node.id)
                matched_symbol_labels.add(node.label.casefold())

        # Prefer one related test/example file and use it as evidence of observable behavior.
        # Path similarity is not enough by itself: look for the recovered symbol names in the test content too.
        related_test_files: list[tuple[float, SourceFile, tuple[int, int, str]]] = []
        symbol_tokens = {token for label in matched_symbol_labels for token in _terms(label) if len(token) >= 4}
        for source in source_files:
            role = _path_role(source.path)
            if role not in {"test", "example"} or not source.redacted_content:
                continue
            chunks = _scored_code_chunks(source, query_terms, intent=question_intent)
            if not chunks:
                continue
            best = chunks[0]
            excerpt_terms = _terms(best[3] + " " + source.path)
            symbol_overlap = len(symbol_tokens & excerpt_terms)
            path_score = _score(query_terms, source.path)
            content_score = _score(query_terms, source.redacted_content[:16000])
            score = content_score + path_score * 2.0 + symbol_overlap * 5.0
            if score > 0:
                related_test_files.append((score, source, best[1:]))
        related_test_files.sort(key=lambda item: (-item[0], item[1].path.casefold()))
        for score, source, (start, end, excerpt) in related_test_files[:1]:
            if len(candidates) >= max(2, max_evidence - 4) or used_chars >= context_char_budget:
                break
            if add_evidence(
                kind="test_code" if _path_role(source.path) == "test" else "example_code",
                path=source.path, start_line=start, end_line=end,
                excerpt=excerpt, score=score,
            ):
                implementation_anchor_paths.add(source.path)

        # Select source files by code/path relevance, not alphabetical README-first order.
        ranked_source_files: list[tuple[float, SourceFile]] = []
        for source in source_files:
            role = _path_role(source.path)
            if role not in source_roles or not source.redacted_content:
                continue
            path_score = _score(query_terms, source.path)
            content_score = _score(query_terms, source.redacted_content[:12000])
            if path_score <= 0 and content_score <= 0:
                continue
            role_bonus = {"source_code": 4, "entrypoint": 3, "test": 2, "example": 1}.get(role, 0)
            ranked_source_files.append((path_score * 4.0 + content_score + role_bonus, source))
        ranked_source_files.sort(key=lambda item: (-item[0], item[1].path.casefold()))
        # Include source chunks that contain the most relevant identifiers, avoiding repeated generic headers.
        for score, source in ranked_source_files:
            if len(candidates) >= max(2, max_evidence - 3) or used_chars >= context_char_budget:
                break
            if source.path in implementation_anchor_paths:
                # We already sent the exact graph symbol from this file; add another chunk only when it has
                # a materially separate match and remaining budget.
                chunks = _scored_code_chunks(source, query_terms, intent=question_intent)
                useful = next((item for item in chunks if item[1] > (0) and item[3].strip()), None)
                if useful is None:
                    continue
                chunk_score, start, end, excerpt = useful
                signature = ("source_code", source.path, start, end)
                if signature in seen_signatures:
                    continue
            else:
                chunks = _scored_code_chunks(source, query_terms, intent=question_intent)
                if not chunks:
                    continue
                chunk_score, start, end, excerpt = chunks[0]
            if add_evidence(
                kind="source_code" if _path_role(source.path) != "test" else "test_code",
                path=source.path, start_line=start, end_line=end,
                excerpt=excerpt, score=score + chunk_score,
            ):
                if _path_role(source.path) in {"source_code", "entrypoint"}:
                    implementation_anchor_paths.add(source.path)

        # Bring in a relevant documentation passage based on matching lines, not only the first README page.
        docs_ranked: list[tuple[float, SourceFile, tuple[int, int, str]]] = []
        for source in source_files:
            if _path_role(source.path) != "documentation" or not source.redacted_content:
                continue
            chunks = _scored_code_chunks(source, query_terms, intent=question_intent)
            if chunks:
                score, start, end, excerpt = chunks[0]
                docs_ranked.append((score, source, (start, end, excerpt)))
        docs_ranked.sort(key=lambda item: (-item[0], item[1].path.casefold()))
        for score, source, (start, end, excerpt) in docs_ranked[:1]:
            if len(candidates) >= max_evidence - 1 or used_chars >= context_char_budget:
                break
            add_evidence(kind="project_documentation", path=source.path, start_line=start, end_line=end, excerpt=excerpt, score=score)

    # Security questions should see existing security findings before general keyword ranking.
    if question_intent == "security" and len(candidates) < max_evidence and used_chars < context_char_budget:
        findings = db.scalars(
            select(Finding).where(Finding.analysis_run_id == run.id)
            .order_by(Finding.severity, Finding.title).limit(300)
        ).all()
        allowed_paths_for_findings = {item.path for item in source_files}
        security_findings = []
        for finding in findings:
            evidence_paths = {
                item.get("path") for item in (finding.evidence or [])
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            is_security_finding = (
                "appsec" in finding.skill_id.casefold()
                or "secret" in finding.skill_id.casefold()
                or finding.category.casefold() == "security"
            )
            if is_security_finding and (not scoped or evidence_paths & allowed_paths_for_findings):
                security_findings.append(finding)
        if not security_findings:
            security_findings = [
                finding for finding in findings
                if not scoped or any(
                    isinstance(item, dict) and item.get("path") in allowed_paths_for_findings
                    for item in (finding.evidence or [])
                )
            ][:4]
        for finding in security_findings[:3]:
            if len(candidates) >= max_evidence or used_chars >= context_char_budget:
                break
            ev = next((item for item in (finding.evidence or []) if isinstance(item, dict)), {})
            path = ev.get("path") if isinstance(ev.get("path"), str) else None
            start = ev.get("start_line") if isinstance(ev.get("start_line"), int) else None
            end = ev.get("end_line") if isinstance(ev.get("end_line"), int) else None
            excerpt = (
                f"Achado existente para revisão humana: {finding.title}\nSkill: {finding.skill_id}\n"
                f"Categoria: {finding.category}\nSeveridade: {finding.severity}\n"
                f"Confiança qualitativa: {finding.confidence_label}\nStatus de revisão: {finding.status}\n"
                f"Resumo: {finding.summary}\nImpacto potencial: {finding.impact}\n"
                f"Recomendação: {finding.recommendation}\n"
                "Limitação: resultado estático; não prova exploração em runtime nem que uma credencial esteja ativa."
            )
            add_evidence(kind="finding", path=path, start_line=start, end_line=end, excerpt=excerpt, score=25.0)


    # Rank remaining code chunks with intent expansion and path-role bias. Enforce file diversity:
    # take the highest-scoring chunk per file first, then allow a second chunk only if space remains.
    ranked_chunks: list[tuple[float, str, int, int, str, SourceFile]] = []
    for source_file in source_files:
        for score, start_line, end_line, excerpt in _scored_code_chunks(source_file, query_terms, intent=question_intent):
            ranked_chunks.append((score, source_file.path, start_line, end_line, excerpt, source_file))
    ranked_chunks.sort(key=lambda item: (-item[0], role_rank.get(_path_role(item[1]), 8), item[1], item[2]))

    used_paths = {item.path for item in candidates if item.path}
    selected_chunks: list[tuple[float, str, int, int, str, SourceFile]] = []
    second_pass_chunks: list[tuple[float, str, int, int, str, SourceFile]] = []
    for item in ranked_chunks:
        if item[1] in used_paths:
            second_pass_chunks.append(item)
        else:
            selected_chunks.append(item)
            used_paths.add(item[1])
    selected_chunks.extend(second_pass_chunks)
    relation_reserve = 2 if question_intent in {"overview", "architecture", "flow", "implementation"} and not scoped else 0
    max_before_relations = max(1, max_evidence - relation_reserve)
    for score, path, start_line, end_line, excerpt, source_file in selected_chunks:
        if len(candidates) >= max_before_relations or used_chars >= context_char_budget:
            break
        add_evidence(
            kind="source_code", path=path, start_line=start_line,
            end_line=min(end_line, start_line + excerpt.count("\n")), excerpt=excerpt, score=score,
        )

    # Expand from selected source files into adjacent graph relations. Overview/architecture get
    # representative structural edges even when their labels do not share query words.
    structural_intents = {"overview", "architecture", "flow", "dependencies", "tests", "security", "implementation"}
    if question_intent in structural_intents and len(candidates) < max_evidence and used_chars < context_char_budget:
        allowed_source_ids = {item.id for item in source_files}
        selected_source_ids_for_edges = {
            item.id for item in source_files if item.path in {citation.path for citation in candidates if citation.path}
        }
        relevant_node_scores: dict[str, float] = {}
        for node in nodes:
            source = source_by_id.get(node.source_file_id or "")
            path = source.path if source else ""
            score = _score(query_terms, node.label, path)
            if source and source.id in selected_source_ids_for_edges:
                score += 10.0
            elif question_intent == "overview" and source and _path_role(source.path) in {"entrypoint", "source_code"}:
                score += 3.0
            if score > 0:
                relevant_node_scores[node.id] = score
        seed_ids = {
            node_id for node_id, _ in sorted(relevant_node_scores.items(), key=lambda pair: (-pair[1], pair[0]))[:30]
        }
        if question_intent == "implementation":
            seed_ids.update(implementation_anchor_node_ids)
        relation_priority = {
            "overview": ("contains", "imports", "defines", "exposes_endpoint", "depends_on", "calls"),
            "architecture": ("imports", "contains", "depends_on", "defines", "exposes_endpoint", "calls"),
            "flow": ("exposes_endpoint", "calls", "imports", "reads_from", "writes_to", "defines"),
            "dependencies": ("depends_on", "imports", "configures"),
            "tests": ("tested_by", "contains", "imports", "defines"),
            "security": ("finding_affects", "supports_finding", "imports", "configures"),
            "implementation": ("defines", "calls", "tested_by", "imports", "contains", "references", "depends_on"),
        }.get(question_intent, ())
        relation_candidates: list[tuple[float, GraphEdge, GraphNode, GraphNode]] = []
        for edge in edges:
            source_node = node_by_id.get(edge.source_node_id)
            target_node = node_by_id.get(edge.target_node_id)
            if source_node is None or target_node is None:
                continue
            if edge.relation_type not in relation_priority:
                continue
            touches_seed = source_node.id in seed_ids or target_node.id in seed_ids
            from_selected_file = source_node.source_file_id in selected_source_ids_for_edges or target_node.source_file_id in selected_source_ids_for_edges
            if not touches_seed and not from_selected_file:
                continue
            if scoped and (source_node.source_file_id not in allowed_source_ids or target_node.source_file_id not in allowed_source_ids):
                continue
            base = max(relevant_node_scores.get(source_node.id, 0.0), relevant_node_scores.get(target_node.id, 0.0))
            role_bonus = (len(relation_priority) - relation_priority.index(edge.relation_type)) * 0.6
            provenance_penalty = 1.5 if edge.provenance_type == "inferred" else 0.0
            relation_candidates.append((base + role_bonus - provenance_penalty, edge, source_node, target_node))
        relation_candidates.sort(key=lambda item: (-item[0], item[1].relation_type, item[2].label, item[3].label))
        relation_budget = 4 if question_intent in {"overview", "architecture", "flow", "implementation"} else 3
        relation_count = 0
        for score, edge, source_node, target_node in relation_candidates:
            if relation_count >= relation_budget or len(candidates) >= max_evidence or used_chars >= context_char_budget:
                break
            source_file = source_by_id.get(source_node.source_file_id or "")
            target_file = source_by_id.get(target_node.source_file_id or "")
            path = source_file.path if source_file else (target_file.path if target_file else None)
            source_ref = f"{source_node.label} ({source_file.path if source_file else 'origem não localizada'})"
            target_ref = f"{target_node.label} ({target_file.path if target_file else 'destino não localizado'})"
            provenance = "inferida, não confirmada" if edge.provenance_type == "inferred" else "determinística"
            excerpt = (
                f"Relação extraída do grafo: {source_ref} --{edge.relation_type}--> {target_ref}. "
                f"Proveniência: {provenance}. Evidência registrada: {edge.evidence}."
            )
            added = add_evidence(
                kind="graph_relation", path=path, start_line=source_node.start_line,
                end_line=source_node.end_line, excerpt=excerpt, score=score,
            )
            if added:
                relation_count += 1

    # Fallback on broad project anchors when lexical matches are absent: do not return empty simply
    # because a natural-language question shares no tokens with code identifiers.
    if not scoped and not any(item.path for item in candidates):
        fallback_order = ("source_code", "test", "example", "documentation", "manifest", "entrypoint") if question_intent == "implementation" else ("documentation", "manifest", "entrypoint", "source_code")
        for role in fallback_order:
            for source_file in sorted(source_files, key=lambda item: item.path):
                if _path_role(source_file.path) != role:
                    continue
                excerpt_info = _excerpt(source_file, max_chars=2200, max_lines=42)
                if not excerpt_info:
                    continue
                start, end, excerpt = excerpt_info
                add_evidence(kind=role, path=source_file.path, start_line=start, end_line=end, excerpt=excerpt, score=1.0)
                if len(candidates) >= max_evidence or used_chars >= context_char_budget:
                    break
            if len(candidates) >= max_evidence or used_chars >= context_char_budget:
                break

    return candidates

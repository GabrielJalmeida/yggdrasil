"""Deterministic graph-building primitives for the first Python-only slice."""

from __future__ import annotations

import ast
import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from app.infrastructure.archive import ArchiveArtifact


@dataclass(slots=True)
class NodeData:
    stable_key: str
    node_type: str
    label: str
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    provenance_type: str = "deterministic"


@dataclass(slots=True)
class EdgeData:
    source_key: str
    target_key: str
    relation_type: str
    provenance_type: str = "deterministic"
    confidence_label: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphBuildResult:
    nodes: list[NodeData]
    edges: list[EdgeData]
    warnings: list[str]
    parsed_python_files: int
    failed_python_files: int
    modules_by_name: dict[str, str]


@dataclass(slots=True)
class _Symbol:
    key: str
    name: str
    qualified_name: str
    kind: str
    node: ast.AST
    node_type: str


@dataclass(slots=True)
class _Import:
    module: str
    line: int
    names: tuple[str, ...] = ()
    relative_level: int = 0


def stable_graph_id(snapshot_id: str, stable_key: str) -> str:
    """Build deterministic IDs inside a snapshot without exposing source code in the ID."""
    return hashlib.sha256(f"{snapshot_id}:{stable_key}".encode()).hexdigest()[:32]


def _module_name(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    for marker in ("src", "app", "lib"):
        if marker in parts:
            parts = parts[parts.index(marker) :]
            break
    return ".".join(part for part in parts if part and part != ".")


def _argument_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render only parameter names, avoiding default expressions that may contain secrets."""
    args = node.args
    names: list[str] = []
    for arg in args.posonlyargs:
        names.append(arg.arg)
    if args.posonlyargs:
        names.append("/")
    names.extend(arg.arg for arg in args.args)
    if args.vararg:
        names.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        names.append("*")
    names.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        names.append(f"**{args.kwarg.arg}")
    return f"({', '.join(names)})"


def _is_orm_model(node: ast.ClassDef) -> bool:
    if any(
        isinstance(statement, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in (
                statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            )
        )
        for statement in node.body
    ):
        return True
    bases = [ast.unparse(base).split(".")[-1].lower() for base in node.bases]
    return any(base in {"basemodel", "sqlmodel"} for base in bases)


def _decorator_endpoint(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, str]]:
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace", "api_route", "websocket"}
    result: list[tuple[str, str]] = []
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if not isinstance(target, ast.Attribute) or target.attr.lower() not in methods:
            continue
        if not isinstance(decorator, ast.Call) or not decorator.args:
            continue
        route = decorator.args[0]
        if not isinstance(route, ast.Constant) or not isinstance(route.value, str):
            continue
        method = target.attr.upper()
        if method == "API_ROUTE":
            method = "ROUTE"
        if method == "WEBSOCKET":
            method = "WS"
        result.append((method, route.value))
    return result


def _collect_symbols(tree: ast.Module, path: str) -> tuple[list[_Symbol], list[_Import], list[tuple[_Symbol, str, str, int]]]:
    symbols: list[_Symbol] = []
    imports: list[_Import] = []
    endpoints: list[tuple[_Symbol, str, str, int]] = []

    def walk_body(body: list[ast.stmt], parent_name: str = "", parent_kind: str = "module") -> None:
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                qualified = f"{parent_name}.{statement.name}" if parent_name else statement.name
                key = f"symbol:{path}:{qualified}:{statement.lineno}"
                kind = "model" if _is_orm_model(statement) else "class"
                symbol = _Symbol(key, statement.name, qualified, "class", statement, kind)
                symbols.append(symbol)
                walk_body(statement.body, qualified, "class")
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{parent_name}.{statement.name}" if parent_name else statement.name
                key = f"symbol:{path}:{qualified}:{statement.lineno}"
                if statement.name.startswith("test_"):
                    node_type = "test"
                else:
                    node_type = "method" if parent_kind == "class" else "function"
                symbol = _Symbol(key, statement.name, qualified, "function", statement, node_type)
                symbols.append(symbol)
                for method, route in _decorator_endpoint(statement):
                    endpoints.append((symbol, method, route, statement.lineno))
                walk_body(statement.body, qualified, "function")

    walk_body(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(_Import(alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                _Import(node.module or "", node.lineno, tuple(alias.name for alias in node.names), node.level)
            )
    return symbols, imports, endpoints


def _imports_for_module(current: str, path: str, imports: list[_Import]) -> list[tuple[str, int]]:
    resolved: list[tuple[str, int]] = []
    package = current if PurePosixPath(path).name == "__init__.py" else current.rpartition(".")[0]
    package_parts = [part for part in package.split(".") if part]
    for imp in imports:
        if imp.relative_level:
            remove = max(imp.relative_level - 1, 0)
            prefix = package_parts[: max(0, len(package_parts) - remove)]
            target = ".".join(prefix + ([imp.module] if imp.module else []))
        else:
            target = imp.module
        if target:
            resolved.append((target, imp.line))
        # `from package import module` can refer to a nested local module.
        if imp.names and target:
            resolved.extend((f"{target}.{name}", imp.line) for name in imp.names if name != "*")
    return resolved


def _dependencies_from_manifest(path: str, text: str) -> list[tuple[str, str | None]]:
    dependencies: dict[str, str | None] = {}
    base = PurePosixPath(path).name.lower()
    if base == "pyproject.toml":
        try:
            data = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, ValueError):
            return []
        project = data.get("project", {})
        if isinstance(project, dict):
            for raw in project.get("dependencies", []) if isinstance(project.get("dependencies", []), list) else []:
                if isinstance(raw, str):
                    match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(.*)", raw)
                    if match:
                        dependencies[match.group(1).lower().replace("_", "-")] = match.group(2).strip() or None
            optional = project.get("optional-dependencies", {})
            if isinstance(optional, dict):
                for rows in optional.values():
                    if isinstance(rows, list):
                        for raw in rows:
                            if isinstance(raw, str):
                                match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(.*)", raw)
                                if match:
                                    dependencies[match.group(1).lower().replace("_", "-")] = match.group(2).strip() or None
        poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool", {}), dict) else {}
        poetry_deps = poetry.get("dependencies", {}) if isinstance(poetry, dict) else {}
        if isinstance(poetry_deps, dict):
            for name, value in poetry_deps.items():
                if str(name).lower() == "python":
                    continue
                version = value if isinstance(value, str) else None
                dependencies[str(name).lower().replace("_", "-")] = version
    elif base.startswith("requirements") and base.endswith(".txt"):
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-", ".", "/")):
                continue
            match = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)", line)
            if match:
                dependencies[match.group(1).lower().replace("_", "-")] = match.group(2).strip() or None
    return sorted(dependencies.items())


def build_graph(owner: str, repo_name: str, files: list[ArchiveArtifact]) -> GraphBuildResult:
    nodes: dict[str, NodeData] = {}
    edges: list[EdgeData] = []
    warnings: list[str] = []
    python_by_path = {artifact.path: artifact for artifact in files if artifact.is_python}
    parsed_details: dict[str, tuple[ast.Module, list[_Symbol], list[_Import], list[tuple[_Symbol, str, str, int]]]] = {}
    module_by_name: dict[str, str] = {}
    module_path_by_key: dict[str, str] = {}
    symbols_by_name: dict[str, list[_Symbol]] = {}
    symbols_by_path: dict[str, list[_Symbol]] = {}
    calls_by_path: dict[str, list[tuple[_Symbol, str, int]]] = {}

    repository_key = f"repo:{owner}/{repo_name}"
    nodes[repository_key] = NodeData(
        stable_key=repository_key,
        node_type="repository",
        label=f"{owner}/{repo_name}",
        properties={"provider": "github", "visibility": "public"},
    )

    # Every encountered file/directory receives a node, including ignored files.
    for artifact in files:
        parts = PurePosixPath(artifact.path).parts
        parent_key = repository_key
        accumulated: list[str] = []
        for component in parts[:-1]:
            accumulated.append(component)
            directory_path = "/".join(accumulated)
            directory_key = f"directory:{directory_path}"
            if directory_key not in nodes:
                nodes[directory_key] = NodeData(
                    stable_key=directory_key,
                    node_type="directory",
                    label=component,
                    properties={"path": directory_path},
                )
                edges.append(EdgeData(parent_key, directory_key, "contains", evidence={"path": directory_path}))
            parent_key = directory_key

        file_key = f"file:{artifact.path}"
        is_test_path = artifact.path.startswith("tests/") or "/tests/" in artifact.path or PurePosixPath(artifact.path).name.startswith("test_")
        nodes[file_key] = NodeData(
            stable_key=file_key,
            node_type="file",
            label=PurePosixPath(artifact.path).name,
            source_path=artifact.path,
            properties={
                "path": artifact.path,
                "size_bytes": artifact.size_bytes,
                "language": artifact.language,
                "eligibility_status": artifact.eligibility_status,
                "parse_status": artifact.parse_status,
                "file_role": "test" if is_test_path else "source",
                "ignored_reason": artifact.metadata.get("ignored_reason"),
            },
        )
        edges.append(EdgeData(parent_key, file_key, "contains", evidence={"path": artifact.path}))

        if artifact.is_python:
            module_name = _module_name(artifact.path)
            module_key = f"module:{module_name or artifact.path}"
            module_by_name[module_name] = module_key
            module_path_by_key[module_key] = artifact.path
            nodes[module_key] = NodeData(
                stable_key=module_key,
                node_type="module",
                label=module_name or PurePosixPath(artifact.path).stem,
                source_path=artifact.path,
                properties={"path": artifact.path, "language": "Python"},
            )
            edges.append(EdgeData(file_key, module_key, "contains", evidence={"path": artifact.path}))
            try:
                tree = ast.parse(artifact.redacted_content or "", filename=artifact.path, type_comments=True)
                symbols, imports, endpoints = _collect_symbols(tree, artifact.path)
                parsed_details[artifact.path] = (tree, symbols, imports, endpoints)
                symbols_by_path[artifact.path] = symbols
                for symbol in symbols:
                    symbols_by_name.setdefault(symbol.name, []).append(symbol)
                    if isinstance(symbol.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end_line = getattr(symbol.node, "end_lineno", symbol.node.lineno)
                        signature = _argument_signature(symbol.node)
                        decorators = [
                            ast.unparse(dec.func if isinstance(dec, ast.Call) else dec)
                            for dec in symbol.node.decorator_list
                        ]
                        properties = {
                            "name": symbol.name,
                            "qualified_name": symbol.qualified_name,
                            "signature": signature,
                            "is_async": isinstance(symbol.node, ast.AsyncFunctionDef),
                            "decorators": decorators,
                        }
                    else:
                        end_line = getattr(symbol.node, "end_lineno", symbol.node.lineno)
                        properties = {
                            "name": symbol.name,
                            "qualified_name": symbol.qualified_name,
                            "bases": [ast.unparse(base) for base in symbol.node.bases]
                            if isinstance(symbol.node, ast.ClassDef)
                            else [],
                        }
                    nodes[symbol.key] = NodeData(
                        stable_key=symbol.key,
                        node_type=symbol.node_type,
                        label=symbol.name,
                        source_path=artifact.path,
                        start_line=symbol.node.lineno,
                        end_line=end_line,
                        properties=properties,
                    )
                    edges.append(
                        EdgeData(
                            module_key,
                            symbol.key,
                            "defines",
                            evidence={
                                "path": artifact.path,
                                "start_line": symbol.node.lineno,
                                "end_line": end_line,
                            },
                        )
                    )
                for symbol, method, route, line in endpoints:
                    endpoint_key = f"endpoint:{artifact.path}:{method}:{route}:{line}"
                    nodes[endpoint_key] = NodeData(
                        stable_key=endpoint_key,
                        node_type="endpoint",
                        label=f"{method} {route}",
                        source_path=artifact.path,
                        start_line=line,
                        end_line=getattr(symbol.node, "end_lineno", line),
                        properties={"method": method, "path": route, "framework": "decorator_pattern"},
                    )
                    edges.append(
                        EdgeData(
                            module_key,
                            endpoint_key,
                            "exposes_endpoint",
                            evidence={"path": artifact.path, "start_line": line},
                        )
                    )
                    edges.append(
                        EdgeData(
                            endpoint_key,
                            symbol.key,
                            "references",
                            evidence={"path": artifact.path, "start_line": line},
                        )
                    )
                # Syntactic call names are useful clues but dynamic dispatch is not resolved.
                for symbol in symbols:
                    if not isinstance(symbol.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    local_calls: set[tuple[str, int]] = set()
                    stack: list[ast.AST] = list(reversed(symbol.node.body))
                    while stack:
                        current = stack.pop()
                        if current is not symbol.node and isinstance(
                            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
                        ):
                            continue
                        if isinstance(current, ast.Call) and isinstance(current.func, ast.Name):
                            local_calls.add((current.func.id, current.lineno))
                        stack.extend(reversed(list(ast.iter_child_nodes(current))))
                    calls_by_path.setdefault(artifact.path, []).extend(
                        (symbol, called_name, line) for called_name, line in local_calls
                    )
                artifact.parse_status = "parsed"
            except (SyntaxError, ValueError, RecursionError):
                artifact.parse_status = "failed"
                nodes[file_key].properties["parse_status"] = "failed"
                warnings.append(f"Parsing Python não concluído para {artifact.path}; o arquivo permaneceu no inventário.")

    # Resolve imports after every eligible module has been discovered.
    for path, (_tree, _symbols, imports, _endpoints) in parsed_details.items():
        current_module = _module_name(path)
        source_key = module_by_name.get(current_module)
        if not source_key:
            continue
        for target_name, line in _imports_for_module(current_module, path, imports):
            target_key = module_by_name.get(target_name)
            if target_key and target_key != source_key:
                edges.append(
                    EdgeData(
                        source_key,
                        target_key,
                        "imports",
                        evidence={"path": path, "start_line": line, "imported_module": target_name},
                    )
                )

    # Only resolve a simple name call when exactly one symbol with that name exists in the repo.
    for path, call_rows in calls_by_path.items():
        for caller, target_name, line in call_rows:
            target_candidates = symbols_by_name.get(target_name, [])
            if len(target_candidates) != 1:
                continue
            target = target_candidates[0]
            if caller.key == target.key:
                continue
            edges.append(
                EdgeData(
                    caller.key,
                    target.key,
                    "calls",
                    provenance_type="inferred",
                    confidence_label="moderate",
                    evidence={
                        "path": path,
                        "start_line": line,
                        "method": "unique local symbol-name match; runtime dispatch is not verified",
                    },
                )
            )

    # Manifest dependencies are explicit evidence, unlike arbitrary imports.
    declared_dependencies: dict[str, tuple[str, str | None]] = {}
    for artifact in files:
        if artifact.redacted_content is None:
            continue
        for name, version in _dependencies_from_manifest(artifact.path, artifact.redacted_content):
            declared_dependencies[name] = (artifact.path, version)
    for name, (manifest_path, version) in declared_dependencies.items():
        dependency_key = f"dependency:{name}"
        nodes[dependency_key] = NodeData(
            stable_key=dependency_key,
            node_type="dependency",
            label=name,
            source_path=manifest_path,
            properties={"name": name, "declared_version": version},
        )
        edges.append(
            EdgeData(
                f"file:{manifest_path}",
                dependency_key,
                "depends_on",
                evidence={"path": manifest_path, "declaration": version or "declared without a pinned version"},
            )
        )

    # Synchronize file-node parse statuses after parsing.
    failed = 0
    parsed = 0
    for path, artifact in python_by_path.items():
        file_node = nodes.get(f"file:{path}")
        if file_node:
            file_node.properties["parse_status"] = artifact.parse_status
        if artifact.parse_status == "parsed":
            parsed += 1
        elif artifact.parse_status == "failed":
            failed += 1
    return GraphBuildResult(
        nodes=list(nodes.values()),
        edges=edges,
        warnings=list(dict.fromkeys(warnings)),
        parsed_python_files=parsed,
        failed_python_files=failed,
        modules_by_name=module_by_name,
    )

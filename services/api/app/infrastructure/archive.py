"""Safe in-memory inspection of GitHub ZIP archives; files are never extracted."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.config import settings
from app.domain.secrets import redact_secrets
from app.infrastructure.github import GitHubError

TEXT_SUFFIXES = {
    ".py", ".pyi", ".toml", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".json",
    ".md", ".rst", ".txt", ".sql", ".sh", ".bash", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".xml", ".properties", ".env", ".example", ".lock", ".gitignore",
    ".dockerignore", ".dockerfile", ".makefile", ".tf", ".gradle", ".bat", ".ps1",
}
SPECIAL_TEXT_NAMES = {
    "Dockerfile", "Containerfile", "Makefile", "Justfile", ".gitignore", ".dockerignore",
    ".env.example", "requirements.txt", "Pipfile", "Procfile", "LICENSE", "NOTICE",
}
EXCLUDED_DIRECTORY_NAMES = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", "vendor", "site-packages",
}


@dataclass(slots=True)
class ArchiveArtifact:
    path: str
    size_bytes: int
    content_hash: str | None = None
    language: str | None = None
    eligibility_status: str = "eligible"
    parse_status: str = "queued"
    redacted_content: str | None = None
    raw_content: str | None = field(default=None, repr=False)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_python(self) -> bool:
        return self.path.endswith((".py", ".pyi")) and self.redacted_content is not None


@dataclass(slots=True)
class ArchiveResult:
    files: list[ArchiveArtifact]
    warnings: list[str]
    archive_size_bytes: int
    unpacked_declared_bytes: int
    source_method: str = "archive"


def _is_safe_relative_path(value: str) -> bool:
    if (
        not value or len(value) > 1024 or value.startswith(("/", "\\", "./"))
        or "\\" in value or "\x00" in value or "//" in value
    ):
        return False
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in raw_parts)
    )


def _language_for(path: str) -> str | None:
    suffix = PurePosixPath(path).suffix.lower()
    return {
        ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".go": "Go",
        ".rs": "Rust", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
        ".json": "JSON", ".toml": "TOML", ".yaml": "YAML", ".yml": "YAML",
        ".md": "Markdown", ".sh": "Shell", ".ps1": "PowerShell",
    }.get(suffix)


def _is_text_candidate(path: str) -> bool:
    p = PurePosixPath(path)
    return p.name in SPECIAL_TEXT_NAMES or p.suffix.lower() in TEXT_SUFFIXES


def _is_in_excluded_directory(path: str) -> bool:
    return any(part.lower() in EXCLUDED_DIRECTORY_NAMES for part in PurePosixPath(path).parts[:-1])


def inspect_archive(archive_bytes: bytes) -> ArchiveResult:
    """Inventory a compressed archive without writing anything to the filesystem.

    The compressed size, file count, single-file size and aggregate uncompressed/text sizes are
    capped. Suspicious paths, symlinks, generated/vendor folders and binary files are not parsed.
    """
    if len(archive_bytes) > settings.max_archive_bytes:
        raise ValueError("archive_too_large")
    files: list[ArchiveArtifact] = []
    warnings: list[str] = []
    total_declared = 0
    total_text = 0

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_files:
                warnings.append(f"O inventário atingiu o limite de {settings.max_files} entradas; a análise pode estar incompleta.")
            for info in entries[: settings.max_files]:
                if info.is_dir():
                    continue
                # GitHub archives have a single generated top-level directory.
                parts = info.filename.split("/", 1)
                if len(parts) != 2:
                    continue
                relative_path = parts[1]
                if not _is_safe_relative_path(relative_path):
                    warnings.append("Uma entrada com caminho inválido foi ignorada por política de segurança.")
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:  # POSIX symbolic link
                    warnings.append(f"Link simbólico ignorado: {relative_path}")
                    continue

                total_declared += max(info.file_size, 0)
                if total_declared > settings.max_total_unpacked_bytes:
                    warnings.append("O limite total de dados descompactados foi atingido; parte do inventário ficou de fora.")
                    break

                artifact = ArchiveArtifact(
                    path=relative_path,
                    size_bytes=max(info.file_size, 0),
                    language=_language_for(relative_path),
                    metadata={"archive_compressed_size": info.compress_size},
                )
                if _is_in_excluded_directory(relative_path):
                    artifact.eligibility_status = "ignored_by_policy"
                    artifact.parse_status = "ignored_by_policy"
                    artifact.metadata["ignored_reason"] = "Diretório de dependências, cache ou artefato gerado."
                    files.append(artifact)
                    continue
                if not _is_text_candidate(relative_path):
                    artifact.eligibility_status = "ignored_by_policy"
                    artifact.parse_status = "unsupported"
                    artifact.metadata["ignored_reason"] = "Extensão fora da lista inicial de arquivos textuais."
                    files.append(artifact)
                    continue
                if info.file_size > settings.max_file_bytes:
                    artifact.eligibility_status = "ignored_by_policy"
                    artifact.parse_status = "unsupported"
                    artifact.metadata["ignored_reason"] = f"Arquivo acima do limite de {settings.max_file_bytes} bytes."
                    files.append(artifact)
                    continue
                if total_text + info.file_size > settings.max_total_text_bytes:
                    artifact.eligibility_status = "ignored_by_policy"
                    artifact.parse_status = "unsupported"
                    artifact.metadata["ignored_reason"] = "Limite agregado de conteúdo textual atingido."
                    files.append(artifact)
                    warnings.append("O limite total de conteúdo textual foi atingido; alguns arquivos não foram lidos.")
                    continue

                try:
                    content_bytes = archive.read(info)
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    artifact.eligibility_status = "failed"
                    artifact.parse_status = "failed"
                    artifact.metadata["ignored_reason"] = "Falha ao ler a entrada compactada."
                    warnings.append(f"Falha ao ler um arquivo do inventário: {relative_path}")
                    files.append(artifact)
                    continue
                total_text += len(content_bytes)
                if b"\x00" in content_bytes:
                    artifact.eligibility_status = "ignored_by_policy"
                    artifact.parse_status = "unsupported"
                    artifact.metadata["ignored_reason"] = "Conteúdo binário detectado."
                    files.append(artifact)
                    continue
                try:
                    decoded = content_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    artifact.eligibility_status = "ignored_by_policy"
                    artifact.parse_status = "unsupported"
                    artifact.metadata["ignored_reason"] = "Codificação textual não suportada pelo MVP."
                    files.append(artifact)
                    continue

                redacted = redact_secrets(decoded)
                artifact.redacted_content = redacted
                artifact.raw_content = decoded
                artifact.content_hash = hashlib.sha256(content_bytes).hexdigest()
                artifact.eligibility_status = "eligible"
                artifact.parse_status = "queued" if artifact.is_python else "not_applicable"
                files.append(artifact)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("invalid_archive") from exc

    if not files:
        warnings.append("Nenhum arquivo foi encontrado no arquivo compactado.")
    return ArchiveResult(
        files=files,
        warnings=list(dict.fromkeys(warnings)),
        archive_size_bytes=len(archive_bytes),
        unpacked_declared_bytes=total_declared,
    )



def inspect_github_tree(
    tree_entries: list[object],
    fetch_file: Callable[[str, int], bytes],
    *,
    tree_truncated: bool = False,
) -> ArchiveResult:
    """Inventory a GitHub tree and fetch only bounded, eligible text blobs.

    The caller must pass the recursive tree for an immutable commit and a downloader that
    only reads that same commit. No path from the tree is used as a URL without validation.
    """
    files: list[ArchiveArtifact] = []
    warnings: list[str] = []
    total_declared = 0
    total_text = 0
    file_entries_seen = 0
    stop_fetching_reason: str | None = None

    if tree_truncated:
        warnings.append(
            "A árvore não pôde ser percorrida integralmente dentro dos limites; o inventário é parcial."
        )

    for entry in tree_entries:
        if not isinstance(entry, dict):
            warnings.append("Uma entrada inválida da árvore GitHub foi ignorada.")
            continue
        entry_type = entry.get("type")
        if entry_type == "tree":
            continue
        if entry_type not in {"blob", "commit"}:
            continue

        file_entries_seen += 1
        if file_entries_seen > settings.max_files:
            warnings.append(
                f"O inventário atingiu o limite de {settings.max_files} arquivos; a análise pode estar incompleta."
            )
            break

        path_value = entry.get("path")
        if not isinstance(path_value, str) or not _is_safe_relative_path(path_value):
            warnings.append("Uma entrada com caminho inválido foi ignorada por política de segurança.")
            continue

        size_value = entry.get("size")
        size_is_valid = isinstance(size_value, int) and not isinstance(size_value, bool) and size_value >= 0
        size = size_value if size_is_valid else 0
        total_declared += size
        if total_declared > settings.max_total_unpacked_bytes:
            warnings.append(
                "O limite total de dados declarados foi atingido; parte do inventário ficou de fora."
            )
            break

        artifact = ArchiveArtifact(
            path=path_value,
            size_bytes=size,
            language=_language_for(path_value),
            metadata={
                "github_blob_sha": entry.get("sha") if isinstance(entry.get("sha"), str) else None,
                "github_mode": entry.get("mode") if isinstance(entry.get("mode"), str) else None,
                "source_method": "github_tree",
            },
        )

        if entry_type == "blob" and not size_is_valid:
            artifact.eligibility_status = "failed"
            artifact.parse_status = "failed"
            artifact.metadata["ignored_reason"] = "Metadados de tamanho inválidos no inventário GitHub."
            files.append(artifact)
            warnings.append(f"Metadados incompletos impediram a leitura de um arquivo: {path_value}")
            continue

        if entry_type == "commit":
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = "Submódulos Git não são baixados automaticamente."
            files.append(artifact)
            continue

        mode = entry.get("mode")
        if mode == "120000":
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = "Links simbólicos não são lidos pelo MVP."
            files.append(artifact)
            continue
        if _is_in_excluded_directory(path_value):
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "ignored_by_policy"
            artifact.metadata["ignored_reason"] = "Diretório de dependências, cache ou artefato gerado."
            files.append(artifact)
            continue
        if not _is_text_candidate(path_value):
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = "Extensão fora da lista inicial de arquivos textuais."
            files.append(artifact)
            continue
        if size > settings.max_file_bytes:
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = (
                f"Arquivo acima do limite de {settings.max_file_bytes} bytes."
            )
            files.append(artifact)
            continue
        if total_text + size > settings.max_total_text_bytes:
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = "Limite agregado de conteúdo textual atingido."
            warnings.append(
                "O limite total de conteúdo textual foi atingido; alguns arquivos não foram lidos."
            )
            files.append(artifact)
            continue
        if stop_fetching_reason is not None:
            artifact.eligibility_status = "failed"
            artifact.parse_status = "failed"
            artifact.metadata["ignored_reason"] = stop_fetching_reason
            files.append(artifact)
            continue

        try:
            content_bytes = fetch_file(path_value, settings.max_file_bytes)
        except GitHubError as exc:
            error_code = exc.code
            status_code = exc.status_code
            if error_code == "RAW_FILE_TOO_LARGE":
                artifact.eligibility_status = "ignored_by_policy"
                artifact.parse_status = "unsupported"
                artifact.metadata["ignored_reason"] = (
                    f"Arquivo acima do limite de {settings.max_file_bytes} bytes."
                )
            else:
                artifact.eligibility_status = "failed"
                artifact.parse_status = "failed"
                artifact.metadata["ignored_reason"] = "Falha ao recuperar o arquivo fixado no commit."
                warnings.append(f"Não foi possível recuperar um arquivo: {path_value}")
                if error_code == "GITHUB_RATE_LIMIT_OR_ACCESS" or status_code == 429:
                    stop_fetching_reason = (
                        "Leitura não tentada porque o GitHub limitou as solicitações restantes."
                    )
                    warnings.append(
                        "O GitHub limitou a leitura de arquivos; parte do conteúdo não pôde ser obtida."
                    )
                elif error_code in {"GITHUB_TIMEOUT", "GITHUB_UNAVAILABLE"} or (
                    isinstance(status_code, int) and status_code >= 500
                ):
                    stop_fetching_reason = (
                        "Leitura não tentada após uma falha de comunicação com o GitHub."
                    )
                    warnings.append(
                        "A leitura foi interrompida após uma falha de comunicação com o GitHub."
                    )
            files.append(artifact)
            continue

        total_text += len(content_bytes)
        if len(content_bytes) > settings.max_file_bytes:
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = (
                f"Arquivo acima do limite de {settings.max_file_bytes} bytes."
            )
            files.append(artifact)
            warnings.append("Um arquivo excedeu o limite durante a leitura e foi ignorado.")
            continue
        if len(content_bytes) != size:
            artifact.eligibility_status = "failed"
            artifact.parse_status = "failed"
            artifact.metadata["ignored_reason"] = "O tamanho recebido não corresponde ao inventário GitHub."
            files.append(artifact)
            warnings.append(f"A integridade de um arquivo não pôde ser confirmada: {path_value}")
            continue

        blob_sha = entry.get("sha")
        if isinstance(blob_sha, str) and len(blob_sha) == 40:
            git_blob = hashlib.sha1(
                b"blob " + str(len(content_bytes)).encode("ascii") + b"\0" + content_bytes
            ).hexdigest()
            if git_blob != blob_sha.lower():
                artifact.eligibility_status = "failed"
                artifact.parse_status = "failed"
                artifact.metadata["ignored_reason"] = "A verificação de integridade do blob falhou."
                files.append(artifact)
                warnings.append(f"A integridade de um arquivo não pôde ser confirmada: {path_value}")
                continue

        if b"\x00" in content_bytes:
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = "Conteúdo binário detectado."
            files.append(artifact)
            continue
        try:
            decoded = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            artifact.eligibility_status = "ignored_by_policy"
            artifact.parse_status = "unsupported"
            artifact.metadata["ignored_reason"] = "Codificação textual não suportada pelo MVP."
            files.append(artifact)
            continue

        artifact.redacted_content = redact_secrets(decoded)
        artifact.raw_content = decoded
        artifact.content_hash = hashlib.sha256(content_bytes).hexdigest()
        artifact.eligibility_status = "eligible"
        artifact.parse_status = "queued" if artifact.is_python else "not_applicable"
        files.append(artifact)

    if not files:
        warnings.append("Nenhum arquivo foi encontrado na árvore GitHub dentro dos limites configurados.")
    return ArchiveResult(
        files=files,
        warnings=list(dict.fromkeys(warnings)),
        archive_size_bytes=0,
        unpacked_declared_bytes=total_declared,
        source_method="github_tree",
    )

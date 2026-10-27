"""Safe, read-only access to public GitHub repositories.

The client never follows user-provided URLs. API and archive hosts are fixed constants;
repository identity is extracted from a strict URL allowlist before any request is made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

from app.config import settings

GITHUB_API = "https://api.github.com"
GITHUB_ARCHIVE = "https://codeload.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
_SLUG_PART = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


class GitHubError(Exception):
    """A safe-to-display error raised for expected GitHub integration failures."""

    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RepositoryAddress:
    owner: str
    name: str
    canonical_url: str


@dataclass(frozen=True, slots=True)
class ResolvedRepository:
    owner: str
    name: str
    canonical_url: str
    default_branch: str
    requested_ref: str
    commit_sha: str
    tree_sha: str
    description: str | None
    repository_created_at: str | None
    commit_message: str | None
    commit_date: str | None

    def safe_metadata(self) -> dict[str, str | None]:
        return {
            "description": self.description,
            "repository_created_at": self.repository_created_at,
            "commit_message": self.commit_message,
            "commit_date": self.commit_date,
        }


def parse_github_url(value: str) -> RepositoryAddress:
    """Accept only https://github.com/{owner}/{repo}[.git] without URL extras."""
    if not value or len(value) > 2048:
        raise GitHubError("INVALID_REPOSITORY_URL", "Informe uma URL válida de repositório público do GitHub.", 422)
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError as exc:
        raise GitHubError("INVALID_REPOSITORY_URL", "A URL do repositório é inválida.", 422) from exc

    if (
        parts.scheme.lower() != "https"
        or parts.hostname is None
        or parts.hostname.lower() != "github.com"
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or parts.query
        or parts.fragment
        or "%" in parts.path
    ):
        raise GitHubError(
            "INVALID_REPOSITORY_URL",
            "Use somente uma URL canônica https://github.com/ proprietário/repositório, sem parâmetros.",
            422,
        )

    if not parts.path.startswith("/") or parts.path.startswith("//") or "//" in parts.path:
        raise GitHubError("INVALID_REPOSITORY_URL", "A URL do repositório possui um caminho inválido.", 422)
    pieces = parts.path.strip("/").split("/")
    if len(pieces) != 2:
        raise GitHubError(
            "INVALID_REPOSITORY_URL",
            "Informe apenas a página principal do repositório, sem caminhos de arquivo ou branch.",
            422,
        )
    owner, name = pieces
    if name.endswith(".git"):
        name = name[:-4]
    if (
        not _SLUG_PART.fullmatch(owner)
        or not _SLUG_PART.fullmatch(name)
        or owner in {".", ".."}
        or name in {".", ".."}
        or name.endswith(".")
    ):
        raise GitHubError("INVALID_REPOSITORY_URL", "O proprietário ou nome do repositório não é válido.", 422)

    return RepositoryAddress(
        owner=owner,
        name=name,
        canonical_url=f"https://github.com/{owner}/{name}",
    )


def validate_git_ref(value: str | None) -> str | None:
    """Reject ref syntax that can be confused with paths or malformed Git refs."""
    if value is None:
        return None
    ref = value.strip()
    forbidden = ("..", "//", "\\", "~", "^", ":", "?", "*", "[", "@{", " ", "\t", "\n")
    if (
        not ref
        or len(ref) > 255
        or ref.startswith("-")
        or ref.endswith(("/", "."))
        or ref.endswith(".lock")
        or any(item in ref for item in forbidden)
    ):
        raise GitHubError("INVALID_GIT_REF", "A referência Git informada não é válida.", 422)
    return ref


class GitHubClient:
    """Bounded, read-only client for GitHub metadata, trees, archives, and raw files."""

    def __init__(self, token: str | None = None, timeout_seconds: float = 15.0) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Yggdrasil-Repository-Mapper/0.1",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            follow_redirects=False,
            headers=headers,
        )
        # Separate connection pool so optional API credentials never reach raw.githubusercontent.com.
        self._raw_client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            follow_redirects=False,
            headers={"User-Agent": "Yggdrasil-Repository-Mapper/0.2"},
        )

    def close(self) -> None:
        self._client.close()
        self._raw_client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _get_json(self, path: str) -> dict[str, object]:
        # Paths are constructed only from validated slug/ref values and static route templates.
        try:
            response = self._client.get(f"{GITHUB_API}{path}")
        except httpx.TimeoutException as exc:
            raise GitHubError("GITHUB_TIMEOUT", "O GitHub demorou demais para responder.", 504) from exc
        except httpx.HTTPError as exc:
            raise GitHubError("GITHUB_UNAVAILABLE", "Não foi possível consultar o GitHub.", 502) from exc

        if response.is_redirect:
            raise GitHubError("GITHUB_REDIRECT_REJECTED", "O GitHub retornou um redirecionamento inesperado.", 502)
        if response.status_code == 404:
            raise GitHubError("REPOSITORY_NOT_ACCESSIBLE", "O repositório ou a referência não estão acessíveis publicamente.", 404)
        if response.status_code in {401, 403, 429}:
            raise GitHubError("GITHUB_RATE_LIMIT_OR_ACCESS", "O GitHub recusou a consulta ou atingiu um limite de uso. Tente novamente mais tarde ou configure um token somente de leitura.", 429)
        if response.status_code >= 500:
            raise GitHubError("GITHUB_UNAVAILABLE", "O GitHub está temporariamente indisponível.", 502)
        if response.status_code != 200:
            raise GitHubError("GITHUB_REQUEST_FAILED", "O GitHub não aceitou a consulta solicitada.", 502)
        try:
            data = response.json()
        except ValueError as exc:
            raise GitHubError("GITHUB_INVALID_RESPONSE", "O GitHub retornou uma resposta inválida.", 502) from exc
        if not isinstance(data, dict):
            raise GitHubError("GITHUB_INVALID_RESPONSE", "O GitHub retornou metadados em formato inesperado.", 502)
        return data

    def resolve(self, address: RepositoryAddress, requested_ref: str | None) -> ResolvedRepository:
        owner = quote(address.owner, safe="")
        name = quote(address.name, safe="")
        repository = self._get_json(f"/repos/{owner}/{name}")
        if repository.get("private") is True or repository.get("visibility") == "private":
            raise GitHubError("PRIVATE_REPOSITORY_UNSUPPORTED", "O MVP aceita somente repositórios públicos.", 403)

        default_branch = repository.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch:
            raise GitHubError("GITHUB_METADATA_INCOMPLETE", "Não foi possível identificar a branch padrão.", 502)
        ref = validate_git_ref(requested_ref) or default_branch
        commit = self._get_json(f"/repos/{owner}/{name}/commits/{quote(ref, safe='')}")
        sha = commit.get("sha")
        if not isinstance(sha, str) or not _COMMIT_SHA.fullmatch(sha):
            raise GitHubError("COMMIT_SHA_INVALID", "O GitHub não retornou um SHA de commit reconhecível.", 502)

        commit_object = commit.get("commit")
        commit_object = commit_object if isinstance(commit_object, dict) else {}
        tree_object = commit_object.get("tree")
        tree_object = tree_object if isinstance(tree_object, dict) else {}
        tree_sha = tree_object.get("sha")
        if not isinstance(tree_sha, str) or not _COMMIT_SHA.fullmatch(tree_sha):
            raise GitHubError("GITHUB_TREE_SHA_INVALID", "O GitHub não retornou o SHA da árvore do commit.", 502)
        commit_message = commit_object.get("message")
        commit_details = commit_object.get("committer")
        commit_details = commit_details if isinstance(commit_details, dict) else {}
        commit_date = commit_details.get("date")
        description = repository.get("description")
        created_at = repository.get("created_at")

        return ResolvedRepository(
            owner=address.owner,
            name=address.name,
            canonical_url=address.canonical_url,
            default_branch=default_branch,
            requested_ref=ref,
            commit_sha=sha.lower(),
            tree_sha=tree_sha.lower(),
            description=description if isinstance(description, str) else None,
            repository_created_at=created_at if isinstance(created_at, str) else None,
            commit_message=commit_message if isinstance(commit_message, str) else None,
            commit_date=commit_date if isinstance(commit_date, str) else None,
        )

    def download_archive(self, repository: ResolvedRepository, max_bytes: int | None = None) -> bytes:
        """Download a bounded archive for a commit SHA; no arbitrary URLs or redirects."""
        limit = max_bytes or settings.max_archive_bytes
        owner = quote(repository.owner, safe="")
        name = quote(repository.name, safe="")
        sha = quote(repository.commit_sha, safe="")
        url = f"{GITHUB_ARCHIVE}/{owner}/{name}/zip/{sha}"
        chunks: list[bytes] = []
        total = 0
        # Do not forward an optional API token to the separate archive host.
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout_seconds, connect=5.0),
                follow_redirects=False,
                headers={"User-Agent": "Yggdrasil-Repository-Mapper/0.1"},
            ) as archive_client:
                with archive_client.stream("GET", url) as response:
                    if response.is_redirect:
                        raise GitHubError("ARCHIVE_REDIRECT_REJECTED", "O download retornou um redirecionamento inesperado.", 502)
                    if response.status_code == 404:
                        raise GitHubError("ARCHIVE_NOT_FOUND", "Não foi possível obter o arquivo compactado do commit.", 404)
                    if response.status_code in {403, 429}:
                        raise GitHubError("GITHUB_RATE_LIMIT_OR_ACCESS", "O GitHub recusou o download do arquivo compactado.", 429)
                    if response.status_code != 200:
                        raise GitHubError("ARCHIVE_DOWNLOAD_FAILED", "Falha ao baixar o arquivo compactado do repositório.", 502)
                    length_header = response.headers.get("content-length")
                    if length_header and length_header.isdigit() and int(length_header) > limit:
                        raise GitHubError("ARCHIVE_TOO_LARGE", "O arquivo compactado excede o limite configurado para o MVP.", 413)
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > limit:
                            raise GitHubError("ARCHIVE_TOO_LARGE", "O arquivo compactado excede o limite configurado para o MVP.", 413)
                        chunks.append(chunk)
        except GitHubError:
            raise
        except httpx.TimeoutException as exc:
            raise GitHubError("GITHUB_TIMEOUT", "O download do repositório excedeu o tempo limite.", 504) from exc
        except httpx.HTTPError as exc:
            raise GitHubError("GITHUB_UNAVAILABLE", "Não foi possível baixar o repositório.", 502) from exc
        return b"".join(chunks)

    def get_repository_tree(self, repository: ResolvedRepository) -> dict[str, object]:
        """Return the fixed commit's recursive tree, recovering truncated trees subtree-by-subtree."""
        owner = quote(repository.owner, safe="")
        name = quote(repository.name, safe="")
        tree_sha = quote(repository.tree_sha, safe="")
        payload = self._get_json(f"/repos/{owner}/{name}/git/trees/{tree_sha}?recursive=1")
        tree = payload.get("tree")
        if not isinstance(tree, list):
            raise GitHubError("GITHUB_TREE_INVALID", "O GitHub retornou uma árvore de arquivos inválida.", 502)
        if payload.get("truncated") is not True:
            return payload

        # GitHub caps recursive tree responses. Re-walk non-recursively rather than silently
        # accepting only its prefix. The traversal itself is bounded by MAX_FILES and
        # MAX_TREE_DIRECTORIES; if those limits are hit, the returned flag remains true.
        pending: list[tuple[str, str]] = [("", repository.tree_sha)]
        collected: list[dict[str, object]] = []
        visited_directories = 0
        leaf_entries = 0
        truncated = False
        visited: set[tuple[str, str]] = set()

        while pending:
            prefix, current_sha = pending.pop()
            visit_key = (prefix, current_sha)
            if visit_key in visited:
                continue
            visited.add(visit_key)
            visited_directories += 1
            if visited_directories > settings.max_tree_directories:
                truncated = True
                break

            current_sha_encoded = quote(current_sha, safe="")
            subtree = self._get_json(
                f"/repos/{owner}/{name}/git/trees/{current_sha_encoded}"
            )
            children = subtree.get("tree")
            if not isinstance(children, list):
                raise GitHubError("GITHUB_TREE_INVALID", "O GitHub retornou uma árvore de arquivos inválida.", 502)
            if subtree.get("truncated") is True:
                truncated = True

            for child_index, child in enumerate(children):
                if not isinstance(child, dict):
                    continue
                relative = child.get("path")
                kind = child.get("type")
                if not isinstance(relative, str) or not relative:
                    continue
                full_path = f"{prefix}/{relative}" if prefix else relative
                if kind == "tree":
                    child_sha = child.get("sha")
                    if isinstance(child_sha, str) and _COMMIT_SHA.fullmatch(child_sha):
                        pending.append((full_path, child_sha))
                    continue
                if kind not in {"blob", "commit"}:
                    continue
                collected.append({**child, "path": full_path})
                leaf_entries += 1
                if leaf_entries >= settings.max_files:
                    if pending or child_index < len(children) - 1:
                        truncated = True
                    pending.clear()
                    break

        return {
            "sha": repository.tree_sha,
            "tree": collected,
            "truncated": truncated,
            "recovered_from_truncated_recursive_tree": True,
        }

    def download_raw_file(
        self,
        repository: ResolvedRepository,
        path: str,
        max_bytes: int | None = None,
    ) -> bytes:
        """Fetch one file from a fixed raw GitHub host, pinned to a commit, with strict bounds."""
        limit = max_bytes if max_bytes is not None else settings.max_file_bytes
        if (
            not path
            or len(path) > 1024
            or path.startswith(("/", "\\"))
            or "\\" in path
            or "\x00" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise GitHubError("GITHUB_PATH_INVALID", "O GitHub retornou um caminho de arquivo inválido.", 502)

        owner = quote(repository.owner, safe="")
        name = quote(repository.name, safe="")
        sha = quote(repository.commit_sha, safe="")
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        url = f"{GITHUB_RAW}/{owner}/{name}/{sha}/{encoded_path}"
        total = 0
        chunks: list[bytes] = []
        try:
            with self._raw_client.stream("GET", url) as response:
                if response.is_redirect:
                    raise GitHubError("RAW_FILE_REDIRECT_REJECTED", "O download de um arquivo retornou redirecionamento inesperado.", 502)
                if response.status_code == 404:
                    raise GitHubError("RAW_FILE_NOT_FOUND", "Um arquivo listado na árvore não pôde ser obtido.", 404)
                if response.status_code in {403, 429}:
                    raise GitHubError("GITHUB_RATE_LIMIT_OR_ACCESS", "O GitHub limitou a obtenção de arquivos. Tente novamente mais tarde ou configure um token somente de leitura.", 429)
                if response.status_code >= 500:
                    raise GitHubError("GITHUB_UNAVAILABLE", "O host de arquivos do GitHub está temporariamente indisponível.", 502)
                if response.status_code != 200:
                    raise GitHubError("RAW_FILE_DOWNLOAD_FAILED", "Falha ao obter um arquivo do repositório.", 502)
                length_header = response.headers.get("content-length")
                if length_header and length_header.isdigit() and int(length_header) > limit:
                    raise GitHubError("RAW_FILE_TOO_LARGE", "Um arquivo excede o limite individual de leitura.", 413)
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise GitHubError("RAW_FILE_TOO_LARGE", "Um arquivo excede o limite individual de leitura.", 413)
                    chunks.append(chunk)
        except GitHubError:
            raise
        except httpx.TimeoutException as exc:
            raise GitHubError("GITHUB_TIMEOUT", "A obtenção de um arquivo excedeu o tempo limite.", 504) from exc
        except httpx.HTTPError as exc:
            raise GitHubError("GITHUB_UNAVAILABLE", "Não foi possível obter um arquivo do GitHub.", 502) from exc
        return b"".join(chunks)

from __future__ import annotations

import pytest

from app.infrastructure.github import GitHubError, parse_github_url, validate_git_ref


def test_canonical_github_url_is_normalized() -> None:
    address = parse_github_url("https://github.com/psf/requests.git")
    assert address.owner == "psf"
    assert address.name == "requests"
    assert address.canonical_url == "https://github.com/psf/requests"


@pytest.mark.parametrize(
    "value",
    [
        "http://github.com/psf/requests",
        "https://github.com.evil.example/psf/requests",
        "https://user:password@github.com/psf/requests",
        "https://github.com/psf/requests/tree/main",
        "https://github.com//psf/requests",
        "https://github.com/psf/requests?download=1",
        "https://github.com/%70sf/requests",
        "https://github.com:443/psf/requests",
    ],
)
def test_unsafe_or_noncanonical_repository_urls_are_rejected(value: str) -> None:
    with pytest.raises(GitHubError):
        parse_github_url(value)


@pytest.mark.parametrize("value", ["main", "release/v1.2", "feature/new-map"])
def test_valid_git_refs(value: str) -> None:
    assert validate_git_ref(value) == value


@pytest.mark.parametrize("value", ["../main", "--upload-pack=x", "main..backup", "main\\evil", "branch?x", "x.lock", "a//b"])
def test_malformed_git_refs_are_rejected(value: str) -> None:
    with pytest.raises(GitHubError):
        validate_git_ref(value)


def test_resolve_captures_tree_sha_from_commit_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.github import GitHubClient

    client = GitHubClient()
    responses = {
        "/repos/psf/requests": {
            "default_branch": "main",
            "private": False,
            "visibility": "public",
            "description": "HTTP for humans",
            "created_at": "2011-02-13T00:00:00Z",
        },
        "/repos/psf/requests/commits/main": {
            "sha": "a" * 40,
            "commit": {
                "tree": {"sha": "b" * 40},
                "message": "sample commit",
                "committer": {"date": "2026-01-01T00:00:00Z"},
            },
        },
    }
    monkeypatch.setattr(client, "_get_json", lambda path: responses[path])
    try:
        resolved = client.resolve(parse_github_url("https://github.com/psf/requests"), None)
        assert resolved.commit_sha == "a" * 40
        assert resolved.tree_sha == "b" * 40
        assert resolved.requested_ref == "main"
    finally:
        client.close()


def test_truncated_recursive_tree_is_recovered_with_subtree_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.github import GitHubClient, ResolvedRepository

    root_sha = "b" * 40
    src_sha = "c" * 40
    calls: list[str] = []
    responses = {
        f"/repos/owner/repo/git/trees/{root_sha}?recursive=1": {
            "tree": [{"path": "partial.py", "type": "blob", "size": 1, "sha": "d" * 40}],
            "truncated": True,
        },
        f"/repos/owner/repo/git/trees/{root_sha}": {
            "tree": [
                {"path": "src", "type": "tree", "sha": src_sha},
                {"path": "README.md", "type": "blob", "size": 5, "sha": "e" * 40},
            ],
            "truncated": False,
        },
        f"/repos/owner/repo/git/trees/{src_sha}": {
            "tree": [{"path": "main.py", "type": "blob", "size": 4, "sha": "f" * 40}],
            "truncated": False,
        },
    }

    def fake_get_json(path: str) -> dict[str, object]:
        calls.append(path)
        return responses[path]

    repository = ResolvedRepository(
        owner="owner",
        name="repo",
        canonical_url="https://github.com/owner/repo",
        default_branch="main",
        requested_ref="main",
        commit_sha="a" * 40,
        tree_sha=root_sha,
        description=None,
        repository_created_at=None,
        commit_message=None,
        commit_date=None,
    )
    client = GitHubClient()
    monkeypatch.setattr(client, "_get_json", fake_get_json)
    try:
        result = client.get_repository_tree(repository)
    finally:
        client.close()

    assert calls[0].endswith(f"/trees/{root_sha}?recursive=1")
    assert result["truncated"] is False
    assert result["recovered_from_truncated_recursive_tree"] is True
    assert {entry["path"] for entry in result["tree"]} == {"README.md", "src/main.py"}

from __future__ import annotations

import io
import zipfile

from app.infrastructure.archive import inspect_archive


def make_zip(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_archive_is_inventoried_without_extracting_and_content_is_redacted() -> None:
    secret = "very_sensitive_value_should_not_be_persisted"
    archive = make_zip({
        "owner-repo-sha/app/main.py": f'API_KEY = "{secret}"\ndef run():\n    return True\n',
        "owner-repo-sha/assets/logo.png": b"\x89PNG\x00binary",
        "owner-repo-sha/vendor/library/module.py": "def external(): pass",
    })
    result = inspect_archive(archive)
    by_path = {file.path: file for file in result.files}
    main = by_path["app/main.py"]
    assert main.redacted_content is not None
    assert secret not in main.redacted_content
    assert secret in main.raw_content
    assert by_path["assets/logo.png"].eligibility_status == "ignored_by_policy"
    assert by_path["vendor/library/module.py"].eligibility_status == "ignored_by_policy"


def test_parent_traversal_entry_is_rejected() -> None:
    archive = make_zip({
        "owner-repo-sha/../outside.py": "print('no')",
        "owner-repo-sha/safe.py": "print('yes')",
    })
    result = inspect_archive(archive)
    assert [file.path for file in result.files] == ["safe.py"]
    assert any("caminho inválido" in warning for warning in result.warnings)


def test_invalid_zip_is_rejected() -> None:
    try:
        inspect_archive(b"not a zip")
    except ValueError as exc:
        assert str(exc) == "invalid_archive"
    else:
        raise AssertionError("invalid ZIP should be rejected")


def test_github_tree_fetches_only_safe_eligible_text_files_and_verifies_blob() -> None:
    import hashlib

    from app.infrastructure.archive import inspect_github_tree

    content = b'def hello():\n    return "world"\n'
    blob_sha = hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()
    requested: list[str] = []

    def fetch(path: str, max_bytes: int) -> bytes:
        assert max_bytes > len(content)
        requested.append(path)
        return content

    result = inspect_github_tree(
        [
            {"path": "app/hello.py", "type": "blob", "mode": "100644", "size": len(content), "sha": blob_sha},
            {"path": "app/logo.png", "type": "blob", "mode": "100644", "size": 3, "sha": "b" * 40},
            {"path": "vendor/pkg/module.py", "type": "blob", "mode": "100644", "size": 12, "sha": "c" * 40},
            {"path": "app/link.py", "type": "blob", "mode": "120000", "size": 8, "sha": "d" * 40},
            {"path": "../outside.py", "type": "blob", "mode": "100644", "size": 1, "sha": "e" * 40},
        ],
        fetch,
        tree_truncated=True,
    )

    by_path = {item.path: item for item in result.files}
    assert requested == ["app/hello.py"]
    assert by_path["app/hello.py"].is_python
    assert by_path["app/hello.py"].metadata["source_method"] == "github_tree"
    assert by_path["app/logo.png"].eligibility_status == "ignored_by_policy"
    assert by_path["vendor/pkg/module.py"].eligibility_status == "ignored_by_policy"
    assert by_path["app/link.py"].eligibility_status == "ignored_by_policy"
    assert any("inventário é parcial" in warning for warning in result.warnings)
    assert any("caminho inválido" in warning for warning in result.warnings)
    assert result.source_method == "github_tree"


def test_github_tree_rejects_blob_content_that_does_not_match_commit_sha() -> None:
    from app.infrastructure.archive import inspect_github_tree

    content = b"def expected(): pass\n"
    result = inspect_github_tree(
        [{"path": "app/module.py", "type": "blob", "mode": "100644", "size": len(content), "sha": "0" * 40}],
        lambda _path, _limit: content,
    )
    item = result.files[0]
    assert item.eligibility_status == "failed"
    assert item.parse_status == "failed"
    assert item.redacted_content is None
    assert any("integridade" in warning for warning in result.warnings)


def test_github_tree_missing_blob_size_is_not_downloaded() -> None:
    from app.infrastructure.archive import inspect_github_tree

    called: list[str] = []
    result = inspect_github_tree(
        [{"path": "app/module.py", "type": "blob", "mode": "100644", "sha": "a" * 40}],
        lambda path, _limit: called.append(path) or b"def unsafe_to_guess(): pass\n",
    )
    assert called == []
    assert result.files[0].eligibility_status == "failed"
    assert result.files[0].redacted_content is None
    assert any("Metadados incompletos" in warning for warning in result.warnings)


def test_github_rate_limit_stops_more_blob_downloads_but_preserves_inventory() -> None:
    from app.infrastructure.archive import inspect_github_tree
    from app.infrastructure.github import GitHubError

    called: list[str] = []
    entries = [
        {"path": f"app/{name}.py", "type": "blob", "mode": "100644", "size": 4, "sha": str(index) * 40}
        for index, name in enumerate(("first", "second", "third"), start=1)
    ]

    def fetch(path: str, _limit: int) -> bytes:
        called.append(path)
        raise GitHubError("GITHUB_RATE_LIMIT_OR_ACCESS", "rate limited", 429)

    result = inspect_github_tree(entries, fetch)
    assert called == ["app/first.py"]
    assert len(result.files) == 3
    assert all(item.eligibility_status == "failed" for item in result.files)
    assert any("limitou a leitura" in warning for warning in result.warnings)

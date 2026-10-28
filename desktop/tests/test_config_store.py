from __future__ import annotations

import json
from pathlib import Path

import pytest

from desktop import config_store


def test_public_endpoint_policy_rejects_plain_http_and_url_credentials() -> None:
    assert config_store.is_safe_base_url("https://generativelanguage.googleapis.com")
    assert config_store.is_safe_base_url("http://127.0.0.1:1234/v1")
    assert not config_store.is_safe_base_url("http://example.com/v1")
    assert not config_store.is_safe_base_url("https://user:pass@example.com/v1")
    assert not config_store.is_safe_base_url("https://example.com/v1?key=secret")


def test_settings_file_never_serializes_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    saved = config_store.save_settings({
        "ai_enabled": True,
        "ai_base_url": "https://generativelanguage.googleapis.com",
        "ai_model": "model-under-test",
        "ai_reasoning_effort": "low",
        "api_key": "must-not-enter-json",
    })
    raw = config_store.settings_path().read_text(encoding="utf-8")
    assert saved["ai_enabled"] is True
    assert "must-not-enter-json" not in raw
    assert "api_key" not in json.loads(raw)


def test_key_is_written_only_as_encrypted_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(config_store, "protect_secret", lambda secret: b"dpapi:" + secret.encode())
    monkeypatch.setattr(config_store, "unprotect_secret", lambda raw: raw.removeprefix(b"dpapi:").decode())
    config_store.write_api_key("secret-not-plain")
    assert config_store.key_path().read_bytes() != b"secret-not-plain"
    assert config_store.read_api_key() == "secret-not-plain"
    assert "secret-not-plain" not in config_store.settings_path().read_text(encoding="utf-8") if config_store.settings_path().exists() else True

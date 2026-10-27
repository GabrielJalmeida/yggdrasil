from __future__ import annotations

import json
import httpx
import pytest

from app.config import Settings
from app.infrastructure import ai_provider
from app.infrastructure.ai_provider import AIProviderError


def _configured_settings() -> Settings:
    return Settings(
        ai_provider="openai-compatible",
        ai_api_key="provider-secret-key-for-test",
        ai_base_url="https://provider.example/v1",
        ai_model="test-model",
        ai_timeout_seconds=4.0,
        ai_max_context_chars=14000,
        ai_max_evidence_items=8,
    )


def test_provider_sends_only_supplied_evidence_and_parses_structured_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        sent = json.loads(request.content)
        seen["model"] = sent["model"]
        seen["response_format"] = sent.get("response_format")
        seen["max_completion_tokens"] = sent.get("max_completion_tokens")
        seen["system"] = sent["messages"][0]["content"]
        seen["user"] = sent["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({
                    "answer": "A função está em app/service.py. [E1]",
                    "citation_ids": ["E1"],
                    "insufficient_evidence": False,
                })}}]
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(ai_provider, "settings", _configured_settings())
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    evidence = [{"id": "E1", "path": "app/service.py", "excerpt": "def calculate(value): return value + 1"}]
    result = ai_provider.generate_answer(
        "Do que se trata o projeto?", evidence, intent="overview", intent_guidance="Priorize README e manifestos."
    )

    assert result.answer == "A função está em app/service.py. [E1]"
    assert result.citation_ids == ["E1"]
    assert result.insufficient_evidence is False
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["authorization"] == "Bearer provider-secret-key-for-test"
    assert seen["model"] == "test-model"
    assert "não confiável" in str(seen["system"])
    assert seen["response_format"] == {"type": "json_object"}
    assert seen["max_completion_tokens"] == 1400
    assert "def calculate" in str(seen["user"])
    user_payload = json.loads(str(seen["user"]))
    assert user_payload["question_intent"] == "overview"
    assert user_payload["analysis_guidance"] == "Priorize README e manifestos."
    assert "provider-secret-key-for-test" not in str(seen["user"])


def test_provider_does_not_expose_upstream_auth_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="private upstream detail and token-like-value")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(ai_provider, "settings", _configured_settings())
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    with pytest.raises(AIProviderError) as error:
        ai_provider.generate_answer("Question", [{"id": "E1", "excerpt": "safe"}])
    assert error.value.code == "AI_CONFIGURATION_ERROR"
    assert "private upstream detail" not in error.value.message
    assert "token-like-value" not in error.value.message


def test_keyless_provider_is_allowed_only_for_local_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    public_keyless = Settings(
        ai_provider="openai-compatible",
        ai_api_key=None,
        ai_base_url="https://provider.example/v1",
        ai_model="test-model",
    )
    monkeypatch.setattr(ai_provider, "settings", public_keyless)
    assert ai_provider.ai_is_configured() is False

    local_keyless = Settings(
        ai_provider="openai-compatible",
        ai_api_key=None,
        ai_base_url="http://localhost:11434/v1",
        ai_model="local-model",
    )
    monkeypatch.setattr(ai_provider, "settings", local_keyless)
    assert ai_provider.ai_is_configured() is True

    unsafe_http = Settings(
        ai_provider="openai-compatible",
        ai_api_key="not-to-be-sent",
        ai_base_url="http://provider.example/v1",
        ai_model="test-model",
    )
    monkeypatch.setattr(ai_provider, "settings", unsafe_http)
    assert ai_provider.ai_is_configured() is False


def test_gemini_uses_native_api_low_thinking_and_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key_header"] = request.headers.get("x-goog-api-key")
        seen["authorization"] = request.headers.get("Authorization")
        sent = json.loads(request.content)
        seen["system"] = sent["systemInstruction"]["parts"][0]["text"]
        seen["user"] = sent["contents"][0]["parts"][0]["text"]
        seen["generation_config"] = sent["generationConfig"]
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({
                "answer": "O trecho mostra uma função. [E1]",
                "citation_ids": ["E1"],
                "insufficient_evidence": False,
            })}]}, "finishReason": "STOP"}]},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(**kwargs):
        timeout = kwargs.get("timeout")
        seen["timeout_total"] = timeout.read
        seen["timeout_connect"] = timeout.connect
        return real_client(transport=transport, **kwargs)

    gemini_settings = Settings(
        ai_provider="openai-compatible",
        ai_api_key="test-gemini-key",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ai_model="gemini-3.8-flash",
        ai_timeout_seconds=35.0,
        ai_reasoning_effort="low",
    )
    monkeypatch.setattr(ai_provider, "settings", gemini_settings)
    monkeypatch.setattr(ai_provider.httpx, "Client", client_factory)

    result = ai_provider.generate_answer("O que faz esta função?", [{"id": "E1", "excerpt": "def f(): return 1"}])

    assert result.citation_ids == ["E1"]
    assert result.answer == "O trecho mostra uma função. [E1]"
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    assert seen["api_key_header"] == "test-gemini-key"
    assert seen["authorization"] is None
    assert "não confiável" in str(seen["system"])
    generation_config = seen["generation_config"]
    assert isinstance(generation_config, dict)
    assert generation_config["thinkingConfig"] == {"thinkingLevel": "LOW"}
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["maxOutputTokens"] == 4096
    assert generation_config["responseJsonSchema"]["required"] == ["answer", "citation_ids", "insufficient_evidence"]
    assert seen["timeout_total"] == 90.0
    assert seen["timeout_connect"] == 8.0
    assert "test-gemini-key" not in str(seen["user"])


def test_gemini_model_not_found_has_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(404, json={"error": {"message": "private details"}}))
    real_client = httpx.Client
    gemini_settings = Settings(
        ai_provider="openai-compatible",
        ai_api_key="test-gemini-key",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ai_model="model-that-does-not-exist",
    )
    monkeypatch.setattr(ai_provider, "settings", gemini_settings)
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    with pytest.raises(AIProviderError) as error:
        ai_provider.generate_answer("Question", [{"id": "E1", "excerpt": "safe"}])
    assert error.value.code == "AI_MODEL_NOT_FOUND"
    assert "AI_MODEL" in error.value.message
    assert "private details" not in error.value.message


def test_gemini_blocked_response_has_safe_message(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(
        200, json={"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
    ))
    real_client = httpx.Client
    gemini_settings = Settings(
        ai_provider="openai-compatible",
        ai_api_key="test-gemini-key",
        ai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ai_model="gemini-3.8-flash",
    )
    monkeypatch.setattr(ai_provider, "settings", gemini_settings)
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    with pytest.raises(AIProviderError) as error:
        ai_provider.generate_answer("Question", [{"id": "E1", "excerpt": "safe"}])
    assert error.value.code == "AI_RESPONSE_BLOCKED"


def test_provider_read_timeout_has_actionable_safe_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive upstream detail")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(ai_provider, "settings", _configured_settings())
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    with pytest.raises(AIProviderError) as error:
        ai_provider.generate_answer("Question", [{"id": "E1", "excerpt": "safe"}])

    assert error.value.code == "AI_RESPONSE_TIMEOUT"
    assert "4 segundos" in error.value.message
    assert "sensitive upstream detail" not in error.value.message


def test_gemini_retries_transient_503_once_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "temporary"}})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({
                "answer": "Resposta curta. [E1]",
                "citation_ids": ["E1"],
                "insufficient_evidence": False,
            })}]}, "finishReason": "STOP"}]},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    gemini_settings = Settings(
        ai_provider="openai-compatible",
        ai_api_key="test-gemini-key",
        ai_base_url="https://generativelanguage.googleapis.com",
        ai_model="gemini-3.8-flash",
        ai_timeout_seconds=90.0,
    )
    monkeypatch.setattr(ai_provider, "settings", gemini_settings)
    monkeypatch.setattr(ai_provider.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    answer = ai_provider.generate_answer("Explique o projeto", [{"id": "E1", "excerpt": "README"}])

    assert calls["count"] == 2
    assert answer.citation_ids == ["E1"]
    assert answer.answer == "Resposta curta. [E1]"


def test_gemini_persistent_503_shows_safe_status_and_attempt_count(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            503,
            json={"error": {"status": "UNAVAILABLE", "message": "private upstream detail with secret"}},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    gemini_settings = Settings(
        ai_provider="openai-compatible",
        ai_api_key="test-gemini-key",
        ai_base_url="https://generativelanguage.googleapis.com",
        ai_model="gemini-3.8-flash",
        ai_timeout_seconds=90.0,
    )
    monkeypatch.setattr(ai_provider, "settings", gemini_settings)
    monkeypatch.setattr(ai_provider.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    with pytest.raises(AIProviderError) as error:
        ai_provider.generate_answer("Explique o projeto", [{"id": "E1", "excerpt": "README"}])

    assert calls["count"] == 2
    assert error.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert "HTTP 503 (UNAVAILABLE)" in error.value.message
    assert "após uma nova tentativa" in error.value.message
    assert "private upstream detail" not in error.value.message
    assert "secret" not in error.value.message
    assert "ai_upstream_failure" in caplog.text
    assert "http_status=503" in caplog.text
    assert "private upstream detail" not in caplog.text

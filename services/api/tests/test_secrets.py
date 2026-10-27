from __future__ import annotations

from app.domain.secrets import detect_secret_candidates, redact_secrets
from app.domain.skills import run_initial_skills
from app.infrastructure.archive import ArchiveArtifact


def test_secret_detection_returns_locations_without_values() -> None:
    source = 'API_KEY = "top_secret_value_12345"\npassword = "change_me"\n'
    candidates = detect_secret_candidates(source)
    assert len(candidates) == 1
    assert candidates[0].start_line == 1
    assert candidates[0].category == "api_key_candidate"
    assert "top_secret_value_12345" not in repr(candidates)


def test_redaction_keeps_lines_and_removes_probable_secret_values() -> None:
    source = 'API_KEY = "top_secret_value_12345"\nprint("still here")\n'
    result = redact_secrets(source)
    assert "top_secret_value_12345" not in result
    assert "[REDACTED]" in result
    assert len(result.splitlines()) == len(source.splitlines())
    assert 'print("still here")' in result


def test_placeholder_is_not_reported_or_redacted() -> None:
    source = 'API_KEY = "your-api-key-here"\npassword = "change_me"\n'
    assert detect_secret_candidates(source) == []
    assert redact_secrets(source) == source


def test_duplicate_secret_candidates_on_same_line_are_coalesced() -> None:
    source = 'API_KEY = "first_private_value_123"; API_KEY = "second_private_value_456"\n'
    artifact = ArchiveArtifact(
        path="config.py",
        size_bytes=len(source.encode("utf-8")),
        language="Python",
        redacted_content=redact_secrets(source),
        raw_content=source,
    )

    findings, warnings = run_initial_skills(
        [artifact],
        "a" * 40,
        ["appsec.secrets-detection"],
    )

    assert not warnings
    assert len(findings) == 1
    assert findings[0].finding_key
    assert findings[0].evidence[0]["path"] == "config.py"
    assert "first_private_value_123" not in repr(findings)
    assert "second_private_value_456" not in repr(findings)


def test_unquoted_config_credentials_are_detected_and_redacted() -> None:
    source = "PASSWORD=VeryLongFakeSecret123\nAPI_KEY=your-api-key-here\n"

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert len(candidates) == 1
    assert candidates[0].category == "hardcoded_password_candidate"
    assert candidates[0].start_line == 1
    assert "VeryLongFakeSecret123" not in redacted
    assert "VeryLongFakeSecret123" not in repr(candidates)
    assert "API_KEY=your-api-key-here" in redacted
    assert len(redacted.splitlines()) == len(source.splitlines())


def test_database_url_credentials_are_flagged_without_exposing_user_or_password() -> None:
    source = 'DATABASE_URL = "postgresql://service_user:VeryFakeDbPassword987@db.example.test/app"\n'

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert len(candidates) == 1
    assert candidates[0].category == "url_credential_candidate"
    assert candidates[0].start_line == 1
    assert "service_user" not in redacted
    assert "VeryFakeDbPassword987" not in redacted
    assert "postgresql://[REDACTED]@db.example.test/app" in redacted
    assert "VeryFakeDbPassword987" not in repr(candidates)


def test_provider_token_formats_are_flagged_and_redacted() -> None:
    google_key = "AIza" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r"
    stripe_key = "sk_live_0123456789abcdef0123"
    slack_token = "xoxb-" + "123456789012-" + "abcdefghijklmnop"
    source = f"# leaked literals\n{google_key}\n{stripe_key}\n{slack_token}\n"

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert {item.category for item in candidates} == {
        "cloud_api_key_candidate",
        "payment_provider_key_candidate",
        "messaging_token_candidate",
    }
    for value in (google_key, stripe_key, slack_token):
        assert value not in redacted
        assert value not in repr(candidates)
    assert len(redacted.splitlines()) == len(source.splitlines())


def test_bearer_tokens_and_urls_with_embedded_credentials_are_redacted() -> None:
    bearer = "eyJhbGciOi_fakeBearerTokenValue01234567890"
    source = (
        f"Authorization: Bearer {bearer}\n"
        "client_url = https://demo_user:DemoPassword987@example.test/path\n"
    )

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert "bearer_token_candidate" in {item.category for item in candidates}
    assert "url_credential_candidate" in {item.category for item in candidates}
    assert bearer not in redacted
    assert "demo_user" not in redacted
    assert "DemoPassword987" not in redacted
    assert "[REDACTED BEARER TOKEN]" in redacted


def test_environment_lookup_expression_is_not_mangled_as_a_literal_secret() -> None:
    source = 'PASSWORD = os.getenv("SERVICE_PASSWORD")\n'

    assert detect_secret_candidates(source) == []
    assert redact_secrets(source) == source


def test_unquoted_secret_with_punctuation_is_redacted_as_a_whole_value() -> None:
    source = "PASSWORD=FakeSecret!Tail$More987,End;And\n"

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert len(candidates) == 1
    assert "FakeSecret" not in redacted
    assert "Tail$More987" not in redacted
    assert "End;And" not in redacted
    assert "[REDACTED]" in redacted


def test_placeholder_url_credentials_are_not_reported_as_a_leak() -> None:
    source = 'DATABASE_URL="postgresql://user:password@localhost/sample"\n'

    assert detect_secret_candidates(source) == []
    assert redact_secrets(source) == source


def test_secret_value_with_placeholder_like_prefix_is_still_detected() -> None:
    source = 'API_KEY="sampleRealSecret123"\n'

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert len(candidates) == 1
    assert candidates[0].category == "api_key_candidate"
    assert "sampleRealSecret123" not in redacted



def test_environment_variable_references_are_not_treated_as_literal_secrets() -> None:
    source = "API_TOKEN=$SERVICE_API_TOKEN\n"

    assert detect_secret_candidates(source) == []
    assert redact_secrets(source) == source


def test_json_quoted_secret_keys_are_detected_and_redacted() -> None:
    source = '{"api_key": "JsonFakeSecretValue987", "name": "demo"}\n'

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert len(candidates) == 1
    assert candidates[0].category == "api_key_candidate"
    assert "JsonFakeSecretValue987" not in redacted
    assert '"name": "demo"' in redacted


def test_generic_username_does_not_hide_a_real_looking_url_password() -> None:
    source = 'DATABASE_URL="postgresql://user:VeryFakePasswordValue987@localhost/app"\n'

    candidates = detect_secret_candidates(source)
    redacted = redact_secrets(source)

    assert len(candidates) == 1
    assert candidates[0].category == "url_credential_candidate"
    assert "VeryFakePasswordValue987" not in redacted
    assert 'postgresql://[REDACTED]@localhost/app' in redacted

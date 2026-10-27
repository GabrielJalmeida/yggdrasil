"""Conservative secret-candidate detection and value redaction for untrusted source text.

Only locations and categories leave this module; candidate values are never returned.
Detection and redaction intentionally share the same patterns so a finding does not point to a
value that the code-inspection UI or persisted source content still exposes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Accept quoted code/config values plus common unquoted .env/YAML-style token literals. Unquoted
# values must end at whitespace or a comment so unsupported punctuation cannot be partly redacted.
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>[\"']?(?:[A-Z0-9_]*_)?(?:api[_-]?key|secret(?:[_-]?(?:access|client|auth|private))?[_-]?key|"
    r"password|passwd|pwd|token|access[_-]?token|private[_-]?key|client[_-]?secret|"
    r"auth[_-]?token|credential|aws[_-]?access[_-]?key|database[_-]?password)\b[\"']?\s*[:=]\s*)"
    r"(?:(?P<quote>['\"])(?P<quoted_value>[^'\"\r\n]{8,})(?P=quote)|"
    r"(?P<unquoted_value>[^\s#\"']{8,})(?=$|[\s#]))"
)
_PLACEHOLDER = re.compile(
    r"(?i)^\s*(?:\$\{[^}]+\}|\$[A-Z_][A-Z0-9_]*|<[^>]+>|\*+|"
    r"your(?:[-_ ][a-z0-9]+){1,5}[-_ ]here|change[-_ ]?me(?:[-_ ]here)?|"
    r"example|sample|dummy|placeholder|test[-_ ]?token|none|null|false|true|redacted|"
    r"replace[-_ ]?me|insert[-_ ](?:value|token|key|password|secret)|todo|"
    r"username|user|password|passwd|pass)\s*$"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----.*?"
    r"-----END (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
    flags=re.DOTALL,
)
_DATABASE_URL_CREDENTIALS = re.compile(
    r"(?i)(?P<scheme>(?:https?|postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|mssql)://)"
    r"(?P<userinfo>[^/@:\s]+:[^/@\s]+)@"
)
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b")
_GOOGLE_API_KEY = re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")
_SLACK_TOKEN = re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")
_SLACK_WEBHOOK = re.compile(
    r"https?://hooks\.slack\.com/services/(?P<token>[A-Z0-9]{6,}/[A-Z0-9]{6,}/[A-Za-z0-9]{10,})",
    flags=re.IGNORECASE,
)
_STRIPE_SECRET = re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")
_BEARER_TOKEN = re.compile(
    r"(?i)(?P<prefix>\bbearer[ \t]+)(?P<value>[A-Za-z0-9._~+/-]{20,}={0,2})"
)
_JWT = re.compile(
    r"\b(?P<value>eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,})\b"
)


@dataclass(frozen=True, slots=True)
class SecretCandidate:
    category: str
    start_line: int
    end_line: int
    evidence_type: str = "static_pattern"


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _not_placeholder(value: str | None) -> bool:
    return bool(value) and _PLACEHOLDER.search(value) is None


def _url_userinfo_is_placeholder(userinfo: str) -> bool:
    """Recognize documentation URLs when the password component is an obvious placeholder."""
    _username, separator, password = userinfo.partition(":")
    if not separator:
        return not _not_placeholder(userinfo)
    # A generic username like `user` is common even in real connection strings, so it must not
    # suppress detection when the password component looks like a real value.
    return not _not_placeholder(password)


def _assignment_value_is_secret_candidate(value: str | None, quote: str | None) -> bool:
    if not _not_placeholder(value):
        return False
    if quote:
        return True
    # References/accessors are not literal values. Dotted secrets from other formats are still
    # detected unless they look like common configuration access expressions.
    assert value is not None
    return re.match(
        r"(?i)^(?:os\.(?:getenv|environ)|settings\.|config\.|secrets\.|"
        r"env\.|get_[a-z0-9_]+\s*\()",
        value,
    ) is None


def _append_candidate(
    candidates: list[SecretCandidate],
    occupied: list[tuple[int, int]],
    text: str,
    start: int,
    end: int,
    category: str,
) -> None:
    if any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied):
        return
    candidates.append(
        SecretCandidate(
            category=category,
            start_line=_line_for_offset(text, start),
            end_line=_line_for_offset(text, max(start, end - 1)),
        )
    )
    occupied.append((start, end))


def detect_secret_candidates(text: str) -> list[SecretCandidate]:
    """Return locations/categories only; never include the secret value in the result."""
    candidates: list[SecretCandidate] = []
    occupied: list[tuple[int, int]] = []

    for match in _PRIVATE_KEY.finditer(text):
        _append_candidate(
            candidates, occupied, text, match.start(), match.end(), "private_key_block"
        )

    # Known URL credentials first, so the whole credential-bearing authority is represented as
    # one candidate rather than as an unrelated substring.
    for match in _DATABASE_URL_CREDENTIALS.finditer(text):
        if not _url_userinfo_is_placeholder(match.group("userinfo")):
            _append_candidate(
                candidates, occupied, text, match.start(), match.end(), "url_credential_candidate"
            )

    for match in _SECRET_ASSIGNMENT.finditer(text):
        value = match.group("quoted_value") or match.group("unquoted_value")
        if not _assignment_value_is_secret_candidate(value, match.group("quote")):
            continue
        key = match.group("prefix").split("=", 1)[0].split(":", 1)[0].strip().lower()
        category = "credential_assignment"
        if "password" in key or "passwd" in key or "pwd" in key:
            category = "hardcoded_password_candidate"
        elif "private" in key:
            category = "private_key_candidate"
        elif "secret" in key:
            category = "hardcoded_secret_candidate"
        elif "token" in key or "bearer" in key:
            category = "token_candidate"
        elif "api" in key or "key" in key:
            category = "api_key_candidate"
        elif "credential" in key:
            category = "credential_assignment"
        _append_candidate(
            candidates, occupied, text, match.start(), match.end(), category
        )

    format_patterns: tuple[tuple[re.Pattern[str], str, str | None], ...] = (
        (_AWS_ACCESS_KEY, "cloud_access_key_candidate", None),
        (_GITHUB_TOKEN, "source_control_token_candidate", None),
        (_GOOGLE_API_KEY, "cloud_api_key_candidate", None),
        (_SLACK_WEBHOOK, "messaging_webhook_candidate", "token"),
        (_SLACK_TOKEN, "messaging_token_candidate", None),
        (_STRIPE_SECRET, "payment_provider_key_candidate", None),
        (_BEARER_TOKEN, "bearer_token_candidate", "value"),
        (_JWT, "jwt_candidate", "value"),
    )
    for pattern, category, value_group in format_patterns:
        for match in pattern.finditer(text):
            if value_group and not _not_placeholder(match.group(value_group)):
                continue
            _append_candidate(
                candidates, occupied, text, match.start(), match.end(), category
            )

    return sorted(
        candidates,
        key=lambda candidate: (candidate.start_line, candidate.end_line, candidate.category),
    )


def redact_secrets(text: str) -> str:
    """Redact supported credential patterns while preserving line count and code shape."""
    redacted = _PRIVATE_KEY.sub(
        lambda match: "[REDACTED PRIVATE KEY BLOCK]" + "\n" * match.group(0).count("\n"),
        text,
    )

    def replace_assignment(match: re.Match[str]) -> str:
        value = match.group("quoted_value") or match.group("unquoted_value")
        if not _assignment_value_is_secret_candidate(value, match.group("quote")):
            return match.group(0)
        quote = match.group("quote")
        if quote:
            return f"{match.group('prefix')}{quote}[REDACTED]{quote}"
        return f"{match.group('prefix')}[REDACTED]"

    redacted = _SECRET_ASSIGNMENT.sub(replace_assignment, redacted)

    def replace_url_credentials(match: re.Match[str]) -> str:
        userinfo = match.group("userinfo")
        if _url_userinfo_is_placeholder(userinfo):
            return match.group(0)
        return f"{match.group('scheme')}[REDACTED]@"

    redacted = _DATABASE_URL_CREDENTIALS.sub(replace_url_credentials, redacted)
    redacted = _AWS_ACCESS_KEY.sub("[REDACTED CLOUD ACCESS KEY]", redacted)
    redacted = _GITHUB_TOKEN.sub("[REDACTED SOURCE CONTROL TOKEN]", redacted)
    redacted = _GOOGLE_API_KEY.sub("[REDACTED CLOUD API KEY]", redacted)
    redacted = _SLACK_WEBHOOK.sub("https://hooks.slack.com/services/[REDACTED]", redacted)
    redacted = _SLACK_TOKEN.sub("[REDACTED MESSAGING TOKEN]", redacted)
    redacted = _STRIPE_SECRET.sub("[REDACTED PAYMENT PROVIDER KEY]", redacted)
    redacted = _BEARER_TOKEN.sub(
        lambda match: f"{match.group('prefix')}[REDACTED BEARER TOKEN]", redacted
    )
    redacted = _JWT.sub("[REDACTED JWT]", redacted)
    return redacted

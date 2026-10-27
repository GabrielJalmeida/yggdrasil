"""Environment-backed settings with safe local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/yggdrasil.db")
    github_token: str | None = os.getenv("GITHUB_TOKEN") or None
    frontend_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    )
    max_archive_bytes: int = int(os.getenv("MAX_ARCHIVE_BYTES", "20971520"))
    max_files: int = int(os.getenv("MAX_FILES", "1000"))
    max_tree_directories: int = int(os.getenv("MAX_TREE_DIRECTORIES", "2000"))
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", "262144"))
    max_total_text_bytes: int = int(os.getenv("MAX_TOTAL_TEXT_BYTES", "8388608"))
    max_total_unpacked_bytes: int = int(
        os.getenv("MAX_TOTAL_UNPACKED_BYTES", "52428800")
    )
    ai_provider: str = os.getenv("AI_PROVIDER", "disabled").strip().lower()
    ai_api_key: str | None = os.getenv("AI_API_KEY") or None
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    ai_model: str = os.getenv("AI_MODEL", "").strip()
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "90"))
    ai_reasoning_effort: str = os.getenv("AI_REASONING_EFFORT", "low").strip().lower()
    ai_max_context_chars: int = int(os.getenv("AI_MAX_CONTEXT_CHARS", "14000"))
    ai_max_evidence_items: int = int(os.getenv("AI_MAX_EVIDENCE_ITEMS", "8"))
    app_version: str = "0.7.0"

    @property
    def ai_base_url_host(self) -> str:
        return (urlsplit(self.ai_base_url).hostname or "").lower()

    @property
    def ai_base_url_is_safe(self) -> bool:
        parsed = urlsplit(self.ai_base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        if parsed.scheme == "https":
            return True
        # Plain HTTP is allowed only for local/self-hosted providers to avoid key leakage in transit.
        return parsed.scheme == "http" and parsed.hostname.lower() in local_hosts

    @property
    def ai_enabled(self) -> bool:
        if self.ai_provider != "openai-compatible" or not self.ai_model or not self.ai_base_url_is_safe:
            return False
        if self.ai_api_key:
            return True
        # A keyless provider is allowed only for explicitly local/self-hosted endpoints.
        return self.ai_base_url_host in {
            "localhost", "127.0.0.1", "::1", "host.docker.internal"
        }

    @property
    def data_directory(self) -> Path:
        return Path("data")


settings = Settings()

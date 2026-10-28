"""Local desktop settings. The API key is never stored in the JSON settings file."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from desktop.secure_store import protect_secret, unprotect_secret

DEFAULT_SETTINGS: dict[str, object] = {
    "ai_enabled": False,
    "ai_base_url": "https://generativelanguage.googleapis.com",
    "ai_model": "",
    "ai_reasoning_effort": "low",
}
_ALLOWED_EFFORTS = {"low", "medium", "high"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def user_data_dir() -> Path:
    override = os.environ.get("YGGDRASIL_USER_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "Yggdrasil"
    return Path.home() / "AppData" / "Local" / "Yggdrasil"


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def key_path() -> Path:
    return user_data_dir() / "ai-key.dpapi"


def load_settings() -> dict[str, object]:
    result = DEFAULT_SETTINGS.copy()
    try:
        payload = json.loads(settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return result
    except (OSError, json.JSONDecodeError):
        return result
    if not isinstance(payload, dict):
        return result
    if isinstance(payload.get("ai_enabled"), bool):
        result["ai_enabled"] = payload["ai_enabled"]
    for key in ("ai_base_url", "ai_model"):
        value = payload.get(key)
        if isinstance(value, str) and len(value) <= 2048:
            result[key] = value
    effort = payload.get("ai_reasoning_effort")
    if isinstance(effort, str) and effort.lower() in _ALLOWED_EFFORTS:
        result["ai_reasoning_effort"] = effort.lower()
    return result


def save_settings(payload: dict[str, object]) -> dict[str, object]:
    ai_enabled = payload.get("ai_enabled", False)
    base_url = payload.get("ai_base_url", DEFAULT_SETTINGS["ai_base_url"])
    model = payload.get("ai_model", "")
    effort = str(payload.get("ai_reasoning_effort", "low")).lower()
    if not isinstance(ai_enabled, bool):
        raise ValueError("A opção de IA precisa estar habilitada ou desabilitada explicitamente.")
    if not isinstance(base_url, str) or len(base_url) > 2048 or not is_safe_base_url(base_url):
        raise ValueError("Informe uma URL HTTPS válida. HTTP só é aceito para um provedor local.")
    if not isinstance(model, str) or len(model.strip()) > 200:
        raise ValueError("O identificador do modelo é inválido.")
    if effort not in _ALLOWED_EFFORTS:
        raise ValueError("O nível de raciocínio precisa ser low, medium ou high.")
    normalized = {
        "ai_enabled": ai_enabled,
        "ai_base_url": base_url.rstrip("/"),
        "ai_model": model.strip(),
        "ai_reasoning_effort": effort,
    }
    directory = user_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path().with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp_path, settings_path())
    return normalized


def is_safe_base_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower()
        return bool(
            parsed.scheme in {"https", "http"}
            and host
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and (parsed.scheme == "https" or host in _LOCAL_HOSTS)
        )
    except ValueError:
        return False


def is_local_base_url(value: str) -> bool:
    try:
        return (urlsplit(value).hostname or "").lower() in _LOCAL_HOSTS
    except ValueError:
        return False


def has_saved_key() -> bool:
    return key_path().is_file()


def read_api_key() -> str | None:
    try:
        return unprotect_secret(key_path().read_bytes())
    except FileNotFoundError:
        return None
    except (OSError, RuntimeError, ValueError):
        return None


def write_api_key(value: str) -> None:
    if not value:
        return
    directory = user_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    encrypted = protect_secret(value)
    target = key_path()
    temp_path = target.with_suffix(".dpapi.tmp")
    temp_path.write_bytes(encrypted)
    os.replace(temp_path, target)


def remove_api_key() -> None:
    try:
        key_path().unlink()
    except FileNotFoundError:
        pass


def test_connection(base_url: str, model: str, api_key: str | None) -> tuple[bool, str]:
    """Perform a short credential/endpoint check without logging or echoing the key."""
    from urllib.parse import urlsplit

    if not is_safe_base_url(base_url):
        return False, "URL recusada: use HTTPS para endpoints externos e HTTP somente em loopback."
    if not model.strip():
        return False, "Informe o identificador do modelo antes de testar."
    host = (urlsplit(base_url).hostname or "").lower()
    if not api_key and host not in _LOCAL_HOSTS:
        return False, "Informe a chave da API; ela será protegida pelo Windows antes de ser salva."
    try:
        import httpx

        headers = {}
        if api_key:
            headers["x-goog-api-key" if host == "generativelanguage.googleapis.com" else "Authorization"] = (
                api_key if host == "generativelanguage.googleapis.com" else f"Bearer {api_key}"
            )
        if host == "generativelanguage.googleapis.com":
            url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
        else:
            url = f"{base_url.rstrip('/')}/models"
        response = httpx.get(url, headers=headers, timeout=httpx.Timeout(10, connect=4), follow_redirects=False)
        if 200 <= response.status_code < 300:
            return True, "Conexão e autenticação aceitas pelo endpoint de modelos. Nenhum prompt foi enviado."
        if response.status_code in {401, 403}:
            return False, "O serviço recusou a autenticação. Confira a chave e as permissões."
        if response.status_code == 404:
            return False, "O endpoint não oferece GET /models. Verifique a URL base; o provedor pode não expor esse recurso."
        if response.status_code == 429:
            return False, "O provedor limitou as solicitações durante o teste. Aguarde e tente mais tarde."
        if response.status_code >= 500:
            return False, f"O provedor retornou HTTP {response.status_code}; tente novamente mais tarde."
        return False, f"O endpoint recusou o teste (HTTP {response.status_code}). Verifique URL, modelo e configuração."
    except Exception:
        # Do not return exception text: it may contain endpoint metadata or headers from third-party clients.
        return False, "Não foi possível alcançar o endpoint. Confira a URL, a conexão e o certificado HTTPS."

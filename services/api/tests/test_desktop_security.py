from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_desktop_api_requires_process_token(monkeypatch) -> None:
    monkeypatch.setenv("YGGDRASIL_DESKTOP_MODE", "1")
    monkeypatch.setenv("YGGDRASIL_DESKTOP_TOKEN", "unit-test-token")
    with TestClient(app) as client:
        denied = client.get("/api/v1/not-a-route")
        allowed_through_guard = client.get(
            "/api/v1/not-a-route", headers={"X-Yggdrasil-Token": "unit-test-token"}
        )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "DESKTOP_TOKEN_REQUIRED"
    assert allowed_through_guard.status_code == 404


def test_desktop_bootstrap_is_not_cacheable(monkeypatch) -> None:
    monkeypatch.setenv("YGGDRASIL_DESKTOP_MODE", "1")
    monkeypatch.setenv("YGGDRASIL_DESKTOP_TOKEN", "another-unit-token")
    with TestClient(app) as client:
        response = client.get("/desktop-bootstrap.js")
    assert response.status_code == 200
    assert "another-unit-token" in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_bootstrap_is_hidden_outside_desktop_mode(monkeypatch) -> None:
    monkeypatch.delenv("YGGDRASIL_DESKTOP_MODE", raising=False)
    monkeypatch.delenv("YGGDRASIL_DESKTOP_TOKEN", raising=False)
    with TestClient(app) as client:
        response = client.get("/desktop-bootstrap.js")
    assert response.status_code == 404


def test_desktop_root_serves_web_app_and_bootstrap(tmp_path, monkeypatch) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text(
        '<!doctype html><html><head><title>desktop-test</title></head><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setenv("YGGDRASIL_DESKTOP_MODE", "1")
    monkeypatch.setenv("YGGDRASIL_DESKTOP_TOKEN", "root-test-token")
    monkeypatch.setenv("YGGDRASIL_WEB_ROOT", str(web))
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert '<script src="/desktop-bootstrap.js"></script>' in response.text
    assert 'id="root"' in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"

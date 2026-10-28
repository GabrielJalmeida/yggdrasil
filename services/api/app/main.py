"""FastAPI application factory and middleware."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings

app = FastAPI(
    title="Yggdrasil API",
    version=settings.app_version,
    description=(
        "Mapa estático de repositórios públicos, com grafo rastreável, análise sem execução, "
        "skills determinísticas, relatório Markdown e perguntas opcionais por IA com recuperação de evidências redigidas."
    ),
    contact={"name": "Yggdrasil"},
    license_info={"name": "MIT"},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Last-Event-ID", "X-Yggdrasil-Token"],
)


@app.middleware("http")
async def protect_desktop_api(request: Request, call_next):
    """Require a per-process random token for every desktop API request."""
    if os.getenv("YGGDRASIL_DESKTOP_MODE") == "1" and request.url.path.startswith("/api/"):
        expected = os.getenv("YGGDRASIL_DESKTOP_TOKEN", "")
        supplied = request.headers.get("x-yggdrasil-token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "DESKTOP_TOKEN_REQUIRED", "message": "A sessão local não foi autorizada."}},
                headers={"Cache-Control": "no-store"},
            )
    return await call_next(request)


app.include_router(router)

_desktop_web_root = Path(os.getenv("YGGDRASIL_WEB_ROOT", "")) if os.getenv("YGGDRASIL_DESKTOP_MODE") == "1" else None
if _desktop_web_root is not None and (_desktop_web_root / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(_desktop_web_root / "assets")), name="desktop-assets")


@app.get("/desktop-bootstrap.js", include_in_schema=False)
def desktop_bootstrap() -> Response:
    if os.getenv("YGGDRASIL_DESKTOP_MODE") != "1":
        raise HTTPException(status_code=404, detail="Not found")
    token = os.getenv("YGGDRASIL_DESKTOP_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="Sessão desktop indisponível")
    source = "window.__YGGDRASIL_API_TOKEN__ = " + json.dumps(token) + ";"
    return Response(
        content=source,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/", include_in_schema=False)
def root() -> Response:
    if os.getenv("YGGDRASIL_DESKTOP_MODE") == "1":
        web_root = Path(os.getenv("YGGDRASIL_WEB_ROOT", ""))
        index_file = web_root / "index.html"
        if index_file.is_file():
            html = index_file.read_text(encoding="utf-8")
            injection = '<script src="/desktop-bootstrap.js"></script>'
            if "</head>" in html and injection not in html:
                html = html.replace("</head>", f"{injection}</head>", 1)
            return HTMLResponse(
                html,
                headers={"Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"},
            )
        raise HTTPException(status_code=503, detail="Os arquivos da interface não estão disponíveis.")
    return JSONResponse(
        {
            "name": "Yggdrasil API",
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/api/v1/health",
            "ai_enabled": settings.ai_enabled,
            "ai_provider": settings.ai_provider if settings.ai_enabled else "disabled",
        }
    )


@app.post("/api/v1/desktop/shutdown", include_in_schema=False)
def desktop_shutdown() -> dict[str, str]:
    if os.getenv("YGGDRASIL_DESKTOP_MODE") != "1":
        raise HTTPException(status_code=404, detail="Not found")
    from app.desktop_runtime import request_shutdown

    if not request_shutdown():
        raise HTTPException(status_code=503, detail="O servidor não disponibilizou o encerramento controlado.")
    return {"status": "shutting_down"}

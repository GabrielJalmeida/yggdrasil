"""FastAPI application factory and middleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    allow_headers=["Content-Type", "Last-Event-ID"],
)
app.include_router(router)


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
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

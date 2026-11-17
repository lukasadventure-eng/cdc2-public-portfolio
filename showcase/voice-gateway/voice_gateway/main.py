# -*- coding: utf-8 -*-
"""Aplicação FastAPI do Voice Gateway."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.http import criar_router as criar_http
from .api.ws import criar_router as criar_ws
from .config import Config, DIRETORIO_WEB
from .core.gateway import VoiceGateway
from .security.auth import AuthManager


def criar_app(config: Config, token: str, diretorio_dados: Path | None = None) -> FastAPI:
    gateway = VoiceGateway(config, diretorio_dados=diretorio_dados)
    auth = AuthManager(token, config.seguranca.exigir_token)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        gateway.auditoria.registrar(
            "GATEWAY_INICIADO",
            agentes=",".join(gateway.adaptadores),
            stt=config.stt.provedor,
            tts=config.tts.provedor,
        )
        try:
            yield
        finally:
            await gateway.fechar()

    app = FastAPI(
        title="Voice Gateway",
        description="Infraestrutura de voz compartilhada para CDC e Salomão AI.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.gateway = gateway
    app.state.auth = auth
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.servidor.cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(criar_http(gateway, auth))
    app.include_router(criar_ws(gateway, auth))

    DIRETORIO_WEB.mkdir(parents=True, exist_ok=True)
    app.mount("/app", StaticFiles(directory=str(DIRETORIO_WEB)), name="app")

    @app.get("/", include_in_schema=False)
    async def raiz() -> FileResponse:
        return FileResponse(str(Path(DIRETORIO_WEB) / "index.html"))

    return app

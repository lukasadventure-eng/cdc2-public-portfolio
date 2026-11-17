# -*- coding: utf-8 -*-
"""STT local compatível com a API OpenAI de transcrições.

Serve para VoiceStudio (local API), whisper.cpp servidor HTTP,
faster-whisper-server etc. Nenhuma chave é necessária para serviços locais.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..audio.wav import pcm_para_wav
from .base import STTProvider


class LocalSTT(STTProvider):
    id = "local"
    nome = "Local / VoiceStudio (Whisper)"

    def descricao(self) -> str:
        return "Transcrição em serviço local compatível com /v1/audio/transcriptions."

    async def transcrever(self, audio: bytes, idioma: str | None = None) -> str:
        lingua = idioma or getattr(self.config, "idioma", "pt-BR")
        cabecalhos: dict[str, str] = {}
        chave = getattr(self.config, "chave_api", "")
        if chave:
            cabecalhos["Authorization"] = f"Bearer {chave}"
        async with httpx.AsyncClient(timeout=60.0) as cliente:
            resposta = await cliente.post(
                self.config.url_local,
                headers=cabecalhos,
                data={
                    "model": getattr(self.config, "modelo_local", "whisper-large-v3"),
                    "language": lingua.split("-")[0],
                },
                files={
                    "file": (
                        "audio.wav",
                        pcm_para_wav(audio, getattr(self.config, "sample_rate", 16_000)),
                        "audio/wav",
                    )
                },
            )
        resposta.raise_for_status()
        dados: Any = resposta.json()
        return str(dados.get("text", "")).strip()

# -*- coding: utf-8 -*-
"""TTS local compatível com /v1/audio/speech (VoiceStudio local API)."""

from __future__ import annotations

import httpx

from .base import AudioSintetizado, TTSProvider


class LocalTTS(TTSProvider):
    id = "local"
    nome = "Local / VoiceStudio"

    def descricao(self) -> str:
        return "Síntese em serviço local compatível com /v1/audio/speech."

    async def sintetizar(
        self,
        texto: str,
        voz: str = "",
        velocidade: float = 1.0,
        altura: float = 1.0,
    ) -> AudioSintetizado | None:
        cabecalhos: dict[str, str] = {}
        chave = getattr(self.config, "chave_api", "")
        if chave:
            cabecalhos["Authorization"] = f"Bearer {chave}"
        payload = {
            "model": getattr(self.config, "modelo_local", "omnivoice"),
            "input": texto,
            "voice": voz or getattr(self.config, "voz_salomao", "salomao-ptbr"),
            "response_format": "mp3",
            "speed": velocidade,
        }
        async with httpx.AsyncClient(timeout=120.0) as cliente:
            resposta = await cliente.post(
                self.config.url_local, headers=cabecalhos, json=payload
            )
        resposta.raise_for_status()
        return AudioSintetizado(
            dados=resposta.content,
            content_type=resposta.headers.get("content-type", "audio/mpeg"),
            formato="mp3",
        )

# -*- coding: utf-8 -*-
"""Auxiliar compartilhado para geração via Ollama local (streaming NDJSON)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List

import httpx

from ..models import agora_iso


async def gerar_stream(
    url_base: str,
    modelo: str,
    system: str,
    mensagens: List[Dict[str, str]],
    cancelamento: asyncio.Event,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    """Transmite tokens de /api/chat. Nenhum proxy/redirecionamento é seguido."""
    payload: Dict[str, Any] = {
        "model": modelo,
        "stream": True,
        "messages": [{"role": "system", "content": system}] + list(mensagens),
        "options": {"temperature": temperature},
    }
    cliente = httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False)
    try:
        async with cliente.stream(
            "POST", url_base.rstrip("/") + "/api/chat", json=payload
        ) as resposta:
            resposta.raise_for_status()
            async for linha in resposta.aiter_lines():
                if cancelamento.is_set():
                    return
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    objeto = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if objeto.get("error"):
                    raise RuntimeError(str(objeto["error"])[:200])
                token = (objeto.get("message") or {}).get("content", "")
                if token:
                    yield str(token)
                if objeto.get("done"):
                    return
    finally:
        await cliente.aclose()


async def gerar_texto(
    url_base: str,
    modelo: str,
    system: str,
    mensagens: List[Dict[str, str]],
    cancelamento: asyncio.Event | None = None,
    temperature: float = 0.7,
) -> str:
    cancelamento = cancelamento or asyncio.Event()
    partes: List[str] = []
    async for token in gerar_stream(
        url_base, modelo, system, mensagens, cancelamento, temperature
    ):
        partes.append(token)
    return "".join(partes).strip()


async def verificar(url_base: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            timeout=3.0, follow_redirects=False, trust_env=False
        ) as cliente:
            resposta = await cliente.get(url_base.rstrip("/") + "/api/tags")
        if resposta.status_code == 200:
            modelos = [m.get("name", "") for m in resposta.json().get("models", [])]
            return {"disponivel": True, "modelos": modelos[:12], "verificado_em": agora_iso()}
    except Exception as erro:  # noqa: BLE001 — status não deve derrubar o gateway
        return {"disponivel": False, "erro": type(erro).__name__}
    return {"disponivel": False}

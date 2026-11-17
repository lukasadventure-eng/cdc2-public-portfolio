# -*- coding: utf-8 -*-
"""Teste de fumaça contra um servidor em execução (Ollama local necessário).

Uso:
    python -m voice_gateway.run --token token-de-teste        # terminal 1
    python -m voice_gateway.tests.smoke_real                  # terminal 2
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import websockets

TOKEN = os.environ.get("VOICE_GATEWAY_TOKEN", "token-de-teste")
URL = os.environ.get("VOICE_GATEWAY_WS", "ws://127.0.0.1:8765/ws/voice")


async def aguardar(ws, tipos, timeout=120):
    eventos = []
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        eventos.append(msg)
        if msg.get("type") in tipos:
            return msg, eventos
    raise TimeoutError(f"Eventos {tipos} não recebidos")


async def main() -> int:
    uri = f"{URL}?token={TOKEN}"
    async with websockets.connect(uri, open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "hello", "agente": "salomao"}))
        pronto, _ = await aguardar(ws, {"ready"}, 10)
        print(f"[ok] ready — agente={pronto['agente']} "
              f"stt={pronto['stt']['id']} tts={pronto['tts']['id']}")

        await ws.send(json.dumps({
            "type": "text_input",
            "texto": "Em uma frase curta, diga quem você é.",
        }))
        resposta, _ = await aguardar(ws, {"answer", "erro"}, 120)
        if resposta["type"] == "erro":
            print(f"[falha] Salomão AI: {resposta['mensagem']}")
            return 1
        print(f"[ok] Salomão AI: {resposta['texto'][:160]}")

        await ws.send(json.dumps({"type": "set_agent", "agente": "cdc"}))
        await aguardar(ws, {"routing"}, 10)
        await ws.send(json.dumps({
            "type": "text_input",
            "texto": "Qual é o modo de operação do CDC?",
        }))
        resposta, _ = await aguardar(ws, {"answer", "erro"}, 30)
        if resposta["type"] == "erro":
            print(f"[falha] CDC: {resposta['mensagem']}")
            return 1
        print(f"[ok] CDC: {resposta['texto'][:160]}")

        await ws.send(json.dumps({"type": "set_agent", "agente": "salomao"}))
        await aguardar(ws, {"routing"}, 10)
        await ws.send(json.dumps({
            "type": "text_input",
            "texto": "Conte uma história longa sobre inteligência artificial e privacidade, com muitos detalhes.",
        }))
        await aguardar(ws, {"token"}, 120)
        await ws.send(json.dumps({"type": "barge_in"}))
        interrompido, _ = await aguardar(ws, {"interrompido"}, 10)
        print(f"[ok] barge-in: agente={interrompido.get('agente')}")

    print("[ok] fumaça concluída")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except (websockets.exceptions.WebSocketException, OSError, TimeoutError) as erro:
        print(f"[falha] {type(erro).__name__}: {erro}", file=sys.stderr)
        raise SystemExit(1)

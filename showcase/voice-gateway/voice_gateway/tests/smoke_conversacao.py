# -*- coding: utf-8 -*-
"""Fumaça real de conversação contínua e interrupção via WebSocket.

Requer gateway rodando e Ollama local. As falas são enviadas como texto
(fluxo de áudio real é exercitado por smoke_operacional + interface).

    python -m voice_gateway.tests.smoke_conversacao
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
import websockets

TOKEN = os.environ.get("VOICE_GATEWAY_TOKEN", "token-de-teste")
BASE = os.environ.get("VOICE_GATEWAY_BASE", "http://127.0.0.1:8765")
WS = BASE.replace("http", "ws") + "/ws/voice"


async def coletar(ws, tipos, timeout=90):
    eventos = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        eventos.append(m)
        if m.get("type") in tipos:
            return m, eventos
    raise TimeoutError(f"Sem eventos {tipos}")


async def main() -> int:
    headers = {"Authorization": "Bearer " + TOKEN}
    async with httpx.AsyncClient(base_url=BASE) as http:
        async with websockets.connect(f"{WS}?token={TOKEN}", open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "hello", "agente": "salomao"}))
            pronto, _ = await coletar(ws, {"ready"}, 10)
            sessao = pronto["sessao"]
            print(f"[info] sessão real {sessao[:12]} — agente {pronto['agente']}")

            respostas = 0
            transcripts = 0
            erros = 0
            for indice in range(10):
                await ws.send(json.dumps({
                    "type": "text_input",
                    "texto": f"Responda em poucas palavras: número {indice + 1}?",
                }))
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
                    if m["type"] == "answer":
                        respostas += 1
                        break
                    if m["type"] == "transcript" and m.get("final"):
                        transcripts += 1
                    if m["type"] == "erro":
                        erros += 1
                        print(f"[falha]turno {indice+1}: {m['mensagem']}")
                        break
                else:
                    print(f"[falha] turno {indice + 1} sem resposta")
                    return 1

            print(f"[ok] respostas={respostas} transcripts={transcripts} erros={erros}")
            if respostas != 10 or erros:
                return 1

            historico = (await http.get(
                f"/api/sessoes/{sessao}", headers=headers
            )).json()
            if len(historico["mensagens"]) < 20:
                print(f"[falha] histórico com {len(historico['mensagens'])} mensagens")
                return 1
            print(f"[ok] histórico persistido: {len(historico['mensagens'])} mensagens")

            # Interrupção real: aguarda tokens, interrompe e mede.
            for tentativa in range(3):
                await ws.send(json.dumps({
                    "type": "text_input",
                    "texto": (
                        "Conte uma história longa e detalhada sobre o oceano, "
                        "com muitos parágrafos."
                    ),
                }))
                _, eventos = await coletar(ws, {"token"}, 90)
                inicio = time.monotonic()
                await ws.send(json.dumps({
                    "type": "barge_in", "deteccao_ms": 0,
                }))
                _, evt = await coletar(ws, {"interrompido"}, 10)
                total = (time.monotonic() - inicio) * 1000
                await ws.send(json.dumps({
                    "type": "metricas_interrupcao",
                    "deteccao_ms": 0.5,
                    "total_ms": total,
                }))
                print(f"[ok] interrupção {tentativa + 1}: total {total:.1f} ms")

            metricas = (await http.get("/api/metricas", headers=headers)).json()
            print(f"[ok] métricas: {metricas['resumo']['total_amostras']} amostras")
    print("[ok] fumaça de continuidade concluída")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as erro:  # noqa: BLE001
        print(f"[falha] {type(erro).__name__}: {erro}", file=sys.stderr)
        raise SystemExit(1)

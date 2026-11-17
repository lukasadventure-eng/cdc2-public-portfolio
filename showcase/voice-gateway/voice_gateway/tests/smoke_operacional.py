# -*- coding: utf-8 -*-
"""Fumaça real da operação por voz: Salomão → OpenCode → resultado falado.

Requer gateway rodando, OpenCode no PATH e Ollama local.

    python -m voice_gateway.run --token token-de-teste
    python -m voice_gateway.tests.smoke_operacional
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
import websockets

TOKEN = os.environ.get("VOICE_GATEWAY_TOKEN", "token-de-teste")
BASE = os.environ.get("VOICE_GATEWAY_BASE", "http://127.0.0.1:8765")
WS = BASE.replace("http", "ws") + "/ws/voice"


async def receber(ws, tipos, timeout=180):
    eventos = []
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        eventos.append(msg)
        if msg.get("type") in tipos:
            return msg, eventos
    raise TimeoutError(f"Eventos {tipos} não recebidos")


async def main() -> int:
    headers = {"Authorization": "Bearer " + TOKEN}
    async with httpx.AsyncClient(base_url=BASE) as http:
        status = (await http.get("/api/operacoes/status", headers=headers)).json()
        oc = status["agentes"]["opencode"]
        print(f"[info] OpenCode disponível={oc['disponivel']} versão={oc['versao']} auto={oc['auto_aprovacao']}")
        if not oc["disponivel"]:
            print("[falha] OpenCode indisponível — nenhuma execução será simulada.")
            return 1
        if oc["auto_aprovacao"]:
            print("[falha] Auto aprovação ativada — inaceitável.")
            return 1

        async with websockets.connect(f"{WS}?token={TOKEN}", open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "hello", "agente": "salomao"}))
            pronto, _ = await receber(ws, {"ready"}, 10)
            sessao = pronto["sessao"]
            print(f"[ok] sessão {sessao[:12]}")

            await ws.send(json.dumps({
                "type": "text_input",
                # Conhecimento geral: não usa ferramentas e não cria arquivos.
                "texto": (
                    "Salomão, peça ao OpenCode para responder apenas o nome "
                    "da capital do Brasil, sem usar ferramentas."
                ),
            }))
            tipos = []
            tarefa_id = ""
            deadline = asyncio.get_event_loop().time() + 180
            while asyncio.get_event_loop().time() < deadline:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                if m["type"] == "comando_reconhecido":
                    tipos.append(m["comando"])
                if m["type"] == "operacional":
                    tipos.append(m["tipo_evento"])
                    tarefa_id = m["tarefa"]
                    if m["tipo_evento"] in ("tarefa_concluida", "tarefa_falha"):
                        break
                if m["type"] == "erro":
                    print(f"[falha] {m['mensagem']}")
                    return 1
            print(f"[ok] eventos: {', '.join(dict.fromkeys(tipos))}")

            tarefa = (await http.get(
                f"/api/tarefas/{tarefa_id}", headers=headers
            )).json()
            print(f"[ok] tarefa {tarefa['estado']} — {tarefa['resultado'][:120]}")
            if tarefa["estado"] != "concluida":
                print(f"[falha] erro: {tarefa['erro'][:200]}")
                return 1

            await ws.send(json.dumps({"type": "text_input", "texto": "Leia o último resultado"}))
            resposta, _ = await receber(ws, {"answer"}, 60)
            print(f"[ok] leitura: {resposta['texto'][:120]}")

            await ws.send(json.dumps({"type": "text_input", "texto": "Qual agente está trabalhando?"}))
            resposta, _ = await receber(ws, {"answer"}, 60)
            print(f"[ok] consulta: {resposta['texto'][:120]}")

    print("[ok] fumaça operacional concluída")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as erro:  # noqa: BLE001 — diagnóstico de fumaça
        print(f"[falha] {type(erro).__name__}: {erro}", file=sys.stderr)
        raise SystemExit(1)

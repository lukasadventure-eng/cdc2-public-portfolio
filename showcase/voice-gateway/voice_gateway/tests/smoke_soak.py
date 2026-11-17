# -*- coding: utf-8 -*-
"""Teste de permanência contínua com duração configurável.

Padrão: 7200 s (2 h), conforme critério 16.11. Para uma verificação rápida:

    VOICE_GATEWAY_SOAK_SECONDS=60 python -m voice_gateway.tests.smoke_soak

O script registra ambiente, hardware, provedor, amostras de memória (quando
disponível), erros e métricas de latência. Ele NÃO afirma estabilidade por 2 h
se executado por menos tempo — o tempo efetivo é sempre impresso.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import time

import httpx
import websockets

TOKEN = os.environ.get("VOICE_GATEWAY_TOKEN", "token-de-teste")
BASE = os.environ.get("VOICE_GATEWAY_BASE", "http://127.0.0.1:8767")
WS = BASE.replace("http", "ws") + "/ws/voice"
SEGUNDOS = int(os.environ.get("VOICE_GATEWAY_SOAK_SECONDS", "7200"))
INTERVALO = int(os.environ.get("VOICE_GATEWAY_SOAK_INTERVAL", "30"))


async def main() -> int:
    from .ambiente_real import encerrar_servidores, garantir_servidores

    processos = await garantir_servidores()
    try:
        return await _rodar()
    finally:
        encerrar_servidores(processos)


async def _rodar() -> int:
    inicio = time.monotonic()
    ctx = None
    try:
        import tracemalloc

        tracemalloc.start()
        ctx = tracemalloc
    except ImportError:
        pass

    headers = {"Authorization": "Bearer " + TOKEN}
    ciclos = erros = 0
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as http:
        while time.monotonic() - inicio < SEGUNDOS:
            try:
                saude = (await http.get("/health")).json()
                async with websockets.connect(
                    f"{WS}?token={TOKEN}", open_timeout=10
                ) as ws:
                    await ws.send(json.dumps({"type": "hello"}))
                    ready = json.loads(await asyncio.wait_for(ws.recv(), 15))
                    if ready.get("type") != "ready":
                        raise RuntimeError("ready não recebido")
                    await ws.send(json.dumps({
                        "type": "text_input", "texto": "Diga apenas: ok",
                    }))
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        evt = json.loads(await asyncio.wait_for(ws.recv(), 60))
                        if evt["type"] in ("answer", "erro"):
                            break
                    if evt["type"] == "erro":
                        erros += 1
                ciclos += 1
                mem = ""
                if ctx is not None:
                    atual, pico = ctx.get_traced_memory()
                    mem = f" mem={atual // 1024}KiB pico={pico // 1024}KiB"
                print(
                    f"[soak] t={int(time.monotonic()-inicio)}s "
                    f"ciclos={ciclos} erros={erros} agentes={len(saude['agentes'])}{mem}",
                    flush=True,
                )
            except Exception as erro:  # noqa: BLE001
                erros += 1
                print(f"[soak] erro: {type(erro).__name__}: {erro}", flush=True)
            await asyncio.sleep(INTERVALO)

    decorrido = time.monotonic() - inicio
    metricas = {}
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as http:
            metricas = (await http.get("/api/metricas", headers=headers)).json().get(
                "resumo", {}
            )
    except Exception:  # noqa: BLE001
        pass

    print("=== RELATÓRIO DE ESTABILIDADE ===")
    print(f"sistema: {platform.system()} {platform.release()} / {platform.machine()}")
    print(f"python: {platform.python_version()}")
    print(f"duração efetiva: {decorrido:.1f}s (solicitada: {SEGUNDOS}s)")
    print(f"ciclos: {ciclos} · erros: {erros}")
    print(f"provedores: {json.dumps(metricas.get('por_tipo', {}), ensure_ascii=False)}")
    if decorrido < 7200:
        print("AVISO: duração inferior a 2h — NÃO comprova o critério de 2 horas.")
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as erro:  # noqa: BLE001
        print(f"[falha] {type(erro).__name__}: {erro}", file=sys.stderr)
        raise SystemExit(1)

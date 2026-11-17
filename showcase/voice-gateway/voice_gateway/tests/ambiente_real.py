# -*- coding: utf-8 -*-
"""Inicialização assistida dos servidores para testes reais.

Evita depender de processos destacados pelo shell, que podem ser encerrados
pelo ambiente. Uso:

    from .ambiente_real import garantir_servidores
    processos = await garantir_servidores()
    ... testes ...
    encerrar_servidores(processos)
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import List

import httpx

RAIZ = Path(__file__).resolve().parents[2]
PORTA_GATEWAY = 8767
PORTA_STT = 8010


async def _saudavel(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as cliente:
            return (await cliente.get(url)).status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def garantir_servidores() -> List[subprocess.Popen]:
    iniciados: List[subprocess.Popen] = []
    if not await _saudavel(f"http://127.0.0.1:{PORTA_STT}/health"):
        iniciados.append(
            subprocess.Popen(
                [sys.executable, "-m", "voice_gateway.stt.servidor_local",
                 "--port", str(PORTA_STT)],
                cwd=str(RAIZ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        for _ in range(40):
            if await _saudavel(f"http://127.0.0.1:{PORTA_STT}/health"):
                break
            await asyncio.sleep(1)
    if not await _saudavel(f"http://127.0.0.1:{PORTA_GATEWAY}/health"):
        iniciados.append(
            subprocess.Popen(
                [sys.executable, "-m", "voice_gateway.run", "--token",
                 "token-de-teste", "--port", str(PORTA_GATEWAY)],
                cwd=str(RAIZ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        for _ in range(30):
            if await _saudavel(f"http://127.0.0.1:{PORTA_GATEWAY}/health"):
                break
            await asyncio.sleep(1)
    return iniciados


def encerrar_servidores(processos: List[subprocess.Popen]) -> None:
    for processo in processos:
        try:
            processo.terminate()
            processo.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                processo.kill()
            except Exception:  # noqa: BLE001
                pass

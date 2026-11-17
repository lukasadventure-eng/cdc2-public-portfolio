# -*- coding: utf-8 -*-
"""Comandos simples de operação da Voice Gateway.

    python -m voice_gateway.operar iniciar
    python -m voice_gateway.operar status
    python -m voice_gateway.operar teste
    python -m voice_gateway.operar parar

Inicia o STT local (faster-whisper) e o gateway, registra PIDs em
``voice_gateway/data/pids.json`` e permite encerrar ambos com um comando.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .config import DIRETORIO_DADOS

PORTA_STT = 8010
PORTA_GATEWAY = 8765
ARQUIVO_PIDS = DIRETORIO_DADOS / "pids.json"


def _saudavel(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def iniciar() -> int:
    DIRETORIO_DADOS.mkdir(parents=True, exist_ok=True)
    pids: dict[str, int] = {}
    sinais = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    if not _saudavel(f"http://127.0.0.1:{PORTA_STT}/health"):
        log = (DIRETORIO_DADOS / "stt.log").open("ab")
        p = subprocess.Popen(
            [sys.executable, "-m", "voice_gateway.stt.servidor_local",
             "--port", str(PORTA_STT)],
            stdout=log, stderr=subprocess.STDOUT, creationflags=sinais,
        )
        pids["stt"] = p.pid
    if not _saudavel(f"http://127.0.0.1:{PORTA_GATEWAY}/health"):
        log = (DIRETORIO_DADOS / "gateway.log").open("ab")
        p = subprocess.Popen(
            [sys.executable, "-m", "voice_gateway.run",
             "--port", str(PORTA_GATEWAY)],
            stdout=log, stderr=subprocess.STDOUT, creationflags=sinais,
        )
        pids["gateway"] = p.pid
    ARQUIVO_PIDS.write_text(json.dumps(pids, indent=2), encoding="utf-8")

    for nome, url in (
        ("STT", f"http://127.0.0.1:{PORTA_STT}/health"),
        ("Gateway", f"http://127.0.0.1:{PORTA_GATEWAY}/health"),
    ):
        for _ in range(60):
            if _saudavel(url):
                print(f"[ok] {nome} pronto: {url}")
                break
            time.sleep(1)
        else:
            print(f"[falha] {nome} não iniciou — veja data/{nome.lower()}.log")
            return 1
    print("Abra http://127.0.0.1:8765 e informe o token exibido em data/gateway.log")
    return 0


def parar() -> int:
    if not ARQUIVO_PIDS.exists():
        print("Nenhum PID registrado.")
        return 0
    pids = json.loads(ARQUIVO_PIDS.read_text(encoding="utf-8"))
    for nome, pid in pids.items():
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, check=False)
            print(f"[ok] {nome} encerrado ({pid})")
        except Exception as erro:  # noqa: BLE001
            print(f"[aviso] {nome}: {erro}")
    ARQUIVO_PIDS.unlink(missing_ok=True)
    return 0


def status() -> int:
    for nome, url in (
        ("STT local", f"http://127.0.0.1:{PORTA_STT}/health"),
        ("Gateway", f"http://127.0.0.1:{PORTA_GATEWAY}/health"),
    ):
        try:
            resposta = httpx.get(url, timeout=3)
            print(f"[ok] {nome}: {resposta.text[:160]}")
        except Exception:  # noqa: BLE001
            print(f"[indisponível] {nome}")
    return 0


def teste() -> int:
    return subprocess.call(
        [sys.executable, "-m", "voice_gateway.tests.run_all"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Operação da Voice Gateway")
    parser.add_argument("comando", choices=["iniciar", "parar", "status", "teste"])
    args = parser.parse_args()
    return {
        "iniciar": iniciar,
        "parar": parar,
        "status": status,
        "teste": teste,
    }[args.comando]()


if __name__ == "__main__":
    raise SystemExit(main())

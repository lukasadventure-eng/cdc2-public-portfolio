# -*- coding: utf-8 -*-
"""Validação real de verificação de falante local (ECAPA-TDNN).

Amostras sintéticas geradas por vozes pt-BR/en-US do Windows são usadas como
titulares de teste. Nenhuma biometria é usada para autorizar operações.
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys

import httpx

from .ambiente_real import encerrar_servidores, garantir_servidores

TOKEN = os.environ.get("VOICE_GATEWAY_TOKEN", "token-de-teste")
BASE = "http://127.0.0.1:8766"
TEMP = os.environ.get("TEMP", "")


async def main() -> int:
    processos = await garantir_servidores()
    try:
        return await _rodar()
    finally:
        encerrar_servidores(processos)


async def _rodar() -> int:
    maria = os.path.join(TEMP, "opencode", "salomao.wav")
    zira = os.path.join(TEMP, "opencode", "salomao_zira.wav")
    if not (os.path.exists(maria) and os.path.exists(zira)):
        print("[falha] WAVs de teste ausentes", file=sys.stderr)
        return 1

    headers = {"Authorization": "Bearer " + TOKEN}
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as http:
        estado = (await http.get("/api/falantes", headers=headers)).json()["estado"]
        print("[info] identificador:", estado["identificador"],
              "disponível:", estado["disponivel"])
        if not estado["disponivel"]:
            print("[falha] identificador indisponível")
            return 1

        perfil = (await http.post(
            "/api/falantes", headers=headers,
            json={"nome": "Titular A", "consentimento": True},
        )).json()
        amostra_maria = base64.b64encode(open(maria, "rb").read()).decode()
        amostra_zira = base64.b64encode(open(zira, "rb").read()).decode()

        r = await http.post(
            "/api/falantes/amostra", headers=headers,
            json={"perfil_id": perfil["id"], "dados": amostra_maria},
        )
        print("[info] amostra registrada:", r.json())
        if r.status_code != 200:
            return 1

        r = await http.post(
            "/api/falantes/identificar", headers=headers,
            json={"dados": amostra_maria},
        )
        identificado = r.json()
        print("[info] titular A →", identificado["perfil"]["nome"] if identificado["perfil"] else None)
        if not identificado["perfil"] or identificado["perfil"]["id"] != perfil["id"]:
            print("[falha] falha ao identificar titular cadastrado")
            return 1

        r = await http.post(
            "/api/falantes/identificar", headers=headers,
            json={"dados": amostra_zira},
        )
        outro = r.json()
        print("[info] titular B →", outro["perfil"]["nome"] if outro["perfil"] else "não identificado")
        if outro["perfil"] is not None:
            print("[falha] falso positivo entre falantes")
            return 1

        r = await http.delete(
            f"/api/falantes/{perfil['id']}", headers=headers
        )
        print("[ok] perfil excluído:", r.json()["removido"])
    print("[ok] fumaça de falante real concluída")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as erro:  # noqa: BLE001
        print(f"[falha] {type(erro).__name__}: {erro}", file=sys.stderr)
        raise SystemExit(1)

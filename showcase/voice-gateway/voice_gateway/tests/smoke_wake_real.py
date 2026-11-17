# -*- coding: utf-8 -*-
"""Validação real da ativação por “Salomão” com STT local.

O áudio de teste é gerado pela voz pt-BR do Windows (Microsoft Maria) em WAV,
reamostrado para 16 kHz e enviado ao gateway como PCM16 — o mesmo formato que
o navegador envia quando captura o microfone. Não há transcrição simulada.

Limitação honesta: o áudio é sintético e injetado via WebSocket, não capturado
por um microfone físico. Para validar o microfone, basta falar “Salomão” com a
interface aberta e o wake ativado.

Requer: STT local em 127.0.0.1:8010 e gateway em 8765/8766.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time
import wave

import httpx
import numpy as np
import websockets

TOKEN = os.environ.get("VOICE_GATEWAY_TOKEN", "token-de-teste")
BASE = os.environ.get("VOICE_GATEWAY_BASE", "http://127.0.0.1:8765")
WS = BASE.replace("http", "ws") + "/ws/voice"
WAV = os.environ.get(
    "VG_TESTE_WAV",
    os.path.join(os.environ.get("TEMP", ""), "opencode", "salomao.wav"),
)


def carregar_pcm16(path: str) -> bytes:
    with wave.open(path, "rb") as wav:
        taxa = wav.getframerate()
        dados = np.frombuffer(
            wav.readframes(wav.getnframes()), dtype="<i2"
        ).astype(np.float32) / 32768.0
    if taxa != 16000:
        indice = np.linspace(0, len(dados) - 1, int(len(dados) * 16000 / taxa))
        dados = np.interp(indice, np.arange(len(dados)), dados)
    return (np.clip(dados, -1, 1) * 32767).astype("<i2").tobytes()


async def main() -> int:
    from .ambiente_real import encerrar_servidores, garantir_servidores

    processos = await garantir_servidores()
    try:
        return await _rodar()
    finally:
        encerrar_servidores(processos)


async def _rodar() -> int:
    if not os.path.exists(WAV):
        print(f"[falha] WAV de teste ausente: {WAV}", file=sys.stderr)
        return 1
    pcm = carregar_pcm16(WAV)
    print(f"[info] áudio: {os.path.basename(WAV)} → {len(pcm)} bytes PCM16@16k")

    async with httpx.AsyncClient(base_url=BASE) as http:
        saude_stt = await http.get("http://127.0.0.1:8010/health", timeout=10)
        print("[info] STT local:", saude_stt.json())

        async with websockets.connect(
            f"{WS}?token={TOKEN}", open_timeout=10
        ) as ws:
            await ws.send(json.dumps({"type": "hello"}))
            pronto = json.loads(await asyncio.wait_for(ws.recv(), 15))
            wake = pronto.get("wake", {})
            print("[info] wake:", wake)
            if not wake.get("pode_ativar"):
                print("[falha] gateway não habilitou wake com STT local")
                return 1

            inicio = time.monotonic()
            await ws.send(json.dumps({
                "type": "wake_audio",
                "dados": base64.b64encode(pcm).decode("ascii"),
            }))
            while True:
                evt = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if evt["type"] == "wake_detected":
                    print(
                        f"[ok] ativação detectada: {evt['palavra']} "
                        f"em {(time.monotonic()-inicio)*1000:.0f} ms"
                    )
                    break
                if evt["type"] == "wake_aguardando":
                    print(f"[info] transcrição local: {evt.get('texto')}")
                if evt["type"] == "erro":
                    print(f"[falha] {evt['mensagem']}")
                    return 1

            # Segunda ativação com modelo já aquecido.
            await asyncio.sleep(3.0)
            inicio2 = time.monotonic()
            await ws.send(json.dumps({
                "type": "wake_audio",
                "dados": base64.b64encode(pcm).decode("ascii"),
            }))
            while True:
                evt = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if evt["type"] == "wake_detected":
                    print(
                        f"[ok] 2ª ativação: {(time.monotonic()-inicio2)*1000:.0f} ms"
                    )
                    break
                if evt["type"] == "erro":
                    print(f"[falha] {evt['mensagem']}")
                    return 1

            # Conversa real após a ativação.
            await ws.send(json.dumps({
                "type": "text_input", "texto": "Diga apenas: ativado",
            }))
            while True:
                evt = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if evt["type"] == "answer":
                    print(f"[ok] SALOMÃO: {evt['texto'][:140]}")
                    break
    print("[ok] fumaça de wake real concluída")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as erro:  # noqa: BLE001
        print(f"[falha] {type(erro).__name__}: {erro}", file=sys.stderr)
        raise SystemExit(1)

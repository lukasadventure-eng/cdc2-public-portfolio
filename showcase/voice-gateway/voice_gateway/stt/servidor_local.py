# -*- coding: utf-8 -*-
"""Servidor STT local compatível com /v1/audio/transcriptions.

Usa faster-whisper (CTranslate2) com modelo baixado do HuggingFace na primeira
execução. Todo o áudio é processado nesta máquina — nenhum envio a serviço
externo de transcrição.

Execução:
    python -m voice_gateway.stt.servidor_local --port 8010
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import shutil
import threading
import wave

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger("voice_gateway.stt_local")


class TranscritorLocal:
    """Carrega o modelo sob demanda e protege o acesso com trava."""

    def __init__(self) -> None:
        self._modelo = None
        self._trava = threading.Lock()
        self._erro_carga = ""
        self.modelo_nome = os.environ.get(
            "VG_STT_MODEL", "small"
        )
        self.dispositivo = os.environ.get("VG_STT_DEVICE", "auto")

    def _carregar(self):
        if self._modelo is not None:
            return self._modelo
        with self._trava:
            if self._modelo is not None:
                return self._modelo
            from faster_whisper import WhisperModel

            dispositivo = self.dispositivo
            if dispositivo == "auto":
                # torch não é dependência do gateway; nvidia-smi indica GPU.
                dispositivo = (
                    "cuda"
                    if shutil.which("nvidia-smi") or self._cuda_disponivel()
                    else "cpu"
                )
            tipo = "float16" if dispositivo == "cuda" else "int8"
            logger.info(
                "Carregando faster-whisper modelo=%s device=%s compute=%s",
                self.modelo_nome,
                dispositivo,
                tipo,
            )
            try:
                self._modelo = WhisperModel(
                    self.modelo_nome, device=dispositivo, compute_type=tipo
                )
            except Exception as erro:  # noqa: BLE001
                logger.warning("Falha GPU, tentando CPU: %s", erro)
                self._modelo = WhisperModel(
                    self.modelo_nome, device="cpu", compute_type="int8"
                )
                dispositivo = "cpu"
            self.dispositivo_efetivo = dispositivo
            return self._modelo

    @staticmethod
    def _cuda_disponivel() -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _decodificar_wav(dados: bytes) -> np.ndarray:
        # Se os dados não começam com RIFF (WAV), assumir PCM16 raw @ 16kHz mono
        if not dados.startswith(b"RIFF"):
            # PCM16 raw, 16kHz, mono
            amostras = np.frombuffer(dados, dtype="<i2").astype(np.float32) / 32768.0
            return amostras
        with wave.open(io.BytesIO(dados), "rb") as arquivo:
            canais = arquivo.getnchannels()
            largura = arquivo.getsampwidth()
            taxa = arquivo.getframerate()
            bruto = arquivo.readframes(arquivo.getnframes())
        if largura != 2:
            raise ValueError("Áudio PCM16 obrigatório.")
        amostras = np.frombuffer(bruto, dtype="<i2").astype(np.float32) / 32768.0
        if canais > 1:
            amostras = amostras.reshape(-1, canais).mean(axis=1)
        if taxa != 16000:
            # Reamostragem linear simples (suficiente para faixa de voz).
            indice = np.linspace(0, len(amostras) - 1, int(len(amostras) * 16000 / taxa))
            amostras = np.interp(indice, np.arange(len(amostras)), amostras).astype(
                np.float32
            )
        return amostras

    def _transcrever_com(self, modelo, amostras, idioma: str) -> str:
        segmentos, _ = modelo.transcribe(
            amostras,
            language=idioma.split("-")[0] if idioma else "pt",
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segmentos if s.text.strip()).strip()

    def transcrever(self, audio: bytes, idioma: str = "pt") -> str:
        modelo = self._carregar()
        amostras = self._decodificar_wav(audio)
        try:
            return self._transcrever_com(modelo, amostras, idioma)
        except RuntimeError as erro:
            mensagem = str(erro).lower()
            if "cublas" not in mensagem and "cuda" not in mensagem:
                raise
            logger.warning("CUDA indisponível em runtime; migrando para CPU")
            with self._trava:
                from faster_whisper import WhisperModel

                self._modelo = WhisperModel(
                    self.modelo_nome, device="cpu", compute_type="int8"
                )
                self.dispositivo_efetivo = "cpu"
                modelo = self._modelo
            return self._transcrever_com(modelo, amostras, idioma)


def criar_app() -> FastAPI:
    transcritor = TranscritorLocal()
    app = FastAPI(title="Voice Gateway STT local", version="1.0")

    @app.on_event("startup")
    async def aquecer_modelo() -> None:
        """Carrega o modelo em segundo plano para não penalizar a 1ª ativação."""
        if os.environ.get("VG_STT_WARMUP", "1").lower() in {"1", "true", "sim"}:
            import asyncio

            asyncio.create_task(asyncio.to_thread(transcritor._carregar))

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "modelo": transcritor.modelo_nome,
            "carregado": transcritor._modelo is not None,
            "dispositivo": getattr(transcritor, "dispositivo_efetivo", transcritor.dispositivo),
        }

    @app.post("/v1/audio/transcriptions")
    async def transcrever(
        file: UploadFile = File(...),
        model: str = Form("small"),
        language: str = Form("pt"),
    ):
        dados = await file.read()
        if not dados:
            return JSONResponse({"text": ""})
        try:
            texto = transcritor.transcrever(dados, language)
        except Exception as erro:  # noqa: BLE001
            logger.exception("Falha na transcrição local")
            return JSONResponse(
                {"text": "", "erro": f"{type(erro).__name__}: {erro}"},
                status_code=500,
            )
        return {"text": texto}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="STT local (faster-whisper)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(criar_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

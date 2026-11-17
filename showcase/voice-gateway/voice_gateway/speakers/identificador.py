# -*- coding: utf-8 -*-
"""Identificador de falante local baseado em ECAPA-TDNN (SpeechBrain).

Modelo: ``speechbrain/spkrec-ecapa-voxceleb`` (Apache 2.0), executado nesta
máquina. Nenhuma amostra de áudio é enviada a serviço externo.

Uso: exige amostras fornecidas e autorizadas pelo titular do perfil.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import wave
from typing import List

import numpy as np

from .servico import IdentificadorFalante

logger = logging.getLogger("voice_gateway.speaker")


class IdentificadorSpeechBrain(IdentificadorFalante):
    nome = "speechbrain-ecapa"
    disponivel = True

    def __init__(self, limiar: float = 0.75) -> None:
        self.limiar = float(limiar)
        self._modelo = None
        self._trava = threading.Lock()
        self._embeddings: dict[str, List[float]] = {}

    def _carregar(self):
        if self._modelo is not None:
            return self._modelo
        with self._trava:
            if self._modelo is not None:
                return self._modelo
            from speechbrain.inference.speaker import EncoderClassifier

            logger.info("Carregando ECAPA-TDNN local")
            self._modelo = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb"
            )
            return self._modelo

    @staticmethod
    def _carregar_wav(dados: bytes):
        import torch

        with wave.open(io.BytesIO(dados), "rb") as arquivo:
            taxa = arquivo.getframerate()
            bruto = arquivo.readframes(arquivo.getnframes())
        amostras = np.frombuffer(bruto, dtype="<i2").astype(np.float32) / 32768.0
        tensor = torch.tensor(amostras).unsqueeze(0)
        if taxa != 16000:
            import torchaudio.functional as F

            tensor = F.resample(tensor, taxa, 16000)
        return tensor

    def embedding(self, amostra: bytes) -> List[float]:
        modelo = self._carregar()
        sinal = self._carregar_wav(amostra)
        with self._trava:
            vetor = modelo.encode_batch(sinal).squeeze().detach().cpu().numpy()
        return [float(v) for v in np.asarray(vetor).flatten()]

    def cadastrar(self, perfil_id: str, amostra: bytes) -> List[float]:
        vetor = self.embedding(amostra)
        self.definir_embedding(perfil_id, vetor)
        return vetor

    def definir_embedding(self, perfil_id: str, vetor: List[float]) -> None:
        self._embeddings[perfil_id] = [float(v) for v in vetor]

    def remover(self, perfil_id: str) -> None:
        self._embeddings.pop(perfil_id, None)

    @staticmethod
    def _similaridade(a: List[float], b: List[float]) -> float:
        va, vb = np.asarray(a), np.asarray(b)
        denominador = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denominador == 0:
            return 0.0
        return float(np.dot(va, vb) / denominador)

    def identificar(self, amostra: bytes) -> str | None:
        if not self._embeddings:
            return None
        vetor = self.embedding(amostra)
        melhor_id = None
        melhor_valor = -1.0
        for perfil_id, referencia in self._embeddings.items():
            valor = self._similaridade(vetor, referencia)
            if valor > melhor_valor:
                melhor_valor = valor
                melhor_id = perfil_id
        logger.info("similaridade máxima %.3f (limiar %.3f)", melhor_valor, self.limiar)
        return melhor_id if melhor_valor >= self.limiar else None

    def estado(self) -> dict:
        return {
            "modelo": self.nome,
            "disponivel": True,
            "carregado": self._modelo is not None,
            "limiar": self.limiar,
            "perfis_cadastrados": len(self._embeddings),
        }

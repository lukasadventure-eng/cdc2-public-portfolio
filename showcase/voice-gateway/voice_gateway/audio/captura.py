# -*- coding: utf-8 -*-
"""Captura de microfone no servidor (Windows WASAPI via soundcard).

Alternativa ao getUserMedia quando o navegador bloqueia o microfone. O áudio
é capturado no mesmo computador do gateway e enviado ao STT local — nunca
saída para serviço externo.

O limiar de fala é adaptativo: estima-se o ruído ambiente de forma contínua e
o limite de detecção é derivado dele, com histerese para evitar oscilações.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

from .wav import pcm_para_wav  # noqa: F401 — conversão disponível aos consumidores


logger = logging.getLogger("voice_gateway.captura")


class CapturadorServidor:
    def __init__(
        self,
        sample_rate: int = 16000,
        limiar: float = 0.012,
        quadros_silencio: int = 18,
        duracao_max_s: float = 20.0,
        dispositivo: str = "",
        adaptativo: bool = True,
        multiplicador_ruido: float = 3.0,
        limiar_minimo: float = 0.004,
        janela_ruido: int = 60,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.limiar_base = float(limiar)
        self.quadros_silencio = int(quadros_silencio)
        self.duracao_max_s = float(duracao_max_s)
        self.dispositivo = dispositivo
        self.adaptativo = bool(adaptativo)
        self.multiplicador_ruido = float(multiplicador_ruido)
        self.limiar_minimo = float(limiar_minimo)
        self.janela_ruido = int(janela_ruido)
        self.ruido_estimado = 0.0
        self._historico: Deque[float] = deque(maxlen=max(20, janela_ruido))
        self.ultimo_estado = "ocioso"
        self.ultimo_dispositivo = ""

    @staticmethod
    def dispositivos() -> List[str]:
        try:
            import soundcard as sc

            return [m.name for m in sc.all_microphones(include_loopback=False)]
        except Exception:  # noqa: BLE001
            return []

    def _selecionar_microfone(self):
        import soundcard as sc

        microfones = sc.all_microphones(include_loopback=False)
        if not microfones:
            raise RuntimeError("Nenhum microfone encontrado no Windows.")
        escolhido = None
        if self.dispositivo:
            escolhido = next((m for m in microfones if m.name == self.dispositivo), None)
            if escolhido is None:
                self.dispositivo = ""
        microfone = escolhido or sc.default_microphone() or microfones[0]
        self.ultimo_dispositivo = microfone.name
        return microfone, microfone.name

    def _novo_recorder(self):
        microfone, nome = self._selecionar_microfone()
        return microfone.recorder(samplerate=self.sample_rate, channels=1), nome

    @staticmethod
    def _bloco_a_pcm16(bloco: np.ndarray) -> tuple[bytes, float]:
        amostras = np.asarray(bloco).reshape(-1)
        rms = float(np.sqrt(np.mean(amostras**2))) if amostras.size else 0.0
        pcm = (np.clip(amostras, -1.0, 1.0) * 32767).astype("<i2")
        return pcm.tobytes(), rms

    def atualizar_ruido(self, rms: float) -> float:
        """Estima ruído ambiente e devolve o limiar atual de fala."""
        self._historico.append(rms)
        if len(self._historico) >= 10:
            ordenado = sorted(self._historico)
            percentil = int(len(ordenado) * 0.35)
            self.ruido_estimado = float(ordenado[percentil])
        if not self.adaptativo:
            return self.limiar_base
        return max(
            self.limiar_minimo,
            self.ruido_estimado * self.multiplicador_ruido,
            self.limiar_base * 0.5,
        )

    def estado(self) -> Dict[str, Any]:
        return {
            "estado": self.ultimo_estado,
            "dispositivo": self.ultimo_dispositivo or self.dispositivo,
            "ruido_estimado": round(self.ruido_estimado, 5),
            "limiar_efetivo": round(
                max(self.limiar_minimo, self.ruido_estimado * self.multiplicador_ruido),
                5,
            ),
            "adaptativo": self.adaptativo,
        }

    async def capturar_turno(
        self,
        publicar_nivel: Callable[[float], None],
        cancelamento: asyncio.Event,
        publicar_estado: Callable[[str], None] | None = None,
    ) -> bytes:
        """Captura até detectar silêncio após fala. Retorna PCM16@16 kHz."""

        def mudar(estado: str) -> None:
            self.ultimo_estado = estado
            if publicar_estado:
                publicar_estado(estado)

        tentativas = 0
        while tentativas < 3 and not cancelamento.is_set():
            try:
                recorder, nome = self._novo_recorder()
                self.ultimo_dispositivo = nome
                break
            except Exception:  # noqa: BLE001
                tentativas += 1
                mudar("erro")
                if tentativas >= 3:
                    raise
                self.dispositivo = ""
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError("Não foi possível abrir o microfone.")

        partes: List[bytes] = []
        falado = False
        silencio = 0
        inicio = time.monotonic()
        mudar("capturando")
        with recorder:
            try:
                while not cancelamento.is_set():
                    if time.monotonic() - inicio > self.duracao_max_s:
                        break
                    try:
                        bloco = await asyncio.to_thread(recorder.record, 1024)
                    except Exception as erro:
                        logger.error(f"Erro na captura WASAPI: {erro}")
                        mudar("erro")
                        raise
                    pcm, rms = self._bloco_a_pcm16(bloco)
                    publicar_nivel(rms)
                    limiar = self.atualizar_ruido(rms)
                    if rms > limiar:
                        if not falado:
                            mudar("falando")
                        falado = True
                        silencio = 0
                        partes.append(pcm)
                    elif falado:
                        silencio += 1
                        partes.append(pcm)
                        if silencio >= self.quadros_silencio:
                            break
                    else:
                        mudar("capturando")
            finally:
                logger.debug("Recurso de captura liberado.")
        return b"".join(partes)

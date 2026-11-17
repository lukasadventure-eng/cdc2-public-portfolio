# -*- coding: utf-8 -*-
"""Converte PCM16 bruto do navegador em WAV (cabeçalho RIFF)."""

from __future__ import annotations

import struct


def pcm_para_wav(
    pcm: bytes, sample_rate: int = 16_000, canais: int = 1, bits: int = 16
) -> bytes:
    if not pcm:
        return b""
    byte_rate = sample_rate * canais * bits // 8
    bloco = canais * bits // 8
    cabecalho = b"".join(
        [
            b"RIFF",
            struct.pack("<I", 36 + len(pcm)),
            b"WAVE",
            b"fmt ",
            struct.pack("<IHHIIHH", 16, 1, canais, sample_rate, byte_rate, bloco, bits),
            b"data",
            struct.pack("<I", len(pcm)),
        ]
    )
    return cabecalho + pcm

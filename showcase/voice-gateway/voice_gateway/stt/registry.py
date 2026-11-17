# -*- coding: utf-8 -*-
"""Registro de provedores STT."""

from __future__ import annotations

from ..config import Config
from .base import STTProvider
from .browser import BrowserSTT
from .local import LocalSTT


def criar_stt(config: Config) -> STTProvider:
    providers: dict[str, type[STTProvider]] = {
        BrowserSTT.id: BrowserSTT,
        LocalSTT.id: LocalSTT,
    }
    classe = providers.get(config.stt.provedor, BrowserSTT)
    return classe(config.stt)

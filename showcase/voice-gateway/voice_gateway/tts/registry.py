# -*- coding: utf-8 -*-
"""Registro de provedores TTS."""

from __future__ import annotations

from ..config import Config
from .base import TTSProvider
from .browser import BrowserTTS
from .local import LocalTTS


def criar_tts(config: Config) -> TTSProvider:
    providers: dict[str, type[TTSProvider]] = {
        BrowserTTS.id: BrowserTTS,
        LocalTTS.id: LocalTTS,
    }
    classe = providers.get(config.tts.provedor, BrowserTTS)
    return classe(config.tts)

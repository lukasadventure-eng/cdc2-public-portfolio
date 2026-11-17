# -*- coding: utf-8 -*-
"""TTS no navegador (speechSynthesis).

Vozes em português brasileiro são selecionadas pelo identificador lógico
``salomao-ptbr`` / ``cdc-ptbr``; o cliente resolve para a melhor voz pt-BR
disponível no dispositivo e aplica velocidade/altura/pausas.
"""

from __future__ import annotations

from .base import TTSProvider


class BrowserTTS(TTSProvider):
    id = "browser"
    nome = "Navegador (SpeechSynthesis)"

    @property
    def sintetiza_no_servidor(self) -> bool:
        return False

    def descricao(self) -> str:
        return "Síntese local no dispositivo, com vozes pt-BR e controle de prosódia."

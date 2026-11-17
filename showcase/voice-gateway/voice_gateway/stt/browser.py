# -*- coding: utf-8 -*-
"""STT no navegador (Web Speech API).

Não introduz dependências nem envia áudio ao servidor. O cliente publica o
texto final via evento ``transcript``. É o padrão porque funciona em desktop e
celular sem configuração; provedores locais podem ser ativados quando a
privacidade/robustez offline exigirem.
"""

from __future__ import annotations

from .base import STTProvider


class BrowserSTT(STTProvider):
    id = "browser"
    nome = "Navegador (Web Speech)"

    @property
    def transcreve_no_servidor(self) -> bool:
        return False

    def descricao(self) -> str:
        return "Reconhecimento no dispositivo via Web Speech API (sem áudio no servidor)."

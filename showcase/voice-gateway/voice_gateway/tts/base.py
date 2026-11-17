# -*- coding: utf-8 -*-
"""Interface comum dos provedores de síntese de fala."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class AudioSintetizado:
    dados: bytes
    content_type: str = "audio/mpeg"
    formato: str = "mp3"


class TTSProvider(ABC):
    id: str = "base"
    nome: str = "Base"

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    def descricao(self) -> str:
        ...

    @property
    def sintetiza_no_servidor(self) -> bool:
        """False quando o navegador sintetiza com speechSynthesis."""
        return True

    async def sintetizar(
        self,
        texto: str,
        voz: str = "",
        velocidade: float = 1.0,
        altura: float = 1.0,
    ) -> AudioSintetizado | None:
        return None

    def info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao(),
            "sintetiza_no_servidor": self.sintetiza_no_servidor,
        }

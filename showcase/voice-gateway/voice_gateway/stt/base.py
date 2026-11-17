# -*- coding: utf-8 -*-
"""Interface comum dos provedores de transcrição."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class STTProvider(ABC):
    id: str = "base"
    nome: str = "Base"

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    def descricao(self) -> str:
        ...

    @property
    def transcreve_no_servidor(self) -> bool:
        """False quando o próprio navegador faz o reconhecimento."""
        return True

    async def transcrever(self, audio: bytes, idioma: str | None = None) -> str:
        raise NotImplementedError(
            f"{self.id} não aceita áudio enviado ao servidor"
        )

    def info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao(),
            "transcreve_no_servidor": self.transcreve_no_servidor,
        }

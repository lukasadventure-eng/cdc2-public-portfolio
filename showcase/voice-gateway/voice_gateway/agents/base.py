# -*- coding: utf-8 -*-
"""Interface comum dos adaptadores de agente."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List

from ..config import AgenteConfig


@dataclass
class ResultadoAgente:
    texto: str
    agente_id: str
    modelo: str = ""
    metadados: Dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """Um adaptador recebe texto + contexto e produz tokens incrementalmente.

    O cancelamento é cooperativo: o gateway sinaliza ``asyncio.Event`` quando o
    usuário interrompe a fala (barge-in) e o adaptador para de gerar.
    """

    def __init__(self, config: AgenteConfig) -> None:
        self.config = config
        self.id = config.id

    @abstractmethod
    def descricao(self) -> str:
        ...

    def status(self) -> Dict[str, Any]:
        return {"id": self.id, "nome": self.config.nome, "ativo": self.config.ativo}

    async def responder(
        self,
        texto: str,
        contexto: List[Dict[str, str]],
        cancelamento: asyncio.Event,
    ) -> AsyncIterator[str]:
        """Gera a resposta em pedaços. Deve checar ``cancelamento`` frequentemente."""
        if cancelamento.is_set():
            return
        resposta = await self.responder_texto(texto, contexto, cancelamento)
        if cancelamento.is_set():
            return
        for indice in range(0, len(resposta), 24):
            if cancelamento.is_set():
                return
            yield resposta[indice : indice + 24]
            await asyncio.sleep(0)

    async def responder_texto(
        self,
        texto: str,
        contexto: List[Dict[str, str]],
        cancelamento: asyncio.Event,
    ) -> str:
        raise NotImplementedError(f"{self.id} não implementou responder_texto/responder")

    async def fechar(self) -> None:
        """Libera processos/conexões persistentes, se houver."""
        return None

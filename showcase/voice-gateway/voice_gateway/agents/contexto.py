# -*- coding: utf-8 -*-
"""Adaptador determinístico para testes de continuidade de contexto.

Não é um agente de produção: responde com o número do turno e o texto recebido,
permitindo verificar que o histórico é preservado entre interações.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, List

from .base import AgentAdapter


class ContextoAdapter(AgentAdapter):
    def descricao(self) -> str:
        return "Adaptador de teste — verifica continuidade de contexto."

    async def responder(
        self,
        texto: str,
        contexto: List[Dict[str, str]],
        cancelamento: asyncio.Event,
    ) -> AsyncIterator[str]:
        if cancelamento.is_set():
            return
        turno = sum(1 for m in contexto if m.get("remetente") == "usuario") + 1
        yield f"Turno {turno}: {texto}"
        await asyncio.sleep(0)

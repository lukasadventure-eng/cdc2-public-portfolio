# -*- coding: utf-8 -*-
"""Adaptador de teste: ecoa o texto com a identidade do agente."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, List

from .base import AgentAdapter


class EchoAdapter(AgentAdapter):
    def descricao(self) -> str:
        return "Adaptador de diagnóstico — repete a mensagem recebida."

    async def responder(
        self,
        texto: str,
        contexto: List[Dict[str, str]],
        cancelamento: asyncio.Event,
    ) -> AsyncIterator[str]:
        yield f"Echo ({self.id}): {texto}"
        await asyncio.sleep(0)

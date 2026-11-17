# -*- coding: utf-8 -*-
"""Barramento de eventos por sessão.

Cada conexão WebSocket assina um canal de sessão. Eventos publicados pelo
gateway são entregues a todas as conexões da mesma sessão, o que permite
interface desktop, celular e terminal acompanharem a mesma conversa.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, Set


class EventBus:
    def __init__(self, queue_maxsize: int = 512) -> None:
        self._queue_maxsize = queue_maxsize
        self._canais: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._todos: Set[asyncio.Queue] = set()

    def subscribe(self, sessao_id: str, fila: asyncio.Queue | None = None) -> asyncio.Queue:
        if fila is None:
            fila = asyncio.Queue(maxsize=self._queue_maxsize)
        self._canais[sessao_id].add(fila)
        return fila

    def subscribe_all(self) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        self._todos.add(fila)
        return fila

    def unsubscribe(self, sessao_id: str, fila: asyncio.Queue) -> None:
        self._canais.get(sessao_id, set()).discard(fila)
        if not self._canais.get(sessao_id):
            self._canais.pop(sessao_id, None)

    def unsubscribe_all(self, fila: asyncio.Queue) -> None:
        self._todos.discard(fila)

    def publish(self, sessao_id: str, payload: Dict[str, Any]) -> None:
        """Publicação síncrona (não bloqueante). Filas cheias descartam o evento."""
        for fila in list(self._canais.get(sessao_id, ())):
            self._entregar(fila, payload)
        for fila in list(self._todos):
            self._entregar(fila, payload)

    def _entregar(self, fila: asyncio.Queue, payload: Dict[str, Any]) -> None:
        try:
            fila.put_nowait(payload)
        except asyncio.QueueFull:
            # Perder um token de fala é preferível a travar o gateway inteiro.
            pass

    def canais_ativos(self) -> Dict[str, int]:
        return {chave: len(valor) for chave, valor in self._canais.items()}

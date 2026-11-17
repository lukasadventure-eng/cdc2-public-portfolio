# -*- coding: utf-8 -*-
"""Autenticação por token e limite de taxa.

A voz NÃO concede permissões administrativas: o mesmo token é exigido para
HTTP e WebSocket, e operações críticas são bloqueadas por configuração.
"""

from __future__ import annotations

import hmac
import time
from collections import deque
from typing import Deque, Optional


class AuthManager:
    def __init__(self, token: str, exigir_token: bool = True) -> None:
        self.token = token or ""
        self.exigir_token = bool(exigir_token and self.token)

    def validar(self, fornecido: Optional[str]) -> bool:
        if not self.exigir_token:
            return True
        if not fornecido:
            return False
        return hmac.compare_digest(str(fornecido), self.token)

    def token_publico(self) -> str:
        """Nunca expõe o token; apenas um rótulo para a UI."""
        return "ativado" if self.exigir_token else "desativado"


class RateLimiter:
    """Janela deslizante simples, por conexão."""

    def __init__(self, limite: int, janela_segundos: float = 60.0) -> None:
        self.limite = max(1, int(limite))
        self.janela = float(janela_segundos)
        self._eventos: Deque[float] = deque()

    def permitir(self, agora: Optional[float] = None) -> bool:
        agora = agora if agora is not None else time.monotonic()
        while self._eventos and agora - self._eventos[0] >= self.janela:
            self._eventos.popleft()
        if len(self._eventos) >= self.limite:
            return False
        self._eventos.append(agora)
        return True

    def reiniciar(self) -> None:
        self._eventos.clear()

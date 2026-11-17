# -*- coding: utf-8 -*-
"""Fábrica de adaptadores de agente."""

from __future__ import annotations

from typing import Dict

from ..config import Config
from .base import AgentAdapter
from .cdc import CDCAdapter
from .contexto import ContextoAdapter
from .echo import EchoAdapter
from .opencode import OpenCodeAdapter
from .salomao import SalomaoAdapter


def criar_agente(config: Config, agente_id: str) -> AgentAdapter:
    cfg = config.agente(agente_id)
    if cfg is None:
        raise ValueError(f"Agente desconhecido: {agente_id}")
    fabricas: Dict[str, type[AgentAdapter]] = {
        "salomao": SalomaoAdapter,
        "cdc": CDCAdapter,
        "opencode": OpenCodeAdapter,
        "echo": EchoAdapter,
        "contexto": ContextoAdapter,
    }
    classe = fabricas.get(cfg.adaptador, EchoAdapter)
    return classe(cfg)

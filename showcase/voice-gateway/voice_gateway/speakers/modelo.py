# -*- coding: utf-8 -*-
"""Modelo de perfil de falante (sem áudio bruto)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict

from ..models import agora_iso, novo_id


@dataclass
class PerfilFalante:
    id: str
    nome: str
    consentimento: bool
    criado_em: str = field(default_factory=agora_iso)
    amostras_autorizadas: int = 0
    metadados: Dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


def novo_perfil(nome: str, consentimento: bool) -> PerfilFalante:
    if not consentimento:
        raise PermissionError("Consentimento do titular é obrigatório.")
    nome = str(nome or "").strip()
    if not nome or len(nome) > 80:
        raise ValueError("Nome do perfil inválido.")
    return PerfilFalante(id=novo_id("fal_"), nome=nome, consentimento=True)

# -*- coding: utf-8 -*-
"""Modelos de domínio do Voice Gateway (sem dependências externas)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def novo_id(prefixo: str = "") -> str:
    return prefixo + uuid.uuid4().hex[:16]


@dataclass
class Mensagem:
    id: str
    remetente: str  # usuario | agente | sistema
    conteudo: str
    agente_id: str = ""
    origem: str = "voz"  # voz | texto | sistema
    timestamp: str = field(default_factory=agora_iso)
    metadados: Dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Sessao:
    id: str
    agente_id: str
    criada_em: str = field(default_factory=agora_iso)
    atualizada_em: str = field(default_factory=agora_iso)
    mensagens: List[Mensagem] = field(default_factory=list)
    voz_id: str = ""
    rotulo: str = ""
    ativa: bool = True

    def adicionar(self, mensagem: Mensagem) -> Mensagem:
        self.mensagens.append(mensagem)
        self.atualizada_em = mensagem.timestamp
        return mensagem

    def contexto(self, limite: int = 40) -> List[Dict[str, str]]:
        """Contexto recente no formato esperado pelos adaptadores de agente."""
        return [
            {
                "remetente": m.remetente,
                "conteudo": m.conteudo,
            }
            for m in self.mensagens[-limite:]
            if m.conteudo and m.remetente in ("usuario", "agente")
        ]

    def para_dict(self, incluir_mensagens: bool = True) -> Dict[str, Any]:
        dados = asdict(self)
        if not incluir_mensagens:
            dados.pop("mensagens", None)
        return dados


def evento(tipo: str, **dados: Any) -> Dict[str, Any]:
    """Constrói um evento do protocolo WebSocket."""
    payload = {"type": tipo, **dados}
    return payload


class EstadoTurno:
    """Estados explícitos do ciclo de fala, usados na UI e na auditoria."""

    OCIOSO = "ocioso"
    OUVINDO = "ouvindo"
    TRANSCREVENDO = "transcrevendo"
    PENSANDO = "pensando"
    FALANDO = "falando"
    INTERROMPIDO = "interrompido"
    ERRO = "erro"

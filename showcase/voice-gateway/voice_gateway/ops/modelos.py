# -*- coding: utf-8 -*-
"""Modelos de domínio das operações (tarefas, estados e eventos)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from ..models import agora_iso, novo_id


class EstadoTarefa(str, Enum):
    RECEBIDA = "recebida"
    AGUARDANDO_CONFIRMACAO = "aguardando_confirmacao"
    CONFIRMADA = "confirmada"
    SESSAO_INICIADA = "sessao_iniciada"
    EM_EXECUCAO = "em_execucao"
    AGUARDANDO_AUTORIZACAO = "aguardando_autorizacao"
    CONCLUIDA = "concluida"
    INTERROMPIDA = "interrompida"
    FALHA = "falha"

    @property
    def terminal(self) -> bool:
        return self in (
            EstadoTarefa.CONCLUIDA,
            EstadoTarefa.INTERROMPIDA,
            EstadoTarefa.FALHA,
        )


TIPOS_EVENTO = (
    "tarefa_recebida",
    "confirmacao_solicitada",
    "tarefa_confirmada",
    "sessao_iniciada",
    "execucao_em_andamento",
    "resposta_parcial",
    "ferramenta_utilizada",
    "autorizacao_necessaria",
    "etapa_concluida",
    "tarefa_concluida",
    "tarefa_interrompida",
    "tarefa_falha",
    "tarefa_continuada",
    "resultado_lido",
)


@dataclass
class EventoOperacional:
    id: str
    tarefa_id: str
    tipo: str
    timestamp: str
    estado: str = ""
    mensagem: str = ""
    dados: Dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TarefaOperacional:
    id: str
    descricao: str
    destino: str
    origem: str
    sessao_voz_id: str = ""
    sessao_opencode_id: str = ""
    estado: EstadoTarefa = EstadoTarefa.RECEBIDA
    impacto: str = "normal"
    criada_em: str = field(default_factory=agora_iso)
    atualizada_em: str = field(default_factory=agora_iso)
    resultado: str = ""
    erro: str = ""
    eventos: List[EventoOperacional] = field(default_factory=list)
    confirmada_por: str = ""

    def para_dict(self, incluir_eventos: bool = True) -> Dict[str, Any]:
        dados = asdict(self)
        dados["estado"] = self.estado.value
        if not incluir_eventos:
            dados.pop("eventos", None)
        return dados


def nova_tarefa(
    descricao: str,
    destino: str,
    origem: str,
    sessao_voz_id: str = "",
    impacto: str = "normal",
) -> TarefaOperacional:
    return TarefaOperacional(
        id=novo_id("tar_"),
        descricao=descricao.strip(),
        destino=destino,
        origem=origem,
        sessao_voz_id=sessao_voz_id,
        impacto=impacto,
    )

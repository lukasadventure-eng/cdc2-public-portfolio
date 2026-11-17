# -*- coding: utf-8 -*-
"""Política de anúncios falados de eventos operacionais.

Eventos parciais e de ferramenta são visualizados, mas não anunciados por
padrão — evita notificações excessivas. A política é configurável.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, Optional, Set


@dataclass
class PoliticaAnuncios:
    eventos: Set[str] = field(
        default_factory=lambda: {
            "tarefa_recebida",
            "confirmacao_solicitada",
            "tarefa_confirmada",
            "sessao_iniciada",
            "autorizacao_necessaria",
            "tarefa_concluida",
            "tarefa_interrompida",
            "tarefa_falha",
        }
    )
    anunciar_ferramentas: bool = False
    anunciar_parciais: bool = False
    max_por_minuto: int = 6
    silenciada: bool = False
    # Janela local "não perturbar" no formato HH:MM. Fora da janela, anúncios
    # continuam; eventos terminais nunca são perdidos silenciosamente.
    nao_perturbar_inicio: str = ""
    nao_perturbar_fim: str = ""
    dedupe_ttl_s: float = 300.0

    @classmethod
    def de_lista(cls, eventos: list[str], **kwargs: Any) -> "PoliticaAnuncios":
        politica = cls(**kwargs)
        if eventos is not None:
            politica.eventos = set(eventos)
        return politica


_MENSAGENS: Dict[str, str] = {
    "tarefa_recebida": "Tarefa recebida. Vou encaminhar ao agente responsável.",
    "confirmacao_solicitada": "Esta operação precisa de confirmação. Diga confirmar para prosseguir.",
    "tarefa_confirmada": "Confirmação recebida. Iniciando a execução.",
    "sessao_iniciada": "Sessão de trabalho iniciada.",
    "execucao_em_andamento": "O OpenCode está executando a tarefa.",
    "ferramenta_utilizada": "Ferramenta utilizada pelo OpenCode.",
    "autorizacao_necessaria": "O OpenCode solicitou autorização para uma ferramenta.",
    "tarefa_concluida": "Tarefa concluída com sucesso.",
    "tarefa_interrompida": "Execução interrompida.",
    "tarefa_falha": "A execução falhou. Consulte o resultado para detalhes.",
    "tarefa_continuada": "Continuando a execução na mesma sessão.",
    "resultado_lido": "Este é o último resultado.",
}

_TERMINAIS = {"tarefa_concluida", "tarefa_interrompida", "tarefa_falha"}


class Notificador:
    def __init__(self, politica: PoliticaAnuncios | None = None) -> None:
        self.politica = politica or PoliticaAnuncios()
        self._historico: Deque[float] = deque()
        self._anunciados: Dict[str, float] = {}

    def _em_nao_perturbar(self) -> bool:
        inicio, fim = (
            self.politica.nao_perturbar_inicio,
            self.politica.nao_perturbar_fim,
        )
        if not inicio or not fim:
            return False
        agora = datetime.now().strftime("%H:%M")
        if inicio <= fim:
            return inicio <= agora <= fim
        return agora >= inicio or agora <= fim  # janela atravessa a meia-noite

    def deve_anunciar(self, evento: Dict[str, Any]) -> bool:
        tipo = str(evento.get("tipo", ""))
        if self.politica.silenciada:
            return False
        identificador = str(
            evento.get("id") or (evento.get("dados") or {}).get("id") or ""
        )
        agora = time.monotonic()
        if identificador:
            ultimo = self._anunciados.get(identificador)
            if ultimo is not None and agora - ultimo < self.politica.dedupe_ttl_s:
                return False  # nunca anuncia o mesmo evento duas vezes
            self._anunciados[identificador] = agora
        if self._em_nao_perturbar() and tipo not in _TERMINAIS:
            return False
        if tipo in _TERMINAIS:
            return True
        if tipo == "ferramenta_utilizada" and not self.politica.anunciar_ferramentas:
            return False
        if tipo == "resposta_parcial" and not self.politica.anunciar_parciais:
            return False
        if tipo not in self.politica.eventos:
            return False
        agora = time.monotonic()
        while self._historico and agora - self._historico[0] >= 60:
            self._historico.popleft()
        if len(self._historico) >= max(1, self.politica.max_por_minuto):
            return False
        self._historico.append(agora)
        return True

    def mensagem(self, evento: Dict[str, Any]) -> str:
        tipo = str(evento.get("tipo", ""))
        base = _MENSAGENS.get(tipo, "")
        dados = evento.get("dados") or {}
        if tipo == "ferramenta_utilizada" and dados.get("ferramenta"):
            return f"Ferramenta utilizada: {str(dados['ferramenta'])[:40]}."
        if tipo == "tarefa_falha":
            # Detalhes de erro podem conter segredos; a voz usa texto genérico.
            return "A execução falhou. Consulte o registro operacional para detalhes."
        return base

# -*- coding: utf-8 -*-
"""Reconhecimento determinístico de comandos operacionais em pt-BR.

Nenhum modelo é necessário para decidir intenção: baixa latência, auditável e
sem depender de provedor externo. O texto é normalizado (sem acentos).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..core.router import normalizar

TIPO_DELEGAR = "delegar"
TIPO_CONTINUAR = "continuar"
TIPO_INTERROMPER = "interromper"
TIPO_CONFIRMAR = "confirmar"
TIPO_EXPLICAR = "explicar"
TIPO_ULTIMO_RESULTADO = "ultimo_resultado"
TIPO_QUAL_AGENTE = "qual_agente"
TIPO_ENCAMINHAR_RESPONSAVEL = "encaminhar_responsavel"
TIPO_LISTAR_TAREFAS = "listar_tarefas"
TIPO_STATUS_PROJETO = "status_projeto"
TIPO_NENHUM = "nenhum"


@dataclass
class IntencaoComando:
    tipo: str
    original: str
    destino: str = ""
    descricao: str = ""
    impacto: str = "normal"
    exigir_confirmacao: bool = False
    emitente: str = ""
    confianca: float = 0.0
    tarefa_id: str = ""

    @property
    def operacional(self) -> bool:
        return self.tipo != TIPO_NENHUM


_PADROES: list[tuple[str, str]] = [
    (
        TIPO_CONFIRMAR,
        r"^(sim|confirmo|confirme|confirmar|confirmado|autorizo|autorizar|pode executar|"
        r"pode continuar|prossiga|execute|executar)\s*[.!]?$",
    ),
    (
        TIPO_INTERROMPER,
        r"\b(interrompa|interromper|interrompa a execucao|pare|parar|cancele|cancelar|"
        r"aborte|abortar|segure|segure a execucao)\b",
    ),
    (TIPO_CONTINUAR, r"\b(continue|continuar|retome|retomar|prossiga com a tarefa)\b"),
    (
        TIPO_ULTIMO_RESULTADO,
        r"\b(ultimo resultado|leia o resultado|leia o ultimo resultado|"
        r"resultado da tarefa|mostre o resultado)\b",
    ),
    (
        TIPO_QUAL_AGENTE,
        r"\b(qual agente|quem esta trabalhando|quem esta executando|"
        r"qual agente esta trabalhando)\b",
    ),
    (
        TIPO_EXPLICAR,
        r"\b(exlique|explique o que esta acontecendo|o que esta acontecendo|"
        r"como vai a execucao|qual o estado da execucao)\b",
    ),
    (
        TIPO_LISTAR_TAREFAS,
        r"\b(quais tarefas|liste as tarefas|tarefas em andamento|"
        r"tarefas ativas|historico de tarefas)\b",
    ),
    (
        TIPO_ENCAMINHAR_RESPONSAVEL,
        r"\b(encaminhe|encaminhar|passe|mande|envie)\b.{0,40}?"
        r"\bagente\s+responsavel\b",
    ),
    (
        TIPO_STATUS_PROJETO,
        r"\b(status|estado do projeto|como esta o projeto|estado das tarefas)\b",
    ),
    (
        TIPO_DELEGAR,
        r"\b(peca|pede|solicite|solicita|mande|manda|encaminhe|encaminha|faca|"
        r"desenvolva|implemente|crie)\b.{0,40}?\b(opencode|codex|cdc)\b"
        r"(?:\s+(?:para|que|de)\s+)?(.*)$",
    ),
    (
        TIPO_DELEGAR,
        r"\b(opencode|codex|cdc)\b\s*,?\s*"
        r"(desenvolva|implemente|crie|faca|execute|analise|verifique)\b\s*(.*)$",
    ),
]
_COMPILADOS = [(tipo, re.compile(padrao)) for tipo, padrao in _PADROES]

_PADRAO_EMITENTE = re.compile(r"^(salomao|cdc|opencode|codex)\s*[,:]\s*(.+)$")

_DESTRUTIVO = re.compile(
    r"\b(apague|apagar|delete|deletar|remova|remover|exclua|excluir|"
    r"redefina|redefinir|reset|restaure|restaurar|force push|push forcado|"
    r"sobrescreva|sobrescrever|desinstale|desinstalar)\b"
)
_ALTO = re.compile(
    r"\b(instale|instalar|publique|publicar|deploy|commitar|faca commit|"
    r"enviar push|envie push|alterar permissao|permissoes|migracao)\b"
)


def avaliar_impacto(texto_norm: str) -> tuple[str, bool]:
    if _DESTRUTIVO.search(texto_norm):
        return "destrutivo", True
    if _ALTO.search(texto_norm):
        return "alto", True
    return "normal", False


class ParserComandos:
    """Interpreta comandos operacionais. Retorna ``nenhum`` se não houver comando."""

    def parse(self, texto: str) -> IntencaoComando:
        original = str(texto or "").strip()
        norm = normalizar(original)
        emitente = ""
        match_emitente = _PADRAO_EMITENTE.match(norm)
        if match_emitente:
            emitente = match_emitente.group(1)
            norm = match_emitente.group(2).strip()

        for tipo, padrao in _COMPILADOS:
            match = padrao.search(norm)
            if not match:
                continue
            destino = ""
            descricao = ""
            if tipo == TIPO_DELEGAR:
                grupos = [g for g in match.groups() if g]
                for grupo in grupos:
                    if normalizar(grupo) in {"opencode", "codex", "cdc"}:
                        destino = "opencode" if normalizar(grupo) in {"opencode", "codex"} else "cdc"
                    elif len(grupo.strip()) > 3:
                        descricao = grupo.strip()
                if not destino and emitente in {"opencode", "codex", "cdc"}:
                    destino = "opencode" if emitente in {"opencode", "codex"} else "cdc"
            impacto, exige = avaliar_impacto(norm)
            return IntencaoComando(
                tipo=tipo,
                original=original,
                destino=destino,
                descricao=descricao,
                impacto=impacto,
                exigir_confirmacao=exige,
                emitente=emitente,
                confianca=0.95 if tipo != TIPO_DELEGAR else 0.85,
            )

        return IntencaoComando(
            tipo=TIPO_NENHUM,
            original=original,
            emitente=emitente,
            confianca=0.0,
        )

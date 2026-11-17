# -*- coding: utf-8 -*-
"""Roteamento determinístico de mensagens entre agentes.

O roteamento é explícito (comando de voz/seleção na UI) ou automático por
pontuação de palavras-chave. Nunca usa um modelo para decidir — baixa latência
e comportamento auditável. As identidades permanecem separadas: o roteador
apenas escolhe o destinatário; quem responde é o adaptador daquele agente.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


def normalizar(texto: str) -> str:
    """minúsculas sem acentos — essencial para pt-BR falado/transcrito."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.casefold().strip()


@dataclass
class DecisaoRoteamento:
    agente_id: str
    confidence: float
    reason: str
    explicito: bool = False
    pontuacao: Dict[str, float] = None  # type: ignore[assignment]

    def para_dict(self) -> Dict[str, object]:
        return {
            "agente": self.agente_id,
            "confianca": round(self.confidence, 3),
            "motivo": self.reason,
            "explicito": self.explicito,
            "pontuacao": self.pontuacao or {},
        }


# Comandos de voz que trocam explicitamente de agente.
COMANDOS_EXPLICITOS: List[Tuple[str, str]] = [
    (r"\b(usar|usem|abrir|chamar|chame|conectar|conecte|falar|fale|trocar|mudar)\b.{0,24}\b(cdc)\b", "cdc"),
    (r"\b(usar|usem|abrir|chamar|chame|conectar|conecte|falar|fale|trocar|mudar)\b.{0,24}\b(salomao|salomao ai|salomao-ai)\b", "salomao"),
    (r"\b(usar|usem|abrir|chamar|chame|conectar|conecte|falar|fale|trocar|mudar)\b.{0,24}\b(opencode|open code|codex)\b", "opencode"),
    (r"\b(agente|modo)\s+(cdc|salomao|opencode|codex)\b", None),  # resolvido abaixo
]

# Pesos por agente. Um termo pode casar com mais de um agente; o maior ganha.
PALAVRAS_CHAVE: Dict[str, Dict[str, float]] = {
    "cdc": {
        "cdc": 4.0,
        "tarefa sal": 3.0,
        r"sal-\d+": 3.5,
        "autorizacao": 2.5,
        "autorizar": 2.0,
        "auditoria": 2.0,
        "relatorio": 1.8,
        "projeto": 1.2,
        "pull request": 1.5,
        "repositorio": 1.2,
        "github": 1.0,
        "git": 0.8,
        "agente cdc": 4.0,
        "status do agente": 2.0,
        "quarentena": 1.5,
        "fencing": 1.5,
        "epoch": 1.5,
    },
    "salomao": {
        "salomao": 4.0,
        "memoria": 2.0,
        "lembra": 1.8,
        "lembrou": 1.8,
        "constituicao": 2.0,
        "governanca": 1.8,
        "opcao": 1.0,
        "opiniao": 1.5,
        "filosofia": 1.5,
        "quem e voce": 2.0,
        "como voce esta": 1.2,
        "converse": 1.0,
        "inteligencia privada": 2.0,
    },
    "opencode": {
        "opencode": 4.0,
        "open code": 3.5,
        "codex": 2.5,
        "editar codigo": 2.0,
        "implementar": 1.5,
        "compilar": 1.5,
        "teste unitario": 1.5,
        "commitar": 1.5,
        "git commit": 2.0,
        "refatorar": 1.5,
    },
}


class AgentRouter:
    """Roteia texto para um agente registrado."""

    def __init__(
        self,
        agentes_disponiveis: Iterable[str],
        agente_padrao: str = "salomao",
        regras_explicitas: Optional[List[Tuple[str, str]]] = None,
        palavras_chave: Optional[Dict[str, Dict[str, float]]] = None,
        limiar_automatico: float = 2.0,
    ) -> None:
        self.disponiveis = set(agentes_disponiveis)
        self.padrao = agente_padrao if agente_padrao in self.disponiveis else (
            next(iter(self.disponiveis), "")
        )
        self.comandos = regras_explicitas or COMANDOS_EXPLICITOS
        self.palavras = palavras_chave or PALAVRAS_CHAVE
        self.limiar = limiar_automatico
        self._compilados = [(re.compile(padrao), alvo) for padrao, alvo in self.comandos]
        self._compiled_keywords: Dict[str, List[Tuple[re.Pattern, float, str]]] = {}
        for agente, termos in self.palavras.items():
            itens: List[Tuple[re.Pattern, float, str]] = []
            for termo, peso in termos.items():
                # Termos com metacaracteres já são regex; demais são literais com
                # fronteira de palavra (necessário para pt-BR sem acentos).
                eh_regex = any(c in termo for c in ".\\*+?[](){}|^$")
                padrao = termo if eh_regex else r"\b" + re.escape(termo) + r"\b"
                itens.append((re.compile(padrao), peso, termo))
            self._compiled_keywords[agente] = itens

    def _alvo_valido(self, alvo: Optional[str]) -> Optional[str]:
        if alvo is None:
            return None
        if alvo in self.disponiveis:
            return alvo
        aliases = {"codex": "opencode", "salomao-ai": "salomao", "salomao ai": "salomao"}
        resolvido = aliases.get(alvo)
        return resolvido if resolvido in self.disponiveis else None

    def route(
        self, texto: str, agente_explicito: Optional[str] = None
    ) -> DecisaoRoteamento:
        explicito = self._alvo_valido(agente_explicito)
        if explicito:
            return DecisaoRoteamento(
                agente_id=explicito,
                confidence=1.0,
                reason="seleção explícita na interface",
                explicito=True,
            )

        texto_norm = normalizar(texto or "")
        if not texto_norm:
            return DecisaoRoteamento(
                self.padrao, 0.0, "mensagem vazia — agente padrão", False, {}
            )

        for padrao, destino in self._compilados:
            if padrao.search(texto_norm):
                if destino is None:
                    match = padrao.search(texto_norm)
                    destino = match.group(2) if match and match.lastindex else None
                resolvido = self._alvo_valido(destino)
                if resolvido:
                    return DecisaoRoteamento(
                        resolvido,
                        1.0,
                        f"comando de voz explícito: {padrao.pattern}",
                        True,
                    )

        pontuacao: Dict[str, float] = {agente: 0.0 for agente in self.disponiveis}
        termos_detectados: Dict[str, str] = {}
        for agente, itens in self._compiled_keywords.items():
            if agente not in self.disponiveis:
                continue
            for padrao, peso, termo in itens:
                if padrao.search(texto_norm):
                    pontuacao[agente] += peso
                    termos_detectados.setdefault(agente, termo)
        melhor = max(pontuacao, key=lambda k: pontuacao[k])
        melhor_valor = pontuacao[melhor]
        if melhor_valor < self.limiar:
            return DecisaoRoteamento(
                self.padrao,
                min(1.0, melhor_valor / self.limiar) if self.limiar else 0.0,
                "sem sinal suficiente — agente padrão",
                False,
                pontuacao,
            )
        segundo = sorted(pontuacao.values(), reverse=True)[1:2]
        margem = segundo[0] if segundo else 0.0
        confianca = min(1.0, 0.5 + (melhor_valor - margem) / (2 * max(melhor_valor, 1.0)))
        return DecisaoRoteamento(
            melhor,
            confianca,
            f"pontuação por palavras-chave ({termos_detectados.get(melhor, 'neutro')})",
            False,
            pontuacao,
        )

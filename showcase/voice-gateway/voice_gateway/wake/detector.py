# -*- coding: utf-8 -*-
"""Detector determinístico da palavra de ativação.

A decisão é feita sobre o texto vindo de STT local — nenhum áudio é enviado a
serviço externo pelo gateway. O detector é desacoplado do transporte e do
provedor de STT, e pode ser substituído por um spotter embarcado no futuro.
"""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from ..core.router import normalizar
from ..models import agora_iso


@dataclass
class DeteccaoWake:
    palavra: str
    texto: str
    confianca: float
    timestamp: str

    def para_dict(self) -> Dict[str, object]:
        return {
            "palavra": self.palavra,
            "texto": self.texto[:120],
            "confianca": round(self.confianca, 2),
            "timestamp": self.timestamp,
        }


class WakeWordDetector:
    PALAVRAS_PADRAO: Tuple[str, ...] = ("salomao", "salomao ai")
    # Variações aceitas do reconhecedor local (ex.: "Salumão" em pt-BR).
    VARIANTES: Tuple[str, ...] = (
        "salomao", "salumao", "salamao", "salomao ai", "salumao ai",
    )
    LIMIAR_SIMILARIDADE = 0.78

    def __init__(
        self,
        palavras: Iterable[str] = PALAVRAS_PADRAO,
        cooldown_s: float = 2.5,
        max_chars: int = 120,
        habilitado: bool = False,
    ) -> None:
        self.palavras = tuple(normalizar(p) for p in palavras)
        self._padroes = [
            re.compile(r"\b" + re.escape(palavra) + r"\b") for palavra in self.palavras
        ]
        self.cooldown_s = float(cooldown_s)
        self.max_chars = int(max_chars)
        self.habilitado = bool(habilitado)
        self._ultima_deteccao = 0.0
        self._deteccoes = 0
        self._ativacoes = 0
        self._desativacoes = 0

    def ativar(self) -> None:
        self.habilitado = True
        self._ativacoes += 1

    def desativar(self) -> None:
        self.habilitado = False
        self._desativacoes += 1

    def alternar(self) -> bool:
        if self.habilitado:
            self.desativar()
        else:
            self.ativar()
        return self.habilitado

    def estado(self) -> Dict[str, object]:
        return {
            "habilitado": self.habilitado,
            "palavras": list(self.palavras),
            "deteccoes": self._deteccoes,
            "ativacoes": self._ativacoes,
            "desativacoes": self._desativacoes,
            "cooldown_s": self.cooldown_s,
        }

    def detectar(self, texto: str) -> Optional[DeteccaoWake]:
        if not self.habilitado:
            return None
        bruto = str(texto or "").strip()
        if not bruto or len(bruto) > self.max_chars:
            return None  # filtro de falsas ativações por ruído longo
        norm = normalizar(bruto)
        encontrada = ""
        for palavra, padrao in zip(self.palavras, self._padroes):
            if padrao.search(norm):
                encontrada = palavra
                break
        if not encontrada:
            # Correspondência tolerante nos tokens iniciais (onde o usuário
            # normalmente diz a palavra de ativação).
            tokens = [t for t in re.split(r"\W+", norm) if t][:3]
            for token in tokens:
                for variante in self.VARIANTES:
                    razao = difflib.SequenceMatcher(None, token, variante).ratio()
                    if razao >= self.LIMIAR_SIMILARIDADE:
                        encontrada = "salomao"
                        break
                if encontrada:
                    break
        if not encontrada:
            return None
        agora = time.monotonic()
        if agora - self._ultima_deteccao < self.cooldown_s:
            return None  # anti-repetição
        self._ultima_deteccao = agora
        self._deteccoes += 1
        return DeteccaoWake(
            palavra=encontrada,
            texto=bruto,
            confianca=1.0,
            timestamp=agora_iso(),
        )

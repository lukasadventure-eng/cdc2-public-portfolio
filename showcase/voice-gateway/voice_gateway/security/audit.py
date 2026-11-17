# -*- coding: utf-8 -*-
"""Trilha de auditoria append-only com corrente de hash.

Nunca registra áudio, transcrições completas, tokens ou credenciais.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict

_CHAVES_SENSIVEIS = (
    "token",
    "chave",
    "senha",
    "credencial",
    "secret",
    "authorization",
    "audio",
    "pcm",
    "amostra",
    "conteudo",
    "texto",
)


class AuditTrail:
    GENESIS = "0" * 64

    def __init__(self, caminho: Path) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._ultimo_hash = self._carregar_ultimo_hash()

    def _carregar_ultimo_hash(self) -> str:
        try:
            linhas = self.caminho.read_text(encoding="utf-8").splitlines()
            if linhas:
                return json.loads(linhas[-1]).get("hash", self.GENESIS)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return self.GENESIS

    @staticmethod
    def _limpar(dados: Dict[str, Any]) -> Dict[str, Any]:
        limpo: Dict[str, Any] = {}
        for chave, valor in dados.items():
            nome = str(chave).lower()
            if any(parte in nome for parte in _CHAVES_SENSIVEIS):
                continue
            if isinstance(valor, (str, int, float, bool)) or valor is None:
                texto = str(valor)
                limpo[str(chave)] = texto[:160]
        return limpo

    def registrar(self, acao: str, **detalhes: Any) -> str:
        with self._trava:
            payload = {
                "acao": str(acao)[:120],
                "detalhes": self._limpar(detalhes),
                "anterior": self._ultimo_hash,
            }
            canonico = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            digest = hashlib.sha256(
                (self._ultimo_hash + canonico).encode("utf-8")
            ).hexdigest()
            registro = {**payload, "hash": digest}
            with self.caminho.open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
                arquivo.flush()
            self._ultimo_hash = digest
            return digest

    def verificar(self) -> bool:
        """Valida a corrente de hash; detecta edição/remoção de registros."""
        try:
            anteriores = self.GENESIS
            for linha in self.caminho.read_text(encoding="utf-8").splitlines():
                registro = json.loads(linha)
                payload = {
                    "acao": registro["acao"],
                    "detalhes": registro["detalhes"],
                    "anterior": registro["anterior"],
                }
                canonico = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                esperado = hashlib.sha256(
                    (anteriores + canonico).encode("utf-8")
                ).hexdigest()
                if registro["anterior"] != anteriores or registro["hash"] != esperado:
                    return False
                anteriores = esperado
            return True
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return False

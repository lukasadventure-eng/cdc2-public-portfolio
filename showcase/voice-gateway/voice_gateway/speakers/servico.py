# -*- coding: utf-8 -*-
"""Serviço de perfis de falantes.

ALCANCE ATUAL (documentado): cadastro, listagem, consentimento, amostras
autorizadas (contador) e exclusão. A identificação depende de um modelo local
de speaker verification, que NÃO está incluído neste ambiente. O identificador
padrão retorna ``None`` e o gateway sempre trata a fala como "falante não
identificado", com fallback integral para a autenticação por token.

Este módulo NUNCA é usado para autorizar operações sensíveis.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .modelo import PerfilFalante, novo_perfil


class IdentificadorFalante(ABC):
    nome: str = "base"
    disponivel: bool = False

    @abstractmethod
    def identificar(self, amostra: bytes) -> Optional[str]:
        ...


class IdentificadorIndisponivel(IdentificadorFalante):
    """Implementação honesta para ambientes sem modelo de verificação."""

    nome = "indisponivel"
    disponivel = False

    def identificar(self, amostra: bytes) -> Optional[str]:
        return None


class ServicoFalantes:
    def __init__(
        self,
        caminho: Path,
        identificador: IdentificadorFalante | None = None,
    ) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.identificador = identificador or IdentificadorIndisponivel()
        self._inicializar()

    @contextmanager
    def _conectar(self):
        conn = sqlite3.connect(str(self.caminho), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def _inicializar(self) -> None:
        with self._conectar() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS falantes (
                    id TEXT PRIMARY KEY,
                    nome TEXT NOT NULL,
                    consentimento INTEGER NOT NULL,
                    criado_em TEXT NOT NULL,
                    amostras_autorizadas INTEGER NOT NULL DEFAULT 0,
                    metadados TEXT NOT NULL DEFAULT '{}'
                )"""
            )
            colunas = {
                linha["name"] for linha in conn.execute("PRAGMA table_info(falantes)")
            }
            if "embedding" not in colunas:
                conn.execute(
                    "ALTER TABLE falantes "
                    "ADD COLUMN embedding TEXT NOT NULL DEFAULT ''"
                )
        self._restaurar_embeddings()

    def _restaurar_embeddings(self) -> None:
        definir = getattr(self.identificador, "definir_embedding", None)
        if not callable(definir):
            return
        with self._conectar() as conn:
            for linha in conn.execute(
                "SELECT id, embedding FROM falantes WHERE embedding != ''"
            ):
                try:
                    definir(linha["id"], json.loads(linha["embedding"]))
                except Exception:  # noqa: BLE001
                    continue

    def criar(self, nome: str, consentimento: bool = False) -> PerfilFalante:
        perfil = novo_perfil(nome, consentimento)
        with self._conectar() as conn:
            conn.execute(
                "INSERT INTO falantes (id, nome, consentimento, criado_em, metadados) "
                "VALUES (?, ?, 1, ?, ?)",
                (perfil.id, perfil.nome, perfil.criado_em, "{}"),
            )
        return perfil

    def listar(self) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            return [
                {
                    "id": linha["id"],
                    "nome": linha["nome"],
                    "consentimento": bool(linha["consentimento"]),
                    "criado_em": linha["criado_em"],
                    "amostras_autorizadas": linha["amostras_autorizadas"],
                }
                for linha in conn.execute(
                    "SELECT * FROM falantes ORDER BY criado_em DESC"
                )
            ]

    def obter(self, perfil_id: str) -> Optional[PerfilFalante]:
        with self._conectar() as conn:
            linha = conn.execute(
                "SELECT * FROM falantes WHERE id = ?", (perfil_id,)
            ).fetchone()
        if linha is None:
            return None
        return PerfilFalante(
            id=linha["id"],
            nome=linha["nome"],
            consentimento=bool(linha["consentimento"]),
            criado_em=linha["criado_em"],
            amostras_autorizadas=linha["amostras_autorizadas"],
            metadados=json.loads(linha["metadados"] or "{}"),
        )

    def registrar_amostra(
        self, perfil_id: str, amostra: bytes | None = None
    ) -> bool:
        """Contabiliza a amostra autorizada e extrai embedding, se disponível.

        O áudio bruto nunca é gravado: apenas o vetor de características e o
        consentimento do titular.
        """
        vetor = None
        if amostra and hasattr(self.identificador, "embedding"):
            vetor = self.identificador.embedding(amostra)
            if hasattr(self.identificador, "definir_embedding"):
                self.identificador.definir_embedding(perfil_id, vetor)
        with self._conectar() as conn:
            if vetor is None:
                cur = conn.execute(
                    "UPDATE falantes SET amostras_autorizadas = "
                    "amostras_autorizadas + 1 "
                    "WHERE id = ? AND consentimento = 1",
                    (perfil_id,),
                )
            else:
                cur = conn.execute(
                    "UPDATE falantes SET amostras_autorizadas = "
                    "amostras_autorizadas + 1, embedding = ? "
                    "WHERE id = ? AND consentimento = 1",
                    (json.dumps(vetor), perfil_id),
                )
        return cur.rowcount > 0

    def excluir(self, perfil_id: str) -> bool:
        remover = getattr(self.identificador, "remover", None)
        if callable(remover):
            remover(perfil_id)
        with self._conectar() as conn:
            cur = conn.execute("DELETE FROM falantes WHERE id = ?", (perfil_id,))
        return cur.rowcount > 0

    def identificar(self, amostra: bytes) -> Optional[PerfilFalante]:
        if not self.identificador.disponivel:
            return None  # fallback: falante não identificado
        perfil_id = self.identificador.identificar(amostra)
        return self.obter(perfil_id) if perfil_id else None

    def estado(self) -> Dict[str, Any]:
        detalhes = {}
        if hasattr(self.identificador, "estado"):
            try:
                detalhes = self.identificador.estado()
            except Exception:  # noqa: BLE001
                detalhes = {}
        return {
            "identificador": self.identificador.nome,
            "disponivel": self.identificador.disponivel,
            "detalhes": detalhes,
            "perfis": len(self.listar()),
            "usado_para_autorizacao": False,
            "alcance": (
                "Cadastro/consentimento/amostras/exclusão operacionais; "
                "identificação depende de modelo local não incluído."
            ),
        }

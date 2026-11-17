# -*- coding: utf-8 -*-
"""Histórico persistente de sessões e transcrições (SQLite, stdlib).

Regras de privacidade:
  * áudio bruto NUNCA é gravado — apenas transcrições, quando habilitado;
  * retenção configurável (0 = indefinida);
  * operações de exclusão são explícitas e auditadas.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..models import Mensagem, Sessao, agora_iso, novo_id


class Historico:
    def __init__(self, caminho: Path, retencao_dias: int = 30, habilitado: bool = True):
        self.caminho = Path(caminho)
        self.retencao_dias = int(retencao_dias)
        self.habilitado = bool(habilitado)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    @contextmanager
    def _conectar(self):
        """Conexão com commit automático e fechamento garantido (Windows)."""
        conn = sqlite3.connect(str(self.caminho), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            with conn:
                yield conn
        finally:
            conn.close()

    def _inicializar(self) -> None:
        with self._conectar() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessoes (
                    id TEXT PRIMARY KEY,
                    agente_id TEXT NOT NULL,
                    criada_em TEXT NOT NULL,
                    atualizada_em TEXT NOT NULL,
                    voz_id TEXT NOT NULL DEFAULT '',
                    rotulo TEXT NOT NULL DEFAULT '',
                    ativa INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_sessoes_atualizada
                    ON sessoes(atualizada_em DESC);
                CREATE TABLE IF NOT EXISTS mensagens (
                    id TEXT PRIMARY KEY,
                    sessao_id TEXT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
                    remetente TEXT NOT NULL,
                    conteudo TEXT NOT NULL,
                    agente_id TEXT NOT NULL DEFAULT '',
                    origem TEXT NOT NULL DEFAULT 'voz',
                    timestamp TEXT NOT NULL,
                    metadados TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_mensagens_sessao
                    ON mensagens(sessao_id, timestamp);
                CREATE TABLE IF NOT EXISTS eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    sessao_id TEXT NOT NULL DEFAULT '',
                    agente_id TEXT NOT NULL DEFAULT '',
                    detalhes TEXT NOT NULL DEFAULT '{}'
                );
                """
            )

    def salvar_sessao(self, sessao: Sessao, salvar_mensagens: bool = True) -> None:
        if not self.habilitado:
            return
        with self._conectar() as conn:
            conn.execute(
                """INSERT INTO sessoes
                   (id, agente_id, criada_em, atualizada_em, voz_id, rotulo, ativa)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       agente_id=excluded.agente_id,
                       atualizada_em=excluded.atualizada_em,
                       voz_id=excluded.voz_id,
                       rotulo=excluded.rotulo,
                       ativa=excluded.ativa""",
                (
                    sessao.id,
                    sessao.agente_id,
                    sessao.criada_em,
                    sessao.atualizada_em,
                    sessao.voz_id,
                    sessao.rotulo,
                    int(sessao.ativa),
                ),
            )
            if salvar_mensagens:
                for mensagem in sessao.mensagens:
                    conn.execute(
                        """INSERT OR IGNORE INTO mensagens
                           (id, sessao_id, remetente, conteudo, agente_id, origem,
                            timestamp, metadados)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            mensagem.id,
                            sessao.id,
                            mensagem.remetente,
                            mensagem.conteudo,
                            mensagem.agente_id,
                            mensagem.origem,
                            mensagem.timestamp,
                            json.dumps(mensagem.metadados, ensure_ascii=False),
                        ),
                    )

    def carregar_sessao(self, sessao_id: str) -> Optional[Sessao]:
        with self._conectar() as conn:
            linha = conn.execute(
                "SELECT * FROM sessoes WHERE id = ?", (sessao_id,)
            ).fetchone()
            if linha is None:
                return None
            sessao = Sessao(
                id=linha["id"],
                agente_id=linha["agente_id"],
                criada_em=linha["criada_em"],
                atualizada_em=linha["atualizada_em"],
                voz_id=linha["voz_id"],
                rotulo=linha["rotulo"],
                ativa=bool(linha["ativa"]),
            )
            for msg in conn.execute(
                "SELECT * FROM mensagens WHERE sessao_id = ? ORDER BY timestamp",
                (sessao_id,),
            ):
                sessao.mensagens.append(
                    Mensagem(
                        id=msg["id"],
                        remetente=msg["remetente"],
                        conteudo=msg["conteudo"],
                        agente_id=msg["agente_id"],
                        origem=msg["origem"],
                        timestamp=msg["timestamp"],
                        metadados=json.loads(msg["metadados"] or "{}"),
                    )
                )
            return sessao

    def listar_sessoes(self, limite: int = 50) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            return [
                dict(linha)
                for linha in conn.execute(
                    """SELECT s.id, s.agente_id, s.criada_em, s.atualizada_em, s.rotulo,
                              s.ativa, COUNT(m.id) AS mensagens
                       FROM sessoes s LEFT JOIN mensagens m ON m.sessao_id = s.id
                       GROUP BY s.id ORDER BY s.atualizada_em DESC LIMIT ?""",
                    (limite,),
                )
            ]

    def registrar_evento(
        self,
        tipo: str,
        sessao_id: str = "",
        agente_id: str = "",
        **detalhes: Any,
    ) -> None:
        if not self.habilitado:
            return
        with self._conectar() as conn:
            conn.execute(
                """INSERT INTO eventos (timestamp, tipo, sessao_id, agente_id, detalhes)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    agora_iso(),
                    tipo,
                    sessao_id,
                    agente_id,
                    json.dumps(detalhes, ensure_ascii=False, default=str),
                ),
            )

    def aplicar_retencao(self) -> Dict[str, int]:
        """Exclui sessões expiradas. Retorno explícito para auditoria."""
        if not self.habilitado or self.retencao_dias <= 0:
            return {"removidas": 0, "retencao_dias": self.retencao_dias}
        corte = (
            datetime.now(timezone.utc) - timedelta(days=self.retencao_dias)
        ).isoformat(timespec="milliseconds")
        with self._conectar() as conn:
            cur = conn.execute("DELETE FROM sessoes WHERE atualizada_em < ?", (corte,))
            removidas = cur.rowcount
            conn.execute(
                "DELETE FROM eventos WHERE timestamp < ?", (corte,)
            )
        self.registrar_evento("RETENCAO_APLICADA", removidas=removidas)
        return {"removidas": removidas, "retencao_dias": self.retencao_dias}

    def excluir_sessao(self, sessao_id: str) -> bool:
        """Exclusão manual e permanente, registrada em auditoria."""
        with self._conectar() as conn:
            cur = conn.execute("DELETE FROM sessoes WHERE id = ?", (sessao_id,))
            removidas = cur.rowcount
        self.registrar_evento("SESSAO_EXCLUIDA", sessao_id=sessao_id)
        return removidas > 0

    def estatisticas(self) -> Dict[str, int]:
        with self._conectar() as conn:
            return {
                "sessoes": conn.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0],
                "mensagens": conn.execute("SELECT COUNT(*) FROM mensagens").fetchone()[0],
                "eventos": conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0],
            }

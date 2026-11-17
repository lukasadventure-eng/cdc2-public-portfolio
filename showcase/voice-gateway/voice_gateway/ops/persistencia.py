# -*- coding: utf-8 -*-
"""Persistência SQLite das operações (tarefas e trilha de eventos)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .modelos import EventoOperacional, TarefaOperacional


class PersistenciaOperacoes:
    def __init__(self, caminho: Path) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    @contextmanager
    def _conectar(self):
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
                CREATE TABLE IF NOT EXISTS tarefas (
                    id TEXT PRIMARY KEY,
                    descricao TEXT NOT NULL,
                    destino TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    sessao_voz_id TEXT NOT NULL DEFAULT '',
                    sessao_opencode_id TEXT NOT NULL DEFAULT '',
                    estado TEXT NOT NULL,
                    impacto TEXT NOT NULL DEFAULT 'normal',
                    criada_em TEXT NOT NULL,
                    atualizada_em TEXT NOT NULL,
                    resultado TEXT NOT NULL DEFAULT '',
                    erro TEXT NOT NULL DEFAULT '',
                    confirmada_por TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tarefas_atualizada
                    ON tarefas(atualizada_em DESC);
                CREATE TABLE IF NOT EXISTS eventos (
                    id TEXT PRIMARY KEY,
                    tarefa_id TEXT NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
                    tipo TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT '',
                    mensagem TEXT NOT NULL DEFAULT '',
                    dados TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_eventos_tarefa
                    ON eventos(tarefa_id, timestamp);
                """
            )

    def salvar_tarefa(self, tarefa: TarefaOperacional) -> None:
        with self._conectar() as conn:
            conn.execute(
                """INSERT INTO tarefas
                   (id, descricao, destino, origem, sessao_voz_id, sessao_opencode_id,
                    estado, impacto, criada_em, atualizada_em, resultado, erro,
                    confirmada_por)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    sessao_opencode_id=excluded.sessao_opencode_id,
                    estado=excluded.estado, atualizada_em=excluded.atualizada_em,
                    resultado=excluded.resultado, erro=excluded.erro,
                    confirmada_por=excluded.confirmada_por""",
                (
                    tarefa.id, tarefa.descricao, tarefa.destino, tarefa.origem,
                    tarefa.sessao_voz_id, tarefa.sessao_opencode_id,
                    tarefa.estado.value, tarefa.impacto, tarefa.criada_em,
                    tarefa.atualizada_em, tarefa.resultado, tarefa.erro,
                    tarefa.confirmada_por,
                ),
            )

    def salvar_evento(self, evento: EventoOperacional) -> None:
        with self._conectar() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO eventos
                   (id, tarefa_id, tipo, timestamp, estado, mensagem, dados)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    evento.id, evento.tarefa_id, evento.tipo, evento.timestamp,
                    evento.estado, evento.mensagem,
                    json.dumps(evento.dados, ensure_ascii=False, default=str),
                ),
            )

    def carregar_tarefa(self, tarefa_id: str) -> Optional[TarefaOperacional]:
        with self._conectar() as conn:
            linha = conn.execute(
                "SELECT * FROM tarefas WHERE id = ?", (tarefa_id,)
            ).fetchone()
            if linha is None:
                return None
            tarefa = TarefaOperacional(
                id=linha["id"],
                descricao=linha["descricao"],
                destino=linha["destino"],
                origem=linha["origem"],
                sessao_voz_id=linha["sessao_voz_id"],
                sessao_opencode_id=linha["sessao_opencode_id"],
                estado=linha["estado"],
                impacto=linha["impacto"],
                criada_em=linha["criada_em"],
                atualizada_em=linha["atualizada_em"],
                resultado=linha["resultado"],
                erro=linha["erro"],
                confirmada_por=linha["confirmada_por"],
            )
            for linha_evento in conn.execute(
                "SELECT * FROM eventos WHERE tarefa_id = ? ORDER BY timestamp",
                (tarefa_id,),
            ):
                tarefa.eventos.append(
                    EventoOperacional(
                        id=linha_evento["id"],
                        tarefa_id=linha_evento["tarefa_id"],
                        tipo=linha_evento["tipo"],
                        timestamp=linha_evento["timestamp"],
                        estado=linha_evento["estado"],
                        mensagem=linha_evento["mensagem"],
                        dados=json.loads(linha_evento["dados"] or "{}"),
                    )
                )
            return tarefa

    def listar_tarefas(self, limite: int = 30) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            return [
                dict(linha)
                for linha in conn.execute(
                    "SELECT * FROM tarefas ORDER BY atualizada_em DESC LIMIT ?",
                    (limite,),
                )
            ]

    def listar_eventos(self, limite: int = 100) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            return [
                dict(linha)
                for linha in conn.execute(
                    "SELECT * FROM eventos ORDER BY timestamp DESC LIMIT ?",
                    (limite,),
                )
            ]

    def estatisticas(self) -> Dict[str, int]:
        with self._conectar() as conn:
            return {
                "tarefas": conn.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0],
                "eventos": conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0],
                "em_execucao": conn.execute(
                    "SELECT COUNT(*) FROM tarefas WHERE estado IN ('em_execucao','sessao_iniciada','confirmada')"
                ).fetchone()[0],
            }

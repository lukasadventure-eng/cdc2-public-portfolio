# -*- coding: utf-8 -*-
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core.history import Historico
from ..models import Mensagem, Sessao


class TestHistorico(unittest.TestCase):
    def test_salvar_carregar_e_listar(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Historico(Path(tmp) / "h.db", retencao_dias=0)
            s = Sessao(id="s1", agente_id="salomao", voz_id="v1")
            s.adicionar(Mensagem(id="m1", remetente="usuario", conteudo="olá"))
            s.adicionar(Mensagem(id="m2", remetente="agente", conteudo="oi"))
            h.salvar_sessao(s)

            carregada = h.carregar_sessao("s1")
            self.assertIsNotNone(carregada)
            self.assertEqual(len(carregada.mensagens), 2)
            self.assertEqual(carregada.voz_id, "v1")
            lista = h.listar_sessoes()
            self.assertEqual(len(lista), 1)
            self.assertEqual(lista[0]["mensagens"], 2)

    def test_idempotencia_e_exclusao(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Historico(Path(tmp) / "h.db")
            s = Sessao(id="s2", agente_id="cdc")
            s.adicionar(Mensagem(id="m1", remetente="usuario", conteudo="teste"))
            h.salvar_sessao(s)
            h.salvar_sessao(s)
            self.assertEqual(h.estatisticas()["mensagens"], 1)
            self.assertTrue(h.excluir_sessao("s2"))
            self.assertIsNone(h.carregar_sessao("s2"))

    def test_retencao(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Historico(Path(tmp) / "h.db", retencao_dias=1)
            antiga = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            with h._conectar() as conn:
                conn.execute(
                    """INSERT INTO sessoes
                       (id, agente_id, criada_em, atualizada_em)
                       VALUES ('antiga', 'cdc', ?, ?)""",
                    (antiga, antiga),
                )
            resultado = h.aplicar_retencao()
            self.assertGreaterEqual(resultado["removidas"], 1)

    def test_desabilitado_nao_grava(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Historico(Path(tmp) / "h.db", habilitado=False)
            h.salvar_sessao(Sessao(id="x", agente_id="cdc"))
            self.assertEqual(h.estatisticas()["sessoes"], 0)


if __name__ == "__main__":
    unittest.main()

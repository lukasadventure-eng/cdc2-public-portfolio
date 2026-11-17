# -*- coding: utf-8 -*-
"""Persistência e isolamento de contexto entre sessões e agentes."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from ..config import AgenteConfig, config_padrao
from ..core.gateway import VoiceGateway


def cfg_teste():
    cfg = config_padrao()
    cfg.agentes = [
        AgenteConfig(id="salomao", nome="Salomão", descricao="",
                     adaptador="contexto", voz="v1"),
        AgenteConfig(id="cdc", nome="CDC", descricao="",
                     adaptador="echo", voz="v2"),
    ]
    cfg.agente_padrao = "salomao"
    cfg.historico.retencao_dias = 0
    return cfg


class TestPersistenciaContexto(unittest.TestCase):
    def test_sessoes_sobrevivem_a_nova_instancia(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                primeiro = VoiceGateway(cfg_teste(), Path(tmp))
                s1 = primeiro.obter_sessao(agente_id="salomao")
                s2 = primeiro.obter_sessao(agente_id="cdc")
                await primeiro.processar_texto(s1.id, "segredo do salomao", "voz")
                await primeiro.processar_texto(s2.id, "estado do cdc", "texto")

                segundo = VoiceGateway(cfg_teste(), Path(tmp))
                carregada1 = segundo.obter_sessao(s1.id)
                carregada2 = segundo.obter_sessao(s2.id)
                self.assertEqual(carregada1.agente_id, "salomao")
                self.assertEqual(carregada2.agente_id, "cdc")
                textos1 = [m.conteudo for m in carregada1.mensagens]
                textos2 = [m.conteudo for m in carregada2.mensagens]
                self.assertIn("segredo do salomao", textos1)
                self.assertNotIn("estado do cdc", textos1)
                self.assertIn("estado do cdc", textos2)
                self.assertNotIn("segredo do salomao", textos2)
                await primeiro.fechar()
                await segundo.fechar()

        asyncio.run(rodar())

    def test_tarefa_associada_a_conversa_e_recuperavel(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway = VoiceGateway(cfg_teste(), Path(tmp))
            sessao = gateway.obter_sessao()
            tarefa = gateway.gerenciador.criar(
                "desenvolver módulo X", "salomao",
                sessao_voz_id=sessao.id,
            )
            gateway.gerenciador.concluir(tarefa.id, "módulo X pronto")

            outro = VoiceGateway(cfg_teste(), Path(tmp))
            recuperada = outro.gerenciador.obter(tarefa.id)
            self.assertIsNotNone(recuperada)
            self.assertEqual(recuperada.sessao_voz_id, sessao.id)
            self.assertEqual(recuperada.resultado, "módulo X pronto")
            self.assertTrue(any(e.tipo == "tarefa_concluida" for e in recuperada.eventos))
            historico = outro.gerenciador.historico(sessao.id)
            self.assertEqual(len(historico), 1)

    def test_estatisticas_e_auditoria_integra(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway = VoiceGateway(cfg_teste(), Path(tmp))
            gateway.gerenciador.criar("tarefa", "usuario", sessao_voz_id="s1")
            self.assertEqual(gateway.gerenciador.estatisticas()["tarefas"], 1)
            self.assertTrue(gateway.auditoria.verificar())


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Conversação contínua (10 turnos) e interrupção (20 ciclos)."""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from ..config import AgenteConfig, config_padrao
from ..core.gateway import VoiceGateway
from ..ops.modelos import EstadoTarefa


def cfg_teste(adaptador: str = "contexto"):
    cfg = config_padrao()
    cfg.agentes = [
        AgenteConfig(
            id="salomao", nome="Salomão", descricao="",
            adaptador=adaptador, voz="v1",
        ),
        AgenteConfig(id="cdc", nome="CDC", descricao="", adaptador="echo", voz="v2"),
    ]
    cfg.agente_padrao = "salomao"
    cfg.operacoes.timeout_sec = 2
    return cfg


class TestConversacaoContínua(unittest.TestCase):
    def test_dez_interacoes_sem_reiniciar_sessao(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                for indice in range(10):
                    origem = "voz" if indice % 2 == 0 else "texto"
                    await gw.processar_texto(
                        sessao.id, f"pergunta {indice + 1}", origem=origem
                    )
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                respostas = [e for e in eventos if e["type"] == "answer"]
                self.assertEqual(len(respostas), 10)
                for indice, resposta in enumerate(respostas):
                    self.assertIn(f"Turno {indice + 1}", resposta["texto"])
                self.assertTrue(all(e.get("agente") == "salomao" for e in respostas))

                # Sem duplicação: um transcript final por turno.
                transcripts = [
                    e for e in eventos
                    if e["type"] == "transcript" and e.get("final")
                ]
                self.assertEqual(len(transcripts), 10)

                recarregada = gw.historico.carregar_sessao(sessao.id)
                self.assertIsNotNone(recarregada)
                self.assertEqual(len(recarregada.mensagens), 20)
                self.assertEqual(recarregada.agente_id, "salomao")
                await gw.fechar()

        asyncio.run(rodar())

    def test_alternancia_voz_texto_preserva_contexto(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                await gw.processar_texto(sessao.id, "primeira", origem="voz")
                await gw.processar_texto(sessao.id, "segunda?", origem="texto")
                historico = gw.obter_sessao(sessao.id).mensagens
                self.assertEqual(
                    [m.origem for m in (historico[0], historico[2])],
                    ["voz", "texto"],
                )
                self.assertEqual(historico[0].conteudo, "primeira")
                self.assertEqual(historico[2].conteudo, "segunda?")
                await gw.fechar()

        asyncio.run(rodar())


class TestInterrupcaoVinetes(unittest.TestCase):
    def test_vinte_interrupcoes_consecutivas(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))
                sessao = gw.obter_sessao()

                async def lento(texto, contexto, cancelamento):
                    for indice in range(200):
                        if cancelamento.is_set():
                            return
                        yield f"token {indice}"
                        await asyncio.sleep(0.02)

                gw.adaptadores["salomao"].responder = lento
                interrompidas = 0
                for _ in range(20):
                    fila = gw.bus.subscribe(sessao.id)
                    tarefa = gw.iniciar_turno(
                        sessao.id, "conte uma história longa sobre o mar"
                    )
                    await asyncio.sleep(0.04)
                    inicio = time.monotonic()
                    if gw.interromper(sessao.id):
                        interrompidas += 1
                    try:
                        await tarefa
                    except asyncio.CancelledError:
                        pass
                    total = (time.monotonic() - inicio) * 1000
                    gw.registrar_interrupcao(sessao.id, 0.5, total)
                    eventos = []
                    while not fila.empty():
                        eventos.append(fila.get_nowait())
                    self.assertTrue(
                        any(e["type"] == "interrompido" for e in eventos)
                    )
                    self.assertFalse(any(e["type"] == "answer" for e in eventos))
                    gw.bus.unsubscribe(sessao.id, fila)

                self.assertEqual(interrompidas, 20)
                resumo = gw.metricas.resumo(sessao.id)
                self.assertEqual(
                    resumo["por_tipo"]["interrupcao_total"]["n"], 20
                )
                self.assertEqual(
                    resumo["por_tipo"]["interrupcao_deteccao"]["n"], 20
                )
                self.assertEqual(
                    gw.obter_sessao(sessao.id).agente_id, "salomao"
                )
                await gw.fechar()

        asyncio.run(rodar())


if __name__ == "__main__":
    unittest.main()

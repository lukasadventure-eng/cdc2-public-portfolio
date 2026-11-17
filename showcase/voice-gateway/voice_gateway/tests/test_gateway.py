# -*- coding: utf-8 -*-
import asyncio
import tempfile
import unittest
from pathlib import Path

from ..config import AgenteConfig, config_padrao
from ..core.gateway import VoiceGateway
from ..models import EstadoTurno


def config_teste() -> object:
    cfg = config_padrao()
    cfg.agentes = [
        AgenteConfig(
            id="salomao", nome="Salomão", descricao="teste",
            adaptador="echo", voz="voz-salomao",
        ),
        AgenteConfig(
            id="cdc", nome="CDC", descricao="teste",
            adaptador="echo", voz="voz-cdc",
        ),
    ]
    cfg.agente_padrao = "salomao"
    cfg.seguranca.max_texto_chars = 100
    return cfg


class TestGateway(unittest.TestCase):
    def test_turno_completo_e_eventos(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(config_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                await gw.processar_texto(sessao.id, "olá gateway")
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                tipos = [e["type"] for e in eventos]
                self.assertIn("transcript", tipos)
                self.assertIn("routing", tipos)
                self.assertIn("token", tipos)
                self.assertIn("answer", tipos)
                roteamento = next(e for e in eventos if e["type"] == "routing")
                self.assertEqual(roteamento["agente"], "salomao")
                resposta = next(e for e in eventos if e["type"] == "answer")
                self.assertIn("Echo (salomao)", resposta["texto"])
                self.assertEqual(resposta["voz"], "salomao-ptbr")
                self.assertEqual(len(gw.obter_sessao(sessao.id).mensagens), 2)
                await gw.fechar()

        asyncio.run(rodar())

    def test_roteamento_para_cdc(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(config_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                await gw.processar_texto(sessao.id, "status da auditoria do CDC")
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                roteamento = next(e for e in eventos if e["type"] == "routing")
                self.assertEqual(roteamento["agente"], "cdc")
                answer = next(e for e in eventos if e["type"] == "answer")
                self.assertEqual(answer["voz"], "cdc-ptbr")
                await gw.fechar()

        asyncio.run(rodar())

    def test_interrupcao_barge_in(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(config_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)

                async def lento(texto, contexto, cancelamento):
                    for i in range(20):
                        if cancelamento.is_set():
                            return
                        yield f"parte {i}"
                        await asyncio.sleep(0.02)

                gw.adaptadores["salomao"].responder = lento
                tarefa = gw.iniciar_turno(sessao.id, "fale por favor")
                await asyncio.sleep(0.06)
                self.assertTrue(gw.interromper(sessao.id))
                with self.assertRaises(asyncio.CancelledError):
                    await tarefa
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                self.assertIn("interrompido", [e["type"] for e in eventos])
                self.assertIn("stop_speech", [e["type"] for e in eventos])
                await gw.fechar()

        asyncio.run(rodar())

    def test_texto_invalido_gera_erro(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(config_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                await gw.processar_texto(sessao.id, "x" * 500)
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                self.assertTrue(any(e["type"] == "erro" for e in eventos))
                await gw.fechar()

        asyncio.run(rodar())

    def test_stt_navegador_nao_aceita_audio(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(config_teste(), Path(tmp))
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                self.assertIsNone(await gw.processar_audio(sessao.id, b"audio"))
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                self.assertTrue(any(e["type"] == "erro" for e in eventos))
                await gw.fechar()

        asyncio.run(rodar())

    def test_estado_interrompido_existe(self):
        self.assertEqual(EstadoTurno.INTERROMPIDO, "interrompido")


if __name__ == "__main__":
    unittest.main()

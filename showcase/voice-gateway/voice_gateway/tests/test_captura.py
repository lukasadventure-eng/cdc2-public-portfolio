# -*- coding: utf-8 -*-
import asyncio
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ..audio.captura import CapturadorServidor
from ..config import config_padrao
from ..core.gateway import VoiceGateway


class TestCapturaServidor(unittest.TestCase):
    def test_pcm16_e_rms(self):
        bloco = np.zeros((1024, 1), dtype=np.float32)
        bloco[:, 0] = 0.25
        pcm, rms = CapturadorServidor._bloco_a_pcm16(bloco)
        self.assertEqual(len(pcm), 2048)
        self.assertAlmostEqual(rms, 0.25, places=3)

    def test_vad_adaptativo(self):
        capturador = CapturadorServidor(limiar=0.005, adaptativo=True,
                                        multiplicador_ruido=3.0, limiar_minimo=0.004)
        for _ in range(30):
            limiar = capturador.atualizar_ruido(0.0003)
        self.assertAlmostEqual(limiar, 0.004, places=4)
        for _ in range(80):
            limiar = capturador.atualizar_ruido(0.02)
        self.assertGreater(limiar, 0.004)

    def test_dispositivos(self):
        dispositivos = CapturadorServidor.dispositivos()
        self.assertIsInstance(dispositivos, list)

    def test_voz_por_agente(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config_padrao()
            gw = VoiceGateway(cfg, Path(tmp))
            self.assertEqual(gw.voz_para_agente("salomao"), "salomao-ptbr")
            self.assertEqual(gw.voz_para_agente("cdc"), "cdc-ptbr")
            self.assertEqual(gw.voz_para_agente("opencode"), "opencode-ptbr")

    def test_captura_com_wake(self):
        from .test_wake import STTLocalFalso, cfg_teste as cfg_wake

        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = cfg_wake()
                cfg.wake.habilitado = True
                gw = VoiceGateway(cfg, Path(tmp))
                gw.stt = STTLocalFalso(cfg.stt)
                # Adiciona executor para o agente destino.
                async def executor(tarefa, manager, cancelamento):
                    return "ok"
                gw.gerenciador.definir_executor(executor, "salomao")
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                await gw.processar_captura(sessao.id, b"pcm")
                tarefa = gw._turnos.get(sessao.id)
                if tarefa:
                    await tarefa
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                tipos = [e["type"] for e in eventos]
                self.assertIn("wake_detected", tipos)
                roteamento = next(e for e in eventos if e["type"] == "routing")
                self.assertEqual(roteamento["agente"], "salomao")
                await gw.fechar()

        asyncio.run(rodar())

    def test_captura_com_stt_falso(self):
        from .test_wake import STTLocalFalso, cfg_teste as cfg_wake

        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = cfg_wake()
                cfg.captura.modo = "servidor"
                gw = VoiceGateway(cfg, Path(tmp))
                gw.stt = STTLocalFalso(cfg.stt)
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                estado = gw.iniciar_captura(sessao.id)
                self.assertEqual(estado["modo"], "servidor")
                gw.parar_captura(sessao.id)
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                self.assertTrue(any(e["type"] == "listening" for e in eventos))
                await gw.fechar()

        asyncio.run(rodar())


if __name__ == "__main__":
    unittest.main()

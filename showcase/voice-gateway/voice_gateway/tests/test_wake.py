# -*- coding: utf-8 -*-
import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from ..config import AgenteConfig, config_padrao
from ..core.gateway import VoiceGateway
from ..core.metricas import Metricas
from ..main import criar_app
from ..stt.base import STTProvider
from ..wake.detector import WakeWordDetector


class TestDetector(unittest.TestCase):
    def test_desligado_nao_detecta(self):
        d = WakeWordDetector(habilitado=False)
        self.assertIsNone(d.detectar("Salomão"))
        self.assertEqual(d.estado()["deteccoes"], 0)

    def test_ativacao_com_acento_e_sem(self):
        d = WakeWordDetector(habilitado=True)
        self.assertIsNotNone(d.detectar("Salomão"))
        d2 = WakeWordDetector(habilitado=True)
        self.assertIsNotNone(d2.detectar("salomao, execute"))

    def test_variacao_asr_salumao(self):
        d = WakeWordDetector(habilitado=True)
        deteccao = d.detectar("Salumão")
        self.assertIsNotNone(deteccao)
        self.assertEqual(deteccao.palavra, "salomao")

    def test_desativacao(self):
        d = WakeWordDetector(habilitado=True)
        self.assertIsNotNone(d.detectar("Salomão"))
        d.desativar()
        self.assertIsNone(d.detectar("Salomão"))
        self.assertEqual(d.estado()["desativacoes"], 1)

    def test_alternar(self):
        d = WakeWordDetector(habilitado=False)
        self.assertTrue(d.alternar())
        self.assertFalse(d.alternar())

    def test_cooldown_e_falsas_ativacoes(self):
        d = WakeWordDetector(habilitado=True, cooldown_s=30)
        self.assertIsNotNone(d.detectar("Salomão"))
        self.assertIsNone(d.detectar("Salomão"))  # cooldown
        self.assertIsNone(d.detectar("ruído aleatório sem palavra"))
        self.assertIsNone(d.detectar("x" * 200))  # texto longo

    def test_contadores(self):
        d = WakeWordDetector(habilitado=False)
        d.ativar()
        d.desativar()
        d.ativar()
        estado = d.estado()
        self.assertEqual(estado["ativacoes"], 2)
        self.assertEqual(estado["desativacoes"], 1)


class STTLocalFalso(STTProvider):
    id = "local_falso"
    nome = "STT local de teste"

    def descricao(self) -> str:
        return "simula apenas a interface local"

    @property
    def transcreve_no_servidor(self) -> bool:
        return True

    async def transcrever(self, audio, idioma=None):
        return "Salomão"


def cfg_teste():
    cfg = config_padrao()
    cfg.agentes = [
        AgenteConfig(id="salomao", nome="Salomão", descricao="", adaptador="echo", voz="v"),
        AgenteConfig(id="cdc", nome="CDC", descricao="", adaptador="echo", voz="v"),
        AgenteConfig(id="opencode", nome="OpenCode", descricao="", adaptador="echo", voz="v"),
    ]
    cfg.agente_padrao = "salomao"
    return cfg


class TestIntegracaoWake(unittest.TestCase):
    def test_browser_stt_nao_permite_wake(self):
        with tempfile.TemporaryDirectory() as tmp:
            gw = VoiceGateway(cfg_teste(), Path(tmp))
            with self.assertRaises(ValueError):
                gw.ativar_wake()
            self.assertFalse(gw.estado_wake()["pode_ativar"])

    def test_wake_com_stt_local_emite_deteccao(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))
                gw.stt = STTLocalFalso(cfg_teste().stt)
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                gw.ativar_wake(sessao.id)
                await gw.processar_wake_audio(sessao.id, b"pcm")
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                tipos = [e["type"] for e in eventos]
                self.assertIn("wake_estado", tipos)
                self.assertIn("wake_detected", tipos)
                self.assertIn("stt", [a.tipo for a in gw.metricas._amostras])
                await gw.fechar()

        asyncio.run(rodar())

    def test_api_wake(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                app = criar_app(cfg_teste(), "tok", Path(tmp))
                headers = {"Authorization": "Bearer tok"}
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as cliente:
                    r = await cliente.get("/api/wake", headers=headers)
                    self.assertEqual(r.status_code, 200)
                    self.assertFalse(r.json()["pode_ativar"])
                    r = await cliente.post("/api/wake/ativar", headers=headers)
                    self.assertEqual(r.status_code, 409)
                    r = await cliente.post("/api/wake/desativar", headers=headers)
                    self.assertEqual(r.status_code, 200)

        asyncio.run(rodar())


class TestMetricas(unittest.TestCase):
    def test_resumo_por_tipo(self):
        m = Metricas()
        for valor in (10.0, 20.0, 30.0, 100.0):
            m.registrar("interrupcao_total", valor, "s1")
        m.registrar("stt", 5.0, "s2")
        resumo = m.resumo("s1")
        self.assertEqual(resumo["por_tipo"]["interrupcao_total"]["n"], 4)
        self.assertEqual(resumo["por_tipo"]["interrupcao_total"]["p50"], 25)
        self.assertEqual(resumo["por_tipo"]["interrupcao_total"]["max"], 100)
        self.assertNotIn("stt", resumo["por_tipo"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

from ..agents.registry import criar_agente
from ..audio.wav import pcm_para_wav
from ..config import Config, carregar_config, config_padrao
from ..stt.registry import criar_stt
from ..tts.registry import criar_tts


class TestConfig(unittest.TestCase):
    def test_config_padrao_tem_tres_agentes(self):
        cfg = config_padrao()
        self.assertEqual([a.id for a in cfg.agentes], ["salomao", "cdc", "opencode"])
        self.assertIsNotNone(cfg.agente("cdc"))

    def test_variaveis_de_ambiente(self):
        os.environ["VOICE_GATEWAY_STT_PROVEDOR"] = "local"
        os.environ["VOICE_GATEWAY_TTS_PROVEDOR"] = "local"
        os.environ["VOICE_GATEWAY_PORT"] = "9999"
        try:
            cfg = carregar_config()
            self.assertEqual(cfg.stt.provedor, "local")
            self.assertEqual(cfg.tts.provedor, "local")
            self.assertEqual(cfg.servidor.port, 9999)
        finally:
            for k in ("VOICE_GATEWAY_STT_PROVEDOR", "VOICE_GATEWAY_TTS_PROVEDOR",
                      "VOICE_GATEWAY_PORT"):
                os.environ.pop(k, None)


    def test_config_legada_exige_opt_in(self):
        from .. import config as cfg_mod

        dados = {
            "agente_padrao": "salomao",
            "agentes": [{
                "id": "opencode", "nome": "OpenCode", "descricao": "",
                "adaptador": "opencode", "voz": "v", "cor": "#fff",
                "ativo": True,
                "opcoes": {"comando": "opencode", "modo": "consulta"},
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(json.dumps(dados), encoding="utf-8")
            original = cfg_mod.ARQUIVO_CONFIG
            cfg_mod.ARQUIVO_CONFIG = caminho
            os.environ.pop("VOICE_GATEWAY_ENABLE_EXECUCAO", None)
            try:
                cfg = cfg_mod.carregar_config()
                self.assertEqual(cfg.agente("opencode").opcoes["modo"], "consulta")
                self.assertTrue(cfg_mod.AVISO_CONFIG_LEGADA)

                os.environ["VOICE_GATEWAY_ENABLE_EXECUCAO"] = "1"
                cfg2 = cfg_mod.carregar_config()
                self.assertEqual(cfg2.agente("opencode").opcoes["modo"], "execucao")
            finally:
                cfg_mod.ARQUIVO_CONFIG = original
                os.environ.pop("VOICE_GATEWAY_ENABLE_EXECUCAO", None)


class TestRegistros(unittest.TestCase):
    def test_agentes(self):
        cfg = config_padrao()
        self.assertEqual(type(criar_agente(cfg, "salomao")).__name__, "SalomaoAdapter")
        self.assertEqual(type(criar_agente(cfg, "cdc")).__name__, "CDCAdapter")
        self.assertEqual(type(criar_agente(cfg, "opencode")).__name__, "OpenCodeAdapter")

    def test_stt_tts_padrao_sao_navegador(self):
        cfg = config_padrao()
        stt = criar_stt(cfg)
        tts = criar_tts(cfg)
        self.assertEqual(stt.id, "browser")
        self.assertFalse(stt.transcreve_no_servidor)
        self.assertEqual(tts.id, "browser")
        self.assertFalse(tts.sintetiza_no_servidor)

    def test_provedor_local(self):
        cfg = config_padrao()
        cfg.stt.provedor = "local"
        cfg.tts.provedor = "local"
        self.assertEqual(criar_stt(cfg).id, "local")
        self.assertEqual(criar_tts(cfg).id, "local")


class TestWav(unittest.TestCase):
    def test_cabecalho_riff(self):
        pcm = struct.pack("<4h", 0, 1000, -1000, 500)
        wav = pcm_para_wav(pcm, 16000, 1, 16)
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(wav[36:40], b"data")
        self.assertEqual(struct.unpack("<I", wav[40:44])[0], len(pcm))
        self.assertTrue(wav.endswith(pcm))

    def test_vazio(self):
        self.assertEqual(pcm_para_wav(b""), b"")


if __name__ == "__main__":
    unittest.main()

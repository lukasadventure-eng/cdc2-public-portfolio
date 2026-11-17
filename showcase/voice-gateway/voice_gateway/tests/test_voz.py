# -*- coding: utf-8 -*-
import io
import tempfile
import unittest
import wave
from pathlib import Path

from ..voz.perfil import CONSENTIMENTO_FRASE, RegistroVoz


def wav_teste() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 2000)
    return buf.getvalue()


class TestRegistroVoz(unittest.TestCase):
    def test_sem_consentimento_nao_registra(self):
        with tempfile.TemporaryDirectory() as tmp:
            registro = RegistroVoz(Path(tmp))
            with self.assertRaises(PermissionError):
                registro.registrar("Salomão", "salomao", wav_teste(), "sim")
            self.assertEqual(registro.listar(), [])

    def test_registro_e_exclusao(self):
        with tempfile.TemporaryDirectory() as tmp:
            registro = RegistroVoz(Path(tmp))
            perfil = registro.registrar(
                "Salomão", "salomao", wav_teste(), CONSENTIMENTO_FRASE
            )
            self.assertEqual(perfil.agente_id, "salomao")
            self.assertEqual(len(registro.listar()), 1)
            self.assertTrue((Path(tmp) / perfil.arquivo).exists())
            self.assertTrue(registro.excluir(perfil.id))
            self.assertFalse((Path(tmp) / perfil.arquivo).exists())
            self.assertEqual(registro.estado()["perfis"], 0)


if __name__ == "__main__":
    unittest.main()

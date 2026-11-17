# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path

from ..security.audit import AuditTrail
from ..security.auth import AuthManager, RateLimiter


class TestAuth(unittest.TestCase):
    def test_token_valido_e_invalido(self):
        auth = AuthManager("segredo", True)
        self.assertTrue(auth.validar("segredo"))
        self.assertFalse(auth.validar("errado"))
        self.assertFalse(auth.validar(None))

    def test_token_vazio_desativa_exigencia(self):
        auth = AuthManager("", True)
        self.assertTrue(auth.validar(None))

    def test_token_publico_nao_vaza(self):
        auth = AuthManager("segredo", True)
        self.assertNotIn("segredo", auth.token_publico())

    def test_rate_limiter(self):
        r = RateLimiter(2, 60)
        self.assertTrue(r.permitir(100))
        self.assertTrue(r.permitir(101))
        self.assertFalse(r.permitir(102))
        self.assertTrue(r.permitir(161))


class TestAuditoria(unittest.TestCase):
    def test_corrente_e_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "auditoria.jsonl"
            trilha = AuditTrail(caminho)
            trilha.registrar("EVENTO_A", sessao="s1")
            trilha.registrar("EVENTO_B", sessao="s2")
            self.assertTrue(trilha.verificar())

            linhas = caminho.read_text(encoding="utf-8").splitlines()
            objeto = json.loads(linhas[0])
            objeto["detalhes"]["sessao"] = " adulterado"
            linhas[0] = json.dumps(objeto, ensure_ascii=False)
            caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            self.assertFalse(trilha.verificar())

    def test_segredos_sao_removidos(self):
        with tempfile.TemporaryDirectory() as tmp:
            trilha = AuditTrail(Path(tmp) / "a.jsonl")
            trilha.registrar(
                "TESTE", token="abc123", chave_api="xyz", audio="dados", sessao="s1"
            )
            conteudo = (Path(tmp) / "a.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("abc123", conteudo)
            self.assertNotIn("xyz", conteudo)
            self.assertNotIn("dados", conteudo)
            self.assertIn("s1", conteudo)


if __name__ == "__main__":
    unittest.main()

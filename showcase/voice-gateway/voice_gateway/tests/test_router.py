# -*- coding: utf-8 -*-
import unittest

from ..core.router import AgentRouter, normalizar


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = AgentRouter(["salomao", "cdc", "opencode"], "salomao")

    def test_normalizacao_ptbr(self):
        self.assertEqual(normalizar("Salomão, AÇÃO"), "salomao, acao")

    def test_selecao_explicita_vence(self):
        d = self.router.route("olá", agente_explicito="cdc")
        self.assertEqual(d.agente_id, "cdc")
        self.assertTrue(d.explicito)

    def test_comando_de_voz_explicito(self):
        for texto, esperado in [
            ("Falar com o CDC", "cdc"),
            ("chame o salomão", "salomao"),
            ("usar o codex", "opencode"),
            ("agente cdc", "cdc"),
        ]:
            with self.subTest(texto=texto):
                d = self.router.route(texto)
                self.assertEqual(d.agente_id, esperado)
                self.assertTrue(d.explicito)

    def test_automatico_cdc(self):
        d = self.router.route("mostre o status da auditoria do CDC")
        self.assertEqual(d.agente_id, "cdc")
        self.assertFalse(d.explicito)

    def test_automatico_tarefa_sal(self):
        d = self.router.route("verifique a tarefa SAL-123")
        self.assertEqual(d.agente_id, "cdc")

    def test_automatico_opencode(self):
        d = self.router.route("implemente um teste unitário no opencode")
        self.assertEqual(d.agente_id, "opencode")

    def test_padrao_quando_neutro(self):
        d = self.router.route("como vai?")
        self.assertEqual(d.agente_id, "salomao")

    def test_vazio(self):
        d = self.router.route("   ")
        self.assertEqual(d.agente_id, "salomao")

    def test_agente_desconhecido_cai_no_padrao(self):
        d = self.router.route("oi", agente_explicito="inexistente")
        self.assertEqual(d.agente_id, "salomao")


if __name__ == "__main__":
    unittest.main()

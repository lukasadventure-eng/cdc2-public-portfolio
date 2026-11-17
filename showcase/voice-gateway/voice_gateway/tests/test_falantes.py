# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

import httpx

from ..config import config_padrao
from ..main import criar_app
from ..speakers.servico import (
    IdentificadorFalante,
    ServicoFalantes,
)


class IdentificadorFalso(IdentificadorFalante):
    nome = "falso"
    disponivel = True

    def __init__(self, alvo):
        self.alvo = alvo

    def identificar(self, amostra):
        return self.alvo


class TestServicoFalantes(unittest.TestCase):
    def test_consentimento_obrigatorio(self):
        with tempfile.TemporaryDirectory() as tmp:
            servico = ServicoFalantes(Path(tmp) / "f.db")
            with self.assertRaises(PermissionError):
                servico.criar("Sem consentimento", False)
            self.assertEqual(servico.listar(), [])

    def test_ciclo_criar_amostra_excluir(self):
        with tempfile.TemporaryDirectory() as tmp:
            servico = ServicoFalantes(Path(tmp) / "f.db")
            perfil = servico.criar("Lucas", True)
            self.assertEqual(perfil.consentimento, True)
            self.assertTrue(servico.registrar_amostra(perfil.id))
            self.assertEqual(
                servico.obter(perfil.id).amostras_autorizadas, 1
            )
            self.assertEqual(len(servico.listar()), 1)
            self.assertTrue(servico.excluir(perfil.id))
            self.assertIsNone(servico.obter(perfil.id))

    def test_identificacao_indisponivel_tem_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            servico = ServicoFalantes(Path(tmp) / "f.db")
            perfil = servico.criar("Lucas", True)
            self.assertIsNone(servico.identificar(b"audio"))  # fallback
            estado = servico.estado()
            self.assertFalse(estado["disponivel"])
            self.assertFalse(estado["usado_para_autorizacao"])

    def test_identificador_pluggable(self):
        with tempfile.TemporaryDirectory() as tmp:
            servico = ServicoFalantes(Path(tmp) / "f.db")
            perfil = servico.criar("Lucas", True)
            servico.identificador = IdentificadorFalso(perfil.id)
            identificado = servico.identificar(b"audio")
            self.assertIsNotNone(identificado)
            self.assertEqual(identificado.nome, "Lucas")


class TestAPIFalantes(unittest.TestCase):
    def test_endpoints_e_notificacoes(self):
        import asyncio

        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                app = criar_app(config_padrao(), "tok", Path(tmp))
                headers = {"Authorization": "Bearer tok"}
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as cliente:
                    r = await cliente.get("/api/falantes", headers=headers)
                    self.assertEqual(r.status_code, 200)
                    self.assertFalse(
                        r.json()["estado"]["usado_para_autorizacao"]
                    )

                    r = await cliente.post(
                        "/api/falantes", headers=headers,
                        json={"nome": "Ana", "consentimento": False},
                    )
                    self.assertEqual(r.status_code, 403)

                    r = await cliente.post(
                        "/api/falantes", headers=headers,
                        json={"nome": "Ana", "consentimento": True},
                    )
                    self.assertEqual(r.status_code, 200)
                    perfil_id = r.json()["id"]

                    r = await cliente.delete(
                        f"/api/falantes/{perfil_id}", headers=headers
                    )
                    self.assertTrue(r.json()["removido"])

                    r = await cliente.get(
                        "/api/notificacoes", headers=headers
                    )
                    self.assertFalse(r.json()["silenciada"])
                    r = await cliente.post(
                        "/api/notificacoes", headers=headers,
                        json={"silenciada": True},
                    )
                    self.assertTrue(r.json()["silenciada"])

        asyncio.run(rodar())


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

import httpx

from ..config import AgenteConfig, config_padrao
from ..main import criar_app


def cfg_teste():
    cfg = config_padrao()
    cfg.agentes = [
        AgenteConfig(id="salomao", nome="Salomão", descricao="", adaptador="echo", voz="v1"),
        AgenteConfig(id="cdc", nome="CDC", descricao="", adaptador="echo", voz="v2"),
    ]
    cfg.agente_padrao = "salomao"
    return cfg


class TestAPI(unittest.TestCase):
    def test_health_e_autorizacao(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                app = criar_app(cfg_teste(), "tok", Path(tmp))
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as cliente:
                    r = await cliente.get("/health")
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(r.json()["status"], "ok")
                    self.assertNotIn("tok", r.text)

                    r = await cliente.get("/api/agentes")
                    self.assertEqual(r.status_code, 401)

                    r = await cliente.get(
                        "/api/agentes", headers={"Authorization": "Bearer tok"}
                    )
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(len(r.json()), 2)

        import asyncio
        asyncio.run(rodar())

    def test_falar_e_interromper(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                app = criar_app(cfg_teste(), "tok", Path(tmp))
                transport = httpx.ASGITransport(app=app)
                headers = {"Authorization": "Bearer tok"}
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as cliente:
                    r = await cliente.post(
                        "/api/falar",
                        headers=headers,
                        json={"texto": "olá", "origem": "texto"},
                    )
                    self.assertEqual(r.status_code, 200)
                    sessao = r.json()["sessao"]
                    self.assertTrue(sessao)

                    r = await cliente.post(
                        "/api/interromper", headers=headers, json={"sessao": sessao}
                    )
                    self.assertEqual(r.status_code, 200)

                    r = await cliente.get(
                        f"/api/sessoes/{sessao}", headers=headers
                    )
                    self.assertEqual(r.status_code, 200)

        import asyncio
        asyncio.run(rodar())


if __name__ == "__main__":
    unittest.main()

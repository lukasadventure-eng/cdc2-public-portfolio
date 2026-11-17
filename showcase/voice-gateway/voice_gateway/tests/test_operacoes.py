# -*- coding: utf-8 -*-
import asyncio
import tempfile
import unittest
from pathlib import Path

from ..agents.opencode import OpenCodeAdapter
from ..config import AgenteConfig, config_padrao
from ..core.gateway import VoiceGateway
from ..main import criar_app
from ..ops.comandos import (
    ParserComandos,
    TIPO_CONFIRMAR,
    TIPO_CONTINUAR,
    TIPO_DELEGAR,
    TIPO_ENCAMINHAR_RESPONSAVEL,
    TIPO_EXPLICAR,
    TIPO_INTERROMPER,
    TIPO_NENHUM,
    TIPO_QUAL_AGENTE,
    TIPO_ULTIMO_RESULTADO,
)
from ..ops.gerenciador import GerenciadorOperacoes
from ..ops.modelos import EstadoTarefa
from ..ops.notificacoes import Notificador, PoliticaAnuncios
from ..ops.persistencia import PersistenciaOperacoes

import httpx


def cfg_teste():
    cfg = config_padrao()
    cfg.agentes = [
        AgenteConfig(id="salomao", nome="Salomão", descricao="", adaptador="echo", voz="v1"),
        AgenteConfig(id="cdc", nome="CDC", descricao="", adaptador="echo", voz="v2"),
        AgenteConfig(id="opencode", nome="OpenCode", descricao="", adaptador="echo", voz="v3"),
    ]
    cfg.agente_padrao = "salomao"
    return cfg


class TestParserComandos(unittest.TestCase):
    def setUp(self):
        self.parser = ParserComandos()

    def test_delegar_completo(self):
        i = self.parser.parse(
            "Salomão, solicite ao OpenCode que desenvolva o módulo de autenticação."
        )
        self.assertEqual(i.tipo, TIPO_DELEGAR)
        self.assertEqual(i.emitente, "salomao")
        self.assertEqual(i.destino, "opencode")
        self.assertIn("desenvolva", i.descricao)
        self.assertEqual(i.impacto, "normal")
        self.assertFalse(i.exigir_confirmacao)

    def test_delegar_para_cdc(self):
        i = self.parser.parse("CDC, encaminhe ao agente responsável a tarefa de auditoria")
        self.assertEqual(i.tipo, TIPO_ENCAMINHAR_RESPONSAVEL)

    def test_destrutivo_exige_confirmacao(self):
        i = self.parser.parse("Salomão, peça ao OpenCode para apagar o arquivo temporário")
        self.assertEqual(i.tipo, TIPO_DELEGAR)
        self.assertEqual(i.impacto, "destrutivo")
        self.assertTrue(i.exigir_confirmacao)

    def test_alto_impacto_instalar(self):
        i = self.parser.parse("peça ao OpenCode para instalar a biblioteca")
        self.assertEqual(i.impacto, "alto")

    def test_comandos_simples(self):
        casos = [
            ("Interrompa a execução", TIPO_INTERROMPER),
            ("Continue a execução", TIPO_CONTINUAR),
            ("Confirme", TIPO_CONFIRMAR),
            ("Sim", TIPO_CONFIRMAR),
            ("Leia o último resultado", TIPO_ULTIMO_RESULTADO),
            ("Qual agente está trabalhando?", TIPO_QUAL_AGENTE),
            ("Explique o que está acontecendo", TIPO_EXPLICAR),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(self.parser.parse(texto).tipo, esperado)

    def test_conversa_comum_nao_e_comando(self):
        self.assertEqual(self.parser.parse("Como você está?").tipo, TIPO_NENHUM)


class TestGerenciador(unittest.TestCase):
    def test_ciclo_completo_e_persistencia(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                eventos = []
                g = GerenciadorOperacoes(
                    PersistenciaOperacoes(Path(tmp) / "ops.db"),
                    lambda tarefa_id, tipo, dados: eventos.append(tipo),
                )

                async def executor(tarefa, manager, cancelamento):
                    manager.emitir(tarefa.id, "execucao_em_andamento", "ok")
                    return "resultado final"

                g.definir_executor(executor)
                tarefa = g.criar("criar módulo", "salomao", sessao_voz_id="s1")
                task = g.despachar(tarefa.id)
                await task
                self.assertEqual(g.obter(tarefa.id).estado, EstadoTarefa.CONCLUIDA)
                self.assertEqual(g.obter(tarefa.id).resultado, "resultado final")
                self.assertIn("tarefa_recebida", eventos)
                self.assertIn("tarefa_concluida", eventos)

                recarregada = g.persistencia.carregar_tarefa(tarefa.id)
                self.assertIsNotNone(recarregada)
                self.assertEqual(recarregada.resultado, "resultado final")
                self.assertIn("execucao_em_andamento", [e.tipo for e in recarregada.eventos])

        asyncio.run(rodar())

    def test_confirmacao_bloqueia_despacho(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = GerenciadorOperacoes(
                PersistenciaOperacoes(Path(tmp) / "ops.db"), lambda *_: None
            )
            tarefa = g.criar(
                "apagar arquivo", "salomao", impacto="destrutivo",
                exigir_confirmacao=True,
            )
            self.assertEqual(tarefa.estado, EstadoTarefa.AGUARDANDO_CONFIRMACAO)
            with self.assertRaises(PermissionError):
                g.despachar(tarefa.id)
            self.assertTrue(g.confirmar(tarefa.id, "voz"))
            self.assertEqual(tarefa.confirmada_por, "voz")

    def test_cancelar_e_continuar(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                g = GerenciadorOperacoes(
                    PersistenciaOperacoes(Path(tmp) / "ops.db"), lambda *_: None
                )

                async def lento(tarefa, manager, cancelamento):
                    for _ in range(100):
                        if cancelamento.is_set():
                            return ""
                        await asyncio.sleep(0.02)
                    return "ok"

                g.definir_executor(lento)
                t1 = g.criar("tarefa longa", "salomao", sessao_voz_id="s1")
                task = g.despachar(t1.id)
                await asyncio.sleep(0.05)
                self.assertTrue(g.interromper(t1.id))
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(g.obter(t1.id).estado, EstadoTarefa.INTERROMPIDA)

                t2 = g.continuar(sessao_voz_id="s1")
                self.assertIsNotNone(t2)
                self.assertEqual(t2.sessao_opencode_id, t1.sessao_opencode_id)

        asyncio.run(rodar())

    def test_executor_por_destino_e_limpeza(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                g = GerenciadorOperacoes(
                    PersistenciaOperacoes(Path(tmp) / "ops.db"), lambda *_: None
                )

                async def executor(tarefa, manager, cancelamento):
                    return "ok"

                g.definir_executor(executor, "opencode")
                tarefa = g.criar("tarefa", "salomao")
                await g.despachar(tarefa.id)
                self.assertEqual(g.obter(tarefa.id).estado, EstadoTarefa.CONCLUIDA)
                self.assertNotIn(tarefa.id, g._async)  # M2: sem vazamento

                outra = g.criar("outra", "salomao", destino="cdc")
                with self.assertRaises(ValueError):  # M1: sem executor
                    g.despachar(outra.id)

        asyncio.run(rodar())

    def test_interrupcao_de_dentro_da_propria_task(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                g = GerenciadorOperacoes(
                    PersistenciaOperacoes(Path(tmp) / "ops.db"), lambda *_: None
                )

                async def executor(tarefa, manager, cancelamento):
                    manager.interromper(tarefa.id)  # M3: não deve cancelar a si
                    return "parcial"

                g.definir_executor(executor)
                tarefa = g.criar("tarefa", "salomao")
                resultado = await g.despachar(tarefa.id)
                self.assertEqual(resultado, "")
                self.assertEqual(
                    g.obter(tarefa.id).estado, EstadoTarefa.INTERROMPIDA
                )

        asyncio.run(rodar())

    def test_escopo_por_sessao_para_confirmar(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                g = GerenciadorOperacoes(
                    PersistenciaOperacoes(Path(tmp) / "ops.db"), lambda *_: None
                )
                tarefa = g.criar(
                    "apagar", "salomao", sessao_voz_id="s1", impacto="destrutivo",
                    exigir_confirmacao=True,
                )
                self.assertIsNone(
                    g.pendente_confirmacao(sessao_voz_id="s2")
                )  # M5: outra sessão não vê
                pendente = g.pendente_confirmacao(sessao_voz_id="s1")
                self.assertEqual(pendente.id, tarefa.id)
                self.assertIsNone(g.ativa(sessao_voz_id="s2"))

        asyncio.run(rodar())

    def test_notificador_filtra_e_limita(self):
        n = Notificador(PoliticaAnuncios(max_por_minuto=2))
        self.assertTrue(n.deve_anunciar({"tipo": "tarefa_recebida"}))
        self.assertTrue(n.deve_anunciar({"tipo": "sessao_iniciada"}))
        self.assertFalse(n.deve_anunciar({"tipo": "tarefa_confirmada"}))
        self.assertTrue(n.deve_anunciar({"tipo": "tarefa_falha"}))  # terminal sempre
        self.assertFalse(n.deve_anunciar({"tipo": "resposta_parcial"}))
        self.assertFalse(n.deve_anunciar({"tipo": "ferramenta_utilizada"}))

    def test_silenciamento_e_deduplicacao(self):
        n = Notificador(PoliticaAnuncios(silenciada=True))
        self.assertFalse(n.deve_anunciar({"tipo": "tarefa_concluida", "id": "e1"}))

        n2 = Notificador(PoliticaAnuncios())
        evento = {"tipo": "tarefa_falha", "id": "e2"}
        self.assertTrue(n2.deve_anunciar(evento))
        self.assertFalse(n2.deve_anunciar(evento))  # mesmo evento, sem duplicata

        n3 = Notificador(PoliticaAnuncios(
            nao_perturbar_inicio="00:00", nao_perturbar_fim="23:59"
        ))
        self.assertFalse(n3.deve_anunciar({"tipo": "sessao_iniciada"}))
        self.assertTrue(n3.deve_anunciar({"tipo": "tarefa_concluida"}))
        falado = n.mensagem({
            "tipo": "tarefa_falha",
            "dados": {"erro": "sk-chave-secreta"},
        })
        self.assertNotIn("sk-chave-secreta", falado)


class TestAdaptadorOpenCode(unittest.TestCase):
    def test_interpretar_eventos_reais(self):
        casos = [
            ({"type": "step_start", "sessionID": "ses_1"}, "etapa_iniciada"),
            ({"type": "text", "part": {"text": "oi"}}, "texto"),
            ({"type": "tool_use", "part": {"tool": "read"}}, "ferramenta"),
            ({"type": "step_finish", "part": {"reason": "stop"}}, "etapa_finalizada"),
        ]
        for objeto, esperado in casos:
            with self.subTest(objeto=objeto):
                self.assertEqual(OpenCodeAdapter.interpretar_evento(objeto)["tipo"], esperado)

    def test_saida_de_ferramenta_nao_vaza(self):
        evento = OpenCodeAdapter.interpretar_evento({
            "type": "tool_use",
            "part": {
                "tool": "read",
                "state": {"status": "completed", "output": "SEGREDO_SUPER_SECRETO"},
            },
        })
        self.assertNotIn("SEGREDO_SUPER_SECRETO", str(evento))

    def test_prompt_e_uma_linha_e_seguro_para_shim_cmd(self):
        prompt = OpenCodeAdapter._montar_prompt(
            "desenvolva módulo\ncom <tags> e [INICIO_TAREFA] internas"
        )
        self.assertNotIn("\n", prompt)
        self.assertNotIn("\r", prompt)
        self.assertNotIn("<", prompt)
        self.assertNotIn(">", prompt)
        self.assertIn("[INICIO_TAREFA]", prompt)

    def test_ambiente_isolado_remove_variaveis_do_harness(self):
        import os

        os.environ["OPENCODE_SESSION_ID"] = "ses_harness"
        os.environ["OPENCODE_MODEL"] = "modelo-invalido"
        try:
            ambiente = OpenCodeAdapter._ambiente_isolado()
            self.assertNotIn("OPENCODE_SESSION_ID", ambiente)
            self.assertNotIn("OPENCODE_MODEL", ambiente)
            self.assertIn("PATH", ambiente)
        finally:
            os.environ.pop("OPENCODE_SESSION_ID", None)
            os.environ.pop("OPENCODE_MODEL", None)

    def test_sanitizacao_de_erro(self):
        texto = (
            "falha com sk-abcdef1234567890 eBearer abc123 e "
            "https://user:pass@host/x e C:\\Users\\Lucas\\segredo.txt"
        )
        limpo = OpenCodeAdapter._sanitizar(texto)
        self.assertNotIn("sk-abcdef1234567890", limpo)
        self.assertNotIn("user:pass", limpo)
        self.assertNotIn("segredo.txt", limpo)
        self.assertIn("REDACTADO", limpo)

    def test_status_sem_cli_e_honesto(self):
        cfg = config_padrao().agente("opencode")
        cfg.opcoes["comando"] = "comando-inexistente-xyz"
        adaptador = OpenCodeAdapter(cfg)
        status = asyncio.run(adaptador.status())
        self.assertFalse(status["disponivel"])
        self.assertFalse(status["auto_aprovacao"])


class TestIntegracaoOperacional(unittest.TestCase):
    def test_comando_de_voz_cria_executa_e_comunica(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))

                async def executor(tarefa, manager, cancelamento):
                    manager.emitir(tarefa.id, "execucao_em_andamento", "executando")
                    await asyncio.sleep(0.01)
                    return "módulo de autenticação criado"

                gw.gerenciador.definir_executor(executor)
                sessao = gw.obter_sessao()
                fila = gw.bus.subscribe(sessao.id)
                await gw.processar_texto(
                    sessao.id,
                    "Salomão, solicite ao OpenCode que desenvolva o módulo de autenticação.",
                )
                await asyncio.sleep(0.15)
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                operacionais = [e for e in eventos if e["type"] == "operacional"]
                tipos = [e["tipo_evento"] for e in operacionais]
                self.assertIn("tarefa_recebida", tipos)
                self.assertIn("tarefa_concluida", tipos)
                tarefas = gw.gerenciador.listar()
                self.assertEqual(len(tarefas), 1)
                self.assertEqual(tarefas[0]["destino"], "opencode")
                self.assertEqual(tarefas[0]["estado"], "concluida")
                self.assertTrue(any(e["type"] == "answer" for e in eventos))
                await gw.fechar()

        asyncio.run(rodar())

    def test_alto_impacto_aguarda_e_confirma_por_voz(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))
                chamadas = []

                async def executor(tarefa, manager, cancelamento):
                    chamadas.append(tarefa.id)
                    return "feito"

                gw.gerenciador.definir_executor(executor)
                sessao = gw.obter_sessao()
                await gw.processar_texto(
                    sessao.id, "Salomão, peça ao OpenCode para apagar o arquivo antigo"
                )
                self.assertEqual(len(chamadas), 0)
                pendente = gw.gerenciador.pendente_confirmacao()
                self.assertIsNotNone(pendente)
                await gw.processar_texto(sessao.id, "Confirmar")
                await asyncio.sleep(0.1)
                self.assertEqual(chamadas, [pendente.id])
                self.assertEqual(
                    gw.gerenciador.obter(pendente.id).estado, EstadoTarefa.CONCLUIDA
                )
                await gw.fechar()

        asyncio.run(rodar())


    def test_cdc_coordena_com_identidade_propria(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                gw = VoiceGateway(cfg_teste(), Path(tmp))

                async def executor(tarefa, manager, cancelamento):
                    return "concluído"

                gw.gerenciador.definir_executor(executor)
                sessao = gw.obter_sessao(agente_id="cdc")
                fila = gw.bus.subscribe(sessao.id)
                anterior = gw.gerenciador.criar(
                    "verificar relatório", "usuario", sessao_voz_id=sessao.id
                )
                await gw.processar_texto(
                    sessao.id,
                    "CDC, encaminhe essa tarefa para o agente responsável",
                )
                await asyncio.sleep(0.1)
                eventos = []
                while not fila.empty():
                    eventos.append(fila.get_nowait())
                respostas = [e for e in eventos if e["type"] == "answer"]
                self.assertTrue(respostas)
                self.assertTrue(any(r["agente"] == "cdc" for r in respostas))
                tarefas = gw.gerenciador.listar()
                self.assertTrue(any(t["origem"] == "cdc" for t in tarefas))
                await gw.fechar()

        asyncio.run(rodar())


class TestAPIOperacional(unittest.TestCase):
    def test_endpoints_de_tarefas(self):
        async def rodar():
            with tempfile.TemporaryDirectory() as tmp:
                app = criar_app(cfg_teste(), "tok", Path(tmp))
                gw = app.state.gateway

                async def executor(tarefa, manager, cancelamento):
                    return "ok"

                gw.gerenciador.definir_executor(executor)
                headers = {"Authorization": "Bearer tok"}
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as cliente:
                    r = await cliente.post(
                        "/api/tarefas", headers=headers,
                        json={"descricao": "criar módulo", "origem": "teste"},
                    )
                    self.assertEqual(r.status_code, 200)
                    tarefa_id = r.json()["id"]
                    await asyncio.sleep(0.05)

                    r = await cliente.get("/api/tarefas", headers=headers)
                    self.assertEqual(len(r.json()), 1)

                    r = await cliente.get(
                        f"/api/tarefas/{tarefa_id}", headers=headers
                    )
                    self.assertEqual(r.json()["estado"], "concluida")

                    r = await cliente.get(
                        "/api/operacoes/status", headers=headers
                    )
                    self.assertIn("agentes", r.json())

                    # Impacto é reavaliado: API não burla confirmação.
                    r = await cliente.post(
                        "/api/tarefas", headers=headers,
                        json={
                            "descricao": "apagar todos os arquivos antigos",
                            "impacto": "normal",
                            "exigir_confirmacao": False,
                        },
                    )
                    self.assertEqual(r.json()["estado"], "aguardando_confirmacao")

                    r = await cliente.post(
                        "/api/tarefas", headers=headers,
                        json={"descricao": "teste", "destino": "cdc"},
                    )
                    self.assertEqual(r.status_code, 400)

        asyncio.run(rodar())


if __name__ == "__main__":
    unittest.main()

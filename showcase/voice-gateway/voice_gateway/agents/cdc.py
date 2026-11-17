# -*- coding: utf-8 -*-
"""Adaptador de voz para o Agente CDC.

FRONTEIRA DE AUTORIDADE: este adaptador somente informa. Ele nunca autoriza,
executa, grava no GitHub nem altera o CDC 2.0. Pedidos de autorização recebem
resposta explícita orientando ao fluxo oficial de aprovação humana.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, TYPE_CHECKING

from ..core.router import normalizar
from . import _ollama
from .base import AgentAdapter

if TYPE_CHECKING:  # evita ciclo
    from ..ops.gerenciador import GerenciadorOperacoes

SISTEMA_CDC = (
    "Você é o assistente de voz do CDC (Controle e Desenvolvimento de Código). "
    "Você informa sobre projetos, tarefas, auditorias e o estado do agente CDC. "
    "Você NÃO tem autoridade para autorizar, aprovar, executar operações críticas, "
    "escrever no GitHub ou alterar o CDC 2.0. Se pedirem isso, explique que é "
    "necessário o fluxo oficial de autorização humana. Responda em português do "
    "Brasil, de forma curta e objetiva, adequada para ser falada."
)

PADRAO_ACAO_CRITICA = re.compile(
    r"\b(autorizar|autoriza|aprovar|aprove|executar|execute|liberar|libere|"
    r"confirmar|confirme|conceder|conceda|desbloquear|desbloqueie|gravar|escrever)\b",
    re.IGNORECASE,
)
PADRAO_CONSULTA = re.compile(
    r"\b(status|estado|configuracao|config|modo|repositorio|saude|diagnostico| "
    r"como esta|oque e|o que e)\b",
    re.IGNORECASE,
)
PADRAO_REDE = re.compile(
    r"\b(pull request|pr|issue|tarefa sal|commit|branch|github)\b", re.IGNORECASE
)


class CDCAdapter(AgentAdapter):
    def __init__(self, config) -> None:  # type: ignore[no-untyped-def]
        super().__init__(config)
        self.raiz = Path(config.opcoes.get("raiz", r"D:\Salomao_CDC_Agente"))
        self.timeout = float(config.opcoes.get("timeout_sec", 20))
        self.consulta_rede = bool(config.opcoes.get("permitir_consultas_rede", False))
        self.url = str(config.opcoes.get("url_ollama", "http://127.0.0.1:11434"))
        self.modelo = str(config.opcoes.get("modelo", "qwen3:8b"))
        self._manager: "GerenciadorOperacoes | None" = None

    def definir_gerenciador(self, manager: "GerenciadorOperacoes") -> None:
        """Habilita coordenação operacional sem fundir identidades."""
        self._manager = manager

    def descricao(self) -> str:
        return "CDC — consultas e acompanhamento. Autorizações exigem aprovação humana."

    def _configuracao(self) -> Dict[str, Any]:
        caminho = self.raiz / "configuracoes" / "agente.json"
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    async def status(self) -> Dict[str, Any]:  # type: ignore[override]
        cfg = self._configuracao()
        base = super().status()
        base.update(
            {
                "raiz_presente": self.raiz.exists(),
                "modo": cfg.get("modo", "indisponivel"),
                "repositorio": cfg.get("repositorio", ""),
                "executar_opencode": bool(cfg.get("executar_opencode", False)),
                "escrita_github": bool(cfg.get("escrita_github", False)),
                "permitir_consultas_rede": self.consulta_rede,
                "operacoes": (
                    self._manager.estatisticas() if self._manager else None
                ),
            }
        )
        return base

    def _resumo_local(self) -> str:
        cfg = self._configuracao()
        if not cfg:
            return (
                "Não consegui ler a configuração do CDC em "
                f"{self.raiz}. Verifique se a instalação está disponível."
            )
        partes = [
            "Agente CDC disponível para consulta.",
            f"Modo: {cfg.get('modo', 'desconhecido')}.",
            f"Repositório: {cfg.get('repositorio', 'não informado')}.",
            "Execução automática: "
            + ("ativada" if cfg.get("executar_opencode") else "desativada")
            + ".",
            "Escrita no GitHub: "
            + ("ativada" if cfg.get("escrita_github") else "desativada")
            + ".",
        ]
        return " ".join(partes)

    def _resumo_operacional(self) -> str:
        if self._manager is None:
            return "Coordenação operacional indisponível."
        estatisticas = self._manager.estatisticas()
        ativa = self._manager.ativa()
        partes = [
            "Coordenação CDC: "
            f"{estatisticas['tarefas']} tarefa(s) registrada(s), "
            f"{estatisticas['em_execucao']} em execução."
        ]
        if ativa:
            partes.append(
                f"Tarefa ativa: {ativa.descricao[:80]} — estado {ativa.estado.value}."
            )
        else:
            partes.append("Nenhuma tarefa em execução no momento.")
        return " ".join(partes)

    async def _consulta_rede(self, texto: str) -> str | None:
        if not self.consulta_rede:
            return None
        try:
            comando = "gh"
            args = ["pr", "list", "--limit", "5", "--repo", "lukasadventure-eng/SALOMAO-AI"]
            processo = await asyncio.create_subprocess_exec(
                comando,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            saida, _ = await asyncio.wait_for(processo.communicate(), timeout=self.timeout)
            if processo.returncode == 0:
                linhas = saida.decode("utf-8", "replace").strip().splitlines()
                return "Últimos pull requests: " + "; ".join(linhas[:5]) if linhas else (
                    "Nenhum pull request encontrado."
                )
        except (OSError, asyncio.TimeoutError):
            pass
        return None

    async def responder(
        self,
        texto: str,
        contexto: List[Dict[str, str]],
        cancelamento: asyncio.Event,
    ) -> AsyncIterator[str]:
        if cancelamento.is_set():
            return

        if PADRAO_ACAO_CRITICA.search(texto):
            resposta = (
                "Entendi o pedido, mas a voz não autoriza operações no CDC. "
                "Autorizações, execuções e escritas exigem aprovação humana no fluxo "
                "oficial do Agente CDC. Posso apenas informar o estado atual."
            )
            for indice in range(0, len(resposta), 24):
                if cancelamento.is_set():
                    return
                yield resposta[indice : indice + 24]
                await asyncio.sleep(0)
            return

        texto_norm = normalizar(texto)
        if self._manager and re.search(
            r"\b(tarefas|execucoes|em andamento|coordenacao)\b", texto_norm
        ):
            resposta = self._resumo_operacional()
        elif PADRAO_CONSULTA.search(texto) or "cdc" in texto.casefold():
            resposta = self._resumo_local()
        elif PADRAO_REDE.search(texto):
            resposta = await self._consulta_rede(texto) or (
                "Consultas de rede estão desativadas nesta configuração. "
                + self._resumo_local()
            )
        else:
            mensagens = [
                {
                    "role": "user" if m.get("remetente") == "usuario" else "assistant",
                    "content": m["conteudo"],
                }
                for m in contexto
                if m.get("conteudo")
            ]
            mensagens.append({"role": "user", "content": texto})
            async for token in _ollama.gerar_stream(
                self.url, self.modelo, SISTEMA_CDC, mensagens, cancelamento, 0.3
            ):
                yield token
            return

        for indice in range(0, len(resposta), 24):
            if cancelamento.is_set():
                return
            yield resposta[indice : indice + 24]
            await asyncio.sleep(0)

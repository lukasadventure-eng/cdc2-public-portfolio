# -*- coding: utf-8 -*-
"""Gerenciador do ciclo de vida das tarefas operacionais.

Não executa nada diretamente: recebe um ``executor`` injetado (o adaptador do
OpenCode) e apenas coordena estados, eventos, confirmação, cancelamento e
persistência. Isso mantém o gateway desacoplado do OpenCode.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..models import agora_iso, novo_id
from .modelos import EstadoTarefa, EventoOperacional, TarefaOperacional, nova_tarefa
from .persistencia import PersistenciaOperacoes

Publicador = Callable[[str, str, Dict[str, Any]], None]
Executor = Callable[[TarefaOperacional, "GerenciadorOperacoes", asyncio.Event], Awaitable[str]]


class GerenciadorOperacoes:
    TRANSICOES = {
        EstadoTarefa.RECEBIDA: {
            EstadoTarefa.AGUARDANDO_CONFIRMACAO,
            EstadoTarefa.CONFIRMADA,
            EstadoTarefa.SESSAO_INICIADA,
            EstadoTarefa.EM_EXECUCAO,
            EstadoTarefa.FALHA,
            EstadoTarefa.INTERROMPIDA,
        },
        EstadoTarefa.AGUARDANDO_CONFIRMACAO: {
            EstadoTarefa.CONFIRMADA,
            EstadoTarefa.INTERROMPIDA,
            EstadoTarefa.FALHA,
        },
        EstadoTarefa.CONFIRMADA: {
            EstadoTarefa.SESSAO_INICIADA,
            EstadoTarefa.EM_EXECUCAO,
            EstadoTarefa.INTERROMPIDA,
            EstadoTarefa.FALHA,
        },
        EstadoTarefa.SESSAO_INICIADA: {
            EstadoTarefa.EM_EXECUCAO,
            EstadoTarefa.AGUARDANDO_AUTORIZACAO,
            EstadoTarefa.CONCLUIDA,
            EstadoTarefa.INTERROMPIDA,
            EstadoTarefa.FALHA,
        },
        EstadoTarefa.EM_EXECUCAO: {
            EstadoTarefa.AGUARDANDO_AUTORIZACAO,
            EstadoTarefa.CONCLUIDA,
            EstadoTarefa.INTERROMPIDA,
            EstadoTarefa.FALHA,
        },
        EstadoTarefa.AGUARDANDO_AUTORIZACAO: {
            EstadoTarefa.EM_EXECUCAO,
            EstadoTarefa.CONCLUIDA,
            EstadoTarefa.INTERROMPIDA,
            EstadoTarefa.FALHA,
        },
    }

    def __init__(
        self,
        persistencia: PersistenciaOperacoes,
        publicar: Publicador,
        max_eventos: int = 200,
    ) -> None:
        self.persistencia = persistencia
        self.publicar = publicar
        self.max_eventos = max_eventos
        self._executores: Dict[str, Executor] = {}
        self._memoria: Dict[str, TarefaOperacional] = {}
        self._async: Dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

    # ------------------------------------------------------------------
    def definir_executor(self, executor: Executor, destino: str = "opencode") -> None:
        """Registra o executor de um destino. Nenhum outro é executado por ele."""
        self._executores[destino] = executor

    def executores_disponiveis(self) -> List[str]:
        return sorted(self._executores)

    def criar(
        self,
        descricao: str,
        origem: str,
        destino: str = "opencode",
        sessao_voz_id: str = "",
        impacto: str = "normal",
        exigir_confirmacao: bool = False,
    ) -> TarefaOperacional:
        tarefa = nova_tarefa(descricao, destino, origem, sessao_voz_id, impacto)
        self._memoria[tarefa.id] = tarefa
        self.persistencia.salvar_tarefa(tarefa)
        self.emitir(
            tarefa.id,
            "tarefa_recebida",
            f"Tarefa recebida de {origem} para {destino}.",
            estado=tarefa.estado.value,
            impacto=impacto,
        )
        if exigir_confirmacao:
            self._mudar_estado(
                tarefa, EstadoTarefa.AGUARDANDO_CONFIRMACAO, "Confirmação necessária."
            )
            self.emitir(
                tarefa.id,
                "confirmacao_solicitada",
                "Operação de alto impacto aguardando confirmação explícita.",
                impacto=impacto,
            )
        return tarefa

    # ------------------------------------------------------------------
    def obter(self, tarefa_id: str) -> Optional[TarefaOperacional]:
        if tarefa_id in self._memoria:
            return self._memoria[tarefa_id]
        tarefa = self.persistencia.carregar_tarefa(tarefa_id)
        if tarefa:
            self._memoria[tarefa.id] = tarefa
        return tarefa

    def listar(self, limite: int = 30) -> List[Dict[str, Any]]:
        return self.persistencia.listar_tarefas(limite)

    def estatisticas(self) -> Dict[str, int]:
        return self.persistencia.estatisticas()

    def ultima(self, sessao_voz_id: str = "") -> Optional[TarefaOperacional]:
        for linha in self.listar(100):
            if sessao_voz_id and linha.get("sessao_voz_id") != sessao_voz_id:
                continue
            tarefa = self.obter(linha["id"])
            if tarefa:
                return tarefa
        return None

    def ativa(self, sessao_voz_id: str = "") -> Optional[TarefaOperacional]:
        for linha in self.listar(100):
            if sessao_voz_id and linha.get("sessao_voz_id") != sessao_voz_id:
                continue
            if linha["estado"] in {
                EstadoTarefa.RECEBIDA.value,
                EstadoTarefa.CONFIRMADA.value,
                EstadoTarefa.SESSAO_INICIADA.value,
                EstadoTarefa.EM_EXECUCAO.value,
                EstadoTarefa.AGUARDANDO_AUTORIZACAO.value,
                EstadoTarefa.AGUARDANDO_CONFIRMACAO.value,
            }:
                return self.obter(linha["id"])
        return None

    def pendente_confirmacao(
        self, sessao_voz_id: str = ""
    ) -> Optional[TarefaOperacional]:
        for linha in self.listar(100):
            if sessao_voz_id and linha.get("sessao_voz_id") != sessao_voz_id:
                continue
            if linha["estado"] == EstadoTarefa.AGUARDANDO_CONFIRMACAO.value:
                return self.obter(linha["id"])
        return None

    def historico(self, sessao_voz_id: str = "", limite: int = 20) -> List[Dict[str, Any]]:
        return [
            linha
            for linha in self.listar(limite)
            if not sessao_voz_id or linha.get("sessao_voz_id") == sessao_voz_id
        ]

    # ------------------------------------------------------------------
    def _mudar_estado(
        self, tarefa: TarefaOperacional, estado: EstadoTarefa, mensagem: str = ""
    ) -> None:
        if tarefa.estado == estado:
            return
        permitido = self.TRANSICOES.get(tarefa.estado, set())
        if estado not in permitido and not tarefa.estado.terminal:
            # Transições inesperadas são registradas, nunca silenciosas.
            self.emitir(
                tarefa.id,
                "transicao_inesperada",
                f"{tarefa.estado.value} -> {estado.value}",
            )
        tarefa.estado = estado
        tarefa.atualizada_em = agora_iso()
        self.persistencia.salvar_tarefa(tarefa)
        if mensagem:
            self.emitir(tarefa.id, "estado_alterado", mensagem, estado=estado.value)

    def emitir(
        self,
        tarefa_id: str,
        tipo: str,
        mensagem: str = "",
        estado: str | None = None,
        **dados: Any,
    ) -> EventoOperacional:
        tarefa = self.obter(tarefa_id)
        evento = EventoOperacional(
            id=novo_id("evt_"),
            tarefa_id=tarefa_id,
            tipo=tipo,
            timestamp=agora_iso(),
            estado=estado or (tarefa.estado.value if tarefa else ""),
            mensagem=mensagem[:500],
            dados=dados,
        )
        if tarefa is not None:
            tarefa.eventos.append(evento)
            if len(tarefa.eventos) > self.max_eventos:
                tarefa.eventos = tarefa.eventos[-self.max_eventos :]
        self.persistencia.salvar_evento(evento)
        self.publicar(tarefa_id, evento.tipo, evento.para_dict())
        return evento

    # ------------------------------------------------------------------
    def confirmar(self, tarefa_id: str, por: str = "voz") -> bool:
        tarefa = self.obter(tarefa_id)
        if tarefa is None or tarefa.estado != EstadoTarefa.AGUARDANDO_CONFIRMACAO:
            return False
        tarefa.confirmada_por = por
        self._mudar_estado(tarefa, EstadoTarefa.CONFIRMADA, "Confirmação recebida.")
        self.emitir(tarefa.id, "tarefa_confirmada", "Operação confirmada.")
        return True

    def despachar(self, tarefa_id: str) -> asyncio.Task:
        tarefa = self.obter(tarefa_id)
        if tarefa is None:
            raise ValueError("Tarefa inexistente.")
        if tarefa.estado == EstadoTarefa.AGUARDANDO_CONFIRMACAO:
            raise PermissionError("Tarefa aguarda confirmação explícita.")
        if tarefa.estado.terminal:
            raise ValueError("Tarefa já encerrada.")
        executor = self._executores.get(tarefa.destino)
        if executor is None:
            raise ValueError(
                f"Nenhum executor registrado para o destino '{tarefa.destino}'."
            )
        cancelamento = asyncio.Event()
        tarefa_async = asyncio.create_task(
            self._executar(tarefa, executor, cancelamento),
            name=f"operacao:{tarefa_id}",
        )
        self._async[tarefa_id] = (tarefa_async, cancelamento)

        def limpar(task: asyncio.Task) -> None:
            atual = self._async.get(tarefa_id)
            if atual is not None and atual[0] is task:
                self._async.pop(tarefa_id, None)

        tarefa_async.add_done_callback(limpar)
        return tarefa_async

    async def _executar(
        self,
        tarefa: TarefaOperacional,
        executor: Executor,
        cancelamento: asyncio.Event,
    ) -> str:
        try:
            resultado = await executor(tarefa, self, cancelamento)
            if cancelamento.is_set():
                self.interromper(tarefa.id)
                return ""
            self.concluir(tarefa.id, resultado)
            return resultado
        except asyncio.CancelledError:
            self.interromper(tarefa.id)
            raise
        except Exception as erro:  # noqa: BLE001
            self.falhar(tarefa.id, f"{type(erro).__name__}: {erro}")
            return ""

    def registrar_sessao(self, tarefa_id: str, sessao_opencode_id: str) -> None:
        tarefa = self.obter(tarefa_id)
        if tarefa is None:
            return
        tarefa.sessao_opencode_id = sessao_opencode_id
        self.persistencia.salvar_tarefa(tarefa)
        self._mudar_estado(tarefa, EstadoTarefa.SESSAO_INICIADA, "Sessão OpenCode pronta.")
        self.emitir(
            tarefa.id,
            "sessao_iniciada",
            "Sessão de trabalho iniciada.",
            sessao=sessao_opencode_id[:40],
        )

    def iniciar_execucao(self, tarefa_id: str) -> None:
        tarefa = self.obter(tarefa_id)
        if tarefa:
            self._mudar_estado(tarefa, EstadoTarefa.EM_EXECUCAO)

    def aguardando_autorizacao(self, tarefa_id: str, mensagem: str = "") -> None:
        tarefa = self.obter(tarefa_id)
        if tarefa:
            self._mudar_estado(
                tarefa,
                EstadoTarefa.AGUARDANDO_AUTORIZACAO,
                "OpenCode solicitou autorização de ferramenta.",
            )
            self.emitir(
                tarefa.id,
                "autorizacao_necessaria",
                mensagem or "Autorização de ferramenta necessária no OpenCode.",
            )

    def concluir(self, tarefa_id: str, resultado: str) -> None:
        tarefa = self.obter(tarefa_id)
        if tarefa is None or tarefa.estado.terminal:
            return
        tarefa.resultado = resultado
        self._mudar_estado(tarefa, EstadoTarefa.CONCLUIDA, "Execução concluída.")
        self.emitir(
            tarefa.id,
            "tarefa_concluida",
            "Tarefa concluída com sucesso.",
            resumo=resultado[:160],
        )

    def falhar(self, tarefa_id: str, erro: str) -> None:
        tarefa = self.obter(tarefa_id)
        if tarefa is None or tarefa.estado.terminal:
            return
        tarefa.erro = erro[:1000]
        self._mudar_estado(tarefa, EstadoTarefa.FALHA, "Execução falhou.")
        self.emitir(tarefa.id, "tarefa_falha", erro[:300])

    def interromper(self, tarefa_id: str) -> bool:
        entrada = self._async.get(tarefa_id)
        if entrada:
            tarefa_async, cancelamento = entrada
            cancelamento.set()
            # Nunca cancela a própria task: isso transformaria uma conclusão
            # controlada em CancelledError no turno do gateway.
            if not tarefa_async.done() and tarefa_async is not asyncio.current_task():
                tarefa_async.cancel()
        tarefa = self.obter(tarefa_id)
        if tarefa is None or tarefa.estado.terminal:
            return False
        self._mudar_estado(tarefa, EstadoTarefa.INTERROMPIDA, "Execução interrompida.")
        self.emitir(tarefa.id, "tarefa_interrompida", "Execução interrompida.")
        return True

    def cancelar(self, tarefa_id: str = "", sessao_voz_id: str = "") -> bool:
        alvo = (
            self.obter(tarefa_id)
            if tarefa_id
            else self.ativa(sessao_voz_id=sessao_voz_id)
        )
        if alvo is None:
            return False
        return self.interromper(alvo.id)

    def continuar(
        self,
        tarefa_id: str = "",
        origem: str = "usuario",
        sessao_voz_id: str = "",
    ) -> Optional[TarefaOperacional]:
        anterior = self.obter(tarefa_id) if tarefa_id else self.ultima(sessao_voz_id)
        if anterior is None:
            return None
        descricao = f"Continue a execução da tarefa anterior: {anterior.descricao}"
        tarefa = self.criar(
            descricao,
            origem=origem,
            destino=anterior.destino,
            sessao_voz_id=sessao_voz_id or anterior.sessao_voz_id,
            impacto=anterior.impacto,
        )
        tarefa.sessao_opencode_id = anterior.sessao_opencode_id
        self.persistencia.salvar_tarefa(tarefa)
        self.emitir(
            tarefa.id,
            "tarefa_continuada",
            "Continuando na mesma sessão do OpenCode.",
            anterior=anterior.id,
        )
        return tarefa

    async def fechar(self) -> None:
        for tarefa_async, cancelamento in list(self._async.values()):
            cancelamento.set()
            if not tarefa_async.done():
                tarefa_async.cancel()

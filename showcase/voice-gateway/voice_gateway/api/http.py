# -*- coding: utf-8 -*-
"""Endpoints REST. Nenhum segredo ou áudio é devolvido."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.gateway import VoiceGateway
from ..core.router import normalizar
from ..ops.comandos import avaliar_impacto
from ..security.auth import AuthManager


class FalarPayload(BaseModel):
    texto: str = Field(min_length=1, max_length=8000)
    agente: str | None = None
    sessao: str | None = None
    origem: str = "texto"


class InterromperPayload(BaseModel):
    sessao: str


class CapturaPayload(BaseModel):
    sessao: str
    dispositivo: str = ""


class VozPayload(BaseModel):
    nome: str
    agente: str = "salomao"
    dados: str  # WAV base64
    consentimento: str = ""


class AmostraFalantePayload(BaseModel):
    perfil_id: str
    dados: str  # WAV em base64


class IdentificarFalantePayload(BaseModel):
    dados: str  # WAV em base64


class FalantePayload(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    consentimento: bool = False


class NotificacoesPayload(BaseModel):
    silenciada: bool | None = None
    eventos: list[str] | None = None


class TarefaPayload(BaseModel):
    descricao: str = Field(min_length=1, max_length=4000)
    destino: str = "opencode"
    origem: str = "interface"
    impacto: str = "normal"
    exigir_confirmacao: bool = False
    sessao: str = ""


def criar_router(gateway: VoiceGateway, auth: AuthManager) -> APIRouter:
    router = APIRouter()

    def verificar(request: Request) -> None:
        cabecalho = request.headers.get("authorization", "")
        fornecido = cabecalho.split(" ", 1)[1] if cabecalho.lower().startswith("bearer ") else (
            request.query_params.get("token")
        )
        if not auth.validar(fornecido):
            raise HTTPException(status_code=401, detail="Token inválido ou ausente.")

    @router.get("/health")
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "versao": "0.1.0",
            "agentes": list(gateway.adaptadores),
            "stt": gateway.stt.info(),
            "tts": gateway.tts.info(),
            "mic": {"status": "ready", "servidor": True},
            "autenticacao": auth.token_publico(),
            "auditoria_integra": gateway.auditoria.verificar(),
            "operacoes": gateway.gerenciador.estatisticas(),
        }

    @router.get("/api/agentes")
    async def agentes(_: None = Depends(verificar)) -> Any:
        return gateway.listar_agentes()

    @router.get("/api/voces")
    async def voces(_: None = Depends(verificar)) -> Any:
        return gateway.listar_voces()

    @router.get("/api/agentes/{agente_id}/status")
    async def status_agente(agente_id: str, _: None = Depends(verificar)) -> Any:
        if agente_id not in gateway.adaptadores:
            raise HTTPException(status_code=404, detail="Agente desconhecido.")
        resultado = gateway.adaptadores[agente_id].status()
        return await resultado if asyncio.iscoroutine(resultado) else resultado

    @router.get("/api/sessoes")
    async def sessoes(_: None = Depends(verificar)) -> Any:
        return gateway.listar_sessoes()

    @router.get("/api/sessoes/{sessao_id}")
    async def sessao(sessao_id: str, _: None = Depends(verificar)) -> Any:
        sessao_obj = gateway.obter_sessao(sessao_id)
        return sessao_obj.para_dict()

    @router.delete("/api/sessoes/{sessao_id}")
    async def excluir_sessao(sessao_id: str, _: None = Depends(verificar)) -> Any:
        removida = gateway.historico.excluir_sessao(sessao_id)
        gateway._sessoes.pop(sessao_id, None)
        gateway.auditoria.registrar("SESSAO_EXCLUIDA_API", sessao=sessao_id)
        return {"removida": removida}

    @router.post("/api/falar")
    async def falar(payload: FalarPayload, _: None = Depends(verificar)) -> Any:
        sessao = gateway.obter_sessao(payload.sessao, payload.agente)
        gateway.iniciar_turno(
            sessao.id, payload.texto, payload.origem, payload.agente
        )
        return {"sessao": sessao.id, "aceito": True}

    @router.post("/api/interromper")
    async def interromper(payload: InterromperPayload, _: None = Depends(verificar)) -> Any:
        return {"interrompido": gateway.interromper(payload.sessao)}

    @router.get("/api/tarefas")
    async def tarefas(_: None = Depends(verificar)) -> Any:
        return gateway.gerenciador.listar()

    @router.post("/api/tarefas")
    async def criar_tarefa(
        payload: TarefaPayload, _: None = Depends(verificar)
    ) -> Any:
        if payload.destino not in gateway.gerenciador.executores_disponiveis():
            raise HTTPException(
                status_code=400,
                detail="Destino sem executor registrado. Use 'opencode'.",
            )
        # O impacto é reavaliado no servidor: um chamador não pode burlar a
        # confirmação declarando "normal" numa descrição destrutiva.
        impacto, exige = avaliar_impacto(normalizar(payload.descricao))
        if impacto == "normal":
            impacto = payload.impacto if payload.impacto in ("normal", "alto", "destrutivo") else "normal"
        exige = (
            exige and gateway.config.operacoes.confirmar_destrutivo
        ) or payload.exigir_confirmacao
        tarefa = gateway.gerenciador.criar(
            payload.descricao,
            origem=payload.origem,
            destino=payload.destino,
            sessao_voz_id=payload.sessao,
            impacto=impacto,
            exigir_confirmacao=exige,
        )
        if tarefa.estado.value != "aguardando_confirmacao":
            gateway.gerenciador.despachar(tarefa.id)
        return tarefa.para_dict(incluir_eventos=False)

    @router.get("/api/tarefas/{tarefa_id}")
    async def tarefa(tarefa_id: str, _: None = Depends(verificar)) -> Any:
        encontrada = gateway.gerenciador.obter(tarefa_id)
        if encontrada is None:
            raise HTTPException(status_code=404, detail="Tarefa inexistente.")
        return encontrada.para_dict()

    @router.post("/api/tarefas/{tarefa_id}/confirmar")
    async def confirmar_tarefa(
        tarefa_id: str, _: None = Depends(verificar)
    ) -> Any:
        if not gateway.gerenciador.confirmar(tarefa_id, "interface"):
            raise HTTPException(status_code=409, detail="Tarefa não aguarda confirmação.")
        gateway.gerenciador.despachar(tarefa_id)
        return {"confirmada": True}

    @router.post("/api/tarefas/{tarefa_id}/cancelar")
    async def cancelar_tarefa(
        tarefa_id: str, _: None = Depends(verificar)
    ) -> Any:
        return {"interrompida": gateway.gerenciador.cancelar(tarefa_id)}

    @router.get("/api/operacoes/eventos")
    async def eventos_operacionais(_: None = Depends(verificar)) -> Any:
        return gateway.gerenciador.persistencia.listar_eventos()

    @router.get("/api/operacoes/status")
    async def status_operacional(_: None = Depends(verificar)) -> Any:
        status: dict[str, Any] = {
            "estatisticas": gateway.gerenciador.estatisticas(),
            "agentes": {},
        }
        for agente_id, adaptador in gateway.adaptadores.items():
            resultado = adaptador.status()
            status["agentes"][agente_id] = (
                await resultado if asyncio.iscoroutine(resultado) else resultado
            )
        return status

    @router.get("/api/captura")
    async def captura_estado(_: None = Depends(verificar)) -> Any:
        return gateway.estado_captura()

    @router.post("/api/captura/iniciar")
    async def captura_iniciar(
        payload: CapturaPayload, _: None = Depends(verificar)
    ) -> Any:
        return gateway.iniciar_captura(payload.sessao, payload.dispositivo)

    @router.post("/api/captura/parar")
    async def captura_parar(
        payload: CapturaPayload, _: None = Depends(verificar)
    ) -> Any:
        return {"parada": gateway.parar_captura(payload.sessao)}

    @router.get("/api/token")
    async def token() -> Any:
        from pathlib import Path
        token_path = Path(__file__).resolve().parents[2] / "data" / "token"
        try:
            return {"token": token_path.read_text(encoding="utf-8").strip()}
        except Exception:
            return {"token": ""}

    @router.get("/api/voz")
    async def voz_estado(_: None = Depends(verificar)) -> Any:
        return gateway.voz.estado()

    @router.post("/api/voz")
    async def voz_registrar(
        payload: VozPayload, _: None = Depends(verificar)
    ) -> Any:
        import base64

        try:
            audio = base64.b64decode(payload.dados, validate=True)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="WAV base64 inválido.")
        try:
            perfil = gateway.voz.registrar(
                payload.nome, payload.agente, audio, payload.consentimento
            )
        except PermissionError as erro:
            raise HTTPException(status_code=403, detail=str(erro))
        except ValueError as erro:
            raise HTTPException(status_code=400, detail=str(erro))
        gateway.auditoria.registrar("VOZ_AUTORIZADA", voz=perfil.id[:16])
        return perfil.para_dict()

    @router.delete("/api/voz/{perfil_id}")
    async def voz_excluir(
        perfil_id: str, _: None = Depends(verificar)
    ) -> Any:
        removido = gateway.voz.excluir(perfil_id)
        gateway.auditoria.registrar("VOZ_EXCLUIDA", voz=perfil_id[:16])
        return {"removido": removido}

    @router.get("/api/falantes")
    async def falantes(_: None = Depends(verificar)) -> Any:
        return {
            "estado": gateway.falantes.estado(),
            "perfis": gateway.falantes.listar(),
        }

    @router.post("/api/falantes")
    async def criar_falante(
        payload: FalantePayload, _: None = Depends(verificar)
    ) -> Any:
        try:
            perfil = gateway.falantes.criar(
                payload.nome, payload.consentimento
            )
        except PermissionError as erro:
            raise HTTPException(status_code=403, detail=str(erro))
        gateway.auditoria.registrar("FALANTE_CRIADO", falante=perfil.id[:16])
        return perfil.para_dict()

    @router.post("/api/falantes/amostra")
    async def registrar_amostra_falante(
        payload: AmostraFalantePayload, _: None = Depends(verificar)
    ) -> Any:
        import base64

        try:
            audio = base64.b64decode(payload.dados, validate=True)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Áudio base64 inválido.")
        if len(audio) > 8_000_000:
            raise HTTPException(status_code=413, detail="Amostra muito grande.")
        if not gateway.falantes.registrar_amostra(payload.perfil_id, audio):
            raise HTTPException(status_code=404, detail="Perfil não encontrado.")
        gateway.auditoria.registrar(
            "AMOSTRA_FALANTE", falante=payload.perfil_id[:16]
        )
        return {"registrada": True}

    @router.post("/api/falantes/identificar")
    async def identificar_falante(
        payload: IdentificarFalantePayload, _: None = Depends(verificar)
    ) -> Any:
        import base64

        try:
            audio = base64.b64decode(payload.dados, validate=True)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Áudio base64 inválido.")
        perfil = gateway.falantes.identificar(audio)
        # Identificação NUNCA autoriza operação sensível.
        return {
            "perfil": perfil.para_dict() if perfil else None,
            "usado_para_autorizacao": False,
        }

    @router.delete("/api/falantes/{perfil_id}")
    async def excluir_falante(
        perfil_id: str, _: None = Depends(verificar)
    ) -> Any:
        removido = gateway.falantes.excluir(perfil_id)
        gateway.auditoria.registrar("FALANTE_EXCLUIDO", falante=perfil_id[:16])
        return {"removido": removido}

    @router.get("/api/notificacoes")
    async def notificacoes_estado(_: None = Depends(verificar)) -> Any:
        return gateway.estado_notificacoes()

    @router.post("/api/notificacoes")
    async def notificacoes_config(
        payload: NotificacoesPayload, _: None = Depends(verificar)
    ) -> Any:
        return gateway.configurar_notificacoes(
            silenciada=payload.silenciada, eventos=payload.eventos
        )

    @router.get("/api/wake")
    async def wake_estado(_: None = Depends(verificar)) -> Any:
        return gateway.estado_wake()

    @router.post("/api/wake/ativar")
    async def wake_ativar(_: None = Depends(verificar)) -> Any:
        try:
            return gateway.ativar_wake()
        except ValueError as erro:
            raise HTTPException(status_code=409, detail=str(erro))

    @router.post("/api/wake/desativar")
    async def wake_desativar(_: None = Depends(verificar)) -> Any:
        return gateway.desativar_wake()

    @router.get("/api/metricas")
    async def metricas(
        sessao: str = "", limite: int = 200, _: None = Depends(verificar)
    ) -> Any:
        return {
            "resumo": gateway.metricas.resumo(sessao),
            "amostras": gateway.metricas.listar(limite, sessao),
        }

    @router.get("/api/estatisticas")
    async def estatisticas(_: None = Depends(verificar)) -> Any:
        return gateway.historico.estatisticas()

    @router.get("/api/config")
    async def configuracao(_: None = Depends(verificar)) -> Any:
        cfg = gateway.config
        return {
            "audio": {
                "sample_rate": cfg.audio.sample_rate,
                "canais": cfg.audio.canais,
                "vad_habilitado": cfg.audio.vad_habilitado,
                "vad_limiar_rms": cfg.audio.vad_limiar_rms,
                "vad_quadros_silencio": cfg.audio.vad_quadros_silencio,
            },
            "stt": {"provedor": cfg.stt.provedor, "idioma": cfg.stt.idioma},
            "tts": {
                "provedor": cfg.tts.provedor,
                "velocidade": cfg.tts.velocidade,
                "altura": cfg.tts.altura,
            },
            "agente_padrao": cfg.agente_padrao,
            "operacoes_criticas_por_voz": (
                cfg.seguranca.permitir_operacoes_criticas_por_voz
            ),
        }

    return router

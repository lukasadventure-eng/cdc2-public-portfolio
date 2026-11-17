# -*- coding: utf-8 -*-
"""Protocolo WebSocket de conversação em tempo real.

Cliente → servidor: hello, set_agent, text_input, transcript, audio_start,
audio_chunk, audio_end, barge_in, speech_start, speech_end, ping.
Servidor → cliente: ready, status, transcript, routing, token, answer, audio,
speech_start, speech_end, stop_speech, interrompido, erro, pong.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Dict

logger = logging.getLogger("voice_gateway.ws")

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.gateway import VoiceGateway
from ..models import EstadoTurno
from ..security.auth import AuthManager, RateLimiter


def criar_router(gateway: VoiceGateway, auth: AuthManager) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/voice")
    async def voz(websocket: WebSocket) -> None:
        token = websocket.query_params.get("token", "")
        if websocket.query_params.get("token_header"):
            token = websocket.headers.get("authorization", "").removeprefix("Bearer ")
        if not auth.validar(token):
            await websocket.close(code=4401, reason="Token inválido")
            return
        await websocket.accept()

        sessao_id = websocket.query_params.get("sessao", "")
        fila_envio: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=512)
        limite = RateLimiter(gateway.config.seguranca.limite_mensagens_por_minuto)
        audio_buffer = bytearray()
        inscrito = ""

        async def enviar() -> None:
            while True:
                mensagem = await fila_envio.get()
                await websocket.send_json(mensagem)

        # Fila de eventos do barramento e tarefa de envio única (evita intercalação).
        fila_entrada: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=512)

        async def repassar() -> None:
            while True:
                try:
                    mensagem = await asyncio.wait_for(fila_entrada.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                await fila_envio.put(mensagem)

        tarefa_envio = asyncio.create_task(enviar())
        tarefa_repassar = asyncio.create_task(repassar())

        def trocar_inscricao(novo_id: str) -> None:
            nonlocal inscrito
            if inscrito and inscrito != novo_id:
                gateway.bus.unsubscribe(inscrito, fila_entrada)
            if novo_id and novo_id != inscrito:
                inscrito = novo_id
                gateway.bus.subscribe(inscrito, fila_entrada)

        if sessao_id:
            trocar_inscricao(sessao_id)

        try:
            while True:
                bruto = await websocket.receive_text()
                if not limite.permitir():
                    await fila_envio.put({"type": "erro", "mensagem": "Limite de mensagens excedido."})
                    continue
                try:
                    msg = json.loads(bruto)
                except json.JSONDecodeError:
                    await fila_envio.put({"type": "erro", "mensagem": "JSON inválido."})
                    continue
                tipo = str(msg.get("type", ""))

                if tipo == "ping":
                    await fila_envio.put({"type": "pong"})

                elif tipo == "hello":
                    sessao_id = str(msg.get("sessao") or sessao_id) or ""
                    agente = msg.get("agente")
                    sessao = gateway.obter_sessao(sessao_id, agente)
                    sessao_id = sessao.id
                    trocar_inscricao(sessao_id)
                    await fila_envio.put(
                        {
                            "type": "ready",
                            "sessao": sessao_id,
                            "agente": sessao.agente_id,
                            "agentes": gateway.listar_agentes(),
                            "voces": gateway.listar_voces(),
                            "stt": gateway.stt.info(),
                            "tts": gateway.tts.info(),
                            "wake": gateway.estado_wake(),
                            "config": {
                                "sample_rate": gateway.config.audio.sample_rate,
                                "vad_limiar_rms": gateway.config.audio.vad_limiar_rms,
                                "vad_quadros_silencio": gateway.config.audio.vad_quadros_silencio,
                            },
                        }
                    )

                elif tipo == "set_agent":
                    agente = str(msg.get("agente", ""))
                    if agente not in gateway.adaptadores:
                        await fila_envio.put({"type": "erro", "mensagem": "Agente desconhecido."})
                        continue
                    sessao = gateway.obter_sessao(sessao_id or None, agente)
                    sessao_id = sessao.id
                    trocar_inscricao(sessao_id)
                    gateway.publicar(sessao_id, "routing", agente=agente, explicito=True, motivo="seleção na interface")
                    gateway.auditoria.registrar("AGENTE_SELECIONADO", sessao=sessao_id, agente=agente)

                elif tipo == "text_input":
                    if not sessao_id:
                        sessao_id = gateway.obter_sessao().id
                        trocar_inscricao(sessao_id)
                    gateway.iniciar_turno(
                        sessao_id,
                        str(msg.get("texto", "")),
                        "texto",
                        msg.get("agente"),
                    )

                elif tipo == "transcript":
                    texto = str(msg.get("texto", "")).strip()
                    final = bool(msg.get("final", True))
                    gateway.publicar(sessao_id, "transcript", texto=texto, final=final, origem="voz")
                    if final and texto:
                        gateway.iniciar_turno(sessao_id, texto, "voz", msg.get("agente"))

                elif tipo == "set_notificacoes":
                    estado = gateway.configurar_notificacoes(
                        silenciada=msg.get("silenciada"),
                        eventos=msg.get("eventos"),
                    )
                    await fila_envio.put({"type": "notificacoes_estado", **estado})

                elif tipo == "mic_dispositivos":
                    await fila_envio.put({
                        "type": "mic_dispositivos",
                        **gateway.estado_captura(),
                    })

                elif tipo == "mic_start":
                    estado = gateway.iniciar_captura(
                        sessao_id, str(msg.get("dispositivo", ""))
                    )
                    await fila_envio.put({"type": "captura_estado", **estado})

                elif tipo == "mic_stop":
                    gateway.parar_captura(sessao_id)
                    await fila_envio.put(
                        {"type": "captura_estado", **gateway.estado_captura()}
                    )

                elif tipo == "set_wake":
                    try:
                        if "habilitado" in msg:
                            estado = (
                                gateway.ativar_wake(sessao_id)
                                if bool(msg["habilitado"])
                                else gateway.desativar_wake(sessao_id)
                            )
                        else:
                            estado = gateway.alternar_wake(sessao_id)
                        await fila_envio.put({"type": "wake_estado", **estado})
                    except ValueError as erro:
                        await fila_envio.put({"type": "erro", "mensagem": str(erro)})

                elif tipo == "wake_audio":
                    try:
                        dados_wake = base64.b64decode(
                            str(msg.get("dados", "")), validate=True
                        )
                    except Exception:  # noqa: BLE001
                        await fila_envio.put({"type": "erro", "mensagem": "Áudio wake inválido."})
                        continue
                    if len(dados_wake) > gateway.config.seguranca.max_chunk_bytes * 8:
                        await fila_envio.put({"type": "erro", "mensagem": "Áudio wake excede o limite."})
                        continue
                    await gateway.processar_wake_audio(sessao_id, dados_wake)

                elif tipo == "audio_start":
                    audio_buffer = bytearray()
                    gateway._status(sessao_id, EstadoTurno.OUVINDO)
                    gateway.publicar(sessao_id, "listening", ativo=True)

                elif tipo == "audio_chunk":
                    limite_bytes = gateway.config.seguranca.max_chunk_bytes
                    try:
                        pedaco = base64.b64decode(str(msg.get("dados", "")), validate=True)
                    except Exception:  # noqa: BLE001
                        await fila_envio.put({"type": "erro", "mensagem": "Chunk de áudio inválido."})
                        continue
                    if len(pedaco) > limite_bytes or len(audio_buffer) > limite_bytes * 8:
                        await fila_envio.put({"type": "erro", "mensagem": "Áudio excede o limite."})
                        continue
                    audio_buffer.extend(pedaco)

                elif tipo == "audio_end":
                    gateway.publicar(sessao_id, "listening", ativo=False)
                    dados = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    if dados:
                        await gateway.processar_audio(sessao_id, dados)

                elif tipo in ("barge_in", "cancel"):
                    gateway.interromper(sessao_id)

                elif tipo == "metricas_interrupcao":
                    resultado = gateway.registrar_interrupcao(
                        sessao_id,
                        float(msg.get("deteccao_ms", 0)),
                        float(msg.get("total_ms", 0)),
                        envio_ms=msg.get("envio_ms"),
                        servidor_ms=msg.get("servidor_ms"),
                        tts_cancel_ms=msg.get("tts_cancel_ms"),
                        som_ms=msg.get("som_ms"),
                        dispositivo_saida=str(msg.get("dispositivo_saida", ""))[:80],
                    )
                    await fila_envio.put(
                        {"type": "metricas_interrupcao", **resultado}
                    )

                elif tipo in ("speech_start", "speech_end"):
                    gateway.publicar(
                        sessao_id,
                        tipo,
                        agente=gateway._agente_da_sessao(sessao_id),
                    )
                    gateway._status(
                        sessao_id,
                        EstadoTurno.FALANDO if tipo == "speech_start" else EstadoTurno.OCIOSO,
                    )

                else:
                    await fila_envio.put({"type": "erro", "mensagem": f"Tipo desconhecido: {tipo}"})
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("Falha no handler WebSocket")
        finally:
            if inscrito:
                gateway.bus.unsubscribe(inscrito, fila_entrada)
            tarefa_envio.cancel()
            tarefa_repassar.cancel()

    return router

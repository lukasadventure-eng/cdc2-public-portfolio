# -*- coding: utf-8 -*-
"""Orquestrador do Voice Gateway.

Responsabilidades (conforme a arquitetura do projeto):
captura → transcrição → roteamento → sessão → encaminhamento → resposta →
síntese → streaming → interrupção → continuidade → histórico → vozes.

O gateway não conhece modelos: tudo passa por adaptadores STT/TTS/agente.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from pathlib import Path
logger = logging.getLogger("voice_gateway")

from ..agents.registry import criar_agente
from ..audio.captura import CapturadorServidor
from ..config import Config, DIRETORIO_DADOS
from ..models import EstadoTurno, Mensagem, Sessao, evento, novo_id
from ..ops.comandos import (
    ParserComandos,
    TIPO_CONFIRMAR,
    TIPO_CONTINUAR,
    TIPO_DELEGAR,
    TIPO_ENCAMINHAR_RESPONSAVEL,
    TIPO_EXPLICAR,
    TIPO_INTERROMPER,
    TIPO_LISTAR_TAREFAS,
    TIPO_NENHUM,
    TIPO_QUAL_AGENTE,
    TIPO_ULTIMO_RESULTADO,
)
from ..ops.gerenciador import GerenciadorOperacoes
from ..ops.notificacoes import Notificador, PoliticaAnuncios
from ..ops.persistencia import PersistenciaOperacoes
from ..security.audit import AuditTrail
from ..speakers.identificador import IdentificadorSpeechBrain
from ..speakers.servico import ServicoFalantes
from ..stt.registry import criar_stt
from ..tts.registry import criar_tts
from ..voz.perfil import RegistroVoz
from ..wake.detector import WakeWordDetector
from .events import EventBus
from .history import Historico
from .metricas import Metricas
from .router import AgentRouter

_CONTROLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class VoiceGateway:
    def __init__(self, config: Config, diretorio_dados: Path | None = None) -> None:
        self.config = config
        self.diretorio_dados = Path(diretorio_dados) if diretorio_dados else DIRETORIO_DADOS
        self.diretorio_dados.mkdir(parents=True, exist_ok=True)
        self.bus = EventBus()
        self.metricas = Metricas()
        self.router = AgentRouter(
            [a.id for a in config.agentes if a.ativo],
            config.agente_padrao,
        )
        self.historico = Historico(
            self.diretorio_dados / config.historico.banco,
            config.historico.retencao_dias,
            config.historico.habilitado,
        )
        self.auditoria = AuditTrail(self.diretorio_dados / "auditoria.jsonl")
        import os

        self.falantes = ServicoFalantes(
            self.diretorio_dados / "falantes.db",
            IdentificadorSpeechBrain(
                float(os.environ.get("VG_SPEAKER_LIMIAR", "0.75"))
            ),
        )
        self.stt = criar_stt(config)
        self.tts = criar_tts(config)
        self.voz = RegistroVoz(self.diretorio_dados / "vozes")
        self.captura = CapturadorServidor(
            sample_rate=config.audio.sample_rate,
            limiar=config.captura.limiar,
            quadros_silencio=config.captura.quadros_silencio,
            dispositivo=config.captura.dispositivo,
            adaptativo=config.captura.adaptativo,
            multiplicador_ruido=config.captura.multiplicador_ruido,
            limiar_minimo=config.captura.limiar_minimo,
            janela_ruido=config.captura.janela_ruido,
        )
        self._capturas: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}
        self._ultimo_wake: dict[str, float] = {}
        self.wake = WakeWordDetector(
            config.wake.palavras,
            config.wake.cooldown_s,
            habilitado=config.wake.habilitado,
        )
        self.adaptadores = {
            agente.id: criar_agente(config, agente.id)
            for agente in config.agentes
            if agente.ativo
        }
        self.parser_comandos = ParserComandos()
        operacoes_cfg = config.operacoes
        self.gerenciador = GerenciadorOperacoes(
            PersistenciaOperacoes(self.diretorio_dados / operacoes_cfg.banco),
            self._publicar_operacional,
            operacoes_cfg.max_eventos_por_tarefa,
        )
        self.notificador = Notificador(
            PoliticaAnuncios.de_lista(
                operacoes_cfg.anunciar_eventos,
                anunciar_ferramentas=operacoes_cfg.anunciar_ferramentas,
                anunciar_parciais=operacoes_cfg.anunciar_parciais,
                max_por_minuto=operacoes_cfg.max_anuncios_por_minuto,
                silenciada=operacoes_cfg.notificacoes_silenciadas,
                nao_perturbar_inicio=operacoes_cfg.nao_perturbar_inicio,
                nao_perturbar_fim=operacoes_cfg.nao_perturbar_fim,
            )
        )
        opencode = self.adaptadores.get("opencode")
        if opencode is not None and hasattr(opencode, "executar_tarefa"):
            self.gerenciador.definir_executor(opencode.executar_tarefa)
        cdc = self.adaptadores.get("cdc")
        if cdc is not None and hasattr(cdc, "definir_gerenciador"):
            cdc.definir_gerenciador(self.gerenciador)
        self._sessoes: Dict[str, Sessao] = {}
        self._turnos: Dict[str, asyncio.Task] = {}
        self._cancelamentos: Dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Sessões e configuração
    # ------------------------------------------------------------------
    def obter_sessao(
        self, sessao_id: Optional[str] = None, agente_id: Optional[str] = None
    ) -> Sessao:
        if sessao_id:
            sessao = self._sessoes.get(sessao_id) or self.historico.carregar_sessao(
                sessao_id
            )
            if sessao is not None:
                self._sessoes[sessao.id] = sessao
        else:
            sessao = None
        if sessao is None:
            agente = agente_id or self.config.agente_padrao
            sessao = Sessao(id=novo_id("sess_"), agente_id=agente)
            self._sessoes[sessao.id] = sessao
            self.historico.salvar_sessao(sessao)
            self.historico.registrar_evento(
                "SESSAO_CRIADA", sessao_id=sessao.id, agente_id=agente
            )
            self.auditoria.registrar("SESSAO_CRIADA", sessao=sessao.id, agente=agente)
        if agente_id and agente_id in self.adaptadores:
            sessao.agente_id = agente_id
            cfg_agente = self.config.agente(agente_id)
            if cfg_agente:
                sessao.voz_id = cfg_agente.voz
            self.historico.salvar_sessao(sessao, salvar_mensagens=False)
        return sessao

    def listar_sessoes(self) -> List[Dict[str, Any]]:
        return self.historico.listar_sessoes()

    def listar_agentes(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": a.id,
                "nome": a.nome,
                "descricao": a.descricao,
                "voz": a.voz,
                "cor": a.cor,
                "ativo": a.ativo,
            }
            for a in self.config.agentes
            if a.ativo
        ]

    def voz_para_agente(self, agente_id: str) -> str:
        """Voz lógica de cada agente — mantém identidades vocais separadas."""
        mapa = {
            "salomao": self.config.tts.voz_salomao,
            "cdc": self.config.tts.voz_cdc,
            "opencode": self.config.tts.voz_opencode,
            "operacoes": self.config.tts.voz_cdc,
        }
        return mapa.get(agente_id, self.config.tts.voz_salomao)

    def listar_voces(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": a.voz,
                "nome": a.nome,
                "agente": a.id,
                "velocidade": self.config.tts.velocidade,
                "altura": self.config.tts.altura,
            }
            for a in self.config.agentes
            if a.ativo
        ]

    # ------------------------------------------------------------------
    # Protocolo de eventos
    # ------------------------------------------------------------------
    def publicar(self, sessao_id: str, tipo: str, **dados: Any) -> None:
        self.bus.publish(sessao_id, evento(tipo, **dados))

    def _status(self, sessao_id: str, estado: str, **dados: Any) -> None:
        self.publicar(sessao_id, "status", estado=estado, **dados)

    # ------------------------------------------------------------------
    # Operações (Voice Gateway 2.0)
    # ------------------------------------------------------------------
    _SUPRIMIR_ANUNCIO = {
        "tarefa_recebida",
        "confirmacao_solicitada",
        "tarefa_confirmada",
    }

    def _publicar_operacional(
        self, tarefa_id: str, tipo: str, dados: Dict[str, Any]
    ) -> None:
        """Callback do gerenciador: leva eventos reais à UI e à voz."""
        tarefa = self.gerenciador.obter(tarefa_id)
        sessao_id = tarefa.sessao_voz_id if tarefa else ""
        self.bus.publish(
            sessao_id,
            evento(
                "operacional",
                tarefa=tarefa_id,
                tipo_evento=tipo,
                destino=tarefa.destino if tarefa else "",
                estado=tarefa.estado.value if tarefa else "",
                dados=dados,
            ),
        )
        if sessao_id:
            self.publicar(
                sessao_id,
                "operacao_status",
                tarefa=tarefa_id,
                estado=tarefa.estado.value if tarefa else "",
                tipo_evento=tipo,
            )
        self.auditoria.registrar(
            "OPERACAO_EVENTO", tarefa=tarefa_id, acao_evento=tipo
        )
        if tipo in self._SUPRIMIR_ANUNCIO:
            return
        if self.notificador.deve_anunciar(dados):
            mensagem = self.notificador.mensagem(dados)
            if mensagem and sessao_id:
                self.publicar(
                    sessao_id,
                    "answer",
                    texto=mensagem,
                    agente="operacoes",
                    voz=self.voz_para_agente("cdc"),
                    velocidade=self.config.tts.velocidade,
                    altura=self.config.tts.altura,
                    sintetiza_no_servidor=self.tts.sintetiza_no_servidor,
                )

    # ------------------------------------------------------------------
    # Captura de microfone no servidor (alternativa ao navegador)
    # ------------------------------------------------------------------
    def estado_captura(self) -> Dict[str, Any]:
        return {
            "modo": self.config.captura.modo,
            "dispositivos": self.captura.dispositivos(),
            "dispositivo": self.config.captura.dispositivo,
            "detalhes": self.captura.estado(),
            "sessoes_ativas": [s for s, v in self._capturas.items() if not v[0].done()],
        }

    def iniciar_captura(self, sessao_id: str, dispositivo: str = "") -> Dict[str, Any]:
        # Um único microfone físico por gateway: evita captura duplicada.
        for outra in list(self._capturas):
            if outra != sessao_id:
                self.parar_captura(outra)
        self.parar_captura(sessao_id)
        if dispositivo:
            self.captura.dispositivo = dispositivo
            self.config.captura.dispositivo = dispositivo
        cancelamento = asyncio.Event()
        tarefa = asyncio.create_task(
            self._loop_captura(sessao_id, cancelamento),
            name=f"captura:{sessao_id}",
        )
        self._capturas[sessao_id] = (tarefa, cancelamento)
        self.auditoria.registrar("CAPTURA_SERVIDOR_INICIADA", sessao=sessao_id)
        return self.estado_captura()

    def parar_captura(self, sessao_id: str) -> bool:
        entrada = self._capturas.pop(sessao_id, None)
        if entrada is None:
            return False
        tarefa, cancelamento = entrada
        cancelamento.set()
        if not tarefa.done():
            tarefa.cancel()
        self.publicar(sessao_id, "listening", ativo=False)
        self.auditoria.registrar("CAPTURA_SERVIDOR_ENCERRADA", sessao=sessao_id)
        return True

    async def processar_captura(self, sessao_id: str, audio: bytes) -> None:
        """STT local → wake word (opcional) → turno do agente."""
        inicio = time.monotonic()
        try:
            texto = await self.stt.transcrever(audio, self.config.stt.idioma)
        except Exception as erro:  # noqa: BLE001
            self.publicar(sessao_id, "erro", mensagem=f"Falha no STT: {type(erro).__name__}")
            return
        self.metricas.registrar(
            "stt", (time.monotonic() - inicio) * 1000, sessao_id=sessao_id
        )
        texto = str(texto or "").strip()
        if not texto:
            self.publicar(sessao_id, "wake_aguardando", texto="")
            return
        self.publicar(sessao_id, "transcript", texto=texto, final=True, origem="voz")

        agente: str | None = None
        if self.wake.habilitado:
            deteccao = self.wake.detectar(texto)
            agora = time.monotonic()
            janela = agora - self._ultimo_wake.get(sessao_id, 0.0)
            if deteccao is not None:
                self._ultimo_wake[sessao_id] = agora
                agente = "salomao"
                self.publicar(sessao_id, "wake_detected", **deteccao.para_dict())
                texto = re.sub(
                    r"(?i)^\s*(salom[ãa]o|salum[ãa]o)(\s+ai)?[\s,.:-]*",
                    "",
                    texto,
                ).strip() or texto
            elif janela > 120:
                # Wake ativo e sem ativação recente: ignora ruído/fala alheia.
                self.publicar(sessao_id, "wake_aguardando", texto=texto[:120])
                return
        self.iniciar_turno(sessao_id, texto, "voz", agente)

    async def _loop_captura(self, sessao_id: str, cancelamento: asyncio.Event) -> None:
        try:
            while not cancelamento.is_set():
                self.publicar(sessao_id, "listening", ativo=True)
                self.publicar(sessao_id, "capture_state", estado="capturando")
                self._status(sessao_id, EstadoTurno.OUVINDO)
                audio = await self.captura.capturar_turno(
                    lambda nivel: self.publicar(
                        sessao_id, "audio_level", nivel=round(float(nivel), 4)
                    ),
                    cancelamento,
                    lambda estado: self.publicar(
                        sessao_id, "capture_state", estado=estado
                    ),
                )
                if cancelamento.is_set():
                    return
                self.publicar(sessao_id, "listening", ativo=False)
                if audio:
                    self.publicar(sessao_id, "capture_state", estado="processando")
                    await self.processar_captura(sessao_id, audio)
                    # Aguarda a resposta antes de ouvir novamente.
                    for _ in range(300):
                        if cancelamento.is_set():
                            return
                        tarefa = self._turnos.get(sessao_id)
                        if tarefa is None or tarefa.done():
                            break
                        await asyncio.sleep(0.1)
                    self.publicar(sessao_id, "capture_state", estado="capturando")
                if not self.config.captura.continuo:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # noqa: BLE001
            self.publicar(sessao_id, "capture_state", estado="erro")
            self.publicar(
                sessao_id,
                "erro",
                mensagem=f"Falha na captura do servidor: {type(erro).__name__}",
            )
        finally:
            self.publicar(sessao_id, "listening", ativo=False)
            self.publicar(sessao_id, "capture_state", estado="encerrada")

    # ------------------------------------------------------------------
    # Notificações (16.6)
    # ------------------------------------------------------------------
    def estado_notificacoes(self) -> Dict[str, Any]:
        politica = self.notificador.politica
        return {
            "silenciada": politica.silenciada,
            "eventos": sorted(politica.eventos),
            "nao_perturbar_inicio": politica.nao_perturbar_inicio,
            "nao_perturbar_fim": politica.nao_perturbar_fim,
        }

    def configurar_notificacoes(
        self,
        silenciada: bool | None = None,
        eventos: List[str] | None = None,
    ) -> Dict[str, Any]:
        if silenciada is not None:
            self.notificador.politica.silenciada = bool(silenciada)
            self.config.operacoes.notificacoes_silenciadas = bool(silenciada)
        if eventos is not None:
            self.notificador.politica.eventos = set(eventos)
            self.config.operacoes.anunciar_eventos = list(eventos)
        self.auditoria.registrar(
            "NOTIFICACOES_CONFIG", silenciada=self.notificador.politica.silenciada
        )
        return self.estado_notificacoes()

    # ------------------------------------------------------------------
    # Ativação por palavra-chave (16.1)
    # ------------------------------------------------------------------
    def ativar_wake(self, sessao_id: str = "") -> Dict[str, Any]:
        if self.config.wake.exigir_stt_local and not self.stt.transcreve_no_servidor:
            raise ValueError(
                "Ativação por voz exige STT local. O provedor 'browser' pode "
                "enviar áudio ao fabricante do navegador."
            )
        self.wake.ativar()
        if sessao_id:
            self.publicar(sessao_id, "wake_estado", **self.wake.estado())
        self.auditoria.registrar("WAKE_ATIVADO")
        return self.wake.estado()

    def desativar_wake(self, sessao_id: str = "") -> Dict[str, Any]:
        self.wake.desativar()
        if sessao_id:
            self.publicar(sessao_id, "wake_estado", **self.wake.estado())
        self.auditoria.registrar("WAKE_DESATIVADO")
        return self.wake.estado()

    def alternar_wake(self, sessao_id: str = "") -> Dict[str, Any]:
        return self.ativar_wake(sessao_id) if not self.wake.habilitado else (
            self.desativar_wake(sessao_id)
        )

    def estado_wake(self) -> Dict[str, Any]:
        estado = self.wake.estado()
        estado["stt_local"] = self.stt.transcreve_no_servidor
        estado["pode_ativar"] = not (
            self.config.wake.exigir_stt_local and not self.stt.transcreve_no_servidor
        )
        estado["indicador_sonoro"] = self.config.wake.indicador_sonoro
        return estado

    async def processar_wake_audio(self, sessao_id: str, audio: bytes) -> None:
        """Transcreve localmente e decide se houve ativação."""
        if self.config.wake.exigir_stt_local and not self.stt.transcreve_no_servidor:
            self.publicar(
                sessao_id,
                "erro",
                mensagem="Ativação por palavra-chave requer STT local configurado.",
            )
            return
        inicio = time.monotonic()
        try:
            texto = await self.stt.transcrever(audio, self.config.stt.idioma)
        except Exception as erro:  # noqa: BLE001
            self.publicar(
                sessao_id, "erro", mensagem=f"Falha no STT local: {type(erro).__name__}"
            )
            return
        self.metricas.registrar(
            "stt", (time.monotonic() - inicio) * 1000,
            sessao_id=sessao_id, wake=True,
        )
        deteccao = self.wake.detectar(texto)
        if deteccao is None:
            self.publicar(sessao_id, "wake_aguardando", texto=texto[:120])
            return
        self.publicar(sessao_id, "wake_detected", **deteccao.para_dict())
        self.historico.registrar_evento(
            "WAKE_DETECTADO", sessao_id=sessao_id, palavra=deteccao.palavra
        )
        self.auditoria.registrar("WAKE_DETECTADO", sessao=sessao_id)

    async def _falarComoSalomao(
        self, sessao: Sessao, texto: str, cancelamento: asyncio.Event
    ) -> None:
        """Fala de interlocução gerada pelo próprio Salomão AI (ponte nativa)."""
        adaptador = self.adaptadores.get("salomao")
        falado = ""
        if adaptador is not None and hasattr(adaptador, "feedback"):
            try:
                falado = await adaptador.feedback(texto, cancelamento)
            except Exception:  # noqa: BLE001
                falado = ""
        if not falado:
            falado = texto
        if cancelamento.is_set() or not falado:
            return
        sessao.adicionar(
            Mensagem(
                id=novo_id("msg_"),
                remetente="agente",
                conteudo=falado,
                agente_id="salomao",
                origem="sistema",
            )
        )
        self.historico.salvar_sessao(
            sessao, salvar_mensagens=self.config.historico.salvar_transcricoes
        )
        self.publicar(
            sessao.id,
            "answer",
            texto=falado,
            agente="salomao",
            voz=self.voz_para_agente("salomao"),
            velocidade=self.config.tts.velocidade,
            altura=self.config.tts.altura,
            sintetiza_no_servidor=self.tts.sintetiza_no_servidor,
        )

    async def _responderOperacional(
        self, sessao: Sessao, texto: str, cancelamento: asyncio.Event
    ) -> None:
        """Resposta falada curta, na voz do agente que conduz a interação."""
        if sessao.agente_id == "cdc":
            if cancelamento.is_set():
                return
            sessao.adicionar(
                Mensagem(
                    id=novo_id("msg_"),
                    remetente="agente",
                    conteudo=texto,
                    agente_id="cdc",
                    origem="sistema",
                )
            )
            self.historico.salvar_sessao(
                sessao, salvar_mensagens=self.config.historico.salvar_transcricoes
            )
            self.publicar(
                sessao.id,
                "answer",
                texto=texto,
                agente="cdc",
                voz=self.voz_para_agente("cdc"),
                velocidade=self.config.tts.velocidade,
                altura=self.config.tts.altura,
                sintetiza_no_servidor=self.tts.sintetiza_no_servidor,
            )
            return
        await self._falarComoSalomao(sessao, texto, cancelamento)

    async def _processar_comando(
        self,
        sessao: Sessao,
        intencao: Any,
        cancelamento: asyncio.Event,
    ) -> bool:
        """Trata comandos operacionais. True = turno concluído pelo gateway."""
        if intencao.tipo == TIPO_NENHUM:
            return False
        if not self.config.operacoes.habilitado:
            await self._responderOperacional(
                sessao,
                "Operações por voz estão desativadas nesta configuração.",
                cancelamento,
            )
            return True

        tipo = intencao.tipo
        self.auditoria.registrar(
            "COMANDO_VOZ", tipo=tipo, destino=intencao.destino
        )
        self.publicar(
            sessao.id,
            "comando_reconhecido",
            comando=tipo,
            destino=intencao.destino,
            impacto=intencao.impacto,
            descricao=intencao.descricao[:160],
        )

        if tipo == TIPO_INTERROMPER:
            cancelada = self.gerenciador.cancelar(sessao_voz_id=sessao.id)
            await self._responderOperacional(
                sessao,
                "Execução interrompida." if cancelada
                else "Não havia execução em andamento para interromper.",
                cancelamento,
            )
            return True

        if tipo == TIPO_CONFIRMAR:
            pendente = self.gerenciador.pendente_confirmacao(sessao_voz_id=sessao.id)
            if pendente and self.gerenciador.confirmar(pendente.id, "voz"):
                self.gerenciador.despachar(pendente.id)
                await self._responderOperacional(
                    sessao,
                    "Confirmação recebida. Informe ao usuário que a execução foi iniciada.",
                    cancelamento,
                )
            else:
                await self._responderOperacional(
                    sessao,
                    "Não há operação aguardando confirmação no momento.",
                    cancelamento,
                )
            return True

        if tipo == TIPO_ULTIMO_RESULTADO:
            ultima = self.gerenciador.ultima(sessao.id)
            if ultima is None:
                texto = "Ainda não há resultados de tarefas nesta sessão."
            else:
                self.gerenciador.emitir(
                    ultima.id, "resultado_lido", "Resultado solicitado por voz."
                )
                texto = (
                    f"Último resultado: {ultima.resultado[:400]}"
                    if ultima.resultado
                    else f"A tarefa está no estado {ultima.estado.value}."
                )
            await self._responderOperacional(sessao, texto, cancelamento)
            return True

        if tipo == TIPO_QUAL_AGENTE:
            ativa = self.gerenciador.ativa(sessao_voz_id=sessao.id)
            texto = (
                f"O agente {ativa.destino} está trabalhando na tarefa: "
                f"{ativa.descricao[:120]}."
                if ativa
                else "Nenhum agente está executando tarefa no momento."
            )
            await self._responderOperacional(sessao, texto, cancelamento)
            return True

        if tipo == TIPO_LISTAR_TAREFAS:
            tarefas = self.gerenciador.listar(5)
            texto = (
                "Tarefas registradas: "
                + "; ".join(
                    f"{t['estado']}: {t['descricao'][:50]}" for t in tarefas
                )
                if tarefas
                else "Nenhuma tarefa registrada."
            )
            await self._responderOperacional(sessao, texto, cancelamento)
            return True

        if tipo == TIPO_EXPLICAR:
            ativa = self.gerenciador.ativa(sessao_voz_id=sessao.id) or self.gerenciador.ultima(sessao.id)
            if ativa is None:
                texto = "Não há execução em andamento nem tarefa recente para explicar."
            else:
                eventos = [e.tipo for e in ativa.eventos[-6:]]
                texto = (
                    f"Estado atual: {ativa.estado.value}. "
                    f"Eventos recentes: {', '.join(eventos)}."
                )
            await self._responderOperacional(sessao, texto, cancelamento)
            return True

        if tipo == TIPO_CONTINUAR:
            tarefa = self.gerenciador.continuar(
                origem=intencao.emitente or "usuario", sessao_voz_id=sessao.id
            )
            if tarefa is None:
                await self._responderOperacional(
                    sessao, "Não há tarefa anterior para continuar.", cancelamento
                )
            else:
                self.gerenciador.despachar(tarefa.id)
                await self._responderOperacional(
                    sessao,
                    "Informe ao usuário que a execução anterior foi retomada na mesma sessão.",
                    cancelamento,
                )
            return True

        if tipo in (TIPO_DELEGAR, TIPO_ENCAMINHAR_RESPONSAVEL):
            descricao = intencao.descricao.strip()
            if tipo == TIPO_ENCAMINHAR_RESPONSAVEL and not descricao:
                anterior = self.gerenciador.ultima(sessao.id)
                descricao = anterior.descricao if anterior else ""
            if not descricao:
                await self._responderOperacional(
                    sessao,
                    "Preciso saber qual tarefa deve ser encaminhada.",
                    cancelamento,
                )
                return True
            destino = intencao.destino or "opencode"
            # Apenas destinos com executor registrado podem ser despachados.
            # CDC e Salomão são coordenadores/interlocutores, não executores.
            if destino not in self.gerenciador.executores_disponiveis():
                destino = "opencode"
            origem = intencao.emitente or sessao.agente_id or "usuario"
            salomao = self.adaptadores.get("salomao")
            if origem == "salomao" and salomao is not None and hasattr(
                salomao, "registrar_contexto"
            ):
                try:
                    await salomao.registrar_contexto(intencao.original)
                except Exception:  # noqa: BLE001
                    pass
            exige = (
                intencao.exigir_confirmacao
                and self.config.operacoes.confirmar_destrutivo
            ) or (
                self.config.operacoes.confirmar_escrita and destino == "opencode"
            )
            tarefa = self.gerenciador.criar(
                descricao=descricao,
                origem=origem,
                destino=destino,
                sessao_voz_id=sessao.id,
                impacto=intencao.impacto,
                exigir_confirmacao=exige,
            )
            if tarefa.estado.value == "aguardando_confirmacao":
                await self._responderOperacional(
                    sessao,
                    "Esta operação é de alto impacto. Informe ao usuário que é necessário dizer 'confirmar' antes da execução.",
                    cancelamento,
                )
            else:
                self.gerenciador.despachar(tarefa.id)
                await self._responderOperacional(
                    sessao,
                    f"Informe ao usuário, em uma frase curta, que a tarefa foi encaminhada ao {destino} e que o acompanhamento está disponível.",
                    cancelamento,
                )
            return True

        return False

    # ------------------------------------------------------------------
    # Turnos
    # ------------------------------------------------------------------
    @staticmethod
    def _validar_texto(texto: str, limite: int) -> str:
        limpo = _CONTROLES.sub(" ", str(texto or "")).strip()
        if not limpo:
            raise ValueError("Mensagem vazia.")
        if len(limpo) > limite:
            raise ValueError(f"Mensagem muito longa (máximo {limite} caracteres).")
        return limpo

    def interromper(self, sessao_id: str) -> bool:
        """Barge-in: cancela geração e síntese imediatamente."""
        cancelamento = self._cancelamentos.get(sessao_id)
        tarefa = self._turnos.get(sessao_id)
        if cancelamento is None or tarefa is None or tarefa.done():
            return False
        cancelamento.set()
        tarefa.cancel()
        self.publicar(sessao_id, "stop_speech")
        self.publicar(sessao_id, "interrompido", agente=self._agente_da_sessao(sessao_id))
        self._status(sessao_id, EstadoTurno.INTERROMPIDO)
        self.historico.registrar_evento("TURNO_INTERROMPIDO", sessao_id=sessao_id)
        self.auditoria.registrar("TURNO_INTERROMPIDO", sessao=sessao_id)
        return True

    def registrar_interrupcao(
        self,
        sessao_id: str,
        deteccao_ms: float,
        total_ms: float,
        **etapas: Any,
    ) -> Dict[str, Any]:
        """Registra cada etapa da interrupção acústica separadamente (16.3)."""
        medidas: Dict[str, float] = {
            "interrupcao_deteccao": float(deteccao_ms),
            "interrupcao_total": float(total_ms),
        }
        mapa = {
            "envio_ms": "interrupcao_envio",
            "servidor_ms": "interrupcao_servidor",
            "tts_cancel_ms": "interrupcao_tts",
            "som_ms": "interrupcao_som",
        }
        for chave, tipo in mapa.items():
            if chave in etapas and etapas[chave] is not None:
                medidas[tipo] = float(etapas[chave])
        for tipo, valor in medidas.items():
            self.metricas.registrar(tipo, valor, sessao_id=sessao_id)
        self.historico.registrar_evento(
            "INTERRUCAO_MEDIDA", sessao_id=sessao_id, **medidas
        )
        return {chave: round(valor, 2) for chave, valor in medidas.items()}

    def _agente_da_sessao(self, sessao_id: str) -> str:
        sessao = self._sessoes.get(sessao_id)
        return sessao.agente_id if sessao else ""

    def iniciar_turno(
        self,
        sessao_id: str,
        texto: str,
        origem: str = "voz",
        agente_explicito: Optional[str] = None,
    ) -> asyncio.Task:
        """Cancela o turno anterior (se houver) e inicia um novo."""
        self.interromper(sessao_id)
        cancelamento = asyncio.Event()
        tarefa = asyncio.create_task(
            self._executar_turno(sessao_id, texto, origem, agente_explicito, cancelamento),
            name=f"turno:{sessao_id}",
        )
        self._cancelamentos[sessao_id] = cancelamento
        self._turnos[sessao_id] = tarefa
        tarefa.add_done_callback(lambda _: self._limpar_turno(sessao_id, tarefa))
        return tarefa

    def _limpar_turno(self, sessao_id: str, tarefa: asyncio.Task) -> None:
        if self._turnos.get(sessao_id) is tarefa:
            self._turnos.pop(sessao_id, None)

    async def processar_texto(
        self,
        sessao_id: str,
        texto: str,
        origem: str = "voz",
        agente_explicito: Optional[str] = None,
    ) -> None:
        """Executa um turno em linha (útil em testes e integrações CLI)."""
        await self.iniciar_turno(sessao_id, texto, origem, agente_explicito)

    async def processar_audio(self, sessao_id: str, audio: bytes) -> Optional[str]:
        if not self.stt.transcreve_no_servidor:
            self.publicar(
                sessao_id,
                "erro",
                mensagem="O provedor STT atual transcreve no navegador.",
            )
            return None
        logger.info("processar_audio: sessao=%s bytes=%d", sessao_id, len(audio))
        self._status(sessao_id, EstadoTurno.TRANSCREVENDO)
        inicio = time.monotonic()
        try:
            transcricao = await asyncio.wait_for(
                self.stt.transcrever(audio, self.config.stt.idioma),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            self.publicar(sessao_id, "erro", mensagem="STT timeout (15s): áudio não transcrito.")
            self._status(sessao_id, EstadoTurno.ERRO)
            return None
        except Exception as erro:  # noqa: BLE001
            self.publicar(sessao_id, "erro", mensagem=f"Falha na transcrição: {erro}")
            self._status(sessao_id, EstadoTurno.ERRO)
            return None
        self.metricas.registrar(
            "stt", (time.monotonic() - inicio) * 1000, sessao_id=sessao_id
        )
        logger.info("processar_audio: transcricao=%r", transcricao)
        self.publicar(sessao_id, "transcript", texto=transcricao, final=True, origem="voz")
        if transcricao:
            self.iniciar_turno(sessao_id, transcricao, "voz")
        return transcricao

    async def _executar_turno(
        self,
        sessao_id: str,
        texto: str,
        origem: str,
        agente_explicito: Optional[str],
        cancelamento: asyncio.Event,
    ) -> None:
        inicio_processamento = time.monotonic()
        sessao = self.obter_sessao(sessao_id, agente_explicito)
        sessao_id = sessao.id
        try:
            texto = self._validar_texto(texto, self.config.seguranca.max_texto_chars)
        except ValueError as erro:
            self.publicar(sessao_id, "erro", mensagem=str(erro))
            return

        decisao = self.router.route(texto, agente_explicito)
        if decisao.agente_id not in self.adaptadores:
            decisao.agente_id = self.config.agente_padrao
        sessao.agente_id = decisao.agente_id
        cfg_agente = self.config.agente(decisao.agente_id)
        if cfg_agente:
            sessao.voz_id = cfg_agente.voz
        self.historico.salvar_sessao(sessao, salvar_mensagens=False)
        self.publicar(sessao_id, "transcript", texto=texto, final=True, origem=origem)
        self.publicar(sessao_id, "routing", **decisao.para_dict())
        self.historico.registrar_evento(
            "ROTEAMENTO",
            sessao_id=sessao_id,
            agente_id=decisao.agente_id,
            confianca=decisao.confidence,
            motivo=decisao.reason,
        )

        sessao.adicionar(
            Mensagem(
                id=novo_id("msg_"),
                remetente="usuario",
                conteudo=texto,
                agente_id=decisao.agente_id,
                origem=origem,
            )
        )
        intencao = self.parser_comandos.parse(texto)
        if intencao.operacional:
            if await self._processar_comando(sessao, intencao, cancelamento):
                self.metricas.registrar(
                    "processamento",
                    (time.monotonic() - inicio_processamento) * 1000,
                    sessao_id=sessao_id,
                    agente=decisao.agente_id,
                    operacional=True,
                )
                return

        self._status(sessao_id, EstadoTurno.PENSANDO, agente=decisao.agente_id)

        adaptador = self.adaptadores[decisao.agente_id]
        partes: List[str] = []
        try:
            async for token in adaptador.responder(
                texto, sessao.contexto()[:-1], cancelamento
            ):
                if cancelamento.is_set():
                    break
                if token:
                    partes.append(token)
                    self.publicar(
                        sessao_id, "token", texto=token, agente=decisao.agente_id
                    )
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # noqa: BLE001
            self.publicar(
                sessao_id,
                "erro",
                mensagem=f"Falha no agente {decisao.agente_id}: {type(erro).__name__}",
                agente=decisao.agente_id,
            )
            self._status(sessao_id, EstadoTurno.ERRO)
            return

        if cancelamento.is_set() or not "".join(partes).strip():
            return

        resposta = "".join(partes).strip()
        sessao.adicionar(
            Mensagem(
                id=novo_id("msg_"),
                remetente="agente",
                conteudo=resposta,
                agente_id=decisao.agente_id,
                origem="sistema",
            )
        )
        self.historico.salvar_sessao(
            sessao,
            salvar_mensagens=self.config.historico.salvar_transcricoes,
        )
        self.historico.registrar_evento(
            "TURNO_CONCLUIDO", sessao_id=sessao_id, agente_id=decisao.agente_id
        )
        self.publicar(
            sessao_id,
            "answer",
            texto=resposta,
            agente=decisao.agente_id,
            voz=self.voz_para_agente(decisao.agente_id) or sessao.voz_id,
            velocidade=self.config.tts.velocidade,
            altura=self.config.tts.altura,
            sintetiza_no_servidor=self.tts.sintetiza_no_servidor,
        )
        self.metricas.registrar(
            "processamento",
            (time.monotonic() - inicio_processamento) * 1000,
            sessao_id=sessao_id,
            agente=decisao.agente_id,
        )
        await self._sintetizar(
            sessao_id, resposta, sessao.voz_id, decisao.agente_id, cancelamento
        )

    async def _sintetizar(
        self,
        sessao_id: str,
        texto: str,
        voz: str,
        agente_id: str,
        cancelamento: asyncio.Event,
    ) -> None:
        if not self.tts.sintetiza_no_servidor:
            # O cliente sintetiza e informa speech_start/speech_end.
            return
        self._status(sessao_id, EstadoTurno.FALANDO, agente=agente_id)
        inicio = time.monotonic()
        try:
            audio = await self.tts.sintetizar(
                texto,
                voz=voz,
                velocidade=self.config.tts.velocidade,
                altura=self.config.tts.altura,
            )
        except Exception as erro:  # noqa: BLE001
            self.metricas.registrar(
                "tts", (time.monotonic() - inicio) * 1000,
                sessao_id=sessao_id, falha=type(erro).__name__,
            )
            # Alternativa de reprodução: o cliente sintetiza localmente.
            self.publicar(
                sessao_id,
                "speak_fallback",
                texto=texto,
                voz=voz,
                velocidade=self.config.tts.velocidade,
                altura=self.config.tts.altura,
            )
            return
        self.metricas.registrar(
            "tts", (time.monotonic() - inicio) * 1000, sessao_id=sessao_id
        )
        if audio is None or cancelamento.is_set():
            return
        self.publicar(
            sessao_id,
            "audio",
            dados=base64.b64encode(audio.dados).decode("ascii"),
            content_type=audio.content_type,
            formato=audio.formato,
            agente=agente_id,
        )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def fechar(self) -> None:
        for tarefa in list(self._turnos.values()):
            tarefa.cancel()
        for sessao_id in list(self._capturas):
            self.parar_captura(sessao_id)
        await self.gerenciador.fechar()
        for adaptador in self.adaptadores.values():
            try:
                await adaptador.fechar()
            except Exception:  # noqa: BLE001
                pass
        self.auditoria.registrar("GATEWAY_ENCERRADO")

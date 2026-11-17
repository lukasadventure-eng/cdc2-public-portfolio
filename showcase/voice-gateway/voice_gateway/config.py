# -*- coding: utf-8 -*-
"""Configuração do Voice Gateway.

Fontes, em ordem de precedência (a última vence):
  1. valores padrão deste módulo;
  2. ``voice_gateway/data/config.json`` (criado do example na primeira execução);
  3. variáveis de ambiente ``VOICE_GATEWAY_*``.

Nenhuma credencial é lida daqui. O token de acesso vive em ``data/token``
(com permissões restritas) ou em ``VOICE_GATEWAY_TOKEN``.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

PACOTE = Path(__file__).resolve().parent
RAIZ_REPOSITORIO = PACOTE.parent
DIRETORIO_DADOS = PACOTE / "data"
DIRETORIO_WEB = PACOTE / "web"
ARQUIVO_CONFIG = DIRETORIO_DADOS / "config.json"
ARQUIVO_EXEMPLO = PACOTE / "config.example.json"
ARQUIVO_TOKEN = DIRETORIO_DADOS / "token"

# Aviso produzido quando uma configuração da v1 (modo consulta) é detectada.
# A elevação para execução exige opt-in explícito do operador.
AVISO_CONFIG_LEGADA = ""


@dataclass
class ServidorConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    # Origens permitidas para o navegador. ``*`` só deve ser usado com token.
    cors_origins: List[str] = field(
        default_factory=lambda: [
            "http://localhost:8765",
            "http://127.0.0.1:8765",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )


@dataclass
class SegurancaConfig:
    # true = exige token mesmo escutando apenas em loopback.
    exigir_token: bool = True
    # Tamanho máximo de um chunk de áudio recebido (bytes, já em base64).
    max_chunk_bytes: int = 262_144
    # Tamanho máximo do texto transcrito/explicitado por turno.
    max_texto_chars: int = 8_000
    # Limite de mensagens WebSocket por minuto por conexão.
    limite_mensagens_por_minuto: int = 600
    # Operações críticas (autorizar/executar) exigem confirmação explícita.
    permitir_operacoes_criticas_por_voz: bool = False


@dataclass
class AudioConfig:
    # Taxa de amostragem do canal de áudio do gateway.
    sample_rate: int = 16_000
    canais: int = 1
    # VAD de energia no servidor (quando o cliente não faz VAD próprio).
    vad_habilitado: bool = True
    vad_limiar_rms: float = 0.012
    vad_quadros_silencio: int = 18
    # Áudio bruto NUNCA é persistido por padrão.
    reter_audio: bool = False


@dataclass
class STTConfig:
    # ``browser`` usa a Web Speech API no cliente; ``local`` aponta para um
    # servidor HTTP compatível (VoiceStudio local API / whisper.cpp / faster-whisper).
    provedor: str = "browser"
    url_local: str = "http://127.0.0.1:8000/v1/audio/transcriptions"
    modelo_local: str = "whisper-large-v3"
    idioma: str = "pt-BR"
    chave_api: str = ""  # preenchida por env, nunca versionada


@dataclass
class TTSConfig:
    # ``browser`` usa speechSynthesis; ``voicestudio`` usa a API local;
    # ``openai`` usa a API da OpenAI (opcional).
    provedor: str = "browser"
    url_local: str = "http://127.0.0.1:8000/v1/audio/speech"
    modelo_local: str = "omnivoice"
    voz_salomao: str = "salomao-ptbr"
    voz_cdc: str = "cdc-ptbr"
    voz_opencode: str = "opencode-ptbr"
    velocidade: float = 1.0
    altura: float = 1.0
    chave_api: str = ""


@dataclass
class HistoricoConfig:
    habilitado: bool = True
    # Caminho relativo ao diretório de dados.
    banco: str = "historico.db"
    retencao_dias: int = 30  # 0 = indefinido
    salvar_transcricoes: bool = True


@dataclass
class CapturaConfig:
    # "navegador" usa getUserMedia; "servidor" captura pelo WASAPI do Windows
    # (útil quando o navegador bloqueia o microfone).
    modo: str = "navegador"
    dispositivo: str = ""
    limiar: float = 0.012
    quadros_silencio: int = 18
    continuo: bool = True
    adaptativo: bool = True
    multiplicador_ruido: float = 3.0
    limiar_minimo: float = 0.004
    janela_ruido: int = 60


@dataclass
class WakeConfig:
    habilitado: bool = False
    palavras: List[str] = field(default_factory=lambda: ["Salomão", "Salomão AI"])
    cooldown_s: float = 2.5
    # Nunca usa STT de navegador para escuta contínua (pode enviar áudio ao
    # fabricante). A ativação exige um provedor local.
    exigir_stt_local: bool = True
    indicador_sonoro: bool = True


@dataclass
class OperacoesConfig:
    habilitado: bool = True
    # Tarefas normais de desenvolvimento NÃO exigem confirmação por voz:
    # as permissões do OpenCode continuam integralmente em vigor (nunca --auto).
    confirmar_escrita: bool = False
    # Operações destrutivas/de alto impacto exigem confirmação por padrão.
    # Desativar isto reduz a proteção — use apenas em ambiente controlado.
    confirmar_destrutivo: bool = True
    timeout_sec: int = 300
    max_eventos_por_tarefa: int = 200
    anunciar_eventos: List[str] = field(
        default_factory=lambda: [
            "tarefa_recebida",
            "confirmacao_solicitada",
            "tarefa_confirmada",
            "sessao_iniciada",
            "autorizacao_necessaria",
            "tarefa_concluida",
            "tarefa_interrompida",
            "tarefa_falha",
        ]
    )
    anunciar_ferramentas: bool = False
    anunciar_parciais: bool = False
    max_anuncios_por_minuto: int = 6
    notificacoes_silenciadas: bool = False
    nao_perturbar_inicio: str = ""
    nao_perturbar_fim: str = ""
    banco: str = "operacoes.db"


@dataclass
class AgenteConfig:
    id: str
    nome: str
    descricao: str
    adaptador: str
    voz: str
    cor: str = "#7c9cff"
    ativo: bool = True
    opcoes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    servidor: ServidorConfig = field(default_factory=ServidorConfig)
    seguranca: SegurancaConfig = field(default_factory=SegurancaConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    historico: HistoricoConfig = field(default_factory=HistoricoConfig)
    operacoes: OperacoesConfig = field(default_factory=OperacoesConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    captura: CapturaConfig = field(default_factory=CapturaConfig)
    agente_padrao: str = "salomao"
    agentes: List[AgenteConfig] = field(default_factory=list)

    def agente(self, agente_id: str) -> AgenteConfig | None:
        for item in self.agentes:
            if item.id == agente_id:
                return item
        return None

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


def config_padrao() -> Config:
    """Configuração de fábrica, com os três agentes integrados."""
    return Config(
        agentes=[
            AgenteConfig(
                id="salomao",
                nome="Salomão AI",
                descricao="Inteligência privada, local e com memória própria.",
                adaptador="salomao",
                voz="salomao-ptbr",
                cor="#8b7cff",
                opcoes={
                    "modo": "auto",  # auto | nativo | ollama
                    "raiz_nativa": r"D:\Salomão_IA",
                    "url_ollama": "http://127.0.0.1:11434",
                    "modelo": "qwen3:8b",
                    "temperature": 0.7,
                },
            ),
            AgenteConfig(
                id="cdc",
                nome="CDC",
                descricao="Consultas e acompanhamento do Agente CDC. Nunca autoriza por voz.",
                adaptador="cdc",
                voz="cdc-ptbr",
                cor="#4fd1c5",
                opcoes={
                    "raiz": r"D:\Salomao_CDC_Agente",
                    "timeout_sec": 20,
                    "permitir_consultas_rede": False,
                    "url_ollama": "http://127.0.0.1:11434",
                    "modelo": "qwen3:8b",
                },
            ),
            AgenteConfig(
                id="opencode",
                nome="OpenCode",
                descricao="Execução de tarefas no ambiente OpenCode (somente com autorização).",
                adaptador="opencode",
                voz="opencode-ptbr",
                cor="#ffb454",
                ativo=True,
                opcoes={
                    "comando": "opencode",
                    "modelo": "ollama/qwen3:8b",
                    "timeout_sec": 300,
                    # execucao permite tarefas reais, mas NUNCA usa --auto:
                    # as permissões do OpenCode permanecem em vigor.
                    "modo": "execucao",  # consulta | execucao
                },
            ),
        ]
    )


def _mesclar(destino: Dict[str, Any], origem: Dict[str, Any]) -> Dict[str, Any]:
    """Mesclado recursivo de dicionários, sem alterar os argumentos."""
    resultado = copy.deepcopy(destino)
    for chave, valor in origem.items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _mesclar(resultado[chave], valor)
        else:
            resultado[chave] = valor
    return resultado


def _from_dict(dados: Dict[str, Any]) -> Config:
    base = config_padrao().para_dict()
    merged = _mesclar(base, dados)
    return Config(
        servidor=ServidorConfig(**merged["servidor"]),
        seguranca=SegurancaConfig(**merged["seguranca"]),
        audio=AudioConfig(**merged["audio"]),
        stt=STTConfig(**merged["stt"]),
        tts=TTSConfig(**merged["tts"]),
        historico=HistoricoConfig(**merged["historico"]),
        operacoes=OperacoesConfig(**merged["operacoes"]),
        wake=WakeConfig(**merged["wake"]),
        captura=CapturaConfig(**merged["captura"]),
        agente_padrao=merged.get("agente_padrao", "salomao"),
        agentes=[AgenteConfig(**item) for item in merged.get("agentes", [])],
    )


_VARIAVEIS = {
    "VOICE_GATEWAY_HOST": ("servidor", "host", str),
    "VOICE_GATEWAY_PORT": ("servidor", "port", int),
    "VOICE_GATEWAY_EXIGIR_TOKEN": ("seguranca", "exigir_token", bool),
    "VOICE_GATEWAY_CAPTURA_MODO": ("captura", "modo", str),
    "VOICE_GATEWAY_CAPTURA_DISPOSITIVO": ("captura", "dispositivo", str),
    "VOICE_GATEWAY_WAKE_HABILITADO": ("wake", "habilitado", bool),
    "VOICE_GATEWAY_STT_PROVEDOR": ("stt", "provedor", str),
    "VOICE_GATEWAY_STT_URL": ("stt", "url_local", str),
    "VOICE_GATEWAY_STT_CHAVE": ("stt", "chave_api", str),
    "VOICE_GATEWAY_TTS_PROVEDOR": ("tts", "provedor", str),
    "VOICE_GATEWAY_TTS_URL": ("tts", "url_local", str),
    "VOICE_GATEWAY_TTS_CHAVE": ("tts", "chave_api", str),
    "VOICE_GATEWAY_RETER_AUDIO": ("audio", "reter_audio", bool),
    "VOICE_GATEWAY_RETENCAO_DIAS": ("historico", "retencao_dias", int),
    "VOICE_GATEWAY_CONFIRMAR_ESCRITA": ("operacoes", "confirmar_escrita", bool),
    "VOICE_GATEWAY_CONFIRMAR_DESTRUTIVO": ("operacoes", "confirmar_destrutivo", bool),
    "VOICE_GATEWAY_TIMEOUT_OPERACAO": ("operacoes", "timeout_sec", int),
    "VOICE_GATEWAY_AGENTE_PADRAO": ("agente_padrao", None, str),
}


def _converter(valor: str, tipo: type) -> Any:
    if tipo is bool:
        return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}
    return tipo(valor)


def carregar_config() -> Config:
    DIRETORIO_DADOS.mkdir(parents=True, exist_ok=True)
    dados: Dict[str, Any] = {}
    if ARQUIVO_CONFIG.exists():
        try:
            dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            dados = {}
    elif ARQUIVO_EXEMPLO.exists():
        try:
            ARQUIVO_CONFIG.write_text(
                ARQUIVO_EXEMPLO.read_text(encoding="utf-8"), encoding="utf-8"
            )
            dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            dados = {}

    # Configuração v1 detectada: NÃO elevamos a postura de segurança sem
    # consentimento explícito. O operador deve definir
    # VOICE_GATEWAY_ENABLE_EXECUCAO=1 para habilitar execução real.
    global AVISO_CONFIG_LEGADA
    AVISO_CONFIG_LEGADA = ""
    if dados and "operacoes" not in dados:
        legada = any(
            agente.get("id") == "opencode"
            and isinstance(agente.get("opcoes"), dict)
            and agente["opcoes"].get("modo") == "consulta"
            for agente in dados.get("agentes", [])
        )
        if legada:
            AVISO_CONFIG_LEGADA = (
                "Configuração v1 detectada: o OpenCode permanece em modo consulta. "
                "Para habilitar execução real, defina VOICE_GATEWAY_ENABLE_EXECUCAO=1."
            )
            if os.environ.get("VOICE_GATEWAY_ENABLE_EXECUCAO", "").strip().lower() in {
                "1", "true", "sim", "yes"
            }:
                for agente in dados.get("agentes", []):
                    if agente.get("id") == "opencode" and isinstance(
                        agente.get("opcoes"), dict
                    ):
                        agente["opcoes"]["modo"] = "execucao"
                try:
                    ARQUIVO_CONFIG.write_text(
                        json.dumps(dados, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
                AVISO_CONFIG_LEGADA = ""

    cfg = _from_dict(dados)
    bruto = cfg.para_dict()
    for variavel, (secao, chave, tipo) in _VARIAVEIS.items():
        if variavel not in os.environ:
            continue
        valor = _converter(os.environ[variavel], tipo)
        if chave is None:
            bruto[secao] = valor
        elif secao in bruto and chave in bruto[secao]:
            bruto[secao][chave] = valor
    return _from_dict(bruto)


def obter_token(cfg: Config, gerar_se_ausente: bool = True) -> str:
    """Obtém o token de acesso. Nunca é gravado em log nem exposto na API."""
    env = os.environ.get("VOICE_GATEWAY_TOKEN", "").strip()
    if env:
        return env
    try:
        if ARQUIVO_TOKEN.exists():
            existente = ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
            if existente:
                return existente
        if gerar_se_ausente:
            import secrets

            token = secrets.token_urlsafe(32)
            ARQUIVO_DADOS = ARQUIVO_TOKEN.parent
            ARQUIVO_DADOS.mkdir(parents=True, exist_ok=True)
            ARQUIVO_TOKEN.write_text(token + "\n", encoding="utf-8")
            try:
                ARQUIVO_TOKEN.chmod(0o600)
            except OSError:
                pass  # Windows: a ACL padrão do diretório do usuário já protege.
            return token
    except OSError:
        pass
    return ""

# Voice Gateway 3.0 — consolidação operacional

Camada independente de modelos que transforma CDC e Salomão AI em agentes com os
quais o proprietário conversa por voz, no computador ou no celular, permite
ativação por “Salomão” com STT local, interrupção acústica, verificação de
falante e delegação **real** de tarefas ao OpenCode.

```
   Microfone / Web Speech        Voice Gateway (este projeto)           Agentes
   ┌────────────────────┐    ┌───────────────────────────────┐   ┌──────────────┐
   │ navegador (PWA)    │◄──►│ HTTP + WebSocket              │──►│ Salomão AI   │
   │ STT/TTS locais  ───┼───►│ sessões · roteamento · turnos │   │ CDC          │
   │ VAD · barge-in     │◄───│ adaptadores · histórico · audit│   │ OpenCode     │
   └────────────────────┘    └───────────────────────────────┘   └──────────────┘
                                      ▲
                                      │ adaptadores trocáveis
                          ┌───────────┴────────────┐
                          │ VoiceStudio / Whisper  │
                          │ Ollama local qwen3:8b  │
                          │ provedores externos    │
                          └────────────────────────┘
```

---

## 1. Estado atual

Implementado e testado (81/81 testes automatizados + smokes reais):

### Operação em um comando

```powershell
.\.venv-voice\Scripts\python.exe -m voice_gateway.operar iniciar
.\.venv-voice\Scripts\python.exe -m voice_gateway.operar status
.\.venv-voice\Scripts\python.exe -m voice_gateway.operar teste
.\.venv-voice\Scripts\python.exe -m voice_gateway.operar parar
```

`iniciar` sobe o STT local (porta 8010) e o gateway (porta 8765), grava PIDs em
`data/pids.json` e registra logs em `data/stt.log` e `data/gateway.log`.
Abra `http://127.0.0.1:8765` e informe o token exibido no log do gateway.

### Dependências e provedores instalados

| Item | Configuração equipada neste ambiente |
|---|---|
| STT | `faster-whisper 1.2.1`, modelo `small`, 16 kHz, VAD; GPU CUDA com fallback automático para CPU (CTranslate2 sem `cublas64_12.dll` neste Windows) |
| Servidor STT | `/v1/audio/transcriptions` em `http://127.0.0.1:8010` — áudio processado localmente |
| TTS | `browser` (speechSynthesis, voz pt-BR do dispositivo); adaptador `local` disponível para VoiceStudio |
| Wake word | “Salomão” / “Salomão AI”, tolerante a variações do ASR (ex.: “Salumão”), cooldown 2,5 s |
| Falante | `speechbrain 1.1.2` + ECAPA-TDNN local, limiar cosine 0,75, embeddings persistidos no SQLite |
| Hardware | RTX 4060 8 GB, 17 GB RAM, Windows 10, Python 3.11.9 |

### Resultados reais medidos

| Medição | Resultado |
|---|---|
| STT local (“Salomão” sintetizado em pt-BR) | transcreveu “Salumão.”; detector normalizou para `salomao` |
| Ativação por wake (áudio real via WebSocket) | 5,9 s (modelo frio) → 3,2 s (aquecido) |
| Verificação de falante | titular cadastrado identificado; falante diferente rejeitado; perfil excluído |
| Conversação contínua | 10 interações, 10 respostas, 20 mensagens persistidas, 0 erros |
| Interrupção | 20 ciclos em integração; 3 interrupções reais via WebSocket: 15–16 ms no servidor |
| OpenCode | v2.3.0, modelo local `ollama/qwen3:8b`, `auto_aprovacao: false` |

| Responsabilidade do enunciado | Onde está |
|---|---|
| Captura de áudio | `web/app.js` (`getUserMedia`, PCM16 16 kHz) |
| Transcrição | `stt/` — `browser` (Web Speech) ou `local` (VoiceStudio/Whisper) |
| Identificação do destinatário | `core/router.py` — explícita e automática (pt-BR sem acentos) |
| Gerenciamento de sessões | `core/gateway.py` + `core/history.py` |
| Encaminhamento contextual | `core/gateway.py` (`Sessao.contexto()`) |
| Recebimento de respostas | streaming de tokens via WebSocket |
| Conversão texto→voz | `tts/` — `browser` (speechSynthesis) ou `local` (VoiceStudio) |
| Streaming de áudio | evento `audio` (base64) + `speechSynthesis` no cliente |
| Interrupções | `barge_in` → `Gateway.interromper()` (cancela geração e síntese) |
| Continuidade | histórico SQLite por sessão; múltiplas abas no mesmo canal |
| Histórico | `core/history.py`, retenção configurável, auditoria com corrente de hash |
| Configuração de vozes | `config.example.json`, seletor na UI, prosódia (velocidade/altura) |
| Comandos operacionais por voz | `ops/comandos.py` — delegar, continuar, interromper, confirmar, explicar, ler resultado, consultar agente |
| Tarefas e eventos | `ops/gerenciador.py`, `ops/persistencia.py`, `ops/notificacoes.py` |
| Execução real no OpenCode | `agents/opencode.py` — sessões, NDJSON, ferramentas, cancelamento |
| Painel operacional | `web/` — indicadores, tarefa ativa, trilha de eventos, confirmação |

---

## 1.1 Controle operacional (novo na 2.0)

Exemplo real já executado:

> “Salomão, solicite ao OpenCode que responda apenas: PRONTO”

Fluxo: comando reconhecido → Salomão registra o pedido em seu histórico nativo →
tarefa criada → sessão OpenCode (`--session`, reutilizável) → eventos JSON reais
(`step_start`, `text`, `tool_use`, `step_finish`) → conclusão → resultado falado.

### Comandos aceitos

| Comando | Ação |
|---|---|
| “Salomão, peça ao OpenCode para desenvolver…” | delega tarefa ao OpenCode |
| “CDC, encaminhe essa tarefa para o agente responsável” | coordenação pelo CDC |
| “Continue a execução” | retoma na **mesma** sessão do OpenCode |
| “Interrompa a execução” | cancela o processo e registra `interrompida` |
| “Confirme” / “Sim” | confirma operação de alto impacto |
| “Explique o que está acontecendo” | resume estado e eventos recentes |
| “Leia o último resultado” | fala o resultado da última tarefa |
| “Qual agente está trabalhando?” | informa agente e tarefa ativos |
| “Quais tarefas?” | lista tarefas registradas |

### Segurança operacional

- O adaptador **nunca** passa `--auto` ao OpenCode: todas as permissões de
  ferramentas do OpenCode permanecem em vigor.
- Modelo padrão do OpenCode: `ollama/qwen3:8b` — execução local, sem cota e sem
  nuvem. Outros modelos podem ser configurados em `opcoes.modelo`.
- Tarefas normais de desenvolvimento não exigem confirmação por voz; operações
  **destrutivas/de alto impacto** (apagar, resetar, instalar, publicar, deploy)
  exigem “confirmar” explícito **por padrão**. Desativar
  `confirmar_destrutivo` remove essa proteção — faça isso apenas em ambiente
  controlado e ciente do risco.
- Se o OpenCode estiver indisponível ou a cota esgotar, o gateway reporta o
  estado real — **nenhuma execução é simulada**.
- Saídas de ferramentas nunca entram nos eventos (evita vazamento de segredos).

### Endpoints operacionais

`GET/POST /api/tarefas`, `GET /api/tarefas/{id}`,
`POST /api/tarefas/{id}/confirmar`, `POST /api/tarefas/{id}/cancelar`,
`GET /api/operacoes/eventos`, `GET /api/operacoes/status`.

Eventos WebSocket: `comando_reconhecido`, `operacional`, `operacao_status`.
Anúncios falados são filtrados por política (`anunciar_eventos`, limites por
minuto) para evitar notificações excessivas.

---

## 2. VoiceStudio — avaliação técnica

Projeto: <https://github.com/debpalash/VoiceStudio> (Palash Debnath), site
<https://voicestudio.sh/>. Licença **AGPL-3.0** (uso comercial permitido nos termos
da AGPL; modelos e vozes têm licenças próprias — clonagem só com consentimento).

**Conclusão:** o VoiceStudio é um **estúdio de produção local** (clonagem, voice
design, dublagem, transcrição, audiolivros, API local e MCP), não um motor
conversacional de baixa latência. Foi tratado como **provedor opcional de
STT/TTS**, não como teto tecnológico nem como cérebro do gateway.

| Capacidade | Uso no gateway |
|---|---|
| TTS local (API `/v1/audio/speech`) | adaptador `tts.local`, ativável com `VOICE_GATEWAY_TTS_PROVEDOR=local` |
| STT local (API `/v1/audio/transcriptions`) | adaptador `stt.local`, mesmo padrão OpenAI-compatível |
| Voice cloning / voice design | suporte via API local; exige amostras autorizadas e consentimento |
| MCP | não acoplado ao gateway; o gateway é a interface Conversacional, VoiceStudio permanece a ferramenta de produção |
| Requisitos | CPU funciona; GPU acelera. Sem custo de nuvem |
| Restrição | AGPL-3.0 — se o gateway for distribuído como derivado, a obrigação de código aberto se aplica; uso interno/privado não dispara distribuição |

O padrão de fábrica usa STT/TTS no navegador para entrega imediata sem serviços
pagos. Para 100% local e offline, configure os adaptadores `local`.

---

## 3. Instalação e execução

```powershell
cd "C:\Users\Lucas\Documents\Projeto Padrão"
python -m venv .venv-voice
.\.venv-voice\Scripts\python.exe -m pip install -r voice_gateway\requirements.txt
.\.venv-voice\Scripts\python.exe -m voice_gateway.run
```

O terminal exibe o endereço e o **token de acesso**. Abra
`http://127.0.0.1:8765`, informe o token no ícone ⚙ e conecte.

Para expor na rede (celular na mesma Wi-Fi), use Tailscale Serve ou
`--host 0.0.0.0` **com token e TLS**. O token também pode vir de
`VOICE_GATEWAY_TOKEN`. Nunca é gravado em log, relatório ouresposta da API.

### Configuração

`voice_gateway/data/config.json` é criado de `config.example.json` na primeira
execução. Sobrescreva por variáveis de ambiente:

| Variável | Efeito |
|---|---|
| `VOICE_GATEWAY_TOKEN` | token de acesso |
| `VOICE_GATEWAY_HOST` / `VOICE_GATEWAY_PORT` | escuta |
| `VOICE_GATEWAY_STT_PROVEDOR` | `browser` \| `local` |
| `VOICE_GATEWAY_STT_URL` | endpoint local de transcrição |
| `VOICE_GATEWAY_TTS_PROVEDOR` | `browser` \| `local` |
| `VOICE_GATEWAY_TTS_URL` | endpoint local de síntese |
| `VOICE_GATEWAY_RETER_AUDIO` | `true` permite reter áudio (padrão `false`) |
| `VOICE_GATEWAY_RETENCAO_DIAS` | retenção de transcrições (`0` = indefinida) |
| `VOICE_GATEWAY_ENABLE_EXECUCAO` | `1` migra explicitamente config v1 de `consulta` para `execucao` |

Instalações da v1 permanecem em **modo consulta** até opt-in explícito — a
elevação silenciosa da postura de segurança não é feita pelo gateway.

---

## 4. Agentes

### Salomão AI

- **Modo nativo (padrão, `auto`):** o gateway inicia
  `bridges/salomao_bridge.py` com o Python do venv de `D:\Salomão_IA` e fala
  somente com `ServicoSalomao`. Identidade, memória, sessões, retenção,
  constituição e segurança continuam pertencendo ao Salomão AI — o gateway não
  reimplementa nem substitui nada.
- **Modo `ollama`:** fallback direto em `http://127.0.0.1:11434` com
  `qwen3:8b`, reproduzindo o prompt de identidade e a regra de contexto de
  `Nucleo/servicos.py`. Usado se a instalação nativa não estiver disponível.
- **Interlocução operacional:** comandos são registrados no histórico nativo
  (`registrar`) e as confirmações faladas são geradas pelo próprio
  `ServicoSalomao` (`feedback`), com a mesma identidade/modelo, sem gravar
  mensagens internas na memória de conversa.

Verificação em tempo real: `GET /api/agentes/salomao/status` (`modo_efetivo`).

### CDC

- Consulta determinística da configuração real em `D:\Salomao_CDC_Agente`,
  sem rede por padrão (`permitir_consultas_rede: false`).
- **Fronteira de autoridade:** pedidos de autorizar/executar/escrever recebem
  recusa explícita e orientação para o fluxo humano oficial. A voz não concede
  permissões administrativas; `permitir_operacoes_criticas_por_voz` é `false`.
- `consultar_pull_requests` por `gh` só se habilitado na configuração.

### OpenCode

- CLI real `opencode run --format json --session ... --standalone --model
  ollama/qwen3:8b`, detectada por `shutil.which` (necessário no Windows por
  causa dos shims `.CMD` do npm).
- Sessões são criadas e reutilizadas; IDs ficam no SQLite operacional.
- Eventos reais são mapeados para a trilha: etapa iniciada/finalizada, texto
  parcial, ferramenta utilizada, autorização necessária, conclusão e falha.
- Cancelamento termina o processo real; `Continue a execução` reusa a sessão.
- Modo `consulta` disponível para ambientes que devem permanecer somente leitura.

### Roteamento

- **Explícito:** seletor na UI ou comandos (“falar com o CDC”, “usar o codex”).
- **Automático:** pontuação por palavras-chave em pt-BR normalizado (sem
  acentos), com detecção de `SAL-123`, “auditoria”, “memória”, “implementar” etc.
  Sem chamada de modelo para decidir — latência zero e decisão auditável.
- Cada agente mantém identidade e contexto próprios; nunca são fundidos.

---

## 5. Protocolo WebSocket

`ws://host/ws/voice?token=...&sessao=...`

| Cliente → servidor | Servidor → cliente |
|---|---|
| `hello`, `set_agent` | `ready`, `routing` |
| `text_input`, `transcript` | `transcript`, `status`, `token` |
| `audio_start`, `audio_chunk`, `audio_end` | `answer`, `audio`, `status` |
| `barge_in`, `cancel` | `stop_speech`, `interrompido` |
| `speech_start`, `speech_end`, `ping` | `speech_start`, `speech_end`, `erro`, `pong` |

O cancelamento é cooperativo: `barge_in` sinaliza `asyncio.Event`, o adaptador
para de gerar tokens e o cliente chama `speechSynthesis.cancel()` imediatamente.

---

## 6. Segurança e privacidade

- Token obrigatório em HTTP e WebSocket; comparação em tempo constante.
- Escuta somente em `127.0.0.1` por padrão; CORS restrito a origens locais.
- Limite de mensagens por conexão e de tamanho de áudio/texto.
- Áudio bruto **não** é persistido (`reter_audio: false`). Transcrições seguem
  retenção configurável e exclusão manual explícita.
- Auditoria append-only com corrente SHA-256; campos sensíveis (token, chave,
  áudio, conteúdo) são removidos antes do registro.
- Conteúdo de modelo/arquivos é sempre tratado como dado, nunca instrução.
- Clonagem de voz exige amostras autorizadas pelo titular — nenhuma amostra é
  coletada automaticamente pelo gateway.

---

## 7. Testes

```powershell
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.run_all
```

80 testes: roteamento, autenticação, auditoria/tamper, SQLite/retenção,
registro de adaptadores, WAV, turnos completos, barge-in, API HTTP, parser de
comandos, gerenciador de tarefas, confirmação, cancelamento, escopo por sessão,
sanitização de erros, isolamento de ambiente, prompt seguro para o shim `.CMD`,
integração operacional, detector de wake word, métricas, notificações, perfis
de falante, 10 interações contínuas, 20 interrupções consecutivas e
persistência/recuperação de contexto.

Teste de fumaça contra o servidor real (requer Ollama e o gateway rodando):

```powershell
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_real
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_operacional
```

Validação real já executada com sucesso:

- WebSocket → Salomão AI **nativo** (`modo_efetivo: nativo`) → resposta em pt-BR;
- WebSocket → CDC → status somente-leitura; `barge_in` interrompendo a geração;
- **“Salomão, peça ao OpenCode que responda apenas: PRONTO”** → tarefa criada,
  sessão real, eventos `sessao_iniciada → execucao_em_andamento →
  etapa_concluida → tarefa_concluida`, resultado “pronto” lido por voz;
- OpenCode v2.3.0 detectado com `auto_aprovacao: false` e modelo local
  `ollama/qwen3:8b`.

---

## 7.1 Voice Gateway 3.0 — critérios de conclusão

| Critério | Implementação | Evidência |
|---|---|---|
| 16.1 Ativação por palavra-chave | `wake/detector.py` + captura local no cliente; “Salomão”/“salomao”, liga/desliga, indicador visual e sonoro, alternativa manual | `test_wake.py` (9 testes); `POST /api/wake/*` |
| 16.2 Conversação contínua | VAD no cliente, modo contínuo, contexto ampliado para 40 mensagens, voz/texto na mesma sessão | `test_conversacao.py` (10 turnos), `smoke_conversacao.py` |
| 16.3 Interrupção em tempo real | `barge_in` local imediato + cancelamento da geração; tempos de detecção e total registrados separadamente | `test_conversacao.py` (20 interrupções), `/api/metricas`, `smoke_conversacao.py` |
| 16.4 Identidade vocal | `tts/` trocável por registry, voz por agente, prosódia na UI, fallback para síntese no cliente | `test_componentes.py`, lógica em `core/gateway.py` |
| 16.5 Reconhecimento de falante | `speakers/` com perfis, consentimento, amostras autorizadas, exclusão e `IdentificadorIndisponivel` | `test_falantes.py`; escopo parcial documentado abaixo |
| 16.6 Notificações proativas | política por evento, deduplicação por ID, silenciamento, janela de não perturbar, apenas eventos reais | `test_operacoes.py`, `/api/notificacoes` |
| 16.7 Integração com agentes | pontes nativas Salomão, adaptador CDC coordenador, OpenCode real com eventos | `smoke_real.py`, `smoke_operacional.py`, `test_operacoes.py` |
| 16.8 Persistência de contexto | `Historico` + `PersistenciaOperacoes` SQLite; tarefas ligadas à sessão; retenção configurável | `test_persistencia_contexto.py` |
| 16.9 Interface desktop/mobile | CSS responsivo, estados explícitos, painel operacional, wake e privacidade nas configurações | verificação no navegador (sem erros de console) |
| 16.10 Segurança/privacidade | token, sem `--auto`, confirmação de alto impacto, sanitização, áudio não retido, wake exige STT local | `test_seguranca.py`, `test_wake.py`, `test_operacoes.py` |
| 16.11 Estabilidade | `smoke_soak.py` com duração configurável, métricas e medição de memória | execução curta realizada; 2 h **não** declaradas sem execução |
| 16.12 Testes | 80 automatizados + 4 smokes reais | ver abaixo |
| 16.13 Documentação | este README + procedimentos abaixo | — |
| 16.14 Critério global | fluxos reais validados com Salomão, CDC e OpenCode | smokes reais |

### Testes simulados × reais

| Natureza | Testes | O que comprovam |
|---|---|---|
| **Simulados** (sem áudio/hardware externo) | `tests/run_all.py` — adaptadores `echo`/`contexto`, STT falso, subprocessos substituídos | lógica, estados, cancelamento, persistência, segurança |
| **Reais** (servidor + Ollama + OpenCode) | `smoke_real.py`, `smoke_operacional.py`, `smoke_conversacao.py`, `smoke_soak.py` | WebSocket real, Salomão nativo, CDC real, OpenCode v2.3.0 com modelo local `ollama/qwen3:8b` |

### Instalação, operação e recuperação

```powershell
# instalação
python -m venv .venv-voice
.\.venv-voice\Scripts\python.exe -m pip install -r voice_gateway\requirements.txt

# inicialização / encerramento
.\.venv-voice\Scripts\python.exe -m voice_gateway.run
# Ctrl+C encerra com auditoria e cancelamento de tarefas

# testes
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.run_all
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_real
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_operacional
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_conversacao
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_wake_real
.\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_falante_real
$env:VOICE_GATEWAY_SOAK_SECONDS=7200; .\.venv-voice\Scripts\python.exe -m voice_gateway.tests.smoke_soak
```

### Solução de problemas rápida

- **“Desconectado” / WebSocket 403:** o gateway foi iniciado com outro token.
  Use sempre `python -m voice_gateway.operar iniciar` (sem `--token`) e recarregue
  a página. O token correto está em `data/token`.
- **“Não aparece transcrição enquanto falo”:** com STT local, a transcrição
  final aparece **depois** que você termina a fala (o áudio é enviado ao
  reconhecedor local). A transcrição intermediária só existe com `stt=browser`.
- **Microfone negado no navegador:** use a captura pelo servidor. Em ⚙ →
  **Captura de áudio**, selecione “Microfone do servidor (Windows)”, escolha o
  dispositivo USB e clique no botão 🎤. O nível de áudio aparece no medidor e a
  transcrição é gerada pelo STT local — sem `getUserMedia`.
- **“Não ouço a resposta”:** confirme que o navegador não está mudo, que há
  voz pt-BR instalada e que a página teve interação do usuário (política de
  áudio do navegador). O gateway envia o evento `answer`; quem fala é o
  `speechSynthesis` do dispositivo quando `tts=browser`.

Recuperação de falhas: o gateway reconecta o WebSocket automaticamente; sessões e
tarefas sobrevivem a reinícios via SQLite; tarefas em execução são canceladas no
encerramento; se o OpenCode falhar, a tarefa vai para `falha` com erro sanitizado e
pode ser retomada com “Continue a execução” na mesma sessão.

### Ativação por voz e privacidade

- A ativação **só é habilitada quando o STT é local** (`stt.provedor = local`).
  Com `browser`, o gateway recusa ativar wake (409) porque o Web Speech do Chrome
  pode enviar áudio ao fabricante.
- O cliente captura áudio localmente, detecta fala por energia (VAD) e envia apenas
  o segmento falado ao STT local para decisão da palavra “Salomão”.
- Controles: ligar/desligar nas configurações, `POST /api/wake/ativar|desativar`,
  comando `set_wake` no WebSocket e botão de microfone como alternativa manual.
- Indicadores: pílula “escutando 'Salomão'”, estado “ativado por voz” e bip curto.
- **Falsas ativações conhecidas:** ruído que o STT local transcreva como
  “Salomão”; palavra dita em conversa com outra pessoa; eco de voz gravada.
  Mitigações: cooldown de 2,5 s, limite de 120 caracteres e exigência de limite
  de palavra. Sensibilidade depende da qualidade do modelo local — ajustável em
  `wake.cooldown_s` e no VAD da interface.

### Reconhecimento de falante — alcance atual

Implementado: cadastro com **consentimento obrigatório**, extração de embedding
ECAPA-TDNN local, contador de amostras autorizadas, listagem, exclusão,
identificação por similaridade cosine com limiar configurável
(`VG_SPEAKER_LIMIAR`, padrão 0,75) e fallback para “não identificado”.
Amostras brutas não são gravadas — apenas o vetor e o consentimento.
Validação real: titular cadastrado identificado, falante diferente rejeitado.

A biometria **nunca** autoriza operações sensíveis: autenticação continua sendo
token + permissões do OpenCode. Para uso cotidiano, é necessário cadastrar
amostras fornecidas e autorizadas por cada titular.

### Identidade vocal personalizada do Salomão

`voz/perfil.py` registra amostras **fornecidas pelo titular** com confirmação
explícita da frase `AUTORIZO_USO_DA_MINHA_VOZ`. A amostra fica em
`data/vozes/` (fora do Git); nunca é inventada ou presumida autorizada.
Endpoints: `GET/POST /api/voz`, `DELETE /api/voz/{id}`; a interface expõe
seleção de arquivo WAV + caixa de consentimento nas configurações.
O `voz_id` do agente é usado por `tts/` para seleção consistente entre sessões;
a **clonagem efetiva** depende de um provedor TTS local com suporte a clonagem
(VoiceStudio/Coqui XTTS) e da amostra autorizada — não disponível nesta sessão.
O gateway reporta honestamente `habilitado: false` enquanto não houver amostra.


- Web Speech API do Chrome pode enviar áudio ao fabricante do navegador; para
  privacidade estrita, use `stt.local` (VoiceStudio/Whisper).
- TTS do navegador depende das vozes pt-BR instaladas no dispositivo; o gateway
  escolhe a melhor disponível. Vozes consistentes entre dispositivos exigem
  `tts.local` com voz clonada autorizada.
- Identidade vocal própria do Salomão AI (clonagem com consentimento) depende
  de amostra autorizada e de um provedor TTS local compatível; a infraestrutura
  de seleção/prosódia já existe, a amostra não é fornecida pelo sistema.
- A ponte nativa do Salomão AI é cooperativa: se o processo for terminado no
  meio da geração, a resposta pode ser registrada pelo serviço original.
- Provedores remotos do OpenCode podem atingir cota (429). O padrão 2.0 usa
  `ollama/qwen3:8b` (local); se outro modelo for escolhido e falhar, o erro real
  é reportado e a tarefa vai para `falha` — nunca é marcada como concluída.
- Confirmações faladas de comandos operacionais são geradas pelo Salomão via
  modelo local; em ambientes sem Ollama, o gateway usa uma frase padrão do
  sistema e informa a origem no evento.
- No Windows, o adaptador usa o executável resolvido por `shutil.which` e envia
  um prompt de **uma linha** ao CLI: o shim `.CMD` do npm corrompe argumentos
  com quebras de linha e caracteres `<` / `>`.
- Mensagens de erro de subprocessos são sanitizadas (credenciais, URLs e
  caminhos removidos) antes de irem para eventos; a voz usa texto genérico.
- Ativação por “Salomão” usa o STT local instalado neste ambiente; sem ele, o
  gateway recusa a ativação e mantém o botão/manual como alternativa. O teste
  real injeta WAV pt-BR sintetizado; a captura por microfone físico depende do
  usuário falar com a interface aberta (o caminho de áudio é o mesmo).
- Identificação biométrica de falante está disponível com ECAPA-TDNN local e
  foi validada com duas vozes sintéticas; ainda exige amostras autorizadas de
  falantes reais para uso cotidiano. Ela nunca autoriza operações sensíveis.
- A latência da ativação (3,2 s aquecido) é dominada pelo STT local em CPU; a
  GPU CUDA do CTranslate2 não carregou `cublas64_12.dll` neste Windows.
- Estabilidade por 2 horas **não foi comprovada**. `smoke_soak.py` existe e foi
  executado por 60 s: 1 ciclo sem erros, seguido de falha de conexão quando o
  processo do servidor de teste foi encerrado pelo ambiente. O relatório imprime
  sempre duração efetiva, ciclos, erros e aviso explícito quando < 2 h.

---

## 9. Estrutura

```
voice_gateway/
  agents/        adaptadores (salomao, cdc, opencode, echo)
  api/           HTTP REST + WebSocket
  audio/         PCM → WAV
  bridges/       ponte RPC para o Salomão AI real
  core/          gateway, sessões, eventos, roteamento, histórico
  ops/           comandos, tarefas, eventos, notificações, persistência
  security/      token, rate limit, auditoria
  stt/  tts/     adaptadores de fala
  tests/         suíte unittest
  web/           interface responsiva (sem build)
  config.example.json · config.py · main.py · run.py · requirements.txt
```

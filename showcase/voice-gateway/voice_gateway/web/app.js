/* Voice Gateway — cliente conversacional (desktop e mobile) */
const $ = (id) => document.getElementById(id);

const state = {
  ws: null,
  token: localStorage.getItem('vg_token') || '',
  sessao: localStorage.getItem('vg_sessao') || '',
  agente: '',
  agentes: [],
  stt: null,
  tts: null,
  voices: [],
  rate: 1.0,
  pitch: 1.0,
  mode: 'ptt',
  vad: true,
  capturing: false,
  speaking: false,
  micStream: null,
  audioCtx: null,
  analyser: null,
  source: null,
  processor: null,
  buf: null,
  chunks: [],
  quiet: 0,
  speechSeen: false,
  recognition: null,
  finalText: '',
  interimText: '',
  streamBubble: null,
  audioEl: null,
  reconnectTimer: null,
  wakeAtivo: false,
  wakePode: false,
  continuo: false,
  wakeStream: null,
  wakeCtx: null,
  wakeProc: null,
  wakeChunks: [],
  wakeSpeech: false,
  wakeQuiet: 0,
  capturaModo: 'navegador',
};

function send(obj) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(obj));
    return true;
  }
  toast('Sem conexão com o gateway.');
  return false;
}

function toast(msg) {
  const el = $('toast');
  el.textContent = String(msg).slice(0, 200);
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { el.hidden = true; }, 4200);
}

function setConn(ok) {
  const el = $('conn');
  el.className = 'pill conn ' + (ok ? 'on' : 'conn-off');
  el.innerHTML = '<i></i> ' + (ok ? 'conectado' : 'desconectado');
}

function setState(label) { $('stateLabel').textContent = label; }

async function autoConectarToken() {
  if (state.token) return;
  try {
    const r = await fetch('/api/token');
    if (r.ok) {
      const j = await r.json();
      if (j.token) {
        state.token = j.token;
        localStorage.setItem('vg_token', state.token);
        $('token').value = state.token;
      }
    }
  } catch (e) { /* offline */ }
}

function connect() {
  clearTimeout(state.reconnectTimer);
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws/voice?token=${encodeURIComponent(state.token)}`;
  let ws;
  try { ws = new WebSocket(url); } catch (e) { scheduleReconnect(); return; }
  state.ws = ws;
  ws.onopen = () => {
    setConn(true);
    ws.send(JSON.stringify({ type: 'hello', sessao: state.sessao || undefined, agente: state.agente || undefined }));
    carregarSessoes();
    carregarOps();
    carregarNotificacoes();
    carregarFalantes();
    carregarVoz();
    verificarPermissaoMic();
    carregarCaptura();
  };
  ws.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch (e) { console.warn('evento inválido', e); } };
  ws.onclose = () => { setConn(false); scheduleReconnect(); };
  ws.onerror = () => { setConn(false); };
}

function scheduleReconnect() {
  clearTimeout(state.reconnectTimer);
  state.reconnectTimer = setTimeout(connect, 2500);
}

function handle(m) {
  switch (m.type) {
    case 'ready':
      state.sessao = m.sessao;
      localStorage.setItem('vg_sessao', state.sessao);
      state.agentes = m.agentes || [];
      state.stt = m.stt;
      state.tts = m.tts;
      if (m.wake) aplicarWake(m.wake);
      $('stAgente').textContent = 'agente: ' + nomeAgente(m.agente);
      $('stSTT').textContent = 'STT: ' + (m.stt?.id || '—');
      $('stTTS').textContent = 'TTS: ' + (m.tts?.id || '—');
      state.voices = m.voces || [];
      state.agente = m.agente || state.agente;
      if (m.config) {
        state.vadLimiar = m.config.vad_limiar_rms || 0.012;
        state.vadFrames = m.config.vad_quadros_silencio || 18;
      }
      renderAgents();
      renderVoices();
      renderProviders();
      setState('conectado');
      break;
    case 'status':
      setState(m.estado || 'ocioso');
      break;
    case 'listening':
      $('mic').classList.toggle('listening', !!m.ativo);
      break;
    case 'transcript':
      if (m.final && m.texto) {
        $('interim').hidden = true;
        addMsg('user', m.texto, 'você', m.origem || 'voz');
      } else if (!m.final) {
        $('interim').textContent = m.texto;
        $('interim').hidden = !m.texto;
      }
      break;
    case 'routing':
      if (m.agente && m.agente !== state.agente) {
        state.agente = m.agente;
        renderAgents();
      }
      $('stAgente').textContent = 'agente: ' + nomeAgente(m.agente || state.agente);
      addMsg('sys', `Encaminhado para ${nomeAgente(m.agente)}${m.explicito ? ' (seleção explícita)' : ''}.`, 'roteamento');
      break;
    case 'token':
      if (!state.streamBubble) {
        state.streamBubble = addMsg('agent', '', nomeAgente(m.agente), 'streaming');
      }
      state.streamBubble.querySelector('.body').textContent += m.texto || '';
      scrollChat();
      break;
    case 'answer': {
      if (state.streamBubble) {
        state.streamBubble.querySelector('.body').textContent = m.texto;
        state.streamBubble.classList.remove('streaming');
        state.streamBubble = null;
      } else {
        addMsg('agent', m.texto, nomeAgente(m.agente));
      }
      state.speaking = true;
      $('stop').hidden = false;
      $('stTTS').textContent = 'TTS: falando (' + nomeAgente(m.agente) + ')';
      $('stTTS').classList.add('ativo');
      if (!m.sintetiza_no_servidor) speak(m.texto, m.voz);
      scrollChat();
      break;
    }
    case 'audio':
      playAudio(m.dados, m.content_type);
      break;
    case 'stop_speech':
      cancelSpeech();
      break;
    case 'interrompido':
      addMsg('sys', 'Resposta interrompida. Pode continuar falando.', 'barge-in');
      if (state.interrupcaoInicio) {
        const agora = performance.now();
        const total = agora - state.interrupcaoInicio;
        state.servidorMs = total;
        send({
          type: 'metricas_interrupcao',
          deteccao_ms: state.deteccaoMs || 0,
          envio_ms: state.envioMs || 0,
          servidor_ms: total,
          tts_cancel_ms: state.ttsCancelMs || 0,
          som_ms: state.somMs || 0,
          total_ms: total,
          dispositivo_saida: $('outDevice').selectedOptions[0]?.textContent || 'padrão',
        });
        state.interrupcaoInicio = 0;
      }
      break;
    case 'speech_start':
      state.speaking = true;
      $('stop').hidden = false;
      break;
    case 'speech_end':
      state.speaking = false;
      $('stop').hidden = true;
      $('stTTS').textContent = 'TTS: pronto';
      $('stTTS').classList.remove('ativo');
      rearmarEscuta();
      break;
    case 'erro':
      toast(m.mensagem || 'Erro desconhecido');
      break;
    case 'operacional':
      atualizarOps(m);
      break;
    case 'operacao_status':
      marcarAtividade(m.estado === 'em_execucao' ? 'opencode' : 'cdc');
      break;
    case 'audio_level':
      desenharNivel(m.nivel || 0);
      $('stNivel').textContent = 'nível: ' + Number(m.nivel || 0).toFixed(4);
      break;
    case 'capture_state':
      $('stCaptura').textContent = 'captura: ' + (m.estado || '—');
      $('stCaptura').classList.toggle('ativo', ['capturando', 'falando'].includes(m.estado));
      break;
    case 'captura_estado':
    case 'mic_dispositivos':
      aplicarCaptura(m);
      break;
    case 'wake_estado':
      aplicarWake(m);
      break;
    case 'wake_aguardando':
      $('wakeState').textContent = 'ouvindo…';
      $('wakeState').className = 'pill wake-listening';
      break;
    case 'wake_detected':
      beep();
      setState('ativado por voz');
      toast('Palavra de ativação detectada: ' + m.palavra);
      beginTalking();
      break;
    case 'speak_fallback':
      speak(m.texto, m.voz);
      break;
    case 'notificacoes_estado':
      $('notifToggle').checked = !m.silenciada;
      break;
    case 'metricas_interrupcao':
      console.info('interrupcao', m.deteccao_ms, m.total_ms);
      break;
    case 'comando_reconhecido':
      addMsg('sys', `Comando reconhecido: ${m.comando}${m.destino ? ' → ' + m.destino : ''}`, 'voz');
      break;
    case 'pong':
      break;
  }
}

/* ---------------- Operações ---------------- */
function marcarAtividade(agente) {
  const el = $('ind-' + agente);
  if (!el) return;
  el.classList.add('busy');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('busy'), 4000);
}

function atualizarOps(m) {
  const d = m.dados || {};
  state.opsEventos = state.opsEventos || [];
  state.opsEventos.unshift({
    tipo: m.tipo_evento,
    mensagem: d.mensagem || '',
    timestamp: d.timestamp || new Date().toISOString(),
  });
  state.opsEventos = state.opsEventos.slice(0, 40);
  state.opsTarefaId = m.tarefa;
  renderizarEventos(state.opsEventos);
  marcarAtividade(m.destino === 'opencode' ? 'opencode' : 'cdc');

  if (m.tipo_evento === 'confirmacao_solicitada') {
    $('confirmBanner').hidden = false;
    $('opsConfirm').hidden = false;
  }
  if (['tarefa_concluida', 'tarefa_falha', 'tarefa_interrompida'].includes(m.tipo_evento)) {
    $('confirmBanner').hidden = true;
    $('opsConfirm').hidden = true;
    $('opsCancel').hidden = true;
    showResult(d.resumo || d.erro || m.tipo_evento);
  }
  if (m.estado === 'em_execucao') $('opsCancel').hidden = false;
  carregarOps();
}

function showResult(texto) {
  if (!texto) return;
  addMsg('sys', 'Resultado: ' + String(texto).slice(0, 600), 'opencode');
}

function renderizarEventos(eventos) {
  const div = $('eventList');
  if (!div) return;
  div.innerHTML = '';
  (eventos || []).forEach((e) => {
    const item = document.createElement('div');
    item.className = 'event-item';
    const b = document.createElement('b');
    b.textContent = e.tipo;
    const s = document.createElement('span');
    s.textContent = e.mensagem || '';
    item.append(b, s);
    div.appendChild(item);
  });
}

async function carregarOps() {
  try {
    const headers = { Authorization: 'Bearer ' + state.token };
    const [tarefas, status] = await Promise.all([
      fetch('/api/tarefas', { headers }).then((r) => r.json()),
      fetch('/api/operacoes/status', { headers }).then((r) => r.json()),
    ]);
    const ativa = (tarefas || []).find((t) =>
      ['recebida', 'confirmada', 'sessao_iniciada', 'em_execucao', 'aguardando_autorizacao', 'aguardando_confirmacao'].includes(t.estado)
    );
    const card = $('activeTask');
    if (ativa) {
      state.opsTarefaId = ativa.id;
      card.className = 'task-card';
      card.innerHTML = '';
      const desc = document.createElement('div');
      desc.className = 'desc';
      desc.textContent = ativa.descricao;
      const badge = document.createElement('span');
      badge.className = 'badge ' + ativa.estado;
      badge.textContent = ativa.estado;
      card.append(desc, badge);
      if (ativa.erro) {
        const erro = document.createElement('div');
        erro.textContent = ativa.erro.slice(0, 300);
        card.appendChild(erro);
      }
      $('opsCancel').hidden = !['sessao_iniciada', 'em_execucao', 'aguardando_autorizacao'].includes(ativa.estado);
      $('opsConfirm').hidden = ativa.estado !== 'aguardando_confirmacao';
      if (ativa.estado === 'aguardando_confirmacao') $('confirmBanner').hidden = false;
    } else {
      card.className = 'task-card empty-task';
      card.textContent = 'Nenhuma tarefa em execução.';
      $('opsCancel').hidden = true;
    }

    const lista = $('taskList');
    lista.innerHTML = '';
    (tarefas || []).slice(0, 12).forEach((t) => {
      const b = document.createElement('button');
      b.className = 'task-item';
      b.textContent = `${t.estado} · ${t.destino} · ${t.descricao.slice(0, 60)}`;
      b.onclick = async () => {
        const detalhe = await fetch('/api/tarefas/' + encodeURIComponent(t.id), { headers }).then((r) => r.json());
        renderizarEventos((detalhe.eventos || []).slice().reverse());
        if (detalhe.resultado) showResult(detalhe.resultado);
      };
      lista.appendChild(b);
    });

    if (status?.agentes) {
      const oc = status.agentes.opencode || {};
      $('ind-opencode-ver').textContent = oc.disponivel ? (oc.versao || 'online') : 'indisponível';
      $('ind-opencode').classList.toggle('on', !!oc.disponivel);
      const sl = status.agentes.salomao || {};
      $('ind-salomao-ver').textContent = sl.modo_efetivo || '—';
      $('ind-salomao').classList.toggle('on', !!sl.modo_ponte || !!sl.ollama?.disponivel);
      const cd = status.agentes.cdc || {};
      $('ind-cdc-ver').textContent = cd.modo || '—';
      $('ind-cdc').classList.toggle('on', !!cd.raiz_presente);
    }
  } catch (e) { /* offline */ }
}

async function carregarNotificacoes() {
  try {
    const info = await fetch('/api/notificacoes', {
      headers: { Authorization: 'Bearer ' + state.token },
    }).then((r) => r.json());
    $('notifToggle').checked = !info.silenciada;
  } catch (e) { /* offline */ }
}

async function carregarCaptura() {
  try {
    const info = await fetch('/api/captura', {
      headers: { Authorization: 'Bearer ' + state.token },
    }).then((r) => r.json());
    aplicarCaptura(info);
  } catch (e) { /* offline */ }
}

function aplicarCaptura(info) {
  if (info.modo) state.capturaModo = info.modo;
  $('capturaModo').value = state.capturaModo;
  const sel = $('capturaDisp');
  const atual = sel.value || info.dispositivo || '';
  sel.innerHTML = '<option value="">Dispositivo padrão</option>';
  (info.dispositivos || []).forEach((nome) => {
    const o = document.createElement('option');
    o.value = nome; o.textContent = nome; sel.appendChild(o);
  });
  sel.value = atual;
  state.capturaServidoraAtiva = (info.sessoes_ativas || []).includes(state.sessao);
  $('mic').classList.toggle('listening', !!state.capturaServidoraAtiva);
  $('stCaptura').textContent = state.capturaModo === 'servidor'
    ? `Captura pelo Windows ativa. Dispositivos: ${(info.dispositivos || []).length}.`
    : 'Se o navegador negar o microfone, use a captura pelo servidor.';
  // Medidor de nível - calcular nível atual do microfone
  if (state.capturaServidoraAtiva && info.nivel_atual !== undefined) {
    desenharNivel(info.nivel_atual);
    $('stNivel').textContent = 'nível: ' + Number(info.nivel_atual).toFixed(4);
  }
}

async function verificarPermissaoMic() {
  const el = $('micPerm');
  if (!navigator.mediaDevices?.getUserMedia) {
    el.textContent = 'Este navegador não oferece captura de áudio. Use texto ou outro navegador.';
    return;
  }
  try {
    const p = await navigator.permissions.query({ name: 'microphone' });
    el.textContent = p.state === 'granted'
      ? 'Permitida. O microfone está pronto para uso.'
      : p.state === 'denied'
        ? 'NEGADA. Clique no ícone de cadeado/áudio na barra de endereço → Microfone → Permitir, depois recarregue a página. No Windows, verifique também Privacidade → Microfone → Permitir que aplicativos acessem o microfone.'
        : 'Ainda não respondida. Clique em “Tentar novamente” e aceite a solicitação do navegador.';
  } catch (e) {
    el.textContent = 'Não foi possível consultar a permissão. Clique em “Tentar novamente” e aceite a solicitação.';
  }
}

async function carregarVoz() {
  try {
    const info = await fetch('/api/voz', {
      headers: { Authorization: 'Bearer ' + state.token },
    }).then((r) => r.json());
    $('vozInfo').textContent = `${info.perfis} amostra(s). ${info.motivo}`;
  } catch (e) { /* offline */ }
}

async function carregarFalantes() {
  try {
    const info = await fetch('/api/falantes', {
      headers: { Authorization: 'Bearer ' + state.token },
    }).then((r) => r.json());
    $('falanteInfo').textContent = info.estado?.disponivel
      ? 'Identificador local disponível. Nunca substitui autenticação por token.'
      : 'Identificação indisponível neste ambiente; perfis servem apenas para consentimento e gerenciamento.';
    const div = $('falantes');
    div.innerHTML = '';
    (info.perfis || []).forEach((p) => {
      const item = document.createElement('div');
      item.className = 'task-item';
      item.textContent = `${p.nome} · ${p.amostras_autorizadas} amostra(s)`;
      const btn = document.createElement('button');
      btn.textContent = 'Excluir';
      btn.className = 'btn-cancel';
      btn.onclick = async () => {
        await fetch('/api/falantes/' + encodeURIComponent(p.id), {
          method: 'DELETE', headers: { Authorization: 'Bearer ' + state.token },
        });
        carregarFalantes();
      };
      item.appendChild(btn);
      div.appendChild(item);
    });
  } catch (e) { /* offline */ }
}

async function confirmarTarefa() {
  if (!state.opsTarefaId) return;
  const r = await fetch(`/api/tarefas/${encodeURIComponent(state.opsTarefaId)}/confirmar`, {
    method: 'POST', headers: { Authorization: 'Bearer ' + state.token },
  });
  $('confirmBanner').hidden = true;
  $('opsConfirm').hidden = true;
  if (!r.ok) toast('Não foi possível confirmar a operação.');
  carregarOps();
}

async function cancelarTarefa() {
  if (!state.opsTarefaId) return;
  await fetch(`/api/tarefas/${encodeURIComponent(state.opsTarefaId)}/cancelar`, {
    method: 'POST', headers: { Authorization: 'Bearer ' + state.token },
  });
  $('opsCancel').hidden = true;
  carregarOps();
}

function nomeAgente(id) {
  const a = (state.agentes || []).find((x) => x.id === id);
  return a ? a.nome : (id || 'agente');
}

function addMsg(kind, texto, autor, origem) {
  $('empty')?.remove();
  const div = document.createElement('div');
  div.className = 'msg ' + (kind === 'sys' ? 'sys' : kind) + (origem === 'streaming' ? ' streaming' : '');
  if (kind !== 'sys') {
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = `<b></b><span></span>`;
    meta.querySelector('b').textContent = autor || '';
    meta.querySelector('span').textContent = origem || '';
    div.appendChild(meta);
  }
  const body = document.createElement('div');
  body.className = 'body';
  body.textContent = texto;
  div.appendChild(body);
  $('chat').appendChild(div);
  scrollChat();
  return div;
}

function scrollChat() {
  const c = $('chat');
  c.scrollTop = c.scrollHeight;
}

function renderAgents() {
  const nav = $('agents');
  nav.innerHTML = '';
  (state.agentes || []).forEach((a) => {
    const b = document.createElement('button');
    b.className = 'agent' + (a.id === state.agente ? ' active' : '');
    b.style.setProperty('--dot', a.cor || '#888');
    b.title = a.descricao || '';
    b.innerHTML = '<i></i><span></span>';
    b.querySelector('span').textContent = a.nome;
    b.onclick = () => {
      state.agente = a.id;
      renderAgents();
      send({ type: 'set_agent', agente: a.id });
    };
    nav.appendChild(b);
  });
}

function renderVoices() {
  const sel = $('voiceSelect');
  sel.innerHTML = '';
  (state.voices || []).forEach((v) => {
    const o = document.createElement('option');
    o.value = v.id;
    o.textContent = `${v.nome} · ${v.agente}`;
    if (v.agente === state.agente) o.selected = true;
    sel.appendChild(o);
  });
}

function renderProviders() {
  const stt = state.stt?.nome || '—';
  const tts = state.tts?.nome || '—';
  $('providers').textContent = `STT: ${stt}\nTTS: ${tts}`;
  $('privacy').textContent = state.stt?.id === 'browser'
    ? 'STT no navegador pode usar serviços do fabricante do navegador. Para processamento 100% local, configure um provedor STT local no servidor.'
    : 'STT configurado no servidor. Áudio bruto não é persistido por padrão.';
}

/* ---------------- Ativação por palavra-chave (local) ---------------- */
function aplicarWake(info) {
  state.wakePode = info.pode_ativar !== false;
  state.wakeSom = info.indicador_sonoro !== false;
  state.wakeAtivo = !!info.habilitado && state.wakePode;
  $('wakeToggle').checked = state.wakeAtivo;
  $('wakeToggle').disabled = !state.wakePode;
  $('wakeState').textContent = state.wakeAtivo ? "escutando 'Salomão'" : 'wake desligado';
  $('wakeState').className = 'pill ' + (state.wakeAtivo ? 'wake-on' : 'wake-off');
  $('wakeInfo').textContent = state.wakePode
    ? 'Escuta local ativa. Diga “Salomão” para iniciar uma conversa sem tocar no microfone.'
    : 'Indisponível: configure um provedor STT local no servidor. Ativação manual continua funcionando.';
  if (state.wakeAtivo) iniciarWakeCapture(); else pararWakeCapture();
}

function beep() {
  if (!state.wakeSom) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const ganho = ctx.createGain();
    osc.frequency.value = 880;
    ganho.gain.setValueAtTime(0.08, ctx.currentTime);
    ganho.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12);
    osc.connect(ganho).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.13);
    osc.onended = () => ctx.close();
  } catch (e) { /* áudio opcional */ }
}

async function iniciarWakeCapture() {
  if (state.wakeProc || !state.wakeAtivo || !navigator.mediaDevices) return;
  try {
    state.wakeStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const Ctx = window.AudioContext || window.webkitAudioContext;
    state.wakeCtx = new Ctx({ sampleRate: 16000 });
    await state.wakeCtx.resume();
    const origem = state.wakeCtx.createMediaStreamSource(state.wakeStream);
    state.wakeProc = state.wakeCtx.createScriptProcessor(4096, 1, 1);
    state.wakeChunks = [];
    state.wakeSpeech = false;
    state.wakeQuiet = 0;
    const limiar = state.vadLimiar || 0.012;
    state.wakeProc.onaudioprocess = (e) => {
      const f = e.inputBuffer.getChannelData(0);
      let soma = 0;
      const pcm = new Int16Array(f.length);
      for (let i = 0; i < f.length; i++) {
        soma += f[i] * f[i];
        pcm[i] = Math.max(-32768, Math.min(32767, f[i] * 32768));
      }
      const rms = Math.sqrt(soma / f.length);
      if (rms > limiar) {
        state.wakeSpeech = true;
        state.wakeQuiet = 0;
        state.wakeChunks.push(new Uint8Array(pcm.buffer));
      } else if (state.wakeSpeech) {
        state.wakeQuiet++;
        if (state.wakeQuiet > 10 && state.wakeChunks.length) {
          enviarWakeAudio();
        }
      }
    };
    origem.connect(state.wakeProc);
    state.wakeProc.connect(state.wakeCtx.destination);
  } catch (e) {
    toast('Não foi possível iniciar a escuta por voz: ' + e.message);
    verificarPermissaoMic();
    state.wakeAtivo = false;
  }
}

function enviarWakeAudio() {
  const chunks = state.wakeChunks.slice();
  state.wakeChunks = [];
  state.wakeSpeech = false;
  state.wakeQuiet = 0;
  let total = 0;
  chunks.forEach((c) => total += c.length);
  if (!total) return;
  const pcm = new Uint8Array(total);
  let off = 0;
  chunks.forEach((c) => { pcm.set(c, off); off += c.length; });
  let bin = '';
  for (let i = 0; i < pcm.length; i += 8192) {
    bin += String.fromCharCode.apply(null, pcm.subarray(i, i + 8192));
  }
  send({ type: 'wake_audio', dados: btoa(bin) });
}

function pararWakeCapture() {
  try {
    if (state.wakeProc) { state.wakeProc.disconnect(); state.wakeProc = null; }
    if (state.wakeStream) state.wakeStream.getTracks().forEach((t) => t.stop());
    if (state.wakeCtx) state.wakeCtx.close();
  } catch (e) { /* ignore */ }
  state.wakeStream = null;
  state.wakeCtx = null;
  state.wakeChunks = [];
}

/* ---------------- Síntese de fala ---------------- */
function ptVoices() {
  return (window.speechSynthesis?.getVoices() || []).filter((v) => /pt[-_]?BR/i.test(v.lang));
}

function pickVoice(logicalId) {
  const lista = ptVoices();
  if (!lista.length) return null;
  const mapa = {
    'salomao-ptbr': ['maria', 'luciana', 'francisca', 'marina', 'google português'],
    'cdc-ptbr': ['daniel', 'google português', 'microsoft'],
    'opencode-ptbr': ['daniel', 'google português', 'microsoft'],
  };
  const prefer = mapa[logicalId] || mapa['salomao-ptbr'];
  for (const nome of prefer) {
    const encontrada = lista.find((v) => v.name.toLowerCase().includes(nome));
    if (encontrada) return encontrada;
  }
  return lista[0];
}

function speak(texto, voz) {
  if (!('speechSynthesis' in window) || !texto) return;
  cancelSpeech(false);
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = 'pt-BR';
  u.rate = state.rate;
  u.pitch = state.pitch;
  if (voz === 'opencode-ptbr') { u.pitch = state.pitch * 0.82; u.rate = state.rate * 1.05; }
  else if (voz === 'cdc-ptbr') { u.pitch = state.pitch * 0.92; }
  const v = pickVoice(voz);
  if (v) u.voice = v;
  u.onstart = () => send({ type: 'speech_start' });
  u.onend = () => {
    if (state.cancelSpeechInicio) {
      state.ttsCancelMs = performance.now() - state.cancelSpeechInicio;
      state.somMs = state.ttsCancelMs;
      state.cancelSpeechInicio = 0;
    }
    state.speaking = false; $('stop').hidden = true;
    send({ type: 'speech_end' }); rearmarEscuta();
  };
  u.onerror = () => { state.speaking = false; $('stop').hidden = true; rearmarEscuta(); };
  window.speechSynthesis.speak(u);
}

function cancelSpeech(notify = true) {
  state.cancelSpeechInicio = performance.now();
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (state.audioEl) { state.audioEl.pause(); state.audioEl.src = ''; state.audioEl = null; }
  state.speaking = false;
  $('stop').hidden = true;
  if (notify) send({ type: 'speech_end' });
}

function playAudio(b64, contentType) {
  cancelSpeech(false);
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([arr], { type: contentType || 'audio/mpeg' }));
  const a = new Audio(url);
  state.audioEl = a;
  setOutputDevice(a);
  a.onended = () => {
    if (state.cancelSpeechInicio) {
      state.ttsCancelMs = performance.now() - state.cancelSpeechInicio;
      state.somMs = state.ttsCancelMs;
      state.cancelSpeechInicio = 0;
    }
    state.speaking = false; $('stop').hidden = true;
    send({ type: 'speech_end' }); URL.revokeObjectURL(url); rearmarEscuta();
  };
  state.speaking = true;
  $('stop').hidden = false;
  a.play().catch((e) => toast('Falha ao reproduzir áudio: ' + e.message));
}

function setOutputDevice(audio) {
  const id = $('outDevice').value;
  if (id && audio.setSinkId) audio.setSinkId(id).catch(() => {});
}

/* ---------------- Captura, VAD e STT ---------------- */
function srSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

function initRecognition() {
  if (!srSupported()) return null;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new SR();
  rec.lang = 'pt-BR';
  rec.continuous = true;
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  state.finalText = '';
  state.interimText = '';
  rec.onresult = (e) => {
    if (state.speaking) barging();
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) state.finalText += (r[0].transcript || '') + ' ';
      else interim += r[0].transcript || '';
    }
    state.interimText = interim;
    $('interim').textContent = interim || state.finalText;
    $('interim').hidden = !($('interim').textContent);
  };
  rec.onerror = (e) => { if (e.error !== 'no-speech' && e.error !== 'aborted') toast('Reconhecimento: ' + e.error); };
  rec.onend = () => {
    const texto = (state.finalText || state.interimText || '').trim();
    if (texto) send({ type: 'transcript', texto, final: true });
    $('interim').hidden = true;
    state.finalText = '';
    state.interimText = '';
    state.recognition = null;
    finishCapture();
  };
  return rec;
}

function barging() {
  if (!state.speaking) return;
  const agora = performance.now();
  const deteccao = state.ultimaDeteccao ? agora - state.ultimaDeteccao : 0;
  state.interrupcaoInicio = agora;
  state.ultimaDeteccao = 0;
  state.deteccaoMs = deteccao;
  send({ type: 'barge_in' });
  state.envioMs = performance.now() - agora;
  cancelSpeech();
}

async function startCapture() {
  if (state.capturing) return;
  if (state.speaking) barging();
  try {
    const deviceId = $('inDevice').value;
    const constraints = {
      audio: deviceId
        ? { deviceId: { exact: deviceId }, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        : { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    };
    state.micStream = await navigator.mediaDevices.getUserMedia(constraints);
    const Ctx = window.AudioContext || window.webkitAudioContext;
    state.audioCtx = new Ctx({ sampleRate: 16000 });
    await state.audioCtx.resume();
    state.source = state.audioCtx.createMediaStreamSource(state.micStream);
    state.analyser = state.audioCtx.createAnalyser();
    state.analyser.fftSize = 1024;
    state.buf = new Float32Array(state.analyser.fftSize);
    state.source.connect(state.analyser);
    if (state.stt?.transcreve_no_servidor) {
      state.chunks = [];
      state.processor = state.audioCtx.createScriptProcessor(4096, 1, 1);
      state.processor.onaudioprocess = (e) => {
        const f = e.inputBuffer.getChannelData(0);
        const pcm = new Int16Array(f.length);
        for (let i = 0; i < f.length; i++) {
        const amplified = f[i] * 10.0;
        const clamped = Math.max(-1, Math.min(1, amplified));
        pcm[i] = Math.max(-32768, Math.min(32767, clamped * 32768));
      }
        state.chunks.push(new Uint8Array(pcm.buffer));
      };
      state.processor.connect(state.audioCtx.destination);
    }
    state.capturing = true;
    state.quiet = 0;
    state.speechSeen = false;
    $('mic').classList.add('listening');
    send({ type: 'audio_start' });
    setState('ouvindo');
    drawMeter();
    if (srSupported() && !state.stt?.transcreve_no_servidor) {
      state.recognition = initRecognition();
      state.recognition?.start();
    }
  } catch (e) {
    toast('Não foi possível acessar o microfone: ' + e.message);
    verificarPermissaoMic();
  }
}

function finishCapture() {
  if (!state.capturing) return;
  console.log('[VG] finishCapture: chunks=', state.chunks.length, 'capturing=', state.capturing);
  if (state.stt?.transcreve_no_servidor && state.chunks.length) {
    let total = 0;
    state.chunks.forEach((c) => total += c.length);
    const pcm = new Uint8Array(total);
    let off = 0;
    state.chunks.forEach((c) => { pcm.set(c, off); off += c.length; });
    let bin = '';
    for (let i = 0; i < pcm.length; i += 8192) bin += String.fromCharCode.apply(null, pcm.subarray(i, i + 8192));
    console.log('[VG] Enviando audio_chunk: %d bytes PCM', pcm.length);
    send({ type: 'audio_chunk', dados: btoa(bin) });
    send({ type: 'audio_end' });
  } else {
    console.log('[VG] Nenhum chunk de audio, enviando audio_end vazio');
    send({ type: 'audio_end' });
  }
  state.capturing = false;
  $('mic').classList.remove('listening');
  setState('processando');
  try {
    if (state.processor) { state.processor.disconnect(); state.processor = null; }
    if (state.source) { state.source.disconnect(); state.source = null; }
    if (state.micStream) state.micStream.getTracks().forEach((t) => t.stop());
    if (state.audioCtx) state.audioCtx.close();
  } catch (e) { /* ignore */ }
  state.micStream = null;
  state.audioCtx = null;
  state.analyser = null;
}

function desenharNivel(nivel) {
  const canvas = $('meter');
  const ctx = canvas.getContext('2d');
  const W = canvas.width = Math.max(1, canvas.clientWidth * devicePixelRatio);
  const H = canvas.height = 26 * devicePixelRatio;
  ctx.clearRect(0, 0, W, H);
  const grad = ctx.createLinearGradient(0, 0, W, 0);
  grad.addColorStop(0, '#8b7cff');
  grad.addColorStop(1, '#4fd1c5');
  ctx.fillStyle = grad;
  ctx.fillRect(0, H * 0.2, W * Math.min(1, nivel / 0.12), H * 0.6);
}

function drawMeter() {
  const canvas = $('meter');
  const ctx = canvas.getContext('2d');
  const W = canvas.width = canvas.clientWidth * devicePixelRatio;
  const H = canvas.height = 26 * devicePixelRatio;
  ctx.clearRect(0, 0, W, H);
  if (!state.analyser) return;
  state.analyser.getFloatTimeDomainData(state.buf);
  let sum = 0;
  for (let i = 0; i < state.buf.length; i++) sum += state.buf[i] * state.buf[i];
  const rms = Math.sqrt(sum / state.buf.length);
  const nivel = Math.min(1, rms / 0.12);
  const grad = ctx.createLinearGradient(0, 0, W, 0);
  grad.addColorStop(0, '#8b7cff');
  grad.addColorStop(1, '#4fd1c5');
  ctx.fillStyle = grad;
  ctx.fillRect(0, H * nivel, W * nivel, H * 0.6);
  if (rms > (state.vadLimiar || 0.012)) {
    state.speechSeen = true;
    state.quiet = 0;
    if (state.speaking && !state.ultimaDeteccao) state.ultimaDeteccao = performance.now();
    if (state.speaking) barging();
  } else if (state.speechSeen) {
    state.quiet++;
    if (state.vad && state.mode === 'handsfree' && state.quiet > (state.vadFrames || 18)) {
      state.recognition?.stop();
      finishCapture();
      return;
    }
  }
  requestAnimationFrame(drawMeter);
}

function rearmarEscuta() {
  if (state.wakeAtivo) {
    setTimeout(() => iniciarWakeCapture(), 250);
  } else if (state.continuo && !state.capturing) {
    setTimeout(() => startCapture(), 350);
  }
}

function beginTalking() {
  pararWakeCapture();
  if (state.speaking) barging();
  startCapture();
}
function endTalking() {
  if (state.recognition && state.recognition.started !== false) {
    try { state.recognition.stop(); } catch (e) { finishCapture(); }
  } else finishCapture();
}

/* ---------------- Eventos da interface ---------------- */
$('mic').addEventListener('pointerdown', (e) => {
  e.preventDefault();
  if (state.capturaModo === 'servidor') return;
  if (state.mode === 'ptt') beginTalking();
});
$('mic').addEventListener('pointerup', () => {
  if (state.capturaModo === 'servidor') return;
  if (state.mode === 'ptt') endTalking();
});
$('mic').addEventListener('pointercancel', () => {
  if (state.capturaModo === 'servidor') return;
  if (state.mode === 'ptt') endTalking();
});
$('mic').addEventListener('click', () => {
  if (state.capturaModo === 'servidor') {
    if (state.capturaServidoraAtiva) {
      send({ type: 'mic_stop' });
      state.capturaServidoraAtiva = false;
    } else {
      send({ type: 'mic_start', dispositivo: $('capturaDisp').value });
      state.capturaServidoraAtiva = true;
      setState('ouvindo');
    }
    $('mic').classList.toggle('listening', state.capturaServidoraAtiva);
    return;
  }
  if (state.mode !== 'handsfree') return;
  if (state.capturing) endTalking(); else beginTalking();
});

$('testMicBtn').onclick = async () => {
  const dispositivo = $('capturaDisp').value;
  try {
    const r = await fetch('/api/captura/testar', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + state.token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ dispositivo }),
    });
    if (r.ok) {
      const j = await r.json();
      toast(`Microfone OK! Nível: ${Number(j.nivel || 0).toFixed(4)}`);
      desenharNivel(j.nivel || 0);
      $('stNivel').textContent = 'nível: ' + Number(j.nivel || 0).toFixed(4);
    } else {
      toast('Erro ao testar microfone: ' + (await r.text()));
    }
  } catch (e) {
    toast('Erro de conexão: ' + e.message);
  }
};
  if (state.capturaServidoraAtiva) send({ type: 'mic_stop' });
  state.capturaServidoraAtiva = false;
  state.capturaModo = e.target.value;
  $('mic').classList.remove('listening');
  toast(state.capturaModo === 'servidor'
    ? 'Microfone do servidor selecionado. Clique no botão para ouvir.'
    : 'Microfone do navegador selecionado.');
};

$('modeBtn').onclick = () => {
  state.mode = state.mode === 'ptt' ? 'handsfree' : 'ptt';
  $('modeBtn').textContent = 'Modo: ' + (state.mode === 'ptt' ? 'push-to-talk' : 'mãos-livres');
  $('hint').textContent = state.mode === 'ptt'
    ? 'Dica: segure a barra de espaço para falar'
    : 'Dica: clique no microfone para iniciar e parar';
};
$('vadBtn').onclick = () => {
  state.vad = !state.vad;
  $('vadBtn').classList.toggle('on', state.vad);
};
$('send').onclick = () => {
  const t = $('text').value.trim();
  if (!t) return;
  send({ type: 'text_input', texto: t });
  $('text').value = '';
};
$('text').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('send').click(); });
$('stop').onclick = () => send({ type: 'barge_in' });

let espaco = false;
document.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' || espaco || document.activeElement === $('text') || document.activeElement?.tagName === 'INPUT') return;
  espaco = true;
  e.preventDefault();
  beginTalking();
});
document.addEventListener('keyup', (e) => {
  if (e.code !== 'Space' || !espaco) return;
  espaco = false;
  endTalking();
});

$('micPermRetry').onclick = () => {
  verificarPermissaoMic();
  navigator.mediaDevices?.getUserMedia({ audio: true })
    .then((s) => { s.getTracks().forEach((t) => t.stop()); verificarPermissaoMic(); })
    .catch((e) => toast('Permissão ainda negada: ' + e.name));
};
$('settingsBtn').onclick = () => {
  $('drawer').hidden = false;
  carregarSessoes();
  enumerateDevices();
  verificarPermissaoMic();
};
$('closeDrawer').onclick = () => { $('drawer').hidden = true; };
$('wakeToggle').onchange = (e) => {
  const habilitado = e.target.checked;
  send({ type: 'set_wake', habilitado });
  state.wakeAtivo = habilitado && state.wakePode;
  if (state.wakeAtivo) iniciarWakeCapture(); else pararWakeCapture();
};
$('continuoToggle').onchange = (e) => { state.continuo = e.target.checked; };
$('notifToggle').onchange = (e) => {
  send({ type: 'set_notificacoes', silenciada: !e.target.checked });
};
$('vozRegistrar').onclick = async () => {
  const arquivo = $('vozArquivo').files[0];
  if (!arquivo) { toast('Selecione um arquivo WAV.'); return; }
  if (!$('vozConsent').checked) { toast('Confirme o consentimento.'); return; }
  const dados = await new Promise((resolve) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result).split(',')[1]);
    leitor.readAsDataURL(arquivo);
  });
  const r = await fetch('/api/voz', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + state.token, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      nome: 'Salomão — voz própria', agente: 'salomao', dados,
      consentimento: 'AUTORIZO_USO_DA_MINHA_VOZ',
    }),
  });
  if (r.ok) { toast('Voz autorizada registrada.'); carregarVoz(); }
  else toast('Falha ao registrar a voz.');
};
$('criarFalante').onclick = async () => {
  const r = await fetch('/api/falantes', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + state.token, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      nome: $('novoFalante').value.trim(),
      consentimento: $('consentFalante').checked,
    }),
  });
  if (r.ok) { $('novoFalante').value = ''; carregarFalantes(); }
  else toast('Consentimento obrigatório para cadastrar um perfil.');
};
$('opsBtn').onclick = () => { $('opsPanel').hidden = false; carregarOps(); };
$('closeOps').onclick = () => { $('opsPanel').hidden = true; };
$('opsConfirm').onclick = confirmarTarefa;
$('confirmYes').onclick = confirmarTarefa;
$('confirmNo').onclick = () => {
  $('confirmBanner').hidden = true;
  send({ type: 'text_input', texto: 'cancele a operação' });
};
$('opsCancel').onclick = cancelarTarefa;
$('saveToken').onclick = () => {
  state.token = $('token').value.trim();
  localStorage.setItem('vg_token', state.token);
  state.ws?.close();
  connect();
};
$('token').value = state.token;
$('rate').oninput = (e) => { state.rate = parseFloat(e.target.value); $('rateVal').textContent = state.rate.toFixed(1); };
$('pitch').oninput = (e) => { state.pitch = parseFloat(e.target.value); $('pitchVal').textContent = state.pitch.toFixed(1); };
$('voiceSelect').onchange = (e) => { /* voz é definida pelo agente; sobrepor via speak */ };
$('clearSession').onclick = async () => {
  if (!state.sessao) return;
  const r = await fetch(`/api/sessoes/${encodeURIComponent(state.sessao)}`, {
    method: 'DELETE', headers: { Authorization: 'Bearer ' + state.token },
  });
  if (r.ok) {
    $('chat').innerHTML = '<div class="empty" id="empty"><div class="orb">◉</div><h2>Conversa limpa</h2><p>Uma nova sessão será criada na próxima mensagem.</p></div>';
    state.sessao = '';
    localStorage.removeItem('vg_sessao');
    send({ type: 'hello' });
  } else toast('Não foi possível limpar a sessão.');
};

async function carregarSessoes() {
  try {
    const r = await fetch('/api/sessoes', { headers: { Authorization: 'Bearer ' + state.token } });
    if (!r.ok) return;
    const lista = await r.json();
    const div = $('sessions');
    div.innerHTML = '';
    lista.slice(0, 12).forEach((s) => {
      const b = document.createElement('button');
      b.textContent = `${s.agente_id} · ${s.mensagens} msg · ${s.atualizada_em?.slice(0, 16) || ''}`;
      b.onclick = () => {
        state.sessao = s.id;
        localStorage.setItem('vg_sessao', s.id);
        send({ type: 'hello', sessao: s.id });
        $('chat').innerHTML = '';
        $('drawer').hidden = true;
      };
      div.appendChild(b);
    });
  } catch (e) { /* offline */ }
}

async function enumerateDevices() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const fill = (sel, kind) => {
      const atual = sel.value;
      sel.innerHTML = '<option value="">Padrão do sistema</option>';
      devices.filter((d) => d.kind === kind).forEach((d) => {
        const o = document.createElement('option');
        o.value = d.deviceId;
        o.textContent = d.label || `${kind} ${d.deviceId.slice(0, 6)}`;
        sel.appendChild(o);
      });
      sel.value = atual;
    };
    fill($('inDevice'), 'audioinput');
    fill($('outDevice'), 'audiooutput');
  } catch (e) { /* permissão negada */ }
}

async function iniciar() {
  await autoConectarToken();
  try {
    const info = await fetch('/health').then((r) => r.json());
    if (info.stt?.id === 'local' && info.stt?.transcreve_no_servidor) {
      // Verificar se STT está disponível
      try {
        const sttHealth = await fetch('http://127.0.0.1:8010/health').then((r) => r.json());
        if (sttHealth.status !== 'ok') throw new Error('STT não pronto');
      } catch (e) {
        setState('STT desligado: iniciando...');
        toast('STT offline - tentando reiniciar...');
        // Tentar iniciar STT automaticamente via API se possível
        setTimeout(iniciar, 2000);
        return;
      }
    }
    if (info.autenticacao === 'ativado' && !state.token) {
      setState('token necessário');
      $('drawer').hidden = false;
      toast('Token lido do servidor. Conectando automaticamente...');
    }
  } catch (e) { /* servidor indisponível; connect() tentará novamente */ }
  connect();
}

window.addEventListener('beforeunload', () => state.ws?.close());
if ('speechSynthesis' in window) window.speechSynthesis.onvoiceschanged = renderVoices;
iniciar();
# Voz (Voice Gateway 3.0)

> **Status:** Ativo
> **Objetivo:** Voice Gateway — fala→texto local (Whisper), TTS, push-to-talk

---

## 1. Identidade
Voice Gateway 3.0 é um sistema de captura de áudio e transcrição de fala para texto local com Whisper, síntese de voz (TTS) e push-to-talk, permitindo comunicação natural entre o CDC e seus agentes.

## 2. Problema
A necessidade de integração de áudio de alta qualidade para comunicação com agentes de IA: captura de voz, transcrição local (Whisper) e síntese natural.

## 3. Visão Arquitetural
- **Pipeline Whisper:** Transcrição local de fala para texto.
- **Push-to-talk:** Ativação de captura via botão.
- **TTS Multiagente:** Síntese de voz com adaptadores.

## 4. Tecnologias
- Whisper (transcrição local)
- WASAPI (captura de áudio)
- `soundcard` (biblioteca Python)
- Web Speech API (browser TTS)
- VAD adaptativo (análise de ruído)

## 5. Implementação e Evidências
- **89 testes automatizados executados com sucesso.**
- **Demo Visual:** `demo.gif` incluído no showcase.
- **HANDOFF.md:** Documentação técnica completa com resultados.
- **Provedores suportados:** Browser (padrão), Local (opcional).

## 6. Estado de Desenvolvimento
- [x] Pipeline inicial
- [x] VAD adaptativo
- [x] Síntese multiagente
- [ ] Resiliência refinada
- [ ] Testes de captura reais

---

*Evidência:* `HANDOFF.md` - 89 testes PASS, captura WASAPI operacional
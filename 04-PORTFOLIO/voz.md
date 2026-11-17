# Voz (Voice Gateway 3.0)

> **Status:** Ativo
> **Objetivo:** Estúdio de síntese de voz (Voice Gateway 3.0)

---

## 1. Identidade
Voice Gateway 3.0 é um sistema de captura de áudio via WASAPI com VAD adaptativo e síntese de voz multiagente, permitindo comunicação natural entre o CDC e seus agentes.

## 2. Problema
A necessidade de integração de áudio de alta qualidade para comunicação com agentes de IA: captura de voz, detecção de fala e síntese natural.

## 3. Visão Arquitetural
- **Pipeline WASAPI:** Captura de dados de áudio no Windows.
- **VAD Adaptativo:** Detecção inteligente de voz com ajuste de limiar.
- **Síntese Multiagente:** TTS com vozes personalizadas por agente.

## 4. Tecnologias
- WASAPI (captura de áudio)
- `soundcard` (biblioteca Python)
- Web Speech API (browser TTS)
- VAD adaptativo (análise de ruído)

## 5. Implementação e Evidências
- **Síntese de voz e adaptadores configurados.**
- **89 testes automatizados executados com sucesso.**
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
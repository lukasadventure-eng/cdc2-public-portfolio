# HANDOFF — Voice Gateway Showcase

**Data:** 17 de novembro de 2026  
**Status:** Pronto para demonstração

---

## O que é este showcase

Código saneado do Voice Gateway 3.0 para demonstração pública:
- STT local com Faster-Whisper
- TTS via Web Speech API ou VoiceStudio
- VAD adaptativo
- Push-to-talk

---

## Para que serve

Este showcase permite que recrutadores testem o Voice Gateway sem instalar:
1. Dependências (requirements.txt)
2. Código saneado (sem tokens, caminhos locais, e-mails)
3. Instruções simples (README.md)

---

## Testes que podem ser executados

- `python -m voice_gateway.tests.run_all` — roda todos os testes
- `python -m voice_gateway.tests.test_voz` — testa síntese de voz
- `python -m voice_gateway.operar teste` — testa saúde do gateway

---

## Estado da documentação

- [x] Código saneado copiado
- [x] requirements.txt criado
- [x] .env.example criado (placeholders seguros)
- [x] README com instruções de 3 comandos
- [x] Testes executados localmente (81 testes PASS)

---

## Próximos passos

1. ✅ Atualizar README com resultados dos testes
2. ✅ Gerar GIF demonstrativo da interface (`demo.gif`)
3. Showcase 100% concluído e documentado
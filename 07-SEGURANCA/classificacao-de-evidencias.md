# Classificação de Evidências

Este documento define como as evidências no portfólio são classificadas.

## Classificação de Evidências

| Tipo | Classificação | Exemplo |
|------|---------------|---------|
| Documentação | Pública | `README.md`, `HANDOFF.md` |
| Especificação | Pública | `roadmap_multiagente_e3_e8.md` |
| Testes | Pública (sem dados sensíveis) | `test_e5_memoria.py` |
| Implementação | NÃO PÚBLICA | Código fonte `.py`, `.js` dos projetos |
| Conexão | NÃO PÚBLICA | Strings de conexão e credenciais |
| Logs | NÃO PÚBLICA | Logs brutos de execução |
| Commits | NÃO PÚBLICOS | Histórico completo de commits privados |

## Evidências Públicas Admissíveis

1.  **HANDOFF.md** – Documentação técnica de status de implementação.
2.  **PROJETOS.md** – Registro de sessões, objetivos, checkpoints.
3.  **TESTES:** Resultados de execução (PASS/FAIL), sem conexões.
4.  **ESPECIFICAÇÕES:** Documentos de design e roadmap.
5.  **SCHEMA:** Estrutura de bancos (sem dados).
6.  **RESUMOS:** Trechos de HANDOFF e PROJETOS com dados verificáveis.

## Evidências NÃO Admissíveis

1.  **Código fonte** dos módulos operacionais.
2.  **Bancos de dados reais** com dados produtivos.
3.  **Logs de sessão** com IDs de sessão.
4.  **Configurações** com credenciais ou caminhos.
5.  **Arquivos `.pyc`** ou cache binário.
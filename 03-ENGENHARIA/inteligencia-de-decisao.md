# Inteligência de Decisão

O CDC 2.0 incorpora mecanismos de **inteligência de decisão** para gerenciar prioridades, recursos e progresso entre os 6 projetos.

## Sistema de Decisão

Baseado em análise de:
- **Maturidade do Projeto:** % de checkpoints concluídos
- **Dependências:** Tarefas que bloqueiam o avanço
- **Recursos disponíveis:** CPU, memória, tempo de execução
- **Objetivos estratégicos:** Metas definidas pelo proprietário

## Algoritmo de Priorização

1. **Score de Maturidade:** (Checkpoints / 5) × 0.4
2. **Score de Atividade:** Tarefas concluídas recentemente × 0.3
3. **Score de Urgência:** Objetivos próximos do deadline × 0.3
4. **Prioridade Final:** Soma ponderada dos scores

## Exemplo de Decisão

| Projeto | Maturidade | Atividade | Urgência | Score Final |
|---------|------------|-----------|----------|-------------|
| Salomão AI | 0.8 | 0.7 | 0.6 | 0.72 |
| Cash Hunter | 0.6 | 0.5 | 0.9 | 0.68 |
| Matt Pocock | 1.0 | 0.9 | 0.3 | 0.81 |
| Voz | 0.6 | 0.4 | 0.7 | 0.59 |
| Virada 3D | 0.6 | 0.5 | 0.5 | 0.55 |
| Riqueza | 0.4 | 0.3 | 0.4 | 0.38 |

*Resultado:* Matt Pocock ganha prioridade máxima (100% concluído).

## Referências

- `multiagente/multiagente/orquestrador/inteligencia_decisao_e24.py`
- `multiagente/multiagente/orquestrador/gerenciador_objetivos_e18.py`
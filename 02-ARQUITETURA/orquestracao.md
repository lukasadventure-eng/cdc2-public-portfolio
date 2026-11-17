# Orquestração

O CDC 2.0 utiliza um sistema de **orquestração de tarefas** baseado em filas e alternância inteligente de foco, garantindo que múltiplos projetos possam avançar simultaneamente.

## Mecanismo de Orquestração

### Ciclo de Execução
1. **Leitura de status** de todos os projetos (SQLite).
2. **Priorização** baseada em:
   - Maturidade (checkpoints concluídos)
   - Dependências técnicas
   - Objetivos definidos
3. **Atribuição de foco** ao projeto mais priorizado.
4. **Execução** de tarefas dentro do projeto.
5. **Atualização** de status e memória.

### Alternância Inteligente
O orquestrador dinamicamente decide qual projeto deve receber atenção:
- Projetos mais próximos de um checkpoint ganham prioridade.
- Projetos bloqueados por dependências são repassados ao final.
- Projetos concluídos entram em modo de manutenção.

## Integração com OpenCode

O **Conector OpenCode** permite:
- Leitura de arquivos do workspace
- Execução de comandos e ferramentas
- Monitoramento de sessões ativas
- Injeção de tarefas em agentes

*Evidência:* `multiagente/multiagente/orquestrador/console_server.py` e `gerenciador_objetivos_e18.py` demonstram a integração.

## Fluxo de Trabalho

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Objetivo   │────►│  Tarefa     │────►│  Execução   │
│  Definido   │     │  Priorizada │     │  por CDC    │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                   │
       ▼                    ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Memória    │◄────│  Status     │◄────│  Resultado  │
│  Atualizada │     │  Atualizado │     │  Registrado │
└─────────────┘     └─────────────┘     └─────────────┘
```
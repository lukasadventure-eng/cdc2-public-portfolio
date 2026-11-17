# Continuidade Operacional

O CDC 2.0 foi projetado para garantir **continuidade de execução** mesmo diante de interrupções inesperadas.

## Recuperação de Execuções

O sistema implementa mecanismos de:
- **Persistência de estado:** SQLite armazena progresso atual.
- **Checkpointing:** Estados críticos são registrados periodicamente.
- **Retry automático:** Falhas são detectadas e reprocessadas.

## Armazenamento de Estado

| Componente | Tecnologia | Finalidade |
|------------|------------|------------|
| SQLite | Persistência | Estado de tarefas, objetivos, memória |
| Sessões | Arquivos JSON | Estado de OpenCode por projeto |
| Logs | Arquivos | Rastreamento de erros e decisões |

## Tratamento de Falhas

1. **Detecção:** Timeout ou exceção durante execução.
2. **Rollback:** Estado anterior é restaurado.
3. **Reprocessamento:** Tarefa é reexecutada com nova estratégia.
4. **Alerta:** Proprietário é notificado (quando configurado).

*Note:* Mecanismos específicos estão implementados em:
- `multiagente/multiagente/orquestrador/gerenciador_objetivos_e18.py`
- `multiagente/multiagente/orquestrador/daemon_autonomo.py`
# Observabilidade

O CDC 2.0 implementa observabilidade através de logs estruturados, métricas de status e telemetria de execução.

## Métricas Monitoradas

### Por Projeto
- **Status:** Online/Offline/Em erro
- **Progresso:** % de checkpoints concluídos
- **Última Atividade:** Timestamp da última tarefa
- **Tarefas Concluídas:** Contagem por período

### Sistema Global
- **Foco Atual:** Qual projeto recebe atenção
- **Ciclos Executados:** Contador de iterações
- **Erros Detectados:** Contagem de falhas

## Logs e Telemetria

### Tipos de Logs
1.  **Informação (`INFO`):** Progresso normal.
2.  **Aviso (`WARNING`):** Condições não críticas.
3.  **Erro (`ERROR`):** Falhas e exceções.
4.  **Depuração (`DEBUG`):** Detalhes técnicos.

### Arquivos de Log
- `cdc.log` - Logs gerais do orquestrador.
- `memoria.log` - Atividades de persistência.
- `execucao.log` - Resultados de tarefas.

## Dashboard de Status

O status pode ser consultado via interface:
- Linha de comando: `python dashboard.py`
- Web server: Interface Flask em `http://localhost:8080/status`

---

*Evidência:* `multiagente/multiagente/orquestrador/console_server.py` expõe status via web.
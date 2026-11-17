# Gestão de Recursos

A gestão de recursos no CDC 2.0 contempla tanto **recursos humanos** (via orquestração de agentes) quanto **recursos computacionais** (via alocação de tarefas).

## Recursos Gerenciados

### Recursos Humanos/Agentes
- **Agentes de Desenvolvimento:** Cada projeto tem um agente dedicado.
- **Foco do Orquestrador:** Alternância dinâmica baseada em prioridade.
- **Tempo de Exequível:** Ciclos de 5 minutos de foco por projeto.

### Recursos Computacionais
- **CPU:** Distribuição de tarefas pesadas (ex: scraping, renderização).
- **Memória:** Compartilhamento via SQLite.
- **Disco:** Armazenamento de logs e backups temporários.

## Alocação de Recursos

| Recurso | Alocador | Estratégia |
|---------|----------|------------|
| Foco CPU | Orquestrador | Round-robin com prioridade |
| SQLite | Memória | Lock compartilhado |
| Sessões | Conector OpenCode | Portas dinâmicas |
| Tempo | Agenda CDC | Cron jobs automáticos |

## Limites

- **Máximo 6 agentes ativos simultaneamente.**
- **SQLite como único ponto de persistência.**
- **Nenhum acesso direto a bancos de dados operacionais de projetos externos.**

---

*Nota: Esta é a visão de design. Implementação detalhada em `multiagente/multiagente/orquestrador/`.*
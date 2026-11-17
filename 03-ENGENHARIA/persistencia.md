# Persistência de Dados

O CDC 2.0 utiliza **SQLite** como mecanismo central de persistência, oferecendo:
- Armazenamento leve e local
- Transações ACID para integridade
- Consultas estruturadas para acesso rápido

## Arquitetura de Persistência

```
CDC 2.0
    │
    └──► SQLite Database
            │
            ├─ memoria
            │   └─ Conhecimento contextual por projeto
            │
            ├─ objetivos
            │   └─ Metas definidas e status
            │
            ├─ tarefas
            │   └─ Lista de atividades e execução
            │
            ├─ status_projetos
            │   └─ Progresso e checklist de marcos
            │
            └─ auditoria
                └─ Histórico de decisões e mudanças
```

## Estratégia de Backup

- O banco SQLite é versionado em `CDC.db` (não incluído no portfólio por questões de segurança).
- Backup automático configurado para diretório temporário do usuário.
- Recuperação possível via `sqlite3 .dump` quando necessário.

## Uso por Projeto

| Projeto | Tabelas Access | Função |
|---------|----------------|--------|
| Salomão AI | memoria, status_projetos | Recuperação de conhecimento |
| Cash Hunter | objetivos, tarefas | Rastreamento de oportunidades |
| Matt Pocock | memoria, auditoria | Registro de skills testadas |
| Voz | status_projetos, tarefas | Controle de pipeline de áudio |
| Virada 3D | objetivos, status_projetos | Progresso de modelagem |
| Riqueza | tarefas, objetivos | Gestão de metas educacionais |

---

*Nota: O arquivo `CDC.db` efetivo permanece no ambiente operacional original e não é distribuído por razões de privacidade e segurança.*
# Memória e Contexto

O CDC 2.0 implementa um sistema de **memória persistente** baseado em SQLite, que permite:

- Armazenar estados de execução
- Recuperar conhecimento contextual entre sessões
- Manter histórico de decisões e resultados

## Arquitetura da Memória

```
┌─────────────────────────────────────┐
│  CDC 2.0 Memory System              │
├─────────────────────────────────────┤
│  SQLite Database (unificado)        │
│  ├─ memoria                         │
│  ├─ objetivos                       │
│  ├─ tarefas                         │
│  ├─ status_projetos                 │
│  └─ auditoria                       │
└─────────────────────────────────────┘
```

## Estrutura de Dados

### Tabela `memoria`
Armazena fatos, contextos e informações recuperáveis.

```python
# Estrutura registrada
CREATE TABLE memoria (
    id INTEGER PRIMARY KEY,
    projeto TEXT,
    categoria TEXT,
    conteudo TEXT,
    tipo TEXT,
    modelo TEXT,
    status TEXT,
    timestamp TEXT
)
```

### Tabela `status_projetos`
Monitora progresso de cada projeto.

| Projeto | Status | Último Progresso | Próxima Etapa |
|---------|--------|------------------|---------------|
| Salomão AI | Ativo | Busca na memória implementada | Validação determinística |
| Cash Hunter | Ativo | 35 oportunidades catalogadas | Teste de varredura automática |
| Matt Pocock | Concluído | 39 skills, 13/13 PASS | Próximo ciclo de evolução |

## Uso Prático

- **Salomão AI:** Recupera memória através de consultas estruturadas.
- **Outros Agentes:** Consultam fatos específicos via `memoria_count` e `listar_memoria_projeto`.

*Evidência:* Testes em `multiagente/multiagente/testes/test_e5_memoria.py` demonstram a funcionalidade de retenção e recuperação.
# Arquitetura Multiagente

O CDC 2.0 utiliza uma arquitetura de agentes cooperativos, onde cada projeto é tratado como um agente autônomo com seu próprio ciclo de vida e objetivos.

## Camada de Agentes

```
CDC 2.0 Orquestrador
    │
    ├── Agente: Salomão AI
    │       └─ Função: Memória e conhecimento contextual
    │
    ├── Agente: Riqueza e Prosperidade
    │       └─ Função: Educação financeira e gamificação
    │
    ├── Agente: Cash Hunter
    │       └─ Função: Identificação de oportunidades
    │
    ├── Agente: Matt Pocock
    │       └─ Função: Catálogo de skills (CONCLUÍDO)
    │
    ├── Agente: Voz
    │       └─ Função: Síntese e captura de voz
    │
    └── Agente: VIRADA 3D STUDIO
            └─ Função: Experiência 3D interativa
```

## Comunicação entre Agentes

- **Canal:** SQLite compartilhado via conexão única.
- **Protocolo:** Mensagens estruturadas em tabelas (`objetivos`, `tarefas`, `memoria`, `status_projetos`).
- **Sincronização:** Polling periódico pelo orquestrador a cada ciclo de execução.

## Especialização por Agente

| Agente | Especialização | Tecnologias Chave |
|--------|----------------|-------------------|
| Salomão AI | Memória contextual | Python, SQLite, LLMs |
| Cash Hunter | Oportunidades | Web scraping, APIs |
| Matt Pocock | Skills catalog | TypeScript, React |
| Voz | Síntese/captura | WASAPI, VAD, Web Speech |
| Virada 3D | Visualização 3D | WebGL, Three.js |
| Riqueza | Educação | Fluxo de trabalho |
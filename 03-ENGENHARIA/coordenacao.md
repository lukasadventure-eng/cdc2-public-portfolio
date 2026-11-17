# Coordenação de Tarefas

A coordenação no CDC 2.0 é executada por um **Gerente Autônomo**, responsável por:

## Funções do Coordenador

1.  **Distribuição de Foco:** Decide qual agente/projeto deve atuar em cada ciclo.
2.  **Síntese de Objetivos:** Traduz metas em tarefas executáveis.
3.  **Inteligência de Decisão:** Avalia trade-offs entre projetos.
4.  **Gestão de Recursos:** Aloca tempo e capacidade computacional.

## Mecanismo de Coordenação

### Por Projeto

- **Salomão AI:** Gerenciado por `Gerenciador de Memória`
- **Cash Hunter:** Coordenado por `Gerenciador de Oportunidades`
- **Matt Pocock:** Supervisionado pela `Tabela de Skills`
- **Voz:** Gerenciado por `Pipeline de Áudio`
- **Virada 3D:** Coordenado por `Motor de Modelagem`
- **Riqueza:** Supervisionado pelo `Gerenciador de Educação`

### Interface entre Agentes

A comunicação ocorre via:
- **SQLite:** Leitura/escrita compartilhada
- **Mensagens estruturadas:** JSON em tabelas específicas
- **Eventos de status:** Atualizações em tempo real

## Evidências de Implementação

- `multiagente/multiagente/orquestrador/gerente_autonomo.py` define o gerenciamento de projetos.
- `multiagente/multiagente/orquestrador/processador_fila.py` trata a fila de tarefas.
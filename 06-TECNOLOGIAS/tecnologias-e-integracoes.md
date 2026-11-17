# Tecnologias e Integrações

## Tecnologias por Projeto

### CDC 2.0 Core
| Tecnologia | Uso | Arquivo |
|------------|-----|---------|
| Python 3.11 | Linguagem principal | `gerente_autonomo.py` |
| SQLite | Persistência de dados | `memoria.py` |
| OpenCode | Integração de desenvolvimento | `console_server.py` |

### Salomão AI
| Tecnologia | Uso |
|------------|-----|
| Python | Desenvolvimento |
| SQLite | Memória persistente |
| LLMs | Processamento do conhecimento |

### Cash Hunter
| Tecnologia | Uso |
|------------|-----|
| Python | Web scraping |
| APIs | Coleta de dados |
| NLP | Classificação de oportunidades |

### Matt Pocock
| Tecnologia | Uso |
|------------|-----|
| TypeScript | Desenvolvimento |
| React | Interface do catálogo |
| Jest | Testes automatizados |

### Voz
| Tecnologia | Uso |
|------------|-----|
| WASAPI | Captura de áudio |
| VAD | Detecção de fala |
| Web Speech API | Síntese de voz (browser) |

### VIRADA 3D
| Tecnologia | Uso |
|------------|-----|
| Three.js | Renderização 3D |
| JavaScript | Lógica de modelagem |
| JSON | Especificações técnicas |

### Riqueza e Prosperidade
| Tecnologia | Uso |
|------------|-----|
| CDC 2.0 | Orquestração |
| Three.js | Visualização 3D |
| Sistema econômico simulado | Simulação de finanças |

## Integrações

- **OpenCode ↔ CDC 2.0:** Conector direto via `console_server.py`
- **SQLite ↔ Todos os projetos:** Conexão única para persistência compartilhada
- **Agentes ↔ Agentes:** Comunicação via tabelas SQLite (`memoria`, `status_projetos`)
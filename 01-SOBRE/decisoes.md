# Decisões que eu tomei

## 1. Migrar para modelos gratuitos
Optei por usar modelos locais (Ollama qwen3:8b) em vez de APIs pagas para garantir continuidade sem custos operacionais. Os agentes implementaram adaptadores trocáveis que permitem alternar entre provedores locais e externos. A decisão foi minha; a implementação técnica foi delegada.

## 2. Vigia anti-travamento
Implementei monitoramento de ciclos para detectar quando um projeto trava e forçar alternância de foco. Os agentes criaram o `processador_fila.py` e `gerente_autonomo.py` que executam essa lógica automaticamente. A arquitetura de decisão é minha; o código é dos agentes.

## 3. Correção de testes (Voz)
Quando os testes de captura WASAPI falhavam, optei por corrigir os testes em vez de alterar o código de produção. Os agentes executaram os ajustes e validaram 89/89 PASS. A estratégia de qualidade é minha; a execução é dos agentes.

## 4. Memória persistente em SQLite
Decidi usar SQLite como único mecanismo de persistência para simplicidade e portabilidade. Os agentes implementaram o schema e as funções de recuperação em `memoria.py`. A escolha arquitetural é minha; a implementação é dos agentes.

## 5. Portfólio público documental
Optei por não expor código-fonte operacional, apenas documentação e evidências. Os agentes criaram a estrutura de pastas e arquivos. A política de segurança é minha; a execução é dos agentes.
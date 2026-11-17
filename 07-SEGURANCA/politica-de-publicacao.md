# Política de Publicação e Segurança

Este repositório (**cdc2-public-portfolio**) tem o propósito único de documentar, demonstrar e apresentar o trabalho arquitetural e tecnológico do ecossistema CDC 2.0.

## 1. Diretrizes de Segurança

Para garantir a integridade da operação do CDC 2.0 e proteger informações sensíveis, esta política é rigorosamente aplicada:

- **Proibição de Segredos:** É estritamente proibida a inclusão de chaves de acesso, credenciais, arquivos `.env` ou qualquer dado de autenticação.
- **Isolamento de Código:** Não é permitido publicar o código-fonte operacional proprietário. A documentação deve se concentrar em visões arquiteturais, fluxos e tecnologias, não na implementação detalhada.
- **Proteção de Dados:** Dados pessoais, logs brutos, conversas privadas, identificadores de sessão e configurações de rede privada não devem ser publicados.
- **Ambiente Separado:** Todo material deste portfólio deve ser preparado em um diretório/repositório independente.

## 2. Classificação de Materiais

| Classificação | Descrição | Status de Publicação |
|---------------|-----------|----------------------|
| **Documental** | Visão geral, arquitetura, objetivos | Permitido |
| **Demonstrativo** | Imagens, diagramas, resumos de funcionamento | Permitido (após revisão) |
| **Operacional** | Código-fonte, bancos SQLite, tokens, logs | **Proibido** |

## 3. Procedimento de Revisão

Antes de qualquer `push` para um repositório remoto público (ex: GitHub):
1. **Verificação de Segredos:** Executar varredura automática (ex: git-guardian, ferramentas de detecção de segredos).
2. **Revisão de Conteúdo:** Garantir que apenas materiais documentais/demonstrativos constem no repositório.
3. **Validação de Direitos:** Confirmar se a informação está autorizada para divulgação pública.

---
*Esta política é um compromisso do idealizador para manter a transparência profissional sem comprometer a segurança do ecossistema.*
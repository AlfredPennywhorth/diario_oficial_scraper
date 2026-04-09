# Memória de Projeto - Diario Oficial Scraper

## 📅 Refatoração de Blindagem e Robustez (Abril 2026)

Este documento registra as decisões arquiteturais e melhorias implementadas para transformar o scraper em um sistema de produção local resiliente.

### 🏗️ Arquitetura e Modularização
- **Parser Decomposto:** O método monolítico `extract_details` foi refatorado em funções especializadas por campo (`_extract_dates`, `_extract_values`, etc.), facilitando a manutenção e testes unitários.
- **Camada de Serviço (`ScraperService`):** Introdução de uma camada intermediária entre a API FastAPI e o motor de scraping (`DiarioScraper`), permitindo testes isolados e melhor organização do código.

### 🛡️ Blindagem e Resiliência
- **Filtro de Erros (Shielding):** Implementação de alertas automáticos para campos críticos ausentes sem interromper o fluxo do robô.
- **Persistência de Resultados Parciais:** Salvamento em `partial_results.json` a cada lote, permitindo a recuperação de dados caso o programa seja fechado inesperadamente.
- **Isolamento de IA:** O enriquecimento via Gemini agora possui um timeout rigoroso de 30s e é tratado como um módulo opcional e protegido contra falhas externas.

### 🔒 Segurança e Controle
- **Execução Única:** Proteção contra múltiplas instâncias simultâneas do robô via flag `is_running`.
- **Restrição CORS:** Backend configurado para aceitar requisições apenas de `localhost`, prevenindo acessos externos não autorizados ao serviço de scraping.
- **WebSocket Protection:** Validação de estado no WebSocket para garantir que o usuário não inicie uma busca sobreposta.

### 📊 Padronização de Dados
- Substituição total de `print()` por `logging` estruturado com níveis apropriados (`INFO`, `WARNING`, `ERROR`).
- Normalização de datas e formatos monetários durante a extração para maior consistência no frontend.

---
*Este arquivo serve como guia histórico para futuras manutenções do projeto.*

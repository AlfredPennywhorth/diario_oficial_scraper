# Diario Oficial Scraper

Ferramenta de raspagem e auditoria do Diário Oficial da Cidade de São Paulo, focada em contratos, licitações e aditamentos da CET.

## 🚀 Como Iniciar

1. **Instalação**:
   ```bash
   pip install -r backend/requirements.txt
   playwright install chromium
   ```

2. **Configuração (.env)**:
   Crie um arquivo `.env` na raiz (ou use variáveis de ambiente):
   - `BROWSER_TIMEOUT_MS`: Tempo limite para o navegador (padrão: 90000).
   - `BROWSER_HEADLESS`: Se o navegador deve rodar em segundo plano (true/false).
   - `BROWSER_EXECUTABLE_PATH`: Caminho customizado para o executável do Chrome/Edge.
   - `SCRAPER_ORGAO_ID`: ID do órgão no sistema do DO (padrão: 68 - CET).

3. **Execução**:
   ```bash
   python backend/main.py
   ```
   Acesse `http://127.0.0.1:8085` no seu navegador.

## 🛡️ Diagnóstico de Navegador

Se encontrar erros de "Nenhum navegador compatível", execute:
```bash
python backend/check_browser.py
```
Este script verificará permissões, caminhos de rede (UNC) e a disponibilidade dos binários do Chromium, Chrome e Edge.

## 📁 Estrutura de Pastas

- `backend/`: Código servidor (FastAPI) e lógica de raspagem.
  - `tests/`: Scripts utilitários e de benchmarking.
  - `logs/`: Logs de execução e depuração.
- `frontend/`: Interface web (HTML/CSS/JS).

## 📄 Licença
Uso restrito e interno para auditoria técnica.

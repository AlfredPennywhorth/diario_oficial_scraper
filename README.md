# Diário Oficial Scraper

Scraper local para coleta de publicações do Diário Oficial, com API FastAPI, frontend web e saída estruturada pronta para uso em relatórios e texto de e-mail.

## Requisitos

- Python 3.12+
- Dependências em `backend/requirements.txt`
- Playwright + navegador Chromium

## Instalação

```bash
cd /home/runner/work/diario_oficial_scraper/diario_oficial_scraper
python -m pip install -r backend/requirements.txt
python -m playwright install chromium
```

## Configuração

### Variáveis opcionais

- `SCRAPER_DEBUG=true` → abre navegador visível durante scraping
- `AUTO_OPEN_BROWSER=false` → não abre navegador automaticamente ao iniciar API
- `GEMINI_API_KEY=...` → habilita enriquecimento opcional por IA

## Execução

```bash
cd /home/runner/work/diario_oficial_scraper/diario_oficial_scraper/backend
python main.py
```

Acesse: `http://127.0.0.1:8085`

## Modo teste (dry-run)

No frontend, marque **"Modo teste (dry-run, sem envio externo)"** antes de iniciar a raspagem.

No dry-run:
- a coleta e estruturação dos dados continuam;
- o modo é sinalizado nos logs;
- integrações externas de envio permanecem desativadas.

## Saídas e relatórios

- Visualização em **Cards** e **Texto Email** no frontend.
- Exportação CSV pelo botão da interface.
- Persistência parcial em `backend/partial_results.json` durante execução.
- Formatação HTML adicional via `backend/formatter.py` (`DiarioFormatter`).

## Validações recomendadas

```bash
cd /home/runner/work/diario_oficial_scraper/diario_oficial_scraper
python -m compileall .
python -m pip check
python -m pytest -q
```

## Observações

- O scraping depende de acesso ao domínio do Diário Oficial.
- Sem conectividade/DNS para o domínio alvo, a execução controlada falhará no `page.goto`.

# Guia de Uso - Scraper do Diário Oficial

## 🚀 Como Usar

### 1. Teste Rápido com Formatação HTML

O jeito mais fácil de usar o scraper com formatação automática:

```bash
cd C:\Users\andres\.gemini\antigravity\scratch\diario_official_scraper\backend
python test_formatado.py
```

Isso vai:
- ✅ Buscar publicações de ontem
- ✅ Gerar arquivo `resultados_diario_oficial.html`
- ✅ Abrir automaticamente no navegador
- ✅ Classificar por tipo (Licitação/Contrato/Aditamento)
- ✅ Aplicar cores diferentes para cada tipo

### 2. Opções Disponíveis

**Modo Debug (ver navegador funcionando):**
```bash
python test_formatado.py --debug
```

**Modo Headless (navegador invisível):**
```bash
python test_formatado.py --headless
```

**Não abrir navegador automaticamente:**
```bash
python test_formatado.py --no-browser
```

### 3. Teste Simples (sem formatação)

Se quiser apenas ver os dados brutos:

```bash
python quick_test.py --headless
```

## 📋 Formato da Saída HTML

O arquivo HTML gerado segue o padrão do Google Colab:

- **🔵 LICITAÇÃO** - Borda azul (#004376)
  - Pregões eletrônicos
  - Concorrências
  - Chamamentos públicos
  - Homologações

- **🔷 CONTRATO** - Borda ciano (#17a2b8), fundo cinza claro
  - Contratos de serviço
  - Contratos de fornecimento

- **🟢 ADITAMENTO** - Borda verde (#28a745), fundo verde claro
  - Termos aditivos
  - Prorrogações
  - Aditamentos de valor

### Exemplo de Card Formatado

```
• Processo SEI: 7410.2023/0001792-5
Aditamento nº 070/2025 ao Contrato nº 057/2020
Contratada: EMPRESA EXEMPLO LTDA, CNPJ/CPF 12.***.***-45
Modalidade: PREGÃO ELETRÔNICO
Objeto: prestação de serviços de manutenção...
Data da Assinatura: 16/12/2025
Data da Publicação: 21/01/2026
Vigência: 21/12/2025 a 21/12/2026
Valor: R$ 49.965,12
```

## 🔧 Uso Programático

Se quiser usar no seu próprio código:

```python
import asyncio
from scraper_service import DiarioScraper
from formatter import DiarioFormatter

async def exemplo():
    # Criar scraper
    scraper = DiarioScraper(debug=False)
    formatter = DiarioFormatter()
    
    # Buscar dados
    results = await scraper.scrape(
        start_date="21/01/2026",
        end_date="21/01/2026",
        terms=[],  # Vazio busca todos
        status_callback=None
    )
    
    # Gerar HTML
    formatter.salvar_html(results, "meu_arquivo.html")
    
    # Ou apenas obter o HTML
    html = formatter.formatar_html(results)
    print(html)

# Executar
asyncio.run(exemplo())
```

## 📊 Campos Extraídos

Para cada publicação, o scraper extrai:

- ✅ **Processo SEI**
- ✅ **Número do Documento**
- ✅ **Objeto** (descrição inteligente)
- ✅ **Contratada** (quando disponível)
- ✅ **CNPJ/CPF** (anonimizado se CPF)
- ✅ **Valor** (R$)
- ✅ **Modalidade** (Pregão, Concorrência, etc.)
- ✅ **Data de Assinatura**
- ✅ **Data de Publicação**
- ✅ **Vigência** (período do contrato)
- ✅ **Data de Abertura** (para licitações)
- ✅ **Licitante Vencedor** (quando homologado)
- ✅ **Links** (HTML e PDF)

## 🎨 Características

### Do Google Colab Original

- ✅ Cards coloridos por tipo
- ✅ Classificação automática
- ✅ Anonimização de CPF
- ✅ Extração inteligente de objeto
- ✅ Formatação pronta para copiar/colar

### Melhorias Adicionadas

- ✅ Não trava mais (timeout de 2 minutos)
- ✅ Logs detalhados
- ✅ Modo debug para diagnóstico
- ✅ Salva em arquivo HTML
- ✅ Abre automaticamente no navegador
- ✅ Resumo por tipo ao final

## ⚡ Dicas

1. **Para produção**, use sempre `--headless` (mais rápido)
2. **Para debugar**, use `--debug` (vê o navegador)
3. **Arquivo gerado** fica em: `backend/resultados_diario_oficial.html`
4. **Copiar para publicação**: Abra o HTML e copie o conteúdo desejado
5. **Múltiplas datas**: Edite o `test_formatado.py` e adicione datas em `DATAS_ALVO`

## 🐛 Solução de Problemas

**Processo trava:**
- Use `--headless` ao invés de `--debug`
- Verifique conexão com internet
- Timeout máximo é 2 minutos

**HTML não abre:**
- Caminho completo está no console
- Abra manualmente o arquivo

**Classificação errada:**
- Verifique o resumo do documento
- Palavras-chave: ADITAMENTO, CONTRATO, PREGÃO, LICITAÇÃO

**Campos vazios:**
- Alguns documentos não têm todos os campos
- Aparecerá "Ver íntegra" ou "-"

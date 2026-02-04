# Guia de Release - Diário Oficial Scraper

## 📦 Processo de Release

### Pré-requisitos
- Conta no GitHub
- Repositório criado (público ou privado)
- Git instalado localmente
- Python e dependências instaladas

---

## 🚀 Passo a Passo

### 1. Atualizar Versão no Código

Edite `backend/version.py` e atualize a constante `VERSION`:

```python
VERSION = "1.4.0"  # Nova versão (usar versionamento semântico)
```

**Versionamento Semântico:**
- **MAJOR.MINOR.PATCH** (ex: 1.4.0)
- MAJOR: Mudanças incompatíveis
- MINOR: Novas funcionalidades (compatíveis)
- PATCH: Correções de bugs

### 2. Criar Release com o Script

Execute o script automatizado:

```bash
python create_release.py
```

O script irá:
1. ✅ Limpar builds anteriores
2. ✅ Compilar com PyInstaller
3. ✅ Criar arquivo ZIP
4. ✅ Gerar `version.json` (você fornecerá as informações)

**Dados solicitados pelo script:**
- Data do release (ex: 2026-02-04)
- URL de download (você criará a release no GitHub primeiro - veja passo 3)
- Lista de mudanças (changelog)
- Se é atualização crítica

### 3. Criar Release no GitHub

#### a) Criar repositório (primeira vez apenas)

1. Acesse https://github.com/new
2. Nome sugerido: `diario-scraper` (ou outro nome de sua preferência)
3. Descrição: "Scraper automatizado do Diário Oficial de São Paulo"
4. Escolha **Público** ou **Privado**
5. Clique em **Create repository**

#### b) Fazer upload inicial do projeto (primeira vez apenas)

```bash
cd c:\Users\andres\.gemini\antigravity\scratch\diario_official_scraper
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<SEU_USUARIO>/diario-scraper.git
git branch -M main
git push -u origin main
```

#### c) Criar Release

1. No GitHub, vá para a aba **Releases**
2. Clique em **Draft a new release**
3. **Tag version**: `v1.3.0` (mesmo valor de `VERSION` no código)
4. **Release title**: `Versão 1.3.0 - Nome Descritivo`
5. **Description**: Cole o changelog
6. **Attach binaries**: Faça upload do `DiarioScraper-v1.3.0.zip`
7. Clique em **Publish release**

#### d) Obter URL de Download

Após publicar, copie a URL do arquivo ZIP. Será algo como:
```
https://github.com/<SEU_USUARIO>/diario-scraper/releases/download/v1.3.0/DiarioScraper-v1.3.0.zip
```

⚠️ **IMPORTANTE:** Se executou `create_release.py` antes de criar a release no GitHub, edite o `version.json` e insira a URL correta.

### 4. Upload do version.json

O arquivo `version.json` precisa estar disponível publicamente para verificação de atualizações.

**Opção A: Commit no repositório (recomendado)**

```bash
git add version.json
git commit -m "Update version.json for v1.3.0"
git push
```

A URL ficará: `https://raw.githubusercontent.com/<SEU_USUARIO>/diario-scraper/main/version.json`

**Opção B: Gist público**

1. Acesse https://gist.github.com/
2. Cole o conteúdo de `version.json`
3. Clique em **Create public gist**
4. Use a URL "Raw"

### 5. Configurar URL no Código

Edite `backend/version.py` e atualize a URL:

```python
VERSION_CHECK_URL = "https://raw.githubusercontent.com/<SEU_USUARIO>/diario-scraper/main/version.json"
```

Substitua `<SEU_USUARIO>` e `<diario-scraper>` pelos valores corretos do seu repositório.

⚠️ **Esta configuração só precisa ser feita UMA VEZ.** Nas próximas releases, apenas atualize o `version.json`.

### 6. Testar Verificação de Atualização

1. Compile novamente com a URL configurada: `python create_release.py`
2. Execute o programa
3. Verifique se a versão aparece corretamente no rodapé
4. Simule uma atualização:
   - Edite `version.json` e aumente a versão
   - Faça commit no GitHub
   - Reinicie o programa
   - O banner de atualização deve aparecer

---

## 📋 Exemplo de version.json

```json
{
  "version": "1.3.0",
  "release_date": "2026-02-04",
  "download_url": "https://github.com/<SEU_USUARIO>/diario-scraper/releases/download/v1.3.0/DiarioScraper-v1.3.0.zip",
  "changelog": [
    "Melhoria na classificação de contratos formalizados",
    "Correção de bugs na identificação de pregões",
    "Interface atualizada com banner de notificações"
  ],
  "critical": false
}
```

---

## ⚙️ Configuração Inicial (Checklist)

- [ ] Criar repositório no GitHub
- [ ] Fazer upload inicial do código
- [ ] Atualizar URL em `backend/version.py`
- [ ] Criar primeira release (v1.3.0)
- [ ] Upload do `version.json` no repositório
- [ ] Testar verificação de atualização
- [ ] Distribuir executável para usuários

---

## 🔄 Fluxo de Releases Futuras

1. Editar código e testar
2. Atualizar `VERSION` em `backend/version.py`
3. Executar `python create_release.py`
4. Criar release no GitHub com o ZIP
5. Atualizar `version.json` no repositório
6. Usuários serão notificados automaticamente!

---

## 🛠️ Troubleshooting

### "URL de verificação não configurada"

- Verifique se `VERSION_CHECK_URL` em `backend/version.py` está correto
- Certifique-se de que não contém `<usuario>` ou `<repo>`

### "Não foi possível verificar atualizações"

- Verifique se `version.json` está acessível publicamente
- Teste abrindo a URL diretamente no navegador
- Verifique se o JSON está válido

### Banner não aparece

- Verifique se a versão em `version.json` é maior que a versão atual
- Abra o DevTools do navegador e veja o console
- Teste manualmente: `http://127.0.0.1:8085/api/check-update`

---

## 📞 Suporte

Se tiver problemas, verifique:
1. Logs do console (F12 no navegador)
2. Arquivo `server_error.log` (se existir)
3. Saída do terminal ao executar o programa

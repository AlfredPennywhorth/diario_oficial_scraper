# Script para configurar Git e fazer upload para GitHub
# Adiciona Git ao PATH temporariamente
$env:Path += ";C:\Program Files\Git\bin"

Write-Host "Configurando Git..." -ForegroundColor Cyan

# Configurar nome e email (EDITE COM SEUS DADOS)
git config --global user.name "AlfredPennyworth"
git config --global user.email "seu.email@exemplo.com"  # ALTERE ESTE EMAIL!

Write-Host "`nVerificando status atual..." -ForegroundColor Cyan
git status 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nInicializando repositório Git..." -ForegroundColor Yellow
    git init
    
    Write-Host "`nAdicionando arquivos..." -ForegroundColor Yellow
    git add .
    
    Write-Host "`nCriando commit inicial..." -ForegroundColor Yellow
    git commit -m "Initial commit"
    
    Write-Host "`nConectando ao repositório remoto..." -ForegroundColor Yellow
    git remote add origin https://github.com/AlfredPennyworth/diario_oficial_scraper.git
    
    Write-Host "`nRenomeando branch para main..." -ForegroundColor Yellow
    git branch -M main
    
    Write-Host "`nFazendo push para GitHub..." -ForegroundColor Green
    Write-Host "IMPORTANTE: Você precisará autenticar com GitHub!" -ForegroundColor Red
    git push -u origin main
} else {
    Write-Host "`nRepositório Git já inicializado!" -ForegroundColor Green
    Write-Host "Fazendo push das alterações..." -ForegroundColor Yellow
    git push
}

Write-Host "`n✅ Concluído!" -ForegroundColor Green

"""
Script para criar release do Diário Oficial Scraper
Automatiza o processo de build e criação do pacote distribuível
"""
import os
import shutil
import json
import subprocess
import sys
from pathlib import Path

# Importar versão do backend
sys.path.insert(0, 'backend')
from version import VERSION

print("=" * 60)
print("DIÁRIO OFICIAL SCRAPER - SCRIPT DE RELEASE")
print("=" * 60)
print(f"\nVersão: {VERSION}")
print()

# 1. Limpar builds anteriores
print("1. Limpando builds anteriores...")
for folder in ['build', 'dist']:
    if os.path.exists(folder):
        shutil.rmtree(folder)
        print(f"   ✓ {folder}/ removido")

# 2. Executar PyInstaller
print("\n2. Compilando com PyInstaller...")
result = subprocess.run(['pyinstaller', 'scraper.spec'], capture_output=True, text=True)
if result.returncode != 0:
    print("   ✗ ERRO ao compilar!")
    print(result.stderr)
    sys.exit(1)
print("   ✓ Compilação concluída")

# 3. Verificar se executável foi criado
exe_path = Path('dist/DiarioScraper/DiarioScraper.exe')
if not exe_path.exists():
    print("   ✗ ERRO: Executável não encontrado!")
    sys.exit(1)
print(f"   ✓ Executável criado: {exe_path}")

# 4. Criar ZIP
print("\n3. Criando arquivo ZIP...")
zip_name = f"DiarioScraper-v{VERSION}"
shutil.make_archive(zip_name, 'zip', 'dist/DiarioScraper')
print(f"   ✓ {zip_name}.zip criado")

# 5. Gerar arquivo version.json
print("\n4. Gerando version.json...")
version_data = {
    "version": VERSION,
    "release_date": input("   Data do release (YYYY-MM-DD): ").strip(),
    "download_url": input("   URL de download (GitHub Release): ").strip(),
    "changelog": [],
    "critical": False
}

# Pedir changelog
print("\n   Digite as mudanças (uma por linha, linha vazia para terminar):")
while True:
    change = input("   - ").strip()
    if not change:
        break
    version_data["changelog"].append(change)

# Perguntar se é crítica
critical = input("\n   Esta é uma atualização crítica? (s/N): ").strip().lower()
version_data["critical"] = critical == 's'

# Salvar version.json
with open('version.json', 'w', encoding='utf-8') as f:
    json.dump(version_data, f, indent=2, ensure_ascii=False)
print("   ✓ version.json criado")

# 6. Resumo final
print("\n" + "=" * 60)
print("RELEASE CONCLUÍDO!")
print("=" * 60)
print(f"\nArquivos gerados:")
print(f"  • {zip_name}.zip ({os.path.getsize(f'{zip_name}.zip') / 1024 / 1024:.1f} MB)")
print(f"  • version.json")
print(f"\nPróximos passos:")
print(f"  1. Crie uma nova release no GitHub")
print(f"  2. Faça upload do {zip_name}.zip")
print(f"  3. Faça upload do version.json para o repositório (branch main)")
print(f"  4. Atualize a URL em backend/version.py se necessário")
print()


import os
import shutil
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Importar versão do backend
sys.path.insert(0, 'backend')
from version import VERSION

print("=" * 60)
print("DIÁRIO OFICIAL SCRAPER - BUILD AUTOMÁTICO")
print("=" * 60)
print(f"\nVersão: {VERSION}")
print()

import time

def remove_readonly(func, path, excinfo):
    os.chmod(path, 0o777)
    func(path)

# 1. Limpar builds anteriores
print("1. Limpando builds anteriores...")
for folder in ['build', 'dist']:
    if os.path.exists(folder):
        print(f"   Tentando remover {folder}...")
        for i in range(3):
            try:
                shutil.rmtree(folder, onerror=remove_readonly)
                print(f"   [OK] {folder}/ removido")
                break
            except PermissionError:
                if i < 2:
                    print(f"   [AVISO] Arquivo em uso. Tentando novamente em 2s...")
                    time.sleep(2)
                else:
                    print(f"   [ERRO] Falha ao remover {folder}. Feche programas que possam estar usando a pasta.")
                    sys.exit(1)

# 2. Executar PyInstaller
print("\n2. Compilando com PyInstaller...")
result = subprocess.run(['pyinstaller', 'scraper.spec'], capture_output=True, text=True)
if result.returncode != 0:
    print("   [ERRO] ERRO ao compilar!")
    print(result.stderr)
    sys.exit(1)
print("   [OK] Compilação concluída")

# 3. Verificar se executável foi criado
exe_path = Path('dist/DiarioScraper/DiarioScraper.exe')
if not exe_path.exists():
    print("   [ERRO] Executável não encontrado!")
    sys.exit(1)
print(f"   [OK] Executável criado: {exe_path}")

# 3.1 Copiar Frontend manualmente (garantia)
print("   > Copiando arquivos do frontend...")
frontend_src = Path('frontend')
frontend_dest = Path('dist/DiarioScraper/_internal/frontend')

# Se _internal não existir (pode variar dependendo da versão do PyInstaller), tentar na raiz ou ajustar
if not frontend_dest.parent.exists():
     # Tentar 'dist/DiarioScraper/frontend' caso não use _internal
     if (Path('dist/DiarioScraper').exists()):
          frontend_dest = Path('dist/DiarioScraper/frontend')

if frontend_dest.exists():
    shutil.rmtree(frontend_dest)

try:
    shutil.copytree(frontend_src, frontend_dest)
    print(f"   [OK] Frontend copiado para: {frontend_dest}")
except Exception as e:
    print(f"   [ERRO] Erro ao copiar frontend: {e}")


# 4. Criar ZIP
print("\n3. Criando arquivo ZIP...")
zip_name = f"DiarioScraper-v{VERSION}"
shutil.make_archive(zip_name, 'zip', 'dist/DiarioScraper')
print(f"   [OK] {zip_name}.zip criado")

# 5. Gerar arquivo version.json
print("\n4. Gerando version.json...")
version_data = {
    "version": VERSION,
    "release_date": datetime.now().strftime("%Y-%m-%d"),
    "download_url": f"https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v{VERSION}/DiarioScraper-v{VERSION}.zip",
    "changelog": [
        "Integração com Inteligência Artificial (Google Gemini) para extração de dados",
        "Melhoria na classificação de Acordos de Cooperação",
        "Filtros de tipo de documento via checkbox",
        "Cálculo automático de vigência quando apenas o prazo é mencionado"
    ],
    "critical": False
}

# Salvar version.json
with open('version.json', 'w', encoding='utf-8') as f:
    json.dump(version_data, f, indent=2, ensure_ascii=False)
print("   [OK] version.json criado")

# 6. Resumo final
print("\n" + "=" * 60)
print("BUILD CONCLUÍDO!")
print("=" * 60)

import os
import shutil
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time

# Importar versão do backend
sys.path.insert(0, 'backend')
from version import VERSION

print("=" * 60)
print("DIÁRIO OFICIAL SCRAPER - BUILD EXPERIMENTAL ONE-FILE")
print("=" * 60)
print(f"\nVersão: {VERSION}")
print()

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

print("\n2. Compilando com PyInstaller (modo One-File)...")
print("   (Isso pode demorar de 1 a 3 minutos. Logs detalhados gravados em pyinstaller_build.log)")
with open('pyinstaller_build.log', 'w', encoding='utf-8') as log_file:
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', 'scraper_onefile.spec'],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True
    )

if result.returncode != 0:
    print("   [ERRO] ERRO ao compilar!")
    try:
        with open('pyinstaller_build.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print("\nÚltimas 30 linhas do log de erro:")
            for line in lines[-30:]:
                print("   " + line.strip())
    except Exception as e:
        print(f"   Não foi possível ler o log: {e}")
    sys.exit(1)
print("   [OK] Compilação concluída")

# 3. Verificar se executável foi criado
exe_path = Path('dist/DiarioScraper.exe')
if not exe_path.exists():
    print("   [ERRO] Executável único não encontrado!")
    sys.exit(1)
print(f"   [OK] Executável único criado: {exe_path}")

# 4. Criar ZIP contendo apenas o DiarioScraper.exe na raiz
print("\n3. Criando arquivo ZIP (One-File)...")
zip_name = f"DiarioScraper-OneFile-v{VERSION}"

# Criar pasta temporária para o ZIP
temp_zip_dir = Path('dist/temp_zip')
temp_zip_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(exe_path, temp_zip_dir / 'DiarioScraper.exe')

# Compactar a pasta temporária
shutil.make_archive(zip_name, 'zip', temp_zip_dir)
# Limpar a pasta temporária
shutil.rmtree(temp_zip_dir)

print(f"   [OK] {zip_name}.zip criado ({os.path.getsize(zip_name + '.zip') / 1024 / 1024:.2f} MB)")

# 5. Gerar arquivo version.json para testes do One-File
print("\n4. Gerando version.json...")
version_data = {
    "version": VERSION,
    "release_date": datetime.now().strftime("%Y-%m-%d"),
    "download_url": f"https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v{VERSION}/{zip_name}.zip",
    "changelog": [
        "BUILD EXPERIMENTAL ONE-FILE",
        "Executável único autossuficiente compilado com PyInstaller",
        "Caminhos unificados e persistência de dados no diretório de execução real",
        "Detecção e fallback refinados para Chrome e Edge locais"
    ],
    "critical": False
}

with open('version.json', 'w', encoding='utf-8') as f:
    json.dump(version_data, f, indent=2, ensure_ascii=False)
    f.write('\n')
print("   [OK] version.json criado")

print("\n" + "=" * 60)
print("BUILD EXPERIMENTAL CONCLUÍDO COM SUCESSO!")
print("=" * 60)

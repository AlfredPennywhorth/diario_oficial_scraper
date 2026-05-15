import asyncio
import os
import sys
import shutil
import platform
import subprocess
from playwright.async_api import async_playwright

async def check_browsers():
    print("=" * 60)
    print("DIAGNÓSTICO DE NAVEGADORES - PLAYWRIGHT")
    print("=" * 60)
    
    print(f"\nSistema Operacional: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    cwd = os.getcwd()
    print(f"Diretório atual: {cwd}")
    
    if cwd.startswith("\\\\"):
        print("\n[AVISO] Detectado caminho de rede UNC. Isso pode causar problemas de permissão com o Playwright.")
    
    browsers_to_check = ["chromium", "chrome", "msedge"]
    
    async with async_playwright() as p:
        for b_name in browsers_to_check:
            print(f"\n--- Verificando {b_name} ---")
            
            try:
                # Verificar se o executável existe (para chrome/edge)
                executable_path = None
                if b_name == "chrome":
                    # Caminhos comuns no Windows
                    paths = [
                        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
                    ]
                    for p_val in paths:
                        if os.path.exists(p_val):
                            executable_path = p_val
                            break
                elif b_name == "msedge":
                    paths = [
                        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")
                    ]
                    for p_val in paths:
                        if os.path.exists(p_val):
                            executable_path = p_val
                            break
                
                if executable_path:
                    print(f"Executável encontrado em: {executable_path}")
                
                # Tentar lançar
                print(f"Tentando lançar {b_name}...")
                launch_args = {}
                if b_name == "chrome":
                    launch_args = {"channel": "chrome"}
                elif b_name == "msedge":
                    launch_args = {"channel": "msedge"}
                
                browser = await getattr(p, "chromium").launch(**launch_args, headless=True, timeout=15000)
                print(f"[OK] {b_name} inicializado com sucesso!")
                await browser.close()
                
            except Exception as e:
                print(f"[ERRO] Falha ao inicializar {b_name}:")
                print(f"      Tipo: {type(e).__name__}")
                print(f"      Mensagem: {str(e)[:200]}...")
                
                if "Executable doesn't exist" in str(e):
                    print("      DICA: O binário do Playwright parece estar ausente. Tente rodar 'playwright install chromium'")
                elif "Timeout" in str(e):
                    print("      DICA: O navegador demorou muito para responder. Pode ser bloqueio de rede, antivírus ou caminho UNC.")

    print("\n" + "=" * 60)
    print("FIM DO DIAGNÓSTICO")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(check_browsers())
    except Exception as e:
        print(f"\nErro fatal no script de diagnóstico: {e}")

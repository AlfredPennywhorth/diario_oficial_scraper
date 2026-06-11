from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError
from contextlib import asynccontextmanager
from typing import List
import uvicorn
import asyncio
import os
import sys
import logging
import traceback
import webbrowser
import threading
import multiprocessing
from datetime import datetime

from scraper_service_layer import ScraperService
from models import SearchRequest, SearchResult
from version import get_current_version, check_for_updates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Iniciando Diario Oficial Scraper...")

    # Debug loop type
    loop = asyncio.get_running_loop()
    if sys.platform == 'win32' and not isinstance(loop, asyncio.ProactorEventLoop):
        logger.error("AVISO: Não está usando ProactorEventLoop! Playwright pode falhar.")

    # Inicializa o serviço de scraping (Camada Intermediária)
    app.state.service = ScraperService(debug=True)

    # Verificar atualizações em background
    asyncio.create_task(check_updates_on_startup())

    yield
    # Shutdown
    logger.info("Encerrando servidor...")

app = FastAPI(lifespan=lifespan)

# CORS restrito para segurança (Modo Local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8085", "http://localhost:8085"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Frontend
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
    frontend_path = os.path.join(base_path, "frontend")
else:
    frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")

if not os.path.exists(frontend_path):
    try: os.makedirs(frontend_path)
    except: pass

app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/api/version")
async def get_version():
    return {"version": get_current_version()}

@app.get("/api/check-update")
async def check_update():
    update_info = await check_for_updates()
    if update_info is None:
        return {"available": False, "current_version": get_current_version(), "error": "Erro ao verificar atualizações"}
    return update_info.to_dict()

def get_clean_env():
    import os
    env = os.environ.copy()
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass = sys._MEIPASS
        paths = env.get("PATH", "").split(os.pathsep)
        cleaned_paths = [p for p in paths if meipass not in p]
        env["PATH"] = os.pathsep.join(cleaned_paths)
    env.pop("sys._MEIPASS", None)
    env.pop("_MEIPASS", None)
    return env

@app.post("/api/start-update")
async def start_update():
    import aiohttp
    import subprocess
    import zipfile

    # 1. Determinar caminhos
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    update_dir = os.path.join(app_dir, "update")
    os.makedirs(update_dir, exist_ok=True)

    lock_path = os.path.join(update_dir, "update.lock")
    zip_path = os.path.join(update_dir, "update_temp.zip")
    ps_path = os.path.join(update_dir, "update_helper.ps1")

    # 2. Verificar se já existe atualização em andamento
    if os.path.exists(lock_path):
        logger.warning("Tentativa de atualização rejeitada: arquivo lock já existe.")
        raise HTTPException(status_code=409, detail="Atualização já em andamento (travado por lock).")

    try:
        # Criar o arquivo de lock
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        # 3. Consultar versão disponível
        update_info = await check_for_updates()
        if not update_info or not update_info.available or not update_info.download_url:
            raise HTTPException(status_code=400, detail="Nenhuma atualização disponível para download.")

        url = update_info.download_url
        logger.info(f"Iniciando download da atualização de {url} para {zip_path}")

        # 4. Baixar o ZIP da release
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=500, detail=f"Erro de download: HTTP {response.status}")
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
        logger.info("Download do ZIP concluído.")

        # 5. Validar o ZIP baixado
        if not os.path.exists(zip_path):
            raise HTTPException(status_code=500, detail="Arquivo ZIP não foi salvo fisicamente.")

        zip_size = os.path.getsize(zip_path)
        if zip_size < 500 * 1024: # Pelo menos 500KB
            raise HTTPException(status_code=400, detail=f"Arquivo ZIP baixado está incompleto ou corrompido (tamanho: {zip_size} bytes).")

        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                namelist = z.namelist()
                has_exe = any(name.endswith("DiarioScraper.exe") for name in namelist)
                has_main = any(name.endswith("backend/main.py") for name in namelist)
                if not (has_exe or has_main):
                    raise Exception("A estrutura interna do ZIP não contém o executável esperado ou backend/main.py.")
        except Exception as z_err:
            raise HTTPException(status_code=400, detail=f"ZIP inválido ou ilegível: {str(z_err)}")

        # 6. Gerar update_helper.ps1
        app_dir_esc = app_dir.replace("\\", "/")
        ps_content = f"""# Script de Autoupdate para DiarioScraper
$AppDir = "{app_dir_esc}"
$UpdateDir = Join-Path $AppDir "update"
$ZipPath = Join-Path $UpdateDir "update_temp.zip"
$TempExtract = Join-Path $UpdateDir "extracted"
$LockPath = Join-Path $UpdateDir "update.lock"
$ParentPid = {os.getpid()}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# Garantir estrutura de logs e backups
if (-not (Test-Path (Join-Path $AppDir "logs"))) {{ New-Item -ItemType Directory -Path (Join-Path $AppDir "logs") -Force }}
if (-not (Test-Path (Join-Path $AppDir "backups"))) {{ New-Item -ItemType Directory -Path (Join-Path $AppDir "backups") -Force }}

# Criar arquivo de log started imediatamente
$StartedPath = Join-Path $AppDir "logs/update_helper_started_$Timestamp.log"
New-Item -ItemType File -Path $StartedPath -Force -ErrorAction SilentlyContinue
Add-Content -Path $StartedPath -Value "Update helper started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

$LogPath = Join-Path $AppDir "logs/update_$Timestamp.log"

function Write-Log {{
    param([string]$message)
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Value "[$time] $message"
}}

Write-Log "Iniciando processo de atualizacao automatica..."
Write-Log "Caminho do aplicativo: $AppDir"
Write-Log "PID do processo pai a encerrar: $ParentPid"

# 1. Aguardar encerramento do processo principal
Write-Log "Aguardando o encerramento do processo pai..."
$Timeout = 10
$Elapsed = 0
$Closed = $false
while ($Elapsed -lt $Timeout) {{
    $proc = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
    if (-not $proc) {{
        $Closed = $true
        break
    }}
    Start-Sleep -Seconds 1
    $Elapsed++
}}

if (-not $Closed) {{
    Write-Log "Processo pai nao encerrou no tempo limite. Forcando finalizacao..."
    Stop-Process -Id $ParentPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}} else {{
    Write-Log "Processo pai encerrou com sucesso."
}}

# 2. Validar arquivo ZIP antes de aplicar
Write-Log "Validando arquivo ZIP..."
if (-not (Test-Path $ZipPath)) {{
    Write-Log "ERRO: Arquivo ZIP nao encontrado em $ZipPath"
    if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}
    exit
}}

# 3. Extrair ZIP para update/extracted
Write-Log "Extraindo arquivos para $TempExtract..."
if (Test-Path $TempExtract) {{ Remove-Item -Recurse -Force $TempExtract }}
try {{
    Expand-Archive -Path $ZipPath -DestinationPath $TempExtract -Force
    Write-Log "Extração concluída com sucesso."
}} catch {{
    Write-Log "ERRO ao extrair ZIP: $_"
    if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}
    exit
}}

# 4. Validar estrutura extraída
Write-Log "Validando estrutura de arquivos extraídos..."
$ExePath = Join-Path $TempExtract "DiarioScraper.exe"
$MainPath = Join-Path $TempExtract "backend/main.py"
if (-not (Test-Path $ExePath) -and -not (Test-Path $MainPath)) {{
    Write-Log "ERRO: Arquivos extraídos invalidos. Executável principal ou backend/main.py nao encontrado."
    if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}
    exit
}}

# 5. Criar backup da instalação atual (apenas arquivos controlados)
$BackupDir = Join-Path $AppDir "backups/backup_before_update_$Timestamp"
Write-Log "Criando backup em $BackupDir..."
try {{
    New-Item -ItemType Directory -Path $BackupDir -Force
    $Controlled = @("DiarioScraper.exe", "_internal", "frontend", "backend")
    foreach ($item in $Controlled) {{
        $src = Join-Path $AppDir $item
        if (Test-Path $src) {{
            Copy-Item -Path $src -Destination (Join-Path $BackupDir $item) -Recurse -Force
        }}
    }}
    Write-Log "Backup concluído com sucesso."
}} catch {{
    Write-Log "ERRO ao criar backup: $_"
    if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}
    exit
}}

# 6. Remover arquivos controlados antigos (preservando o resto)
Write-Log "Removendo instalacao anterior (arquivos controlados)..."
try {{
    foreach ($item in $Controlled) {{
        $src = Join-Path $AppDir $item
        if (Test-Path $src) {{
            Remove-Item -Path $src -Recurse -Force
        }}
    }}
    Write-Log "Remoção concluída."
}} catch {{
    Write-Log "ERRO ao remover arquivos antigos: $_. Tentando restaurar backup..."
    foreach ($item in $Controlled) {{
        $back = Join-Path $BackupDir $item
        if (Test-Path $back) {{
            Copy-Item -Path $back -Destination (Join-Path $AppDir $item) -Recurse -Force
        }}
    }}
    if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}
    exit
}}

# 7. Copiar novos arquivos
Write-Log "Instalando nova versão..."
try {{
    Copy-Item -Path (Join-Path $TempExtract "*") -Destination $AppDir -Recurse -Force
    Write-Log "Instalação concluída com sucesso."
}} catch {{
    Write-Log "ERRO ao copiar novos arquivos: $_. Tentando restaurar do backup..."
    foreach ($item in $Controlled) {{
        $back = Join-Path $BackupDir $item
        if (Test-Path $back) {{
            Copy-Item -Path $back -Destination (Join-Path $AppDir $item) -Recurse -Force
        }}
    }}
    if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}
    exit
}}

# 8. Limpeza de temporários
Write-Log "Limpando arquivos temporários..."
if (Test-Path $TempExtract) {{ Remove-Item -Recurse -Force $TempExtract }}
if (Test-Path $ZipPath) {{ Remove-Item -Force $ZipPath }}
if (Test-Path $LockPath) {{ Remove-Item -Force $LockPath }}

# 9. Iniciar nova versão
Write-Log "Reiniciando aplicativo..."
$NewExe = Join-Path $AppDir "DiarioScraper.exe"
if (Test-Path $NewExe) {{
    Start-Process -FilePath $NewExe -WorkingDirectory $AppDir
    Write-Log "Executável reiniciado."
}} else {{
    Start-Process -FilePath "python" -ArgumentList "backend/main.py" -WorkingDirectory $AppDir
    Write-Log "Python backend/main.py reiniciado."
}}

Write-Log "Processo de atualização finalizado com sucesso."
Remove-Item $MyInvocation.MyCommand.Path -Force
"""
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(ps_content)

        # 7. Executar o PowerShell desacoplado de forma robusta
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        powershell_path = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if not os.path.exists(powershell_path):
            logger.warning(f"PowerShell absoluto não encontrado em {powershell_path}. Usando fallback do PATH.")
            powershell_path = "powershell.exe"

        creationflags = 0
        if sys.platform == "win32":
            # CREATE_NEW_CONSOLE (0x00000010) cria um console independente que não morre com o pai
            creationflags = subprocess.CREATE_NEW_CONSOLE

        logger.info("Disparando update_helper.ps1 de forma desacoplada...")
        logger.info(f"Comando: {powershell_path} -NoProfile -ExecutionPolicy Bypass -File {ps_path}")
        logger.info(f"Caminho do script existe? {os.path.exists(ps_path)}")

        try:
            p = subprocess.Popen(
                [powershell_path, "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", ps_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
                cwd=app_dir,
                env=get_clean_env()
            )
            logger.info(f"PowerShell disparado com sucesso. PID: {p.pid}")
            if p.pid is None:
                raise Exception("Falha ao obter o PID do processo PowerShell.")
        except Exception as popen_err:
            logger.error(f"Erro crítico ao disparar Popen do PowerShell: {popen_err}", exc_info=True)
            raise popen_err

        # 8. Agendar desligamento
        async def shutdown():
            await asyncio.sleep(1.5) # Pequeno delay para garantir retorno do JSON
            logger.info("Encerrando aplicação para aplicar a atualização...")
            os._exit(0)

        asyncio.create_task(shutdown())

        return {"status": "success", "message": "Atualização iniciada. A aplicação será reiniciada em instantes."}

    except Exception as e:
        logger.error(f"Erro ao processar atualização: {e}", exc_info=True)
        # Limpeza defensiva do lock e arquivos locais do servidor em caso de erro
        if os.path.exists(lock_path):
            try: os.remove(lock_path)
            except: pass
        if os.path.exists(zip_path):
            try: os.remove(zip_path)
            except: pass
        if os.path.exists(ps_path):
            try: os.remove(ps_path)
            except: pass

        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro interno de atualização: {str(e)}")


async def check_updates_on_startup():
    await asyncio.sleep(2)
    update_info = await check_for_updates()
    if update_info and update_info.available:
        logger.info(f"🎉 Nova versão disponível: {update_info.latest_version}")

@app.post("/api/search", response_model=List[SearchResult])
async def search_endpoint(request: SearchRequest):
    try:
        logger.info(f"Pesquisa via API iniciada: {request.start_date} a {request.end_date}")
        results = await app.state.service.run(request)
        return results
    except Exception as e:
        logger.error(f"Pesquisa via API falhou: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                data = await websocket.receive_json()
                if data.get('action') == 'start_search':
                    # Proteção: Apenas 1 execução simultânea por sessão
                    if app.state.service.is_running:
                        await websocket.send_json({"type": "error", "message": "Scraper já em execução."})
                        continue

                    payload = data.get('payload', {})
                    try:
                        req = SearchRequest(**payload)
                    except ValidationError as ve:
                        await websocket.send_json({"type": "error", "message": f"Erro de validação: {ve.errors()[0]['msg']}"})
                        continue

                    async def log_callback(msg):
                        await websocket.send_json({"type": "log", "message": msg})

                    results = await app.state.service.run(req, status_callback=log_callback)
                    response_data = [r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in results]

                    await websocket.send_json({"type": "result", "data": response_data})
                    await websocket.send_json({"type": "complete"})

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Erro no WebSocket: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "message": f"Erro interno: {str(e)}"})
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    print("\n" + "="*60)
    print(" INICIALIZANDO DIARIO OFICIAL SCRAPER")
    print("="*60)

    try:
        if sys.platform == "win32":
            import asyncio
            from asyncio.windows_events import ProactorEventLoop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running(): loop.stop()
            except: pass
            loop = ProactorEventLoop()
            asyncio.set_event_loop(loop)

        def open_browser():
            import time
            time.sleep(2.5)
            url = "http://127.0.0.1:8085"
            print(f"[INFO] Abrindo navegador em {url} ...")
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=8085, reload=False, log_level="info")
    except Exception as e:
        print("\nERRO FATAL NA INICIALIZAÇÃO:"); traceback.print_exc()
        input("\nPressione ENTER para fechar...")

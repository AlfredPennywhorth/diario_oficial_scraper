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

from scraper_service import DiarioScraper
from models import SearchRequest, SearchResult
from version import get_current_version, check_for_updates

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Diario Scraper...")
    
    # Debug loop type
    loop = asyncio.get_running_loop()
    logger.info(f"Event Loop Type: {type(loop)}")
    if sys.platform == 'win32' and not isinstance(loop, asyncio.ProactorEventLoop):
        logger.error("WARNING: Not running on ProactorEventLoop! Playwright will fail.")

    # Debug=True makes browser visible, often avoiding headless detection issues
    # and giving user feedback since they are watching local execution
    app.state.scraper = DiarioScraper(debug=True)
    
    # Verificar atualizações em background (não bloqueia startup)
    asyncio.create_task(check_updates_on_startup())
    
    yield
    # Shutdown
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Frontend
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    base_path = sys._MEIPASS
    frontend_path = os.path.join(base_path, "frontend")
else:
    # Running as script
    frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")

# Create if not exists to avoid error on startup
if not os.path.exists(frontend_path):
    # In frozen mode this shouldn't happen if properly bundled, but good for safety
    try:
        os.makedirs(frontend_path)
    except: pass

app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/api/version")
async def get_version():
    """Retorna a versão atual do aplicativo"""
    return {"version": get_current_version()}

@app.get("/api/check-update")
async def check_update():
    """Verifica se há atualização disponível"""
    update_info = await check_for_updates()
    
    if update_info is None:
        # Erro ao verificar ou URL não configurada
        return {
            "available": False,
            "current_version": get_current_version(),
            "error": "Não foi possível verificar atualizações"
        }
    
    return update_info.to_dict()

async def check_updates_on_startup():
    """Tarefa assíncrona para verificar updates no startup"""
    await asyncio.sleep(2)  # Aguarda 2s para não competir com startup do scraper
    update_info = await check_for_updates()
    if update_info and update_info.available:
        logger.info(f"🎉 Nova versão disponível: {update_info.latest_version}")

@app.post("/api/search", response_model=List[SearchResult])
async def search_endpoint(request: SearchRequest):
    # This endpoint is synchronous in response but runs scrape async. 
    try:
        logger.info(f"Received search request for {request.start_date} to {request.end_date}")
        results = await app.state.scraper.scrape(
            request.start_date, 
            request.end_date, 
            request.terms
        )
        return results
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                data = await websocket.receive_json()
                if data.get('action') == 'start_search':
                    payload = data.get('payload', {})
                    
                    # Validate payload using Pydantic model
                    # This ensures we have valid dates and terms before passing to scraper
                    try:
                        req = SearchRequest(**payload)
                    except ValidationError as ve:
                        await websocket.send_json({
                            "type": "error", 
                            "message": f"Erro de validação: {ve.errors()[0]['msg']}"
                        })
                        continue

                    async def log_callback(msg):
                        await websocket.send_json({"type": "log", "message": msg})
                    
                    results = await app.state.scraper.scrape(
                        req.start_date,
                        req.end_date,
                        req.terms,
                        status_callback=log_callback
                    )
                    
                    # Convert results to dict (compatible with Pydantic v1/v2)
                    response_data = [r.model_dump() if hasattr(r, 'model_dump') else r.dict() for r in results]
                    
                    await websocket.send_json({"type": "result", "data": response_data})
                    await websocket.send_json({"type": "complete"})
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"WebSocket error: {e}", exc_info=True)
                
                # Write to error log file for debugging
                try:
                    with open("server_error.log", "a", encoding="utf-8") as f:
                        f.write(f"\n[{datetime.now()}] ERROR: {str(e)}\n{error_trace}\n")
                except:
                    pass

                await websocket.send_json({"type": "error", "message": f"Erro interno: {str(e)}"})
                # Don't break loop on error, allow user to try again
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")

if __name__ == "__main__":
    # Suporte para congelamento do executável (PyInstaller) no Windows
    # OBRIGATÓRIO para evitar múltiplas instâncias e travamentos ao usar multiprocessing/playwright
    multiprocessing.freeze_support()
    
    print("\n" + "="*60)
    print(" INICIALIZANDO DIARIO OFICIAL SCRAPER")
    print("="*60)
    
    try:
        # Fix for Windows + Playwright + Uvicorn
        # We must force ProactorEventLoop and avoid reload=True to prevent subprocess issues
        if sys.platform == "win32":
            import asyncio
            from asyncio.windows_events import ProactorEventLoop
            
            # Garantir que o loop anterior seja fechado se existir
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()
            except:
                pass
                
            loop = ProactorEventLoop()
            asyncio.set_event_loop(loop)
            print("[OK] Loop de eventos Proactor configurado para Windows")

        print("[INFO] Iniciando servidor web na porta 8085...")
        print("[INFO] Playwright será inicializado na primeira pesquisa.")
        
        # Open browser automatically after 2.5 seconds
        def open_browser():
            try:
                time.sleep(2.5)
                url = "http://127.0.0.1:8085"
                print(f"[INFO] Abrindo navegador em {url} ...")
                webbrowser.open(url)
            except Exception as eb:
                print(f"[AVISO] Não foi possível abrir o navegador automaticamente: {eb}")
                print(f"[DICA] Abra manualmente: http://127.0.0.1:8085")
        
        import time
        threading.Thread(target=open_browser, daemon=True).start()

        # Pass the app object directly to avoid import errors in frozen state
        # log_level="info" ensures we see uvicorn startup logs
        uvicorn.run(app, host="127.0.0.1", port=8085, reload=False, log_level="info")
    
    except Exception as e:
        print("\n" + "!"*60)
        print(" ERRO FATAL NA INICIALIZAÇÃO:")
        print("!"*60)
        traceback.print_exc()
        print("!"*60)
        
        # Log error to file
        try:
            with open("startup_error.log", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now()}] FATAL STARTUP ERROR: {str(e)}\n{traceback.format_exc()}\n")
        except: pass
        
        input("\nPressione ENTER para fechar a janela...")

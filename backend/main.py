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

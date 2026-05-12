import asyncio
import logging
import multiprocessing
import os
import sys
import threading
import traceback
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from models import SearchRequest, SearchResult
from scraper_service_layer import ScraperService
from version import check_for_updates, get_current_version

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "127.0.0.1")
PORT_RAW = os.getenv("PORT", "8085")
try:
    PORT = int(PORT_RAW)
except ValueError:
    logger.warning("Valor inválido para PORT=%s. Usando 8085.", PORT_RAW)
    PORT = 8085
ALLOWED_ORIGINS = [f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"]

if getattr(sys, 'frozen', False):
    BASE_PATH = Path(getattr(sys, '_MEIPASS'))
    FRONTEND_PATH = BASE_PATH / "frontend"
else:
    FRONTEND_PATH = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Diario Oficial Scraper...")

    loop = asyncio.get_running_loop()
    if sys.platform == 'win32' and not isinstance(loop, asyncio.ProactorEventLoop):
        logger.error("AVISO: Não está usando ProactorEventLoop! Playwright pode falhar.")

    app.state.service = ScraperService(debug=os.getenv("SCRAPER_DEBUG", "false").lower() == "true")
    asyncio.create_task(check_updates_on_startup())

    yield
    logger.info("Encerrando servidor...")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_PATH.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_PATH)), name="static")


@app.get("/")
async def read_index():
    return FileResponse(FRONTEND_PATH / "index.html")


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
        logger.info("🎉 Nova versão disponível: %s", update_info.latest_version)


@app.post("/api/search", response_model=List[SearchResult])
async def search_endpoint(request: SearchRequest):
    try:
        logger.info("Pesquisa via API iniciada: %s a %s", request.start_date, request.end_date)
        return await app.state.service.run(request)
    except Exception as exc:
        logger.error("Pesquisa via API falhou: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                data = await websocket.receive_json()
                if data.get('action') != 'start_search':
                    continue

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
            except Exception as exc:
                logger.error("Erro no WebSocket: %s", exc, exc_info=True)
                await websocket.send_json({"type": "error", "message": f"Erro interno: {exc}"})
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    logger.info("=" * 60)
    logger.info(" INICIALIZANDO DIARIO OFICIAL SCRAPER")
    logger.info("=" * 60)

    try:
        if sys.platform == "win32":
            from asyncio.windows_events import ProactorEventLoop

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()
            except RuntimeError:
                pass
            loop = ProactorEventLoop()
            asyncio.set_event_loop(loop)

        def open_browser():
            import time

            time.sleep(2.5)
            url = f"http://{HOST}:{PORT}"
            logger.info("Abrindo navegador em %s ...", url)
            webbrowser.open(url)

        if os.getenv("AUTO_OPEN_BROWSER", "true").lower() == "true":
            threading.Thread(target=open_browser, daemon=True).start()

        uvicorn.run(app, host=HOST, port=PORT, reload=False, log_level="info")
    except Exception:
        logger.error("ERRO FATAL NA INICIALIZAÇÃO")
        logger.error(traceback.format_exc())
        input("\nPressione ENTER para fechar...")

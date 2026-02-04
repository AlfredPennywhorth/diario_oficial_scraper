
import asyncio
import sys
import os
from scraper_service import DiarioScraper
from datetime import datetime

# Add backend to path
sys.path.append(os.getcwd())

async def run():
    print(f"[{datetime.now()}] Iniciando verificação de saúde do scraper...")
    scraper = DiarioScraper(debug=False)
    
    # Use a single date, preferably today or yesterday
    target_date = datetime.now().strftime("%d/%m/%Y")
    
    print(f"[{datetime.now()}] Testando scrape para apenas 1 dia: {target_date}")
    
    async def log(msg):
        # Print only essential logs to avoid buffer overflow
        if "[ERRO]" in msg or "Encontrados" in msg:
            print(f"[CALLBACK] {msg}")

    try:
        results = await scraper.scrape(target_date, target_date, ["Contrato"], status_callback=log)
        print(f"[{datetime.now()}] Sucesso! Retornados {len(results)} resultados.")
    except Exception as e:
        print(f"[{datetime.now()}] ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run())

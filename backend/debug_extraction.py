
import asyncio
import sys
import os

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Ensure backend acts as package root
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from scraper_service import DiarioScraper

# Monkey patch _log to print to stdout
def log_patch(self, msg):
    try:
        print(f"[DEBUG] {msg}", flush=True)
    except:
        pass

DiarioScraper._log = log_patch

async def run_targeted_debug():
    scraper = DiarioScraper(debug=False)
    
    print("🚀 DEBUGGING extração do dia 14/01/2026...")
    
    # We will hook into the scrape logic by running it but catching the flow or just trusting the logging change
    # But better to just run it and see the new logs if we add them to the service.
    # Actually, let's modify the service to print WHY it skips items.
    
    results = await scraper.scrape(
        start_date="14/01/2026",
        end_date="14/01/2026",
        terms=[]
    )
    
    print(f"\n✅ Encontrados {len(results)} documentos.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_targeted_debug())

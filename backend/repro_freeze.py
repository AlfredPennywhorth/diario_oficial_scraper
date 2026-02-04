import asyncio
import sys
import os
from scraper_service import DiarioScraper

# Add backend to path
sys.path.append(os.getcwd())

async def run():
    print("Initializing scraper...")
    scraper = DiarioScraper(debug=False)
    
    start_date = "28/01/2026"
    end_date = "27/01/2026"
    
    print(f"Testing inverted dates: {start_date} to {end_date}")
    
    async def log(msg):
        print(f"[CALLBACK] {msg}")

    try:
        print("Calling scrape...")
        results = await scraper.scrape(start_date, end_date, ["Contrato"], status_callback=log)
        print(f"Scrape returned. Results count: {len(results)}")
    except Exception as e:
        print(f"ERROR CAUGHT: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run())

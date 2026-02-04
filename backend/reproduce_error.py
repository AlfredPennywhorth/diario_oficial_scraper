
import asyncio
import sys
import os
from datetime import datetime

# Add backend to path
sys.path.append(os.getcwd())

from scraper_service import DiarioScraper

async def run():
    scraper = DiarioScraper(debug=False)
    today = datetime.now().strftime("%d/%m/%Y")
    print(f"Testing scraper for TODAY: {today}")
    
    async def log(msg):
        print(f"[LOG] {msg}")

    try:
        results = await scraper.scrape(today, today, [], status_callback=log)
        print(f"Results: {len(results)}")
    except Exception as e:
        print(f"ERROR CAUGHT: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run())

import asyncio
import os
import sys
from datetime import datetime
import time

# Add current directory to path so we can import scraper_service
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper_service import DiarioScraper

async def run_test():
    scraper = DiarioScraper(debug=True)
    
    # Test with a date that likely has data (e.g. yesterday or a week ago)
    # Today is 2026-02-18. Let's try 2026-02-10 (Tuesday)
    test_date = "10/02/2026"
    
    print(f"Starting test for {test_date}...")
    start_time = time.time()
    
    async def callback(msg):
        print(f"[CALLBACK] {msg}")

    try:
        results = await scraper.scrape(test_date, test_date, [], status_callback=callback)
        end_time = time.time()
        print(f"Test finished in {end_time - start_time:.2f} seconds.")
        print(f"Found {len(results)} results.")
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())

import asyncio
import os
import sys
import time

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper_service import DiarioScraper

async def run_benchmark():
    scraper = DiarioScraper(debug=True)
    
    # query 3 days
    start_date = "05/02/2026"
    end_date = "07/02/2026"
    
    print(f"Starting benchmark for {start_date} to {end_date}...")
    start_time = time.time()
    
    async def callback(msg):
        print(f"[CALLBACK] {msg}")

    try:
        results = await scraper.scrape(start_date, end_date, [], status_callback=callback)
        total_time = time.time() - start_time
        print(f"\nBenchmark finished in {total_time:.2f} seconds.")
        print(f"Found {len(results)} results.")
        
        # Simple analysis
        days = 3
        print(f"Average time per day: {total_time / days:.2f}s")
        
    except Exception as e:
        print(f"Benchmark failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())

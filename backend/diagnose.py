
import asyncio
import sys
import os
from datetime import datetime
from playwright.async_api import async_playwright

# Force unbuffered output
sys.stdout.reconfigure(encoding='utf-8')

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

async def diagnose():
    log("🚀 Starting diagnostics...")
    
    # 1. Check Internet
    log("1️⃣  Checking connection to google.com...")
    try:
        import socket
        socket.create_connection(("www.google.com", 80), timeout=5)
        log("✅ Connection OK")
    except Exception as e:
        log(f"❌ Connection FAILED: {e}")

    # 2. Test Playwright Launch
    log("2️⃣  Testing Playwright Browser Launch...")
    try:
        async with async_playwright() as p:
            log("   - Launching Chromium...")
            browser = await asyncio.wait_for(p.chromium.launch(headless=True), timeout=10)
            log("   - Browser launched.")
            page = await browser.new_page()
            log("   - Page created.")
            
            # 3. Test Target URL
            url = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=materias_pesquisar"
            log(f"3️⃣  Navigating to {url}...")
            await asyncio.wait_for(page.goto(url, timeout=30000), timeout=35)
            log("✅ Navigation successful")
            
            title = await page.title()
            log(f"   - Page Title: {title}")
            
            await browser.close()
            log("✅ Browser closed")
            
    except asyncio.TimeoutError:
        log("❌ Operation TIMED OUT")
    except Exception as e:
        log(f"❌ Playwright Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(diagnose())

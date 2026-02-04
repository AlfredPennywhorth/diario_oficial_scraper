import asyncio
from playwright.async_api import async_playwright

BASE_URL = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=materias_pesquisar"

async def test_connection():
    print(f"Testing connection to {BASE_URL}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            print("Navigating...")
            response = await page.goto(BASE_URL, timeout=60000)
            
            if response:
                print(f"Status: {response.status}")
                print(f"Title: {await page.title()}")
            else:
                print("No response received.")
                
            print("Taking screenshot...")
            await page.screenshot(path="connection_test.png")
            print("Screenshot saved to connection_test.png")
            
            await browser.close()
            print("Success!")
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())

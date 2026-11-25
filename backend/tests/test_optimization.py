import asyncio
import os
import sys
import time
import pytest
from playwright.async_api import async_playwright

@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('RUN_PORTAL_INTEGRATION') != '1', reason='Requer navegador instalado e acesso ao portal; execute com RUN_PORTAL_INTEGRATION=1')
async def test_optimizations():
    url = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=materias_pesquisar"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("--- Test 1: DOMContentLoaded ---")
        start = time.time()
        response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        assert response and response.ok, f"Portal indisponível: HTTP {response.status if response else 'desconhecido'}"
        print(f"Goto (domcontentloaded) took: {time.time() - start:.2f}s")

        current_date = "10/02/2026"
        orgao_id = "68"
        
        js_cmd = f"""
            var f = document.createElement('form'); f.action='md_epubli_controlador.php?acao=materias_pesquisar'; f.method='POST';
            var i1=document.createElement('input');i1.name='hdnDataPublicacao';i1.value='{current_date}';f.appendChild(i1);
            var i2=document.createElement('input');i2.name='hdnOrgaoFiltro';i2.value='{orgao_id}';f.appendChild(i2);
            var i3=document.createElement('input');i3.name='hdnModoPesquisa';i3.value='DATA';f.appendChild(i3);
            var i4=document.createElement('input');i4.name='hdnVisualizacao';i4.value='L';f.appendChild(i4);
            document.body.appendChild(f); f.submit();
        """
        
        print("Submitting form...")
        start_submit = time.time()
        async with page.expect_navigation():
             await page.evaluate(js_cmd)
        
        print(f"Form submission navigation took: {time.time() - start_submit:.2f}s")
        
        await page.wait_for_selector('div.dadosDocumento', timeout=5000)
        print("Results found!")

        print("\n--- Test 2: Consecutive Search (No Goto) ---")
        next_date = "11/02/2026"
        js_cmd_next = f"""
            var f = document.createElement('form'); f.action='md_epubli_controlador.php?acao=materias_pesquisar'; f.method='POST';
            var i1=document.createElement('input');i1.name='hdnDataPublicacao';i1.value='{next_date}';f.appendChild(i1);
            var i2=document.createElement('input');i2.name='hdnOrgaoFiltro';i2.value='{orgao_id}';f.appendChild(i2);
            var i3=document.createElement('input');i3.name='hdnModoPesquisa';i3.value='DATA';f.appendChild(i3);
            var i4=document.createElement('input');i4.name='hdnVisualizacao';i4.value='L';f.appendChild(i4);
            document.body.appendChild(f); f.submit();
        """
        
        print(f"Attempting search for {next_date} directly from current page...")
        start_next = time.time()
        async with page.expect_navigation(timeout=10000):
            await page.evaluate(js_cmd_next)
        print(f"Consecutive search navigation took: {time.time() - start_next:.2f}s")
        await page.wait_for_load_state('domcontentloaded')
        print("Consecutive search page loaded.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_optimizations())

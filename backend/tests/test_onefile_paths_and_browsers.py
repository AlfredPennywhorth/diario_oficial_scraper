import os
import sys
import pytest
from unittest import mock
from pathlib import Path

# Adiciona o diretório backend ao sys.path se necessário
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from paths import get_bundle_dir, get_app_dir, get_frontend_dir, get_logs_dir, get_partial_results_path
from scraper_service import DiarioScraper

def test_paths_in_development():
    """Testa se os caminhos retornados em modo desenvolvimento (não congelado) estão corretos."""
    with mock.patch('sys.frozen', False, create=True):
        bundle = get_bundle_dir()
        app = get_app_dir()
        frontend = get_frontend_dir()
        logs = get_logs_dir()
        partial = get_partial_results_path()

        # No desenvolvimento, todos devem apontar para a raiz do repositório/estrutura correta
        assert bundle.exists()
        assert app.exists()
        assert frontend.name == "frontend"
        assert logs.name == "logs"
        assert partial.name == "partial_results.json"

def test_paths_in_frozen_onefile():
    """Testa se os caminhos simulados em modo congelado One-File resolvem para locais corretos."""
    fake_meipass = "/tmp/fake_meipass"
    fake_executable = "/usr/bin/DiarioScraper.exe" if sys.platform != "win32" else "C:\\Program Files\\DiarioScraper\\DiarioScraper.exe"

    with mock.patch('sys.frozen', True, create=True), \
         mock.patch('sys._MEIPASS', fake_meipass, create=True), \
         mock.patch('sys.executable', fake_executable, create=True), \
         mock.patch('os.makedirs') as mock_makedirs:

        bundle = get_bundle_dir()
        app = get_app_dir()
        frontend = get_frontend_dir()
        logs = get_logs_dir()
        partial = get_partial_results_path()

        # Usar Path para normalizar barras do Windows/Unix nas asserções
        assert Path(bundle) == Path(fake_meipass)
        assert Path(app) == Path(os.path.dirname(fake_executable))
        assert Path(frontend) == Path(fake_meipass) / "frontend"
        assert Path(logs) == Path(os.path.dirname(fake_executable)) / "logs"
        assert Path(partial) == Path(os.path.dirname(fake_executable)) / "partial_results.json"

@pytest.mark.asyncio
async def test_scraper_friendly_browser_error():
    """Testa se o scraper levanta um erro amigável quando nenhum navegador é encontrado."""
    scraper = DiarioScraper(debug=False)
    
    # Vamos simular que todas as tentativas de lançamento de navegador falham
    # com "Executable doesn't exist" (que é o comportamento padrão quando não há navegadores instalados no playwright)
    
    # Mock do async_playwright context manager
    mock_playwright_instance = mock.AsyncMock()
    # Fazer p.chromium.launch lançar a exceção
    mock_playwright_instance.chromium.launch = mock.AsyncMock(
        side_effect=Exception("Executable doesn't exist at /usr/bin/local/chromium...")
    )
    
    # Substituir o context manager async_playwright
    with mock.patch('scraper_service.async_playwright') as mock_async_playwright:
        mock_async_playwright.return_value.__aenter__.return_value = mock_playwright_instance
        
        with pytest.raises(Exception) as exc_info:
            # Chamar scrape (o método correto) com uma data qualquer para disparar a inicialização do browser
            await scraper.scrape(
                start_date="08/07/2026", 
                end_date="08/07/2026", 
                terms=["teste"],
                use_ai=False
            )
            
        assert "Não foi possível localizar o Google Chrome ou o Microsoft Edge" in str(exc_info.value)
        assert "preferencialmente o Microsoft Edge no Windows" in str(exc_info.value)

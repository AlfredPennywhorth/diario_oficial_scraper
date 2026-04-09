import logging
from typing import List
from models import SearchRequest, SearchResult
from scraper_service import DiarioScraper

logger = logging.getLogger(__name__)

class ScraperService:
    """Camada intermediária para desacoplar a API do Scraper"""
    
    def __init__(self, debug: bool = True):
        self._scraper = DiarioScraper(debug=debug)

    @property
    def is_running(self) -> bool:
        return self._scraper.is_running

    async def run(self, request: SearchRequest, status_callback=None, use_ai=True) -> List[SearchResult]:
        """Executa o scraping baseado num objeto SearchRequest"""
        logger.info(f"Iniciando serviço de scraping para {len(request.terms)} termos... (IA={use_ai})")
        
        return await self._scraper.scrape(
            start_date=request.start_date,
            end_date=request.end_date,
            terms=request.terms,
            status_callback=status_callback,
            use_ai=use_ai
        )

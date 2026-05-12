import logging
from typing import List

from models import SearchRequest, SearchResult
from scraper_service import DiarioScraper

logger = logging.getLogger(__name__)


class ScraperService:
    """Camada intermediária para desacoplar a API do Scraper."""

    def __init__(self, debug: bool = True):
        self._scraper = DiarioScraper(debug=debug)

    @property
    def is_running(self) -> bool:
        return self._scraper.is_running

    async def run(self, request: SearchRequest, status_callback=None, use_ai: bool | None = None) -> List[SearchResult]:
        if use_ai is None:
            use_ai = not request.dry_run

        logger.info(
            "Iniciando serviço de scraping para %d termos... (IA=%s, dry_run=%s)",
            len(request.terms),
            use_ai,
            request.dry_run,
        )

        if request.dry_run and status_callback:
            await status_callback("Modo dry-run ativo: coleta e formatação executadas sem integrações externas de envio.")

        return await self._scraper.scrape(
            start_date=request.start_date,
            end_date=request.end_date,
            terms=request.terms,
            status_callback=status_callback,
            use_ai=use_ai,
        )

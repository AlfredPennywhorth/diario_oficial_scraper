import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_service import DiarioScraper, IncompleteSearch, SearchFailure, _classify_unit


def test_classification_uses_only_metadata_and_institutional_header():
    assert _classify_unit('CET/DBP', BeautifulSoup('<p>GSU</p>', 'html.parser')) == 'DBP'
    assert _classify_unit('', BeautifulSoup('<p class="Centralizado_Timbre_Secretaria">Departamento de Aquisição de Bens e Serviços Especializados</p>', 'html.parser')) == 'DBE'
    assert _classify_unit('CET/GSU/DTC/PP', BeautifulSoup('', 'html.parser')) == 'GSU'
    assert _classify_unit('CET/OUTRO', BeautifulSoup('', 'html.parser')) == 'OUTRA'
    assert _classify_unit('', BeautifulSoup('<p>Contrato CET/DBE e CET/DBP</p>', 'html.parser')) is None
    assert _classify_unit('CET/DBP', BeautifulSoup('<p class="Centralizado_Timbre_Secretaria">CET/DBE</p>', 'html.parser')) is None


def make_page(status=200, navigation_error=None):
    page = MagicMock()
    page.url = 'https://portal.example/resultado'
    navigation = MagicMock()
    navigation.__aenter__ = AsyncMock(return_value=navigation, side_effect=navigation_error)
    navigation.__aexit__ = AsyncMock(return_value=False)
    async def response():
        return SimpleNamespace(status=status)
    type(navigation).value = property(lambda self: response())
    page.expect_navigation.return_value = navigation
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    page.evaluate = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=['publicacao'])
    page.content = AsyncMock(return_value='Nenhum registro encontrado')
    return page


@pytest.mark.asyncio
async def test_search_does_not_select_unit():
    scraper = DiarioScraper()
    page = make_page()
    assert await scraper._fetch_day(page, '09/11/2026') == ['publicacao']
    script, arguments = page.evaluate.await_args.args
    assert arguments == {'date': '09/11/2026', 'orgao': '68'}
    assert 'hdnUnidadeResponsavelFiltro' not in script


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [PlaywrightTimeoutError('timeout'), PlaywrightError('net::ERR_CONNECTION_RESET')])
async def test_transient_navigation_errors_retry_with_trace(error, caplog):
    scraper = DiarioScraper()
    page = make_page(navigation_error=error)
    with patch('scraper_service.asyncio.sleep', new_callable=AsyncMock) as sleep:
        with pytest.raises(type(error)):
            await scraper._fetch_day(page, '09/11/2026')
    assert page.expect_navigation.call_count == 2
    page.goto.assert_awaited_once_with(scraper.base_url, timeout=30000)
    sleep.assert_awaited_once_with(2)
    assert '09/11/2026' in caplog.text and 'timeout_ms=30000' in caplog.text
    assert 'Traceback' in caplog.text


@pytest.mark.asyncio
async def test_http_403_is_not_retried(caplog):
    page = make_page(status=403)
    with pytest.raises(SearchFailure, match='HTTP 403'):
        await DiarioScraper()._fetch_day(page, '09/11/2026')
    assert page.expect_navigation.call_count == 1
    assert 'HTTP=403' in caplog.text


@pytest.mark.asyncio
async def test_empty_is_distinct_from_unknown_page():
    page = make_page()
    page.wait_for_selector.side_effect = PlaywrightTimeoutError('selector timeout')
    assert await DiarioScraper()._fetch_day(page, '09/11/2026') == []
    page.content.return_value = '<html>sessão expirada</html>'
    with pytest.raises(SearchFailure, match='falha de sessão'):
        await DiarioScraper()._fetch_day(page, '09/11/2026')


@pytest.mark.asyncio
async def test_disappearing_results_are_not_reported_as_empty():
    page = make_page()
    page.query_selector_all.return_value = []
    page.content.return_value = '<html>Resultados indisponíveis</html>'
    with pytest.raises(SearchFailure, match='desapareceram'):
        await DiarioScraper()._fetch_day(page, '09/11/2026')
    page.content.return_value = '<html>Nenhum registro encontrado</html>'
    assert await DiarioScraper()._fetch_day(page, '09/11/2026') == []


@pytest.mark.asyncio
async def test_empty_message_must_be_presented_and_can_arrive_late():
    page = make_page()
    page.query_selector_all.return_value = []
    page.content.return_value = '<html><script>"Nenhum registro encontrado"</script></html>'
    with pytest.raises(SearchFailure, match='desapareceram'):
        await DiarioScraper()._fetch_day(page, '09/11/2026')
    page.content.return_value = '<div style="display: none">Nenhum registro encontrado</div>'
    with pytest.raises(SearchFailure, match='desapareceram'):
        await DiarioScraper()._fetch_day(page, '09/11/2026')
    page.wait_for_selector.side_effect = PlaywrightTimeoutError('selector timeout')
    page.content.side_effect = ['<html>Carregando</html>', '<html>Nenhum registro encontrado</html>']
    assert await DiarioScraper()._fetch_day(page, '09/11/2026') == []


@pytest.mark.asyncio
async def test_failed_days_preserve_partial_results_without_overwriting_files(tmp_path):
    scraper = DiarioScraper()
    scraper.partial_results_file = str(tmp_path / 'partial.json')
    with open(scraper.partial_results_file, 'w', encoding='utf-8') as existing:
        existing.write('existing')
    item = MagicMock()
    item.inner_text = AsyncMock(return_value='Documento: 123\nUnidade responsável: CET/DBP\nContrato')
    link = MagicMock()
    link.get_attribute = AsyncMock(return_value='md_epubli_visualizar.php?id=123')
    item.query_selector = AsyncMock(return_value=link)
    page = make_page()
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    detail = make_page()
    detail.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    detail.content = AsyncMock(return_value='<p class="Centralizado_Timbre_Secretaria">CET/DBP</p><p>Contrato</p>')
    detail.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=[page, detail])
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, side_effect=[[item], SearchFailure('HTTP 403'), PlaywrightTimeoutError('timeout')]):
        with pytest.raises(IncompleteSearch) as caught:
            await scraper.scrape('09/11/2026', '11/11/2026', ['contrato'], use_ai=False)
    assert caught.value.failures == ['10/11/2026', '11/11/2026']
    assert [(result.document_id, result.unit) for result in caught.value.results] == [('123', 'DBP')]
    with open(scraper.partial_results_file, encoding='utf-8') as existing:
        assert existing.read() == 'existing'
    assert scraper._run_results_file != scraper.partial_results_file
    with open(scraper._run_results_file, encoding='utf-8') as saved:
        assert '"document_id": "123"' in saved.read()


@pytest.mark.asyncio
async def test_unexpected_error_after_results_preserves_partial_data():
    scraper = DiarioScraper()
    item = MagicMock()
    item.inner_text = AsyncMock(return_value='Documento: 123\nUnidade responsável: CET/DBP\nContrato')
    link = MagicMock()
    link.get_attribute = AsyncMock(return_value='md_epubli_visualizar.php?id=123')
    item.query_selector = AsyncMock(return_value=link)
    detail = make_page()
    detail.content = AsyncMock(return_value='<p class="Centralizado_Timbre_Secretaria">CET/DBP</p><p>Contrato</p>')
    detail.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=[make_page(), detail])
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock(side_effect=PlaywrightError('browser closed unexpectedly'))
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, return_value=[item]), \
         patch.object(scraper, '_save_partial_results'):
        with pytest.raises(IncompleteSearch) as caught:
            await scraper.scrape('09/11/2026', '09/11/2026', ['contrato'], use_ai=False)
    assert [result.document_id for result in caught.value.results] == ['123']
    assert caught.value.failures == ['09/11/2026']
    assert isinstance(caught.value.__cause__, PlaywrightError)


@pytest.mark.asyncio
async def test_units_classified_after_broad_search_without_dropdown(caplog):
    scraper = DiarioScraper()
    page = make_page()
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    items = []
    details = []
    for doc_id, unit in [('101', 'DBP'), ('102', 'DBE'), ('103', 'GSU'), ('104', 'ABC'), ('105', 'DBE')]:
        item = MagicMock()
        item.inner_text = AsyncMock(return_value=f'Documento: {doc_id}\n' + ('Aviso' if doc_id == '105' else 'Contrato'))
        link = MagicMock()
        link.get_attribute = AsyncMock(return_value=f'md_epubli_visualizar.php?id={doc_id}')
        item.query_selector = AsyncMock(return_value=link)
        items.append(item)
        detail = make_page()
        detail.goto = AsyncMock(return_value=SimpleNamespace(status=200))
        detail.content = AsyncMock(return_value=f'<p class="Centralizado_Timbre_Secretaria">CET/{unit}</p><p>Contrato</p>')
        detail.close = AsyncMock()
        details.append(detail)
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=[page] + details)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    caplog.set_level('INFO')
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, return_value=items), \
         patch.object(scraper, '_save_partial_results'):
        results = await scraper.scrape('09/11/2026', '09/11/2026', ['contrato'], use_ai=False)
    assert [(result.document_id, result.unit) for result in results] == [('101', 'DBP'), ('102', 'DBE')]
    assert 'recuperadas=5 termos=4' in caplog.text and "'DBE': 2" in caplog.text and 'pertinentes=2' in caplog.text
    assert 'unidade GSU fora do escopo' in caplog.text and 'unidade OUTRA fora do escopo' in caplog.text
    assert 'documento=105 etapa=filtro motivo=termo não correspondente' in caplog.text


@pytest.mark.asyncio
async def test_metadata_avoids_unnecessary_detail_requests_and_flags_unknown(caplog):
    scraper = DiarioScraper()
    records = [
        ('201', 'Unidade responsável: CET/DBP\nContrato com referência à CET/GSU'),
        ('202', 'Unidade responsável: CET/DBE\nAviso'),
        ('203', 'Unidade responsável: CET/GSU/DTC/PP\nContrato'),
        ('204', 'Unidade responsável: CET/GAB\nContrato'),
        ('205', 'Contrato'),
    ]
    items = []
    for document_id, text in records:
        item = MagicMock()
        item.inner_text = AsyncMock(return_value=f'Documento: {document_id}\n{text}')
        link = MagicMock()
        link.get_attribute = AsyncMock(return_value=f'md_epubli_visualizar.php?id={document_id}')
        item.query_selector = AsyncMock(return_value=None if document_id == '202' else link)
        items.append(item)
    known_detail = make_page()
    known_detail.content = AsyncMock(return_value='<p class="Centralizado_Timbre_Secretaria">CET/DBP</p><p>Contrato com referência à CET/GSU</p>')
    known_detail.close = AsyncMock()
    unknown_detail = make_page()
    unknown_detail.content = AsyncMock(return_value='<p>Contrato sem unidade identificável</p>')
    unknown_detail.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=[make_page(), known_detail, unknown_detail])
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    caplog.set_level('INFO')
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, return_value=items), \
         patch.object(scraper, '_save_partial_results'):
        with pytest.raises(IncompleteSearch) as caught:
            await scraper.scrape('09/11/2026', '09/11/2026', ['contrato'], use_ai=False)
    assert [(result.document_id, result.unit) for result in caught.value.results] == [('201', 'DBP')]
    assert caught.value.failures == ['09/11/2026']
    assert context.new_page.await_count == 3
    assert known_detail.goto.await_count == unknown_detail.goto.await_count == 1
    assert 'recuperadas=5 termos=4' in caplog.text
    assert "'DBP': 1" in caplog.text and "'DBE': 1" in caplog.text
    assert "'GSU': 1" in caplog.text and "'OUTRA': 1" in caplog.text and "'INDEFINIDA': 1" in caplog.text
    assert 'documento=205' in caplog.text and 'unidade=desconhecida motivo=revisão necessária' in caplog.text
    assert 'documento=204' in caplog.text and 'motivo=revisão de unidade não reconhecida' in caplog.text


@pytest.mark.asyncio
async def test_browser_fallback_to_chrome():
    scraper = DiarioScraper()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(side_effect=[Exception("Executable doesn't exist"), Exception('chrome launched')])
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('scraper_service.async_playwright', return_value=manager):
        with pytest.raises(Exception):
            await scraper.scrape('09/11/2026', '09/11/2026', [], use_ai=False)
    assert playwright.chromium.launch.await_args_list[1].kwargs['channel'] == 'chrome'
    assert playwright.chromium.launch.await_args_list[2].kwargs['channel'] == 'msedge'


@pytest.mark.asyncio
@pytest.mark.parametrize(('errors', 'channel'), [([Exception('missing')], 'chrome'), ([Exception('missing'), Exception('missing')], 'msedge')])
async def test_browser_fallback_succeeds(errors, channel):
    scraper = DiarioScraper()
    page = make_page()
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(side_effect=errors + [browser])
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, return_value=[]):
        assert await scraper.scrape('09/11/2026', '09/11/2026', [], use_ai=False) == []
    assert playwright.chromium.launch.await_args.kwargs['channel'] == channel


@pytest.mark.asyncio
async def test_all_days_failed_never_reports_success():
    scraper = DiarioScraper()
    page = make_page()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    callback = AsyncMock()
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, side_effect=SearchFailure('HTTP 403')):
        with pytest.raises(IncompleteSearch) as caught:
            await scraper.scrape('09/11/2026', '11/11/2026', [], status_callback=callback, use_ai=False)
    assert caught.value.results == []
    assert caught.value.failures == ['09/11/2026', '10/11/2026', '11/11/2026']
    assert not any('Concluído' in call.args[0] for call in callback.await_args_list)


def test_websocket_preserves_partial_results_and_reports_incomplete():
    from fastapi.testclient import TestClient
    from backend.main import app
    from models import SearchResult

    result = SearchResult(date='09/11/2026', term='contrato', unit='DBE', document_id='123',
                          summary='contrato', object_text='objeto', link_html='https://example.com', link_pdf='https://example.com')
    service = MagicMock()
    service.is_running = False
    service.run = AsyncMock(side_effect=IncompleteSearch([result], ['10/11/2026']))
    with patch.object(app.state, 'service', service, create=True):
        client = TestClient(app)
        with client.websocket_connect('/ws/logs') as socket:
            socket.send_json({'action': 'start_search', 'payload': {'start_date': '09/11/2026', 'end_date': '10/11/2026', 'terms': ['contrato']}})
            first = socket.receive_json()
            second = socket.receive_json()
    assert first['type'] == 'result' and first['data'][0]['unit'] == 'DBE'
    assert second['type'] == 'incomplete' and '10/11/2026' in second['message']


@pytest.mark.parametrize('transport', ['api', 'websocket'])
def test_read_failure_returns_prior_and_later_results(transport):
    from fastapi.testclient import TestClient
    from backend.main import app

    scraper = DiarioScraper()
    items = []
    detail_pages = []
    for document_id in ('123', '456'):
        item = MagicMock()
        item.inner_text = AsyncMock(return_value=f'Documento: {document_id}\nUnidade responsável: CET/DBP\nContrato')
        link = MagicMock()
        link.get_attribute = AsyncMock(return_value=f'md_epubli_visualizar.php?id={document_id}')
        item.query_selector = AsyncMock(return_value=link)
        items.append(item)
        detail = make_page()
        detail.goto = AsyncMock(return_value=SimpleNamespace(status=200))
        detail.content = AsyncMock(return_value='<p class="Centralizado_Timbre_Secretaria">CET/DBP</p><p>Contrato</p>')
        detail.close = AsyncMock()
        detail_pages.append(detail)
    broken = MagicMock()
    broken.inner_text = AsyncMock(side_effect=PlaywrightError('DOM detached'))
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=[make_page()] + detail_pages)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    service = MagicMock()
    service.is_running = False

    async def run(request, status_callback=None):
        return await scraper.scrape(request.start_date, request.end_date, request.terms, status_callback=status_callback, use_ai=False)

    service.run = run
    payload = {'start_date': '09/11/2026', 'end_date': '10/11/2026', 'terms': ['contrato']}
    with patch.object(app.state, 'service', service, create=True), \
         patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, side_effect=[[items[0]], [broken, items[1]]]), \
         patch.object(scraper, '_save_partial_results'):
        client = TestClient(app)
        if transport == 'api':
            response = client.post('/api/search', json=payload)
            assert response.status_code == 503
            data = response.json()
            assert data['failed_dates'] == ['10/11/2026']
            returned = data['results']
        else:
            with client.websocket_connect('/ws/logs') as socket:
                socket.send_json({'action': 'start_search', 'payload': payload})
                messages = []
                while not messages or messages[-1]['type'] != 'incomplete':
                    message = socket.receive_json()
                    assert message['type'] not in ('error', 'complete')
                    messages.append(message)
                assert '10/11/2026' in messages[-1]['message']
                returned = next(message['data'] for message in messages if message['type'] == 'result')
        assert [result['document_id'] for result in returned] == ['123', '456']


def test_websocket_shows_friendly_http_error():
    from fastapi.testclient import TestClient
    from backend.main import app
    service = MagicMock()
    service.is_running = False
    service.run = AsyncMock(side_effect=SearchFailure('HTTP 403 ao acessar o portal'))
    with patch.object(app.state, 'service', service, create=True):
        client = TestClient(app)
        with client.websocket_connect('/ws/logs') as socket:
            socket.send_json({'action': 'start_search', 'payload': {'start_date': '09/11/2026', 'end_date': '09/11/2026', 'terms': []}})
            response = socket.receive_json()
    assert response['type'] == 'error'
    assert 'HTTP 403' in response['message'] and 'acesso ao portal' in response['message']
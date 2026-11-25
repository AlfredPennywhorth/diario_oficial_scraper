import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from formatter import DiarioFormatter
from models import SearchResult
from scraper_service import (DiarioScraper, SearchFailure, _classify_unit, _format_contract_number,
                             _ListingSnapshot)


def header(text):
    return BeautifulSoup(f'<p class="Centralizado_Timbre_Secretaria">{text}</p>', 'html.parser')


def test_dbp_and_dbe_institutional_headers():
    # O portal publica o cabeçalho do DBP sem espaço entre "Departamento" e "de".
    assert _classify_unit('', header('Departamentode Aquisições de Bens e Serviços Padronizados')) == 'DBP'
    assert _classify_unit('', header('Departamento de Aquisições de Bens e Serviços Padronizados')) == 'DBP'
    assert _classify_unit('', header('Departamento de Aquisição de Bens e Serviços Especializados')) == 'DBE'
    assert _classify_unit('CET/DBP', header('Departamento de Aquisições de Bens e Serviços Padronizados')) == 'DBP'
    assert _classify_unit('CET/DBE', header('Departamento de Aquisições de Bens e Serviços Padronizados')) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('breadcrumb,expected', [
    ('CET > CET/DBP', 'DBP'), ('CET > CET/DBE', 'DBE'), ('CET > CET/GSU/DTC/PP', 'GSU'),
])
async def test_listing_breadcrumb_identifies_unit(breadcrumb, expected):
    element = MagicMock()
    element.inner_text = AsyncMock(return_value=f'{breadcrumb}\nProcesso: 7410.2026/1-1 - X\nDocumento: 168 - Homologação (NP)')
    element.query_selector = AsyncMock(return_value=None)
    item = await DiarioScraper()._read_listing_item(element, [])
    assert _classify_unit(item['unit_metadata']) == expected


@pytest.mark.parametrize('raw,year,expected', [
    ('212026', '2026', '021/2026'),
    ('4826', '2026', '048/2026'),
    ('48/26', '2026', '048/2026'),
    ('21/2026', '2026', '021/2026'),
    ('57', '2026', '057/2026'),
    ('57', None, '57'),
    ('4826', None, '4826'),
    ('4826', '', '4826'),
    ('7410.2026/0002060-3', '2026', '7410.2026/0002060-3'),
    ('PE 09/2026', '2026', 'PE 09/2026'),
    ('1234', '2026', '1234'),
    ('', '2026', ''),
    ('-', '2026', '-'),
])
def test_contract_number_format(raw, year, expected):
    assert _format_contract_number(raw, year) == expected


def listing_page(offsets, docs, status=200):
    page = MagicMock()
    state = {'n': 0}
    pages = [docs[i:i + 2] for i in range(0, len(docs), 2)]

    async def evaluate(script, *args):
        if 'navegar' in script:
            state['n'] = int(args[0]) // 10
            if state['n'] >= len(pages):
                raise RuntimeError('boom')
            return None
        return [{'text': f'Documento: {d}', 'href': f'visualizar?{d}'} for d in pages[state['n']]]

    async def content():
        links = ''.join(f"navegar('{o}')" for o in offsets)
        return links

    navigation = MagicMock()
    navigation.__aenter__ = AsyncMock(return_value=navigation)
    navigation.__aexit__ = AsyncMock(return_value=False)

    async def response():
        return SimpleNamespace(status=status)
    type(navigation).value = property(lambda self: response())
    page.expect_navigation.return_value = navigation
    page.evaluate = evaluate
    page.content = content
    page.wait_for_selector = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_all_listing_pages_are_collected():
    page = listing_page([10, 20], ['1', '2', '3', '4', '5'])
    items = await DiarioScraper()._collect_pages(page, '09/11/2026', [])
    assert [await i.inner_text() for i in items] == [f'Documento: {d}' for d in '12345']


@pytest.mark.asyncio
async def test_pagination_failure_keeps_collected_items():
    page = listing_page([10, 20, 30], ['1', '2', '3', '4'])
    with pytest.raises(SearchFailure) as exc:
        await DiarioScraper()._collect_pages(page, '09/11/2026', [])
    assert [await i.inner_text() for i in exc.value.partial] == [f'Documento: {d}' for d in '1234']


@pytest.mark.asyncio
async def test_snapshot_exposes_link():
    snap = _ListingSnapshot('Documento: 1', 'visualizar?1')
    link = await snap.query_selector('a')
    assert await link.get_attribute('href') == 'visualizar?1'


@pytest.mark.asyncio
async def test_same_process_documents_and_partial_pages_are_preserved():
    scraper = DiarioScraper()
    page = MagicMock()
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    docs = [('168409477', 'DBP', 'Extrato de Contrato'), ('168412339', 'DBP', 'Homologação Pregão'),
            ('168386581', 'DBE', 'Extrato de Contrato')]
    items = []
    details = []
    for doc_id, unit, kind in docs:
        items.append(_ListingSnapshot(
            f'CET > CET/{unit}\nProcesso: 7410.2026/0002060-3 - Pregão\nDocumento: {doc_id} - {kind}', f'visualizar?{doc_id}'))
        detail = MagicMock()
        detail.goto = AsyncMock(return_value=SimpleNamespace(status=200))
        detail.url = 'u'
        detail.content = AsyncMock(return_value='<p class="Centralizado_Timbre_Secretaria">Sem unidade</p>'
                                                f'<p>{kind} Contrato nº 48/26 Pregão</p>')
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
    failure = SearchFailure('página 2 falhou')
    failure.partial = items
    with patch('scraper_service.async_playwright', return_value=manager), \
         patch.object(scraper, '_open_search_page', new_callable=AsyncMock), \
         patch.object(scraper, '_fetch_day', new_callable=AsyncMock, side_effect=failure), \
         patch.object(scraper, '_save_partial_results'):
        with pytest.raises(Exception) as exc:
            await scraper.scrape('09/11/2026', '09/11/2026', ['contrato', 'pregão'], use_ai=False)
    results = exc.value.results
    assert exc.value.failures == ['09/11/2026']
    assert {(r.document_id, r.unit) for r in results} == {
        ('168409477', 'DBP'), ('168412339', 'DBP'), ('168386581', 'DBE')}
    assert {r.process_number for r in results if r.document_id != '168386581'} == {'7410.2026/0002060-3'}


def sliding_window_page(windows, docs_by_start):
    """Portal simulado cujos links de navegação formam uma janela móvel."""
    page = MagicMock()
    state = {'start': 0, 'calls': []}

    async def evaluate(script, *args):
        if 'navegar' in script:
            state['start'] = int(args[0])
            state['calls'].append(state['start'])
            return None
        return [{'text': f'Documento: {d}', 'href': f'visualizar?{d}'} for d in docs_by_start[state['start']]]

    async def content():
        return ''.join(f"navegar('{o}')" for o in windows[state['start']])

    navigation = MagicMock()
    navigation.__aenter__ = AsyncMock(return_value=navigation)
    navigation.__aexit__ = AsyncMock(return_value=False)

    async def response():
        return SimpleNamespace(status=200)
    type(navigation).value = property(lambda self: response())
    page.expect_navigation.return_value = navigation
    page.evaluate = evaluate
    page.content = content
    page.wait_for_selector = AsyncMock()
    return page, state


@pytest.mark.asyncio
async def test_sliding_window_links_are_followed_to_the_end():
    windows = {0: [10, 20], 10: [0, 20, 30], 20: [10, 30, 40], 30: [20, 40], 40: [20, 30]}
    docs = {0: ['1', '2'], 10: ['3', '4'], 20: ['5'], 30: ['6'], 40: ['7']}
    page, state = sliding_window_page(windows, docs)
    items = await DiarioScraper()._collect_pages(page, '09/11/2026', [])
    assert [await i.inner_text() for i in items] == [f'Documento: {d}' for d in '1234567']
    assert state['calls'] == [10, 20, 30, 40]


@pytest.mark.asyncio
async def test_repeated_page_stops_pagination_without_duplicates():
    windows = {0: [10], 10: [20], 20: [30], 30: [40], 40: []}
    docs = {0: ['1', '2'], 10: ['3', '4'], 20: ['3', '4'], 30: ['1'], 40: ['9']}
    page, state = sliding_window_page(windows, docs)
    items = await DiarioScraper()._collect_pages(page, '09/11/2026', [])
    assert [await i.inner_text() for i in items] == [f'Documento: {d}' for d in '1234']
    assert state['calls'] == [10, 20]


@pytest.mark.asyncio
async def test_looping_links_do_not_revisit_offsets():
    windows = {0: [10], 10: [0, 10]}
    docs = {0: ['1'], 10: ['2']}
    page, state = sliding_window_page(windows, docs)
    items = await DiarioScraper()._collect_pages(page, '09/11/2026', [])
    assert len(items) == 2 and state['calls'] == [10]


@pytest.mark.asyncio
async def test_same_process_documents_on_different_pages_are_kept():
    windows = {0: [10], 10: []}
    docs = {0: ['1'], 10: ['2']}
    page, _ = sliding_window_page(windows, docs)
    items = await DiarioScraper()._collect_pages(page, '09/11/2026', [])
    assert [await i.inner_text() for i in items] == ['Documento: 1', 'Documento: 2']


def _result(doc_type, **kw):
    base = dict(date='09/11/2026', term='Contrato', summary='x', object_text='y', link_html='#', link_pdf='#',
                doc_type=doc_type, contract_number='021/2026', parent_contract='001/2025', amendment_number='1')
    base.update(kw)
    return SearchResult(**base)


@pytest.mark.parametrize('method,doc_type', [('formatar_contrato', 'CONTRATO'), ('formatar_aditamento', 'ADITAMENTO')])
def test_html_signature_date_is_not_replaced_by_vigencia(method, doc_type):
    fmt = DiarioFormatter()
    both = getattr(fmt, method)(_result(doc_type, data_assinatura='15/10/2026', validity_start='20/10/2026', validity_end='20/10/2027'))
    assert 'Data da Assinatura:</span> <span class="val">15/10/2026' in both
    assert '20/10/2026 a 20/10/2027' in both
    missing = getattr(fmt, method)(_result(doc_type, data_assinatura='', validity_start='20/10/2026', validity_end='20/10/2027'))
    assert 'Data da Assinatura:</span> <span class="val">-<' in missing
    assert '20/10/2026 a 20/10/2027' in missing

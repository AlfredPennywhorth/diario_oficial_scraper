import re
import asyncio
import os
import sys
import logging
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from models import SearchResult
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configuração de Logs
logger = logging.getLogger(__name__)

class DiarioScraper:
    def __init__(self, debug=False):
        self.debug = debug  # If True, browser will be visible
        self.base_url = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=materias_pesquisar"
        self.orgao_id = "68"  # CET
        self.is_running = False # Controle de execução simultânea
        
        # Determine base directory for logs
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        self.logs_dir = os.path.join(base_dir, "logs")
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)
        
        self.partial_results_file = os.path.join(base_dir, "partial_results.json")
    
    def _save_partial_results(self, results):
        """Salva resultados parciais em JSON para resiliência"""
        try:
            temp_results = []
            for r in results:
                if hasattr(r, 'model_dump'):
                    temp_results.append(r.model_dump())
                elif hasattr(r, 'dict'):
                    temp_results.append(r.dict())
                else:
                    temp_results.append(r)

            with open(self.partial_results_file, "w", encoding="utf-8") as f:
                json.dump(temp_results, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar resultados parciais: {e}")
    
    def clean_link(self, link):
        if not link: return "#"
        if "chrome-extension" in link:
            parts = link.split("http")
            return "http" + parts[-1] if len(parts) > 1 else link
        if not link.startswith("http"):
            return f"https://diariooficial.prefeitura.sp.gov.br/{link}"
        return link

    def extract_details(self, soup, default_summary=""):
        """Método principal de extração (Refatorado)"""
        data = {
            "contratada": "-", "contractor": "-", "doc_fiscal": "-", "sintese": default_summary,
            "num_contrato": "-", "integra_id": "", "data_assinatura": "",
            "prazo": "", "tipo_prazo": "", "valor": "-", "modality": "-",
            "opening_date": "-", "tipo_doc": "OUTRO", "num_aditamento": "",
            "contrato_pai": "", "validade_inicio": "-", "validade_fim": "-"
        }
        
        # 1. Extração de campos estruturados (Tabelas/Labels)
        self._extract_structured_fields(soup, data)
        
        # Fallback Síntese caso os campos estruturados falhem
        if not data.get('sintese') or len(data.get('sintese', "")) < 10:
             div_main = soup.find('div', {'class': 'conteudoMateria'}) or soup.find('div', {'class': 'materia'})
             if div_main:
                 data['sintese'] = div_main.get_text(" ", strip=True)

        full_text = data.get('sintese', "")
        
        # 2. Extração via Regex (Smart Extraction)
        self._extract_modality(full_text, data)
        self._extract_dates(full_text, data)
        self._extract_contractor(full_text, data)
        self._extract_contract_info(full_text, data)
        self._extract_values(full_text, data)
        
        # 3. Classificação Final do Documento
        self._classify_document(full_text, data)

        # 4. Blindagem / Validações
        self._apply_shielding(data)

        return data

    def _extract_structured_fields(self, soup, data):
        mapa = {
            "Contratado(a)": "contractor", "Contratada": "contractor",
            "Licitante Vencedor": "contractor", 
            "CPF /CNPJ/ RNE": "doc_fiscal", "CNPJ": "doc_fiscal",
            "Síntese (Texto do Despacho)": "sintese", "Texto do despacho": "sintese",
            "Número do Contrato": "num_contrato", "Número": "num_contrato",
            "Íntegra do Contrato (Número do Documento SEI)": "integra_id",
            "Arquivo (Número do documento SEI)": "integra_id", 
            "Data da Assinatura": "data_assinatura",
            "Data da sessão": "opening_date", "Data de Abertura": "opening_date",
            "Modalidade": "modality",
            "Prazo do Contrato": "prazo", "Tipo do Prazo": "tipo_prazo",
            "Valor": "valor",
            "Objeto da licitação": "explicit_object", "Objeto": "explicit_object" 
        }

        for elem in soup.find_all(['span', 'div', 'strong', 'label', 'p', 'b']):
            txt = elem.get_text(strip=True)
            clean_txt = txt.rstrip(":")
            if txt in mapa or clean_txt in mapa:
                key = mapa.get(txt) or mapa.get(clean_txt)
                proximo = elem.find_next()
                while proximo and not proximo.get_text(strip=True):
                    proximo = proximo.find_next()
                if proximo:
                    valor = proximo.get_text(" ", strip=True)
                    if valor and valor != txt:
                        if not data.get(key) or len(valor) > len(data.get(key, "")):
                             data[key] = valor

    def _extract_modality(self, text, data):
        if data.get('modality') in ["-", "", None]:
            m_mod = re.search(r'(PREGÃO ELETRÔNICO|PREGÃO|CONCORRÊNCIA|TOMADA DE PREÇOS|CONVITE|LEILÃO|DIÁLOGO COMPETITIVO|INEXIGIBILIDADE|DISPENSA)', text, re.IGNORECASE)
            if m_mod:
                data['modality'] = m_mod.group(1).upper()
            elif "LICITAÇÃO" in text.upper():
                data['modality'] = "LICITAÇÃO"

    def _extract_contractor(self, text, data):
        if data.get('contractor') in ["-", "", None]:
             patterns = [
                 r'(?:Vencedor(?:es)?|Adjudicado para|Empresa|Contratada)\s*[:\.-]?\s*([A-Z\s\.,&LTDA\-]+?)(?:,?\s*CNPJ|CPF|$)',
                 r'Empresa\s+([A-Z\s\.,&LTDA\-]+?)\s+,',
             ]
             for p in patterns:
                 m_winner = re.search(p, text, re.IGNORECASE)
                 if m_winner:
                      candidate = m_winner.group(1).strip().rstrip(',.-')
                      if len(candidate) > 3 and "PROCESS" not in candidate.upper():
                           data['contractor'] = candidate
                           break
        
        # Fix concatenated CPFs (e.g. ...178-34074.999...)
        doc = data.get('doc_fiscal', '')
        if doc and len(doc) > 15:
            doc = re.sub(r'(-\d{2})(\d{3}\.)', r'\1, \2', doc)
            data['doc_fiscal'] = doc

    def _extract_contract_info(self, text, data):
        if data.get('num_contrato') in ["-", "", None]:
            m_id = re.search(r'(?:Pregão(?: Eletrônico)?|Contrato|Licitação|Carta Convite|Nota de Empenho|Termo de Fomento|Termo de Colaboração|Acordo de Coopera[çc][ãa]o|Termo de Doação|Termo de Comodato)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
            if m_id: 
                data['num_contrato'] = m_id.group(1)

        m_adit = re.search(r'(?:Termo de )?(Aditamento|Apostilamento)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
        if m_adit:
            data['tipo_doc'] = m_adit.group(1).upper()
            data['num_aditamento'] = m_adit.group(2)
            
            # Parent Contract identification
            m_pai = re.search(r'ao (?:Termo de )?(?:Contrato|Termo de Colaboração|Termo de Fomento|Ajuste)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
            if m_pai:
                data['contrato_pai'] = m_pai.group(1)

    def _extract_values(self, text, data):
        if data.get('valor') in ["-", "", None] or len(data.get('valor','')) < 10:
             if re.search(r'(sem impacto|sem ônus|sem o acréscimo)', text, re.IGNORECASE):
                data['valor'] = "Sem impacto"
             else:
                m_val_ext = re.search(r'(?:R\$\s?|Valor:?\s*)([\d\.,]+\s*\([^\)]+\))', text, re.IGNORECASE)
                if m_val_ext: 
                    data['valor'] = m_val_ext.group(1)
                else:
                    m_val = re.search(r'(?:R\$\s?|Valor:?\s*)([\d\.,]+)', text)
                    if m_val: data['valor'] = m_val.group(1)

    def _extract_dates(self, text, data):
        validade_inicio = data.get('data_assinatura', "")
        validade_fim = "-"
        
        def normalize_date(d):
            if not d: return ""
            return d.replace('.', '/')

        if validade_inicio: validade_inicio = normalize_date(validade_inicio)

        if not validade_inicio or len(validade_inicio) < 8:
            m_dt = re.search(r'Data da Assinatura:?\s*(\d{2}[/.]\d{2}[/.]\d{4})', text, re.IGNORECASE)
            if m_dt: validade_inicio = normalize_date(m_dt.group(1))
            
        patterns_vigencia = [
            r'Vigência:?\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*e\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
            r'compreendidos entre\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*e\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
            r'(?:vigência|período|prazo).*?de\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*a\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
        ]
        
        found_vig = False
        for p in patterns_vigencia:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                validade_inicio = normalize_date(m.group(1))
                validade_fim = normalize_date(m.group(2))
                found_vig = True
                break
        
        if not found_vig and validade_inicio and data.get('prazo'):
            try:
                dt_ini = datetime.strptime(validade_inicio, "%d/%m/%Y")
                prazo_val = int(re.sub(r'\D', '', data['prazo']))
                tipo = data['tipo_prazo'].lower() if data.get('tipo_prazo') else ''
                if not tipo:
                    if 'mês' in data['prazo'].lower() or 'meses' in data['prazo'].lower(): tipo = 'mês'
                    elif 'ano' in data['prazo'].lower(): tipo = 'ano'
                    elif 'dia' in data['prazo'].lower(): tipo = 'dia'

                if 'mês' in tipo or 'mes' in tipo:
                    months_total = dt_ini.month - 1 + prazo_val
                    y_add = months_total // 12
                    new_m = months_total % 12 + 1
                    try: dt_fim = dt_ini.replace(year=dt_ini.year + y_add, month=new_m)
                    except ValueError: dt_fim = dt_ini.replace(year=dt_ini.year + y_add, month=new_m, day=28)
                    validade_fim = dt_fim.strftime("%d/%m/%Y")
                elif 'dia' in tipo:
                    dt_fim = dt_ini + timedelta(days=prazo_val)
                    validade_fim = dt_fim.strftime("%d/%m/%Y")
                elif 'ano' in tipo:
                     try: dt_fim = dt_ini.replace(year=dt_ini.year + prazo_val)
                     except ValueError: dt_fim = dt_ini.replace(year=dt_ini.year + prazo_val, day=28)
                     validade_fim = dt_fim.strftime("%d/%m/%Y")
            except: pass

        data['validade_inicio'] = validade_inicio
        data['validade_fim'] = validade_fim

    def _classify_document(self, text, data):
        if data.get('tipo_doc') in ['ADITAMENTO', 'APOSTILAMENTO']:
            return

        if data.get('modality') == 'DISPENSA' or "DISPENSA" in data.get('modality', '').upper():
             data['tipo_doc'] = 'PEDIDO_COMPRA'
        elif re.search(r'(?:Formalização|Termo|Extrato) d[oa] Contrato', text, re.IGNORECASE) or \
             re.search(r'Contrato\s*(?:nº|n°)\s*[\d]+', text, re.IGNORECASE):
             data['tipo_doc'] = 'CONTRATO'
        elif re.search(r'(?:DESPACHO DE ADJUDICAÇÃO|ADJUDICO|DESPACHO DE HOMOLOGAÇÃO|HOMOLOGO|AUTORIZO a contratação)', text, re.IGNORECASE):
             data['tipo_doc'] = 'HOMOLOGACAO'
        elif re.search(r'Termo de (Fomento|Colaboração|Doação|Comodato)', text, re.IGNORECASE):
             data['tipo_doc'] = 'PARCERIA' # Simplified grouping
        elif re.search(r'Acordo de Coopera[çc][ãa]o', text, re.IGNORECASE):
             data['tipo_doc'] = 'ACORDO_COOPERACAO'
        elif re.search(r'(ESCLARECIMENTO|QUESTIONAMENTO|DESPACHO DE IMPUGNAÇ|IMPUGNAÇ[ÃA]O|NOTIFICAÇÃO|ATA DE ABERTURA)', text, re.IGNORECASE):
             data['tipo_doc'] = 'DIVERSOS'
        else:
             data['tipo_doc'] = 'OUTRO'

    def _apply_shielding(self, data):
        """Blindagem: Alertas sobre campos críticos ausentes"""
        criticos = [
            ("contractor", "Contratada/Vencedora não identificada"),
            ("valor", "Valor não identificado"),
            ("num_contrato", "Número do contrato/pregão não identificado"),
            ("validade_inicio", "Data de início/assinatura não identificada")
        ]
        for campo, msg in criticos:
            valor = data.get(campo)
            if not valor or valor in ["-", "", None]:
                logger.warning(f"[BLINDAGEM] {msg}")

    async def enrich_with_ai(self, details, item_id, enabled=True):
        """Isolamento da IA: Execução opcional e protegida"""
        if not enabled:
            return
            
        try:
            from ai_extractor import is_ai_enabled, extract_with_gemini
            
            if not is_ai_enabled():
                return
                
            logger.info(f"Enriquecendo documento {item_id} com IA...")
            # Timeout controlado de 30s para não travar o scraping
            ai_data = await asyncio.wait_for(extract_with_gemini(details['sintese']), timeout=30.0)
            
            if ai_data:
                logger.debug(f"IA retornou dados para {item_id}")
                mapeamento = {
                    'contractor': 'contractor',
                    'company_doc': 'doc_fiscal',
                    'object_text': 'explicit_object',
                    'validity_start': 'validade_inicio',
                    'validity_end': 'validade_fim',
                    'value': 'valor',
                    'contract_number': 'num_contrato'
                }
                for ai_key, dev_key in mapeamento.items():
                    if ai_data.get(ai_key) and ai_data[ai_key] != '-':
                        details[dev_key] = ai_data[ai_key]
                
                if ai_data.get('modality'):
                    details['modality'] = ai_data['modality'].upper()
                    if any(x in details['modality'] for x in ["DIVERSOS", "ATA", "JULGAMENTO"]):
                        details['tipo_doc'] = 'DIVERSOS'
                    elif "ACORDO DE COOPERA" in details['modality']:
                         details['tipo_doc'] = 'ACORDO_COOPERACAO'
        except Exception as e:
            logger.error(f"Falha na IA para doc {item_id}: {e}")

    def extract_object(self, text):
        if not text: return "VERIFICAR NA ÍNTEGRA"
        txt = re.sub(r'\s+', ' ', text)
        
        # 0. Priority: Aditamento specific smart capture (Prorrogação)
        if "PRORROG" in txt.upper() or "ADITAMENTO" in txt.upper():
             m_prorrog = re.search(r'(?:fica|para)\s+prorrogad[oa].*?(?:meses|dias|anos|vigência)', txt, re.IGNORECASE)
             if m_prorrog:
                 start, end = m_prorrog.span()
                 sub = txt[start:end+20]
                 return sub.strip('.,; ')

        # 1. Clean explicit OBJETO
        match_obj = re.search(r'(?:OBJETO da licitação|OBJETO|ASSUNTO):?\s*(.*?)(?=\s*(?:JULGAMENTO|REGIME|MODALIDADE|MODO|Valor|Prazo|Local|Data|Edital|Sessão|II\s?-|II\.|\.|$))', txt, re.IGNORECASE)
        if match_obj:
            val = match_obj.group(1).strip()
            if len(val) < 300: return val.rstrip('.')

        # 2. Look for action verbs at start
        termos_parada = r'(?:II\s?-|II\.|2\.|A CET poderá|Nesta hipótese|EXPEDIENTE Nº|Data d[ae]|Edital|Sessão|Realização|com fundamento|nos termos|por inexigibilidade|em conformidade|Formalizado em|Disponível no|Publicado no|$)'
        padrao_acao = r'(?:para [oa]s?|visando [oa]s?|objetivando|referente [àao]s?)\s+(.*?)(?=\s*' + termos_parada + ')'
        match = re.search(padrao_acao, txt, re.IGNORECASE)
        if match:
             return match.group(0).strip()

        # 3. Text inside quotes
        match_quote = re.search(r'(?:que trata\s*(?:d[eao])?|objeto:?)\s*["“\'](.*?)["”\']', txt, re.IGNORECASE)
        if match_quote:
             return match_quote.group(1).strip()

        # 4. Text WITHOUT quotes
        match_no_quote = re.search(r'(?:que trata\s*(?:d[eao])?|objeto:?)\s*(?!["“\'])(.*?)(?=\.|,|;|-|Modalidade|Valor|Data|$)', txt, re.IGNORECASE)
        if match_no_quote:
             val = match_no_quote.group(1).strip()
             if len(val) > 3:
                return val

        return "Verificar objeto na íntegra."

    async def scrape(self, start_date: str | datetime, end_date: str | datetime, terms: list, status_callback=None, use_ai=True):
        if self.is_running:
            raise Exception("O robô já está em execução. Aguarde a finalização.")
        
        self.is_running = True
        start_time = datetime.now()
        results = []
        
        try:
            if isinstance(start_date, str):
                d1 = datetime.strptime(start_date, "%d/%m/%Y")
            else:
                d1 = start_date
                
            if isinstance(end_date, str):
                d2 = datetime.strptime(end_date, "%d/%m/%Y")
            else:
                d2 = end_date
            
            if d1 > d2: d1, d2 = d2, d1
            
            delta = d2 - d1
            date_list = [(d1 + timedelta(days=i)).strftime("%d/%m/%Y") for i in range(delta.days + 1)]

            logger.info(f"Iniciando navegador (debug={self.debug})...")
            
            async with async_playwright() as p:
                browser = None
                launch_options = {"headless": not self.debug, "timeout": 30000}
                
                try:
                    browser = await p.chromium.launch(**launch_options)
                except:
                    try:
                        browser = await p.chromium.launch(channel="chrome", **launch_options)
                    except:
                        browser = await p.chromium.launch(channel="msedge", **launch_options)
                
                if not browser: raise Exception("Falha crítica ao iniciar navegador.")

                context = await browser.new_context(user_agent="Mozilla/5.0 DiárioOficialScraper/1.0")
                context.set_default_navigation_timeout(30000) 
                page = await context.new_page()
                
                await page.goto(self.base_url, timeout=30000)

                total_days = len(date_list)
                for day_idx, current_date in enumerate(date_list):
                    progress_msg = f"Processando dia {day_idx+1} de {total_days}: {current_date}"
                    if status_callback: await status_callback(progress_msg)

                    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
                    async def fetch_results_with_retry():
                        try: _ = page.url
                        except: await page.goto(self.base_url, timeout=30000)

                        js_script = f"""
                            var f = document.createElement('form'); f.action='md_epubli_controlador.php?acao=materias_pesquisar'; f.method='POST';
                            var i1=document.createElement('input');i1.name='hdnDataPublicacao';i1.value='{current_date}';f.appendChild(i1);
                            var i2=document.createElement('input');i2.name='hdnOrgaoFiltro';i2.value='{self.orgao_id}';f.appendChild(i2);
                            var i3=document.createElement('input');i3.name='hdnModoPesquisa';i3.value='DATA';f.appendChild(i3);
                            var i4=document.createElement('input');i4.name='hdnVisualizacao';i4.value='L';f.appendChild(i4);
                            document.body.appendChild(f); f.submit();
                        """
                        try:
                            async with page.expect_navigation(timeout=30000):
                                await page.evaluate(js_script)
                        except: pass

                        try:
                            await page.wait_for_selector('div.dadosDocumento', state="attached", timeout=3000)
                            return await page.query_selector_all('div.dadosDocumento')
                        except:
                             content = await page.content()
                             if any(p in content for p in ["Nenhum registro encontrado", "Não foram encontrados registros"]):
                                 return []
                             await page.wait_for_selector('div.dadosDocumento', state="attached", timeout=10000)
                             return await page.query_selector_all('div.dadosDocumento')

                    elementos = []
                    try:
                        elementos = await fetch_results_with_retry()
                    except:
                        logger.error(f"Falha ao buscar {current_date}")
                        continue

                    if not elementos: continue

                    links_to_visit = []
                    for el in elementos:
                        txt = await el.inner_text()
                        if "GSU" in txt.upper(): continue
                        
                        matches_term = False
                        matched_term_name = "Geral"
                        if not terms: matches_term = True
                        else:
                            for t in terms:
                                if t.lower() in txt.lower():
                                    matches_term = True
                                    matched_term_name = t
                                    break
                        
                        if matches_term:
                            m_proc = re.search(r'Processo:?\s?([\d\./-]+)', txt)
                            proc = m_proc.group(1) if m_proc else "N/A"
                            m_id = re.search(r'Documento:\s*(\d+)', txt)
                            doc_id = m_id.group(1) if m_id else "S/N"
                            link_el = await el.query_selector('a[href*="visualizar"]')
                            if link_el:
                                href = await link_el.get_attribute('href')
                                links_to_visit.append({"url": self.clean_link(href), "doc_id": doc_id, "processo": proc, "term": matched_term_name})

                    if not links_to_visit: continue

                    sem = asyncio.Semaphore(5)
                    total_items = len(links_to_visit)
                    day_processed_count = 0

                    async def fetch_and_extract(item):
                        nonlocal day_processed_count
                        async with sem:
                            @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=5))
                            async def fetch_item_details():
                                page_detail = await context.new_page()
                                try:
                                    await page_detail.goto(item['url'], timeout=30000)
                                    return await page_detail.content()
                                finally: await page_detail.close()

                            try:
                                content = await fetch_item_details()
                                soup = BeautifulSoup(content, 'html.parser')
                                details = self.extract_details(soup)
                                await self.enrich_with_ai(details, item['doc_id'], enabled=use_ai)
                                
                                link_pdf = item['url']
                                if details.get('integra_id'):
                                     a_precise = soup.find('a', string=lambda t: t and details['integra_id'] in t)
                                     if a_precise and a_precise.has_attr('href'):
                                         link_pdf = self.clean_link(a_precise['href'])
                                     else:
                                         for a in soup.find_all('a', href=True):
                                            if details['integra_id'] in a['href']:
                                                link_pdf = self.clean_link(a['href'])
                                                break
                                
                                obj_text = details.get('explicit_object')
                                if not obj_text or len(obj_text) <= 5: obj_text = self.extract_object(details['sintese'])
                                
                                res = SearchResult(
                                    date=current_date, term=item['term'], process_number=item['processo'],
                                    document_id=item['doc_id'], summary=details['sintese'][:200] + "...",
                                    object_text=obj_text, contractor=details['contractor'], company_doc=details['doc_fiscal'],
                                    contract_number=details['num_contrato'], validity_start=details['validade_inicio'],
                                    validity_end=details['validade_fim'], value=details['valor'], link_html=item['url'],
                                    link_pdf=link_pdf, modality=details.get('modality', '-'), opening_date=details.get('opening_date', '-'),
                                    amendment_number=details.get('num_aditamento', ''), parent_contract=details.get('contrato_pai', ''),
                                    doc_type=details.get('tipo_doc', 'OUTRO')
                                )
                                day_processed_count += 1
                                if status_callback: await status_callback(f"Extraindo item {day_processed_count} de {total_items} ({current_date})")
                                return res
                            except Exception as e:
                                logger.error(f"Erro no item {item['doc_id']}: {e}")
                                day_processed_count += 1
                                return None

                    day_tasks = [fetch_and_extract(it) for it in links_to_visit]
                    day_results = await asyncio.gather(*day_tasks)
                    results.extend([r for r in day_results if r])
                    self._save_partial_results(results)
                
                await browser.close()
            
            elapsed = datetime.now() - start_time
            finish_msg = f"Concluído em {elapsed}. Total: {len(results)}"
            logger.info(finish_msg)
            if status_callback: await status_callback(finish_msg)
            return results

        except Exception as e:
            logger.error(f"Erro fatal no scraping: {e}")
            raise
        finally:
            self.is_running = False

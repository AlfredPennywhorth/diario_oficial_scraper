import re
import asyncio
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from models import SearchResult
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import sys

class DiarioScraper:
    def __init__(self, debug=False):
        self.debug = debug  # If True, browser will be visible
        self.base_url = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=materias_pesquisar"
        self.orgao_id = "68"  # CET
        
        # Determine base directory for logs
        if getattr(sys, 'frozen', False):
            # If frozen (exe), save logs next to the executable
            base_dir = os.path.dirname(sys.executable)
        else:
            # If script, save in backend/logs
            base_dir = os.path.dirname(os.path.abspath(__file__))

        # Ensure logs directory exists for screenshots
        self.logs_dir = os.path.join(base_dir, "logs")
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)
    
    def _log(self, msg):
        """Log with timestamp"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {msg}", flush=True)
        except Exception:
            pass # Ignore logging errors
    
    def clean_link(self, link):
        if not link: return "#"
        if "chrome-extension" in link:
            parts = link.split("http")
            return "http" + parts[-1] if len(parts) > 1 else link
        if not link.startswith("http"):
            return f"https://diariooficial.prefeitura.sp.gov.br/{link}"
        return link

    def extract_details(self, soup, default_summary=""):
        data = {
            "contratada": "-", "contractor": "-", "doc_fiscal": "-", "sintese": default_summary,
            "num_contrato": "-", "integra_id": "", "data_assinatura": "",
            "prazo": "", "tipo_prazo": "", "valor": "-"
        }
        
        # 1. Extract from structured fields (if available)
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
        
        # Fallback Síntese
        if not data.get('sintese') or len(data.get('sintese', "")) < 10:
             div_main = soup.find('div', {'class': 'conteudoMateria'}) or soup.find('div', {'class': 'materia'})
             if div_main:
                 data['sintese'] = div_main.get_text(" ", strip=True)

        full_text = data.get('sintese', "")
        
        # 2. Smart Extraction
        
        # Modality
        if data.get('modality') in ["-", "", None]:
            m_mod = re.search(r'(PREGÃO ELETRÔNICO|PREGÃO|CONCORRÊNCIA|TOMADA DE PREÇOS|CONVITE|LEILÃO|DIÁLOGO COMPETITIVO|INEXIGIBILIDADE|DISPENSA)', full_text, re.IGNORECASE)
            if m_mod:
                data['modality'] = m_mod.group(1).upper()
            elif "LICITAÇÃO" in full_text.upper():
                data['modality'] = "LICITAÇÃO"

        # Opening Date
        if data.get('opening_date') in ["-", "", None]:
             m_open = re.search(r'(?:abertura|sessão).*?(\d{2}/\d{2}/\d{4})', full_text, re.IGNORECASE)
             if m_open:
                 data['opening_date'] = m_open.group(1)

        # Contractor Logic
        if data.get('contractor') in ["-", "", None]:
             # Try stricter patterns first
             patterns = [
                 r'(?:Vencedor(?:es)?|Adjudicado para|Empresa|Contratada)\s*[:\.-]?\s*([A-Z\s\.,&LTDA\-]+?)(?:,?\s*CNPJ|CPF|$)',
                 r'Empresa\s+([A-Z\s\.,&LTDA\-]+?)\s+,',
             ]
             for p in patterns:
                 m_winner = re.search(p, full_text, re.IGNORECASE)
                 if m_winner:
                      candidate = m_winner.group(1).strip().rstrip(',.-')
                      if len(candidate) > 3 and "PROCESS" not in candidate.upper():
                           data['contractor'] = candidate
                           break
             
             # if not data.get('contractor'):
             #    data['contractor'] = "EM PROCESSO"

        # Publication Number (Pregão/Contrato IDs)
        # Priority: explicit contract number -> finding patterns like "Pregão Eletrônico nº 01/25"
        if data.get('num_contrato') in ["-", "", None]:
            # Look for Pregão/Contrato specific IDs
            m_id = re.search(r'(?:Pregão(?: Eletrônico)?|Contrato|Licitação|Carta Convite|Nota de Empenho|Termo de Fomento|Termo de Colaboração|Acordo de Coopera[çc][ãa]o|Termo de Doação|Termo de Comodato)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', full_text, re.IGNORECASE)
            if m_id: 
                data['num_contrato'] = m_id.group(1)

        # Aditamento / Contrato Specifics / Apostilamento
        # Try to extract Aditamento/Apostilamento Number
        m_adit = re.search(r'(?:Termo de )?(Aditamento|Apostilamento)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', full_text, re.IGNORECASE)
        if m_adit:
            tipo_encontrado = m_adit.group(1).upper()
            data['tipo_doc'] = tipo_encontrado # ADITAMENTO ou APOSTILAMENTO
            data['num_aditamento'] = m_adit.group(2)
        else:
            # Check for other specific types
            if re.search(r'Termo de Fomento', full_text, re.IGNORECASE):
                data['tipo_doc'] = 'PARCERIA'
            elif re.search(r'Termo de Colaboração', full_text, re.IGNORECASE):
                data['tipo_doc'] = 'PARCERIA'
            elif re.search(r'Acordo de Coopera[çc][ãa]o', full_text, re.IGNORECASE):
                 # Set as a separate type to easily format it in the frontend
                 data['tipo_doc'] = 'ACORDO_COOPERACAO'
                 
                 # Try to extract the number of the "Acordo de Cooperação" to contract_number
                 m_acordo = re.search(r'Acordo de Coopera[çc][ãa]o\s*(?:n(?:[º°]|um)[.\s]*)?([\d\.]+(?:/[\d]{2,4})?)', full_text, re.IGNORECASE)
                 if m_acordo:
                     data['num_contrato'] = m_acordo.group(1)
            elif re.search(r'Termo de Doação', full_text, re.IGNORECASE):
                 data['tipo_doc'] = 'DOACAO'
            elif re.search(r'Termo de Comodato', full_text, re.IGNORECASE):
                 data['tipo_doc'] = 'COMODATO'
            elif re.search(r'Nota de Empenho', full_text, re.IGNORECASE):
                 data['tipo_doc'] = 'EMPENHO'
            # Irrelevant / Diversos
            # Irrelevant / Diversos
            elif re.search(r'(ESCLARECIMENTO|QUESTIONAMENTO|DESPACHO DE IMPUGNAÇ|IMPUGNAÇ[ÃA]O AO EDITAL)', full_text, re.IGNORECASE):
                 data['tipo_doc'] = 'DIVERSOS'
            else:
                # Check for CONTRATO
                # Strong indicators: "Contrato nº" (with number), "Formalização do Contrato", "Termo de Contrato"
                is_contract = False
                # 1. Matches "Formalização do Contrato", "Termo de Contrato", "Extrato de Contrato"
                if re.search(r'(?:Formalização|Termo|Extrato) d[oa] Contrato', full_text, re.IGNORECASE):
                     is_contract = True
                # 2. Matches "Contrato nº 123" (must have number)
                elif re.search(r'Contrato\s*(?:nº|n°)\s*[\d]+', full_text, re.IGNORECASE):
                     is_contract = True
                
                if is_contract:
                    data['tipo_doc'] = 'CONTRATO'
                else:
                    data['tipo_doc'] = 'OUTRO'

        # Parent Contract for Aditamento/Apostilamento -> "ao Contrato nº 31/16"
        if data['tipo_doc'] in ['ADITAMENTO', 'APOSTILAMENTO']:
            m_pai = re.search(r'ao (?:Termo de )?(?:Contrato|Termo de Colaboração|Termo de Fomento|Ajuste)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', full_text, re.IGNORECASE)
            if m_pai:
                data['contrato_pai'] = m_pai.group(1)

        # Value with full text
        # User wants "R$ 313.856,40 (trezentos...)"
        if data.get('valor') in ["-", "", None] or len(data.get('valor','')) < 10:
             if re.search(r'(sem impacto|sem ônus|sem o acréscimo)', full_text, re.IGNORECASE):
                data['valor'] = "Sem impacto"
             else:
                # Capture regex with (...) for extended text
                m_val_ext = re.search(r'(?:R\$\s?|Valor:?\s*)([\d\.,]+\s*\([^\)]+\))', full_text, re.IGNORECASE)
                if m_val_ext: 
                    data['valor'] = m_val_ext.group(1)
                else:
                    # Simple value fallback
                    m_val = re.search(r'(?:R\$\s?|Valor:?\s*)([\d\.,]+)', full_text)
                    if m_val: data['valor'] = m_val.group(1)

        # Dates & Validity
        # ... (rest of method unchanged) ...
        # (skipping extensive unchanged lines for brevity in replace tool if possible, but for replace_file_content we should be careful)
        # However, we need to jump to where SearchResult is created.
        
        # ... (skipping to line 492) ...
        
        # NOTE: replace_file_content works on contiguous blocks. I will do this in two steps or a larger block if needed.
        # It's better to do two REPLACE calls or one MULTI_REPLACE. I will use MULTI_REPLACE.
        pass # Placeholder for tool usage logic


        # Dates & Validity
        # User wants "Vigência: 01/02/2026 e 01/02/2027" or separate Start/End
        validade_inicio = data.get('data_assinatura', "")
        validade_fim = "-"
        
        # Helper to normalize dates (dot to slash)
        def normalize_date(d):
            if not d: return ""
            return d.replace('.', '/')

        if validade_inicio: validade_inicio = normalize_date(validade_inicio)

        # Try to find signature date in text if missing
        if not validade_inicio or len(validade_inicio) < 8:
            m_dt = re.search(r'Data da Assinatura:?\s*(\d{2}[/.]\d{2}[/.]\d{4})', full_text, re.IGNORECASE)
            if m_dt: validade_inicio = normalize_date(m_dt.group(1))
            
        # Specific "Vigência" extraction for user format
        # 1. "Vigência: 01/02/2026 e 01/02/2027"
        # 2. "compreendidos entre 01.02.2026 e 01.02.2027"
        
        patterns_vigencia = [
            r'Vigência:?\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*e\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
            r'compreendidos entre\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*e\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
            r'(?:vigência|período|prazo).*?de\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*a\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
        ]
        
        found_vig = False
        for p in patterns_vigencia:
            m = re.search(p, full_text, re.IGNORECASE)
            if m:
                validade_inicio = normalize_date(m.group(1))
                validade_fim = normalize_date(m.group(2))
                found_vig = True
                break
        
        # Calculate end date if we have start date and duration and no specific end date found
        if not found_vig and validade_inicio and data.get('prazo'):
            try:
                dt_ini = datetime.strptime(validade_inicio, "%d/%m/%Y")
                prazo_val = int(re.sub(r'\D', '', data['prazo']))
                tipo = data['tipo_prazo'].lower() if data.get('tipo_prazo') else ''
                
                # If tipo is empty, try to guess from prazo string itself
                if not tipo:
                    if 'mês' in data['prazo'].lower() or 'meses' in data['prazo'].lower(): tipo = 'mês'
                    elif 'ano' in data['prazo'].lower(): tipo = 'ano'
                    elif 'dia' in data['prazo'].lower(): tipo = 'dia'

                if 'mês' in tipo or 'mes' in tipo:
                    # Add months roughly: 30 days per month to avoid dateutil, or standard math:
                    months_total = dt_ini.month - 1 + prazo_val
                    y_add = months_total // 12
                    new_m = months_total % 12 + 1
                    try:
                        dt_fim = dt_ini.replace(year=dt_ini.year + y_add, month=new_m)
                    except ValueError:
                        # Handle e.g., Feb 29 to Feb 28
                        dt_fim = dt_ini.replace(year=dt_ini.year + y_add, month=new_m, day=28)
                    validade_fim = dt_fim.strftime("%d/%m/%Y")
                elif 'dia' in tipo:
                    dt_fim = dt_ini + timedelta(days=prazo_val)
                    validade_fim = dt_fim.strftime("%d/%m/%Y")
                elif 'ano' in tipo:
                     try:
                         dt_fim = dt_ini.replace(year=dt_ini.year + prazo_val)
                     except ValueError:
                         dt_fim = dt_ini.replace(year=dt_ini.year + prazo_val, day=28) # Leap year safe
                     validade_fim = dt_fim.strftime("%d/%m/%Y")
            except:
                pass 

        # Another heuristic for calculating dates directly from text "prazo de X [meses|anos]" if not caught above
        if not found_vig and validade_fim == "-" and validade_inicio:
            m_prazo_inline = re.search(r'prazo\s*(?:de\s*(?:vigência\s*)?)?(\d+)\s*(meses|anos?)', full_text, re.IGNORECASE)
            if m_prazo_inline:
                try:
                    val = int(m_prazo_inline.group(1))
                    tipo = m_prazo_inline.group(2).lower()
                    dt_ini = datetime.strptime(validade_inicio, "%d/%m/%Y")
                    if 'ano' in tipo:
                        try: dt_fim = dt_ini.replace(year=dt_ini.year + val)
                        except ValueError: dt_fim = dt_ini.replace(year=dt_ini.year + val, day=28)
                        validade_fim = dt_fim.strftime("%d/%m/%Y")
                    elif 'mes' in tipo:
                        months_total = dt_ini.month - 1 + val
                        try: dt_fim = dt_ini.replace(year=dt_ini.year + months_total//12, month=months_total%12+1)
                        except ValueError: dt_fim = dt_ini.replace(year=dt_ini.year + months_total//12, month=months_total%12+1, day=28)
                        validade_fim = dt_fim.strftime("%d/%m/%Y")
                except: pass

        data['validade_inicio'] = validade_inicio
        data['validade_fim'] = validade_fim

        # Fix concatenated CPFs (e.g. ...178-34074.999...)
        # Pattern: ends with -XX immediately followed by XXX.
        doc = data.get('doc_fiscal', '')
        if doc and len(doc) > 15:
            # Insert ", " between -XX and XXX.
            # Example: 942.204.178-34074.999.568-81 -> 942.204.178-34, 074.999.568-81
            doc = re.sub(r'(-\d{2})(\d{3}\.)', r'\1, \2', doc)
            data['doc_fiscal'] = doc
        
        # --- Type Classification Improvements ---
        
        # 1. PEDIDO DE COMPRA (Dispensa de Licitação)
        # Often these look like contracts but have "Modalidade: DISPENSA"
        if data.get('modality') == 'DISPENSA' or "DISPENSA" in data.get('modality', '').upper():
            # If it looks like a contract/compra
             data['tipo_doc'] = 'PEDIDO_COMPRA'

        # 2. DESTAQUE: Homologação / Adjudicação / Autorizo contratação
        # High value information: Winner + CNPJ
        destaque_keywords = r'(?:DESPACHO DE ADJUDICAÇÃO|ADJUDICO|DESPACHO DE HOMOLOGAÇÃO|HOMOLOGO|AUTORIZO a contratação)'
        if re.search(destaque_keywords, full_text, re.IGNORECASE):
             data['tipo_doc'] = 'HOMOLOGACAO'
             # Ensure we really try to get the winner for these
             if data.get('contractor') in ["-", "", None]:
                  # Try finding winner again closer to "Vencedor" or "Empresa"
                  m_win = re.search(r'(?:Empresa|Vencedor|Adjudicado para)[:\s]*([A-Z\s\.,&LTDA\-]+?)(?:,?\s*CNPJ|CPF|$)', full_text, re.IGNORECASE)
                  if m_win:
                      data['contractor'] = m_win.group(1).strip().strip('-,.')

        # 3. OUTROS (DIVERSOS) updates
        msg_diversos = r'(?:ESCLARECIMENTO|QUESTIONAMENTO|DESPACHO DE IMPUGNAÇ|IMPUGNAÇ[ÃA]O AO EDITAL|NOTIFICAÇÃO DE APLICAÇÃO DE PENALIDADE|Notificação de Penalidade|Aplicação de Penalidade|EXTRATO DA ATA DE ABERTURA|ATA DE ABERTURA|TERMO DE JULGAMENTO|APLICO a penalidade|DEMONSTRATIVO DAS COMPRAS)'
        if re.search(msg_diversos, full_text, re.IGNORECASE):
             data['tipo_doc'] = 'DIVERSOS'

        return data

    def extract_object(self, text):
        if not text: return "VERIFICAR NA ÍNTEGRA"
        txt = re.sub(r'\s+', ' ', text)
        
        # 0. Priority: Aditamento specific smart capture (Prorrogação)
        # Capture strings like "prorroga o prazo por 12 meses" or "fica prorrogado..."
        # We do this FIRST because often Aditamentos mention the original object ("referente a...") which distracts the regex.
        if "PRORROG" in txt.upper() or "ADITAMENTO" in txt.upper():
             m_prorrog = re.search(r'(?:fica|para)\s+prorrogad[oa].*?(?:meses|dias|anos|vigência)', txt, re.IGNORECASE)
             if m_prorrog:
                 # Try to grab a bit more context
                 start, end = m_prorrog.span()
                 sub = txt[start:end+20] # a bit more padding
                 return sub.strip('.,; ')

        # 1. Clean explicit OBJETO
        # Look for "OBJETO:", but stop at common next field headers.
        # We check "OBJETO da licitação" first so "OBJETO" doesn't match just the first word.
        match_obj = re.search(r'(?:OBJETO da licitação|OBJETO|ASSUNTO):?\s*(.*?)(?=\s*(?:JULGAMENTO|REGIME|MODALIDADE|MODO|Valor|Prazo|Local|Data|Edital|Sessão|II\s?-|II\.|\.|$))', txt, re.IGNORECASE)
        if match_obj:
            val = match_obj.group(1).strip()
            # If nice and short, return. If too long, maybe refine.
            if len(val) < 300: return val.rstrip('.')

        # 2. Look for action verbs at start (common in despachos)
        termos_parada = r'(?:II\s?-|II\.|2\.|A CET poderá|Nesta hipótese|EXPEDIENTE Nº|Data d[ae]|Edital|Sessão|Realização|com fundamento|nos termos|por inexigibilidade|em conformidade|Formalizado em|Disponível no|Publicado no|$)'
        padrao_acao = r'(?:para [oa]s?|visando [oa]s?|objetivando|referente [àao]s?)\s+(.*?)(?=\s*' + termos_parada + ')'
        match = re.search(padrao_acao, txt, re.IGNORECASE)
        if match:
             return match.group(0).strip() # Return full phrase "para ..."

        if match:
             return match.group(0).strip() # Return full phrase "para ..."

        # 3. New logic: Text inside quotes after "que trata"
        # Note: 'txt' has already effectively removed newlines (replaced with space)
        # Matches "que trata de", "que trata da", "que trata do" or just "que trata" followed by quotes
        match_quote = re.search(r'(?:que trata\s*(?:d[eao])?|objeto:?)\s*["“\'](.*?)["”\']', txt, re.IGNORECASE)
        if match_quote:
             return match_quote.group(1).strip()

        # 4. New logic: Text WITHOUT quotes after "que trata"
        # Match "que trata de X" until punctuation or next keyword
        # "que trata de AQUISICAO ... ."
        match_no_quote = re.search(r'(?:que trata\s*(?:d[eao])?|objeto:?)\s*(?!["“\'])(.*?)(?=\.|,|;|-|Modalidade|Valor|Data|$)', txt, re.IGNORECASE)
        if match_no_quote:
             val = match_no_quote.group(1).strip()
             if len(val) > 3 and len(val) < 500: # Sanity check
                return val

        return "Verificar objeto na íntegra."



    async def scrape(self, start_date: str | datetime, end_date: str | datetime, terms: list, status_callback=None):
        start_time = datetime.now()
        results = []
        
        # Flexibilidad para recibir string o datetime
        if isinstance(start_date, str):
            d1 = datetime.strptime(start_date, "%d/%m/%Y")
        else:
            d1 = start_date
            
        if isinstance(end_date, str):
            d2 = datetime.strptime(end_date, "%d/%m/%Y")
        else:
            d2 = end_date
        
        # Auto-correction for inverted dates
        if d1 > d2:
            self._log(f"[AVISO] Data inicial ({d1.strftime('%d/%m/%Y')}) maior que final ({d2.strftime('%d/%m/%Y')}). Invertendo...")
            d1, d2 = d2, d1
            
        delta = d2 - d1
        date_list = [
            (d1 + timedelta(days=i)).strftime("%d/%m/%Y")
            for i in range(delta.days + 1)
        ]

        self._log(f"Iniciando navegador (debug={self.debug})...")
        
        async with async_playwright() as p:

            # Try to launch browser with fallback options
            browser = None
            launch_options = {
                "headless": not self.debug,
                "timeout": 30000
            }
            
            # 1. Try default (bundled Chromium)
            try:
                self._log("Tentando abrir navegador padrão (Chromium)...")
                browser = await p.chromium.launch(**launch_options)
            except Exception as e1:
                self._log(f"Falha no Chromium padrão: {e1}")
                # 2. Try Google Chrome
                try:
                    self._log("Tentando abrir Google Chrome instalado...")
                    browser = await p.chromium.launch(channel="chrome", **launch_options)
                except Exception as e2:
                    self._log(f"Falha no Google Chrome: {e2}")
                    # 3. Try Microsoft Edge
                    try:
                        self._log("Tentando abrir Microsoft Edge instalado...")
                        browser = await p.chromium.launch(channel="msedge", **launch_options)
                    except Exception as e3:
                        self._log(f"Falha no Microsoft Edge: {e3}")
                        raise Exception("Nenhum navegador compatível encontrado (Chromium, Chrome ou Edge).")
            
            if not browser:
                raise Exception("Falha crítica ao iniciar navegador.")

            
            # Custom User-Agent to identify the scraper nicely while looking like a browser
            my_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 DiárioOficialScraper/1.0"
            
            context = await browser.new_context(
                user_agent=my_ua
            )
            # Reduced navigation timeout from 90s to 30s
            context.set_default_navigation_timeout(30000) 
            page = await context.new_page()
            
            self._log("Navegador aberto com sucesso")

            self._log("Navegador aberto com sucesso")
            
            # Navigate to base URL ONCE
            self._log(f"[LINK] Acessando URL base (sessão inicial)...")
            try:
                await page.goto(self.base_url, timeout=30000)
            except Exception as e:
                self._log(f"[ERRO] Falha ao acessar URL base: {e}")
                raise

            for current_date in date_list:
                if status_callback:
                    await status_callback(f"Acessando Diário Oficial para: {current_date}")

                # Retry logic now focuses on the SEARCH ACTION, not the page load
                @retry(
                    stop=stop_after_attempt(2), 
                    wait=wait_exponential(multiplier=1, min=2, max=5),
                    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception))
                )
                async def fetch_results_with_retry():
                    # We are already on the page (or a result page). 
                    # Use JS to submit form for the new date.
                    
                    self._log(f"Pesquisando por {current_date}...")
                    
                    # Check if we are still on a valid page context
                    try:
                        url = page.url
                    except:
                        # If lost context, reload base
                        self._log("Contexto perdido. Recarregando URL base...")
                        await page.goto(self.base_url, timeout=30000)

                    js_script = f"""
                        var f = document.createElement('form'); f.action='md_epubli_controlador.php?acao=materias_pesquisar'; f.method='POST';
                        var i1=document.createElement('input');i1.name='hdnDataPublicacao';i1.value='{current_date}';f.appendChild(i1);
                        var i2=document.createElement('input');i2.name='hdnOrgaoFiltro';i2.value='{self.orgao_id}';f.appendChild(i2);
                        var i3=document.createElement('input');i3.name='hdnModoPesquisa';i3.value='DATA';f.appendChild(i3);
                        var i4=document.createElement('input');i4.name='hdnVisualizacao';i4.value='L';f.appendChild(i4);
                        document.body.appendChild(f); f.submit();
                    """
                    
                    try:
                        # Expect navigation because form submit reloads the page (or goes to results)
                        async with page.expect_navigation(timeout=30000):
                            await page.evaluate(js_script)
                    except PlaywrightTimeoutError:
                         self._log("[AVISO] Timeout na navegação do formulário. Verificando se carregou...")
                         # Sometimes it loads but the event isn't fired cleanly? 
                         # Verify if selectors exist
                         pass

                    
                    # Wait for results or 'no results' message
                    # We wait for EITHER dadosDocumento OR a specific body text indicating no results
                    # But wait_for_selector only waits for one.
                    # Best approach: wait for load state 'domcontentloaded' then check.
                    
                    # await page.wait_for_load_state('domcontentloaded') # expect_navigation already does this mostly
                    
                    self._log(f"Aguardando elementos ou mensagem de erro...")
                    
                    # Fast check for results
                    try:
                        # Optimization: Wait only 3s first. If results take longer, we catch and check "no results".
                        # If "no results" also absent, we wait longer for results (slow connection).
                        await page.wait_for_selector('div.dadosDocumento', state="attached", timeout=3000)
                        elementos = await page.query_selector_all('div.dadosDocumento')
                        self._log(f"Encontrados {len(elementos)} elementos no HTML")
                        return elementos
                    except:
                        # If not found quickly, check for "No results" text
                         content = await page.content()
                         no_results_patterns = [
                             "Nenhum registro encontrado",
                             "Não foram encontrados registros",
                             "sua pesquisa não retornou resultados",
                             "Tente refazer a pesquisa",
                             "Sem publicações no dia"
                         ]
                         if any(p in content for p in no_results_patterns):
                             self._log(f"[INFO] Nenhum registro encontrado para {current_date}")
                             return []
                         
                         # If neither, maybe it's just slow? Wait a bit longer?
                         # Or maybe it's an error page.
                         # Let's try waiting a bit more for selector if connection is slow
                         try:
                             await page.wait_for_selector('div.dadosDocumento', state="attached", timeout=10000)
                             return await page.query_selector_all('div.dadosDocumento')
                         except:
                             # Real timeout or error
                             safe_date = current_date.replace('/', '-')
                             try:
                                 with open(os.path.join(self.logs_dir, f"debug_html_{safe_date}.html"), "w", encoding='utf-8') as f:
                                     f.write(content)
                             except: pass
                             raise Exception("Timeout ou erro ao buscar resultados (seletor não encontrado).")
                
                elementos = []
                try:
                    elementos = await fetch_results_with_retry()
                except Exception as e:
                    self._log(f"[ERRO] Falha ao buscar {current_date} após tentativas: {e}")
                    # Screenshot for debugging
                    safe_date = current_date.replace('/', '-')
                    try:
                        await page.screenshot(path=os.path.join(self.logs_dir, f"error_{safe_date}.png"))
                    except: pass
                    
                    if status_callback:
                        await status_callback(f"[ERRO] Erro ou timeout ao buscar {current_date}. Verifique logs.")
                    continue

                if not elementos:
                     if status_callback:
                        await status_callback(f"[AVISO] Nenhuma publicação encontrada para {current_date}")
                     continue

                links_to_visit = []
                for el in elementos:
                    txt = await el.inner_text()
                    # self._log(f"DEBUG ITEM: {txt[:100]}...") # Too noisy usually, but good for now
                    if "GSU" in txt.upper(): 
                        # self._log("Skipping GSU")
                        continue
                    # Filter removed to capture all relevant documents
                    # if not re.search(r'(DBE|DBP|GSP)', txt, re.IGNORECASE): 
                    #    self._log(f"Skipping (No DBE/DBP/GSP): {txt[:50]}...")
                    #    continue
                    
                    matches_term = False
                    matched_term_name = "Geral"
                    if not terms:
                        matches_term = True
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
                            links_to_visit.append({
                                "url": self.clean_link(href),
                                "doc_id": doc_id,
                                "processo": proc,
                                "term": matched_term_name
                            })

                if status_callback:
                    await status_callback(f"Encontrados {len(links_to_visit)} itens relevantes em {current_date}. Extraindo detalhes (Modo Paralelo)...")

                # Concurrency control
                sem = asyncio.Semaphore(5)  # 5 concurrent requests
                total_items = len(links_to_visit)
                processed_count = 0

                async def fetch_and_extract(item):
                    nonlocal processed_count
                    async with sem:
                        # Retry logic for individual items
                        @retry(
                            stop=stop_after_attempt(2), 
                            wait=wait_exponential(multiplier=1, min=2, max=5),
                            retry=retry_if_exception_type((Exception))
                        )
                        async def fetch_item_details():
                            self._log(f"Acessando detalhes do documento {item['doc_id']}...")
                            # Create a new page for this specific task to handle concurrency safely
                            page_detail = await context.new_page()
                            try:
                                await page_detail.goto(item['url'], timeout=30000)
                                content = await page_detail.content()
                                return content
                            finally:
                                # Always ensure the page is closed, even if errors occur
                                await page_detail.close()

                        try:
                            content = await fetch_item_details()
                            soup = BeautifulSoup(content, 'html.parser')
                            
                            details = self.extract_details(soup)
                            
                            # Integração com Inteligência Artificial (Gemini)
                            try:
                                import sys
                                import os
                                sys.path.append(os.path.dirname(os.path.abspath(__file__)))
                                from ai_extractor import is_ai_enabled, extract_with_gemini
                                
                                if is_ai_enabled() and details.get('sintese'):
                                    self._log(f"Iniciando decodificação com IA para Documento {item['doc_id']}...")
                                    ai_data = await extract_with_gemini(details['sintese'])
                                    if ai_data:
                                        self._log(f"IA decodificou documento {item['doc_id']} com sucesso.")
                                        if ai_data.get('contractor') and ai_data['contractor'] != '-': details['contractor'] = ai_data['contractor']
                                        if ai_data.get('company_doc') and ai_data['company_doc'] != '-': details['doc_fiscal'] = ai_data['company_doc']
                                        if ai_data.get('object_text') and ai_data['object_text'] != '-': details['explicit_object'] = ai_data['object_text']
                                        if ai_data.get('validity_start') and ai_data['validity_start'] != '-': details['validade_inicio'] = ai_data['validity_start']
                                        if ai_data.get('validity_end') and ai_data['validity_end'] != '-': details['validade_fim'] = ai_data['validity_end']
                                        if ai_data.get('modality') and ai_data['modality'] != '-': 
                                            details['modality'] = ai_data['modality'].upper()
                                            if "DIVERSOS" in details['modality'] or "ATA" in details['modality']:
                                                details['tipo_doc'] = 'DIVERSOS'
                                            elif "ACORDO DE COOPERA" in details['modality']:
                                                # Só sobrepõe para acordo se o regex original não tiver cravado como DIVERSOS
                                                if details.get('tipo_doc') != 'DIVERSOS':
                                                    details['tipo_doc'] = 'ACORDO_COOPERACAO'
                                        
                                        if ai_data.get('value') and ai_data['value'] != '-': details['valor'] = ai_data['value']
                                        if ai_data.get('contract_number') and ai_data['contract_number'] != '-': details['num_contrato'] = ai_data['contract_number']
                            except Exception as e_ai:
                                self._log(f"Erro na IA para doc {item['doc_id']}: {e_ai}")
                               
                            
                            link_pdf = item['url']
                            if details['integra_id']:
                                 # Try finding link with text matching the ID
                                 a_precise = soup.find('a', string=lambda t: t and details['integra_id'] in t)
                                 if a_precise and a_precise.has_attr('href'):
                                     link_pdf = self.clean_link(a_precise['href'])
                                 else:
                                     # Fallback to href check
                                     for a in soup.find_all('a', href=True):
                                        if details['integra_id'] in a['href']:
                                            link_pdf = self.clean_link(a['href'])
                                            break
                            
                            
                            # Prioritize explicit object field if found structured
                            obj_text = details.get('explicit_object')
                            if obj_text and len(obj_text) > 5:
                                 # Clean it up a bit if needed
                                 obj_text = re.sub(r'\s+', ' ', obj_text).strip()
                            else:
                                 obj_text = self.extract_object(details['sintese'])
                            
                            res = SearchResult(
                                date=current_date,
                                term=item['term'],
                                process_number=item['processo'],
                                document_id=item['doc_id'],
                                summary=details['sintese'][:200] + "...",
                                object_text=obj_text,
                                contractor=details['contractor'], # Was 'contratada', now 'contractor' in details dict due to update? Check extract_details.
                                company_doc=details['doc_fiscal'],
                                contract_number=details['num_contrato'],
                                validity_start=details['validade_inicio'],
                                validity_end=details['validade_fim'],
                                value=details['valor'],
                                link_html=item['url'],
                                link_pdf=link_pdf,
                                modality=details.get('modality', '-'),
                                opening_date=details.get('opening_date', '-'),
                                amendment_number=details.get('num_aditamento', ''),
                                parent_contract=details.get('contrato_pai', ''),
                                doc_type=details.get('tipo_doc', 'OUTRO')
                            )
                            processed_count += 1
                            if status_callback:
                                await status_callback(f"Processado {processed_count}/{total_items}: Doc {item['doc_id']}")
                            return res
                            
                        except Exception as e:
                            self._log(f"[ERRO] Erro no item {item['doc_id']}: {e}")
                            processed_count += 1
                            if status_callback:
                                await status_callback(f"Falha {processed_count}/{total_items}: Doc {item['doc_id']}")
                            return None

                # Launch all tasks
                tasks = [fetch_and_extract(item) for item in links_to_visit]
                extracted_results = await asyncio.gather(*tasks)
                
                # Filter out None results (failures)
                valid_results = [r for r in extracted_results if r]
                results.extend(valid_results)
            
            try:
                await browser.close()
                self._log("Navegador fechado com sucesso")
            except Exception as e:
                self._log(f"[ERRO] Erro ao fechar navegador: {e}")
            
            elapsed = datetime.now() - start_time
            self._log(f"Raspagem finalizada em {elapsed}. Total de resultados: {len(results)}")
            if status_callback:
                await status_callback(f"Concluído em {elapsed}. Encontrados: {len(results)}")

            return results


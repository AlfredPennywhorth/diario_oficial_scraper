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

import unicodedata

# Configuração de Logs
logger = logging.getLogger(__name__)

def _normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = str(text)
    # Decompor caracteres Unicode para remover acentos (diacríticos)
    normalized = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower()
    # Substituir múltiplos espaços por um único espaço
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()

TERM_PATTERNS = {
    "acordo de cooperacao": ["cooperacao"],
    "pregao": ["pregao"],
    "aditamento": ["aditamento", "aditivo", "apostilamento"],
    "termo de colaboracao": ["colaboracao"],
    "termo de fomento": ["fomento"],
    "termo de doacao": ["doacao"],
    "termo de comodato": ["comodato"],
    "nota de empenho": ["empenho"],
    "contrato": ["contrato"]
}

def _match_term(term: str, text: str) -> tuple[bool, str | None]:
    norm_term = _normalize_text(term)
    norm_text = _normalize_text(text)

    patterns = TERM_PATTERNS.get(norm_term)
    if patterns:
        for p in patterns:
            if p in norm_text:
                return True, p
        return False, None
    else:
        if norm_term in norm_text:
            return True, norm_term
        return False, None

def _parse_date_by_extenso(text: str | None) -> str | None:
    if not text:
        return None
    text_clean = text.strip().lower()
    m = re.search(r'(?:sã?o\s+paulo\s*,\s*)?(\d{1,2})\s+de\s+([a-zçãõáéíóúâêîôû]+)\s+de\s+(\d{4})', text_clean)
    if not m:
        return None
    day_str, month_name, year_str = m.groups()
    months = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
        "abril": 4, "maio": 5, "junho": 6, "julho": 7,
        "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
        "dezembro": 12
    }
    month_num = months.get(month_name)
    if not month_num:
        return None
    try:
        day = int(day_str)
        year = int(year_str)
        dt = datetime(year=year, month=month_num, day=day)
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return None

class DiarioScraper:
    def __init__(self, debug=False):
        self.debug = debug  # If True, browser will be visible

        # Centralized Configurations (Load from Environment or Defaults)
        self.base_url = os.getenv("SCRAPER_BASE_URL", "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=materias_pesquisar")
        self.orgao_id = os.getenv("SCRAPER_ORGAO_ID", "68")  # Default 68 (CET)

        # Browser Configurations
        self.browser_timeout = int(os.getenv("BROWSER_TIMEOUT_MS", "90000"))
        self.browser_executable = os.getenv("BROWSER_EXECUTABLE_PATH", None)
        # BROWSER_HEADLESS env overwrites self.debug if present
        env_headless = os.getenv("BROWSER_HEADLESS", None)
        if env_headless is not None:
            self.headless = env_headless.lower() in ("true", "1", "yes")
        else:
            self.headless = not self.debug

        self.is_running = False # Controle de execução simultânea

        # Determine base directory for logs and artifacts
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

        div_main = soup.find('div', {'class': 'conteudoMateria'}) or soup.find('div', {'class': 'materia'})
        full_body_text = div_main.get_text(" ", strip=True) if div_main else soup.get_text(" ", strip=True)

        full_text = f"{data.get('num_contrato', '')} {data.get('sintese', '')} {data.get('explicit_object', '')} {full_body_text}"

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
            "Número da Publicação": "num_contrato",
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

        if data.get("explicit_object"):
            data['explicit_object'] = re.sub(r'(?i)^(?:CELEBRA[ÇC][ÃA]O\s+DE\s+ACORDO\s+DE\s+COOPERA[ÇC][ÃA]O\s+PARA\s+(?:A\s+)?|OBJETO:\s*)', '', data['explicit_object']).strip()

    def _extract_modality(self, text, data):
        if data.get('modality') in ["-", "", None]:
            m_mod = re.search(r'(PREGÃO ELETRÔNICO|PREGÃO|CONCORRÊNCIA|TOMADA DE PREÇOS|CONVITE|LEILÃO|DIÁLOGO COMPETITIVO|INEXIGIBILIDADE|DISPENSA)', text, re.IGNORECASE)
            if m_mod:
                data['modality'] = m_mod.group(1).upper()
            elif "LICITAÇÃO" in text.upper():
                data['modality'] = "LICITAÇÃO"

    def _extract_contractor(self, text, data):
        # Extrair CNPJ se ainda não tiver
        if not data.get('doc_fiscal') or data.get('doc_fiscal') == "-":
            m_cnpj = re.search(r'([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})', text)
            if m_cnpj:
                data['doc_fiscal'] = m_cnpj.group(1)

        # Regra específica para Acordo de Cooperação
        m_acordo = re.search(
            r'celebra[çc][ãa]o do Acordo de Coopera[çc][ãa]o.*?(?:com a|com o|celebrado com a|celebrado com o)\s+(?:(?-i:empresa|institui[çc][ãa]o)\s+)?([^\r\n]+?)(?=\s*(?:,\s*(?:CNPJ|CPF|Processo|Objeto|Vig[êe]ncia|Valor|Data da assinatura|Formalizado em|inscrit[oa]))|\s+(?:CNPJ|CPF|Processo|Objeto|Vig[êe]ncia|Valor|Data da assinatura|Formalizado em|inscrit[oa])|$)',
            text,
            re.IGNORECASE
        )
        if not m_acordo:
            m_acordo = re.search(
                r'celebrado\s+com\s+(?:a\s+|o\s+)?(?:(?-i:empresa|institui[çc][ãa]o)\s+)?([^\r\n]+?)(?=\s*(?:,\s*(?:CNPJ|CPF|Processo|Objeto|Vig[êe]ncia|Valor|Data da assinatura|Formalizado em|inscrit[oa]))|\s+(?:CNPJ|CPF|Processo|Objeto|Vig[êe]ncia|Valor|Data da assinatura|Formalizado em|inscrit[oa])|$)',
                text,
                re.IGNORECASE
            )

        if m_acordo:
            data['contractor'] = m_acordo.group(1).strip()

        # Fallback genérico se ainda não foi extraído
        if data.get('contractor') in ["-", "", None]:
             patterns = [
                 r'(?:Vencedor(?:es)?|Adjudicado para|Empresa|Contratada|Partícipe)\s*[:\.-]?\s*([A-ZÇÃÕÁÉÍÓÚ\s\.,&LTDA\-]+?)(?:,?\s*CNPJ|CPF|$)',
                 r'Empresa\s+([A-ZÇÃÕÁÉÍÓÚ\s\.,&LTDA\-]+?)\s+,',
                 r'([^.\n:;]{5,120}?)(?:,?\s*CNPJ|CPF)'
             ]
             for p in patterns:
                 m_winner = re.search(p, text, re.IGNORECASE)
                 if m_winner:
                       candidate = m_winner.group(1).strip().rstrip(',.-')
                       if len(candidate) > 3 and "PROCESS" not in candidate.upper() and "PUBLICACAO" not in candidate.upper():
                            data['contractor'] = candidate
                            break

        # Pós-processamento de limpeza de contractor
        if data.get('contractor') and data.get('contractor') != "-":
            contractor_val = data['contractor'].strip()
            # Remover prefixos comuns de ligação do início da string (case-insensitive)
            contractor_val = re.sub(
                r'^(?:com\s+a\s+|com\s+o\s+|celebrado\s+com\s+a\s+|celebrado\s+com\s+o\s+|celebrado\s+com\s+)',
                '',
                contractor_val,
                flags=re.IGNORECASE
            ).strip()
            # Remover prefixos de substantivos do início da string (case-sensitive para evitar remover nomes próprios de empresas)
            contractor_val = re.sub(
                r'^(?:empresa|institui[çc][ãa]o)\s+',
                '',
                contractor_val
            ).strip()
            # Limpar pontuação excedente apenas nas extremidades
            contractor_val = contractor_val.strip(' ,-')
            if contractor_val.startswith('.'):
                contractor_val = contractor_val[1:].strip()
            data['contractor'] = contractor_val

        # Fix concatenated CPFs (e.g. ...178-34074.999...)
        doc = data.get('doc_fiscal', '')
        if doc and len(doc) > 15:
            doc = re.sub(r'(-\d{2})(\d{3}\.)', r'\1, \2', doc)
            data['doc_fiscal'] = doc

    def _extract_contract_info(self, text, data):
        # 1. Busca específica por CONTRATO com prioridade (pode sobrescrever labels genéricos)
        m_con = re.search(r'(?:Formalização d[oa] |Extrato de |Termo de |Celebrado o )?Contrato\s*(?:n[º°.º]|n[°º])?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
        if m_con:
             data['num_contrato'] = m_con.group(1)

        # 2. Busca genérica se ainda estiver com valor padrão ou "-"
        if data.get('num_contrato') in ["-", "", None]:
            m_id = re.search(r'(?:Pregão(?: Eletrônico)?|Licitação|Carta Convite|Nota de Empenho|Termo de Fomento|Termo de Colaboração|Acordo de Coopera[çc][ãa]o|Termo de Doação|Termo de Comodato)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
            if m_id:
                data['num_contrato'] = m_id.group(1)

        # 3. Busca específica por ACORDO DE COOPERAÇÃO (para garantir o prefixo)
        m_acordo = re.search(r'(ACORDO DE COOPERA[ÇC][ÃA]O)\s*(?:n[º°.º]|n[°º])?\s*([\d\.]+)/([\d]{2,4})', text, re.IGNORECASE)
        if m_acordo:
             ano = m_acordo.group(3)
             if len(ano) == 4:
                 ano = ano[2:]
             data['num_contrato'] = f"Acordo de Cooperação {m_acordo.group(2)}/{ano}"

        # 4. Busca por Aditamentos / Apostilamentos (Melhorado tornando o número opcional)
        m_adit = re.search(r'(?:Termo de |Extrato de |Termo )?(Aditamento|Apostilamento|Aditivo)(?:\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?))?', text, re.IGNORECASE)

        if m_adit and m_adit.group(1):
            tipo_encontrado = m_adit.group(1).upper()
            data['tipo_doc'] = 'ADITAMENTO' if tipo_encontrado in ['ADITAMENTO', 'ADITIVO'] else 'APOSTILAMENTO'
            data['num_aditamento'] = m_adit.group(2) if m_adit.group(2) else ""

            # Identificação do Contrato Pai (Original)
            m_pai = re.search(r'(?:ao |do )(?:Termo de )?(?:Contrato|Termo de Colaboração|Termo de Fomento|Ajuste)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
            if m_pai:
                data['contrato_pai'] = m_pai.group(1)
        elif re.search(r'\b(?:Aditamento|Aditivo)\b', text, re.IGNORECASE):
            data['tipo_doc'] = 'ADITAMENTO'
            data['num_aditamento'] = ""
            m_pai = re.search(r'(?:ao |do )(?:Termo de )?(?:Contrato|Termo de Colaboração|Termo de Fomento|Ajuste)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
            if m_pai:
                data['contrato_pai'] = m_pai.group(1)
        elif re.search(r'\b(?:Apostilamento)\b', text, re.IGNORECASE):
            data['tipo_doc'] = 'APOSTILAMENTO'
            data['num_aditamento'] = ""
            m_pai = re.search(r'(?:ao |do )(?:Termo de )?(?:Contrato|Termo de Colaboração|Termo de Fomento|Ajuste)\s*(?:nº|n°)?\s*([\d\.]+(?:/[\d]{2,4})?)', text, re.IGNORECASE)
            if m_pai:
                data['contrato_pai'] = m_pai.group(1)

        # Fallback do num_contrato estruturado para contrato_pai em Aditamentos/Apostilamentos
        if data.get('tipo_doc') in ['ADITAMENTO', 'APOSTILAMENTO']:
            if not data.get('contrato_pai') or data.get('contrato_pai') == "-":
                structured_num = data.get('num_contrato')
                if structured_num and structured_num != "-":
                    data['contrato_pai'] = structured_num

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
        validade_inicio = ""

        def normalize_date(d):
            if not d: return ""
            return d.replace('.', '/')

        # Tentar 1: Data da assinatura
        m_dt = re.search(r'Data\s+da\s+Assinatura:?\s*(\d{2}[/.]\d{2}[/.]\d{4})', text, re.IGNORECASE)
        if m_dt:
            validade_inicio = normalize_date(m_dt.group(1))

        # Tentar 2: Assinado em
        if not validade_inicio:
            m_ass = re.search(r'Assinado\s+em\s*(\d{2}[/.]\d{2}[/.]\d{4})', text, re.IGNORECASE)
            if m_ass:
                validade_inicio = normalize_date(m_ass.group(1))

        # Tentar 3: Formalizado em
        if not validade_inicio:
            m_form = re.search(r'Formalizado\s+em\s*(\d{2}[/.]\d{2}[/.]\d{4})', text, re.IGNORECASE)
            if m_form:
                validade_inicio = normalize_date(m_form.group(1))

        # Tentar 4: Celebrado em
        if not validade_inicio:
            m_cel = re.search(r'Celebrado\s+em\s*(\d{2}[/.]\d{2}[/.]\d{4})', text, re.IGNORECASE)
            if m_cel:
                validade_inicio = normalize_date(m_cel.group(1))

        # Tentar 5: Data por extenso em linha final, somente como último fallback
        if not validade_inicio:
            final_part = text[-300:]
            m_ext = re.search(r'Sã?o\s+Paulo\s*,\s*(\d{1,2})\s+de\s+([a-zçãõáéíóúâêîôû]+)\s+de\s+(\d{4})', final_part, re.IGNORECASE)
            if m_ext:
                day, month_name, year = m_ext.groups()
                date_parsed = _parse_date_by_extenso(f"{day} de {month_name} de {year}")
                if date_parsed:
                    validade_inicio = date_parsed

        patterns_vigencia = [
            r'Vigência:?\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*(?:e|a)\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
            r'compreendidos entre\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*(?:e|a)\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
            r'(?:vigência|período|prazo).*?(?:de\s*)?"?(\d{2}[/.]\d{2}[/.]\d{4})"?\s*(?:e|a)\s*"?(\d{2}[/.]\d{2}[/.]\d{4})"?',
        ]

        vig_start = ""
        vig_end = ""
        found_vig = False
        for p in patterns_vigencia:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                vig_start = normalize_date(m.group(1))
                vig_end = normalize_date(m.group(2))
                found_vig = True
                break

        if not found_vig:
            m_vig2 = re.search(r'(\d{2}[/.]\d{2}[/.]\d{4})\s*a\s*(\d{2}[/.]\d{2}[/.]\d{4})', text)
            if m_vig2:
                vig_start = normalize_date(m_vig2.group(1))
                vig_end = normalize_date(m_vig2.group(2))
                found_vig = True

        # Preencher validity_start
        if vig_start:
            data['validity_start'] = vig_start
        elif validade_inicio:
            # Aceitar data de assinatura como início apenas quando o texto disser que a vigência começa na assinatura, formalização ou celebração
            inicio_na_assinatura = re.search(
                r'(?:vigência|vigente|prazo|início|iniciando|contados|a partir)\s+(?:de|a\s+partir\s+de|na|da|de\s+sua)?\s*(?:data\s+de\s+sua\s+|data\s+da\s+|data\s+de\s+)?(?:assinatura|formalização|formalizacao|celebração|celebracao)',
                text,
                re.IGNORECASE
            )
            if inicio_na_assinatura:
                data['validity_start'] = validade_inicio
            else:
                data['validity_start'] = "-"
        else:
            data['validity_start'] = "-"

        # Determinar validity_end
        validade_fim = "-"
        if vig_end:
            validade_fim = vig_end
        elif re.search(r'Plano\s+de\s+Trabalho', text, re.IGNORECASE):
            if re.search(r'(?:vigência|término|prazo).*?Plano\s+de\s+Trabalho', text, re.IGNORECASE):
                validade_fim = "Conforme Plano de Trabalho"

        # Fallback de prazo calculado
        if validade_fim == "-" and data['validity_start'] != "-" and data.get('prazo'):
            try:
                dt_ini = datetime.strptime(data['validity_start'], "%d/%m/%Y")
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

        data['data_assinatura'] = validade_inicio if validade_inicio else "-"
        data['validade_inicio'] = data['validity_start']
        data['validade_fim'] = validade_fim
        data['validity_end'] = validade_fim

    def _classify_document(self, text, data):
        """Classifica o documento conforme hierarquia e termos fortes"""
        txt = text.upper()
        modality = data.get('modality', '').upper()

        # 1. ADITAMENTO / APOSTILAMENTO
        if any(x in txt for x in ["TERMO ADITIVO", "ADITAMENTO", "EXTRATO DE TERMO DE ADITAMENTO", "APOSTILAMENTO"]) or data.get('num_aditamento'):
             data['tipo_doc'] = 'ADITAMENTO'
             return

        # 2. CONTRATO
        if any(x in txt for x in ["CONTRATO Nº", "CONTRATO N.º", "CONTRATO N°", "FORMALIZAÇÃO DO CONTRATO", "EXTRATO DE CONTRATO", "CELEBRAÇÃO DE CONTRATO"]):
             data['tipo_doc'] = 'CONTRATO'
             return

        # 3. ACORDO DE COOPERAÇÃO / PARCERIA / CONVÊNIO
        if re.search(r'\b(?:ACORDOS?\ DE\ COOPERA[ÇC][ÃA]O|TERMO\ DE\ COOPERA[ÇC][ÃA]O)\b', txt):
             data['tipo_doc'] = 'ACORDO_COOPERACAO'
             return

        if re.search(r'\b(?:TERMO\ DE\ PARCERIA|CONV[ÊE]NIO|TERMO\ DE\ FOMENTO|TERMO\ DE\ COLABORA[ÇC][ÃA]O)\b', txt):
             data['tipo_doc'] = 'PARCERIA'
             return

        # 4. DISPENSA / COMPRA (Se houver evidência forte)
        if "DISPENSA" in txt or ("DISPENSA" in modality and "OBJETO" in txt):
             data['tipo_doc'] = 'PEDIDO_COMPRA'
             return

        # 5. PREGÃO (Exige evidência explícita de pregão/licitação)
        termos_fortes_pregao = [
            "PREGÃO", "PREGAO",
            "AVISO DE LICITAÇÃO", "ABERTURA DE LICITAÇÃO",
            "HOMOLOGAÇÃO DE PREGÃO", "HOMOLOGAÇÃO DE LICITAÇÃO",
            "ATA DE REGISTRO DE PREÇOS", "SISTEMA DE REGISTRO DE PREÇOS"
        ]

        # Termos que indicam publicação genérica/administrativa (DIVERSOS)
        # Devem ter prioridade sobre o fallback de modalidade
        termos_diversos = [
            "ESCLARECIMENTO", "QUESTIONAMENTO", "DESPACHO DE IMPUGNAÇ",
            "IMPUGNAÇ", "NOTIFICAÇÃO", "ATA DE ABERTURA",
            "DEMONSTRATIVO DAS COMPRAS", "RESPOSTA A QUESTIONAMENTO",
            "PAGAMENTO", "DESPACHO", "PUBLICAÇÃO"
        ]

        if any(x in txt for x in termos_diversos):
            data['tipo_doc'] = 'DIVERSOS'
            return

        # Se contiver algum termo forte no TEXTO, é PREGAO
        if any(x in txt for x in termos_fortes_pregao):
             data['tipo_doc'] = 'PREGAO'
             return

        # Fallback para modalidade apenas se houver evidência de ser a publicação principal
        # e NÃO for apenas um termo genérico
        if any(x in modality for x in ["PREGÃO", "PREGAO", "LICITAÇÃO", "LICITACAO"]):
             # Exige 'OBJETO' + algum dado relevante (VALOR ou CONTRATADA) para não ser DIVERSOS
             if "OBJETO" in txt and (any(v in txt for v in ["VALOR", "R$", "CONTRATAD", "VENCEDOR", "ADJUDIC"])):
                 data['tipo_doc'] = 'PREGAO'
                 return

        # 6. DIVERSOS (Fallback final para qualquer coisa que não se encaixe acima)
        data['tipo_doc'] = 'DIVERSOS'

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
                    elif "ACORDO DE COOPERA" in details['modality'] or "TERMO DE COOPERA" in details['modality']:
                         details['tipo_doc'] = 'ACORDO_COOPERACAO'

            # --- PROTEÇÃO ABSOLUTA DA CLASSIFICAÇÃO DE ACORDO DE COOPERAÇÃO ---
            # Independentemente do que a IA disse, se for Acordo de Cooperação, forçamos o tipo.
            num_contrato_up = details.get('contract_number', '').upper()
            summary_up = details.get('summary', '').upper()
            full_body_up = details.get('explicit_object', '').upper() + " " + item_html.upper()

            if re.search(r'\b(?:ACORDOS?\ DE\ COOPERA[ÇC][ÃA]O|TERMO\ DE\ COOPERA[ÇC][ÃA]O)\b', num_contrato_up) or \
               re.search(r'\b(?:ACORDOS?\ DE\ COOPERA[ÇC][ÃA]O|TERMO\ DE\ COOPERA[ÇC][ÃA]O)\b', summary_up) or \
               re.search(r'\b(?:ACORDOS?\ DE\ COOPERA[ÇC][ÃA]O|TERMO\ DE\ COOPERA[ÇC][ÃA]O)\b', full_body_up):
                # Salvo se for claramente aditamento
                if 'ADITAMENTO' not in summary_up and 'ADITIVO' not in summary_up:
                    details['tipo_doc'] = 'ACORDO_COOPERACAO'

            # --- FIM PROTEÇÃO ---
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
        match_obj = re.search(r'(?:OBJETO da licitação|OBJETO|ASSUNTO):?\s*(.*?)(?=\s*(?:JULGAMENTO|REGIME|MODALIDADE|MODO|Valor|Prazo|Local|Data|Edital|Sessão|Licitante|II\s?-|II\.|\.|$))', txt, re.IGNORECASE)
        if match_obj:
            val = match_obj.group(1).strip()
            if len(val) < 300: return self._clean_object_text(val.rstrip('.'))

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
        match_no_quote = re.search(r'(?:que trata\s*(?:d[eao])?|objeto:?)\s*(?!["“\'])(.*?)(?=\.|,|;|-|Modalidade|Valor|Data|Licitante|$)', txt, re.IGNORECASE)
        if match_no_quote:
             val = match_no_quote.group(1).strip()
             if len(val) > 3:
                return self._clean_object_text(val)

        return "Verificar objeto na íntegra."

    def _clean_object_text(self, text):
        cleaned = re.sub(r'^(?:CELEBRAÇÃO\s+DE\s+)?ACORDO\s+DE\s+COOPERA[ÇC][ÃA]O\s+(?:PARA\s+A\s+|PARA\s+)?', '', text, flags=re.IGNORECASE)
        return cleaned.strip()

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

            async with async_playwright() as p:
                browser = None
                launch_options = {
                    "headless": self.headless,
                    "timeout": self.browser_timeout
                }
                if self.browser_executable:
                    launch_options["executable_path"] = self.browser_executable
                    logger.info(f"Usando executável customizado: {self.browser_executable}")

                # Fallback Sequence with detailed logging
                browsers_to_try = [
                    {"name": "Chromium (Playwright)", "args": {}},
                    {"name": "Google Chrome", "args": {"channel": "chrome"}},
                    {"name": "Microsoft Edge", "args": {"channel": "msedge"}}
                ]

                last_error = ""
                for b_config in browsers_to_try:
                    try:
                        logger.info(f"Tentando iniciar {b_config['name']} (timeout={self.browser_timeout}ms)...")
                        browser = await p.chromium.launch(**{**launch_options, **b_config['args']})
                        logger.info(f"[OK] {b_config['name']} iniciado com sucesso.")
                        break
                    except Exception as e:
                        err_msg = str(e)
                        last_error = err_msg
                        # Differentiate error types
                        if "Executable doesn't exist" in err_msg:
                            diag = "Executável não encontrado."
                        elif "Timeout" in err_msg:
                            diag = "Timeout de inicialização (pode ser bloqueio de rede/antivírus ou caminho UNC)."
                        else:
                            diag = f"Erro inesperado: {err_msg[:100]}"

                        logger.warning(f"[FALHA] {b_config['name']} falhou: {diag}")

                if not browser:
                    error_detail = f"Não foi possível iniciar nenhum navegador. Último erro: {last_error}"
                    logger.error(error_detail)
                    raise Exception(error_detail)

                context = await browser.new_context(user_agent="Mozilla/5.0 DiárioOficialScraper/1.0")
                context.set_default_navigation_timeout(self.browser_timeout)
                page = await context.new_page()

                logger.info(f"Acessando URL base: {self.base_url}")
                await page.goto(self.base_url, timeout=self.browser_timeout)

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
                        if not terms:
                            matches_term = True
                        else:
                            for t in terms:
                                matched, pattern = _match_term(t, txt)
                                if matched:
                                    matches_term = True
                                    matched_term_name = t
                                    logger.info(f"[FILTRO] Correspondencia encontrada para o termo '{t}' (padrao: '{pattern}') no texto: {txt[:150]}...")
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
                                    validity_end=details['validade_fim'], data_assinatura=details.get('data_assinatura', '-'),
                                    value=details['valor'], link_html=item['url'],
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


import re

def extract_object(text):
    if not text: return "VERIFICAR NA ÍNTEGRA"
    # Logic from scraper_service.py
    txt = re.sub(r'\s+', ' ', text)
    print(f"DEBUG: Cleaned text: '{txt}'")
    
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
        print(f"DEBUG: Match found! Group 1: '{match_obj.group(1)}'")
        val = match_obj.group(1).strip()
        if len(val) < 300: return val.rstrip('.')
        else: print(f"DEBUG: Value too long ({len(val)} chars).")

    # 2. Action verbs
    termos_parada = r'(?:II\s?-|II\.|2\.|A CET poderá|Nesta hipótese|EXPEDIENTE Nº|Data d[ae]|Edital|Sessão|Realização|com fundamento|nos termos|por inexigibilidade|em conformidade|Formalizado em|Disponível no|Publicado no|$)'
    padrao_acao = r'(?:para [oa]s?|visando [oa]s?|objetivando|referente [àao]s?)\s+(.*?)(?=\s*' + termos_parada + ')'
    match = re.search(padrao_acao, txt, re.IGNORECASE)
    if match:
            return match.group(0).strip() 

    return "Verificar objeto na íntegra."

# Test Case 1: Pregão with "Objeto da licitação"
# Simulating the text soup.get_text(" ", strip=True) might return
# Note: "Data da Abertura" follows immediately.
text1 = """
Número da Publicação: PREGÃO ELETRÔNICO 020/2025
Licitante Vencedor: -
Modalidade: PREGÃO ELETRÔNICO
Objeto da licitação Conversão da sinalização horizontal existente
Data da Abertura: 03/02/2026
Data de Publicação: 09/01/2026
"""

print("--- TEST 1 ---")
print("Result:", extract_object(text1))

# Test Case 2: Pregão with explicit colon
text2 = """
Objeto: Aquisição de 28 unidades de Notebook
Data da Abertura: 09/02/2026
"""
print("\n--- TEST 2 ---")
print("Result:", extract_object(text2))

# Test Case 3: The problematic one user mentioned?
# "Objeto da licitação" is a header. Text below is "CONTRATAÇÃO DE SERVIÇOS..."
text3 = """
Modalidade: PREGÃO ELETRÔNICO
Objeto da licitação
CONTRATAÇÃO DE SERVIÇOS ESPECIALIZADOS PARA DESENVOLVIMENTO, SUSTENTAÇÃO DE SOFTWARE E SISTEMA DE SEGURANÇA VIÁRIA EM TEMPO REAL, CONFORME METODOLOGIA ÁGIL ADOTADA PELA CET
Data da Abertura: 23/01/2026
"""
print("\n--- TEST 3 ---")
print("Result:", extract_object(text3))

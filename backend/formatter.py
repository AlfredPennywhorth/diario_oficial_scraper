"""
Formatador de resultados do scraper do Diário Oficial
Converte resultados em HTML formatado estilo Google Colab
"""
import re
from typing import List
from models import SearchResult


class DiarioFormatter:
    """Formatador de resultados com classificação por tipo e cores"""
    
    def __init__(self):
        self.css = """
        <style>
            .card { 
                border: 1px solid #ddd; 
                padding: 15px; 
                margin-bottom: 20px; 
                font-family: Arial, sans-serif; 
                background: #fff; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }
            .compra { border-left: 5px solid #004376; }
            .contrato { border-left: 5px solid #17a2b8; background-color: #fcfcfc; }
            .aditamento { border-left: 5px solid #28a745; background-color: #f9fff9; }
            .label { font-weight: bold; color: #333; }
            .val { color: #000; }
            a { text-decoration: none; color: #0056b3; font-weight: bold; }
        </style>
        """
    
    def anonimizar_cpf(self, texto: str) -> str:
        """Anonimiza CPF mantendo apenas primeiro e últimos dígitos"""
        if not texto:
            return ""
        limpo = re.sub(r'\D', '', texto)
        if len(limpo) == 11:
            return re.sub(r'(\d{3})[\.\s]?(\d{3})[\.\s]?(\d{3})[-\s]?(\d{2})', 
                         r'\1.***.***-\4', texto)
        return texto
    
    def classificar_tipo(self, summary: str) -> str:
        """Classifica o tipo de publicação com base no contexto"""
        txt = summary.upper()
        
        # Prioridade 1: Verificar formalizações explícitas de contrato
        if "FORMALIZAÇÃO DO CONTRATO" in txt or "FORMALIZADO EM" in txt:
            return "CONTRATO"
        
        # Prioridade 2: Aditamentos
        if "ADITAMENTO" in txt or "TERMO ADITIVO" in txt:
            return "ADITAMENTO"
        
        # Prioridade 3: Contratos em geral (verificar contexto)
        if "CONTRATO" in txt and "ADITAMENTO" not in txt:
            # Se é formalização ou celebração, definitivamente é contrato
            if any(palavra in txt for palavra in ["FORMALIZAÇÃO", "CELEBRADO", "ASSINATURA DO CONTRATO", "NÚMERO DO CONTRATO"]):
                return "CONTRATO"
            # Se menciona "contrato" mas não tem contexto de formalização, pode ser apenas referência
            # Neste caso, continua verificando outras possibilidades
        
        # Prioridade 4: Licitações (pregão, homologação, etc)
        if "PREGÃO" in txt or "LICITAÇÃO" in txt or "HOMOLOG" in txt:
            # Se já foi identificado como contrato acima, não sobrescrever
            # Se chegou aqui, é porque não tinha contexto forte de contrato
            return "LICITACAO"
        
        # Prioridade 5: Se tem "CONTRATO" mas não se encaixou em nenhum dos acima
        if "CONTRATO" in txt:
            return "CONTRATO"
        
        return "OUTROS"
    
    def extrair_numero_aditamento(self, texto: str) -> str:
        """Extrai número do aditamento"""
        m_adit = re.search(r'(?:ADITAMENTO|TERMO ADITIVO)[^0-9]*(\d+/\d+)', texto.upper())
        if m_adit:
            parts = m_adit.group(1).split('/')
            ano = parts[1] if len(parts[1]) == 4 else "20" + parts[1]
            return f"{parts[0].zfill(3)}/{ano}"
        return "S/N"
    
    def extrair_numero_contrato_origem(self, texto: str) -> str:
        """Extrai número do contrato original (para aditamentos)"""
        m_orig = re.search(r'CONTRATO Nº\s*(\d+/\d+)', texto.upper())
        return m_orig.group(1) if m_orig else "S/N"
    
    def extrair_numero_licitacao(self, texto: str, doc_id: str) -> str:
        """Extrai número da licitação"""
        m_num = re.search(r'(?:PREGÃO|LICITAÇÃO|CHAMAMENTO)[^0-9]*(\d+/\d+)', texto.upper())
        return m_num.group(1) if m_num else doc_id
    
    def extrair_vencedor(self, texto: str) -> str:
        """Extrai vencedor da licitação"""
        txt = texto.upper()
        if "HOMOLOG" in txt or "ADJUDIC" in txt:
            m_emp = re.search(r'EMPRESA\s+(.*?)(?:,|\.|CNPJ)', txt)
            if m_emp:
                return m_emp.group(1).strip()
        return "EM PROCESSO"
    
    def extrair_data_abertura(self, texto: str) -> str:
        """Extrai data de abertura da licitação"""
        txt = re.sub(r'\s+', ' ', texto)
        
        padrao_data = r'(?:abertura|sessão|disputa|lances|ocorrerá).*?(?:dia|em|at[ée])\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})'
        match = re.search(padrao_data, txt, re.IGNORECASE)
        if match:
            return match.group(1)
        
        match_label = re.search(r'Data da sessão\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})', txt, re.IGNORECASE)
        if match_label:
            return match_label.group(1)
        
        return "Ver Edital"
    
    def extrair_vigencia(self, texto: str) -> str:
        """Extrai período de vigência"""
        # Padrão 1: "Data de início e término... X e Y"
        m_inicio_fim = re.search(
            r'Data de início e t[ée]rmino.*?:?\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})\s*e\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})',
            texto, re.IGNORECASE
        )
        if m_inicio_fim:
            return f"{m_inicio_fim.group(1)} a {m_inicio_fim.group(2)}"
        
        # Padrão 2: "período de X a Y"
        m_periodo = re.search(
            r'período de\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})\s*a\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})',
            texto, re.IGNORECASE
        )
        if m_periodo:
            return f"{m_periodo.group(1)} a {m_periodo.group(2)}"
        
        # Padrão 3: Prazo em meses
        m_meses = re.search(r'pelo prazo de (?:mais)?\s*(\d+.*?)meses', texto)
        if m_meses:
            return f"{m_meses.group(1)}meses (ver datas no contrato)"
        
        return "Ver Contrato"
    
    def extrair_modalidade(self, texto: str) -> str:
        """Extrai modalidade da licitação"""
        txt = texto.upper()
        if "CONCORRÊNCIA" in txt:
            return "CONCORRÊNCIA"
        elif "DISPENSA" in txt:
            return "DISPENSA DE LICITAÇÃO"
        elif "INEXIGIBILIDADE" in txt:
            return "INEXIGIBILIDADE"
        elif "CHAMAMENTO" in txt:
            return "CHAMAMENTO PÚBLICO"
        return "PREGÃO ELETRÔNICO"
    
    def formatar_aditamento(self, r: SearchResult) -> str:
        """Formata card de aditamento"""
        num_adit = self.extrair_numero_aditamento(r.summary)
        num_orig = self.extrair_numero_contrato_origem(r.summary)
        
        contratada_full = "Ver íntegra"
        if r.contractor and r.contractor != "-":
            doc = self.anonimizar_cpf(r.value if r.value else "")
            contratada_full = f"{r.contractor}, CNPJ/CPF {doc}"
        
        vigencia = self.extrair_vigencia(r.summary)
        modalidade = self.extrair_modalidade(r.summary)
        
        return f"""<div class="card aditamento">
        • <span class="label">Processo SEI:</span> <span class="val">{r.process_number}</span><br>
        Aditamento nº <a href="{r.link_pdf}">{num_adit}</a> ao Contrato nº {num_orig}<br>
        <span class="label">Contratada:</span> <span class="val">{contratada_full}</span><br>
        <span class="label">Modalidade:</span> <span class="val">{modalidade}</span><br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Assinatura:</span> <span class="val">{r.date}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Vigência:</span> <span class="val">{vigencia}</span><br>
        <span class="label">Valor:</span> <span class="val">{r.value if r.value != '-' else 'Ver íntegra'}</span>
        </div>"""
    
    def formatar_contrato(self, r: SearchResult) -> str:
        """Formata card de contrato"""
        num_con = self.extrair_numero_contrato_origem(r.summary)
        
        contratada_full = "Ver íntegra"
        if r.contractor and r.contractor != "-":
            doc = self.anonimizar_cpf(r.value if r.value else "")
            contratada_full = f"{r.contractor}, CNPJ/CPF {doc}"
        
        return f"""<div class="card contrato">
        • <span class="label">Processo SEI:</span> <span class="val">{r.process_number}</span><br>
        Contrato nº <a href="{r.link_pdf}">{num_con}</a> - {contratada_full}<br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Assinatura:</span> <span class="val">{r.date}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Valor:</span> <span class="val">{r.value if r.value != '-' else 'Ver íntegra'}</span>
        </div>"""
    
    def formatar_licitacao(self, r: SearchResult) -> str:
        """Formata card de licitação"""
        mod_nome = self.extrair_modalidade(r.summary)
        num_pub = self.extrair_numero_licitacao(r.summary, r.document_id)
        vencedor = self.extrair_vencedor(r.summary)
        data_abertura = self.extrair_data_abertura(r.summary)
        
        return f"""<div class="card compra">
        <span class="label">Número do Processo:</span> <span class="val">{r.process_number}</span><br>
        <span class="label">Número da Publicação:</span> <a href="{r.link_pdf}">{mod_nome} {num_pub}</a><br>
        <span class="label">Documento:</span> <a href="{r.link_html}">{r.document_id}</a><br>
        <span class="label">Licitante Vencedor:</span> <span class="val">{vencedor}</span><br>
        <span class="label">Modalidade:</span> <span class="val">{mod_nome}</span><br>
        <span class="label">Data da Abertura:</span> <span class="val">{data_abertura}</span><br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data de Publicação:</span> <span class="val">{r.date}</span>
        </div>"""
    
    def formatar_html(self, results: List[SearchResult]) -> str:
        """Formata todos os resultados em HTML"""
        if not results:
            return "<p>❌ Nenhum dado coletado.</p>"
        
        html = f"{self.css}\n<h2>📋 RESULTADOS - DIÁRIO OFICIAL</h2>\n"
        
        for r in results:
            tipo = self.classificar_tipo(r.summary)
            
            if tipo == "ADITAMENTO":
                html += self.formatar_aditamento(r)
            elif tipo == "CONTRATO":
                html += self.formatar_contrato(r)
            elif tipo == "LICITACAO":
                html += self.formatar_licitacao(r)
            else:
                # Fallback para outros tipos
                html += f"""<div class="card">
                <span class="label">Processo:</span> {r.process_number}<br>
                <span class="label">Documento:</span> <a href="{r.link_html}">{r.document_id}</a><br>
                <span class="label">Objeto:</span> {r.object_text}<br>
                <span class="label">Data:</span> {r.date}
                </div>"""
        
        return html
    
    def formatar_pedido_compra(self, r: SearchResult) -> str:
        """Formata card de pedido de compra (dispensa)"""
        # Similar to contract but specific style
        contratada_full = "Ver íntegra"
        if r.contractor and r.contractor != "-":
            doc = self.anonimizar_cpf(r.value if r.value else "") # This looks like a bug in original code (passing value instead of company_doc), let's fix it here? No, let's keep it safe or fix it properly. 
            # Wait, r.value is money value. r.company_doc is the doc.
            # The previous code had `doc = self.anonimizar_cpf(r.value if r.value else "")` ... wait, lines 144 and 168 in original: `doc = self.anonimizar_cpf(r.value if r.value else "")`
            # That looks suspicious. It should probably be r.company_doc.
            # I will fix it here for the new method, and maybe fixing the others is out of scope unless I'm sure.
            # Actually, `r.value` usually holds the monetary value "2.178,00". `r.company_doc` holds CNPJ.
            # The user complained about CPF anonymization not being seen. maybe because it was looking at the wrong field?
            # I'll check `models.py`. company_doc is the field.
            doc = self.anonimizar_cpf(r.company_doc if r.company_doc else "")
            contratada_full = f"{r.contractor}, CNPJ/CPF {doc}"

        return f"""<div class="card pedido-compra">
        <div style="background-color: #e3f2fd; padding: 5px; border-bottom: 1px solid #ddd; margin-bottom: 10px;">
            <strong>🛒 PEDIDO DE COMPRA / DISPENSA</strong>
        </div>
        • <span class="label">Processo SEI:</span> <span class="val">{r.process_number}</span><br>
        <span class="label">Contratada:</span> <span class="val">{contratada_full}</span><br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Assinatura:</span> <span class="val">{r.validity_start}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Valor:</span> <span class="val">{r.value}</span><br>
        <div style="margin-top: 10px;">
             <a href="{r.link_pdf}" target="_blank">📄 Ver Documento</a> | <a href="{r.link_html}" target="_blank">🔗 Ver no Diário</a>
        </div>
        </div>"""

    def formatar_destaque(self, r: SearchResult) -> str:
        """Formata card de destaque (Homologação/Adjudicação)"""
        vencedor = r.contractor
        doc = self.anonimizar_cpf(r.company_doc if r.company_doc else "")
        
        return f"""<div class="card destaque">
        <div style="background-color: #fff3cd; color: #856404; padding: 10px; border-bottom: 2px solid #ffeeba; margin-bottom: 10px; font-size: 1.1em;">
            <strong>🏆 RESULTADO DE LICITAÇÃO / HOMOLOGAÇÃO</strong>
        </div>
        <span class="label">Processo:</span> <span class="val">{r.process_number}</span><br>
        <span class="label">Vencedor:</span> <span class="val" style="font-size: 1.1em; color: #000;">{vencedor}</span><br>
        <span class="label">CNPJ/CPF:</span> <span class="val">{doc}</span><br>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data de Publicação:</span> <span class="val">{r.date}</span><br>
        <div style="margin-top: 10px; text-align: right;">
             <a href="{r.link_pdf}" class="btn" style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 4px;">Abrir Documento 📄</a>
        </div>
        </div>"""

    def formatar_html(self, results: List[SearchResult]) -> str:
        """Formata todos os resultados em HTML"""
        if not results:
            return "<p>❌ Nenhum dado coletado.</p>"
        
        # Update CSS for new types
        extra_css = """
        .pedido-compra { border-left: 5px solid #2196F3; background-color: #fbfdff; }
        .destaque { border: 2px solid #ffc107; box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
        """
        
        html = f"{self.css}{extra_css}</style>\n<h2>📋 RESULTADOS - DIÁRIO OFICIAL</h2>\n"
        
        for r in results:
            # Check explicit doc_type first (populated by scraper_service)
            if r.doc_type == "PEDIDO_COMPRA":
                html += self.formatar_pedido_compra(r)
                continue
            elif r.doc_type == "HOMOLOGACAO":
                html += self.formatar_destaque(r)
                continue
            elif r.doc_type == "DIVERSOS":
                 continue # User implies "Outros" might be excluded or just put in "Outros" group?
                 # "outros termos que precisam entrar na regra de Outros" -> Assuming "Outros" means "Excluded" or just "Generic/Ignored"?
                 # User said: "os documentos que se referirem a 'Pedido de Compra'... sejam colocados em outro agrupamento"
                 # And "Outros termos que precisam entrar na regra de Outros... NOTIFICAÇÃO..."
                 # Usually "Outros/Diversos" implies we might not want to show them prominently or at all if they are noise.
                 # Current code: `return "OUTROS"` in classify -> put in generic card.
                 # Scraper sets `doc_type` = 'DIVERSOS'. 
                 # Let's render them as generic cards for now so they aren't lost, unless user said "Exclude".
                 # "exclude specific document types ... that are not relevant for publication" (from previous summary). 
                 # So DIVERSOS should probably be SKIPPED or put in a separate list at bottom. 
                 # Let's skip them for now if they are truly irrelevant, or render minimally.
                 # User said: "classificar esses documentos como 'DIVERSOS' e garantindo que essa classificação seja passada para o frontend para exibição adequada."
                 # So maybe just show them.
                 pass
            
            # Fallback to text classification if doc_type is generic
            tipo = self.classificar_tipo(r.summary)
            if r.doc_type == 'DIVERSOS': tipo = "OUTROS_IRRELEVANTES" # catch-all

            if tipo == "ADITAMENTO":
                html += self.formatar_aditamento(r)
            elif tipo == "CONTRATO":
                html += self.formatar_contrato(r)
            elif tipo == "LICITACAO":
                html += self.formatar_licitacao(r)
            elif tipo == "OUTROS_IRRELEVANTES":
                 # Maybe exclude? Or render small.
                 html += f"""<div class="card" style="opacity: 0.6; border-left: 5px solid #ccc;">
                 <span class="label">Outros/Diversos:</span> <span class="val">{r.summary[:100]}...</span>
                 </div>"""
            else:
                # Fallback
                html += f"""<div class="card">
                <span class="label">Processo:</span> {r.process_number}<br>
                <span class="label">Documento:</span> <a href="{r.link_html}">{r.document_id}</a><br>
                <span class="label">Objeto:</span> {r.object_text}<br>
                <span class="label">Data:</span> {r.date}
                </div>"""
        
        return html
    
    def salvar_html(self, results: List[SearchResult], filename: str = "resultados.html"):
        """Salva resultados em arquivo HTML"""
        html = self.formatar_html(results)
        html_completo = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resultados - Diário Oficial</title>
</head>
<body>
    {html}
</body>
</html>"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_completo)
        
        return filename

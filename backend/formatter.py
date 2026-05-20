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
            .compra { border-left: 5px solid #3b82f6; }
            .contrato { border-left: 5px solid #10b981; background-color: #fcfcfc; }
            .aditamento { border-left: 5px solid #f59e0b; background-color: #fff9f0; }
            .parceria { border-left: 5px solid #22c55e; background-color: #f6fff6; }
            .doacao { border-left: 5px solid #a855f7; background-color: #fdf6ff; }
            .destaque { border: 2px solid #ffc107; background-color: #fffdf0; }
            .label { font-weight: bold; color: #333; }
            .val { color: #000; }
            a { text-decoration: none; color: #2563eb; font-weight: bold; }
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
    
    def classificar_tipo(self, summary: str, doc_type: str = "OUTRO") -> str:
        """Classifica o tipo de publicação com base no contexto e no doc_type do backend"""
        # Se o backend já classificou como algo específico (não OUTRO ou DIVERSOS genérico), respeitamos
        if doc_type in ["ADITAMENTO", "CONTRATO", "PARCERIA", "ACORDO_COOPERACAO", "PEDIDO_COMPRA", "PREGAO", "HOMOLOGACAO", "DIVERSOS"]:
            return doc_type

        txt = summary.upper()
        
        # Hierarquia manual como fallback (Sincronizada com backend)
        if any(x in txt for x in ["ADITAMENTO", "TERMO ADITIVO", "APOSTILAMENTO"]):
            return "ADITAMENTO"
        
        if any(x in txt for x in ["CONTRATO Nº", "CONTRATO N.º", "CONTRATO N°", "FORMALIZAÇÃO DO CONTRATO", "EXTRATO DE CONTRATO"]):
            return "CONTRATO"

        if any(x in txt for x in ["ACORDO DE COOPERAÇÃO", "TERMO DE PARCERIA", "CONVÊNIO", "TERMO DE FOMENTO"]):
            return "PARCERIA"

        termos_diversos = ["ESCLARECIMENTO", "QUESTIONAMENTO", "IMPUGNAÇ", "IMPUGNAC", "NOTIFICAÇÃO", "DESPACHO", "PAGAMENTO"]
        if any(x in txt for x in termos_diversos):
            return "DIVERSOS"
        
        termos_fortes_pregao = [
            "PREGÃO", "PREGAO", "ABERTURA DE LICITAÇÃO", "AVISO DE LICITAÇÃO", 
            "HOMOLOGAÇÃO DE PREGÃO", "ATA DE REGISTRO DE PREÇOS", "SISTEMA DE REGISTRO DE PREÇOS"
        ]
        if any(x in txt for x in termos_fortes_pregao):
            return "PREGAO"
            
        if any(x in txt for x in ["DISPENSA"]):
            return "PEDIDO_COMPRA"
        
        return "DIVERSOS"
    
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
        return "Ver Edital"
    
    def extrair_vigencia(self, texto: str) -> str:
        """Extrai período de vigência"""
        m_inicio_fim = re.search(
            r'Data de início e t[ée]rmino.*?:?\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})\s*e\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})',
            texto, re.IGNORECASE
        )
        if m_inicio_fim:
            return f"{m_inicio_fim.group(1)} a {m_inicio_fim.group(2)}"
        
        m_periodo = re.search(
            r'período de\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})\s*a\s*([\d]{2}[/.][\d]{2}[/.][\d]{4})',
            texto, re.IGNORECASE
        )
        if m_periodo:
            return f"{m_periodo.group(1)} a {m_periodo.group(2)}"
        
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
        num_adit = r.amendment_number if r.amendment_number else self.extrair_numero_aditamento(r.summary)
        num_orig = r.parent_contract if r.parent_contract else self.extrair_numero_contrato_origem(r.summary)
        
        contratada_full = "Ver íntegra"
        if r.contractor and r.contractor != "-":
            doc = self.anonimizar_cpf(r.company_doc if r.company_doc else "")
            contratada_full = f"{r.contractor}, CNPJ/CPF {doc}"
        
        vigencia = f"{r.validity_start} a {r.validity_end}" if r.validity_end != "-" else self.extrair_vigencia(r.summary)
        modalidade = r.modality if r.modality != "-" else self.extrair_modalidade(r.summary)
        
        return f"""<div class="card aditamento">
        <div style="background-color: #fff9f0; padding: 5px; border-bottom: 1px solid #f59e0b; margin-bottom: 10px;">
            <strong>📑 TERMO DE ADITAMENTO / APOSTILAMENTO</strong>
        </div>
        • <span class="label">Processo SEI:</span> <span class="val">{r.process_number}</span><br>
        <strong>Aditamento nº </strong> <a href="{r.link_pdf}">{num_adit}</a> <strong>ao Contrato nº </strong> {num_orig}<br>
        <span class="label">Contratada:</span> <span class="val">{contratada_full}</span><br>
        <span class="label">Modalidade de Origem:</span> <span class="val">{modalidade}</span><br>
        <span class="label">Objeto do Aditamento:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Assinatura:</span> <span class="val">{r.validity_start}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Vigência/Prorrogação:</span> <span class="val">{vigencia}</span><br>
        <span class="label">Valor:</span> <span class="val">{r.value if r.value != '-' else 'Ver íntegra'}</span>
        </div>"""
    
    def formatar_contrato(self, r: SearchResult) -> str:
        """Formata card de contrato"""
        num_con = r.contract_number if r.contract_number != "-" else self.extrair_numero_contrato_origem(r.summary)
        
        contratada_full = "Ver íntegra"
        if r.contractor and r.contractor != "-":
            doc = self.anonimizar_cpf(r.company_doc if r.company_doc else "")
            contratada_full = f"{r.contractor}, CNPJ/CPF {doc}"
        
        modalidade = r.modality if r.modality != "-" else self.extrair_modalidade(r.summary)
        vigencia = f"{r.validity_start} a {r.validity_end}" if r.validity_end != "-" else "Ver íntegra"

        return f"""<div class="card contrato">
        <div style="background-color: #f0fff4; padding: 5px; border-bottom: 1px solid #10b981; margin-bottom: 10px;">
            <strong>📜 EXTRATO DE CONTRATO</strong>
        </div>
        • <span class="label">Processo SEI:</span> <span class="val">{r.process_number}</span><br>
        <strong>Contrato nº </strong> <a href="{r.link_pdf}">{num_con}</a> - {contratada_full}<br>
        <span class="label">Modalidade/Origem:</span> <span class="val">{modalidade}</span><br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Assinatura:</span> <span class="val">{r.validity_start}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Vigência:</span> <span class="val">{vigencia}</span><br>
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
    
    def formatar_pedido_compra(self, r: SearchResult) -> str:
        """Formata card de pedido de compra (dispensa)"""
        contratada_full = "Ver íntegra"
        if r.contractor and r.contractor != "-":
            doc = self.anonimizar_cpf(r.company_doc if r.company_doc else "")
            contratada_full = f"{r.contractor}, CNPJ/CPF {doc}"

        return f"""<div class="card compra">
        <div style="background-color: #e3f2fd; padding: 5px; border-bottom: 1px solid #ddd; margin-bottom: 10px;">
            <strong>🛒 PEDIDO DE COMPRA / DISPENSA</strong>
        </div>
        • <span class="label">Processo SEI:</span> <span class="val">{r.process_number}</span><br>
        <span class="label">Contratada:</span> <span class="val">{contratada_full}</span><br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Valor:</span> <span class="val">{r.value}</span><br>
        </div>"""

    def formatar_acordo_cooperacao(self, r: SearchResult) -> str:
        """Formata card de Acordo de Cooperação / Parceria"""
        formatted_num = r.contract_number if r.contract_number != "-" else "S/N"
        orgao_completo = r.contractor if r.contractor != "-" else "-"
        if r.company_doc and r.company_doc != "-":
            orgao_completo += f", CNPJ nº {r.company_doc}"

        vig_inicio = r.validity_start if r.validity_start != "-" else "-"
        vig_fim = r.validity_end if r.validity_end != "-" else "-"
        
        # Se for especificamente um Acordo de Cooperação, usamos o rótulo adequado
        label_principal = "🤝 ACORDO DE COOPERAÇÃO" if "ACORDO" in formatted_num.upper() or r.doc_type == "ACORDO_COOPERACAO" else "🤝 PARCERIA / CONVÊNIO"

        return f"""<div class="card parceria">
        <div style="background-color: #e8f5e9; padding: 5px; border-bottom: 1px solid #22c55e; margin-bottom: 10px;">
            <strong>{label_principal}</strong>
        </div>
        <span class="label">Número do processo:</span> <a href="{r.link_html}" target="_blank">{r.process_number}</a><br>
        <span class="label">Número do termo:</span> <a href="{r.link_pdf}" target="_blank">{formatted_num}</a><br>
        <span class="label">Nome da Organização:</span> <span class="val">{orgao_completo}</span><br>
        <span class="label">Objeto:</span> <span class="val">{r.object_text}</span><br>
        <span class="label">Data da Assinatura:</span> <span class="val">{r.data_assinatura if r.data_assinatura else r.validity_start}</span><br>
        <span class="label">Data da Publicação:</span> <span class="val">{r.date}</span><br>
        <span class="label">Vigência:</span> <span class="val">{vig_inicio} a {vig_fim}</span>
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
             <a href="{r.link_pdf}" class="btn" style="background-color: #2563eb; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none;">Abrir 📄</a>
        </div>
        </div>"""

    def formatar_html(self, results: List[SearchResult]) -> str:
        """Formata todos os resultados em HTML"""
        if not results:
            return "<p>❌ Nenhum dado coletado.</p>"
        
        html = f"{self.css}\n<h2>📋 RESULTADOS - DIÁRIO OFICIAL</h2>\n"
        
        for r in results:
            if r.doc_type == "PEDIDO_COMPRA":
                html += self.formatar_pedido_compra(r)
                continue
            elif r.doc_type == "HOMOLOGACAO":
                html += self.formatar_destaque(r)
                continue
            elif r.doc_type == "ACORDO_COOPERACAO" or r.doc_type == "PARCERIA":
                html += self.formatar_acordo_cooperacao(r)
                continue
            elif r.doc_type == "DOACAO":
                 html += f"""<div class="card doacao">
                 <span class="label">DOAÇÃO / COMODATO:</span> <span class="val">{r.process_number}</span><br>
                 <span class="label">Objeto:</span> {r.object_text}<br>
                 <span class="label">Data:</span> {r.date}
                 </div>"""
                 continue

            tipo = self.classificar_tipo(r.summary, r.doc_type)

            if tipo == "ADITAMENTO":
                html += self.formatar_aditamento(r)
            elif tipo == "CONTRATO" or r.doc_type == "EMPENHO":
                html += self.formatar_contrato(r)
            elif tipo == "LICITACAO" or r.doc_type == "PREGAO" or tipo == "PREGAO":
                html += self.formatar_licitacao(r)
            elif tipo == "DIVERSOS":
                 html += f"""<div class="card" style="opacity: 0.6; border-left: 5px solid #ccc;">
                 <span class="label">Diversos:</span> <span class="val">{r.summary[:150]}...</span>
                 </div>"""
            else:
                html += f"""<div class="card">
                <span class="label">Processo:</span> {r.process_number}<br>
                <span class="label">Objeto:</span> {r.object_text}<br>
                <span class="label">Data:</span> {r.date}
                </div>"""
        
        return html
    
    def salvar_html(self, results: List[SearchResult], filename: str = "resultados.html"):
        """Salva resultados em arquivo HTML"""
        html = self.formatar_html(results)
        html_completo = f"<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'><title>Resultados</title></head><body>{html}</body></html>"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_completo)
        return filename

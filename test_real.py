import sys
import os
sys.path.append(os.path.abspath('backend'))
from bs4 import BeautifulSoup
from backend.scraper_service import DiarioScraper

text_g = """
    <div class="conteudoMateria">
    Número do Processo: 7410.2026/0003378-0<br>
    Número da Publicação: PUBLICACAO ACORDO DE COOPERAÇÃO 001/2026<br>
    Documento: 157353067<br>
    Licitante Vencedor: -<br>
    Modalidade: -<br>
    Data da Abertura: -<br>
    Objeto: CELEBRAÇÃO DE ACORDO DE COOPERAÇÃO PARA A REALIZAÇÃO DE ATIVIDADES DE EDUCAÇÃO PARA O TRÂNSITO<br>
    Data de Publicação: 14/05/2026<br>

    FUNDACION MAPFRE, CNPJ 64.916.265/0001-17. Data da Assinatura: 05/05/2026. Vigência: 10/05/2026 a 03/10/2026.
    </div>
"""
soup = BeautifulSoup(text_g, 'html.parser')
scraper = DiarioScraper()
data = scraper.extract_details(soup, default_summary="")
print("tipo_doc:", data.get("tipo_doc"))
print("num_contrato:", data.get("num_contrato"))
print("contractor:", data.get("contractor"))
print("doc_fiscal:", data.get("doc_fiscal"))
print("validade_inicio:", data.get("validade_inicio"))
print("validade_fim:", data.get("validade_fim"))
print("modality:", data.get("modality"))

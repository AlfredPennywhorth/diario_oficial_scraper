import sys
import os
import re

# Adicionar o diretório backend ao path para importar os módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_service import DiarioScraper
from formatter import DiarioFormatter
from models import SearchResult

def run_tests():
    scraper = DiarioScraper()
    formatter = DiarioFormatter()
    
    print("=== INICIANDO TESTES DE CLASSIFICAÇÃO ===\n")

    # CENÁRIO A: Dispensa que formaliza contrato
    print("Cenário A: Dispensa + Formalização de Contrato")
    text_a = """
    Número do Processo: 7410.2026/0003170-2
    Número da Publicação: DISPENSA 272026
    Licitante Vencedor: EMPRESA BRASILEIRA DE CORREIOS E TELÉGRAFOS
    Modalidade: DISPENSA
    Objeto: referente à contratação de produtos e serviços... FORMALIZAÇÃO DO CONTRATO Nº 027/2026 (ECT - Contrato Múltiplo...)
    """
    data_a = {
        "contractor": "EMPRESA BRASILEIRA DE CORREIOS E TELÉGRAFOS",
        "modality": "DISPENSA",
        "sintese": text_a,
        "num_contrato": "DISPENSA 272026", # Simulando que veio do label
        "tipo_doc": "OUTRO"
    }
    scraper._extract_contract_info(text_a, data_a)
    scraper._classify_document(text_a, data_a)
    
    print(f"  -> Tipo: {data_a['tipo_doc']} (Esperado: CONTRATO)")
    print(f"  -> Número: {data_a['num_contrato']} (Esperado: 027/2026)")
    assert data_a['tipo_doc'] == 'CONTRATO'
    assert data_a['num_contrato'] == '027/2026'

    # CENÁRIO B: Dispensa sem contrato formal
    print("\nCenário B: Dispensa Simples")
    text_b = "DISPENSA DE LICITAÇÃO Nº 123/2026. Objeto: Compra de materiais de escritório."
    data_b = {"modality": "DISPENSA", "sintese": text_b, "num_contrato": "-", "tipo_doc": "OUTRO"}
    scraper._extract_contract_info(text_b, data_b)
    scraper._classify_document(text_b, data_b)
    print(f"  -> Tipo: {data_b['tipo_doc']} (Esperado: PEDIDO_COMPRA)")
    assert data_b['tipo_doc'] == 'PEDIDO_COMPRA'

    # CENÁRIO C: Termo Aditivo
    print("\nCenário C: Termo Aditivo")
    text_c = "EXTRATO DE TERMO DE ADITAMENTO Nº 054/25 ao Contrato nº 053/17. Objeto: Prorrogação."
    data_c = {"modality": "DISPENSA", "sintese": text_c, "num_contrato": "-", "tipo_doc": "OUTRO"}
    scraper._extract_contract_info(text_c, data_c)
    scraper._classify_document(text_c, data_c)
    print(f"  -> Tipo: {data_c['tipo_doc']} (Esperado: ADITAMENTO)")
    print(f"  -> Aditamento: {data_c.get('num_aditamento')} (Esperado: 054/25)")
    print(f"  -> Contrato Pai: {data_c.get('contrato_pai')} (Esperado: 053/17)")
    assert data_c['tipo_doc'] == 'ADITAMENTO'
    assert data_c['num_aditamento'] == '054/25'
    assert data_c['contrato_pai'] == '053/17'

    # CENÁRIO D: Pregão Comum
    print("\nCenário D: Pregão")
    text_d = "PREGÃO ELETRÔNICO Nº 100/2026. Objeto: Aquisição de veículos."
    data_d = {"modality": "PREGÃO", "sintese": text_d, "num_contrato": "-", "tipo_doc": "OUTRO"}
    scraper._extract_contract_info(text_d, data_d)
    scraper._classify_document(text_d, data_d)
    print(f"  -> Tipo: {data_d['tipo_doc']} (Esperado: PREGAO)")
    assert data_d['tipo_doc'] == 'PREGAO'

    # CENÁRIO E: Publicação Genérica
    print("\nCenário E: Publicação Genérica")
    text_e = "ESCLARECIMENTO Nº 01. Objeto: Resposta a questionamento sobre o edital."
    data_e = {"modality": "PREGÃO", "sintese": text_e, "num_contrato": "-", "tipo_doc": "OUTRO"}
    scraper._extract_contract_info(text_e, data_e)
    scraper._classify_document(text_e, data_e)
    print(f"  -> Tipo: {data_e['tipo_doc']} (Esperado: DIVERSOS)")
    assert data_e['tipo_doc'] == 'DIVERSOS'

    # CENÁRIO F: Acordo de Cooperação
    print("\nCenário F: Acordo de Cooperação")
    text_f = """
    Número do processo: 7410.2023/0001792-5
    ACORDO DE COOPERAÇÃO 013/25
    Partícipe: FUNDAÇÃO INSTITUTO DE MOLÉSTIAS DO APARELHO DIGESTIVO E DA NUTRIÇÃO
    CNPJ nº 61.062.212/0001-98
    Objeto: CELEBRAÇÃO DE ACORDO DE COOPERAÇÃO PARA IMPLANTAÇÃO DA SINALIZAÇÃO DE ORIENTAÇÃO DE TRÁFEGO SERVIÇOS - ÁREA VILA MARIANA
    Data da Assinatura: 17/11/2025
    Vigência: de 17/11/2025 a 17/11/2030
    """
    data_f = {"modality": "-", "sintese": text_f, "num_contrato": "-", "tipo_doc": "OUTRO"}
    scraper._extract_contract_info(text_f, data_f)
    scraper._classify_document(text_f, data_f)
    scraper._extract_dates(text_f, data_f)
    
    print(f"  -> Tipo: {data_f['tipo_doc']} (Esperado: ACORDO_COOPERACAO ou PARCERIA)")
    print(f"  -> Termo: {data_f['num_contrato']} (Esperado: 013/25)")
    print(f"  -> Início: {data_f['validade_inicio']} (Esperado: 17/11/2025)")
    print(f"  -> Fim: {data_f['validade_fim']} (Esperado: 17/11/2030)")
    
    assert data_f['tipo_doc'] in ['ACORDO_COOPERACAO', 'PARCERIA']
    assert '013/25' in data_f['num_contrato']
    assert data_f['validade_inicio'] == '17/11/2025'
    assert data_f['validade_fim'] == '17/11/2030'

    # CENÁRIO G: Acordo de Cooperação Real MAPFRE
    print("\nCenário G: Acordo de Cooperação MAPFRE")
    text_g = """
    Número do Processo: 7410.2026/0003378-0
    Número da Publicação: PUBLICACAO Acordo de Cooperação 001/26
    Documento: 157353067
    Licitante Vencedor: atos do Chamamento Público nº 01/2021 e AUTORIZO a celebração do Acordo de Cooperação nº 001/2026 com a FUNDACION MAPFRE
    Objeto: CELEBRAÇÃO DE ACORDO DE COOPERAÇÃO PARA A REALIZAÇÃO DE ATIVIDADES DE EDUCAÇÃO PARA O TRÂNSITO
    Modalidade: -
    Data da Abertura: -
    Data de Publicação: 14/05/2026
    ... texto completo ...
    CNPJ nº 64.916.265/0001-17. Data da Assinatura: 05/05/2026. Vigência: 10/05/2026 a 03/10/2026.
    """
    data_g = {"modality": "-", "sintese": text_g, "num_contrato": "PUBLICACAO Acordo de Cooperação 001/26", "tipo_doc": "OUTRO", "contractor": "atos do Chamamento Público nº 01/2021 e AUTORIZO a celebração do Acordo de Cooperação nº 001/2026 com a FUNDACION MAPFRE", "doc_fiscal": "-", "explicit_object": "CELEBRAÇÃO DE ACORDO DE COOPERAÇÃO PARA A REALIZAÇÃO DE ATIVIDADES DE EDUCAÇÃO PARA O TRÂNSITO"}
    
    # Simula extração estruturada
    scraper._extract_contractor(text_g, data_g)
    data_g['explicit_object'] = re.sub(r'(?i)^(?:CELEBRA[ÇC][ÃA]O\s+DE\s+ACORDO\s+DE\s+COOPERA[ÇC][ÃA]O\s+PARA\s+(?:A\s+)?|OBJETO:\s*)', '', data_g['explicit_object']).strip()
    
    scraper._extract_contract_info(text_g, data_g)
    scraper._classify_document(text_g, data_g)
    scraper._extract_dates(text_g, data_g)
    
    obj_text = data_g.get('explicit_object', '')
    
    print(f"  -> Tipo: {data_g['tipo_doc']} (Esperado: ACORDO_COOPERACAO)")
    print(f"  -> Termo: {data_g['num_contrato']} (Esperado: Acordo de Cooperação 001/26)")
    print(f"  -> Organização: {data_g['contractor']} (Esperado: FUNDACION MAPFRE)")
    print(f"  -> CNPJ: {data_g.get('doc_fiscal', '-')} (Esperado: 64.916.265/0001-17)")
    print(f"  -> Objeto: {obj_text} (Esperado: REALIZAÇÃO DE ATIVIDADES DE EDUCAÇÃO PARA O TRÂNSITO)")
    print(f"  -> Início: {data_g.get('validity_start', '')} (Esperado: 10/05/2026)")
    print(f"  -> Fim: {data_g.get('validity_end', '')} (Esperado: 03/10/2026)")
    
    assert data_g['tipo_doc'] == 'ACORDO_COOPERACAO'
    assert '001/26' in data_g['num_contrato']
    assert 'MAPFRE' in data_g['contractor']
    assert '64.916.265/0001-17' in data_g.get('doc_fiscal', '')
    assert 'CELEBRAÇÃO' not in obj_text.upper()
    assert data_g.get('validity_start') == '10/05/2026'
    assert data_g.get('validity_end') == '03/10/2026'
    assert data_g.get('data_assinatura') == '05/05/2026'

    print("\nCenário H: Pedido de Compra / Buffet")
    text_h = """
    AVISO-PROCESSO SEI Nº 7410.2026/0005666-7
    MODALIDADE: DISPENSA ELETRÔNICA Nº 14/2026
    Objeto: PRESTAÇÃO DE SERVIÇOS DE BUFFET PARA EVENTOS - CET 50 ANOS
    Data da Publicação: 14/05/2026
    """
    data_h = {"modality": "-", "sintese": text_h, "num_contrato": "Instrumento nº 14/2026", "tipo_doc": "OUTRO", "contractor": "-"}
    scraper._extract_contract_info(text_h, data_h)
    scraper._classify_document(text_h, data_h)
    print(f"  -> Tipo: {data_h['tipo_doc']} (Esperado: PEDIDO_COMPRA ou DISPENSA)")
    assert data_h['tipo_doc'] in ['PEDIDO_COMPRA', 'DISPENSA']

    print("\nCenário I: Pedido de Compra / Coletes")
    text_i = """
    AVISO-PROCESSO SEI Nº 7410.2026/0003746-8
    MODALIDADE: DISPENSA ELETRÔNICA Nº 13/2026
    Objeto: FORNECIMENTO DE COLETES REFLETIVOS E BANDEIRAS PARA TRAVESSIA DE ESCOLARES.
    Data da Publicação: 14/05/2026
    """
    data_i = {"modality": "-", "sintese": text_i, "num_contrato": "Instrumento nº 13/2026", "tipo_doc": "OUTRO", "contractor": "-"}
    scraper._extract_contract_info(text_i, data_i)
    scraper._classify_document(text_i, data_i)
    print(f"  -> Tipo: {data_i['tipo_doc']} (Esperado: PEDIDO_COMPRA ou DISPENSA)")
    assert data_i['tipo_doc'] in ['PEDIDO_COMPRA', 'DISPENSA']

    print("\nCenário J: Pedido de Compra / Filmagem")
    text_j = """
    AVISO-PROCESSO SEI Nº 7410.2026/0005668-3
    MODALIDADE: DISPENSA ELETRÔNICA Nº 15/2026
    Objeto: PRESTAÇÃO DE SERVIÇOS DE FILMAGEM E FOTOGRAFIA.
    Data da Publicação: 14/05/2026
    """
    data_j = {"modality": "-", "sintese": text_j, "num_contrato": "Instrumento nº 15/2026", "tipo_doc": "OUTRO", "contractor": "-"}
    scraper._extract_contract_info(text_j, data_j)
    scraper._classify_document(text_j, data_j)
    print(f"  -> Tipo: {data_j['tipo_doc']} (Esperado: PEDIDO_COMPRA ou DISPENSA)")
    assert data_j['tipo_doc'] in ['PEDIDO_COMPRA', 'DISPENSA']

    print("\n=== TODOS OS TESTES PASSARAM COM SUCESSO! ===")

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\n❌ ERRO NOS TESTES: {e}")
        sys.exit(1)

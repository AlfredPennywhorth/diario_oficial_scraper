import sys
import os
import re
import pytest

# Adicionar o diretório backend ao path para importar os módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_service import DiarioScraper
from formatter import DiarioFormatter
from models import SearchResult

def test_amendment_extraction_scenarios():
    scraper = DiarioScraper()

    # 1. ocorrência genérica de aditamento antes de ocorrência numerada
    text_generic_before = "AUTORIZO o aditamento do contrato... FORMALIZAÇÃO DO ADITAMENTO Nº 014/26"
    data = {"tipo_doc": "OUTRO", "num_aditamento": "", "contrato_pai": "", "num_contrato": "-"}
    scraper._extract_contract_info(text_generic_before, data)
    assert data["tipo_doc"] == "ADITAMENTO"
    assert data["num_aditamento"] == "014/26"

    # 2. FORMALIZAÇÃO ADITAMENTO Nº 002/2026
    text_002_2026 = "FORMALIZAÇÃO ADITAMENTO Nº 002/2026 REFERENTE AO CONTRATO"
    data = {"tipo_doc": "OUTRO", "num_aditamento": "", "contrato_pai": "", "num_contrato": "-"}
    scraper._extract_contract_info(text_002_2026, data)
    assert data["tipo_doc"] == "ADITAMENTO"
    assert data["num_aditamento"] == "002/2026"

    # 3. FORMALIZAÇÃO DO ADITAMENTO Nº 014/26
    text_014_26 = "FORMALIZAÇÃO DO ADITAMENTO Nº 014/26 - CONTRATO"
    data = {"tipo_doc": "OUTRO", "num_aditamento": "", "contrato_pai": "", "num_contrato": "-"}
    scraper._extract_contract_info(text_014_26, data)
    assert data["tipo_doc"] == "ADITAMENTO"
    assert data["num_aditamento"] == "014/26"

    # 4 & 5. número com ano de 4 dígitos, 2 dígitos e zeros preservados
    # Testando os diferentes termos individualmente para validar preservação de dígitos e zeros à esquerda
    for t, expected_num, expected_type in [
        ("TERMO DE ADITAMENTO Nº 003/2025", "003/2025", "ADITAMENTO"),
        ("ADITIVO Nº 054/25", "054/25", "ADITAMENTO"),
        ("APOSTILAMENTO Nº 007/2026", "007/2026", "APOSTILAMENTO"),
        ("APOSTILAMENTO Nº 0007/2026", "0007/2026", "APOSTILAMENTO"),
        ("ADITAMENTO N 014/26", "014/26", "ADITAMENTO"),
        ("ADITAMENTO No 014/26", "014/26", "ADITAMENTO"),
        ("ADITAMENTO N.º 014/26", "014/26", "ADITAMENTO"),
        ("ADITAMENTO N° 014/26", "014/26", "ADITAMENTO")
    ]:
        data = {"tipo_doc": "OUTRO", "num_aditamento": "", "contrato_pai": "", "num_contrato": "-"}
        scraper._extract_contract_info(t, data)
        assert data["tipo_doc"] == expected_type
        assert data["num_aditamento"] == expected_num

    # 7 & 18. aditamento realmente sem número continua vazio (caso Porto Seguro)
    text_porto_seguro = "Formalização do Aditamento do Contrato nº 25/25, celebrado com a empresa PORTO SEGURO"
    data = {"tipo_doc": "OUTRO", "num_aditamento": "", "contrato_pai": "", "num_contrato": "-"}
    scraper._extract_contract_info(text_porto_seguro, data)
    assert data["tipo_doc"] == "ADITAMENTO"
    assert data["num_aditamento"] == ""
    assert data["contrato_pai"] == "25/25"

    # 8. contrato pai não vira número do aditamento
    assert data["num_aditamento"] != data["contrato_pai"]

    # 9, 10, 11, 12. Pareceres, Contratos, Expedientes etc. não viram número do aditamento
    for name, text_ex in [
        ("Parecer SAJ nº 002/26", "Parecer SAJ nº 002/26"),
        ("Parecer Jurídico nº 054/26", "Parecer Jurídico nº 054/26"),
        ("Contrato nº 066/23", "Contrato nº 066/23"),
        ("Contrato nº 048/22", "Contrato nº 048/22"),
        ("Expediente nº 920/2022", "Expediente nº 920/2022")
    ]:
        data = {"tipo_doc": "OUTRO", "num_aditamento": "", "contrato_pai": "", "num_contrato": "-"}
        scraper._extract_contract_info(text_ex, data)
        assert data["num_aditamento"] == ""

    # 13. data estruturada de assinatura prevalece sobre início de vigência
    data_struct = {"data_assinatura": "03/06/2026", "validity_start": "-", "validity_end": "-"}
    text_sig_prev = "compreendidos entre 22/06/2026 a 22/06/2027"
    scraper._extract_dates(text_sig_prev, data_struct)
    assert data_struct["data_assinatura"] == "03/06/2026"
    assert data_struct["validity_start"] == "22/06/2026"
    assert data_struct["validity_end"] == "22/06/2027"

    # 17. valor explícito R$ 1.877.100,00 prevalece sobre “Sem impacto”
    text_val = "acrescendo ao mesmo o valor total de R$ 1.877.100,00"
    data_val = {"valor": "-"}
    scraper._extract_values(text_val, data_val)
    assert "1.877.100,00" in data_val["valor"]
    assert data_val["valor"] != "Sem impacto"

    # 19. número do aditamento vazio no backend é retornado como vazio
    data_empty = SearchResult(
        date="10/06/2026", term="Geral", process_number="123", document_id="1",
        summary="Extrato de Aditamento", object_text="Objeto", contractor="Empresa",
        company_doc="123", contract_number="-", validity_start="10/06/2026", validity_end="10/06/2027",
        value="-", link_html="h", link_pdf="p", modality="-", opening_date="-",
        amendment_number="", parent_contract="456", doc_type="ADITAMENTO", data_assinatura="10/06/2026"
    )
    formatter = DiarioFormatter()
    html_empty = formatter.formatar_aditamento(data_empty)
    assert html_empty is not None

def test_mundo_telecomunicacoes_real_case():
    scraper = DiarioScraper()
    text = "À vista das informações constantes no expediente, especialmente com base no Parecer SAJ nº 002/26, AUTORIZO o Aditamento ao Contrato nº 066/23. FORMALIZAÇÃO ADITAMENTO Nº 002/2026 REFERENTE AO CONTRATO Nº 066/2023, celebrado entre a CET e a empresa MUNDO TELECOMUNICAÇÕES E INFORMÁTICA LTDA. Formalizado em 08/06/2026."

    data = {
        "contratada": "-", "contractor": "-", "doc_fiscal": "-", "sintese": text,
        "num_contrato": "-", "integra_id": "", "data_assinatura": "",
        "prazo": "", "tipo_prazo": "", "valor": "-", "modality": "-",
        "opening_date": "-", "tipo_doc": "OUTRO", "num_aditamento": "",
        "contrato_pai": "", "validade_inicio": "-", "validade_fim": "-"
    }

    scraper._extract_contract_info(text, data)
    scraper._extract_dates(text, data)
    scraper._extract_contractor(text, data)
    scraper._classify_document(text, data)

    assert data["tipo_doc"] == "ADITAMENTO"
    assert data["num_aditamento"] == "002/2026"
    assert data["contrato_pai"] in ["066/23", "066/2023"]
    assert "MUNDO TELECOMUNICAÇÕES" in data["contractor"].upper()
    assert data["data_assinatura"] == "08/06/2026"

def test_simpress_real_case():
    scraper = DiarioScraper()
    text = "Parecer Jurídico nº 054/26. AUTORIZO o aditamento do contrato celebrado com a empresa SIMPRESS COMÉRCIO LOCAÇÃO E SERVIÇOS LTDA. FORMALIZAÇÃO DO ADITAMENTO Nº 014/26 - CONTRATO Nº 048/22, para prorrogar o prazo por 12 meses, compreendidos entre 22/06/2026 a 22/06/2027, acrescendo ao mesmo o valor total de R$ 1.877.100,00. Formalizado em 03/06/2026."

    data = {
        "contratada": "-", "contractor": "SIMPRESS COMÉRCIO LOCAÇÃO SERVIÇOS LTDA", "doc_fiscal": "0743251700107", "sintese": text,
        "num_contrato": "0482022", "integra_id": "", "data_assinatura": "03/06/2026",
        "prazo": "12", "tipo_prazo": "Mês", "valor": "-", "modality": "-",
        "opening_date": "-", "tipo_doc": "OUTRO", "num_aditamento": "",
        "contrato_pai": "", "validade_inicio": "-", "validade_fim": "-"
    }

    scraper._extract_contract_info(text, data)
    scraper._extract_dates(text, data)
    scraper._extract_contractor(text, data)
    scraper._extract_values(text, data)
    scraper._classify_document(text, data)

    assert data["tipo_doc"] == "ADITAMENTO"
    assert data["num_aditamento"] == "014/26"
    assert data["contrato_pai"] in ["048/22", "0482022"]
    assert data["data_assinatura"] == "03/06/2026"
    assert data["validity_start"] == "22/06/2026"
    assert data["validity_end"] == "22/06/2027"
    assert "1.877.100,00" in data["valor"]

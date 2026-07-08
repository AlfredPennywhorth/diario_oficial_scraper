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


def test_cnpj_validation_scenarios():
    from scraper_service import _normalize_cnpj_cpf

    # 1. Regra CPF (11 dígitos): deve seguir a regra atual, sem ser afetado
    assert _normalize_cnpj_cpf("34028316000") == "340.283.160-00"

    # 2. CNPJ repetitivo inválido
    assert _normalize_cnpj_cpf("1" * 14) == "1" * 14

    # 3. CNPJ de 14 dígitos com verificadores inválidos
    assert _normalize_cnpj_cpf("34028316000100") == "34028316000100"

    # 4. CNPJ de 13 dígitos com exatamente uma reconstrução válida (ex: SIMPRESS)
    assert _normalize_cnpj_cpf("0743251700107") == "07.432.517/0001-07"

    # 5. CNPJ de 13 dígitos com nenhuma reconstrução válida
    assert _normalize_cnpj_cpf("1234567890122") == "1234567890122"

    # 6. CNPJ de 13 dígitos com mais de uma hipótese válida
    assert _normalize_cnpj_cpf("1" * 13) == "1" * 13

    # 7. CNPJ formatado inválido no texto (preservar literalmente)
    assert _normalize_cnpj_cpf("11.111.111/1111-11") == "11.111.111/1111-11"


def test_number_normalization_scenarios():
    from formatter import DiarioFormatter

    formatter = DiarioFormatter()
    # Padrão X/Y com ano de 2 dígitos
    assert formatter._normalize_num_ano("17/26") == "017/2026"
    assert formatter._normalize_num_ano("03/23") == "003/2023"
    assert formatter._normalize_num_ano("25/25") == "025/2025"
    # Padrão X/Y com ano de 4 dígitos
    assert formatter._normalize_num_ano("017/2026") == "017/2026"
    # Acordo de cooperação
    assert formatter._normalize_num_ano("Acordo de Cooperação 12/23") == "Acordo de Cooperação 012/2023"
    # Valores nulos/vazios/travessões
    assert formatter._normalize_num_ano("—") == "S/N"
    assert formatter._normalize_num_ano("-") == "S/N"
    assert formatter._normalize_num_ano("S/N") == "S/N"
    # Número avulso
    assert formatter._normalize_num_ano("123") == "123"
    assert formatter._normalize_num_ano("5") == "005"


def test_formatter_by_document_type():
    from models import SearchResult
    from formatter import DiarioFormatter

    formatter = DiarioFormatter()

    # 1. CONTRATO: assinatura correta e vigência correta
    res_contrato = SearchResult(
        date="10/06/2026",
        term="Geral",
        process_number="7410.2023/0001792-5",
        document_id="12345",
        summary="Extrato de Contrato",
        object_text="Objeto do Contrato",
        contractor="CONTRATADA",
        company_doc="34028316000103",
        contract_number="048/22",
        validity_start="22/06/2026",
        validity_end="22/06/2027",
        value="R$ 1.000,00",
        link_html="http://link",
        link_pdf="http://link",
        modality="PREGÃO ELETRÔNICO",
        opening_date="-",
        amendment_number="",
        parent_contract="",
        doc_type="CONTRATO",
        data_assinatura="03/06/2026"
    )
    html_contrato = formatter.formatar_contrato(res_contrato)
    # Deve conter a data de assinatura correta (03/06/2026) e número formatado (048/2022)
    assert "Data da Assinatura:</span> <span class=\"val\">03/06/2026</span>" in html_contrato
    assert "Vigência:</span> <span class=\"val\">22/06/2026 a 22/06/2027</span>" in html_contrato
    assert "048/2022" in html_contrato

    # 2. ADITAMENTO: assinatura 03/06/2026, vigência 07/06/2026 a 07/06/2027, números normalizados, link completo
    res_adit = SearchResult(
        date="10/06/2026",
        term="Geral",
        process_number="7410.2023/0001816-6",
        document_id="12345",
        summary="Termo de Aditamento",
        object_text="Objeto do Aditamento",
        contractor="IMAGE X DESIGN LTDA ME",
        company_doc="05548348000131",
        contract_number="03/23",
        validity_start="07/06/2026",
        validity_end="07/06/2027",
        value="R$ 1.000,00",
        link_html="http://link",
        link_pdf="http://link",
        modality="PREGÃO ELETRÔNICO",
        opening_date="-",
        amendment_number="17/26",
        parent_contract="03/23",
        doc_type="ADITAMENTO",
        data_assinatura="03/06/2026"
    )
    html_adit = formatter.formatar_aditamento(res_adit)
    # Deve conter a data de assinatura correta (03/06/2026)
    assert "Data da Assinatura:</span> <span class=\"val\">03/06/2026</span>" in html_adit
    # Deve conter a vigência (07/06/2026 a 07/06/2027)
    assert "Vigência/Prorrogação:</span> <span class=\"val\">07/06/2026 a 07/06/2027</span>" in html_adit
    # Deve conter os números normalizados
    assert "017/2026" in html_adit
    assert "003/2023" in html_adit
    # O link deve cobrir apenas a expressão do aditamento
    assert 'href="http://link">Aditamento nº 017/2026</a> ao Contrato nº 003/2023' in html_adit


def test_html_table_parsing_scenarios():
    from bs4 import BeautifulSoup
    from scraper_service import DiarioScraper

    scraper = DiarioScraper()

    # th + td
    html_1 = "<table><tr><th>CNPJ</th><td>34.028.316/0001-86</td></tr></table>"
    soup_1 = BeautifulSoup(html_1, "html.parser")
    res_1 = {"doc_fiscal": "-"}
    scraper._extract_structured_fields(soup_1, res_1)
    assert res_1["doc_fiscal"] == "34.028.316/0001-86"

    # td + td
    html_2 = "<table><tr><td>CNPJ</td><td>34.028.316/0001-86</td></tr></table>"
    soup_2 = BeautifulSoup(html_2, "html.parser")
    res_2 = {"doc_fiscal": "-"}
    scraper._extract_structured_fields(soup_2, res_2)
    assert res_2["doc_fiscal"] == "34.028.316/0001-86"

    # label em strong
    html_3 = "<table><tr><td><strong>CNPJ:</strong></td><td>34.028.316/0001-86</td></tr></table>"
    soup_3 = BeautifulSoup(html_3, "html.parser")
    res_3 = {"doc_fiscal": "-"}
    scraper._extract_structured_fields(soup_3, res_3)
    assert res_3["doc_fiscal"] == "34.028.316/0001-86"

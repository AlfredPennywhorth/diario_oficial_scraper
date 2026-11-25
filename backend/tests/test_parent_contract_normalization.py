import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper_service import _normalize_parent_contract


def test_contrato_original_4923():
    texto = "prorrogar o Contrato n\u00ba 49/23 por mais 12 meses"
    assert _normalize_parent_contract("4923", texto) == "049/2023"


def test_contrato_original_com_barra():
    texto = "Aditamento ao Contrato n\u00ba 49/23"
    assert _normalize_parent_contract("49/23", texto) == "049/2023"


def test_contrato_original_sem_ano_confiavel():
    assert _normalize_parent_contract("49", "Prorroga??o contratual") == "49"


def test_nao_modificar_contrato_sem_correspondencia():
    texto = "Refer?ncia ao Contrato n\u00ba 49/23"
    assert _normalize_parent_contract("7824", texto) == "7824"


def test_parent_contract_with_truncated_summary_and_object():
    summary = "EXPEDIENTE 1032/22 DESPACHO DE AUTORIZA??O"
    object_text = (
        "prorrogar o Contrato n\u00ba 49/23 por mais 12 meses"
    )

    combined = f"{summary} {object_text}"

    assert _normalize_parent_contract("4923", combined) == "049/2023"

from datetime import datetime
from typing import List

from pydantic import BaseModel, field_validator, model_validator


class SearchRequest(BaseModel):
    start_date: str
    end_date: str
    terms: List[str]
    categories: List[str] = []
    dry_run: bool = False

    @field_validator('terms')
    @classmethod
    def clean_terms(cls, v: List[str]) -> List[str]:
        return [t.strip() for t in v if t and t.strip()]

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%d/%m/%Y")
        except ValueError as exc:
            raise ValueError("Data deve estar no formato DD/MM/AAAA") from exc
        return v

    @model_validator(mode='after')
    def validate_date_range(self) -> 'SearchRequest':
        d1 = datetime.strptime(self.start_date, "%d/%m/%Y")
        d2 = datetime.strptime(self.end_date, "%d/%m/%Y")
        if d1 > d2:
            raise ValueError("Data inicial não pode ser superior à data final")
        return self


class SearchResult(BaseModel):
    date: str
    term: str
    category: str = "Geral"
    process_number: str = "-"
    document_id: str = "-"
    summary: str
    object_text: str
    contractor: str = "-"
    company_doc: str = "-"
    value: str = "-"
    contract_number: str = "-"
    validity_start: str = "-"
    validity_end: str = "-"
    link_html: str
    link_pdf: str
    modality: str = "-"
    opening_date: str = "-"
    amendment_number: str = ""
    parent_contract: str = ""
    doc_type: str = "OUTRO"

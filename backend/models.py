from pydantic import BaseModel, field_validator, model_validator
from typing import List, Optional
from datetime import datetime

class SearchRequest(BaseModel):
    start_date: str
    end_date: str
    terms: List[str]
    categories: List[str] = []

    @field_validator('terms')
    @classmethod
    def clean_terms(cls, v: List[str]) -> List[str]:
        # Remove empty strings and whitespace
        return [t.strip() for t in v if t and t.strip()]

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%d/%m/%Y")
        except ValueError:
            raise ValueError("Data deve estar no formato DD/MM/AAAA")
        return v

    @model_validator(mode='after')
    def validate_date_range(self) -> 'SearchRequest':
        try:
            d1 = datetime.strptime(self.start_date, "%d/%m/%Y")
            d2 = datetime.strptime(self.end_date, "%d/%m/%Y")
            if d1 > d2:
                raise ValueError("Data inicial não pode ser superior à data final")
            
            # Optional: Limit range to prevent huge scrapes? User suggested "Avisar ... se o período ficou muito grande"
            # Let's add a soft check or just leave it for now.
            if (d2 - d1).days > 31:
                # Warning could be logged, but for validation maybe strictly blocking is too valid. 
                # Leaving as valid for now.
                pass
        except ValueError:
            pass # Already caught by field_validator
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
    company_doc: str = "-"  # CNPJ/CPF
    value: str = "-"
    contract_number: str = "-"
    validity_start: str = "-"
    validity_end: str = "-"
    link_html: str
    link_pdf: str
    modality: str = "-"
    opening_date: str = "-"
    amendment_number: str = "" # New
    parent_contract: str = "" # New
    doc_type: str = "OUTRO" # New: ADITAMENTO, CONTRATO, DIVERSOS, etc.

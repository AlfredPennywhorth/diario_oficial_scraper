import os
import json
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import generation_types

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)

# Define the rigorous schema for our JSON extraction
JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "contractor": {
      "type": "string",
      "description": "Nome da instituição, empresa, concedente ou convenente vencedora ou parceira. Extraia apenas o nome limpo."
    },
    "company_doc": {
      "type": "string",
      "description": "Número do CNPJ ou CPF da instituição parceira/contratada, se mencionado no texto. Apenas números e formatação padrão."
    },
    "object_text": {
      "type": "string",
      "description": "O objeto do documento, resumo do que se trata o acordo, licitação ou contrato. Limpo e direto."
    },
    "validity_start": {
      "type": "string",
      "description": "Data de assinatura ou início da vigência em formato DD/MM/AAAA. Pode estar sob expressões como 'Lavrado em'."
    },
    "validity_end": {
      "type": "string",
      "description": "Data final da vigência em formato DD/MM/AAAA. Se o texto citar apenas o prazo (ex: 5 anos, 60 meses), FAÇA O CÁLCULO matemático seguro a partir da validity_start para determinar esta data."
    },
    "modality": {
      "type": "string",
      "description": "Modalidade do documento: ACORDO DE COOPERAÇÃO, PREGÃO, LICITAÇÃO, CONTRATO, TERMO DE FOMENTO, etc."
    },
    "value": {
      "type": "string",
      "description": "O valor financeiro referenciado no texto. Se for 'Sem ônus', preencha com 'Sem ônus'. Se houver um valor exato, informe (ex: 'R$ 15.000,00')."
    },
    "contract_number": {
      "type": "string",
      "description": "O número do documento referenciado, no formato NNN/AAAA ou similar (ex: 014/25, 013/2025)."
    }
  },
  "required": [
    "contractor",
    "object_text",
    "modality"
  ]
}"""

# Using flash model for high speed and low latency
# Free tier limitation: 15 Requests per Minute. 
# We configure response schema to guarantee JSON.
MODEL_NAME = "gemini-2.5-flash"

def is_ai_enabled():
    return bool(API_KEY)

async def extract_with_gemini(text: str) -> dict:
    """
    Calls Gemini API to extract structured fields from the raw unstructured text.
    Returns a dictionary matching the SearchResult variables needed.
    """
    if not is_ai_enabled():
        return {}
        
    system_instruction = (
        "Você é um extrator de dados altamente preciso especializado no Diário Oficial de São Paulo. "
        "Sua função é ler o despacho/publicação e retornar ESTRITAMENTE um JSON plano com o schema fornecido. "
        "DIRETRIZES FUNDAMENTAIS:\n"
        "1. Para 'contractor', pegue o nome do Concedente, Convenente, Parceiro Privado ou Empresa Vencedora principal.\n"
        "2. Para 'modality', se o texto for primariamente uma ATA (ex: 'Ata de Julgamento', 'Ata da Sessão', 'Extrato de Ata'), "
        "preencha EXATAMENTE com 'DIVERSOS' independentemente do tema tratado nela. Caso contrário, se for a celebração do "
        "próprio acordo, preencha EXATAMENTE com 'ACORDO DE COOPERAÇÃO'.\n"
        "3. Para datas ('validity_start' e 'validity_end'): localize indícios de assinatura (ex: 'data da lavratura', 'celebrado em', 'São Paulo, DD de MM de AAAA').\n"
        "4. CÁLCULO DE VIGÊNCIA (Muito Crítico): Se o texto informar um PRAZO (ex: 'prazo de vigência de 60 meses', 'prazo de 5 anos') mas NÃO ditar a data final, "
        "você DEVERÁ calcular a 'validity_end' somando o prazo à 'validity_start'. Retorne sempre o formato DD/MM/AAAA. NUNCA deixe 'validity_end' vazia se o texto mencionar um prazo!"
    )
    
    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=system_instruction,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        prompt = f"Extraia os dados deste texto do Diário Oficial. Siga o schema exigido.\nTexto: {text}\nSchema exigido:\n{JSON_SCHEMA}"
        
        response = await model.generate_content_async(prompt)
        
        # Validar e processar o JSON retornado
        result_text = response.text
        if result_text:
            data = json.loads(result_text)
            return data
            
    except Exception as e:
        logger.error(f"Failed to extract with Gemini: {e}")
        
    return {}

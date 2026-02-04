import unittest
import sys
import os

# Add backend directory to sys.path to allow imports from models
sys.path.append(os.path.join(os.path.dirname(__file__)))

from scraper_service import DiarioScraper
from models import SearchResult
from bs4 import BeautifulSoup
import re

class TestScraperRefinements(unittest.TestCase):
    def setUp(self):
        self.scraper = DiarioScraper()

    def test_extract_object_fixes(self):
        # Case 1: Text with "que trata de " FORNECIMENTO..."" (With Quotes)
        text_with_quotes = """
        Processo SEI: 7410.2025/0016744-0
        Contrato nº 032 - SISTÉCNICA INFORMÁTICA
        que trata de "FORNECIMENTO DE 200 (DUZENTOS) MOUSES ÓPTICOS"
        Data da Assinatura: 09/01/2026
        """
        obj = self.scraper.extract_object(text_with_quotes)
        self.assertEqual(obj, "FORNECIMENTO DE 200 (DUZENTOS) MOUSES ÓPTICOS")

        # Case 2: Text WITHOUT Quotes (User scenario)
        text_no_quotes = """
        Processo SEI: 0086/25
        Objeto da licitação
        CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NA PRESTAÇÃO DE SERVIÇOS DE OUTSOURCING DE COMPUTADORES E NOTEBOOKS, ABRANGENDO O FORNECIMENTO, INSTALAÇÃO, SUBSTITUIÇÃO, MANUTENÇÃO E SUPORTE TÉCNICO DOS EQUIPAMENTOS.
        Processo
        """
        # Note: extract_object has logic for "OBJETO da licitação" too.
        obj2 = self.scraper.extract_object(text_no_quotes)
        self.assertTrue("OUTSOURCING" in obj2)
        
        # Case 3: "que trata de" without quotes (New requirement)
        text_trata_no_quotes = """
        Contrato 123
        que trata de AQUISICAO DE MESAS E CADEIRAS COM RODINHAS.
        Data de Assinatura
        """
        obj3 = self.scraper.extract_object(text_trata_no_quotes)
        self.assertEqual(obj3, "AQUISICAO DE MESAS E CADEIRAS COM RODINHAS")

    def test_explicit_object_priority(self):
        # Case: "Objeto da licitação" is extracted as explicit field (simulated)
        # We need to test the logic that prioritizes this. This logic is in 'scrape' method (hard to test here)
        # OR we can update extract_details to output it?
        # Actually, let's test that 'extract_details' captures it into the dict.
        
        html = """
        <div>
            <span class="label">Objeto da licitação</span>
            <span>CONTRATACAO DE PRIORIDADE ALTA</span>
            <div class="materia">
                Texto do Despacho...
                que trata de "COISA VELHA BAIXA PRIORIDADE"
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        details = self.scraper.extract_details(soup)
        self.assertEqual(details.get('explicit_object'), "CONTRATACAO DE PRIORIDADE ALTA")
        
        # We can't easily test the 'scrape' method loop where the priority happens without mocking,
        # but verifying extraction is the key part. The priority logic is just an 'if/else' added to scraper_service.py.

    def test_classification_pedido_compra(self):
        # Case: Modality DISPENSA -> Pedido de Compra
        # The scraper logic relies heavily on 'sintese' (full_text) to find modality if structured field isn't perfect.
        # Or structured field "Modalidade".
        
        html = """
        <div>
            <div class="materia">
            Processo 123
            Modalidade: DISPENSA
            Contratada: EMPRESA X
            que trata de "AQUISICAO X"
            </div>
        </div>
        """
        # Note: scraper.extract_details logic:
        # 1. Scans spans/divs/etc for "Modalidade" key.
        # 2. Or falls back to regex on full text.
        # In our mock HTML, everything is in one div. The loop over elements might miss 'Modalidade:' if it's just text inside one big div.
        # It relies on 'sintese' fallback which gets the whole text.
        # Then "Modality" regex runs on full text.
        
        soup = BeautifulSoup(html, "html.parser")
        details = self.scraper.extract_details(soup)
        
        # Validating it sets type to PEDIDO_COMPRA
        self.assertEqual(details.get('tipo_doc'), 'PEDIDO_COMPRA')

    def test_classification_destaque(self):
        # Case: Homologação
        html = """
        <div>
            <div class="materia">
            DESPACHO DE HOMOLOGAÇÃO
            2025/0001
            HOMOLOGO o procedimento licitatório
            Vencedor: EMPRESA VENCEDORA S.A., CNPJ 00.000.000/0001-00
            Objeto: CONSTRUCAO DE PONTE
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        details = self.scraper.extract_details(soup)
        
        self.assertEqual(details.get('tipo_doc'), 'HOMOLOGACAO')
        self.assertIn('EMPRESA VENCEDORA', details.get('contractor'))

    def test_classification_outros(self):
        # Case: Notificação de Penalidade
        html = """
        <div>
            <div class="materia">
            NOTIFICAÇÃO DE APLICAÇÃO DE PENALIDADE
            Aplicada a empresa X
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        details = self.scraper.extract_details(soup)
        self.assertEqual(details.get('tipo_doc'), 'DIVERSOS')

if __name__ == '__main__':
    unittest.main()

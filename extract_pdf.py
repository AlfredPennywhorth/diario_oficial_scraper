
from pypdf import PdfReader
import sys
import io

# Fix encoding for console output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    reader = PdfReader("2S Manual Botao Acesso a Informacao 14102025.pdf")
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    
    print(text)
except Exception as e:
    print(f"Error reading PDF: {e}")

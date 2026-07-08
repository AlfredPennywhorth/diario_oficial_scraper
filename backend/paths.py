import os
import sys
from pathlib import Path

def get_bundle_dir() -> Path:
    """
    Retorna o diretório base onde os arquivos empacotados pelo PyInstaller estão.
    Se estiver rodando congelado (one-file), é a pasta temporária sys._MEIPASS.
    Se estiver em desenvolvimento, retorna a raiz do projeto.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

def get_app_dir() -> Path:
    """
    Retorna o diretório onde o executável do usuário está de fato rodando (diretório persistente).
    Se estiver congelado, é a pasta onde o DiarioScraper.exe está localizado.
    Se estiver em desenvolvimento, retorna a raiz do projeto.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def get_frontend_dir() -> Path:
    """
    Retorna a localização da pasta frontend (somente leitura, dentro do bundle).
    """
    return get_bundle_dir() / "frontend"

def get_data_dir() -> Path:
    """
    Retorna o diretório base de dados do usuário (persistentes).
    """
    return get_app_dir()

def get_logs_dir() -> Path:
    """
    Retorna o diretório de logs (persistente, dentro do diretório do app).
    """
    logs_path = get_data_dir() / "logs"
    os.makedirs(logs_path, exist_ok=True)
    return logs_path

def get_partial_results_path() -> Path:
    """
    Retorna o caminho do arquivo de resultados parciais (persistente).
    """
    return get_data_dir() / "partial_results.json"

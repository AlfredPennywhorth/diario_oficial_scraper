"""
Sistema de versionamento e verificação de atualizações
"""
import aiohttp
import logging
from packaging import version
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Versão atual do aplicativo (atualizar manualmente a cada release)
VERSION = "1.3.0"

# URL do arquivo de metadados de versão no GitHub
# URL do arquivo de metadados de versão no GitHub
# INSTRUÇÕES: Após criar o repositório, substitua <usuario> e <repo> pelos valores corretos
# Exemplo: "https://raw.githubusercontent.com/seuusuario/diario-scraper/main/version.json"
VERSION_CHECK_URL = "https://raw.githubusercontent.com/AlfredPennywhorth/diario_oficial_scraper/main/version.json"

# Timeout para verificação de atualização (em segundos)
UPDATE_CHECK_TIMEOUT = 5


class UpdateInfo:
    """Informações sobre atualização disponível"""
    
    def __init__(self, data: dict):
        self.available = False
        self.current_version = VERSION
        self.latest_version = data.get("version", VERSION)
        self.download_url = data.get("download_url", "")
        self.changelog = data.get("changelog", [])
        self.release_date = data.get("release_date", "")
        self.critical = data.get("critical", False)
        
        # Comparar versões
        try:
            if version.parse(self.latest_version) > version.parse(self.current_version):
                self.available = True
        except Exception as e:
            logger.warning(f"Erro ao comparar versões: {e}")
    
    def to_dict(self) -> Dict:
        """Converte para dicionário para JSON response"""
        return {
            "available": self.available,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "download_url": self.download_url,
            "changelog": self.changelog,
            "release_date": self.release_date,
            "critical": self.critical,
        }


async def check_for_updates() -> Optional[UpdateInfo]:
    """
    Verifica se há atualização disponível
    
    Returns:
        UpdateInfo se conseguiu verificar, None se houve erro
    """
    # Validação: URL ainda não foi configurada
    if "<usuario>" in VERSION_CHECK_URL or "<repo>" in VERSION_CHECK_URL:
        logger.info("URL de verificação de atualização não configurada ainda")
        return None
    
    try:
        logger.info(f"Verificando atualizações... Versão atual: {VERSION}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                VERSION_CHECK_URL,
                timeout=aiohttp.ClientTimeout(total=UPDATE_CHECK_TIMEOUT)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    update_info = UpdateInfo(data)
                    
                    if update_info.available:
                        logger.info(
                            f"✨ Nova versão disponível: {update_info.latest_version} "
                            f"(atual: {update_info.current_version})"
                        )
                    else:
                        logger.info("✅ Aplicação está atualizada")
                    
                    return update_info
                else:
                    logger.warning(f"Falha ao verificar atualização: HTTP {response.status}")
                    return None
                    
    except aiohttp.ClientError as e:
        logger.warning(f"Erro de rede ao verificar atualização: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao verificar atualização: {e}", exc_info=True)
        return None


def get_current_version() -> str:
    """Retorna a versão atual do aplicativo"""
    return VERSION

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open, AsyncMock
import pytest

# Adicionar pasta backend e raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.main import app, get_clean_env, start_update

def test_get_clean_env_removes_meipass():
    # Simular ambiente frozen do PyInstaller
    dummy_meipass = r"C:\Users\Temp\_MEI12345"

    with patch.object(sys, 'frozen', True, create=True), \
         patch.object(sys, '_MEIPASS', dummy_meipass, create=True), \
         patch.dict(os.environ, {
             "PATH": f"C:\\Windows;{dummy_meipass};C:\\Windows\\System32",
             "_MEIPASS": dummy_meipass,
             "sys._MEIPASS": dummy_meipass
         }):

        clean_env = get_clean_env()

        # 1. Garante que chaves _MEIPASS foram removidas
        assert "_MEIPASS" not in clean_env
        assert "sys._MEIPASS" not in clean_env

        # 2. Garante que a pasta temporária do PyInstaller foi removida do PATH
        paths = clean_env.get("PATH", "").split(os.pathsep)
        assert dummy_meipass not in paths
        assert "C:\\Windows" in paths
        assert "C:\\Windows\\System32" in paths

def exists_side_effect(path):
    if "update.lock" in str(path):
        return False
    return True

@pytest.mark.asyncio
@patch("backend.main.check_for_updates")
@patch("aiohttp.ClientSession.get")
@patch("builtins.open", new_callable=mock_open)
@patch("zipfile.ZipFile")
@patch("os.path.exists", side_effect=exists_side_effect)
@patch("os.path.getsize")
@patch("subprocess.Popen")
@patch("asyncio.create_task")
async def test_start_update_popen_robustness(
    mock_create_task,
    mock_popen,
    mock_getsize,
    mock_exists,
    mock_zipfile,
    mock_open_file,
    mock_http_get,
    mock_check_updates
):
    # Setup mocks
    mock_getsize.return_value = 1024 * 1024  # 1MB

    # Mock check_for_updates
    mock_update_info = MagicMock()
    mock_update_info.available = True
    mock_update_info.latest_version = "1.5.3"
    mock_update_info.download_url = "https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.3/DiarioScraper-v1.5.3.zip"
    mock_check_updates.return_value = mock_update_info

    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status = 200
    # Usar AsyncMock para o método read() que é awaitado
    mock_response.content.read = AsyncMock(side_effect=[b"zipdata", b""])

    # Mock context managers
    mock_http_get.return_value.__aenter__.return_value = mock_response

    # Mock zipfile internal structure
    mock_zip_instance = MagicMock()
    mock_zip_instance.namelist.return_value = ["DiarioScraper.exe", "backend/main.py"]
    mock_zipfile.return_value.__enter__.return_value = mock_zip_instance

    # Mock subprocess process
    mock_process = MagicMock()
    mock_process.pid = 99999
    mock_popen.return_value = mock_process

    # Capturar e fechar a corrotina agendada para evitar RuntimeWarning
    scheduled_coroutines = []
    def capture_and_close_coroutine(coro):
        scheduled_coroutines.append(coro)
        coro.close()
        return MagicMock()
    mock_create_task.side_effect = capture_and_close_coroutine

    # Executar diretamente o endpoint como corotina assíncrona
    response = await start_update()

    # Assertions
    assert response["status"] == "success"

    # 1. Verificar se Popen foi chamado com argumentos corretos
    assert mock_popen.call_count == 1
    args, kwargs = mock_popen.call_args

    cmd_list = args[0]
    # Argumentos do PowerShell usam caminho absoluto
    assert "powershell.exe" in cmd_list[0].lower()
    assert os.path.isabs(cmd_list[0]) or cmd_list[0] == "powershell.exe"

    # Argumentos usam -NoProfile, -ExecutionPolicy Bypass, -WindowStyle Hidden
    assert "-NoProfile" in cmd_list
    assert "-ExecutionPolicy" in cmd_list
    assert "Bypass" in cmd_list
    assert "-WindowStyle" in cmd_list
    assert "Hidden" in cmd_list

    # Popen usa shell=False por padrão quando passamos lista e não definimos shell=True
    assert kwargs.get("shell", False) is False

    # close_fds=True para dissociação robusta
    assert kwargs.get("close_fds") is True

    # creationflags usa CREATE_NEW_CONSOLE (0x00000010) no Windows
    if sys.platform == "win32":
        import subprocess
        assert kwargs.get("creationflags") == subprocess.CREATE_NEW_CONSOLE

    # Encerramento agendado (asyncio.create_task chamado para shutdown)
    assert mock_create_task.call_count == 1
    assert len(scheduled_coroutines) == 1

@pytest.mark.asyncio
@patch("backend.main.check_for_updates")
@patch("aiohttp.ClientSession.get")
@patch("builtins.open", new_callable=mock_open)
@patch("zipfile.ZipFile")
@patch("os.path.exists", side_effect=exists_side_effect)
@patch("os.path.getsize")
@patch("subprocess.Popen")
@patch("asyncio.create_task")
async def test_start_update_popen_failure_does_not_schedule_shutdown(
    mock_create_task,
    mock_popen,
    mock_getsize,
    mock_exists,
    mock_zipfile,
    mock_open_file,
    mock_http_get,
    mock_check_updates
):
    # Setup mocks
    mock_getsize.return_value = 1024 * 1024  # 1MB

    # Mock check_for_updates
    mock_update_info = MagicMock()
    mock_update_info.available = True
    mock_update_info.latest_version = "1.5.3"
    mock_update_info.download_url = "https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.3/DiarioScraper-v1.5.3.zip"
    mock_check_updates.return_value = mock_update_info

    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.content.read = AsyncMock(side_effect=[b"zipdata", b""])
    mock_http_get.return_value.__aenter__.return_value = mock_response

    # Mock zipfile
    mock_zip_instance = MagicMock()
    mock_zip_instance.namelist.return_value = ["DiarioScraper.exe", "backend/main.py"]
    mock_zipfile.return_value.__enter__.return_value = mock_zip_instance

    # Mock subprocess Popen to throw FileNotFoundError (PowerShell missing)
    mock_popen.side_effect = FileNotFoundError("powershell.exe not found")

    # Executar e assegurar que lança HTTPException
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await start_update()

    # Assertions
    # Deve retornar erro HTTP 500 porque a inicialização do helper falhou
    assert exc_info.value.status_code == 500
    assert "Erro interno de atualização" in exc_info.value.detail

    # 1. Encerramento NÃO é agendado quando Popen falha
    assert mock_create_task.call_count == 0

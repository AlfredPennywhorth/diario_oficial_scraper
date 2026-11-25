import os
import sys
from unittest.mock import patch
import pytest

# Adicionar pasta backend e raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.main import app, get_clean_env, start_update

def test_get_clean_env_removes_meipass(tmp_path):
    # Simular ambiente frozen do PyInstaller
    dummy_meipass = str(tmp_path / '_MEI12345')
    system_path = str(tmp_path / 'system')
    extra_path = str(tmp_path / 'system32')

    with patch.object(sys, 'frozen', True, create=True), \
         patch.object(sys, '_MEIPASS', dummy_meipass, create=True), \
         patch.dict(os.environ, {
             "PATH": os.pathsep.join([system_path, dummy_meipass, extra_path]),
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
        assert system_path in paths
        assert extra_path in paths

@pytest.mark.asyncio
async def test_start_update_popen_robustness(tmp_path, monkeypatch):
    from fastapi import HTTPException

    installation = tmp_path / 'installed'
    (installation / 'logs').mkdir(parents=True)
    (installation / 'results').mkdir()
    files = {'DiarioScraper.exe': b'executable', '.env': b'config',
             'logs/app.log': b'log', 'results/result.json': b'result'}
    for name, content in files.items():
        (installation / name).write_bytes(content)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(installation / 'DiarioScraper.exe'))

    with patch('subprocess.Popen') as popen, patch('os._exit') as exit_process, \
         patch('asyncio.create_task') as create_task:
        with pytest.raises(HTTPException) as caught:
            await start_update()
        assert caught.value.status_code == 503
        popen.assert_not_called()
        exit_process.assert_not_called()
        create_task.assert_not_called()
    assert {path.relative_to(installation).as_posix(): path.read_bytes()
            for path in installation.rglob('*') if path.is_file()} == files

@pytest.mark.asyncio
async def test_start_update_popen_failure_does_not_schedule_shutdown():
    from fastapi import HTTPException

    with patch('subprocess.Popen', side_effect=FileNotFoundError('powershell.exe not found')) as popen, \
         patch('os._exit') as exit_process, patch('asyncio.create_task') as create_task, \
         patch('backend.main.check_for_updates') as check_updates:
        with pytest.raises(HTTPException) as caught:
            await start_update()
        assert caught.value.status_code == 503
        assert 'desativada por segurança' in caught.value.detail
        popen.assert_not_called()
        exit_process.assert_not_called()
        create_task.assert_not_called()
        check_updates.assert_not_called()

import hashlib
import json
import stat
import sys
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from secure_update import SecureUpdateError, TRUSTED_METADATA_URL, TrustedMetadata, apply_prepared_update, download_and_prepare, fetch_trusted_metadata, is_network_location, is_unc_path, validate_package


def package(tmp_path, files, package_format='multi-file', version='1.5.9'):
    manifest = {'version': version, 'format': package_format,
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    path = tmp_path / 'package.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('update-manifest.json', json.dumps(manifest))
        for name, content in files.items():
            archive.writestr(name, content)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_valid_package_and_digest(tmp_path):
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'exe', '_internal/runtime.dll': b'dll'})
    assert validate_package(path, digest, '1.5.9')['format'] == 'multi-file'
    with pytest.raises(SecureUpdateError, match='SHA-256'):
        validate_package(path, '0' * 64, '1.5.9')
    with pytest.raises(SecureUpdateError, match='Versão'):
        validate_package(path, digest, '1.5.10')


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'C:/outside', 'a/../outside', 'a\\outside', 'NUL.txt', 'COM¹.txt', 'LPT².log', 'CONOUT$', 'logs/file', 'backend/.env', 'partial_results_abc.json'])
def test_unsafe_paths_are_rejected(tmp_path, name):
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'exe', '_internal/runtime.dll': b'dll', name: b'data'})
    with pytest.raises(SecureUpdateError):
        validate_package(path, digest, '1.5.9')


def test_incomplete_package_is_rejected(tmp_path):
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'exe'}, package_format='multi-file')
    with pytest.raises(SecureUpdateError, match='multi-file'):
        validate_package(path, digest, '1.5.9')


def test_missing_and_invalid_package_are_rejected(tmp_path):
    with pytest.raises(SecureUpdateError, match='ausente ou inválido'):
        validate_package(tmp_path / 'missing.zip', 'a' * 64, '1.5.9')
    invalid = tmp_path / 'invalid.zip'
    invalid.write_bytes(b'not a zip')
    digest = hashlib.sha256(invalid.read_bytes()).hexdigest()
    with pytest.raises(SecureUpdateError, match='ausente ou inválido'):
        validate_package(invalid, digest, '1.5.9')


def test_zip_rejects_case_collisions_and_symlinks(tmp_path):
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'exe', '_internal/A.dll': b'a', '_internal/a.dll': b'b'})
    with pytest.raises(SecureUpdateError, match='duplicado'):
        validate_package(path, digest, '1.5.9')
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'exe', '_internal/runtime.dll': b'dll'})
    with zipfile.ZipFile(path, 'a') as archive:
        entry = zipfile.ZipInfo('_internal/link')
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, 'runtime.dll')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SecureUpdateError, match='inseguro'):
        validate_package(path, digest, '1.5.9')


@pytest.mark.asyncio
async def test_metadata_requires_authenticated_origin_and_sha256():
    metadata = {'version': '1.5.9', 'sha256': 'a' * 64,
                'download_url': 'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip'}
    response = MagicMock(status=200, url=TRUSTED_METADATA_URL)
    async def content():
        yield json.dumps(metadata).encode()
    response.content.iter_chunked = lambda size: content()
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('secure_update.aiohttp.ClientSession', return_value=manager):
        trusted = await fetch_trusted_metadata('1.5.8')
        assert trusted.sha256 == 'a' * 64
        session.get.assert_called_with(TRUSTED_METADATA_URL, allow_redirects=False)
        metadata.pop('sha256')
        with pytest.raises(SecureUpdateError):
            await fetch_trusted_metadata('1.5.8')
        metadata['sha256'] = 'a' * 64
        response.status = 302
        with pytest.raises(SecureUpdateError, match='Origem'):
            await fetch_trusted_metadata('1.5.8')


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_digest', [False, True])
async def test_download_prepares_only_after_hash_validation(tmp_path, bad_digest):
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'exe', '_internal/runtime.dll': b'dll'})
    payload = path.read_bytes()
    metadata = TrustedMetadata('1.5.9', '0' * 64 if bad_digest else digest,
                               'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip')
    response = MagicMock(status=200)
    async def content():
        yield payload
    response.content.iter_chunked = lambda size: content()
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    workspace = tmp_path / 'workspace'
    with patch('secure_update.aiohttp.ClientSession', return_value=manager):
        if bad_digest:
            with pytest.raises(SecureUpdateError, match='SHA-256'):
                await download_and_prepare(metadata, workspace)
            assert not (workspace / 'stage').exists()
        else:
            stage, manifest = await download_and_prepare(metadata, workspace)
            assert (stage / 'DiarioScraper.exe').read_bytes() == b'exe'
            assert (stage / '_internal/runtime.dll').read_bytes() == b'dll'
            assert manifest['version'] == '1.5.9'


@pytest.mark.asyncio
async def test_download_enforces_extraction_limits(tmp_path):
    path, digest = package(tmp_path, {'DiarioScraper.exe': b'executable', '_internal/runtime.dll': b'dll'})
    payload = path.read_bytes()
    metadata = TrustedMetadata('1.5.9', digest,
                               'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip')
    response = MagicMock(status=200)
    async def content():
        yield payload
    response.content.iter_chunked = lambda size: content()
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('secure_update.aiohttp.ClientSession', return_value=manager), \
         patch('secure_update.MAX_FILE_SIZE', 4):
        with pytest.raises(SecureUpdateError, match='limite'):
            await download_and_prepare(metadata, tmp_path / 'workspace')


@pytest.mark.asyncio
async def test_download_rejects_untrusted_redirect(tmp_path):
    metadata = TrustedMetadata('1.5.9', 'a' * 64,
                               'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip')
    response = MagicMock(status=302, headers={'Location': 'http://example.com/package.zip'})
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('secure_update.aiohttp.ClientSession', return_value=manager):
        with pytest.raises(SecureUpdateError, match='origem não permitida'):
            await download_and_prepare(metadata, tmp_path / 'workspace')
    assert not (tmp_path / 'workspace' / 'stage').exists()


@pytest.mark.asyncio
async def test_download_failure_never_prepares_stage(tmp_path):
    metadata = TrustedMetadata('1.5.9', 'a' * 64,
                               'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip')
    response = MagicMock(status=403)
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch('secure_update.aiohttp.ClientSession', return_value=manager):
        with pytest.raises(SecureUpdateError, match='HTTP 403'):
            await download_and_prepare(metadata, tmp_path / 'workspace')
    assert not (tmp_path / 'workspace' / 'stage').exists()


def make_installation(tmp_path, old_format, new_format):
    install = tmp_path / 'installed'
    stage = tmp_path / 'stage'
    install.mkdir()
    stage.mkdir()
    old_files = {'DiarioScraper.exe': b'old executable'}
    new_files = {'DiarioScraper.exe': b'new executable'}
    if old_format == 'multi-file':
        old_files['_internal/old.dll'] = b'old runtime'
    if new_format == 'multi-file':
        new_files['_internal/new.dll'] = b'new runtime'
    for root, files in ((install, old_files), (stage, new_files)):
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    persistent = {
        '.env': b'secret', 'logs/session.log': b'log', 'results/result.txt': b'result',
        'exports/export.csv': b'export', 'backups/old.txt': b'backup',
        'partial_results.json': b'partial', 'partial_results_123.json': b'partial newer',
        'backend/settings.json': b'settings', '_internal/other/user.dat': b'user data',
    }
    for name, content in persistent.items():
        path = install / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    def manifest(version, package_format, files):
        return {'version': version, 'format': package_format,
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    return install, stage, tmp_path / 'backup', manifest('1.5.8', old_format, old_files), manifest('1.5.9', new_format, new_files), persistent


@pytest.mark.parametrize(('old_format', 'new_format'), [
    ('multi-file', 'multi-file'), ('multi-file', 'one-file'),
    ('one-file', 'multi-file'), ('one-file', 'one-file'),
])
def test_format_migrations_preserve_persistent_files(tmp_path, old_format, new_format):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, old_format, new_format)
    process = MagicMock()
    process.stop.return_value = True
    process.healthy.return_value = True
    assert apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process) == backup
    assert (install / 'DiarioScraper.exe').read_bytes() == b'new executable'
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content
    if old_format == 'multi-file':
        assert (backup / '_internal/old.dll').read_bytes() == b'old runtime'
        assert not (install / '_internal/old.dll').exists()
    if new_format == 'multi-file':
        assert (install / '_internal/new.dll').read_bytes() == b'new runtime'
    process.healthy.assert_called_once_with('1.5.9')


def test_unknown_collision_and_missing_inventory_abort_without_removing_data(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'one-file', 'multi-file')
    collision = install / '_internal/new.dll'
    collision.write_bytes(b'unknown data')
    process = MagicMock()
    with pytest.raises(SecureUpdateError, match='Colisão'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert collision.read_bytes() == b'unknown data'
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    process.stop.assert_not_called()
    with pytest.raises(SecureUpdateError, match='instalação paralela'):
        apply_prepared_update(install, stage, backup, None, new_manifest, process)


def test_case_insensitive_collision_is_rejected(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'one-file', 'multi-file')
    collision = install / '_internal/NEW.DLL'
    collision.write_bytes(b'unknown data')
    process = MagicMock()
    with pytest.raises(SecureUpdateError, match='Colisão'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert collision.read_bytes() == b'unknown data'
    process.stop.assert_not_called()


def test_case_insensitive_parent_collision_is_rejected(tmp_path):
    install = tmp_path / 'installed'
    stage = tmp_path / 'stage'
    install.mkdir()
    stage.mkdir()
    (install / 'DiarioScraper.exe').write_bytes(b'old')
    (install / '_Internal').mkdir()
    (install / '_Internal' / 'user.dat').write_bytes(b'preserve')
    (stage / 'DiarioScraper.exe').write_bytes(b'new')
    (stage / '_internal').mkdir()
    (stage / '_internal' / 'runtime.dll').write_bytes(b'dll')
    old = {'version': '1.5.8', 'format': 'one-file', 'files': {'DiarioScraper.exe': hashlib.sha256(b'old').hexdigest()}}
    new = {'version': '1.5.9', 'format': 'multi-file', 'files': {'DiarioScraper.exe': hashlib.sha256(b'new').hexdigest(), '_internal/runtime.dll': hashlib.sha256(b'dll').hexdigest()}}
    process = MagicMock()
    with pytest.raises(SecureUpdateError, match='Colisão de caixa em diretório'):
        apply_prepared_update(install, stage, tmp_path / 'backup', old, new, process)
    assert (install / '_Internal' / 'user.dat').read_bytes() == b'preserve'
    process.stop.assert_not_called()


def test_interrupted_backup_leaves_installation_unchanged(tmp_path):
    import secure_update
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'multi-file', 'multi-file')
    process = MagicMock()
    original_copy = secure_update._copy_verified
    copies = []
    def fail_second_copy(source, destination, digest):
        copies.append(destination)
        if len(copies) == 2:
            raise PermissionError('backup denied')
        return original_copy(source, destination, digest)
    with patch('secure_update._copy_verified', side_effect=fail_second_copy):
        with pytest.raises(SecureUpdateError, match='Backup incompleto'):
            apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert len(copies) == 2 and copies[0].is_file()
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content
    process.stop.assert_not_called()


def test_stop_failure_requires_manual_restart_without_modification(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'one-file', 'one-file')
    process = MagicMock()
    process.stop.side_effect = PermissionError('cannot confirm shutdown')
    with pytest.raises(SecureUpdateError, match='reinicie a versão anterior manualmente'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    assert (backup / 'DiarioScraper.exe').read_bytes() == b'old executable'
    process.start.assert_not_called()


def test_unconfirmed_stop_never_replaces_files(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'one-file', 'one-file')
    process = MagicMock()
    process.stop.return_value = False
    with pytest.raises(SecureUpdateError, match='Encerramento do processo não confirmado'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content
    process.start.assert_not_called()


@pytest.mark.parametrize('failure', ['replace', 'start', 'health'])
def test_failure_rolls_back_and_verifies_old_version(tmp_path, failure):
    import secure_update
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'multi-file', 'multi-file')
    process = MagicMock()
    process.stop.return_value = True
    process.healthy.return_value = True
    if failure == 'start':
        process.start.side_effect = [OSError('start failed'), None]
    if failure == 'health':
        process.healthy.side_effect = [False, True]
    original_replace = secure_update._replace_verified
    calls = []
    def fail_second_replace(source, target, digest):
        calls.append(target)
        if failure == 'replace' and len(calls) == 2:
            raise PermissionError('replace denied')
        return original_replace(source, target, digest)
    with patch('secure_update._replace_verified', side_effect=fail_second_replace):
        with pytest.raises(SecureUpdateError, match='versão anterior restaurada'):
            apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    assert (install / '_internal/old.dll').read_bytes() == b'old runtime'
    assert not (install / '_internal/new.dll').exists()
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content
    assert process.healthy.call_args.args == ('1.5.8',)
    if failure in ('start', 'health'):
        assert process.stop.call_count == 2


def test_recovery_failure_requires_manual_restoration(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'one-file', 'one-file')
    process = MagicMock()
    process.healthy.return_value = False
    process.stop.side_effect = [True, PermissionError('cannot stop new process')]
    with pytest.raises(SecureUpdateError, match='restaure manualmente'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert (backup / 'DiarioScraper.exe').read_bytes() == b'old executable'
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content


def test_unconfirmed_new_process_stop_requires_manual_recovery(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'one-file', 'one-file')
    process = MagicMock()
    process.stop.side_effect = [True, False]
    process.healthy.return_value = False
    with pytest.raises(SecureUpdateError, match='restaure manualmente'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert (install / 'DiarioScraper.exe').read_bytes() == b'new executable'
    assert (backup / 'DiarioScraper.exe').read_bytes() == b'old executable'
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content


def test_wrong_restart_version_rolls_back_and_checks_previous_version(tmp_path):
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'multi-file', 'multi-file')
    process = MagicMock()
    process.stop.return_value = True
    process.healthy.side_effect = lambda expected: expected == '1.5.8'
    with pytest.raises(SecureUpdateError, match='versão anterior restaurada'):
        apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert [call.args[0] for call in process.healthy.call_args_list] == ['1.5.9', '1.5.8']
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content


@pytest.mark.parametrize('when', ['before', 'after'])
def test_interruption_during_replacement_restores_known_files(tmp_path, when):
    import secure_update
    install, stage, backup, old_manifest, new_manifest, persistent = make_installation(tmp_path, 'multi-file', 'multi-file')
    process = MagicMock()
    process.stop.return_value = True
    process.healthy.return_value = True
    original_replace = secure_update._replace_verified
    calls = []

    def interrupt_once(source, target, digest):
        calls.append(target)
        if len(calls) == 1:
            if when == 'after':
                original_replace(source, target, digest)
            raise KeyboardInterrupt('interrupted during replacement')
        return original_replace(source, target, digest)

    with patch('secure_update._replace_verified', side_effect=interrupt_once):
        with pytest.raises(SecureUpdateError, match='versão anterior restaurada'):
            apply_prepared_update(install, stage, backup, old_manifest, new_manifest, process)
    assert (install / 'DiarioScraper.exe').read_bytes() == b'old executable'
    assert (install / '_internal/old.dll').read_bytes() == b'old runtime'
    assert not (install / '_internal/new.dll').exists()
    for name, content in persistent.items():
        assert (install / name).read_bytes() == content
    process.healthy.assert_called_with('1.5.8')


def test_legacy_update_endpoint_is_disabled():
    from fastapi.testclient import TestClient
    from backend.main import app
    response = TestClient(app).post('/api/start-update')
    assert response.status_code == 503
    assert 'desativada por segurança' in response.json()['detail']


@pytest.mark.parametrize(('path', 'expected'), [
    (r'\\server\share\app\DiarioScraper.exe', True),
    ('//server/share/app/DiarioScraper.exe', True),
    (r'\\?\UNC\server\share\app', True),
    (r'\\?\C:\app\DiarioScraper.exe', False),
    (r'C:\app\DiarioScraper.exe', False),
])
def test_unc_detection(path, expected):
    assert is_unc_path(path) is expected


@pytest.mark.parametrize(('drive_type', 'expected'), [(3, False), (4, True), (0, True), (1, True)])
def test_windows_mapped_drive_detection(monkeypatch, drive_type, expected):
    monkeypatch.setattr(sys, 'platform', 'win32')
    with patch('secure_update._windows_drive_type', return_value=drive_type) as query:
        assert is_network_location(r'Z:\app\DiarioScraper.exe') is expected
        query.assert_called_once_with('Z:')


@pytest.mark.asyncio
async def test_unc_preparation_is_blocked_before_download():
    metadata = TrustedMetadata('1.5.9', 'a' * 64,
                               'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip')
    with patch('secure_update.aiohttp.ClientSession') as session:
        with pytest.raises(SecureUpdateError, match='administração centralizada'):
            await download_and_prepare(metadata, r'\\server\share\staging')
    session.assert_not_called()


@pytest.mark.asyncio
async def test_resolved_network_preparation_parent_is_blocked_before_write(tmp_path):
    metadata = TrustedMetadata('1.5.9', 'a' * 64,
                               'https://github.com/AlfredPennywhorth/diario_oficial_scraper/releases/download/v1.5.9/DiarioScraper-v1.5.9.zip')
    workspace = tmp_path / 'stage'
    with patch('secure_update.is_network_location', side_effect=[False, True]), \
         patch('secure_update.aiohttp.ClientSession') as session:
        with pytest.raises(SecureUpdateError, match='administração centralizada'):
            await download_and_prepare(metadata, workspace)
    assert not workspace.exists()
    session.assert_not_called()


def test_unc_application_update_is_blocked_without_side_effects(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', r'\\server\share\DiarioScraper.exe')
    with patch('subprocess.Popen') as popen, patch('os._exit') as exit_process:
        client = TestClient(app)
        response = client.post('/api/start-update')
        assert response.status_code == 503
        assert 'administrada centralmente' in response.json()['detail']
        assert client.get('/api/version').status_code == 200
        assert client.get('/').status_code == 200
        popen.assert_not_called()
        exit_process.assert_not_called()


def test_unc_engine_is_blocked_before_filesystem_operations(tmp_path):
    process = MagicMock()
    with pytest.raises(SecureUpdateError, match='administração centralizada'):
        apply_prepared_update(r'\\server\share\app', tmp_path / 'stage', tmp_path / 'backup', {}, {}, process)
    assert list(tmp_path.iterdir()) == []
    process.stop.assert_not_called()


def test_resolved_network_engine_path_is_blocked_before_backup(tmp_path):
    install = tmp_path / 'install'
    stage = tmp_path / 'stage'
    install.mkdir()
    stage.mkdir()
    process = MagicMock()
    with patch('secure_update.is_network_location', side_effect=[False, False, False, True]):
        with pytest.raises(SecureUpdateError, match='administração centralizada'):
            apply_prepared_update(install, stage, tmp_path / 'backup', {}, {}, process)
    assert not (tmp_path / 'backup').exists()
    process.stop.assert_not_called()
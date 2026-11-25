import hashlib
import hmac
import json
import logging
import ntpath
import os
import re
import shutil
import stat
import tempfile
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import aiohttp
from packaging.version import InvalidVersion, Version


class SecureUpdateError(Exception):
    pass


MANIFEST_NAME = 'update-manifest.json'
MAX_FILE_SIZE = 512 * 1024 * 1024
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024
WINDOWS_RESERVED = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$', *(f'com{number}' for number in range(1, 10)), *(f'lpt{number}' for number in range(1, 10))}
PERSISTENT_DIRS = {'logs', 'results', 'exports', 'backups', 'update'}
PERSISTENT_NAMES = {'.env', 'partial_results.json', 'config.json', 'settings.json', 'user_config.json'}
TRUSTED_METADATA_URL = 'https://raw.githubusercontent.com/AlfredPennywhorth/diario_oficial_scraper/main/version.json'
logger = logging.getLogger(__name__)


def is_unc_path(path):
    normalized = os.fspath(path).replace('/', '\\')
    if not normalized.startswith('\\\\'):
        return False
    if re.match(r'^\\\\[?.]\\[A-Za-z]:\\', normalized):
        return False
    return True


def _windows_drive_type(drive):
    from ctypes import windll
    return windll.kernel32.GetDriveTypeW(drive + '\\')


def is_network_location(path):
    if is_unc_path(path):
        return True
    if sys.platform != 'win32':
        return False
    drive = ntpath.splitdrive(ntpath.abspath(os.fspath(path)))[0]
    if not drive:
        return True
    if drive.startswith(('\\\\?\\', '\\\\.\\')):
        drive = drive[4:]
    try:
        return _windows_drive_type(drive) in (0, 1, 4)
    except (AttributeError, OSError):
        return True


@dataclass(frozen=True)
class TrustedMetadata:
    version: str
    sha256: str
    download_url: str


async def fetch_trusted_metadata(current_version):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=True) as session:
            async with session.get(TRUSTED_METADATA_URL, allow_redirects=False) as response:
                if response.status != 200 or str(response.url) != TRUSTED_METADATA_URL:
                    raise SecureUpdateError('Origem dos metadados não autenticada ou indisponível')
                content = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    content.extend(chunk)
                    if len(content) > 256 * 1024:
                        raise SecureUpdateError('Metadados de atualização excedem o limite permitido')
        data = json.loads(content)
        version = data['version']
        digest = data['sha256']
        download_url = data['download_url']
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise SecureUpdateError('Versão de destino inválida')
        if Version(version) <= Version(current_version):
            raise SecureUpdateError('A versão de destino não é superior à instalada')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise SecureUpdateError('Metadados autenticados não contêm SHA-256 válido')
        parsed = urlsplit(download_url)
        expected_path = f'/AlfredPennywhorth/diario_oficial_scraper/releases/download/v{version}/DiarioScraper-v{version}.zip'
        if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or parsed.path != expected_path
                or parsed.query or parsed.fragment):
            raise SecureUpdateError('URL de download não corresponde à origem oficial')
        return TrustedMetadata(version, digest.lower(), download_url)
    except SecureUpdateError:
        raise
    except (aiohttp.ClientError, OSError, ValueError, KeyError, TypeError) as exc:
        raise SecureUpdateError(f'Não foi possível autenticar os metadados de atualização: {exc}') from exc


async def download_and_prepare(metadata, workspace):
    if not isinstance(metadata, TrustedMetadata):
        raise SecureUpdateError('Metadados autenticados são obrigatórios')
    if is_network_location(workspace):
        raise SecureUpdateError('Preparação em compartilhamento de rede bloqueada; solicite administração centralizada')
    try:
        version = str(Version(metadata.version))
        parsed = urlsplit(metadata.download_url)
        expected_path = f'/AlfredPennywhorth/diario_oficial_scraper/releases/download/v{version}/DiarioScraper-v{version}.zip'
        if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or parsed.path != expected_path
                or parsed.query or parsed.fragment or not re.fullmatch(r'[0-9a-f]{64}', metadata.sha256)):
            raise SecureUpdateError('Metadados de download inválidos')
        workspace = Path(workspace)
        parent = workspace.parent.resolve(strict=True)
        if is_network_location(parent):
            raise SecureUpdateError('Preparação em compartilhamento de rede bloqueada; solicite administração centralizada')
        workspace.mkdir(mode=0o700, exist_ok=False)
        workspace = workspace.resolve(strict=True)
        package = workspace / 'package.zip'
        url = metadata.download_url
        logger.info('etapa=download versão=%s', version)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300), trust_env=True) as session:
            for attempt in range(4):
                async with session.get(url, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get('Location')
                        if not location:
                            raise SecureUpdateError('Redirecionamento sem destino')
                        url = urljoin(url, location)
                        redirected = urlsplit(url)
                        if (redirected.scheme != 'https' or redirected.netloc not in
                                ('github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com')):
                            raise SecureUpdateError('Redirecionamento para origem não permitida')
                        continue
                    if response.status != 200:
                        raise SecureUpdateError(f'Falha no download: HTTP {response.status}')
                    size = 0
                    with package.open('xb') as output:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            size += len(chunk)
                            if size > MAX_TOTAL_SIZE:
                                raise SecureUpdateError('Download excede o limite permitido')
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    break
            else:
                raise SecureUpdateError('Excesso de redirecionamentos no download')
        logger.info('etapa=validação versão=%s', version)
        with package.open('rb') as package_stream:
            manifest = validate_package(package_stream, metadata.sha256, version)
            stage = workspace / 'stage'
            stage.mkdir()
            logger.info('etapa=preparação versão=%s', version)
            with zipfile.ZipFile(package_stream) as archive:
                total_size = 0
                for name, digest in manifest['files'].items():
                    path = _safe_path(name)
                    entry = archive.getinfo(path)
                    if entry.file_size > MAX_FILE_SIZE:
                        raise SecureUpdateError(f'Arquivo preparado excede o limite permitido: {path}')
                    destination = _checked_path(stage, path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    file_size = 0
                    with archive.open(entry) as source, destination.open('xb') as target:
                        while chunk := source.read(1024 * 1024):
                            file_size += len(chunk)
                            total_size += len(chunk)
                            if file_size > MAX_FILE_SIZE or total_size > MAX_TOTAL_SIZE:
                                raise SecureUpdateError('Extração excede o limite permitido')
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    if not hmac.compare_digest(_hash_path(destination), digest.lower()):
                        raise SecureUpdateError(f'Arquivo preparado corrompido: {path}')
            package_stream.seek(0)
            if not hmac.compare_digest(_file_hash(package_stream), metadata.sha256):
                raise SecureUpdateError('Pacote alterado durante a preparação')
        return stage, manifest
    except SecureUpdateError:
        raise
    except (aiohttp.ClientError, OSError, ValueError, TypeError, zipfile.BadZipFile, KeyError) as exc:
        raise SecureUpdateError(f'Falha de download ou preparação: {exc}') from exc


def _safe_path(name):
    if not isinstance(name, str) or not name or name.startswith('/') or '\\' in name:
        raise SecureUpdateError('Caminho inseguro no pacote')
    parts = name.rstrip('/').split('/')
    for part in parts:
        if (not part or part in ('.', '..') or part.endswith((' ', '.')) or ':' in part
                or any(ord(char) < 32 or char in '<>"|?*' for char in part)
                or unicodedata.normalize('NFKC', part).split('.')[0].casefold() in WINDOWS_RESERVED):
            raise SecureUpdateError(f'Caminho inseguro no pacote: {name}')
    return '/'.join(parts)


def _persistent_path(name):
    parts = [part.casefold() for part in name.split('/')]
    return any(part in PERSISTENT_DIRS or part in PERSISTENT_NAMES or part.startswith('.env.')
               or part.startswith(('config.', 'settings.', 'user_config.'))
               or part.endswith(('.db', '.sqlite', '.sqlite3'))
               or part.startswith('partial_results_') and part.endswith('.json') for part in parts)


def _file_hash(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def validate_package(package_path, expected_sha256, target_version):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
        raise SecureUpdateError('SHA-256 autenticado ausente ou inválido')
    try:
        expected_version = Version(target_version)
    except (InvalidVersion, TypeError) as exc:
        raise SecureUpdateError('Versão de destino inválida') from exc

    try:
        with zipfile.ZipFile(package_path) as archive:
            archive.fp.seek(0)
            actual_hash = _file_hash(archive.fp)
            if not hmac.compare_digest(actual_hash, expected_sha256.lower()):
                raise SecureUpdateError('SHA-256 do pacote não corresponde aos metadados autenticados')
            entries = {}
            total_size = 0
            for entry in archive.infolist():
                path = _safe_path(entry.filename)
                key = path.casefold()
                if key in entries:
                    raise SecureUpdateError(f'Caminho duplicado no pacote: {path}')
                mode = entry.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or stat.S_ISLNK(mode):
                    raise SecureUpdateError(f'Tipo de arquivo inseguro: {path}')
                if entry.file_size > MAX_FILE_SIZE:
                    raise SecureUpdateError('Arquivo do pacote excede o limite permitido')
                total_size += entry.file_size
                if total_size > MAX_TOTAL_SIZE:
                    raise SecureUpdateError('Pacote excede o limite permitido')
                if _persistent_path(path):
                    raise SecureUpdateError(f'Pacote contém caminho reservado a dados persistentes: {path}')
                entries[key] = (path, entry)

            for key, (_, entry) in entries.items():
                parts = key.split('/')
                for index in range(1, len(parts)):
                    parent = entries.get('/'.join(parts[:index]))
                    if parent and not parent[1].is_dir():
                        raise SecureUpdateError('Pacote contém conflito entre arquivo e diretório')

            manifest_entry = entries.get(MANIFEST_NAME.casefold())
            if not manifest_entry or manifest_entry[1].is_dir() or manifest_entry[1].file_size > 1024 * 1024:
                raise SecureUpdateError('Manifesto do pacote ausente ou inválido')
            try:
                manifest = json.loads(archive.read(manifest_entry[1]))
                manifest_version = Version(manifest['version'])
                package_format = manifest['format']
                files = manifest['files']
            except (ValueError, KeyError, TypeError) as exc:
                raise SecureUpdateError('Manifesto do pacote inválido') from exc
            if manifest_version != expected_version:
                raise SecureUpdateError('Versão do pacote não corresponde aos metadados autenticados')
            if package_format not in ('one-file', 'multi-file') or not isinstance(files, dict) or not files:
                raise SecureUpdateError('Formato ou lista de arquivos do manifesto inválido')

            declared = {}
            for name, digest in files.items():
                path = _safe_path(name)
                key = path.casefold()
                if key == MANIFEST_NAME.casefold() or key in declared or _persistent_path(path):
                    raise SecureUpdateError(f'Arquivo inválido no manifesto: {path}')
                if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
                    raise SecureUpdateError(f'SHA-256 inválido no manifesto: {path}')
                declared[key] = (path, digest.lower())

            actual_files = {key for key, (_, entry) in entries.items() if not entry.is_dir() and key != MANIFEST_NAME.casefold()}
            if actual_files != set(declared) or 'diarioscraper.exe' not in actual_files:
                raise SecureUpdateError('Conteúdo do pacote não corresponde ao manifesto')
            if package_format == 'one-file' and actual_files != {'diarioscraper.exe'}:
                raise SecureUpdateError('Pacote one-file contém arquivos adicionais')
            if package_format == 'multi-file' and not any(key.startswith('_internal/') for key in actual_files):
                raise SecureUpdateError('Pacote multi-file não contém arquivos internos')
            for key, (path, digest) in declared.items():
                with archive.open(entries[key][1]) as stream:
                    if not hmac.compare_digest(_file_hash(stream), digest):
                        raise SecureUpdateError(f'Arquivo do pacote corrompido: {path}')
            archive.fp.seek(0)
            if not hmac.compare_digest(_file_hash(archive.fp), expected_sha256.lower()):
                raise SecureUpdateError('Pacote alterado durante a validação')
            return manifest
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise SecureUpdateError(f'Pacote ausente ou inválido: {exc}') from exc


def _inventory(manifest):
    if not isinstance(manifest, dict) or manifest.get('format') not in ('one-file', 'multi-file'):
        raise SecureUpdateError('Inventário autenticado da instalação ausente ou inválido; use instalação paralela')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise SecureUpdateError('Inventário autenticado da instalação ausente ou inválido; use instalação paralela')
    inventory = {}
    for name, digest in files.items():
        path = _safe_path(name)
        key = path.casefold()
        if _persistent_path(path) or key in inventory or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise SecureUpdateError(f'Arquivo inseguro no inventário: {path}')
        inventory[key] = (path, digest.lower())
    if 'diarioscraper.exe' not in inventory:
        raise SecureUpdateError('Inventário não contém o executável')
    if manifest['format'] == 'one-file' and set(inventory) != {'diarioscraper.exe'}:
        raise SecureUpdateError('Inventário one-file contém arquivos adicionais')
    if manifest['format'] == 'multi-file' and not any(key.startswith('_internal/') for key in inventory):
        raise SecureUpdateError('Inventário multi-file não contém arquivos internos')
    return inventory


def _checked_path(root, relative):
    path = root
    parts = relative.split('/')
    for index, part in enumerate(parts):
        path = path / part
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise SecureUpdateError(f'Link simbólico em caminho controlado: {relative}')
        if index < len(parts) - 1 and path.exists() and not path.is_dir():
            raise SecureUpdateError(f'Colisão com arquivo no caminho: {relative}')
    if not path.resolve().is_relative_to(root):
        raise SecureUpdateError(f'Caminho fora da instalação: {relative}')
    return path


def _hash_path(path):
    with path.open('rb') as stream:
        return _file_hash(stream)


def _copy_verified(source, destination, expected_hash):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as source_stream, destination.open('xb') as target_stream:
        shutil.copyfileobj(source_stream, target_stream)
        target_stream.flush()
        os.fsync(target_stream.fileno())
    if not hmac.compare_digest(_hash_path(destination), expected_hash):
        raise SecureUpdateError(f'Verificação de arquivo falhou: {destination.name}')


def _replace_verified(source, target, expected_hash):
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.diario-update-', dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with source.open('rb') as source_stream, os.fdopen(descriptor, 'wb') as target_stream:
            shutil.copyfileobj(source_stream, target_stream)
            target_stream.flush()
            os.fsync(target_stream.fileno())
        if not hmac.compare_digest(_hash_path(temporary), expected_hash):
            raise SecureUpdateError(f'Verificação de arquivo falhou: {target.name}')
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_prepared_update(install_dir, stage_dir, backup_dir, old_manifest, new_manifest, process):
    if any(is_network_location(directory) for directory in (install_dir, stage_dir, backup_dir)):
        raise SecureUpdateError('Atualização automática em compartilhamento de rede bloqueada; solicite administração centralizada')
    for directory in (Path(install_dir), Path(stage_dir), Path(backup_dir)):
        if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
            raise SecureUpdateError('Diretório de atualização não pode ser link simbólico')
    try:
        install = Path(install_dir).resolve(strict=True)
        stage = Path(stage_dir).resolve(strict=True)
    except OSError as exc:
        raise SecureUpdateError(f'Instalação ou preparação ausente ou inacessível: {exc}') from exc
    backup = Path(backup_dir).resolve()
    if any(is_network_location(directory) for directory in (install, stage, backup)):
        raise SecureUpdateError('Atualização automática em compartilhamento de rede bloqueada; solicite administração centralizada')
    if (not install.is_dir() or not stage.is_dir() or install == stage or install.is_relative_to(stage)
            or stage.is_relative_to(install) or backup.is_relative_to(install) or install.is_relative_to(backup)
            or backup.is_relative_to(stage) or stage.is_relative_to(backup)):
        raise SecureUpdateError('Instalação, preparação e backup devem ser diretórios isolados')
    old_files = _inventory(old_manifest)
    new_files = _inventory(new_manifest)
    try:
        old_version = str(Version(old_manifest['version']))
        new_version = str(Version(new_manifest['version']))
        if Version(new_version) <= Version(old_version):
            raise SecureUpdateError('A versão de destino deve ser superior à instalada')
    except (KeyError, InvalidVersion, TypeError) as exc:
        raise SecureUpdateError('Versão do inventário inválida') from exc

    logger.info('etapa=inventário origem=%s destino=%s', old_version, new_version)
    existing = {}
    def inventory_error(exc):
        raise SecureUpdateError(f'Não foi possível inventariar a instalação: {exc}') from exc

    for directory, subdirectories, files in os.walk(install, followlinks=False, onerror=inventory_error):
        for name in subdirectories + files:
            relative = (Path(directory) / name).relative_to(install).as_posix()
            key = relative.casefold()
            if key in existing and existing[key] != relative:
                logger.warning('etapa=inventário colisão=%s', relative)
                raise SecureUpdateError(f'Colisão de caixa na instalação: {relative}')
            existing[key] = relative
    for key in old_files.keys() & new_files.keys():
        if old_files[key][0] != new_files[key][0]:
            logger.warning('etapa=inventário colisão=%s', old_files[key][0])
            raise SecureUpdateError(f'Colisão de caixa entre arquivos: {old_files[key][0]}')
    for path, digest in old_files.values():
        target = _checked_path(install, path)
        if not target.is_file() or not hmac.compare_digest(_hash_path(target), digest):
            raise SecureUpdateError(f'Arquivo instalado ausente ou modificado; revisão manual: {path}')
    for key, (path, digest) in new_files.items():
        source = _checked_path(stage, path)
        target = _checked_path(install, path)
        parts = path.split('/')
        for index in range(1, len(parts)):
            parent = '/'.join(parts[:index])
            if parent.casefold() in existing and existing[parent.casefold()] != parent:
                logger.warning('etapa=inventário colisão=%s', parent)
                raise SecureUpdateError(f'Colisão de caixa em diretório instalado: {parent}')
        if not source.is_file() or not hmac.compare_digest(_hash_path(source), digest):
            raise SecureUpdateError(f'Arquivo preparado ausente ou inválido: {path}')
        if key not in old_files and (target.exists() or key in existing):
            logger.warning('etapa=inventário colisão=%s', path)
            raise SecureUpdateError(f'Colisão com arquivo não identificado; revisão manual: {path}')
        if key in old_files and key in existing and existing[key] != old_files[key][0]:
            logger.warning('etapa=inventário colisão=%s', path)
            raise SecureUpdateError(f'Colisão de caixa com arquivo instalado: {path}')

    logger.info('etapa=backup destino=%s', backup)
    try:
        backup.mkdir(parents=True, exist_ok=False)
        for path, digest in old_files.values():
            _copy_verified(_checked_path(install, path), _checked_path(backup, path), digest)
    except (OSError, SecureUpdateError) as exc:
        raise SecureUpdateError(f'Backup incompleto; instalação não alterada. Verifique {backup}: {exc}') from exc

    changes = []
    stopped = False
    new_started = False
    try:
        logger.info('etapa=encerramento')
        if process.stop() is not True:
            raise SecureUpdateError('Encerramento do processo não confirmado')
        stopped = True
        logger.info('etapa=substituição')
        for key, (path, digest) in new_files.items():
            target = _checked_path(install, path)
            if key in old_files:
                if not target.is_file() or not hmac.compare_digest(_hash_path(target), old_files[key][1]):
                    raise SecureUpdateError(f'Arquivo alterado após o backup: {path}')
            elif target.exists():
                raise SecureUpdateError(f'Colisão após o backup: {path}')
            changes.append((path, digest, old_files.get(key)))
            _replace_verified(_checked_path(stage, path), target, digest)
        for key, (path, digest) in old_files.items():
            if key not in new_files:
                target = _checked_path(install, path)
                if not target.is_file() or not hmac.compare_digest(_hash_path(target), digest):
                    raise SecureUpdateError(f'Arquivo alterado após o backup: {path}')
                changes.append((path, None, (path, digest)))
                target.unlink()
        logger.info('etapa=reinício versão=%s', new_version)
        new_started = True
        process.start(install / 'DiarioScraper.exe')
        if process.healthy(new_version) is not True:
            raise SecureUpdateError('Aplicação não iniciou com a versão e saúde esperadas')
        logger.info('etapa=confirmada versão=%s', new_version)
        return backup
    except (Exception, KeyboardInterrupt) as exc:
        logger.exception('etapa=falha atualização=%s', new_version)
        if not stopped:
            raise SecureUpdateError(f'Atualização interrompida antes da substituição; o processo pode ter sido encerrado. Verifique e reinicie a versão anterior manualmente. Backup: {backup}: {exc}') from exc
        try:
            if new_started:
                if process.stop() is not True:
                    raise SecureUpdateError('Encerramento do novo processo não confirmado')
            for path, new_digest, old_entry in reversed(changes):
                target = _checked_path(install, path)
                if old_entry:
                    if target.is_file() and hmac.compare_digest(_hash_path(target), old_entry[1]):
                        continue
                    if target.exists() and (new_digest is None or not target.is_file()
                                            or not hmac.compare_digest(_hash_path(target), new_digest)):
                        raise SecureUpdateError(f'Arquivo alterado durante a recuperação: {path}')
                    _replace_verified(_checked_path(backup, path), target, old_entry[1])
                elif target.exists():
                    if not target.is_file() or not hmac.compare_digest(_hash_path(target), new_digest):
                        raise SecureUpdateError(f'Arquivo alterado durante a recuperação: {path}')
                    target.unlink()
            process.start(install / 'DiarioScraper.exe')
            if process.healthy(old_version) is not True:
                raise SecureUpdateError('Versão anterior não passou na verificação de saúde')
        except Exception as recovery_error:
            logger.exception('etapa=recuperação manual backup=%s', backup)
            raise SecureUpdateError(f'Recuperação automática insegura ou incompleta. Não sobrescreva os dados; restaure manualmente a instalação a partir de {backup}: {recovery_error}') from exc
        raise SecureUpdateError(f'Atualização falhou; versão anterior restaurada e verificada. Backup: {backup}: {exc}') from exc


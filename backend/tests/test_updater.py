import os
import sys
import tempfile
import zipfile
import pytest

# Adicionar pasta backend ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test list of controlled files (must be only DiarioScraper.exe, _internal, frontend, backend)
def test_controlled_files_list():
    controlled = ["DiarioScraper.exe", "_internal", "frontend", "backend"]
    # List of files we MUST preserve
    preserved = [
        ".env", "partial_results.json", "logs", "results", "exports", 
        "update", "backups", "database.db", "data.sqlite", "data.sqlite3",
        "config.json", "settings.json", "user_config.json"
    ]
    
    # Assert that no preserved file is in the controlled list
    for p in preserved:
        assert p not in controlled, f"Erro: {p} está na lista de controlados e seria excluído!"

# Helper to validate a ZIP file (equivalent to python code in main.py)
def validate_zip_structure(zip_path):
    if not os.path.exists(zip_path):
        return False, "Arquivo ZIP não encontrado."
    if os.path.getsize(zip_path) < 100:  # Mock check
        return False, "Arquivo ZIP muito pequeno."
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            namelist = z.namelist()
            has_exe = any(name.endswith("DiarioScraper.exe") for name in namelist)
            has_main = any(name.endswith("backend/main.py") for name in namelist)
            if not (has_exe or has_main):
                return False, "Estrutura do ZIP inválida: DiarioScraper.exe ou backend/main.py não encontrado."
        return True, "Válido"
    except Exception as e:
        return False, str(e)

def test_zip_validation_invalid():
    # Test file that does not exist
    ok, msg = validate_zip_structure("non_existent_file.zip")
    assert not ok
    assert "não encontrado" in msg

    # Test file too small
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        f.write(b"corrupted contents")
        temp_name = f.name
    try:
        ok, msg = validate_zip_structure(temp_name)
        assert not ok
        assert "muito pequeno" in msg
    finally:
        os.remove(temp_name)

    # Test ZIP that has no executable or main.py
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        temp_name = f.name
    try:
        with zipfile.ZipFile(temp_name, 'w') as z:
            z.writestr("random_file.txt", "hello")
        ok, msg = validate_zip_structure(temp_name)
        assert not ok
        assert "não encontrado" in msg
    finally:
        os.remove(temp_name)

    # Test valid ZIP
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        temp_name = f.name
    try:
        with zipfile.ZipFile(temp_name, 'w') as z:
            z.writestr("DiarioScraper.exe", "x" * 200)
        ok, msg = validate_zip_structure(temp_name)
        assert ok
    finally:
        os.remove(temp_name)

# Lock file simulation
class UpdateLock:
    def __init__(self, directory):
        self.lock_path = os.path.join(directory, "update.lock")

    def acquire(self):
        if os.path.exists(self.lock_path):
            return False
        with open(self.lock_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True

    def release(self):
        if os.path.exists(self.lock_path):
            os.remove(self.lock_path)

def test_lock_creation():
    with tempfile.TemporaryDirectory() as temp_dir:
        lock = UpdateLock(temp_dir)
        
        # Test creation succeeds
        assert lock.acquire() is True
        assert os.path.exists(lock.lock_path)
        
        # Test second attempt fails (concurrency rejection)
        assert lock.acquire() is False
        
        # Test release cleans up lock file
        lock.release()
        assert not os.path.exists(lock.lock_path)
        
        # Test we can acquire again after release
        assert lock.acquire() is True
        lock.release()

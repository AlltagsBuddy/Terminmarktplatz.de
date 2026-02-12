"""
Tests für API_ONLY-Modus: Root liefert JSON, nicht erlaubte Pfade liefern 404.
Wird in Subprocess ausgeführt, da API_ONLY vor App-Import gesetzt werden muss.
"""
import subprocess
import sys
import platform

import pytest

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Subprocess asyncio issue on Windows",
)


def _run_api_only_script(script: str) -> subprocess.CompletedProcess:
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent.parent
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(project_root),
    )


def test_api_only_root_returns_json():
    """In API_ONLY-Modus liefert GET / JSON statt HTML."""
    script = '''
import os
import tempfile
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.clear()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["API_ONLY"] = "1"
import app as app_module
client = app_module.app.test_client()
r = client.get("/")
assert r.status_code == 200
data = r.get_json()
assert data is not None
assert data.get("ok") is True
assert data.get("service") == "api"
assert "time" in data
'''
    result = _run_api_only_script(script)
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def test_api_only_forbidden_path_returns_404():
    """In API_ONLY-Modus liefert GET /kategorien 404 (api_only)."""
    script = '''
import os
import tempfile
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.clear()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["API_ONLY"] = "1"
import app as app_module
client = app_module.app.test_client()
r = client.get("/kategorien")
assert r.status_code == 404
data = r.get_json()
assert data is not None
assert data.get("error") == "api_only"
'''
    result = _run_api_only_script(script)
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def test_api_only_allowed_paths_still_work():
    """In API_ONLY-Modus funktionieren /auth/, /api/health, /login weiterhin."""
    script = '''
import os
import tempfile
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.clear()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["API_ONLY"] = "1"
import app as app_module
from models import Base
Base.metadata.create_all(app_module.engine)
client = app_module.app.test_client()
r = client.get("/api/health")
assert r.status_code == 200
r2 = client.get("/login")
assert r2.status_code == 200
r3 = client.get("/healthz")
assert r3.status_code == 200
'''
    result = _run_api_only_script(script)
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")

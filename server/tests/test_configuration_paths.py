import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _pythonpath_env(env: dict) -> str:
    existing = env.get("PYTHONPATH")
    if existing:
        return os.pathsep.join([str(PROJECT_ROOT), existing])
    return str(PROJECT_ROOT)


def test_custom_paths_honored(tmp_path):
    custom_storage = tmp_path / "custom-storage"
    custom_files = custom_storage / "files"
    custom_db = tmp_path / "alt-switchboard.db"

    script = """
import json
from server.db import DATABASE_URL, STORAGE_ROOT, FILES_ROOT, engine
from server.file_store import ensure_root, full_path

ensure_root()
resolved = full_path("demo/payload.bin")

print(json.dumps({
    "database_url": DATABASE_URL,
    "engine_url": engine.url.render_as_string(hide_password=False),
    "storage_root": str(STORAGE_ROOT),
    "files_root": str(FILES_ROOT),
    "resolved_path": str(resolved),
}))
"""

    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath_env(env)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{custom_db}"
    env["STORAGE_ROOT"] = str(custom_storage)
    env["FILES_ROOT"] = str(custom_files)

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["database_url"] == env["DATABASE_URL"]
    assert payload["engine_url"] == env["DATABASE_URL"]
    assert payload["storage_root"] == str(custom_storage.resolve())
    assert payload["files_root"] == str(custom_files.resolve())
    expected_resolved = (custom_files / "demo" / "payload.bin").resolve()
    assert payload["resolved_path"] == str(expected_resolved)

    assert (
        custom_files.exists()
    ), "ensure_root should create the configured files directory"

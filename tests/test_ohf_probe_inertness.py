from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

from scripts.ohf.laboratory import FORBIDDEN_IMPORT_PREFIXES, REPO_ROOT
from scripts.ohf.run_probe import main as run_probe_main

OHF_ROOT = REPO_ROOT / "scripts" / "ohf"


def _python_files() -> list[Path]:
    return [path for path in OHF_ROOT.rglob("*.py") if path.is_file()]


def test_ohf_package_does_not_import_executive_lifecycle():
    imported: set[str] = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    forbidden = {
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES)
    }
    assert not forbidden


def test_probe_does_not_open_executive_sqlite_or_arm_runtime(tmp_path, monkeypatch):
    opened: list[str] = []
    real_connect = sqlite3.connect

    def wrapped(database, *args, **kwargs):
        opened.append(str(database))
        text = str(database).lower()
        if "executive" in text:
            raise AssertionError(f"OHF probe opened Executive SQLite: {database}")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", wrapped)
    routes = REPO_ROOT / "config" / "executive_worker_routes.json"
    before_routes = routes.read_bytes() if routes.is_file() else None
    before_auth = (Path.home() / ".codex" / "auth.json").stat().st_mtime if (Path.home() / ".codex" / "auth.json").is_file() else None

    out = tmp_path / "evidence"
    assert run_probe_main(["--backend", "fake", "--workdir", str(tmp_path / "lab"), "--out-dir", str(out)]) == 0
    assert (out / "probe.json").is_file()
    assert (out / "probe.md").is_file()
    assert not any("executive" in item.lower() for item in opened)
    if before_routes is not None:
        assert routes.read_bytes() == before_routes
    if before_auth is not None:
        assert (Path.home() / ".codex" / "auth.json").stat().st_mtime == before_auth


def test_worker_execution_adapter_is_untouched():
    adapter = (REPO_ROOT / "control_plane" / "worker_adapter.py").read_text(encoding="utf-8")
    assert "class WorkerExecutionAdapter" in adapter
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        assert "WorkerExecutionAdapter" not in text
        assert "from control_plane.worker_adapter" not in text
        assert "import control_plane.worker_adapter" not in text

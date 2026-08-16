from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ohf.laboratory import Laboratory, default_user_codex_home
from scripts.ohf.run_probe import main as run_probe_main

REPO_ROOT = Path(__file__).resolve().parents[1]
OHF_ROOT = REPO_ROOT / "scripts" / "ohf"


def _ohf_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in OHF_ROOT.rglob("*.py"))


def test_auth_copy_helper_is_absent():
    source = _ohf_source()
    assert "copy_auth_if_present" not in source
    assert "def copy_auth" not in source
    laboratory = (OHF_ROOT / "laboratory.py").read_text(encoding="utf-8")
    for line in laboratory.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue
        if "auth.json" not in line:
            continue
        if any(token in line for token in ("copy2(", "copyfile(", "shutil.copy(", "symlink(", "symlink_to(")):
            raise AssertionError(f"auth cloning path still present: {line}")


def test_live_cli_requires_explicit_codex_home(tmp_path):
    assert run_probe_main(["--live", "--out-dir", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out" / "probe.json").exists()


def test_live_refuses_default_user_home(tmp_path):
    with pytest.raises(RuntimeError, match="refuses"):
        Laboratory(
            root=tmp_path,
            backend="live",
            dedicated_codex_home=default_user_codex_home(),
        )


def test_live_refuses_missing_home(tmp_path):
    missing = tmp_path / "no-such-codex-home"
    with pytest.raises(RuntimeError, match="not a directory"):
        Laboratory(root=tmp_path, backend="live", dedicated_codex_home=missing)


def test_live_refuses_unauthenticated_home(tmp_path):
    home = tmp_path / "dedicated"
    home.mkdir()
    with pytest.raises(RuntimeError, match="not authenticated"):
        Laboratory(root=tmp_path / "lab", backend="live", dedicated_codex_home=home)


def test_live_env_uses_dedicated_home_not_lab_or_default(tmp_path):
    home = tmp_path / "dedicated"
    home.mkdir()
    (home / "auth.json").write_text("{}\n", encoding="utf-8")
    lab = Laboratory(root=tmp_path / "lab", backend="live", dedicated_codex_home=home)
    env = lab.env()
    assert env["CODEX_HOME"] == str(home.resolve())
    assert env["CODEX_HOME"] != str(lab.codex_home)
    assert Path(env["CODEX_HOME"]) != default_user_codex_home()
    assert not (lab.codex_home / "auth.json").exists()
    assert not any(path.is_symlink() for path in lab.codex_home.rglob("*"))

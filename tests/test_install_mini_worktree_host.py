from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import install_mini_worktree_host as installer


def test_install_pins_helper_config_and_wrapper(tmp_path: Path):
    source_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    home.mkdir()

    receipt = installer.install(source_root=source_root, home=home, bootstrap=False)

    helper = Path(receipt["helper"])
    wrapper = Path(receipt["wrapper"])
    config = Path(receipt["config"])
    assert helper.is_file()
    assert wrapper.is_file()
    assert config.is_file()
    assert helper.stat().st_mode & 0o777 == 0o755
    assert wrapper.stat().st_mode & 0o777 == 0o755
    assert config.stat().st_mode & 0o777 == 0o600

    payload = json.loads(config.read_text(encoding="utf-8"))
    assert payload["min_free_bytes"] == 50 * installer.GIB
    assert payload["resume_free_bytes"] == 70 * installer.GIB
    assert payload["repositories"]["macro"]["exclude_dirs"] == [
        "data",
        "site",
        "mockups",
        "verify_shots",
    ]
    assert payload["repositories"]["mastermind"]["exclude_dirs"] == ["vendor"]
    text = wrapper.read_text(encoding="utf-8")
    assert str(helper) in text
    assert str(config) in text

    second = installer.install(source_root=source_root, home=home, bootstrap=False)
    assert second["changes"] == {"config": False, "helper": False, "wrapper": False}


def test_install_refuses_existing_config_drift(tmp_path: Path):
    source_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    config = home / ".config/mastermind/mini-worktrees.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}\n", encoding="utf-8")

    with pytest.raises(installer.InstallError, match="refusing overwrite"):
        installer.install(source_root=source_root, home=home, bootstrap=False)

    assert config.read_text(encoding="utf-8") == "{}\n"
    assert not (home / ".local/bin/mmx-mini-worktree").exists()

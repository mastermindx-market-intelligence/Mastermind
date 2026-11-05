from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import install_mini_worktree_host as installer


MACRO_REMOTE = "git@github.com:mastermindx-market-intelligence/macro.git"
MACRO_SSH_COMMAND = "ssh -i /owner/private/macro-readonly -o IdentitiesOnly=yes"


@pytest.fixture(autouse=True)
def _macro_private_remote(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(installer.MACRO_REMOTE_ENV, MACRO_REMOTE)
    monkeypatch.setenv(installer.MACRO_SSH_COMMAND_ENV, MACRO_SSH_COMMAND)


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
    assert payload["repositories"]["macro"]["url"] == MACRO_REMOTE
    assert payload["repositories"]["macro"]["git_ssh_command_env"] == installer.MACRO_SSH_COMMAND_ENV
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


def test_install_refuses_missing_macro_identity_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv(installer.MACRO_SSH_COMMAND_ENV, raising=False)

    with pytest.raises(installer.InstallError, match="environment"):
        installer.install(source_root=source_root, home=home, bootstrap=False)

    assert not (home / ".config/mastermind/mini-worktrees.json").exists()
    assert not (home / ".local/bin/mmx-mini-worktree").exists()


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/" + "mastermindx-market-intelligence/macro.git",
        "git@github.com:other/macro.git",
        " git@github.com:mastermindx-market-intelligence/macro.git",
    ],
)
def test_install_refuses_unqualified_macro_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: str
):
    source_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv(installer.MACRO_REMOTE_ENV, remote)

    with pytest.raises(
        installer.InstallError,
        match="canonical Macro repository|required host-owner environment",
    ):
        installer.install(source_root=source_root, home=home, bootstrap=False)

    assert not (home / ".config/mastermind/mini-worktrees.json").exists()


def test_install_accepts_only_qualified_complete_bootstrap_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(installer, "_git_sha", lambda _root: "a" * 40)
    config = installer.desired_config(home)
    rows = []
    for repository, profile in sorted(config["repositories"].items()):
        rows.append(
            {
                "repository": repository,
                "store": str((home / "stores" / repository).resolve()),
                "created": False,
                "remote_head": "b" * 40,
                "excluded_dirs": list(profile["exclude_dirs"]),
                "included_top_dirs": ["scripts"],
                "free_bytes": 123,
            }
        )
    document = {
        "schema_version": installer.HELPER_SCHEMA,
        "action": "bootstrap",
        "effect": "APPLIED",
        "receipt": rows,
    }

    def successful_bootstrap(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(document),
            stderr="",
        )

    monkeypatch.setattr(installer.subprocess, "run", successful_bootstrap)
    receipt = installer.install(source_root=source_root, home=home, bootstrap=True)

    assert receipt["bootstrap"] == document
    installed = json.loads(Path(receipt["config"]).read_text(encoding="utf-8"))
    assert installed["repositories"]["macro"]["url"] == MACRO_REMOTE
    assert MACRO_SSH_COMMAND not in Path(receipt["config"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mutation",
    ["wrong-effect", "missing-repository", "duplicate-repository", "extra-field", "bad-head"],
)
def test_bootstrap_success_contract_is_closed_and_complete(
    tmp_path: Path, mutation: str
):
    row = {
        "repository": "fixture",
        "store": str((tmp_path / "store").resolve()),
        "created": False,
        "remote_head": "c" * 40,
        "excluded_dirs": [],
        "included_top_dirs": ["src"],
        "free_bytes": 1,
    }
    document = {
        "schema_version": installer.HELPER_SCHEMA,
        "action": "bootstrap",
        "effect": "APPLIED",
        "receipt": [row],
    }
    expected = {"fixture"}
    if mutation == "wrong-effect":
        document["effect"] = "NOT_APPLIED"
    elif mutation == "missing-repository":
        expected.add("other")
    elif mutation == "duplicate-repository":
        document["receipt"] = [row, dict(row)]
    elif mutation == "extra-field":
        document["receipt"][0]["ready"] = True
    elif mutation == "bad-head":
        document["receipt"][0]["remote_head"] = "not-a-commit"

    with pytest.raises(installer.InstallError) as raised:
        installer._qualified_bootstrap_receipt(
            json.dumps(document), expected_repositories=expected
        )
    assert raised.value.effect == "EFFECT_UNKNOWN"
    assert raised.value.reconciliation_required is True

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "scripts" / "c1_sol_state_relay.py"


def _module():
    try:
        return importlib.import_module("scripts.c1_sol_state_relay")
    except ModuleNotFoundError:
        pytest.fail("C1 Relay entrypoint is not implemented")


def test_parser_exposes_only_config_and_no_secret_or_identity_overrides():
    entrypoint = _module()
    parser = entrypoint.build_parser()

    parsed = parser.parse_args(["--config", "/etc/mastermind/sol-relay.json"])
    assert parsed.config == "/etc/mastermind/sol-relay.json"

    option_strings = {
        option
        for action in parser._actions
        for option in getattr(action, "option_strings", ())
    }
    assert "--config" in option_strings
    assert "--token" not in option_strings
    assert "--channel" not in option_strings
    assert "--bot-user" not in option_strings
    assert "--workspace" not in option_strings

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--config", "/etc/mastermind/sol-relay.json", "--token", "FORBIDDEN"]
        )


def test_entrypoint_imports_under_production_isolated_stdlib_runtime():
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(ENTRYPOINT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Mastermind C1 SOL_STATE Relay" in completed.stdout

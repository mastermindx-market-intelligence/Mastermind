"""Actual package CLI and pure settings composition; no native provider calls."""
import copy
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from integrations.native_context.adapter import IntegrationConflict, compose_fragment, hook_fragment

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/native_context_hook.py"


def invoke(*args, input=None):
    return subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), *args],
                          input=input, capture_output=True, timeout=10)


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_actual_cli_orientation_roundtrip(provider):
    output = invoke("--provider", provider,
                    input=b'{"hook_event_name":"SessionStart","source":"startup"}')
    assert output.returncode == 0 and output.stderr == b""
    data = json.loads(output.stdout)
    assert "UNBOUND" in data["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_fragment_is_unbound_and_quotes_paths(provider):
    script = Path("/approved path/hook;not-a-shell-command.py")
    fragment = hook_fragment(provider=provider, python=Path("/qualified python/python3"), script=script)
    command = fragment["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    argv = shlex.split(command)
    assert argv == ["/qualified python/python3", "-I", "-B", str(script), "--provider", provider]
    assert "--hydrate" not in argv and "--workstream" not in argv
    assert set(fragment) == {"hooks"}


def test_composition_preserves_existing_settings_and_is_idempotent():
    original = {"model": "retain-current", "permissions": {"ask": ["Bash(sensitive)"]},
                "autoMemoryDirectory": "/existing/private-memory", "mcpServers": {"existing": {}},
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "existing-guard"}]}],
                          "Stop": [{"hooks": [{"type": "command", "command": "existing-stop"}]}]}}
    before = copy.deepcopy(original)
    fragment = hook_fragment(provider="claude", python=Path("/python"), script=Path("/release/hook.py"))
    merged = compose_fragment(original, fragment)
    assert original == before
    assert merged["permissions"] == before["permissions"]
    assert merged["mcpServers"] == before["mcpServers"]
    assert merged["model"] == before["model"]
    assert merged["autoMemoryDirectory"] == before["autoMemoryDirectory"]
    assert merged["hooks"]["Stop"] == before["hooks"]["Stop"]
    assert len(merged["hooks"]["SessionStart"]) == 2
    assert compose_fragment(merged, fragment) == merged


def test_same_command_different_hook_configuration_is_not_blindly_duplicated():
    fragment = hook_fragment(provider="codex", python=Path("/python"), script=Path("/release/hook.py"))
    existing = copy.deepcopy(fragment)
    existing["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] = 10
    with pytest.raises(IntegrationConflict):
        compose_fragment(existing, fragment)


@pytest.mark.parametrize("fragment", [
    {"permissions": {}}, {"hooks": {"Stop": []}}, {"hooks": {"SessionStart": {}}},
    {"hooks": {"SessionStart": [{"hooks": [{"command": ""}]}]}},
])
def test_invalid_fragment_never_overwrites_other_config(fragment):
    existing = {"permissions": {"deny": ["everything-not-admitted"]}}
    before = copy.deepcopy(existing)
    with pytest.raises(IntegrationConflict):
        compose_fragment(existing, fragment)
    assert existing == before


def test_cli_missing_canonical_dependency_is_honest_not_mocked():
    output = invoke("--provider", "codex", "--hydrate", "--workstream", "EXAMPLE-CONTEXT",
                    "--macro-root", "/approved/Macro", "--expected-macro-sha", "a" * 40,
                    "--expected-mastermind-sha", "b" * 40,
                    input=b'{"hook_event_name":"SessionStart","source":"startup"}')
    assert output.returncode == 0
    assert "READER_UNAVAILABLE" in json.loads(output.stdout)["hookSpecificOutput"]["additionalContext"]
    assert b"Traceback" not in output.stderr


def test_cli_unsupported_event_and_invalid_json_emit_empty_object():
    for raw in (b'{"hook_event_name":"Stop"}', b"bad json", b"X" * 32769):
        output = invoke("--provider", "claude", input=raw)
        assert output.returncode == 0 and json.loads(output.stdout) == {}


def test_cli_fragment_is_only_printed_not_installed(tmp_path):
    # Repository autouse fixtures populate tmp_path before this test begins.
    # Give this CLI a dedicated empty HOME; never weaken the zero-write assertion.
    home = tmp_path / "native_hook_home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home))
    output = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), "--provider", "claude",
                             "--emit-hook-fragment"], capture_output=True, timeout=10, env=env)
    assert output.returncode == 0
    assert set(json.loads(output.stdout)) == {"hooks"}
    assert list(home.iterdir()) == []


def test_package_contains_no_native_provider_launch_or_configuration_writer():
    # A source boundary check supplements, but does not replace, executed CLI tests.
    paths = [SCRIPT, ROOT / "integrations/native_context/adapter.py", ROOT / "integrations/native_context/bridge.py"]
    for path in paths:
        source = path.read_text()
        for forbidden in ("subprocess.Popen", "subprocess.run", "os.system", "write_text(", "write_bytes("):
            assert forbidden not in source


def test_same_adapter_different_argv_cannot_get_a_second_global_registration():
    fragment = hook_fragment(provider="codex", python=Path("/python"), script=Path("/release/hook.py"))
    existing = copy.deepcopy(fragment)
    existing["hooks"]["SessionStart"][0]["hooks"][0]["command"] += " --hydrate"
    with pytest.raises(IntegrationConflict):
        compose_fragment(existing, fragment)


@pytest.mark.parametrize("extra", [{"timeout": 0}, {"permissionDecision": "allow"}])
def test_fragment_cannot_smuggle_control_fields(extra):
    fragment = hook_fragment(provider="codex", python=Path("/python"), script=Path("/release/hook.py"))
    fragment["hooks"]["SessionStart"][0]["hooks"][0].update(extra)
    with pytest.raises(IntegrationConflict):
        compose_fragment({}, fragment)


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_bound_nonhydrating_cli_retains_public_pin_argument(provider):
    output = invoke("--provider", provider, "--workstream", "EXAMPLE-CONTEXT",
                    "--macro-root", "/approved/Macro",
                    "--expected-macro-sha", "a" * 40,
                    "--expected-mastermind-sha", "b" * 40,
                    input=b'{"hook_event_name":"SessionStart","source":"startup"}')
    assert output.returncode == 0 and output.stderr == b""
    context = json.loads(output.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "ORIENTATION_ONLY" in context
    assert "Declared reader pin: " + "b" * 40 in context
    assert "CANONICAL_PAYLOAD_INCLUDED" not in context

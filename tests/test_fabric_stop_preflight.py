"""Read-only regression checks for adapter drift that suppresses native returns."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from integrations.session_bridge import fabric_stop_preflight as preflight
from integrations.session_bridge import fabric_stop_return as stop


@pytest.fixture
def installed(tmp_path):
    hook = tmp_path / "fabric_stop_return.py"
    hook.write_text("raise RuntimeError('preflight must not execute the hook')\n")
    adapter = tmp_path / "fabric_task.py"
    adapter.write_text("raise RuntimeError('preflight must not execute the adapter')\n")
    state = tmp_path / "private attention"
    state.mkdir(mode=0o700)
    marker = state / "existing.subscriptions.json"
    marker.write_bytes(b"private subscription data, deliberately not JSON")
    tokens = ["python3", str(hook), "--adapter", str(adapter), "--adapter-sha256",
              stop.digest(adapter.read_bytes()), "--subscribed-state-dir", str(state)]
    definition = {"type": "command", "command": shlex.join(tokens), "timeout": 25}
    config = tmp_path / "hooks.json"
    def write():
        config.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [definition]}]}}))
    write()
    return config, hook, adapter, state, definition, tokens, write


def test_matching_binding_is_static_only_and_does_not_touch_attention(installed, monkeypatch):
    config, _, _, state, _, _, _ = installed
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in state.iterdir()}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute commands"))
    report = preflight.inspect_hooks(config)
    assert report["static_checks_pass"] is True
    assert report["effects"] == "NONE"
    assert report["native_loading"] == report["native_delivery"] == "UNOBSERVED"
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in state.iterdir()} == before
    assert "private subscription data" not in json.dumps(report)


def test_changed_adapter_reproduces_installed_drift(installed):
    config, _, adapter, _, _, _, _ = installed
    expected = stop.digest(adapter.read_bytes())
    adapter.write_text("print('new reviewed adapter release')\n")
    report = preflight.inspect_hooks(config)
    row = report["bindings"][0]
    assert not report["static_checks_pass"]
    assert row["issues"] == ["adapter_source_changed"]
    assert row["expected_adapter_sha256"] == expected
    assert row["observed_adapter_sha256"] == stop.digest(adapter.read_bytes())


@pytest.mark.parametrize("target", ["hook", "adapter", "state"])
def test_symlink_targets_are_unqualified(installed, target, tmp_path):
    config, hook, adapter, state, _, _, _ = installed
    path = {"hook": hook, "adapter": adapter, "state": state}[target]
    moved = tmp_path / (path.name + ".original")
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=target == "state")
    assert not preflight.inspect_hooks(config)["static_checks_pass"]


def test_unsafe_directory_does_not_get_repaired(installed):
    config, _, _, state, _, _, _ = installed
    state.chmod(0o770)
    report = preflight.inspect_hooks(config)
    assert "state_directory_unsafe" in report["bindings"][0]["issues"]
    assert state.stat().st_mode & 0o777 == 0o770


def test_duplicate_flags_and_shell_commands_are_not_evaluated(installed):
    config, _, _, _, definition, tokens, write = installed
    for command in (shlex.join(tokens + ["--adapter", "/secret"]),
                    shlex.join(tokens) + " ; touch /must-not-run",
                    shlex.join(tokens).replace("python3 ", "python3\n", 1),
                    shlex.join(tokens).replace("python3 ", "python3;", 1),
                    "env TOKEN=secret " + shlex.join(tokens)):
        definition["command"] = command
        write()
        report = preflight.inspect_hooks(config)
        assert not report["static_checks_pass"]
        assert report["bindings"][0]["issues"] == ["unsupported_command"]
        assert "TOKEN=secret" not in json.dumps(report)


def test_hash_named_hook_drift_is_visible(installed):
    config, hook, _, _, definition, tokens, write = installed
    named = hook.with_name("fabric_stop_return_000000000000.py")
    hook.rename(named)
    tokens[1] = str(named)
    definition["command"] = shlex.join(tokens)
    write()
    report = preflight.inspect_hooks(config)
    assert "hash_named_hook_source_changed" in report["bindings"][0]["issues"]


def test_fixed_binding_and_unrelated_hooks_are_preserved(installed):
    config, _, _, state, definition, tokens, _ = installed
    tokens[-2:] = ["--root", "original-root", "--run", "original-run", "--receipt-dir", str(state)]
    definition["command"] = shlex.join(tokens)
    document = {"hooks": {"SessionStart": [{"hooks": [{"command": "unrelated"}]}],
                         "Stop": [{"hooks": [{"type": "command", "command": "unrelated"}, definition]}]}}
    config.write_text(json.dumps(document))
    before = config.read_bytes()
    report = preflight.inspect_hooks(config)
    assert report["static_checks_pass"]
    assert len(report["bindings"]) == 1 and report["bindings"][0]["mode"] == "fixed"
    assert config.read_bytes() == before


def test_missing_or_malformed_config_is_not_success(tmp_path):
    config = tmp_path / "hooks.json"
    assert not preflight.inspect_hooks(config)["static_checks_pass"]
    for text in ("not JSON", "[]", '{"hooks":{"Stop":null}}', '{"hooks":{}}'):
        config.write_text(text)
        assert not preflight.inspect_hooks(config)["static_checks_pass"]


@pytest.mark.parametrize("key", ["--root", "--run"])
@pytest.mark.parametrize("identity", ["bad root", "bad/root", "r" * 512])
def test_fixed_identity_matches_incumbent_validation(installed, key, identity):
    config, _, _, state, definition, tokens, write = installed
    tokens[-2:] = ["--root", "original-root", "--run", "original-run", "--receipt-dir", str(state)]
    tokens[tokens.index(key) + 1] = identity
    definition["command"] = shlex.join(tokens)
    write()
    report = preflight.inspect_hooks(config)
    assert not report["static_checks_pass"]
    assert report["bindings"][0]["issues"] == ["invalid_fixed_identity"]


@pytest.mark.parametrize("field,value", [("timeout", float("nan")), ("timeout", float("inf")),
    ("timeout", float("-inf")), ("timeout", 10 ** 400), ("timeout", True), ("async", 0), ("async", 0.0),
    ("async", None), ("async", True)])
def test_invalid_handler_values_never_pass(installed, field, value):
    config, _, _, _, definition, _, write = installed
    definition[field] = value
    write()
    assert not preflight.inspect_hooks(config)["static_checks_pass"]


def test_literal_false_async_remains_supported(installed):
    config, _, _, _, definition, _, write = installed
    definition["async"] = False
    write()
    assert preflight.inspect_hooks(config)["static_checks_pass"]


def test_cli_returns_nonzero_for_drift_without_running_adapter(installed):
    config, _, adapter, _, _, _, _ = installed
    adapter.write_text("raise SystemExit('do not run')\n")
    result = subprocess.run([sys.executable, "-m", "integrations.session_bridge.fabric_stop_preflight",
                             "--hooks-file", str(config)], text=True, capture_output=True)
    assert result.returncode == 78
    assert json.loads(result.stdout)["bindings"][0]["issues"] == ["adapter_source_changed"]
    assert not result.stderr

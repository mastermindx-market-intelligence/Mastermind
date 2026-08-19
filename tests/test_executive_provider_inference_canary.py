"""Linux-safe tests for the Codex provider-inference canary."""
from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANARY_PATH = ROOT / "ops" / "executive_os" / "provider_inference_canary.py"
SPEC = importlib.util.spec_from_file_location(
    "executive_provider_inference_canary", CANARY_PATH
)
assert SPEC is not None and SPEC.loader is not None
canary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = canary
SPEC.loader.exec_module(canary)


def _config(tmp_path: Path) -> object:
    probe = tmp_path / "probe"
    probe.mkdir()
    return canary.ProviderCanaryConfig(
        canary_id="canary-aaaaaaaaaaaa",
        worker_user="_mastermind_worker",
        worker_uid=451,
        worker_gid=451,
        provider_home=tmp_path / "provider-home",
        installed_codex_binary=tmp_path / "codex-0.147.0",
        expected_codex_version="0.147.0",
        expected_codex_sha256="a" * 64,
        expected_codex_team="2DC432GLL2",
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        probe_root=probe,
        executive_database=tmp_path / "control" / "executive.sqlite3",
        production_workspaces=tmp_path / "jobs" / "workspaces",
        production_runs=tmp_path / "jobs" / "runs",
        control_root=tmp_path / "control",
        operator_home=tmp_path / "Users" / "operator",
        timeout_seconds=2.0,
    )


def _completed_stdout() -> bytes:
    events = [
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok":true}'}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    ]
    return b"".join(json.dumps(event).encode("utf-8") + b"\n" for event in events)


def test_login_status_success_and_workspace_403_is_preflight_fail() -> None:
    classified = canary.classify_provider_streams(
        stdout=b"",
        stderr=b"ChatGPT 403 Forbidden invalid_workspace_selected\n",
        result=None,
        exit_code=1,
        timed_out=False,
    )
    readiness = canary.evaluate_provider_preflight(
        login_status_ok=True, canary=classified
    )
    assert classified["terminal_event_class"] == "invalid_workspace_selected"
    assert classified["passed"] is False
    assert readiness["passed"] is False
    assert readiness["refusal"] == "invalid_workspace_selected"
    assert "403" not in json.dumps(readiness)
    assert "Forbidden" not in json.dumps(classified)


def test_malformed_provider_response_fails() -> None:
    classified = canary.classify_provider_streams(
        stdout=b"not-json\n{bad",
        stderr=b"",
        result=b"also not json",
        exit_code=0,
        timed_out=False,
    )
    assert classified["passed"] is False
    assert classified["terminal_event_class"] == "malformed_provider_response"


def test_timeout_fails() -> None:
    classified = canary.classify_provider_streams(
        stdout=b"",
        stderr=b"",
        result=None,
        exit_code=124,
        timed_out=True,
    )
    assert classified["passed"] is False
    assert classified["terminal_event_class"] == "timeout"


def test_successful_terminal_turn_and_valid_inert_result_passes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.provider_home.mkdir()
    (config.provider_home / "auth.json").write_text("opaque", encoding="utf-8")
    config.executive_database.parent.mkdir(parents=True)
    config.executive_database.write_text("sqlite", encoding="utf-8")
    config.production_workspaces.mkdir(parents=True)
    config.production_runs.mkdir(parents=True)
    config.operator_home.mkdir(parents=True)

    def runner(invocation: canary.CodexInvocation) -> canary.CodexRunResult:
        invocation.result_path.write_text('{"ok": true}', encoding="utf-8")
        canary.assert_invocation_isolation(config, invocation)
        assert invocation.env["CODEX_HOME"] == str(config.provider_home)
        assert invocation.env["HOME"] != str(config.operator_home)
        assert invocation.env["HOME"] != str(config.provider_home)
        assert str(config.executive_database) not in invocation.argv
        assert "-C" in invocation.argv
        workspace = invocation.argv[invocation.argv.index("-C") + 1]
        assert workspace.startswith(str(config.probe_root))
        assert "forced_chatgpt_workspace_id" not in " ".join(invocation.argv)
        return canary.CodexRunResult(
            exit_code=0, stdout=_completed_stdout(), stderr=b"", timed_out=False
        )

    receipt = canary.run_canary(
        config,
        runner=runner,
        binary_sha256="b" * 64,
        observed_version="0.147.0",
    )
    assert receipt["passed"] is True
    assert receipt["terminal_event_class"] == "turn_completed"
    assert receipt["result_valid"] is True
    assert receipt["forced_chatgpt_workspace_id_applied"] is False
    assert receipt["workspace_selection_mechanism"] == "none"
    payload = {key: value for key, value in receipt.items() if key != "result_valid"}
    assert '"ok"' not in json.dumps(payload)
    assert not (config.probe_root / config.canary_id / "workspace").exists()
    assert not (config.probe_root / config.canary_id / "result.json").exists()
    persisted = json.loads(
        (config.probe_root / config.canary_id / "receipt.json").read_text(encoding="utf-8")
    )
    assert persisted["canary_id"] == "canary-aaaaaaaaaaaa"
    assert persisted["stdout_sha256"]


def test_canary_cannot_touch_executive_db_or_production_workspaces(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.provider_home.mkdir()
    config.executive_database.parent.mkdir(parents=True)
    config.executive_database.write_bytes(b"KEEP")
    config.production_workspaces.mkdir(parents=True)
    marker = config.production_workspaces / "JOB-001"
    marker.mkdir()
    config.production_runs.mkdir(parents=True)
    config.operator_home.mkdir(parents=True)
    original = config.executive_database.read_bytes()

    def runner(invocation: canary.CodexInvocation) -> canary.CodexRunResult:
        canary.assert_invocation_isolation(config, invocation)
        poisoned = canary.CodexInvocation(
            argv=invocation.argv + (str(config.executive_database),),
            env=invocation.env,
            cwd=invocation.cwd,
            stdin=invocation.stdin,
            workspace=invocation.workspace,
            schema_path=invocation.schema_path,
            result_path=invocation.result_path,
            home=invocation.home,
            tmp=invocation.tmp,
        )
        with pytest.raises(canary.ProviderCanaryError):
            canary.assert_invocation_isolation(config, poisoned)
        invocation.result_path.write_text('{"ok": true}', encoding="utf-8")
        return canary.CodexRunResult(
            exit_code=0, stdout=_completed_stdout(), stderr=b"", timed_out=False
        )

    canary.run_canary(
        config,
        runner=runner,
        binary_sha256="b" * 64,
        observed_version="0.147.0",
    )
    assert config.executive_database.read_bytes() == original
    assert marker.exists()


def test_canary_cannot_inherit_operator_home_or_expose_credentials(tmp_path: Path) -> None:
    config = _config(tmp_path)
    invocation = canary.prepare_probe(config)
    assert "OPENAI_API_KEY" not in invocation.env
    assert "CODEX_ACCESS_TOKEN" not in invocation.env
    assert invocation.env["HOME"] != str(config.operator_home)
    assert str(config.operator_home) not in invocation.env["HOME"]
    assert "--with-api-key" not in invocation.argv
    dumped = json.dumps(invocation.env) + " ".join(invocation.argv)
    assert "opaque-token" not in dumped
    text = invocation.stdin.decode("utf-8")
    assert "auth.json" not in text
    canary._scrub_probe_secrets(invocation)


def test_failure_output_is_bounded_and_redacted() -> None:
    classified = canary.classify_provider_streams(
        stdout=b"",
        stderr=(
            b"account=user@example.com token=sk-abcdefghijklmnopqrstuvwxyz012345 "
            b"invalid_workspace_selected\n"
        ),
        result=None,
        exit_code=1,
        timed_out=False,
    )
    encoded = json.dumps(classified)
    assert "example.com" not in encoded
    assert "sk-" not in encoded
    assert encoded.count("invalid_workspace_selected") == 1


def test_canary_script_is_executable_and_syntax_valid() -> None:
    script = ROOT / "ops" / "executive_os" / "provider-inference-canary.sh"
    assert stat.S_IMODE(script.stat().st_mode) & 0o111
    completed = subprocess.run(
        ["/bin/bash", "-n", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    source = script.read_text(encoding="utf-8")
    assert "-I -S -B" in source
    assert "must run as root" in source


def test_canary_source_never_reads_auth_or_allowlists_process_names() -> None:
    source = CANARY_PATH.read_text(encoding="utf-8")
    assert "auth.json" not in source
    assert "distnoted" not in source
    assert "process-name allowlist" not in source.lower()
    assert "forced_chatgpt_workspace_id_applied" in source
    assert "OPENAI_API_KEY" in source
    assert "/bin/cat" not in source
    assert "jq " not in source

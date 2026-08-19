"""Linux-safe tests for the Codex provider-inference canary."""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
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
    python_line = next(
        line for line in source.splitlines() if "provider_inference_canary.py" in line
    )
    assert '"$@"' not in source
    assert "--probe-root" not in python_line
    assert "--operator-home" not in python_line
    assert "--receipt-path" not in python_line


def test_canary_source_never_reads_auth_or_allowlists_process_names() -> None:
    source = CANARY_PATH.read_text(encoding="utf-8")
    assert "auth.json" not in source
    assert "distnoted" not in source
    assert "process-name allowlist" not in source.lower()
    assert "forced_chatgpt_workspace_id_applied" in source
    assert "OPENAI_API_KEY" in source
    assert "/bin/cat" not in source
    assert "jq " not in source
    assert 'parser.add_argument("--probe-root"' not in source
    assert 'parser.add_argument("--receipt-path"' not in source
    assert 'parser.add_argument("--operator-home"' not in source
    assert "assign_probe_tree_to_worker" in source
    assert "LOCAL_FS_EACCES_STDERR" in source
    assert "config.probe_root" in source


def test_live_cli_rejects_path_overrides_including_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "control" / "db" / "data" / "control_plane" / "executive.sqlite3"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"KEEP")
    argv_sets = [
        ["--probe-root", str(tmp_path / "probe")],
        ["--probe-root", str(tmp_path / "safe"), "--probe-root", str(db.parent)],
        ["--receipt-path", str(db)],
        ["--operator-home", str(tmp_path / "Users" / "operator")],
        [
            "--probe-root",
            str(tmp_path / "probe"),
            "--receipt-path",
            str(db),
            "--operator-home",
            str(tmp_path / "Users" / "operator"),
        ],
        [f"--probe-root={db.parent}", f"--receipt-path={db}"],
    ]
    dests = [action.dest for action in canary._parser()._actions]
    assert "probe_root" not in dests
    assert "receipt_path" not in dests
    assert "operator_home" not in dests
    for argv in argv_sets:
        with pytest.raises(canary.ProviderCanaryError) as rejected:
            canary.reject_live_path_options(argv)
        assert rejected.value.code == "configuration_invalid"
        with pytest.raises(canary.ProviderCanaryError):
            canary.main(argv)
    assert db.read_bytes() == b"KEEP"
    assert not db.with_name("receipt.json").exists()


def test_receipt_persistence_cannot_target_executive_or_operator_paths(
    tmp_path: Path,
) -> None:
    import dataclasses

    config = _config(tmp_path)
    config.provider_home.mkdir()
    config.executive_database.parent.mkdir(parents=True)
    config.executive_database.write_bytes(b"KEEP")
    config.production_workspaces.mkdir(parents=True)
    config.production_runs.mkdir(parents=True)
    config.control_root.mkdir(parents=True, exist_ok=True)
    config.operator_home.mkdir(parents=True)
    receipt = {"schema_version": canary.SCHEMA_VERSION, "passed": False}
    poisoned = [
        dataclasses.replace(config, probe_root=config.control_root),
        dataclasses.replace(config, probe_root=config.production_workspaces),
        dataclasses.replace(config, probe_root=config.production_runs),
        dataclasses.replace(config, probe_root=config.provider_home),
        dataclasses.replace(config, probe_root=config.operator_home),
        dataclasses.replace(config, probe_root=config.executive_database.parent),
    ]
    for bad in poisoned:
        with pytest.raises(canary.ProviderCanaryError) as blocked:
            canary.persist_canary_receipt(bad, receipt)
        assert blocked.value.code == "isolation_violation"
        assert not (Path(bad.probe_root) / bad.canary_id / "receipt.json").exists()
    with pytest.raises(canary.ProviderCanaryError):
        canary.assert_receipt_destination_allowed(config.executive_database, config)
    with pytest.raises(canary.ProviderCanaryError):
        canary.assert_receipt_destination_allowed(
            config.control_root / "receipt.json", config
        )
    assert config.executive_database.read_bytes() == b"KEEP"


def _ownership(
    path: Path, uid: int, gid: int, mode: int, is_dir: bool
) -> object:
    return canary.PathOwnership(
        path=path,
        uid=uid,
        gid=gid,
        mode=mode,
        is_dir=is_dir,
        is_symlink=False,
    )


def test_local_filesystem_eacces_is_isolation_violation_not_process_failed() -> None:
    classified = canary.classify_provider_streams(
        stdout=b"",
        stderr=canary.LOCAL_FS_EACCES_STDERR,
        result=None,
        exit_code=1,
        timed_out=False,
    )
    readiness = canary.evaluate_provider_preflight(
        login_status_ok=True, canary=classified
    )
    assert classified["terminal_event_class"] == "isolation_violation"
    assert classified["passed"] is False
    assert readiness["passed"] is False
    assert readiness["refusal"] == "isolation_violation"
    assert readiness["refusal"] != "process_failed"


def test_root_owned_outer_probe_root_with_worker_descendants_fails_preflight(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    invocation = canary.prepare_probe(config)
    plan = canary.worker_probe_path_plan(config, invocation)
    assert plan[0][0] == config.probe_root
    live_bug = tuple(
        _ownership(path, 0 if index == 0 else 451, 0 if index == 0 else 451, mode, is_dir)
        for index, (path, mode, is_dir) in enumerate(plan)
    )
    assert (
        canary.probe_hierarchy_allows_worker_traversal(
            live_bug, plan, worker_uid=451, worker_gid=451
        )
        is False
    )
    with pytest.raises(canary.ProviderCanaryError) as refused:
        canary.assert_worker_probe_hierarchy(config, invocation)
    assert refused.value.code == "isolation_violation"


def test_corrected_451_hierarchy_is_worker_traversable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    invocation = canary.prepare_probe(config)
    plan = canary.worker_probe_path_plan(config, invocation)
    owned = tuple(
        _ownership(path, 451, 451, mode, is_dir) for path, mode, is_dir in plan
    )
    assert (
        canary.probe_hierarchy_allows_worker_traversal(
            owned, plan, worker_uid=451, worker_gid=451
        )
        is True
    )
    world = _ownership(config.probe_root, 451, 451, 0o711, True)
    assert (
        canary.worker_principal_owns_mode(
            world,
            worker_uid=451,
            worker_gid=451,
            expected_mode=0o700,
            expect_dir=True,
        )
        is False
    )
    assert canary.WORKER_UID == 451
    assert canary.WORKER_GID == 451


def test_outer_root_not_worker_owned_never_invokes_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    invocation = canary.prepare_probe(config)
    called: list[str] = []

    def fake_assign(_config: object, _invocation: object) -> None:
        return None

    def fake_subprocess(_invocation: object, *, timeout_seconds: float) -> object:
        called.append("subprocess")
        return canary.CodexRunResult(0, b"", b"", timed_out=False)

    monkeypatch.setattr(canary, "assign_probe_tree_to_worker", fake_assign)
    monkeypatch.setattr(canary, "subprocess_runner", fake_subprocess)
    with pytest.raises(canary.ProviderCanaryError) as blocked:
        canary.live_worker_runner(config, invocation)
    assert blocked.value.code == "isolation_violation"
    assert called == []


def test_corrected_preparation_makes_probe_root_worker_owned_0700(
    tmp_path: Path,
) -> None:
    uid, gid = os.geteuid(), os.getegid()
    config = dataclasses.replace(_config(tmp_path), worker_uid=uid, worker_gid=gid)
    invocation = canary.prepare_probe(config)
    paths = canary.worker_probe_chown_paths(config, invocation)
    assert paths[0] == config.probe_root
    assert (config.probe_root / config.canary_id) in paths
    assert invocation.workspace in paths
    assert invocation.schema_path in paths
    canary.assign_probe_tree_to_worker(config, invocation)
    canary.assert_worker_probe_hierarchy(config, invocation)
    for path, mode, is_dir in canary.worker_probe_path_plan(config, invocation):
        identity = canary.inspect_path_ownership(path)
        assert identity.uid == uid
        assert identity.gid == gid
        assert identity.mode == mode
        assert identity.mode & 0o077 == 0
        assert identity.is_dir is is_dir
        if is_dir:
            assert os.access(path, os.X_OK | os.R_OK)


def test_root_cleanup_removes_worker_owned_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(canary, "LIVE_PROBE_PARENT", tmp_path)
    uid, gid = os.geteuid(), os.getegid()
    probe = canary.create_live_probe_root(worker_uid=uid, worker_gid=gid)
    identity = canary.inspect_path_ownership(probe)
    assert identity.uid == uid
    assert identity.gid == gid
    assert identity.mode == 0o700
    child = probe / "canary-aaaaaaaaaaaa"
    child.mkdir(mode=0o700)
    canary.cleanup_live_probe_root(probe)
    assert probe.exists() is False

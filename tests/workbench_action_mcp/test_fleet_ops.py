from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import time

import pytest

import integrations.workbench_action_mcp.fleet_ops as fleet_ops_module
from integrations.workbench_action_mcp.fleet_ops import (
    FleetOperationError,
    doctor,
    inspect_artifact_evidence,
    qualify,
    renew,
)
from integrations.workbench_action_mcp.runtime import (
    FixedTunnelChannel,
    channel_client_ref,
    channel_subject_digest,
)
from integrations.workbench_action_mcp.tunnel import TUNNEL_SCHEMA


SOURCE_SHA = "c" * 40
CHANNEL = FixedTunnelChannel(
    tunnel_id="tunnel-workbench-c1",
    organization_id="org-c1",
    workspace_id="workspace-c1",
)


def _document(tmp_path: Path, *, expires_at_ms: int | None = None) -> tuple[dict, Path]:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    artifacts = tmp_path / "artifacts"
    for directory in (project, audit, artifacts):
        directory.mkdir(mode=0o700)
    key = tmp_path / "action.hex"
    key.write_text("9" * 64 + "\n", encoding="ascii")
    os.chmod(key, 0o600)
    python_executable = os.path.realpath(sys.executable)
    recipe_root = (
        Path(__file__).resolve().parents[2]
        / "integrations"
        / "workbench_action_mcp"
        / "recipes"
    )
    if expires_at_ms is None:
        expires_at_ms = int(time.time() * 1000) + 30 * 24 * 60 * 60 * 1000
    document = {
        "schema": TUNNEL_SCHEMA,
        "tunnel_id": CHANNEL.tunnel_id,
        "organization_id": CHANNEL.organization_id,
        "workspace_id": CHANNEL.workspace_id,
        "audit_policy_id": "workbench-fleet-test",
        "project_root": str(project),
        "audit_directory": str(audit),
        "artifact_directory": str(artifacts),
        "host_id": "a" * 64,
        "action_key_file": str(key),
        "python_executable": python_executable,
        "python_sha256": hashlib.sha256(
            Path(python_executable).read_bytes()
        ).hexdigest(),
        "recipe_root": str(recipe_root),
        "process_deadline_seconds": 5.0,
        "max_concurrency": 1,
        "io_timeout_seconds": 5.0,
        "close_timeout_seconds": 5.0,
        "action_ttl_ms": 60_000,
        "lease": {
            "expected_subject_digest": channel_subject_digest(CHANNEL),
            "expected_client_ref": channel_client_ref(CHANNEL),
            "resource": "https://workbench-action.example/mcp",
            "required_scopes": ["workbench.action"],
            "project_ref": "project:" + "1" * 64,
            "context_ref": "context:" + "2" * 64,
            "responsibility_ref": "responsibility:" + "3" * 64,
            "operation_ref": "operation:" + "4" * 64,
            "owner_ref": "owner:" + "5" * 64,
            "generation": "generation:" + "6" * 64,
            "allowed_paths": ["sample.py"],
            "committed_head": None,
            "lease_expires_at_ms": expires_at_ms,
        },
    }
    config_path = tmp_path / "action.json"
    config_path.write_text(json.dumps(document, sort_keys=True), encoding="ascii")
    os.chmod(config_path, 0o600)
    return document, config_path


def _wrapper(tmp_path: Path, config_path: Path) -> Path:
    release = tmp_path / "releases" / SOURCE_SHA / "scripts"
    release.mkdir(parents=True)
    launcher = release / "mastermind_workbench_action_stdio.py"
    launcher.write_text("# source fixture\n", encoding="utf-8")
    wrapper = tmp_path / "mastermind-workbench-c1"
    wrapper.write_text(
        "#!/bin/sh\n"
        f'exec "{os.path.realpath(sys.executable)}" "{launcher}" --config "{config_path}"\n',
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o700)
    return wrapper


def _status(wrapper: Path, *, workspace_id: str = CHANNEL.workspace_id) -> dict:
    return {
        "healthy": True,
        "ready": True,
        "process_running": True,
        "runtime_state": "ready",
        "remote_lookup_auth_ref": "file:/private/runtime.key",
        "remote": {
            "id": CHANNEL.tunnel_id,
            "organization_ids": [CHANNEL.organization_id],
            "workspace_ids": [workspace_id],
        },
        "process": {
            "profile_name": "mastermind-workbench-c1",
            "profile_dir": "/private/profiles/c1",
            "target_value": str(wrapper),
        },
    }


def _identity(action_id: str, *, purpose: str = "text_patch") -> dict[str, str]:
    return {"action_id": action_id, "purpose": purpose}


def _claim(root: Path, action_id: str, *, purpose: str = "text_patch") -> None:
    (root / f"{action_id}.claim").write_text(
        json.dumps(
            {
                "schema": "mastermind.workbench_action_claim.v1",
                "identity": _identity(action_id, purpose=purpose),
                "claimed_at_ms": 100,
                "phase": "claimed",
            }
        ),
        encoding="utf-8",
    )


def _result(
    root: Path,
    action_id: str,
    *,
    effect_state: str = "APPLIED",
    purpose: str = "text_patch",
    identity_action_id: str | None = None,
) -> None:
    selected_identity = _identity(
        action_id if identity_action_id is None else identity_action_id,
        purpose=purpose,
    )
    (root / f"{action_id}.result").write_text(
        json.dumps(
            {
                "schema": "mastermind.workbench_action_result.v1",
                "identity": selected_identity,
                "effect_state": effect_state,
                "completed_at_ms": 101,
                "durability": "durable",
            }
        ),
        encoding="utf-8",
    )


def test_pinned_executable_accepts_root_owner_and_refuses_foreign_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = Path("/private/fake-python")
    monkeypatch.setattr(fleet_ops_module.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(fleet_ops_module.os, "geteuid", lambda: 501)
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda _self: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o755, st_uid=0, st_nlink=1
        ),
    )

    fleet_ops_module._trusted_pinned_executable(str(selected))

    monkeypatch.setattr(
        Path,
        "lstat",
        lambda _self: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o755, st_uid=12345, st_nlink=1
        ),
    )
    with pytest.raises(FleetOperationError) as caught:
        fleet_ops_module._trusted_pinned_executable(str(selected))

    assert caught.value.code == "TARGET_REFUSED"


def test_doctor_accepts_exact_ready_binding(tmp_path: Path) -> None:
    document, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    now_ms = document["lease"]["lease_expires_at_ms"] - 20 * 24 * 60 * 60 * 1000

    receipt = doctor(
        alias="mastermind-workbench-c1",
        config_path=str(config_path),
        expected_source_sha=SOURCE_SHA,
        now_ms=now_ms,
        runner=lambda _argv: _status(wrapper),
        tool_probe=lambda _argv: None,
    )

    assert receipt.state == "READY"
    assert receipt.tunnel_id == CHANNEL.tunnel_id
    assert receipt.workspace_id == CHANNEL.workspace_id
    assert receipt.source_release_sha == SOURCE_SHA
    assert receipt.completed_action_count == 0
    assert receipt.unresolved_action_ids == ()


def test_doctor_refuses_pinned_project_head_drift(tmp_path: Path) -> None:
    document, config_path = _document(tmp_path)
    document["lease"]["committed_head"] = SOURCE_SHA
    config_path.write_text(json.dumps(document, sort_keys=True), encoding="ascii")
    os.chmod(config_path, 0o600)
    wrapper = _wrapper(tmp_path, config_path)

    with pytest.raises(FleetOperationError) as caught:
        doctor(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            expected_source_sha=SOURCE_SHA,
            runner=lambda _argv: _status(wrapper),
            tool_probe=lambda _argv: None,
            head_probe=lambda _root: "d" * 40,
        )

    assert caught.value.code == "PROJECT_HEAD_MISMATCH"


def test_doctor_refuses_wrapper_interpreter_drift(tmp_path: Path) -> None:
    _document_value, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    launcher = tmp_path / "releases" / SOURCE_SHA / "scripts" / "mastermind_workbench_action_stdio.py"
    wrapper.write_text(
        "#!/bin/sh\n"
        f'exec "/bin/sh" "{launcher}" --config "{config_path}"\n',
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o700)

    with pytest.raises(FleetOperationError) as caught:
        doctor(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            expected_source_sha=SOURCE_SHA,
            runner=lambda _argv: _status(wrapper),
            tool_probe=lambda _argv: None,
        )

    assert caught.value.code == "TARGET_REFUSED"


def test_doctor_refuses_workspace_cross_binding(tmp_path: Path) -> None:
    _document_value, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)

    with pytest.raises(FleetOperationError) as caught:
        doctor(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            expected_source_sha=SOURCE_SHA,
            runner=lambda _argv: _status(wrapper, workspace_id="workspace-other"),
            tool_probe=lambda _argv: None,
        )

    assert caught.value.code == "CHANNEL_BINDING_MISMATCH"


def test_artifact_inspection_blocks_pending_claim_and_accepts_durable_pair(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    pending = "1" * 32
    completed = "2" * 32
    _claim(root, pending)
    _claim(root, completed)
    _result(root, completed)

    receipt = inspect_artifact_evidence(str(root))

    assert receipt.unresolved_action_ids == (pending,)
    assert receipt.completed_action_count == 1


def test_artifact_inspection_refuses_orphan_output_and_identity_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    orphan_output = "5" * 32
    mismatch = "6" * 32
    (root / f"{orphan_output}.stdout").write_bytes(b"partial command output\n")
    _claim(root, mismatch)
    _result(root, mismatch, identity_action_id="7" * 32)

    receipt = inspect_artifact_evidence(str(root))

    assert receipt.unresolved_action_ids == (orphan_output, mismatch)
    assert receipt.completed_action_count == 0


def test_doctor_refuses_unresolved_action_evidence(tmp_path: Path) -> None:
    document, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    _claim(Path(document["artifact_directory"]), "3" * 32)

    with pytest.raises(FleetOperationError) as caught:
        doctor(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            expected_source_sha=SOURCE_SHA,
            runner=lambda _argv: _status(wrapper),
            tool_probe=lambda _argv: None,
        )

    assert caught.value.code == "UNRESOLVED_ACTION_EVIDENCE"


def test_renew_changes_only_expiry_and_reconnects_same_runtime(tmp_path: Path) -> None:
    document, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    calls: list[tuple[str, ...]] = []

    def runner(argv):
        argv = tuple(argv)
        calls.append(argv)
        if argv[2] == "status":
            return _status(wrapper)
        if argv[2] == "stop":
            return {"process_running": False, "runtime_state": "stopped"}
        if argv[2] == "connect":
            assert "--tunnel-id" in argv
            assert argv[argv.index("--tunnel-id") + 1] == CHANNEL.tunnel_id
            assert argv[argv.index("--mcp-command") + 1] == str(wrapper)
            assert (
                argv[argv.index("--runtime-api-key") + 1]
                == "file:/private/runtime.key"
            )
            return {
                "healthy": True,
                "ready": True,
                "runtime_state": "ready",
            }
        raise AssertionError(argv)

    original = json.loads(config_path.read_text(encoding="ascii"))
    now_ms = 1_800_000_000_000
    receipt = renew(
        alias="mastermind-workbench-c1",
        config_path=str(config_path),
        expected_source_sha=SOURCE_SHA,
        extend_ms=30 * 24 * 60 * 60 * 1000,
        now_ms=now_ms,
        runner=runner,
        tool_probe=lambda _argv: None,
        native_probe=lambda _argv: None,
    )
    updated = json.loads(config_path.read_text(encoding="ascii"))

    assert receipt.state == "READY"
    assert updated["lease"]["lease_expires_at_ms"] == (
        now_ms + 30 * 24 * 60 * 60 * 1000
    )
    original["lease"]["lease_expires_at_ms"] = updated["lease"]["lease_expires_at_ms"]
    assert updated == original
    assert [call[2] for call in calls] == ["status", "stop", "connect", "status"]


def test_renew_refuses_same_channel_authority_swap_after_stop(tmp_path: Path) -> None:
    _document_value, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    calls: list[tuple[str, ...]] = []

    def runner(argv):
        argv = tuple(argv)
        calls.append(argv)
        if argv[2] == "status":
            return _status(wrapper)
        if argv[2] == "stop":
            current = json.loads(config_path.read_text(encoding="ascii"))
            current["audit_policy_id"] = "workbench-swapped-policy"
            config_path.write_text(json.dumps(current, sort_keys=True), encoding="ascii")
            os.chmod(config_path, 0o600)
            return {"process_running": False, "runtime_state": "stopped"}
        if argv[2] == "connect":
            raise AssertionError("ambiguous config must not reconnect")
        raise AssertionError(argv)

    with pytest.raises(FleetOperationError) as caught:
        renew(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            extend_ms=30 * 24 * 60 * 60 * 1000,
            runner=runner,
            tool_probe=lambda _argv: None,
            native_probe=lambda _argv: None,
        )

    assert caught.value.code == "CONFIG_CHANGED_DURING_CEREMONY"
    assert [call[2] for call in calls] == ["status", "stop"]


def test_renew_refuses_unresolved_before_runtime_stop(tmp_path: Path) -> None:
    document, config_path = _document(tmp_path)
    _claim(Path(document["artifact_directory"]), "4" * 32)
    calls: list[tuple[str, ...]] = []

    with pytest.raises(FleetOperationError) as caught:
        renew(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            extend_ms=30 * 24 * 60 * 60 * 1000,
            runner=lambda argv: calls.append(tuple(argv)) or {},
            tool_probe=lambda _argv: None,
        )

    assert caught.value.code == "UNRESOLVED_ACTION_EVIDENCE"
    assert calls == []


def test_qualify_stops_probes_and_restores_exact_route(tmp_path: Path) -> None:
    _document_value, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    calls: list[tuple[str, ...]] = []
    probes: list[tuple[str, ...]] = []

    def runner(argv):
        argv = tuple(argv)
        calls.append(argv)
        if argv[2] == "status":
            return _status(wrapper)
        if argv[2] == "stop":
            return {"process_running": False, "runtime_state": "stopped"}
        if argv[2] == "connect":
            return {"healthy": True, "ready": True, "runtime_state": "ready"}
        raise AssertionError(argv)

    receipt = qualify(
        alias="mastermind-workbench-c1",
        config_path=str(config_path),
        expected_source_sha=SOURCE_SHA,
        runner=runner,
        tool_probe=lambda _argv: None,
        native_probe=lambda argv: probes.append(tuple(argv)),
    )

    assert receipt.state == "READY"
    assert probes == [(str(wrapper),)]
    assert [call[2] for call in calls] == [
        "status", "status", "stop", "connect", "status"
    ]


def test_qualify_probe_refusal_recovers_original_runtime(tmp_path: Path) -> None:
    _document_value, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    calls: list[tuple[str, ...]] = []

    def runner(argv):
        argv = tuple(argv)
        calls.append(argv)
        if argv[2] == "status":
            return _status(wrapper)
        if argv[2] == "stop":
            return {"process_running": False, "runtime_state": "stopped"}
        if argv[2] == "connect":
            return {"healthy": True, "ready": True, "runtime_state": "ready"}
        raise AssertionError(argv)

    def refuse(_argv):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")

    with pytest.raises(FleetOperationError) as caught:
        qualify(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            expected_source_sha=SOURCE_SHA,
            runner=runner,
            tool_probe=lambda _argv: None,
            native_probe=refuse,
        )

    assert caught.value.code == "TOOL_CONTRACT_MISMATCH"
    assert [call[2] for call in calls] == ["status", "status", "stop", "connect"]


def test_qualify_config_change_after_stop_stays_stopped(tmp_path: Path) -> None:
    _document_value, config_path = _document(tmp_path)
    wrapper = _wrapper(tmp_path, config_path)
    calls: list[tuple[str, ...]] = []
    probes: list[tuple[str, ...]] = []

    def runner(argv):
        argv = tuple(argv)
        calls.append(argv)
        if argv[2] == "status":
            return _status(wrapper)
        if argv[2] == "stop":
            current = json.loads(config_path.read_text(encoding="ascii"))
            current["audit_policy_id"] = "changed-while-stopped"
            config_path.write_text(json.dumps(current, sort_keys=True), encoding="ascii")
            os.chmod(config_path, 0o600)
            return {"process_running": False, "runtime_state": "stopped"}
        if argv[2] == "connect":
            raise AssertionError("ambiguous config must remain stopped")
        raise AssertionError(argv)

    with pytest.raises(FleetOperationError) as caught:
        qualify(
            alias="mastermind-workbench-c1",
            config_path=str(config_path),
            expected_source_sha=SOURCE_SHA,
            runner=runner,
            tool_probe=lambda _argv: None,
            native_probe=lambda argv: probes.append(tuple(argv)),
        )

    assert caught.value.code == "CONFIG_CHANGED_DURING_CEREMONY"
    assert probes == []
    assert [call[2] for call in calls] == ["status", "status", "stop"]

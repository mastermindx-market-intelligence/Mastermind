from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import web_sol_deployment as deployment
from scripts import web_sol_deployment_apply as cli


def test_cli_rejects_duplicate_json_members_without_effect(
    tmp_path: Path,
    capsys,
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        '{"schema":"first","schema":"second"}',
        encoding="utf-8",
    )
    request.chmod(0o600)

    result = cli.main(["preflight", "--request", str(request)])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {
        "schema": cli.ERROR_SCHEMA,
        "status": "REFUSED",
        "code": "INVALID_INPUT",
        "target_effect": "NONE",
        "production_acceptance_granted": False,
    }


def _bundle(tmp_path: Path) -> tuple[deployment.DeploymentBundle, Path]:
    install_root = tmp_path / "install"
    install_root.mkdir(mode=0o700)
    binding = sb.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "multilogin",
            "folder_id": "11111111-1111-4111-8111-111111111111",
            "profile_id": "22222222-2222-4222-8222-222222222222",
            "url": "https://chatgpt.com/c/cli-test",
        },
        observed_at="2026-09-16T00:00:00Z",
        seat_ref="chatgpt1",
        binding_id="33333333-3333-4333-8333-333333333333",
    )
    release = deployment.WebSolRelease(
        package_version="0.2.0",
        source_commit="a" * 40,
        repository_root=tmp_path / "repo",
        python_executable=Path(sys.executable),
        install_root=install_root,
    )
    return deployment.render_bundle(binding, release), install_root


def _request_document(
    bundle: deployment.DeploymentBundle,
    install_root: Path,
    current_files: dict[str, bytes] | None = None,
) -> dict[str, object]:
    plan = deployment.plan_deployment(
        bundle,
        {} if current_files is None else current_files,
    )
    artifacts = [
        {
            "kind": row.kind,
            "destination": str(row.destination),
            "content_base64": base64.b64encode(row.content).decode("ascii"),
            "mode": row.mode,
            "sha256": row.sha256,
        }
        for row in bundle.artifacts
    ]
    changes = [
        {
            "path": str(row.path),
            "action": row.action,
            "prior_sha256": row.prior_sha256,
            "next_sha256": row.next_sha256,
            "mode": row.mode,
        }
        for row in plan.changes
    ]
    return {
        "schema": cli.REQUEST_SCHEMA,
        "operation_key": "web-sol-install1-transactional-applier-source-20260916-sol-001",
        "install_root": str(install_root),
        "expected_uid": install_root.stat().st_uid,
        "expected_gid": install_root.stat().st_gid,
        "bundle": {
            "instance_id": bundle.instance_id,
            "native_host_name": bundle.native_host_name,
            "source_commit": bundle.source_commit,
            "wrapper_argv": list(bundle.wrapper_argv),
            "bundle_digest": bundle.bundle_digest,
            "artifacts": artifacts,
        },
        "plan": {
            "bundle_digest": plan.bundle_digest,
            "changes": changes,
            "rollback_entries": plan.rollback_manifest["entries"],
        },
    }


def _write_private(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_cli_preflight_emits_only_public_prepared_receipt(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    _write_private(request, _request_document(bundle, install_root))

    result = cli.main(["preflight", "--request", str(request)])

    assert result == 0
    output = capsys.readouterr()
    assert output.err == ""
    receipt = json.loads(output.out)
    assert receipt["schema"] == cli.applier.PREPARED_RECEIPT_SCHEMA
    assert receipt["status"] == "PREPARED"
    assert receipt["target_count"] == 3
    assert receipt["create_count"] == 3
    assert receipt["production_acceptance_granted"] is False
    serialized = json.dumps(receipt, sort_keys=True)
    assert str(install_root) not in serialized
    assert list(install_root.rglob("*")) == []


def test_cli_apply_persists_private_state_and_public_receipt(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))

    result = cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    )

    assert result == 0
    output = capsys.readouterr()
    assert output.err == ""
    receipt = json.loads(output.out)
    assert receipt["schema"] == cli.applier.APPLY_RECEIPT_SCHEMA
    assert receipt["status"] == "APPLIED_VERIFIED"
    assert receipt["target_count"] == 3
    assert receipt["production_acceptance_granted"] is False
    serialized = json.dumps(receipt, sort_keys=True)
    assert str(install_root) not in serialized
    assert state.is_file() and not state.is_symlink()
    assert state.stat().st_mode & 0o777 == 0o600
    private_state = json.loads(state.read_text(encoding="utf-8"))
    assert private_state["schema"] == cli.PRIVATE_STATE_SCHEMA
    assert private_state["phase"] == "APPLIED"
    for artifact in bundle.artifacts:
        assert artifact.destination.read_bytes() == artifact.content
        assert artifact.destination.stat().st_mode & 0o777 == artifact.mode


def test_cli_verify_and_rollback_from_persisted_state(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    capsys.readouterr()

    assert cli.main(["verify", "--state", str(state)]) == 0
    verify_output = capsys.readouterr()
    assert verify_output.err == ""
    verify_receipt = json.loads(verify_output.out)
    assert verify_receipt["schema"] == cli.applier.READBACK_RECEIPT_SCHEMA
    assert verify_receipt["status"] == "READBACK_VERIFIED"
    assert verify_receipt["target_count"] == 3

    assert cli.main(["rollback", "--state", str(state)]) == 0
    rollback_output = capsys.readouterr()
    assert rollback_output.err == ""
    rollback_receipt = json.loads(rollback_output.out)
    assert rollback_receipt["schema"] == cli.applier.ROLLBACK_RECEIPT_SCHEMA
    assert rollback_receipt["status"] == "ROLLBACK_VERIFIED"
    assert rollback_receipt["removed_count"] == 3
    assert rollback_receipt["restored_count"] == 0
    assert list(install_root.rglob("*")) == []
    terminal_state = json.loads(state.read_text(encoding="utf-8"))
    assert terminal_state["phase"] == "ROLLED_BACK"


def test_cli_duplicate_apply_reconciles_applied_state_without_replay(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    first_receipt = json.loads(capsys.readouterr().out)
    first_inodes = {
        str(row.destination): row.destination.stat().st_ino
        for row in bundle.artifacts
    }

    def forbidden_replace(*_args, **_kwargs):
        raise AssertionError("duplicate apply attempted a filesystem replacement")

    monkeypatch.setattr(cli.os, "replace", forbidden_replace)

    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    second_output = capsys.readouterr()
    assert second_output.err == ""
    assert json.loads(second_output.out) == first_receipt
    assert {
        str(row.destination): row.destination.stat().st_ino
        for row in bundle.artifacts
    } == first_inodes


def test_cli_resumes_exact_prepared_state_when_no_target_effect_began(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request_path = tmp_path / "request.json"
    state_path = tmp_path / "state.json"
    request_document = _request_document(bundle, install_root)
    _write_private(request_path, request_document)
    decoded_bundle, plan, metadata = cli._decode_request(request_document)
    prepared = cli.applier.prepare_deployment(
        decoded_bundle,
        plan,
        install_root=metadata["install_root"],
        expected_uid=metadata["expected_uid"],
        expected_gid=metadata["expected_gid"],
        operation_key=metadata["operation_key"],
    )
    initial = cli._private_state_document(
        request_document=request_document,
        prepared=prepared,
        phase="PREPARED",
    )
    cli._write_private_state(state_path, initial, expected_digest=None)

    assert cli.main(
        ["apply", "--request", str(request_path), "--state", str(state_path)]
    ) == 0

    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["status"] == "APPLIED_VERIFIED"
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "APPLIED"
    for artifact in bundle.artifacts:
        assert artifact.destination.read_bytes() == artifact.content


def test_cli_reconciles_exact_postimages_when_state_remained_prepared(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request_path = tmp_path / "request.json"
    state_path = tmp_path / "state.json"
    request_document = _request_document(bundle, install_root)
    _write_private(request_path, request_document)
    decoded_bundle, plan, metadata = cli._decode_request(request_document)
    prepared = cli.applier.prepare_deployment(
        decoded_bundle,
        plan,
        install_root=metadata["install_root"],
        expected_uid=metadata["expected_uid"],
        expected_gid=metadata["expected_gid"],
        operation_key=metadata["operation_key"],
    )
    initial = cli._private_state_document(
        request_document=request_document,
        prepared=prepared,
        phase="PREPARED",
    )
    cli._write_private_state(state_path, initial, expected_digest=None)
    applied = cli.applier.apply_deployment(prepared)
    assert applied.public_receipt["status"] == "APPLIED_VERIFIED"

    def forbidden_apply(_prepared):
        raise AssertionError("reconciliation replayed the deployment")

    monkeypatch.setattr(cli.applier, "apply_deployment", forbidden_apply)

    assert cli.main(
        ["apply", "--request", str(request_path), "--state", str(state_path)]
    ) == 0

    output = capsys.readouterr()
    assert output.err == ""
    receipt = json.loads(output.out)
    assert receipt["status"] == "APPLIED_VERIFIED"
    assert receipt["changed_count"] == 3
    assert receipt["reconciled_count"] == 3
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "APPLIED"


def test_cli_mixed_prepared_state_is_effect_unknown_without_replay(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request_path = tmp_path / "request.json"
    state_path = tmp_path / "state.json"
    request_document = _request_document(bundle, install_root)
    _write_private(request_path, request_document)
    decoded_bundle, plan, metadata = cli._decode_request(request_document)
    prepared = cli.applier.prepare_deployment(
        decoded_bundle,
        plan,
        install_root=metadata["install_root"],
        expected_uid=metadata["expected_uid"],
        expected_gid=metadata["expected_gid"],
        operation_key=metadata["operation_key"],
    )
    initial = cli._private_state_document(
        request_document=request_document,
        prepared=prepared,
        phase="PREPARED",
    )
    cli._write_private_state(state_path, initial, expected_digest=None)
    first = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    first.destination.parent.mkdir(parents=True, mode=0o700)
    first.destination.write_bytes(first.content)
    first.destination.chmod(first.mode)

    assert cli.main(
        ["apply", "--request", str(request_path), "--state", str(state_path)]
    ) == 2

    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)
    assert error["code"] == "APPLY_EFFECT_UNKNOWN"
    assert error["target_effect"] == "UNKNOWN"
    assert first.destination.read_bytes() == first.content
    assert sum(row.destination.exists() for row in bundle.artifacts) == 1
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "PREPARED"


def test_cli_rejects_tampered_state_digest_without_target_effect(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    capsys.readouterr()
    document = json.loads(state.read_text(encoding="utf-8"))
    document["phase"] = "ROLLED_BACK"
    _write_private(state, document)

    assert cli.main(["verify", "--state", str(state)]) == 2

    output = capsys.readouterr()
    error = json.loads(output.err)
    assert error["code"] == "STATE_INVALID"
    assert error["target_effect"] == "NONE"
    for artifact in bundle.artifacts:
        assert artifact.destination.read_bytes() == artifact.content


def test_cli_rejects_changed_request_against_existing_state(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    original = _request_document(bundle, install_root)
    _write_private(request, original)
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    capsys.readouterr()
    changed = json.loads(json.dumps(original))
    changed["operation_key"] = "web-sol-install1-different-operation-20260916-sol-001"
    _write_private(request, changed)

    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 2

    output = capsys.readouterr()
    error = json.loads(output.err)
    assert error["code"] == "STATE_CONFLICT"
    assert error["target_effect"] == "NONE"
    for artifact in bundle.artifacts:
        assert artifact.destination.read_bytes() == artifact.content


def test_cli_duplicate_rollback_is_terminal_and_effect_none(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    capsys.readouterr()
    assert cli.main(["rollback", "--state", str(state)]) == 0
    capsys.readouterr()

    assert cli.main(["rollback", "--state", str(state)]) == 2

    output = capsys.readouterr()
    error = json.loads(output.err)
    assert error["code"] == "TRANSACTION_CONSUMED"
    assert error["target_effect"] == "NONE"
    assert list(install_root.rglob("*")) == []


def test_cli_reconciles_completed_rollback_when_state_remained_applied(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    capsys.readouterr()
    phase, _request, _prepared, applied, _digest = cli._decode_private_state(
        cli._private_json_file(state)
    )
    assert phase == "APPLIED" and applied is not None
    direct_receipt = cli.applier.rollback_deployment(applied)
    assert direct_receipt["status"] == "ROLLBACK_VERIFIED"
    assert list(install_root.rglob("*")) == []

    def forbidden_rollback(_applied):
        raise AssertionError("rollback reconciliation repeated filesystem effects")

    monkeypatch.setattr(cli.applier, "rollback_deployment", forbidden_rollback)

    assert cli.main(["rollback", "--state", str(state)]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    receipt = json.loads(output.out)
    assert receipt["status"] == "ROLLBACK_VERIFIED"
    assert receipt["removed_count"] == 3
    assert json.loads(state.read_text(encoding="utf-8"))["phase"] == "ROLLED_BACK"


def test_cli_state_parent_symlink_swap_never_writes_outside_state_directory(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    _write_private(request, _request_document(bundle, install_root))
    state_parent = tmp_path / "state-parent"
    state_parent.mkdir(mode=0o700)
    state = state_parent / "state.json"
    outside = tmp_path / "state-outside"
    outside.mkdir(mode=0o700)
    displaced = tmp_path / "state-parent-displaced"
    original_replace = cli.os.replace
    injected = False

    def swap_parent_then_replace(source, target, *args, **kwargs):
        nonlocal injected
        if not injected and Path(target).name == state.name:
            injected = True
            source_fd = kwargs.get("src_dir_fd")
            if source_fd is None:
                payload = Path(source).read_bytes()
            else:
                descriptor = cli.os.open(str(source), cli.os.O_RDONLY, dir_fd=source_fd)
                try:
                    payload = b""
                    while True:
                        chunk = cli.os.read(descriptor, 65536)
                        if not chunk:
                            break
                        payload += chunk
                finally:
                    cli.os.close(descriptor)
            state_parent.rename(displaced)
            state_parent.symlink_to(outside, target_is_directory=True)
            attack_temp = outside / Path(source).name
            attack_temp.write_bytes(payload)
            attack_temp.chmod(0o600)
        return original_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(cli.os, "replace", swap_parent_then_replace)

    result = cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    )

    assert injected is True
    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "STATE_EFFECT_UNKNOWN"
    assert not (outside / state.name).exists()
    assert list(install_root.rglob("*")) == []


def test_cli_rollback_refuses_state_through_symlinked_parent_before_target_effect(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    _write_private(request, _request_document(bundle, install_root))
    state_parent = tmp_path / "state-parent-read"
    state_parent.mkdir(mode=0o700)
    state = state_parent / "state.json"
    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 0
    capsys.readouterr()
    outside = tmp_path / "state-outside-read"
    outside.mkdir(mode=0o700)
    copied = outside / state.name
    copied.write_bytes(state.read_bytes())
    copied.chmod(0o600)
    displaced = tmp_path / "state-parent-read-displaced"
    state_parent.rename(displaced)
    state_parent.symlink_to(outside, target_is_directory=True)

    result = cli.main(["rollback", "--state", str(state)])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "STATE_INVALID"
    for artifact in bundle.artifacts:
        assert artifact.destination.read_bytes() == artifact.content



def test_cli_refuses_state_inside_install_root_before_target_effect(
    tmp_path: Path,
    capsys,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = install_root / "transaction-state.json"
    _write_private(request, _request_document(bundle, install_root))

    result = cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    )

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {
        "schema": cli.ERROR_SCHEMA,
        "status": "REFUSED",
        "code": "INVALID_INPUT",
        "target_effect": "NONE",
        "production_acceptance_granted": False,
    }
    assert not state.exists()
    assert list(install_root.rglob("*")) == []



def test_cli_refuses_state_capsule_larger_than_its_read_limit_before_effect(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    request_document = _request_document(bundle, install_root)
    _write_private(request, request_document)
    monkeypatch.setattr(cli, "MAX_JSON_BYTES", len(request.read_bytes()) + 128)

    result = cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    )

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {
        "schema": cli.ERROR_SCHEMA,
        "status": "REFUSED",
        "code": "STATE_INVALID",
        "target_effect": "NONE",
        "production_acceptance_granted": False,
    }
    assert not state.exists()
    assert list(install_root.rglob("*")) == []



def test_cli_request_parent_swap_never_reads_outside_private_file(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request_parent = tmp_path / "request-parent"
    request_parent.mkdir(mode=0o700)
    request = request_parent / "request.json"
    _write_private(request, _request_document(bundle, install_root))

    outside = tmp_path / "outside-request"
    outside.mkdir(mode=0o700)
    alternate = _request_document(bundle, install_root)
    alternate["operation_key"] = "outside-substituted-operation"
    _write_private(outside / request.name, alternate)
    displaced = tmp_path / "displaced-request-parent"
    original_lstat = Path.lstat
    original_open = Path.open
    injected = False
    outside_read = False

    def swap_parent_after_request_lstat(self: Path):
        nonlocal injected
        info = original_lstat(self)
        if self == request and not injected:
            injected = True
            request_parent.rename(displaced)
            request_parent.symlink_to(outside, target_is_directory=True)
        return info

    def track_path_open(self: Path, *args, **kwargs):
        nonlocal outside_read
        if self == request and injected:
            outside_read = True
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", swap_parent_after_request_lstat)
    monkeypatch.setattr(Path, "open", track_path_open)

    result = cli.main(["preflight", "--request", str(request)])
    output = capsys.readouterr()

    assert result in {0, 2}
    assert outside_read is False
    if result == 0:
        receipt = json.loads(output.out)
        assert receipt["operation_key"] != "outside-substituted-operation"
    assert list(install_root.rglob("*")) == []



def test_cli_persists_preimage_conflict_without_replay(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[1]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    target.destination.parent.chmod(0o700)
    prior = b"approved-cli-preimage-before-temporary"
    target.destination.write_bytes(prior)
    target.destination.chmod(target.mode)

    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(
        request,
        _request_document(
            bundle,
            install_root,
            current_files={str(target.destination): prior},
        ),
    )

    original_write = cli.applier._write_exact_temporary_at
    foreign = b"concurrent-cli-owner-change"
    injected = False

    def write_then_change_target(*args, **kwargs) -> None:
        nonlocal injected
        original_write(*args, **kwargs)
        parent_descriptor, temporary_name = args[:2]
        prepared = args[4]
        if (
            injected
            or temporary_name
            != cli.applier._temporary_path(target, prepared).name
        ):
            return
        injected = True
        flags = cli.applier.os.O_WRONLY | cli.applier.os.O_TRUNC
        if hasattr(cli.applier.os, "O_NOFOLLOW"):
            flags |= cli.applier.os.O_NOFOLLOW
        descriptor = cli.applier.os.open(
            target.destination.name,
            flags,
            dir_fd=parent_descriptor,
        )
        try:
            view = memoryview(foreign)
            offset = 0
            while offset < len(view):
                written = cli.applier.os.write(descriptor, view[offset:])
                assert written > 0
                offset += written
            cli.applier.os.fsync(descriptor)
        finally:
            cli.applier.os.close(descriptor)

    monkeypatch.setattr(
        cli.applier,
        "_write_exact_temporary_at",
        write_then_change_target,
    )

    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 2
    first_output = capsys.readouterr()
    assert first_output.out == ""
    first_error = json.loads(first_output.err)
    assert first_error["code"] == "PREIMAGE_CONFLICT"
    assert first_error["target_effect"] == "NONE"
    assert injected is True
    assert target.destination.read_bytes() == foreign
    assert json.loads(state.read_text(encoding="utf-8"))["phase"] == "CONFLICT"

    def forbidden_replay(_prepared):
        raise AssertionError("terminal conflict replayed target effects")

    monkeypatch.setattr(cli.applier, "apply_deployment", forbidden_replay)

    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 2
    second_output = capsys.readouterr()
    assert second_output.out == ""
    second_error = json.loads(second_output.err)
    assert second_error["code"] == "TRANSACTION_CONSUMED"
    assert second_error["target_effect"] == "NONE"
    assert target.destination.read_bytes() == foreign



def test_cli_persists_exact_abort_without_replay(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request = tmp_path / "request.json"
    state = tmp_path / "state.json"
    _write_private(request, _request_document(bundle, install_root))

    original_write = cli.applier._write_exact_temporary_at
    calls = 0

    def fail_after_second_temporary(*args, **kwargs) -> None:
        nonlocal calls
        original_write(*args, **kwargs)
        calls += 1
        if calls == 2:
            raise cli.applier.WebSolDeploymentApplyError(
                "TEMPORARY_WRITE_FAILED"
            )

    monkeypatch.setattr(
        cli.applier,
        "_write_exact_temporary_at",
        fail_after_second_temporary,
    )

    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 2
    first_output = capsys.readouterr()
    assert first_output.out == ""
    first_error = json.loads(first_output.err)
    assert first_error["code"] == "APPLY_ABORTED_ROLLED_BACK"
    assert first_error["target_effect"] == "NONE"
    assert calls == 2
    assert list(install_root.rglob("*")) == []
    assert (
        json.loads(state.read_text(encoding="utf-8"))["phase"]
        == "ABORTED_ROLLED_BACK"
    )

    def forbidden_replay(_prepared):
        raise AssertionError("exactly rolled-back apply was replayed")

    monkeypatch.setattr(cli.applier, "apply_deployment", forbidden_replay)

    assert cli.main(
        ["apply", "--request", str(request), "--state", str(state)]
    ) == 2
    second_output = capsys.readouterr()
    assert second_output.out == ""
    second_error = json.loads(second_output.err)
    assert second_error["code"] == "TRANSACTION_CONSUMED"
    assert second_error["target_effect"] == "NONE"
    assert list(install_root.rglob("*")) == []


def test_private_state_preserves_cleanup_nonce(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    request_document = _request_document(bundle, install_root)
    decoded_bundle, plan, metadata = cli._decode_request(request_document)
    prepared = cli.applier.prepare_deployment(
        decoded_bundle,
        plan,
        install_root=metadata["install_root"],
        expected_uid=metadata["expected_uid"],
        expected_gid=metadata["expected_gid"],
        operation_key=metadata["operation_key"],
    )
    document = cli._private_state_document(
        request_document=request_document,
        prepared=prepared,
        phase="PREPARED",
    )

    nonce = document["prepared"].get("cleanup_nonce")
    assert type(nonce) is str and len(nonce) == 32
    phase, _request, restored, applied, _digest = cli._decode_private_state(document)
    assert phase == "PREPARED"
    assert applied is None
    assert cli.applier._cleanup_quarantine_name("fixed.tmp", restored) == (
        cli.applier._cleanup_quarantine_name("fixed.tmp", prepared)
    )

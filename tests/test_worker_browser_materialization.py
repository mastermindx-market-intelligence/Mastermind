"""The trusted admission must bind the exact Control-authorized launch.

A live owned process generation proves only that SOME process is held by this
Attempt. Only the operator materialization receipt proves it is the launch
Control actually admitted. These cases are discriminating: each one leaves the
whole existing lease/generation/attestation chain valid and breaks nothing but
the launch binding, so they fail if that binding is removed.

Nothing here grants the Worker a store, lease, token or run-root policy; the
admission stays supervisor-side and the Worker gets only the served stdio pair.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path

import pytest

from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from tests.test_workbench_browser_tunnel import _call, _error_code
from tests.test_worker_browser_admission import _materialize, _setup


def _root(tmp_path, name):
    path = Path(tmp_path) / name
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def _drive(config, build):
    """Run one admission against the browser surface and return its outcome."""

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            server = build(runtime)
            return await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    return asyncio.run(exercise())


def test_matching_receipt_admits_the_exact_launch(tmp_path):
    """Positive control: the binding must not refuse a correct launch."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    result = _drive(config, lambda runtime: api.create_worker_browser_server(
        runtime, config.browser, api.WorkerBrowserAdmission(
            executive.store, lease, epoch, generation, requested, profile,
            "worker-browser-isolated", runtime,
            run_root=run_root, expected_owner_uid=os.getuid())))
    assert result.structuredContent["status"] == "PREPARED"


@pytest.mark.parametrize("field,value", [
    ("pid", 202),
    ("pgid", 202),
    ("process_start_identity", "other-process-start"),
    ("boot_id", "other-boot"),
])
def test_receipt_process_identity_must_match_owned_generation(
    tmp_path, field, value
):
    """The logical launch IDs are insufficient without exact OS-process identity."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    other = _root(tmp_path, f"process-mismatch-{field}")
    process_identity = {
        "pid": 101,
        "pgid": 101,
        "process_start_identity": "fixture-start",
        "boot_id": "fixture-boot",
    }
    process_identity[field] = value
    process_credentials = {
        "process_identity": dict(process_identity),
        "os_principal_name": "fixture",
        "os_principal_uid": os.getuid(),
    }
    _materialize(
        other, executive, epoch, generation, requested,
        process_identity=process_identity,
        process_credentials=process_credentials,
    )

    result = _drive(config, lambda runtime: api.create_worker_browser_server(
        runtime, config.browser, api.WorkerBrowserAdmission(
            executive.store, lease, epoch, generation, requested, profile,
            "worker-browser-isolated", runtime,
            run_root=other, expected_owner_uid=os.getuid())))
    assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
    assert list(Path(config.action.artifact_directory).iterdir()) == []


@pytest.mark.parametrize("field,value", [
    ("session_epoch_id", "EPOCH-other"),
    ("process_generation_id", "GEN-other"),
    ("requested_profile_digest", "d" * 64),
    ("provider_session_id", "another-provider-session"),
])
def test_receipt_for_a_different_launch_refuses_before_any_browser_effect(
    tmp_path, field, value
):
    """Every id the receipt pins must equal the live owner, or admission fails."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    other = _root(tmp_path, f"mismatch-{field}")
    _materialize(other, executive, epoch, generation, requested, **{field: value})

    result = _drive(config, lambda runtime: api.create_worker_browser_server(
        runtime, config.browser, api.WorkerBrowserAdmission(
            executive.store, lease, epoch, generation, requested, profile,
            "worker-browser-isolated", runtime,
            run_root=other, expected_owner_uid=os.getuid())))
    assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
    assert list(Path(config.action.artifact_directory).iterdir()) == []


def test_receipt_contract_itself_bars_a_foreign_worker_identity(tmp_path):
    """Not this layer's guarantee: the receipt contract refuses to even build a
    receipt whose worker differs from its own attestation. Recorded so the
    admission is not credited with a defense that lives upstream of it."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    from control_plane.operator_materialization_receipt import (
        OperatorMaterializationReceiptError,
    )
    with pytest.raises(OperatorMaterializationReceiptError,
                       match="worker identity differs"):
        _materialize(_root(tmp_path, "foreign-worker"), executive, epoch,
                     generation, requested, worker_id="worker-99")


def test_absent_materialization_receipt_refuses(tmp_path):
    """No Control-authorized launch is absence of authority, never a retry."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    empty = _root(tmp_path, "no-receipt")

    result = _drive(config, lambda runtime: api.create_worker_browser_server(
        runtime, config.browser, api.WorkerBrowserAdmission(
            executive.store, lease, epoch, generation, requested, profile,
            "worker-browser-isolated", runtime,
            run_root=empty, expected_owner_uid=os.getuid())))
    assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
    assert list(Path(config.action.artifact_directory).iterdir()) == []


def test_tampered_receipt_file_refuses(tmp_path):
    """An unreadable or rewritten receipt is refused, not treated as absent."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    receipts = list(Path(run_root).rglob("receipt.json"))
    assert len(receipts) == 1
    receipts[0].write_text("{\"schema\": \"tampered\"}", encoding="utf-8")

    result = _drive(config, lambda runtime: api.create_worker_browser_server(
        runtime, config.browser, api.WorkerBrowserAdmission(
            executive.store, lease, epoch, generation, requested, profile,
            "worker-browser-isolated", runtime,
            run_root=run_root, expected_owner_uid=os.getuid())))
    assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
    assert list(Path(config.action.artifact_directory).iterdir()) == []


def test_attestation_resealed_after_materialization_refuses(tmp_path):
    """Defense-in-depth, already owned upstream: a reseal that keeps the digest
    self-consistent is caught by the existing compare_launch check, NOT by the
    materialization binding added here (verified by mutation: this case still
    refuses with the binding removed). Kept as a regression guard, and recorded
    so the new binding is not credited with it."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)
    with executive.store.read() as connection:
        raw = connection.execute(
            "SELECT observed_attestation_json FROM process_generations"
        ).fetchone()["observed_attestation_json"]
    changed = json.loads(raw)
    changed["harness_binary_digest"] = "e" * 64
    payload = json.dumps(changed)
    import hashlib
    with executive.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET observed_attestation_json=?, "
            "observed_attestation_digest=?",
            (payload, hashlib.sha256(payload.encode()).hexdigest()))

    result = _drive(config, lambda runtime: api.create_worker_browser_server(
        runtime, config.browser, api.WorkerBrowserAdmission(
            executive.store, lease, epoch, generation, requested, profile,
            "worker-browser-isolated", runtime,
            run_root=run_root, expected_owner_uid=os.getuid())))
    assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
    assert list(Path(config.action.artifact_directory).iterdir()) == []


def test_generation_without_a_materialization_command_refuses_construction(tmp_path):
    """Only the frozen G1-start/G2-resume law has a command; invent no third."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            with pytest.raises(ValueError, match="BROWSER_WORKER_ADMISSION_REFUSED"):
                api.WorkerBrowserAdmission(
                    executive.store, lease, epoch,
                    dataclasses.replace(generation, generation_number=3),
                    requested, profile, "worker-browser-isolated", runtime,
                    run_root=run_root, expected_owner_uid=os.getuid())
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())


@pytest.mark.parametrize("run_root_value", ["operator-run-root", 7, None])
def test_relative_or_untyped_run_root_refuses_construction(tmp_path, run_root_value):
    """A misconfigured launch-custody root fails closed at build, not per call."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            with pytest.raises(ValueError, match="BROWSER_WORKER_ADMISSION_REFUSED"):
                api.WorkerBrowserAdmission(
                    executive.store, lease, epoch, generation, requested, profile,
                    "worker-browser-isolated", runtime,
                    run_root=run_root_value, expected_owner_uid=os.getuid())
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())


def test_admission_never_exposes_launch_custody_to_the_worker(tmp_path):
    """RuntimeStore, lease token and run-root policy stay supervisor-side."""
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = _setup(tmp_path)

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(
                executive.store, lease, epoch, generation, requested, profile,
                "worker-browser-isolated", runtime,
                run_root=run_root, expected_owner_uid=os.getuid())
            text = repr(admission) + repr(admission.grant)
            assert lease.lease_token not in text
            assert str(run_root) not in text
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())

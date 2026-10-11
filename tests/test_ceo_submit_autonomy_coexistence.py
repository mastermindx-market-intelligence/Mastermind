"""Parent acceptance tests for the paired full-autonomy/CEO authority boundary."""
import copy
import dataclasses
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from ops.executive_os import autonomy_control as control
from tests import test_executive_autonomy as receipts
from tests import test_executive_autonomy_control as hosts


def full_host():
    host = hosts.FakeCeoSubmitHost()
    host.control_config.update(coo_autonomy_armed=True, coo_operator_harness_armed=True)
    host.worker_config["operator_harness_armed"] = True
    return host


def full_receipt(configs):
    return receipts._receipt(
        release_sha=hosts.SHA,
        control_config_sha256=configs.control_sha256,
        worker_config_sha256=configs.worker_sha256,
        capability_policy_digest=control.CAPABILITY_POLICY_DIGEST,
        execution_profile_digest=control.EXECUTION_PROFILE_DIGEST,
        native_helper_grant_digest=control.NATIVE_HELPER_GRANT_DIGEST,
        security_config_digest=control.SECURITY_CONFIG_DIGEST,
    )


def test_full_arm_admission_requires_current_sealed_pair(monkeypatch):
    host = full_host()
    configs = host.load_ceo_submit_configs(hosts.SHA)
    proof = full_receipt(configs)
    # Exercise the production proof, not a fake true verdict.
    method = getattr(control, "coexistence_receipt_eligible", None)
    assert callable(method), "full-arm eligibility still has no sealed-pair proof"
    host.proves_safe_coexistence = lambda value: method(
        value, proof, receipts._metadata(), expected_sha=hosts.SHA, now=hosts.NOW
    )
    admitted = control.evaluate_ceo_submit_arm_admission(
        host, hosts._ceo_submit_request(), now=hosts.NOW
    )
    assert admitted.configs == configs
    assert host.control_writes == host.worker_writes == 0


@pytest.mark.parametrize("defect", ["absent", "expired", "worker", "control", "release", "metadata", "split", "predicate"])
def test_full_arm_proof_refuses_drift(defect):
    host = full_host()
    configs = host.load_ceo_submit_configs(hosts.SHA)
    proof = full_receipt(configs)
    metadata = receipts._metadata()
    if defect == "absent": proof = None
    if defect == "expired": proof["readiness_expires_at"] = "2026-08-24T12:00:00Z"
    if defect in {"worker", "control"}: proof[defect + "_config_sha256"] = "f" * 64
    if defect == "release": proof["release_sha"] = "f" * 40
    if defect == "metadata": metadata = dataclasses.replace(metadata, mode=0o644)
    if defect == "split": configs.control["coo_operator_harness_armed"] = False
    if defect == "predicate": proof["predicates"]["gate_b_passed"] = False
    method = getattr(control, "coexistence_receipt_eligible", None)
    assert callable(method), "full-arm eligibility still has no sealed-pair proof"
    assert not method(configs, proof, metadata, expected_sha=hosts.SHA, now=hosts.NOW)


def test_rebound_receipt_preserves_existing_authority_and_expiry():
    host = full_host()
    configs = host.load_ceo_submit_configs(hosts.SHA)
    proof = full_receipt(configs)
    candidates = control.derive_ceo_submit_candidate(configs, armed=True)
    transaction = control.TransactionContext(
        transaction_id="autonomy-012345abcdef", expected_sha=hosts.SHA,
        prior_configs=configs, candidates=candidates, admission=None,
    )
    method = getattr(control, "rebind_coexistence_receipt", None)
    assert callable(method), "CEO flag changes still invalidate the autonomy seal"
    rebound = method(transaction, proof)
    assert rebound["control_config_sha256"] == candidates.control_sha256
    allowed = {"control_config_sha256", "prior_control_config_sha256", "transaction_id"}
    assert {key for key in proof if proof[key] != rebound[key]} <= allowed
    assert candidates.worker_bytes == configs.worker_bytes
    assert rebound["readiness_expires_at"] == proof["readiness_expires_at"]
    post = dataclasses.replace(configs, control=candidates.control, control_sha256=candidates.control_sha256,
                               control_bytes=candidates.control_bytes)
    assert control.coexistence_receipt_eligible(post, rebound, receipts._metadata(), expected_sha=hosts.SHA, now=hosts.NOW)


def production_pair(monkeypatch, tmp_path):
    """Real file/flock transaction; only privilege and service adapters are fake."""
    from control_plane import executive_autonomy
    root, marker = hosts._inprocess_marker_host(monkeypatch, tmp_path)
    monkeypatch.setattr(executive_autonomy, "_macos_acl", lambda _path: False)
    for path, updates in ((control.CONTROL_CONFIG, {"coo_autonomy_armed": True, "coo_operator_harness_armed": True}),
                          (control.WORKER_CONFIG, {"operator_harness_armed": True})):
        document = json.loads(path.read_bytes()); document.update(updates)
        path.chmod(0o600); path.write_bytes(control.encode_config(document)); path.chmod(0o440)
    host = hosts._harness_ceo_submit_host()
    host._read_control_launchd_disabled_override = lambda: False
    configs = host.load_ceo_submit_configs(hosts.SHA)
    proof = full_receipt(configs)
    now = datetime.now(UTC).replace(microsecond=0)
    proof.update(observed_at=control._iso(now), readiness_observed_at=control._iso(now),
                 credential_expires_at=control._iso(now + timedelta(hours=2)),
                 readiness_expires_at=control._iso(now + timedelta(hours=1)))
    control.AUTONOMY_RECEIPT.write_bytes(control._encoded_json(proof))
    control.AUTONOMY_RECEIPT.chmod(0o444)
    host._prove_rolled_back_control_live = lambda tx: host._persist_phase(tx, "ROLLBACK_CONTROL_PROVEN")
    return host, marker, configs, proof


def test_production_full_arm_then_ceo_arm_disarm_preserves_worker_and_authority(monkeypatch, tmp_path):
    host, marker, before, proof = production_pair(monkeypatch, tmp_path)
    worker_info = control.WORKER_CONFIG.stat()
    result = control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    assert result.state == "CEO_SUBMIT_ARMED" and not marker.exists()
    post = host.load_ceo_submit_configs(hosts.SHA)
    assert post.control["ceo_submit_armed"] is True and host.proves_safe_coexistence(post)
    assert control.WORKER_CONFIG.read_bytes() == before.worker_bytes
    assert control.WORKER_CONFIG.stat().st_ino == worker_info.st_ino
    assert control.WORKER_CONFIG.stat().st_mode == worker_info.st_mode
    control.require_ceo_submit_runtime_admission(post.control, own_config_sha256=post.control_sha256)
    assert control.evaluate_ceo_submit_status(host, hosts._ceo_submit_request()).state == "CEO_SUBMIT_ARMED"
    result = control.execute_ceo_submit_disarm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    final = host.load_ceo_submit_configs(hosts.SHA)
    assert result.state == "CEO_SUBMIT_DISARMED" and not marker.exists()
    assert final.control["ceo_submit_armed"] is False and host.proves_safe_coexistence(final)
    assert control.WORKER_CONFIG.read_bytes() == before.worker_bytes
    assert json.loads(control.AUTONOMY_RECEIPT.read_bytes())["readiness_expires_at"] == proof["readiness_expires_at"]
    with pytest.raises(control.CeoSubmitAdmissionError):
        control.require_ceo_submit_runtime_admission(final.control, own_config_sha256=final.control_sha256)


@pytest.mark.parametrize("fault", ["rebind_full_autonomy_receipt", "replace_control_config", "write_ceo_submit_receipt", "reconcile_control_service"])
@pytest.mark.parametrize("disarm", [False, True])
def test_production_pair_rolls_back_both_receipts_byte_exact(monkeypatch, tmp_path, fault, disarm):
    host, marker, _, _ = production_pair(monkeypatch, tmp_path)
    if disarm:
        control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    paths = (control.CONTROL_CONFIG, control.WORKER_CONFIG, control.AUTONOMY_RECEIPT, control.CEO_SUBMIT_RECEIPT)
    before = [p.read_bytes() if p.exists() else None for p in paths]
    real = getattr(host, fault)
    def after_write(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("injected known failure after owned write")
    monkeypatch.setattr(host, fault, after_write)
    execute = control.execute_ceo_submit_disarm if disarm else control.execute_ceo_submit_arm
    with pytest.raises(control.ArmTransactionError):
        execute(host, hosts._ceo_submit_request(), now=hosts.NOW)
    assert [p.read_bytes() if p.exists() else None for p in paths] == before
    assert not marker.exists()


def test_runtime_guard_never_reads_worker_config_and_refuses_pair_drift(monkeypatch, tmp_path):
    host, marker, _, _ = production_pair(monkeypatch, tmp_path)
    control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    post = host.load_ceo_submit_configs(hosts.SHA)
    original = control.load_receipt_file
    reads = []
    def observe(path):
        reads.append(path)
        assert path != control.WORKER_CONFIG
        return original(path)
    monkeypatch.setattr(control, "load_receipt_file", observe)
    control.require_ceo_submit_runtime_admission(post.control, own_config_sha256=post.control_sha256)
    assert reads == [control.CEO_SUBMIT_RECEIPT, control.AUTONOMY_RECEIPT]
    marker.mkdir(mode=0o700)
    with pytest.raises(control.CeoSubmitAdmissionError):
        control.require_ceo_submit_runtime_admission(post.control, own_config_sha256=post.control_sha256)
    marker.rmdir()
    with pytest.raises(control.CeoSubmitAdmissionError):
        control.require_ceo_submit_runtime_admission(post.control, own_config_sha256="f" * 64)


def test_unknown_effect_stays_on_original_marker_and_cannot_replay(monkeypatch, tmp_path):
    host, marker, _, _ = production_pair(monkeypatch, tmp_path)
    real = host.rebind_full_autonomy_receipt
    def lost_return(transaction):
        real(transaction)
        raise control.TransactionEffectUnknown()
    monkeypatch.setattr(host, "rebind_full_autonomy_receipt", lost_return)
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
        manifest = (marker / "transaction.json").read_bytes()
        with pytest.raises(control.TransactionEffectUnknown):
            control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
        assert (marker / "transaction.json").read_bytes() == manifest
        assert set(control._COEXISTENCE_ARCHIVES) <= {p.name for p in marker.iterdir()}
    finally:
        if host._transaction_owner_fd is not None: host._release_transaction_owner()


@pytest.mark.parametrize("fault", ["rebind_full_autonomy_receipt", "replace_control_config", "write_ceo_submit_receipt", "reconcile_control_service"])
@pytest.mark.parametrize("disarm", [False, True])
def test_same_marker_recovery_restores_pair_after_lost_response(monkeypatch, tmp_path, fault, disarm):
    host, marker, _, _ = production_pair(monkeypatch, tmp_path)
    if disarm:
        control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    paths = (control.CONTROL_CONFIG, control.WORKER_CONFIG, control.AUTONOMY_RECEIPT, control.CEO_SUBMIT_RECEIPT)
    before = [p.read_bytes() if p.exists() else None for p in paths]
    original = getattr(host, fault)
    def lost_response(*args):
        original(*args)
        raise control.TransactionEffectUnknown()
    monkeypatch.setattr(host, fault, lost_response)
    execute = control.execute_ceo_submit_disarm if disarm else control.execute_ceo_submit_arm
    with pytest.raises(control.TransactionEffectUnknown):
        execute(host, hosts._ceo_submit_request(), now=hosts.NOW)
    manifest = json.loads((marker / "transaction.json").read_bytes())
    assert manifest[control._CONTROL_LAUNCHD_PREIMAGE_FIELD] is False
    host._release_transaction_owner()  # simulate controller exit; retain same marker
    recovered = hosts._harness_ceo_submit_host()
    recovered._read_control_launchd_disabled_override = lambda: False
    recovered._prove_rolled_back_control_live = lambda tx: recovered._persist_phase(tx, "ROLLBACK_CONTROL_PROVEN")
    result = recovered.recover_ceo_submit_effect_unknown(hosts._ceo_submit_request(), now=hosts.NOW)
    assert result.transaction_id == manifest["transaction_id"]
    assert result.state == ("CEO_SUBMIT_ARMED" if disarm else "CEO_SUBMIT_DISARMED")
    assert [p.read_bytes() if p.exists() else None for p in paths] == before
    assert not marker.exists()


@pytest.mark.parametrize("defect", ["archive", "foreign-control", "foreign-receipt"])
def test_pair_recovery_never_overwrites_unowned_or_unsealed_state(monkeypatch, tmp_path, defect):
    host, marker, _, _ = production_pair(monkeypatch, tmp_path)
    original = host.write_ceo_submit_receipt
    def lost_response(*args):
        original(*args)
        raise control.TransactionEffectUnknown()
    monkeypatch.setattr(host, "write_ceo_submit_receipt", lost_response)
    with pytest.raises(control.TransactionEffectUnknown):
        control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    target = {"archive": marker / control._COEXISTENCE_ARCHIVES[0],
              "foreign-control": control.CONTROL_CONFIG,
              "foreign-receipt": control.AUTONOMY_RECEIPT}[defect]
    mode = target.stat().st_mode & 0o777
    target.chmod(0o600); target.write_bytes(target.read_bytes() + b" \n"); target.chmod(mode)
    protected = [control.CONTROL_CONFIG, control.WORKER_CONFIG, control.AUTONOMY_RECEIPT, control.CEO_SUBMIT_RECEIPT]
    before = [p.read_bytes() for p in protected]
    host._release_transaction_owner()
    recovered = hosts._harness_ceo_submit_host()
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            recovered.recover_ceo_submit_effect_unknown(hosts._ceo_submit_request(), now=hosts.NOW)
        assert [p.read_bytes() for p in protected] == before
        assert marker.exists()
    finally:
        if recovered._transaction_owner_fd is not None: recovered._release_transaction_owner()


def test_strict_v2_full_arm_submission_and_lost_response_use_one_durable_root(monkeypatch, tmp_path):
    import asyncio
    from control_plane.executive_runtime import Runtime
    from control_plane.executive_service import ExecutiveControlService
    from tests import test_executive_ceo_ingress_admission_hook as ingress
    from tests import test_executive_service as service_tests
    host, marker, _, _ = production_pair(monkeypatch, tmp_path)
    control.execute_ceo_submit_arm(host, hosts._ceo_submit_request(), now=hosts.NOW)
    post = host.load_ceo_submit_configs(hosts.SHA)
    service = ExecutiveControlService(
        service_tests._config(tmp_path, ceo_submit_armed=True, coo_autonomy_armed=True,
                              coo_operator_harness_armed=True),
        autonomy_guard=lambda: None,
        ceo_submit_admission_guard=lambda: control.require_ceo_submit_runtime_admission(
            post.control, own_config_sha256=post.control_sha256),
    )
    runtime = Runtime.at(tmp_path / "strict-runtime")
    try:
        first = asyncio.run(ingress._strict_v2_submission(
            runtime, tmp_path, guard=lambda _envelope: service._require_ceo_submit_admission()))
        assert first["duplicate"] is False
        assert runtime.jobs.get_job(first["job_id"]).orchestration_role == "aggregation"
        # Close/reopen the durable store and revoke fresh admission. Reconciliation
        # of the lost response still returns the original root with zero dispatch.
        # Runtime uses per-operation connections, all closed on return.
        runtime = Runtime.at(tmp_path / "strict-runtime")
        marker.mkdir(mode=0o700)
        replay = asyncio.run(ingress.ceo_ingress.handle_frame(
            ingress._strict_v2_frame(), runtime=runtime,
            grounding_provider=ingress.pr_a._FakeGrounding(error=AssertionError("no new grounding on replay")),
            workspace_root=ingress._workspace_root(tmp_path), service_state="READY",
            ceo_ingress_armed=True, strict_v2_admission=True,
            dialogue_source_provider=None,
            admission_guard=lambda _envelope: service._require_ceo_submit_admission()))
        assert replay["duplicate"] is True and replay["job_id"] == first["job_id"]
        assert replay["dispatched"] is False
        assert len(runtime.jobs.list_jobs()) == 1
        fresh = Runtime.at(tmp_path / "fresh-runtime")
        try:
            with pytest.raises(ingress.ceo_ingress.CeoIngressError) as refused:
                asyncio.run(ingress._strict_v2_submission(
                    fresh, tmp_path, guard=lambda _envelope: service._require_ceo_submit_admission()))
            assert refused.value.code == "backend_refused"
            assert fresh.jobs.list_jobs() == []
        finally:
            assert not fresh.store._bound_connections
    finally:
        assert not runtime.store._bound_connections


def test_production_public_admission_without_sealed_guard_refuses(tmp_path, monkeypatch):
    from control_plane.executive_service import ExecutiveControlService, _CeoSubmitUnarmedError
    from tests import test_executive_service as service_tests
    service = ExecutiveControlService(service_tests._config(tmp_path, ceo_submit_armed=True))
    monkeypatch.setattr(service, "_is_production_control_socket", lambda: True)
    with pytest.raises(_CeoSubmitUnarmedError):
        service._require_ceo_submit_admission()

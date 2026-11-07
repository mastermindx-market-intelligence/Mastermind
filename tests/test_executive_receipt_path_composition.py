"""The production loader and sealed receipt must agree on path representation."""
import asyncio
import copy
import dataclasses
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.executive_os import autonomy_control as control
from scripts import executive_os_phase1c as cli
from tests.test_ceo_submit_armed_composition import _raw, _write
from tests.test_ceo_submit_autonomy_coexistence import full_receipt
from tests.test_executive_admission_diagnostic import _observe
from tests.test_executive_autonomy_control import FakeCeoSubmitHost, NOW, SHA


@pytest.fixture(params=[False, True], ids=["literal-paths", "symlink-aliases"])
def alias_paths(request):
    return request.param


@pytest.fixture(params=[False, True], ids=["ceo-only", "full-autonomy"])
def composition(tmp_path, monkeypatch, request, alias_paths):
    host = FakeCeoSubmitHost(safe_coexistence=request.param)
    host.control_config.pop("preserved")
    host.control_config = _raw(tmp_path, **host.control_config)
    host.control_config.update(
        ceo_ingress_peer_uid=os.geteuid() + 3,
        ceo_ingress_app_peer_uid=os.geteuid() + 4,
        coo_autonomy_armed=request.param,
        coo_operator_harness_armed=request.param,
    )
    host.worker_config["operator_harness_armed"] = request.param
    if alias_paths:
        physical = tmp_path / "physical"
        physical.mkdir()
        alias = tmp_path / "alias"
        alias.symlink_to(physical, target_is_directory=True)
        host.control_config.update(ceo_ingress_socket_path=str(alias / "ceo.sock"),
                                   ceo_ingress_app_macro_root=str(alias / "macro"))
    pair = full_receipt(host.load_ceo_submit_configs(SHA))
    # Fake only the transaction's receipt storage, using the real rebinder.
    def rebind(transaction):
        nonlocal pair
        pair = control.rebind_coexistence_receipt(transaction, pair)
    host.rebind_full_autonomy_receipt = rebind
    control.execute_ceo_submit_arm(host, control.CeoSubmitRequest(expected_sha=SHA), now=NOW)
    path = _write(tmp_path, host.control_config)
    path.write_bytes(control.encode_config(host.control_config))
    loaded = cli.load_control_config(path)
    config_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = control.ReceiptMetadata(uid=0, gid=0, mode=0o444, nlink=1,
                                      is_regular=True, is_symlink=False, has_acl=False)
    now = datetime.now(UTC).replace(microsecond=0)
    pair.update(observed_at=control._iso(now), readiness_observed_at=control._iso(now),
                credential_expires_at=control._iso(now + timedelta(hours=2)),
                readiness_expires_at=control._iso(now + timedelta(hours=1)))
    files = {control.CEO_SUBMIT_RECEIPT: (host.receipt, metadata),
             control.AUTONOMY_RECEIPT: (pair, metadata)}
    reads = []
    def read_receipt(receipt_path):
        reads.append(receipt_path)
        # The worker's private config is never an admission read target.
        assert receipt_path in files
        return files[receipt_path]
    monkeypatch.setattr(control, "load_receipt_file", read_receipt)
    monkeypatch.setattr(control, "AUTONOMY_TRANSACTION", tmp_path / "absent-transaction")
    return path, loaded, config_sha, files, reads


def test_real_loaded_config_admits_same_receipt_as_json_without_mutation(composition, alias_paths):
    path, loaded, config_sha, files, reads = composition
    raw = json.loads(path.read_bytes())
    assert isinstance(loaded["ceo_ingress_socket_path"], Path)
    assert isinstance(loaded["ceo_ingress_app_macro_root"], Path)
    if alias_paths:
        assert os.fspath(loaded["ceo_ingress_socket_path"]) != raw["ceo_ingress_socket_path"]
    before = copy.deepcopy(loaded)
    receipt_bytes = json.dumps(files[control.CEO_SUBMIT_RECEIPT][0], sort_keys=True)
    control.require_ceo_submit_runtime_admission(raw, own_config_sha256=config_sha)
    raw_reads = list(reads)
    reads.clear()
    cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": config_sha})()
    assert loaded == before
    assert reads == raw_reads
    assert json.dumps(files[control.CEO_SUBMIT_RECEIPT][0], sort_keys=True) == receipt_bytes


def test_real_loaded_callback_and_private_observation_admit_without_runtime(
    composition, tmp_path, short_socket_root, monkeypatch,
):
    path, loaded, config_sha, _, _ = composition
    guard = cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": config_sha})
    result = asyncio.run(_observe(tmp_path, short_socket_root, monkeypatch, guard=guard))
    assert result["result"] == {
        "schema": "mastermind.executive_ceo_admission_observation/v1",
        "scope": "CURRENT_ONLY", "phase": "admitted",
    }
    # Submission uses this same callback; no submission or Runtime is constructed.
    assert guard() is None


@pytest.mark.parametrize("field", ["ceo_ingress_socket_path", "ceo_ingress_app_macro_root"])
def test_loaded_path_drift_still_refuses(composition, field):
    path, loaded, config_sha, _, _ = composition
    loaded[field] = loaded[field] / "different"
    with pytest.raises(cli.CeoAdmissionPhaseRefusal):
        cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": config_sha})()


@pytest.mark.parametrize("field", ["ceo_ingress_socket_path", "ceo_ingress_app_macro_root"])
def test_equivalent_receipt_path_spelling_does_not_gain_authority(composition, field):
    path, loaded, config_sha, files, _ = composition
    receipt = files[control.CEO_SUBMIT_RECEIPT][0]
    original = receipt["projection"][field]
    changed = original + "/."
    assert Path(original).resolve() == Path(changed).resolve()
    receipt["projection"][field] = changed
    receipt["projection_digest"] = control.ceo_submit_projection_digest(receipt["projection"])
    with pytest.raises(cli.CeoAdmissionPhaseRefusal) as caught:
        cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": config_sha})()
    assert caught.value.phase == "receipt_refused"


@pytest.mark.parametrize("defect", ["metadata", "digest", "unarmed", "transaction"])
def test_loaded_guard_preserves_existing_authority_refusals(composition, defect):
    path, loaded, config_sha, files, _ = composition
    receipt, metadata = files[control.CEO_SUBMIT_RECEIPT]
    if defect == "metadata":
        files[control.CEO_SUBMIT_RECEIPT] = receipt, dataclasses.replace(metadata, mode=0o644)
    elif defect == "digest":
        receipt["projection_digest"] = "f" * 64
    elif defect == "unarmed":
        loaded["ceo_submit_armed"] = False
    elif defect == "transaction":
        control.AUTONOMY_TRANSACTION.mkdir()
    with pytest.raises(cli.CeoAdmissionPhaseRefusal) as caught:
        cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": config_sha})()
    assert caught.value.phase == "receipt_refused"


def test_loaded_callback_preserves_attestation_digest_contract(composition):
    path, loaded, _, _, _ = composition
    with pytest.raises(cli.CeoAdmissionPhaseRefusal) as caught:
        cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": "f" * 64})()
    assert caught.value.phase == "config_binding_refused"


def test_production_callback_still_rejects_changed_config_file(composition):
    path, loaded, config_sha, _, _ = composition
    guard = cli._ceo_admission_guard(loaded, path, lambda: {"config_sha256": config_sha})
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(cli.CeoAdmissionPhaseRefusal) as caught:
        guard()
    assert caught.value.phase == "config_binding_refused"

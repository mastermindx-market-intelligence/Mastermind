"""A pre-proof supersession preserves an interrupted post-canary, no-Job prefix.

The new ``supersede_preproof_v1`` class is fitted to the installed release
``bcf4a2f72538682f2fbe4902f6417e59cd038678`` shape: started, activated the live
secret-canary receipt with its own envelope, then failed at ``status.sh`` before
any proof Job. The walk re-asserts every other strict check that already
protects ``supersede_prejob_v1`` and ``supersede_unstarted_v1`` and binds the
new envelope-based canary rule end-to-end. The single schema admission (a) lets a
``supersede_prejob_v1`` descriptor point at another ``supersede_prejob_v1``
selected release; ``U3`` proves the schema gate alone admits the selection and
the full link check still requires the same sealed bundle and run marker.
"""
import argparse
import ast
import copy
import dataclasses
import grp
import hashlib
import json
import os
import pwd
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_supersede_unstarted import (
    A, S, N, _fixture as unstarted_fixture, _rewrite,
)
from tests.test_executive_acceptance_supersede_prejob import (
    WORKER_ID, attended_membership, fixture as prejob_fixture, group_receipt, receipt_prefix,
)
# _terminal_fixture is imported lazily inside the helpers that need it
# (the existing test modules in this directory import it the same way).

PROBE_PID = 1327


# --- receipt producer shapes ----------------------------------------------

def launchd_before_receipt():
    return {"sha256": "1" * 64, "labels_excluded": 2}


def assignment_root_receipt():
    return {"passed": True, "workspace_root_listing": "DENIED", "run_root_listing": "DENIED"}


def control_status_response():
    return {"ok": True, "result": {"service_state": "AWAITING_CANARY",
                                    "control_pid": PROBE_PID}}


def failure_control_status_response():
    return {"ok": False, "result": {"service_state": "QUARANTINED"}}


def broker_status():
    return {"broker_pid": PROBE_PID, "worker_uid": 470, "worker_gid": 460,
            "supplementary_gids": [], "operator_harness_armed": False,
            "active_operator_attempt_id": None, "active_operator_generation_id": None,
            "startup_sweep": {"passed": True}, "quarantined_reason": None}


def launchd_principals():
    return {
        "control": {"pid": PROBE_PID, "uid": 460},
        "worker": {"pid": PROBE_PID + 1, "uid": 470, "gid": 460,
                   "supplementary_gids": []},
    }


def control_environment_probe_receipt(pid=PROBE_PID):
    return {
        "schema_version": "mastermind.executive_control_env_probe/v1",
        "passed": True,
        "control_process_identity": {
            "pid": pid, "pgid": pid, "session_id": pid,
            "effective_uid": 460, "effective_gid": 460,
            "real_uid": 460, "real_gid": 460,
        },
        "worker_principal": {"real_uid": 470, "effective_uid": 470,
                              "real_gid": 460, "effective_gid": 460},
        "config_sha256": "e" * 64,
        "release_manifest_sha256": "f" * 64,
        "sentinel_value_sha256": "9" * 64,
        "process_identity_sha256": "c" * 64,
        "checks": {},
    }


def envelope():
    return {
        "schema_version": "mastermind.executive_secret_canary_envelope/v1",
        "secret_canary": {"passed": True, "generation": "fixture",
                          "control_environment_probe_sha256": "d" * 64},
        "control_environment_probe": {"pid": PROBE_PID},
        "control_environment_probe_sha256": "d" * 64,
    }


# --- fixture --------------------------------------------------------------

def write_full_preproof_root(runtime, selected, monkeypatch, *,
                              include_optional=False):
    """Stamp the pre-Job two-receipt prefix plus the seven additional pre-proof
    receipts (and optionally the bounded failure artifact) under S's acceptance
    directory and re-write the run marker for the selected release."""
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    root = runtime / "control/acceptance" / selected["successor_sha"]
    root.parent.chmod(0o700)
    root.mkdir(mode=0o700)
    docs = {
        "assignment-root-nonlistability.json": assignment_root_receipt(),
        "awaiting-canary-status.json": control_status_response(),
        "failure-control-status.json": failure_control_status_response(),
        "launchd-principals.json": launchd_principals(),
        "nonexecutive-launchd-before.json": launchd_before_receipt(),
        "protected-group-membership.json": group_receipt(),
        "secret-canary-envelope.json": envelope(),
        "worker-broker-startup.json": broker_status(),
        f"control-environment-probe-{PROBE_PID}.json": control_environment_probe_receipt(),
    }
    for name, doc in docs.items():
        (root / name).write_text(json.dumps(doc))
        (root / name).chmod(0o400)
    if include_optional:
        (root / "host-service-status-failure.txt").write_bytes(b"status.sh failed: exit 1\n")
        (root / "host-service-status-failure.txt").chmod(0o400)
    m.write_sealed(m.bundle_path(selected["successor_sha"]) / "run-started.json", {
        "schema_version": selected["schema_version"],
        "descriptor_sha256": m.digest(selected),
    }, public=True)
    return root


def fixture(tmp_path, monkeypatch):
    """A preproof candidate pointing at the bcf4a2f7-style selected SU1 release.

    Returns ``(candidate, selected, before, artifacts, canary, bundle, root, envelope_value)``.
    ``envelope_value`` is the parsed envelope written to live receipt, the
    acceptance dir, and the candidate's ``prior_canary_sha256`` digest."""
    d, selected, before, artifacts, canary, bundle, runtime = unstarted_fixture(tmp_path, monkeypatch)
    root = write_full_preproof_root(runtime, selected, monkeypatch)
    envelope_value = envelope()
    evidence_digest, read_envelope = m.preproof_evidence(S)
    assert read_envelope == envelope_value
    del d["superseded_unstarted_sha"]
    d.update(
        schema_version=m.SCHEMA_PREPROOF,
        interrupted_preproof_sha=S,
        preproof_evidence_sha256=evidence_digest,
        prior_canary_sha256=m.digest(envelope_value),
    )
    return d, selected, before, artifacts, canary, bundle, root, envelope_value


# --- (A) acceptance class is admitted and re-asserted on every strict path ----

def test_a1_strict_walk_admits_the_preproof_candidate(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    paths = [*bundle.iterdir(), *root.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=envelope_value)
    assert {str(p): p.read_bytes() for p in paths} == original
    # The descriptor's prior_canary_sha256 binds the live receipt (= envelope).
    assert d["prior_canary_sha256"] == m.digest(envelope_value)


def test_a2_prepare_candidate_validation_passes_and_binds_live_receipt(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = (
        fixture(tmp_path, monkeypatch))
    # Driving prepare requires the full host gate; spy on validate_superseded_binding
    # the same way the existing supersede-unstarted tests do, and prove the
    # candidate descriptor the prepare path would publish has prior_canary_sha256
    # equal to digest(live receipt).
    seen = []
    real = m.validate_superseded_binding

    def spy(descriptor, **kwargs):
        seen.append((descriptor["schema_version"], descriptor["prior_canary_sha256"], kwargs.get("prior_canary")))
        return real(descriptor, **kwargs)

    monkeypatch.setattr(m, "validate_superseded_binding", spy)
    candidate = dict(d, prior_canary_sha256=m.digest(envelope_value))
    m.validate_superseded_binding(candidate, before=before, artifacts=artifacts,
                                  prior_canary=envelope_value)
    assert seen == [(m.SCHEMA_PREPROOF, m.digest(envelope_value), envelope_value)]
    assert candidate["prior_canary_sha256"] == m.digest(envelope_value)
    new = m.bundle_path(N)
    new.mkdir()
    m.write_sealed(new / "descriptor.json", candidate, public=True)
    assert m.descriptor_for(N) == candidate


def test_a3_historical_walk_admits_without_prior_canary(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    m.validate_superseded_binding(d, historical=True)


def test_a4_maintenance_level_strict_recheck_passes(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    runtime = root.parent.parent.parent
    new = m.bundle_path(N)
    new.mkdir()
    for name in ("baseline.json", "inventory.json", "prestate.sqlite3"):
        (new / name).write_bytes((bundle / name).read_bytes())
        (new / name).chmod(0o400)
    # Prepare's prior-secret-canary.json gets the live receipt; for a PREPROOF
    # candidate the live receipt equals the envelope. Write it accordingly so
    # Maintenance.__init__'s own sealed-binding digest holds.
    m.write_sealed(new / "prior-secret-canary.json", envelope_value, public=False)
    m.write_sealed(new / "descriptor.json", d, public=True)
    monkeypatch.setattr(m, "validate_prior_carry_binding", lambda descriptor: None)
    monkeypatch.setattr(m, "require_stopped", lambda: None)
    monkeypatch.setattr(m, "verify_inventory", lambda value: None)
    database = runtime / "data/control_plane/executive.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_bytes((bundle / "prestate.sqlite3").read_bytes())
    # The live receipt must equal the envelope at strict re-check time.
    live_canary = tmp_path / "live-canary.json"
    live_canary.write_text(json.dumps(envelope_value))
    from control_plane.executive_runtime import Runtime
    monkeypatch.setattr(Runtime, "at", lambda *a, **kw: SimpleNamespace(
        jobs=SimpleNamespace(get_job=lambda job: SimpleNamespace(job_id=job))))
    monkeypatch.setattr(m, "terminal_carry_fields",
                          lambda *a, **kw: (None, {
                              key: d[key] for key in m._DESCRIPTOR_V2_KEYS - m._DESCRIPTOR_KEYS}))
    config = dict(runtime_root=str(runtime), secret_canary_receipt_path=str(live_canary),
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    owner = m.Maintenance(N, m.digest(d), config)
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, "old", N, "worker", "proof") is False
    assert m.sealed_json(new / "run-started.json") == {
        "schema_version": m.SCHEMA_PREPROOF, "descriptor_sha256": m.digest(d)}


def test_a5_optional_failure_artifact_present_changes_evidence_digest(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    bare_digest = m.preproof_evidence(S)[0]
    (root / "host-service-status-failure.txt").write_bytes(b"status.sh failed: exit 1\n")
    (root / "host-service-status-failure.txt").chmod(0o400)
    with_digest = m.preproof_evidence(S)[0]
    assert bare_digest != with_digest
    # A candidate bound to the bare digest must be re-validated when the
    # artifact appears: its preproof_evidence_sha256 no longer matches.
    d_drift = dict(d, preproof_evidence_sha256=bare_digest)
    with pytest.raises(m.MaintenanceError, match="interrupted pre-proof evidence drifted"):
        m.validate_superseded_binding(d_drift, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_a6_chain_of_27_inner_links_plus_one_preproof_link_passes(tmp_path, monkeypatch):
    """The 28-deep chain (27 inner SUPERSEDE + 1 PREPROOF at the tail) walks."""
    base_d, leaf, before, artifacts, canary, runtime = _inner_chain(tmp_path, monkeypatch, 27)
    root = write_full_preproof_root(runtime, leaf, monkeypatch)
    evidence_digest, envelope_value = m.preproof_evidence(leaf["successor_sha"])
    preproof = dict(base_d, schema_version=m.SCHEMA_PREPROOF,
                    interrupted_preproof_sha=leaf["successor_sha"],
                    preproof_evidence_sha256=evidence_digest,
                    prior_canary_sha256=m.digest(envelope_value))
    m.validate_superseded_binding(preproof, before=before, artifacts=artifacts,
                                  prior_canary=envelope_value)


def _inner_chain(tmp_path, monkeypatch, nodes):
    """Build an internal supersede_unstarted_v1 chain of ``nodes`` inner links."""
    candidate, leaf, before, artifacts, canary, leaf_bundle, runtime = unstarted_fixture(tmp_path, monkeypatch)
    selected = [leaf]
    for index in range(nodes - 1):
        previous = selected[-1]
        sha = f"{index + 2:040x}"
        bundle = m.bundle_path(sha)
        shutil.copytree(leaf_bundle, bundle)
        descriptor = dict(previous, schema_version=m.SCHEMA_SUPERSEDE, successor_sha=sha,
                          superseded_unstarted_sha=previous["successor_sha"],
                          superseded_descriptor_sha256=m.digest(previous))
        _rewrite(bundle / "descriptor.json", descriptor)
        _rewrite(bundle / "preparing.json", {"schema_version": m.SCHEMA_SUPERSEDE})
        selected.append(descriptor)
    candidate.update(superseded_unstarted_sha=selected[-1]["successor_sha"],
                     superseded_descriptor_sha256=m.digest(selected[-1]))
    return candidate, selected[-1], before, artifacts, canary, runtime


# --- (R) refusal surface ----------------------------------------------------

def test_r1_db_drift_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    before["tables"]["schema_migrations"].append({"version": 6})
    with pytest.raises(m.MaintenanceError, match="superseded sealed baseline drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r2_inventory_drift_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    artifacts["changed"] = True
    with pytest.raises(m.MaintenanceError, match="superseded sealed baseline drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r3_extra_unknown_receipt_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / "quarantine-status.json").write_text("{}")
    (root / "quarantine-status.json").chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r4_host_status_txt_present_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / "host-status.txt").write_text("OK")
    (root / "host-status.txt").chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r5_second_probe_file_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / "control-environment-probe-2000.json").write_text(json.dumps(control_environment_probe_receipt(2000)))
    (root / "control-environment-probe-2000.json").chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("missing", [
    "assignment-root-nonlistability.json",
    "awaiting-canary-status.json",
    "failure-control-status.json",
    "launchd-principals.json",
    "nonexecutive-launchd-before.json",
    "protected-group-membership.json",
    "secret-canary-envelope.json",
    "worker-broker-startup.json",
])
def test_r6_missing_core_receipt_refuses(tmp_path, monkeypatch, missing):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / missing).unlink()
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r7_zero_probe_files_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / f"control-environment-probe-{PROBE_PID}.json").unlink()
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("name", [
    "interrupted-job-lost.json", "interrupted-dispatch.json", "interrupted-reconciliation-evidence.json",
    "health-before-success.json", "registered-worker.json",
    "backup-prepare.json", "leakage-failures.json",
])
def test_r8_post_job_receipt_refuses(tmp_path, monkeypatch, name):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / name).write_text("{}")
    (root / name).chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("fault", [
    "mode-440", "owner", "nlink-2", "symlink",
])
def test_r9_receipt_mode_owner_link_refuses(tmp_path, monkeypatch, fault):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    receipt = root / "launchd-principals.json"
    if fault == "mode-440":
        receipt.chmod(0o440)
    elif fault == "owner":
        monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid() + 1))
    elif fault == "nlink-2":
        # hardlink the receipt to create a second link
        os.link(receipt, tmp_path / "extra-link.json")
    elif fault == "symlink":
        target = tmp_path / "target.json"
        receipt.rename(target)
        receipt.symlink_to(target)
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("name", [
    "assignment-root-nonlistability.json",
    "launchd-principals.json",
    "secret-canary-envelope.json",
])
@pytest.mark.parametrize("fault", ["extra-key", "missing-key"])
def test_r10_key_set_drift_refuses(tmp_path, monkeypatch, name, fault):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    receipt = root / name
    receipt.chmod(0o600)
    value = json.loads(receipt.read_text())
    if fault == "extra-key":
        value["drift"] = True
    else:
        keys = list(value)
        if keys:
            del value[keys[0]]
    receipt.write_text(json.dumps(value))
    receipt.chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance receipt schema drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("fault", ["oversize", "wrong-mode", "symlink"])
def test_r11_failure_artifact_safety_refuses(tmp_path, monkeypatch, fault):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / "host-service-status-failure.txt").write_bytes(b"ok")
    (root / "host-service-status-failure.txt").chmod(0o400)
    if fault == "oversize":
        (root / "host-service-status-failure.txt").chmod(0o600)
        (root / "host-service-status-failure.txt").write_bytes(b"x" * (256 * 1024 + 1))
        (root / "host-service-status-failure.txt").chmod(0o400)
    elif fault == "wrong-mode":
        (root / "host-service-status-failure.txt").chmod(0o600)
    elif fault == "symlink":
        target = tmp_path / "src.bin"
        target.write_bytes(b"x")
        (root / "host-service-status-failure.txt").unlink()
        (root / "host-service-status-failure.txt").symlink_to(target)
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r12_final_host_status_failure_txt_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    (root / "final-host-status-failure.txt").write_text("done")
    (root / "final-host-status-failure.txt").chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance is not a pre-proof prefix"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r13_live_receipt_differs_from_envelope_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    with pytest.raises(m.MaintenanceError, match="interrupted pre-proof canary binding drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary={"passed": True, "different": "live"})


def test_r14_descriptor_prior_canary_sha256_differs_from_envelope_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    d["prior_canary_sha256"] = "0" * 64
    with pytest.raises(m.MaintenanceError, match="interrupted pre-proof canary binding drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r15_inner_link_sealed_canary_differs_from_selected_refuses(tmp_path, monkeypatch):
    """A nested inner link whose sealed canary differs from the PREPROOF's
    selected bundle sealed canary is refused at the deeper iteration."""
    base_d, leaf, before, artifacts, canary, runtime = _inner_chain(tmp_path, monkeypatch, 3)
    root = write_full_preproof_root(runtime, leaf, monkeypatch)
    evidence_digest, envelope_value = m.preproof_evidence(leaf["successor_sha"])
    preproof = dict(base_d, schema_version=m.SCHEMA_PREPROOF,
                    interrupted_preproof_sha=leaf["successor_sha"],
                    preproof_evidence_sha256=evidence_digest,
                    prior_canary_sha256=m.digest(envelope_value))
    inner_sha = leaf["superseded_unstarted_sha"]
    inner_bundle = m.bundle_path(inner_sha)
    target = inner_bundle / "prior-secret-canary.json"
    target.chmod(0o600)
    inner_canary = json.loads(target.read_text())
    inner_canary["drift"] = True
    target.write_text(json.dumps(inner_canary))
    target.chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="superseded sealed baseline drifted"):
        m.validate_superseded_binding(preproof, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("fault", ["schema", "digest"])
def test_r16_run_started_drift_refuses(tmp_path, monkeypatch, fault):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    marker = {"schema_version": m.SCHEMA_PREPROOF if fault == "schema" else m.SCHEMA_V2,
              "descriptor_sha256": m.digest(selected) if fault == "schema" else "0" * 64}
    _rewrite(bundle / "run-started.json", marker)
    with pytest.raises(m.MaintenanceError,
                       match="interrupted pre-proof evidence drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r17_depth_overrun_refuses(tmp_path, monkeypatch):
    """65-deep chain (64 inner SUPERSEDE + 1 PREPROOF) refuses with too-deep."""
    base_d, leaf, before, artifacts, canary, runtime = _inner_chain(tmp_path, monkeypatch, 64)
    root = write_full_preproof_root(runtime, leaf, monkeypatch)
    evidence_digest, envelope_value = m.preproof_evidence(leaf["successor_sha"])
    preproof = dict(base_d, schema_version=m.SCHEMA_PREPROOF,
                    interrupted_preproof_sha=leaf["successor_sha"],
                    preproof_evidence_sha256=evidence_digest,
                    prior_canary_sha256=m.digest(envelope_value))
    with pytest.raises(m.MaintenanceError, match="too deep"):
        m.validate_superseded_binding(preproof, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r18_cycle_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    # Create a self-cycle: top descriptor points at its own successor_sha.
    cyclic = dict(d, interrupted_preproof_sha=N)
    N_bundle = m.bundle_path(N)
    N_bundle.mkdir()
    m.write_sealed(N_bundle / "descriptor.json", cyclic, public=True)
    with pytest.raises(m.MaintenanceError, match="cyclic"):
        m.validate_superseded_binding(cyclic, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r19_evidence_digest_mismatch_refuses(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    d["preproof_evidence_sha256"] = "0" * 64
    with pytest.raises(m.MaintenanceError, match="interrupted pre-proof evidence drifted"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


@pytest.mark.parametrize("extra", [
    "carry-forward.json", "extra-name.json",
])
def test_r20_selected_bundle_contains_extra_entry_refuses(tmp_path, monkeypatch, extra):
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    m.write_sealed(bundle / extra, {})
    with pytest.raises(m.MaintenanceError,
                       match="superseded bundle contains acceptance or partial state"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r21_schema_v4_refuses(tmp_path, monkeypatch):
    """The sealed prestate.sqlite3 schema_migrations row is bumped to v4 in
    lockstep with the sealed baseline.json; the descriptor is re-bound to
    those bytes; the schema-v5 guard in ``_validate_superseded_link`` is the
    binding refusal."""
    d, selected, before, artifacts, canary, bundle, root, envelope_value = fixture(tmp_path, monkeypatch)
    # Step 1: rewrite the prestate.sqlite3 schema_migrations row to v4.
    (bundle / "prestate.sqlite3").chmod(0o600)
    with sqlite3.connect(bundle / "prestate.sqlite3") as conn:
        conn.execute("UPDATE schema_migrations SET version=4")
    (bundle / "prestate.sqlite3").chmod(0o400)
    # Step 2: rewrite the sealed baseline.json to v4 so the snapshot/baseline
    # pair stay equal at the SQS seam (sealed_backup_snapshot equality check).
    baseline = m.sealed_json(bundle / "baseline.json")
    baseline["tables"]["schema_migrations"][0]["version"] = 4
    _rewrite(bundle / "baseline.json", baseline)
    # Step 3: keep the live before in lockstep so (before != baseline) at the
    # link check does not fire before the schema-v5 guard.
    before["tables"]["schema_migrations"][0]["version"] = 4
    # Step 4: re-bind the selected descriptor and its run marker to the v4 bytes.
    selected["baseline_sha256"] = m.digest(baseline)
    selected["backup_sha256"] = m._file_digest(bundle / "prestate.sqlite3")
    _rewrite(bundle / "descriptor.json", selected)
    _rewrite(bundle / "run-started.json", {
        "schema_version": selected["schema_version"],
        "descriptor_sha256": m.digest(selected)})
    # Step 5: bring the candidate descriptor into the v4 world and validate.
    d["baseline_sha256"] = m.digest(baseline)
    d["superseded_descriptor_sha256"] = m.digest(selected)
    with pytest.raises(m.MaintenanceError, match="supersession requires unchanged schema v5"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts,
                                      prior_canary=envelope_value)


def test_r22_prepare_two_selection_flags_refuses(tmp_path, monkeypatch):
    system = tmp_path / "system"
    (system / "config").mkdir(parents=True)
    (system / "config" / "control.json").write_text(json.dumps(dict(proof_base_sha=S,
        ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)))
    (system / "config" / "worker-codex.json").write_text('{"operator_harness_armed":false}')
    monkeypatch.setattr(m, "SYSTEM_ROOT", system)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(m, "require_stopped", lambda: None)
    args = argparse.Namespace(predecessor_sha=A, successor_sha=N, root_job_id="root",
                              recovery_job_id=None, recovery_attempt_id=None,
                              carry_terminal_dispatch=True,
                              supersede_unstarted_sha=S,
                              supersede_prejob_sha=S,
                              supersede_preproof_sha=None,
                              superseded_descriptor_sha256=m.digest({"schema_version": m.SCHEMA_SUPERSEDE}))
    with pytest.raises(m.MaintenanceError, match="select one supersession mode"):
        m.prepare(args)


# --- (U) unchanged-class regressions and the one ruled admission (a) ----------

def test_u1_supersede_unstarted_selecting_prejob_or_preproof_refused(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, runtime = unstarted_fixture(tmp_path, monkeypatch)
    prejob_sha = "0" * 40
    preproof_sha = "1" * 40
    prejob_d = dict(selected, schema_version=m.SCHEMA_PREJOB, successor_sha=prejob_sha,
                    interrupted_prejob_sha=N, superseded_descriptor_sha256=m.digest(selected),
                    prejob_evidence_sha256="f" * 64)
    preproof_d = dict(selected, schema_version=m.SCHEMA_PREPROOF, successor_sha=preproof_sha,
                      interrupted_preproof_sha=N, superseded_descriptor_sha256=m.digest(selected),
                      preproof_evidence_sha256="f" * 64)
    for patched in (prejob_d, preproof_d):
        bundle = m.bundle_path(patched["successor_sha"])
        bundle.mkdir()
        m.write_sealed(bundle / "descriptor.json", patched, public=True)
        candidate = dict(d, superseded_unstarted_sha=patched["successor_sha"],
                         superseded_descriptor_sha256=m.digest(patched))
        with pytest.raises(m.MaintenanceError,
                           match="superseded descriptor or accepted ancestor mismatch"):
            m.validate_superseded_binding(candidate)


def test_u2_prejob_selecting_preproof_refused(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = prejob_fixture(tmp_path, monkeypatch)
    preproof_sha = "2" * 40
    preproof_d = dict(selected, schema_version=m.SCHEMA_PREPROOF, successor_sha=preproof_sha,
                      interrupted_preproof_sha=N, superseded_descriptor_sha256=m.digest(selected),
                      preproof_evidence_sha256="f" * 64)
    bundle = m.bundle_path(preproof_sha)
    bundle.mkdir()
    m.write_sealed(bundle / "descriptor.json", preproof_d, public=True)
    candidate = dict(d, interrupted_prejob_sha=preproof_sha,
                     superseded_descriptor_sha256=m.digest(preproof_d))
    with pytest.raises(m.MaintenanceError):
        m.validate_superseded_binding(candidate, before=before, artifacts=artifacts,
                                      prior_canary=canary)


def test_u3_prejob_selecting_prejob_release_admission_a_passes(tmp_path, monkeypatch):
    """Admission (a): a supersede_prejob_v1 descriptor may select a
    supersede_prejob_v1 release. Both bundles hold exactly the two pre-Job
    receipts and a run marker; live receipt unchanged across the pair."""
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    base_d, leaf, before, artifacts, canary, leaf_bundle, runtime = unstarted_fixture(tmp_path, monkeypatch)
    # Stage the leaf's acceptance dir with the pre-Job prefix (only two receipts).
    leaf_root = runtime / "control/acceptance" / S
    leaf_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (leaf_root / "nonexecutive-launchd-before.json").write_text(json.dumps(launchd_before_receipt()))
    (leaf_root / "nonexecutive-launchd-before.json").chmod(0o400)
    (leaf_root / "protected-group-membership.json").write_text(json.dumps(group_receipt()))
    (leaf_root / "protected-group-membership.json").chmod(0o400)
    m.write_sealed(m.bundle_path(S) / "run-started.json", {
        "schema_version": m.SCHEMA_V2, "descriptor_sha256": m.digest(leaf)}, public=True)
    # Build an inner PREJOB release pointing at the leaf (selected link).
    # Use a distinct sha value to keep predecessor_sha / successor_sha well-defined.
    inner_sha = "1" * 40
    inner_bundle = m.bundle_path(inner_sha)
    shutil.copytree(m.bundle_path(S), inner_bundle)
    inner_prejob = dict(leaf, schema_version=m.SCHEMA_PREJOB, successor_sha=inner_sha,
                        interrupted_prejob_sha=S,
                        superseded_descriptor_sha256=m.digest(leaf),
                        prejob_evidence_sha256=m.prejob_evidence(S))
    _rewrite(inner_bundle / "descriptor.json", inner_prejob)
    _rewrite(inner_bundle / "preparing.json", {"schema_version": m.SCHEMA_PREJOB})
    # shutil.copytree copied S's run-started; chmod 0o600 and overwrite it.
    _rewrite(inner_bundle / "run-started.json", {
        "schema_version": m.SCHEMA_PREJOB, "descriptor_sha256": m.digest(inner_prejob)})
    inner_root = runtime / "control/acceptance" / inner_sha
    inner_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (inner_root / "nonexecutive-launchd-before.json").write_text(json.dumps(launchd_before_receipt()))
    (inner_root / "nonexecutive-launchd-before.json").chmod(0o400)
    (inner_root / "protected-group-membership.json").write_text(json.dumps(group_receipt()))
    (inner_root / "protected-group-membership.json").chmod(0o400)
    # Top PREJOB selecting the inner PREJOB release; admission (a) admits and
    # the link check still requires the sealed bundle to match the candidate.
    top = dict(base_d, schema_version=m.SCHEMA_PREJOB, predecessor_sha=base_d["predecessor_sha"],
               successor_sha=N, interrupted_prejob_sha=inner_sha,
               superseded_descriptor_sha256=m.digest(inner_prejob),
               prejob_evidence_sha256=m.prejob_evidence(inner_sha))
    top.pop("superseded_unstarted_sha", None)
    m.bundle_path(N).mkdir()
    m.write_sealed(m.bundle_path(N) / "descriptor.json", top, public=True)
    m.validate_superseded_binding(top, before=before, artifacts=artifacts, prior_canary=canary)


def test_u4_prejob_refuses_with_third_receipt(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = prejob_fixture(tmp_path, monkeypatch)
    (root / "host-service-status-failure.txt").write_text("status.sh failed")
    (root / "host-service-status-failure.txt").chmod(0o400)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance passed the pre-Job boundary"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


def test_u5_prejob_evidence_source_is_byte_identical_to_base():
    """Pre-job evidence function bytes match base commit exactly."""
    # sha256 of ast.get_source_segment(prejob_evidence) at base 9f83376b3d0d54ad331c2e74dd12cea10e46f5b1;
    # the seat ruling keeps the pre-Job evidence rule byte-identical, so changing it is a reviewed change to this pin.
    _BASE_PREJOB_EVIDENCE_SHA256 = "5986c1e2766d61e9f976cebe38558d7ece45ec7e48911741e0717230a45b5e2c"
    source = Path(m.__file__).read_text()
    tree = ast.parse(source)
    prejob_nodes = [n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "prejob_evidence"]
    assert len(prejob_nodes) == 1, (
        f"expected exactly one prejob_evidence FunctionDef, found {len(prejob_nodes)}"
    )
    segment = ast.get_source_segment(source, prejob_nodes[0])
    assert hashlib.sha256(segment.encode("utf-8")).hexdigest() == _BASE_PREJOB_EVIDENCE_SHA256


def test_u6_existing_test_modules_load_unmodified():
    """Every pre-existing maintenance test module still collects against the new
    descriptor set; the byte-unchanged status of those modules is proven by
    the PR's name-status, not by this test."""
    modules = (
        "tests/test_executive_acceptance_supersede_unstarted.py",
        "tests/test_executive_acceptance_supersede_prejob.py",
        "tests/test_executive_carry_chain_depth.py",
        "tests/test_executive_maintenance_service_absence.py",
        "tests/test_executive_prejob_historical_legacy_group_receipt.py",
        "tests/test_incident_maintenance_config_join.py",
        "tests/test_executive_acceptance_maintenance.py",
        "tests/test_executive_acceptance_maintenance_v2.py",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         *modules],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, combined[-2000:]
    for module in modules:
        assert module in result.stdout, module

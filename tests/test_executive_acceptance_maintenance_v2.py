"""Chained acceptance preserves a failed dispatch without granting it a retry."""
from copy import deepcopy
from types import SimpleNamespace
import dataclasses
import hashlib
import json

import pytest

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_terminal_dispatch_recovery import _failed_planner


def _chain(monkeypatch):
    prior = {
        "schema_version": m.SCHEMA, "predecessor_sha": "a"*40, "successor_sha": "b"*40,
        "root_job_id": "JOB-root", "root_identity_sha256": "1"*64,
        "root_event_id": 1, "root_event_sha256": "2"*64,
    }
    summaries = {sha: ({"success_job_id": "JOB-proof"}, sha.encode()) for sha in ("b"*40, "c"*40)}
    receipts = {}
    descriptors = {"b"*40: prior}
    def carry(sha, descriptor):
        return dict(schema_version=descriptor["schema_version"], passed=True, baseline_preserved=True,
                    descriptor_sha256=m.digest(descriptor),
                    acceptance_summary_sha256=hashlib.sha256(summaries[sha][1]).hexdigest())
    receipts["b"*40] = carry("b"*40, prior)
    current = {
        **prior, "schema_version": m.SCHEMA_V2, "predecessor_sha": "b"*40, "successor_sha": "c"*40,
        "frozen_base_sha": "a"*40, "prior_descriptor_sha256": m.digest(prior),
        "prior_carry_sha256": m.digest(receipts["b"*40]),
        "prior_summary_sha256": hashlib.sha256(summaries["b"*40][1]).hexdigest(),
    }
    descriptors["c"*40] = current
    receipts["c"*40] = carry("c"*40, current)
    monkeypatch.setattr(m, "descriptor_for", lambda sha: descriptors.get(sha))
    monkeypatch.setattr(m, "summary_document", lambda sha: summaries[sha])
    monkeypatch.setattr(m, "sealed_json", lambda path: receipts[path.parent.name])
    return descriptors, receipts, summaries


def test_v2_carry_validates_prior_pass_and_derives_original_base(monkeypatch):
    descriptors, receipts, summaries = _chain(monkeypatch)
    m.validate_carry_receipt("c"*40, hashlib.sha256(summaries["c"*40][1]).hexdigest())
    prior, _summary, material = m.prior_carry_material("c"*40)
    assert prior is descriptors["c"*40]
    assert material["frozen_base_sha"] == "a"*40
    assert material["prior_carry_sha256"] == m.digest(receipts["c"*40])
    maintenance = object.__new__(m.Maintenance)
    maintenance.descriptor = descriptors["c"*40]
    assert maintenance.predecessor_recovery_required is False
    maintenance.descriptor = descriptors["b"*40]
    assert maintenance.predecessor_recovery_required is True


@pytest.mark.parametrize("fault", ["prior-failed", "prior-summary", "prior-descriptor", "chosen-base", "foreign-root", "cycle"])
def test_v2_carry_refuses_broken_chain(monkeypatch, fault):
    descriptors, receipts, summaries = _chain(monkeypatch)
    current = descriptors["c"*40]
    if fault == "prior-failed":
        receipts["b"*40]["passed"] = False
    elif fault == "prior-summary":
        summaries["b"*40] = ({}, b"different")
    elif fault == "prior-descriptor":
        descriptors["b"*40]["root_event_sha256"] = "9"*64
    elif fault == "chosen-base":
        current["frozen_base_sha"] = "d"*40
    elif fault == "foreign-root":
        current["root_job_id"] = "JOB-foreign"
    else:
        current["predecessor_sha"] = "c"*40
    # Seal the changed current document to exercise the prior-chain predicate,
    # rather than merely failing the outer descriptor digest.
    receipts["c"*40]["descriptor_sha256"] = m.digest(current)
    with pytest.raises(m.MaintenanceError):
        m.validate_carry_receipt("c"*40, hashlib.sha256(summaries["c"*40][1]).hexdigest())


def _terminal_fixture(tmp_path, monkeypatch, *, marker=True):
    runtime, root_id, job_id, _command, attempt_id = _failed_planner(tmp_path, marker=marker)
    root = runtime.jobs.get_job(root_id)
    # Unit projection supplies the host binding; the Runtime fixture owns the claim.
    root = dataclasses.replace(root, constraints={**root.constraints, "base_sha": "a"*40})
    before = m.snapshot(runtime.store.path)
    admission = next(e for e in before["tables"]["events"] if e["job_id"] == root_id and e["event_type"] == "JOB_CREATED")
    prior = dict(root_job_id=root_id, root_identity_sha256=m.root_identity(root),
                 root_event_id=admission["event_id"], root_event_sha256=m.digest(admission))
    material = dict(frozen_base_sha=root.constraints["base_sha"], prior_descriptor_sha256="1"*64,
                    prior_carry_sha256="2"*64, prior_summary_sha256="3"*64)
    proof = SimpleNamespace(job_id="JOB-proof", status=SimpleNamespace(value="COMPLETED"),
                            orchestration_role=None, constraints={"base_sha": "b"*40},
                            to_dict=lambda: {"job_id": "JOB-proof", "base_sha": "b"*40})
    original = runtime.jobs.get_job
    monkeypatch.setattr(runtime.jobs, "get_job", lambda job: proof if job == "JOB-proof" else original(job))
    monkeypatch.setattr(m, "prior_carry_material", lambda sha: (prior, {"success_job_id": "JOB-proof"}, material))
    monkeypatch.setattr(m, "terminal_assignment", lambda *args: {"assignment_seal_sha256": "4"*64})
    config = {"worker_id": "worker-1", "quota_class": "default"}
    return runtime, root, before, config, prior, material, proof, job_id, attempt_id


def test_terminal_carry_uses_canonical_read_owner_without_writes(tmp_path, monkeypatch):
    runtime, root, before, config, _prior, _material, proof, job_id, attempt_id = _terminal_fixture(tmp_path, monkeypatch)
    selected, fields = m.terminal_carry_fields(runtime, root, config, before, "b"*40)
    assert selected is proof
    assert fields["terminal_job_id"] == job_id
    assert fields["terminal_attempt_id"] == attempt_id
    assert fields["template_proof_job_id"] == proof.job_id
    assert fields["frozen_base_sha"] == "a"*40
    assert m.snapshot(runtime.store.path) == before


@pytest.mark.parametrize("fault", ["root", "base", "extra-child", "native", "process", "quota", "template", "missing-marker"])
def test_terminal_carry_refuses_drift_before_sealing(tmp_path, monkeypatch, fault):
    runtime, root, before, config, prior, material, proof, job_id, attempt_id = _terminal_fixture(
        tmp_path, monkeypatch, marker=fault != "missing-marker",
    )
    if fault == "root":
        prior["root_identity_sha256"] = "f"*64
    elif fault == "base":
        material["frozen_base_sha"] = "f"*40
    elif fault == "extra-child":
        before["tables"]["jobs"].append({"root_job_id": root.job_id, "job_id": "JOB-extra"})
    elif fault == "native":
        before["tables"]["harness_session_epochs"].append({"attempt_id": attempt_id})
    elif fault == "process":
        attempts = runtime.attempts.list_attempts(job_id)
        monkeypatch.setattr(runtime.attempts, "list_attempts", lambda job: [dataclasses.replace(attempts[0], pid=123)])
    elif fault == "quota":
        before["tables"]["worker_quota_classes"][0]["status"] = "UNKNOWN"
    elif fault == "template":
        proof.constraints["base_sha"] = "f"*40
    with pytest.raises(m.MaintenanceError):
        m.terminal_carry_fields(runtime, root, config, before, "b"*40)


def _preserved_proof_delta():
    template = dict(job_id="JOB-template", objective="proof", department="infrastructure", priority=0,
                    authority_level="A0", attempt_limit=2, requested_authorities_json='["READ"]',
                    allowed_write_paths_json="[]", validation_commands_json="[]",
                    constraints_json=json.dumps({"base_sha": "b"*40}), status="COMPLETED", orchestration_role=None)
    tables = dict(jobs=[template, {"job_id": "JOB-root", "status": "QUEUED"},
                             {"job_id": "JOB-failed", "status": "FAILED"}],
                  attempts=[{"attempt_id": "ATT-failed", "job_id": "JOB-failed", "status": "FAILED"}],
                  events=[{"event_id": 1, "event_type": "COO_DISPATCH_EFFECT_UNKNOWN"}],
                  workers=[{"worker_id": "worker", "version": 1}],
                  worker_quota_classes=[dict(worker_id="worker", quota_class="proof", status="AVAILABLE",
                                             held_attempt_id=None, fence_counter=0, version=1)],
                  harness_session_epochs=[], process_generations=[], untouched=[{"value": "preserve"}])
    before = dict(schema=[], tables=tables)
    after = deepcopy(before)
    for job_id, status, attempt_id, ordinal, fence in [
        ("JOB-new1", "COMPLETED", "ATT-new1", 1, 1),
        ("JOB-new2", "LOST", "ATT-lost", 1, 2),
        ("JOB-new2", "COMPLETED", "ATT-new2", 2, 3),
    ]:
        if ordinal == 1:
            after["tables"]["jobs"].append(dict(template, job_id=job_id,
                constraints_json=json.dumps({"base_sha": "c"*40}),
                attempt_count=1 if job_id == "JOB-new1" else 2,
                current_attempt_id="ATT-new1" if job_id == "JOB-new1" else "ATT-new2"))
        after["tables"]["attempts"].append(dict(attempt_id=attempt_id, job_id=job_id,
            status=status, attempt_number=ordinal, fence_generation=fence, worker_id="worker", quota_class="proof"))
        after["tables"]["events"].append(dict(event_id=10+fence, event_type="JOB_CLAIMED",
            job_id=job_id, attempt_id=attempt_id, worker_id="worker", quota_class="proof",
            payload_json=json.dumps({"fence_generation": fence})))
    after["tables"]["events"].append(dict(event_id=20, event_type="PROOF_CAPACITY_RECOVERED",
        job_id="JOB-new2", attempt_id="ATT-lost", worker_id="worker", quota_class="proof"))
    after["tables"]["worker_quota_classes"][0]["fence_counter"] = 3
    descriptor = dict(schema_version=m.SCHEMA_V2, template_proof_job_id="JOB-template",
                      successor_sha="c"*40, worker_id="worker", quota_class="proof")
    return before, after, descriptor


def test_v2_preservation_allows_only_fresh_proof_recovery(monkeypatch):
    before, after, descriptor = _preserved_proof_delta()
    validated = []
    monkeypatch.setattr(m, "_validate_recovery_event", lambda e, j, a, d: validated.append((j, a)))
    m.verify_preserved(before, after, descriptor, ["JOB-new1", "JOB-new2"])
    assert validated == [("JOB-new2", "ATT-lost")]
    v1 = dict(descriptor, schema_version=m.SCHEMA, recovery_job_id="JOB-template",
              recovery_attempt_id="ATT-prior")
    with pytest.raises(m.MaintenanceError, match="recovery event count"):
        m.verify_preserved(before, after, v1, ["JOB-new1", "JOB-new2"])


@pytest.mark.parametrize("fault", ["root", "attempt", "marker", "unrelated", "old-recovery", "held-quota"])
def test_v2_preservation_refuses_any_historical_change(monkeypatch, fault):
    before, after, descriptor = _preserved_proof_delta()
    monkeypatch.setattr(m, "_validate_recovery_event", lambda *args: None)
    if fault == "root":
        after["tables"]["jobs"][1]["status"] = "COMPLETED"
    elif fault == "attempt":
        after["tables"]["attempts"][0]["status"] = "COMPLETED"
    elif fault == "marker":
        after["tables"]["events"].pop(0)
    elif fault == "unrelated":
        after["tables"]["untouched"][0]["value"] = "changed"
    elif fault == "old-recovery":
        after["tables"]["events"].append(dict(event_id=21, event_type="PROOF_CAPACITY_RECOVERED",
            job_id="JOB-template", attempt_id="ATT-prior", worker_id="worker", quota_class="proof"))
    else:
        after["tables"]["worker_quota_classes"][0]["held_attempt_id"] = "ATT-failed"
    with pytest.raises(m.MaintenanceError):
        m.verify_preserved(before, after, descriptor, ["JOB-new1", "JOB-new2"])


@pytest.mark.parametrize("schema", [m.SCHEMA, m.SCHEMA_V2])
def test_descriptor_versions_keep_closed_independent_shapes(tmp_path, monkeypatch, schema):
    import os
    monkeypatch.setattr(m, "SYSTEM_ROOT", tmp_path)
    monkeypatch.setattr(m, "_TRUSTED_UID", os.getuid())
    monkeypatch.setattr(m, "_sealed_ancestors", lambda path: [])
    keys = m._DESCRIPTOR_KEYS if schema == m.SCHEMA else m._DESCRIPTOR_V2_KEYS
    value = {key: "f"*64 for key in keys}
    for key in keys:
        if key.endswith(("_job_id", "_attempt_id")) or key in {"worker_id", "quota_class"}:
            value[key] = "fixture-" + key
        if key.endswith("_event_id"):
            value[key] = 1
    value.update(schema_version=schema, predecessor_sha="a"*40, successor_sha="b"*40)
    if schema == m.SCHEMA_V2:
        value["frozen_base_sha"] = "c"*40
    path = m.bundle_path("b"*40)/"descriptor.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value))
    path.chmod(0o444)
    assert m.descriptor_for("b"*40) == value
    value["unexpected"] = "not admitted"
    path.chmod(0o600)
    path.write_text(json.dumps(value))
    path.chmod(0o444)
    with pytest.raises(m.MaintenanceError, match="schema"):
        m.descriptor_for("b"*40)


@pytest.mark.parametrize("fault", [None, "worker", "control", "job", "attempt", "sweep", "inode", "mode", "path"])
def test_terminal_assignment_binds_existing_uid_and_filesystem_receipt(tmp_path, monkeypatch, fault):
    import os
    import pwd
    import stat
    from ops.executive_os import autonomy_control as autonomy
    from tests.test_executive_worker_broker import FakeSweeper

    workspace = tmp_path/"workspace"
    run_root = tmp_path/"runs"
    workspace.mkdir(mode=0o700)
    run_root.mkdir(mode=0o700)
    run = run_root/"ATT-one"
    run.mkdir(mode=0o700)
    def identity(path):
        info = path.stat()
        return dict(path=str(path), device=info.st_dev, inode=info.st_ino, uid=info.st_uid,
                    gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns)
    receipt = dict(schema_version="mastermind.executive_assignment_seal/v1", passed=True,
                   control_uid=os.getuid(), job_id="JOB-one", attempt_id="ATT-one",
                   uid_sweep=FakeSweeper().sweep("status_absence").to_dict(),
                   paths={key: {"after": identity(path), "worker_traversal_revoked": True}
                          for key, path in {"workspace": workspace, "run": run}.items()})
    if fault == "worker":
        receipt["uid_sweep"]["worker_uid"] += 1
    elif fault == "control":
        receipt["control_uid"] += 1
    elif fault in {"job", "attempt"}:
        receipt[fault + "_id"] = "foreign"
    elif fault == "sweep":
        receipt["uid_sweep"]["passed"] = False
    elif fault == "inode":
        receipt["paths"]["workspace"]["after"]["inode"] += 1
    elif fault == "mode":
        workspace.chmod(0o750)
    elif fault == "path":
        receipt["paths"]["run"]["after"]["path"] = str(workspace)
    monkeypatch.setattr(pwd, "getpwnam", lambda user: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(autonomy, "_root_json", lambda *args, **kwargs: (
        receipt, json.dumps(receipt).encode(),
    ))
    config = dict(receipts_root=str(tmp_path/"receipts"), worker_runs_root=str(run_root), worker_uid=os.getuid())
    job = SimpleNamespace(job_id="JOB-one", worktree=str(workspace))
    attempt = SimpleNamespace(attempt_id="ATT-one")
    if fault is None:
        assert set(m.terminal_assignment(config, job, attempt)) == {"assignment_seal_sha256"}
    else:
        with pytest.raises(m.MaintenanceError):
            m.terminal_assignment(config, job, attempt)


def _close_dispatch(runtime, root, job_id, attempt_id, *, block=True):
    from control_plane.executive_coo_cycle import CooCycle
    command = f"coo-cycle:{root.job_id}:dispatch:{job_id}:attempt:1"
    receipt = runtime.attempts.terminal_cycle_dispatch_outcome(job_id, command_id=command)
    runtime.jobs.reconcile_cycle_dispatch_effect(root.job_id, selected_job_id=job_id,
                                                dispatch_command_id=command, receipt=receipt)
    if block:
        def forbidden(*args):
            raise AssertionError("resolved terminal history cannot dispatch")
        assert CooCycle(runtime, dispatcher=forbidden).run_once(root.job_id).action == "BLOCKED"
    return command


def test_terminal_carry_preserves_canonical_block_without_reopening(tmp_path, monkeypatch):
    runtime, root, _before, config, prior, material, proof, job_id, attempt_id = _terminal_fixture(tmp_path, monkeypatch)
    _close_dispatch(runtime, root, job_id, attempt_id)
    before = m.snapshot(runtime.store.path)
    selected, fields = m.terminal_carry_fields(runtime, root, config, before, "b"*40)
    assert selected is proof
    assert fields["terminal_attempt_id"] == attempt_id
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id) is None
    assert runtime.jobs.validated_cycle_block(root.job_id)[1]["reason"] == "plan_terminal_adverse"
    assert m.snapshot(runtime.store.path) == before
    descriptor = dict(prior, schema_version=m.SCHEMA_V2, predecessor_sha="b"*40,
                      successor_sha="c"*40, **material)
    monkeypatch.setattr(m, "descriptor_for", lambda sha: descriptor)
    monkeypatch.setattr(m, "summary_document", lambda sha: ({}, b"accepted"))
    monkeypatch.setattr(m, "validate_carry_receipt", lambda *args: None)
    # Policy rotation must not recover the old root's historical binding.
    current = dict(base_sha="c"*40, execution_profile_digest="f"*64, operator_harness_armed=True)
    assert m.frozen_binding(root, current, runtime.store) is current


@pytest.mark.parametrize("fault", ["no-block", "extra-resolution", "order", "block-identity", "claim", "lease"])
def test_blocked_terminal_carry_refuses_incomplete_or_changed_history(tmp_path, monkeypatch, fault):
    runtime, root, _before, config, _prior, _material, _proof, job_id, attempt_id = _terminal_fixture(tmp_path, monkeypatch)
    command = _close_dispatch(runtime, root, job_id, attempt_id, block=fault != "no-block")
    if fault in {"block-identity", "claim", "lease"}:
        with runtime.store.transaction() as conn:
            # Deliberate corruption of this isolated test database: the normal
            # immutability triggers already reject these writes at runtime.
            conn.execute("DROP TRIGGER " + ("terminal_attempts_are_immutable" if fault == "lease"
                                           else "events_are_immutable_update"))
            if fault == "block-identity":
                conn.execute("UPDATE events SET actor='foreign' WHERE event_type='COO_CYCLE_BLOCKED' AND job_id=?", (root.job_id,))
            elif fault == "claim":
                conn.execute("UPDATE events SET aggregate_id='foreign' WHERE command_id=?", (command,))
            else:
                conn.execute("PRAGMA ignore_check_constraints=ON")
                conn.execute("UPDATE attempts SET lease_token='foreign' WHERE attempt_id=?", (attempt_id,))
    before = m.snapshot(runtime.store.path)
    if fault == "extra-resolution":
        resolution = next(e for e in before["tables"]["events"] if e["event_type"] == "COO_DISPATCH_RECONCILED")
        before["tables"]["events"].append(dict(resolution, event_id=9999))
    elif fault == "order":
        next(e for e in before["tables"]["events"] if e["event_type"] == "COO_CYCLE_BLOCKED")["event_id"] = 1
    with pytest.raises(m.MaintenanceError):
        m.terminal_carry_fields(runtime, root, config, before, "b"*40)

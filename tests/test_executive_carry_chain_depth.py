"""Release history depth is bounded independently of preserved root identity."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as m


def lineage(monkeypatch, count):
    descriptors, receipts, summaries = {}, {}, {}
    for index in range(1, count + 1):
        sha, predecessor = f"{index:040x}", f"{index - 1:040x}"
        descriptor = dict(schema_version=m.SCHEMA, successor_sha=sha,
                          predecessor_sha=predecessor, root_job_id="JOB-preserved",
                          root_identity_sha256="1" * 64, root_event_id=1,
                          root_event_sha256="2" * 64)
        if index > 1:
            descriptor.update(
                schema_version=m.SCHEMA_V2, frozen_base_sha="0" * 40,
                prior_descriptor_sha256=m.digest(descriptors[predecessor]),
                prior_carry_sha256=m.digest(receipts[predecessor]),
                prior_summary_sha256=hashlib.sha256(summaries[predecessor][1]).hexdigest(),
            )
        descriptors[sha] = descriptor
        summaries[sha] = ({"success_job_id": f"JOB-proof-{index}"}, sha.encode())
        receipts[sha] = dict(schema_version=descriptor["schema_version"], passed=True,
                             baseline_preserved=True, descriptor_sha256=m.digest(descriptor),
                             acceptance_summary_sha256=hashlib.sha256(sha.encode()).hexdigest())
    monkeypatch.setattr(m, "descriptor_for", lambda sha: descriptors.get(sha))
    monkeypatch.setattr(m, "summary_document", lambda sha: summaries[sha])
    monkeypatch.setattr(m, "sealed_json", lambda path: receipts[path.parent.name])
    return sha, descriptors, receipts, summaries


@pytest.mark.parametrize("count", [9, 63, 64])
def test_long_accepted_release_history_preserves_original_root(monkeypatch, count):
    sha, descriptors, receipts, summaries = lineage(monkeypatch, count)
    m.validate_carry_receipt(sha, hashlib.sha256(summaries[sha][1]).hexdigest())
    prior, _, material = m.prior_carry_material(sha)
    assert prior is descriptors[sha]
    assert material["frozen_base_sha"] == "0" * 40
    assert material["prior_carry_sha256"] == m.digest(receipts[sha])


def test_first_over_budget_history_refuses_before_unbounded_reads(monkeypatch):
    sha, descriptors, _, summaries = lineage(monkeypatch, 65)
    reads = []
    def descriptor_for(value):
        reads.append(value)
        return descriptors.get(value)
    monkeypatch.setattr(m, "descriptor_for", descriptor_for)
    with pytest.raises(m.MaintenanceError, match="too deep"):
        m.validate_carry_receipt(sha, hashlib.sha256(summaries[sha][1]).hexdigest())
    assert len(set(reads)) <= 65


@pytest.mark.parametrize("seen_count", [1, 64])
def test_repeated_release_is_a_cycle_even_at_depth_limit(monkeypatch, seen_count):
    sha = "1" * 40
    seen = frozenset([sha] + [f"{index:040x}" for index in range(2, seen_count + 1)])
    monkeypatch.setattr(m, "descriptor_for", lambda _: pytest.fail("cycle must refuse before read"))
    with pytest.raises(m.MaintenanceError, match="cyclic"):
        m.validate_carry_receipt(sha, "0" * 64, _seen=seen)


@pytest.mark.parametrize("fault", ["receipt", "summary", "descriptor", "root", "base"])
def test_long_history_still_validates_old_ancestor(monkeypatch, fault):
    sha, descriptors, receipts, summaries = lineage(monkeypatch, 12)
    oldest = f"{1:040x}"
    if fault == "receipt":
        receipts[oldest]["passed"] = False
    elif fault == "summary":
        summaries[oldest] = ({}, b"changed")
    elif fault == "descriptor":
        descriptors[oldest]["root_event_sha256"] = "3" * 64
    else:
        # An internally resealed descendant must still retain its ancestor's
        # root identity and original frozen base, not merely its own PASS.
        descriptors[sha]["root_job_id" if fault == "root" else "frozen_base_sha"] = (
            "JOB-other" if fault == "root" else "f" * 40)
        receipts[sha]["descriptor_sha256"] = m.digest(descriptors[sha])
    with pytest.raises(m.MaintenanceError):
        m.validate_carry_receipt(sha, hashlib.sha256(summaries[sha][1]).hexdigest())


def test_prospective_successor_counts_toward_same_budget(monkeypatch):
    sha, _, _, _ = lineage(monkeypatch, 64)
    # Current accepted history fits; adding another release must fail before
    # terminal fields inspect Runtime or a preparation bundle can be written.
    m.prior_carry_material(sha)
    with pytest.raises(m.MaintenanceError, match="too deep"):
        m.terminal_carry_fields(None, None, {}, {}, sha, f"{65:040x}")


def test_prospective_successor_cannot_reuse_an_ancestor_release(monkeypatch):
    sha, _, _, _ = lineage(monkeypatch, 12)
    with pytest.raises(m.MaintenanceError, match="cyclic"):
        m.terminal_carry_fields(None, None, {}, {}, sha, f"{1:040x}")


def test_longer_predecessor_cycle_is_not_reported_as_valid_history(monkeypatch):
    sha, descriptors, receipts, summaries = lineage(monkeypatch, 12)
    oldest = f"{1:040x}"
    descriptors[oldest].update(schema_version=m.SCHEMA_V2, predecessor_sha=sha)
    receipts[oldest].update(schema_version=m.SCHEMA_V2,
                           descriptor_sha256=m.digest(descriptors[oldest]))
    with pytest.raises(m.MaintenanceError, match="cyclic"):
        m.validate_carry_receipt(sha, hashlib.sha256(summaries[sha][1]).hexdigest())


def test_preparation_rejects_future_limit_before_artifact_or_bundle_writes(tmp_path, monkeypatch):
    from control_plane.executive_runtime import Runtime
    predecessor, _, _, _ = lineage(monkeypatch, 64)
    system = tmp_path / "system"
    (system / "config").mkdir(parents=True)
    (system / "config/control.json").write_text(json.dumps(dict(
        runtime_root=str(tmp_path / "runtime"), proof_base_sha=predecessor,
        ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)))
    (system / "config/worker-codex.json").write_text('{"operator_harness_armed":false}')
    monkeypatch.setattr(m, "SYSTEM_ROOT", system)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(m, "require_stopped", lambda: None)
    monkeypatch.setattr(m, "snapshot", lambda _: {"tables": {"attempts": [], "worker_quota_classes": []}})
    monkeypatch.setattr(m, "inventory", lambda _: pytest.fail("must refuse before artifact scan/writes"))
    root = SimpleNamespace(job_id="JOB-preserved", status=SimpleNamespace(value="QUEUED"),
                           orchestration_role="aggregation", attempt_count=0, current_attempt_id=None,
                           parent_job_id=None, root_job_id="JOB-preserved", depth=0,
                           constraints={"operator_harness_armed": False}, orchestration_provenance_digest="a" * 64)
    monkeypatch.setattr(Runtime, "at", lambda *a, **kw: SimpleNamespace(
        jobs=SimpleNamespace(get_job=lambda _: root)))
    args = SimpleNamespace(predecessor_sha=predecessor, successor_sha=f"{65:040x}",
                           root_job_id=root.job_id, carry_terminal_dispatch=True,
                           recovery_job_id=None, recovery_attempt_id=None)
    with pytest.raises(m.MaintenanceError, match="too deep"):
        m.prepare(args)
    assert not (system / "acceptance-maintenance").exists()

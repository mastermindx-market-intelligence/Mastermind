"""An ordinary accepted carry cannot authorize a schema transition by resealing."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import os

import pytest

from ops.executive_os import acceptance_maintenance as m


class _WriteBoundary(RuntimeError):
    def __init__(self, path):
        self.path = Path(path)
        super().__init__(str(path))


def _ordinary_boundary(tmp_path, monkeypatch, fault):
    """Keep unrelated admission owners fixed; exercise the real write boundaries."""
    from control_plane import executive_runtime as rt

    predecessor, successor = "a" * 40, "b" * 40
    system = tmp_path / "system"
    (system / "config").mkdir(parents=True)
    canary = tmp_path / "canary.json"
    canary.write_text("{}")
    config = {
        "proof_base_sha": predecessor,
        "runtime_root": str(tmp_path / "runtime"),
        "worker_id": "fixture-worker",
        "quota_class": "fixture-quota",
        "secret_canary_receipt_path": str(canary),
        **{key: str(tmp_path / key) for key in (
            "proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root")},
    }
    (system / "config" / "control.json").write_text(json.dumps(config))
    (system / "config" / "worker-codex.json").write_text(
        '{"operator_harness_armed": false}')
    baseline = {
        "schema": [["table", "schema_migrations", "schema_migrations",
                    "CREATE TABLE schema_migrations(version INTEGER, digest TEXT)"]],
        "tables": {
            "schema_migrations": [
                {"version": version, "digest": str(version) * 64}
                for version in range(1, 6)],
            "attempts": [],
            "worker_quota_classes": [],
            "jobs": [],
            "events": [{"job_id": "fixture-root", "event_type": "JOB_CREATED",
                        "event_id": 1}],
        },
    }
    current = deepcopy(baseline)
    prior = {"schema_version": m.SCHEMA_V2,
             "baseline_sha256": m.digest(baseline)}
    if fault == "schema":
        current["schema"].append(["index", "new_index", "jobs", "CREATE INDEX new_index"])
    elif fault == "migration-history":
        current["tables"]["schema_migrations"][1]["digest"] = "9" * 64
    elif fault == "new-migration":
        current["tables"]["schema_migrations"].append({"version": 6, "digest": "6" * 64})
    elif fault == "baseline-pin":
        prior["baseline_sha256"] = "0" * 64
    elif fault == "missing-history":
        del current["tables"]["schema_migrations"]
    elif fault == "typed-history":
        # Python's plain equality conflates True and 1; sealed JSON must not.
        current["tables"]["schema_migrations"][0]["version"] = True
    elif fault == "missing-prior":
        prior = None
    descriptor = {
        "schema_version": m.SCHEMA_V2,
        "predecessor_sha": predecessor,
        "successor_sha": successor,
        "root_job_id": "fixture-root",
        "baseline_sha256": m.digest(current),
        "inventory_sha256": m.digest({}),
        "prior_canary_sha256": m.digest({}),
        "backup_sha256": "d" * 64,
    }
    root = SimpleNamespace(
        job_id="fixture-root", root_job_id="fixture-root", parent_job_id=None,
        status=SimpleNamespace(value="QUEUED"), orchestration_role="aggregation",
        attempt_count=0, current_attempt_id=None, depth=0,
        orchestration_provenance_digest="provenance",
        constraints={"operator_harness_armed": False, "base_sha": predecessor},
    )
    runtime = SimpleNamespace(jobs=SimpleNamespace(get_job=lambda _job_id: root))
    descriptors = {predecessor: prior, successor: descriptor}
    real_uid = os.geteuid()
    monkeypatch.setattr(m, "SYSTEM_ROOT", system)
    monkeypatch.setattr(m, "_TRUSTED_UID", real_uid)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "platform", "darwin")
    monkeypatch.setattr(m, "require_stopped", lambda: None)
    monkeypatch.setattr(m, "require_disarmed", lambda _config: None)
    monkeypatch.setattr(m, "descriptor_for", lambda sha: descriptors.get(sha))
    monkeypatch.setattr(m, "validate_prior_carry_binding", lambda _descriptor: None)
    monkeypatch.setattr(m, "snapshot", lambda _database, **_options: deepcopy(current))
    monkeypatch.setattr(m, "inventory", lambda _roots: {})
    monkeypatch.setattr(m, "verify_inventory", lambda _inventory: None)
    monkeypatch.setattr(m, "_file_digest", lambda _path: "d" * 64)
    monkeypatch.setattr(m, "_sealed_ancestors", lambda _path: [])
    monkeypatch.setattr(m, "terminal_carry_fields", lambda *_args, **_kwargs: (None, {}))
    monkeypatch.setattr(rt.Runtime, "at", lambda *_args, **_kwargs: runtime)

    def sealed(path):
        if path.name == "baseline.json":
            return deepcopy(baseline if path.parent.name == predecessor else current)
        if path.name in {"inventory.json", "prior-secret-canary.json"}:
            return {}
        raise AssertionError("unexpected fixture read: " + str(path))

    writes = []
    def write_edge(path, *_args, **_kwargs):
        writes.append(Path(path))
        raise _WriteBoundary(path)

    monkeypatch.setattr(m, "sealed_json", sealed)
    monkeypatch.setattr(m, "write_sealed", write_edge)
    args = SimpleNamespace(
        predecessor_sha=predecessor, successor_sha=successor,
        root_job_id=root.job_id, carry_terminal_dispatch=True,
        recovery_job_id=None, recovery_attempt_id=None,
    )
    return args, config, descriptor, baseline, current, writes


@pytest.mark.parametrize("phase", ["preparation", "acceptance"])
@pytest.mark.parametrize("fault", [
    None, "schema", "migration-history", "new-migration", "baseline-pin",
    "missing-history", "typed-history", "missing-prior",
])
def test_ordinary_v2_checks_accepted_schema_before_any_write(
    tmp_path, monkeypatch, phase, fault,
):
    args, config, descriptor, _baseline, _current, writes = _ordinary_boundary(
        tmp_path, monkeypatch, fault)
    def invoke():
        if phase == "preparation":
            return m.prepare(args)
        return m.Maintenance(args.successor_sha, m.digest(descriptor), config)

    if fault is None:
        with pytest.raises(_WriteBoundary) as reached:
            invoke()
        expected = "preparing.json" if phase == "preparation" else "run-started.json"
        assert reached.value.path.name == expected
        assert len(writes) == 1
    else:
        with pytest.raises(m.MaintenanceError, match=(
            "accepted predecessor baseline" if fault == "missing-prior"
            else "explicit verified maintenance transition"
        )):
            invoke()
        assert writes == []
        assert not m.bundle_path(args.successor_sha).exists()
        if phase == "preparation":
            assert not m.bundle_path(args.successor_sha).parent.exists()


def test_schema_guard_leaves_ordinary_proof_row_checks_to_the_existing_owner(
    tmp_path, monkeypatch,
):
    args, _config, _descriptor, _baseline, current, _writes = _ordinary_boundary(
        tmp_path, monkeypatch, None)
    current["tables"]["events"].append(
        {"job_id": "legitimate-proof", "event_type": "JOB_CREATED", "event_id": 2})
    # Only schema/history equality is this guard's job. Runtime and preservation
    # owners still decide which job/event changes are permitted.
    m.require_unchanged_schema(args.predecessor_sha, current)


# The joined path uses real temporary SQLite, migration/backup/restore owners
# and Maintenance validators. Only host/account/ACL/install observations and
# the fixed legacy accepted seed are fixture inputs; no live host is exercised.
from contextlib import closing, contextmanager
import fcntl
import gc
import hashlib
import shutil
import sqlite3

from control_plane import executive_backup as backup
from control_plane import executive_runtime as rt
from ops.executive_os import acceptance_schema_transition as transition
from ops.executive_os import schema_upgrade_evidence as evidence_owner
from tests import test_executive_acceptance_v5_to_v7 as joined
from tests.test_executive_acceptance_v5_to_v7 import _no_external_effects
from tests.test_prepare_control_successor import control_input

LEGACY, ACCEPTED, SUCCESSOR = "9"*40, "b"*40, "c"*40


@contextmanager
def _historical_v5(monkeypatch):
    """Construct historical records under schema5 before actual closed upgrades."""
    with monkeypatch.context() as historical:
        historical.setattr(rt, "_MIGRATIONS", rt._MIGRATIONS[:5])
        historical.setattr(rt, "SCHEMA_VERSION", 5)
        historical.setattr(rt, "_NORMALIZED_V7_SCHEMA_DIGEST", rt._NORMALIZED_V5_SCHEMA_DIGEST)
        yield


def _config(f, raw):
    path = m.SYSTEM_ROOT/"config/control.json"
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(0o440)
    f.config.clear()
    f.config.update(json.loads(raw))


def _summary(f, sha, proof_ids, monkeypatch):
    with monkeypatch.context() as local:
        local.setattr(joined, "SUCCESSOR", sha)
        value = joined._real_pass_summary(f, proof_ids)
    directory = f.runtime_root.parent.parent/"control"/"acceptance"/sha
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/"acceptance-summary.json"
    joined._write_receipt(path, value)
    return path


def _args(f, **changes):
    value = dict(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
                 root_job_id=f.root.job_id, carry_terminal_dispatch=True,
                 recovery_job_id=None, recovery_attempt_id=None,
                 seal_accepted_v2_v5_source=True, accepted_v2_v5_to_v7=False,
                 accepted_v2_source_sha256=None)
    value.update(changes)
    return SimpleNamespace(**value)


def _accepted_fixture(tmp_path, monkeypatch, *, quiesce=True):
    """A real accepted V2 delta, above one explicitly fixed legacy PASS input."""
    real_prior = m.prior_carry_material
    f = joined._v5_host_fixture(tmp_path, monkeypatch)
    # The inherited fixture supplies an opaque old ancestor. Replace only that
    # seam with sealed historical input so the new accepted-V2 walk is real.
    monkeypatch.setattr(m, "prior_carry_material", real_prior)
    full = control_input.__wrapped__()
    full.update(f.config)
    full.update(control_uid=os.getuid(), worker_uid=os.getuid()+1,
                worker_gid=os.getgid()+1, shared_run_gid=os.getgid()+1,
                proof_base_sha=LEGACY, ceo_ingress_app_armed=False,
                terminal_return_armed=False,
                terminal_return_socket_path="/var/db/mastermind-agent-relay/socket/agent-relay.sock")
    _config(f, (json.dumps(full, sort_keys=True, indent=2)+"\n").encode())
    f.current_install = [LEGACY]
    f.install_checks = []
    def installed(sha):
        f.install_checks.append(sha)
        if sha != f.current_install[0]:
            raise m.MaintenanceError("inert exact-install observation refused")
    monkeypatch.setattr(m, "_require_preparation_install", installed)
    legacy_bundle = m.bundle_path(LEGACY)
    legacy_bundle.mkdir()
    shutil.copyfile(f.runtime.store.path, legacy_bundle/"prestate.sqlite3")
    (legacy_bundle/"prestate.sqlite3").chmod(0o400)
    legacy = dict(f.ancestor, predecessor_sha=joined.ACCEPTED, successor_sha=LEGACY,
                  baseline_sha256=m.digest(f.before),
                  backup_sha256=m._file_digest(legacy_bundle/"prestate.sqlite3"),
                  inventory_sha256=m.digest(f.artifacts),
                  prior_canary_sha256=m.digest(f.live_envelope),
                  recovery_job_id=f.proof.job_id,
                  recovery_attempt_id=f.proof.current_attempt_id,
                  recovery_job_sha256=m.digest(f.proof.to_dict()))
    for name, value in (
            ("descriptor.json", legacy), ("baseline.json", f.before),
            ("inventory.json", f.artifacts), ("prior-secret-canary.json", f.live_envelope),
            ("preparing.json", {"schema_version": m.SCHEMA})):
        m.write_sealed(legacy_bundle/name, value, public=name == "descriptor.json")
    with _historical_v5(monkeypatch), monkeypatch.context() as old:
        old.setattr(joined, "SUCCESSOR", LEGACY)
        legacy_proofs = joined._actual_proof_delta(f, dict(
            template_proof_job_id=f.proof.job_id, worker_id=f.config["worker_id"],
            quota_class=f.config["quota_class"]))
    legacy_summary = _summary(f, LEGACY, legacy_proofs, monkeypatch)
    m.write_sealed(legacy_bundle/"carry-forward.json", dict(
        schema_version=m.SCHEMA, passed=True, baseline_preserved=True,
        descriptor_sha256=m.digest(legacy),
        acceptance_summary_sha256=hashlib.sha256(legacy_summary.read_bytes()).hexdigest()))
    m.validate_carry_receipt(LEGACY, hashlib.sha256(legacy_summary.read_bytes()).hexdigest())
    with _historical_v5(monkeypatch), monkeypatch.context() as old:
        old.setattr(joined, "SUCCESSOR", ACCEPTED)
        prepared = m.prepare(_args(f, predecessor_sha=LEGACY, successor_sha=ACCEPTED,
                                   seal_accepted_v2_v5_source=False))
        f.accepted_descriptor = m.descriptor_for(ACCEPTED)
        f.accepted_baseline = m.sealed_json(prepared/"baseline.json")
        _config(f, m._normal_installed_preparation_config(
            (m.SYSTEM_ROOT/"config/control.json").read_bytes(), ACCEPTED))
        f.current_install[0] = ACCEPTED
        owner = m.Maintenance(ACCEPTED, m.digest(f.accepted_descriptor), f.config)
        f.accepted_proofs = joined._actual_proof_delta(f, f.accepted_descriptor)
        accepted_summary = _summary(f, ACCEPTED, f.accepted_proofs, monkeypatch)
        owner.finish(f.accepted_proofs, accepted_summary)
    # Acceptance may still have a live WAL: capture its consistent view first.
    # The offline fixture boundary below proves the same view after checkpoint.
    f.source_before = m.snapshot(f.runtime.store.path)
    assert m.digest(f.accepted_baseline) != m.digest(f.source_before)
    m.verify_preserved(f.accepted_baseline, f.source_before,
                      f.accepted_descriptor, f.accepted_proofs)
    m.prior_carry_material(ACCEPTED)
    f.database = Path(f.runtime.store.path)
    # Historical commands have exited before the offline source phase.
    # Release their unreachable SQLite connections; never remove sidecars.
    gc.collect()
    if quiesce:
        # Model the already-authorized offline boundary on disposable fixture
        # state. Use SQLite's real checkpoint/close protocol; never unlink a
        # sidecar or weaken Maintenance's absence gate.
        with closing(sqlite3.connect(f.database)) as connection:
            assert connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
            assert connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        assert not any(Path(str(f.database)+suffix).exists()
                       for suffix in ("-wal", "-shm", "-journal"))
        assert m.snapshot(f.database, immutable=True) == f.source_before
    f.args = _args(f)
    return f


def _sealed_source(tmp_path, monkeypatch):
    f = _accepted_fixture(tmp_path, monkeypatch)
    f.source_bundle = m.prepare(f.args)
    f.intent = m.sealed_json(f.source_bundle/"intent.json")
    assert f.intent["baseline_sha256"] == m.digest(f.source_before)
    assert not m.bundle_path(SUCCESSOR).exists()
    f.source_state = {path.name: (path.read_bytes(), path.stat().st_ino)
                      for path in f.source_bundle.iterdir()}
    return f


def _migrated_accepted(tmp_path, monkeypatch):
    f = _sealed_source(tmp_path, monkeypatch)
    raw = m._normal_installed_preparation_config(
        (f.source_bundle/"source-control.json").read_bytes(), SUCCESSOR)
    _config(f, raw)
    f.current_install[0] = SUCCESSOR
    joined._migrate_source_fixture(f, tmp_path, monkeypatch)
    f.consume_args = _args(f, seal_accepted_v2_v5_source=False,
                          accepted_v2_v5_to_v7=True,
                          accepted_v2_source_sha256=m.digest(f.intent))
    return f


def _assert_source_unchanged(f):
    assert f.source_state == {path.name: (path.read_bytes(), path.stat().st_ino)
                              for path in f.source_bundle.iterdir()}


def test_accepted_v2_direct_journey_seals_migrates_admits_restores_and_carries(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    class SourceClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 6, 12, 0, 0, 200000, tzinfo=timezone.utc)
    # P56's real producer has seconds precision. Sealing at .200000 then
    # preflighting at .800000 in the same second is a valid ordered journey.
    monkeypatch.setattr(transition, "datetime", SourceClock)
    monkeypatch.setattr(backup, "_upgrade_now", lambda: "2026-11-06T12:00:00+00:00")
    f = _migrated_accepted(tmp_path, monkeypatch)
    assert f.intent["sealed_at"] == "2026-11-06T12:00:00+00:00"
    with pytest.raises(m.MaintenanceError):
        m.prepare(f.args)  # existing source and a different selected release
    result = m.prepare(f.consume_args)
    descriptor = m.descriptor_for(SUCCESSOR)
    assert descriptor["schema_version"] == m.SCHEMA_ACCEPTED_V2_V5_TO_V7
    assert descriptor["accepted_source_sha256"] == m.digest(f.intent)
    assert descriptor["baseline_sha256"] == m.digest(f.v7_before)
    assert descriptor["baseline_sha256"] != f.intent["baseline_sha256"]
    assert not (result/"run-started.json").exists()
    owner = m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert owner.predecessor_recovery_required is False
    assert m.sealed_json(result/"run-started.json")["descriptor_sha256"] == m.digest(descriptor)
    with pytest.raises(m.MaintenanceError):
        m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    _assert_source_unchanged(f)
    proof_ids = joined._actual_proof_delta(f, descriptor)
    receipt, verification, drill, applied = joined._proof_backup_chain(f, tmp_path)
    acceptance = joined._write_proof_receipts(f, receipt, verification, drill, applied)
    summary = _summary(f, SUCCESSOR, proof_ids, monkeypatch)
    # A legitimate restore and subsequent Service activity must not be
    # misclassified as an INITIAL migration-target identity failure.
    restored_identity = (f.database.stat().st_dev, f.database.stat().st_ino)
    assert restored_identity != (f.intent["database"]["device"], f.intent["database"]["inode"])
    outside = os.open(f.lock, os.O_RDWR)
    fcntl.flock(outside, fcntl.LOCK_EX | fcntl.LOCK_NB)
    live = sqlite3.connect(f.database)
    live.execute("PRAGMA journal_mode=WAL")
    with live:
        live.execute("UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1,"
                     "updated_at_ms=updated_at_ms+1,version=version+1")
    try:
        owner.finish(proof_ids, summary)
    finally:
        live.close()
        fcntl.flock(outside, fcntl.LOCK_UN)
        os.close(outside)
    carry = m.sealed_json(result/"carry-forward.json")
    assert carry["schema_version"] == m.SCHEMA_ACCEPTED_V2_V5_TO_V7
    assert carry["acceptance_restore_evidence_sha256"] == m.digest(
        m.sealed_json(result/m._V5_TO_V7_RESTORE_EVIDENCE_NAME))
    with pytest.raises(m.MaintenanceError):
        owner.finish(proof_ids, summary)
    # Future carry traverses the real historical migration/restore reader;
    # today's unrelated live rows are not retrospective source proof.
    rt.Runtime.at(f.runtime_root).jobs.create_job("later unrelated fixture job")
    (Path(f.config["receipts_root"])/"later-unrelated.txt").write_text("later independent artifact")
    m.validate_carry_receipt(SUCCESSOR, hashlib.sha256(summary.read_bytes()).hexdigest())
    future = {key: value for key, value in descriptor.items() if key in m._DESCRIPTOR_V2_KEYS}
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=SUCCESSOR, successor_sha="1"*40,
        prior_descriptor_sha256=m.digest(descriptor), prior_carry_sha256=m.digest(carry),
        prior_summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest())
    m.validate_prior_carry_binding(future)
    _assert_source_unchanged(f)


@pytest.mark.parametrize("fault", [
    "both-actions", "no-carry", "same-release", "missing-digest", "orphan-digest",
    "recovery", "preproof", "prepared", "pre-census", "source-only",
])
def test_accepted_v2_selector_is_closed_before_owner_access(fault):
    args = SimpleNamespace(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
        root_job_id="fixture-root", carry_terminal_dispatch=True,
        seal_accepted_v2_v5_source=False, accepted_v2_v5_to_v7=True,
        accepted_v2_source_sha256="a"*64)
    if fault == "both-actions":
        args.seal_accepted_v2_v5_source = True
    elif fault == "no-carry":
        args.carry_terminal_dispatch = False
    elif fault == "same-release":
        args.successor_sha = ACCEPTED
    elif fault == "missing-digest":
        args.accepted_v2_source_sha256 = None
    elif fault == "orphan-digest":
        args.accepted_v2_v5_to_v7 = False
    else:
        name = {
            "recovery": "recovery_job_id", "preproof": "supersede_preproof_sha",
            "prepared": "supersede_unstarted_migration_preparation_sha",
            "pre-census": "qualify_v5_pre_census_continuation",
            "source-only": "qualify_v5_source_only",
        }[fault]
        setattr(args, name, True)
    with pytest.raises(m.MaintenanceError):
        m.prepare(args)


def _rewrite_fixture(path, value):
    """Adversarial rewrite of disposable sealed input, including its hash."""
    mode = path.stat().st_mode & 0o7777
    path.chmod(0o600)
    path.write_bytes((json.dumps(value, sort_keys=True, indent=2)+"\n").encode())
    path.chmod(mode)


def _replace_fixture(path):
    """Preserve bytes/mode while changing the actual held namespace identity."""
    original = path.read_bytes()
    inode = path.stat().st_ino
    replacement = path.with_name(path.name+".adversarial-replacement")
    replacement.write_bytes(original)
    replacement.chmod(path.stat().st_mode & 0o7777)
    os.replace(replacement, path)
    assert path.read_bytes() == original and path.stat().st_ino != inode


@pytest.mark.parametrize("fault", [
    "wrong-root", "missing-carry", "migration-started", "warm-sidecars",
])
def test_source_seal_refuses_unaccepted_or_nonquiescent_input_before_publication(
    tmp_path, monkeypatch, fault,
):
    f = _accepted_fixture(tmp_path, monkeypatch)
    connection = None
    if fault == "wrong-root":
        f.args.root_job_id = "foreign-root"
    elif fault == "missing-carry":
        path = m.bundle_path(ACCEPTED)/"carry-forward.json"
        path.rename(path.with_name("withdrawn-carry.json"))
    elif fault == "migration-started":
        path = f.database.parent/backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME
        m.write_sealed(path, {"untrusted": "already-present"})
    else:
        connection = sqlite3.connect(f.database)
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("SELECT COUNT(*) FROM jobs").fetchone()
        assert Path(str(f.database)+"-wal").exists()
    try:
        with pytest.raises((m.MaintenanceError, OSError)):
            m.prepare(f.args)
    finally:
        if connection is not None:
            connection.close()
    assert not transition.source_bundle(m, SUCCESSOR).exists()
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not (m.bundle_path(SUCCESSOR).parent/
                (".preparing-schema-source-"+SUCCESSOR)).exists()


@pytest.mark.parametrize("namespace", ["partial", "final"])
def test_source_seal_never_overwrites_or_removes_an_existing_operation(
    tmp_path, monkeypatch, namespace,
):
    f = _accepted_fixture(tmp_path, monkeypatch)
    path = (transition.source_bundle(m, SUCCESSOR) if namespace == "final" else
            m.bundle_path(SUCCESSOR).parent/(".preparing-schema-source-"+SUCCESSOR))
    path.mkdir(mode=0o700)
    marker = path/"original-operation.json"
    marker.write_text('{"operation": "preserve-me"}')
    before = marker.read_bytes(), marker.stat().st_ino
    with pytest.raises(m.MaintenanceError, match="reconcile the original operation"):
        m.prepare(f.args)
    assert (marker.read_bytes(), marker.stat().st_ino) == before
    assert not m.bundle_path(SUCCESSOR).exists()


@pytest.mark.parametrize("fault", [
    "source-inode", "source-device", "source-after-p56", "naive-time",
])
def test_resealed_source_cannot_replace_actual_p56_identity_or_chronology(
    tmp_path, monkeypatch, fault,
):
    f = _migrated_accepted(tmp_path, monkeypatch)
    changed = deepcopy(f.intent)
    if fault == "source-inode":
        changed["database"]["inode"] += 1
        match = "P56 authoritative source identity differs"
    elif fault == "source-device":
        changed["database"]["device"] += 1
        match = "P56 authoritative source identity differs"
    elif fault == "source-after-p56":
        changed["sealed_at"] = "2099-01-01T00:00:00+00:00"
        match = "source seal postdates P56"
    else:
        changed["sealed_at"] = "2026-11-06T12:00:00"
        match = "timezone-aware UTC"
    _rewrite_fixture(f.source_bundle/"intent.json", changed)
    f.consume_args.accepted_v2_source_sha256 = m.digest(changed)
    with pytest.raises(m.MaintenanceError, match=match):
        m.prepare(f.consume_args)
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not (m.bundle_path(SUCCESSOR).parent/
                (".preparing-accepted-v2-"+SUCCESSOR)).exists()


def test_p56_source_identity_is_detached_data_without_changing_material(
    tmp_path, monkeypatch,
):
    f = _migrated_accepted(tmp_path, monkeypatch)
    with evidence_owner.open_v5_to_v7_evidence(f.runtime_root, SUCCESSOR) as evidence:
        material = m._json_data(evidence.material)
        original = evidence.source_v5_database_identity
        assert original == f.intent["database"]
        changed = evidence.source_v5_database_identity
        changed["inode"] += 1
        changed["path"] = str(tmp_path/"foreign.sqlite3")
        assert evidence.source_v5_database_identity == original
        assert m._json_data(evidence.material) == material
        assert "source_v5_database_identity" not in material
        assert "source_v5_preflight_created_at" not in material
        with m._UnstartedPreproofGuard() as guard:
            source = transition.open_source(m, SUCCESSOR, guard,
                expected_digest=m.digest(f.intent), predecessor=ACCEPTED,
                root_id=f.root.job_id)
            source.bind_evidence(evidence, phase=evidence_owner.EVIDENCE_PHASE_INITIAL)
    _assert_source_unchanged(f)


@pytest.mark.parametrize("phase", ["prepare", "admission"])
def test_historical_data_cannot_authorize_initial_descriptor_or_runmarker(
    tmp_path, monkeypatch, phase,
):
    f = _migrated_accepted(tmp_path, monkeypatch)
    if phase == "admission":
        f.working_bundle = m.prepare(f.consume_args)
        descriptor = m.descriptor_for(SUCCESSOR)
    with evidence_owner.open_v5_to_v7_evidence(f.runtime_root, SUCCESSOR) as evidence:
        material = m._json_data(evidence.material)
    @contextmanager
    def historical(runtime_root, release):
        with evidence_owner.open_retained_v5_to_v7_evidence(
                runtime_root, release, pinned_material=material) as retained:
            assert retained.phase == evidence_owner.EVIDENCE_PHASE_HISTORICAL
            yield retained
    monkeypatch.setattr(evidence_owner, "open_v5_to_v7_evidence", historical)
    with pytest.raises(m.MaintenanceError, match="exact normal chain"):
        if phase == "prepare":
            m.prepare(f.consume_args)
        else:
            m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    if phase == "prepare":
        assert not m.bundle_path(SUCCESSOR).exists()
    else:
        assert not (f.working_bundle/"run-started.json").exists()
    _assert_source_unchanged(f)


@pytest.mark.parametrize("phase", ["prepare", "admission"])
def test_live_canary_replacement_after_first_read_cannot_publish(
    tmp_path, monkeypatch, phase,
):
    f = _migrated_accepted(tmp_path, monkeypatch)
    if phase == "admission":
        working = m.prepare(f.consume_args)
        descriptor = m.descriptor_for(SUCCESSOR)
    real = Path.read_text
    fired = []
    def replace_after_read(path, *args, **kwargs):
        value = real(path, *args, **kwargs)
        if path == Path(f.config["secret_canary_receipt_path"]) and not fired:
            _replace_fixture(path)
            fired.append(path)
        return value
    monkeypatch.setattr(Path, "read_text", replace_after_read)
    with pytest.raises((m.MaintenanceError, evidence_owner.SchemaUpgradeEvidenceError, OSError)):
        if phase == "prepare":
            m.prepare(f.consume_args)
        else:
            m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert fired
    if phase == "prepare":
        assert not m.bundle_path(SUCCESSOR).exists()
        assert (m.bundle_path(SUCCESSOR).parent/
                (".preparing-accepted-v2-"+SUCCESSOR)).exists()
    else:
        assert not (working/"run-started.json").exists()
    _assert_source_unchanged(f)


@pytest.mark.parametrize("phase", ["seal", "prepare", "admission"])
@pytest.mark.parametrize("target", ["config", "accepted-baseline", "database", "lock"])
def test_final_terminal_read_rechecks_actual_held_names_before_publication(
    tmp_path, monkeypatch, phase, target,
):
    f = (_accepted_fixture(tmp_path, monkeypatch) if phase == "seal" else
         _migrated_accepted(tmp_path, monkeypatch))
    if phase == "admission":
        working = m.prepare(f.consume_args)
        descriptor = m.descriptor_for(SUCCESSOR)
    real = m.terminal_carry_fields
    fired = []
    def replace_after_terminal_read(*args, **kwargs):
        value = real(*args, **kwargs)
        pending = m.bundle_path(SUCCESSOR).parent/(".preparing-accepted-v2-"+SUCCESSOR)
        if not fired and (phase in {"seal", "admission"} or pending.exists()):
            path = {"config": m.SYSTEM_ROOT/"config/control.json",
                    "accepted-baseline": m.bundle_path(ACCEPTED)/"baseline.json",
                    "database": f.database, "lock": f.lock}[target]
            _replace_fixture(path)
            fired.append(path)
        return value
    monkeypatch.setattr(m, "terminal_carry_fields", replace_after_terminal_read)
    with pytest.raises((m.MaintenanceError, evidence_owner.SchemaUpgradeEvidenceError, OSError)):
        if phase == "seal":
            m.prepare(f.args)
        elif phase == "prepare":
            m.prepare(f.consume_args)
        else:
            m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert fired
    if phase == "seal":
        assert not transition.source_bundle(m, SUCCESSOR).exists()
        assert (m.bundle_path(SUCCESSOR).parent/
                (".preparing-schema-source-"+SUCCESSOR)).exists()
    elif phase == "prepare":
        assert not m.bundle_path(SUCCESSOR).exists()
        assert (m.bundle_path(SUCCESSOR).parent/
                (".preparing-accepted-v2-"+SUCCESSOR)).exists()
    else:
        assert not (working/"run-started.json").exists()


def _admitted_accepted(tmp_path, monkeypatch):
    f = _migrated_accepted(tmp_path, monkeypatch)
    f.working_bundle = m.prepare(f.consume_args)
    f.descriptor = m.descriptor_for(SUCCESSOR)
    f.owner = m.Maintenance(SUCCESSOR, m.digest(f.descriptor), f.config)
    f.proof_ids = joined._actual_proof_delta(f, f.descriptor)
    receipt, verification, drill, applied = joined._proof_backup_chain(f, tmp_path)
    joined._write_proof_receipts(f, receipt, verification, drill, applied)
    f.summary = _summary(f, SUCCESSOR, f.proof_ids, monkeypatch)
    return f


@pytest.mark.parametrize("fault", [
    "promoted-config", "working-baseline", "prior-canary",
    "working-inventory", "working-inventory-file-only",
])
def test_fully_resealed_working_bundle_cannot_rewrite_historical_source_join(
    tmp_path, monkeypatch, fault,
):
    f = _admitted_accepted(tmp_path, monkeypatch)
    f.owner.finish(f.proof_ids, f.summary)
    summary_sha = hashlib.sha256(f.summary.read_bytes()).hexdigest()
    m.validate_carry_receipt(SUCCESSOR, summary_sha)
    descriptor = dict(f.descriptor)
    if fault == "promoted-config":
        path = f.working_bundle/m._V5_TO_V7_SOURCE_CONTROL_NAME
        raw = path.read_bytes()+b"\n"
        path.chmod(0o600)
        path.write_bytes(raw)
        path.chmod(0o400)
        descriptor["source_control_config_sha256"] = hashlib.sha256(raw).hexdigest()
        match = "descriptor does not retain its accepted source ancestry"
    elif fault == "prior-canary":
        path = f.working_bundle/"prior-secret-canary.json"
        forged = dict(m.sealed_json(path), untrusted_extra="replacement")
        _rewrite_fixture(path, forged)
        descriptor["prior_canary_sha256"] = m.digest(forged)
        match = "descriptor does not retain its accepted source ancestry"
    elif fault.startswith("working-inventory"):
        path = f.working_bundle/"inventory.json"
        forged = m.sealed_json(path)
        source_inventory = m.sealed_json(f.source_bundle/"inventory.json")
        assert source_inventory
        removed = next(iter(source_inventory))
        assert removed in forged
        del forged[removed]
        _rewrite_fixture(path, forged)
        if fault == "working-inventory":
            descriptor["inventory_sha256"] = m.digest(forged)
        match = "working inventory is not the original source plus migration additions"
    else:
        path = f.working_bundle/"prestate.sqlite3"
        path.chmod(0o600)
        with closing(sqlite3.connect(path)) as connection:
            with connection:
                connection.execute("UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1,"
                                   "updated_at_ms=updated_at_ms+1,version=version+1")
        path.chmod(0o400)
        before = m.snapshot(path, immutable=True)
        assert m.digest(before) != descriptor["baseline_sha256"]
        _rewrite_fixture(f.working_bundle/"baseline.json", before)
        descriptor["baseline_sha256"] = m.digest(before)
        descriptor["backup_sha256"] = m._file_digest(path)
        match = "working baseline is not the original C67 target"
    _rewrite_fixture(f.working_bundle/"descriptor.json", descriptor)
    _rewrite_fixture(f.working_bundle/"run-started.json",
        {"schema_version": descriptor["schema_version"], "descriptor_sha256": m.digest(descriptor)})
    carry = m.sealed_json(f.working_bundle/"carry-forward.json")
    _rewrite_fixture(f.working_bundle/"carry-forward.json",
                     dict(carry, descriptor_sha256=m.digest(descriptor)))
    with pytest.raises(m.MaintenanceError, match=match):
        m.validate_carry_receipt(SUCCESSOR, summary_sha)
    _assert_source_unchanged(f)


def test_finish_retains_restore_evidence_but_refuses_carry_after_source_replacement(
    tmp_path, monkeypatch,
):
    f = _admitted_accepted(tmp_path, monkeypatch)
    real = m.write_sealed
    fired = []
    restore = f.working_bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME
    def replace_after_restore(path, *args, **kwargs):
        value = real(path, *args, **kwargs)
        if path == restore and not fired:
            _replace_fixture(f.source_bundle/"intent.json")
            fired.append(path)
        return value
    monkeypatch.setattr(m, "write_sealed", replace_after_restore)
    with pytest.raises(m.MaintenanceError):
        f.owner.finish(f.proof_ids, f.summary)
    assert fired and restore.exists()
    retained = restore.read_bytes(), restore.stat().st_ino
    assert not (f.working_bundle/"carry-forward.json").exists()
    # A caller must reconcile this partial operation, not overwrite its receipt.
    with pytest.raises(m.MaintenanceError, match="already sealed"):
        f.owner.finish(f.proof_ids, f.summary)
    assert (restore.read_bytes(), restore.stat().st_ino) == retained


@pytest.mark.parametrize("logical", [False, True])
def test_incumbent_preproof_joined_restore_and_historical_carry_remain_unchanged(
    tmp_path, monkeypatch, logical,
):
    # Focused regression of the common finish/history dispatch changed here.
    # Runs only on this changed candidate and disposable inputs.
    original_fixture = joined._preflight_fixture
    def installed_fixture(*args, **kwargs):
        f = original_fixture(*args, **kwargs)
        # Model the installed maintenance parent's actual 0755 contract before
        # the guard opens it. The private process umask may otherwise create
        # this disposable ancestor as 0700; the incumbent owner's later chmod
        # then correctly trips its own held-custody check.
        m.bundle_path(SUCCESSOR).parent.chmod(0o755)
        return f
    monkeypatch.setattr(joined, "_preflight_fixture", installed_fixture)
    joined.test_joined_chain_from_preflight_to_future_carry(tmp_path, monkeypatch, logical)

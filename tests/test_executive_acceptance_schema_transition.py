"""Synthetic databases only; never inspect an installed runtime or launch a service."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from control_plane import executive_backup as backup
from ops.executive_os import acceptance_maintenance as maintenance
from test_executive_upgrade_v6 import _exact_v5
from test_executive_backup import _upgrade_test_release_and_census


@pytest.fixture
def migrated(tmp_path, monkeypatch):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v5(tmp_path / "runtime" / "executive.sqlite3")
    before = maintenance.snapshot(database)
    receipt = backup.upgrade_v5_to_v6(database, tmp_path / "backups", release_sha=release)
    return database, before, maintenance.snapshot(database), receipt


def test_ordinary_maintenance_keeps_schema_equality(migrated):
    _db, before, after, _receipt = migrated
    with pytest.raises(maintenance.MaintenanceError, match="schema"):
        maintenance.verify_preserved(before, after, {"schema_version": maintenance.SCHEMA_V2}, [])


def test_completed_exact_m6_has_an_explicit_history_validator(migrated):
    database, before, after, receipt = migrated
    # RED against the original owner: it has no migration-aware maintenance path.
    # The positive control above demonstrates why bypassing ordinary equality is wrong.
    module = "ops.executive_os.acceptance_schema_transition"
    assert importlib.util.find_spec(module) is not None, "missing explicit 5-to-6 maintenance transition"
    transition = importlib.import_module(module)
    transition.verify_history(before, after)
    assert backup.verify_backup(database, expected_schema_version=6)
    assert json.loads(Path(receipt.completion_receipt_path).read_text())["full_v4_content_equal"] is True


def _material(migrated):
    from ops.executive_os import acceptance_schema_transition as t
    _db, before, after, receipt = migrated
    pre = json.loads(Path(receipt.preflight_receipt_path).read_text())
    done = json.loads(Path(receipt.completion_receipt_path).read_text())
    source = t._proof(Path(receipt.v5_backup_path), 5, Path(receipt.v5_backup_manifest_path))
    target = t._proof(Path(receipt.v6_backup_path), 6, Path(receipt.v6_backup_manifest_path))
    intent = dict(successor_sha=receipt.release_sha, database=pre["database"], proof=source,
                  sealed_at=(datetime.fromisoformat(pre["created_at"])-timedelta(seconds=1)).isoformat())
    return t, intent, before, after, pre, done, source, target


def test_real_upgrade_receipts_are_consumable(migrated):
    t, intent, before, after, pre, done, source, target = _material(migrated)
    t.verify_receipts(intent, before, after, pre, done, source, target, pre["operation_id"])


@pytest.mark.parametrize("fault", [
    "partial", "foreign-operation", "foreign-release", "wrong-version", "false-version",
    "no-preflight-link", "foreign-namespace", "replaced-inode", "replayed-time",
    "release-tree", "release-manifest", "census", "schema", "migration-vector",
    "old-m5-digest", "history-digest", "legacy-digest", "false-equality",
])
def test_receipt_chain_rejects_missing_foreign_partial_replayed_or_false_proof(migrated, fault):
    t, intent, before, after, pre, done, source, target = _material(migrated)
    if fault == "partial":
        done.pop("v6_backup")
    elif fault == "foreign-operation":
        done["operation_id"] = "f"*32
    elif fault == "foreign-release":
        done["release_sha"] = "f"*40
    elif fault in {"wrong-version", "false-version"}:
        done["source_schema_version"] = 4 if fault == "wrong-version" else True
    elif fault == "no-preflight-link":
        done["preflight_receipt_digest"] = "f"*64
    elif fault == "foreign-namespace":
        pre["database"]["path"] += ".foreign"
        # Break source binding too; the seal is independent of the mutable receipt.
        intent["database"] = {**pre["database"], "path": pre["database"]["path"].removesuffix(".foreign")}
        done["preflight_receipt_digest"] = backup._upgrade_digest(pre)
    elif fault == "replaced-inode":
        done["authoritative_v6_database"]["inode"] += 1
    elif fault == "replayed-time":
        intent["sealed_at"] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    elif fault == "release-tree":
        done["tool_release_tree_sha"] = "f"*40
    elif fault == "release-manifest":
        done["tool_release_manifest_sha256"] = "f"*64
    elif fault == "census":
        pre["quiesce_writer_census"]["processes"] = [{"unexpected": True}]
        done["preflight_receipt_digest"] = backup._upgrade_digest(pre)
    elif fault == "schema":
        done["authoritative_v6_schema_digest"] = "f"*64
    elif fault == "migration-vector":
        done["migration_vector"][0]["checksum"] = "f"*64
    elif fault == "old-m5-digest":
        done["post_v5_migration_receipt_digest"] = "f"*64
    elif fault == "history-digest":
        done["post_full_v4_content_digest"] = "f"*64
    elif fault == "legacy-digest":
        done["post_v4_legacy_content_digest"] = "f"*64
    else:
        done["full_v4_content_equal"] = False
    with pytest.raises(maintenance.MaintenanceError):
        t.verify_receipts(intent, before, after, pre, done, source, target, pre["operation_id"])


@pytest.mark.parametrize("table,field,value", [
    ("jobs", "objective", "changed"), ("jobs", "root_job_id", "foreign-root"),
    ("jobs", "constraints_json", '{"base_sha":"foreign"}'),
    ("attempts", "lease_owner", "foreign"), ("attempts", "lease_expires_at_ms", 999),
    ("attempts", "effective_grant_json", '{"grant":"broader"}'),
    ("attempts", "placement_snapshot_json", '{"placement":"foreign"}'),
    ("events", "payload_json", '{"changed":true}'),
    ("worker_quota_classes", "fence_counter", 99),
    ("schema_migrations", "applied_at_ms", 999),
])
def test_no_old_semantic_row_can_be_changed(migrated, table, field, value):
    t, intent, before, after, pre, done, source, target = _material(migrated)
    after = deepcopy(after)
    row = next((r for r in after["tables"][table] if table != "schema_migrations" or r["version"] == 1))
    row[field] = value
    with pytest.raises(maintenance.MaintenanceError, match="old"):
        t.verify_receipts(intent, before, after, pre, done, source, target, pre["operation_id"])


@pytest.fixture(params=["delete", "wal"])
def prepared(tmp_path, monkeypatch, request):
    from ops.executive_os import acceptance_schema_transition as t
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    system = tmp_path / "system"
    system.mkdir()
    monkeypatch.setattr(maintenance, "SYSTEM_ROOT", system)
    monkeypatch.setattr(maintenance, "_TRUSTED_UID", os.getuid())
    monkeypatch.setattr(maintenance, "_sealed_ancestors", lambda path: [])
    runtime = tmp_path / "runtime"
    state = runtime / "data/control_plane"
    state.mkdir(parents=True, mode=0o700)
    (state / backup.DEFAULT_SERVICE_LOCK_NAME).touch(mode=0o600)
    database = _exact_v5(state / "executive.sqlite3")
    if request.param == "wal":
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.close()
    config = dict(runtime_root=str(runtime), control_uid=os.getuid(), proof_base_sha="b"*40,
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    for name in ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        config[name] = str(path)
    canary = runtime.parent.parent / "canary-fixtures"
    canary.mkdir(mode=0o700, exist_ok=True)
    args = SimpleNamespace(predecessor_sha="b"*40, successor_sha=release, root_job_id="JOB-V4-ROOT",
                           carry_terminal_dispatch=True, recovery_job_id=None, recovery_attempt_id=None)
    # Host acceptance is a separate prerequisite, tested through its real carry
    # validators below. This fixture supplies only that already-accepted boundary;
    # all SQLite migration, backup, snapshot, sealing and receipt code is real.
    accepted = dict(root_job_id=args.root_job_id, root_identity_sha256="1"*64,
                    root_event_id=1, root_event_sha256="2"*64)
    monkeypatch.setattr(t, "accepted_source", lambda *_: accepted)
    source = t.seal_source(args, config)
    receipt = backup.upgrade_v5_to_v6(database, Path(config["backup_root"]), release_sha=release)
    pre = json.loads(Path(receipt.preflight_receipt_path).read_text())
    done = json.loads(Path(receipt.completion_receipt_path).read_text())
    args.schema_transition_operation = pre["operation_id"]
    args.migration_preflight_sha256 = backup._upgrade_digest(pre)
    args.migration_completion_sha256 = backup._upgrade_digest(done)
    config["proof_base_sha"] = release
    return t, args, config, database, source, receipt


def test_seal_consume_separate_baseline_and_refuse_replay(prepared):
    t, args, config, database, source, receipt = prepared
    before_bytes = (source / "baseline.json").read_bytes()
    chain = t.consume(args, config)
    baseline = maintenance.snapshot(database)
    descriptor = dict(schema_transition_sha256=maintenance.digest(chain), successor_sha=args.successor_sha,
                      predecessor_sha=args.predecessor_sha, root_job_id=args.root_job_id)
    t.validate_sealed(descriptor, baseline, config)
    assert chain["target_baseline_sha256"] == maintenance.digest(baseline)
    assert (source / "baseline.json").read_bytes() == before_bytes
    assert not (maintenance.bundle_path(args.successor_sha) / "carry-forward.json").exists()
    assert not (maintenance.bundle_path(args.successor_sha) / "run-started.json").exists()
    with pytest.raises((FileExistsError, maintenance.MaintenanceError)):
        t.consume(args, config)
    with pytest.raises(maintenance.MaintenanceError, match="already started|sidecar"):
        t.seal_source(args, {**config, "proof_base_sha":args.predecessor_sha})


@pytest.mark.parametrize("fault", ["missing", "partial", "foreign-operation", "wrong-backup", "drill", "schema",
                                  "root", "config", "namespace", "old-row", "quarantine"])
def test_consumption_fails_closed_and_preserves_source_and_quarantine(prepared, fault):
    t, args, config, database, source, receipt = prepared
    source_bytes = (source / "prestate.sqlite3").read_bytes()
    completed = Path(receipt.completion_receipt_path)
    done = json.loads(completed.read_text())
    if fault == "missing":
        completed.unlink()
    elif fault == "partial":
        completed.write_text("{}")
    elif fault == "foreign-operation":
        args.schema_transition_operation = "f"*32
    elif fault == "wrong-backup":
        Path(receipt.v6_backup_path).write_bytes(b"bad sqlite")
    elif fault == "drill":
        done["v6_backup"]["restore_drill_digest"] = "f"*64
        completed.write_text(json.dumps(done))
        args.migration_completion_sha256 = backup._upgrade_digest(done)
    elif fault == "schema":
        with sqlite3.connect(Path(receipt.v6_backup_path)) as conn:
            conn.execute("CREATE TABLE unexpected(x)")
    elif fault == "root":
        args.root_job_id = "FOREIGN"
    elif fault == "config":
        config["control_uid"] += 1
    elif fault == "namespace":
        config["runtime_root"] += "-foreign"
    elif fault == "old-row":
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE workers SET last_seen_at_ms=99")
    else:
        (database.parent / backup._UPGRADE_BARRIER_NAME).write_text("unresolved")
    with pytest.raises((maintenance.MaintenanceError, OSError, backup.ExecutiveBackupError)):
        t.consume(args, config)
    assert (source / "prestate.sqlite3").read_bytes() == source_bytes
    assert not (maintenance.bundle_path(args.successor_sha) / "descriptor.json").exists()
    if fault == "quarantine":
        assert (database.parent / backup._UPGRADE_BARRIER_NAME).read_text() == "unresolved"


def test_accepted_source_never_invents_predecessor_pass(monkeypatch):
    from ops.executive_os import acceptance_schema_transition as t
    def refused(*args):
        raise maintenance.MaintenanceError("preserved root has no matching maintenance PASS receipt")
    monkeypatch.setattr(maintenance, "prior_carry_material", refused)
    with pytest.raises(maintenance.MaintenanceError, match="PASS"):
        t.accepted_source("b"*40, "root", {})


def test_ordinary_terminal_preparation_cannot_skip_schema_transition(migrated, monkeypatch):
    _db, before, after, _receipt = migrated
    monkeypatch.setattr(maintenance, "descriptor_for", lambda sha: {"baseline_sha256":maintenance.digest(before)})
    monkeypatch.setattr(maintenance, "sealed_json", lambda path: before)
    assert hasattr(maintenance, "require_unchanged_schema"), "ordinary preparation needs an explicit migration fence"
    maintenance.require_unchanged_schema("b"*40, before)
    with pytest.raises(maintenance.MaintenanceError, match="explicit"):
        maintenance.require_unchanged_schema("b"*40, after)


def test_v3_acceptance_keeps_v2_proof_and_no_predecessor_recovery(monkeypatch):
    from tests.test_executive_acceptance_maintenance_v2 import _preserved_proof_delta
    before, after, descriptor = _preserved_proof_delta()
    descriptor["schema_version"] = maintenance.SCHEMA_V3
    validated = []
    monkeypatch.setattr(maintenance, "_validate_recovery_event", lambda e, j, a, d: validated.append((j, a)))
    maintenance.verify_preserved(before, after, descriptor, ["JOB-new1", "JOB-new2"])
    assert validated == [("JOB-new2", "ATT-lost")]
    owner = object.__new__(maintenance.Maintenance)
    owner.descriptor = descriptor
    assert owner.predecessor_recovery_required is False
    after["schema"].append(["table", "extra", "extra", "CREATE TABLE extra(x)"])
    with pytest.raises(maintenance.MaintenanceError, match="schema"):
        maintenance.verify_preserved(before, after, descriptor, ["JOB-new1", "JOB-new2"])


@pytest.mark.parametrize("fault", [None, "missing-pass", "foreign-root", "old-row", "baseline-digest"])
def test_source_uses_real_predecessor_carry_and_preservation_validators(monkeypatch, fault):
    from ops.executive_os import acceptance_schema_transition as t
    from tests.test_executive_acceptance_maintenance_v2 import _chain, _preserved_proof_delta
    descriptors, receipts, summaries = _chain(monkeypatch)
    baseline, accepted, proof_descriptor = _preserved_proof_delta()
    prior = descriptors["c"*40]
    prior.update(proof_descriptor, baseline_sha256=maintenance.digest(baseline), backup_sha256="8"*64)
    summary = summaries["c"*40][0]
    summary.update(success_job_id="JOB-new1", interrupted_requeued_job_id="JOB-new2")
    receipts["c"*40]["descriptor_sha256"] = maintenance.digest(prior)
    read_receipt = maintenance.sealed_json
    monkeypatch.setattr(maintenance, "sealed_json", lambda path:
                        baseline if path.name == "baseline.json" else read_receipt(path))
    monkeypatch.setattr(maintenance, "_file_digest", lambda path: "8"*64)
    monkeypatch.setattr(maintenance, "snapshot", lambda path, **kwargs: baseline)
    monkeypatch.setattr(maintenance, "_validate_recovery_event", lambda *args: None)
    root = prior["root_job_id"]
    if fault == "missing-pass":
        receipts["c"*40]["passed"] = False
    elif fault == "foreign-root":
        root = "other"
    elif fault == "old-row":
        accepted["tables"]["untouched"][0]["value"] = "changed"
    elif fault == "baseline-digest":
        baseline["schema"].append("changed")
    if fault is None:
        result = t.accepted_source("c"*40, root, accepted)
        assert result["root_job_id"] == root and result["frozen_base_sha"] == "a"*40
    else:
        with pytest.raises(maintenance.MaintenanceError):
            t.accepted_source("c"*40, root, accepted)


def test_closed_v3_descriptor_requires_chain_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "SYSTEM_ROOT", tmp_path)
    monkeypatch.setattr(maintenance, "_TRUSTED_UID", os.getuid())
    monkeypatch.setattr(maintenance, "_sealed_ancestors", lambda path: [])
    keys = maintenance._DESCRIPTOR_V3_KEYS
    value = {key: "f"*64 for key in keys}
    for key in keys:
        if key.endswith(("_job_id", "_attempt_id")) or key in {"worker_id", "quota_class"}:
            value[key] = "fixture-" + key
        if key.endswith("_event_id"):
            value[key] = 1
    value.update(schema_version=maintenance.SCHEMA_V3, predecessor_sha="b"*40,
                 successor_sha="c"*40, frozen_base_sha="a"*40)
    path = maintenance.bundle_path("c"*40)/"descriptor.json"
    path.parent.mkdir(parents=True)
    maintenance.write_sealed(path, value, public=True)
    assert maintenance.descriptor_for("c"*40) == value
    path.chmod(0o600)
    del value["schema_transition_sha256"]
    path.write_text(json.dumps(value))
    path.chmod(0o444)
    with pytest.raises(maintenance.MaintenanceError, match="schema"):
        maintenance.descriptor_for("c"*40)


@pytest.mark.parametrize("fault", ["old-baseline", "target-baseline", "completion", "backup", "config-release", "quarantine"])
def test_acceptance_entry_revalidates_sealed_chain(prepared, fault):
    t, args, config, database, source, receipt = prepared
    chain = t.consume(args, config)
    baseline = maintenance.snapshot(database)
    descriptor = dict(schema_transition_sha256=maintenance.digest(chain), successor_sha=args.successor_sha,
                      predecessor_sha=args.predecessor_sha, root_job_id=args.root_job_id)
    if fault == "old-baseline":
        path = source / "baseline.json"
        path.chmod(0o600)
        path.write_text("{}")
        path.chmod(0o400)
    elif fault == "target-baseline":
        baseline["tables"]["jobs"][0]["objective"] = "different"
    elif fault == "completion":
        path = source / "completion/completion.json"
        path.chmod(0o600)
        done = json.loads(path.read_text())
        done["operation_id"] = "f"*32
        path.write_text(json.dumps(done))
        path.chmod(0o400)
    elif fault == "backup":
        path = source / "completion/v6" / Path(receipt.v6_backup_path).name
        path.chmod(0o600)
        path.write_bytes(b"replaced")
        path.chmod(0o400)
    elif fault == "config-release":
        config["proof_base_sha"] = args.predecessor_sha
    else:
        (database.parent/backup._UPGRADE_BARRIER_NAME).write_text("uncertain")
    with pytest.raises(maintenance.MaintenanceError):
        t.validate_sealed(descriptor, baseline, config)
    assert not (maintenance.bundle_path(args.successor_sha)/"carry-forward.json").exists()


def test_backup_owner_exact_schema_is_required_even_with_parseable_sqlite(migrated):
    from ops.executive_os import acceptance_schema_transition as t
    database, _before, _after, _receipt = migrated
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE unexpected(x)")
    with pytest.raises(backup.BackupVerificationError, match="schema"):
        t._proof(database, 6)


def test_receipt_hashes_use_existing_owner_unicode_canonicalization(tmp_path, monkeypatch):
    root = tmp_path / "répertoire"
    root.mkdir()
    release = _upgrade_test_release_and_census(monkeypatch, root)
    database = _exact_v5(root / "runtime/executive.sqlite3")
    before = maintenance.snapshot(database)
    receipt = backup.upgrade_v5_to_v6(database, root / "backups", release_sha=release)
    t, intent, before, after, pre, done, source, target = _material(
        (database, before, maintenance.snapshot(database), receipt))
    t.verify_receipts(intent, before, after, pre, done, source, target, pre["operation_id"])

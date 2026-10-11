"""Closed, offline maintenance evidence for the existing owner's exact 5 -> 6.

No migration, Runtime construction, service control, marker removal or PASS
publication occurs here. Copies are root-owned evidence, never restore inputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from control_plane import executive_backup as backup
from ops.executive_os import acceptance_maintenance as m

SOURCE_SCHEMA = "mastermind.executive_maintenance_schema_source/v1"
CHAIN_SCHEMA = "mastermind.executive_maintenance_schema_5_to_6/v1"
_PREFLIGHT_KEYS = set("schema_version operation_id source_schema_version target_schema_version database migration_vector normalized_schema_digest full_v4_content_digest v5_migration_receipt_digest barrier_identity v5_backup quiesce_writer_census quiesce_writer_census_digest tool_release_root tool_release_tree_sha tool_release_manifest_sha256 release_sha created_at".split())
_COMPLETION_KEYS = set("schema_version operation_id source_schema_version target_schema_version preflight_receipt_digest authoritative_v6_database authoritative_v6_schema_digest migration_vector pre_full_v4_content_digest post_full_v4_content_digest pre_v5_migration_receipt_digest post_v5_migration_receipt_digest full_v4_content_equal pre_v4_legacy_content_digest post_v4_legacy_content_digest legacy_content_equal v6_backup quiesce_writer_census_digest tool_release_root tool_release_tree_sha tool_release_manifest_sha256 release_sha completed_at".split())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise m.MaintenanceError("schema maintenance: " + message)


def source_bundle(successor: str) -> Path:
    return m.bundle_path(successor).with_name("schema-source-" + successor)


def database_for(config: dict) -> Path:
    return Path(config["runtime_root"]) / "data/control_plane/executive.sqlite3"


def config_digest(config: dict) -> str:
    # Only the explicit release promotion may differ. Namespace, principals,
    # paths, arms, grants and all other configuration remain bound exactly.
    return m.digest({k: v for k, v in config.items() if k != "proof_base_sha"})


def _absent(path: Path) -> bool:
    return not os.path.lexists(path)


def _offline(database: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        _require(_absent(Path(str(database) + suffix)), "SQLite sidecar remains")
    _no_owner_marker(database)


def _no_owner_marker(database: Path) -> None:
    for name in (backup._UPGRADE_BARRIER_NAME, backup.DEFAULT_SERVICE_MARKER_NAME):
        _require(_absent(database.parent / name), "owner quarantine/service marker remains")


def _snapshot(database: Path) -> dict:
    return m.snapshot(database, immutable=True)


def _copy(source: Path, destination: Path, uid: int) -> dict:
    """Capture stable private bytes under the maintenance principal, without chown."""
    _require(source.is_absolute() and source.resolve(strict=True) == source,
             "noncanonical private artifact")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                 and info.st_uid == uid and not info.st_mode & 0o077
                 and not m.has_macos_acl(source), "private artifact ownership/mode")
        out = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        h = hashlib.sha256()
        try:
            with os.fdopen(os.dup(fd), "rb") as stream, os.fdopen(os.dup(out), "wb") as target:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
                    target.write(chunk)
                target.flush()
            os.fchmod(out, 0o400)
            os.fsync(out)
        finally:
            os.close(out)
        _require(m._identity(info) == m._identity(os.fstat(fd)) == m._identity(source.lstat())
                 and source.resolve(strict=True) == source, "artifact changed during capture")
        parent = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return dict(path=str(source), device=info.st_dev, inode=info.st_ino,
                    size=info.st_size, sha256=h.hexdigest())
    finally:
        os.close(fd)


def _proof(path: Path, version: int, manifest: Path | None = None) -> dict:
    # Existing backup owner owns schema/checksum semantics. Root verifies its
    # own stable copy; control-owned originals retain their original ownership.
    _offline(path)
    verified = backup.verify_backup(path, manifest, expected_schema_version=version)
    drill = backup.verify_restore_drill(path, manifest, expected_schema_version=version)
    with backup._readonly_database(path) as connection:
        full = backup.full_v4_content_digest(connection)
        migration5 = backup._v5_migration_receipt_digest(connection)
    _offline(path)
    return dict(sha256=verified.database_sha256,
                migration_vector=[row.to_dict() for row in verified.migrations],
                normalized_schema_digest=verified.normalized_schema_digest,
                legacy_content_digest=verified.legacy_content_digest,
                full_v4_content_digest=full, v5_migration_receipt_digest=migration5,
                restore_drill_receipt=drill.to_dict())


def verify_history(before: dict, after: dict) -> None:
    """After exact schema verification, allow only the one appended M6 receipt."""
    bt, at = before["tables"], after["tables"]
    _require(set(bt) == set(at), "table set changed")
    for name in bt:
        if name != "schema_migrations":
            _require(m.digest(bt[name]) == m.digest(at[name]), "old rows changed: " + name)
    old, new = bt["schema_migrations"], at["schema_migrations"]
    _require(sorted(row["version"] for row in old) == [1, 2, 3, 4, 5]
             and sorted(row["version"] for row in new) == [1, 2, 3, 4, 5, 6],
             "not the exact 5-to-6 history delta")
    _require(m.digest(old) == m.digest([row for row in new if row["version"] != 6]),
             "old migration receipts changed")


def accepted_source(predecessor: str, root_id: str, before: dict) -> dict:
    prior, summary, material = m.prior_carry_material(predecessor)
    _require(prior["schema_version"] == m.SCHEMA_V2 and prior["root_job_id"] == root_id,
             "requires the actually accepted v2 predecessor/root")
    bundle = m.bundle_path(predecessor)
    baseline = m.sealed_json(bundle / "baseline.json")
    _require(m.digest(baseline) == prior["baseline_sha256"]
             and m._file_digest(bundle / "prestate.sqlite3") == prior["backup_sha256"]
             and m.digest(_snapshot(bundle / "prestate.sqlite3")) == m.digest(baseline),
             "accepted predecessor baseline changed")
    m.verify_preserved(baseline, before, prior,
                       [summary["success_job_id"], summary["interrupted_requeued_job_id"]])
    return dict(material, root_job_id=root_id, root_identity_sha256=prior["root_identity_sha256"],
                root_event_id=prior["root_event_id"], root_event_sha256=prior["root_event_sha256"])


def _artifacts(config: dict) -> dict:
    roots = [Path(config[k]) for k in
             ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root")]
    roots.append(Path(config["runtime_root"]).parent.parent / "canary-fixtures")
    return m.inventory(roots)


def seal_source(args, config: dict) -> Path:
    """Run before migration, with the existing accepted predecessor still selected."""
    _require(args.carry_terminal_dispatch and not args.recovery_job_id and not args.recovery_attempt_id,
             "schema transition requires terminal carry and grants no recovery")
    _require(config["proof_base_sha"] == args.predecessor_sha, "predecessor is not selected")
    _require(args.predecessor_sha != args.successor_sha, "release pair must differ")
    database = database_for(config)
    _offline(database)
    for name in (backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME, backup._UPGRADE_V5_TO_V6_COMPLETION_NAME):
        _require(_absent(database.parent / name), "migration already started; no retrospective baseline")
    before = _snapshot(database)
    accepted = accepted_source(args.predecessor_sha, args.root_job_id, before)
    _require(all(row["status"] in m._TERMINAL for row in before["tables"]["attempts"])
             and all(row["held_attempt_id"] is None for row in before["tables"]["worker_quota_classes"]),
             "runtime is not quiescent")
    parent = m.bundle_path(args.successor_sha).parent
    parent.mkdir(mode=0o755, exist_ok=True)
    m._sealed_ancestors(parent / "unused")
    _require(_absent(m.bundle_path(args.successor_sha)), "successor descriptor already exists")
    bundle = source_bundle(args.successor_sha)
    bundle.mkdir(mode=0o700)  # O_EXCL namespace; partial preparation is retained.
    identity = _copy(database, bundle / "prestate.sqlite3", config["control_uid"])
    proof = _proof(bundle / "prestate.sqlite3", 5)
    _require(m.digest(_snapshot(bundle / "prestate.sqlite3")) == m.digest(before)
             and m.digest(_snapshot(database)) == m.digest(before), "source changed during sealing")
    artifacts = _artifacts(config)
    m.write_sealed(bundle / "baseline.json", before)
    m.write_sealed(bundle / "inventory.json", artifacts)
    intent = dict(schema_version=SOURCE_SCHEMA, predecessor_sha=args.predecessor_sha,
                  successor_sha=args.successor_sha, accepted=accepted,
                  config_sha256=config_digest(config), database=identity,
                  baseline_sha256=m.digest(before), proof=proof,
                  inventory_sha256=m.digest(artifacts),
                  sealed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    m.write_sealed(bundle / "intent.json", intent)
    _offline(database)
    return bundle


def _load_source(successor: str) -> tuple[dict, dict]:
    bundle = source_bundle(successor)
    intent = m.sealed_json(bundle / "intent.json")
    before = m.sealed_json(bundle / "baseline.json")
    _require(intent["schema_version"] == SOURCE_SCHEMA and intent["successor_sha"] == successor
             and m.digest(before) == intent["baseline_sha256"]
             and m.digest(_snapshot(bundle / "prestate.sqlite3")) == m.digest(before)
             and m.digest(_proof(bundle / "prestate.sqlite3", 5)) == m.digest(intent["proof"]),
             "sealed v5 baseline changed")
    return intent, before


def _backup_copy(item: dict, directory: Path, uid: int, version: int) -> tuple[dict, dict]:
    _require(set(item) == set("database_path database_sha256 manifest_path manifest_sha256 restore_drill_receipt restore_drill_digest full_v4_content_digest".split()),
             "backup receipt shape")
    directory.mkdir(mode=0o700)
    db, manifest = Path(item["database_path"]), Path(item["manifest_path"])
    local_db, local_manifest = directory / db.name, directory / manifest.name
    _offline(db)
    db_id = _copy(db, local_db, uid)
    manifest_id = _copy(manifest, local_manifest, uid)
    _offline(db)
    _require(db_id["sha256"] == item["database_sha256"]
             and manifest_id["sha256"] == item["manifest_sha256"], "backup bytes/manifest differ")
    proof = _proof(local_db, version, local_manifest)
    _require(backup._upgrade_digest(proof["restore_drill_receipt"]) == backup._upgrade_digest(item["restore_drill_receipt"])
             == item["restore_drill_digest"]
             and proof["full_v4_content_digest"] == item["full_v4_content_digest"],
             "backup/drill proof differs")
    return proof, _snapshot(local_db)


def verify_receipts(intent: dict, before: dict, after: dict, pre: dict, done: dict,
                    source_proof: dict, target_proof: dict, operation: str) -> None:
    """Closed receipt consumer; never trust a PASS/equality boolean alone."""
    _require(re.fullmatch(r"[0-9a-f]{32}", operation) is not None, "operation identity is invalid")
    _require(set(pre) == _PREFLIGHT_KEYS and set(done) == _COMPLETION_KEYS, "partial/unknown receipt fields")
    _require(pre["schema_version"] == backup.UPGRADE_PREFLIGHT_SCHEMA
             and done["schema_version"] == backup.UPGRADE_COMPLETION_SCHEMA, "receipt schema")
    for value in (pre, done):
        _require(value["operation_id"] == operation and type(value["source_schema_version"]) is int
                 and value["source_schema_version"] == 5 and type(value["target_schema_version"]) is int
                 and value["target_schema_version"] == 6
                 and value["release_sha"] == intent["successor_sha"], "foreign operation/release/version")
    _require(done["preflight_receipt_digest"] == backup._upgrade_digest(pre), "completion does not bind preflight")
    _require(pre["database"] == intent["database"], "source database namespace/identity changed")
    _require(all(done["authoritative_v6_database"][key] == pre["database"][key]
                 for key in ("path", "device", "inode")), "target database namespace/identity changed")
    _require(datetime.fromisoformat(intent["sealed_at"]) <= datetime.fromisoformat(pre["created_at"])
             <= datetime.fromisoformat(done["completed_at"]), "replayed/out-of-order completion")
    _require(all(pre[key] == done[key] for key in
                 ("tool_release_root", "tool_release_tree_sha", "tool_release_manifest_sha256",
                  "quiesce_writer_census_digest"))
             and Path(pre["tool_release_root"]).name == intent["successor_sha"]
             and m._SHA.fullmatch(pre["tool_release_tree_sha"]) is not None
             and m._DIGEST.fullmatch(pre["tool_release_manifest_sha256"]) is not None
             and backup._upgrade_digest(pre["quiesce_writer_census"]) == pre["quiesce_writer_census_digest"],
             "release/quiescence chain differs")
    for receipt, proof, vector, schema in (
        (pre, source_proof, "migration_vector", "normalized_schema_digest"),
        (done, target_proof, "migration_vector", "authoritative_v6_schema_digest"),
    ):
        _require(receipt[vector] == proof["migration_vector"]
                 and receipt[schema] == proof["normalized_schema_digest"], "schema/history proof differs")
    for field in ("full_v4_content_digest", "v5_migration_receipt_digest"):
        _require(intent["proof"][field] == source_proof[field] == target_proof[field]
                 == pre[field] == done["pre_" + field] == done["post_" + field], "retained history proof differs")
    _require(done["full_v4_content_equal"] is True and done["legacy_content_equal"] is True
             and intent["proof"]["legacy_content_digest"] == source_proof["legacy_content_digest"]
             == target_proof["legacy_content_digest"] == done["pre_v4_legacy_content_digest"]
             == done["post_v4_legacy_content_digest"], "retained legacy proof differs")
    verify_history(before, after)


def consume(args, config: dict) -> dict:
    """Seal completion once, then let ordinary maintenance prepare the v6 baseline."""
    intent, before = _load_source(args.successor_sha)
    _require(intent["predecessor_sha"] == args.predecessor_sha
             and intent["accepted"]["root_job_id"] == args.root_job_id
             and config_digest(config) == intent["config_sha256"]
             and config["proof_base_sha"] == args.successor_sha, "release/config/root binding changed")
    _require(accepted_source(args.predecessor_sha, args.root_job_id, before) == intent["accepted"],
             "predecessor PASS chain changed")
    database = database_for(config)
    _offline(database)
    bundle = source_bundle(args.successor_sha)
    inventory = m.sealed_json(bundle / "inventory.json")
    _require(m.digest(inventory) == intent["inventory_sha256"], "source inventory digest changed")
    m.verify_inventory(inventory)
    completion_bundle = bundle / "completion"
    completion_bundle.mkdir(mode=0o700)  # Partial/replayed consumption fails closed.
    uid = config["control_uid"]
    for name, original in (("preflight.json", backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME),
                           ("completion.json", backup._UPGRADE_V5_TO_V6_COMPLETION_NAME)):
        _copy(database.parent / original, completion_bundle / name, uid)
    pre = m.sealed_json(completion_bundle / "preflight.json")
    done = m.sealed_json(completion_bundle / "completion.json")
    _require(set(pre) == _PREFLIGHT_KEYS and set(done) == _COMPLETION_KEYS, "partial/unknown receipt fields")
    _require(backup._upgrade_digest(pre) == args.migration_preflight_sha256
             and backup._upgrade_digest(done) == args.migration_completion_sha256, "owner return digests differ")
    source_proof, source_snapshot = _backup_copy(pre["v5_backup"], completion_bundle / "v5", uid, 5)
    target_proof, target_snapshot = _backup_copy(done["v6_backup"], completion_bundle / "v6", uid, 6)
    _require(m.digest(source_snapshot) == m.digest(before), "source backup does not match sealed baseline")
    identity = _copy(database, completion_bundle / "target.sqlite3", uid)
    _require(identity == done["authoritative_v6_database"], "live target differs from completed operation")
    live_proof = _proof(completion_bundle / "target.sqlite3", 6)
    _require(m.digest(_snapshot(completion_bundle / "target.sqlite3")) == m.digest(target_snapshot)
             and all(live_proof[key] == target_proof[key] for key in
                     ("normalized_schema_digest", "migration_vector", "full_v4_content_digest",
                      "v5_migration_receipt_digest", "legacy_content_digest")), "target backup differs")
    verify_receipts(intent, before, target_snapshot, pre, done, source_proof, target_proof,
                    args.schema_transition_operation)
    _offline(database)
    chain = dict(schema_version=CHAIN_SCHEMA, source_intent_sha256=m.digest(intent),
                 operation_id=args.schema_transition_operation, preflight_sha256=backup._upgrade_digest(pre),
                 completion_sha256=backup._upgrade_digest(done), target_baseline_sha256=m.digest(target_snapshot))
    m.write_sealed(completion_bundle / "chain.json", chain)
    return chain


def validate_sealed(descriptor: dict, baseline: dict, config: dict) -> None:
    """Recheck the retained chain at acceptance entry; never replace its baseline."""
    intent, before = _load_source(descriptor["successor_sha"])
    bundle = source_bundle(descriptor["successor_sha"]) / "completion"
    chain = m.sealed_json(bundle / "chain.json")
    pre, done = m.sealed_json(bundle / "preflight.json"), m.sealed_json(bundle / "completion.json")
    _require(chain["schema_version"] == CHAIN_SCHEMA
             and m.digest(chain) == descriptor["schema_transition_sha256"]
             and chain["source_intent_sha256"] == m.digest(intent)
             and chain["preflight_sha256"] == backup._upgrade_digest(pre)
             and chain["completion_sha256"] == backup._upgrade_digest(done)
             and chain["target_baseline_sha256"] == m.digest(baseline)
             and config_digest(config) == intent["config_sha256"]
             and config["proof_base_sha"] == descriptor["successor_sha"]
             and descriptor["predecessor_sha"] == intent["predecessor_sha"]
             and descriptor["root_job_id"] == intent["accepted"]["root_job_id"], "sealed transition chain differs")
    proofs = []
    for version, receipt in ((5, pre), (6, done)):
        item = receipt[f"v{version}_backup"]
        db = bundle / f"v{version}" / Path(item["database_path"]).name
        manifest = bundle / f"v{version}" / Path(item["manifest_path"]).name
        _require(m._file_digest(db) == item["database_sha256"]
                 and m._file_digest(manifest) == item["manifest_sha256"], "retained backup changed")
        proof = _proof(db, version, manifest)
        _require(backup._upgrade_digest(proof["restore_drill_receipt"]) == item["restore_drill_digest"], "retained drill differs")
        _require(m.digest(_snapshot(db)) == m.digest(before if version == 5 else baseline),
                 "retained backup baseline differs")
        proofs.append(proof)
    verify_receipts(intent, before, baseline, pre, done, *proofs, chain["operation_id"])
    # Original Runtime/acceptance reads may materialize an empty WAL/SHM pair.
    # No raw live DB is copied here; normal acceptance checks its full logical
    # snapshot, while the owner markers still prohibit unresolved effects.
    _no_owner_marker(database_for(config))
    info = database_for(config).stat()
    _require(str(database_for(config)) == done["authoritative_v6_database"]["path"]
             and (info.st_dev, info.st_ino) == (done["authoritative_v6_database"]["device"],
                                             done["authoritative_v6_database"]["inode"]), "target namespace replaced")

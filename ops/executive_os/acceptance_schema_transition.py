"""Accepted-V2 source provenance, subordinate to Acceptance Maintenance.

This module seals only the exact pre-migration source and joins it to DATA
from schema_upgrade_evidence. Maintenance owns dispatch, admission, working
preparations, run markers and carry. No migration receipt is independently
opened here, and no migration, service, restore or recovery action is issued.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SOURCE_SCHEMA = "mastermind.executive_maintenance_accepted_v2_source/v1"
_SOURCE_NAMES = frozenset({
    "preparing.json", "intent.json", "baseline.json", "prestate.sqlite3",
    "inventory.json", "prior-secret-canary.json", "source-control.json",
})
_SOURCE_KEYS = frozenset({
    "schema_version", "source_schema_version", "target_schema_version",
    "predecessor_sha", "successor_sha", "root_job_id", "accepted",
    "database", "baseline_sha256", "backup_sha256", "inventory_sha256",
    "prior_canary_sha256", "control_config_sha256", "full_v5_content_digest",
    "sealed_at",
})
_ACCEPTED_KEYS = frozenset({
    "prior_descriptor_sha256", "prior_carry_sha256", "prior_summary_sha256",
    "frozen_base_sha", "root_job_id", "root_identity_sha256",
    "root_event_id", "root_event_sha256",
})
_DATABASE_KEYS = frozenset({"path", "device", "inode", "size", "sha256"})
_INSTANT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)"
)


def _require(m, condition: bool, message: str) -> None:
    if not condition:
        raise m.MaintenanceError("accepted V2 source: " + message)


def source_bundle(m, successor: str) -> Path:
    return m.bundle_path(successor).with_name("schema-source-" + successor)


def _instant(m, value: str) -> datetime:
    _require(m, isinstance(value, str) and _INSTANT.fullmatch(value) is not None,
             "timestamp is not the producer's timezone-aware UTC form")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise m.MaintenanceError("accepted V2 source: invalid timestamp") from exc
    _require(m, result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
             "timestamp is not UTC")
    return result


def _require_v5(m, baseline: dict) -> None:
    tables = baseline.get("tables")
    rows = tables.get("schema_migrations") if isinstance(tables, dict) else None
    _require(m, isinstance(baseline.get("schema"), list) and isinstance(rows, list)
             and len(rows) == 5 and all(isinstance(row, dict)
                 and type(row.get("version")) is int for row in rows)
             and sorted(row["version"] for row in rows) == [1, 2, 3, 4, 5],
             "source must retain exactly the original schema-5 history")


def _hold_accepted_chain(m, predecessor: str, successor: str, guard) -> None:
    from ops.executive_os.autonomy_control import RUNTIME_ROOT
    seen = {successor}
    selected = predecessor
    while True:
        _require(m, selected not in seen and len(seen) < m._MAX_CARRY_DEPTH,
                 "accepted ancestry is cyclic or too deep")
        seen.add(selected)
        guard.tree(m.bundle_path(selected))
        guard.file(m._runtime_owner_path(
            RUNTIME_ROOT/"control"/"acceptance"/selected/"acceptance-summary.json", guard))
        prior = m.descriptor_for(selected)
        _require(m, prior is not None, "accepted predecessor descriptor disappeared")
        guard.lineage(prior)
        if prior["schema_version"] == m.SCHEMA:
            break
        _require(m, prior["schema_version"] in m._TERMINAL_CARRY_SCHEMAS,
                 "accepted predecessor schema is unsupported")
        selected = prior["predecessor_sha"]
    guard.check()


def accepted_source(m, predecessor: str, successor: str, root_id: str,
                    before: dict, guard) -> dict:
    """Prove the accepted original baseline and its actual two-job proof delta."""
    _hold_accepted_chain(m, predecessor, successor, guard)
    prior, summary, material = m.prior_carry_material(
        predecessor, _seen=frozenset({successor}))
    _require(m, prior["schema_version"] == m.SCHEMA_V2
             and prior["root_job_id"] == root_id,
             "requires the actually accepted V2 predecessor and root")
    baseline = m.sealed_json(m.bundle_path(predecessor)/"baseline.json")
    _require_v5(m, baseline)
    _require_v5(m, before)
    _require(m, m.digest(baseline) == prior["baseline_sha256"]
             and m.digest(m.sealed_backup_snapshot(
                 m.bundle_path(predecessor)/"prestate.sqlite3", prior["backup_sha256"]))
                 == m.digest(baseline), "accepted predecessor baseline changed")
    proof_ids = [summary.get("success_job_id"), summary.get("interrupted_requeued_job_id")]
    _require(m, all(isinstance(job, str) and job for job in proof_ids)
             and len(set(proof_ids)) == 2, "accepted proof identities are invalid")
    m.verify_preserved(baseline, before, prior, proof_ids)
    guard.check()
    return dict(material, **{key: prior[key] for key in
        ("root_job_id", "root_identity_sha256", "root_event_id", "root_event_sha256")})


def artifact_roots(config: dict) -> list[Path]:
    roots = [Path(config[key]) for key in
             ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root")]
    roots.append(Path(config["runtime_root"]).parent.parent/"canary-fixtures")
    return roots


def _copy_held_database(m, source: Path, destination: Path, guard) -> dict:
    """Copy the already-qualified no-follow FD; preserve exact source bytes."""
    fd = guard._hold(source, directory=False, exact=True)
    info = os.fstat(fd)
    out = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    observed = hashlib.sha256()
    try:
        offset = 0
        while offset < info.st_size:
            block = os.pread(fd, min(1024 * 1024, info.st_size - offset), offset)
            _require(m, bool(block), "source copy was truncated")
            observed.update(block)
            view = memoryview(block)
            while view:
                written = os.write(out, view)
                _require(m, written > 0, "source copy failed")
                view = view[written:]
            offset += len(block)
        os.fchmod(out, 0o400)
        os.fsync(out)
    finally:
        os.close(out)
    guard.check()
    _require(m, m._file_digest(destination) == observed.hexdigest(), "source copy digest changed")
    return dict(path=os.fspath(source), device=info.st_dev, inode=info.st_ino,
                size=info.st_size, sha256=observed.hexdigest())


def _pre_migration_absences(m, database: Path, guard) -> None:
    from control_plane import executive_backup as backup
    for name in (backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,
                 backup._UPGRADE_V5_TO_V6_COMPLETION_NAME,
                 backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME,
                 backup._UPGRADE_V6_TO_V7_COMPLETION_NAME):
        _require(m, not os.path.lexists(database.parent/name),
                 "migration already started; no retrospective source seal")
        guard.absent(database.parent/name)


def _source_namespace(m, successor: str, guard) -> tuple[Path, Path]:
    parent = m.bundle_path(successor).parent
    parent.mkdir(mode=0o755, exist_ok=True)
    m._sealed_ancestors(parent/"unused")
    _require(m, not parent.is_symlink() and parent.stat().st_uid == m._TRUSTED_UID,
             "source parent is not Root-owned")
    final = source_bundle(m, successor)
    partial = parent/(".preparing-schema-source-" + successor)
    _require(m, not any(os.path.lexists(path) for path in
             (final, partial, m.bundle_path(successor))),
             "source/preparation already exists; reconcile the original operation")
    guard.absent(final)
    guard.absent(m.bundle_path(successor))
    partial.mkdir(mode=0o700)
    return partial, final


def seal_source(m, args, config_holder, lock, guard) -> Path:
    """Called only by Maintenance's explicit pre-migration source action."""
    from ops.executive_os.autonomy_control import RUNTIME_ROOT
    from control_plane import executive_backup as backup
    config = config_holder.value
    _require(m, config["proof_base_sha"] == args.predecessor_sha,
             "accepted predecessor is not the selected installed release")
    m._require_preparation_install(args.predecessor_sha)
    backup._prove_upgrade_release(args.successor_sha)
    database = m._quiescent_database(config, lock, guard)
    _pre_migration_absences(m, database, guard)
    guard.absent(m._runtime_owner_path(
        RUNTIME_ROOT/"control"/"acceptance"/args.successor_sha, guard))
    before = m.snapshot(database, immutable=True)
    accepted = accepted_source(m, args.predecessor_sha, args.successor_sha,
                               args.root_job_id, before, guard)
    tables = before["tables"]
    _require(m, all(row["status"] in m._TERMINAL for row in tables["attempts"])
             and all(row["held_attempt_id"] is None for row in tables["worker_quota_classes"]),
             "source runtime is not quiescent")
    roots = artifact_roots(config)
    artifacts = m.inventory(roots)
    canary_path = Path(config["secret_canary_receipt_path"])
    guard.file(canary_path)
    canary = json.loads(canary_path.read_text())
    # Validate the exact normal promotion now, before any source publication.
    # The two-argument producer keeps the original Macro coordinate unchanged.
    m._normal_installed_preparation_config(config_holder.raw, args.successor_sha)
    partial, final = _source_namespace(m, args.successor_sha, guard)
    m.write_sealed(partial/"preparing.json", {"schema_version": SOURCE_SCHEMA})
    identity = _copy_held_database(m, database, partial/"prestate.sqlite3", guard)
    _require(m, m.digest(m.snapshot(partial/"prestate.sqlite3", immutable=True))
             == m.digest(before), "source copy snapshot differs")
    runtime = m._verification_runtime(partial/"prestate.sqlite3")
    root = runtime.jobs.get_job(args.root_job_id)
    m._v5_to_v7_queued_root(runtime, root, before)
    m.terminal_carry_fields(runtime, root, config, before,
                            args.predecessor_sha, args.successor_sha)
    intent = dict(
        schema_version=SOURCE_SCHEMA, source_schema_version=5, target_schema_version=7,
        predecessor_sha=args.predecessor_sha, successor_sha=args.successor_sha,
        root_job_id=args.root_job_id, accepted=accepted, database=identity,
        baseline_sha256=m.digest(before), backup_sha256=identity["sha256"],
        inventory_sha256=m.digest(artifacts), prior_canary_sha256=m.digest(canary),
        control_config_sha256=hashlib.sha256(config_holder.raw).hexdigest(),
        full_v5_content_digest=m._full_v5_digest(partial/"prestate.sqlite3"),
        sealed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    m.write_sealed(partial/"baseline.json", before)
    m.write_sealed(partial/"inventory.json", artifacts)
    m.write_sealed(partial/"prior-secret-canary.json", canary)
    m.write_sealed_bytes(partial/"source-control.json", config_holder.raw)
    m.write_sealed(partial/"intent.json", intent)
    _require(m, {p.name for p in partial.iterdir()} == _SOURCE_NAMES,
             "source preparation namespace differs")
    _require(m, accepted_source(m, args.predecessor_sha, args.successor_sha,
                                args.root_job_id, before, guard) == accepted,
             "accepted predecessor changed before source publication")
    database = m._quiescent_database(config, lock, guard)
    _pre_migration_absences(m, database, guard)
    _require(m, m.digest(m.snapshot(database, immutable=True)) == m.digest(before)
             and m.inventory(roots) == artifacts
             and json.loads(canary_path.read_text()) == canary,
             "source state changed before publication")
    guard.tree(partial)
    m._fsync_maintenance_directory(partial)
    config_holder.check()
    lock.check()
    guard.check()
    os.rename(partial, final)
    m._fsync_maintenance_directory(final.parent)
    return final


class AcceptedSource:
    """Held immutable provenance; no receipt reader or runtime authority."""
    def __init__(self, m, successor: str, guard, *, expected_digest: str,
                 predecessor: str, root_id: str):
        self.m, self.guard = m, guard
        self.bundle = source_bundle(m, successor)
        guard.tree(self.bundle)
        _require(m, {p.name for p in self.bundle.iterdir()} == _SOURCE_NAMES,
                 "source seal namespace differs")
        self.intent = m.sealed_json(self.bundle/"intent.json")
        value = self.intent
        _require(m, set(value) == _SOURCE_KEYS and value["schema_version"] == SOURCE_SCHEMA
                 and type(value["source_schema_version"]) is int and value["source_schema_version"] == 5
                 and type(value["target_schema_version"]) is int and value["target_schema_version"] == 7
                 and value["predecessor_sha"] == predecessor and value["successor_sha"] == successor
                 and value["root_job_id"] == root_id and predecessor != successor
                 and isinstance(expected_digest, str) and m._DIGEST.fullmatch(expected_digest)
                 and m.digest(value) == expected_digest,
                 "source seal does not bind the requested accepted predecessor/successor")
        m.bundle_path(predecessor)
        for key in ("baseline_sha256", "backup_sha256", "inventory_sha256",
                    "prior_canary_sha256", "control_config_sha256", "full_v5_content_digest"):
            _require(m, isinstance(value[key], str) and m._DIGEST.fullmatch(value[key]),
                     "source digest is malformed")
        _require(m, isinstance(value["accepted"], dict) and set(value["accepted"]) == _ACCEPTED_KEYS,
                 "source accepted ancestry has an unknown shape")
        identity = value["database"]
        _require(m, isinstance(identity, dict) and set(identity) == _DATABASE_KEYS
                 and isinstance(identity["path"], str) and Path(identity["path"]).is_absolute()
                 and ".." not in Path(identity["path"]).parts
                 and all(type(identity[key]) is int and identity[key] > 0 for key in ("device", "inode", "size"))
                 and identity["sha256"] == value["backup_sha256"],
                 "source database identity is malformed")
        _instant(m, value["sealed_at"])
        _require(m, m.sealed_json(self.bundle/"preparing.json") == {"schema_version": SOURCE_SCHEMA},
                 "source preparation marker differs")
        self.before = m.sealed_json(self.bundle/"baseline.json")
        self.inventory = m.sealed_json(self.bundle/"inventory.json")
        self.canary = m.sealed_json(self.bundle/"prior-secret-canary.json")
        self.control_raw = m.sealed_bytes(self.bundle/"source-control.json", m._MAX_DOCUMENT_BYTES)
        self.control = json.loads(self.control_raw)
        _require(m, m.digest(self.before) == value["baseline_sha256"]
                 and m.digest(self.inventory) == value["inventory_sha256"]
                 and m.digest(self.canary) == value["prior_canary_sha256"]
                 and hashlib.sha256(self.control_raw).hexdigest() == value["control_config_sha256"]
                 and self.control["proof_base_sha"] == predecessor
                 and m.digest(m.sealed_backup_snapshot(
                     self.bundle/"prestate.sqlite3", value["backup_sha256"])) == m.digest(self.before)
                 and m._full_v5_digest(self.bundle/"prestate.sqlite3") == value["full_v5_content_digest"],
                 "source sealed data changed")
        _require(m, identity["path"] == os.fspath(m._runtime_owner_path(
            Path(self.control["runtime_root"])/"data/control_plane/executive.sqlite3", guard)),
            "source database is outside its fixed runtime")
        _require(m, accepted_source(m, predecessor, successor, root_id, self.before, guard)
                 == value["accepted"], "accepted predecessor PASS chain changed")
        # Parsing/whole-document validation belongs to the existing producer.
        self.promoted_control = m._normal_installed_preparation_config(self.control_raw, successor)
        self.check()

    def require_descriptor(self, descriptor: dict) -> None:
        m = self.m
        _require(m, descriptor.get("schema_version") == m.SCHEMA_ACCEPTED_V2_V5_TO_V7
                 and descriptor.get("accepted_source_sha256") == m.digest(self.intent)
                 and descriptor.get("source_control_config_sha256")
                 == hashlib.sha256(self.promoted_control).hexdigest()
                 and descriptor.get("prior_canary_sha256") == self.intent["prior_canary_sha256"]
                 and all(descriptor.get(key) == self.intent[key] for key in
                         ("predecessor_sha", "successor_sha", "root_job_id"))
                 and all(descriptor.get(key) == value for key, value in self.intent["accepted"].items()),
                 "descriptor does not retain its accepted source ancestry")
        self.check()

    def bind_evidence(self, evidence, *, phase: str, descriptor: dict | None = None) -> None:
        m = self.m
        owner = m._evidence_owner()
        material = m._json_data(evidence.material)
        _require(m, phase in {owner.EVIDENCE_PHASE_INITIAL, owner.EVIDENCE_PHASE_HISTORICAL}
                 and evidence.phase == phase
                 and material["schema_version"] == owner.MATERIAL_SCHEMA_VERSION
                 and material["phase"] == owner.EVIDENCE_PHASE_INITIAL
                 and m._v5_to_v7_tool_release(material) == self.intent["successor_sha"],
                 "requires the exact normal chain and its actual migration executor")
        _require(m, m.digest(m.snapshot(Path(evidence.source_v5_database), immutable=True))
                 == m.digest(self.before)
                 and evidence.source_v5_content_digest == self.intent["full_v5_content_digest"],
                 "P56 source is not the sealed post-acceptance source")
        _require(m, m.digest(evidence.source_v5_database_identity) == m.digest(self.intent["database"])
                 and material["chain"]["database_path"] == self.intent["database"]["path"],
                 "P56 authoritative source identity differs")
        _require(m, _instant(m, self.intent["sealed_at"])
                 <= _instant(m, evidence.source_v5_preflight_created_at),
                 "source seal postdates P56; no retrospective seal")
        if phase == owner.EVIDENCE_PHASE_HISTORICAL:
            _require(m, isinstance(descriptor, dict),
                     "historical evidence requires the actual working descriptor")
            self.require_descriptor(descriptor)
            # Reconstruct the original metadata; never enumerate today's live
            # artifact roots. Hold files, since finish adds its own receipts
            # to the working directory while this historical context is open.
            working = m.bundle_path(self.intent["successor_sha"])
            self.guard.file(working/"inventory.json")
            expected_inventory = m._v5_to_v7_working_inventory(
                self.inventory, evidence.inventory_additions, artifact_roots(self.control))
            _require(m, m.digest(expected_inventory) == descriptor["inventory_sha256"]
                     and m.digest(m.sealed_json(working/"inventory.json"))
                     == m.digest(expected_inventory),
                     "working inventory is not the original source plus migration additions")
            self.guard.file(working/"prior-secret-canary.json")
            _require(m, m.digest(m.sealed_json(working/"prior-secret-canary.json"))
                     == self.intent["prior_canary_sha256"],
                     "working canary is not the sealed source canary")
            _require(m, m.digest(m.snapshot(Path(evidence.target_v7_database), immutable=True))
                     == descriptor["baseline_sha256"],
                     "working baseline is not the original C67 target")
        evidence.check()
        self.check()

    def check(self) -> None:
        self.guard.check()


def open_source(m, successor: str, guard, *, expected_digest: str,
                predecessor: str, root_id: str) -> AcceptedSource:
    return AcceptedSource(m, successor, guard, expected_digest=expected_digest,
                          predecessor=predecessor, root_id=root_id)

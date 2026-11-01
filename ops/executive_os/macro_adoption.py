"""Finite, offline adoption of one independently qualified immutable Macro root.

This owner never stops services, edits Runtime, arms a sink, or schedules itself.
Its observation receipt is not admission. An uncertain mutation has no retry or
rollback verb: retain the original operation and use read-only status.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from types import MappingProxyType

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if __name__ == "__main__":
    # Enter the canonical package before defining any owner class or process
    # state. The observation publisher imports that SAME module identity.
    from ops.executive_os.macro_adoption import main as _canonical_main
    raise SystemExit(_canonical_main())

from ops.executive_os import autonomy_control as control
from ops.executive_os import acceptance_maintenance as maintenance
from ops.executive_os import prepare_control_successor as preparation
from control_plane.executive_control_observation import OBSERVATION_PATH

SCHEMA = "mastermind.executive_macro_adoption/v1"
RECEIPT_SCHEMA = "mastermind.executive_macro_adoption_observation/v1"
RECEIPT = control.CONFIG_ROOT / "macro-adoption-receipt-v1.json"
RECEIPTS = MappingProxyType({
    "ceo_submit": control.CEO_SUBMIT_RECEIPT,
    "autonomy": control.AUTONOMY_RECEIPT,
    "control_observation": Path(OBSERVATION_PATH),
    "adoption": RECEIPT,
})
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ACTIVE_OWNER = None
_MAX_BYTES = 128 * 1024
_PUBLIC_DIRECTORY_MODE = (stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)


class AdoptionError(RuntimeError):
    def __init__(self, code, *, effect_unknown=False):
        self.code = code
        self.effect_unknown = effect_unknown
        super().__init__(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def decoded(raw, *, maximum=_MAX_BYTES):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AdoptionError("duplicate_key")
            result[key] = value
        return result
    try:
        if len(raw) > maximum:
            raise AdoptionError("document_too_large")
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(AdoptionError("invalid_json")))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise AdoptionError("invalid_json") from exc


def _macro_path(value):
    parent = control.SYSTEM_ROOT / "macro-sources"
    if (type(value) is not str or Path(value).parent != parent
            or str(Path(value)) != value or not _SHA.fullmatch(Path(value).name)):
        raise AdoptionError("macro_root_invalid")
    return value


@dataclass(frozen=True)
class AdoptionRequest:
    expected_release_sha: str
    current_control_sha256: str
    current_worker_sha256: str
    expected_old_macro_root: str
    target_macro_root: str
    target_macro_sha: str
    target_generation_seal_sha256: str
    target_artifact_sha256: str
    expected_receipts: object

    def document(self):
        value = {name: getattr(self, name) for name in self.__dataclass_fields__}
        value["expected_receipts"] = dict(self.expected_receipts)
        return value


def parse_request(value):
    if type(value) is not dict or set(value) != set(AdoptionRequest.__dataclass_fields__):
        raise AdoptionError("request_fields_invalid")
    for key in ("expected_release_sha", "target_macro_sha"):
        if type(value[key]) is not str or not _SHA.fullmatch(value[key]):
            raise AdoptionError("request_sha_invalid")
    for key in ("current_control_sha256", "current_worker_sha256",
                "target_generation_seal_sha256", "target_artifact_sha256"):
        if type(value[key]) is not str or not _DIGEST.fullmatch(value[key]):
            raise AdoptionError("request_digest_invalid")
    old, new = (_macro_path(value[key]) for key in
                ("expected_old_macro_root", "target_macro_root"))
    if old == new or Path(new).name != value["target_macro_sha"]:
        raise AdoptionError("macro_transition_invalid")
    receipts = value["expected_receipts"]
    if type(receipts) is not dict or set(receipts) != set(RECEIPTS):
        raise AdoptionError("receipt_fields_invalid")
    if any(v is not None and (type(v) is not str or not _DIGEST.fullmatch(v))
           for v in receipts.values()):
        raise AdoptionError("receipt_digest_invalid")
    return AdoptionRequest(**dict(value, expected_receipts=MappingProxyType(dict(receipts))))


def _closed(control_value):
    maintenance.require_disarmed(control_value)
    company = control_value.get("company_consultation", {})
    if (type(company) is not dict or company.get("native_return_armed", False) is not False
            or control_value.get("coo_operator_model_alias") == "coo.operator.native-return"):
        raise AdoptionError("native_return_not_closed")
    # An inert historical Wake value is preserved. Normal full-disarm revokes
    # effective COO/native execution; requiring literal null would make ordinary
    # disarm unreachable for retained historical values.


def prepare_candidate(request, control_bytes):
    request = parse_request(request.document())
    if digest(control_bytes) != request.current_control_sha256:
        raise AdoptionError("control_preimage_mismatch")
    value = decoded(control_bytes)
    try:
        preparation._validate_document(value)
        _closed(value)
    except (preparation.PreparationError, maintenance.MaintenanceError) as exc:
        raise AdoptionError("control_not_closed_or_valid") from exc
    if (value["proof_base_sha"] != request.expected_release_sha
            or value["ceo_ingress_app_macro_root"] != request.expected_old_macro_root):
        raise AdoptionError("source_preimage_mismatch")
    candidate = dict(value, ceo_ingress_app_macro_root=request.target_macro_root)
    preparation._validate_document(candidate)
    if set(candidate) != set(value) or {k for k in value if candidate[k] != value[k]} != {"ceo_ingress_app_macro_root"}:
        raise AdoptionError("candidate_scope_invalid")
    return encoded(candidate)


def adopt(host, request):
    request = parse_request(request.document())
    effect = False
    try:
        with host.qualified(request) as held:
            held.recheck_preimage()
            effect = True  # before attempting the first modifying operation
            held.begin()
            held.recheck_before_replace()
            held.phase("CONFIG_RENAME_STARTED")
            held.replace_control()
            held.recheck_postimage()
            held.phase("OBSERVATION_PUBLICATION_STARTED")
            observed = held.publish_observation()
            held.phase("RECEIPT_PUBLICATION_STARTED")
            result = held.publish_receipt(observed)
            held.phase("COMPLETE")
            held.complete()
            return result
    except BaseException as exc:
        if effect:
            raise AdoptionError("adoption_effect_unknown", effect_unknown=True) from exc
        if isinstance(exc, AdoptionError):
            raise
        raise AdoptionError("adoption_preflight_refused") from exc


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _sealed_bytes(path, *, modes, gid=None):
    # Root's guarded read checks every sealed ancestor and brackets raw file
    # identity. Preserve the exact original guard; never rebase its snapshots.
    before = maintenance._sealed_ancestors(path)
    raw, info = control._read_root_file(path, modes=frozenset(modes), gid=gid)
    if (any(_identity(p.lstat()) != ident for p, ident in before)
            or _identity(path.lstat()) != _identity(info)):
        raise AdoptionError("file_changed")
    return raw, _identity(info)


def _rename_exclusive(source, destination):
    """Normal Darwin exclusive rename; no replacing an existing proof path."""
    if sys.platform != "darwin":
        raise AdoptionError("darwin_exclusive_publication_required")
    library = ctypes.CDLL(None, use_errno=True)
    operation = library.renameatx_np
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    if operation(-2, os.fsencode(source), -2, os.fsencode(destination), 4) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def _archive_generation(marker, archive, fd):
    """Close by one atomic namespace move, retaining EVERY original byte."""
    held = _identity(os.fstat(fd))[:5]
    if _identity(marker.lstat())[:5] != held or os.path.lexists(archive):
        raise AdoptionError("completed_archive_occupied_or_changed", effect_unknown=True)
    _rename_exclusive(marker, archive)
    control._fsync_directory(marker.parent)
    if os.path.lexists(marker) or _identity(archive.lstat())[:5] != held:
        raise AdoptionError("completed_archive_unknown", effect_unknown=True)


def _check_config_mutex(fd):
    info, named = os.fstat(fd), control.CONFIG_ROOT.lstat()
    if (_identity(info)[:5] != _identity(named)[:5] or info.st_uid != 0 or info.st_gid != 0
            or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != _PUBLIC_DIRECTORY_MODE
            or maintenance.has_macos_acl(control.CONFIG_ROOT, descriptor=fd, expected_identity=info)):
        raise AdoptionError("config_mutex_custody_invalid")


def _receipt_preimages():
    result = {}
    for key, path in RECEIPTS.items():
        try:
            result[key] = _sealed_bytes(path, modes={0o444} if key != "adoption" else {0o400}, gid=0)
        except control.HostControlError:
            if os.path.lexists(path):
                raise
            result[key] = None
    return result


def _check_source(expected):
    if type(expected) is not str or not _SHA.fullmatch(expected):
        raise AdoptionError("request_sha_invalid")
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise AdoptionError("root_darwin_required")
    root = control.SYSTEM_ROOT / "releases" / expected
    if Path(__file__).resolve(strict=True) != root / "ops/executive_os/macro_adoption.py":
        raise AdoptionError("installed_helper_required")
    host = control.ProductionArmHost()
    if host.require_exact_install(expected) != expected:
        raise AdoptionError("selected_release_mismatch")
    return host


def _require_current(generated_at, reference_at):
    from control_plane.autonomy_control_room_projection import (
        _freshness_for, Freshness, FRESHNESS_BUDGET, _parse_iso8601,
    )
    _, freshness = _freshness_for(generated_at, reference_at)
    if (freshness != Freshness.CURRENT
            or (_parse_iso8601(generated_at) + FRESHNESS_BUDGET - _parse_iso8601(reference_at)).total_seconds() <= 0):
        raise AdoptionError("target_artifact_not_current")


def _read_artifact_fd(fd, limit):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, size = [], 0
    while size <= limit:
        block = os.read(fd, min(65536, limit + 1 - size))
        if not block:
            return b"".join(chunks)
        chunks.append(block)
        size += len(block)
    raise AdoptionError("target_artifact_over_budget")


@contextmanager
def _held_macro_artifact(target):
    """Bind real immutable-target custody and bytes across generation proof.

    Root-owned 0755 directories are permitted under exclusive administrative
    custody; no unprivileged writer, ACL or symlink can redirect this target.
    This cannot exclude a deliberately noncooperating privileged Root writer.
    """
    from control_plane.workspace_source_join import INSTALLED_BYTE_BUDGET
    root = Path(_macro_path(target))
    artifact = root / "data/governance/agent_os_state.json"
    if root.resolve(strict=True) != root or artifact.resolve(strict=True) != artifact:
        raise AdoptionError("target_not_direct_canonical_root")
    ancestors = maintenance._sealed_ancestors(artifact)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_info = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != 0
                or root_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                or maintenance.has_macos_acl(root, descriptor=root_fd, expected_identity=root_info)):
            raise AdoptionError("target_root_custody_invalid")
        fd = os.open(artifact, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
                    or info.st_nlink != 1
                    or maintenance.has_macos_acl(artifact, descriptor=fd, expected_identity=info)):
                raise AdoptionError("target_artifact_custody_invalid")
            data = _read_artifact_fd(fd, INSTALLED_BYTE_BUDGET)

            def check():
                if (root.resolve(strict=True) != root or artifact.resolve(strict=True) != artifact
                        or _identity(root_info) != _identity(os.fstat(root_fd))
                        or _identity(root_info) != _identity(root.lstat())
                        or _identity(info) != _identity(os.fstat(fd))
                        or _identity(info) != _identity(artifact.lstat())
                        or any(_identity(parent.lstat()) != identity for parent, identity in ancestors)
                        or _read_artifact_fd(fd, INSTALLED_BYTE_BUDGET) != data):
                    raise AdoptionError("target_changed_during_generation_proof")
            check()
            yield data, check
            check()
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)


def _qualification_probe(target, expected, *, require_current=True):
    """Actual Control-UID read-only collector child; returns no private packet."""
    from integrations.executive_mcp import installed
    from scripts.executive_os_phase1c import load_control_config, _attest_app_boot_runtime
    from control_plane.workspace_source_join import INSTALLED_BYTE_BUDGET
    _macro_path(target)
    if type(expected) is not str or not _SHA.fullmatch(expected):
        raise AdoptionError("request_sha_invalid")
    identity = pwd.getpwnam(control.CONTROL_USER)
    if os.geteuid() != identity.pw_uid or sys.platform != "darwin":
        raise AdoptionError("collector_principal_required")
    root = control.SYSTEM_ROOT / "releases" / expected
    if Path(__file__).resolve(strict=True) != root / "ops/executive_os/macro_adoption.py":
        raise AdoptionError("installed_helper_required")
    raw = load_control_config(control.CONTROL_CONFIG)
    if raw["proof_base_sha"] != expected:
        raise AdoptionError("selected_release_mismatch")
    python = _attest_app_boot_runtime(Path(raw["ceo_ingress_app_boot_python"]))
    source = Path(raw["proof_source_repository"])
    collector = installed.InstalledBootPacketCollector(
        source_root=source, macro_root=Path(target), code_root=root,
        python_executable=python, expected_source_sha=expected)
    deadline = time.monotonic() + 28.0
    now = datetime.now(timezone.utc).isoformat()
    with _held_macro_artifact(target) as (data, check_target):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AdoptionError("collector_deadline_exceeded")
        collector(repo_root=source, macro_root_flag=target, now=now,
                  timeout=remaining)
        check_target()
        if deadline - time.monotonic() <= 0:
            raise AdoptionError("collector_deadline_exceeded")
        observed = collector._snapshot_pair(
            installed._installed_child_env(code_root=root, macro_root=Path(target)),
            deadline=deadline)
        check_target()
    value = decoded(data, maximum=INSTALLED_BYTE_BUDGET)
    stamp = value.get("generated_at")
    now = datetime.now(timezone.utc).isoformat()
    if require_current:
        _require_current(stamp, now)
    if observed[0] != expected or observed[1] != Path(target).name:
        raise AdoptionError("target_source_mismatch")
    return {"source_sha": observed[0], "macro_sha": observed[1],
            "macro_seal_sha256": observed[3], "artifact_sha256": digest(data),
            "generated_at": stamp, "observed_at": now}


class ProductionHost:
    @contextmanager
    def qualified(self, request):
        global _ACTIVE_OWNER
        authority = _check_source(request.expected_release_sha)
        if _ACTIVE_OWNER is not None:
            raise AdoptionError("owner_occupied")
        authority.require_services_already_stopped()
        authority.require_service_uids_quiescent()
        # Same config-directory inode mutex as all incumbent transaction owners.
        control.ProductionTransactionHost._config_root_safe()
        mutex = os.open(control.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _check_config_mutex(mutex)
            # Same incumbent config-inode mutex, bounded refusal rather than
            # waiting on a different creator's still-unpublished generation.
            fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with ExitStack() as stack:
                held = _HeldAdoption(request, authority, mutex, stack)
                held.initialize()
                _ACTIVE_OWNER = held
                try:
                    yield held
                finally:
                    _ACTIVE_OWNER = None
        finally:
            fcntl.flock(mutex, fcntl.LOCK_UN)
            os.close(mutex)


def _runtime_quiescent(db):
    """Read only known Runtime shapes; queued nonexecuting history is retained."""
    from control_plane.executive_runtime import JobStatus
    if ([row[0] for row in db.execute("PRAGMA quick_check")] != ["ok"]
            or list(db.execute("PRAGMA foreign_key_check"))):
        raise AdoptionError("runtime_integrity_failed")
    control.validate_runtime_attempt_statuses([row[0] for row in db.execute("SELECT status FROM attempts")])
    statuses = [row[0] for row in db.execute("SELECT status FROM jobs")]
    if any(status not in {state.value for state in JobStatus} for status in statuses):
        raise AdoptionError("runtime_job_status_unknown")
    if (any(status in {"RUNNING", "CHECKPOINTED", "CANCEL_REQUESTED"} for status in statuses)
            or db.execute("SELECT 1 FROM worker_quota_classes WHERE held_attempt_id IS NOT NULL LIMIT 1").fetchone()):
        raise AdoptionError("runtime_not_quiescent")


def _publish_prepared_generation(private, operation_id, files, candidate, candidate_gid, stack, check):
    """Private filesystem mechanism; only the held owner supplies its edge proof."""
    parent = control.CONFIG_ROOT
    # Never auto-delete or select an interrupted unselected stage.
    stage = Path(tempfile.mkdtemp(prefix=".macro-adoption-stage-" + operation_id + "-", dir=parent))
    os.chown(stage, 0, 0)
    fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stack.callback(os.close, fd)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name, raw in files.items():
        control._atomic_file(stage / name, raw, mode=0o400, uid=0, gid=0, replace=False)
    control._atomic_file(stage / "candidate-control.json", candidate,
                         mode=0o440, uid=0, gid=candidate_gid, replace=False)
    control._fsync_directory(stage)
    check()
    if os.path.lexists(private) or os.path.lexists(control.AUTONOMY_TRANSACTION):
        raise AdoptionError("transaction_occupied", effect_unknown=True)
    _rename_exclusive(stage, private)
    control._fsync_directory(parent)
    check()
    if os.path.lexists(control.AUTONOMY_TRANSACTION):
        raise AdoptionError("transaction_occupied", effect_unknown=True)
    _rename_exclusive(private, control.AUTONOMY_TRANSACTION)
    control._fsync_directory(parent)
    return fd


class _HeldAdoption:
    def __init__(self, request, authority, mutex, stack):
        self.request, self.authority = request, authority
        self.mutex, self.stack = mutex, stack
        self.marker_fd = None
        self.marker_identity = None
        # A private publication interrupted before canonical rename must also
        # prevent another target/request from bypassing that original effect.
        self.operation_id = "autonomy-" + request.current_control_sha256[:12]
        self.private = control.CONFIG_ROOT / (".macro-adoption-" + self.operation_id)
        self.manifest = None
        self.files = {}
        self.postimage = False

    def initialize(self):
        if os.path.lexists(control.AUTONOMY_TRANSACTION) or os.path.lexists(self.private):
            raise AdoptionError("transaction_occupied")
        with maintenance._RootConfig() as config:
            self.before = config.raw
            self.config = config.value
            self.config_identity = config.initial
        self.candidate = prepare_candidate(self.request, self.before)
        self.worker, self.worker_identity = _sealed_bytes(
            control.WORKER_CONFIG, modes={0o440}, gid=self.config["worker_gid"])
        if digest(self.worker) != self.request.current_worker_sha256:
            raise AdoptionError("worker_preimage_mismatch")
        if decoded(self.worker).get("operator_harness_armed") is not False:
            raise AdoptionError("worker_harness_not_closed")
        self.receipts = _receipt_preimages()
        if {k: None if v is None else digest(v[0]) for k, v in self.receipts.items()} != dict(self.request.expected_receipts):
            raise AdoptionError("receipt_preimage_mismatch")
        self.acceptance_digest = self.authority.validate_acceptance(self.request.expected_release_sha)
        self.lock = self.stack.enter_context(maintenance._ServiceAdmissionLock(self.config))
        self.guard = self.stack.enter_context(maintenance._UnstartedPreproofGuard())
        self.database = maintenance._quiescent_database(self.config, self.lock, self.guard)
        self.database_identity = _identity(self.database.lstat())
        self.recheck_preimage()

    def _source_and_namespace(self):
        _check_source(self.request.expected_release_sha)
        _check_config_mutex(self.mutex)
        self.lock.check()
        self.guard.check()
        self.authority.require_services_already_stopped()
        self.authority.require_service_uids_quiescent()
        current, identity = _sealed_bytes(control.WORKER_CONFIG, modes={0o440},
                                         gid=self.config["worker_gid"])
        if current != self.worker or identity != self.worker_identity:
            raise AdoptionError("worker_changed")
        if _identity(self.database.lstat()) != self.database_identity:
            raise AdoptionError("runtime_changed")
        maintenance._quiescent_database(self.config, self.lock, self.guard)
        from control_plane.executive_backup import _readonly_database
        with _readonly_database(self.database) as db:
            _runtime_quiescent(db)
        if self.authority.validate_acceptance(self.request.expected_release_sha) != self.acceptance_digest:
            raise AdoptionError("historical_acceptance_changed")

    def _config_matches(self, raw, identity=None):
        # Open a new unchanged guard only after this owner's completed namespace
        # mutation. Never modify an existing guard's pinned ancestor baseline.
        with maintenance._RootConfig() as current:
            if current.raw != raw or (identity is not None and current.initial != identity):
                raise AdoptionError("control_changed")
            _closed(current.value)
            current.check()

    def _target(self, *, completed=False):
        # Fixed legitimate Control principal, exact current immutable source and
        # system interpreter. All target content is public source; stdout is
        # closed metadata only, never the boot packet or account/config bytes.
        interpreter = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
        process = subprocess.run([
            "/usr/bin/sudo", "-n", "-u", control.CONTROL_USER,
            "/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME=" + pwd.getpwnam(control.CONTROL_USER).pw_dir,
            "GIT_NO_LAZY_FETCH=1", "GIT_NO_REPLACE_OBJECTS=1", "GIT_TERMINAL_PROMPT=0",
            interpreter, "-I", "-S", "-B", str(Path(__file__).resolve()),
            "observe-completed-target" if completed else "qualify-target",
            "--release-sha", self.request.expected_release_sha,
            "--macro-root", self.request.target_macro_root,
        ], capture_output=True, timeout=33, check=False)
        if process.returncode != 0 or len(process.stdout) > 4096:
            raise AdoptionError("target_qualification_refused")
        observed = decoded(process.stdout)
        if (set(observed) != {"source_sha", "macro_sha", "macro_seal_sha256", "artifact_sha256", "generated_at", "observed_at"}
                or observed["source_sha"] != self.request.expected_release_sha
                or observed["macro_sha"] != self.request.target_macro_sha
                or observed["macro_seal_sha256"] != self.request.target_generation_seal_sha256
                or observed["artifact_sha256"] != self.request.target_artifact_sha256):
            raise AdoptionError("target_qualification_mismatch")
        self.target_observation = observed
        if not completed:
            _require_current(observed["generated_at"], datetime.now(timezone.utc).isoformat())

    def recheck_preimage(self):
        self._source_and_namespace()
        self._config_matches(self.before, self.config_identity)
        if _receipt_preimages() != self.receipts:
            raise AdoptionError("receipt_changed")
        self._target()

    def begin(self):
        self.files = {"prior-control.json": self.before, "prior-worker.json": self.worker}
        for key, value in self.receipts.items():
            self.files["prior-" + key + ".json"] = b"" if value is None else value[0]
        self.manifest = {"schema": SCHEMA, "operation": "MACRO_ADOPT", "operation_id": self.operation_id,
                         "request": self.request.document(), "candidate_sha256": digest(self.candidate),
                         "phase": "PREPARED"}
        fd = _publish_prepared_generation(
            self.private, self.operation_id, dict(self.files, **{"transaction.json": encoded(self.manifest)}),
            self.candidate, pwd.getpwnam(control.CONTROL_USER).pw_gid,
            self.stack, self.recheck_preimage)
        self.marker_fd, self.marker_identity = fd, _identity(os.fstat(fd))[:5]
        self._marker()

    def _marker(self):
        if _ACTIVE_OWNER is not self or self.marker_fd is None:
            raise AdoptionError("held_owner_required", effect_unknown=True)
        if (_identity(os.fstat(self.marker_fd))[:5] != self.marker_identity
                or _identity(control.AUTONOMY_TRANSACTION.lstat())[:5] != self.marker_identity):
            raise AdoptionError("transaction_identity_changed", effect_unknown=True)
        fcntl.flock(self.marker_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest, _ = _sealed_bytes(control.AUTONOMY_TRANSACTION / "transaction.json", modes={0o400}, gid=0)
        if manifest != encoded(self.manifest):
            raise AdoptionError("transaction_manifest_changed", effect_unknown=True)
        for name, expected in self.files.items():
            if _sealed_bytes(control.AUTONOMY_TRANSACTION / name, modes={0o400}, gid=0)[0] != expected:
                raise AdoptionError("transaction_archive_changed", effect_unknown=True)

    def recheck_before_replace(self):
        self._marker()
        self.recheck_preimage()

    def phase(self, phase):
        self._marker()
        self.manifest = dict(self.manifest, phase=phase)
        control._atomic_file(control.AUTONOMY_TRANSACTION / "transaction.json", encoded(self.manifest),
                             mode=0o400, uid=0, gid=0, replace=True)
        self._marker()

    def replace_control(self):
        # Actual rename edge, after its durable phase and immediately after all
        # final gate checks. No asynchronous job can start: both services are
        # absent and the canonical Runtime lock remains held.
        self.recheck_before_replace()
        candidate = control.AUTONOMY_TRANSACTION / "candidate-control.json"
        if _sealed_bytes(candidate, modes={0o440}, gid=pwd.getpwnam(control.CONTROL_USER).pw_gid)[0] != self.candidate:
            raise AdoptionError("candidate_changed", effect_unknown=True)
        _require_current(self.target_observation["generated_at"], datetime.now(timezone.utc).isoformat())
        os.replace(candidate, control.CONTROL_CONFIG)
        control._fsync_directory(control.CONFIG_ROOT)
        self.postimage = True

    def recheck_postimage(self):
        self._marker()
        self._source_and_namespace()
        self._config_matches(self.candidate)
        if _receipt_preimages() != self.receipts:
            raise AdoptionError("receipt_changed", effect_unknown=True)

    def observation_publication_binding(self):
        if type(self) is not _HeldAdoption or _ACTIVE_OWNER is not self or not self.postimage:
            raise AdoptionError("held_owner_required", effect_unknown=True)
        self._marker()
        if self.manifest["phase"] != "OBSERVATION_PUBLICATION_STARTED":
            raise AdoptionError("observation_phase_invalid", effect_unknown=True)
        self.recheck_postimage()
        return self.request.expected_release_sha, digest(self.candidate)

    def publish_observation(self):
        from ops.executive_os.control_observation import publish_for_macro_adoption
        self.observation_digest = publish_for_macro_adoption(self)
        return self.observation_digest

    def publish_receipt(self, observation_digest):
        self._marker()
        self._source_and_namespace()
        self._config_matches(self.candidate)
        current = _receipt_preimages()
        for key in ("ceo_submit", "autonomy", "adoption"):
            if current[key] != self.receipts[key]:
                raise AdoptionError("receipt_changed", effect_unknown=True)
        if (current["control_observation"] is None
                or digest(current["control_observation"][0]) != observation_digest
                or observation_digest != self.observation_digest):
            raise AdoptionError("observation_changed", effect_unknown=True)
        result = {"schema": RECEIPT_SCHEMA, "operation_id": self.operation_id,
                  "request_sha256": digest(encoded(self.request.document())),
                  "release_sha": self.request.expected_release_sha,
                  "old_control_sha256": digest(self.before), "new_control_sha256": digest(self.candidate),
                  "worker_sha256": digest(self.worker), "old_macro_root": self.request.expected_old_macro_root,
                  "target_macro_root": self.request.target_macro_root,
                  "target": self.target_observation, "historical_acceptance_sha256": self.acceptance_digest,
                  "control_observation_sha256": observation_digest,
                  "authority_resumed": False, "services_started": False,
                  "observed_at": datetime.now(timezone.utc).isoformat()}
        self.result_bytes = encoded(result)
        control._atomic_file(RECEIPT, self.result_bytes, mode=0o400, uid=0, gid=0,
                             replace=self.receipts["adoption"] is not None)
        if _sealed_bytes(RECEIPT, modes={0o400}, gid=0)[0] != self.result_bytes:
            raise AdoptionError("receipt_publication_unknown", effect_unknown=True)
        return result

    def complete(self):
        self._marker()
        self._source_and_namespace()
        self._config_matches(self.candidate)
        if self.manifest["phase"] != "COMPLETE" or _sealed_bytes(RECEIPT, modes={0o400}, gid=0)[0] != self.result_bytes:
            raise AdoptionError("closeout_unknown", effect_unknown=True)
        current = _receipt_preimages()
        if (any(current[key] != self.receipts[key] for key in ("ceo_submit", "autonomy"))
                or current["control_observation"] is None
                or digest(current["control_observation"][0]) != self.observation_digest):
            raise AdoptionError("closeout_receipt_changed", effect_unknown=True)
        expected = set(self.files) | {"transaction.json"}
        if set(os.listdir(self.marker_fd)) != expected:
            raise AdoptionError("transaction_namespace_changed", effect_unknown=True)
        _archive_generation(control.AUTONOMY_TRANSACTION, self.private, self.marker_fd)


def validate_prepared(request, manifest, archives, candidate_control, current_control,
                      current_worker, current_receipts):
    """Exact no-effect byte join only; never custody or cleanup authority."""
    request = parse_request(request.document())
    keys = {"schema", "operation", "operation_id", "request", "candidate_sha256", "phase"}
    names = {"prior-control.json", "prior-worker.json"} | {"prior-" + k + ".json" for k in RECEIPTS}
    if (type(manifest) is not dict or set(manifest) != keys
            or manifest["schema"] != SCHEMA or manifest["operation"] != "MACRO_ADOPT"
            or manifest["operation_id"] != "autonomy-" + request.current_control_sha256[:12]
            or manifest["request"] != request.document() or manifest["phase"] != "PREPARED"
            or type(archives) is not dict or set(archives) != names
            or type(current_receipts) is not dict or set(current_receipts) != set(RECEIPTS)):
        raise AdoptionError("prepared_generation_unproven")
    if (current_control != archives["prior-control.json"]
            or current_worker != archives["prior-worker.json"]
            or digest(current_worker) != request.current_worker_sha256):
        raise AdoptionError("prepared_preimage_changed")
    candidate = prepare_candidate(request, archives["prior-control.json"])
    if candidate_control != candidate or manifest["candidate_sha256"] != digest(candidate):
        raise AdoptionError("prepared_candidate_changed")
    if decoded(current_worker).get("operator_harness_armed") is not False:
        raise AdoptionError("worker_harness_not_closed")
    for key in RECEIPTS:
        raw = archives["prior-" + key + ".json"]
        expected = request.expected_receipts[key]
        if ((expected is None and raw != b"")
                or (expected is not None and digest(raw) != expected)
                or current_receipts[key] != (None if expected is None else raw)):
            raise AdoptionError("prepared_receipt_changed")
    return candidate


def _prepared_archive(request, device, inode):
    if type(device) is not int or type(inode) is not int or not 0 <= device < 2**64 or not 0 < inode < 2**64:
        raise AdoptionError("prepared_owner_token_invalid")
    operation = "autonomy-" + request.current_control_sha256[:12]
    return control.CONFIG_ROOT / (".macro-adoption-prepared-closed-" + operation + "-" + str(device) + "-" + str(inode))


def _prepared_directory(path, fd, device, inode):
    maintenance._sealed_ancestors(path / "transaction.json")
    held = os.fstat(fd)
    if ((held.st_dev, held.st_ino) != (device, inode)
            or _identity(held)[:5] != _identity(path.lstat())[:5]
            or held.st_uid != 0 or held.st_gid != 0
            or stat.S_IMODE(held.st_mode) != stat.S_IRWXU
            or maintenance.has_macos_acl(path, descriptor=fd, expected_identity=held)):
        raise AdoptionError("prepared_owner_custody_invalid")
    return _identity(held)[:5]


def _prepared_files(path, fd, candidate_gid):
    names = {"prior-control.json", "prior-worker.json"} | {"prior-" + k + ".json" for k in RECEIPTS}
    if set(os.listdir(fd)) != names | {"transaction.json", "candidate-control.json"}:
        raise AdoptionError("prepared_namespace_incomplete")
    files = {name: _sealed_bytes(path / name, modes={0o400}, gid=0)[0] for name in names | {"transaction.json"}}
    candidate = _sealed_bytes(path / "candidate-control.json", modes={0o440}, gid=candidate_gid)[0]
    return decoded(files.pop("transaction.json")), files, candidate


def _close_prepared_generation(request, owner_device, owner_inode, candidate_gid, prove):
    """Private namespace mechanism; outer owner retains every authority lock.

    `prove` is the owner's closed-over real offline/preimage proof, never a CLI
    input or substitute authority. Tests of this mechanism do not qualify it.
    """
    archive = _prepared_archive(request, owner_device, owner_inode)
    private = control.CONFIG_ROOT / (".macro-adoption-autonomy-" + request.current_control_sha256[:12])
    locations = [p for p in (control.AUTONOMY_TRANSACTION, private) if os.path.lexists(p)]
    observed_archive = os.path.lexists(archive)
    if (observed_archive and locations) or (not observed_archive and len(locations) != 1):
        raise AdoptionError("prepared_generation_ambiguous")
    path = archive if observed_archive else locations[0]
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    mutation = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        initial = _prepared_directory(path, fd, owner_device, owner_inode)

        def proof():
            current_control, current_worker, receipts = prove()
            if _prepared_directory(path, fd, owner_device, owner_inode) != initial:
                raise AdoptionError("prepared_owner_changed")
            manifest, archives, candidate = _prepared_files(path, fd, candidate_gid)
            actual = {k: None if v is None else v[0] for k, v in receipts.items()}
            validate_prepared(request, manifest, archives, candidate,
                              current_control, current_worker, actual)
            return manifest, archives, candidate, receipts

        first = proof()
        if proof() != first:
            raise AdoptionError("prepared_bytes_changed")
        if not observed_archive:
            if os.path.lexists(archive) or any(os.path.lexists(p) for p in (control.AUTONOMY_TRANSACTION, private) if p != path):
                raise AdoptionError("prepared_namespace_changed")
            mutation = True
            _archive_generation(path, archive, fd)
        return {"operation_id": first[0]["operation_id"], "closeout": "PREPARED_CLOSED",
                "owner_device": owner_device, "owner_inode": owner_inode,
                "configuration_changed": False, "authority_resumed": False, "services_started": False}
    except BaseException as exc:
        if mutation:
            raise AdoptionError("prepared_close_effect_unknown", effect_unknown=True) from exc
        if isinstance(exc, AdoptionError):
            raise
        raise AdoptionError("prepared_close_refused") from exc
    finally:
        os.close(fd)


def close_prepared(request, *, owner_device, owner_inode):
    """Explicit same-generation no-effect close or positively proven lost ACK.

    No config, receipt, phase or Runtime is written. Later phases and incomplete
    generations remain held. A name alone never proves archive identity.
    """
    request = parse_request(request.document())
    _prepared_archive(request, owner_device, owner_inode)
    authority = _check_source(request.expected_release_sha)
    authority.require_services_already_stopped()
    authority.require_service_uids_quiescent()
    control.ProductionTransactionHost._config_root_safe()
    mutex = os.open(control.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _check_config_mutex(mutex)
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ExitStack() as stack:
            with maintenance._RootConfig() as current:
                config, config_raw = current.value, current.raw
            _closed(config)
            worker, worker_identity = _sealed_bytes(control.WORKER_CONFIG, modes={0o440}, gid=config["worker_gid"])
            acceptance = authority.validate_acceptance(request.expected_release_sha)
            lock = stack.enter_context(maintenance._ServiceAdmissionLock(config))
            guard = stack.enter_context(maintenance._UnstartedPreproofGuard())
            database = maintenance._quiescent_database(config, lock, guard)
            database_identity = _identity(database.lstat())

            def proof():
                _check_source(request.expected_release_sha)
                _check_config_mutex(mutex)
                authority.require_services_already_stopped()
                authority.require_service_uids_quiescent()
                lock.check()
                guard.check()
                maintenance._quiescent_database(config, lock, guard)
                if _identity(database.lstat()) != database_identity:
                    raise AdoptionError("runtime_changed")
                from control_plane.executive_backup import _readonly_database
                with _readonly_database(database) as db:
                    _runtime_quiescent(db)
                if authority.validate_acceptance(request.expected_release_sha) != acceptance:
                    raise AdoptionError("historical_acceptance_changed")
                with maintenance._RootConfig() as current:
                    if current.raw != config_raw:
                        raise AdoptionError("prepared_control_changed")
                    current.check()
                now_worker, now_identity = _sealed_bytes(control.WORKER_CONFIG, modes={0o440}, gid=config["worker_gid"])
                if now_worker != worker or now_identity != worker_identity:
                    raise AdoptionError("prepared_worker_changed")
                return config_raw, worker, _receipt_preimages()

            return _close_prepared_generation(request, owner_device, owner_inode,
                                             pwd.getpwnam(control.CONTROL_USER).pw_gid, proof)
    except AdoptionError:
        raise
    except BaseException as exc:
        raise AdoptionError("prepared_close_refused") from exc
    finally:
        os.close(mutex)


def validate_completed(request, manifest, archives, current_control, current_worker,
                       current_receipts, observation_bytes, acceptance_digest):
    """Pure completed-bytes join; does not confer custody or cleanup authority."""
    expected_manifest = {"schema", "operation", "operation_id", "request", "candidate_sha256", "phase"}
    if (type(manifest) is not dict or set(manifest) != expected_manifest
            or manifest["schema"] != SCHEMA or manifest["operation"] != "MACRO_ADOPT"
            or manifest["operation_id"] != "autonomy-" + request.current_control_sha256[:12]
            or manifest["request"] != request.document()
            or manifest["phase"] not in {"RECEIPT_PUBLICATION_STARTED", "COMPLETE"}):
        raise AdoptionError("completed_phase_unproven")
    expected_archives = {"prior-control.json", "prior-worker.json"} | {"prior-" + key + ".json" for key in RECEIPTS}
    if set(archives) != expected_archives:
        raise AdoptionError("completed_archives_invalid")
    candidate = prepare_candidate(request, archives["prior-control.json"])
    if (candidate != current_control or digest(candidate) != manifest["candidate_sha256"]
            or current_worker != archives["prior-worker.json"]
            or digest(current_worker) != request.current_worker_sha256):
        raise AdoptionError("completed_config_mismatch")
    for key in RECEIPTS:
        raw = archives["prior-" + key + ".json"]
        expected = request.expected_receipts[key]
        if (expected is None and raw != b"") or (expected is not None and digest(raw) != expected):
            raise AdoptionError("completed_preimage_mismatch")
    for key in ("ceo_submit", "autonomy"):
        if current_receipts[key] != (None if request.expected_receipts[key] is None else archives["prior-" + key + ".json"]):
            raise AdoptionError("completed_authority_changed")
    if current_receipts["adoption"] is None or current_receipts["control_observation"] != observation_bytes:
        raise AdoptionError("completed_publication_missing")
    receipt = decoded(current_receipts["adoption"])
    keys = {"schema", "operation_id", "request_sha256", "release_sha", "old_control_sha256", "new_control_sha256",
            "worker_sha256", "old_macro_root", "target_macro_root", "target", "historical_acceptance_sha256",
            "control_observation_sha256", "authority_resumed", "services_started", "observed_at"}
    expected = {"schema": RECEIPT_SCHEMA, "operation_id": manifest["operation_id"],
                "request_sha256": digest(encoded(request.document())), "release_sha": request.expected_release_sha,
                "old_control_sha256": request.current_control_sha256, "new_control_sha256": digest(candidate),
                "worker_sha256": request.current_worker_sha256, "old_macro_root": request.expected_old_macro_root,
                "target_macro_root": request.target_macro_root, "historical_acceptance_sha256": acceptance_digest,
                "control_observation_sha256": digest(observation_bytes), "authority_resumed": False, "services_started": False}
    if (type(receipt) is not dict or set(receipt) != keys
            or any(type(receipt.get(k)) is not type(v) or receipt.get(k) != v for k, v in expected.items())):
        raise AdoptionError("completed_receipt_mismatch")
    target = receipt["target"]
    if (type(target) is not dict or set(target) != {"source_sha", "macro_sha", "macro_seal_sha256", "artifact_sha256", "generated_at", "observed_at"}
            or target["source_sha"] != request.expected_release_sha or target["macro_sha"] != request.target_macro_sha
            or target["macro_seal_sha256"] != request.target_generation_seal_sha256
            or target["artifact_sha256"] != request.target_artifact_sha256):
        raise AdoptionError("completed_target_mismatch")
    return receipt


def close_complete(request):
    """Explicit normal owner closeout of proven completed SAME operation only.

    No config/observation/receipt/phase is replayed or repaired. A missing or
    mismatched completed byte remains held. Acquire the original inode flock
    without waiting; an original live writer always wins.
    """
    authority = _check_source(request.expected_release_sha)
    authority.require_services_already_stopped()
    authority.require_service_uids_quiescent()
    control.ProductionTransactionHost._config_root_safe()
    mutex = os.open(control.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    mutation = False
    try:
        _check_config_mutex(mutex)
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ExitStack() as stack:
            marker = control.AUTONOMY_TRANSACTION
            fd = os.open(marker, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            initial = _identity(os.fstat(fd))[:5]
            if (initial != _identity(marker.lstat())[:5] or initial[3:] != (0, 0)
                    or stat.S_IMODE(initial[2]) != stat.S_IRWXU):
                raise AdoptionError("completed_owner_custody_invalid")
            raw, _ = _sealed_bytes(marker / "transaction.json", modes={0o400}, gid=0)
            manifest = decoded(raw)
            names = {"prior-control.json", "prior-worker.json"} | {"prior-" + key + ".json" for key in RECEIPTS}
            if set(os.listdir(fd)) != names | {"transaction.json"}:
                raise AdoptionError("completed_namespace_invalid")
            archives = {name: _sealed_bytes(marker / name, modes={0o400}, gid=0)[0] for name in names}
            with maintenance._RootConfig() as current:
                config, config_raw = current.value, current.raw
            _closed(config)
            worker, _ = _sealed_bytes(control.WORKER_CONFIG, modes={0o440}, gid=config["worker_gid"])
            if decoded(worker).get("operator_harness_armed") is not False:
                raise AdoptionError("worker_harness_not_closed")
            lock = stack.enter_context(maintenance._ServiceAdmissionLock(config))
            guard = stack.enter_context(maintenance._UnstartedPreproofGuard())
            database = maintenance._quiescent_database(config, lock, guard)
            from control_plane.executive_backup import _readonly_database
            with _readonly_database(database) as db:
                _runtime_quiescent(db)
            acceptance = authority.validate_acceptance(request.expected_release_sha)
            from ops.executive_os.control_observation import _source, _snapshot
            _source(request.expected_release_sha)
            observation, _ = _snapshot(request.expected_release_sha)
            actual_receipts = _receipt_preimages()
            actual = {k: None if v is None else v[0] for k, v in actual_receipts.items()}
            receipt = validate_completed(request, manifest, archives, config_raw, worker, actual, observation, acceptance)
            # Re-observe immutable target bytes/seal even if its historical
            # completed proof has since aged. This read cannot admit adoption.
            held = _HeldAdoption(request, authority, mutex, stack)
            held._target(completed=True)
            if {k: held.target_observation[k] for k in ("source_sha", "macro_sha", "macro_seal_sha256", "artifact_sha256", "generated_at")} != {
                    k: receipt["target"][k] for k in ("source_sha", "macro_sha", "macro_seal_sha256", "artifact_sha256", "generated_at")}:
                raise AdoptionError("completed_target_changed")
            authority.require_services_already_stopped()
            authority.require_service_uids_quiescent()
            lock.check()
            guard.check()
            if (_identity(os.fstat(fd))[:5] != initial or _identity(marker.lstat())[:5] != initial
                    or _sealed_bytes(marker / "transaction.json", modes={0o400}, gid=0)[0] != raw
                    or _receipt_preimages() != actual_receipts):
                raise AdoptionError("completed_state_changed")
            with maintenance._RootConfig() as current:
                if current.raw != config_raw:
                    raise AdoptionError("completed_config_changed")
            if _sealed_bytes(control.WORKER_CONFIG, modes={0o440}, gid=config["worker_gid"])[0] != worker:
                raise AdoptionError("completed_worker_changed")
            for name, expected in archives.items():
                if _sealed_bytes(marker / name, modes={0o400}, gid=0)[0] != expected:
                    raise AdoptionError("completed_archive_changed")
            archive = control.CONFIG_ROOT / (".macro-adoption-" + manifest["operation_id"])
            if os.path.lexists(archive):
                raise AdoptionError("completed_archive_occupied_or_changed")
            _check_config_mutex(mutex)
            mutation = True
            _archive_generation(marker, archive, fd)
            return {"operation_id": manifest["operation_id"], "closeout": "COMPLETED", "authority_resumed": False}
    except BaseException as exc:
        if mutation:
            raise AdoptionError("closeout_effect_unknown", effect_unknown=True) from exc
        if isinstance(exc, AdoptionError):
            raise
        raise AdoptionError("completed_closeout_refused") from exc
    finally:
        os.close(mutex)


def _status_facts(request, actual, marker_location, manifest, receipt):
    """Display independent facts, never turn correlation into cleanup authority."""
    result = {"schema": SCHEMA, "state": "CONFLICT_OR_UNKNOWN", "configuration": "OTHER",
              "request_sha256": digest(encoded(request.document())), "modifying_action": False,
              "marker_location": marker_location, "phase": None, "receipt_state": "ABSENT_OR_UNAVAILABLE"}
    if actual == request.current_control_sha256:
        result["configuration"] = "PREIMAGE"
    if marker_location is not None:
        result["state"] = "HELD_UNKNOWN"
        if (type(manifest) is dict and manifest.get("schema") == SCHEMA
                and manifest.get("operation") == "MACRO_ADOPT"
                and manifest.get("request") == request.document()):
            result.update(phase=manifest.get("phase"), operation_id=manifest.get("operation_id"))
            if actual == manifest.get("candidate_sha256"):
                result["configuration"] = "POSTIMAGE"
    if type(receipt) is dict:
        result["receipt_state"] = "OTHER"
        if (receipt.get("schema") == RECEIPT_SCHEMA and receipt.get("request_sha256") == result["request_sha256"]
                and receipt.get("new_control_sha256") == actual
                and receipt.get("authority_resumed") is False and receipt.get("services_started") is False):
            result.update(receipt_state="MATCHING_POSTIMAGE_OBSERVATION", configuration="POSTIMAGE",
                          operation_id=receipt.get("operation_id"))
            if marker_location == "PRIVATE" and result["phase"] == "COMPLETE":
                result["state"] = "COMPLETED_ARCHIVE_OBSERVED_REQUIRES_ADJUDICATION"
            elif marker_location is None:
                result["state"] = "POSTIMAGE_OBSERVED_REQUIRES_ADJUDICATION"
    if marker_location is None and result["configuration"] == "PREIMAGE":
        result["state"] = "PREIMAGE_NO_CANONICAL_OPERATION_OBSERVED"
    return result


def _prepared_status_token(request, path):
    """Nonauthorizing observation; the close action must re-prove everything."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        info = os.fstat(fd)
        _prepared_directory(path, fd, info.st_dev, info.st_ino)
        with maintenance._RootConfig() as current:
            config, raw = current.value, current.raw
        worker = _sealed_bytes(control.WORKER_CONFIG, modes={0o440}, gid=config["worker_gid"])[0]
        manifest, archives, candidate = _prepared_files(path, fd, pwd.getpwnam(control.CONTROL_USER).pw_gid)
        receipts = {k: None if v is None else v[0] for k, v in _receipt_preimages().items()}
        validate_prepared(request, manifest, archives, candidate, raw, worker, receipts)
        _prepared_directory(path, fd, info.st_dev, info.st_ino)
        return {"device": info.st_dev, "inode": info.st_ino}
    finally:
        os.close(fd)


def status(request):
    """Observe marker AND receipt facts, including a torn/partial marker."""
    request = parse_request(request.document())
    _check_source(request.expected_release_sha)
    with maintenance._RootConfig() as current:
        actual = digest(current.raw)
    private = control.CONFIG_ROOT / (".macro-adoption-autonomy-" + request.current_control_sha256[:12])
    location = "CANONICAL" if os.path.lexists(control.AUTONOMY_TRANSACTION) else (
        "PRIVATE" if os.path.lexists(private) else None)
    manifest = receipt = None
    if location:
        marker = control.AUTONOMY_TRANSACTION if location == "CANONICAL" else private
        try:
            manifest = decoded(_sealed_bytes(marker / "transaction.json", modes={0o400}, gid=0)[0])
        except (OSError, AdoptionError, control.HostControlError, maintenance.MaintenanceError):
            pass
    try:
        receipt = decoded(_sealed_bytes(RECEIPT, modes={0o400}, gid=0)[0])
    except (OSError, AdoptionError, control.HostControlError, maintenance.MaintenanceError):
        pass
    result = _status_facts(request, actual, location, manifest, receipt)
    result["prepared_owner_token"] = None
    if location:
        try:
            result["prepared_owner_token"] = _prepared_status_token(request, marker)
        except (OSError, AdoptionError, control.HostControlError, maintenance.MaintenanceError):
            pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "adopt", "status", "close-complete", "close-prepared"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--request", required=True)
        if name == "close-prepared":
            cmd.add_argument("--owner-device", required=True, type=int)
            cmd.add_argument("--owner-inode", required=True, type=int)
        if name == "prepare":
            cmd.add_argument("--control-input", required=True)
            cmd.add_argument("--output", required=True)
    for name in ("qualify-target", "observe-completed-target"):
        probe = sub.add_parser(name)
        probe.add_argument("--release-sha", required=True)
        probe.add_argument("--macro-root", required=True)
    args = parser.parse_args()
    try:
        if args.command in ("qualify-target", "observe-completed-target"):
            result = _qualification_probe(args.macro_root, args.release_sha,
                                          require_current=args.command == "qualify-target")
        else:
            request = parse_request(decoded(Path(args.request).read_bytes()))
            if args.command == "prepare":
                raw = prepare_candidate(request, Path(args.control_input).read_bytes())
                with open(args.output, "xb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                result = {"candidate_sha256": digest(raw), "host_qualified": False}
            elif args.command == "adopt":
                result = adopt(ProductionHost(), request)
            elif args.command == "close-prepared":
                result = close_prepared(request, owner_device=args.owner_device, owner_inode=args.owner_inode)
            elif args.command == "close-complete":
                result = close_complete(request)
            else:
                result = status(request)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"code": exc.code if isinstance(exc, AdoptionError) else "refused",
                          "effect_unknown": isinstance(exc, AdoptionError) and exc.effect_unknown}))
        return 2

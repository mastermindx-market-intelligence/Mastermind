#!/usr/bin/env python3
"""One-run, local read-only observation. The existing parent owns transport.

No lifecycle decisions, arbitrary paths, environment discovery, process control,
or worker stdout reads. All evidence is an observation, never acceptance.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import pwd
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
LEASE_SCHEMA = "mastermind.local_lane_lease.v1"
HOLD_SCHEMA = "mastermind.local_lane_reconciliation_hold.v1"
PROCESS_SCHEMA = "mastermind.local_owned_process_receipt.v1"
RELEASE_SCHEMA = "remote-support-code.v1"
SOURCE_FILES = frozenset({
    "remote_sub_exec.py", "artifact_production.py", "artifact_reader.py",
    "native_remote.py", "go_remote_codex.py", "go_remote_capsule.py",
    "lane_runtime.py", "sub.sh", "slot.py", "glm_bound_claude.py", "pick.py",
    "model_tier.py", "codex_usage.py", "mm_codex_exec.sh", "glm_codex_exec.sh",
    "go_codex_exec.sh", "qwen_exec.sh", "fabric_client_projection.py",
    "studio_mcp_projection.sh", "mm_feeder_lib.py", "pool_ledger.py",
    "lease_broker.py", "glm_keys.py", "bailian_keys.py",
})
PREVIOUS_FILES = SOURCE_FILES - {"glm_bound_claude.py"}
GENERATIONS = (SOURCE_FILES, PREVIOUS_FILES,
               PREVIOUS_FILES - {"artifact_production.py", "artifact_reader.py"})
# Exact additional immutable generation used by the original issuer-preflight run.
# Existing generations and strict directory/file custody remain unchanged.
ACTIVE_SUPPORT_DIGEST = '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114'
ACTIVE_SUPPORT_FILES = SOURCE_FILES | {
    'fabric_operator_client.py', 'fabric_operator_stop.py',
    'fabric_policy_snapshot.py', 'pools.yaml', 'fabric_operator_diagnostics.py', 'yes',
}
PROC_ROOT = Path("/proc")  # fixed Linux observation surface; not a request field
MAX_CODE = 2 * 1024 * 1024
MAX_CODE_TOTAL = 16 * 1024 * 1024


class Invalid(ValueError):
    pass


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Invalid("duplicate_json_key")
            out[key] = value
        return out
    def bad_constant(_):
        raise Invalid("nonfinite_json_number")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid("invalid_json") from None


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def directory_identity(s):
    # Other runs may change a shared directory's mtime. Identity and custody,
    # rather than unrelated child activity, determine whether our path moved.
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid)


def metadata(s):
    return {"device": s.st_dev, "inode": s.st_ino, "uid": s.st_uid,
            "mode": stat.S_IMODE(s.st_mode), "bytes": s.st_size,
            "mtime_ns": s.st_mtime_ns}


class Reader:
    """Held directory descriptors; each path is a fixed internal tuple."""
    def __init__(self, root, uid, *, require_final_owner=True):
        self.uid, self.fds, self.edges = uid, [], []
        root = Path(root)
        if not root.is_absolute() or ".." in root.parts:
            raise Invalid("invalid_account_home")
        try:
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(fd)
            self._directory(os.fstat(fd))
            for part in root.parts[1:]:
                self.descend(part)
            if require_final_owner and os.fstat(self.fds[-1]).st_uid != uid:
                raise Invalid("home_owner_mismatch")
        except BaseException:
            self.close()
            raise

    def _directory(self, s):
        if (not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, self.uid)
                or s.st_mode & 0o022):
            raise Invalid("directory_owner_mode_or_type")

    def descend(self, part):
        if not part or part in (".", "..") or "/" in part:
            raise Invalid("invalid_fixed_path")
        parent = self.fds[-1]
        fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                     dir_fd=parent)
        self.fds.append(fd)
        s = os.fstat(fd)
        self._directory(s)
        self.edges.append((parent, part, fd, directory_identity(s)))
        self.verify()

    def verify(self):
        for parent, name, fd, expected in self.edges:
            if (directory_identity(os.fstat(fd)) != expected or
                    directory_identity(os.stat(name, dir_fd=parent,
                                                follow_symlinks=False)) != expected):
                raise Invalid("directory_changed")

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _file(self, s, mode=None):
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != self.uid
                or s.st_nlink != 1 or s.st_mode & 0o022
                or (mode is not None and stat.S_IMODE(s.st_mode) != mode)):
            raise Invalid("file_owner_mode_or_type")

    def read(self, parts, limit, *, content=True, mode=None, proc=False):
        depth, edge_depth = len(self.fds), len(self.edges)
        fd = None
        try:
            for part in parts[:-1]:
                self.descend(part)
            name, parent = parts[-1], self.fds[-1]
            if not name or name in (".", "..") or "/" in name:
                raise Invalid("invalid_fixed_path")
            if not content:
                # Deliberately do not open or read stdout, including on Linux.
                before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                self._file(before, mode)
                after = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if identity(before) != identity(after):
                    raise Invalid("file_changed")
                self.verify()
                return None, before
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
            before = os.fstat(fd)
            self._file(before, mode)
            if before.st_size > limit:
                raise Invalid("size_limit")
            chunks, remaining = [], limit + 1
            while remaining:
                chunk = os.read(fd, min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > limit:
                raise Invalid("size_limit")
            if (identity(before) != identity(os.fstat(fd))
                    or identity(before) != identity(os.stat(
                        name, dir_fd=parent, follow_symlinks=False))
                    or (not proc and len(raw) != before.st_size)):
                raise Invalid("file_changed")
            self.verify()
            return raw, before
        except FileNotFoundError:
            # Absence is credible only while every opened parent remains bound.
            self.verify()
            raise
        finally:
            if fd is not None:
                os.close(fd)
            for held in reversed(self.fds[depth:]):
                os.close(held)
            del self.fds[depth:]
            del self.edges[edge_depth:]


def capture(fn):
    try:
        return {"status": "observed", **fn()}
    except FileNotFoundError:
        return {"status": "absent", "reason": "missing_at_observation"}
    except OSError as exc:
        # A permission denial ends this request; never switch to another probe.
        if exc.errno in (errno.EACCES, errno.EPERM):
            raise
        return {"status": "unavailable", "reason": "filesystem_error",
                "errno": exc.errno}
    except (Invalid, UnicodeError, OverflowError, RecursionError) as exc:
        return {"status": "unavailable",
                "reason": str(exc) if isinstance(exc, Invalid) else "malformed_data"}


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise Invalid("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise Invalid("invalid_timestamp") from None


def integer(value, name, low=0, high=2**63-1):
    if type(value) is not int or not low <= value <= high:
        raise Invalid("invalid_" + name)
    return value


SUPPORT_METADATA_RUN = 'b-f08-alert-race-review-01a128b7-v1'
SUPPORT_METADATA_DIGEST = 'afb81a34429f67fcad0f1981ac9014968bde4641cf9f8457a3fc43738ce55a57'
SUPPORT_METADATA_SCHEMA = 'mastermind.support_directory_metadata.v1'
SUPPORT_METADATA_LIMITS = [
    'Directory metadata only; no file content read',
    'Release content and hashes are not verified; no content identity is proven',
    'Not an atomic directory snapshot',
    'Does not grant strict Reader admission',
    'No lifecycle, acceptance, retry, cancellation, or release decision',
]
SUPPORT_METADATA_MAX_COMPONENTS = 16


def support_metadata(run_id, digest):
    """Exact B-only fixed ancestry metadata; never read a file or denied child.

    This diagnostic does not grant Reader admission. It uses the same directory
    invariant, reports its first failure, and stops before opening that component.
    """
    if run_id != SUPPORT_METADATA_RUN or digest != SUPPORT_METADATA_DIGEST:
        raise Invalid('support_metadata_scope_not_admitted')
    uid = os.getuid()
    report = dict(schema=SUPPORT_METADATA_SCHEMA, run_id=run_id,
                  expected_support_digest=digest, account_uid=uid,
                  status='unavailable', verdict='UNAVAILABLE', metadata_only=True,
                  content_read=False, component=None, expected=None, observed=None,
                  failures=[], reason=None, errno=None, account_home=None,
                  components=[], limits=list(SUPPORT_METADATA_LIMITS))
    fds, edges = [], []
    def verify_edges():
        for parent, name, opened, expected in edges:
            if (directory_identity(os.fstat(opened)) != expected or
                    directory_identity(os.stat(name, dir_fd=parent,
                                                follow_symlinks=False)) != expected):
                raise Invalid('directory_changed')
    try:
        home_text = pwd.getpwuid(uid).pw_dir
        home = Path(home_text)
        if (not home.is_absolute() or '..' in home.parts or home == Path('/')
                or str(home) != home_text or len(home_text) > 256
                or len(home.parts) + 4 > SUPPORT_METADATA_MAX_COMPONENTS):
            raise Invalid('invalid_account_home')
        report['account_home'] = home_text
        chain = [('/', 'filesystem_root')]
        chain.extend((part, 'account_home' if i == len(home.parts)-1
                      else 'account_home_ancestor')
                     for i, part in enumerate(home.parts[1:], 1))
        chain.extend((('lanes','lanes'), ('support-releases','support-releases'),
                      (digest,'release'), ('ext','release-ext')))
        path = Path('/')
        for name, role in chain:
            path = path if role == 'filesystem_root' else path / name
            allowed = [uid] if role == 'account_home' else sorted({0, uid})
            report.update(component=dict(role=role,path=str(path)),
                          expected=dict(directory=True,uids=allowed,forbidden_mode_bits=0o022),
                          observed=None, failures=[])
            row = dict(component=report['component'], expected=report['expected'],
                       observed=None, failures=[])
            report['components'].append(row)
            info = os.stat(name, follow_symlinks=False,
                           **({'dir_fd':fds[-1]} if fds else {}))
            kind = ('directory' if stat.S_ISDIR(info.st_mode) else
                    'symlink' if stat.S_ISLNK(info.st_mode) else 'other')
            report['observed'] = dict(kind=kind, **metadata(info))
            failures = (["type"] if kind != 'directory' else [])
            if info.st_uid not in allowed:
                failures.append('uid')
            if info.st_mode & 0o022:
                failures.append('mode')
            row.update(observed=report['observed'], failures=failures)
            verify_edges()
            if failures:
                report.update(status='observed',verdict='INVARIANT_FAILED',failures=failures)
                return report
            opened = os.open(name,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             **({'dir_fd':fds[-1]} if fds else {}))
            fds.append(opened)
            if directory_identity(os.fstat(opened)) != directory_identity(info):
                raise Invalid('directory_changed')
            if len(fds)>1:
                edges.append((fds[-2],name,opened,directory_identity(info)))
            elif directory_identity(os.stat('/',follow_symlinks=False)) != directory_identity(info):
                raise Invalid('directory_changed')
            verify_edges()
        report.update(status='observed',verdict='CHAIN_VALID')
    except OSError as exc:
        report.update(status='unavailable',verdict='UNAVAILABLE',
                      reason=('os_permission_denied' if exc.errno in (errno.EACCES,errno.EPERM)
                              else 'filesystem_unavailable'),errno=exc.errno)
    except (Invalid,KeyError) as exc:
        report.update(status='unavailable',verdict='UNAVAILABLE',
                      reason=str(exc) if isinstance(exc,Invalid) else 'account_home_unavailable')
    finally:
        for opened in reversed(fds):
            os.close(opened)
    return report


def support(reader, digest):
    base = ("lanes", "support-releases", digest)
    raw, _ = reader.read((*base, "RELEASE.json"), 65536, mode=0o444)
    data = strict_json(raw)
    if not isinstance(data, dict) or data.get("schema") != RELEASE_SCHEMA:
        raise Invalid("release_schema_mismatch")
    files = data.get("files")
    generations = (ACTIVE_SUPPORT_FILES,) if digest == ACTIVE_SUPPORT_DIGEST else GENERATIONS
    if not isinstance(files, dict) or frozenset(files) not in generations:
        raise Invalid("release_file_set_mismatch")
    if any(not isinstance(v, str) or not HEX.fullmatch(v) for v in files.values()):
        raise Invalid("release_hash_invalid")
    canonical = json.dumps({"schema": RELEASE_SCHEMA, "files": files},
                           sort_keys=True, separators=(",", ":")).encode()
    if data.get("digest") != digest or hashlib.sha256(canonical).hexdigest() != digest:
        raise Invalid("release_digest_mismatch")
    total = 0
    for name in sorted(files):  # names admitted only by fixed source generations
        code, _ = reader.read((*base, "ext", name),
                              min(MAX_CODE, MAX_CODE_TOTAL-total), mode=0o555)
        total += len(code)
        if hashlib.sha256(code).hexdigest() != files[name]:
            raise Invalid("release_code_mismatch")
    # The manifest must still be the same after checking the code closure.
    after, _ = reader.read((*base, "RELEASE.json"), 65536, mode=0o444)
    if after != raw:
        raise Invalid("release_manifest_changed")
    return {"digest": digest, "verified_code_files": len(files),
            "verification": "manifest_and_fixed_code_hashes",
            "running_process_source_identity_proven": False,
            "release_links_verified": False}


def marker(reader, run, now):
    raw, info = reader.read(("lanes", "ext", "active", run), 65536)
    data = strict_json(raw)
    hold = None
    if isinstance(data, dict) and data.get("schema") == HOLD_SCHEMA:
        original = data.get("original_lease")
        if (set(data) != {"schema", "key", "reason", "held_at", "host", "original_lease"}
                or data.get("key") != run or data.get("reason") != "worker_cleanup_unproven"
                or type(original) is not dict or original.get("reconcile_unreleased") is not True
                or type(data.get("host")) is not str
                or not RUN_ID.fullmatch(data["host"]) or original.get("host") != data["host"]):
            raise Invalid("hold_schema_or_binding_mismatch")
        held = timestamp(data["held_at"])
        if not timestamp(original.get("started_at")) <= held or held.timestamp() > now:
            raise Invalid("hold_time_invalid")
        hold = {"schema": HOLD_SCHEMA, "reason": data["reason"],
                "held_at": held.isoformat(), "original_lease_key_matches": True}
        data = original
    if (not isinstance(data, dict) or data.get("schema") != LEASE_SCHEMA
            or data.get("key") != run or data.get("label") != run):
        raise Invalid("marker_schema_or_run_mismatch")
    pid = integer(data.get("pid"), "pid", 1, 2**31-1)
    started = timestamp(data.get("started_at"))
    age = now - started.timestamp()
    if age < 0:
        raise Invalid("marker_time_in_future")
    source = data.get("source_sha256")
    if source is not None and (not isinstance(source, str) or not HEX.fullmatch(source)):
        raise Invalid("invalid_marker_source_hash")
    result = {"file": metadata(info), "marker_sha256": hashlib.sha256(raw).hexdigest(),
              "pid": pid, "started_at": started.isoformat(),
              "elapsed_since_marker_seconds": round(age, 3),
              "source_sha256": source, "process_generation_proven": False,
              "root_identity_proven": False}
    if hold is not None:
        result["reconciliation_hold"] = hold
    return result


def rc_file(reader, run):
    raw, info = reader.read(("lanes", "ext", f"lanes_{run}.rc"), 16)
    if not re.fullmatch(rb"(?:0|[1-9][0-9]{0,2})\n?", raw):
        raise Invalid("invalid_returncode")
    value = integer(int(raw), "returncode", 0, 255)
    return {"file": metadata(info), "returncode": value,
            "terminal_acceptance_proven": False}


def stdout_metadata(reader, run):
    _, info = reader.read(("lanes", "ext", f"lanes_{run}.stdout"),
                          0, content=False)
    return {"file": metadata(info), "content_read": False,
            "useful_progress_proven": False}


def process_receipt(reader, run):
    raw, info = reader.read(("lanes", "ext", "lanes", run+".process.jsonl"), 65536)
    if not raw or not raw.endswith(b"\n"):
        raise Invalid("incomplete_process_receipt")
    lines = raw.splitlines()
    if len(lines) > 64:
        raise Invalid("process_record_limit")
    summary = None
    for line in lines:
        data = strict_json(line)
        if (not isinstance(data, dict) or data.get("schema") != PROCESS_SCHEMA
                or data.get("label") != run):
            raise Invalid("process_schema_or_run_mismatch")
        started, ended = timestamp(data.get("started_at")), timestamp(data.get("ended_at"))
        if ended < started:
            raise Invalid("process_time_order")
        summary = {"pid": integer(data.get("pid"), "pid", 1, 2**31-1),
                   "started_at": started.isoformat(), "ended_at": ended.isoformat(),
                   "returncode": integer(data.get("returncode"), "returncode", -255, 255)}
        for key in ("timed_out", "stdout_truncated", "stderr_truncated"):
            if type(data.get(key)) is not bool:
                raise Invalid("invalid_process_flag")
            summary[key] = data[key]
        for key in ("stdout_bytes", "stderr_bytes"):
            summary[key] = integer(data.get(key), key)
        # Cleanup is reported as recorded, not promoted to a lifecycle verdict.
        cleanup = data.get("cleanup")
        if not isinstance(cleanup, dict):
            raise Invalid("invalid_cleanup_record")
        summary["recorded_cleanup"] = {}
        for key in ("identity_verified", "stdout_capture_complete",
                    "stderr_capture_complete", "stdin_delivery_complete"):
            if key in cleanup:
                if type(cleanup[key]) is not bool:
                    raise Invalid("invalid_cleanup_flag")
                summary["recorded_cleanup"][key] = cleanup[key]
    return {"file": metadata(info), "records": len(lines), "last_record": summary,
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "original_child_identity_proven": False, "accepted": False}


def proc_observation(pid, uid):
    # No ps, cmdline, environ, signal-zero probe, or alternative platform path.
    try:
        proc_root = Reader(PROC_ROOT, uid, require_final_owner=False)
    except FileNotFoundError:
        raise Invalid("procfs_unavailable") from None
    with proc_root as proc:
        proc.descend(str(pid))
        if os.fstat(proc.fds[-1]).st_uid != uid:
            raise Invalid("pid_owner_mismatch")
        raw, _ = proc.read(("stat",), 4096, proc=True)
    text = raw.decode("ascii")
    split = text.rfind(") ")
    if split < 0 or text.partition(" (")[0] != str(pid):
        raise Invalid("invalid_proc_stat")
    fields = text[split+2:].split()
    if len(fields) < 20 or fields[0] not in {"R", "S", "D", "Z", "T", "t", "X", "x", "K", "W", "P", "I"}:
        raise Invalid("invalid_proc_stat")
    if not re.fullmatch(r"[0-9]{1,20}", fields[19]):
        raise Invalid("invalid_proc_start_ticks")
    return {"observed_pid_present": True, "state": fields[0],
            "start_ticks": int(fields[19]), "original_child_identity_proven": False,
            "useful_progress_proven": False}


def observe(run_id, expected_support_digest, *, observe_pid=False):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise Invalid("invalid_run_id")
    if not isinstance(expected_support_digest, str) or not HEX.fullmatch(expected_support_digest):
        raise Invalid("invalid_support_digest")
    if type(observe_pid) is not bool:
        raise Invalid("invalid_observe_pid")
    report = {"schema": "mastermind.run_observation.v1", "run_id": run_id,
              "expected_support_digest": expected_support_digest,
              "status": "unavailable", "observations": {},
              "limits": ["Not an atomic cross-file snapshot",
                         "Support hashes do not attest a running process",
                         "PID presence does not prove original child identity or progress",
                         "No lifecycle, acceptance, retry, cancellation, or release decision"]}
    observations = report["observations"]
    now = time.time()
    try:
        uid = os.getuid()
        home = pwd.getpwuid(uid).pw_dir  # never HOME or caller-supplied cwd
        with Reader(home, uid) as reader:
            observations["support"] = capture(lambda: support(reader, expected_support_digest))
            if observations["support"]["status"] != "observed":
                report["reason"] = "original_support_unverified"
                return report
            for name, fn in (("marker", lambda: marker(reader, run_id, now)),
                             ("returncode", lambda: rc_file(reader, run_id)),
                             ("stdout", lambda: stdout_metadata(reader, run_id)),
                             ("process_receipt", lambda: process_receipt(reader, run_id))):
                observations[name] = capture(fn)
            if observe_pid and observations["marker"]["status"] == "observed":
                observations["pid"] = capture(lambda: proc_observation(observations["marker"]["pid"], uid))
                if observations["pid"]["status"] == "absent":
                    observations["pid"]["observed_pid_present"] = False
                    observations["pid"]["original_child_identity_proven"] = False
            elif observe_pid:
                observations["pid"] = {"status": "unavailable", "reason": "validated_marker_required"}
            reader.verify()
        report["status"] = ("unavailable" if any(
            value["status"] == "unavailable" for value in observations.values()) else "observed")
        if report["status"] == "unavailable":
            report["reason"] = "one_or_more_observations_unavailable"
    except OSError as exc:
        report["reason"] = ("os_permission_denied" if exc.errno in (errno.EACCES, errno.EPERM)
                            else "filesystem_unavailable")
        report["errno"] = exc.errno
        report["request_stopped"] = True
    except (Invalid, KeyError) as exc:
        report["reason"] = str(exc) if isinstance(exc, Invalid) else "account_home_unavailable"
    report["observed_at"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    return report


def observe_reserved(run_id):
    """Exact original reservation diagnosis; never assert launch/source identity.

    The controller failed before retaining its support digest. That prevents
    source attestation, but does not prevent a separately scoped metadata read.
    Reuse every directory/file guard. No stdout contents or process probes.
    """
    if run_id != "gmi-w3b-clock-patch-20261010-astra-001":
        raise Invalid("reservation_scope_not_admitted")
    now = time.time()
    report = {"schema": "mastermind.run_observation.v1", "run_id": run_id,
              "expected_support_digest": None, "status": "unavailable",
              "reason": "original_support_not_recorded",
              "observations": {"support": {"status": "unavailable",
                  "reason": "not_recorded_before_controller_failure"}},
              "limits": ["Not an atomic cross-file snapshot",
                         "Support hashes do not attest a running process",
                         "PID presence does not prove original child identity or progress",
                         "No lifecycle, acceptance, retry, cancellation, or release decision"]}
    try:
        uid = os.getuid()
        with Reader(pwd.getpwuid(uid).pw_dir, uid) as reader:
            for name, fn in (("marker", lambda: marker(reader, run_id, now)),
                             ("returncode", lambda: rc_file(reader, run_id)),
                             ("stdout", lambda: stdout_metadata(reader, run_id)),
                             ("process_receipt", lambda: process_receipt(reader, run_id))):
                report["observations"][name] = capture(fn)
            reader.verify()
    except OSError as exc:
        report["reason"] = ("os_permission_denied" if exc.errno in (errno.EACCES, errno.EPERM)
                            else "filesystem_unavailable")
        report["errno"] = exc.errno
        report["request_stopped"] = True
    except (Invalid, KeyError) as exc:
        report["reason"] = str(exc) if isinstance(exc, Invalid) else "account_home_unavailable"
    report["observed_at"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--expected-support-digest", required=True)
    parser.add_argument("--observe-pid", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = observe(args.run_id, args.expected_support_digest, observe_pid=args.observe_pid)
    except Invalid as exc:
        result = {"status": "unavailable", "reason": str(exc)}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "observed" else 78


if __name__ == "__main__":
    raise SystemExit(main())

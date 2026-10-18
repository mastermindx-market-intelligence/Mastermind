"""Dormant live-origin interval owner for the exact DUE10 forward transition.

The production composer selects this fixed owner only after its source-owned
forward policy is authorized; that policy remains ``None``. No service,
socket, permission or provider effect occurs at import. The incident-only v2
observation preserves a stopped frozen Relay's historical provenance while
the four authority roles use the current release. Generic convergence remains
strict, and source tests do not qualify any physical recovery operation.

Guarantee scope (accepted decision d9f51538): sampled observation, never a
globally atomic census.  The original root installer retains its live
observation resources; one directly spawned, source-owned UID450 child carries
observations to the canonical broker over the single accepted connection.
Drift, death or EOF before the effect attempt refuses cleanly; after the
canonical action has been submitted the same detection retains uncertainty and
never relabels it as success or clean custody.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import selectors
import stat
import subprocess
import sys
import time
from typing import Any, Mapping

from control_plane import executive_installed_peer as peer
from control_plane import executive_release_observation as release
from control_plane import executive_incident_release_observation as incident_release
from control_plane import executive_recovery_host_observation as host
from control_plane import executive_recovery_namespace as namespace
from control_plane.executive_process_identity import (
    _observe_process_instance as _observe_native_instance,
)
from control_plane.executive_recovery_observation_normalization import Instance

__all__ = ()

_ORIGIN_CLIENT_RELATIVE = "scripts/executive_os_incident_foreground_client.py"
_SERVICE_UID = 450
_SERVICE_GID = 450
_BROKER_LABEL = "com.mastermind.executive.privileged"
_BROKER_PLIST = "/Library/LaunchDaemons/com.mastermind.executive.privileged.plist"
_BROKER_SERVICE = "system/" + _BROKER_LABEL
_ROLES = ("control", "worker", "relay", "gateway", "broker")
_ENABLE_ARGV = ("/bin/launchctl", "enable", _BROKER_SERVICE)
_BOOTSTRAP_ARGV = ("/bin/launchctl", "bootstrap", "system", _BROKER_PLIST)
_PRINT_BROKER_ARGV = ("/bin/launchctl", "print", _BROKER_SERVICE)
_ORIGIN_COMMANDS = (_ENABLE_ARGV, _BOOTSTRAP_ARGV, _PRINT_BROKER_ARGV)
# The one fixed direct-child launch shape.  No caller argv, path, uid, fd or
# callback is ever accepted; the pinned signed interpreter runs exactly one
# fixed root-owned sealed entrypoint from the exact installed release.
# Launch the already-qualified signed main image directly: the pythonw wrapper
# performs another exec, which cannot be adopted after first-generation binding.
_CHILD_ARGV_PREFIX = (peer._PYTHON_MAIN_EXECUTABLE, "-I", "-S", "-B")
_CHILD_ENVIRONMENT = {
    "HOME": "/var/empty",
    "LANG": "C",
    "LC_ALL": "C",
    "NO_COLOR": "1",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "PYTHONUNBUFFERED": "1",
    "TZ": "UTC",
}
_MAX_FRAME_BYTES = 65536
_WIRE_VERSION = 2
_MAX_WITNESS_EXCHANGES = 16
_MAX_STDERR_BYTES = 65536
_SETTLE_GRACE_SECONDS = 1.0
_KILL_GRACE_SECONDS = 0.5


class OriginIntervalError(ValueError):
    """Closed nonsecret origin refusal; no reflected payload."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise OriginIntervalError(code) from None


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _require_instance(value: Any, *, code: str) -> Instance:
    if (
        type(value) is not Instance
        or type(value.pid) is not int
        or not 0 < value.pid < 2**31
        or type(value.unique_id) is not int
        or not 0 < value.unique_id < 2**64
        or type(value.pidversion) is not int
        or not 0 < value.pidversion < 2**31
    ):
        _refuse(code)
    return value


def _instance_record(instance: Instance) -> dict:
    return {
        "pid": instance.pid,
        "unique_id": instance.unique_id,
        "pidversion": instance.pidversion,
    }


def _release_root(release_commit: str) -> str:
    if (
        type(release_commit) is not str
        or len(release_commit) != 40
        or any(char not in "0123456789abcdef" for char in release_commit)
        or set(release_commit) == {"0"}
    ):
        _refuse("ORIGIN_RELEASE_IDENTITY_MALFORMED")
    return release._RELEASES + release_commit


def _canonical_socket_digest(budget: release._Budget) -> str:
    """Digest of the one fixed socket node; shape checked, never created."""
    info = budget.call(peer._lstat, namespace._CANONICAL)
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != 450
        or info.st_gid != 453
        or stat.S_IMODE(info.st_mode) != 0o660
        or info.st_nlink != 1
    ):
        _refuse("ORIGIN_SOCKET_PROFILE_DRIFT")
    payload = json.dumps(
        list(peer._object_identity(info)), separators=(",", ":")
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _run_origin_command(argv: tuple, budget: release._Budget) -> tuple:
    """Closed owned launcher readback; bounded pipes and complete cleanup."""
    if type(argv) is not tuple or argv not in _ORIGIN_COMMANDS:
        _refuse("ORIGIN_COMMAND_REFUSED")
    return _run_owned_native_command(argv, budget)


def _run_owned_native_command(argv: tuple, budget: release._Budget) -> tuple:
    """Internal process mechanic; trusted callers own their fixed verb lists.

    No request, environment or public CLI selects this callable or its argv.
    The original origin entry retains its narrower command fence above.
    """
    budget.check(force=True)
    end = min(budget.endpoint, time.monotonic_ns() + 3_000_000_000)
    process = None
    selector = None
    failure = None
    result = None
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=peer._LAUNCHD_ENVIRONMENT,
            close_fds=True,
        )
        selector = selectors.DefaultSelector()
        output = [bytearray(), bytearray()]
        for index, stream in enumerate((process.stdout, process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, index)
        while selector.get_map():
            budget.check(force=True)
            remaining = (end - time.monotonic_ns()) / 1_000_000_000
            if remaining <= 0:
                _refuse("ORIGIN_COMMAND_TIMEOUT")
            for key, _ in selector.select(min(remaining, 0.05)):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    output[key.data].extend(chunk)
                    if sum(map(len, output)) > 65536:
                        _refuse("ORIGIN_COMMAND_OUTPUT_TOO_LARGE")
        remaining = min(budget.remaining(), (end - time.monotonic_ns()) / 1_000_000_000)
        if remaining <= 0:
            _refuse("ORIGIN_COMMAND_TIMEOUT")
        result = (process.wait(timeout=remaining), bytes(output[0]), bytes(output[1]))
    except BaseException as error:
        failure = error
    finally:
        cleanup = []
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=min(0.5, max(0.0, (budget.endpoint - time.monotonic_ns()) / 1e9)))
            except BaseException as error:
                cleanup.append(error)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as error:
                        cleanup.append(error)
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                cleanup.append(error)
        if failure is None and cleanup:
            failure = cleanup[0]
    if failure is not None:
        raise failure
    budget.check(force=True)
    return result


def _broker_load_state(budget: release._Budget) -> str:
    """Strict bootstrap readback: anything but the exact absence is loaded."""
    rc, out, err = _run_origin_command(_PRINT_BROKER_ARGV, budget)
    if type(rc) is not int or rc != 0 or err:
        _refuse("ORIGIN_BOOTSTRAP_READBACK_UNAVAILABLE")
    try:
        if release._exact_unloaded_reply(_BROKER_LABEL, rc, out, err):
            _refuse("ORIGIN_BOOTSTRAP_READBACK_UNLOADED")
    except release.ReleaseObservationError:
        _refuse("ORIGIN_BOOTSTRAP_READBACK_UNAVAILABLE")
    return "LOADED"


class _OriginChild:
    """The actual root-owned Popen child and its retained pipe handles."""

    def __init__(self, process, forward_request_sha256: str, request, origin):
        self.process = process
        self.pid = process.pid
        self.instance = None
        self.forward_request_sha256 = forward_request_sha256
        self.request = request
        self.origin = origin
        self.settled = False
        self.returncode = None


@dataclass(frozen=True)
class _OriginResult:
    classification: str
    response: dict | None
    refusal: str | None
    returncode: int | None
    exchanges: int
    transcript_sha256: str


class _OriginInterval:
    """One original live-origin interval; endpoint never renewed.

    Phases: ``EXCLUSIVE`` (pre-bootstrap custody), ``OBSERVATION_ONLY`` (after
    the single owner bootstrap; no further publish/arm method exists) and
    ``CLOSED``.  Any refusal inside an operation latches ``failed``; a failed
    interval can never resume mutation.
    """

    def __init__(
        self,
        *,
        boot_id: str,
        release_commit: str,
        cohort_content_sha256: str,
        observer: Instance,
        deadline_monotonic_ns: int,
        handles,
        started_monotonic_ns: int,
        completed_monotonic_ns: int,
    ):
        self.boot_id = boot_id
        self.release_commit = release_commit
        if not _hex(cohort_content_sha256):
            _refuse("ORIGIN_COHORT_DIGEST_MALFORMED")
        self.cohort_content_sha256 = cohort_content_sha256
        self.observer = observer
        self.deadline_monotonic_ns = deadline_monotonic_ns
        self.started_monotonic_ns = started_monotonic_ns
        self.completed_monotonic_ns = completed_monotonic_ns
        self._handles = handles
        self.phase = "EXCLUSIVE"
        self.failed = False
        self.bootstrapped = False
        self.closed = False
        self.child = None
        self.bootstrap_attempted = False
        self._socket_anchor = None
        self._held_budget = release._Budget(deadline_monotonic_ns)

    def _budget(self) -> release._Budget:
        # Always the SAME original absolute endpoint; never a fresh window.
        return self._held_budget

    def _check_usable(self) -> None:
        if self.failed:
            _refuse("ORIGIN_INTERVAL_FAILED")
        if self.closed or self.phase == "CLOSED":
            _refuse("ORIGIN_INTERVAL_CLOSED")

    def bootstrap_once(self) -> None:
        """The single fixed owner bootstrap; observation-only afterwards."""
        self._check_usable()
        if self.bootstrap_attempted or self.bootstrapped or self.phase != "EXCLUSIVE":
            _refuse("ORIGIN_BOOTSTRAP_UNAVAILABLE")
        try:
            budget = self._budget()
            whole = budget.call(
                incident_release._observe_incident_release,
                deadline_monotonic_ns=self.deadline_monotonic_ns,
            )
            if whole.boot_id != self.boot_id:
                _refuse("ORIGIN_BOOT_DRIFT")
            incident_release._validate_observation(whole)
            if (whole.cohort_content_sha256 != self.cohort_content_sha256
                    or any(row.state != "UNLOADED" for row in whole.roles[:3])):
                _refuse("ORIGIN_COHORT_DRIFT")
            if tuple(role.role for role in whole.roles) != _ROLES:
                _refuse("ORIGIN_PUBLICATION_INCOHERENT")
            if whole.roles[-1].role != "broker" or whole.roles[-1].state != "UNLOADED":
                _refuse("ORIGIN_BROKER_STILL_PUBLISHED")
            if whole.roles[0].content.release_commit != self.release_commit:
                _refuse("ORIGIN_SOURCE_DRIFT")
            budget.call(namespace._require_socket_absent, self._handles)
            self.bootstrap_attempted = True  # burned before the first possible effect
            rc, out, err = _run_origin_command(_ENABLE_ARGV, budget)
            if type(rc) is not int or rc != 0 or err:
                _refuse("ORIGIN_ENABLE_REFUSED")
            rc, out, err = _run_origin_command(_BOOTSTRAP_ARGV, budget)
            if type(rc) is not int or rc != 0 or err:
                _refuse("ORIGIN_BOOTSTRAP_REFUSED")
            _broker_load_state(budget)
            budget.call(namespace._recheck_namespace, self._handles)
            self._socket_anchor = budget.call(namespace._observe_socket_node, self._handles)
            self.bootstrapped = True
            self.phase = "OBSERVATION_ONLY"
            budget.check(force=True)
        except BaseException:
            self.failed = True
            raise

    def close_once(self) -> None:
        """Release the held namespace observation handles exactly once."""
        if self.closed:
            _refuse("ORIGIN_INTERVAL_CLOSED")
        self.closed = True
        self.phase = "CLOSED"
        # Own observation resources only; no durable evidence, socket node or
        # service belonging to any owner is ever removed here.
        namespace._release_namespace(self._handles)

    def _settle_child(self, child: _OriginChild) -> int | None:
        """Bounded once-only reap/close of the born child; uncertainty kept."""
        if child.settled:
            _refuse("ORIGIN_CHILD_ALREADY_SETTLED")
        child.settled = True
        failures = []
        try:
            child.process.stdin.close()
        except BaseException as error:
            failures.append(error)
        code = None
        try:
            budget = self._budget()
            remaining = min(_SETTLE_GRACE_SECONDS, max(0.0, budget.remaining()))
            code = child.process.wait(timeout=remaining)
        except BaseException as error:
            failures.append(error)
            try:
                child.process.kill()
            except BaseException as error:
                failures.append(error)
            try:
                child.process.wait(timeout=min(_KILL_GRACE_SECONDS, max(0.0, (self.deadline_monotonic_ns - time.monotonic_ns()) / 1e9)))
            except BaseException as error:
                failures.append(error)
        for stream in (child.process.stdout, child.process.stderr):
            try:
                stream.close()
            except BaseException as error:
                failures.append(error)
        child.returncode = code if type(code) is int else None
        if failures:
            # A failed cleanup is retained as uncertainty; it is never reported
            # as clean settlement and never retried on a reused handle.
            _refuse("ORIGIN_CHILD_SETTLE_UNPROVEN")
        return child.returncode

    def _abandon_child(self, child: _OriginChild) -> None:
        """Best-effort settle that never masks the caller's primary refusal."""
        try:
            self._settle_child(child)
        except BaseException:
            pass


def _installed_incident_observation(budget: release._Budget, boot_id: str):
    whole = budget.call(incident_release._observe_incident_release, deadline_monotonic_ns=budget.endpoint)
    incident_release._validate_observation(whole)
    if whole.boot_id != boot_id:
        _refuse("ORIGIN_BOOT_DRIFT")
    if tuple(role.role for role in whole.roles) != _ROLES:
        _refuse("ORIGIN_PUBLICATION_INCOHERENT")
    if any(row.state != "UNLOADED" for row in whole.roles[:3]):
        _refuse("ORIGIN_CONSUMERS_NOT_STOPPED")
    return whole


def _enter_origin_interval(*, deadline_monotonic_ns: int) -> _OriginInterval:
    """Open the one original interval; strict PRE-bootstrap exclusion only.

    This is not ``_observe_old_owner_exclusion`` after bootstrap: the RUNNING
    origin/broker bindings come from :func:`_observe_running_owner_set` later,
    never from re-running the pre-bootstrap predicate at a RUNNING stage.
    """
    if type(deadline_monotonic_ns) is not int or not 0 < deadline_monotonic_ns < 2**63:
        _refuse("ORIGIN_DEADLINE_INVALID")
    handles = None
    try:
        budget = release._Budget(deadline_monotonic_ns)
        if sys.platform != "darwin" or os.geteuid() != 0:
            _refuse("ORIGIN_PRINCIPAL_UNQUALIFIED")
        boot = budget.call(release._boot, budget)
        observer = budget.call(host._instance, os.getpid(), budget)
        _require_instance(observer, code="ORIGIN_OBSERVER_IDENTITY_UNAVAILABLE")
        handles = namespace._acquire_namespace(deadline_monotonic_ns=deadline_monotonic_ns)
        budget.check(force=True)
        budget.call(namespace._require_socket_absent, handles)
        budget.call(
            host._observe_old_owner_exclusion,
            deadline_monotonic_ns=deadline_monotonic_ns,
        )
        if budget.call(release._boot, budget) != boot:
            _refuse("ORIGIN_BOOT_DRIFT")
        whole = _installed_incident_observation(budget, boot)
        budget.check(force=True)
        interval = _OriginInterval(
            boot_id=boot,
            release_commit=whole.roles[0].content.release_commit,
            cohort_content_sha256=whole.cohort_content_sha256,
            observer=observer,
            deadline_monotonic_ns=deadline_monotonic_ns,
            handles=handles,
            started_monotonic_ns=budget.started,
            completed_monotonic_ns=budget.last,
        )
        interval._held_budget = budget
        return interval
    except BaseException:
        # A failed entry never leaves held handles behind; release once.
        if handles is not None:
            try:
                namespace._release_namespace(handles)
            except namespace.NamespaceObservationError:
                pass
        raise


def _forward_module():
    from ops.executive_os import provider_incident_forward as forward

    return forward


def _sealed_client_entrypoint(budget: release._Budget, origin: _OriginInterval) -> str:
    root = _release_root(origin.release_commit)
    path = root + "/" + _ORIGIN_CLIENT_RELATIVE
    # Custody read only; the fixed launch from this trusted factory is the
    # source admission, not a kernel proof of script identity.
    raw, info = budget.call(
        peer._read_trusted_bytes,
        path,
        budget=budget,
        maximum=262144,
        expected_mode=0o644,
        expected_gid=0,
    )
    manifest_raw, _ = budget.call(peer._read_trusted_bytes, root + "/.executive-release-manifest.json",
        budget=budget, maximum=peer._MAX_READ_BYTES, expected_mode=0o444, expected_gid=0)
    manifest = peer._load_strict_json(manifest_raw, code="ORIGIN_MANIFEST_MALFORMED")
    rows = [row for row in manifest.get("entries", ()) if row.get("path") == _ORIGIN_CLIENT_RELATIVE]
    if manifest.get("commit_sha") != origin.release_commit or len(rows) != 1 or rows[0] != {
            "path": _ORIGIN_CLIENT_RELATIVE, "type": "file", "mode": 0o644, "uid": 0, "gid": 0,
            "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}:
        _refuse("ORIGIN_HELPER_MANIFEST_MISMATCH")
    return path


def _require_child_parent(child: _OriginChild, observation, origin: _OriginInterval,
                          budget: release._Budget) -> Instance:
    """Bind the child to this process by native original-parent identity."""
    if (
        type(observation.unique_id) is not int
        or not 0 < observation.unique_id < 2**64
        or type(observation.pidversion) is not int
        or not 0 < observation.pidversion < 2**31
        or observation.parent_unique_id is None
        or observation.parent_pidversion is None
    ):
        _refuse("ORIGIN_CHILD_PARENT_UNAVAILABLE")
    if (
        observation.parent_unique_id != origin.observer.unique_id
        or observation.parent_pidversion != origin.observer.pidversion
    ):
        _refuse("ORIGIN_CHILD_PARENT_MISMATCH")
    instance = Instance(child.pid, observation.unique_id, observation.pidversion)
    budget.check(force=True)
    return instance


def _spawn_origin_client(origin: _OriginInterval, request: Mapping) -> _OriginChild:
    """The one fixed direct UID450 child; retains actual Popen/pipe handles."""
    if type(origin) is not _OriginInterval:
        _refuse("ORIGIN_INTERVAL_REQUIRED")
    origin._check_usable()
    if origin.phase != "OBSERVATION_ONLY" or not origin.bootstrapped:
        _refuse("ORIGIN_CLIENT_SPAWN_UNAVAILABLE")
    if origin.child is not None:
        _refuse("ORIGIN_CHILD_ALREADY_BORN")
    child = None
    try:
        if not isinstance(request, Mapping):
            _refuse("ORIGIN_ACTION_MALFORMED")
        forward = _forward_module()
        validated, forward_digest = forward.validate_forward_request(dict(request))
        if type(validated) is not forward.PrivilegedActionRequest:
            _refuse("ORIGIN_ACTION_MALFORMED")
        budget = origin._budget()
        entrypoint = _sealed_client_entrypoint(budget, origin)
        argv = _CHILD_ARGV_PREFIX + (entrypoint,)
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=_release_root(origin.release_commit),
            env=dict(_CHILD_ENVIRONMENT),
            user=_SERVICE_UID,
            group=_SERVICE_GID,
            extra_groups=[],
            close_fds=True,
            bufsize=0,
        )
        child = _OriginChild(process, forward_digest, validated, origin)
        origin.child = child
        budget.check(force=True)
        observation = budget.call(_observe_native_instance, child.pid)
        child.instance = _require_child_parent(child, observation, origin, budget)
        budget.check(force=True)
        return child
    except BaseException:
        # A child that reached birth is settled immediately and the interval
        # latches the failure; a pre-spawn validation refusal stays retryable
        # with a corrected exact request because nothing was ever born.
        if child is not None:
            origin.failed = True
            origin._abandon_child(child)
        raise


# One closed protocol shared by the parent, child and broker context.
_STAGES = ("before_preflight", "before_reservation", "before_reservation_attempt",
           "before_grant", "before_terminal", "before_settlement", "after_settlement")
_WITNESS = {"kind", "v", "stage", "ordinal", "nonce", "reservation_sha256",
            "deadline_monotonic_ns", "binding_sha256"}
_OBS = {"kind", "v", "stage", "ordinal", "boot_id", "release_commit", "origin",
        "broker", "socket_sha256", "deadline_monotonic_ns", "binding_sha256",
        "purpose", "cohort_content_sha256"}
_ACQUIRE = {"kind", "v", "nonce", "binding", "binding_sha256", "deadline_monotonic_ns"}
_CLOSE = {"kind", "v", "nonce", "ordinal", "binding_sha256"}


def _shape(frame, keys, kind):
    if (type(frame) is not dict or set(frame) != set(keys) or frame.get("kind") != kind
            or type(frame.get("v")) is not int or frame["v"] != _WIRE_VERSION):
        _refuse("ORIGIN_FRAME_MALFORMED")


def _hex(value, size=64):
    return type(value) is str and len(value) == size and all(c in "0123456789abcdef" for c in value)


def _tighten(budget, endpoint):
    budget.check(force=True)
    if type(endpoint) is not int or not 0 < endpoint < 2**63:
        _refuse("ORIGIN_ENDPOINT_INVALID")
    budget.endpoint = min(budget.endpoint, endpoint)
    budget.check(force=True)
    return budget.endpoint


def _binding_payload(request, source, policy, nonce):
    forward = _forward_module()
    validated, digest = forward.validate_forward_request(request)
    args = validated.args_dict()
    if (args["expected_current_release_sha"] != source["release_sha"] or
            args["expected_current_manifest_sha256"] != source["manifest_sha256"]):
        _refuse("ORIGIN_SOURCE_BINDING_MISMATCH")
    return {"I": forward.ORIGINAL_ISSUER_REQUEST_ID, "D": forward.ORIGINAL_REQUEST_SHA256,
            "M": forward.ORIGINAL_MARKER_SHA256, "R": forward.ORIGINAL_RELEASE_SHA,
            "Q": forward.SUCCESSOR_REQUEST_ID, "F": digest, "source": dict(source),
            "policy": dict(policy), "nonce": nonce,
            "observation_purpose": incident_release._PURPOSE}


class _FrameBuffer:
    def __init__(self):
        self.pending = bytearray()

    def extract(self, *, code_prefix):
        newline = self.pending.find(b"\n")
        if newline < 0:
            if len(self.pending) >= _MAX_FRAME_BYTES:
                _refuse(code_prefix + "_FRAME_TOO_LARGE")
            return None
        if newline + 1 > _MAX_FRAME_BYTES:
            _refuse(code_prefix + "_FRAME_TOO_LARGE")
        line = bytes(self.pending[:newline])
        del self.pending[:newline + 1]
        return line

    def feed(self, chunk, *, code_prefix):
        self.pending.extend(chunk)
        if len(self.pending) > _MAX_FRAME_BYTES + 4096:
            _refuse(code_prefix + "_FRAME_TOO_LARGE")


def _parse_frame_line(line, *, code_prefix):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        value = json.loads(line.decode("ascii", "strict"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
    except (UnicodeError, ValueError, RecursionError):
        _refuse(code_prefix + "_FRAME_MALFORMED")
    if type(value) is not dict:
        _refuse(code_prefix + "_FRAME_MALFORMED")
    return value


def _stream_frame(stream, buffer, budget):
    # Real pipes always use nonblocking descriptors; in-memory streams exist
    # only in unit tests. No buffered read or flush can wait beyond the budget.
    try:
        fd = stream.fileno()
    except (AttributeError, OSError):
        fd = None
    while True:
        budget.check(force=True)
        line = buffer.extract(code_prefix="ORIGIN_PIPE")
        if line is not None:
            return _parse_frame_line(line, code_prefix="ORIGIN_PIPE")
        if fd is None:
            chunk = stream.read(4096)
        else:
            os.set_blocking(fd, False)
            with selectors.DefaultSelector() as selector:
                selector.register(fd, selectors.EVENT_READ)
                if not selector.select(min(.05, budget.remaining())):
                    continue
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
        if not chunk:
            if buffer.pending:
                _refuse("ORIGIN_PIPE_PARTIAL_EOF")
            return None
        buffer.feed(chunk, code_prefix="ORIGIN_PIPE")


def _stream_send(stream, value, budget):
    raw = _canonical(value)
    if len(raw) > _MAX_FRAME_BYTES:
        _refuse("ORIGIN_PIPE_FRAME_TOO_LARGE")
    try:
        fd = stream.fileno()
    except (AttributeError, OSError):
        fd = None
    view = memoryview(raw)
    while view:
        budget.check(force=True)
        if fd is None:
            written = stream.write(view)
        else:
            os.set_blocking(fd, False)
            with selectors.DefaultSelector() as selector:
                selector.register(fd, selectors.EVENT_WRITE)
                if not selector.select(min(.05, budget.remaining())):
                    continue
            try:
                written = os.write(fd, view)
            except BlockingIOError:
                continue
        if type(written) is not int or written <= 0:
            _refuse("ORIGIN_PIPE_CLOSED")
        view = view[written:]
    budget.check(force=True)


def _write_child_frame(child, value, budget):
    _stream_send(child.process.stdin, value, budget)


def _observe_running_owner_set(budget: release._Budget, *,
                               origin_instance: Instance,
                               broker_observation) -> "_RunningOwnerSet":
    """Exact RUNNING owner set {origin, broker} over the complete root rows.

    Retains every census row; other nonmatching root rows stay observed and
    classified, never discarded.  The only inventory-child exclusion is the
    settled native inventory child already owned by the census runner.  No
    wire PID list or caller exemption enters here, and this is a sampled
    observation, never an atomic origin-liveness lock.
    """
    if type(budget) is not release._Budget:
        _refuse("ORIGIN_BUDGET_REQUIRED")
    if type(broker_observation) is not incident_release._IncidentReleaseObservation:
        _refuse("ORIGIN_RELEASE_OBSERVATION_REQUIRED")
    incident_release._validate_observation(broker_observation)
    if any(row.state != "UNLOADED" for row in broker_observation.roles[:3]):
        _refuse("ORIGIN_CONSUMERS_NOT_STOPPED")
    _require_instance(origin_instance, code="ORIGIN_OWNER_INSTANCE_MALFORMED")
    if tuple(role.role for role in broker_observation.roles) != _ROLES:
        _refuse("ORIGIN_ROLE_SET_REFUSED")
    record = broker_observation.roles[-1]
    if record.role != "broker" or record.state != "RUNNING":
        _refuse("ORIGIN_BROKER_NOT_RUNNING")
    broker_instance = budget.call(host._instance, record.pid, budget)
    _require_instance(broker_instance, code="ORIGIN_BROKER_INSTANCE_UNAVAILABLE")
    if (
        broker_instance.pid != record.pid
        or broker_instance.unique_id != record.unique_id
        or broker_instance.pidversion != record.pidversion
    ):
        _refuse("ORIGIN_BROKER_INSTANCE_DRIFT")
    if origin_instance == broker_instance:
        _refuse("ORIGIN_OWNER_SET_COLLAPSED")
    census = budget.call(host._root_census, budget)
    observer = census.observer
    if observer != origin_instance and observer != broker_instance:
        _refuse("ORIGIN_OBSERVER_FOREIGN")
    rows_by_pid = {row.instance.pid: row for row in census.rows}
    matching = set(census.matching_runtime_instances)
    for needed in (origin_instance, broker_instance):
        row = rows_by_pid.get(needed.pid)
        if row is None or row.instance != needed:
            _refuse("ORIGIN_OWNER_ROW_MISSING")
        if needed not in matching:
            _refuse("ORIGIN_OWNER_IMAGE_UNQUALIFIED")
    if matching != {origin_instance, broker_instance}:
        _refuse("ORIGIN_EXTRA_ROOT_INTERPRETER")
    if budget.call(release._boot, budget) != broker_observation.boot_id:
        _refuse("ORIGIN_BOOT_DRIFT")
    budget.check(force=True)
    return _RunningOwnerSet(
        origin_instance=origin_instance,
        broker_instance=broker_instance,
        observer=observer,
        rows=census.rows,
        boot_id=broker_observation.boot_id,
    )


@dataclass(frozen=True)
class _RunningOwnerSet:
    origin_instance: Instance
    broker_instance: Instance
    observer: Instance
    rows: tuple
    boot_id: str


_CHALLENGE_KEYS = frozenset({
    "kind", "v", "stage", "ordinal", "nonce", "reservation_sha256",
    "deadline_monotonic_ns",
})
_OBSERVATION_KEYS = frozenset({
    "kind", "v", "stage", "ordinal", "boot_id", "release_commit",
    "origin", "broker", "socket_sha256", "purpose", "cohort_content_sha256",
})
_TERMINAL_KINDS = ("sent", "challenge", "response", "failed")


def _parent_observation(origin: _OriginInterval, stage: str, ordinal: int,
                        budget: release._Budget) -> dict:
    """Fresh independent root-side joins for one witness stage."""
    fresh = budget.call(
        incident_release._observe_incident_release, deadline_monotonic_ns=origin.deadline_monotonic_ns
    )
    incident_release._validate_observation(fresh)
    if (fresh.cohort_content_sha256 != origin.cohort_content_sha256
            or any(row.state != "UNLOADED" for row in fresh.roles[:3])):
        _refuse("ORIGIN_COHORT_DRIFT")
    owners = budget.call(
        _observe_running_owner_set,
        budget,
        origin_instance=origin.observer,
        broker_observation=fresh,
    )
    budget.call(namespace._recheck_namespace, origin._handles)
    budget.call(namespace._require_same_socket, origin._handles, origin._socket_anchor)
    socket_sha256 = hashlib.sha256(_canonical({"identity": origin._socket_anchor.identity})).hexdigest()
    if fresh.boot_id != origin.boot_id or owners.boot_id != origin.boot_id:
        _refuse("ORIGIN_BOOT_DRIFT")
    commit = fresh.roles[0].content.release_commit
    if commit != origin.release_commit:
        _refuse("ORIGIN_SOURCE_DRIFT")
    return {
        "kind": "observation",
        "v": _WIRE_VERSION,
        "stage": stage,
        "ordinal": ordinal,
        "boot_id": owners.boot_id,
        "release_commit": commit,
        "purpose": fresh.purpose,
        "cohort_content_sha256": fresh.cohort_content_sha256,
        "origin": _instance_record(owners.origin_instance),
        "broker": _instance_record(owners.broker_instance),
        "socket_sha256": socket_sha256,
    }


def _serve_origin_witnesses(origin: _OriginInterval, child: _OriginChild) -> _OriginResult:
    """One connected pump. Acknowledged attempt precedes any action byte."""
    if type(origin) is not _OriginInterval or type(child) is not _OriginChild or child is not origin.child or child.settled:
        _refuse("ORIGIN_WITNESS_CONTEXT_INVALID")
    origin._check_usable()
    budget = origin._budget()
    exchanges = 0
    attempted = acquired = closing = prechecked = False
    response = refusal = binding_digest = nonce = reservation = None
    transcript = hashlib.sha256()
    returncode = None
    cleanup_proven = True
    selector = selectors.DefaultSelector()
    buffer = _FrameBuffer()
    stderr_size = 0
    try:
        for stream in (child.process.stdout, child.process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        _write_child_frame(child, {"kind": "origin-interval", "v": _WIRE_VERSION,
            "boot_id": origin.boot_id, "release_commit": origin.release_commit,
            "purpose": incident_release._PURPOSE, "cohort_content_sha256": origin.cohort_content_sha256,
            "origin": _instance_record(origin.observer), "deadline_monotonic_ns": budget.endpoint,
            "request": child.request.to_dict(), "socket": namespace._CANONICAL}, budget)
        while response is None:
            budget.check(force=True)
            line = buffer.extract(code_prefix="ORIGIN_CHILD")
            if line is None:
                for key, _ in selector.select(min(.05, budget.remaining())):
                    try:
                        chunk = os.read(key.fileobj.fileno(), 4096)
                    except BlockingIOError:
                        continue
                    if key.fileobj is child.process.stderr:
                        stderr_size += len(chunk)
                        if stderr_size > _MAX_STDERR_BYTES:
                            _refuse("ORIGIN_CHILD_STDERR_OVERFLOW")
                        if not chunk:
                            selector.unregister(key.fileobj)
                    elif not chunk:
                        # stdout EOF must not hide already-written stderr. Its
                        # descriptor is nonblocking and the total byte bound
                        # still applies even when both channels close together.
                        while True:
                            try:
                                tail = os.read(child.process.stderr.fileno(), 4096)
                            except BlockingIOError:
                                break
                            if not tail:
                                break
                            stderr_size += len(tail)
                            if stderr_size > _MAX_STDERR_BYTES:
                                _refuse("ORIGIN_CHILD_STDERR_OVERFLOW")
                        _refuse("ORIGIN_CHILD_EOF_AFTER_SUBMISSION" if attempted else "ORIGIN_CHILD_EOF")
                    else:
                        buffer.feed(chunk, code_prefix="ORIGIN_CHILD")
                continue
            frame = _parse_frame_line(line, code_prefix="ORIGIN_CHILD")
            if not origin.closed:
                observed = budget.call(_observe_native_instance, child.pid)
                if _require_child_parent(child, observed, origin, budget) != child.instance:
                    _refuse("ORIGIN_CHILD_INSTANCE_DRIFT")
            kind = frame.get("kind")
            transcript.update(_canonical(frame))
            if kind == "need-precheck":
                _shape(frame, {"kind", "v"}, kind)
                if prechecked or attempted:
                    _refuse("ORIGIN_PRECHECK_REPLAY")
                observation = _parent_observation(origin, "precheck", 0, budget)
                observation.pop("origin"); observation.pop("stage"); observation.pop("ordinal")
                observation["kind"] = "precheck"
                _write_child_frame(child, observation, budget)
                prechecked = True
            elif kind == "sent":
                _shape(frame, {"kind", "v", "forward_request_sha256"}, kind)
                if not prechecked or attempted or frame["forward_request_sha256"] != child.forward_request_sha256:
                    _refuse("ORIGIN_SUBMISSION_REPLAY_OR_MISMATCH")
                attempted = True
                _write_child_frame(child, {"kind": "attempt-ack", "v": _WIRE_VERSION,
                    "forward_request_sha256": child.forward_request_sha256}, budget)
            elif kind == "origin-witness-acquire":
                _shape(frame, _ACQUIRE, kind)
                if not attempted or acquired or not _hex(frame["nonce"], 32):
                    _refuse("ORIGIN_ACQUISITION_REPLAY")
                forward = _forward_module()
                policy = forward.validate_forward_policy(forward.PRODUCTION_FORWARD_RECOVERY_POLICY)
                source = budget.call(forward.recovery.current_executive_source)
                expected = _binding_payload(child.request.to_dict(), source, policy, frame["nonce"])
                if (frame["binding"] != expected or frame["binding_sha256"] != hashlib.sha256(_canonical(expected)).hexdigest()
                        or source["release_sha"] != origin.release_commit):
                    _refuse("ORIGIN_BINDING_MISMATCH")
                endpoint = _tighten(budget, frame["deadline_monotonic_ns"])
                origin.deadline_monotonic_ns = endpoint
                _tighten(origin._handles.budget, endpoint)
                nonce, binding_digest = frame["nonce"], frame["binding_sha256"]
                observation = _parent_observation(origin, "acquire", 0, budget)
                observation.update(deadline_monotonic_ns=endpoint, binding_sha256=binding_digest)
                _write_child_frame(child, observation, budget)
                acquired = True
            elif kind == "origin-witness-challenge":
                _shape(frame, _WITNESS, kind)
                if (not acquired or closing or exchanges >= len(_STAGES)
                        or frame["stage"] != _STAGES[exchanges] or type(frame["ordinal"]) is not int
                        or frame["ordinal"] != exchanges + 1 or frame["nonce"] != nonce
                        or frame["binding_sha256"] != binding_digest or frame["deadline_monotonic_ns"] != budget.endpoint):
                    _refuse("ORIGIN_CHALLENGE_BINDING_MISMATCH")
                incoming = frame["reservation_sha256"]
                if exchanges < 2:
                    if incoming is not None: _refuse("ORIGIN_RESERVATION_PREMATURE")
                elif not _hex(incoming) or (reservation is not None and incoming != reservation):
                    _refuse("ORIGIN_RESERVATION_MISMATCH")
                else: reservation = incoming
                exchanges += 1
                observation = _parent_observation(origin, frame["stage"], exchanges, budget)
                observation.update(deadline_monotonic_ns=budget.endpoint, binding_sha256=binding_digest)
                _write_child_frame(child, observation, budget)
            elif kind == "origin-witness-cleanup":
                _shape(frame, _CLOSE, kind)
                if (not acquired or closing or exchanges != len(_STAGES) or frame["nonce"] != nonce
                        or frame["binding_sha256"] != binding_digest or type(frame["ordinal"]) is not int
                        or frame["ordinal"] != exchanges + 1):
                    _refuse("ORIGIN_CLOSE_BINDING_MISMATCH")
                _parent_observation(origin, "closing", exchanges + 1, budget)
                origin.close_once()
                budget.check(force=True)
                closing = True
                _write_child_frame(child, dict(frame, kind="origin-witness-cleanup-ack"), budget)
            elif kind == "response":
                _shape(frame, {"kind", "v", "response"}, kind)
                if not attempted: _refuse("ORIGIN_RESPONSE_BEFORE_ACTION")
                from control_plane.executive_privileged_client import validate_forward_recovery_response
                response = validate_forward_recovery_response(frame["response"], child.request.to_dict(),
                    expected_release_sha=origin.release_commit)
                if response["ok"] and not closing:
                    _refuse("ORIGIN_RESPONSE_BEFORE_CLEANUP")
            else:
                _refuse("ORIGIN_CHILD_FRAME_KIND_INVALID")
    except BaseException as error:
        refusal = getattr(error, "code", "ORIGIN_WITNESS_UNAVAILABLE")
    finally:
        try:
            if not origin.closed: origin.close_once()
        except BaseException:
            cleanup_proven = False
            refusal = refusal or "ORIGIN_CLEANUP_UNPROVEN"
        try:
            returncode = origin._settle_child(child)
            if type(returncode) is not int:
                cleanup_proven = False
                refusal = refusal or "ORIGIN_CHILD_SETTLE_UNPROVEN"
        except BaseException:
            cleanup_proven = False
            refusal = refusal or "ORIGIN_CHILD_SETTLE_UNPROVEN"
        selector.close()
    success = response is not None and response.get("ok") is True and closing and refusal is None and returncode == 0
    return _OriginResult("SUCCEEDED" if success else "UNKNOWN_RETAINED" if attempted or not cleanup_proven else "REFUSED_CLEAN",
        response, refusal, returncode, exchanges, transcript.hexdigest())

"""Distinct-principal worker broker for Executive OS Phase 1C-A.

The broker is deliberately smaller than a scheduler or control plane.  It runs
as the dedicated Codex worker account, accepts requests only from the configured
Executive control UID over a Unix-domain socket, and exposes five typed
operations around :class:`CodexWorkerAdapter`:

``start`` -> ``status`` -> ``collect`` / ``cancel`` and ``validate``.

There is no generic command or shell endpoint.  Validation argv must be frozen
in the start request and is matched byte-for-byte before execution.  The
production entrypoint also requires the worker UID to be dedicated to this one
broker.  That permits a residual sweep to enumerate and SIGKILL every other
process carrying the worker UID, including a descendant that deliberately
escaped its original process group or session, without broadcasting from the
broker process itself.
"""
from __future__ import annotations

import asyncio
import ctypes
import dataclasses
import datetime as dt
import enum
import hashlib
import json
import os
import platform
import re
import signal
import socket
import stat
import struct
import subprocess
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from common.redaction import sanitize_external_text
from control_plane.executive_ambient_process import (
    AmbientClassification,
    AmbientProcessClassifier,
    AmbientProcessIdentity,
    NullAmbientClassifier,
)
from control_plane.codex_worker import (
    ArtifactReceipt,
    BinaryAttestation,
    CancelReceipt,
    CodexWorkerAdapter,
    CollectionReceipt,
    GitPreflightFailed,
    GitPreflightTimeout,
    ISOLATION_MANIFEST_SCHEMA_VERSION,
    LaunchSpec,
    LaunchValidationStageError,
    ProcessIdentityError,
    ProcessRef,
    ValidationReceipt,
    WorkerResult,
    WorkerRunStatus,
)
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.operator_harness_contract import (
    CandidateResult,
    EventCursor,
    LaunchComparison,
    LaunchDecision,
    NormalizedEvent,
    ObservedHarnessAttestation,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
)
from control_plane.operator_harness_wire import (
    OperatorHarnessWireError,
    event_cursor as wire_event_cursor,
    launch_comparison as wire_launch_comparison,
    operation_id as wire_operation_id,
    process_identity_observation as wire_process_identity_observation,
    process_generation_ref as wire_process_generation_ref,
    requested_execution_profile as wire_requested_execution_profile,
    session_epoch_ref as wire_session_epoch_ref,
    provider_session_handoff as wire_provider_session_handoff,
    to_wire as operator_to_wire,
    turn_ref as wire_turn_ref,
)


BROKER_REQUEST_SCHEMA_VERSION = "mastermind.executive_worker_broker_request/v1"
BROKER_RESPONSE_SCHEMA_VERSION = "mastermind.executive_worker_broker_response/v1"
UID_SWEEP_SCHEMA_VERSION = "mastermind.executive_uid_sweep/v2"
UID_SWEEP_TERMINAL_REASONS = frozenset({"run_terminal"})
_AMBIENT_ATTRIBUTIONS = frozenset({"attested", "absent", "failed_closed"})
_AMBIENT_IDENTITY_FIELDS = frozenset(
    {
        "pid",
        "uid",
        "launchd_domain",
        "launchd_label",
        "launchd_reported_pid",
        "plist_path",
        "program_path",
        "executable_path",
        "executable_device",
        "executable_inode",
        "codesign_identifier",
        "codesign_verified",
    }
)

# Error code carried by the envelope a connection handler frames when it is
# unwound by a ``BaseException`` -- a launchd stop cancelling the in-flight
# handler, ``SystemExit``, ``KeyboardInterrupt`` -- before the operation could
# produce its own typed result.  It is deliberately distinct from
# ``InternalBrokerError`` so the control side can tell "the broker went away
# mid-request" from "the operation failed".
BROKER_UNAVAILABLE_ERROR_CODE = "BrokerUnavailableError"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OHF_OPERATIONS = frozenset(
    {
        "ohf-validate",
        "ohf-identity",
        "ohf-start",
        "ohf-resume",
        "ohf-begin-turn",
        "ohf-collect-turn",
        "ohf-interrupt",
        "ohf-stop",
        "ohf-cancel",
        "ohf-reconcile",
        "ohf-reconcile-absence",
    }
)
_ALLOWED_OPERATIONS = frozenset(
    {"start", "status", "collect", "cancel", "validate"}
) | _OHF_OPERATIONS
_MAX_REQUEST_BYTES = 1024 * 1024
_MAX_OPERATOR_PROMPT_BYTES = 512 * 1024
_MAX_VALIDATION_COMMANDS = 32
_MAX_VALIDATION_ARGS = 128
_MAX_VALIDATION_BYTES = 64 * 1024
_MAX_HISTORY = 32
_SHELL_EXECUTABLES = frozenset(
    {
        "/bin/bash",
        "/bin/csh",
        "/bin/dash",
        "/bin/fish",
        "/bin/ksh",
        "/bin/sh",
        "/bin/tcsh",
        "/bin/zsh",
        "/usr/bin/env",
    }
)


class WorkerBrokerError(RuntimeError):
    """Base class for fail-closed broker errors."""


class PeerAuthorizationError(WorkerBrokerError):
    """The Unix peer is not the configured Executive control principal."""


class BrokerProtocolError(WorkerBrokerError):
    """A request did not match the fixed broker protocol."""


class BrokerStateError(WorkerBrokerError):
    """A typed operation is invalid for the broker's current state."""


class DedicatedUIDError(WorkerBrokerError):
    """The dedicated-worker-UID cleanup invariant could not be proven."""


@dataclasses.dataclass(frozen=True)
class PeerCredentials:
    """Kernel-reported Unix peer identity."""

    uid: int
    gid: int
    pid: int | None = None


@dataclasses.dataclass(frozen=True)
class UIDSweepReceipt:
    """Secret-free receipt for one dedicated-UID residual sweep.

    v2 distinguishes three PID classes so ``residual_pids_before`` is never
    silently widened or narrowed:

    * ``broker_pid`` — exact broker identity, never a residual
    * ``ambient_pids`` — launchd/codesign-attested platform helpers
    * ``residual_pids_*`` — untrusted same-UID processes only
    """

    schema_version: str
    observed_at: str
    reason: str
    worker_uid: int
    broker_pid: int
    residual_pids_before: tuple[int, ...]
    residual_pids_after: tuple[int, ...]
    signal_name: str
    signal_sent: bool
    quiescent_observations: int
    ambient_pids: tuple[int, ...] = ()
    ambient_identities: tuple[AmbientProcessIdentity, ...] = ()
    ambient_attribution: str = "absent"

    @property
    def passed(self) -> bool:
        return not self.residual_pids_after

    @property
    def found_residuals(self) -> bool:
        return bool(self.residual_pids_before)

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["residual_pids_before"] = list(self.residual_pids_before)
        value["residual_pids_after"] = list(self.residual_pids_after)
        value["ambient_pids"] = list(self.ambient_pids)
        value["ambient_identities"] = [
            identity.to_dict() if isinstance(identity, AmbientProcessIdentity) else dict(identity)
            for identity in self.ambient_identities
        ]
        value["passed"] = self.passed
        value["found_residuals"] = self.found_residuals
        return value


def _positive_pid(value: Any) -> bool:
    return type(value) is int and value > 1


def _ambient_identity_mapping_is_valid(value: Any, *, worker_uid: int) -> bool:
    """True when ``value`` is one reviewed ambient identity mapping."""

    if not isinstance(value, Mapping) or set(value) != _AMBIENT_IDENTITY_FIELDS:
        return False
    pid = value.get("pid")
    reported = value.get("launchd_reported_pid")
    uid = value.get("uid")
    if not _positive_pid(pid) or type(reported) is not int or reported != pid:
        return False
    if type(uid) is not int or uid != worker_uid:
        return False
    if type(value.get("executable_device")) is not int:
        return False
    if type(value.get("executable_inode")) is not int:
        return False
    if value.get("codesign_verified") is not True:
        return False
    for key in (
        "launchd_domain",
        "launchd_label",
        "plist_path",
        "program_path",
        "executable_path",
        "codesign_identifier",
    ):
        field = value.get(key)
        if type(field) is not str or not field:
            return False
    return True


def _v2_ambient_projection_is_coherent(value: Mapping[str, Any]) -> bool:
    """Keep in sync with ``ops.executive_os.acceptance._uid_sweep_is_passing``."""

    attribution = value.get("ambient_attribution")
    ambient = value.get("ambient_pids")
    identities = value.get("ambient_identities")
    before = value.get("residual_pids_before")
    after = value.get("residual_pids_after")
    broker_pid = value.get("broker_pid")
    worker_uid = value.get("worker_uid")
    if attribution not in _AMBIENT_ATTRIBUTIONS:
        return False
    if not isinstance(ambient, list) or not isinstance(identities, list):
        return False
    if not isinstance(before, list) or not isinstance(after, list):
        return False
    if not all(_positive_pid(item) for item in ambient):
        return False
    if len(ambient) != len(set(ambient)):
        return False
    if type(worker_uid) is not int or worker_uid <= 0:
        return False
    if not _positive_pid(broker_pid):
        return False
    identity_pids: list[int] = []
    for identity in identities:
        if not _ambient_identity_mapping_is_valid(identity, worker_uid=worker_uid):
            return False
        identity_pids.append(identity["pid"])
    if len(identity_pids) != len(set(identity_pids)):
        return False
    if set(identity_pids) != set(ambient):
        return False
    if attribution == "attested":
        if not ambient or not identities:
            return False
    elif ambient or identities:
        return False
    pid_sets = (set(ambient), set(before), set(after), {broker_pid})
    for index, left in enumerate(pid_sets):
        for right in pid_sets[index + 1 :]:
            if not left.isdisjoint(right):
                return False
    return True


def uid_sweep_receipt_is_passing(value: Any) -> bool:
    """True when ``value`` is a passing v2 dedicated-UID sweep receipt.

    The ambient projection must be internally coherent: attested receipts carry
    matching PID/identity sets of the reviewed shape; non-attested receipts
    carry neither. A malformed attested/empty-PID receipt does not pass.
    """

    if not isinstance(value, Mapping):
        return False
    before = value.get("residual_pids_before")
    after = value.get("residual_pids_after")
    return (
        value.get("schema_version") == UID_SWEEP_SCHEMA_VERSION
        and value.get("passed") is True
        and isinstance(before, list)
        and isinstance(after, list)
        and after == []
        and all(_positive_pid(item) for item in before)
        and value.get("found_residuals") is bool(before)
        and _v2_ambient_projection_is_coherent(value)
    )


class ResidualSweeper(Protocol):
    def sweep(self, reason: str) -> UIDSweepReceipt:
        """Terminate and prove absence of every other process for the worker UID."""


class OperatorAdapter(Protocol):
    """Worker-local subset of the frozen Operator Harness adapter."""

    def validate_requested_profile(
        self, requested: RequestedExecutionProfile
    ) -> ProfileValidation: ...

    def start_session(self, **kwargs: Any) -> Any: ...

    def resume_session(self, **kwargs: Any) -> Any: ...

    def observed_attestation(self, generation: ProcessGenerationRef) -> Any: ...

    def observe_process_credentials(
        self, generation: ProcessGenerationRef
    ) -> OSProcessCredentialObservation: ...

    def observe_provider_home_identity(
        self, generation: ProcessGenerationRef
    ) -> ProviderHomeIdentityObservation: ...

    def begin_turn(self, **kwargs: Any) -> Any: ...

    def read_events(self, cursor: EventCursor, *, timeout_seconds: float) -> Any: ...

    def collect_candidate_result(self, turn: TurnRef) -> Any: ...

    def observe_raw_role_result(self, turn: TurnRef) -> RawRoleResultObservation: ...

    def interrupt_turn(self, turn: TurnRef, *, operation_id: OperationId) -> None: ...

    def graceful_stop(self, generation: ProcessGenerationRef, **kwargs: Any) -> Any: ...

    def cancel(self, generation: ProcessGenerationRef, **kwargs: Any) -> Any: ...

    def reconcile(self, generation: ProcessGenerationRef) -> Any: ...


OperatorAdapterFactory = Callable[
    [Path, Callable[[TurnRef], str], RequestedExecutionProfile], OperatorAdapter
]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, UIDSweepReceipt):
        return _jsonable(value.to_dict())
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise BrokerProtocolError(f"broker value is not JSON serializable: {type(value).__name__}")


_RESPONSE_EXCERPT_BYTES = 48
_RESPONSE_SCAN_BYTES = 4096


def _response_excerpt(raw: bytes) -> str:
    """Bounded, redacted, printable-ASCII excerpt of a malformed response.

    A broker response is externally-produced text, so it passes through the
    shared sanitizer before it can reach a client-facing message.

    Ordering is load-bearing: the excerpt is bounded LAST.  Slicing to
    ``_RESPONSE_EXCERPT_BYTES`` first would cut a 64-character token down to
    the ~28 characters that fit, dropping it below every shape threshold in
    :func:`sanitize_external_text`, and the surviving fragment would then be
    printed verbatim.  So a generous window is mapped to printable ASCII byte
    for byte -- a credential's own characters are all printable, so a secret
    run survives that mapping intact and is still matchable -- redacted whole,
    and only then trimmed by the sanitizer's own limit.

    Note this deliberately differs from ``acceptance.py``'s refusal sanitizer,
    which exempts exactly-40 lowercase hex to keep Git object ids readable for
    release-SHA comparison.  A broker wire excerpt is not that path, so the
    shared helper's stricter 32+ hex rule applies here unmodified.
    """

    window = bytes(raw[:_RESPONSE_SCAN_BYTES])
    printable = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in window)
    return sanitize_external_text(printable, limit=_RESPONSE_EXCERPT_BYTES)


def _frame_response(response: Mapping[str, Any]) -> bytes:
    """Serialize one broker response as a single newline-terminated JSON line.

    ``json.dumps`` defaults to ``ensure_ascii=True``, so the encoded document is
    pure ASCII and the following UTF-8 encode cannot fail; the newline is the
    frame terminator the client reads with ``readline``.
    """

    return (
        json.dumps(_jsonable(response), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically replace one owner-only, non-symlink JSON receipt."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.resolve(strict=True)
    info = parent.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise DedicatedUIDError("UID sweep receipt parent is not a real directory")
    temporary = parent / f".{path.name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = (
            json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write while persisting UID sweep receipt")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


_PS_UID_PROJECTION = "svuid=,ruid=,uid=,pid="


def _ps_pids_for_uid(uid: int) -> tuple[int, ...]:
    """Return a bounded process-table projection without shell evaluation.

    The projection must be a SUPERSET of the processes the worker UID can
    signal, or ``UIDSweepReceipt.passed`` can certify quiescence with a
    reachable process still alive -- and that receipt is what
    ``executive_supervisor`` treats as the terminal absence proof.

    Darwin's ``man 2 kill`` says the receiver matches on "real or effective"
    uid, but that wording is wrong: the kernel checks the receiver's real or
    SAVED uid.  Measured on this host as uid 501, ``kill(pid, 0)`` against
    ``loginwindow`` (``ruid=0 euid=501 svuid=0``) returns ``EPERM`` -- an
    effective-uid match is not sufficient to signal.  So the killable set is
    ``{ruid == W} | {svuid == W}`` while ``ps -o uid`` prints only the
    effective uid.  Enumerating on ``uid`` alone both misses killable
    processes (a setuid binary started by the worker uid prints ``uid=0`` with
    ``ruid=<worker>``) and, on its own, is not a superset in the ``svuid``
    direction either.

    This therefore unions the saved, real, and effective columns.  The
    effective column is kept deliberately: it can only ever ADD unreachable
    processes (the ``loginwindow`` case), and over-reporting fails the sweep
    closed rather than certifying a false absence.

    The one process this MUST NOT count is the enumeration's own ``ps`` child.
    ``/bin/ps`` is setuid root (``-rwsr-xr-x root wheel``), so the child this
    function spawns is itself observed as ``ruid=<caller> euid=0 svuid=0`` and
    the union above matches it on ``ruid`` -- the sweeper would then see a
    residual on EVERY observation, a fresh transient pid each time, and could
    never reach quiescence.  Enumerating on ``uid`` alone used to hide this by
    accident (the setuid child prints ``uid=0``); adding the real-uid term made
    the projection self-referential.  The child is therefore spawned through
    ``Popen`` so its pid is CAPTURED rather than guessed, and exactly that pid
    is dropped.  Identity is the only sound filter here: command name, ``euid``
    and liveness are all properties a genuine residual can share, so filtering
    on any of them would mask real processes.  Dropping the captured pid cannot
    mask one, because a pid is unique among live processes and our child is
    alive across the whole snapshot.

    Honest scope note: on this host no process currently carries an ``svuid``
    distinct from its ``ruid``, so the saved-uid term closes an unestablished
    invariant rather than a demonstrated escape.  The effective-uid term, by
    contrast, is demonstrably wide: measured as uid 501, ``loginwindow``
    (``svuid=0 ruid=0 euid=501``) is enumerated and ``kill(pid, 0)`` against it
    returns ``EPERM``.  That shape is retained in the QUIESCENCE gate on
    purpose -- under a dedicated worker uid it requires either a setuid-to-W
    binary or a root process that assumed W's effective identity, and either
    one is an isolation breach that must fail the sweep closed rather than be
    reported and tolerated.
    """

    argv = ["/bin/ps", "-axo", _PS_UID_PROJECTION]
    with subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        text=True,
    ) as process:
        enumeration_pid = process.pid
        try:
            stdout, _stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Mirror subprocess.run(timeout=...): reap the child before the
            # timeout propagates, so a wedged ps cannot be left running as the
            # worker uid -- which would be a residual this sweep just created.
            process.kill()
            process.wait()
            raise
        except BaseException:
            process.kill()
            raise
        returncode = process.returncode
    if returncode != 0:
        # Defense in depth, not the load-bearing check: a ps lacking one of
        # these keywords exits non-zero AND prints short rows, which the
        # arity check below already refuses.  Either alone fails closed.
        raise DedicatedUIDError("cannot inspect the worker UID process table")
    values: list[int] = []
    rows = 0
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 4:
            raise DedicatedUIDError("worker UID process table projection is malformed")
        try:
            saved_uid, real_uid, effective_uid, pid = (int(item) for item in fields)
        except ValueError:
            raise DedicatedUIDError(
                "worker UID process table projection is malformed"
            ) from None
        rows += 1
        if pid == enumeration_pid:
            # This row IS the ps invocation above.  Counted after `rows` so it
            # still witnesses a non-empty table, and dropped before the union
            # so the reader cannot report itself as a residual.
            continue
        if uid in (saved_uid, real_uid, effective_uid):
            values.append(pid)
    if rows == 0:
        # A live host always has a process table.  Without this, a ps that
        # exits 0 with empty stdout yields no residuals at all -- a receipt
        # with `passed=True` and `residual_pids_after=()` that proves nothing.
        raise DedicatedUIDError("worker UID process table projection is empty")
    return tuple(sorted(set(values)))


class DedicatedUIDSweeper:
    """Darwin worker-UID reaper that also supports injected Linux CI fakes."""

    def __init__(
        self,
        worker_uid: int,
        *,
        receipt_path: Path | None = None,
        current_uid: Callable[[], int] = os.geteuid,
        current_pid: Callable[[], int] = os.getpid,
        process_lister: Callable[[int], tuple[int, ...]] = _ps_pids_for_uid,
        kill_fn: Callable[[int, int], None] = os.kill,
        sleep_fn: Callable[[float], None] = time.sleep,
        settle_interval: float = 0.05,
        timeout_seconds: float = 5.0,
        required_quiescent_observations: int = 2,
        ambient_classifier: AmbientProcessClassifier | None = None,
    ) -> None:
        self.worker_uid = int(worker_uid)
        self.receipt_path = Path(receipt_path) if receipt_path is not None else None
        self.current_uid = current_uid
        self.current_pid = current_pid
        self.process_lister = process_lister
        self.kill_fn = kill_fn
        self.sleep_fn = sleep_fn
        self.settle_interval = float(settle_interval)
        self.timeout_seconds = float(timeout_seconds)
        self.required_quiescent_observations = int(required_quiescent_observations)
        self.ambient_classifier = ambient_classifier or NullAmbientClassifier()
        if self.worker_uid <= 0:
            raise DedicatedUIDError("the dedicated worker UID must be non-root")
        if self.settle_interval <= 0 or self.timeout_seconds <= 0:
            raise DedicatedUIDError("UID sweep timing must be positive")
        if self.required_quiescent_observations < 2:
            raise DedicatedUIDError("UID sweep requires at least two quiescent observations")

    def _classify_ambient(self) -> AmbientClassification:
        try:
            classified = self.ambient_classifier.classify(worker_uid=self.worker_uid)
        except Exception:
            return AmbientClassification(status="failed_closed")
        if not isinstance(classified, AmbientClassification):
            return AmbientClassification(status="failed_closed")
        return classified

    def _observed(self, broker_pid: int) -> tuple[int, ...]:
        return tuple(
            pid
            for pid in self.process_lister(self.worker_uid)
            if pid > 1 and pid != broker_pid
        )

    def _partition(
        self, broker_pid: int, classified: AmbientClassification
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[AmbientProcessIdentity, ...]]:
        observed = set(self._observed(broker_pid))
        attested = tuple(
            identity
            for identity in classified.identities
            if identity.pid in observed
            and identity.uid == self.worker_uid
            and identity.launchd_reported_pid == identity.pid
        )
        ambient_pids = {identity.pid for identity in attested}
        residuals = tuple(sorted(pid for pid in observed if pid not in ambient_pids))
        return residuals, tuple(sorted(ambient_pids)), attested

    def _residuals(self, broker_pid: int) -> tuple[int, ...]:
        residuals, _ambient, _identities = self._partition(
            broker_pid, self._classify_ambient()
        )
        return residuals

    def _kill_residuals(self, residuals: Sequence[int]) -> bool:
        """SIGKILL only the residual PIDs captured by the last observation.

        A dedicated worker UID makes every observed residual unauthorized, no
        matter which process group or session it escaped into.  Addressing the
        captured PIDs directly preserves that closure while keeping the broker
        outside the signal target set.  A process that exits between the
        observation and signal is harmless; repeated observations catch any
        replacement or newly detached process before quiescence can pass.
        """

        delivered = False
        permission_error: PermissionError | None = None
        for pid in residuals:
            try:
                self.kill_fn(int(pid), signal.SIGKILL)
                delivered = True
            except ProcessLookupError:
                continue
            except PermissionError as exc:
                # Keep trying the other observed residuals before failing the
                # sweep closed on an identity the dedicated UID cannot signal.
                permission_error = permission_error or exc
        if permission_error is not None:
            raise DedicatedUIDError("worker UID could not signal an observed residual")
        return delivered

    def sweep(self, reason: str) -> UIDSweepReceipt:
        if not isinstance(reason, str) or not reason or len(reason) > 160:
            raise DedicatedUIDError("UID sweep reason is invalid")
        observed_uid = int(self.current_uid())
        if observed_uid != self.worker_uid:
            raise DedicatedUIDError(
                f"broker effective UID {observed_uid} does not match worker UID {self.worker_uid}"
            )
        broker_pid = int(self.current_pid())
        classified = self._classify_ambient()
        before, ambient_before, identities_before = self._partition(broker_pid, classified)
        sent = False
        if before:
            sent = self._kill_residuals(before)

        deadline = time.monotonic() + self.timeout_seconds
        quiescent = 0
        after: tuple[int, ...] = before
        ambient_after = ambient_before
        identities_after = identities_before
        while time.monotonic() < deadline:
            classified = self._classify_ambient()
            after, ambient_after, identities_after = self._partition(broker_pid, classified)
            if after:
                quiescent = 0
                sent = self._kill_residuals(after) or sent
            else:
                quiescent += 1
                if quiescent >= self.required_quiescent_observations:
                    break
            self.sleep_fn(self.settle_interval)

        receipt = UIDSweepReceipt(
            schema_version=UID_SWEEP_SCHEMA_VERSION,
            observed_at=_utc_now(),
            reason=reason,
            worker_uid=self.worker_uid,
            broker_pid=broker_pid,
            residual_pids_before=before,
            residual_pids_after=after,
            signal_name="SIGKILL",
            signal_sent=sent,
            quiescent_observations=quiescent,
            ambient_pids=ambient_after,
            ambient_identities=identities_after,
            ambient_attribution=classified.status,
        )
        payload = receipt.to_dict()
        if self.receipt_path is not None:
            _write_private_json(self.receipt_path, payload)
            if reason in UID_SWEEP_TERMINAL_REASONS:
                terminal_path = self.receipt_path.with_name("uid-sweep-terminal.json")
                _write_private_json(terminal_path, payload)
        if not receipt.passed or quiescent < self.required_quiescent_observations:
            raise DedicatedUIDError("worker UID did not become quiescent after SIGKILL")
        return receipt


@dataclasses.dataclass(frozen=True)
class BrokerPolicy:
    """Static host boundary supplied by the root-owned worker config."""

    control_uid: int
    worker_uid: int
    worker_gid: int
    worker_user: str
    worker_id: str
    workspace_root: Path
    run_root: Path
    provider_home: Path
    allowed_supplementary_gids: frozenset[int] = frozenset()
    require_secret_canary: bool = True
    max_request_bytes: int = _MAX_REQUEST_BYTES

    def __post_init__(self) -> None:
        if int(self.control_uid) <= 0:
            raise WorkerBrokerError("control UID must be a non-root service principal")
        if int(self.worker_uid) <= 0 or int(self.worker_uid) == int(self.control_uid):
            raise WorkerBrokerError("worker UID must be non-root and distinct from control UID")
        if int(self.worker_gid) <= 0:
            raise WorkerBrokerError("worker GID must be non-root")
        if (
            any(type(group_id) is not int or group_id <= 0 for group_id in self.allowed_supplementary_gids)
            or int(self.worker_gid) in self.allowed_supplementary_gids
        ):
            raise WorkerBrokerError("allowed supplementary GIDs are invalid")
        if not _ID_RE.fullmatch(self.worker_id):
            raise WorkerBrokerError("worker_id is invalid")
        if not self.worker_user or any(character.isspace() for character in self.worker_user):
            raise WorkerBrokerError("worker_user is invalid")
        if not 1024 <= int(self.max_request_bytes) <= _MAX_REQUEST_BYTES:
            raise WorkerBrokerError("max_request_bytes is outside the safe ceiling")
        roots = (self.workspace_root, self.run_root, self.provider_home)
        resolved: list[Path] = []
        for value in roots:
            lexical = Path(value)
            if not lexical.is_absolute():
                raise WorkerBrokerError("broker filesystem roots must be absolute")
            info = lexical.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise WorkerBrokerError("broker filesystem roots must be real directories")
            resolved.append(lexical.resolve(strict=True))
        for index, left in enumerate(resolved):
            for right in resolved[index + 1 :]:
                if left == right or _is_within(left, right) or _is_within(right, left):
                    raise WorkerBrokerError(
                        "workspace, run, and provider roots must be disjoint"
                    )
        provider_info = resolved[2].lstat()
        if stat.S_IMODE(provider_info.st_mode) & 0o077:
            raise WorkerBrokerError("provider home must be mode 0700 or narrower")
        if int(provider_info.st_uid) != int(self.worker_uid):
            raise WorkerBrokerError("provider home is not owned by the worker UID")


@dataclasses.dataclass
class _BrokerRun:
    spec: LaunchSpec
    process_ref: ProcessRef
    validation_commands: tuple[tuple[str, ...], ...]
    launch_attestation: Any = None
    collected_receipt: Any = None
    cancel_receipt: Any = None
    validation_receipts: dict[tuple[str, ...], Any] = dataclasses.field(default_factory=dict)
    terminal_error: str | None = None
    collecting: bool = False
    cancelling: bool = False
    terminal_sweep_task: asyncio.Task[UIDSweepReceipt] | None = None


@dataclasses.dataclass
class _BrokerOperatorRun:
    """Process-local handle for one Runtime-owned OHF generation."""

    adapter: OperatorAdapter
    requested: RequestedExecutionProfile
    epoch: SessionEpochRef
    generation: ProcessGenerationRef
    provider_session_id: str
    prompts: dict[str, str] = dataclasses.field(default_factory=dict)
    terminal_error: str | None = None
    busy: bool = False


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_child(value: Any, root: Path, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BrokerProtocolError(f"{field} must be an absolute path string")
    lexical = Path(value)
    if not lexical.is_absolute():
        raise BrokerProtocolError(f"{field} must be absolute")
    resolved = lexical.resolve(strict=True)
    canonical_root = Path(root).resolve(strict=True)
    if resolved == canonical_root or not _is_within(resolved, canonical_root):
        raise BrokerProtocolError(f"{field} escapes its configured root")
    return resolved


def _validation_commands(value: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or len(value) > _MAX_VALIDATION_COMMANDS:
        raise BrokerProtocolError("validation_commands must be a bounded list")
    commands: list[tuple[str, ...]] = []
    encoded_bytes = 0
    for raw in value:
        if (
            not isinstance(raw, list)
            or not raw
            or len(raw) > _MAX_VALIDATION_ARGS
            or any(not isinstance(item, str) or not item or "\x00" in item for item in raw)
        ):
            raise BrokerProtocolError("each validation command must be a bounded argv array")
        command = tuple(raw)
        if not Path(command[0]).is_absolute():
            raise BrokerProtocolError("validation executable must be absolute")
        if command[0] in _SHELL_EXECUTABLES:
            raise BrokerProtocolError("shell and env validation executables are forbidden")
        encoded_bytes += sum(len(item.encode("utf-8")) for item in command)
        commands.append(command)
    if encoded_bytes > _MAX_VALIDATION_BYTES:
        raise BrokerProtocolError("validation command bytes exceed the broker ceiling")
    if len(commands) != len(set(commands)):
        raise BrokerProtocolError("validation_commands contains duplicates")
    return tuple(commands)


_LAUNCH_SPEC_FIELDS = frozenset(
    {
        "run_id",
        "job_id",
        "worker_id",
        "workspace_path",
        "run_dir",
        "prompt",
        "result_schema_path",
        "codex_home",
        "authorities",
        "authority",
        "model",
        "reasoning_effort",
        "timeout_seconds",
        "cancel_grace_seconds",
        "worker_user",
        "expected_base_sha",
        "allowed_artifact_paths",
        "isolation_roots",
        "isolation_denied_paths",
        "isolation_manifest",
        "isolation_manifest_sha256",
        "forbidden_paths",
        "max_artifacts",
        "max_artifact_bytes",
        "max_artifact_total_bytes",
        "expected_worker_uid",
        "expected_worker_gid",
        "shared_run_gid",
        "secret_canary_verdict",
        "require_secret_canary",
    }
)


def _launch_spec(value: Any, policy: BrokerPolicy) -> LaunchSpec:
    if not isinstance(value, dict):
        raise BrokerProtocolError("launch_spec must be an object")
    unknown = set(value) - _LAUNCH_SPEC_FIELDS
    if unknown:
        raise BrokerProtocolError(f"launch_spec has unknown fields: {sorted(unknown)}")
    required = {
        "run_id",
        "job_id",
        "worker_id",
        "workspace_path",
        "run_dir",
        "prompt",
        "result_schema_path",
        "codex_home",
        "expected_base_sha",
    }
    missing = required - set(value)
    if missing:
        raise BrokerProtocolError(f"launch_spec is missing fields: {sorted(missing)}")
    if value.get("worker_id") != policy.worker_id:
        raise BrokerProtocolError("launch_spec worker_id does not match the broker")
    requested_user = value.get("worker_user", policy.worker_user)
    if requested_user != policy.worker_user:
        raise BrokerProtocolError("launch_spec worker_user does not match the broker")
    expected_uid = value.get("expected_worker_uid", policy.worker_uid)
    expected_gid = value.get("expected_worker_gid", policy.worker_gid)
    shared_gid = value.get("shared_run_gid", policy.worker_gid)
    try:
        principal_matches = (
            int(expected_uid) == policy.worker_uid
            and int(expected_gid) == policy.worker_gid
            and int(shared_gid) == policy.worker_gid
        )
    except (TypeError, ValueError) as exc:
        raise BrokerProtocolError("launch_spec worker principal is invalid") from exc
    if not principal_matches:
        raise BrokerProtocolError("launch_spec worker principal does not match the broker")
    expected_sha = value.get("expected_base_sha")
    if not isinstance(expected_sha, str) or _SHA_RE.fullmatch(expected_sha.lower()) is None:
        raise BrokerProtocolError("launch_spec requires an exact 40-hex base SHA")
    workspace = _resolve_child(value["workspace_path"], policy.workspace_root, field="workspace_path")
    run_dir = _resolve_child(value["run_dir"], policy.run_root, field="run_dir")
    schema = _resolve_child(value["result_schema_path"], run_dir, field="result_schema_path")
    if not isinstance(value["codex_home"], str):
        raise BrokerProtocolError("launch_spec CODEX_HOME must be an absolute path string")
    provider_home = Path(value["codex_home"]).resolve(strict=True)
    if provider_home != Path(policy.provider_home).resolve(strict=True):
        raise BrokerProtocolError("launch_spec CODEX_HOME is not the dedicated provider home")
    authorities = value.get("authorities", [])
    artifacts = value.get("allowed_artifact_paths", [])
    isolation = value.get("isolation_roots", [])
    isolation_denied = value.get("isolation_denied_paths", [])
    isolation_manifest = value.get("isolation_manifest", {})
    isolation_manifest_sha256 = value.get("isolation_manifest_sha256")
    forbidden = value.get("forbidden_paths", [])
    if not isinstance(authorities, list) or not isinstance(artifacts, list):
        raise BrokerProtocolError("authorities and artifact paths must be arrays")
    if not isinstance(isolation, list) or len(isolation) > 64:
        raise BrokerProtocolError("isolation_roots must be a bounded array")
    required_isolation_roots = {
        Path(policy.workspace_root).resolve(strict=True),
        Path(policy.run_root).resolve(strict=True),
    }
    isolation_roots: set[Path] = set()
    for raw in isolation:
        if not isinstance(raw, str) or not Path(raw).is_absolute():
            raise BrokerProtocolError("isolation_roots entries must be absolute")
        isolation_roots.add(Path(raw).resolve(strict=False))
    if isolation_roots != required_isolation_roots:
        raise BrokerProtocolError(
            "isolation roots must exactly match the broker workspace and run roots"
        )
    if not isinstance(isolation_denied, list) or len(isolation_denied) > 128:
        raise BrokerProtocolError("isolation_denied_paths must be a bounded array")
    isolation_denied_paths: list[Path] = []
    for raw in isolation_denied:
        if not isinstance(raw, str) or not Path(raw).is_absolute():
            raise BrokerProtocolError("isolation_denied_paths entries must be absolute")
        isolation_denied_paths.append(Path(raw).resolve(strict=False))
    allowed_denial_roots = required_isolation_roots
    for denied in isolation_denied_paths:
        if not any(denied.parent == root for root in allowed_denial_roots):
            raise BrokerProtocolError(
                "isolation denial must be a direct child of a broker assignment root"
            )
        if denied in {workspace, run_dir}:
            raise BrokerProtocolError("isolation denial targets the current assignment")
    if isolation_roots and (
        not isinstance(isolation_manifest_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", isolation_manifest_sha256) is None
    ):
        raise BrokerProtocolError("isolation manifest requires a SHA-256 digest")
    if isolation_roots:
        if not isinstance(isolation_manifest, dict) or set(isolation_manifest) != {
            "schema_version",
            "roots",
            "entries",
            "workspace_path",
            "run_dir",
        }:
            raise BrokerProtocolError("isolation manifest shape is invalid")
        if (
            isolation_manifest.get("schema_version")
            != ISOLATION_MANIFEST_SCHEMA_VERSION
            or isolation_manifest.get("workspace_path") != str(workspace)
            or isolation_manifest.get("run_dir") != str(run_dir)
        ):
            raise BrokerProtocolError("isolation manifest assignment identity drifted")
        digest = hashlib.sha256(
            json.dumps(
                isolation_manifest,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if digest != isolation_manifest_sha256:
            raise BrokerProtocolError("isolation sibling manifest digest does not match")
        manifest_roots = isolation_manifest.get("roots")
        manifest_entries = isolation_manifest.get("entries")
        if not isinstance(manifest_roots, list) or not isinstance(manifest_entries, list):
            raise BrokerProtocolError("isolation manifest lists are invalid")
        root_paths = [
            item.get("path") if isinstance(item, dict) else None
            for item in manifest_roots
        ]
        if root_paths != sorted(str(path) for path in required_isolation_roots):
            raise BrokerProtocolError("isolation manifest roots are incomplete")
        manifest_denied: list[str] = []
        current: dict[str, str] = {}
        for item in manifest_entries:
            if not isinstance(item, dict) or set(item) != {
                "root_path",
                "disposition",
                "identity",
            }:
                raise BrokerProtocolError("isolation manifest entry shape is invalid")
            identity = item.get("identity")
            if not isinstance(identity, dict) or not isinstance(identity.get("path"), str):
                raise BrokerProtocolError("isolation manifest entry identity is invalid")
            path = identity["path"]
            disposition = item.get("disposition")
            if disposition == "DENY":
                manifest_denied.append(path)
            elif disposition in {"CURRENT_WORKSPACE", "CURRENT_RUN"}:
                current[str(disposition)] = path
            else:
                raise BrokerProtocolError("isolation manifest entry disposition is invalid")
        if sorted(manifest_denied) != sorted(str(path) for path in isolation_denied_paths):
            raise BrokerProtocolError("isolation denial list is incomplete")
        if current != {
            "CURRENT_WORKSPACE": str(workspace),
            "CURRENT_RUN": str(run_dir),
        }:
            raise BrokerProtocolError("isolation manifest omits the current assignment")
    if not isinstance(forbidden, list) or len(forbidden) > 64:
        raise BrokerProtocolError("forbidden_paths must be a bounded array")
    forbidden_paths: list[Path] = []
    for raw in forbidden:
        if not isinstance(raw, str) or not Path(raw).is_absolute():
            raise BrokerProtocolError("forbidden_paths entries must be absolute")
        forbidden_paths.append(Path(raw).resolve(strict=False))
    require_canary = bool(value.get("require_secret_canary", policy.require_secret_canary))
    if policy.require_secret_canary and not require_canary:
        raise BrokerProtocolError("the broker requires a passing secret-canary verdict")
    keyword: dict[str, Any] = {
        "run_id": value["run_id"],
        "job_id": value["job_id"],
        "worker_id": value["worker_id"],
        "workspace_path": workspace,
        "run_dir": run_dir,
        "prompt": value["prompt"],
        "result_schema_path": schema,
        "codex_home": provider_home,
        "authorities": tuple(authorities),
        "authority": value.get("authority"),
        "worker_user": policy.worker_user,
        "expected_base_sha": expected_sha.lower(),
        "allowed_artifact_paths": tuple(artifacts),
        "isolation_roots": tuple(sorted(isolation_roots, key=str)),
        "isolation_denied_paths": tuple(isolation_denied_paths),
        "isolation_manifest": isolation_manifest,
        "isolation_manifest_sha256": isolation_manifest_sha256,
        "forbidden_paths": tuple(forbidden_paths),
        "expected_worker_uid": policy.worker_uid,
        "expected_worker_gid": policy.worker_gid,
        "shared_run_gid": policy.worker_gid,
        "secret_canary_verdict": value.get("secret_canary_verdict", {}),
        "require_secret_canary": require_canary,
    }
    for optional in (
        "model",
        "reasoning_effort",
        "timeout_seconds",
        "cancel_grace_seconds",
        "max_artifacts",
        "max_artifact_bytes",
        "max_artifact_total_bytes",
    ):
        if optional in value:
            keyword[optional] = value[optional]
    return LaunchSpec(**keyword)


def get_peer_credentials(peer_socket: socket.socket) -> PeerCredentials:
    """Read kernel-authenticated Unix peer credentials on Darwin or Linux."""

    descriptor = peer_socket.fileno()
    if descriptor < 0:
        raise PeerAuthorizationError("peer socket is closed")
    if platform.system() == "Darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        getpeereid = libc.getpeereid
        getpeereid.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        getpeereid.restype = ctypes.c_int
        uid = ctypes.c_uint()
        gid = ctypes.c_uint()
        if getpeereid(descriptor, ctypes.byref(uid), ctypes.byref(gid)) != 0:
            raise PeerAuthorizationError("cannot resolve Unix peer credentials")
        return PeerCredentials(uid=int(uid.value), gid=int(gid.value))
    if hasattr(socket, "SO_PEERCRED"):
        raw = peer_socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", raw)
        return PeerCredentials(uid=int(uid), gid=int(gid), pid=int(pid))
    raise PeerAuthorizationError("Unix peer credentials are unsupported on this host")


def activate_launchd_socket(name: str) -> socket.socket:
    """Claim exactly one launchd-activated socket by plist key name."""

    if platform.system() != "Darwin":
        raise WorkerBrokerError("launchd socket activation is available only on Darwin")
    if not isinstance(name, str) or not _ID_RE.fullmatch(name):
        raise WorkerBrokerError("launchd socket name is invalid")
    libc = ctypes.CDLL(None, use_errno=True)
    activate = libc.launch_activate_socket
    activate.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    activate.restype = ctypes.c_int
    descriptors = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    result = activate(name.encode("utf-8"), ctypes.byref(descriptors), ctypes.byref(count))
    if result != 0:
        raise WorkerBrokerError(f"launchd socket activation failed with errno {result}")
    try:
        values = [int(descriptors[index]) for index in range(int(count.value))]
    finally:
        libc.free.argtypes = [ctypes.c_void_p]
        libc.free.restype = None
        libc.free(descriptors)
    if len(values) != 1:
        for descriptor in values:
            os.close(descriptor)
        raise WorkerBrokerError("worker broker requires exactly one launchd socket")
    activated = socket.socket(fileno=values[0])
    activated.setblocking(False)
    return activated


class ExecutiveWorkerBroker:
    """One-worker, one-active-job typed adapter broker."""

    def __init__(
        self,
        adapter: CodexWorkerAdapter,
        policy: BrokerPolicy,
        sweeper: ResidualSweeper,
        *,
        peer_resolver: Callable[[socket.socket], PeerCredentials] = get_peer_credentials,
        operator_adapter_factory: OperatorAdapterFactory | None = None,
        operator_harness_armed: bool = False,
        autonomy_guard: Callable[[], None] | None = None,
    ) -> None:
        self.adapter = adapter
        self.policy = policy
        self.sweeper = sweeper
        self.peer_resolver = peer_resolver
        self.operator_adapter_factory = operator_adapter_factory
        self.operator_harness_armed = bool(operator_harness_armed)
        self.autonomy_guard = autonomy_guard
        if self.operator_harness_armed and self.operator_adapter_factory is None:
            raise WorkerBrokerError(
                "armed Operator Harness requires a reviewed worker-local adapter factory"
            )
        if self.operator_harness_armed and not callable(self.autonomy_guard):
            raise WorkerBrokerError(
                "armed Operator Harness requires a runtime autonomy guard"
            )
        self._runs: OrderedDict[str, _BrokerRun] = OrderedDict()
        self._active_run_id: str | None = None
        self._operator_run: _BrokerOperatorRun | None = None
        self._operator_terminal: OrderedDict[
            str, tuple[ProcessGenerationRef, ReconcileObservation]
        ] = OrderedDict()
        self._operator_session_attempts: OrderedDict[str, str] = OrderedDict()
        self._state_lock = asyncio.Lock()
        self._starting = False
        self._validation_busy = False
        self._status_sweep_busy = False
        self._quarantined_reason: str | None = None
        self.startup_sweep: UIDSweepReceipt | None = None
        self.last_sweep: UIDSweepReceipt | None = None

    def _require_current_autonomy(self) -> None:
        """Revalidate current arm authority without exposing receipt diagnostics."""

        if not self.operator_harness_armed:
            return
        if self._quarantined_reason == "autonomy_receipt_refused":
            raise BrokerStateError("Executive autonomy receipt refused")
        try:
            assert self.autonomy_guard is not None
            self.autonomy_guard()
        except Exception as exc:
            self._quarantined_reason = "autonomy_receipt_refused"
            raise BrokerStateError("Executive autonomy receipt refused") from exc

    def initialize(self) -> UIDSweepReceipt:
        """Prove the dedicated UID is clean before accepting any request."""

        if self.startup_sweep is not None:
            return self.startup_sweep
        self._require_current_autonomy()
        if os.geteuid() != self.policy.worker_uid or os.getegid() != self.policy.worker_gid:
            raise DedicatedUIDError("broker process does not match the configured worker UID/GID")
        observed_groups = set(os.getgroups()) - {self.policy.worker_gid}
        if observed_groups != set(self.policy.allowed_supplementary_gids):
            raise DedicatedUIDError("worker broker supplementary groups differ from policy")
        self.startup_sweep = self.sweeper.sweep("broker_startup")
        self.last_sweep = self.startup_sweep
        return self.startup_sweep

    def _remember(self, run_id: str, value: _BrokerRun) -> None:
        self._runs[run_id] = value
        self._runs.move_to_end(run_id)
        while len(self._runs) > _MAX_HISTORY:
            oldest, _ = next(iter(self._runs.items()))
            if oldest == self._active_run_id:
                break
            self._runs.popitem(last=False)

    def _run(self, run_id: Any) -> _BrokerRun:
        if not isinstance(run_id, str) or not _ID_RE.fullmatch(run_id):
            raise BrokerProtocolError("run_id is invalid")
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise BrokerStateError(f"run {run_id!r} is unknown to this broker") from exc

    def _authorize_peer(self, peer: PeerCredentials) -> None:
        if int(peer.uid) != int(self.policy.control_uid):
            raise PeerAuthorizationError("Unix peer UID is not the Executive control principal")

    async def execute(self, request: Mapping[str, Any], *, peer: PeerCredentials) -> dict[str, Any]:
        self._authorize_peer(peer)
        if not isinstance(request, Mapping):
            raise BrokerProtocolError("request must be a JSON object")
        allowed = {"schema_version", "request_id", "operation", "payload"}
        if set(request) != allowed:
            raise BrokerProtocolError("request fields do not match the broker schema")
        if request.get("schema_version") != BROKER_REQUEST_SCHEMA_VERSION:
            raise BrokerProtocolError("request schema version is unsupported")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not _ID_RE.fullmatch(request_id):
            raise BrokerProtocolError("request_id is invalid")
        operation = request.get("operation")
        if operation not in _ALLOWED_OPERATIONS:
            raise BrokerProtocolError("operation is not allowed")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            raise BrokerProtocolError("payload must be an object")
        result = await self._dispatch(str(operation), payload)
        return {
            "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
            "request_id": request_id,
            "operation": operation,
            "ok": True,
            "result": _jsonable(result),
        }

    async def _dispatch(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation == "start":
            return await self._start(payload)
        if operation == "status":
            return await self._status(payload)
        if operation == "collect":
            return await self._collect(payload)
        if operation == "cancel":
            return await self._cancel(payload)
        if operation == "validate":
            return await self._validate(payload)
        if operation == "ohf-validate":
            return await self._ohf_validate(payload)
        if operation == "ohf-identity":
            return await self._ohf_identity(payload)
        if operation == "ohf-start":
            return await self._ohf_start(payload, resume=False)
        if operation == "ohf-resume":
            return await self._ohf_start(payload, resume=True)
        if operation == "ohf-begin-turn":
            return await self._ohf_begin_turn(payload)
        if operation == "ohf-collect-turn":
            return await self._ohf_collect_turn(payload)
        if operation == "ohf-interrupt":
            return await self._ohf_interrupt(payload)
        if operation == "ohf-stop":
            return await self._ohf_stop(payload)
        if operation == "ohf-cancel":
            return await self._ohf_cancel(payload)
        if operation == "ohf-reconcile":
            return await self._ohf_reconcile(payload)
        if operation == "ohf-reconcile-absence":
            return await self._ohf_reconcile_absence(payload)
        raise AssertionError(operation)  # pragma: no cover

    def _operator_factory(
        self, requested: RequestedExecutionProfile
    ) -> tuple[OperatorAdapter, dict[str, str]]:
        self._require_current_autonomy()
        if not self.operator_harness_armed or self.operator_adapter_factory is None:
            raise BrokerStateError("the Operator Harness is not armed by worker policy")
        workspace = _resolve_child(
            requested.workspace.workspace_path,
            self.policy.workspace_root,
            field="operator workspace",
        )
        if workspace.parent != Path(self.policy.workspace_root).resolve(strict=True):
            raise BrokerProtocolError(
                "operator workspace must be a direct broker assignment"
            )
        prompts: dict[str, str] = {}

        def load_turn(turn: TurnRef) -> str:
            try:
                return prompts[turn.turn_id]
            except KeyError as exc:
                raise BrokerStateError(
                    "the Executive turn prompt is not bound inside the broker"
                ) from exc

        try:
            adapter = self.operator_adapter_factory(workspace, load_turn, requested)
        except Exception as exc:
            raise BrokerStateError(
                f"operator adapter construction failed: {type(exc).__name__}"
            ) from exc
        return adapter, prompts

    @staticmethod
    async def _operator_call(phase: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(function, *args, **kwargs)
        except WorkerBrokerError:
            raise
        except Exception as exc:
            failure = getattr(getattr(exc, "failure_class", None), "value", None)
            suffix = f" ({failure})" if failure else ""
            raise BrokerStateError(
                f"operator adapter {phase} failed{suffix}: {type(exc).__name__}"
            ) from exc

    async def _ohf_validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"requested"}:
            raise BrokerProtocolError("ohf-validate payload fields are invalid")
        try:
            requested = wire_requested_execution_profile(payload["requested"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        async with self._state_lock:
            if (
                self._active_run_id is not None
                or self._operator_run is not None
                or self._starting
                or self._validation_busy
                or self._status_sweep_busy
            ):
                raise BrokerStateError("the worker broker already has active work")
            self._starting = True
        try:
            adapter, _prompts = self._operator_factory(requested)
            validation = await self._operator_call(
                "profile validation", adapter.validate_requested_profile, requested
            )
            if not isinstance(validation, ProfileValidation):
                raise BrokerStateError(
                    "operator adapter returned an untyped profile validation"
                )
            return {"validation": operator_to_wire(validation)}
        finally:
            async with self._state_lock:
                self._starting = False

    async def _ohf_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload:
            raise BrokerProtocolError("ohf-identity payload must be empty")
        binary = getattr(self.adapter, "binary", None)
        if binary is None:
            raise BrokerStateError("worker binary attestation is unavailable")
        return {
            "worker_id": self.policy.worker_id,
            "binary_sha256": str(getattr(binary, "sha256", "") or ""),
            "binary_version": str(getattr(binary, "version", "") or ""),
            "operator_harness_armed": self.operator_harness_armed,
        }

    async def _ohf_start(
        self, payload: dict[str, Any], *, resume: bool
    ) -> dict[str, Any]:
        self._require_current_autonomy()
        expected = {"operation_id", "requested", "epoch", "generation"}
        if resume:
            expected.add("provider_session")
        if set(payload) != expected:
            raise BrokerProtocolError("OHF session payload fields are invalid")
        try:
            operation = wire_operation_id(payload["operation_id"])
            requested = wire_requested_execution_profile(payload["requested"])
            epoch = wire_session_epoch_ref(payload["epoch"])
            generation = wire_process_generation_ref(payload["generation"])
            handoff = (
                wire_provider_session_handoff(payload["provider_session"])
                if resume
                else None
            )
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        if (
            epoch.attempt_id == ""
            or epoch.worker_id != self.policy.worker_id
            or generation.worker_id != self.policy.worker_id
            or generation.session_epoch_id != epoch.session_epoch_id
            or requested.worker_id != self.policy.worker_id
        ):
            raise BrokerProtocolError("OHF session identities do not match the broker")
        if handoff is not None and handoff.worker_id != self.policy.worker_id:
            raise BrokerProtocolError("OHF resume handoff does not match the broker")
        async with self._state_lock:
            if self._quarantined_reason is not None:
                raise BrokerStateError(
                    f"worker broker is quarantined: {self._quarantined_reason}"
                )
            if (
                self._active_run_id is not None
                or self._operator_run is not None
                or self._starting
                or self._validation_busy
                or self._status_sweep_busy
            ):
                raise BrokerStateError("the worker broker already has active work")
            if handoff is not None:
                prior_attempt = self._operator_session_attempts.get(
                    handoff.provider_session_id
                )
                if prior_attempt is not None and prior_attempt != epoch.attempt_id:
                    raise BrokerStateError(
                        "provider session cannot be reused across Executive Attempts"
                    )
            self._starting = True
        adapter: OperatorAdapter | None = None
        state: _BrokerOperatorRun | None = None
        try:
            adapter, prompts = self._operator_factory(requested)
            if resume:
                assert handoff is not None
                observation = await self._operator_call(
                    "resume",
                    adapter.resume_session,
                    operation_id=operation,
                    epoch=epoch,
                    generation=generation,
                    provider_session=handoff,
                    requested=requested,
                )
            else:
                observation = await self._operator_call(
                    "start",
                    adapter.start_session,
                    operation_id=operation,
                    requested=requested,
                    epoch=epoch,
                    generation=generation,
                )
            provider_session_id = str(
                getattr(observation, "provider_session_id", "") or ""
            )
            if not isinstance(observation, SessionStartObservation) or not provider_session_id:
                raise BrokerStateError(
                    "operator start returned no typed provider session identity"
                )
            if handoff is not None and provider_session_id != handoff.provider_session_id:
                raise BrokerStateError(
                    "operator resume returned a different provider session identity"
                )
            observed = await self._operator_call(
                "attestation", adapter.observed_attestation, generation
            )
            credentials = await self._operator_call(
                "process principal", adapter.observe_process_credentials, generation
            )
            provider_home = await self._operator_call(
                "provider home", adapter.observe_provider_home_identity, generation
            )
            if (
                not isinstance(observed, ObservedHarnessAttestation)
                or not isinstance(credentials, OSProcessCredentialObservation)
                or not isinstance(provider_home, ProviderHomeIdentityObservation)
            ):
                raise BrokerStateError(
                    "operator start returned untyped attestation or principal evidence"
                )
            state = _BrokerOperatorRun(
                adapter=adapter,
                requested=requested,
                epoch=epoch,
                generation=generation,
                provider_session_id=provider_session_id,
                prompts=prompts,
            )
            async with self._state_lock:
                self._operator_run = state
                self._operator_session_attempts[provider_session_id] = epoch.attempt_id
                self._operator_session_attempts.move_to_end(provider_session_id)
                while len(self._operator_session_attempts) > 64:
                    self._operator_session_attempts.popitem(last=False)
            return {
                "observation": operator_to_wire(observation),
                "attestation": operator_to_wire(observed),
                "process_credentials": operator_to_wire(credentials),
                "provider_home": operator_to_wire(provider_home),
                "startup_sweep": self.startup_sweep,
            }
        except Exception:
            if adapter is not None and state is None:
                try:
                    cleanup = await asyncio.to_thread(
                        self.sweeper.sweep, "operator_start_failed"
                    )
                    self.last_sweep = cleanup
                    if cleanup.found_residuals:
                        raise BrokerStateError(
                            "operator start cleanup left a detached same-UID process"
                        )
                except Exception as sweep_exc:
                    async with self._state_lock:
                        self._quarantined_reason = (
                            "operator start cleanup failed: "
                            f"{type(sweep_exc).__name__}"
                        )
            raise
        finally:
            async with self._state_lock:
                self._starting = False

    async def _operator_state(
        self, generation: ProcessGenerationRef
    ) -> _BrokerOperatorRun:
        async with self._state_lock:
            state = self._operator_run
            if state is None or state.generation != generation:
                raise BrokerStateError(
                    "operator generation is not active in this worker broker"
                )
            if state.busy:
                raise BrokerStateError("operator generation already has an active operation")
            state.busy = True
            return state

    async def _operator_release_busy(self, state: _BrokerOperatorRun) -> None:
        async with self._state_lock:
            state.busy = False

    async def _ohf_begin_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_current_autonomy()
        if set(payload) != {
            "operation_id",
            "turn",
            "generation",
            "launch",
            "prompt",
        }:
            raise BrokerProtocolError("ohf-begin-turn payload fields are invalid")
        try:
            operation = wire_operation_id(payload["operation_id"])
            turn = wire_turn_ref(payload["turn"])
            generation = wire_process_generation_ref(payload["generation"])
            launch = wire_launch_comparison(payload["launch"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        prompt = payload["prompt"]
        if (
            not isinstance(prompt, str)
            or not prompt
            or len(prompt.encode("utf-8")) > _MAX_OPERATOR_PROMPT_BYTES
        ):
            raise BrokerProtocolError("operator prompt is outside the closed byte bound")
        state = await self._operator_state(generation)
        try:
            if (
                turn.attempt_id != state.epoch.attempt_id
                or turn.session_epoch_id != state.epoch.session_epoch_id
                or turn.process_generation_id
                != state.generation.process_generation_id
                or launch.requested != state.requested
                or launch.decision is not LaunchDecision.ALLOW
            ):
                raise BrokerProtocolError(
                    "operator turn or launch decision is outside the active generation"
                )
            state.prompts[turn.turn_id] = prompt
            try:
                observation = await self._operator_call(
                    "begin turn",
                    state.adapter.begin_turn,
                    operation_id=operation,
                    turn=turn,
                    generation=generation,
                    launch=launch,
                )
            finally:
                state.prompts.pop(turn.turn_id, None)
            if not isinstance(observation, TurnStartObservation):
                raise BrokerStateError(
                    "operator begin-turn returned an untyped observation"
                )
            return {"observation": operator_to_wire(observation)}
        finally:
            await self._operator_release_busy(state)

    async def _ohf_collect_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"turn", "cursor", "timeout_seconds"}:
            raise BrokerProtocolError("ohf-collect-turn payload fields are invalid")
        try:
            turn = wire_turn_ref(payload["turn"])
            cursor = wire_event_cursor(payload["cursor"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        timeout = payload["timeout_seconds"]
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < float(timeout) <= 300
        ):
            raise BrokerProtocolError("operator turn timeout is outside (0, 300]")
        generation = ProcessGenerationRef(
            process_generation_id=turn.process_generation_id,
            session_epoch_id=turn.session_epoch_id,
            generation_number=0,
            worker_id=self.policy.worker_id,
        )
        async with self._state_lock:
            active = self._operator_run
            if active is None or (
                active.generation.process_generation_id
                != generation.process_generation_id
                or active.epoch.session_epoch_id != generation.session_epoch_id
            ):
                raise BrokerStateError(
                    "operator turn generation is not active in this worker broker"
                )
            generation = active.generation
        state = await self._operator_state(generation)
        try:
            if (
                turn.attempt_id != state.epoch.attempt_id
                or cursor.attempt_id != turn.attempt_id
                or cursor.session_epoch_id != turn.session_epoch_id
                or cursor.process_generation_id != turn.process_generation_id
                or cursor.turn_id != turn.turn_id
            ):
                raise BrokerProtocolError(
                    "operator turn cursor is outside the active generation"
                )
            events, next_cursor = await self._operator_call(
                "read events",
                state.adapter.read_events,
                cursor,
                timeout_seconds=float(timeout),
            )
            candidate = await self._operator_call(
                "collect candidate", state.adapter.collect_candidate_result, turn
            )
            raw = await self._operator_call(
                "observe raw role result", state.adapter.observe_raw_role_result, turn
            )
            events = tuple(events)
            if (
                len(events) > 4096
                or any(not isinstance(item, NormalizedEvent) for item in events)
                or not isinstance(next_cursor, EventCursor)
                or not isinstance(candidate, CandidateResult)
                or not isinstance(raw, RawRoleResultObservation)
            ):
                raise BrokerStateError(
                    "operator collection returned untyped or oversized evidence"
                )
            return {
                "events": operator_to_wire(events),
                "cursor": operator_to_wire(next_cursor),
                "candidate": operator_to_wire(candidate),
                "raw_role_result": operator_to_wire(raw),
            }
        finally:
            await self._operator_release_busy(state)

    async def _ohf_interrupt(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"operation_id", "turn"}:
            raise BrokerProtocolError("ohf-interrupt payload fields are invalid")
        try:
            operation = wire_operation_id(payload["operation_id"])
            turn = wire_turn_ref(payload["turn"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        async with self._state_lock:
            active = self._operator_run
            if active is None or (
                active.generation.process_generation_id != turn.process_generation_id
                or active.epoch.session_epoch_id != turn.session_epoch_id
                or active.epoch.attempt_id != turn.attempt_id
            ):
                raise BrokerStateError("operator turn generation is not active")
            generation = active.generation
        state = await self._operator_state(generation)
        try:
            await self._operator_call(
                "interrupt turn",
                state.adapter.interrupt_turn,
                turn,
                operation_id=operation,
            )
            return {"interrupted": True}
        finally:
            await self._operator_release_busy(state)

    async def _terminal_operator_sweep(self, reason: str) -> UIDSweepReceipt:
        try:
            sweep = await asyncio.to_thread(self.sweeper.sweep, reason)
        except Exception as exc:
            async with self._state_lock:
                self._quarantined_reason = (
                    f"operator terminal UID sweep failed: {type(exc).__name__}"
                )
            raise
        async with self._state_lock:
            self.last_sweep = sweep
        if sweep.found_residuals:
            raise BrokerStateError(
                "operator generation left a detached same-UID process"
            )
        return sweep

    async def _remember_operator_terminal(
        self, state: _BrokerOperatorRun, observation: ReconcileObservation
    ) -> None:
        async with self._state_lock:
            self._operator_terminal[state.generation.process_generation_id] = (
                state.generation,
                observation,
            )
            self._operator_terminal.move_to_end(
                state.generation.process_generation_id
            )
            while len(self._operator_terminal) > _MAX_HISTORY:
                self._operator_terminal.popitem(last=False)
            if self._operator_run is state:
                self._operator_run = None

    async def _ohf_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"operation_id", "generation"}:
            raise BrokerProtocolError("ohf-stop payload fields are invalid")
        try:
            operation = wire_operation_id(payload["operation_id"])
            generation = wire_process_generation_ref(payload["generation"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        state = await self._operator_state(generation)
        try:
            observation = await self._operator_call(
                "graceful stop",
                state.adapter.graceful_stop,
                generation,
                operation_id=operation,
            )
            sweep = await self._terminal_operator_sweep("operator_terminal")
            if (
                not isinstance(observation, ReconcileObservation)
                or observation.process_liveness is not ProcessLiveness.PROVEN_DEAD
                or observation.provider_writer_state is not ProviderWriterState.RELEASED
            ):
                async with self._state_lock:
                    self._quarantined_reason = (
                        "operator graceful stop lacked exact dead/released evidence"
                    )
                raise BrokerStateError(
                    "operator graceful stop lacked exact dead/released evidence"
                )
            await self._remember_operator_terminal(state, observation)
            return {
                "observation": operator_to_wire(observation),
                "uid_sweep": sweep,
            }
        finally:
            await self._operator_release_busy(state)

    async def _ohf_cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"operation_id", "generation", "reason"}:
            raise BrokerProtocolError("ohf-cancel payload fields are invalid")
        try:
            operation = wire_operation_id(payload["operation_id"])
            generation = wire_process_generation_ref(payload["generation"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        reason = payload["reason"]
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise BrokerProtocolError("operator cancellation reason is invalid")
        state = await self._operator_state(generation)
        try:
            observation = await self._operator_call(
                "cancel",
                state.adapter.cancel,
                generation,
                reason=reason.strip(),
                operation_id=operation,
            )
            sweep = await self._terminal_operator_sweep("operator_terminal")
            if (
                not isinstance(observation, ReconcileObservation)
                or observation.process_liveness is not ProcessLiveness.PROVEN_DEAD
                or observation.provider_writer_state is not ProviderWriterState.RELEASED
            ):
                async with self._state_lock:
                    self._quarantined_reason = (
                        "operator cancellation lacked exact dead/released evidence"
                    )
                raise BrokerStateError(
                    "operator cancellation lacked exact dead/released evidence"
                )
            await self._remember_operator_terminal(state, observation)
            return {
                "observation": operator_to_wire(observation),
                "uid_sweep": sweep,
            }
        finally:
            await self._operator_release_busy(state)

    async def _ohf_reconcile(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"generation"}:
            raise BrokerProtocolError("ohf-reconcile payload fields are invalid")
        try:
            generation = wire_process_generation_ref(payload["generation"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        async with self._state_lock:
            terminal_receipt = self._operator_terminal.get(
                generation.process_generation_id
            )
        if terminal_receipt is not None:
            terminal_generation, terminal = terminal_receipt
            if terminal_generation != generation:
                raise BrokerProtocolError(
                    "operator terminal generation identity drifted"
                )
            return {"observation": operator_to_wire(terminal), "terminal": True}
        state = await self._operator_state(generation)
        try:
            observation = await self._operator_call(
                "reconcile", state.adapter.reconcile, generation
            )
            if not isinstance(observation, ReconcileObservation):
                raise BrokerStateError(
                    "operator reconciliation returned an untyped observation"
                )
            return {"observation": operator_to_wire(observation), "terminal": False}
        finally:
            await self._operator_release_busy(state)

    async def _ohf_reconcile_absence(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Prove a lost in-memory generation absent at the dedicated-UID boundary.

        This operation exists only for broker-restart reconciliation.  It does
        not adopt a provider session or allocate lifecycle identity: the
        Executive supplies the already-durable generation/process/session
        tuple, while the worker broker proves that no untrusted process remains
        under its dedicated UID.  Runtime validates the returned observation
        against its own immutable rows before it can affect authority.
        """

        if set(payload) != {
            "generation",
            "process",
            "provider_session_id",
            "config_digest",
        }:
            raise BrokerProtocolError(
                "ohf-reconcile-absence payload fields are invalid"
            )
        try:
            generation = wire_process_generation_ref(payload["generation"])
            process = wire_process_identity_observation(payload["process"])
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(str(exc)) from exc
        provider_session_id = payload["provider_session_id"]
        config_digest = payload["config_digest"]
        if (
            generation.worker_id != self.policy.worker_id
            or not isinstance(provider_session_id, str)
            or not provider_session_id.strip()
            or len(provider_session_id) > 512
            or not isinstance(config_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", config_digest) is None
            or process.pid is None
            or process.pgid is None
            or not process.process_start_identity
            or not process.boot_id
        ):
            raise BrokerProtocolError(
                "OHF absence identity is incomplete or outside broker policy"
            )
        async with self._state_lock:
            if (
                self._active_run_id is not None
                or self._operator_run is not None
                or self._starting
                or self._validation_busy
                or self._status_sweep_busy
            ):
                raise BrokerStateError(
                    "OHF absence proof requires an idle worker broker"
                )
            self._status_sweep_busy = True
        try:
            sweep = await asyncio.to_thread(
                self.sweeper.sweep, "operator_reconcile_absence"
            )
        finally:
            async with self._state_lock:
                self._status_sweep_busy = False
        async with self._state_lock:
            self.last_sweep = sweep
        if not sweep.passed:
            raise BrokerStateError(
                "dedicated UID is not quiescent after OHF absence sweep"
            )
        observation = ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=process,
            provider_session_reachable=False,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id=provider_session_id,
            observed_config_digest=config_digest,
        )
        return {
            "observation": operator_to_wire(observation),
            "uid_sweep": sweep,
        }

    async def _start(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_current_autonomy()
        if set(payload) != {"launch_spec", "validation_commands"}:
            raise BrokerProtocolError("start payload fields are invalid")
        spec = _launch_spec(payload["launch_spec"], self.policy)
        commands = _validation_commands(payload["validation_commands"])
        async with self._state_lock:
            if self._quarantined_reason is not None:
                raise BrokerStateError(f"worker broker is quarantined: {self._quarantined_reason}")
            if (
                self._active_run_id is not None
                or self._operator_run is not None
                or self._starting
                or self._validation_busy
                or self._status_sweep_busy
            ):
                raise BrokerStateError("the worker broker already has active work")
            if spec.run_id in self._runs:
                raise BrokerStateError("run_id cannot be reused")
            self._starting = True
        try:
            process_ref = await self.adapter.start(spec)
            attestation_reader = getattr(self.adapter, "launch_attestation", None)
            attestation = attestation_reader(process_ref) if callable(attestation_reader) else None
        except Exception:
            try:
                self.last_sweep = await asyncio.to_thread(self.sweeper.sweep, "start_failed")
            except Exception as sweep_exc:
                async with self._state_lock:
                    self._quarantined_reason = f"start cleanup failed: {type(sweep_exc).__name__}"
            raise
        finally:
            async with self._state_lock:
                self._starting = False
        async with self._state_lock:
            state = _BrokerRun(
                spec=spec,
                process_ref=process_ref,
                validation_commands=commands,
                launch_attestation=attestation,
            )
            self._remember(spec.run_id, state)
            self._active_run_id = spec.run_id
        return {
            "process_ref": process_ref,
            "launch_attestation": attestation,
            "startup_sweep": self.startup_sweep,
        }

    async def _status(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) - {"run_id", "fresh_uid_sweep"}:
            raise BrokerProtocolError("status payload fields are invalid")
        run_id = payload.get("run_id")
        fresh_uid_sweep = payload.get("fresh_uid_sweep", False)
        if not isinstance(fresh_uid_sweep, bool):
            raise BrokerProtocolError("fresh_uid_sweep must be a boolean")
        status_sweep: UIDSweepReceipt | None = None
        if fresh_uid_sweep:
            async with self._state_lock:
                if (
                    self._active_run_id is not None
                    or self._operator_run is not None
                    or self._starting
                    or self._validation_busy
                    or self._status_sweep_busy
                ):
                    raise BrokerStateError(
                        "a fresh status UID sweep requires an idle worker broker"
                    )
                self._status_sweep_busy = True
            try:
                status_sweep = await asyncio.to_thread(
                    self.sweeper.sweep, "status_absence"
                )
            except Exception as exc:
                async with self._state_lock:
                    self._quarantined_reason = (
                        f"status UID sweep failed: {type(exc).__name__}"
                    )
                    self._status_sweep_busy = False
                raise
        async with self._state_lock:
            try:
                if status_sweep is not None:
                    self.last_sweep = status_sweep
                result: dict[str, Any] = {
                    "broker_pid": os.getpid(),
                    "worker_uid": os.geteuid(),
                    "worker_gid": os.getegid(),
                    "supplementary_gids": sorted(set(os.getgroups()) - {os.getegid()}),
                    "active_run_id": self._active_run_id,
                    "active_operator_attempt_id": (
                        self._operator_run.epoch.attempt_id
                        if self._operator_run is not None
                        else None
                    ),
                    "active_operator_generation_id": (
                        self._operator_run.generation.process_generation_id
                        if self._operator_run is not None
                        else None
                    ),
                    "operator_harness_armed": self.operator_harness_armed,
                    "starting": self._starting,
                    "validation_busy": self._validation_busy,
                    "status_sweep_busy": False if fresh_uid_sweep else self._status_sweep_busy,
                    "quarantined_reason": self._quarantined_reason,
                    "startup_sweep": self.startup_sweep,
                    "last_sweep": self.last_sweep,
                    "status_sweep": status_sweep,
                }
                state = self._run(run_id) if run_id is not None else None
            finally:
                if fresh_uid_sweep:
                    self._status_sweep_busy = False
        if run_id is not None:
            assert state is not None
            if state.collected_receipt is not None:
                status: Any = state.collected_receipt.result.status
            elif state.cancel_receipt is not None:
                status = WorkerRunStatus.CANCELLED
            elif state.terminal_error is not None:
                status = "ERROR"
            else:
                status = await self.adapter.status(state.process_ref)
            result["run"] = {
                "run_id": run_id,
                "status": status,
                "process_ref": state.process_ref,
                "terminal_error": state.terminal_error,
                "validated_commands": [list(command) for command in state.validation_receipts],
            }
        return result

    async def _terminal_sweep(
        self,
        state: _BrokerRun,
        *,
        reason: str,
    ) -> UIDSweepReceipt:
        """Run exactly one same-UID sweep when collect and cancel race."""

        async with self._state_lock:
            if state.terminal_sweep_task is None:
                state.terminal_sweep_task = asyncio.create_task(
                    asyncio.to_thread(self.sweeper.sweep, reason)
                )
            task = state.terminal_sweep_task
        try:
            receipt = await task
        except Exception as exc:
            async with self._state_lock:
                self._quarantined_reason = f"terminal UID sweep failed: {type(exc).__name__}"
                state.terminal_error = self._quarantined_reason
            raise
        async with self._state_lock:
            self.last_sweep = receipt
        return receipt

    async def _collect(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"run_id"}:
            raise BrokerProtocolError("collect payload fields are invalid")
        async with self._state_lock:
            state = self._run(payload["run_id"])
            if self._active_run_id != state.spec.run_id:
                raise BrokerStateError("only the active run can be collected")
            if state.collecting:
                raise BrokerStateError("collection is already in progress")
            state.collecting = True
        try:
            receipt = await self.adapter.collect_result(state.process_ref)
            async with self._state_lock:
                state.collected_receipt = receipt
            sweep = await self._terminal_sweep(state, reason="run_terminal")
            async with self._state_lock:
                if self._active_run_id == state.spec.run_id:
                    self._active_run_id = None
            if sweep.found_residuals:
                async with self._state_lock:
                    state.terminal_error = (
                        "worker left a detached same-UID process after collection"
                    )
                raise BrokerStateError(state.terminal_error)
            return {"collection": receipt, "uid_sweep": sweep}
        finally:
            async with self._state_lock:
                state.collecting = False

    async def _cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"run_id", "reason"}:
            raise BrokerProtocolError("cancel payload fields are invalid")
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise BrokerProtocolError("cancel reason is invalid")
        async with self._state_lock:
            state = self._run(payload["run_id"])
            if self._active_run_id != state.spec.run_id:
                raise BrokerStateError("only the active run can be cancelled")
            if state.cancelling:
                raise BrokerStateError("cancellation is already in progress")
            state.cancelling = True
        adapter_error: Exception | None = None
        receipt: Any = None
        try:
            receipt = await self.adapter.cancel(state.process_ref, reason.strip())
            async with self._state_lock:
                state.cancel_receipt = receipt
        except Exception as exc:  # cleanup continues through the stronger UID boundary
            adapter_error = exc
        finally:
            async with self._state_lock:
                state.cancelling = False
        sweep = await self._terminal_sweep(state, reason="run_terminal")
        async with self._state_lock:
            if self._active_run_id == state.spec.run_id:
                self._active_run_id = None
        if adapter_error is not None:
            async with self._state_lock:
                state.terminal_error = (
                    f"adapter cancellation failed: {type(adapter_error).__name__}"
                )
            raise BrokerStateError(state.terminal_error) from adapter_error
        return {"cancellation": receipt, "uid_sweep": sweep}

    async def _validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"run_id", "argv", "timeout_seconds"}:
            raise BrokerProtocolError("validate payload fields are invalid")
        commands = _validation_commands([payload["argv"]])
        command = commands[0]
        timeout = payload.get("timeout_seconds")
        if not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 3600:
            raise BrokerProtocolError("validation timeout is outside the safe range")
        async with self._state_lock:
            if (
                self._active_run_id is not None
                or self._operator_run is not None
                or self._starting
                or self._validation_busy
                or self._status_sweep_busy
            ):
                raise BrokerStateError("validation is serialized after worker collection")
            state = self._run(payload["run_id"])
            if state.collected_receipt is None:
                raise BrokerStateError("validation requires a collected worker result")
            if command not in state.validation_commands:
                raise BrokerProtocolError("validation argv was not frozen in the start request")
            if command in state.validation_receipts:
                raise BrokerStateError("validation argv has already been executed")
            self._validation_busy = True
        try:
            adapter_error: Exception | None = None
            receipt: Any = None
            try:
                receipt = await self.adapter.run_validation_argv(
                    state.spec,
                    command,
                    timeout_seconds=float(timeout),
                )
            except Exception as exc:
                adapter_error = exc
            try:
                sweep = await asyncio.to_thread(self.sweeper.sweep, "validation_terminal")
            except Exception as exc:
                async with self._state_lock:
                    self._quarantined_reason = (
                        f"validation UID sweep failed: {type(exc).__name__}"
                    )
                    state.terminal_error = self._quarantined_reason
                raise
            async with self._state_lock:
                self.last_sweep = sweep
            if adapter_error is not None:
                async with self._state_lock:
                    state.terminal_error = (
                        f"adapter validation failed: {type(adapter_error).__name__}"
                    )
                raise BrokerStateError(state.terminal_error) from adapter_error
            if sweep.found_residuals:
                async with self._state_lock:
                    state.terminal_error = "validation left a detached same-UID process"
                raise BrokerStateError(state.terminal_error)
            async with self._state_lock:
                state.validation_receipts[command] = receipt
            return {"validation": receipt, "uid_sweep": sweep}
        finally:
            async with self._state_lock:
                self._validation_busy = False

    async def shutdown(self) -> None:
        """Cancel an active run, then prove the dedicated UID is quiescent."""

        async with self._state_lock:
            active_run_id = self._active_run_id
            operator = self._operator_run
        if active_run_id is not None:
            try:
                await self._cancel(
                    {"run_id": active_run_id, "reason": "worker broker shutdown"}
                )
            except WorkerBrokerError:
                pass
        if operator is not None:
            try:
                await self._ohf_cancel(
                    {
                        "operation_id": {
                            "command_id": (
                                "ohf-op:broker-shutdown-"
                                + operator.generation.process_generation_id
                            )[:113]
                        },
                        "generation": operator_to_wire(operator.generation),
                        "reason": "worker broker shutdown",
                    }
                )
            except WorkerBrokerError:
                pass
        self.last_sweep = await asyncio.to_thread(self.sweeper.sweep, "broker_shutdown")

    async def _write_interrupted_envelope(
        self,
        writer: asyncio.StreamWriter,
        request_id: str,
        operation: str,
        exc: BaseException,
    ) -> None:
        """Best-effort typed envelope for a handler that never reached delivery.

        This is called while ``exc`` is propagating, so it must never raise:
        the peer may already be gone, and the caller's exception -- including a
        ``CancelledError`` that has to keep unwinding -- stays authoritative.
        """

        if isinstance(exc, Exception):
            code = "InternalBrokerError"
            message = f"broker response delivery failed: {type(exc).__name__}"
        else:
            code = BROKER_UNAVAILABLE_ERROR_CODE
            message = (
                "broker is unavailable: the connection handler was interrupted "
                f"before the operation completed ({type(exc).__name__})"
            )
        try:
            writer.write(
                _frame_response(
                    {
                        "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                        "request_id": request_id,
                        "operation": operation,
                        "ok": False,
                        "error": {"code": code, "message": message},
                    }
                )
            )
            await writer.drain()
        except BaseException:
            # The peer is gone, or the interrupt landed again inside this
            # best-effort write.  Either way the caller re-raises the original.
            return

    async def handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Serve one authenticated request and close the connection.

        Every exit path that can still reach the peer frames exactly one
        newline-terminated envelope.  ``asyncio.CancelledError``,
        ``SystemExit`` and ``KeyboardInterrupt`` are direct ``BaseException``
        subclasses, so before this guard they unwound the handler straight into
        the teardown with zero bytes written -- the control side saw a bare EOF
        and could only report an opaque framing error with no record of which
        condition happened.  ``scripts/executive_os_phase1c_worker.py`` reaches
        exactly that state on every launchd stop that lands mid-``start``.  The
        interrupted path now frames a typed ``BrokerUnavailableError`` envelope
        and re-raises, so cancellation still propagates and shutdown semantics
        are unchanged.

        That envelope is written ONLY once the request's identity is known.
        The same shutdown cancels handlers still parked in ``readline`` whose
        request never arrived; an envelope carrying the ``"invalid"`` sentinel
        would fail the client's request-id/operation check and surface as
        ``broker response identity does not match the request`` -- a worse,
        actively misleading diagnosis than the clean-EOF message the client
        derives when no envelope is sent at all.  Pre-parse interrupts
        therefore fall through to that accurate message deliberately.
        """

        request_id = "invalid"
        operation = "invalid"
        identity_known = False
        delivered = False
        try:
            try:
                peer_socket = writer.get_extra_info("socket")
                if peer_socket is None:
                    raise PeerAuthorizationError("connection has no Unix peer socket")
                peer = self.peer_resolver(peer_socket)
                self._authorize_peer(peer)
                raw = await reader.readline()
                if (
                    not raw
                    or len(raw) > self.policy.max_request_bytes
                    or not raw.endswith(b"\n")
                ):
                    raise BrokerProtocolError("request framing is invalid")
                try:
                    request = json.loads(raw.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BrokerProtocolError("request is not valid UTF-8 JSON") from exc
                if isinstance(request, dict):
                    parsed_id = str(request.get("request_id") or "")[:128]
                    parsed_operation = str(request.get("operation") or "")[:32]
                    if parsed_id:
                        request_id = parsed_id
                    if parsed_operation:
                        operation = parsed_operation
                    # Defense in depth, not load-bearing today: `execute`
                    # validates both identity fields synchronously, so a
                    # request missing either one raises before the first
                    # `await` and no interrupt can land while this is False.
                    # It becomes load-bearing the moment anything awaits
                    # earlier -- pin it with a test if that changes.
                    identity_known = bool(parsed_id and parsed_operation)
                response = await self.execute(request, peer=peer)
            except LaunchValidationStageError as exc:
                response = {
                    "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                    "request_id": request_id,
                    "operation": operation,
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": f"Launch validation failed at stage: {exc.stage}",
                        "stage": exc.stage,
                    },
                }
            except GitPreflightFailed as exc:
                response = {
                    "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                    "request_id": request_id,
                    "operation": operation,
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": (
                            f"Git preflight failed: {exc.operation} "
                            f"(exit {exc.exit_code})"
                        ),
                        "operation": exc.operation,
                        "exit_code": exc.exit_code,
                    },
                }
            except GitPreflightTimeout as exc:
                # These exceptions deliberately expose only audited fields:
                # an allowlisted validation stage or Git operation, a bounded
                # exit code, and the fixed timeout. Other adapter failures stay
                # opaque below.
                response = {
                    "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                    "request_id": request_id,
                    "operation": operation,
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": (
                            f"Git preflight timed out after "
                            f"{exc.timeout_seconds:g}s: {exc.operation}"
                        ),
                        "operation": exc.operation,
                        "timeout_seconds": exc.timeout_seconds,
                    },
                }
            except WorkerBrokerError as exc:
                response = {
                    "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                    "request_id": request_id,
                    "operation": operation,
                    "ok": False,
                    "error": {"code": type(exc).__name__, "message": str(exc)[:500]},
                }
            except Exception as exc:  # keep traces and values out of the socket
                response = {
                    "schema_version": BROKER_RESPONSE_SCHEMA_VERSION,
                    "request_id": request_id,
                    "operation": operation,
                    "ok": False,
                    "error": {
                        "code": "InternalBrokerError",
                        "message": f"broker operation failed: {type(exc).__name__}",
                    },
                }
            payload = _frame_response(response)
            delivered = True
            writer.write(payload)
            await writer.drain()
        except BaseException as exc:
            # `delivered` keeps a second envelope off a stream that already
            # carries one (a drain() that fails after its write() succeeded
            # would otherwise corrupt the frame); `identity_known` keeps an
            # unaddressable envelope off the wire entirely.
            if not delivered and identity_known:
                await self._write_interrupted_envelope(
                    writer, request_id, operation, exc
                )
            raise
        finally:
            writer.close()
            await writer.wait_closed()

    async def serve(self, activated_socket: socket.socket) -> None:
        """Run forever on one launchd-owned Unix listener."""

        self.initialize()
        server = await asyncio.start_unix_server(
            self.handle_connection,
            sock=activated_socket,
            limit=self.policy.max_request_bytes,
        )
        async with server:
            await server.serve_forever()


class RemoteBrokerError(WorkerBrokerError):
    """Typed error returned by the worker-side broker."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str | None = None,
        operation: str | None = None,
        exit_code: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.code = str(code)
        self.stage = stage
        self.operation = operation
        self.exit_code = exit_code
        self.timeout_seconds = timeout_seconds
        super().__init__(str(message))


class WorkerBrokerClient:
    """One-request-per-connection async/sync Unix client for the control UID."""

    def __init__(
        self,
        socket_path: str | Path,
        *,
        timeout_seconds: float = 30.0,
        max_response_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.socket_path = Path(socket_path)
        if not self.socket_path.is_absolute():
            raise WorkerBrokerError("worker broker socket path must be absolute")
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)
        if not 0.1 <= self.timeout_seconds <= 3600:
            raise WorkerBrokerError("worker broker client timeout is outside the safe range")
        if not 1024 <= self.max_response_bytes <= 16 * 1024 * 1024:
            raise WorkerBrokerError("worker broker response ceiling is invalid")

    async def request(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if operation not in _ALLOWED_OPERATIONS:
            raise BrokerProtocolError("client operation is not allowed")
        request_id = f"req-{uuid.uuid4().hex}"
        document = {
            "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "operation": operation,
            "payload": _jsonable(dict(payload)),
        }
        encoded = (
            json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise BrokerProtocolError("client request exceeds the broker ceiling")

        async def exchange() -> bytes:
            reader, writer = await asyncio.open_unix_connection(
                str(self.socket_path),
                limit=self.max_response_bytes,
            )
            try:
                writer.write(encoded)
                await writer.drain()
                raw = await reader.readline()
                # One opaque "framing is invalid" used to cover three very
                # different conditions.  Name each one and carry the bounded
                # evidence that tells them apart after the fact.
                if not raw:
                    raise BrokerProtocolError(
                        "broker closed the connection without sending a response "
                        "(0 bytes read): the broker process died or its connection "
                        "handler was cancelled mid-request"
                    )
                if len(raw) > self.max_response_bytes:
                    raise BrokerProtocolError(
                        f"broker response exceeds the client ceiling: {len(raw)} "
                        f"bytes read, ceiling {self.max_response_bytes} bytes"
                    )
                if not raw.endswith(b"\n"):
                    raise BrokerProtocolError(
                        f"broker response is unterminated: {len(raw)} bytes read "
                        "with no newline terminator (excerpt "
                        f"{_response_excerpt(raw)!r})"
                    )
                return raw
            finally:
                writer.close()
                await writer.wait_closed()

        effective_timeout = (
            self.timeout_seconds if timeout_seconds is None else float(timeout_seconds)
        )
        if not 0.1 <= effective_timeout <= 25 * 60 * 60:
            raise BrokerProtocolError("per-request timeout is outside the safe range")
        raw = await asyncio.wait_for(exchange(), timeout=effective_timeout)
        try:
            response = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerProtocolError("broker response is not valid UTF-8 JSON") from exc
        if not isinstance(response, dict):
            raise BrokerProtocolError("broker response must be an object")
        if response.get("schema_version") != BROKER_RESPONSE_SCHEMA_VERSION:
            raise BrokerProtocolError("broker response schema is unsupported")
        if response.get("request_id") != request_id or response.get("operation") != operation:
            raise BrokerProtocolError("broker response identity does not match the request")
        if response.get("ok") is not True:
            error = response.get("error")
            if not isinstance(error, dict):
                raise BrokerProtocolError("broker error response is malformed")
            code = str(error.get("code") or "RemoteBrokerError")
            try:
                if code == LaunchValidationStageError.code:
                    stage = error.get("stage")
                    if not isinstance(stage, str):
                        raise ValueError("stage is not a string")
                    classified = LaunchValidationStageError(stage=stage)
                    raise RemoteBrokerError(
                        code,
                        str(classified),
                        stage=classified.stage,
                    )
                if code == GitPreflightFailed.code:
                    operation = error.get("operation")
                    exit_code = error.get("exit_code")
                    if not isinstance(operation, str):
                        raise ValueError("operation is not a string")
                    classified = GitPreflightFailed(
                        operation=operation,
                        exit_code=exit_code,
                    )
                    raise RemoteBrokerError(
                        code,
                        str(classified),
                        operation=classified.operation,
                        exit_code=classified.exit_code,
                    )
                if code == GitPreflightTimeout.code:
                    operation = error.get("operation")
                    timeout_seconds = error.get("timeout_seconds")
                    if not isinstance(operation, str):
                        raise ValueError("operation is not a string")
                    classified = GitPreflightTimeout(
                        operation=operation,
                        timeout_seconds=timeout_seconds,
                    )
                    raise RemoteBrokerError(
                        code,
                        str(classified),
                        operation=classified.operation,
                        timeout_seconds=classified.timeout_seconds,
                    )
            except RemoteBrokerError:
                raise
            except (TypeError, ValueError) as exc:
                raise BrokerProtocolError(
                    "broker typed error response is malformed"
                ) from exc
            raise RemoteBrokerError(
                code,
                str(error.get("message") or "worker broker rejected the request")[:500],
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise BrokerProtocolError("broker result must be an object")
        return result

    def request_sync(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Synchronous startup/reconciliation seam; never call from a running loop."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.request(operation, payload, timeout_seconds=timeout_seconds)
            )
        raise WorkerBrokerError("request_sync cannot run inside an active event loop")


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BrokerProtocolError(f"remote {field} must be an object")
    return value


def _binary_from_json(value: Any) -> BinaryAttestation:
    raw = _mapping(value, field="binary attestation")
    try:
        return BinaryAttestation(**raw)
    except (TypeError, ValueError) as exc:
        raise BrokerProtocolError("remote binary attestation is invalid") from exc


def _process_ref_from_json(value: Any) -> ProcessRef:
    raw = _mapping(value, field="process reference").copy()
    raw["binary"] = _binary_from_json(raw.get("binary"))
    try:
        return ProcessRef(**raw)
    except (TypeError, ValueError) as exc:
        raise BrokerProtocolError("remote process reference is invalid") from exc


def _collection_from_json(value: Any) -> CollectionReceipt:
    raw = _mapping(value, field="collection receipt")
    result_raw = _mapping(raw.get("result"), field="worker result").copy()
    artifacts = result_raw.get("artifact_manifest")
    if not isinstance(artifacts, list):
        raise BrokerProtocolError("remote artifact manifest is invalid")
    try:
        result_raw["artifact_manifest"] = tuple(
            ArtifactReceipt(**_mapping(item, field="artifact receipt")) for item in artifacts
        )
        result_raw["status"] = WorkerRunStatus(result_raw["status"])
        result = WorkerResult(**result_raw)
        return CollectionReceipt(
            process_ref=_process_ref_from_json(raw.get("process_ref")),
            result=result,
            stdout_sha256=raw["stdout_sha256"],
            stderr_sha256=raw["stderr_sha256"],
            result_sha256=raw.get("result_sha256"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BrokerProtocolError("remote collection receipt is invalid") from exc


def _cancel_from_json(value: Any) -> CancelReceipt:
    try:
        return CancelReceipt(**_mapping(value, field="cancel receipt"))
    except (TypeError, ValueError) as exc:
        raise BrokerProtocolError("remote cancel receipt is invalid") from exc


def _validation_from_json(value: Any) -> ValidationReceipt:
    raw = _mapping(value, field="validation receipt").copy()
    argv = raw.get("argv")
    if not isinstance(argv, list):
        raise BrokerProtocolError("remote validation argv is invalid")
    raw["argv"] = tuple(argv)
    try:
        return ValidationReceipt(**raw)
    except (TypeError, ValueError) as exc:
        raise BrokerProtocolError("remote validation receipt is invalid") from exc


def _uid_sweep_from_json(value: Any) -> dict[str, Any]:
    raw = _mapping(value, field="UID sweep receipt").copy()
    if not uid_sweep_receipt_is_passing(raw):
        raise BrokerProtocolError("remote UID sweep receipt is not a passing v2 receipt")
    return raw


def _launch_spec_to_json(spec: LaunchSpec) -> dict[str, Any]:
    return _jsonable(dataclasses.asdict(spec))


class RemoteCodexWorkerAdapter:
    """Control-side Codex adapter facade backed by the distinct-UID broker."""

    def __init__(
        self,
        client: WorkerBrokerClient,
        *,
        validation_commands_for_spec: (
            Callable[[LaunchSpec], Sequence[Sequence[str]]] | None
        ) = None,
    ) -> None:
        self.client = client
        self.validation_commands_for_spec = validation_commands_for_spec or (lambda _spec: ())
        self._refs: dict[str, ProcessRef] = {}
        self._attestations: dict[str, Mapping[str, Any]] = {}
        self._specs: dict[str, LaunchSpec] = {}
        self._uid_sweeps: dict[str, Mapping[str, Any]] = {}
        self.startup_uid_sweep: Mapping[str, Any] | None = None
        self.inspector = _UnavailableRemoteInspector()

    async def start(self, spec: LaunchSpec) -> ProcessRef:
        commands = [list(command) for command in self.validation_commands_for_spec(spec)]
        result = await self.client.request(
            "start",
            {
                "launch_spec": _launch_spec_to_json(spec),
                "validation_commands": commands,
            },
        )
        process_ref = _process_ref_from_json(result.get("process_ref"))
        if process_ref.run_id != spec.run_id:
            raise BrokerProtocolError("remote process run_id does not match LaunchSpec")
        attestation = _mapping(result.get("launch_attestation"), field="launch attestation")
        startup_sweep = _uid_sweep_from_json(result.get("startup_sweep"))
        self._refs[spec.run_id] = process_ref
        self._attestations[spec.run_id] = attestation
        self._specs[spec.run_id] = spec
        self.startup_uid_sweep = startup_sweep
        return process_ref

    def launch_attestation(self, ref: ProcessRef) -> Mapping[str, Any]:
        if self._refs.get(ref.run_id) != ref:
            raise BrokerStateError("unknown or altered remote ProcessRef")
        return self._attestations[ref.run_id]

    def uid_sweep_receipt(self, ref: ProcessRef) -> Mapping[str, Any]:
        """Return the last validated per-run broker sweep for durable persistence."""

        if self._refs.get(ref.run_id) != ref or ref.run_id not in self._uid_sweeps:
            raise BrokerStateError("no remote UID sweep is available for this ProcessRef")
        return self._uid_sweeps[ref.run_id]

    async def cleanup_unbound_run(self, run_id: str) -> Mapping[str, Any]:
        """Cancel a start whose response was lost, then prove broker-wide absence."""

        terminal_sweep: Mapping[str, Any] | None = None
        try:
            cancelled = await self.client.request(
                "cancel",
                {"run_id": run_id, "reason": "ambiguous control-side start response"},
            )
            terminal_sweep = _uid_sweep_from_json(cancelled.get("uid_sweep"))
        except RemoteBrokerError as exc:
            if exc.code != "BrokerStateError":
                raise
        status = await self.client.request("status", {"fresh_uid_sweep": True})
        sweep = _uid_sweep_from_json(status.get("status_sweep"))
        if (
            status.get("active_run_id") is not None
            or status.get("starting") is not False
            or status.get("validation_busy") is not False
            or status.get("status_sweep_busy") is not False
            or status.get("quarantined_reason") is not None
        ):
            raise BrokerStateError("ambiguous start cleanup did not prove broker absence")
        combined = dict(sweep)
        if terminal_sweep is not None:
            combined["preceding_terminal_sweep"] = dict(terminal_sweep)
        self._uid_sweeps[run_id] = combined
        return combined

    async def status(self, ref: ProcessRef) -> WorkerRunStatus:
        if self._refs.get(ref.run_id) != ref:
            raise BrokerStateError("unknown or altered remote ProcessRef")
        result = await self.client.request("status", {"run_id": ref.run_id})
        run = _mapping(result.get("run"), field="run status")
        value = run.get("status")
        aliases = {
            "COLLECTED": WorkerRunStatus.SUCCEEDED,
            "ERROR": WorkerRunStatus.FAILED,
        }
        if value in aliases:
            return aliases[str(value)]
        try:
            return WorkerRunStatus(value)
        except ValueError as exc:
            raise BrokerProtocolError("remote worker status is invalid") from exc

    async def collect_result(self, ref: ProcessRef) -> CollectionReceipt:
        if self._refs.get(ref.run_id) != ref:
            raise BrokerStateError("unknown or altered remote ProcessRef")
        spec = self._specs[ref.run_id]
        result = await self.client.request(
            "collect",
            {"run_id": ref.run_id},
            timeout_seconds=float(spec.timeout_seconds)
            + max(60.0, float(spec.cancel_grace_seconds) + 30.0),
        )
        receipt = _collection_from_json(result.get("collection"))
        collected_ref = receipt.process_ref
        immutable_ref = dataclasses.replace(
            collected_ref,
            provider_session_id=ref.provider_session_id,
        )
        if immutable_ref != ref:
            raise BrokerProtocolError("remote collection changed immutable process identity")
        if (
            ref.provider_session_id is not None
            and collected_ref.provider_session_id != ref.provider_session_id
        ):
            raise BrokerProtocolError("remote collection changed provider session identity")
        if collected_ref.provider_session_id != receipt.result.provider_session_id:
            raise BrokerProtocolError("remote collection provider session identities disagree")
        self._uid_sweeps[ref.run_id] = _uid_sweep_from_json(result.get("uid_sweep"))
        return receipt

    async def cancel(self, ref: ProcessRef, reason: str) -> CancelReceipt:
        if self._refs.get(ref.run_id) != ref:
            raise BrokerStateError("unknown or altered remote ProcessRef")
        result = await self.client.request(
            "cancel",
            {"run_id": ref.run_id, "reason": reason},
        )
        self._uid_sweeps[ref.run_id] = _uid_sweep_from_json(result.get("uid_sweep"))
        return _cancel_from_json(result.get("cancellation"))

    async def run_validation_argv(
        self,
        spec: LaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        if self._specs.get(spec.run_id) != spec:
            raise BrokerStateError("unknown or altered remote LaunchSpec")
        result = await self.client.request(
            "validate",
            {
                "run_id": spec.run_id,
                "argv": list(argv),
                "timeout_seconds": float(timeout_seconds),
            },
            timeout_seconds=float(timeout_seconds) + 60.0,
        )
        self._uid_sweeps[spec.run_id] = _uid_sweep_from_json(result.get("uid_sweep"))
        return _validation_from_json(result.get("validation"))


class RemoteWorkerProcessController:
    """Synchronous restart-reconciliation facade over broker status/cancel."""

    def __init__(self, client: WorkerBrokerClient) -> None:
        self.client = client
        self._uid_sweeps: dict[str, Mapping[str, Any]] = {}

    def uid_sweep_receipt(self, attempt_or_run_id: Any) -> Mapping[str, Any]:
        """Return the validated sweep captured during restart cancellation."""

        run_id = getattr(attempt_or_run_id, "attempt_id", attempt_or_run_id)
        if not isinstance(run_id, str) or run_id not in self._uid_sweeps:
            raise BrokerStateError("no restart-cancellation UID sweep is available")
        return self._uid_sweeps[run_id]

    def cleanup_unbound_run(self, run_id: str) -> Mapping[str, Any]:
        """Synchronous counterpart used by restart/control recovery seams."""

        try:
            result = self.client.request_sync(
                "cancel",
                {"run_id": run_id, "reason": "ambiguous control-side start response"},
            )
            self._uid_sweeps[run_id] = _uid_sweep_from_json(result.get("uid_sweep"))
        except RemoteBrokerError as exc:
            if exc.code != "BrokerStateError":
                raise
        if not self._fresh_overall_absence(run_id):
            raise BrokerStateError("ambiguous start cleanup did not prove broker absence")
        return self._uid_sweeps[run_id]

    @staticmethod
    def _matches_attempt(process: ProcessRef, attempt: Any) -> bool:
        metadata = getattr(attempt, "launch_metadata", None)
        if not isinstance(metadata, dict):
            return False
        attestation = metadata.get("launch_attestation")
        if not isinstance(attestation, dict):
            return False
        identity = attestation.get("process_identity")
        if not isinstance(identity, dict):
            return False
        expected = {
            "pid": process.pid,
            "pgid": process.pgid,
            "session_id": process.session_id,
            "start_identity": process.process_start_identity,
            "boot_id": process.boot_session_id,
            "effective_uid": process.effective_uid,
            "effective_gid": process.effective_gid,
            "real_uid": process.real_uid,
            "real_gid": process.real_gid,
        }
        if any(identity.get(key) != value for key, value in expected.items()):
            return False
        return (
            process.pid == attempt.pid
            and process.pgid == attempt.pgid
            and process.process_start_identity == attempt.process_start_identity
            and process.boot_session_id == attempt.boot_id
            and attestation.get("launch_nonce") == process.launch_nonce
        )

    def _fresh_overall_absence(self, run_id: str) -> bool:
        try:
            status = self.client.request_sync(
                "status", {"fresh_uid_sweep": True}
            )
        except (WorkerBrokerError, OSError):
            return False
        try:
            sweep = _uid_sweep_from_json(status.get("status_sweep"))
        except BrokerProtocolError:
            return False
        absent = (
            status.get("active_run_id") is None
            and status.get("starting") is False
            and status.get("validation_busy") is False
            and status.get("status_sweep_busy") is False
            and status.get("quarantined_reason") is None
        )
        if absent:
            # Restart reconciliation needs both facts: the terminal sweep that
            # killed residual same-UID descendants and the subsequent fresh
            # idle sweep that closes the race before fence rotation. Preserve
            # the former inside the latter across repeated absence checks.
            previous = self._uid_sweeps.get(run_id)
            preceding = None
            if isinstance(previous, Mapping):
                candidate = previous.get("preceding_terminal_sweep")
                if isinstance(candidate, Mapping):
                    preceding = dict(candidate)
                elif previous.get("reason") != "status_absence":
                    preceding = dict(previous)
            combined = dict(sweep)
            if preceding is not None:
                combined["preceding_terminal_sweep"] = preceding
            self._uid_sweeps[run_id] = combined
        return absent

    def presence(self, attempt: Any):
        from control_plane.executive_supervisor import ProcessPresence

        try:
            status = self.client.request_sync("status", {"run_id": attempt.attempt_id})
        except RemoteBrokerError as exc:
            if exc.code == "BrokerStateError" and self._fresh_overall_absence(
                attempt.attempt_id
            ):
                return ProcessPresence.ABSENT
            return ProcessPresence.UNKNOWN
        except (WorkerBrokerError, OSError):
            return ProcessPresence.UNKNOWN
        run = status.get("run")
        if not isinstance(run, dict):
            return ProcessPresence.UNKNOWN
        try:
            process = _process_ref_from_json(run.get("process_ref"))
        except BrokerProtocolError:
            return ProcessPresence.UNKNOWN
        if not self._matches_attempt(process, attempt):
            return ProcessPresence.UNKNOWN
        if run.get("status") in {"STARTING", "RUNNING", "CANCELLING"}:
            return ProcessPresence.LIVE
        if self._fresh_overall_absence(attempt.attempt_id):
            return ProcessPresence.ABSENT
        return ProcessPresence.UNKNOWN

    def absence_verified(self, attempt: Any) -> bool:
        from control_plane.executive_supervisor import ProcessPresence

        return self.presence(attempt) is ProcessPresence.ABSENT

    def terminate(self, attempt: Any) -> None:
        from control_plane.executive_supervisor import ProcessPresence

        presence = self.presence(attempt)
        if presence is ProcessPresence.ABSENT:
            return
        if presence is not ProcessPresence.LIVE:
            raise BrokerStateError("remote process identity is ambiguous; refusing cancellation")
        result = self.client.request_sync(
            "cancel",
            {"run_id": attempt.attempt_id, "reason": "supervisor restart reconciliation"},
        )
        self._uid_sweeps[attempt.attempt_id] = _uid_sweep_from_json(
            result.get("uid_sweep")
        )


class _UnavailableRemoteInspector:
    """Fail-closed marker: cross-UID inspection must use the remote controller."""

    @staticmethod
    def boot_session_id() -> str:
        raise ProcessIdentityError(
            "remote worker identity requires RemoteWorkerProcessController"
        )

    @staticmethod
    def identity(_pid: int) -> tuple[str, int]:
        raise ProcessIdentityError(
            "remote worker identity requires RemoteWorkerProcessController"
        )


__all__ = [
    "BROKER_REQUEST_SCHEMA_VERSION",
    "BROKER_RESPONSE_SCHEMA_VERSION",
    "BROKER_UNAVAILABLE_ERROR_CODE",
    "UID_SWEEP_SCHEMA_VERSION",
    "uid_sweep_receipt_is_passing",
    "BrokerPolicy",
    "BrokerProtocolError",
    "BrokerStateError",
    "DedicatedUIDError",
    "DedicatedUIDSweeper",
    "ExecutiveWorkerBroker",
    "PeerAuthorizationError",
    "PeerCredentials",
    "RemoteBrokerError",
    "RemoteCodexWorkerAdapter",
    "RemoteWorkerProcessController",
    "UIDSweepReceipt",
    "WorkerBrokerClient",
    "WorkerBrokerError",
    "activate_launchd_socket",
    "get_peer_credentials",
]

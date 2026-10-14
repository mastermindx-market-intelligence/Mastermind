"""Live source evidence for one authenticated finite Session Bridge invocation.

The private handler owns this scope. Runtime claims, launch pins and the original
controller's START fence remain authority; exported receipt data grants nothing.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import dataclasses
import hashlib
import json
import re
import time
from collections.abc import Mapping

from common.session_bridge_private_contract import PRIVATE_SCHEMA
from control_plane import ceo_intent, ceo_request
from control_plane.executive_runtime import _dialogue_source_from_root_creation
from control_plane.principal_projection import neutral_principal_projection
from control_plane.remote_attempt_transport import (
    RemoteTransportPurpose, _read_claim,
)

_IDENTITY = ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")
_BINDING = ("root_id", "job_id", "attempt_id", "effective_grant_digest", "commission_sha256")
_PRINCIPAL = frozenset((*_IDENTITY, "issuer", "scopes", "issued_at", "expires_at", "jti_digest"))
_SCOPES = frozenset({"mastermind.executive.read", "mastermind.executive.intent.submit"})
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_MINT = object()
_ACTIVE = contextvars.ContextVar("mastermind_foreground_operation", default=None)


class ForegroundOperationRefusal(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


class ForegroundOperationClosed(ForegroundOperationRefusal):
    def __init__(self, message="no live foreground operation in this context"):
        super().__init__("foreground_unavailable", message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class StartReceipt:
    root_id: str
    job_id: str
    attempt_id: str
    effective_grant_digest: str
    commission_sha256: str
    physical_binding_sha256: str
    start_request_sha256: str
    principal_identity: tuple
    operation_key: str
    arguments_sha256: str
    _source: object = dataclasses.field(repr=False, compare=False)
    _mint: object = dataclasses.field(repr=False, compare=False)

    def __post_init__(self):
        if self._mint is not _MINT or type(self._source) is not ForegroundOperation:
            raise ForegroundOperationRefusal("receipt_composition_denied", "receipt is host-composed only")

    def as_dict(self):
        """Inert, nonsecret evidence; this projection cannot be deserialized as authority."""
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self)
                if not f.name.startswith("_")}

    def principal_deadline(self):
        self._source._require_live()
        return self._source._principal.expires_at


class ForegroundOperation:
    def __init__(self, *, mint, runtime, host_current, principal, arguments):
        if mint is not _MINT:
            raise ForegroundOperationClosed("operation is composed by the private handler only")
        self._runtime, self._host_current, self._principal = runtime, host_current, principal
        self._arguments_sha256 = _digest(arguments)
        self._operation_key = arguments["operation_key"]
        self._command = ceo_intent.command_id_for(ceo_request.automated_intent_id(
            ceo_request.app_request_ref(self._operation_key)))
        # Presence at entry is never fresh admission, including equal timestamps.
        self._preexisting = runtime.store.find_event_by_command_id(self._command)
        self._root, self._root_event_sha256, self._closed = None, None, False
        self._closed_event = asyncio.Event()

    def _mark_source_closed(self):
        self._closed = True
        self._closed_event.set()

    async def wait_closed(self):
        """Liveness observation only; cancellation still belongs to the exact owner."""
        await self._closed_event.wait()

    def _require_live(self):
        if self._closed or _ACTIVE.get() is not self:
            raise ForegroundOperationClosed("the originating invocation is no longer current")
        now = time.time()
        p = self._principal
        if not (type(p.issued_at) is int and type(p.expires_at) is int
                and p.issued_at <= now < p.expires_at):
            raise ForegroundOperationRefusal("principal_not_live", "principal window is not live")
        if not _SCOPES <= set(p.scopes):
            raise ForegroundOperationRefusal("scope_denied", "Executive READ and SUBMIT scopes are required")
        try:
            if self._host_current() is not None:
                raise ValueError("invalid trusted host guard result")
        except Exception:
            raise ForegroundOperationRefusal("host_not_current", "the originating host connection is no longer current") from None
        # A trusted host read may block while the original event loop closes.
        if self._closed or _ACTIVE.get() is not self:
            raise ForegroundOperationClosed("the originating invocation is no longer current")
        if not p.issued_at <= time.time() < p.expires_at:
            raise ForegroundOperationRefusal("principal_not_live", "principal window is not live")

    def require_arguments(self, arguments):
        self._require_live()
        try:
            normalized = ceo_request.normalize_high_level_request(arguments)
        except (TypeError, ValueError, ceo_request.CeoRequestError):
            raise ForegroundOperationRefusal("arguments_changed", "invocation arguments changed") from None
        if _digest(normalized) != self._arguments_sha256:
            raise ForegroundOperationRefusal("arguments_changed", "invocation arguments changed")

    def require_qualification_request(self, operation_key, arguments_sha256):
        """Match fixed host restrictions; actual authentication remains upstream.

        This does not bind a root. Only the original fresh admission callback
        may bind it, and the current claim/commission is still required at START.
        """
        self._require_live()
        if (operation_key != self._operation_key
                or arguments_sha256 != self._arguments_sha256):
            raise ForegroundOperationRefusal("qualification_request_mismatch",
                "finite qualification belongs to another request")

    def _bind_admitted_root(self, root_id, command_id):
        """Private observer passed only to the canonical sink's fresh commit branch.

        This accepts no receipt, dispatched boolean or public caller field.
        The sink never invokes this observer on duplicate or losing submissions.
        """
        self._require_live()
        if self._root is not None:
            raise ForegroundOperationRefusal("root_already_bound", "invocation root is already bound")
        if self._preexisting is not None or command_id != self._command:
            raise ForegroundOperationRefusal("admission_not_fresh", "the original fresh admission source is required")
        root = self._runtime.jobs.get_job(root_id)
        event = self._runtime.store.find_event_by_command_id(command_id)
        if (root is None or root.root_job_id != root_id or root.parent_job_id is not None
                or root.orchestration_role != "aggregation" or event is None
                or event.get("event_type") != "JOB_CREATED" or event.get("job_id") != root_id
                or not isinstance(root.orchestration_provenance, dict)
                or root.orchestration_provenance.get("command_id") != command_id):
            raise ForegroundOperationRefusal("root_unavailable", "canonical root creation source differs")
        self._root = root_id
        self._root_event_sha256 = _digest(event)
        # Return None: the observation is neither a receipt nor execution.

    def require_root(self, root_id):
        """Recheck this fresh source before the incumbent canonical claim."""
        self._require_live()
        if self._root is None or root_id != self._root:
            raise ForegroundOperationRefusal("root_unbound", "the exact fresh admitted root is required")
        event = self._runtime.store.find_event_by_command_id(self._command)
        if event is None or event.get("job_id") != root_id or _digest(event) != self._root_event_sha256:
            raise ForegroundOperationRefusal("root_replaced", "canonical root creation source changed")
        self._require_live()  # The canonical read may have waited for another writer.

    def _current_claim(self, binding, physical_binding_sha256, start_request_sha256):
        self._require_live()
        if self._root is None:
            raise ForegroundOperationRefusal("root_unbound", "no fresh admitted root is bound")
        if (not isinstance(binding, Mapping) or set(binding) != set(_BINDING)
                or any(type(binding[k]) is not str or not binding[k] for k in _BINDING)
                or any(type(v) is not str or _HEX64.fullmatch(v) is None for v in
                       (physical_binding_sha256, start_request_sha256,
                        binding["effective_grant_digest"], binding["commission_sha256"]))):
            raise ForegroundOperationRefusal("binding_invalid", "launch binding is invalid")
        if binding["root_id"] != self._root:
            raise ForegroundOperationRefusal("root_replaced", "launch root differs from fresh admission")
        self.require_root(binding["root_id"])
        try:
            job, attempt, _quota, _join = _read_claim(self._runtime,
                job_id=binding["job_id"], attempt_id=binding["attempt_id"],
                purpose=RemoteTransportPurpose.LAUNCH)
        except Exception:
            raise ForegroundOperationRefusal("claim_refused", "canonical launch claim is not current") from None
        if (job.job_id != binding["job_id"] or job.root_job_id != self._root
                or attempt.attempt_id != binding["attempt_id"]
                or attempt.effective_grant_digest != binding["effective_grant_digest"]):
            raise ForegroundOperationRefusal("claim_moved", "canonical launch claim differs")
        try:
            with self._runtime.store.read() as connection:
                source = _dialogue_source_from_root_creation(connection, root_job_id=self._root)
            commission = source.commission_ref.content_sha256
        except Exception:
            raise ForegroundOperationRefusal("commission_unavailable", "canonical root commission is unavailable") from None
        if commission != binding["commission_sha256"]:
            raise ForegroundOperationRefusal("commission_moved", "canonical commission differs")

    def start_receipt(self, binding, physical_binding_sha256, start_request_sha256):
        """Bind actual transport-owner digests to this live source and current claim.

        The transport must independently derive the physical and request digests,
        then revalidate its Runtime pin and original controller reservation.
        """
        self._current_claim(binding, physical_binding_sha256, start_request_sha256)
        return StartReceipt(*(binding[k] for k in _BINDING), physical_binding_sha256,
            start_request_sha256, tuple(getattr(self._principal, k) for k in _IDENTITY),
            self._operation_key, self._arguments_sha256, self, _MINT)


def current_foreground_operation():
    operation = _ACTIVE.get()
    if type(operation) is not ForegroundOperation:
        raise ForegroundOperationClosed()
    operation._require_live()
    return operation


def _current_foreground_operation_or_none():
    # Optional composition preserves the legacy queued path. A present but
    # expired/closed/drifted scope must refuse; it cannot fall back to legacy.
    return None if _ACTIVE.get() is None else current_foreground_operation()


def require_start(receipt, binding, physical_binding_sha256, start_request_sha256):
    operation = current_foreground_operation()
    if type(receipt) is not StartReceipt or receipt._source is not operation:
        raise ForegroundOperationRefusal("receipt_refused", "receipt belongs to a different invocation")
    operation._current_claim(binding, physical_binding_sha256, start_request_sha256)
    if (tuple(getattr(receipt, k) for k in _BINDING) != tuple(binding[k] for k in _BINDING)
            or receipt.physical_binding_sha256 != physical_binding_sha256
            or receipt.start_request_sha256 != start_request_sha256
            or receipt.principal_identity != tuple(getattr(operation._principal, k) for k in _IDENTITY)
            or receipt.operation_key != operation._operation_key
            or receipt.arguments_sha256 != operation._arguments_sha256):
        raise ForegroundOperationRefusal("receipt_stale", "receipt differs from the current invocation")


def require_start_transmission(operation, payload, receipt):
    """Recheck the original source at the final pre-write boundary.

    Call on the decoded immutable transmission bytes, after connection/peer
    authentication, with no await before writing. No new authority is issued.
    """
    command = payload.get("control_start")
    projected = isinstance(command, Mapping) and "owner_projection" in command
    if receipt is None and not projected:
        return  # Existing legacy transport behavior.
    if operation != "start" or not projected or type(receipt) is not StartReceipt:
        raise ForegroundOperationRefusal("receipt_refused", "attended transport requires its original source")
    from control_plane.executive_fabric_bridge_broker import start_request_sha256
    require_start(receipt, payload["binding"], payload["physical_binding_sha256"],
                  start_request_sha256(payload))
    if (command.get("foreground_expires_at") != receipt.principal_deadline()
            or _digest(command["owner_projection"].get("attendance")) != _digest(receipt.as_dict())):
        raise ForegroundOperationRefusal("receipt_stale", "transmitted attendance differs from its source")


@contextlib.asynccontextmanager
async def _session_bridge_foreground_dispatch(runtime, frame, require_host_current):
    # The integration's semantic validator already ran in the actual handler.
    if (not callable(require_host_current) or not isinstance(frame, Mapping)
            or set(frame) != {"schema", "tool", "principal", "arguments"}
            or frame["schema"] != PRIVATE_SCHEMA or frame["tool"] != "session_summon"):
        raise ForegroundOperationClosed("finite foreground source requires the private summon handler")
    raw = frame["principal"]
    try:
        if not isinstance(raw, Mapping) or set(raw) != _PRINCIPAL or type(raw["scopes"]) is not list:
            raise ValueError("principal")
        p = neutral_principal_projection(**{**dict(raw), "scopes": tuple(raw["scopes"])})
        arguments = ceo_request.normalize_high_level_request(frame["arguments"])
        operation = ForegroundOperation(mint=_MINT, runtime=runtime,
            host_current=require_host_current, principal=p, arguments=arguments)
    except (TypeError, ValueError, ceo_request.CeoRequestError):
        raise ForegroundOperationClosed("validated private frame source is unavailable") from None
    token = _ACTIVE.set(operation)
    try:
        operation._require_live()
        yield operation
    finally:
        operation._mark_source_closed()
        operation._root, operation._host_current = None, None
        _ACTIVE.reset(token)


@contextlib.asynccontextmanager
async def _observe_private_request_end(operation, reader):
    """One already-framed request's EOF/expiry; no worker/lifecycle control."""
    if type(operation) is not ForegroundOperation or _ACTIVE.get() is not operation:
        raise ForegroundOperationClosed("private request observer belongs to another invocation")
    operation._require_live()
    async def observe():
        try:
            remaining = max(0.0, operation._principal.expires_at - time.time())
            # The one allowed frame is already consumed. EOF or extra bytes
            # end this invocation; no second request is accepted on this socket.
            await asyncio.wait_for(reader.read(1), timeout=remaining)
        except asyncio.TimeoutError:
            pass
        finally:
            operation._mark_source_closed()
    task = asyncio.create_task(observe(), name="executive-foreground-request-end")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

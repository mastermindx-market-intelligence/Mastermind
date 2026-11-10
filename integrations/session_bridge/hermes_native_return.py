"""Session-bridge delivery of ``mastermind.execution_return/v1`` to the
ORIGINAL Hermes teammate conversation.

DONE_WHEN row 5 (T3_HANDOFF_V2 §0): evidence returns to the original Hermes
teammate/project, and delivery is explicitly NOT user acceptance.

Laws (mirrors :mod:`control_plane.t3_execution_adapter`'s port-contract law
and :mod:`control_plane.teamlink_contracts`' unknown-outside-the-chain law):

* **No new transport.**  Delivery rides the EXISTING hermes_native send seam
  (:class:`integrations.session_bridge.hermes_native.HermesNativeSession` →
  the installed Secretary composition client → the native ``submit``
  operation).  This module defines only a thin injectable port over that
  seam; no gateway HTTP, no queue, no broker, no listener, no retry loop.
* **Idempotent delivery.**  Keyed by ``(return digest, conversation id)``:
  a redelivery returns the PRIOR receipt and never sends again.  After an
  ``unknown`` receipt (ambiguous send) there is no auto-retry — ever; the
  receipt is the honest terminal marker until a reconciliation owner acts
  on the ORIGINAL submission id.  ``refused`` (a clean refusal — the send
  definitively did not land) is likewise terminal here.
* **Receipt vocabulary is closed** and owned by
  :mod:`control_plane.execution_return_projection` (``delivered`` /
  ``unknown`` / ``refused``); the TypeScript mirror asserts equality against
  the committed fixture.
* **Port contract.**  Only a typed :class:`HermesReturnDeliveryError`
  proves a clean refusal. Other send failures remain ambiguous. The native
  transport requires the Executive owner's callback at the actual prewrite
  boundary; a retained intent can only be reconciled by ``read_original``.
* **In-process receipts only.**  The idempotency ledger here is
  request-scoped memory; durable persistence of the receipt belongs to the
  Executive runtime transaction at the integrator's wiring point — this
  module creates no database.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import MutableMapping
from typing import Any, Callable, Protocol, runtime_checkable

from control_plane.execution_return_projection import (
    EXECUTION_RETURN_DELIVERY_SCHEMA,
    EXECUTION_RETURN_DELIVERY_STATES,
    REFUSAL_CODE_PATTERN,
    canonical_record_bytes,
    validate_execution_return,
    ExecutionReturnProjectionError,
    mint_return_submission_id as _mint_return_submission_id,
    validate_execution_return_delivery as _validate_execution_return_delivery,
    validate_execution_return_receipt as _validate_execution_return_receipt,
)
from control_plane.remote_worker_transport import (
    TransportEffect,
    TransportError,
    validate_secretary_operation,
)

_REFUSAL_RE = re.compile(REFUSAL_CODE_PATTERN)
#: These BridgeError codes prove preflight refusal only before the native
#: callback is reached. The same binding guard also runs after dispatch.
_PRE_DISPATCH_CODES = frozenset({
    "binding_unavailable", "ingress_unavailable", "backend_unavailable",
})


class HermesReturnDeliveryError(ValueError):
    """A typed refusal before any send; ``code`` is closed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class HermesReturnUnknownOutcome(Exception):
    """The port's explicit ambiguous-send marker; never authorizes retry."""


@runtime_checkable
class HermesReturnTransport(Protocol):
    """The existing native submit and original-read seams.

    ``send`` delivers one message into the ORIGINAL conversation and returns
    a transport reference string.  It raises :class:`HermesReturnUnknownOutcome`
    when the outcome is ambiguous; only a typed delivery error is a refusal.
    """

    async def send(self, *, conversation_id: str, submission_id: str,
                   text: str, before_write: Callable[[dict[str, Any]], None] | None = None) -> str: ...

    async def read_original(self, original: dict[str, Any]) -> str: ...


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False))


def _native_input_digest(text: str) -> str:
    # Matches the native owner's finite-input digest, including UTF-8 text.
    return hashlib.sha256(json.dumps(
        {"text": text, "finite": True}, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _original_submission(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"binding", "request", "input_sha256"}:
        raise HermesReturnDeliveryError("INPUT_INVALID", "original submission is not closed")
    original = _copy(value)
    request = validate_secretary_operation(original["request"])
    binding = original["binding"]
    if (request["operation"] != "submit" or type(binding) is not dict
            or any(request["target"][key] != binding.get(key)
                   for key in ("profile_id", "session_id", "principal_id"))
            or original["input_sha256"] != _native_input_digest(request["text"])):
        raise HermesReturnDeliveryError("INPUT_INVALID", "original submission binding differs")
    return original


def mint_return_submission_id(return_digest: str, conversation_id: str) -> str:
    """The shared original-return submission identity."""
    return _mint_return_submission_id(return_digest, conversation_id)


def validate_execution_return_delivery(value: Any) -> dict[str, Any]:
    """Preserve the transport error type around the shared pure validator."""
    try:
        return _validate_execution_return_delivery(value)
    except ExecutionReturnProjectionError as exc:
        raise HermesReturnDeliveryError(exc.code, exc.detail) from exc


class HermesExecutionReturnDeliverer:
    """Idempotent deliverer of execution-return records over one transport.

    One in-process receipt per ``(return digest, conversation id)``; the
    cache avoids sequential duplicate calls. Cross-instance and concurrent
    exclusion belong to the Executive transaction at ``before_write``.
    """

    def __init__(self, transport: HermesReturnTransport, *,
                 receipts: MutableMapping[tuple[str, str], dict[str, Any]] | None = None):
        if not callable(getattr(transport, "send", None)):
            raise HermesReturnDeliveryError("INPUT_INVALID", "transport does not implement send")
        self._transport = transport
        self._receipts: MutableMapping[tuple[str, str], dict[str, Any]] = (
            receipts if receipts is not None else {}
        )

    @staticmethod
    def _key(validated: dict[str, Any]) -> tuple[str, str]:
        return (validated["digest"],
                validated["original_requester"]["conversation_id"])

    def prior_receipt(self, record: Any) -> dict[str, Any] | None:
        """The retained receipt for this record's (digest, conversation), if any."""

        validated = validate_execution_return(record)
        receipt = self._receipts.get(self._key(validated))
        return dict(receipt) if receipt is not None else None

    @staticmethod
    def validate_receipt(record: Any, value: Any) -> dict[str, Any]:
        # Preserve the original record validator's error boundary. Receipt
        # failures retain the transport's public typed refusal API.
        validated = validate_execution_return(record)
        try:
            return _validate_execution_return_receipt(validated, value)
        except ExecutionReturnProjectionError as exc:
            raise HermesReturnDeliveryError(exc.code, exc.detail) from exc

    @staticmethod
    def _receipt(validated: dict[str, Any], state: str, *,
                 transport_ref: str | None = None, refusal_code: str | None = None) -> dict[str, Any]:
        conversation_id = validated["original_requester"]["conversation_id"]
        return validate_execution_return_delivery({
            "schema": EXECUTION_RETURN_DELIVERY_SCHEMA,
            "return_id": validated["return_id"],
            "return_digest": validated["digest"],
            "conversation_id": conversation_id,
            "submission_id": mint_return_submission_id(validated["digest"], conversation_id),
            "state": state,
            "transport_ref": transport_ref,
            "refusal_code": refusal_code,
        })

    async def read_original(self, record: Any, original: Any) -> dict[str, Any]:
        """Read the frozen original only; absence/refusal never permits submit."""
        validated = validate_execution_return(record)
        try:
            original = _original_submission(original)
            request = original["request"]
            if (request["text"] != canonical_record_bytes(validated).decode("utf-8")
                    or request["submission_id"] != mint_return_submission_id(*self._key(validated))
                    or request["target"]["session_id"] != self._key(validated)[1]):
                raise HermesReturnUnknownOutcome("frozen original does not match the return")
            reference = await self._transport.read_original(original)
            receipt = self._receipt(validated, "delivered", transport_ref=reference)
        except (Exception, asyncio.CancelledError):
            # Even NO_EFFECT describes only this read, not the original send.
            receipt = self._receipt(validated, "unknown")
        self._receipts[self._key(validated)] = dict(receipt)
        return receipt

    async def deliver(self, record: Any, *,
                      before_write: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        """Deliver one validated record; returns the (validated) receipt.

        A retained receipt short-circuits BEFORE any transport call: the same
        ``(digest, conversation)`` never sends twice through this deliverer —
        including after ``unknown`` and ``refused``.
        """

        validated = validate_execution_return(record)
        conversation_id = validated["original_requester"]["conversation_id"]
        key = self._key(validated)
        prior = self._receipts.get(key)
        if prior is not None:
            return dict(prior)
        submission_id = mint_return_submission_id(validated["digest"], conversation_id)
        text = canonical_record_bytes(validated).decode("utf-8")
        state = "delivered"
        transport_ref: str | None = None
        refusal_code: str | None = None
        try:
            arguments: dict[str, Any] = dict(
                conversation_id=conversation_id, submission_id=submission_id, text=text)
            if before_write is not None:
                arguments["before_write"] = before_write
            transport_ref = await self._transport.send(**arguments)
            if type(transport_ref) is not str or not transport_ref or len(transport_ref) > 256:
                # A post-send malformed ref cannot downgrade the send to a
                # clean refusal: the outcome is ambiguous, never guessed.
                raise HermesReturnUnknownOutcome("transport returned a malformed reference")
        except HermesReturnDeliveryError as exc:
            state, transport_ref = "refused", None
            code = getattr(exc, "code", None)
            refusal_code = code if type(code) is str and _REFUSAL_RE.fullmatch(code) \
                else "TRANSPORT_REFUSED"
        except (Exception, asyncio.CancelledError):
            state, transport_ref = "unknown", None
        receipt = self._receipt(validated, state, transport_ref=transport_ref,
                                refusal_code=refusal_code)
        self._receipts[key] = dict(receipt)
        return dict(receipt)


class SecretaryNativeSendTransport:
    """The production port over the EXISTING hermes_native send seam.

    Wraps one :class:`~integrations.session_bridge.hermes_native.HermesNativeSession`
    selection (duck-typed ``request(binding, native_request)`` — the exact
    seam ``hermes_native.HermesNativeSession.request`` already exposes) and
    submits the closed native ``submit`` request through it.  No HTTP, no
    socket, no gateway URL: the session owns the transport entirely.

    Ambiguity law for this seam: an admission-bearing result (ADMITTED, or
    OBSERVED with an admission for our submission) is delivered;
    EFFECT_UNKNOWN or any malformed post-dispatch result is
    :class:`HermesReturnUnknownOutcome`; NOT_SUBMITTED / REFUSED /
    UNAVAILABLE are clean refusals (the send definitively did not land);
    guard ``BridgeError`` codes that provably precede dispatch are clean
    refusals, every other exception is ambiguous.
    """

    def __init__(self, session: Any, binding: dict[str, Any], *,
                 target: dict[str, Any]) -> None:
        if any(not callable(getattr(session, method, None))
               for method in ("request", "require_binding", "require_submit")):
            raise HermesReturnDeliveryError("INPUT_INVALID", "session lacks the guarded native seam")
        if (type(binding) is not dict or type(target) is not dict
                or any(type(binding.get(key)) is not str or not binding[key]
                       or target.get(key) != binding[key]
                       for key in ("profile_id", "session_id", "principal_id"))):
            raise HermesReturnDeliveryError("INPUT_INVALID", "native binding and target differ")
        self._session = session
        self._binding = _copy(binding)
        self._target = _copy(target)

    @staticmethod
    def _admission_reference(result: Any, original: dict[str, Any]) -> str:
        binding = original["binding"]
        admission = result.get("admission") if isinstance(result, dict) else None
        if (not isinstance(result, dict)
                or result.get("schema") != "mastermind.hermes_secretary_native_control/v1"
                or result.get("status") not in {"ADMITTED", "OBSERVED"}
                or not isinstance(admission, dict)
                or admission.get("ref") != {"profile_id": binding["profile_id"],
                                             "session_id": binding["session_id"]}
                or admission.get("status") not in {"queued", "started", "unknown", "terminal"}
                or type(admission.get("sequence")) is not int or admission["sequence"] < 1
                or type(admission.get("authority_epoch")) is not int or admission["authority_epoch"] < 1
                or set(admission) != {"admission_id", "ref", "sequence", "status", "outcome",
                                      "authority_epoch", "execution_generation"}
                or (admission["execution_generation"] is not None
                    and (type(admission["execution_generation"]) is not int
                         or admission["execution_generation"] < 0))
                or (admission["outcome"] is not None and type(admission["outcome"]) is not str)):
            raise HermesReturnUnknownOutcome("native admission does not identify the original session")
        reference = admission.get("admission_id")
        if (type(reference) is not str or not reference or len(reference) > 256
                or any(ord(char) < 32 or ord(char) == 127 for char in reference)):
            raise HermesReturnUnknownOutcome("native admission reference is malformed")
        return reference

    async def read_original(self, original: dict[str, Any]) -> str:
        """Use the native owner's exact input lookup; never observe or submit."""
        try:
            original = _original_submission(original)
            if original["binding"] != self._binding:
                raise HermesReturnUnknownOutcome("original native selection is unavailable")
            binding, request = original["binding"], original["request"]
            self._session.require_binding(binding)
            result = await self._session.request(binding, {
                "operation": "read_original", "session_id": binding["session_id"],
                "submission_id": request["submission_id"],
                "input_sha256": original["input_sha256"],
            })
            self._session.require_binding(binding)
            if not isinstance(result, dict) or result.get("status") != "OBSERVED":
                raise HermesReturnUnknownOutcome("original admission is not observable")
            return self._admission_reference(result, original)
        except Exception as exc:
            raise HermesReturnUnknownOutcome("original send outcome remains unknown") from exc

    async def send(self, *, conversation_id: str, submission_id: str, text: str,
                   before_write: Callable[[dict[str, Any]], None] | None = None) -> str:
        if conversation_id != self._binding["session_id"]:
            # Never route a record into a conversation the binding did not
            # select: a mismatched send is refused before any dispatch.
            raise HermesReturnDeliveryError(
                "CONVERSATION_MISMATCH",
                "record conversation does not match the selected native binding",
            )
        native_request = {
            "operation": "submit",
            "target": dict(self._target),
            "submission_id": submission_id,
            "text": text,
        }
        if not callable(before_write):
            raise HermesReturnDeliveryError("PREWRITE_REQUIRED", "durable original intent is required")
        try:
            original = _original_submission({
                "binding": self._binding, "request": native_request,
                "input_sha256": _native_input_digest(text),
            })
            self._session.require_submit(self._binding)
        except Exception as exc:
            code = getattr(exc, "code", None)
            raise HermesReturnDeliveryError(
                code if type(code) is str and _REFUSAL_RE.fullmatch(code) else "NATIVE_PREFLIGHT_REFUSED",
                "native submit refused before dispatch") from exc
        reached_prewrite = False

        def commit_original(operation: str, request: dict[str, Any]) -> None:
            nonlocal reached_prewrite
            reached_prewrite = True
            self._session.require_submit(self._binding)
            if operation != "submit" or request != original["request"]:
                raise ValueError("native prewrite request changed")
            if before_write(_copy(original)) is not None:
                raise ValueError("invalid original-intent callback result")
            self._session.require_submit(self._binding)

        try:
            result = await self._session.request(
                self._binding, _copy(native_request), before_write=commit_original)
        except Exception as exc:
            code = getattr(exc, "code", None)
            no_effect = isinstance(exc, TransportError) and exc.classification is TransportEffect.NO_EFFECT
            if no_effect or (not reached_prewrite and code in _PRE_DISPATCH_CODES):
                # A post-request binding guard can share a preflight code;
                # its code alone never proves the preceding submit absent.
                raise HermesReturnDeliveryError(code, "native request proved no effect") from None
            raise HermesReturnUnknownOutcome("native send outcome unknown") from exc
        if not reached_prewrite:
            raise HermesReturnUnknownOutcome("native seam did not execute the required prewrite guard")
        if (not isinstance(result, dict)
                or result.get("schema") != "mastermind.hermes_secretary_native_control/v1"):
            raise HermesReturnUnknownOutcome("native result is not readable")
        status = result.get("status")
        if status in {"NOT_SUBMITTED", "REFUSED", "UNAVAILABLE"}:
            reason = result.get("reason")
            code = reason if type(reason) is str and _REFUSAL_RE.fullmatch(reason) else status
            raise HermesReturnDeliveryError(code, f"native refused with {status}")
        if status == "EFFECT_UNKNOWN":
            raise HermesReturnUnknownOutcome("native send is effect-unknown")
        return self._admission_reference(result, original)

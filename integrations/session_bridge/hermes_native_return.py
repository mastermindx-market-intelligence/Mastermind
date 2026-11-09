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
* **Port contract.**  A transport implementation raises
  :class:`HermesReturnUnknownOutcome` EXACTLY when the send's outcome is
  ambiguous (mirrors ``T3UnknownOutcomeError``); any other exception is a
  clean refusal (the send definitively did not take effect).
* **In-process receipts only.**  The idempotency ledger here is
  request-scoped memory; durable persistence of the receipt belongs to the
  Executive runtime transaction at the integrator's wiring point — this
  module creates no database.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import MutableMapping
from typing import Any, Protocol, runtime_checkable

from control_plane.execution_return_projection import (
    EXECUTION_RETURN_DELIVERY_SCHEMA,
    EXECUTION_RETURN_DELIVERY_STATES,
    REFUSAL_CODE_PATTERN,
    canonical_record_bytes,
    validate_execution_return,
)

_REFUSAL_RE = re.compile(REFUSAL_CODE_PATTERN)
_SUBMISSION_ID_RE = re.compile(r"execret-[0-9a-f]{32}")
_RECEIPT_KEYS = frozenset({
    "schema", "return_id", "return_digest", "conversation_id",
    "submission_id", "state", "transport_ref", "refusal_code",
})
#: BridgeError codes that provably precede any native dispatch (guards in
#: HermesNativeSession.request fire before the client call); every other
#: live-seam failure after dispatch is treated as AMBIGUOUS, never clean.
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
    """The port's ambiguous-send marker: EXACTLY this exception means the
    send's outcome is unknown.  Never retried automatically."""


@runtime_checkable
class HermesReturnTransport(Protocol):
    """The existing native send seam, narrowed to one method.

    ``send`` delivers one message into the ORIGINAL conversation and returns
    a transport reference string.  It raises :class:`HermesReturnUnknownOutcome`
    when the outcome is ambiguous; any other exception is a clean refusal.
    """

    async def send(self, *, conversation_id: str, submission_id: str,
                   text: str) -> str: ...


def mint_return_submission_id(return_digest: str, conversation_id: str) -> str:
    """Deterministic native submission id for (return digest, conversation).

    Same pair ⇒ same id, so a replayed delivery is recognised as the SAME
    native submission by the existing seam (mirrors the TeamLink message-id
    mint).  Grammar: ``execret-`` + 32 hex.
    """

    canonical = json.dumps(
        {"return_digest": return_digest, "conversation_id": conversation_id},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return "execret-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def validate_execution_return_delivery(value: Any) -> dict[str, Any]:
    """Fail-closed validation of one delivery receipt; returns a deep copy."""

    if not isinstance(value, dict) or set(value) != _RECEIPT_KEYS:
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt is not the closed shape")
    if value["schema"] != EXECUTION_RETURN_DELIVERY_SCHEMA:
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt schema is unknown")
    if value["state"] not in EXECUTION_RETURN_DELIVERY_STATES:
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt state is outside the closed vocabulary")
    for field in ("return_id", "conversation_id"):
        item = value[field]
        if type(item) is not str or not item or len(item) > 256 \
                or any(ord(char) < 32 or ord(char) == 127 for char in item):
            raise HermesReturnDeliveryError("INPUT_INVALID", f"receipt {field} is malformed")
    digest = value["return_digest"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt return_digest is not 64-hex")
    submission = value["submission_id"]
    if type(submission) is not str or _SUBMISSION_ID_RE.fullmatch(submission) is None:
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt submission_id is malformed")
    if submission != mint_return_submission_id(digest, value["conversation_id"]):
        raise HermesReturnDeliveryError("INPUT_INVALID", "submission_id does not derive from (digest, conversation)")
    transport_ref = value["transport_ref"]
    if transport_ref is not None and (type(transport_ref) is not str
                                      or not transport_ref or len(transport_ref) > 256):
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt transport_ref is malformed")
    refusal = value["refusal_code"]
    if refusal is not None and (type(refusal) is not str
                                or _REFUSAL_RE.fullmatch(refusal) is None):
        raise HermesReturnDeliveryError("INPUT_INVALID", "receipt refusal_code is malformed")
    if value["state"] == "delivered" and transport_ref is None:
        raise HermesReturnDeliveryError("INPUT_INVALID", "a delivered receipt carries a transport ref")
    if value["state"] == "unknown" and transport_ref is not None:
        raise HermesReturnDeliveryError("INPUT_INVALID", "an ambiguous receipt cannot carry a transport ref")
    if value["state"] != "refused" and refusal is not None:
        raise HermesReturnDeliveryError("INPUT_INVALID", "only a refused receipt carries a refusal code")
    if value["state"] == "refused" and refusal is None:
        raise HermesReturnDeliveryError("INPUT_INVALID", "a refused receipt carries a refusal code")
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False))


class HermesExecutionReturnDeliverer:
    """Idempotent deliverer of execution-return records over one transport.

    One in-process receipt per ``(return digest, conversation id)``; the
    existing seam sees at most ONE native submission per pair through this
    object.  Durable receipt persistence is the integrator's wiring point.
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

    async def deliver(self, record: Any) -> dict[str, Any]:
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
            transport_ref = await self._transport.send(
                conversation_id=conversation_id,
                submission_id=submission_id,
                text=text,
            )
            if type(transport_ref) is not str or not transport_ref or len(transport_ref) > 256:
                # A post-send malformed ref cannot downgrade the send to a
                # clean refusal: the outcome is ambiguous, never guessed.
                raise HermesReturnUnknownOutcome("transport returned a malformed reference")
        except HermesReturnUnknownOutcome:
            state, transport_ref = "unknown", None
        except Exception as exc:  # any other exception is a clean refusal
            state, transport_ref = "refused", None
            code = getattr(exc, "code", None)
            refusal_code = code if type(code) is str and _REFUSAL_RE.fullmatch(code) \
                else "TRANSPORT_REFUSED"
        receipt = validate_execution_return_delivery({
            "schema": EXECUTION_RETURN_DELIVERY_SCHEMA,
            "return_id": validated["return_id"],
            "return_digest": validated["digest"],
            "conversation_id": conversation_id,
            "submission_id": submission_id,
            "state": state,
            "transport_ref": transport_ref,
            "refusal_code": refusal_code,
        })
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
        if not callable(getattr(session, "request", None)):
            raise HermesReturnDeliveryError("INPUT_INVALID", "session does not expose the native request seam")
        if not isinstance(binding, dict) or not isinstance(binding.get("session_id"), str):
            raise HermesReturnDeliveryError("INPUT_INVALID", "binding does not name a native session")
        if not isinstance(target, dict) or type(target.get("session_id")) is not str:
            raise HermesReturnDeliveryError("INPUT_INVALID", "target does not name a native session")
        self._session = session
        self._binding = binding
        self._target = dict(target)

    async def send(self, *, conversation_id: str, submission_id: str, text: str) -> str:
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
        try:
            result = await self._session.request(self._binding, native_request)
        except Exception as exc:
            code = getattr(exc, "code", None)
            if type(code) is str and code in _PRE_DISPATCH_CODES:
                # A guard refusal provably precedes dispatch: clean, and the
                # receipt carries the guard's own code.
                raise HermesReturnDeliveryError(code, "native guard refused before dispatch") from None
            raise HermesReturnUnknownOutcome("native send outcome unknown") from exc
        if not isinstance(result, dict):
            raise HermesReturnUnknownOutcome("native result is not readable")
        status = result.get("status")
        if status in {"NOT_SUBMITTED", "REFUSED", "UNAVAILABLE"}:
            reason = result.get("reason")
            code = reason if type(reason) is str and _REFUSAL_RE.fullmatch(reason) else status
            raise HermesReturnDeliveryError(code, f"native refused with {status}")
        if status == "EFFECT_UNKNOWN":
            raise HermesReturnUnknownOutcome("native send is effect-unknown")
        admission = result.get("admission")
        if status in {"ADMITTED", "OBSERVED"} and isinstance(admission, dict):
            ref = admission.get("admission_id", submission_id)
            if type(ref) is not str or not ref or len(ref) > 256:
                ref = submission_id
            return ref
        # ADMITTED/OBSERVED without an admission, or an unknown status, after
        # dispatch: the outcome cannot be established — ambiguous, never green.
        raise HermesReturnUnknownOutcome(f"native result status {status!r} is ambiguous")

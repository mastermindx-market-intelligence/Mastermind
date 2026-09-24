"""Runtime-backed Company MCP consultation dispatcher.

This joins ``CompanyConsultationGateway`` to ``ConsultationRuntime``. The
dispatcher owns no peer registry and no Runtime lookup of its own — the host
supplies the verified ``CallerIdentity`` (current RuntimeBinding), the
``recipients`` resolver that maps each trusted ``peer.peer_ref`` to the
recipient's actor ref + ``recipient_binding``, the injected
``ConsultationPacketCarrier`` (the only carrier of question/answer bodies),
and the ``InvocationContextSource`` (the only source of the owner-issued
invocation identity for ``company.consult``).

Production packet carriage is declared ``UNAVAILABLE`` in this slice; the
owner of body production is the existing dialogue carrier lineage
(issues #611, #719, #738). No module-level state, dictionary, transcript
store or mailbox table may be added here.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    CONSULTATION_V2_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    RECEIPT_KEYS,
    build_consultation,
    canonical_consultation_json,
    validate_consultation,
)
from control_plane.company_inbox_projection import (
    company_inbox_row,
    project_company_inbox,
)
from control_plane.consultation_runtime import (
    ConsultationConflict,
    ConsultationRuntime,
)
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.wake_events import utc_now_iso
from integrations.mastermind_company_mcp.consultation import (
    validate_company_consult_dispatch_request,
)


# IAC-1 self-contained constants. Not in ``common/*`` (forbidden).
_INBOX_SCHEMA = "mastermind.company_inbox.v1"
_CONSULTATION_REF_RE = re.compile(r"\Aconsult-[0-9a-f]{32}\Z")
_REPLY_SEMANTIC_KEYS = frozenset(
    {"consultation_ref", "answer", "supersedes_message_key", "evidence_refs"}
)
_READ_SEMANTIC_KEYS = frozenset({"consultation_ref"})
_ACKNOWLEDGED_WAKE_STATES = frozenset(
    {"TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"}
)

# Closed set of refusal codes. Every ``ConsultationRefusal`` raised by the
# dispatcher carries exactly one of these; the gateway surfaces the raise
# as ``{"ok": False, "error": {"code": "EFFECT_UNKNOWN"}}``.
REFUSAL_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "NOT_A_PARTY",
        "STALE_BINDING",
        "CARRIER_UNAVAILABLE",
        "CARRIER_INTEGRITY",
        "CARRIER_RECONCILIATION_REQUIRED",
        "INVOCATION_CONTEXT_UNAVAILABLE",
        "CONFLICT",
        "WAKE_NOT_ACKNOWLEDGED",
        "UNAVAILABLE",
        "BODY_OVER_BUDGET",
    }
)

# Body-over-budget threshold for the dispatcher-emitted read result.
_BODY_BUDGET_BYTES = 60_000

# Production packet carriage is intentionally declared UNAVAILABLE here.
# The owner is the existing dialogue carrier lineage (issues #611, #719,
# #738). This dispatcher never reads bodies from a dictionary, transcript
# store or mailbox table — only from the injected ``ConsultationPacketCarrier``.
PRODUCTION_PACKET_CARRIAGE = "UNAVAILABLE"

# Fixed default response budget used when the ``InvocationContext`` does not
# override it. Closed shape; ``max_payload_bytes`` is the cap enforced on the
# canonical answer JSON at reply time.
_DEFAULT_RESPONSE_BUDGET = {
    "max_answers": 1,
    "max_evidence_reads": 4,
    "max_forward_hops": 0,
    "max_payload_bytes": 32768,
}


class ConsultationPacketCarrier(Protocol):
    """Single injected port for QUESTION/ANSWER bodies.

    The recipient dispatcher ``put_question``s the exact validated QUESTION
    frame after the runtime admitted the INTENT (inserted or replayed); the
    recipient dispatcher ``put_answer``s the exact admitted ANSWER frame
    after the runtime admitted a non-historical ``ANSWER_AVAILABLE``. The
    requester dispatcher reads the bodies via ``get_question`` /
    ``get_answer``; the dispatcher never reads bodies from any other
    location.
    """

    def put_question(
        self, consultation_id: str, frame: Mapping[str, Any]
    ) -> None: ...

    def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None: ...

    def put_answer(
        self, consultation_id: str, frame: Mapping[str, Any]
    ) -> None: ...

    def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None: ...


class InMemoryConsultationPacketCarrier:
    """TEST-ONLY carrier — hermetic in-memory carrier for tests.

    This implementation is not a production body source. The production
    owner is the existing dialogue carrier lineage (issues #611, #719,
    #738) and PRODUCTION_PACKET_CARRIAGE is declared ``UNAVAILABLE`` in
    this slice.
    """

    def __init__(self) -> None:
        self._questions: dict[str, dict[str, Any]] = {}
        self._answers: dict[str, dict[str, Any]] = {}

    def put_question(
        self, consultation_id: str, frame: Mapping[str, Any]
    ) -> None:
        self._questions[consultation_id] = dict(frame)

    def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        frame = self._questions.get(consultation_id)
        return dict(frame) if frame is not None else None

    def put_answer(
        self, consultation_id: str, frame: Mapping[str, Any]
    ) -> None:
        self._answers[consultation_id] = dict(frame)

    def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        frame = self._answers.get(consultation_id)
        return dict(frame) if frame is not None else None


@dataclasses.dataclass(frozen=True)
class CallerIdentity:
    """The verified current RuntimeBinding the host injects.

    ``job_id`` is REQUIRED — the runtime cross-checks requester/recipient
    actor identity at all four edges (consult, reply, read, consume).
    """

    job_id: str
    worker_id: str
    attempt_id: str
    reasoning_surface: str
    binding: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class RecipientBinding:
    """One recipient resolved by the trusted host resolver."""

    actor_ref: Mapping[str, Any]
    recipient_binding: Mapping[str, Any]


RecipientResolver = Callable[[str], RecipientBinding]
ClockFn = Callable[[], str]


@dataclasses.dataclass(frozen=True)
class InvocationContext:
    """The owner-issued invocation identity for one ``company.consult``.

    Every field is required; there are no defaults. ``invocation_id`` is
    the owner's correlation id for this exact consult request and is bound
    into the requester identity hash. ``parent_fingerprint`` is a 64-hex
    sha256 digest used as the upstream trace fingerprint.
    """

    invocation_id: str
    issued_at: str
    parent_fingerprint: str
    deadline_ms: int
    valid_for_seconds: int
    response_budget: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.invocation_id, str) or not self.invocation_id:
            raise ValueError("invocation_id is required")
        if (
            not isinstance(self.parent_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.parent_fingerprint)
        ):
            raise ValueError("parent_fingerprint must be 64 lowercase hex")
        if not isinstance(self.issued_at, str) or not self.issued_at:
            raise ValueError("issued_at is required")
        if not isinstance(self.deadline_ms, int) or self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be a positive int")
        if (
            not isinstance(self.valid_for_seconds, int)
            or self.valid_for_seconds <= 0
        ):
            raise ValueError("valid_for_seconds must be a positive int")
        if not isinstance(self.response_budget, Mapping):
            raise ValueError("response_budget must be a mapping")


class InvocationContextSource(Protocol):
    """Single injected port for the owner-issued invocation identity.

    The owner process issues an ``InvocationContext`` per consult request.
    Returning ``None`` means no live invocation is in scope and the
    dispatcher refuses with zero effect.
    """

    def current(self) -> InvocationContext | None: ...


class ConsultationRefusal(Exception):
    """Typed zero-effect refusal raised by the dispatcher.

    The refusal carries exactly one closed-set ``code`` and never the raw
    exception text. ``detail_digest`` is the 16-hex prefix of the sha256
    of the diagnostic detail; the raw detail is not stored and not
    returned anywhere. ``__str__`` returns the code only.
    """

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        effect: str = "NONE",
    ) -> None:
        if code not in REFUSAL_CODES:
            raise ValueError(f"unknown refusal code: {code}")
        if effect != "NONE":
            raise ValueError("refusal effect must be NONE")
        self.code = code
        self.effect = effect
        if detail is None:
            self.detail_digest = ""
        else:
            self.detail_digest = hashlib.sha256(
                detail.encode("utf-8")
            ).hexdigest()[:16]
        super().__init__(code)

    def __str__(self) -> str:
        return self.code


class NoSuchRecipient(Exception):
    """The trust host has no current RuntimeBinding for ``peer_ref``."""


def _sha64(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_consultation_json(value).encode("utf-8")
    ).hexdigest()


def _parse_utc_seconds(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )


def _format_utc_seconds(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _consultation_schema_for(surface: str) -> str:
    if surface == "grok-bot":
        return GROK_CONSULTATION_SCHEMA
    return CONSULTATION_SCHEMA


def _mint_request_identity(
    *,
    caller: CallerIdentity,
    peer_ref: str,
    invocation_id: str,
) -> str:
    """Deterministic program-scoped consultation identity input.

    The hash binds only the semantic identity inputs (caller job+attempt+
    worker+surface, the trusted peer ref, and the owner-issued
    invocation_id). It never enters the request question text, evidence,
    artifact revisions, ``issued_at`` or any other time.
    """
    payload = {
        "actor": {
            "job_id": caller.job_id,
            "worker_id": caller.worker_id,
            "attempt_id": caller.attempt_id,
            "reasoning_surface": caller.reasoning_surface,
        },
        "peer_ref": peer_ref,
        "invocation_id": invocation_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_deterministic_ids(identity_hash: str) -> tuple[str, str]:
    consultation_id = f"consult-{identity_hash[:32]}"
    message_key_digest = hashlib.sha256(
        f"message:{identity_hash}".encode("utf-8")
    ).hexdigest()
    message_key = f"asd-consultation-{message_key_digest[:16]}"
    return consultation_id, message_key


def _validate_reply_semantic(semantic: Mapping[str, Any]) -> str | None:
    """Return an ``INVALID_REQUEST`` detail or ``None`` if valid."""
    if set(semantic) != _REPLY_SEMANTIC_KEYS:
        return (
            "semantic must carry exactly "
            "{consultation_ref, answer, supersedes_message_key, evidence_refs}"
        )
    consultation_ref = semantic.get("consultation_ref")
    if not isinstance(consultation_ref, str):
        return "consultation_ref must be a string"
    if _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None:
        return "consultation_ref must match ^consult-[0-9a-f]{32}$"
    answer = semantic.get("answer")
    supersedes = semantic.get("supersedes_message_key")
    evidence_refs = semantic.get("evidence_refs")
    if not isinstance(answer, str):
        return "answer must be a string"
    if supersedes is not None and not isinstance(supersedes, str):
        return "supersedes_message_key must be a string or null"
    if not isinstance(evidence_refs, list) or any(
        not isinstance(item, str) for item in evidence_refs
    ):
        return "evidence_refs must be a list of strings"
    return None


def _validate_read_semantic(semantic: Mapping[str, Any]) -> str | None:
    """Return an ``INVALID_REQUEST`` detail or ``None`` if valid."""
    if set(semantic) != _READ_SEMANTIC_KEYS:
        return "semantic must carry exactly {consultation_ref}"
    consultation_ref = semantic.get("consultation_ref")
    if not isinstance(consultation_ref, str):
        return "consultation_ref must be a string"
    if _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None:
        return "consultation_ref must match ^consult-[0-9a-f]{32}$"
    return None


def _question_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _intent_matches_frame(
    intent_payload: Mapping[str, Any], frame: Mapping[str, Any]
) -> bool:
    """Compare every persisted INTENT field against the carrier frame."""
    request = {
        "message_key": intent_payload["message_key"],
        "consultation_id": intent_payload["consultation_id"],
        "fingerprint": intent_payload["semantic_fingerprint"],
        "requester_actor_ref": intent_payload["requester_actor_ref"],
        "recipient_actor_ref": intent_payload["recipient_actor_ref"],
        "recipient_binding": intent_payload["recipient_binding"],
        "recipient_peer_ref": intent_payload["recipient_peer_ref"],
        "correlation": intent_payload["correlation"],
        "artifact_revisions": intent_payload["artifact_revisions"],
        "response_budget": intent_payload["response_budget"],
        "valid_until": intent_payload["valid_until"],
        "deadline_ms": intent_payload["deadline_ms"],
    }
    for key, value in request.items():
        if frame.get(key) != value:
            return False
    return True


def _validated_question_frame(
    intent_payload: Mapping[str, Any], frame: Mapping[str, Any] | None
) -> Mapping[str, Any] | None:
    """Return the frame if it fully matches the persisted INTENT, else ``None``.

    Every persisted identity and scope field must agree with the carrier
    frame, the frame must pass ``validate_consultation``, the persisted
    fingerprint and the persisted question digest must equal the
    corresponding frame fields, and the frame's ``consultation_id`` must
    equal the requested ``consultation_ref`` (already encoded in
    ``intent_payload['consultation_id']``).
    """
    if not isinstance(frame, Mapping):
        return None
    try:
        validate_consultation(dict(frame))
    except Exception:
        return None
    if not _intent_matches_frame(intent_payload, frame):
        return None
    if frame.get("fingerprint") != intent_payload.get("semantic_fingerprint"):
        return None
    if _question_digest(str(frame.get("question", ""))) != intent_payload.get(
        "question_digest"
    ):
        return None
    if frame.get("consultation_id") != intent_payload.get("consultation_id"):
        return None
    return frame


def _validated_answer_frame(
    intent_payload: Mapping[str, Any],
    answer_event: Any | None,
    frame: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Return the ANSWER frame iff every persisted field agrees.

    ``answer_event`` is the admitted non-historical ``ANSWER_AVAILABLE``
    event; ``frame`` is the carrier's ``get_answer`` result. The frame
    must pass ``validate_consultation``, be ``purpose == 'ANSWER'``,
    match the INTENT's ``consultation_id`` / ``message_key`` /
    ``correlation`` (with ``request_message_key`` set to the INTENT's
    message_key), agree with the INTENT on actors / binding / peer /
    artifact_revisions / valid_until / deadline_ms / response_budget,
    and agree with the admitted ``ANSWER_AVAILABLE`` payload on
    ``message_key``, ``fingerprint``, semantic answer digest and
    evidence revision digest.
    """
    if not isinstance(frame, Mapping):
        return None
    try:
        validate_consultation(dict(frame))
    except Exception:
        return None
    if frame.get("purpose") != "ANSWER":
        return None
    if frame.get("consultation_id") != intent_payload.get("consultation_id"):
        return None
    if frame.get("question_message_key") != intent_payload.get("message_key"):
        return None
    expected_correlation = dict(intent_payload.get("correlation") or {})
    expected_correlation["request_message_key"] = intent_payload.get(
        "message_key"
    )
    if dict(frame.get("correlation") or {}) != expected_correlation:
        return None
    if dict(frame.get("requester_actor_ref") or {}) != dict(
        intent_payload.get("requester_actor_ref") or {}
    ):
        return None
    if dict(frame.get("recipient_actor_ref") or {}) != dict(
        intent_payload.get("recipient_actor_ref") or {}
    ):
        return None
    if dict(frame.get("recipient_binding") or {}) != dict(
        intent_payload.get("recipient_binding") or {}
    ):
        return None
    if frame.get("recipient_peer_ref") != intent_payload.get(
        "recipient_peer_ref"
    ):
        return None
    if list(frame.get("artifact_revisions") or []) != list(
        intent_payload.get("artifact_revisions") or []
    ):
        return None
    if frame.get("valid_until") != intent_payload.get("valid_until"):
        return None
    if frame.get("deadline_ms") != intent_payload.get("deadline_ms"):
        return None
    if dict(frame.get("response_budget") or {}) != dict(
        intent_payload.get("response_budget") or {}
    ):
        return None
    if answer_event is None:
        return None
    admitted_payload = answer_event.payload
    if frame.get("message_key") != admitted_payload.get("message_key"):
        return None
    if frame.get("fingerprint") != admitted_payload.get("answer_fingerprint"):
        return None
    if _semantic_answer_digest(frame) != admitted_payload.get(
        "semantic_answer_digest"
    ):
        return None
    admitted_evidence_digest = admitted_payload.get("evidence_revision_digest")
    if admitted_evidence_digest:
        frame_artifact_digest = hashlib.sha256(
            canonical_consultation_json(
                frame.get("artifact_revisions", [])
            ).encode("utf-8")
        ).hexdigest()
        if frame_artifact_digest != admitted_evidence_digest:
            return None
    return frame


def _find_consultation_event(
    runtime: Runtime, consultation_id: str, event_type: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == event_type:
            return event
    return None


def _non_historical_answer_event(
    runtime: Runtime, consultation_id: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == "ANSWER_AVAILABLE" and not event.payload.get(
            "historical", False
        ):
            return event
    return None


def _caller_matches_actor(
    caller: CallerIdentity, actor_ref: Mapping[str, Any]
) -> bool:
    return (
        caller.job_id == str(actor_ref.get("job_id", ""))
        and caller.attempt_id == str(actor_ref.get("attempt_id", ""))
        and caller.worker_id == str(actor_ref.get("worker_id", ""))
    )


def _caller_matches_binding(
    caller: CallerIdentity, binding: Mapping[str, Any]
) -> bool:
    return (
        caller.binding.get("binding_id")
        == binding.get("binding_id")
        and caller.binding.get("binding_generation")
        == binding.get("binding_generation")
        and caller.binding.get("reasoning_surface")
        == binding.get("reasoning_surface")
    )


def _canonical_size(value: Mapping[str, Any]) -> int:
    return len(canonical_consultation_json(value).encode("utf-8"))


class RuntimeConsultationDispatcher:
    """Async gateway dispatcher; delegates durable effects to ConsultationRuntime.

    The dispatcher never invents body content; question/answer bodies are
    only ever taken from the ``packets`` carrier or returned to the caller
    after the runtime admitted the corresponding event. The
    ``invocations`` source is the only allowed source of identity for
    ``company.consult``. Production packet carriage is declared
    ``UNAVAILABLE``; see ``PRODUCTION_PACKET_CARRIAGE``.
    """

    _ALLOWED_TOOLS = frozenset(
        {"company.consult", "company.reply", "company.consultation"}
    )

    def __init__(
        self,
        *,
        runtime: Runtime,
        repository_root: Path,
        caller: CallerIdentity,
        recipients: RecipientResolver,
        packets: ConsultationPacketCarrier,
        invocations: InvocationContextSource,
        _clock: ClockFn | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        self.runtime = runtime
        self.repository_root = Path(repository_root).resolve()
        self.caller = caller
        self.recipients = recipients
        self.packets = packets
        self.invocations = invocations
        self._clock = _clock or utc_now_iso
        self._consultations = ConsultationRuntime(
            runtime, repository_root=self.repository_root, _clock=self._clock
        )

    async def __call__(
        self, tool_name: str, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        if tool_name not in self._ALLOWED_TOOLS:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"unknown tool: {tool_name}",
            )
        if tool_name == "company.consult":
            return await self._dispatch_consult(request)
        if tool_name == "company.reply":
            return await self._dispatch_reply(request)
        return await self._dispatch_read(request)

    # -- explicit authenticated consumption seam (NOT reachable via __call__) --

    def consume_answer(self, consultation_ref: str) -> dict[str, Any]:
        """Append one exact ``CONSUMED_BY_REQUESTER`` event for the requester.

        This is the only Python seam that appends ``CONSUMED_BY_REQUESTER``
        — the read tool ``company.consultation`` is zero-write and never
        calls it. ``self.caller`` must equal the persisted
        ``requester_actor_ref`` on job_id+attempt_id+worker_id (else
        ``NOT_A_PARTY``). The admitted non-historical ``ANSWER_AVAILABLE``
        event must exist (else ``CONFLICT``). The carrier must hold a
        frame that matches it (else ``CARRIER_UNAVAILABLE``).
        """
        intent = _find_consultation_event(
            self.runtime, consultation_ref, "INTENT"
        )
        if intent is None:
            raise ConsultationRefusal(
                "UNAVAILABLE", detail="no INTENT for consultation_ref"
            )
        requester_ref = intent.payload.get("requester_actor_ref") or {}
        if not _caller_matches_actor(self.caller, requester_ref):
            raise ConsultationRefusal(
                "NOT_A_PARTY",
                detail="caller is not the requester Runtime Attempt",
            )
        answer_frame = self.packets.get_answer(consultation_ref)
        if answer_frame is None:
            raise ConsultationRefusal(
                "CARRIER_UNAVAILABLE",
                detail="no admitted ANSWER frame on the carrier",
            )
        reserved = _non_historical_answer_event(
            self.runtime, consultation_ref
        )
        if reserved is None:
            raise ConsultationRefusal(
                "CONFLICT",
                detail="no admitted non-historical ANSWER_AVAILABLE",
            )
        if (
            str(reserved.payload.get("message_key", ""))
            != str(answer_frame.get("message_key", ""))
            or str(reserved.payload.get("answer_fingerprint", ""))
            != str(answer_frame.get("fingerprint", ""))
            or str(reserved.payload.get("semantic_answer_digest", ""))
            != _semantic_answer_digest(answer_frame)
        ):
            raise ConsultationRefusal(
                "CONFLICT",
                detail="carrier ANSWER frame does not match admitted event",
            )
        try:
            result = self._consultations.consumed_by_requester(
                answer_frame,
                requester_attempt_id=self.caller.attempt_id,
                observed_at=self._clock(),
            )
        except (StateConflict, ConsultationConflict) as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc
        return {
            "consultation_ref": consultation_ref,
            "state": "CONSUMED",
            "inserted": bool(result.inserted),
        }

    # -- company.consult --

    async def _dispatch_consult(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            validated = validate_company_consult_dispatch_request(dict(request))
        except Exception as exc:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"dispatch envelope invalid: {type(exc).__name__}",
            ) from exc

        peer_ref = validated["peer"]["peer_ref"]
        semantic = dict(validated["semantic"])

        if semantic.get("to") != peer_ref:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail="semantic.to must equal peer.peer_ref",
            )

        try:
            recipient = self.recipients(peer_ref)
            recipient_actor_ref = _normalized_actor_ref(recipient.actor_ref)
            normalized_recipient_binding = dict(recipient.recipient_binding)
        except NoSuchRecipient as exc:
            raise ConsultationRefusal(
                "NOT_A_PARTY", detail=type(exc).__name__
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"recipient binding normalization failed: {type(exc).__name__}",
            ) from exc

        if recipient_actor_ref["worker_id"] == self.caller.worker_id:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail="requester and recipient worker_ids must differ",
            )

        ctx = self.invocations.current()
        if ctx is None:
            raise ConsultationRefusal(
                "INVOCATION_CONTEXT_UNAVAILABLE",
                detail="invocations.current() returned None",
            )

        identity_hash = _mint_request_identity(
            caller=self.caller,
            peer_ref=peer_ref,
            invocation_id=ctx.invocation_id,
        )
        consultation_id, message_key = _build_deterministic_ids(identity_hash)

        # Deadline / valid_until derive from the owner-issued context.
        valid_until = _format_utc_seconds(
            _parse_utc_seconds(ctx.issued_at)
            + dt.timedelta(seconds=ctx.valid_for_seconds)
        )

        response_budget = dict(ctx.response_budget)

        requester_actor_ref = {
            "kind": "worker_attempt",
            "job_id": self.caller.job_id,
            "attempt_id": self.caller.attempt_id,
            "worker_id": self.caller.worker_id,
        }
        (
            requester_actor_digest,
            recipient_actor_digest,
        ) = _correlation_digests(requester_actor_ref, recipient_actor_ref)

        correlation = {
            "parent_fingerprint": ctx.parent_fingerprint,
            "request_message_key": message_key,
            "consultation_id": consultation_id,
            "requester_actor_digest": requester_actor_digest,
            "recipient_actor_digest": recipient_actor_digest,
        }

        question_frame = _build_question_frame(
            caller=self.caller,
            requester_actor_ref=requester_actor_ref,
            recipient_actor_ref=recipient_actor_ref,
            recipient_peer_ref=peer_ref,
            recipient_binding=normalized_recipient_binding,
            correlation=correlation,
            question_text=semantic["question"],
            evidence_refs=list(semantic.get("evidence_refs", [])),
            artifact_revisions=list(semantic.get("artifact_revisions", [])),
            message_key=message_key,
            consultation_id=consultation_id,
            valid_until=valid_until,
            deadline_ms=ctx.deadline_ms,
            response_budget=response_budget,
        )

        # If an INTENT for this consultation_id already exists, reconcile
        # the entire normalized semantic request against the persisted
        # INTENT. Rebuild a CANDIDATE frame under the persisted identity
        # and scope (message_key, consultation_id, requester/recipient
        # refs, recipient_binding, peer, correlation, artifact handling,
        # valid_until, deadline_ms, response_budget) but with the NEW
        # request's ``question``, ``evidence_refs``, and
        # ``artifact_revisions``. The candidate's contract fingerprint
        # must equal the persisted semantic fingerprint and its
        # recipient peer_ref must equal the persisted recipient peer
        # ref; when the carrier holds the original QUESTION packet, the
        # body parts (``question``, ``evidence_refs``,
        # ``artifact_revisions``) must also be exactly equal to the
        # carrier frame. Any mismatch → CONFLICT with zero ``intent()``
        # and zero ``put_question``. On full equality, replay
        # ``intent()`` (returns ``inserted=False``) and call
        # ``put_question`` only if the carrier doesn't already hold it.
        existing_intent = _find_consultation_event(
            self.runtime, consultation_id, "INTENT"
        )
        carrier_question_frame = self.packets.get_question(consultation_id)
        carrier_holds_packet = carrier_question_frame is not None
        if existing_intent is not None:
            persisted_payload = existing_intent.payload
            candidate = _build_question_frame(
                caller=self.caller,
                requester_actor_ref=dict(
                    persisted_payload.get("requester_actor_ref")
                    or requester_actor_ref
                ),
                recipient_actor_ref=dict(
                    persisted_payload.get("recipient_actor_ref")
                    or recipient_actor_ref
                ),
                recipient_peer_ref=str(
                    persisted_payload.get(
                        "recipient_peer_ref", peer_ref
                    )
                ),
                recipient_binding=dict(
                    persisted_payload.get("recipient_binding")
                    or normalized_recipient_binding
                ),
                correlation=dict(
                    persisted_payload.get("correlation") or correlation
                ),
                question_text=str(semantic["question"]),
                evidence_refs=list(semantic.get("evidence_refs", [])),
                artifact_revisions=list(
                    semantic.get("artifact_revisions", [])
                ),
                message_key=str(persisted_payload.get("message_key")),
                consultation_id=str(
                    persisted_payload.get("consultation_id")
                ),
                valid_until=str(persisted_payload.get("valid_until")),
                deadline_ms=int(persisted_payload.get("deadline_ms")),
                response_budget=dict(
                    persisted_payload.get("response_budget")
                    or response_budget
                ),
            )
            persisted_fingerprint = str(
                persisted_payload.get("semantic_fingerprint", "")
            )
            persisted_peer_ref = str(
                persisted_payload.get("recipient_peer_ref", "")
            )
            candidate_fingerprint = str(candidate.get("fingerprint", ""))
            fingerprint_agrees = (
                candidate_fingerprint == persisted_fingerprint
            )
            peer_ref_agrees = (
                str(candidate.get("recipient_peer_ref", ""))
                == persisted_peer_ref
            )
            body_agrees = True
            if carrier_holds_packet:
                body_agrees = (
                    str(candidate.get("question", ""))
                    == str(carrier_question_frame.get("question", ""))
                    and list(candidate.get("evidence_refs", []))
                    == list(carrier_question_frame.get("evidence_refs", []))
                    and list(candidate.get("artifact_revisions", []))
                    == list(
                        carrier_question_frame.get("artifact_revisions", [])
                    )
                )
            if not (fingerprint_agrees and peer_ref_agrees and body_agrees):
                raise ConsultationRefusal(
                    "CONFLICT",
                    detail="consultation_id reused with changed semantic payload",
                )
            question_frame = candidate

        carrier_ref = f"company-mcp://{consultation_id}"

        try:
            intent_result = self._consultations.intent(
                question_frame,
                requester_attempt_id=self.caller.attempt_id,
                carrier_ref=carrier_ref,
                observed_at=ctx.issued_at,
                repository_root=self.repository_root,
            )
        except ConsultationConflict as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc
        except StateConflict as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc

        # Carrier put happens only after ``intent()`` returned (inserted
        # or replayed). For a replay path, the carrier already holds
        # the frame — skip the put so we don't clobber the original
        # question text the original caller put on the carrier. The
        # whole-semantic replay above already proved the carrier packet
        # agrees with the rebuilt candidate frame.
        if existing_intent is None or not carrier_holds_packet:
            self.packets.put_question(consultation_id, question_frame)

        try:
            wake_state = self._consultations.resolve_restart(question_frame)
        except StateConflict:
            return {
                "ok": True,
                "result": {
                    "schema": _INBOX_SCHEMA,
                    "consultation_ref": consultation_id,
                    "consultation_id": consultation_id,
                    "wake_state": "RECONCILIATION_REQUIRED",
                    "deadline": valid_until,
                    "intended": intent_result.inserted,
                    "is_already_intended": not intent_result.inserted,
                    "state": (
                        "ALREADY_INTENDED"
                        if not intent_result.inserted
                        else "INTENDED"
                    ),
                    "carrier_ref": carrier_ref,
                    "blocker": "WAKE_STATE_UNAVAILABLE",
                },
            }
        return {
            "ok": True,
            "result": {
                "schema": _INBOX_SCHEMA,
                "consultation_ref": consultation_id,
                "consultation_id": consultation_id,
                "wake_state": wake_state,
                "deadline": valid_until,
                "intended": intent_result.inserted,
                "is_already_intended": not intent_result.inserted,
                "state": (
                    "ALREADY_INTENDED"
                    if not intent_result.inserted
                    else "INTENDED"
                ),
                "carrier_ref": carrier_ref,
            },
        }

    # -- company.reply --

    async def _dispatch_reply(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        raw_semantic = request.get("semantic")
        if not isinstance(raw_semantic, Mapping):
            raise ConsultationRefusal(
                "INVALID_REQUEST", detail="semantic mapping required"
            )
        semantic = dict(raw_semantic)
        invalid = _validate_reply_semantic(semantic)
        if invalid is not None:
            raise ConsultationRefusal("INVALID_REQUEST", detail=invalid)

        consultation_ref = semantic["consultation_ref"]
        intent = _find_consultation_event(
            self.runtime, consultation_ref, "INTENT"
        )
        if intent is None:
            raise ConsultationRefusal(
                "UNAVAILABLE", detail="no INTENT for consultation_ref"
            )
        recipient_actor_ref = intent.payload.get("recipient_actor_ref") or {}
        recipient_binding = intent.payload.get("recipient_binding") or {}
        if not _caller_matches_actor(self.caller, recipient_actor_ref):
            raise ConsultationRefusal(
                "NOT_A_PARTY",
                detail="caller is not the recipient Runtime Attempt",
            )
        if not _caller_matches_binding(self.caller, recipient_binding):
            raise ConsultationRefusal(
                "STALE_BINDING",
                detail="caller RuntimeBinding does not match persisted recipient_binding",
            )

        question_frame = self.packets.get_question(consultation_ref)
        if question_frame is None:
            raise ConsultationRefusal(
                "CARRIER_UNAVAILABLE",
                detail="no QUESTION frame on the carrier",
            )
        try:
            validate_consultation(dict(question_frame))
        except Exception as exc:
            raise ConsultationRefusal(
                "CONFLICT",
                detail=f"carrier QUESTION frame invalid: {type(exc).__name__}",
            ) from exc
        if (
            question_frame.get("consultation_id") != consultation_ref
            or question_frame.get("message_key")
            != intent.payload.get("message_key")
            or question_frame.get("fingerprint")
            != intent.payload.get("semantic_fingerprint")
            or _question_digest(str(question_frame.get("question", "")))
            != intent.payload.get("question_digest")
        ):
            raise ConsultationRefusal(
                "CONFLICT",
                detail="carrier QUESTION frame does not match persisted INTENT",
            )
        if not _intent_matches_frame(intent.payload, question_frame):
            raise ConsultationRefusal(
                "CONFLICT",
                detail="carrier QUESTION frame fields disagree with persisted INTENT",
            )

        # Enforce response_budget.max_payload_bytes on the canonical answer JSON.
        answer_text = str(semantic.get("answer", ""))
        evidence_refs = list(semantic.get("evidence_refs", []))
        answer_canonical = canonical_consultation_json(
            {"text": answer_text, "evidence_refs": evidence_refs}
        )
        max_payload_bytes = int(
            intent.payload.get("response_budget", {}).get(
                "max_payload_bytes", _DEFAULT_RESPONSE_BUDGET["max_payload_bytes"]
            )
        )
        if len(answer_canonical.encode("utf-8")) > max_payload_bytes:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"answer canonical JSON exceeds {max_payload_bytes} bytes",
            )

        try:
            answer_frame = _build_answer_frame(
                question_frame,
                answer_text=answer_text,
                evidence_refs=evidence_refs,
                supersedes=semantic.get("supersedes_message_key"),
            )
        except Exception as exc:
            raise ConsultationRefusal(
                "CONFLICT",
                detail=f"answer frame invalid: {type(exc).__name__}",
            ) from exc

        try:
            question_item = self._consultations._intent_from_event(intent)
            pre_wake_state = self._consultations._canonical_wake_state(
                question_item
            ).value
        except ConsultationConflict as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc
        except StateConflict as exc:
            raise ConsultationRefusal(
                "WAKE_NOT_ACKNOWLEDGED",
                detail=f"wake state unavailable: {type(exc).__name__}",
            ) from exc

        if pre_wake_state not in _ACKNOWLEDGED_WAKE_STATES:
            raise ConsultationRefusal(
                "WAKE_NOT_ACKNOWLEDGED",
                detail="answer requires canonical TARGET_ACKNOWLEDGED Wake evidence",
            )

        def _reconciled_envelope(
            reserved_event: Any,
        ) -> dict[str, Any]:
            return {
                "ok": True,
                "result": {
                    "schema": _INBOX_SCHEMA,
                    "consultation_ref": consultation_ref,
                    "state": "ANSWER_AVAILABLE",
                    "answer_fingerprint": reserved_event.payload.get(
                        "answer_fingerprint", ""
                    ),
                    "semantic_answer_digest": reserved_event.payload.get(
                        "semantic_answer_digest", ""
                    ),
                    "historical": False,
                    "inserted": False,
                    "reconciled": True,
                },
            }

        # Reconcile on the carrier FIRST. If the runtime already admitted
        # a non-historical ANSWER_AVAILABLE, the carrier is the
        # single source of truth for the admitted packet: validate it
        # with ``_validated_answer_frame`` and reconcile without
        # touching the runtime or the carrier again. A missing or
        # mismatched carrier frame is the same-carrier recovery
        # barrier (CARRIER_RECONCILIATION_REQUIRED); we never rewrite
        # and never resend.
        reserved = _non_historical_answer_event(
            self.runtime, consultation_ref
        )
        if reserved is not None:
            packet = self.packets.get_answer(consultation_ref)
            validated = _validated_answer_frame(
                intent.payload, reserved, packet
            )
            if validated is None:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="admitted ANSWER_AVAILABLE but carrier frame is missing or fails validation",
                )
            return _reconciled_envelope(reserved)

        try:
            answer = self._consultations.answer_available(
                answer_frame, observed_at=self._clock()
            )
        except ConsultationConflict as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc
        except StateConflict as exc:
            message = str(exc)
            if "TARGET_ACKNOWLEDGED" in message:
                raise ConsultationRefusal(
                    "WAKE_NOT_ACKNOWLEDGED",
                    detail="answer requires TARGET_ACKNOWLEDGED Wake evidence",
                ) from exc
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc

        event = answer.event
        event_type = getattr(event, "event_type", "")
        payload_fact = (
            event.payload.get("fact") if hasattr(event, "payload") else None
        )
        if event_type == "ANSWER_REFUSED" or payload_fact == "ANSWER_REFUSED":
            raise ConsultationRefusal(
                "CONFLICT", detail="ANSWER_REFUSED"
            )

        historical = bool(event.payload.get("historical", False))
        if historical:
            # Historical answer is not put on the carrier; never labelled
            # current.
            return {
                "ok": True,
                "result": {
                    "schema": _INBOX_SCHEMA,
                    "consultation_ref": consultation_ref,
                    "state": "ANSWER_HISTORICAL",
                    "answer_fingerprint": event.payload.get(
                        "answer_fingerprint", ""
                    ),
                    "semantic_answer_digest": event.payload.get(
                        "semantic_answer_digest", ""
                    ),
                    "historical": True,
                    "inserted": bool(answer.inserted),
                },
            }

        # Race path: the runtime did not append a new event because it
        # returned the already-reserved event (``inserted=False``). Take
        # the same readback path as the early reserved check — no
        # ``put_answer``.
        if not answer.inserted:
            current_reserved = _non_historical_answer_event(
                self.runtime, consultation_ref
            )
            packet = self.packets.get_answer(consultation_ref)
            validated = _validated_answer_frame(
                intent.payload, current_reserved, packet
            )
            if validated is None:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="replay ANSWER_AVAILABLE admitted but carrier frame is missing or fails validation",
                )
            return _reconciled_envelope(current_reserved)

        # Admitted only: cache the exact admitted frame for the
        # requester dispatcher to drive ``consume_answer``. The runtime
        # event is the durable source of truth; a lost carrier write
        # here is the lost-write barrier — we raise
        # CARRIER_RECONCILIATION_REQUIRED and never retry inside this
        # call.
        if (
            event_type == "ANSWER_AVAILABLE"
            and payload_fact == "ANSWER_AVAILABLE"
        ):
            try:
                self.packets.put_answer(consultation_ref, answer_frame)
            except Exception as exc:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="runtime event admitted but carrier write failed",
                ) from exc

        return {
            "ok": True,
            "result": {
                "schema": _INBOX_SCHEMA,
                "consultation_ref": consultation_ref,
                "state": "ANSWER_AVAILABLE",
                "answer_fingerprint": event.payload.get(
                    "answer_fingerprint", ""
                ),
                "semantic_answer_digest": event.payload.get(
                    "semantic_answer_digest", ""
                ),
                "historical": False,
                "inserted": bool(answer.inserted),
            },
        }

    # -- company.consultation --

    async def _dispatch_read(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        raw_semantic = request.get("semantic")
        if not isinstance(raw_semantic, Mapping):
            raise ConsultationRefusal(
                "INVALID_REQUEST", detail="semantic mapping required"
            )
        semantic = dict(raw_semantic)
        invalid = _validate_read_semantic(semantic)
        if invalid is not None:
            raise ConsultationRefusal("INVALID_REQUEST", detail=invalid)

        consultation_ref = semantic["consultation_ref"]
        intent = _find_consultation_event(
            self.runtime, consultation_ref, "INTENT"
        )
        if intent is None:
            raise ConsultationRefusal(
                "UNAVAILABLE", detail="no INTENT for consultation_ref"
            )
        requester_ref = intent.payload.get("requester_actor_ref") or {}
        recipient_ref = intent.payload.get("recipient_actor_ref") or {}
        if not (
            _caller_matches_actor(self.caller, requester_ref)
            or _caller_matches_actor(self.caller, recipient_ref)
        ):
            raise ConsultationRefusal(
                "NOT_A_PARTY",
                detail="caller is neither requester nor recipient Runtime Attempt",
            )

        row = company_inbox_row(
            self.runtime,
            consultation_ref,
            {
                "job_id": self.caller.job_id,
                "attempt_id": self.caller.attempt_id,
                "worker_id": self.caller.worker_id,
            },
            self._clock(),
        )

        question_frame = self.packets.get_question(consultation_ref)
        answer_frame = self.packets.get_answer(consultation_ref)

        # Validate every carrier frame against the persisted INTENT and
        # (for answers) the admitted non-historical ANSWER_AVAILABLE
        # event. Reject the body entirely on any mismatch; the row's
        # blocker becomes ``CARRIER_INTEGRITY`` and no part of the
        # rejected frame reaches the read result, blocker, log, or
        # exception.
        reserved_answer = _non_historical_answer_event(
            self.runtime, consultation_ref
        )
        validated_question = _validated_question_frame(
            intent.payload, question_frame
        )
        validated_answer = _validated_answer_frame(
            intent.payload, reserved_answer, answer_frame
        )

        question_body, question_blocker = _build_question_body(
            question_frame, validated_question is not None
        )
        answer_body, answer_blocker = _build_answer_body(
            answer_frame, reserved_answer, validated_answer is not None
        )

        body_status, body_blocker = _body_status_for(
            question_body, answer_body, question_blocker, answer_blocker
        )

        result = dict(row)
        result["question"] = question_body
        result["answer"] = answer_body
        result["body_status"] = body_status
        if body_blocker is not None:
            result["blocker"] = body_blocker
        elif row.get("blocker") is None:
            result["blocker"] = None

        if _canonical_size(result) > _BODY_BUDGET_BYTES:
            digest_only = dict(row)
            digest_only["question"] = None
            digest_only["answer"] = None
            digest_only["body_status"] = "UNAVAILABLE"
            digest_only["blocker"] = "BODY_OVER_BUDGET"
            return {"ok": True, "result": digest_only}

        return {"ok": True, "result": result}

    def inbox_projection(self) -> dict[str, Any]:
        """Return the full inbox projection for the caller. Read-only."""
        return project_company_inbox(
            self.runtime,
            actor={
                "job_id": self.caller.job_id,
                "attempt_id": self.caller.attempt_id,
                "worker_id": self.caller.worker_id,
            },
            now=self._clock(),
        )


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _semantic_answer_digest(frame: Mapping[str, Any]) -> str:
    answer = frame.get("answer")
    if not isinstance(answer, Mapping):
        return ""
    try:
        parsed = json.loads(str(answer.get("text", "")))
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(parsed, Mapping):
        return ""
    return hashlib.sha256(
        canonical_consultation_json(parsed).encode("utf-8")
    ).hexdigest()


def _normalized_actor_ref(actor_ref: Mapping[str, Any]) -> dict[str, str]:
    actor = dict(actor_ref)
    job_id = actor.get("job_id")
    attempt_id = actor.get("attempt_id")
    worker_id = actor.get("worker_id")
    if not (
        isinstance(job_id, str)
        and isinstance(attempt_id, str)
        and isinstance(worker_id, str)
    ):
        raise KeyError(
            "recipient actor_ref requires job_id, attempt_id, worker_id"
        )
    if not (job_id and attempt_id and worker_id):
        raise KeyError(
            "recipient actor_ref requires non-empty job_id, attempt_id, worker_id"
        )
    return {
        "kind": str(actor.get("kind", "worker_attempt")),
        "job_id": job_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
    }


def _correlation_digests(
    requester: Mapping[str, Any], recipient: Mapping[str, Any]
) -> tuple[str, str]:
    return (
        _sha64(dict(requester)),
        _sha64(dict(recipient)),
    )


def _build_question_frame(
    *,
    caller: CallerIdentity,
    requester_actor_ref: Mapping[str, Any],
    recipient_actor_ref: Mapping[str, Any],
    recipient_peer_ref: str,
    recipient_binding: Mapping[str, Any],
    correlation: Mapping[str, Any],
    question_text: str,
    evidence_refs: list[str],
    artifact_revisions: list[dict[str, str]],
    message_key: str,
    consultation_id: str,
    valid_until: str,
    deadline_ms: int,
    response_budget: Mapping[str, Any],
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": _consultation_schema_for(caller.reasoning_surface),
        "message_key": message_key,
        "consultation_id": consultation_id,
        "purpose": "QUESTION",
        "requester_actor_ref": dict(requester_actor_ref),
        "recipient_actor_ref": dict(recipient_actor_ref),
        "recipient_peer_ref": recipient_peer_ref,
        "recipient_binding": dict(recipient_binding),
        "correlation": dict(correlation),
        "question": question_text,
        "answer": None,
        "evidence_refs": list(evidence_refs),
        "artifact_revisions": list(artifact_revisions),
        "valid_until": valid_until,
        "deadline_ms": int(deadline_ms),
        "response_budget": dict(response_budget),
        "supersedes_message_key": None,
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    return build_consultation(raw)


def _rebuild_question_frame_from_intent(
    intent_payload: Mapping[str, Any], carrier_frame: Mapping[str, Any]
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": str(intent_payload["consultation_schema"]),
        "message_key": intent_payload["message_key"],
        "consultation_id": intent_payload["consultation_id"],
        "purpose": "QUESTION",
        "requester_actor_ref": dict(intent_payload["requester_actor_ref"]),
        "recipient_actor_ref": dict(intent_payload["recipient_actor_ref"]),
        "recipient_peer_ref": intent_payload["recipient_peer_ref"],
        "recipient_binding": dict(intent_payload["recipient_binding"]),
        "correlation": dict(intent_payload["correlation"]),
        "question": carrier_frame["question"],
        "answer": None,
        "evidence_refs": list(carrier_frame.get("evidence_refs", [])),
        "artifact_revisions": list(intent_payload["artifact_revisions"]),
        "valid_until": intent_payload["valid_until"],
        "deadline_ms": int(intent_payload["deadline_ms"]),
        "response_budget": dict(intent_payload["response_budget"]),
        "supersedes_message_key": None,
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    try:
        return build_consultation(raw)
    except Exception:
        raise


def _build_answer_frame(
    question_frame: Mapping[str, Any],
    *,
    answer_text: str,
    evidence_refs: list[str],
    supersedes: Any,
) -> dict[str, Any]:
    semantic_answer = {"text": answer_text, "evidence_refs": list(evidence_refs)}
    semantic_answer_text = json.dumps(
        semantic_answer, sort_keys=True, separators=(",", ":")
    )
    raw_answer_digest_payload = {
        "text": semantic_answer_text,
        "evidence_refs": list(evidence_refs),
    }
    sem_answer_digest = hashlib.sha256(
        canonical_consultation_json(raw_answer_digest_payload).encode("utf-8")
    ).hexdigest()
    message_key_digest = hashlib.sha256(
        ("asd-answer-" + sem_answer_digest).encode("utf-8")
    ).hexdigest()
    message_key = f"asd-consultation-{message_key_digest[:16]}"

    raw = {
        "schema": CONSULTATION_V2_SCHEMA,
        "message_key": message_key,
        "consultation_id": question_frame["consultation_id"],
        "purpose": "ANSWER",
        "requester_actor_ref": dict(question_frame["requester_actor_ref"]),
        "recipient_actor_ref": dict(question_frame["recipient_actor_ref"]),
        "recipient_peer_ref": question_frame["recipient_peer_ref"],
        "recipient_binding": dict(question_frame["recipient_binding"]),
        "correlation": {
            **dict(question_frame["correlation"]),
            "request_message_key": question_frame["message_key"],
        },
        "question": None,
        "answer": raw_answer_digest_payload,
        "evidence_refs": list(evidence_refs),
        "artifact_revisions": list(question_frame["artifact_revisions"]),
        "valid_until": question_frame["valid_until"],
        "deadline_ms": int(question_frame["deadline_ms"]),
        "response_budget": dict(question_frame["response_budget"]),
        "supersedes_message_key": supersedes,
        "question_message_key": question_frame["message_key"],
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    return build_consultation(raw)


def _build_question_body(
    question_frame: Mapping[str, Any] | None,
    is_validated: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(body, blocker)``.

    ``is_validated`` is the result of ``_validated_question_frame`` against
    the persisted INTENT. Three cases:

    * Validated frame with a string ``question`` → body + no blocker.
    * Frame present but fails any validation check → body withheld,
      blocker ``CARRIER_INTEGRITY`` (the frame is corrupted relative to
      the persisted INTENT).
    * No frame on the carrier → body withheld, blocker
      ``CARRIER_UNAVAILABLE`` (the carrier never received the question).
    """
    if question_frame is None:
        return (None, "CARRIER_UNAVAILABLE")
    if not is_validated:
        return (None, "CARRIER_INTEGRITY")
    question = question_frame.get("question")
    if not isinstance(question, str):
        return (None, "CARRIER_INTEGRITY")
    return (
        {
            "text": question,
            "evidence_refs": list(question_frame.get("evidence_refs", [])),
        },
        None,
    )


def _build_answer_body(
    answer_frame: Mapping[str, Any] | None,
    reserved_event: Any | None,
    is_validated: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(body, blocker)``.

    Four cases:

    * No admitted non-historical ``ANSWER_AVAILABLE`` → body not yet
      available, blocker ``CARRIER_UNAVAILABLE``.
    * Admitted ``ANSWER_AVAILABLE`` but the carrier has no ANSWER frame
      → body withheld, blocker ``CARRIER_UNAVAILABLE`` (the carrier
      never received the answer; the lost-write barrier on the reply
      path is the recovery seam).
    * Frame present but fails ``_validated_answer_frame`` (or the frame
      has no parseable answer text) → body withheld, blocker
      ``CARRIER_INTEGRITY`` (the frame is corrupted relative to the
      admitted ``ANSWER_AVAILABLE``).
    * Validated frame → body with the recipient's original text +
      evidence_refs.
    """
    if reserved_event is None and answer_frame is None:
        return (None, "CARRIER_UNAVAILABLE")
    if reserved_event is None:
        return (None, "CARRIER_UNAVAILABLE")
    if answer_frame is None:
        return (None, "CARRIER_UNAVAILABLE")
    if not is_validated:
        return (None, "CARRIER_INTEGRITY")
    raw_answer = answer_frame.get("answer")
    if not isinstance(raw_answer, Mapping):
        return (None, "CARRIER_INTEGRITY")
    raw_text = raw_answer.get("text")
    if not isinstance(raw_text, str):
        return (None, "CARRIER_INTEGRITY")
    try:
        parsed = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        return (None, "CARRIER_INTEGRITY")
    if not isinstance(parsed, Mapping):
        return (None, "CARRIER_INTEGRITY")
    text = parsed.get("text")
    if not isinstance(text, str):
        return (None, "CARRIER_INTEGRITY")
    evidence_refs = parsed.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    return ({"text": text, "evidence_refs": list(evidence_refs)}, None)


def _body_status_for(
    question_body: dict[str, Any] | None,
    answer_body: dict[str, Any] | None,
    question_blocker: str | None,
    answer_blocker: str | None,
) -> tuple[str, str | None]:
    if question_body is not None and answer_body is not None:
        return ("AVAILABLE", None)
    blocker = question_blocker or answer_blocker
    if question_body is None and answer_body is None:
        return ("UNAVAILABLE", blocker or "CARRIER_UNAVAILABLE")
    return ("PARTIAL", blocker or "CARRIER_UNAVAILABLE")


__all__ = [
    "CallerIdentity",
    "ConsultationPacketCarrier",
    "ConsultationRefusal",
    "InMemoryConsultationPacketCarrier",
    "InvocationContext",
    "InvocationContextSource",
    "NoSuchRecipient",
    "PRODUCTION_PACKET_CARRIAGE",
    "REFUSAL_CODES",
    "RecipientBinding",
    "RecipientResolver",
    "RuntimeConsultationDispatcher",
]
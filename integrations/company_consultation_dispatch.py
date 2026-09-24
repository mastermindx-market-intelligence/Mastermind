"""Runtime-backed Company MCP consultation dispatcher.

This joins ``CompanyConsultationGateway`` to ``ConsultationRuntime``. The
dispatcher owns no peer registry and no Runtime lookup of its own — the host
supplies the verified ``CallerIdentity`` (current RuntimeBinding) and the
``recipients`` resolver that maps each trusted ``peer.peer_ref`` to the
recipient's actor ref + ``recipient_binding``.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    CONSULTATION_V2_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    RECEIPT_KEYS,
    build_consultation,
    canonical_consultation_json,
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
_DEFAULT_DEADLINE_MS = 60_000
_VALID_UNTIL_OFFSET = dt.timedelta(hours=24)
_INBOX_SCHEMA = "mastermind.company_inbox.v1"
_CONSULTATION_REF_RE = re.compile(r"\Aconsult-[0-9a-f]{32}\Z")
_REPLY_SEMANTIC_KEYS = frozenset(
    {"consultation_ref", "answer", "supersedes_message_key", "evidence_refs"}
)
_READ_SEMANTIC_KEYS = frozenset({"consultation_ref"})
_ANSWER_PAYLOAD_BUDGET_BYTES = 32768
_ACKNOWLEDGED_WAKE_STATES = frozenset(
    {"TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"}
)


class AnswerFrameCarrier(Protocol):
    """In-process carrier for the deterministic ANSWER frame.

    The recipient dispatcher puts the exact admitted ANSWER frame into the
    carrier; the requester dispatcher reads it to drive
    ``consumed_by_requester``. The carrier holds ``frame`` only after the
    runtime has actually admitted ``ANSWER_AVAILABLE`` for the
    ``consultation_id`` — never before.
    """

    def put(self, consultation_id: str, frame: Mapping[str, Any]) -> None:
        ...

    def get(self, consultation_id: str) -> Mapping[str, Any] | None:
        ...


class InMemoryAnswerFrameCarrier:
    """Hermetic in-process ``AnswerFrameCarrier`` used by tests."""

    def __init__(self) -> None:
        self._frames: dict[str, dict[str, Any]] = {}

    def put(self, consultation_id: str, frame: Mapping[str, Any]) -> None:
        self._frames[consultation_id] = dict(frame)

    def get(self, consultation_id: str) -> Mapping[str, Any] | None:
        frame = self._frames.get(consultation_id)
        return dict(frame) if frame is not None else None


@dataclasses.dataclass(frozen=True)
class CallerIdentity:
    """The verified current RuntimeBinding the host injects."""

    worker_id: str
    attempt_id: str
    reasoning_surface: str
    binding: Mapping[str, Any]
    job_id: str = ""


@dataclasses.dataclass(frozen=True)
class RecipientBinding:
    """One recipient resolved by the trusted host resolver."""

    actor_ref: Mapping[str, Any]
    recipient_binding: Mapping[str, Any]


RecipientResolver = Callable[[str], RecipientBinding]
ClockFn = Callable[[], str]


class ConsultationRefusal(Exception):
    """Typed zero-effect refusal surfaced as a dict."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message if message is not None else code
        super().__init__(self.message)


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
    semantic_fingerprint: str,
) -> str:
    """Deterministic program-scoped consultation identity input.

    The hash binds only the semantic identity inputs (caller worker +
    attempt + peer + semantic fingerprint). ``issued_at`` and
    ``valid_until`` are admitted as inert payload fields but never enter
    the hash — an advancing gateway clock cannot mint a new
    consultation_id for the same question.
    """
    payload = {
        "actor": {
            "worker_id": caller.worker_id,
            "attempt_id": caller.attempt_id,
            "reasoning_surface": caller.reasoning_surface,
        },
        "peer_ref": peer_ref,
        "semantic_fingerprint": semantic_fingerprint,
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


def _typed_refusal(code: str, message: str) -> dict[str, Any]:
    return {
        "schema": _INBOX_SCHEMA,
        "code": code,
        "message": message,
        "refusal": True,
        "blocker": code,
    }


def _validate_reply_semantic(semantic: Mapping[str, Any]) -> str | None:
    """Return an ``INVALID_REQUEST`` message or ``None`` if valid."""
    if set(semantic) != _REPLY_SEMANTIC_KEYS:
        return (
            "semantic must carry exactly "
            "{consultation_ref, answer, supersedes_message_key, evidence_refs}"
        )
    consultation_ref = semantic.get("consultation_ref")
    if not isinstance(consultation_ref, str):
        return "consultation_ref must be a string"
    if _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None:
        return (
            "consultation_ref must match ^consult-[0-9a-f]{32}$"
        )
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
    canonical = canonical_consultation_json(
        {"text": answer, "evidence_refs": list(evidence_refs)}
    )
    if len(canonical.encode("utf-8")) > _ANSWER_PAYLOAD_BUDGET_BYTES:
        return (
            f"answer canonical JSON exceeds { _ANSWER_PAYLOAD_BUDGET_BYTES } bytes"
        )
    return None


def _validate_read_semantic(semantic: Mapping[str, Any]) -> str | None:
    """Return an ``INVALID_REQUEST`` message or ``None`` if valid."""
    if set(semantic) != _READ_SEMANTIC_KEYS:
        return "semantic must carry exactly {consultation_ref}"
    consultation_ref = semantic.get("consultation_ref")
    if not isinstance(consultation_ref, str):
        return "consultation_ref must be a string"
    if _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None:
        return (
            "consultation_ref must match ^consult-[0-9a-f]{32}$"
        )
    return None


class RuntimeConsultationDispatcher:
    """Async gateway dispatcher; delegates durable effects to ConsultationRuntime."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        repository_root: Path,
        caller: CallerIdentity,
        recipients: RecipientResolver,
        answer_frames: AnswerFrameCarrier,
        _clock: ClockFn | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        self.runtime = runtime
        self.repository_root = Path(repository_root).resolve()
        self.caller = caller
        self.recipients = recipients
        self.answer_frames = answer_frames
        self._clock = _clock or utc_now_iso
        self._consultations = ConsultationRuntime(
            runtime, repository_root=self.repository_root, _clock=self._clock
        )

    async def __call__(
        self, tool_name: str, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        if tool_name == "company.consult":
            return await self._dispatch_consult(request)
        if tool_name == "company.reply":
            return await self._dispatch_reply(request)
        if tool_name == "company.consultation":
            return await self._dispatch_read(request)
        return {
            "ok": True,
            "result": _typed_refusal(
                "UNAVAILABLE", f"unknown tool: {tool_name}"
            ),
        }

    async def _dispatch_consult(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            validated = validate_company_consult_dispatch_request(dict(request))
        except Exception as exc:  # noqa: BLE001 — contract-defined typed refusal.
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", str(exc) or "invalid request"
                ),
            }

        peer_ref = validated["peer"]["peer_ref"]
        semantic = dict(validated["semantic"])
        issued_at = validated["issued_at"]

        if semantic.get("to") != peer_ref:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST",
                    "semantic.to must equal peer.peer_ref",
                ),
            }

        try:
            recipient = self.recipients(peer_ref)
            recipient_actor_ref = _normalized_actor_ref(recipient.actor_ref)
            normalized_recipient_binding = dict(recipient.recipient_binding)
        except NoSuchRecipient as exc:
            return {
                "ok": True,
                "result": _typed_refusal("NOT_A_PARTY", str(exc)),
            }
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INTERNAL_ERROR",
                    f"recipient binding normalization failed: {exc}",
                ),
            }
        except Exception as exc:  # noqa: BLE001 — generic typed refusal
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INTERNAL_ERROR",
                    f"recipient resolution failed: {exc}",
                ),
            }

        if recipient_actor_ref["worker_id"] == self.caller.worker_id:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST",
                    "requester and recipient worker_ids must differ",
                ),
            }

        sem_fingerprint_input = {
            "question": semantic["question"],
            "evidence_refs": list(semantic.get("evidence_refs", [])),
            "artifact_revisions": list(semantic.get("artifact_revisions", [])),
        }
        sem_fingerprint = hashlib.sha256(
            json.dumps(
                sem_fingerprint_input, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

        identity_hash = _mint_request_identity(
            caller=self.caller,
            peer_ref=peer_ref,
            semantic_fingerprint=sem_fingerprint,
        )
        consultation_id, message_key = _build_deterministic_ids(identity_hash)

        valid_until = _format_utc_seconds(
            _parse_utc_seconds(issued_at) + _VALID_UNTIL_OFFSET
        )

        requester_actor_ref = {
            "kind": "worker_attempt",
            "job_id": _requester_job_id(self.caller),
            "attempt_id": self.caller.attempt_id,
            "worker_id": self.caller.worker_id,
        }

        (
            requester_actor_digest,
            recipient_actor_digest,
        ) = _correlation_digests(requester_actor_ref, recipient_actor_ref)

        raw_question_frame: dict[str, Any] = {
            "schema": _consultation_schema_for(self.caller.reasoning_surface),
            "message_key": message_key,
            "consultation_id": consultation_id,
            "purpose": "QUESTION",
            "requester_actor_ref": requester_actor_ref,
            "recipient_actor_ref": recipient_actor_ref,
            "recipient_peer_ref": peer_ref,
            "recipient_binding": normalized_recipient_binding,
            "correlation": {
                "parent_fingerprint": "0" * 64,
                "request_message_key": message_key,
                "consultation_id": consultation_id,
                "requester_actor_digest": requester_actor_digest,
                "recipient_actor_digest": recipient_actor_digest,
            },
            "question": semantic["question"],
            "answer": None,
            "evidence_refs": list(semantic.get("evidence_refs", [])),
            "artifact_revisions": list(semantic.get("artifact_revisions", [])),
            "valid_until": valid_until,
            "deadline_ms": _DEFAULT_DEADLINE_MS,
            "response_budget": {
                "max_answers": 1,
                "max_evidence_reads": 4,
                "max_forward_hops": 0,
                "max_payload_bytes": _ANSWER_PAYLOAD_BUDGET_BYTES,
            },
            "supersedes_message_key": None,
            "receipts": {key: None for key in RECEIPT_KEYS},
            "fingerprint": "",
        }
        question_frame = build_consultation(raw_question_frame)

        carrier_ref = f"company-mcp://{consultation_id}"

        try:
            intent_result = self._consultations.intent(
                question_frame,
                requester_attempt_id=self.caller.attempt_id,
                carrier_ref=carrier_ref,
                observed_at=issued_at,
                repository_root=self.repository_root,
            )
        except ConsultationConflict as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "CONFLICT", str(exc) or "intent refused"
                ),
            }
        except StateConflict as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", str(exc) or "intent refused"
                ),
            }

        try:
            wake_state = self._consultations.resolve_restart(question_frame)
        except StateConflict:
            return {
                "ok": True,
                "result": {
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
                "consultation_ref": consultation_id,
                "consultation_id": consultation_id,
                "wake_state": wake_state,
                "deadline": valid_until,
                "intended": intent_result.inserted,
                "is_already_intended": not intent_result.inserted,
                "state": (
                    "ALREADY_INTENDED" if not intent_result.inserted else "INTENDED"
                ),
                "carrier_ref": carrier_ref,
            },
        }

    async def _dispatch_reply(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        raw_semantic = request.get("semantic")
        if not isinstance(raw_semantic, Mapping):
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", "semantic mapping required"
                ),
            }
        semantic = dict(raw_semantic)
        invalid = _validate_reply_semantic(semantic)
        if invalid is not None:
            return {
                "ok": True,
                "result": _typed_refusal("INVALID_REQUEST", invalid),
            }

        consultation_ref = semantic["consultation_ref"]
        intent = _lookup_intent(self.runtime, consultation_ref)
        if intent is None:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "UNAVAILABLE", "no INTENT for consultation_ref"
                ),
            }

        recipient_actor = intent.payload.get("recipient_actor_ref") or {}
        recipient_worker_id = str(recipient_actor.get("worker_id", ""))
        if self.caller.worker_id != recipient_worker_id:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "NOT_A_PARTY",
                    "caller is not the recipient",
                ),
            }

        question_frame = _intent_question_frame(intent)
        answer_frame = _build_answer_frame(
            question_frame,
            answer_text=str(semantic.get("answer", "")),
            evidence_refs=list(semantic.get("evidence_refs", [])),
            supersedes=semantic.get("supersedes_message_key"),
        )

        try:
            question_item = self._consultations._intent_from_event(intent)
            pre_wake_state = self._consultations._canonical_wake_state(
                question_item
            ).value
        except ConsultationConflict as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "CONFLICT",
                    str(exc) or "wake state CONFLICT",
                ),
            }
        except StateConflict as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "WAKE_NOT_ACKNOWLEDGED",
                    str(exc) or "wake state unavailable",
                ),
            }

        if pre_wake_state not in _ACKNOWLEDGED_WAKE_STATES:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "WAKE_NOT_ACKNOWLEDGED",
                    "answer requires canonical TARGET_ACKNOWLEDGED Wake evidence",
                ),
            }

        try:
            answer = self._consultations.answer_available(
                answer_frame, observed_at=self._clock()
            )
        except ConsultationConflict as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "CONFLICT", str(exc) or "answer refused"
                ),
            }
        except StateConflict as exc:
            message = str(exc)
            # Runtime backstop: a TARGET_ACKNOWLEDGED race after the
            # pre-check returned acknowledged is still WAKE_NOT_ACKNOWLEDGED.
            # Any other StateConflict is a deterministic CONFLICT.
            if "TARGET_ACKNOWLEDGED" in message:
                return {
                    "ok": True,
                    "result": _typed_refusal(
                        "WAKE_NOT_ACKNOWLEDGED",
                        "answer requires TARGET_ACKNOWLEDGED Wake evidence",
                    ),
                }
            return {
                "ok": True,
                "result": _typed_refusal(
                    "CONFLICT", message or "answer refused"
                ),
            }

        event = answer.event
        event_type = getattr(event, "event_type", "")
        payload_fact = (
            event.payload.get("fact") if hasattr(event, "payload") else None
        )
        if event_type == "ANSWER_REFUSED" or payload_fact == "ANSWER_REFUSED":
            return {
                "ok": True,
                "result": _typed_refusal(
                    "CONFLICT",
                    str(
                        event.payload.get(
                            "conflict", "answer replay conflict"
                        )
                    )
                    if hasattr(event, "payload")
                    else "answer replay conflict",
                ),
            }

        # Admitted only: cache the exact admitted frame for the requester
        # dispatcher to replay ``consumed_by_requester``.
        if (
            event_type == "ANSWER_AVAILABLE"
            and payload_fact == "ANSWER_AVAILABLE"
            and not bool(event.payload.get("historical", False))
        ):
            self.answer_frames.put(consultation_ref, answer_frame)

        return {
            "ok": True,
            "result": {
                "consultation_ref": consultation_ref,
                "state": "ANSWER_AVAILABLE",
                "answer_fingerprint": event.payload.get(
                    "answer_fingerprint", ""
                ),
                "semantic_answer_digest": event.payload.get(
                    "semantic_answer_digest", ""
                ),
                "historical": bool(event.payload.get("historical", False)),
                "inserted": answer.inserted,
            },
        }

    async def _dispatch_read(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        raw_semantic = request.get("semantic")
        if not isinstance(raw_semantic, Mapping):
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", "semantic mapping required"
                ),
            }
        semantic = dict(raw_semantic)
        invalid = _validate_read_semantic(semantic)
        if invalid is not None:
            return {
                "ok": True,
                "result": _typed_refusal("INVALID_REQUEST", invalid),
            }

        consultation_ref = semantic["consultation_ref"]
        intent = _lookup_intent(self.runtime, consultation_ref)
        if intent is None:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "UNAVAILABLE", "no INTENT for consultation_ref"
                ),
            }
        requester_worker = str(
            (intent.payload.get("requester_actor_ref") or {}).get(
                "worker_id", ""
            )
        )
        recipient_worker = str(
            (intent.payload.get("recipient_actor_ref") or {}).get(
                "worker_id", ""
            )
        )

        if self.caller.worker_id not in (requester_worker, recipient_worker):
            return {
                "ok": True,
                "result": _typed_refusal(
                    "NOT_A_PARTY",
                    "caller is neither requester nor recipient",
                ),
            }
        role = "REQUESTER" if self.caller.worker_id == requester_worker else "RECIPIENT"

        intent_attempt = str(
            (intent.payload.get("requester_actor_ref") or {}).get(
                "attempt_id", ""
            )
        )

        consumed_event = _first_event(
            self.runtime, consultation_ref, "CONSUMED_BY_REQUESTER"
        )

        if (
            role == "REQUESTER"
            and consumed_event is None
            and self._has_answer_available(consultation_ref)
        ):
            answer_frame = self.answer_frames.get(consultation_ref)
            if (
                answer_frame is None
                or intent_attempt != self.caller.attempt_id
            ):
                # No admit-only frame available; never consume and never
                # append a CONSUMED_BY_REQUESTER event. Surface a typed
                # blocker with zero effect.
                row = company_inbox_row(
                    self.runtime,
                    consultation_ref,
                    self.caller.worker_id,
                    self._clock(),
                )
                row = dict(row)
                row["state"] = "ANSWER_AVAILABLE"
                row["wake_state"] = (
                    row.get("wake_state") or "TARGET_ACKNOWLEDGED"
                )
                row["blocker"] = "ANSWER_FRAME_UNAVAILABLE"
                row["owed_turn"] = "REQUESTER"
                return {"ok": True, "result": row}
            try:
                self._consultations.consumed_by_requester(
                    answer_frame,
                    requester_attempt_id=self.caller.attempt_id,
                    observed_at=self._clock(),
                )
            except ConsultationConflict as exc:
                return {
                    "ok": True,
                    "result": _typed_refusal(
                        "CONFLICT", str(exc) or "consumption refused"
                    ),
                }
            except StateConflict as exc:
                return {
                    "ok": True,
                    "result": _typed_refusal(
                        "CONFLICT",
                        str(exc) or "consumption refused",
                    ),
                }

        row = company_inbox_row(
            self.runtime, consultation_ref, self.caller.worker_id, self._clock()
        )
        return {"ok": True, "result": row}

    def _has_answer_available(self, consultation_ref: str) -> bool:
        for event in self.runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=consultation_ref
        ):
            if event.event_type == "ANSWER_AVAILABLE":
                return True
        return False

    def inbox_projection(self, actor_worker_id: str) -> dict[str, Any]:
        """Return the full inbox projection for an actor. Read-only."""
        return project_company_inbox(
            self.runtime, actor_worker_id=actor_worker_id, now=self._clock()
        )


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


def _requester_job_id(caller: CallerIdentity) -> str:
    return caller.job_id


def _correlation_digests(
    requester: Mapping[str, Any], recipient: Mapping[str, Any]
) -> tuple[str, str]:
    return (
        _sha64(dict(requester)),
        _sha64(dict(recipient)),
    )


def _lookup_intent(
    runtime: Runtime, consultation_id: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == "INTENT":
            return event
    return None


def _first_event(
    runtime: Runtime, consultation_id: str, event_type: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == event_type:
            return event
    return None


def _intent_question_frame(intent: Any) -> dict[str, Any]:
    """Rehydrate a QUESTION frame from the persisted INTENT event payload."""
    payload = intent.payload
    artifact_revisions = payload.get("artifact_revisions")
    if not isinstance(artifact_revisions, list):
        artifact_revisions = []
    response_budget = payload.get("response_budget")
    if not isinstance(response_budget, Mapping):
        response_budget = {}
    return {
        "schema": str(payload["consultation_schema"]),
        "message_key": payload["message_key"],
        "consultation_id": payload["consultation_id"],
        "purpose": "QUESTION",
        "requester_actor_ref": dict(payload["requester_actor_ref"]),
        "recipient_actor_ref": dict(payload["recipient_actor_ref"]),
        "recipient_peer_ref": payload["recipient_peer_ref"],
        "recipient_binding": dict(payload["recipient_binding"]),
        "correlation": dict(payload["correlation"]),
        "question": "?",
        "answer": None,
        "evidence_refs": [],
        "artifact_revisions": list(artifact_revisions),
        "valid_until": payload["valid_until"],
        "deadline_ms": int(payload["deadline_ms"]),
        "response_budget": dict(response_budget),
        "supersedes_message_key": None,
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": payload["semantic_fingerprint"],
    }


def _build_answer_frame(
    question_frame: Mapping[str, Any],
    *,
    answer_text: str,
    evidence_refs: list[str],
    supersedes: Any,
) -> dict[str, Any]:
    # The runtime's ``_semantic_answer_digest`` parses the answer's ``text``
    # field as canonical semantic JSON that decodes to a Mapping. Wrap the
    # recipient's raw text into the smallest JSON object that conveys it.
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


__all__ = [
    "AnswerFrameCarrier",
    "CallerIdentity",
    "InMemoryAnswerFrameCarrier",
    "NoSuchRecipient",
    "RecipientBinding",
    "RecipientResolver",
    "RuntimeConsultationDispatcher",
    "ConsultationRefusal",
]

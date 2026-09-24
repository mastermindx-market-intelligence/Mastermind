"""Runtime-backed Company MCP consultation dispatcher.

This joins ``CompanyConsultationGateway`` to ``ConsultationRuntime``. The
dispatcher owns no peer registry and no Runtime lookup of its own — the host
supplies the verified ``CallerIdentity`` (current RuntimeBinding) and the
``recipients`` resolver that maps each trusted ``peer.peer_ref`` to the
recipient's actor ref + ``recipient_binding``.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

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


# Process-scoped cache that mirrors the ANSWER frame minted by the recipient
# dispatcher so the requester dispatcher can replay ``consumed_by_requester``
# against the exact frame the runtime already admitted. The runtime itself
# persists only the answer digests, so this in-process side-channel is the
# only way to re-construct the deterministic answer frame downstream.
_ANSWER_FRAME_CACHE: dict[str, dict[str, Any]] = {}


def _answer_frame_cache_get(key: str) -> dict[str, Any] | None:
    return _ANSWER_FRAME_CACHE.get(key)


def _answer_frame_cache_put(key: str, frame: dict[str, Any]) -> None:
    _ANSWER_FRAME_CACHE[key] = frame


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
    issued_at: str,
) -> str:
    """Deterministic program-scoped consultation identity input."""
    payload = {
        "actor": {
            "worker_id": caller.worker_id,
            "attempt_id": caller.attempt_id,
            "reasoning_surface": caller.reasoning_surface,
        },
        "peer_ref": peer_ref,
        "semantic_fingerprint": semantic_fingerprint,
        "issued_at": issued_at,
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


class RuntimeConsultationDispatcher:
    """Async gateway dispatcher; delegates durable effects to ConsultationRuntime."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        repository_root: Path,
        caller: CallerIdentity,
        recipients: RecipientResolver,
        _clock: ClockFn | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        self.runtime = runtime
        self.repository_root = Path(repository_root).resolve()
        self.caller = caller
        self.recipients = recipients
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
        except NoSuchRecipient as exc:
            return {
                "ok": True,
                "result": _typed_refusal("NOT_A_PARTY", str(exc)),
            }

        recipient_actor_ref = _normalized_actor_ref(recipient.actor_ref)
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
            issued_at=issued_at,
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
            "recipient_binding": dict(recipient.recipient_binding),
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
                "max_payload_bytes": 32768,
            },
            "supersedes_message_key": None,
            "receipts": {key: None for key in RECEIPT_KEYS},
            "fingerprint": "",
        }
        question_frame = build_consultation(raw_question_frame)
        _ANSWER_FRAME_CACHE.pop(consultation_id, None)

        carrier_ref = f"company-mcp://{consultation_id}"

        try:
            intent_result = self._consultations.intent(
                question_frame,
                requester_attempt_id=self.caller.attempt_id,
                carrier_ref=carrier_ref,
                observed_at=issued_at,
                repository_root=self.repository_root,
            )
        except StateConflict as exc:
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", str(exc) or "intent refused"
                ),
            }

        wake_state = self._consultations.resolve_restart(question_frame)
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
        semantic = dict(request.get("semantic", {}))
        consultation_ref = semantic.get("consultation_ref")
        if not isinstance(consultation_ref, str):
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", "consultation_ref required"
                ),
            }

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
        _answer_frame_cache_put(consultation_ref, answer_frame)

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
            # Only map the canonical runtime conflict "answer requires canonical
            # TARGET_ACKNOWLEDGED Wake evidence…"; every other StateConflict
            # is a generic INVALID_REQUEST.
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
                    "INVALID_REQUEST", message or "answer refused"
                ),
            }

        return {
            "ok": True,
            "result": {
                "consultation_ref": consultation_ref,
                "state": "ANSWER_AVAILABLE",
                "answer_fingerprint": answer.event.payload.get(
                    "answer_fingerprint", ""
                ),
                "semantic_answer_digest": answer.event.payload.get(
                    "semantic_answer_digest", ""
                ),
                "historical": bool(answer.event.payload.get("historical", False)),
                "inserted": answer.inserted,
            },
        }

    async def _dispatch_read(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        semantic = dict(request.get("semantic", {}))
        consultation_ref = semantic.get("consultation_ref")
        if not isinstance(consultation_ref, str):
            return {
                "ok": True,
                "result": _typed_refusal(
                    "INVALID_REQUEST", "consultation_ref required"
                ),
            }

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

        row = company_inbox_row(
            self.runtime, consultation_ref, self.caller.worker_id, self._clock()
        )
        state = row.get("state", "RECONCILIATION_REQUIRED")

        consumed_event = _first_event(
            self.runtime, consultation_ref, "CONSUMED_BY_REQUESTER"
        )

        if (
            role == "REQUESTER"
            and state == "ANSWER_AVAILABLE"
            and consumed_event is None
        ):
            answer_frame = _answer_frame_cache_get(consultation_ref)
            if (
                answer_frame is not None
                and intent_attempt == self.caller.attempt_id
            ):
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
                            "INVALID_REQUEST",
                            str(exc) or "consumption refused",
                        ),
                    }
                row = company_inbox_row(
                    self.runtime,
                    consultation_ref,
                    self.caller.worker_id,
                    self._clock(),
                )

        return {"ok": True, "result": row}

    def inbox_projection(self, actor_worker_id: str) -> dict[str, Any]:
        """Return the full inbox projection for an actor. Read-only."""
        return project_company_inbox(
            self.runtime, actor_worker_id=actor_worker_id, now=self._clock()
        )


def _normalized_actor_ref(actor_ref: Mapping[str, Any]) -> dict[str, str]:
    actor = dict(actor_ref)
    return {
        "kind": str(actor.get("kind", "worker_attempt")),
        "job_id": str(actor["job_id"]),
        "attempt_id": str(actor["attempt_id"]),
        "worker_id": str(actor["worker_id"]),
    }


def _requester_job_id(caller: CallerIdentity) -> str:
    return caller.job_id


def _correlation_digests(
    requester: Mapping[str, Any], recipient: Mapping[str, Any]
) -> tuple[str, str]:
    return (
        _sha64(copy.deepcopy(dict(requester))),
        _sha64(copy.deepcopy(dict(recipient))),
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
    return {
        "schema": str(payload["consultation_schema"]),
        "message_key": payload["message_key"],
        "consultation_id": payload["consultation_id"],
        "purpose": "QUESTION",
        "requester_actor_ref": copy.deepcopy(payload["requester_actor_ref"]),
        "recipient_actor_ref": copy.deepcopy(payload["recipient_actor_ref"]),
        "recipient_peer_ref": payload["recipient_peer_ref"],
        "recipient_binding": copy.deepcopy(payload["recipient_binding"]),
        "correlation": copy.deepcopy(payload["correlation"]),
        "question": "?",
        "answer": None,
        "evidence_refs": [],
        "artifact_revisions": copy.deepcopy(payload["artifact_revisions"]),
        "valid_until": payload["valid_until"],
        "deadline_ms": int(payload["deadline_ms"]),
        "response_budget": copy.deepcopy(payload["response_budget"]),
        "supersedes_message_key": None,
        "receipts": {},
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
        "requester_actor_ref": copy.deepcopy(dict(question_frame["requester_actor_ref"])),
        "recipient_actor_ref": copy.deepcopy(dict(question_frame["recipient_actor_ref"])),
        "recipient_peer_ref": question_frame["recipient_peer_ref"],
        "recipient_binding": copy.deepcopy(dict(question_frame["recipient_binding"])),
        "correlation": {
            **copy.deepcopy(dict(question_frame["correlation"])),
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
    "CallerIdentity",
    "NoSuchRecipient",
    "RecipientBinding",
    "RecipientResolver",
    "RuntimeConsultationDispatcher",
    "ConsultationRefusal",
]

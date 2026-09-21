"""Executive-owned at-most-once Workspace Agent trigger effect.

This module closes one narrow effect seam.  It does not create a Workspace queue,
retry ledger, scheduler, budget store, target registry, or result plane.  It reuses
the Executive Runtime events.command_id uniqueness boundary to durably bind one
already-authorized Workspace trigger before provider I/O.

Crash law:
* INTENT + DISPATCH_COMMITTED are written atomically before the POST.
* Once DISPATCH_COMMITTED exists, execute_once never calls the provider again.
* A missing terminal receipt after that commitment projects EFFECT_UNKNOWN.
* A known 202 becomes APPLIED only as provider queue acceptance.
* Known provider rejection becomes REFUSED.
* Transport/malformed/uncertain outcomes become EFFECT_UNKNOWN.
* Candidate return, Wake ACK, company acceptance, and next-child admission remain
  separate owners and are never synthesized here.

The provider token is an ephemeral call argument.  It is never persisted, hashed,
returned, logged, or included in an Executive event.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Callable

from control_plane.executive_runtime import Event, Runtime, StateConflict
from integrations.workspace_agent_api import InvalidObservation, TriggerObservation
from integrations.workspace_agent_trigger import WorkspaceAgentTriggerPlan, trigger_once

EFFECT_SCHEMA = "mastermind.workspace_agent_trigger_effect.v1"
EFFECT_BINDING_SCHEMA = "mastermind.workspace_agent_trigger_effect_binding.v1"
PROVIDER_CONTRACT = "workspace_agent_trigger_accepted_uncorrelated_v1"

_INTENT = "WORKSPACE_AGENT_TRIGGER_INTENT"
_DISPATCH = "WORKSPACE_AGENT_TRIGGER_DISPATCH_COMMITTED"
_APPLIED = "WORKSPACE_AGENT_TRIGGER_APPLIED"
_REFUSED = "WORKSPACE_AGENT_TRIGGER_REFUSED"
_EFFECT_UNKNOWN = "WORKSPACE_AGENT_TRIGGER_EFFECT_UNKNOWN"
_ACTOR = "workspace-agent-trigger"
_AGGREGATE_TYPE = "workspace_agent_trigger"
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_EVENT_REF = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z", re.ASCII)
_OPERATION_KEY = re.compile(r"\A[a-z0-9][a-z0-9-]{2,95}\Z", re.ASCII)
_PROVIDER_REJECTION = re.compile(r"\APROVIDER_REJECTED_[0-9]{3}\Z", re.ASCII)


class WorkspaceTriggerEffectError(RuntimeError):
    """Closed local refusal. Provider prose and secret material never cross it."""

    _CODES = frozenset(
        {
            "INVALID_EFFECT_BINDING",
            "INVALID_TRIGGER_PLAN",
            "EFFECT_EVENT_CONFLICT",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("unknown Workspace trigger effect error")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceTriggerEffectBinding:
    """Safe durable identity supplied by already-owned activation/current-target seams."""

    event_ref: str
    operation_key: str
    activation_digest: str
    current_binding_digest: str
    economic_envelope_digest: str
    package_digest: str

    def normalized(self) -> dict[str, str]:
        values = {
            "event_ref": self.event_ref,
            "operation_key": self.operation_key,
            "activation_digest": self.activation_digest,
            "current_binding_digest": self.current_binding_digest,
            "economic_envelope_digest": self.economic_envelope_digest,
            "package_digest": self.package_digest,
        }
        if (
            _EVENT_REF.fullmatch(values["event_ref"]) is None
            or _OPERATION_KEY.fullmatch(values["operation_key"]) is None
            or any(
                _DIGEST.fullmatch(values[name]) is None
                for name in (
                    "activation_digest",
                    "current_binding_digest",
                    "economic_envelope_digest",
                    "package_digest",
                )
            )
        ):
            raise WorkspaceTriggerEffectError("INVALID_EFFECT_BINDING")
        return {"schema": EFFECT_BINDING_SCHEMA, **values}


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceTriggerEffectOutcome:
    schema: str
    state: str
    reason: str
    event_ref: str
    effect_fingerprint: str
    terminal_command_id: str | None
    provider_request_sent: bool
    replayed: bool
    terminal_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


TriggerCall = Callable[..., TriggerObservation]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise WorkspaceTriggerEffectError("INVALID_EFFECT_BINDING") from None


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _plan_document(plan: WorkspaceAgentTriggerPlan) -> dict[str, str]:
    if type(plan) is not WorkspaceAgentTriggerPlan:
        raise WorkspaceTriggerEffectError("INVALID_TRIGGER_PLAN")
    try:
        plan.__post_init__()
    except InvalidObservation:
        raise WorkspaceTriggerEffectError("INVALID_TRIGGER_PLAN") from None
    except Exception:
        raise WorkspaceTriggerEffectError("INVALID_TRIGGER_PLAN") from None
    return {
        "channel_id": plan.channel_id,
        "operation_key": plan.operation_key,
        "payload_sha256": plan.payload_sha256,
        "idempotency_key": plan.idempotency_key,
        "provider_contract": PROVIDER_CONTRACT,
    }


def _documents(
    binding: WorkspaceTriggerEffectBinding,
    plan: WorkspaceAgentTriggerPlan,
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any], str]:
    bound = binding.normalized()
    planned = _plan_document(plan)
    if bound["operation_key"] != planned["operation_key"]:
        raise WorkspaceTriggerEffectError("INVALID_EFFECT_BINDING")
    effect_fingerprint = _sha(
        {
            "schema": EFFECT_SCHEMA,
            "binding": bound,
            "plan": planned,
        }
    )
    intent = {
        "schema": EFFECT_SCHEMA,
        "phase": "INTENT",
        "effect_fingerprint": effect_fingerprint,
        "binding": bound,
        "plan": planned,
    }
    dispatch = {
        "schema": EFFECT_SCHEMA,
        "phase": "DISPATCH_COMMITTED",
        "event_ref": bound["event_ref"],
        "effect_fingerprint": effect_fingerprint,
        "payload_sha256": planned["payload_sha256"],
        "provider_idempotency_key": planned["idempotency_key"],
    }
    return bound, intent, dispatch, effect_fingerprint


def _command_ids(event_ref: str) -> dict[str, str]:
    base = "workspace-trigger-" + hashlib.sha256(event_ref.encode("ascii")).hexdigest()[:32]
    return {
        "intent": base,
        "dispatch": base + ":dispatch",
        "applied": base + ":applied",
        "refused": base + ":refused",
        "effect_unknown": base + ":effect-unknown",
    }


def _require_event(
    event: Event,
    *,
    event_type: str,
    aggregate_id: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    if (
        not isinstance(event, Event)
        or event.aggregate_type != _AGGREGATE_TYPE
        or event.aggregate_id != aggregate_id
        or event.event_type != event_type
        or event.actor != _ACTOR
        or event.job_id is not None
        or event.attempt_id is not None
        or event.worker_id is not None
        or event.quota_class is not None
        or (payload is not None and event.payload != dict(payload))
    ):
        raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")


def _terminal_payload(
    *,
    event_ref: str,
    effect_fingerprint: str,
    state: str,
    reason: str,
) -> dict[str, str]:
    return {
        "schema": EFFECT_SCHEMA,
        "phase": "TERMINAL",
        "event_ref": event_ref,
        "effect_fingerprint": effect_fingerprint,
        "state": state,
        "reason": reason,
    }


def _terminal_from_events(
    events: Mapping[str, Event | None],
    *,
    event_ref: str,
    effect_fingerprint: str,
) -> tuple[str, str, Event] | None:
    found: list[tuple[str, str, Event]] = []
    specs = (
        ("APPLIED", _APPLIED, "applied"),
        ("REFUSED", _REFUSED, "refused"),
        ("EFFECT_UNKNOWN", _EFFECT_UNKNOWN, "effect_unknown"),
    )
    for state, event_type, key in specs:
        event = events.get(key)
        if event is None:
            continue
        if (
            event.aggregate_type != _AGGREGATE_TYPE
            or event.aggregate_id != event_ref
            or event.event_type != event_type
            or event.actor != _ACTOR
            or event.job_id is not None
            or event.attempt_id is not None
            or event.worker_id is not None
            or event.quota_class is not None
            or not isinstance(event.payload, dict)
            or event.payload.get("schema") != EFFECT_SCHEMA
            or event.payload.get("phase") != "TERMINAL"
            or event.payload.get("event_ref") != event_ref
            or event.payload.get("effect_fingerprint") != effect_fingerprint
            or event.payload.get("state") != state
            or not isinstance(event.payload.get("reason"), str)
        ):
            raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")
        found.append((state, str(event.payload["reason"]), event))
    if len(found) > 1:
        raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")
    return found[0] if found else None


def _outcome(
    *,
    state: str,
    reason: str,
    event_ref: str,
    effect_fingerprint: str,
    terminal_command_id: str | None,
    provider_request_sent: bool,
    replayed: bool,
    terminal_persisted: bool,
) -> WorkspaceTriggerEffectOutcome:
    return WorkspaceTriggerEffectOutcome(
        schema=EFFECT_SCHEMA,
        state=state,
        reason=reason,
        event_ref=event_ref,
        effect_fingerprint=effect_fingerprint,
        terminal_command_id=terminal_command_id,
        provider_request_sent=provider_request_sent,
        replayed=replayed,
        terminal_persisted=terminal_persisted,
    )


class WorkspaceTriggerEffectOwner:
    """One Executive-event-backed external trigger owner; no hidden retry path."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        trigger_call: TriggerCall = trigger_once,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        if not callable(trigger_call):
            raise TypeError("trigger_call must be callable")
        self._runtime = runtime
        self._trigger_call = trigger_call

    def _read_events(self, commands: Mapping[str, str], *, connection=None) -> dict[str, Event | None]:
        return {
            key: self._runtime.store.get_event_by_command_id(
                command_id,
                connection=connection,
            )
            for key, command_id in commands.items()
        }

    def _validate_prefix(
        self,
        events: Mapping[str, Event | None],
        *,
        event_ref: str,
        intent: Mapping[str, Any],
        dispatch: Mapping[str, Any],
    ) -> None:
        intent_event = events["intent"]
        if intent_event is None:
            raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")
        _require_event(
            intent_event,
            event_type=_INTENT,
            aggregate_id=event_ref,
            payload=intent,
        )
        dispatch_event = events["dispatch"]
        if dispatch_event is None:
            raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")
        _require_event(
            dispatch_event,
            event_type=_DISPATCH,
            aggregate_id=event_ref,
            payload=dispatch,
        )

    def reconcile(
        self,
        *,
        binding: WorkspaceTriggerEffectBinding,
        plan: WorkspaceAgentTriggerPlan,
    ) -> WorkspaceTriggerEffectOutcome:
        """Read canonical effect state without provider I/O or mutation."""

        bound, intent, dispatch, fingerprint = _documents(binding, plan)
        commands = _command_ids(bound["event_ref"])
        events = self._read_events(commands)
        if events["intent"] is None:
            if any(value is not None for key, value in events.items() if key != "intent"):
                raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")
            return _outcome(
                state="NOT_STARTED",
                reason="INTENT_NOT_RECORDED",
                event_ref=bound["event_ref"],
                effect_fingerprint=fingerprint,
                terminal_command_id=None,
                provider_request_sent=False,
                replayed=False,
                terminal_persisted=False,
            )

        self._validate_prefix(
            events,
            event_ref=bound["event_ref"],
            intent=intent,
            dispatch=dispatch,
        )
        terminal = _terminal_from_events(
            events,
            event_ref=bound["event_ref"],
            effect_fingerprint=fingerprint,
        )
        if terminal is None:
            return _outcome(
                state="EFFECT_UNKNOWN",
                reason="DISPATCH_COMMITTED_WITHOUT_TERMINAL",
                event_ref=bound["event_ref"],
                effect_fingerprint=fingerprint,
                terminal_command_id=None,
                provider_request_sent=False,
                replayed=True,
                terminal_persisted=False,
            )
        state, reason, event = terminal
        return _outcome(
            state=state,
            reason=reason,
            event_ref=bound["event_ref"],
            effect_fingerprint=fingerprint,
            terminal_command_id=event.command_id,
            provider_request_sent=False,
            replayed=True,
            terminal_persisted=True,
        )

    def execute_once(
        self,
        *,
        binding: WorkspaceTriggerEffectBinding,
        plan: WorkspaceAgentTriggerPlan,
        token: str,
    ) -> WorkspaceTriggerEffectOutcome:
        """Commit dispatch identity, perform at most one POST, then seal outcome."""

        bound, intent, dispatch, fingerprint = _documents(binding, plan)
        event_ref = bound["event_ref"]
        commands = _command_ids(event_ref)

        should_call = False
        with self._runtime.store.transaction() as connection:
            events = self._read_events(commands, connection=connection)
            if events["intent"] is None:
                if any(value is not None for key, value in events.items() if key != "intent"):
                    raise WorkspaceTriggerEffectError("EFFECT_EVENT_CONFLICT")
                timestamp = self._runtime.store.now_ms()
                self._runtime.store.append_event(
                    connection,
                    aggregate_type=_AGGREGATE_TYPE,
                    aggregate_id=event_ref,
                    event_type=_INTENT,
                    actor=_ACTOR,
                    payload=intent,
                    command_id=commands["intent"],
                    timestamp_ms=timestamp,
                )
                self._runtime.store.append_event(
                    connection,
                    aggregate_type=_AGGREGATE_TYPE,
                    aggregate_id=event_ref,
                    event_type=_DISPATCH,
                    actor=_ACTOR,
                    payload=dispatch,
                    command_id=commands["dispatch"],
                    timestamp_ms=timestamp,
                )
                should_call = True
            else:
                self._validate_prefix(
                    events,
                    event_ref=event_ref,
                    intent=intent,
                    dispatch=dispatch,
                )
                terminal = _terminal_from_events(
                    events,
                    event_ref=event_ref,
                    effect_fingerprint=fingerprint,
                )
                if terminal is not None:
                    state, reason, event = terminal
                    return _outcome(
                        state=state,
                        reason=reason,
                        event_ref=event_ref,
                        effect_fingerprint=fingerprint,
                        terminal_command_id=event.command_id,
                        provider_request_sent=False,
                        replayed=True,
                        terminal_persisted=True,
                    )

        if not should_call:
            return _outcome(
                state="EFFECT_UNKNOWN",
                reason="DISPATCH_COMMITTED_WITHOUT_TERMINAL",
                event_ref=event_ref,
                effect_fingerprint=fingerprint,
                terminal_command_id=None,
                provider_request_sent=False,
                replayed=True,
                terminal_persisted=False,
            )

        try:
            observed = self._trigger_call(plan=plan, token=token)
        except InvalidObservation:
            state = "REFUSED"
            reason = "LOCAL_TRIGGER_REFUSED"
        except BaseException:
            state = "EFFECT_UNKNOWN"
            reason = "TRIGGER_EFFECT_UNKNOWN"
        else:
            if (
                isinstance(observed, TriggerObservation)
                and observed.disposition == "accepted"
                and observed.reason == "ACCEPTED_UNCORRELATED"
                and observed.run_id is None
                and observed.conversation_url is None
                and observed.correlation_available is False
            ):
                state = "APPLIED"
                reason = "PROVIDER_ACCEPTED_UNCORRELATED"
            elif (
                isinstance(observed, TriggerObservation)
                and observed.disposition == "rejected"
                and _PROVIDER_REJECTION.fullmatch(observed.reason) is not None
                and observed.run_id is None
                and observed.conversation_url is None
                and observed.correlation_available is False
            ):
                state = "REFUSED"
                reason = observed.reason
            else:
                state = "EFFECT_UNKNOWN"
                reason = "TRIGGER_EFFECT_UNKNOWN"

        command_key = {
            "APPLIED": "applied",
            "REFUSED": "refused",
            "EFFECT_UNKNOWN": "effect_unknown",
        }[state]
        event_type = {
            "APPLIED": _APPLIED,
            "REFUSED": _REFUSED,
            "EFFECT_UNKNOWN": _EFFECT_UNKNOWN,
        }[state]
        terminal_payload = _terminal_payload(
            event_ref=event_ref,
            effect_fingerprint=fingerprint,
            state=state,
            reason=reason,
        )

        with self._runtime.store.transaction() as connection:
            events = self._read_events(commands, connection=connection)
            self._validate_prefix(
                events,
                event_ref=event_ref,
                intent=intent,
                dispatch=dispatch,
            )
            prior = _terminal_from_events(
                events,
                event_ref=event_ref,
                effect_fingerprint=fingerprint,
            )
            if prior is not None:
                prior_state, prior_reason, prior_event = prior
                return _outcome(
                    state=prior_state,
                    reason=prior_reason,
                    event_ref=event_ref,
                    effect_fingerprint=fingerprint,
                    terminal_command_id=prior_event.command_id,
                    provider_request_sent=True,
                    replayed=True,
                    terminal_persisted=True,
                )
            self._runtime.store.append_event(
                connection,
                aggregate_type=_AGGREGATE_TYPE,
                aggregate_id=event_ref,
                event_type=event_type,
                actor=_ACTOR,
                payload=terminal_payload,
                command_id=commands[command_key],
            )

        return _outcome(
            state=state,
            reason=reason,
            event_ref=event_ref,
            effect_fingerprint=fingerprint,
            terminal_command_id=commands[command_key],
            provider_request_sent=True,
            replayed=False,
            terminal_persisted=True,
        )


__all__ = [
    "EFFECT_BINDING_SCHEMA",
    "EFFECT_SCHEMA",
    "PROVIDER_CONTRACT",
    "WorkspaceTriggerEffectBinding",
    "WorkspaceTriggerEffectError",
    "WorkspaceTriggerEffectOutcome",
    "WorkspaceTriggerEffectOwner",
]

"""Pure, fail-closed evidence boundary for the Grok -> ChatGPT Desktop loop.

These are observations and plans, NOT permissions, a queue, a session registry,
a retry journal, or an OperatorHarnessAdapter. Executive/OHF owns reservation,
at-most-once dispatch, admission, effect persistence and recovery. The native
producer must supply authenticated binding context and scoped semantic evidence;
model prose, OCR, a window title or a locally constructed dataclass cannot attest
an account, project, conversation, served model or runtime lease.

No production native producer/actuator is registered by this module. In
particular, do not compose these functions with the legacy global-click/Enter
scripts: those do not satisfy this evidence contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Literal

from control_plane.operator_harness_contract import (
    OperationId, OperationIntentReceipt, OperationIntentTarget, OperationKind,
    OperationResolution, TurnStartObservation,
)

MAX_TEXT_BYTES = 262144
MAX_MESSAGES = 256
MAX_SNAPSHOT_AGE_SECONDS = 5.0
MAX_CLOCK_SKEW_SECONDS = 1.0


class EvidenceError(ValueError):
    """Static reason only; never copy a prompt, transcript or native error."""


def _text(value: object, code: str, *, maximum: int, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise EvidenceError(code)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise EvidenceError(code) from None
    if size > maximum or ('\x00' in value) or (not empty and not value):
        raise EvidenceError(code)
    return value


def _ref(value: object, code: str = 'invalid_reference') -> str:
    result = _text(value, code, maximum=256)
    if result.strip() != result or any(ord(c) < 32 or ord(c) == 127 for c in result):
        raise EvidenceError(code)
    return result


def _positive(value: object, code: str) -> None:
    if type(value) is not int or value <= 0:
        raise EvidenceError(code)


def _clock(value: object) -> float:
    if type(value) not in (int, float):
        raise EvidenceError('invalid_observation_time')
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        raise EvidenceError('invalid_observation_time') from None
    if not math.isfinite(numeric) or numeric <= 0:
        raise EvidenceError('invalid_observation_time')
    return numeric


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class DesktopTarget:
    """Projection of existing RuntimeBinding and exact native target identity."""

    intent_target: OperationIntentTarget
    binding_id: str
    binding_generation: int
    host_ref: str
    seat_ref: str
    project_ref: str
    app_bundle_id: str
    app_version: str
    pid: int
    process_start_ref: str
    window_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.intent_target, OperationIntentTarget):
            raise EvidenceError('missing_runtime_target')
        if self.intent_target.operation_kind != OperationKind.BEGIN_TURN:
            raise EvidenceError('not_a_begin_turn_operation')
        for value in self.intent_target.to_event_payload().values():
            _ref(value)
        for key in ('binding_id', 'host_ref', 'seat_ref', 'project_ref',
                    'app_bundle_id', 'app_version', 'process_start_ref'):
            _ref(getattr(self, key))
        for key in ('binding_generation', 'pid', 'window_id'):
            _positive(getattr(self, key), 'invalid_target_generation')


@dataclass(frozen=True)
class ModeSelection:
    """Exact observed labels. Never interpret 'Latest' as a particular model."""

    surface: Literal['chat', 'work']
    model: str
    effort: Literal['PRO', 'EXTRA_HIGH']

    def __post_init__(self) -> None:
        if self.surface not in ('chat', 'work'):
            raise EvidenceError('invalid_surface')
        if self.effort not in ('PRO', 'EXTRA_HIGH'):
            raise EvidenceError('invalid_effort')
        _ref(self.model, 'invalid_model_label')
        if self.model.casefold() in ('latest', 'auto', 'unknown'):
            raise EvidenceError('model_alias_not_attested')
        # Do not infer that Work is required for Extra High. Product availability
        # and spending eligibility are checked separately by the existing owner.


@dataclass(frozen=True)
class MessageEvidence:
    message_id: str
    role: Literal['user', 'assistant', 'tool', 'system']
    text: str
    complete: bool
    native_turn_id: str | None = None
    reply_to_user_id: str | None = None

    def __post_init__(self) -> None:
        _ref(self.message_id)
        if self.role not in ('user', 'assistant', 'tool', 'system'):
            raise EvidenceError('invalid_message_role')
        _text(self.text, 'invalid_message_text', maximum=MAX_TEXT_BYTES, empty=True)
        if type(self.complete) is not bool:
            raise EvidenceError('invalid_message_completion')
        for value in (self.native_turn_id, self.reply_to_user_id):
            if value is not None:
                _ref(value)


@dataclass(frozen=True)
class DesktopSnapshot:
    """A trusted native projection; all IDs must describe one scoped conversation.

    scope_complete means the operation-relevant message region is complete, not
    that every historical message has been retained. text completeness is separate
    from generation completion. Neither may be inferred from a quiet screen.
    """

    target: DesktopTarget
    snapshot_id: str
    observed_at: float
    source: Literal['semantic', 'ocr', 'unknown']
    scope_complete: bool
    mode: ModeSelection | None
    state: Literal['idle', 'generating', 'failed', 'blocked', 'unknown']
    composer_text: str
    messages: tuple[MessageEvidence, ...]
    block_reason: Literal['none', 'safety', 'permission', 'auth', 'quota', 'transport', 'unknown'] = 'none'

    def __post_init__(self) -> None:
        if not isinstance(self.target, DesktopTarget):
            raise EvidenceError('invalid_snapshot_target')
        _ref(self.snapshot_id)
        _clock(self.observed_at)
        if self.source not in ('semantic', 'ocr', 'unknown'):
            raise EvidenceError('invalid_evidence_source')
        if type(self.scope_complete) is not bool:
            raise EvidenceError('invalid_scope_completion')
        if self.mode is not None and not isinstance(self.mode, ModeSelection):
            raise EvidenceError('invalid_mode_evidence')
        if self.state not in ('idle', 'generating', 'failed', 'blocked', 'unknown'):
            raise EvidenceError('invalid_observed_state')
        if self.block_reason not in ('none', 'safety', 'permission', 'auth', 'quota', 'transport', 'unknown'):
            raise EvidenceError('invalid_block_reason')
        _text(self.composer_text, 'invalid_composer_text', maximum=MAX_TEXT_BYTES, empty=True)
        if not isinstance(self.messages, tuple) or len(self.messages) > MAX_MESSAGES:
            raise EvidenceError('invalid_message_collection')
        if any(not isinstance(m, MessageEvidence) for m in self.messages):
            raise EvidenceError('invalid_message_collection')
        if sum(len(m.text.encode('utf-8')) for m in self.messages) > MAX_TEXT_BYTES * 4:
            raise EvidenceError('snapshot_text_budget_exceeded')
        ids = [m.message_id for m in self.messages]
        if len(set(ids)) != len(ids):
            raise EvidenceError('duplicate_message_identity')

    def content_digest(self) -> str:
        # Snapshot time/id are deliberately excluded. Evidence itself is not.
        data = asdict(self)
        data.pop('snapshot_id')
        data.pop('observed_at')
        return _digest(json.dumps(data, sort_keys=True, separators=(',', ':')))


@dataclass(frozen=True)
class PreparedTurn:
    """Non-authoritative prepared payload for an existing OHF begin-turn INTENT."""

    intent: OperationIntentReceipt
    target: DesktopTarget
    requested_mode: ModeSelection
    wire_text: str
    before_snapshot_id: str
    before_digest: str
    before_message_ids: tuple[str, ...]
    prepared_at: float

    def __post_init__(self) -> None:
        if (not isinstance(self.intent, OperationIntentReceipt)
                or not isinstance(self.intent.operation_id, OperationId)
                or not isinstance(self.target, DesktopTarget)
                or self.intent.target != self.target.intent_target
                or not isinstance(self.requested_mode, ModeSelection)):
            raise EvidenceError('invalid_prepared_turn')
        _text(self.wire_text, 'invalid_prepared_payload', maximum=MAX_TEXT_BYTES)
        if not self.wire_text.startswith('MMX_TURN:' + _digest(self.intent.command_id) + '\n'):
            raise EvidenceError('prepared_operation_marker_mismatch')
        _ref(self.before_snapshot_id)
        if not isinstance(self.before_digest, str) or re.fullmatch('[0-9a-f]{64}', self.before_digest) is None:
            raise EvidenceError('invalid_preimage_digest')
        if not isinstance(self.before_message_ids, tuple) or len(self.before_message_ids) > MAX_MESSAGES:
            raise EvidenceError('invalid_preimage_messages')
        for value in self.before_message_ids:
            _ref(value)
        if len(set(self.before_message_ids)) != len(self.before_message_ids):
            raise EvidenceError('invalid_preimage_messages')
        _clock(self.prepared_at)

    @property
    def payload_digest(self) -> str:
        return _digest(json.dumps({
            'intent': self.intent.target.to_event_payload(),
            'operation_id': self.intent.command_id,
            'target': asdict(self.target),
            'mode': asdict(self.requested_mode),
            'wire_text_sha256': _digest(self.wire_text),
        }, sort_keys=True, separators=(',', ':')))


def _validate_snapshot(target: DesktopTarget, snapshot: DesktopSnapshot, now: float) -> None:
    if not isinstance(snapshot, DesktopSnapshot):
        raise EvidenceError('snapshot_unavailable')
    if snapshot.target != target:
        raise EvidenceError('exact_target_mismatch')
    age = _clock(now) - _clock(snapshot.observed_at)
    if age > MAX_SNAPSHOT_AGE_SECONDS or age < -MAX_CLOCK_SKEW_SECONDS:
        raise EvidenceError('stale_or_future_snapshot')
    if snapshot.source != 'semantic' or snapshot.scope_complete is not True:
        raise EvidenceError('insufficient_semantic_evidence')


def prepare_turn(*, intent: OperationIntentReceipt, target: DesktopTarget,
                 requested_mode: ModeSelection, prompt: str,
                 snapshot: DesktopSnapshot, now: float,
                 allowed_surfaces: frozenset[str] = frozenset({'chat'})) -> PreparedTurn:
    """Prepare, never reserve or dispatch. Native/runtime admission is still owed."""
    if (not isinstance(intent, OperationIntentReceipt)
            or not isinstance(intent.operation_id, OperationId)
            or not isinstance(target, DesktopTarget)
            or intent.target != target.intent_target):
        raise EvidenceError('intent_target_mismatch')
    if not isinstance(requested_mode, ModeSelection):
        raise EvidenceError('invalid_requested_mode')
    # Projection of the existing owner's scope/spending envelope, not a new
    # permission grant. Never expose this argument as a model-selected override.
    if (not isinstance(allowed_surfaces, frozenset) or not allowed_surfaces
            or not allowed_surfaces <= {'chat', 'work'}):
        raise EvidenceError('invalid_surface_envelope')
    if requested_mode.surface not in allowed_surfaces:
        raise EvidenceError('surface_not_in_admitted_envelope')
    _validate_snapshot(target, snapshot, now)
    if snapshot.block_reason != 'none' or snapshot.state != 'idle':
        raise EvidenceError('surface_not_ready')
    if snapshot.composer_text:
        raise EvidenceError('existing_composer_draft')
    if snapshot.mode != requested_mode:
        raise EvidenceError('mode_not_verified')
    _text(prompt, 'invalid_prompt', maximum=MAX_TEXT_BYTES - 100)
    marker = 'MMX_TURN:' + _digest(intent.command_id)
    wire_text = marker + '\n' + prompt
    if any(m.role == 'user' and m.text.startswith(marker + '\n') for m in snapshot.messages):
        raise EvidenceError('operation_already_visible')
    return PreparedTurn(intent, target, requested_mode, wire_text,
                        snapshot.snapshot_id, snapshot.content_digest(),
                        tuple(m.message_id for m in snapshot.messages), float(now))


def verify_pre_dispatch(plan: PreparedTurn, snapshot: DesktopSnapshot, *, now: float) -> None:
    """Second read immediately before the owner-approved native effect boundary.

    Success is an observation check, NOT a reusable dispatch token. The existing
    runtime must own the exclusive writer and durable at-most-once operation gate.
    """
    _validate_snapshot(plan.target, snapshot, now)
    if snapshot.snapshot_id == plan.before_snapshot_id or snapshot.observed_at < plan.prepared_at:
        raise EvidenceError('fresh_pre_dispatch_observation_required')
    if _clock(now) - _clock(plan.prepared_at) > MAX_SNAPSHOT_AGE_SECONDS:
        raise EvidenceError('prepared_turn_expired')
    if now < plan.prepared_at - MAX_CLOCK_SKEW_SECONDS:
        raise EvidenceError('prepared_turn_in_future')
    if snapshot.content_digest() != plan.before_digest:
        raise EvidenceError('pre_dispatch_state_changed')


@dataclass(frozen=True)
class TurnObservation:
    """Input effect and answer observation are deliberately separate axes."""

    input_effect: OperationResolution
    response_state: Literal['not_observed', 'active', 'complete', 'error', 'ambiguous']
    reason: str
    provider_native_turn_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    response_text: str | None = None
    requested_next_mode: str | None = None
    served_model: str = 'UNKNOWN'

    def as_turn_start(self) -> TurnStartObservation:
        return TurnStartObservation(
            provider_native_turn_id=self.provider_native_turn_id,
            acknowledged=self.input_effect == OperationResolution.APPLIED,
        )


def _mode_advice(text: str) -> str | None:
    # A completed assistant's terminal line is advice only. Do not scan quoted
    # history, tools, partial output, error banners, or arbitrary message text.
    lines = text.rstrip().splitlines()
    if not lines:
        return None
    fence = None
    for line in lines[:-1]:
        match = re.match(r'^[ ]{0,3}(`{3,}|~{3,})(.*)$', line)
        if match:
            token, suffix = match.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not suffix.strip():
                fence = None
    if fence is not None:
        return None
    return {'REQUEST_MODE: PRO': 'PRO',
            'REQUEST_MODE: EXTRA_HIGH': 'EXTRA_HIGH'}.get(lines[-1])


def reconcile_turn(plan: PreparedTurn, snapshot: DesktopSnapshot | None, *, now: float) -> TurnObservation:
    """Read-only reducer after possible dispatch. NEVER says absent == not sent.

    The original OHF operation must be retained on missing, stale, truncated or
    mismatched evidence. No retry, host/mode switch or replacement chat follows
    from any result of this function. A verified bubble proves input, not worker
    pickup, execution completion, mission acceptance or permission to continue.
    """
    unknown = OperationResolution.EFFECT_UNKNOWN
    try:
        _validate_snapshot(plan.target, snapshot, now)  # type: ignore[arg-type]
    except EvidenceError as exc:
        return TurnObservation(unknown, 'not_observed', str(exc))
    assert snapshot is not None
    if snapshot.snapshot_id == plan.before_snapshot_id or snapshot.observed_at < plan.prepared_at:
        return TurnObservation(unknown, 'not_observed', 'pre_dispatch_observation_reused')
    if snapshot.mode != plan.requested_mode:
        return TurnObservation(unknown, 'not_observed', 'mode_drift_after_dispatch')
    marker = plan.wire_text.split('\n', 1)[0] + '\n'
    users = [m for m in snapshot.messages if m.role == 'user' and m.text.startswith(marker)
             and m.message_id not in plan.before_message_ids]
    if len(users) != 1:
        reason = 'duplicate_operation_messages' if users else 'input_not_confirmed'
        return TurnObservation(unknown, 'ambiguous' if users else 'not_observed', reason)
    user = users[0]
    if not user.complete or user.text != plan.wire_text or not user.native_turn_id:
        return TurnObservation(unknown, 'not_observed', 'input_payload_not_verified')
    applied = OperationResolution.APPLIED
    common = {'provider_native_turn_id': user.native_turn_id, 'user_message_id': user.message_id}
    # Once input is confirmed, a safety/permission/quota failure does not erase it.
    if snapshot.block_reason != 'none' or snapshot.state in ('blocked', 'failed'):
        return TurnObservation(applied, 'error', 'provider_surface_blocked', **common)
    replies = [m for m in snapshot.messages if m.role == 'assistant'
               and m.reply_to_user_id == user.message_id]
    if len(replies) > 1:
        return TurnObservation(applied, 'ambiguous', 'multiple_assistant_branches', **common)
    if not replies:
        return TurnObservation(applied, 'active', 'assistant_not_observed', **common)
    reply = replies[0]
    if (reply.message_id in plan.before_message_ids
            or snapshot.messages.index(reply) < snapshot.messages.index(user)):
        return TurnObservation(applied, 'ambiguous', 'assistant_order_or_identity_mismatch', **common)
    if reply.native_turn_id != user.native_turn_id:
        return TurnObservation(applied, 'ambiguous', 'native_turn_mismatch', **common)
    if not reply.complete or snapshot.state != 'idle' or not reply.text.strip():
        return TurnObservation(applied, 'active', 'response_not_complete', **common)
    return TurnObservation(applied, 'complete', 'exact_response_captured',
                           assistant_message_id=reply.message_id, response_text=reply.text,
                           requested_next_mode=_mode_advice(reply.text), **common)

"""Private normal-Supervisor OCR-3 composition; no provider or lifecycle owner.

The first supported input is one plain UTF-8 text request without a resource or
skill suffix. A completed native turn plus exact retained input establishes the
capsule-specific ACK threshold. It does not establish model use, useful action,
Job completion, or consumption by the original parent.
"""
from __future__ import annotations

import dataclasses
import hashlib

from control_plane.executive_runtime import (
    AttemptLease, Runtime, StateConflict, _dialogue_source_from_root_creation,
    _strict_canonical_json_loads, _job_from_row, orchestration_digest,
)
from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.operator_continuation import (
    ContinuationAck, MAX_CAPSULE_BYTES, OPERATION_KEY_RE,
    OPERATOR_CONTINUATION_ACK_SCHEMA,
)
from control_plane.operator_continuation_sources import (
    ContinuationExternalRefs, build_current_continuation_draft,
)
from control_plane.operator_harness_contract import OperationId
from control_plane.operator_harness_orchestrator import OperatorTurnReceipt
from control_plane.operator_harness_wire import (
    CONTINUATION_OPERATION_PREFIX, retained_plain_input_evidence, to_wire,
)
from control_plane.codex_operator_adapter import (
    CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST,
    CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
)
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import load_session_targets


_ALIAS = "EXECUTIVE-COO-CODEX-A"
_MAX_RENDER_BYTES = 512 * 1024
_HEADER = "\n\nExecutive immutable continuation capsule (canonical JSON):\n"
_FOOTER = "\nContinue the bounded next action under the existing commission and grant.\n"


def _placement(attempt):
    value = attempt.placement_snapshot
    if (type(value) is not dict or orchestration_digest(value) != attempt.placement_snapshot_digest
            or value.get("worker_id") != attempt.worker_id
            or value.get("quota_class") != attempt.quota_class
            or any(type(value.get(k)) is not str or not value[k]
                   for k in ("provider", "account_label"))):
        raise StateConflict("continuation placement is not immutable admitted material")
    return value["provider"], value["account_label"]


def _source_snapshot(runtime, job, commission):
    if commission is None:
        raise StateConflict("cross-realm continuation requires an immutable commission")
    with runtime.store.read() as connection:
        source = _dialogue_source_from_root_creation(connection, root_job_id=job.root_job_id)
        root_row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job.root_job_id,)).fetchone()
        root = None if root_row is None else _job_from_row(root_row)
        rows = connection.execute(
            "SELECT * FROM events WHERE event_type='JOB_CREATED' AND job_id=? LIMIT 2",
            (job.root_job_id,),
        ).fetchall()
        if source is None or root is None or len(rows) != 1:
            raise StateConflict("continuation has no exact original root source")
        row = rows[0]
        payload = _strict_canonical_json_loads(row["payload_json"], name="continuation root creation")
        provenance = root.orchestration_provenance
        operation = provenance.get("source_id") if type(provenance) is dict else None
        if (type(operation) is not str or OPERATION_KEY_RE.fullmatch(operation) is None
                or payload.get("provenance", {}).get("intent_id") != operation
                or payload.get("orchestration_provenance_digest") != root.orchestration_provenance_digest
                or orchestration_digest(provenance) != root.orchestration_provenance_digest
                or source.commission_ref.to_dict() != commission.ref_dict()
                or hashlib.sha256(commission.content).hexdigest() != commission.content_sha256):
            raise StateConflict("continuation original operation or commission source drifted")
        return source, operation, (row["event_id"], row["payload_json"], root.orchestration_provenance_digest)


def _target():
    target = load_session_targets().get(_ALIAS)
    if (target.target_seat != "coo" or target.reasoning_surface != "codex"
            or target.wake_transport != "codex-app-server"
            or target.allowed_transports != ("codex-app-server",)):
        raise StateConflict("continuation logical target declaration is incompatible")
    return target


def _predecessor(runtime, expected):
    attempt = runtime.attempts.get_attempt(expected.attempt_id)
    if attempt is None or attempt.attempt_number != expected.attempt_number:
        raise StateConflict("continuation target Attempt disappeared")
    if attempt.attempt_number == 1:
        return None
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT attempt_id FROM attempts WHERE job_id=? AND attempt_number=? LIMIT 2",
            (attempt.job_id, attempt.attempt_number - 1),
        ).fetchall()
    if len(rows) != 1:
        raise StateConflict("continuation requires one adjacent predecessor")
    previous = runtime.attempts.get_attempt(rows[0]["attempt_id"])
    if previous is None:
        raise StateConflict("continuation predecessor disappeared")
    return None if _placement(previous) == _placement(attempt) else previous


@dataclasses.dataclass
class _ContinuationDelivery:
    runtime: Runtime = dataclasses.field(repr=False)
    lease: AttemptLease = dataclasses.field(repr=False)
    job: object = dataclasses.field(repr=False)
    commission: object = dataclasses.field(repr=False)
    source_attempt_id: str
    refs: ContinuationExternalRefs = dataclasses.field(repr=False)
    source_snapshot: tuple = dataclasses.field(repr=False)
    target_snapshot: dict = dataclasses.field(repr=False)
    base_prompt: str = dataclasses.field(repr=False)
    capsule: object = dataclasses.field(default=None, repr=False)
    rendered: str | None = dataclasses.field(default=None, repr=False)
    callback_attempted: bool = False

    @property
    def operation(self):
        return OperationId(CONTINUATION_OPERATION_PREFIX + self.lease.attempt.attempt_id)

    def _recheck_sources(self):
        source, operation, snapshot = _source_snapshot(self.runtime, self.job, self.commission)
        if (snapshot != self.source_snapshot or operation != self.refs.operation_key
                or _target().to_dict() != self.target_snapshot):
            raise StateConflict("continuation source or target declaration changed")
        return source

    def prepare(self, session):
        self._recheck_sources()
        target = _target()
        facts = self.runtime.current_harness_binding_source(self.lease.attempt.attempt_id)
        binding = project_runtime_binding(self.runtime, facts.attempt_id, target)
        if (facts.session_epoch_id != session.epoch.session_epoch_id
                or facts.process_generation_id != session.generation.process_generation_id
                or binding.native_handle != facts.provider_session_id
                or session.observed.effective_skills):
            raise StateConflict("continuation target binding or input shape is unsupported")
        draft = build_current_continuation_draft(self.runtime,
            source_attempt_id=self.source_attempt_id,
            target_attempt_id=self.lease.attempt.attempt_id, refs=self.refs)
        self.capsule = ExecutiveOperatorHarnessPort(self.runtime, self.lease).prepare_operator_continuation(
            self.lease.attempt.attempt_id, draft)
        self.rendered = self.base_prompt + _HEADER + self.capsule.canonical_bytes().decode("utf-8") + _FOOTER
        return self.rendered

    def consume_before_seal(self, receipt, raw, adapter, session):
        # A lost callback reply must never cause another ACK attempt or turn.
        if self.callback_attempted:
            raise StateConflict("continuation validation was already attempted")
        self.callback_attempted = True
        self._recheck_sources()
        if type(receipt) is not OperatorTurnReceipt or type(raw) is not RawRoleResultObservation:
            raise StateConflict("continuation requires typed native result observations")
        if self.capsule is None or self.rendered is None:
            raise StateConflict("continuation has no privately prepared render")
        turn = receipt.turn
        keys = ("attempt_id", "session_epoch_id", "process_generation_id", "turn_id")
        raw = RawRoleResultObservation(**raw.to_dict())
        if (turn.attempt_id != self.lease.attempt.attempt_id
                or turn.session_epoch_id != session.epoch.session_epoch_id
                or turn.process_generation_id != session.generation.process_generation_id
                or receipt.start.acknowledged is not True
                or type(receipt.start.provider_native_turn_id) is not str
                or not receipt.start.provider_native_turn_id
                or any(getattr(raw, k) != getattr(turn, k) for k in keys)
                or raw.provider_session_id != session.observation.provider_session_id
                or raw.provider_native_turn_id != receipt.start.provider_native_turn_id
                or raw.provider_turn_artifact_digest != receipt.candidate.artifact_digest):
            raise StateConflict("continuation completed candidate is not the exact native turn")
        completed = [e for e in receipt.events if e.kind == "turn/completed"
                     and e.native_subordinate_id is None]
        if (len(completed) != 1
                or any(getattr(completed[0], k) != getattr(turn, k) for k in keys)
                or completed[0].provider_event_id != receipt.start.provider_native_turn_id):
            raise StateConflict("continuation requires one genuine parent native completion")
        collector = getattr(adapter, "collect_retained_plain_text_evidence", None)
        if not callable(collector):
            raise StateConflict("continuation adapter has no qualified retained-input reader")
        proof = retained_plain_input_evidence(to_wire(collector(turn)))
        rendered = self.rendered.encode("utf-8", errors="strict")
        if (any(getattr(proof, k) != getattr(turn, k) for k in keys)
                or proof.provider_session_id != raw.provider_session_id
                or proof.provider_native_turn_id != raw.provider_native_turn_id
                or proof.retained_input_digest != hashlib.sha256(rendered).hexdigest()
                or proof.retained_input_byte_length != len(rendered)):
            raise StateConflict("continuation retained input differs from the exact trusted capsule render")
        self._recheck_sources()  # The native read can block; source drift is not acceptance.
        ack = ContinuationAck(OPERATOR_CONTINUATION_ACK_SCHEMA, turn.attempt_id,
            self.capsule.capsule_id, raw.provider_session_id, True)
        port = ExecutiveOperatorHarnessPort(self.runtime, self.lease)
        try:
            port.acknowledge_operator_continuation(turn.attempt_id, ack)
        except Exception:
            # Same-operation readback only. No callback/ACK/dispatch replay.
            with self.runtime.store.read() as connection:
                self.runtime._continuation_current_facts(connection,
                    attempt_id=turn.attempt_id, fence_generation=port.fence_generation,
                    lease_token=port.lease_token, draft=self.capsule.draft)
                facts = self.runtime.current_harness_binding_source(turn.attempt_id, connection=connection)
                prepared = self.runtime._continuation_event(connection,
                    command_id=f"operator-continuation:prepare:{turn.attempt_id}",
                    event_type="OPERATOR_CONTINUATION_PREPARED", facts=facts)
                row = self.runtime._continuation_event(connection,
                    command_id=f"operator-continuation:ack:{turn.attempt_id}",
                    event_type="OPERATOR_CONTINUATION_ACKNOWLEDGED", facts=facts)
                expected = {"schema_version": "mastermind.operator_continuation_acknowledged/v1",
                    "prepared_command_id": f"operator-continuation:prepare:{turn.attempt_id}",
                    "session_epoch_id": facts.session_epoch_id, "ack": ack.to_dict()}
                if (prepared is None or row is None or row["event_id"] <= prepared["event_id"]
                        or self.runtime._continuation_from_event(prepared, facts) != self.capsule
                        or _strict_canonical_json_loads(row["payload_json"], name="continuation ACK") != expected):
                    raise StateConflict("continuation ACK response is unresolved; same operation held") from None


def _continuation_for_claim(runtime, job, lease, requested, commission, base_prompt):
    previous = _predecessor(runtime, lease.attempt)
    if previous is None:
        return None
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    profile = ExecutionCapabilityRegistry.load().resolve(job.constraints.get("execution_profile_id", ""))
    if (requested.provider != "openai-codex" or requested.harness_kind != "codex-app-server"
            or requested.harness_version != CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION
            or requested.harness_binary_digest != CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST
            or profile.skill_grants or profile.resource_grants or profile.skills
            or type(base_prompt) is not str or not base_prompt.strip()
            or len(base_prompt.encode("utf-8", errors="strict")) + MAX_CAPSULE_BYTES
                 + len((_HEADER + _FOOTER).encode()) > _MAX_RENDER_BYTES):
        raise StateConflict("cross-realm continuation input/build is UNSUPPORTED before PREPARE")
    source, operation, snapshot = _source_snapshot(runtime, job, commission)
    target = _target()
    ref = source.commission_ref
    refs = ContinuationExternalRefs(operation, target.target_seat, target.session_alias,
        (f"https://github.com/{ref.repository}/blob/{ref.commit}/{ref.path}",),
        (source.work_ref,), {"repository": ref.repository, "head_sha": ref.commit,
            "path": ref.path, "content_sha256": ref.content_sha256}, None, (),
        {"mastermind": ref.commit})
    # No provider session is started for an already-known unsafe predecessor.
    with runtime.store.read() as connection:
        rows = connection.execute("""SELECT g.ended_at_ms,g.executive_writer_held,g.provider_writer_state
            FROM process_generations g JOIN harness_session_epochs e USING(session_epoch_id)
            WHERE e.attempt_id=?""", (previous.attempt_id,)).fetchall()
        if (not rows or any(r["ended_at_ms"] is None or r["executive_writer_held"] != 0
                or r["provider_writer_state"] != "RELEASED" for r in rows)
                or connection.execute("""SELECT 1 FROM events WHERE
                    event_type='OPERATOR_OPERATION_EFFECT_UNKNOWN' AND attempt_id IN (?,?) LIMIT 1""",
                    (previous.attempt_id, lease.attempt.attempt_id)).fetchone() is not None):
            raise StateConflict("continuation predecessor or original operation remains held")
    build_current_continuation_draft(runtime, source_attempt_id=previous.attempt_id,
        target_attempt_id=lease.attempt.attempt_id, refs=refs)
    return _ContinuationDelivery(runtime, lease, job, commission, previous.attempt_id,
        refs, snapshot, target.to_dict(), base_prompt)


def _continuation_recovery_held(runtime, attempt):
    """No recovery can reconstruct ephemeral trusted delivery proof by resending.

    Cancellation remains the existing owner's containment path. A later source
    milestone may add same-operation proof recovery; this slice does not.
    """
    if runtime.events.get_event_by_command_id(f"operator-continuation:prepare:{attempt.attempt_id}") is not None:
        return True
    return _predecessor(runtime, attempt) is not None

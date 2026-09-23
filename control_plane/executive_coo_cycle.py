"""Deterministic, production-inert Phase 1F-C COO run-once bookkeeping.

The cycle owns no durable state and performs at most one top-level mutation.
Every write delegates to the existing Executive Runtime command boundaries.
It never polls, selects a parent, invokes a model, or contacts a provider.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from control_plane.executive_authority import (
    AuthorityPolicyError,
    ExecutiveAuthorityPolicy,
)
from control_plane.executive_coo_policy import (
    CooCyclePolicy,
    CooCyclePolicyError,
    EXPECTED_POLICY_SHA256,
)
from control_plane.executive_runtime import (
    COO_CYCLE_BLOCK_REASONS,
    FINITE_CONTROL_STABLE_PIN_KEYS,
    AttemptStatus,
    FiniteControlContext,
    FiniteReservationDecision,
    Job,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    WorkerStatus,
    _current_orchestration_tree_material,
    _current_orchestration_tree_material_for_dispatch,
    _review_attempt_is_independent,
    _validated_aggregation_handoff,
    _validated_plan_admission,
    _validated_role_completion_material,
    finite_host_binding_digest,
)

FINITE_CUTOFF_SCHEMA = "mastermind.executive_coo_finite_cutoff/v1"

CYCLE_OUTCOME_SCHEMA = "mastermind.executive_coo_cycle_outcome/v1"
_ROLE_PRECEDENCE = {"plan": 0, "work": 1, "repair": 2, "review": 3, "aggregation": 4}
_RECOVERABLE = {JobStatus.RATE_LIMITED, JobStatus.FAILED, JobStatus.LOST}

Dispatch = Callable[[str, str], OrchestrationDispatchOutcome | None]


@dataclasses.dataclass(frozen=True)
class CooCycleOutcome:
    root_job_id: str
    action: str
    selected_job_id: str | None
    command_id: str | None
    receipt: dict[str, Any]
    schema_version: str = CYCLE_OUTCOME_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        value["outcome_digest"] = hashlib.sha256(encoded).hexdigest()
        return value


def _job_sort_key(job: Job, ordinals: Mapping[str, int]) -> tuple[int, int, int, str]:
    ordinal = -1 if job.plan_step_id is None else int(ordinals.get(job.plan_step_id, 1 << 30))
    return (
        _ROLE_PRECEDENCE.get(str(job.orchestration_role), 99),
        ordinal,
        int(job.repair_round or 0),
        job.job_id,
    )


@dataclasses.dataclass(frozen=True)
class FiniteControlGate:
    """Advisory finite-control facts established for one root, once per cycle.

    ``None`` from :meth:`CooCycle._finite_control_gate` means the root is
    outside every finite control composition: no durable arm and no owner
    context bound to it.  Such a root keeps its exact legacy behaviour.

    ``context_proven`` with an undrifted current policy pin set are the only
    facts that let ``already_issued`` from ``validate_finite_first_issuance``
    support an incumbent settlement.  The advisory read reports
    ``already_issued`` from persisted Attempt evidence alone and returns
    before it ever re-reads the bound context, the durable arm, or the
    persisted host pin, so that flag by itself proves only "this Attempt was
    launched".  It never proves which root, which composition, or which
    currently governing policies the launch belonged to.
    """

    root_job_id: str
    armed: bool
    bound: bool
    context_proven: bool
    halt: bool
    halt_reason: str | None
    expired: bool
    exhausted: bool
    spent: int
    remaining: int
    current_policy_pin_drift: bool
    refusal_reasons: tuple[str, ...] = ()
    status: dict[str, Any] | None = None
    definition: dict[str, Any] | None = None


def _classify_invalid(exc: Exception) -> str:
    text = str(exc).lower()
    if "policy" in text:
        return "invalid_policy"
    if "fan-out" in text or "fan out" in text:
        return "fan_out_exceeded"
    if "reserved child" in text or "child total" in text:
        return "children_total_exceeded"
    if "capacity" in text or "reservation exceeds" in text:
        return "plan_capacity_exceeded"
    if "depth" in text or "non-direct child" in text:
        return "depth_exceeded"
    if "validation" in text:
        return "validation_contract_invalid"
    if "grant" in text or "authority" in text:
        return "effective_grant_invalid"
    if "principal" in text or "placement" in text:
        return "principal_snapshot_invalid"
    if any(word in text for word in ("result", "seal", "terminal evidence", "envelope")):
        return "result_protocol_invalid"
    if "plan" in text and "lineage" not in text:
        return "invalid_plan"
    if "handoff" in text:
        return "aggregation_handoff_invalid"
    if "lineage" in text or "revision" in text or "unexpected child" in text:
        return "lineage_invalid"
    return "state_conflict"


class CooCycle:
    """Choose and commit the first eligible mutation for one explicit root."""

    def __init__(self, runtime: Runtime, *, dispatcher: Dispatch | None = None) -> None:
        self.runtime = runtime
        self._uses_inert_dispatcher = dispatcher is None
        self.dispatcher = dispatcher or self._dispatch_unavailable

    @staticmethod
    def _dispatch_unavailable(
        job_id: str, command_id: str
    ) -> OrchestrationDispatchOutcome | None:
        """The inert CLI has no accepted supervisor execution boundary."""

        return None

    def _outcome(
        self,
        root: str,
        action: str,
        selected: str | None,
        command: str | None,
        receipt: Any,
    ) -> CooCycleOutcome:
        if hasattr(receipt, "to_dict"):
            receipt = receipt.to_dict()
        elif dataclasses.is_dataclass(receipt):
            receipt = dataclasses.asdict(receipt)
        elif not isinstance(receipt, dict):
            receipt = {"value": receipt}
        return CooCycleOutcome(root, action, selected, command, dict(receipt))

    def _dispatch_none_was_preclaim(self, before: Job) -> bool:
        """True only when a ``None`` dispatcher result left the Job untouched."""

        after = self.runtime.jobs.get_job(before.job_id)
        return bool(
            after is not None
            and after.status == before.status
            and after.attempt_count == before.attempt_count
            and after.current_attempt_id == before.current_attempt_id
        )

    @staticmethod
    def _is_read_only_frontier_work(job: Job) -> bool:
        """Return whether one current work revision is safe for bounded overlap."""

        return bool(
            job.orchestration_role == "work"
            and job.requested_authorities == ["READ"]
            and not job.allowed_write_paths
            and not job.validation_commands
            and job.plan_attempt_id
            and job.plan_digest
            and job.plan_step_id
            and int(job.repair_round or 0) == 0
            and job.supersedes_job_id is None
        )

    def _active_attempt_is_current_and_live(self, job: Job) -> bool:
        """Fail closed unless Runtime still owns an exact unexpired active Attempt."""

        if job.attempt_count < 1 or not job.current_attempt_id:
            return False
        attempt = self.runtime.attempts.get_attempt(job.current_attempt_id)
        if attempt is None or attempt.job_id != job.job_id:
            return False
        if attempt.attempt_number != job.attempt_count or not attempt.lease_owner:
            return False
        expected_job_status = {
            AttemptStatus.CLAIMED: JobStatus.RUNNING,
            AttemptStatus.RUNNING: JobStatus.RUNNING,
            AttemptStatus.CHECKPOINTED: JobStatus.CHECKPOINTED,
        }.get(attempt.status)
        if expected_job_status is None or job.status is not expected_job_status:
            return False
        if (
            job.assigned_worker_id != attempt.worker_id
            or job.assigned_quota_class != attempt.quota_class
        ):
            return False
        quota = self.runtime.workers.get_quota_class(
            attempt.worker_id, attempt.quota_class
        )
        if (
            quota is None
            or quota.status is not WorkerStatus.BUSY
            or quota.active_attempt_id != attempt.attempt_id
            or quota.active_job_id != job.job_id
            or quota.fence_generation != attempt.fence_generation
        ):
            return False
        with self.runtime.store.read() as connection:
            row = connection.execute(
                "SELECT lease_token,lease_expires_at_ms FROM attempts WHERE attempt_id=?",
                (attempt.attempt_id,),
            ).fetchone()
        return bool(
            row is not None
            and row["lease_token"] is not None
            and int(row["lease_expires_at_ms"]) > self.runtime.store.now_ms()
        )

    @classmethod
    def _ready_frontier_open(
        cls,
        active: list[Job],
        queued: list[Job],
        current_by_step: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        if not active or not queued:
            return False
        for job in [*active, *queued]:
            if not cls._is_read_only_frontier_work(job):
                return False
            step_id = job.plan_step_id
            if not isinstance(step_id, str):
                return False
            current = current_by_step.get(step_id)
            if (
                not isinstance(current, Mapping)
                or current.get("current_job_id") != job.job_id
            ):
                return False
        return True

    def _ready_frontier_candidate(
        self, candidate: Job, active: list[Job]
    ) -> bool:
        if not active or not self._is_read_only_frontier_work(candidate):
            return False
        for current in active:
            if (
                not self._is_read_only_frontier_work(current)
                or current.plan_attempt_id != candidate.plan_attempt_id
                or current.plan_digest != candidate.plan_digest
                or current.plan_step_id == candidate.plan_step_id
                or not self._active_attempt_is_current_and_live(current)
            ):
                return False
        return True

    def _dispatch_queued(
        self, root_id: str, selected: Job
    ) -> CooCycleOutcome | None:
        command = (
            f"coo-cycle:{root_id}:dispatch:{selected.job_id}:attempt:"
            f"{selected.attempt_count + 1}"
        )
        try:
            receipt = self.dispatcher(selected.job_id, command)
        except Exception:
            # Preserve the existing Runtime-owned reconciliation barrier when
            # a dispatch raises after committing its exact claim.
            if not self._dispatch_none_was_preclaim(selected):
                self.runtime.jobs.record_cycle_dispatch_effect_unknown(
                    root_id,
                    selected_job_id=selected.job_id,
                    dispatch_command_id=command,
                )
            raise
        if receipt is None:
            if not self._dispatch_none_was_preclaim(selected):
                self.runtime.jobs.record_cycle_dispatch_effect_unknown(
                    root_id,
                    selected_job_id=selected.job_id,
                    dispatch_command_id=command,
                )
                raise StateConflict(
                    "exact dispatch return is ambiguous after durable Job transition"
                )
            if self._uses_inert_dispatcher:
                return self._block(
                    root_id, selected.job_id, "exact_dispatch_unavailable"
                )
            return None
        return self._outcome(
            root_id, "DISPATCHED", selected.job_id, command, receipt
        )

    def _block(
        self,
        root: str,
        selected: str,
        reason: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> CooCycleOutcome:
        if reason not in COO_CYCLE_BLOCK_REASONS:
            reason = "state_conflict"
        command = f"coo-cycle:{root}:block:{reason}:{selected}"
        receipt = self.runtime.jobs.block_cycle(
            root,
            selected_job_id=selected,
            reason=reason,
            command_id=command,
            evidence=evidence,
            policy_sha=EXPECTED_POLICY_SHA256,
        )
        return self._outcome(root, "BLOCKED", selected, command, receipt)

    def _finite_control_gate(
        self, root_id: str, root: Job
    ) -> FiniteControlGate | None:
        """Establish every finite control fact this cycle relies on, once.

        The advisory read cannot supply these facts: for an already issued
        Attempt it returns before re-reading the bound context, the durable
        arm, or the persisted host pin.  They are established here instead,
        from the existing owner-issued context definition and the existing
        durable arm, so no later dispatch can lean on ``already_issued``.
        """

        try:
            status = self.runtime.jobs.finite_cycle_status(root_id)
        except StateConflict:
            # A malformed or duplicated durable arm refuses rather than
            # silently reading as unarmed, and never reaches a dispatcher.
            return FiniteControlGate(
                root_job_id=root_id,
                armed=False,
                bound=self._finite_bound_root(root_id) is not None,
                context_proven=False,
                halt=True,
                halt_reason="malformed_arm",
                expired=False,
                exhausted=False,
                spent=0,
                remaining=0,
                current_policy_pin_drift=False,
                refusal_reasons=("malformed_arm",),
            )
        context_definition = self._finite_context_definition()
        definition = self._finite_bound_root(root_id)
        bound = definition is not None
        if status is None and context_definition is None:
            return None

        refusals: list[str] = []
        if context_definition is None:
            refusals.append("armed_root_without_bound_context")
        elif context_definition["phase"] != "bound":
            # An admission-only context carries no root_job_id at all, so the
            # phase refusal has to precede any root comparison.
            refusals.append("admission_only_context")
        elif not bound:
            refusals.append("foreign_bound_context")

        context_proven = bound and definition["phase"] == "bound"
        if status is None:
            context_proven = False
            refusals.append("bound_root_without_durable_arm")
        elif context_proven:
            # Only a bound context can be compared against the durable arm;
            # every other shape is already refused by name above.
            if not self._finite_arm_matches_context(definition, status):
                context_proven = False
                refusals.append("arm_context_projection_drift")
            if not self._finite_host_pin_matches(definition, root):
                context_proven = False
                refusals.append("host_binding_pin_drift")
            if not self._finite_provenance_matches(definition, root):
                context_proven = False
                refusals.append("root_provenance_drift")

        expired = bool(status["expired"]) if status is not None else False
        exhausted = bool(status["exhausted"]) if status is not None else False
        halt = expired or exhausted or not context_proven
        if expired:
            halt_reason = "expired"
        elif exhausted:
            halt_reason = "budget_exhausted"
        elif not context_proven:
            halt_reason = "unproven_finite_context"
        else:
            halt_reason = None
        return FiniteControlGate(
            root_job_id=root_id,
            armed=status is not None,
            bound=bound,
            context_proven=context_proven,
            halt=halt,
            halt_reason=halt_reason,
            expired=expired,
            exhausted=exhausted,
            spent=int(status["spent"]) if status is not None else 0,
            remaining=int(status["remaining"]) if status is not None else 0,
            current_policy_pin_drift=(
                self._finite_current_policy_pin_drift(definition)
                if definition is not None
                else False
            ),
            refusal_reasons=tuple(sorted(refusals)),
            status=status,
            definition=definition,
        )

    def _finite_context_definition(self) -> dict[str, Any] | None:
        """Read the existing owner-issued context definition, if one is bound.

        ``RuntimeStore._finite_control_context`` is the composition seam the
        control owner already binds in process; its ``definition`` property is
        the public read over that immutable input.  No new Runtime API is
        added and no caller-supplied definition is ever accepted.
        """

        context = self.runtime.store._finite_control_context
        if context is None:
            return None
        try:
            definition = context.definition
        except StateConflict:
            return None
        return definition if isinstance(definition, dict) else None

    def _finite_bound_root(self, root_id: str) -> dict[str, Any] | None:
        definition = self._finite_context_definition()
        if definition is None or definition.get("root_job_id") != root_id:
            return None
        return definition

    @staticmethod
    def _finite_arm_matches_context(
        definition: dict[str, Any], status: dict[str, Any]
    ) -> bool:
        """The durable arm must still be the exact projection of the context."""

        policy = status.get("policy")
        if not isinstance(policy, dict):
            return False
        for key in FINITE_CONTROL_STABLE_PIN_KEYS:
            if policy.get(key) != str(definition[key]):
                return False
        return (
            int(status["max_total_attempts"]) == int(definition["max_total_attempts"])
            and int(status["expires_at_ms"]) == int(definition["expires_at_ms"])
        )

    @staticmethod
    def _finite_host_pin_matches(definition: dict[str, Any], root: Job) -> bool:
        """The persisted Job host binding must still pin the context."""

        constraints = root.constraints
        if not isinstance(constraints, Mapping):
            return False
        if constraints.get("operator_harness_armed") is not True:
            return False
        try:
            return (
                finite_host_binding_digest(constraints)
                == definition["host_binding_digest_sha256"]
            )
        except StateConflict:
            return False

    @staticmethod
    def _finite_provenance_matches(definition: dict[str, Any], root: Job) -> bool:
        """The root's immutable provenance must still name the armed intent."""

        provenance = root.orchestration_provenance
        if not isinstance(provenance, dict):
            return False
        return (
            provenance.get("source_id") == definition["intent_id"]
            and provenance.get("source_digest") == definition["intent_fingerprint"]
        )

    @staticmethod
    def _finite_current_policy_pin_drift(
        definition: dict[str, Any] | None,
    ) -> bool:
        """Whether the currently loaded policies have drifted from the pins.

        Drifted current policy pins refuse every fresh issuance on their own
        (the advisory read returns ``authorized_first_launch=False``) and they
        equally refuse the ``already_issued`` incumbent dispatch: that flag is
        persisted Attempt evidence and never proves the launch still belongs
        to the currently pinned composition.  A malformed or unavailable
        current policy proves nothing either, so it reads as drift — fail
        closed, never raising out of the finite gate.  Settlement itself is
        not touched — the Runtime's incumbent owner seams do not consult the
        current pins, so this cycle's zero-write refusal never strands a
        lawfully held incumbent.
        """

        if definition is None:
            return False
        try:
            authority = ExecutiveAuthorityPolicy.load().sha256
        except AuthorityPolicyError:
            return True
        try:
            coo = CooCyclePolicy.load().policy_sha256
        except CooCyclePolicyError:
            return True
        return (
            authority != definition["authority_policy_sha256"]
            or coo != definition["coo_policy_sha256"]
        )

    def _finite_first_issuance(
        self, root_id: str, job: Job
    ) -> FiniteReservationDecision:
        """Advisory read of one current same-root Attempt, without allocation."""

        attempt_id = str(job.current_attempt_id or "")
        return self.runtime.jobs.validate_finite_first_issuance(root_id, attempt_id)

    def _finite_incumbent_allowed(
        self, gate: FiniteControlGate | None, root_id: str, job: Job
    ) -> tuple[bool, FiniteReservationDecision | None]:
        """Whether this current same-root Attempt may reach the dispatcher.

        A legacy root has no finite composition at all, so the advisory read
        is recorded but never gates it.  A finite root requires either the
        Runtime's own ``authorized_first_launch`` verdict, or a persisted
        ``already_issued`` incumbent whose bound context, durable arm and
        persisted pins were just re-proven by the gate and whose composition
        the currently loaded policies still pin unchanged.
        """

        if job.root_job_id != root_id:
            return False, None
        decision = self._finite_first_issuance(root_id, job)
        if gate is None:
            return True, decision
        if decision.authorized_first_launch:
            return True, decision
        if (
            decision.already_issued
            and gate.context_proven
            and not gate.current_policy_pin_drift
        ):
            return True, decision
        return False, decision

    def _finite_outcome(
        self,
        root_id: str,
        policy_sha: str,
        gate: FiniteControlGate,
        decisions: Iterable[FiniteReservationDecision] = (),
        settled: str | None = None,
    ) -> CooCycleOutcome:
        """Deterministic zero-write NO_NEW_WORK receipt for a finite root."""

        return self._outcome(
            root_id,
            "NO_NEW_WORK",
            None,
            None,
            {
                "schema_version": FINITE_CUTOFF_SCHEMA,
                "halt_reason": gate.halt_reason,
                "expired": gate.expired,
                "exhausted": gate.exhausted,
                "spent": gate.spent,
                "remaining": gate.remaining,
                "policy_sha": policy_sha,
                "finite_control": {
                    "armed": gate.armed,
                    "bound": gate.bound,
                    "context_proven": gate.context_proven,
                    "current_policy_pin_drift": gate.current_policy_pin_drift,
                    "refusal_reasons": list(gate.refusal_reasons),
                    "advisory_first_issuance": [
                        {
                            "authorized_first_launch": decision.authorized_first_launch,
                            "already_issued": decision.already_issued,
                            "halt_reason": decision.halt_reason,
                        }
                        for decision in decisions
                    ],
                    "settled_incumbent_job_id": settled,
                },
            },
        )

    @staticmethod
    def _finite_halt_policy_sha(gate: FiniteControlGate) -> str:
        """Deterministic policy pin for a halt receipt, with no policy load.

        The halt resolves before the current policy is ever loaded, so its
        receipt reports the pin the composition was bound under when a bound
        definition carries one, and otherwise the reviewed
        ``EXPECTED_POLICY_SHA256`` that every policy-pinned receipt in this
        module already uses.  A malformed or unavailable current policy can
        change neither the halt nor this pin.
        """

        if gate.definition is not None:
            pinned = gate.definition.get("coo_policy_sha256")
            if isinstance(pinned, str) and pinned:
                return pinned
        return EXPECTED_POLICY_SHA256

    def _finite_halt_outcome(
        self, root_id: str, gate: FiniteControlGate, policy_sha: str
    ) -> CooCycleOutcome:
        """Resolve a halted finite root: incumbent settlement, nothing else.

        Every fresh, requeue, block, repair, review, planner, plan, handoff,
        queued and root-fresh path is closed with zero writes.  The one
        permitted mutation is the existing exact dispatcher replaying the
        original command for a same-root current Attempt that either the
        Runtime authorizes as a first launch, or that already holds its
        charged issuance under a re-proven bound context.
        """

        all_jobs = [
            job for job in self.runtime.jobs.list_jobs() if job.root_job_id == root_id
        ]
        children = [job for job in all_jobs if job.job_id != root_id]
        ordinals = self._finite_plan_ordinals(root_id)
        decisions: list[FiniteReservationDecision] = []

        active = sorted(
            [
                job
                for job in children
                if job.status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
            ],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        for selected in active:
            if not selected.attempt_count or not selected.current_attempt_id:
                continue
            allowed, decision = self._finite_incumbent_allowed(
                gate, root_id, selected
            )
            if decision is not None:
                decisions.append(decision)
            if not allowed:
                continue
            command = (
                f"coo-cycle:{root_id}:dispatch:{selected.job_id}:attempt:"
                f"{selected.attempt_count}"
            )
            receipt = self.dispatcher(selected.job_id, command)
            if receipt is None:
                raise StateConflict(
                    "active exact dispatch returned no reconcilable outcome"
                )
            return self._outcome(
                root_id, "DISPATCHED", selected.job_id, command, receipt
            )

        handoff_events = [
            event
            for event in self.runtime.events.list_events(job_id=root_id)
            if event.event_type == "COO_AGGREGATION_HANDOFF_READY"
        ]
        root = self.runtime.jobs.get_job(root_id)
        if (
            handoff_events
            and root is not None
            and root.status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
            and root.attempt_count
            and root.current_attempt_id
        ):
            allowed, decision = self._finite_incumbent_allowed(gate, root_id, root)
            if decision is not None:
                decisions.append(decision)
            if allowed:
                command = (
                    f"coo-cycle:{root_id}:dispatch:{root_id}:attempt:"
                    f"{root.attempt_count}"
                )
                receipt = self.dispatcher(root_id, command)
                if receipt is None:
                    raise StateConflict(
                        "active exact root dispatch returned no reconcilable outcome"
                    )
                return self._outcome(
                    root_id, "DISPATCHED", root_id, command, receipt
                )

        return self._finite_outcome(root_id, policy_sha, gate, decisions)

    def _finite_plan_ordinals(self, root_id: str) -> dict[str, int]:
        """Best-effort step ordinals; halt ordering never needs a valid plan."""

        try:
            with self.runtime.store.read() as connection:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id=?", (root_id,)
                ).fetchone()
                if row is None:
                    return {}
                _admission, plan_body = _validated_plan_admission(connection, row)
                return {
                    str(step["step_id"]): index
                    for index, step in enumerate(plan_body["steps"])
                }
        except (StateConflict, CooCyclePolicyError):
            return {}

    def run_once(self, parent_job_id: str) -> CooCycleOutcome:
        root_id = str(parent_job_id or "").strip()
        root = self.runtime.jobs.get_job(root_id)
        if root is None:
            raise StateConflict(f"root job {root_id!r} does not exist")

        # Finite control facts are established immediately after the root
        # lookup — before the current policy is loaded and before any durable
        # block is replayed — so a halted root can only ever settle an
        # incumbent: neither a malformed current policy nor a stale
        # preexisting block can answer before the deterministic zero-write
        # NO_NEW_WORK, and every fresh, requeue, block, repair, review,
        # planner, plan, handoff, queued and root-fresh path below is
        # unreachable once this gate reports a halt.
        gate = self._finite_control_gate(root_id, root)
        if gate is not None and gate.halt:
            return self._finite_halt_outcome(
                root_id, gate, self._finite_halt_policy_sha(gate)
            )

        try:
            policy = CooCyclePolicy.load()
        except CooCyclePolicyError as exc:
            return self._block(
                root_id,
                root_id,
                "invalid_policy",
                evidence={"error_type": type(exc).__name__},
            )

        existing_block = self.runtime.jobs.validated_cycle_block(root_id)
        if existing_block is not None:
            command_id, payload = existing_block
            return self._outcome(
                root_id,
                "BLOCKED",
                str(payload["selected_job_id"]),
                command_id,
                payload,
            )

        provenance = root.orchestration_provenance
        if (
            root.parent_job_id is not None
            or root.root_job_id != root.job_id
            or root.depth != 0
            or root.orchestration_role != "aggregation"
            or not isinstance(provenance, dict)
            or provenance.get("schema_version")
            != "mastermind.executive_orchestration_provenance/v1"
            or provenance.get("creator") != "ceo_intent"
            or provenance.get("role") != "aggregation"
            or provenance.get("job_id") != root.job_id
            or provenance.get("root_job_id") != root.job_id
            or provenance.get("parent_job_id") is not None
            or not provenance.get("source_id")
            or not provenance.get("source_digest")
        ):
            return self._block(root_id, root_id, "invalid_root")

        pending_dispatch = (
            self.runtime.jobs.pending_cycle_dispatch_effect_unknown(root_id)
        )
        if pending_dispatch is not None:
            selected_id = str(pending_dispatch["selected_job_id"])
            command = str(pending_dispatch["dispatch_command_id"])
            receipt = self.dispatcher(selected_id, command)
            if receipt is None:
                raise StateConflict(
                    "active exact dispatch returned no reconcilable outcome"
                )
            self.runtime.jobs.reconcile_cycle_dispatch_effect(
                root_id,
                selected_job_id=selected_id,
                dispatch_command_id=command,
                receipt=receipt,
            )
            return self._outcome(
                root_id, "DISPATCHED", selected_id, command, receipt
            )

        all_jobs = [
            job
            for job in self.runtime.jobs.list_jobs()
            if job.root_job_id == root_id
        ]
        children = [job for job in all_jobs if job.job_id != root_id]
        events = self.runtime.events.list_events(job_id=root_id)
        admission_events = [event for event in events if event.event_type == "COO_PLAN_ADMITTED"]
        handoff_events = [
            event for event in events if event.event_type == "COO_AGGREGATION_HANDOFF_READY"
        ]
        if len(admission_events) > 1 or len(handoff_events) > 1:
            return self._block(root_id, root_id, "lineage_invalid")

        admission: dict[str, Any] | None = None
        plan_body: dict[str, Any] | None = None
        current_by_step: dict[str, dict[str, Any]] = {}
        try:
            with self.runtime.store.read() as connection:
                root_row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id=?", (root_id,)
                ).fetchone()
                assert root_row is not None
                if admission_events:
                    admission, plan_body = _validated_plan_admission(connection, root_row)
                    current = _current_orchestration_tree_material_for_dispatch(
                        connection, root_row, admission, plan_body
                    )
                    current_by_step = {
                        str(item["plan_step_id"]): item for item in current
                    }
                if handoff_events:
                    _validated_aggregation_handoff(connection, root_row)
        except (StateConflict, CooCyclePolicyError) as exc:
            return self._block(
                root_id,
                root_id,
                _classify_invalid(exc),
                evidence={"error_type": type(exc).__name__},
            )

        ordinals: dict[str, int] = {}
        if plan_body is not None:
            ordinals = {
                str(step["step_id"]): index
                for index, step in enumerate(plan_body["steps"])
            }

        # A pre-admission root may contain only the exact cycle-created planner.
        # Prove this before requeue or dispatch so a queued forged/corrupt child
        # can never cross the claim boundary.
        if not admission_events and children:
            if len(children) != 1:
                return self._block(root_id, root_id, "unexpected_pre_admission_child")
            planner = children[0]
            planner_provenance = planner.orchestration_provenance
            expected_create_command = f"coo-cycle:{root_id}:create-planner:0"
            if (
                planner.orchestration_role != "plan"
                or planner.parent_job_id != root_id
                or planner.root_job_id != root_id
                or planner.depth != 1
                or planner.plan_attempt_id is not None
                or planner.plan_digest is not None
                or planner.plan_step_id is not None
                or planner.supersedes_job_id is not None
                or not isinstance(planner_provenance, dict)
                or planner_provenance.get("schema_version")
                != "mastermind.executive_orchestration_provenance/v1"
                or planner_provenance.get("creator") != "coo_cycle"
                or planner_provenance.get("command_id") != expected_create_command
                or planner_provenance.get("job_id") != planner.job_id
                or planner_provenance.get("parent_job_id") != root_id
                or planner_provenance.get("root_job_id") != root_id
                or planner_provenance.get("role") != "plan"
                or planner_provenance.get("source_id") != root_id
                or planner_provenance.get("source_digest")
                != root.orchestration_provenance_digest
            ):
                return self._block(root_id, planner.job_id, "lineage_invalid")

        # 2. One recoverable same-Job requeue precedes every create/dispatch.
        recoverable = sorted(
            [
                job
                for job in all_jobs
                if job.status in _RECOVERABLE and job.attempt_count < job.attempt_limit
            ],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        if recoverable:
            selected = recoverable[0]
            if not selected.current_attempt_id:
                return self._block(root_id, selected.job_id, "state_conflict")
            expectation = self.runtime.jobs.project_retry_safety(
                selected.job_id,
                expected_attempt_id=str(selected.current_attempt_id),
            )
            try:
                committed = self.runtime.jobs.commit_coo_retry_decision(
                    root_id,
                    selected_job_id=selected.job_id,
                    expectation=expectation,
                    policy_sha=EXPECTED_POLICY_SHA256,
                )
            except StateConflict as exc:
                return self._outcome(
                    root_id,
                    "RECONCILIATION_REQUIRED",
                    selected.job_id,
                    None,
                    {
                        "schema_version": "mastermind.executive_retry_reconciliation/v1",
                        "decision": "NEEDS_RECONCILIATION",
                        "effect_state": "NONE",
                        "reason": _classify_invalid(exc),
                        "error_type": type(exc).__name__,
                    },
                )
            return self._outcome(
                root_id,
                committed.action,
                selected.job_id,
                committed.command_id,
                committed.receipt,
            )

        # 3. Resolve one closed adverse terminal/review verdict.
        adverse: list[tuple[tuple[int, int, int, str], str, Job, dict[str, Any]]] = []
        for job in all_jobs:
            exhausted = job.attempt_count >= job.attempt_limit
            if job.orchestration_role == "plan" and (
                job.status == JobStatus.CANCELLED
                or (job.status in _RECOVERABLE and exhausted)
            ):
                adverse.append((_job_sort_key(job, ordinals), "block_plan", job, {}))
            elif job.orchestration_role in {"work", "repair"} and (
                job.status == JobStatus.CANCELLED
                or (job.status in _RECOVERABLE and exhausted)
            ):
                adverse.append((_job_sort_key(job, ordinals), "block_child", job, {}))
            elif job.orchestration_role == "aggregation" and (
                job.status == JobStatus.CANCELLED
                or (job.status in _RECOVERABLE and exhausted)
            ):
                adverse.append((_job_sort_key(job, ordinals), "block_root", job, {}))

        if admission is not None and plan_body is not None:
            with self.runtime.store.read() as connection:
                rows = {
                    str(row["job_id"]): row
                    for row in connection.execute(
                        "SELECT * FROM jobs WHERE root_job_id=?", (root_id,)
                    )
                }
                review_groups: dict[str, list[Job]] = {}
                for review in children:
                    if review.orchestration_role == "review" and review.reviews_job_id:
                        review_groups.setdefault(review.reviews_job_id, []).append(review)
                for target_id, unsorted_peers in review_groups.items():
                    target = next(
                        (candidate for candidate in children if candidate.job_id == target_id),
                        None,
                    )
                    if target is None or current_by_step.get(str(target.plan_step_id), {}).get(
                        "current_job_id"
                    ) != target.job_id:
                        continue
                    peers = sorted(unsorted_peers, key=lambda item: item.job_id)
                    approvals: list[Job] = []
                    rejects: list[tuple[Job, str]] = []
                    voids: list[Job] = []
                    terminal_adverse: list[Job] = []
                    invalid_results: list[Job] = []
                    living: list[Job] = []
                    for review in peers:
                        exhausted = review.attempt_count >= review.attempt_limit
                        if review.status == JobStatus.CANCELLED or (
                            review.status in _RECOVERABLE and exhausted
                        ):
                            terminal_adverse.append(review)
                            continue
                        if review.status != JobStatus.COMPLETED:
                            living.append(review)
                            continue
                        try:
                            attempt, seal, _terminal, completion_digest = (
                                _validated_role_completion_material(
                                    connection,
                                    job_row=rows[review.job_id],
                                    expected_role="review",
                                    root_job_id=root_id,
                                )
                            )
                            body = seal["result_envelope"]["role_result"]
                            independent = _review_attempt_is_independent(
                                connection,
                                review_attempt_id=str(attempt["attempt_id"]),
                                reviewed_attempt_id=str(body["reviewed_attempt_id"]),
                            )
                        except StateConflict:
                            invalid_results.append(review)
                            continue
                        if not independent:
                            voids.append(review)
                        elif body.get("verdict") == "approve":
                            approvals.append(review)
                        elif body.get("verdict") == "reject":
                            rejects.append((review, completion_digest))
                        else:
                            invalid_results.append(review)

                    # A qualifying replacement approval resolves the target as a
                    # set; a historical VOID or adverse record cannot veto it.
                    if approvals:
                        continue
                    if invalid_results:
                        selected = invalid_results[0]
                        adverse.append(
                            (_job_sort_key(selected, ordinals), "block_result", selected, {})
                        )
                        continue
                    if rejects:
                        selected, review_digest = rejects[0]
                        kind = (
                            "repair"
                            if int(target.repair_round or 0) < policy.max_repair_rounds
                            else "block_repairs"
                        )
                        adverse.append(
                            (
                                _job_sort_key(selected, ordinals),
                                kind,
                                selected,
                                {
                                    "target": target.job_id,
                                    "review_result_digest": review_digest,
                                },
                            )
                        )
                        continue
                    if living:
                        continue
                    closed = [*voids, *terminal_adverse]
                    if closed and len(peers) < policy.max_review_attempts_per_job:
                        selected = sorted(closed, key=lambda item: item.job_id)[0]
                        adverse.append(
                            (
                                _job_sort_key(selected, ordinals),
                                "replace_review",
                                selected,
                                {"target": target.job_id, "ordinal": len(peers) + 1},
                            )
                        )
                    elif voids:
                        selected = voids[0]
                        adverse.append(
                            (_job_sort_key(selected, ordinals), "block_independence", selected, {})
                        )
                    elif terminal_adverse:
                        selected = terminal_adverse[0]
                        adverse.append(
                            (_job_sort_key(selected, ordinals), "block_reviews", selected, {})
                        )

        if adverse:
            _key, kind, selected, data = sorted(adverse, key=lambda item: item[0])[0]
            reason = {
                "block_plan": "plan_terminal_adverse",
                "block_child": "child_terminal_adverse",
                "block_root": "aggregation_terminal_adverse",
                "block_reviews": "review_jobs_exhausted",
                "block_independence": "review_not_independent",
                "block_repairs": "repair_rounds_exhausted",
                "block_result": "result_protocol_invalid",
            }.get(kind)
            if reason:
                return self._block(root_id, selected.job_id, reason)
            if kind == "replace_review":
                target = str(data["target"])
                command = f"coo-cycle:{root_id}:create-review:{target}:{int(data['ordinal'])}"
                try:
                    receipt = self.runtime.jobs.create_cycle_review(
                        root_id, target, command_id=command
                    )
                except StateConflict as exc:
                    return self._block(root_id, selected.job_id, _classify_invalid(exc))
                return self._outcome(root_id, "REVIEW_CREATED", receipt.job_id, command, receipt)
            if kind == "repair":
                target = str(data["target"])
                next_round = int(
                    next(job for job in children if job.job_id == target).repair_round or 0
                ) + 1
                command = (
                    f"coo-cycle:{root_id}:create-repair:{target}:{selected.job_id}:"
                    f"{data['review_result_digest']}:{next_round}"
                )
                try:
                    receipt = self.runtime.jobs.create_cycle_repair(
                        root_id, target, selected.job_id, command_id=command
                    )
                except StateConflict as exc:
                    return self._block(root_id, selected.job_id, _classify_invalid(exc))
                return self._outcome(root_id, "REPAIR_CREATED", receipt.job_id, command, receipt)

        # 4. Materialize one lowest-ordinal missing dependency-ready V3 work Job.
        if (
            admission is not None
            and plan_body is not None
            and admission.get("schema_version") == "mastermind.coo_plan_admission/v2"
            and plan_body.get("schema_version") == "mastermind.execution_plan/v3"
        ):
            materialized_steps = {
                str(job.plan_step_id)
                for job in children
                if job.orchestration_role in {"work", "repair"}
                and job.plan_step_id is not None
            }
            for step in plan_body["steps"]:
                step_id = str(step["step_id"])
                if (
                    not step["prerequisite_step_ids"]
                    or step_id in materialized_steps
                ):
                    continue
                try:
                    manifest = (
                        self.runtime.jobs.project_cycle_work_dependency_manifest(
                            root_id, step_id
                        )
                    )
                except StateConflict:
                    continue
                command = (
                    f"coo-cycle:{root_id}:create-work:{step_id}:"
                    f"{manifest['dependency_manifest_digest']}"
                )
                try:
                    job = self.runtime.jobs.create_cycle_work(
                        root_id,
                        step_id,
                        dependency_manifest=manifest,
                        command_id=command,
                    )
                except StateConflict as exc:
                    return self._block(
                        root_id, root_id, _classify_invalid(exc)
                    )
                return self._outcome(
                    root_id, "WORK_CREATED", job.job_id, command, job
                )

        # 5. Create exactly the sole planner.
        if not children and not admission_events:
            command = f"coo-cycle:{root_id}:create-planner:0"
            planner = self.runtime.jobs.create_cycle_planner(root_id, command_id=command)
            return self._outcome(root_id, "PLANNER_CREATED", planner.job_id, command, planner)

        # 6. Service one bounded ready sibling only when every active child is
        # exact, lease-live, read-only work from the same sealed plan.  Any stale
        # Attempt, review/repair activity, write authority, or source-custody risk
        # preserves reconciliation-first behavior.
        active = sorted(
            [
                job
                for job in children
                if job.status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
            ],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        queued = sorted(
            [job for job in children if job.status == JobStatus.QUEUED],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        if (
            active
            and queued
            and plan_body is not None
            and plan_body["schema_version"] == "mastermind.execution_plan/v3"
            and self._ready_frontier_open(active, queued, current_by_step)
        ):
            for candidate in queued:
                if not self._ready_frontier_candidate(candidate, active):
                    continue
                outcome = self._dispatch_queued(root_id, candidate)
                if outcome is not None:
                    return outcome

        # 7. Reconcile an active exact dispatch before any coupled/new work.
        # Replaying the original command resumes or returns the same Attempt;
        # it never claims a replacement or another Job.
        if active:
            selected = active[0]
            if selected.attempt_count < 1 or not selected.current_attempt_id:
                return self._block(root_id, selected.job_id, "state_conflict")
            allowed, decision = self._finite_incumbent_allowed(gate, root_id, selected)
            if not allowed:
                assert gate is not None
                return self._finite_outcome(
                    root_id, policy.policy_sha256, gate, [decision]
                )
            command = (
                f"coo-cycle:{root_id}:dispatch:{selected.job_id}:attempt:"
                f"{selected.attempt_count}"
            )
            receipt = self.dispatcher(selected.job_id, command)
            if receipt is None:
                raise StateConflict(
                    "active exact dispatch returned no reconcilable outcome"
                )
            return self._outcome(root_id, "DISPATCHED", selected.job_id, command, receipt)

        # 8. With no active child, try queued work in deterministic order.
        # Explicit dispatcher pre-claim unavailability is temporary capacity
        # pressure, not a durable root blocker.
        if queued:
            unavailable: list[str] = []
            for candidate in queued:
                outcome = self._dispatch_queued(root_id, candidate)
                if outcome is not None:
                    return outcome
                unavailable.append(candidate.job_id)
                if not (
                    plan_body is not None
                    and plan_body["schema_version"] == "mastermind.execution_plan/v3"
                    and all(self._is_read_only_frontier_work(job) for job in queued)
                ):
                    break
            return self._outcome(
                root_id,
                "NO_ACTION",
                None,
                None,
                {
                    "reason": "exact_dispatch_unavailable",
                    "unavailable_job_ids": unavailable,
                    "policy_sha": policy.policy_sha256,
                },
            )

        # 9. Admit the completed plan and its ordered initial work wave.
        if not admission_events:
            planners = [job for job in children if job.orchestration_role == "plan"]
            if len(planners) != 1 or len(children) != 1:
                return self._block(root_id, root_id, "unexpected_pre_admission_child")
            planner = planners[0]
            if planner.status == JobStatus.COMPLETED and planner.current_attempt_id:
                command = f"coo-cycle:{root_id}:admit-plan:{planner.current_attempt_id}"
                try:
                    members = self.runtime.jobs.admit_cycle_plan(root_id, command_id=command)
                except StateConflict as exc:
                    return self._block(root_id, planner.job_id, _classify_invalid(exc))
                return self._outcome(
                    root_id,
                    "PLAN_ADMITTED",
                    planner.job_id,
                    command,
                    {"work_job_ids": [member.job_id for member in members]},
                )

        # 10. Create one missing review for the lowest completed current revision.
        if admission is not None:
            missing: list[Job] = []
            for step_id, material in current_by_step.items():
                if not material["review_required"]:
                    continue
                current_job = next(
                    job for job in children if job.job_id == material["current_job_id"]
                )
                reviews = [job for job in children if job.reviews_job_id == current_job.job_id]
                if current_job.status == JobStatus.COMPLETED and not reviews:
                    missing.append(current_job)
            if missing:
                target = sorted(missing, key=lambda job: _job_sort_key(job, ordinals))[0]
                command = f"coo-cycle:{root_id}:create-review:{target.job_id}:1"
                review = self.runtime.jobs.create_cycle_review(
                    root_id, target.job_id, command_id=command
                )
                return self._outcome(root_id, "REVIEW_CREATED", review.job_id, command, review)

        # 11. Derived approvals flow directly to the immutable handoff mutation.
        if admission is not None and not handoff_events:
            living = [
                job
                for job in children
                if job.status not in {
                    JobStatus.RATE_LIMITED, JobStatus.FAILED, JobStatus.LOST,
                    JobStatus.COMPLETED, JobStatus.CANCELLED,
                }
            ]
            if not living:
                try:
                    with self.runtime.store.read() as connection:
                        root_row = connection.execute(
                            "SELECT * FROM jobs WHERE job_id=?", (root_id,)
                        ).fetchone()
                        assert root_row is not None and plan_body is not None
                        _current_orchestration_tree_material(
                            connection, root_row, admission, plan_body
                        )
                    command = f"coo-cycle:{root_id}:aggregation-handoff:1"
                    handoff = self.runtime.jobs.create_cycle_handoff(
                        root_id, command_id=command
                    )
                    return self._outcome(
                        root_id, "HANDOFF_CREATED", root_id, command, handoff
                    )
                except StateConflict as exc:
                    return self._block(root_id, root_id, _classify_invalid(exc))

        # 12. Dispatch/reconcile the exact root only after immutable handoff.
        if handoff_events and root.status in {
            JobStatus.RUNNING,
            JobStatus.CHECKPOINTED,
        }:
            if root.attempt_count < 1 or not root.current_attempt_id:
                return self._block(root_id, root_id, "state_conflict")
            allowed, decision = self._finite_incumbent_allowed(gate, root_id, root)
            if not allowed:
                assert gate is not None
                return self._finite_outcome(
                    root_id, policy.policy_sha256, gate, [decision]
                )
            command = (
                f"coo-cycle:{root_id}:dispatch:{root_id}:attempt:"
                f"{root.attempt_count}"
            )
            receipt = self.dispatcher(root_id, command)
            if receipt is None:
                raise StateConflict(
                    "active exact root dispatch returned no reconcilable outcome"
                )
            return self._outcome(root_id, "DISPATCHED", root_id, command, receipt)
        if handoff_events and root.status == JobStatus.QUEUED:
            command = (
                f"coo-cycle:{root_id}:dispatch:{root_id}:attempt:"
                f"{root.attempt_count + 1}"
            )
            receipt = self.dispatcher(root_id, command)
            if receipt is None:
                if not self._dispatch_none_was_preclaim(root):
                    self.runtime.jobs.record_cycle_dispatch_effect_unknown(
                        root_id,
                        selected_job_id=root_id,
                        dispatch_command_id=command,
                    )
                    raise StateConflict(
                        "exact root dispatch return is ambiguous after durable Job transition"
                    )
                if self._uses_inert_dispatcher:
                    return self._block(
                        root_id, root_id, "exact_dispatch_unavailable"
                    )
                return self._outcome(
                    root_id,
                    "NO_ACTION",
                    None,
                    None,
                    {
                        "reason": "exact_dispatch_unavailable",
                        "unavailable_job_ids": [root_id],
                        "policy_sha": policy.policy_sha256,
                    },
                )
            return self._outcome(root_id, "DISPATCHED", root_id, command, receipt)

        return self._outcome(
            root_id,
            "NO_ACTION",
            None,
            None,
            {"policy_sha": policy.policy_sha256},
        )


__all__ = [
    "CYCLE_OUTCOME_SCHEMA",
    "FINITE_CUTOFF_SCHEMA",
    "CooCycle",
    "CooCycleOutcome",
    "Dispatch",
    "FiniteControlGate",
]

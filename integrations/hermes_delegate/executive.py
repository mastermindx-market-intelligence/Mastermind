"""Read-only qualification of a host-selected Executive child.

This module is imported explicitly by a trusted host. It is not an admission
port, a carrier, or a model-visible tool. A successful observation grants no
authority to launch, retry, review, cancel, or consume a result.

Beside that observation binding it carries the explicit trusted-host
production composition: one frozen selected child, the incumbent Executive
service that owns the claim, and the canonical command reference derived from
the frozen Attempt ordinal. The composition holds no lifecycle state of its
own; every fact is resolved from the canonical Runtime.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from control_plane import executive_runtime as owner
from control_plane.coo_principal_host import CooHostProvider
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.executive_delegation_identity import derive_delegation_identity

QUALIFICATION_SCHEMA = "mastermind.hermes_delegate.executive_child_observation/v1"
SELECTED_CHILD_SCHEMA = "mastermind.hermes_delegate.selected_child/v1"


@dataclass(frozen=True)
class ExecutiveChildSelection:
    """Exact coordinates supplied by the existing authenticated host owner."""

    root_job_id: str
    parent_job_id: str
    job_id: str
    plan_attempt_id: str
    plan_digest: str
    plan_step_id: str
    repair_round: int
    # None means no current Attempt, never "accept any current Attempt".
    expected_current_attempt_id: str | None


def _response(state: str, reason: str | None = None, **fields: Any) -> dict[str, Any]:
    return {
        "schema": QUALIFICATION_SCHEMA,
        "state": state,
        "reason": reason,
        "authority": "OBSERVATION_ONLY",
        "live_submit": False,
        **fields,
    }


def _valid_selection(selection: Any) -> bool:
    if not isinstance(selection, ExecutiveChildSelection):
        return False
    text = (
        selection.root_job_id, selection.parent_job_id, selection.job_id,
        selection.plan_attempt_id, selection.plan_digest, selection.plan_step_id,
    )
    return (
        all(isinstance(value, str) and 0 < len(value) <= 128 for value in text)
        and type(selection.repair_round) is int
        and selection.repair_round in {0, 1, 2}
        and (
            selection.expected_current_attempt_id is None
            or (
                isinstance(selection.expected_current_attempt_id, str)
                and 0 < len(selection.expected_current_attempt_id) <= 128
            )
        )
    )


@dataclass(frozen=True)
class ExecutiveChildQualification:
    """Observe one fixed child from the existing Runtime's coherent read.

    The caller owns authentication and selection. Never construct this binding
    from model arguments. The read revalidates the admitted plan and current
    persisted work/repair lineage; it does not reproduce dispatch eligibility
    or every repair-admission condition.
    """

    runtime: owner.Runtime = field(repr=False)
    selection: ExecutiveChildSelection

    def qualify(self) -> dict[str, Any]:
        selected = self.selection
        if not _valid_selection(selected):
            return _response("REFUSED", "EXECUTIVE_SELECTION_INVALID")
        if selected.parent_job_id != selected.root_job_id:
            return _response("REFUSED", "EXECUTIVE_CHILD_DEPTH_UNSUPPORTED")
        try:
            with self.runtime.store.read() as connection:
                root = connection.execute(
                    "SELECT * FROM jobs WHERE job_id=?", (selected.root_job_id,)
                ).fetchone()
                child = connection.execute(
                    "SELECT * FROM jobs WHERE job_id=?", (selected.job_id,)
                ).fetchone()
                if root is None or child is None:
                    return _response("REFUSED", "EXECUTIVE_CHILD_NOT_FOUND")
                # Check raw identity before the decoder's legacy root fallback.
                if (
                    root["job_id"] != selected.root_job_id
                    or root["root_job_id"] != selected.root_job_id
                    or root["parent_job_id"] is not None
                    or root["depth"] != 0
                    or root["orchestration_role"] != "aggregation"
                ):
                    return _response("REFUSED", "EXECUTIVE_ROOT_UNVERIFIED")
                if (
                    child["root_job_id"] != selected.root_job_id
                    or child["parent_job_id"] != selected.parent_job_id
                    or child["depth"] != 1
                ):
                    return _response("REFUSED", "EXECUTIVE_CHILD_SCOPE_MISMATCH")
                if child["orchestration_role"] not in {"work", "repair"}:
                    return _response("REFUSED", "EXECUTIVE_CHILD_ROLE_UNSUPPORTED")

                derive_delegation_identity(owner._job_from_row(root))
                job = owner._job_from_row(child)
                identity = derive_delegation_identity(job)
                if (
                    job.plan_attempt_id != selected.plan_attempt_id
                    or job.plan_digest != selected.plan_digest
                    or job.plan_step_id != selected.plan_step_id
                    or job.repair_round != selected.repair_round
                ):
                    return _response("REFUSED", "EXECUTIVE_PLAN_SELECTION_CHANGED")

                admission, plan = owner._validated_plan_admission(connection, root)
                current = owner._current_orchestration_tree_material_for_dispatch(
                    connection, root, admission, plan
                )
                step = next(
                    (item for item in current
                     if item["plan_step_id"] == selected.plan_step_id),
                    None,
                )
                if step is None or step["current_job_id"] != selected.job_id:
                    return _response("REFUSED", "EXECUTIVE_CHILD_SUPERSEDED")
                if (
                    admission["plan_attempt_id"] != selected.plan_attempt_id
                    or admission["plan_digest"] != selected.plan_digest
                ):
                    return _response("REFUSED", "EXECUTIVE_PLAN_SELECTION_CHANGED")
                if job.current_attempt_id != selected.expected_current_attempt_id:
                    return _response("REFUSED", "EXECUTIVE_CURRENT_ATTEMPT_CHANGED")

                attempt = None
                if selected.expected_current_attempt_id is not None:
                    attempt_row = connection.execute(
                        "SELECT * FROM attempts WHERE attempt_id=?",
                        (selected.expected_current_attempt_id,),
                    ).fetchone()
                    if (
                        attempt_row is None
                        or attempt_row["job_id"] != selected.job_id
                        or attempt_row["attempt_number"] != job.attempt_count
                    ):
                        return _response("REFUSED", "EXECUTIVE_CURRENT_ATTEMPT_UNVERIFIED")
                    attempt = owner._attempt_from_row(attempt_row)

                observation = _response(
                    "QUALIFIED",
                    observation_kind="CURRENT_PLAN_CHILD",
                    root_job_id=identity.root_job_id,
                    parent_job_id=job.parent_job_id,
                    job_id=identity.job_id,
                    orchestration_role=job.orchestration_role,
                    job_status=job.status.value,
                    plan_attempt_id=job.plan_attempt_id,
                    plan_digest=job.plan_digest,
                    plan_step_id=job.plan_step_id,
                    repair_round=job.repair_round,
                    policy_sha=admission["policy_sha"],
                    reservation_digest=admission["reservation_digest"],
                    review_required=step["review_required"],
                    current_attempt_id=job.current_attempt_id,
                    attempt_status=attempt.status.value if attempt else None,
                    operation_key=identity.operation_key,
                    session_ref=identity.session_ref,
                )
            # The installed read binding also checks custody on context exit.
            return observation
        except (owner.StateConflict, ValueError, TypeError, KeyError):
            return _response("REFUSED", "EXECUTIVE_PLAN_LINEAGE_UNVERIFIED")
        except Exception:
            # Includes persistence/custody failures during context exit. Never
            # expose private database, grant, principal or filesystem details.
            return _response("UNAVAILABLE", "EXECUTIVE_READ_UNAVAILABLE")


@dataclass(frozen=True)
class ExecutiveSelectedChild:
    """The host's frozen dispatch coordinates for one admitted child.

    The Attempt ordinal is frozen with the selection, so the canonical
    dispatch command is derived once and never recomputed from a later
    ``attempt_count``. A repeated submit observes that exact command and
    Attempt.
    """

    selection: ExecutiveChildSelection
    attempt_ordinal: int

    @property
    def command_id(self) -> str:
        """The incumbent deterministic coo-cycle dispatch command."""

        return (
            f"coo-cycle:{self.selection.root_job_id}:dispatch:"
            f"{self.selection.job_id}:attempt:{self.attempt_ordinal}"
        )

    def expected_selection(self) -> owner.ExpectedChildSelection:
        """The frozen selection the Runtime re-proves at the claim."""

        selected = self.selection
        return owner.ExpectedChildSelection(
            root_job_id=selected.root_job_id,
            parent_job_id=selected.parent_job_id,
            job_id=selected.job_id,
            plan_attempt_id=selected.plan_attempt_id,
            plan_digest=selected.plan_digest,
            plan_step_id=selected.plan_step_id,
            repair_round=selected.repair_round,
            expected_current_attempt_id=selected.expected_current_attempt_id,
            attempt_ordinal=self.attempt_ordinal,
            command_id=self.command_id,
        )


def _selected_child_valid(child: Any) -> bool:
    if not isinstance(child, ExecutiveSelectedChild):
        return False
    if type(child.attempt_ordinal) is not int or child.attempt_ordinal < 1:
        return False
    return _valid_selection(child.selection)


class SelectedChildRefused(Exception):
    """One closed refusal reason for the selected-child composition."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _selected_child_refusal(
    state: str, reason: str, child: ExecutiveSelectedChild | None = None,
) -> dict[str, Any]:
    return {
        "schema": SELECTED_CHILD_SCHEMA, "state": state, "reason": reason,
        "command_id": child.command_id if child is not None else None,
        "job_id": child.selection.job_id if child is not None else None,
        "attempt_id": None, "attempt_status": None, "job_status": None,
        "live_submit": None if state in {"EFFECT_UNKNOWN", "UNAVAILABLE"} else False,
    }


def _envelope(body: Mapping[str, Any], child: ExecutiveSelectedChild) -> dict[str, Any]:
    """Validate original identity before projecting finite canonical facts."""
    states = {"ACTIVE", "NOT_CLAIMED", "EFFECT_UNKNOWN", "COMPLETED", "FAILED",
        "CANCELLED", "RATE_LIMITED", "CANCEL_REQUESTED", "UNVERIFIED", "REFUSED", "UNAVAILABLE"}
    allowed = {"command_id", "job_id", "root_job_id", "orchestration_role", "job_status",
        "attempt_id", "attempt_number", "attempt_status", "state", "reason", "result_status",
        "role", "operation_key", "session_ref", "result_envelope_digest", "terminal_evidence_digest"}
    if (type(body) is not dict or not set(body) <= allowed
            or body.get("command_id") != child.command_id
            or body.get("job_id") != child.selection.job_id
            or type(body.get("state")) is not str or body["state"] not in states):
        raise ValueError("selected child result does not describe its original command")
    attempt = body.get("attempt_id")
    if attempt is not None and (type(attempt) is not str or not attempt or len(attempt) > 128):
        raise ValueError("selected child Attempt is invalid")
    if body["state"] not in {"NOT_CLAIMED", "EFFECT_UNKNOWN", "REFUSED", "UNAVAILABLE"} and attempt is None:
        raise ValueError("selected child result lacks its canonical Attempt")
    merged = {"reason": None, "attempt_id": None, "attempt_status": None, "job_status": None, **body}
    merged["schema"] = SELECTED_CHILD_SCHEMA
    merged["live_submit"] = True if attempt is not None else (
        None if body["state"] in {"EFFECT_UNKNOWN", "UNAVAILABLE"} else False)
    return merged


@dataclass(frozen=True)
class ExecutiveSelectedChildComposition:
    """Trusted host inputs; Runtime retains every command and lifecycle fact.

    Authority is private host material, never fields accepted from the model.
    The async entry points run on the incumbent Control loop. Synchronous
    adapters schedule that same operation once and retain uncertainty after
    any possible scheduling; they never cancel or retry a timed-out submit.
    """
    service: Any
    runtime: Any
    children: tuple[ExecutiveSelectedChild, ...]
    loop: Any
    timeout: float = 60.0
    authority: CooHostProvider | None = field(default=None, repr=False)
    context: PrincipalAdmissionContext | None = field(default=None, repr=False)
    capability_profile_digest: str | None = field(default=None, repr=False)
    receiving_request_guard: Callable[[], None] | None = field(default=None, repr=False)

    def child_for(self, command_id: str) -> ExecutiveSelectedChild | None:
        if type(self.children) is not tuple or len(self.children) > 64:
            return None
        matches = [child for child in self.children
                   if _selected_child_valid(child) and child.command_id == command_id]
        return matches[0] if len(matches) == 1 else None

    def _claim_guard(self, child: ExecutiveSelectedChild) -> Callable[[], None]:
        from control_plane.executive_service import ExecutiveControlService
        if (type(self.service) is not ExecutiveControlService or type(self.runtime) is not owner.Runtime
                or self.service._require_runtime() is not self.runtime
                or type(self.authority) is not CooHostProvider
                or type(self.context) is not PrincipalAdmissionContext
                or type(self.capability_profile_digest) is not str
                or len(self.capability_profile_digest) != 64
                or not callable(self.receiving_request_guard)):
            raise owner.StateConflict("selected child private host authority unavailable")
        def require_request():
            if self.service._require_runtime() is not self.runtime:
                raise owner.StateConflict("receiving selected-child Runtime changed")
            guard = self.receiving_request_guard
            if (inspect.iscoroutinefunction(guard)
                    or inspect.iscoroutinefunction(getattr(guard, "__call__", None))):
                raise owner.StateConflict("receiving selected-child request must be synchronous")
            guarded = guard()
            if guarded is not None:
                if inspect.iscoroutine(guarded):
                    guarded.close()
                raise owner.StateConflict("receiving selected-child request unavailable")
        def current_guard():
            require_request()
            self.authority.guard_dialogue(context=self.context,
                root_job_id=child.selection.root_job_id,
                capability_profile_digest=self.capability_profile_digest)
            require_request()
        return current_guard

    def _run(self, coroutine: Any) -> dict[str, Any]:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            coroutine.close()
            raise SelectedChildRefused("EXECUTIVE_SELECTED_CHILD_LOOP_REENTRANT")
        if (not isinstance(self.loop, asyncio.AbstractEventLoop)
                or not self.loop.is_running() or self.loop.is_closed()):
            coroutine.close()
            raise SelectedChildRefused("EXECUTIVE_SELECTED_CHILD_LOOP_UNAVAILABLE")
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        except Exception:
            coroutine.close()
            raise SelectedChildRefused("EXECUTIVE_SELECTED_CHILD_NOT_SCHEDULED") from None
        # After scheduling, even a generic owner exception is not a no-effect
        # receipt. Do not cancel: only the original command's status reconciles.
        return future.result(timeout=self.timeout)

    async def submit_async(self, command_id: str) -> dict[str, Any]:
        child = self.child_for(command_id)
        if child is None:
            return _selected_child_refusal("REFUSED", "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND")
        dispatch_started = False
        try:
            observed = await self.service.selected_child_status(
                job_id=child.selection.job_id, command_id=command_id)
            if observed.get("state") != "NOT_CLAIMED":
                return _envelope(observed, child)
            guard = self._claim_guard(child)
            guard()
            qualification = ExecutiveChildQualification(self.runtime, child.selection).qualify()
            if qualification.get("state") != "QUALIFIED":
                return _selected_child_refusal("REFUSED",
                    str(qualification.get("reason") or "EXECUTIVE_CHILD_REFUSED"), child)
            dispatch_started = True
            result = await self.service.dispatch_selected_child(
                job_id=child.selection.job_id, command_id=command_id,
                expected_selection=child.expected_selection(), admission_guard=guard)
            return _envelope(result, child)
        except (owner.StateConflict, ValueError):
            return _selected_child_refusal(
                "EFFECT_UNKNOWN" if dispatch_started else "REFUSED",
                "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN" if dispatch_started
                else "EXECUTIVE_SELECTED_CHILD_CLAIM_REFUSED", child)
        except Exception:
            return _selected_child_refusal(
                "EFFECT_UNKNOWN" if dispatch_started else "UNAVAILABLE",
                "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN" if dispatch_started
                else "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE", child)

    async def status_async(self, command_id: str) -> dict[str, Any]:
        child = self.child_for(command_id)
        if child is None:
            return _selected_child_refusal("REFUSED", "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND")
        try:
            result = await self.service.selected_child_status(
                job_id=child.selection.job_id, command_id=command_id)
            return _envelope(result, child)
        except Exception:
            return _selected_child_refusal("UNAVAILABLE", "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE", child)

    def submit(self, command_id: str) -> dict[str, Any]:
        child = self.child_for(command_id)
        if child is None:
            return _selected_child_refusal("REFUSED", "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND")
        try:
            return self._run(self.submit_async(command_id))
        except SelectedChildRefused as exc:
            return _selected_child_refusal("REFUSED", exc.reason, child)
        except Exception:
            return _selected_child_refusal("EFFECT_UNKNOWN", "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN", child)

    def status(self, command_id: str) -> dict[str, Any]:
        child = self.child_for(command_id)
        if child is None:
            return _selected_child_refusal("REFUSED", "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND")
        try:
            return self._run(self.status_async(command_id))
        except SelectedChildRefused as exc:
            return _selected_child_refusal("REFUSED", exc.reason, child)
        except Exception:
            return _selected_child_refusal("UNAVAILABLE", "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE", child)


_SELECTED_CHILD_COMPOSITION: ExecutiveSelectedChildComposition | None = None
_SELECTED_CHILD_LOCK = threading.Lock()


def install_selected_child_composition(
    composition: ExecutiveSelectedChildComposition | None,
) -> None:
    """Install one trusted-host production composition in this process.

    Registration stores the binding only. It admits nothing, reads no
    credential, and starts no worker. The default is unbound.
    """

    global _SELECTED_CHILD_COMPOSITION
    if composition is not None and not isinstance(
        composition, ExecutiveSelectedChildComposition
    ):
        raise TypeError("selected child composition is not the reviewed binding")
    with _SELECTED_CHILD_LOCK:
        _SELECTED_CHILD_COMPOSITION = composition


def clear_selected_child_composition() -> None:
    """Remove the installed composition and restore the unbound default."""

    global _SELECTED_CHILD_COMPOSITION
    with _SELECTED_CHILD_LOCK:
        _SELECTED_CHILD_COMPOSITION = None


def selected_child_composition() -> ExecutiveSelectedChildComposition | None:
    """Return the installed composition, if the host installed one."""

    with _SELECTED_CHILD_LOCK:
        return _SELECTED_CHILD_COMPOSITION

"""Read-only qualification of a host-selected Executive child.

This module is imported explicitly by a trusted host. It is not an admission
port, a carrier, or a model-visible tool. A successful observation grants no
authority to launch, retry, review, cancel, or consume a result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from control_plane import executive_runtime as owner
from control_plane.executive_delegation_identity import derive_delegation_identity

QUALIFICATION_SCHEMA = "mastermind.hermes_delegate.executive_child_observation/v1"


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

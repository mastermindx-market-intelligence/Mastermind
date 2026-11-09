"""Read one exact principal attention anchor from the existing Wake ledger.

The host supplies a work/root scope already derived from its authenticated
principal. This reader does not authenticate that principal, select a child,
assert the message's type, or authorize a send. The caller must revalidate the
live attempt and Relay message before using the anchor at the COMMIT boundary.
Acknowledging attention is not resolving its underlying source obligation.
"""
from __future__ import annotations

from dataclasses import dataclass

from common.executive_workspace_contract import _check_work_ref
from control_plane.dialogue_source_resolution import PhysicalDialogueSourceIdentity
from control_plane.executive_runtime import Runtime
from control_plane.wake_events import (
    JOB_ID_RE, WAKE_ID_RE, SourceKind, WakeKind, WakeObligation,
)
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository


class PrincipalDialogueObligationUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PRINCIPAL_DIALOGUE_OBLIGATION_UNAVAILABLE")


@dataclass(frozen=True)
class PrincipalDialogueObligationRead:
    obligation: WakeObligation
    physical_source: PhysicalDialogueSourceIdentity
    observed_event_ids: tuple[int, ...]


def read_principal_dialogue_obligation(
    runtime: Runtime, *, obligation_id: str, expected_work_ref: str,
    expected_root_job_id: str,
) -> PrincipalDialogueObligationRead:
    """Read an unresolved source for fresh decision acquisition."""
    return _read_anchor(runtime, obligation_id=obligation_id,
        expected_work_ref=expected_work_ref, expected_root_job_id=expected_root_job_id,
        require_unresolved=True)


def read_original_principal_dialogue_obligation(
    runtime: Runtime, *, obligation_id: str, expected_work_ref: str,
    expected_root_job_id: str,
) -> PrincipalDialogueObligationRead:
    """Read the immutable original anchor, including after source resolution.

    Only for receipt reconciliation. This read supplies no fresh-effect authority;
    decision acquisition must continue using read_principal_dialogue_obligation.
    """
    return _read_anchor(runtime, obligation_id=obligation_id,
        expected_work_ref=expected_work_ref, expected_root_job_id=expected_root_job_id,
        require_unresolved=False)


def _read_anchor(runtime, *, obligation_id, expected_work_ref,
                 expected_root_job_id, require_unresolved):
    """Read the supplied original obligation; never fall back to another one.

    Scope is trusted host input, not an authorization-bearing tool argument.
    The existing repository hydrates and causally validates the entire selected
    stream, including source/physical identity correlation. No record is added.
    """
    try:
        if (type(runtime) is not Runtime or type(obligation_id) is not str
                or WAKE_ID_RE.fullmatch(obligation_id) is None
                or type(expected_work_ref) is not str
                or not _check_work_ref(expected_work_ref)
                or type(expected_root_job_id) is not str
                or JOB_ID_RE.fullmatch(expected_root_job_id) is None):
            raise PrincipalDialogueObligationUnavailable()
        rows = WakeLedgerRepository(runtime).list_records(obligation_id)
        if not rows or (require_unresolved and any(
                row.record.phase is LedgerPhase.SOURCE_RESOLVED for row in rows)):
            raise PrincipalDialogueObligationUnavailable()
        requested = rows[0].record
        obligation, physical = requested.obligation, requested.physical_source
        if (requested.phase is not LedgerPhase.WAKE_REQUESTED
                or type(obligation) is not WakeObligation
                or type(physical) is not PhysicalDialogueSourceIdentity
                or obligation.obligation_id != obligation_id
                or obligation.wake_kind is not WakeKind.DIALOGUE_TURN_PENDING
                or obligation.source_kind is not SourceKind.AGENT_DIALOGUE_ATTENTION
                or obligation.declared_target_seat != "coo"
                or physical.target_seat != "coo"
                or obligation.source_workstream != expected_work_ref
                or obligation.root_job_id != expected_root_job_id
                or physical.candidate.root_job_id != expected_root_job_id
                or physical.candidate.job_id == expected_root_job_id):
            raise PrincipalDialogueObligationUnavailable()
        return PrincipalDialogueObligationRead(
            obligation, physical, tuple(row.event.event_id for row in rows),
        )
    except Exception:
        # Do not disclose whether a foreign source exists or expose owner errors.
        raise PrincipalDialogueObligationUnavailable() from None

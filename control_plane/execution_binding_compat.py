"""Shared adapter-side ``ExecutionBinding.v1`` compatibility (pure).

The adapter lanes in this program accept the broker-issued
``ExecutionBinding.v1`` through this one pure check.  Compatibility only —
this module neither activates a lane nor invents a binding; a spec without a
placement admission stays a legacy spec.

Provenance: lifted verbatim from PR #2330 (branch
``feat/mmos-v1-wo16-17-deepseek-compat-ledger``, head ``fe315477``, file
``control_plane/execution_binding_compat.py``), because that branch is not an
ancestor of this PR's base (``feat/mmos-v1-shared-contracts``) and the WO-10
adapter needs the same gate.  Extended here (PR #2311 review M1) with the
opt-in ``require_issued`` / ``current_fence`` refused cases — fence currency
and non-empty lease — so the WO-16 lanes' behavior with ``required=...`` only
is byte-identical to the #2330 original, and the copy converges to this
shared module when the branches merge.

Law: ``control_plane/child_execution_contracts.py`` (WO-02) and Rev 4
§S3.D — the binding is issued by the sole placement authority
(``broker.claim_job``, WO-14), contains opaque grant references and never
credentials, and ``effective_complexity`` is the admitted class the child
cannot self-promote.
"""
from __future__ import annotations

from typing import Any, Mapping

from control_plane.child_execution_contracts import ExecutionBinding

__all__ = [
    "ExecutionBindingCompatError",
    "binding_for_launch_spec",
]

#: WO-16 typed refusal codes (adapters surface them verbatim).
BINDING_REQUIRED = "EXECUTION_BINDING_REQUIRED"
BINDING_TYPE_INVALID = "EXECUTION_BINDING_TYPE_INVALID"
BINDING_IDENTITY_MISMATCH = "EXECUTION_BINDING_IDENTITY_MISMATCH"
#: PR #2311 review M1 extension (opt-in via ``require_issued`` /
#: ``current_fence``): fence currency and non-empty lease refusals.
BINDING_FENCE_NOT_CURRENT = "EXECUTION_BINDING_FENCE_NOT_CURRENT"
BINDING_LEASE_REQUIRED = "EXECUTION_BINDING_LEASE_REQUIRED"


class ExecutionBindingCompatError(ValueError):
    """The lane cannot accept this binding as the admitted assignment."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _spec_field(spec: Any, name: str) -> str:
    value = getattr(spec, name, "")
    return str(value) if value is not None else ""


def _identity_problems(binding: ExecutionBinding, spec: Any) -> str:
    mismatches = []
    if binding.job_ref != _spec_field(spec, "job_id"):
        mismatches.append(f"job_ref {binding.job_ref!r} != spec.job_id "
                          f"{_spec_field(spec, 'job_id')!r}")
    if binding.attempt_ref != _spec_field(spec, "run_id"):
        mismatches.append(f"attempt_ref {binding.attempt_ref!r} != spec.run_id "
                          f"{_spec_field(spec, 'run_id')!r}")
    spec_worker = _spec_field(spec, "worker_id")
    if binding.worker_id and spec_worker and binding.worker_id != spec_worker:
        mismatches.append(f"worker_id {binding.worker_id!r} != spec.worker_id "
                          f"{spec_worker!r}")
    return "; ".join(mismatches)


def _issued_problems(
    binding: ExecutionBinding, current_fence: int | None, *, require_issued: bool
) -> list[tuple[str, str]]:
    """Issuance and current-fence checks selected independently by the caller."""
    problems = []
    if not require_issued and current_fence is None:
        return problems
    if require_issued and not binding.lease_expiry:
        problems.append((
            BINDING_LEASE_REQUIRED,
            "lease_expiry is empty: a broker claim always carries the "
            "lease deadline that this gate's expiry check needs"))
    fence = binding.fence_counter
    if type(fence) is not int or fence < 1:
        problems.append((
            BINDING_FENCE_NOT_CURRENT,
            f"fence_counter {fence!r} is not a broker-issued claim fence "
            "(must be an int >= 1: coordinator attempts carry "
            "fence_generation > 0 and re-claims only get fence + 1; "
            "fence_counter 0 is the WO-02 contract default of a binding "
            "nobody issued)"))
    elif current_fence is not None:
        if type(current_fence) is not int or current_fence < 1:
            problems.append((
                BINDING_FENCE_NOT_CURRENT,
                f"broker current fence {current_fence!r} is not a positive int"))
        elif fence != current_fence:
            problems.append((
                BINDING_FENCE_NOT_CURRENT,
                f"fence_counter {fence!r} is not the broker's current fence "
                f"{current_fence!r} for this attempt"))
    return problems


def binding_for_launch_spec(
    spec: Any,
    binding: ExecutionBinding | Mapping[str, Any] | None,
    *,
    required: bool = False,
    require_issued: bool = False,
    current_fence: int | None = None,
) -> ExecutionBinding | None:
    """Validate an admitted binding against one launch spec, or refuse.

    ``required=True`` marks a binding-required lane (a placement child per
    WO-13/WO-14): a missing binding is refused before any lifecycle effect.
    When ``binding`` is None and not required, the call is a legacy passthrough
    returning None.  A supplied binding is accepted as the canonical
    ``ExecutionBinding.v1`` (mapping payloads are parsed, never re-invented)
    and must fence exactly this spec's Job/Attempt/Worker identity.  The
    admitted class is ``binding.effective_complexity`` (canonical long name,
    validated by the binding record itself).

    ``require_issued=True`` (PR #2311 review M1) additionally refuses a
    binding that cannot have come from a broker claim: an empty
    ``lease_expiry`` and a ``fence_counter`` that is not an int >= 1 (0 is
    the WO-02 contract default of a never-issued record).  ``current_fence``,
    when the caller holds the broker's current fence generation for this
    attempt (the authenticated owner channel can supply it), must equal
    ``binding.fence_counter`` — refusing a stale/drifted fence at this seam.
    These checks are independently opt-in. With neither requested, only the
    existing type/identity compatibility is verified; that alone is not proof
    of a current broker-issued launch grant. PR #2330 compatibility is retained.
    """
    if binding is None:
        if required:
            raise ExecutionBindingCompatError(
                BINDING_REQUIRED,
                "this lane executes a placement child and requires "
                "ExecutionBinding.v1 from broker.claim_job")
        return None
    if isinstance(binding, ExecutionBinding):
        admitted = binding
    elif isinstance(binding, Mapping):
        admitted = ExecutionBinding.from_dict(binding)
    else:
        raise ExecutionBindingCompatError(
            BINDING_TYPE_INVALID,
            f"binding must be ExecutionBinding.v1 or its mapping, got {type(binding).__name__}")
    problems = _identity_problems(admitted, spec)
    if problems:
        raise ExecutionBindingCompatError(BINDING_IDENTITY_MISMATCH, problems)
    lease_or_fence = _issued_problems(
        admitted, current_fence, require_issued=require_issued)
    for code, detail in lease_or_fence:
        raise ExecutionBindingCompatError(code, detail)
    return admitted

"""WO-16 adapter-side ``ExecutionBinding.v1`` compatibility (pure).

The incumbent DeepSeek lane (``OpenCodeWorkerAdapter``) and the ACP lane
(``AcpWorkerAdapter``) accept the broker-issued ``ExecutionBinding.v1`` and
the admitted class through this one pure check.  Compatibility only — this
module neither activates a lane nor invents a binding; a spec without a
placement admission stays a legacy spec.

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


def binding_for_launch_spec(
    spec: Any,
    binding: ExecutionBinding | Mapping[str, Any] | None,
    *,
    required: bool = False,
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
    return admitted

"""Qualified S19 result input for a prospective source proposal, never a grant.

This adapter reads the existing terminal owner and retains one request-local
materialization. The source publisher may freeze these exact bytes in its
existing original-input owner before an effect. After publication changes the
canonical WS, reconciliation belongs to that original source operation; this
object must never pretend the old planning source is still current.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json

from common import direct_native_result_contract as result_wire
from control_plane import direct_native_execution as native
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.foreground_operation import ForegroundOperationClosed, ForegroundOperationRefusal
from control_plane import project_planning_admission as planning

SCHEMA = "mastermind.project_plan_proposal_result.v1"
_SEAL = object()


class PlanResultUnavailable(ValueError):
    def __init__(self, code="RESULT_UNAVAILABLE"):
        self.code = code
        super().__init__(code)


def _canonical(value):
    return result_wire.canonical_bytes(value)


def _observe(runtime, *, result_reader, selection, source, executive_admission):
    if (type(runtime) is not Runtime or type(result_reader) is not Runtime or type(source) is not planning.ProjectPlanningSource
            or type(executive_admission) is not native.DirectNativeAdmission):
        raise PlanResultUnavailable()
    selected = result_wire.validate_selection(selection)
    if not runtime.store.path.samefile(result_reader.store.path):
        raise PlanResultUnavailable()
    access = planning.requalify_original(runtime, job_id=selected["job_id"],
        source=source, executive_admission=executive_admission)
    before = runtime.jobs.direct_native_provenance(selected["job_id"])
    if type(before) is not dict or "project_planning" not in before:
        raise PlanResultUnavailable()
    context = planning.normalize_context(before["project_planning"])
    if (selected["work_ref"] != context["work_ref"]
            or access.principal_scope != context["principal_scope"]
            or context != source.material()):
        raise PlanResultUnavailable()
    response = result_wire.validate_response(Runtime.read_direct_native_result_bounded(
        result_reader, selected, access=access))
    if (response["schema"] != result_wire.SCHEMA
            or response["availability"] != "AVAILABLE"
            or response["selection"] != selected):
        raise PlanResultUnavailable("NO_COMPLETED_RESULT")
    # AVAILABLE in this original schema is the Runtime's Event-backed exact
    # COMPLETED proof. Cancelled, incomplete and historical/foreign selections
    # cannot substitute a result DTO or a digest for the actual read owner.
    payload = result_wire.validate_payload({key: response["result"][key]
                                            for key in result_wire.PAYLOAD_KEYS})
    terminal_digest = result_wire.hex_digest(response["result"]["result_digest"])
    planning.requalify_original(runtime, job_id=selected["job_id"],
        source=source, executive_admission=executive_admission).check()
    if (not runtime.store.path.samefile(result_reader.store.path)
            or runtime.jobs.direct_native_provenance(selected["job_id"]) != before):
        raise PlanResultUnavailable("RESULT_SOURCE_CHANGED")
    return dict(schema=SCHEMA, selection=selected, stage=context["stage"],
        result_digest=terminal_digest, payload=payload,
        payload_sha256=hashlib.sha256(_canonical(payload)).hexdigest(),
        planning_context_sha256=hashlib.sha256(_canonical(context)).hexdigest(),
        planning_request_sha256=context["request_sha256"],
        planning_input_artifact_sha256=context["input_artifact_sha256"],
        principal_scope=context["principal_scope"], origin_root=context["origin_root"],
        budget_ref=context["budget_ref"], return_ref=context["return_ref"])


@dataclass(frozen=True, slots=True)
class QualifiedPlanningResult:
    """Private request-local evidence, not publication/execution authority."""
    _seal: object = field(repr=False)
    _runtime: Runtime = field(repr=False)
    _reader: Runtime = field(repr=False)
    _source: planning.ProjectPlanningSource = field(repr=False)
    _admission: native.DirectNativeAdmission = field(repr=False)
    _selection: bytes = field(repr=False)
    _material: bytes = field(repr=False)

    def material(self):
        if self._seal is not _SEAL:
            raise PlanResultUnavailable()
        return json.loads(self._material)

    def check(self):
        if self._seal is not _SEAL:
            raise PlanResultUnavailable()
        try:
            observed = _observe(self._runtime, result_reader=self._reader, selection=json.loads(self._selection),
                source=self._source, executive_admission=self._admission)
        except (ValueError, TypeError, KeyError, AttributeError, OSError, StateConflict,
                ForegroundOperationClosed, ForegroundOperationRefusal):
            raise PlanResultUnavailable() from None
        # Consumption is deliberately not part of this material: an original
        # parent's separate acknowledgment cannot change terminal result bytes.
        if _canonical(observed) != self._material:
            raise PlanResultUnavailable("RESULT_SOURCE_CHANGED")
        return copy.deepcopy(observed)


def capture_completed_planning_result(runtime, *, result_reader, selection, source, executive_admission):
    """Use the genuine existing Runtime/S19 owners; never accept supplied DATA."""
    try:
        selected = result_wire.validate_selection(selection)
        material = _observe(runtime, result_reader=result_reader, selection=selected, source=source,
                            executive_admission=executive_admission)
        return QualifiedPlanningResult(_SEAL, runtime, result_reader, source, executive_admission,
            _canonical(selected), _canonical(material))
    except PlanResultUnavailable:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError, StateConflict, ForegroundOperationClosed, ForegroundOperationRefusal):
        raise PlanResultUnavailable() from None

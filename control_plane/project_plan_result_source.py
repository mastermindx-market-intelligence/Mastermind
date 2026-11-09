"""Qualified S19 result input for a prospective source proposal, never a grant.

This adapter reads the existing terminal owner and retains one request-local
materialization. The source publisher may freeze these exact bytes in its
existing original-input owner before an effect. After publication changes the
canonical WS, reconciliation belongs to that original source operation; this
object must never pretend the old planning source is still current.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
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
_OBSERVATION = object()
_CURRENT_OBSERVATION = ContextVar('original_planning_consumed_observation',default=None)


class PlanResultUnavailable(ValueError):
    def __init__(self, code="RESULT_UNAVAILABLE"):
        self.code = code
        super().__init__(code)


@dataclass(eq=False, repr=False)
class _ConsumedPlanningObservation:
    seal: object
    result: object
    source: object
    binding: object
    identity: tuple
    selection: bytes
    material_bytes: bytes
    active: bool = True

    def material(self, expected_result):
        if (self.seal is not _OBSERVATION or not self.active
                or _CURRENT_OBSERVATION.get() is not self
                or type(expected_result) is not QualifiedPlanningResult
                or self.result is not expected_result or self.source is not expected_result._source
                or self.binding is not self.source._observation_binding
                or self.selection != expected_result._selection
                or self.material_bytes != expected_result._material):
            raise PlanResultUnavailable()
        current = self.source._read_observation_identity()
        if (type(current) is not tuple or len(current) != len(self.identity)
                or any(a is not b for a,b in zip(current,self.identity))):
            raise PlanResultUnavailable()
        return json.loads(self.material_bytes)


def _canonical(value):
    return result_wire.canonical_bytes(value)


def _observe(runtime, *, result_reader, selection, source, executive_admission):
    return _observe_response(runtime,result_reader=result_reader,selection=selection,
        source=source,executive_admission=executive_admission)[0]


def _observe_response(runtime, *, result_reader, selection, source, executive_admission):
    if type(source) is not planning.ProjectPlanningSource:raise PlanResultUnavailable()
    # All operations in this body are original-record reads. The nominal owner
    # completes its full outer postcheck before any captured result escapes.
    with source.read_scope():
        return _observe_in_scope(runtime,result_reader=result_reader,selection=selection,
            source=source,executive_admission=executive_admission)


def _observe_in_scope(runtime, *, result_reader, selection, source, executive_admission):
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
    material = dict(schema=SCHEMA, selection=selected, stage=context["stage"],
        result_digest=terminal_digest, payload=payload,
        payload_sha256=hashlib.sha256(_canonical(payload)).hexdigest(),
        planning_context_sha256=hashlib.sha256(_canonical(context)).hexdigest(),
        planning_request_sha256=context["request_sha256"],
        planning_input_artifact_sha256=context["input_artifact_sha256"],
        principal_scope=context["principal_scope"], origin_root=context["origin_root"],
        budget_ref=context["budget_ref"], return_ref=context["return_ref"])
    # Consumption is not part of immutable terminal material. Keep the actual
    # same qualified response available to the separate pure consumption proof;
    # this is local return data, never a cached observation or authority.
    return material, copy.deepcopy(response["consumption"])


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

    @contextmanager
    def read_scope(self):
        """Group a pure consumer through its existing host-owned source scope.

        This yields no view, grant or receipt. The original source callback
        owns all nominal/currentness/deadline checks and the full postcheck.
        No private retention, Event, consumption or publication belongs here.
        """
        if self._seal is not _SEAL or type(self._source) is not planning.ProjectPlanningSource:
            raise PlanResultUnavailable()
        with self._source.read_scope():yield

    def require_consumed(self):
        return self._consumed_material()[1]

    @contextmanager
    def _consumed_observation(self):
        # The source's actual factory issuer authenticates the full lexical
        # bracket. A copied Source, generic capture or caller callback cannot
        # substitute for that issuer. No observation survives this scope.
        with self.read_scope():
            observed, _ = self._consumed_material()
            identity = self._source._read_observation_identity()
            if _canonical(observed) != self._material:
                raise PlanResultUnavailable('RESULT_SOURCE_CHANGED')
            observation = _ConsumedPlanningObservation(_OBSERVATION,self,self._source,
                self._source._observation_binding,identity,self._selection,self._material)
            token = _CURRENT_OBSERVATION.set(observation)
            try:
                yield observation
            finally:
                observation.active = False
                _CURRENT_OBSERVATION.reset(token)

    def _consumed_material(self):
        """One current bounded response proves terminal bytes and explicit Keep.

        The incumbent observation still checks the original access, exact store,
        principal/selection/digest and provenance before/after that read. Its
        full source scope closes before either copied value escapes. Every call
        performs a new observation; no result survives a private/Event effect.
        """
        if self._seal is not _SEAL:
            raise PlanResultUnavailable()
        # As before, an outer source postcheck failure is the original owner's
        # refusal, not normalized into a different result-read exception.
        with self.read_scope():
            try:
                observed, consumption = _observe_in_scope(self._runtime,
                    result_reader=self._reader,selection=json.loads(self._selection),
                    source=self._source,executive_admission=self._admission)
            except (ValueError, TypeError, KeyError, AttributeError, OSError, StateConflict,
                    ForegroundOperationClosed, ForegroundOperationRefusal):
                raise PlanResultUnavailable() from None
            if _canonical(observed) != self._material:
                raise PlanResultUnavailable('RESULT_SOURCE_CHANGED')
            if consumption['state'] != 'CONSUMED':
                raise PlanResultUnavailable('ORIGINAL_RESULT_NOT_CONSUMED')
            return copy.deepcopy(observed), copy.deepcopy(consumption)

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


def _capture_consumed_planning_result(runtime, *, result_reader, selection, source, executive_admission):
    """Private initial preparation proof from ONE genuine current response.

    The existing observation completes its full source postcheck before this
    sealed result can return. This is not a consumption write or a reusable
    observation: the service still observes freshly on every effect boundary.
    Public standalone completed-result capture retains its original semantics.
    """
    selected = result_wire.validate_selection(selection)
    # Keep the existing full source scope outside exception normalization so
    # its outer postcheck refusal remains authoritative and no value escapes.
    material, consumption = _observe_response(runtime, result_reader=result_reader,
        selection=selected, source=source, executive_admission=executive_admission)
    if consumption['state'] != 'CONSUMED':
        raise PlanResultUnavailable('ORIGINAL_RESULT_NOT_CONSUMED')
    return QualifiedPlanningResult(_SEAL, runtime, result_reader, source, executive_admission,
        _canonical(selected), _canonical(material))


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

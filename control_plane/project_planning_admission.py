"""Explicit first project request, composed into the incumbent native Runtime.

Publication is source data. Only the already-issued Executive execution access
can authorize this composition. No public frame, store, queue, worker/session
creator or automatic activation is installed here.
"""
from __future__ import annotations

from contextlib import contextmanager

import copy
from dataclasses import dataclass
import inspect
import re

from control_plane import direct_native_execution as native
from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader

SCHEMA = "mastermind.project_initial_planning.v1"
_SEAL = object()
_FIELDS = {"schema", "work_ref", "source", "publication",
           "operation_key", "request_sha256", "stage", "principal_scope",
           "origin_root", "return_ref", "budget_ref", "executive_authority_sha256", "input_artifact_sha256"}


def normalize_context(value):
    """Closed immutable references only; private request text never enters it."""
    from common.workspace_project_session_contract import validate_project_source
    from common.workspace_project_plan_contract import validate_selection
    from common.workspace_source_operation_contract import validate_lookup
    if type(value) is not dict or set(value) != _FIELDS or value["schema"] != SCHEMA:
        raise ValueError("project planning context is invalid")
    value = copy.deepcopy(value)
    selected = validate_selection({"work_ref":value["work_ref"]})
    value["source"] = validate_project_source(value["source"], selected)
    publication = value["publication"]
    if (type(publication) is not dict or set(publication) != {"request_id", "principal_scope", "event_id", "receipt_sha256"}
            or type(publication["event_id"]) is not int or publication["event_id"] <= 0):
        raise ValueError("project planning publication reference is invalid")
    validate_lookup(dict(schema="mastermind.workspace_source_operation_lookup.v1", action="publish_project_proposal",
        request_id=publication["request_id"],work_ref=value["work_ref"]))
    native.require_digest(publication["principal_scope"])
    native.require_digest(publication["receipt_sha256"])
    for key in ("request_sha256", "principal_scope", "executive_authority_sha256", "input_artifact_sha256"):
        native.require_digest(value[key])
    if value["stage"] not in {"clarify", "plan"}:
        raise ValueError("project planning stage is invalid")
    for key in ("operation_key", "origin_root", "return_ref", "budget_ref"):
        if type(value[key]) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value[key]) is None:
            raise ValueError("project planning reference is invalid")
    return value


def _sync(guard):
    if not callable(guard) or inspect.iscoroutinefunction(guard) or inspect.iscoroutinefunction(getattr(guard, "__call__", None)):
        raise ValueError("project planning authority guard unavailable")
    result = guard()
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result): result.close()
        raise ValueError("project planning authority guard must be synchronous")
    return result


_READ_OBSERVATION_BINDING = object()


@dataclass(frozen=True, slots=True)
class _ReadObservationBinding:
    seal: object
    source: object
    guard: object
    read_scope: object


_CANONICAL_GROUNDING_BINDING = object()

@dataclass(frozen=True, slots=True)
class _CanonicalGroundingBinding:
    seal: object
    source: object
    guard: object


@dataclass(frozen=True, slots=True)
class ProjectPlanningSource:
    """Nominal installed source + distinct incumbent Executive capability.

    The current authority owner returns the complete closed context on every
    check, including original root, budget and return custody. A digest-only
    permission callback cannot issue this object.
    """
    _seal: object
    _reader: AgentOsProjectCreationReader
    _executive: native.DirectNativeExecutionAccess
    _material: bytes
    _authority_guard: object
    _input_owner: ProjectPlanningInput
    _events: object
    _publication_guard: object
    _canonical_source_reader: object = None
    _read_scope: object = None
    _observation_binding: object = None
    _canonical_grounding_binding: object = None

    def _grounding_macro_commit(self):
        import json
        # Private nominal source composition only. Public/caller DATA never
        # selects this branch; legacy sources keep their exact CREATE commit.
        if self._seal is not _SEAL:
            raise ValueError('project planning grounding owner unavailable')
        binding = self._canonical_grounding_binding
        if binding is None:
            return normalize_context(json.loads(self._material))['source']['commit']
        if (type(binding) is not _CanonicalGroundingBinding
                or binding.seal is not _CANONICAL_GROUNDING_BINDING
                or binding.source is not self or not callable(binding.guard)):
            raise ValueError('project planning grounding owner unavailable')
        value = binding.guard(self)
        if type(value) is not str or re.fullmatch(r'[0-9a-f]{40}', value) is None:
            raise ValueError('project planning grounding source unavailable')
        return value

    def _read_observation_identity(self):
        binding = self._observation_binding
        if (self._seal is not _SEAL or type(binding) is not _ReadObservationBinding
                or binding.seal is not _READ_OBSERVATION_BINDING
                or binding.source is not self or binding.read_scope is not self._read_scope
                or not callable(binding.guard)):
            raise ValueError('original planning observation issuer unavailable')
        return binding.guard(self)

    @contextmanager
    def read_scope(self):
        """Private pure-read bracket; never an authority or effect allowance."""
        if self._seal is not _SEAL:raise ValueError("project planning source is not host-issued")
        if self._read_scope is None:
            yield
        else:
            with self._read_scope():yield

    def material(self):
        import json
        if self._seal is not _SEAL:
            raise ValueError("project planning source is not host-issued")
        return normalize_context(json.loads(self._material))

    def check(self):
        material = self.material()
        if type(self._reader) is not AgentOsProjectCreationReader or type(self._executive) is not native.DirectNativeExecutionAccess:
            raise ValueError("project planning source/Executive owner unavailable")
        self._executive.check()
        if (self._executive.principal_scope != material["principal_scope"]
                or self._executive.work_ref != material["work_ref"]
                or self._executive.authority_generation_digest != material["executive_authority_sha256"]):
            raise ValueError("project planning Executive identity differs")
        if normalize_context(_sync(self._authority_guard)) != material:
            raise ValueError("project planning current authority differs")
        if type(self._input_owner) is not ProjectPlanningInput:
            raise ValueError("project planning original private input unavailable")
        from control_plane.workspace_source_operations import SourceOperationEvents
        if (type(self._events) is not SourceOperationEvents
                or self._events.store is not self._input_owner.supervisor.runtime.store):
            raise ValueError("project planning publication Event owner differs")
        publication = material["publication"]
        lookup = dict(schema="mastermind.workspace_source_operation_lookup.v1",action="publish_project_proposal",
            request_id=publication["request_id"],work_ref=material["work_ref"])
        SourceOperationEvents.read_publication(self._events,lookup,publication["principal_scope"],
            event_id=publication["event_id"],receipt_sha256=publication["receipt_sha256"],
            source={key:value for key,value in material["source"].items() if key != "request_sha256"},
            guard=self._publication_guard)
        self._input_owner.read(material)
        # Force the nominal facade implementation; caller overrides cannot
        # turn a DTO or filesystem path into installed-source qualification.
        observed = (AgentOsProjectCreationReader.read(self._reader,
            work_ref=material["work_ref"], record_commit=material["source"]["commit"],
            expected_current_macro_sha=material["source"]["commit"]) if self._canonical_source_reader is None
            else _sync(self._canonical_source_reader))
        if observed != material["source"]:
            raise ValueError("project planning canonical source changed")
        self._executive.check()
        if normalize_context(_sync(self._authority_guard)) != material:
            raise ValueError("project planning authority changed during source observation")


def _issue_source(*, reader, executive, context, authority_guard, input_owner, events, publication_guard, canonical_source_reader=None, read_scope=None, observation_guard=None, canonical_grounding_guard=None):
    """Private host join; publication/Workspace grants cannot call this alone."""
    value = ProjectPlanningSource(_SEAL, reader, executive,
        native.canonical(normalize_context(context)), authority_guard, input_owner,events,publication_guard,canonical_source_reader,read_scope)
    value.check()
    if observation_guard is not None:
        if not callable(observation_guard):raise ValueError('original planning observation issuer unavailable')
        object.__setattr__(value,'_observation_binding',_ReadObservationBinding(_READ_OBSERVATION_BINDING,value,observation_guard,read_scope))
    if canonical_grounding_guard is not None:
        if not callable(canonical_grounding_guard):raise ValueError('project planning grounding owner unavailable')
        object.__setattr__(value,'_canonical_grounding_binding',_CanonicalGroundingBinding(
            _CANONICAL_GROUNDING_BINDING,value,canonical_grounding_guard))
    return value


def operation_intent_id(context):
    return "ceo-project-planning-" + native.digest({"principal_scope": context["principal_scope"],
        "operation_key": context["operation_key"]})[:40]


def _input_identity(context):
    # Artifact hash is the output of custody; it cannot enter its own header.
    fingerprint = native.digest({key:value for key,value in context.items() if key != "input_artifact_sha256"})
    return dict(command_id="project-planning-input:" + native.digest({"principal_scope":context["principal_scope"],
        "operation_key":context["operation_key"]})[:40], issuer_scope_sha256=context["principal_scope"],
        fingerprint_sha256=fingerprint)


class ProjectPlanningInput:
    """Semantic wrapper over the incumbent Supervisor's private artifact custody.

    This owns no directory scheme or second store; the existing bounded,
    no-follow immutable TerminalOriginalInputArtifacts owner retains all bytes.
    """
    def __init__(self, supervisor):
        from control_plane.executive_supervisor import ExecutiveSupervisor
        if type(supervisor) is not ExecutiveSupervisor:
            raise ValueError("project planning requires its actual Supervisor")
        self.supervisor = supervisor

    def prepare(self, context, payload):
        from control_plane import ceo_intent
        from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts
        preliminary = normalize_context({**context, "input_artifact_sha256":"0"*64})
        if type(payload) is not bytes or not payload or native.hashlib.sha256(payload).hexdigest() != preliminary["request_sha256"]:
            raise ValueError("project planning original private input differs")
        command = ceo_intent.command_id_for(operation_intent_id(preliminary))
        if self.supervisor.runtime.store.find_event_by_command_id(command) is not None:
            raise ValueError("project planning original command already exists; reconcile only")
        reference = TerminalOriginalInputArtifacts(self.supervisor.runs_root).prepare(**_input_identity(preliminary),payload=payload)
        return reference.artifact_sha256

    def read(self, context):
        from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts, TerminalInputError
        material = normalize_context(context)
        try:
            payload = TerminalOriginalInputArtifacts(self.supervisor.runs_root).read(**_input_identity(material),
                expected_artifact_sha256=material["input_artifact_sha256"])
        except TerminalInputError:
            raise ValueError("project planning original private input unavailable") from None
        if native.hashlib.sha256(payload).hexdigest() != material["request_sha256"]:
            raise ValueError("project planning original private bytes differ")
        return payload

    def turn_input(self, runtime, job_id, *, source, executive_admission):
        """Existing adapter TurnInputLoader calls this only for its exact Job."""
        if self is not source._input_owner or self.supervisor.runtime is not runtime:
            raise ValueError("project planning input/Runtime custody differs")
        access = requalify_original(runtime,job_id=job_id,source=source,executive_admission=executive_admission)
        access.check()
        payload = self.read(source.material())
        text = payload.decode("utf-8", errors="strict")
        access.check()
        return text


def compose_admission(*, source, executive_admission):
    """Keep source/authority checks live at Job creation and fresh Attempt claim."""
    if type(source) is not ProjectPlanningSource:
        raise ValueError("project planning requires its actual source owner")
    source.check()
    if (type(executive_admission) is not native.DirectNativeAdmission
            or executive_admission._execution_access is not source._executive
            or executive_admission._project_planning is not None):
        raise ValueError("project planning requires its original Executive admission")
    executive_admission.check()
    context = source.material()
    generation = native.digest(context)

    def current():
        source.check()
        return native.digest(source.material())

    access = native._issue_access(context["principal_scope"], context["work_ref"], generation, current)
    execution = native._issue_execution_access(access, source.check)
    # Retain the real Executive commission and managed workspace owner. The
    # supplemental Macro source does not change repository/adapter authority.
    return native._issue_admission(access, executive_admission.source, executive_admission.binding,
        execution_access=execution, project_planning=context)


def submit_initial_request(runtime, *, source, executive_admission, request, grounding, workspace_root,
                           fresh_admission_observer=None):
    """One explicit request -> one canonical Job; never dispatch/open a session.

    Request text must already be held by the incumbent private turn-input
    owner. Runtime receives a fixed public objective and only its byte digest.
    The original operation uses the canonical intent command/idempotency sink.
    """
    from control_plane import ceo_intent, ceo_request
    if type(source) is not ProjectPlanningSource:
        raise ValueError("project planning source owner absent")
    context = source.material()
    if source._input_owner.supervisor.runtime is not runtime:
        raise ValueError("project planning Runtime and private input owner differ")
    if (type(request) is not dict or set(request) != {"operation_key", "stage", "request_sha256"}
            or any(request[key] != context[key] for key in request)):
        raise ValueError("project planning original request differs")
    if grounding.get("macro_sha") != source._grounding_macro_commit():
        raise ValueError("project planning grounding differs from canonical source")
    admission = compose_admission(source=source, executive_admission=executive_admission)
    intent_id = operation_intent_id(context)
    operation = intent_id[4:]
    normalized = ceo_request.normalize_high_level_request(dict(operation_key=operation,
        objective="Initial project clarification" if context["stage"] == "clarify" else "Initial project planning",
        department="executive-infrastructure", priority=0, execution_profile="native_research_only",
        workstream=context["work_ref"], attempt_limit=1))
    intent = ceo_request.build_trusted_envelope(normalized, intent_id=intent_id,
        workspace_root=str(workspace_root), grounding=grounding)
    intent.update(schema=ceo_intent.INTENT_SCHEMA_DIRECT, intent_kind="direct_native_readonly", business_impact="routine")
    intent["project_planning_sha256"] = native.digest(context)
    # The closed planning context is part of the canonical intent fingerprint,
    # carried through the private admission rather than any public payload.
    return ceo_intent.submit_intent(runtime, intent, workspace_root=workspace_root, direct_admission=admission,
        fresh_admission_observer=fresh_admission_observer)


def requalify_original(runtime, *, job_id, source, executive_admission):
    """Return the SAME original access for status/result/claim, never resubmit.

    The existing service, Supervisor and native result/consumption owner use
    this access. Rehydration cannot adopt another root/request/budget/receiver.
    """
    if type(source) is not ProjectPlanningSource or source._input_owner.supervisor.runtime is not runtime:
        raise ValueError("project planning original Runtime owner differs")
    admission = compose_admission(source=source, executive_admission=executive_admission)
    if runtime.jobs.direct_native_provenance(job_id) != native.admission_material(admission):
        raise ValueError("project planning original Runtime binding differs")
    return admission._execution_access

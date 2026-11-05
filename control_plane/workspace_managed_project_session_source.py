"""Read the existing retained managed-session owner without continuation authority.

No broker/provider start, session selection registry, listener or fallback owner.
The current fixed Workspace reader supplies the principal/catalogue/release
bracket; this source accepts only the existing work/root selector.
"""
from __future__ import annotations

from common import workspace_project_session_contract as wire
from control_plane import ceo_intent
from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, RetainedNativeOperatorSession
from control_plane.operator_harness_contract import OperationId
from control_plane.operator_harness_wire import requested_execution_profile, to_wire
from control_plane.operator_materialization_receipt import requested_profile_digest
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from control_plane.workspace_project_session import read_creation_evidence, compose_project_session_association


class ExistingManagedProjectSessionSource:
    """Bound to one existing control service, sealed Macro reader and supervisor."""
    def __init__(self, service, source_reader):
        from control_plane.executive_service import ExecutiveControlService
        if type(service) is not ExecutiveControlService or type(source_reader) is not AgentOsProjectCreationReader:
            raise ValueError("source_unavailable")
        self._service = service
        self._source_reader = source_reader

    def _current(self, selected):
        service = self._service
        if service._closing or service._service_state != "READY":
            raise ValueError("source_unavailable")
        runtime = service._require_runtime()
        supervisor = service.operator_supervisor
        dispatch = service._native_operator_dispatch
        retained = getattr(dispatch, "retained", None)
        if (type(supervisor) is not ExecutiveOperatorSupervisor
                or type(retained) is not RetainedNativeOperatorSession
                or retained.owner is not supervisor or supervisor.runtime is not runtime
                or retained.job.root_job_id != selected["root_job_id"]
                or dispatch.job_id != retained.job.job_id
                or not isinstance(retained.adapter, RemoteOperatorHarnessAdapter)):
            raise ValueError("source_unavailable")
        facts = supervisor._require_retained_native(retained)
        # Initial project materialization uses the exact existing start request.
        # A resume requires its original handoff; absence never manufactures one.
        if retained.session.generation.generation_number != 1:
            raise ValueError("source_unavailable")
        attempt = runtime.attempts.get_attempt(retained.session.attempt_id)
        if attempt is None or type(attempt.requested_execution_profile) is not dict:
            raise ValueError("source_unavailable")
        requested = requested_execution_profile(attempt.requested_execution_profile)
        return runtime, supervisor, dispatch, retained, facts, requested

    def read(self, *, work_ref, root_job_id, expected_macro_sha=None):
        selected = wire.selection({"work_ref": work_ref, "root_job_id": root_job_id})
        reader = self._source_reader
        try:
            first = self._current(selected)
            runtime, supervisor, dispatch, retained, facts, requested = first
            root = runtime.jobs.get_job(root_job_id)
            command = root.orchestration_provenance["command_id"]
            if not command.startswith(ceo_intent.COMMAND_ID_PREFIX):
                raise ValueError("source_mismatch")
            receipt = ceo_intent.resolve_intent(runtime, command[len(ceo_intent.COMMAND_ID_PREFIX):])
            if receipt.get("work_ref") != work_ref or receipt.get("job_id") != root_job_id:
                raise ValueError("source_mismatch")
            source_kwargs = {"work_ref": work_ref, "record_commit": receipt["grounding"]["macro_sha"]}
            if expected_macro_sha is not None:
                if not wire._hex(expected_macro_sha, 40): raise ValueError("source_mismatch")
                source_kwargs["expected_current_macro_sha"] = expected_macro_sha
            source = reader.read(**source_kwargs)
            evidence = read_creation_evidence(runtime, selected=selected, project_source=source)
            adapter = retained.adapter
            args = {"operation_id": OperationId("ohf-op:start:" + retained.session.attempt_id),
                    "requested": requested, "epoch": retained.session.epoch, "generation": retained.session.generation}
            status = adapter.materialization_status(**args)
            body = compose_project_session_association(evidence, epoch=retained.session.epoch,
                generation=retained.session.generation, requested_profile_digest=requested_profile_digest(to_wire(requested)),
                broker_status=to_wire(status))
            # No current-session/permission proof is inferred from a retained
            # receipt. Recheck the actual same source and existing live owner.
            after = self._current(selected)
            if (self._source_reader is not reader or any(after[index] is not first[index] for index in range(4))
                    or after[4:] != first[4:]
                    or retained.adapter is not adapter or adapter.materialization_status(**args) != status
                    or reader.read(**source_kwargs) != source):
                return wire.unavailable(selected, "SOURCE_CHANGED")
            return wire.validate_body(body)
        except Exception as exc:
            reason = {"source_changed": "SOURCE_CHANGED", "source_mismatch": "SOURCE_MISMATCH"}.get(
                str(exc) if type(exc) is ValueError else "", "SOURCE_UNAVAILABLE")
            return wire.unavailable(selected, reason)

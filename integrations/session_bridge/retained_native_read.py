"""Nonowning native READ views of the original service dispatch and adapter.

No adapter factory, reconnect, resume, registry or durable owner is created here.
The Runtime caller proves original root/principal ownership before selecting.
"""
from __future__ import annotations
import hashlib
import inspect
from typing import Callable

from common.session_bridge_private_contract import BridgeError
from control_plane.native_conversation_read_contract import (
    NativeReadUnavailable, canonical, native_read_frame, validate_native_read_binding,
    validate_native_read_response,
)


def _guard(callback):
    result = callback()
    if result is not None:
        if inspect.iscoroutine(result):
            result.close()
        raise NativeReadUnavailable()


class RetainedNativeReadPort:
    """Request-local view of one already retained authenticated generation."""
    def __init__(self, adapter, session, association, *, current):
        from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
        if not isinstance(adapter, RemoteOperatorHarnessAdapter) or not callable(current):
            raise TypeError("original retained native adapter required")
        self._adapter, self._session, self._association = adapter, session, association
        self._client, self._guard = adapter.client, current
        self._captured = (adapter, session, association, self._client, current)
        self.association_sha256 = association.digest
        self.require_current()

    def require_current(self):
        adapter, session, association, client, current = self._captured
        if (self._adapter is not adapter or self._session is not session or self._association is not association
                or self._client is not client or adapter.client is not client or self._guard is not current
                or self.association_sha256 != association.digest):
            raise NativeReadUnavailable()
        _guard(current)

    async def read(self, *, principal_scope, issued_at, expires_at, request, before_write):
        frame = native_read_frame(association_sha256=self.association_sha256,
            principal_scope=principal_scope, issued_at=issued_at, expires_at=expires_at, request=request)
        def current():
            self.require_current()
            _guard(before_write)
            self.require_current()
        current()
        try:
            value = await self._adapter.read_native_content(
                epoch=self._session.epoch, generation=self._session.generation,
                association=self._association.document(), request=frame, before_read=current)
            current()
            return validate_native_read_response(value, frame)
        except Exception:
            raise NativeReadUnavailable() from None


class RetainedNativeReadResolver:
    """Trusted composition, selecting a finite view only after canonical ownership proof."""
    def __init__(self, service, runtime, composition, *, require_current: Callable[[], None]):
        from control_plane.executive_service import ExecutiveControlService
        from control_plane.executive_runtime import Runtime
        from control_plane.native_conversation_binding import NativeConversationHostComposition
        if (type(service) is not ExecutiveControlService or type(runtime) is not Runtime
                or type(composition) is not NativeConversationHostComposition
                or not callable(require_current) or inspect.iscoroutinefunction(require_current)):
            raise TypeError("original installed native read composition required")
        self._service, self._runtime, self._composition, self._guard = service, runtime, composition, require_current

    async def select(self, principal, selection, *, root_guard):
        from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, RetainedNativeOperatorSession
        from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
        from integrations.session_bridge.deepseek_native import (
            DeepSeekNativeAssociation, DeepSeekNativeReadSource, DeepSeekNativeSession, principal_namespace)
        service, runtime, composition, source_guard = (
            self._service, self._runtime, self._composition, self._guard)
        def source():
            if (self._service is not service or self._runtime is not runtime
                    or self._composition is not composition or self._guard is not source_guard
                    or service._require_runtime() is not runtime):
                raise NativeReadUnavailable()
            _guard(source_guard)
            _guard(root_guard)
            composition.require_current()
        try:
            source()
            dispatch, supervisor = service._native_operator_dispatch, service.operator_supervisor
            if (dispatch is None or type(supervisor) is not ExecutiveOperatorSupervisor
                    or supervisor.runtime is not runtime or service._service_state != "READY"
                    or dispatch.active_turn is not None or dispatch.pending_turn is not None
                    or type(dispatch.retained) is not RetainedNativeOperatorSession):
                raise NativeReadUnavailable()
            handle = dispatch.retained
            adapter, session = handle.adapter, handle.session
            if not isinstance(adapter, RemoteOperatorHarnessAdapter):
                raise NativeReadUnavailable()
            client = adapter.client
            facts = supervisor._require_retained_native(handle)
            composition_sha = composition.composition_sha256
            if type(composition_sha) is not str or len(composition_sha) != 64:
                raise NativeReadUnavailable()
            def current():
                source()
                if (service._native_operator_dispatch is not dispatch or service.operator_supervisor is not supervisor
                        or supervisor.runtime is not runtime or service._service_state != "READY"
                        or dispatch.retained is not handle or dispatch.active_turn is not None or dispatch.pending_turn is not None
                        or getattr(dispatch, "native_phase", None) != "READY" or dispatch.continuation.done()
                        or getattr(dispatch, "_fresh_turn_source", None) is not None
                        or getattr(dispatch, "_fresh_control_source", None) is not None
                        or getattr(dispatch, "_fresh_interrupt_source", None) is not None
                        or handle.adapter is not adapter or handle.session is not session or adapter.client is not client):
                    raise NativeReadUnavailable()
                live = supervisor._require_retained_native(handle)
                child_event = runtime.events.get_event_by_command_id(
                    f"coo-cycle:{selection['root_job_id']}:create-interactive:0")
                child = runtime.jobs.get_job(child_event.job_id) if child_event else None
                if (child is None or child.job_id != dispatch.job_id or child.job_id != handle.job.job_id
                        or child.root_job_id != selection["root_job_id"] or child.parent_job_id != selection["root_job_id"]
                        or child.current_attempt_id != session.attempt_id or live != facts
                        or live.provider_session_id != session.observation.provider_session_id
                        or live.worker_id != composition.registration.worker_id):
                    raise NativeReadUnavailable()
                runtime.jobs.assert_native_conversation_execution(child.job_id)
            current()
            observed = validate_native_read_binding(await adapter.read_native_binding(
                epoch=session.epoch, generation=session.generation, before_read=current))
            current()
            if observed["native_session_id"] != session.observation.provider_session_id:
                raise NativeReadUnavailable()
            association = DeepSeekNativeAssociation(
                work_ref=selection["work_ref"], root_job_id=selection["root_job_id"],
                native_session_id=observed["native_session_id"], owner_principal_scope=principal_namespace(principal),
                composition_sha256=composition_sha, native_package_sha256=observed["native_package_sha256"],
                donor_sha=observed["donor_sha"])
            port = RetainedNativeReadPort(adapter, session, association, current=current)
            source_capability = DeepSeekNativeReadSource(association, port, require_current=current)
            return DeepSeekNativeSession(source_capability, read_guard=current)
        except Exception:
            raise BridgeError("backend_unavailable", "original retained native history is unavailable") from None

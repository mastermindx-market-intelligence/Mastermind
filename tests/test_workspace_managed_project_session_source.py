"""Real inert native Runtime and Git source; broker transport is a READ fixture.

This checks composition, not installed collector/HTTP admission or a provider.
The sealed reader method delegates to the independently tested real Git helper;
the service record is an inert exact-class fixture, never started.
"""
import copy
import dataclasses
import json

import pytest

from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader, read_from_macro_owner
from control_plane.executive_service import ExecutiveControlService, _NativeOperatorDispatch
from control_plane.operator_harness_wire import requested_execution_profile, to_wire
from control_plane.operator_materialization_receipt import (
    build_operator_materialization_receipt, requested_profile_digest, MATERIALIZATION_STATUS_SCHEMA,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from control_plane.workspace_managed_project_session_source import ExistingManagedProjectSessionSource
from tests.test_agentos_project_creation_source import source, git
from tests.test_operator_materialization_receipt import _inputs
from tests.test_remote_operator_harness_adapter import _capabilities
from tests.test_native_retained_runtime import _retained
import tests.test_executive_operator_supervisor as native_fixture


@pytest.fixture
def owner(source, tmp_path, monkeypatch):
    macro, _, _ = source
    macro_sha = git(macro, "rev-parse", "HEAD")
    original_submit = native_fixture.submit_intent

    def submit(runtime, intent, **kwargs):
        # Explicit synthetic input to the ACTUAL creation owner, not a receipt.
        intent = {**intent, "workstream": "WS:SYNTHETIC-PROJECT",
                  "grounding": {**intent["grounding"], "macro_sha": macro_sha}}
        return original_submit(runtime, intent, **kwargs)

    monkeypatch.setattr(native_fixture, "submit_intent", submit)
    runtime, supervisor, retained, native = _retained(tmp_path / "native")
    attempt = runtime.attempts.get_attempt(retained.session.attempt_id)
    requested = requested_execution_profile(attempt.requested_execution_profile)
    values = _inputs()
    values.pop("expected_provider_session_id")
    process = to_wire(retained.session.observation.process)
    values.update(operation_command_id="ohf-op:start:" + attempt.attempt_id, attempt_id=attempt.attempt_id,
        worker_id=attempt.worker_id, session_epoch_id=retained.session.epoch.session_epoch_id,
        process_generation_id=retained.session.generation.process_generation_id,
        generation_number=retained.session.generation.generation_number,
        provider_session_id=retained.session.observation.provider_session_id,
        process_identity=process, observed_attestation=to_wire(retained.session.observed),
        requested_profile_digest=requested_profile_digest(to_wire(requested)))
    values["process_credentials"]["process_identity"] = process
    receipt = build_operator_materialization_receipt(**values)

    class Client:
        def __init__(self):
            self.calls = []
            self.after_read = None
        def request_sync(self, operation, payload, **kwargs):
            assert operation == "ohf-materialization-status"
            assert payload["operation_id"]["command_id"] == values["operation_command_id"]
            self.calls.append((operation, copy.deepcopy(payload)))
            if self.after_read is not None:
                self.after_read(self)
            return {"schema_version": MATERIALIZATION_STATUS_SCHEMA,
                    "status": "RECEIPT_CURRENT_IN_LIVE_BROKER", "receipt": receipt.to_dict()}

    client = Client()
    adapter = RemoteOperatorHarnessAdapter(client, turn_input_loader=lambda _: pytest.fail("provider input requested"),
                                          capabilities=_capabilities())
    retained = dataclasses.replace(retained, adapter=adapter)
    service = ExecutiveControlService.__new__(ExecutiveControlService)
    service.runtime, service.operator_supervisor = runtime, supervisor
    service._closing, service._service_state = False, "READY"
    service._native_operator_dispatch = _NativeOperatorDispatch(retained.job.job_id, "fixture-dispatch", None, None, retained)
    reader = AgentOsProjectCreationReader(macro_root=macro)
    monkeypatch.setattr(AgentOsProjectCreationReader, "read", lambda self, *, work_ref, record_commit, expected_current_macro_sha=None:
        read_from_macro_owner(macro_root=macro, expected_macro_sha=git(macro, "rev-parse", "HEAD"),
                              work_ref=work_ref, record_commit=record_commit))
    selected = {"work_ref": "WS:SYNTHETIC-PROJECT", "root_job_id": retained.job.root_job_id}
    return ExistingManagedProjectSessionSource(service, reader), service, selected, client, native


def test_real_retained_runtime_source_and_typed_proxy_compose_without_a_send_target(owner):
    source, service, selected, client, native = owner
    before = service.runtime.events.list_events()
    body = source.read(**selected)
    assert body["state"] == "MATERIALIZED_OBSERVATION", body
    assert body["observational_only"] is True and body["can_send"] is False and body["continuation_target"] is None
    assert len(client.calls) == 2
    assert service.runtime.events.list_events() == before
    assert native.stop_calls == 0 and native.begin_turn_calls == 1
    assert "SESSION-ACTIVE" not in json.dumps(body) and "fixture-principal" not in json.dumps(body)


def test_current_service_loss_refuses_before_broker_read(owner):
    source, service, selected, client, _ = owner
    service._closing = True
    body = source.read(**selected)
    assert body["state"] == "UNAVAILABLE" and body["project_source"] is None and client.calls == []


def test_a_foreign_project_cannot_borrow_the_current_root_or_session(owner):
    source, _, selected, client, _ = owner
    body = source.read(**{**selected, "work_ref": "WS:OTHER-PROJECT"})
    assert body["state"] == "UNAVAILABLE" and body["reason"] == "SOURCE_MISMATCH" and client.calls == []


def test_equal_valued_replacement_dispatch_is_a_different_owner_and_discards_the_result(owner):
    source, service, selected, client, _ = owner
    def replace_dispatch(_):
        service._native_operator_dispatch = dataclasses.replace(service._native_operator_dispatch)
    client.after_read = replace_dispatch
    body = source.read(**selected)
    assert body["state"] == "UNAVAILABLE" and body["reason"] == "SOURCE_CHANGED"
    assert body["materialization"] is None

"""Real project source/artifact and bounded result reads; no live providers.

The incumbent project factory fixture supplies current authentication/source
observations. The completion fixture uses real Runtime/COO seals with an inert
physical worker; these tests do not attest an installed service or model.
"""
import asyncio
import copy
import dataclasses
import json
from types import SimpleNamespace

import pytest

from common import project_conversation_read_contract as read_wire
from common import project_execution_private_contract as execution_wire
from common.executive_principal_namespace import principal_scope_from_identity
from control_plane import project_execution_admission as admission
from control_plane.installed_project_conversations_binding import require_installed_project_conversations
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.project_conversation_transport import validate_result
from integrations.session_bridge.project_conversations import RuntimeProjectConversationsReader
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.schemas import BridgeError
from tests.test_project_execution_factory import fixture, invoke
from tests.test_project_execution_service import composed


async def _finish(factory, root_id, monkeypatch):
    from control_plane.executive_runtime import JobStatus
    from tests.test_executive_service import _FakeSupervisor
    from tests.test_executive_coo_hierarchy_service import _plan_body, _complete
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    service = factory.service
    physical = _FakeSupervisor(service.runtime)
    supervisor = factory._supervisor()

    async def start(job_id, *, command_id):
        return await physical.start_cycle_job(job_id, command_id=command_id)

    async def finish(active):
        dispatch = SimpleNamespace(attempt=active.lease.attempt, lease_token=active.lease.lease_token)
        job = service.runtime.jobs.get_job(dispatch.attempt.job_id)
        if job.orchestration_role == "plan":
            parent = service.runtime.jobs.get_job(job.parent_job_id)
            return _complete(service.runtime, dispatch, _plan_body(dispatch, parent, delegation=None))[1]
        return finish_result(service.runtime, dispatch)

    monkeypatch.setattr(supervisor, "start_cycle_job", start)
    monkeypatch.setattr(supervisor, "finish_job", finish)
    for _ in range(30):
        outcome = await service._run_coo_cycle(root_id)
        assert outcome.action not in {"BLOCKED", "RECONCILIATION_REQUIRED"}, outcome
        tasks = tuple(service._dispatch_tasks.values())
        if tasks:
            await asyncio.gather(*tasks)
        assert service.service_state == "READY", service._dispatch_errors
        if service.runtime.jobs.get_job(root_id).status is JobStatus.COMPLETED:
            return
    pytest.fail("Fixture project did not settle")


def _case(tmp_path, monkeypatch, *, complete=False, composed_only=False):
    if complete or composed_only:
        factory, principal, args, _ = composed(tmp_path, monkeypatch)
    else:
        factory, principal, args, _, _ = fixture(tmp_path, monkeypatch)
    accepted = asyncio.run(invoke(factory, principal, args, raise_errors=True))
    runtime = factory.service.runtime
    root_id = accepted["data"]["receipt"]["job_id"]
    if complete:
        asyncio.run(_finish(factory, root_id, monkeypatch))
    base = RuntimeFabricTargetProjector(runtime)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("Project execution READ attempted Dialogue/provider I/O")

    original = RuntimeSessionReturn(runtime, fabric=base, codex=RuntimeCodexTargetProjector(base),
        socket_path=tmp_path / "never-open.sock", service_call=forbidden,
        authorized_policies=factory.planning.policies)
    owner = RuntimeProjectConversationsReader(original, supervisor=factory._supervisor())
    projection = principal_projection(principal)
    scope = principal_scope_from_identity(**{k: getattr(principal, k) for k in
        ("issuer_digest", "subject_digest", "client_ref", "resource")})
    return SimpleNamespace(factory=factory, principal=principal, projection=projection,
        args=args, runtime=runtime, root_id=root_id, owner=owner, original=original, scope=scope)


def _page(s, *, principal=None, guard=lambda: True):
    return s.owner.execution_references(principal or s.projection,
        {"work_ref": s.args["work_ref"]}, guard=guard)


def _read(s, reference=None, *, principal=None, guard=lambda: True):
    reference = reference or _page(s)["entries"][0]["reference"]
    return asyncio.run(s.owner.execution_read(principal or s.projection, reference, guard=guard))


def _events(s):
    return [event.to_dict() for event in s.runtime.events.list_events()]


def test_real_queued_project_reopens_original_goal_without_session_or_send_authority(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    before = _events(s)
    page = _page(s)
    assert page["coverage"] == {"state": "COMPLETE", "limit": 8, "returned": 1}
    row = page["entries"][0]
    assert row["goal"] == s.args["objective"] and row["root_state"] == "QUEUED"
    window = _read(s, row["reference"])
    assert window == _read(s, row["reference"])
    assert window["state"] == "QUEUED" and window["goal"] == s.args["objective"]
    assert window["result"] is None and window["parent_witness"] is None
    assert window["previous_run"] is None and window["can_send"] is False
    assert window["locator"]["root_job_id"] == s.root_id
    assert s.args["handoff_text"] not in json.dumps(window)
    assert _events(s) == before and s.runtime.attempts.list_attempts() == []
    assert validate_result(page, "execution_references", {"work_ref": s.args["work_ref"]}) == page
    assert validate_result(window, "execution_read", row["reference"]) == window


def test_real_completed_root_read_retains_exact_result_and_parent_witness(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch, complete=True)
    before = _events(s)
    reference = _page(s)["entries"][0]["reference"]
    window = _read(s, reference)
    completed = admission.completed_run(s.factory._supervisor(), s.root_id, s.args["work_ref"], s.scope)
    assert window["state"] == "COMPLETED"
    assert window["result"]["envelope"] == completed["result_envelope"]
    assert window["parent_witness"] == completed["witness"]
    assert window["result"]["digest"] == completed["witness"]["result_envelope_sha256"]
    assert window["result"]["envelope"]["role"] == "aggregation"
    assert window["can_send"] is False and _events(s) == before
    assert validate_result(window, "execution_read", reference) == window
    # A recorded result remains readable after live execution admission closes.
    monkeypatch.setattr(s.factory, "_binding", lambda: (_ for _ in ()).throw(AssertionError("fresh execution")))
    assert _read(s, reference) == window


def test_installed_read_policy_reuses_original_namespace_without_minting_submit(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    read = dataclasses.replace(s.projection, policy_id=s.factory.planning.policies.read.policy_id,
        scopes=("mastermind.executive.read",))
    page = _page(s, principal=read)
    assert page["entries"][0]["reference"]["principal_scope_sha256"] == s.scope
    assert _read(s, page["entries"][0]["reference"], principal=read)["can_send"] is False


@pytest.mark.parametrize("field", ["subject_digest", "issuer_digest", "client_ref", "resource", "policy_id"])
def test_foreign_principal_cannot_read_execution_input(tmp_path, monkeypatch, field):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    foreign = dataclasses.replace(s.projection, **{field: "foreign" if field in ("client_ref", "policy_id") else "f" * 64})
    calls = []
    original = admission.read_original_input
    monkeypatch.setattr(admission, "read_original_input", lambda *a: calls.append(True) or original(*a))
    with pytest.raises(BridgeError):
        _read(s, reference, principal=foreign)
    assert not calls


@pytest.mark.parametrize("field", ["root_job_id", "root_event_id", "root_event_sha256",
    "project_execution_source_sha256", "principal_scope_sha256", "work_ref"])
def test_reference_tampering_is_refused_before_original_input_read(tmp_path, monkeypatch, field):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    reference[field] = (reference[field] + 1 if field == "root_event_id" else
        "JOB-999999" if field == "root_job_id" else "WS:another" if field == "work_ref" else "f" * 64)
    calls = []
    monkeypatch.setattr(admission, "read_original_input", lambda *_: calls.append(True) or b"{}")
    with pytest.raises(BridgeError):
        _read(s, reference)
    assert not calls


def test_actual_original_artifact_corruption_withholds_history(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts
    monkeypatch.setattr(TerminalOriginalInputArtifacts, "read", lambda *a, **k: b'{"wrong":"private input"}')
    before = _events(s)
    with pytest.raises(BridgeError):
        _read(s, reference)
    with pytest.raises(BridgeError):
        _page(s)
    assert _events(s) == before


def test_source_corruption_cannot_manufacture_or_retain_a_project_reference(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    event = s.runtime.store.unique_root_created_event(s.root_id)
    payload = copy.deepcopy(event.payload)
    payload["provenance"]["project_execution_digest"] = "f" * 64
    # The real store prohibits event edits. Simulate a corrupt source read,
    # without disabling the database's immutable-event invariant.
    original = s.runtime.store.unique_root_created_event
    corrupted = dataclasses.replace(event, payload=payload)
    monkeypatch.setattr(s.runtime.store, "unique_root_created_event",
        lambda root_id: corrupted if root_id == s.root_id else original(root_id))
    before = _events(s)
    with pytest.raises(BridgeError):
        _read(s, reference)
    assert _events(s) == before


def test_guard_withdrawal_during_private_input_read_withholds_entire_body(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    live = [True]
    original = admission.read_original_input
    def withdraw(*args):
        result = original(*args)
        live[0] = False
        return result
    monkeypatch.setattr(admission, "read_original_input", withdraw)
    before = _events(s)
    with pytest.raises(BridgeError):
        _read(s, reference, guard=lambda: live[0])
    assert _events(s) == before


def test_execution_owner_must_be_actual_same_runtime_and_remain_bound(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        RuntimeProjectConversationsReader(s.original, supervisor=SimpleNamespace(runtime=s.runtime))
    absent = RuntimeProjectConversationsReader(s.original)
    with pytest.raises(BridgeError):
        absent.execution_references(s.projection, {"work_ref": s.args["work_ref"]}, guard=lambda: True)
    issued = s.owner.installed_binding()
    assert require_installed_project_conversations(issued, s.runtime) is issued
    page = issued.execution_references(s.projection, {"work_ref": s.args["work_ref"]}, guard=lambda: True)
    assert asyncio.run(issued.execution_read(s.projection, page["entries"][0]["reference"],
        guard=lambda: True))["can_send"] is False
    monkeypatch.setattr(s.factory._supervisor(), "runs_root", tmp_path / "foreign-artifacts")
    with pytest.raises(ValueError):
        require_installed_project_conversations(issued, s.runtime)


def test_catalogue_is_bounded_to_eight_latest_owned_project_roots(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    for ordinal in range(1, 10):
        args = {**s.args, "objective": f"Project turn {ordinal}"}
        args["operation_key"] = execution_wire.operation_key(s.scope, args)
        assert asyncio.run(invoke(s.factory, s.principal, args))["ok"]
    before = _events(s)
    page = _page(s)
    assert len(page["entries"]) == 8 and page["coverage"]["state"] == "PARTIAL"
    assert [row["goal"] for row in page["entries"]] == [f"Project turn {n}" for n in range(9, 1, -1)]
    assert _events(s) == before
    assert len(json.dumps(page, ensure_ascii=False).encode()) < 32768


@pytest.mark.parametrize("fault", ["can_send", "result", "witness", "attempt", "reference"])
def test_closed_http_window_cannot_promote_queued_data_to_a_completed_reply(tmp_path, monkeypatch, fault):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    window = _read(s, reference)
    if fault == "can_send":
        window["can_send"] = True
    elif fault == "result":
        window["result"] = {"digest": "f" * 64, "envelope": {}, "terminal_receipt_sha256": "f" * 64}
    elif fault == "witness":
        window["parent_witness"] = {}
    elif fault == "attempt":
        window["locator"]["job_id"] = "JOB-999999"
    else:
        window["reference"]["project_execution_source_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        validate_result(window, "execution_read", reference)


def test_execution_read_wire_is_closed_and_keeps_fresh_reference_distinct(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    reference = _page(s)["entries"][0]["reference"]
    assert read_wire.arguments(reference, "execution_read") == reference
    with pytest.raises(ValueError):
        read_wire.arguments(reference, "fresh_read")
    for changed in ({**reference, "can_send": True}, {**reference, "root_event_id": True},
                    {**reference, "schema": "mastermind.fresh_conversation_reference.v1"}):
        with pytest.raises(ValueError):
            read_wire.arguments(changed, "execution_read")

# Signed HTTP and the existing Unix client exercise the two fixed READ routes.
# Runtime source validity is established above; temporary IPC is the only peer.
from tests import test_project_conversation_transport as signed_transport
from tests import test_mastermind_os_session_transport as session_transport
from tests import test_mastermind_executive_app_asgi as auth

rsa_key = auth.rsa_key


@pytest.mark.parametrize("operation", ("execution_references", "execution_read"))
@pytest.mark.parametrize("submit", (False, True))
def test_signed_execution_read_over_incumbent_unix_client(tmp_path, monkeypatch, rsa_key, operation, submit):
    import tempfile
    from pathlib import Path
    from integrations.mastermind_executive_app.gateway import CeoIngressClient
    from integrations.mastermind_executive_app.project_conversation_transport import (
        ProjectConversationReadClient, ProjectConversationTransportApp,
    )
    s = _case(tmp_path, monkeypatch)
    page = _page(s)
    arguments = {"work_ref": s.args["work_ref"]} if operation == "execution_references" else page["entries"][0]["reference"]
    expected = page if operation == "execution_references" else _read(s, arguments)
    before = _events(s)

    async def run():
        owner, _, _, _ = session_transport.make_app(rsa_key)
        observed = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project-read.sock"

            async def serve(reader, writer):
                observed.append(read_wire.decode_frame(await reader.readline()))
                writer.write((json.dumps({"ok": True, "result": expected}) + "\n").encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            server = await asyncio.start_unix_server(serve, path=str(path))
            try:
                client = ProjectConversationReadClient(path, client=CeoIngressClient())
                app = ProjectConversationTransportApp(client, auth_owner=owner)
                token = (auth._submit_token if submit else auth._read_token)(rsa_key)
                status, data = await signed_transport.exchange(app, token, operation, arguments)
                assert status == 200 and data == expected and data["can_send"] is False
                assert len(observed) == 1
                assert observed[0]["operation"] == operation and observed[0]["arguments"] == arguments
                assert observed[0]["principal"]["policy_id"] == ("bsc-e1-test-submit" if submit else "bsc-e1-test-read")
                assert set(observed[0]) == {"schema", "operation", "principal", "arguments"}
            finally:
                server.close()
                await server.wait_closed()

    asyncio.run(run())
    assert _events(s) == before


@pytest.mark.parametrize("operation", ("execution_references", "execution_read"))
@pytest.mark.parametrize("claims", ({"sub": "foreign-user"}, {"exp": auth.NOW - 1}))
def test_signed_execution_read_refuses_bad_identity_before_peer(tmp_path, monkeypatch, rsa_key, operation, claims):
    s = _case(tmp_path, monkeypatch)
    page = _page(s)
    arguments = {"work_ref": s.args["work_ref"]} if operation == "execution_references" else page["entries"][0]["reference"]
    expected = page if operation == "execution_references" else _read(s, arguments)
    app, calls, _, _ = signed_transport.setup(rsa_key, operation, result=expected)
    token = auth._token(rsa_key, scope=auth.READ_SCOPE, **claims)
    status, body = asyncio.run(signed_transport.exchange(app, token, operation, arguments))
    assert status == 401 and calls == [] and set(body) == {"error"}


@pytest.mark.parametrize("operation", ("execution_references", "execution_read"))
def test_late_read_authorization_withdrawal_withholds_execution_body_without_retry(tmp_path, monkeypatch, rsa_key, operation):
    s = _case(tmp_path, monkeypatch)
    page = _page(s)
    arguments = {"work_ref": s.args["work_ref"]} if operation == "execution_references" else page["entries"][0]["reference"]
    expected = page if operation == "execution_references" else _read(s, arguments)

    def revoke():
        audit.fail = True

    app, calls, _, audit = signed_transport.setup(rsa_key, operation, after=revoke, result=expected)
    status, body = asyncio.run(signed_transport.exchange(app, auth._read_token(rsa_key), operation, arguments))
    assert status == 401 and set(body) == {"error"} and len(calls) == 1


@pytest.mark.parametrize("work_ref", ("WS:project-1", "WS:PROJECT.1", "WS:A", "WS:PROJECT_1"))
def test_execution_read_selectors_preserve_canonical_project_grammar(work_ref):
    with pytest.raises(ValueError):
        read_wire.arguments({"work_ref": work_ref}, "execution_references")
    reference = dict(schema="mastermind.project_execution_reference.v1", work_ref=work_ref,
        root_job_id="JOB-000001", root_event_id=1, root_event_sha256="a" * 64,
        project_execution_source_sha256="b" * 64, principal_scope_sha256="c" * 64)
    with pytest.raises(ValueError):
        read_wire.arguments(reference, "execution_read")


def test_installed_execution_stamp_distinguishes_replaced_supervisor_on_same_runtime(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    original = s.owner.installed_binding()
    replacement_owner = RuntimeProjectConversationsReader(s.original, supervisor=copy.copy(s.owner._supervisor))
    replacement = replacement_owner.installed_binding()
    assert require_installed_project_conversations(replacement, s.runtime) is replacement
    assert original.source == replacement.source
    assert original.execution_source != replacement.execution_source
    assert original.execution_source == s.owner._execution_source
    s.owner._supervisor = replacement_owner._supervisor
    with pytest.raises(ValueError):
        require_installed_project_conversations(original, s.runtime)


def test_catalogue_byte_budget_keeps_exact_unicode_goal_and_marks_partial(tmp_path, monkeypatch):
    s = _case(tmp_path, monkeypatch)
    goals = []
    for index in range(3):
        arguments = copy.deepcopy(s.args)
        arguments["objective"] = "😀" * 3998 + f"{index:02}"
        arguments["operation_key"] = execution_wire.operation_key(s.scope, arguments)
        asyncio.run(invoke(s.factory, s.principal, arguments, raise_errors=True))
        goals.append(arguments["objective"])
    before = _events(s)
    page = _page(s)
    assert page["coverage"] == {"state": "PARTIAL", "limit": 8, "returned": 1}
    assert page["entries"][0]["goal"] == goals[-1]
    assert len(execution_wire.canonical(page)) < read_wire.MAX_RESPONSE_BYTES
    assert _events(s) == before

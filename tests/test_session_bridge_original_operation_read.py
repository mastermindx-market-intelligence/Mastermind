"""Original-operation recovery over real Runtime provenance; no live proof."""
import asyncio
import dataclasses
import sqlite3
from pathlib import Path

import pytest

from control_plane import executive_runtime as er
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE
from integrations.session_bridge.native_read import NativeReplyReader
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.session_bridge.schemas import BridgeError
from test_session_bridge_runtime_return import setup, populate


def tool(s):
    return NativeReplyReadTool(NativeReplyReader(
        s.owner, socket_path=Path('/private/tmp/original-operation-read.sock'),
        service_call=s.service))


def configure_trusted_read_pair(s):
    """Emulate trusted host composition, not a caller-supplied pairing."""
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.session_bridge.runtime_return import RuntimeSessionReturn
    from tests import test_mastermind_executive_app_asgi as auth
    shared = dict(
        resource=s.principal.resource,
        resource_metadata_url=s.principal.resource + "/.well-known/oauth-protected-resource",
        issuer=s.principal.issuer,
        authorization_servers=[s.principal.issuer],
        jwks_uri=s.principal.issuer + ".well-known/jwks.json",
        allowed_subject_digests=[s.principal.subject_digest],
    )
    policies = AppPolicies(
        read=auth._read_policy(policy_id="test-read", **shared),
        submit=auth._submit_policy(policy_id=s.principal.policy_id, **shared),
    )
    s.owner = RuntimeSessionReturn(
        s.runtime, fabric=s.owner.fabric, codex=s.owner.codex,
        socket_path=s.owner.socket_path, service_call=s.service,
        authorized_policies=policies,
    )
    return policies


def events(s):
    return [e.to_dict() for e in s.runtime.events.list_events(job_id=s.epoch.job_id)]


def test_lost_read_ref_recovers_exact_reply_using_original_operation_only(setup):
    s = setup
    expected_ref = populate(s)
    before = events(s)
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(s.principal, 'session_reply_read',
        {'operation_key': s.args['operation_key']}))
    assert result['ok'] is True
    assert result['data']['read_ref'] == expected_ref
    assert result['data']['text'] == 'The bounded finding is confirmed.'
    assert result['data']['reply_committed'] is True
    assert result['data']['parent_consumed'] is False
    assert s.service.calls and all(c['operation'] == 'read_thread' for c in s.service.calls)
    assert events(s) == before


def test_original_send_remains_readable_under_same_principal_read_only_policy(setup):
    s = setup
    configure_trusted_read_pair(s)
    read_ref = populate(s)  # Original request was admitted with READ + SEND.
    before = events(s)
    reader = dataclasses.replace(
        s.principal, policy_id='test-read', scopes=('mastermind.executive.read',))
    s.enabled[0] = False  # No current target is needed to read original return.
    s.service.calls.clear()

    result = asyncio.run(tool(s).handle(
        reader, 'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is True
    assert result['data']['read_ref'] == read_ref
    assert result['data']['reply_committed'] is True
    assert result['data']['parent_consumed'] is False
    assert [c['operation'] for c in s.service.calls] and all(
        c['operation'] == 'read_thread' for c in s.service.calls)
    assert events(s) == before


@pytest.mark.parametrize('change', [
    {'subject_digest': 'f' * 64}, {'client_ref': 'foreign'},
    {'issuer_digest': 'f' * 64}, {'resource': 'https://foreign.invalid'},
])
def test_read_only_policy_transition_does_not_cross_principal_identity(setup, change):
    s = setup
    configure_trusted_read_pair(s)
    populate(s)
    before = events(s)
    reader = dataclasses.replace(s.principal,
        policy_id='test-read', scopes=('mastermind.executive.read',), **change)
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(
        reader, 'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


def test_changed_policy_without_read_only_scope_does_not_recover_original(setup):
    s = setup
    configure_trusted_read_pair(s)
    populate(s)
    before = events(s)
    foreign = dataclasses.replace(s.principal, policy_id='test-foreign')
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(
        foreign, 'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


@pytest.mark.parametrize('configure', [False, True])
def test_unapproved_read_only_policy_cannot_read_original(setup, configure):
    s = setup
    if configure:
        configure_trusted_read_pair(s)
    populate(s)
    before = events(s)
    stranger = dataclasses.replace(
        s.principal, policy_id='unapproved-read-policy',
        scopes=('mastermind.executive.read',))
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(
        stranger, 'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


def test_missing_trusted_pair_withholds_even_legitimate_read_only_policy(setup):
    s = setup
    populate(s)
    before = events(s)
    reader = dataclasses.replace(
        s.principal, policy_id='test-read',
        scopes=('mastermind.executive.read',))
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(
        reader, 'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


def test_trusted_read_pair_requires_matching_original_policy_and_principal(setup):
    s = setup
    pairs = configure_trusted_read_pair(s)
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.session_bridge.runtime_return import RuntimeSessionReturn

    def construct(policies):
        return RuntimeSessionReturn(
            s.runtime, fabric=s.owner.fabric, codex=s.owner.codex,
            socket_path=s.owner.socket_path, service_call=s.service,
            authorized_policies=policies)

    assert construct(pairs) is not None
    with pytest.raises(ValueError, match='trusted read and submit policy pair invalid'):
        construct(AppPolicies(
            read=dataclasses.replace(pairs.read, policy_id=pairs.submit.policy_id),
            submit=pairs.submit))
    with pytest.raises(ValueError, match='trusted read and submit policy pair invalid'):
        construct(AppPolicies(
            read=dataclasses.replace(pairs.read, allowed_subject_digests=('f' * 64,)),
            submit=pairs.submit))
    with pytest.raises(ValueError, match='trusted read and submit policy pair invalid'):
        construct(AppPolicies(
            read=dataclasses.replace(pairs.read, resource='https://foreign.invalid'),
            submit=pairs.submit))


def test_read_only_policy_inflight_runtime_expiry_withholds_answer(setup, monkeypatch):
    """Runtime must revalidate independent READ after an awaited carrier read."""
    from integrations.session_bridge import runtime_return as runtime_module
    s = setup
    configure_trusted_read_pair(s)
    read_ref = populate(s)
    before = events(s)
    reader = dataclasses.replace(
        s.principal, policy_id='test-read',
        scopes=('mastermind.executive.read',))
    s.service.calls.clear()
    # Expiration is triggered while the *Runtime resolver* awaits Dialogue.
    s.service.on_read = lambda: monkeypatch.setattr(
        runtime_module.time, 'time', lambda: reader.expires_at + 60)
    with pytest.raises(BridgeError) as error:
        asyncio.run(s.owner.resolve_read(
            principal=principal_projection(reader), read_ref=read_ref))
    assert error.value.code == 'reply_unavailable'
    assert s.service.calls and all(
        c['operation'] == 'read_thread' for c in s.service.calls)
    assert events(s) == before


def test_uncommitted_request_target_drift_blocks_read_only_recovery(setup, monkeypatch):
    """Do not apply the committed-reply archival exception to an active drift."""
    from integrations.session_bridge import runtime_return as runtime_module
    s = setup
    configure_trusted_read_pair(s)
    read_ref = s.owner.bind_request(s.projection, s.args)
    before = events(s)
    reader = dataclasses.replace(
        s.principal, policy_id='test-read',
        scopes=('mastermind.executive.read',))
    s.service.calls.clear()
    monkeypatch.setattr(runtime_module, '_read_current_target', lambda *_: None)
    assert s.owner.resolve_operation_read_ref(
        principal=principal_projection(reader),
        operation_key=s.args['operation_key']) == read_ref
    result = asyncio.run(tool(s).handle(
        reader, 'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


def test_reference_resolution_uses_original_provenance_without_target_revival(setup):
    s = setup
    expected_ref = populate(s)
    before = events(s)
    s.enabled[0] = False
    s.service.calls.clear()
    assert s.owner.resolve_operation_read_ref(principal=s.projection,
        operation_key=s.args['operation_key']) == expected_ref
    assert not s.service.calls
    assert events(s) == before


@pytest.mark.parametrize('change', [
    {'subject_digest': 'f' * 64}, {'client_ref': 'foreign'},
    {'issuer_digest': 'f' * 64}, {'resource': 'https://foreign.invalid'},
    {'scopes': ()}, {'expires_at': 1},
])
def test_original_operation_does_not_disclose_foreign_or_expired_provenance(setup, change):
    s = setup
    populate(s)
    before = events(s)
    s.service.calls.clear()
    result = asyncio.run(tool(s).handle(dataclasses.replace(s.principal, **change),
        'session_reply_read', {'operation_key': s.args['operation_key']}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


@pytest.mark.parametrize('args', [
    {'operation_key': ''}, {'operation_key': 'a' * 257}, {'operation_key': 1},
    {'operation_key': 'bad key'}, {'operation_key': 'original', 'read_ref': 'reply'},
    {'operation_key': 'original', 'resubmit': True},
    {'operation_key': 'original', 'target_ref': 'new'},
])
def test_invalid_operation_reads_fail_before_any_owner_effect(setup, args):
    s = setup
    before = events(s)
    result = asyncio.run(tool(s).handle(s.principal, 'session_reply_read', args))
    assert result['ok'] is False
    assert result['error']['code'] == 'invalid_input'
    assert not s.service.calls
    assert events(s) == before


def test_unknown_original_operation_does_not_create_provenance(setup):
    s = setup
    before = events(s)
    result = asyncio.run(tool(s).handle(s.principal, 'session_reply_read',
        {'operation_key': 'never-submitted'}))
    assert result['ok'] is False
    assert result['error']['code'] == 'reply_unavailable'
    assert not s.service.calls
    assert events(s) == before


def test_bounded_metadata_window_stable_across_pages_and_appends(setup):
    """Reader traverses finite metadata, not Event payloads or new appends."""
    s = setup
    populate(s)
    store = s.runtime.store
    watermark, first = store.bounded_event_metadata_window(limit=2)
    assert len(first) <= 2
    assert all("payload_json" not in row and "payload_bytes" in row for row in first)
    assert [r["event_id"] for r in first] == sorted(
        (r["event_id"] for r in first), reverse=True)
    with store.transaction() as conn:
        store.append_event(
            conn, aggregate_type="test", aggregate_id="append-after-watermark",
            event_type="TEST_APPENDED", command_id="test-r2-late-metadata-event",
            payload={"late": True})
    stable, rest = store.bounded_event_metadata_window(
        high_water=watermark, before_event_id=first[-1]["event_id"], limit=2)
    assert stable == watermark
    assert all(row["event_id"] < first[-1]["event_id"] for row in rest)
    assert all(row["event_id"] <= watermark for row in rest)
    assert store.bounded_event_metadata_window(high_water=0)[1] == []
    for invalid in (0, -1, 257, True, "2"):
        with pytest.raises(ValueError):
            store.bounded_event_metadata_window(limit=invalid)
    with pytest.raises(ValueError):
        store.bounded_event_metadata_window(before_event_id=0)


def test_original_root_uniqueness_is_bounded_and_fail_closed(setup):
    s = setup
    read_ref = populate(s)
    root = s.runtime.store.unique_root_created_event(s.epoch.root_job_id)
    assert root.event_type == "JOB_CREATED"
    assert root.job_id == s.epoch.root_job_id
    assert s.runtime.store.unique_root_created_event(s.epoch.root_job_id) == root
    with pytest.raises(ValueError):
        s.runtime.store.unique_root_created_event(s.epoch.root_job_id,
                                                   max_payload_bytes=1)
    with s.runtime.store.transaction() as conn:
        s.runtime.store.append_event(
            conn, aggregate_type="test", aggregate_id="duplicated-root",
            event_type="JOB_CREATED", job_id=s.epoch.root_job_id,
            command_id="test-r2-duplicate-root", payload={"duplicate": True})
    with pytest.raises(ValueError):
        s.runtime.store.unique_root_created_event(s.epoch.root_job_id)
    with pytest.raises(ValueError):
        s.owner._stored_request(read_ref)


def test_reference_projection_is_canonical_read_only_and_cursor_bound(setup):
    s = setup
    expected = populate(s)
    work_ref = s.binding.work_ref if hasattr(s.binding, "work_ref") else "WS:WORKSPACE-AGENT-PROGRAM"
    before = events(s)
    s.service.calls.clear()
    page = s.owner.session_reply_references(
        principal=s.projection, work_ref=work_ref, page_size=1)
    assert page["schema"] == "mastermind.session_reply_references.v1"
    assert len(page["references"]) == 1
    assert page["references"][0]["read_ref"] == expected
    assert page["references"][0]["reference_only"] is True
    assert page["status"] == "PARTIAL"
    assert events(s) == before
    assert not s.service.calls
    next_page = s.owner.session_reply_references(
        principal=s.projection, work_ref=work_ref, page_size=1,
        cursor=page["next_cursor"])
    assert next_page["references"] == []
    assert next_page["status"] == "COMPLETE"
    with pytest.raises(BridgeError):
        s.owner.session_reply_references(principal=s.projection,
            work_ref="WS:OTHER", cursor=page["next_cursor"])
    for malformed in (
        page["next_cursor"] + "Z",
        page["next_cursor"] + "%",
        page["next_cursor"] + "\n",
        page["next_cursor"] + "===",
        "Z" + page["next_cursor"][1:],
    ):
        with pytest.raises(BridgeError):
            s.owner.session_reply_references(principal=s.projection,
                work_ref=work_ref, cursor=malformed)
    stranger = dataclasses.replace(s.projection, subject_digest="f" * 64)
    assert s.owner.session_reply_references(
        principal=stranger, work_ref=work_ref)["references"] == []
    with pytest.raises(BridgeError):
        s.owner.session_reply_references(
            principal=stranger, work_ref=work_ref, cursor=page["next_cursor"])
    assert events(s) == before


@pytest.mark.parametrize("fault", [
    pytest.param(None, id="valid-original"),
    pytest.param("aggregate_id", id="mismatched-aggregate"),
    pytest.param("request_message_key", id="mismatched-request-message-key"),
])
def test_reference_projection_binds_original_request_provenance(setup, monkeypatch, fault):
    s = setup
    read_ref = s.owner.bind_request(s.projection, s.args)
    request, value = s.owner._stored_request(read_ref)
    before = s.runtime.events.list_events()
    assert not s.service.calls
    other_aggregate = "f" * 64
    other_message = "asd-dot-continue-" + "f" * 40
    assert request.aggregate_id != other_aggregate
    assert value["request_message_key"] != other_message

    # Keep the actual Runtime metadata, request and root fixtures. Change only
    # one otherwise well-formed field at the actual Event conversion seam used
    # by both the incumbent separate reads and the bounded observation.
    convert = er._event_from_row
    candidate_reads = []
    root_reads = []

    def read_event(row):
        event = convert(row)
        if event.event_id == value["root_event_id"]:
            root_reads.append(event.job_id)
        if event.event_id != request.event_id:
            return event
        candidate_reads.append(event.event_id)
        if fault == "aggregate_id":
            return dataclasses.replace(event, aggregate_id=other_aggregate)
        if fault == "request_message_key":
            return dataclasses.replace(
                event, payload={**event.payload, "request_message_key": other_message})
        return event

    monkeypatch.setattr(er, "_event_from_row", read_event)
    arguments = dict(principal=s.projection,
        work_ref=value["context"]["work_ref"], page_size=1)
    if fault is None:
        page = s.owner.session_reply_references(**arguments)
        assert page["schema"] == "mastermind.session_reply_references.v1"
        [row] = page["references"]
        assert row["read_ref"] == read_ref
        assert row["operation_key"] == value["operation_key"]
        assert row["request_ref"] == request.command_id
        assert row["request_event_id"] == request.event_id
        assert row["root_job_id"] == value["root_job_id"]
        assert row["reference_only"] is True
        assert root_reads == [value["root_job_id"]]
    else:
        with pytest.raises(BridgeError,
                match="authorized canonical reply references unavailable") as error:
            s.owner.session_reply_references(**arguments)
        assert error.value.code == "reply_unavailable"
        assert root_reads == []
    assert candidate_reads == [request.event_id]
    monkeypatch.setattr(er, "_event_from_row", convert)
    assert s.runtime.events.list_events() == before
    assert not s.service.calls


def _record_reference_observations(monkeypatch):
    observations = []
    initialize = er.BoundedRuntimeReadObservation.__init__

    def record(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        observations.append(self)

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "__init__", record)
    return observations


def test_reference_page_uses_one_actual_readonly_observation_and_vm_activation(setup, monkeypatch):
    s = setup
    expected = s.owner.bind_request(s.projection, s.args)
    before = events(s)
    observations = _record_reference_observations(monkeypatch)
    connections = []
    connect = sqlite3.connect
    activate = er._RuntimeReadProgressGuard.activate
    activations = []

    def open_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append((args[0], kwargs, connection))
        return connection

    def activate_guard(self):
        activations.append(self)
        return activate(self)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", open_connection)
        patch.setattr(er._RuntimeReadProgressGuard, "activate", activate_guard)
        page = s.owner.session_reply_references(
            principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM", page_size=1)
    assert [row["read_ref"] for row in page["references"]] == [expected]
    assert len(connections) == len(observations) == 1
    path, options, connection = connections[0]
    assert options.get("uri") is True and "mode=ro" in str(path)
    [observation] = observations
    assert activations == [observation._vm_progress]
    assert observation._vm_progress.steps > 0
    assert observation._vm_progress._removed and not observation._vm_progress._active
    assert observation.receipt.state == "UNKNOWN"
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert events(s) == before
    assert not s.service.calls


def test_reference_page_cumulative_bytes_refuse_when_each_isolated_stage_fits(setup, monkeypatch):
    s = setup
    expected = s.owner.bind_request(s.projection, s.args)
    request, value = s.owner._stored_request(expected)
    watermark, window = s.runtime.store.bounded_event_metadata_window()
    with s.runtime.store.read() as connection:
        candidate = dict(connection.execute(
            "SELECT * FROM events WHERE event_id=?", (request.event_id,)).fetchone())
        root = dict(connection.execute(
            "SELECT * FROM events WHERE event_id=?", (value["root_event_id"],)).fetchone())

    # Measure the real fixture's SQLite scalar bytes, independently of the
    # bounded loader. Event columns here are exactly NULL, INTEGER or TEXT.
    def size(cell):
        assert cell is None or type(cell) in (int, str)
        return 0 if cell is None else len(str(cell).encode("utf-8"))

    window_bytes = size(watermark) + sum(size(cell) for row in window for cell in row.values())
    candidate_bytes = sum(size(cell) for cell in candidate.values())
    root_metadata_bytes = size(root["event_id"]) + size(len(root["payload_json"].encode("utf-8")))
    root_bytes = root_metadata_bytes + sum(size(cell) for cell in root.values())
    isolated = (window_bytes, candidate_bytes, root_bytes)
    # The window, candidate and root metadata also fit together. Only charging
    # the final full root to that same acquisition can cross this ceiling.
    before_full_root = window_bytes + candidate_bytes + root_metadata_bytes
    ceiling = max(before_full_root, root_bytes) + 1
    assert all(0 < charged < ceiling for charged in isolated)
    assert before_full_root < ceiling
    assert ceiling < sum(isolated) < er.BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES
    assert [row["read_ref"] for row in s.owner.session_reply_references(
        principal=s.projection, work_ref=value["context"]["work_ref"], page_size=1
    )["references"]] == [expected]
    before = events(s)
    observations = _record_reference_observations(monkeypatch)
    loaders = []
    initialize = er._BoundedRoleResultLoader.__init__

    def record_loader(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        loaders.append(self)

    monkeypatch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES", ceiling)
    monkeypatch.setattr(er._BoundedRoleResultLoader, "__init__", record_loader)
    with pytest.raises(BridgeError, match="authorized canonical reply references unavailable") as error:
        s.owner.session_reply_references(
            principal=s.projection, work_ref=value["context"]["work_ref"], page_size=1)
    assert error.value.code == "reply_unavailable"
    assert len(loaders) == len(observations) == 1
    assert loaders[0]._total_bytes == sum(isolated) > ceiling
    with pytest.raises(er.StateConflict):
        _ = observations[0].receipt
    assert events(s) == before
    assert not s.service.calls


def test_reference_page_bounds_nonpayload_metadata_before_event_conversion(setup, monkeypatch):
    s = setup
    s.owner.bind_request(s.projection, s.args)
    ceiling = 65536
    with s.runtime.store.transaction() as connection:
        s.runtime.store.append_event(
            connection, aggregate_type="test", aggregate_id="large-reference-metadata",
            event_type="TEST_NOISE", actor="m" * (ceiling + 1),
            command_id="test-r2-large-reference-metadata", payload={"small": True})
    before = events(s)
    convert = er._event_from_row
    decoded = []

    def decode(row):
        decoded.append(row["event_id"])
        return convert(row)

    with monkeypatch.context() as patch:
        patch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_CELL_BYTES", ceiling)
        patch.setattr(er, "_event_from_row", decode)
        with pytest.raises(BridgeError, match="authorized canonical reply references unavailable"):
            s.owner.session_reply_references(
                principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM", page_size=1)
    assert decoded == []
    assert events(s) == before
    assert not s.service.calls


def test_reference_page_exhausts_actual_sqlite_progress_budget_without_partial_page(setup, monkeypatch):
    s = setup
    s.owner.bind_request(s.projection, s.args)
    before = events(s)
    observations = _record_reference_observations(monkeypatch)
    guard = er._RuntimeReadProgressGuard
    initialize = guard.__init__

    def limited_guard(self):
        initialize(self, limit=32)

    monkeypatch.setattr(guard, "__init__", limited_guard)
    with pytest.raises(BridgeError, match="authorized canonical reply references unavailable") as error:
        s.owner.session_reply_references(
            principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM", page_size=1)
    assert error.value.code == "reply_unavailable"
    [observation] = observations
    assert observation._vm_progress.tripped
    assert observation._vm_progress.steps == 32
    assert observation._vm_progress._removed and not observation._vm_progress._active
    with pytest.raises(er.StateConflict):
        _ = observation.receipt
    assert events(s) == before
    assert not s.service.calls


@pytest.mark.parametrize("fault", ["close", "finalize"])
def test_reference_page_does_not_escape_failed_observation_close(setup, monkeypatch, fault):
    s = setup
    expected = s.owner.bind_request(s.projection, s.args)
    assert s.owner.session_reply_references(
        principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM", page_size=1
    )["references"][0]["read_ref"] == expected
    before = events(s)
    observations = _record_reference_observations(monkeypatch)
    with monkeypatch.context() as patch:
        if fault == "close":
            close = s.runtime.store._close_read_connection

            def fail_close(connection):
                close(connection)
                raise er.RuntimeReadUnavailable("fixture owner close failure")

            patch.setattr(s.runtime.store, "_close_read_connection", fail_close)
        else:
            finalize = er.BoundedRuntimeReadObservation._finalize

            def fail_finalize(self):
                finalize(self)
                raise er.RuntimeReadUnavailable("fixture owner finalization failure")

            patch.setattr(er.BoundedRuntimeReadObservation, "_finalize", fail_finalize)
        with pytest.raises(BridgeError, match="authorized canonical reply references unavailable") as error:
            s.owner.session_reply_references(
                principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM", page_size=1)
    assert error.value.code == "reply_unavailable"
    [observation] = observations
    assert observation._vm_progress._removed and not observation._active
    with pytest.raises(sqlite3.ProgrammingError):
        observation._vm_progress._native.execute("SELECT 1")
    with pytest.raises(er.StateConflict):
        _ = observation.receipt
    assert events(s) == before
    assert not s.service.calls


@pytest.mark.parametrize("policy,scopes,client,visible", [
    ("test", (READ_SCOPE, SUBMIT_SCOPE), None, True),
    ("test", (READ_SCOPE, "fixture.extra"), None, True),
    ("test-read", (READ_SCOPE,), None, True),
    ("test-read", (READ_SCOPE, "fixture.extra"), None, False),
    ("test", (READ_SCOPE,), "x" * 2049, False),
])
def test_reference_page_preserves_exact_and_trusted_paired_identity_law(
        setup, monkeypatch, policy, scopes, client, visible):
    s = setup
    configure_trusted_read_pair(s)
    expected = s.owner.bind_request(s.projection, s.args)
    _, value = s.owner._stored_request(expected)
    reader = dataclasses.replace(s.projection, policy_id=policy, scopes=scopes,
        client_ref=s.projection.client_ref if client is None else client)
    before = events(s)
    root_reads = []
    convert = er._event_from_row

    def decode(row):
        event = convert(row)
        if event.event_id == value["root_event_id"]:
            root_reads.append(event.event_id)
        return event

    with monkeypatch.context() as patch:
        patch.setattr(er, "_event_from_row", decode)
        page = s.owner.session_reply_references(
            principal=reader, work_ref=value["context"]["work_ref"], page_size=1)
    assert [row["read_ref"] for row in page["references"]] == ([expected] if visible else [])
    assert root_reads == ([value["root_event_id"]] if visible else [])
    assert events(s) == before
    assert not s.service.calls


def test_reference_page_keeps_uninspected_33rd_candidate_on_next_page(setup):
    from control_plane.native_continuation import _continue_key, _request_key
    s = setup
    expected = s.owner.bind_request(s.projection, s.args)
    request, value = s.owner._stored_request(expected)
    with s.runtime.store.transaction() as connection:
        for index in range(32):
            operation = f"bounded-foreign-reference-{index}"
            key = _request_key(operation)
            foreign = {**value, "operation_key": operation,
                "read_ref": "session-reply-" + key,
                "request_message_key": _continue_key(operation),
                "principal": {**value["principal"], "client_ref": "foreign"}}
            s.runtime.store.append_event(connection,
                aggregate_type=request.aggregate_type, aggregate_id=key,
                event_type=request.event_type, actor=request.actor,
                job_id=request.job_id, attempt_id=request.attempt_id,
                worker_id=request.worker_id, command_id="session-bridge-continue:" + key,
                payload=foreign)
    before = events(s)
    first = s.owner.session_reply_references(
        principal=s.projection, work_ref=value["context"]["work_ref"], page_size=32)
    assert first["references"] == [] and first["status"] == "PARTIAL"
    assert first["next_cursor"]
    second = s.owner.session_reply_references(
        principal=s.projection, work_ref=value["context"]["work_ref"], page_size=32,
        cursor=first["next_cursor"])
    assert [row["read_ref"] for row in second["references"]] == [expected]
    assert second["high_water"] == first["high_water"]
    assert events(s) == before
    assert not s.service.calls


def test_reference_projection_fails_closed_on_duplicate_root(setup):
    s = setup
    populate(s)
    with s.runtime.store.transaction() as conn:
        s.runtime.store.append_event(
            conn, aggregate_type="test", aggregate_id="duplicate-root-ref",
            event_type="JOB_CREATED", job_id=s.epoch.root_job_id,
            command_id="test-r2-duplicate-root-ref", payload={"duplicate": True})
    with pytest.raises(BridgeError):
        s.owner.session_reply_references(
            principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM")


def test_reference_projection_sparse_history_empty_intermediate_page(setup):
    s = setup
    expected = populate(s)
    s.service.calls.clear()
    store = s.runtime.store
    with store.transaction() as conn:
        for i in range(275):
            store.append_event(conn, aggregate_type="test", aggregate_id="noise",
                event_type="TEST_NOISE", command_id=f"test-r2-noise-{i}",
                payload={"synthetic": i})
    before = events(s)
    first = s.owner.session_reply_references(
        principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM")
    assert first["references"] == []
    assert first["status"] == "PARTIAL"
    assert first["next_cursor"]
    with store.transaction() as conn:
        store.append_event(conn, aggregate_type="test", aggregate_id="new-later",
            event_type="TEST_NEW", command_id="test-r2-appended-after-watermark",
            payload={"late": True})
    second = s.owner.session_reply_references(
        principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM",
        cursor=first["next_cursor"])
    assert [r["read_ref"] for r in second["references"]] == [expected]
    assert all(r["request_event_id"] <= first["high_water"]
               for r in second["references"])
    assert before == events(s)
    assert not s.service.calls or all(c["operation"] != "send_message" for c in s.service.calls)


def test_reference_projection_oversized_candidate_is_unavailable(setup):
    s = setup
    populate(s)
    with s.runtime.store.transaction() as conn:
        s.runtime.store.append_event(
            conn, aggregate_type="session_bridge_continue",
            aggregate_id="oversized", event_type="SESSION_BRIDGE_CONTINUE_REQUESTED",
            actor="executive-session-bridge", command_id="test-r2-oversized-request",
            payload={"untrusted": "X" * 70000})
    with pytest.raises(BridgeError):
        s.owner.session_reply_references(
            principal=s.projection, work_ref="WS:WORKSPACE-AGENT-PROGRAM")


def test_original_reference_private_read_route_is_closed_and_effect_free(setup):
    from common.session_bridge_private_contract import (
        PRIVATE_SCHEMA, SESSION_TOOLS, MODIFYING_TOOLS)
    from integrations.session_bridge.installed import (
        InstalledSessionBridgeProvider, private_ingress_owner, principal_frame)
    from integrations.session_bridge.reference_tools import NativeReplyReferencesTool

    s = setup
    expected = populate(s)
    s.service.calls.clear()
    assert "session_reply_references" in SESSION_TOOLS
    assert "session_reply_references" not in MODIFYING_TOOLS
    provider = InstalledSessionBridgeProvider(
        target_projector=lambda *_: [], reply_handler=lambda *_: {},
        summon_handler=lambda *_: {},
        reference_handler=lambda principal, args:
            s.owner.session_reply_references(principal=principal, **args))
    frame = {"schema": PRIVATE_SCHEMA, "tool": "session_reply_references",
             "principal": principal_frame(s.principal),
             "arguments": {"work_ref": "WS:WORKSPACE-AGENT-PROGRAM"}}
    response = asyncio.run(private_ingress_owner(provider).handle_frame(frame))
    assert response["ok"] is True
    assert response["data"]["references"][0]["read_ref"] == expected
    assert response["data"]["references"][0]["reference_only"] is True
    assert not s.service.calls
    foreign = dataclasses.replace(s.principal, subject_digest="f" * 64)
    denied = asyncio.run(private_ingress_owner(provider).handle_frame(
        {**frame, "principal": principal_frame(foreign)}))
    assert denied["ok"] is True
    assert denied["data"]["references"] == []
    assert not s.service.calls
    assert NativeReplyReferencesTool.validate(
        "session_reply_references", frame["arguments"]) == frame["arguments"]
    for invalid in ({"work_ref": "A", "page_size": True},
                    {"work_ref": "A", "page_size": 33},
                    {"work_ref": "A", "fake": 1}, {}):
        with pytest.raises(Exception):
            NativeReplyReferencesTool.validate("session_reply_references", invalid)


def test_original_reference_tool_uses_existing_private_read_peer(setup):
    from types import SimpleNamespace
    from integrations.mastermind_executive_app.gateway import TRANSPORT_SENT_OK
    from integrations.session_bridge.installed import (
        InstalledSessionBridgeClient, InstalledSessionBridgeProvider)
    from integrations.session_bridge.reference_tools import NativeReplyReferencesTool

    s = setup
    expected = populate(s)
    s.service.calls.clear()
    provider = InstalledSessionBridgeProvider(
        target_projector=lambda *_: [], reply_handler=lambda *_: {},
        summon_handler=lambda *_: {},
        reference_handler=lambda principal, args:
            s.owner.session_reply_references(principal=principal, **args))

    class ExistingPrivatePeer:
        async def send_frame(self, _socket, frame):
            return SimpleNamespace(transport=TRANSPORT_SENT_OK, ok=True,
                                   result=await provider.handle_frame(frame))

    client = InstalledSessionBridgeClient(
        "/private/tmp/isolated-r2-reference-test.sock", client=ExistingPrivatePeer())
    tool = NativeReplyReferencesTool(client)
    result = asyncio.run(tool.handle(s.principal, "session_reply_references",
                                     {"work_ref": "WS:WORKSPACE-AGENT-PROGRAM"}))
    assert result["ok"] is True
    assert result["data"]["references"][0]["read_ref"] == expected
    assert result["data"]["references"][0]["reference_only"] is True
    assert not s.service.calls
    for args in ({"work_ref": "A", "page_size": True}, {}, {"work_ref": 19}):
        refused = asyncio.run(tool.handle(s.principal, "session_reply_references", args))
        assert refused["ok"] is False
        assert refused["error"]["code"] == "invalid_input"


def test_qualified_original_aggregate_history_is_finite_and_fail_closed(setup):
    s = setup
    read_ref = populate(s)
    event, _ = s.owner._stored_request(read_ref)
    before = s.runtime.store.bounded_aggregate_events(
        event.aggregate_type, event.aggregate_id)
    assert before and before[0].event_id == event.event_id
    with pytest.raises(ValueError):
        s.runtime.store.bounded_aggregate_events(
            event.aggregate_type, event.aggregate_id, max_total_bytes=1)
    with s.runtime.store.transaction() as conn:
        for index in range(256):
            s.runtime.store.append_event(
                conn, aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type="TEST_UNRECOGNIZED", actor="test",
                command_id=f"test-r2-overlong-aggregate-{index}",
                payload={"synthetic": index})
    with pytest.raises(ValueError):
        s.runtime.store.bounded_aggregate_events(
            event.aggregate_type, event.aggregate_id)
    with pytest.raises(ValueError):
        s.runtime.store.bounded_aggregate_events(
            event.aggregate_type, event.aggregate_id, max_events=1)
    result = asyncio.run(tool(s).handle(
        s.principal, "session_reply_read", {"read_ref": read_ref}))
    assert result["ok"] is False and result["error"]["code"] == "reply_unavailable"
    # No new SEND, retry, or parent ACK is involved.


def test_installed_private_frames_share_signed_cursor_for_control_lifetime(setup):
    """One trusted Control composition's per-frame providers can page the same READ."""
    from common.session_bridge_private_contract import PRIVATE_SCHEMA
    from integrations.session_bridge.installed import (
        build_runtime_session_bridge, principal_frame)
    s = setup
    expected = populate(s)
    key = b"x" * 32
    options = dict(dialogue_socket_path=Path("/private/tmp/r2-cursor-frame-test.sock"))
    first_owner = build_runtime_session_bridge(s.runtime, **options,
                                                reference_cursor_key=key)
    second_owner = build_runtime_session_bridge(s.runtime, **options,
                                                 reference_cursor_key=key)
    frame = {"schema": PRIVATE_SCHEMA, "tool": "session_reply_references",
             "principal": principal_frame(s.principal),
             "arguments": {"work_ref": "WS:WORKSPACE-AGENT-PROGRAM", "page_size": 1}}
    before = events(s)
    first = asyncio.run(first_owner.handle_frame(frame))
    assert first["ok"] is True
    assert [r["read_ref"] for r in first["data"]["references"]] == [expected]
    assert first["data"]["status"] == "PARTIAL"
    cursor = first["data"]["next_cursor"]
    second = asyncio.run(second_owner.handle_frame({
        **frame, "arguments": {**frame["arguments"], "cursor": cursor}}))
    assert second["ok"] is True
    assert second["data"]["status"] == "COMPLETE"
    assert second["data"]["references"] == []

    restarted_owner = build_runtime_session_bridge(
        s.runtime, **options, reference_cursor_key=b"y" * 32)
    restarted = asyncio.run(restarted_owner.handle_frame({
        **frame, "arguments": {**frame["arguments"], "cursor": cursor}}))
    assert restarted["ok"] is False
    assert restarted["error"]["code"] == "reply_unavailable"
    assert events(s) == before
    for invalid in (b"short", "not-bytes", 123):
        with pytest.raises(TypeError):
            build_runtime_session_bridge(s.runtime, **options,
                                         reference_cursor_key=invalid)


# Exact-original READ acquisition below uses source fixtures only.  In
# particular, direct populate() still exercises the existing live-writer
# fallback; these tests do not turn its fake transport receipt into Runtime
# admission or claim any installed/native-provider proof.
def _seed_committed_exact_reply_fixture(s, *, foreign_index=None, indexed_actor=None):
    """Seed immutable COMMIT facts, optionally one explicit indexed-only fault."""
    from integrations.session_bridge import runtime_return as bridge

    assert ((foreign_index is None and indexed_actor is None)
            or (foreign_index in {'continue', 'native'} and type(indexed_actor) is str))
    read_ref = populate(s)
    event, value = s.owner._stored_request(read_ref)
    request = next(item['message'] for item in s.service.items
                   if item['message']['message_key'] == value['request_message_key'])
    reply = next(item['message'] for item in s.service.items
                 if item['message']['reply_to_message_key'] == request['message_key'])
    native_binding = s.owner.resolve(
        native_session_id=s.facts.provider_session_id,
        operation_key=value['operation_key'], in_reply_to=request['message_key'])
    continue_command = bridge._COMMIT_PREFIX + event.aggregate_id
    native_command = bridge._NATIVE_COMMIT_PREFIX + event.aggregate_id
    assert s.runtime.store.get_event_by_command_id(continue_command) is None
    assert s.runtime.store.get_event_by_command_id(native_command) is None
    continue_payload = s.owner._commit_payload(event, request)
    native_payload = {
        'schema': 'mastermind.session_bridge.native_reply_commit.v1',
        'request_event_id': event.event_id,
        'request_event_sha256': bridge._digest(event.to_dict()),
        'message_key': reply['message_key'], 'fingerprint': reply['fingerprint'],
        'message_sha256': bridge._digest(reply),
        'binding_sha256': bridge._digest(dataclasses.asdict(native_binding)),
    }
    with s.runtime.store.transaction() as connection:
        for kind, event_type, command, payload in (
            ('continue', bridge._COMMIT_EVENT, continue_command, continue_payload),
            ('native', bridge._NATIVE_COMMIT_EVENT, native_command, native_payload),
        ):
            s.runtime.store.append_event(
                connection, aggregate_type=event.aggregate_type,
                aggregate_id=('foreign-index-' + event.aggregate_id
                              if kind == foreign_index else event.aggregate_id),
                event_type=event_type,
                actor=(indexed_actor if kind == foreign_index else bridge._ACTOR),
                job_id=event.job_id,
                attempt_id=event.attempt_id, worker_id=event.worker_id,
                command_id=command, payload=payload)
    # Prove the fixture really has both independently indexed facts and the
    # ordered aggregate that the production validators must reconcile.
    continued = s.runtime.store.get_event_by_command_id(continue_command)
    native = s.runtime.store.get_event_by_command_id(native_command)
    assert type(continued) is type(native) is er.Event
    assert event.event_id < continued.event_id < native.event_id
    assert continued.payload == continue_payload and native.payload == native_payload
    aggregate = s.runtime.store.bounded_aggregate_events(event.aggregate_type, event.aggregate_id)
    assert [item.to_dict() for item in aggregate] == [
        item.to_dict() for item in (event, continued, native)
        if item.aggregate_id == event.aggregate_id]
    if foreign_index is None:
        assert len(aggregate) == 3
        assert s.owner._native_commit_admission(event, aggregate).to_dict() == native.to_dict()
        assert s.owner._commit_started(event, request) is True
    else:
        foreign = continued if foreign_index == 'continue' else native
        assert foreign.aggregate_id == 'foreign-index-' + event.aggregate_id
        assert foreign.actor == indexed_actor and len(aggregate) == 2
    s.service.calls.clear()
    return read_ref


def _capture_exact_read_ownership(monkeypatch):
    trace = {'observations': _record_reference_observations(monkeypatch),
             'connections': [], 'activations': [], 'loaders': [], 'selections': []}
    connect = sqlite3.connect
    activate = er._RuntimeReadProgressGuard.activate
    initialize_loader = er._BoundedRoleResultLoader.__init__

    def open_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        path = args[0] if args else kwargs['database']
        trace['connections'].append((path, dict(kwargs), connection))
        return connection

    def activate_guard(self):
        trace['activations'].append(self)
        return activate(self)

    def initialize(self, *args, **kwargs):
        initialize_loader(self, *args, **kwargs)
        trace['loaders'].append(self)

    monkeypatch.setattr(sqlite3, 'connect', open_connection)
    monkeypatch.setattr(er._RuntimeReadProgressGuard, 'activate', activate_guard)
    monkeypatch.setattr(er._BoundedRoleResultLoader, '__init__', initialize)
    for kind, name in (
        ('original', 'read_session_original_request_bounded'),
        ('reply', 'read_session_reply_evidence_bounded'),
    ):
        selection = getattr(er.BoundedRuntimeReadObservation, name, None)
        if selection is None:
            # The old head can run the public call; it fails the actual
            # ownership/budget assertions instead of a missing-method stub.
            continue

        def selected(self, *, read_ref, _selection=selection, _kind=kind):
            trace['selections'].append((_kind, self))
            return _selection(self, read_ref=read_ref)

        monkeypatch.setattr(er.BoundedRuntimeReadObservation, name, selected)
    return trace


def _assert_exact_read_closed(trace, *, finalized=None):
    observations = trace['observations']
    assert observations, 'the public READ bypassed the Runtime observation owner'
    assert len(trace['connections']) == len(trace['loaders']) == len(observations)
    assert trace['activations'] == [item._vm_progress for item in observations]
    assert [item for _, item in trace['selections']] == observations
    if finalized is None:
        finalized = len(observations)
    for index, observation in enumerate(observations):
        path, options, connection = trace['connections'][index]
        assert options.get('uri') is True and 'mode=ro' in str(path)
        assert not observation._active
        assert observation._vm_progress.steps > 0
        assert observation._vm_progress._removed and not observation._vm_progress._active
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')
        if index < finalized:
            assert observation.receipt.schema == er.RUNTIME_READ_OBSERVATION_SCHEMA
            assert observation.receipt.state == 'UNKNOWN'
            assert observation.receipt.source_identity is None
        else:
            with pytest.raises(er.StateConflict):
                _ = observation.receipt


def _call_exact_read_public(s, read_ref, entry):
    if entry == 'reference':
        return s.owner.resolve_operation_read_ref(
            principal=s.projection, operation_key=s.args['operation_key'])
    assert entry in {'read_ref', 'operation_key'}
    arguments = ({'read_ref': read_ref} if entry == 'read_ref'
                 else {'operation_key': s.args['operation_key']})
    return asyncio.run(tool(s).handle(s.principal, 'session_reply_read', arguments))


def _expect_exact_read_unavailable(s, read_ref, entry):
    if entry == 'reference':
        with pytest.raises(BridgeError) as error:
            _call_exact_read_public(s, read_ref, entry)
        assert error.value.code == 'reply_unavailable'
    else:
        result = _call_exact_read_public(s, read_ref, entry)
        assert result['ok'] is False and result['error']['code'] == 'reply_unavailable'


def _exact_fixture_rows(s, read_ref):
    from integrations.session_bridge import runtime_return as bridge

    event, value = s.owner._stored_request(read_ref)
    with s.runtime.store.read() as connection:
        request = dict(connection.execute(
            'SELECT * FROM events WHERE event_id=?', (event.event_id,)).fetchone())
        root = dict(connection.execute(
            'SELECT * FROM events WHERE event_id=?', (value['root_event_id'],)).fetchone())
        aggregate = [dict(row) for row in connection.execute(
            'SELECT * FROM events WHERE aggregate_type=? AND aggregate_id=? ORDER BY sequence',
            (event.aggregate_type, event.aggregate_id)).fetchall()]
        indexed = [dict(connection.execute(
            'SELECT * FROM events WHERE command_id=?', (prefix + event.aggregate_id,)
        ).fetchone()) for prefix in (bridge._COMMIT_PREFIX, bridge._NATIVE_COMMIT_PREFIX)]
    return {'request': request, 'root': root, 'aggregate': aggregate,
            'continue': indexed[0], 'native': indexed[1]}


def _exact_scalar_bytes(value):
    # Independently count SQLite scalar material, not decoded Event JSON.
    assert value is None or type(value) in (int, str, bytes)
    if value is None:
        return 0
    return len(value) if type(value) is bytes else len(str(value).encode('utf-8'))


def _exact_row_bytes(row):
    return sum(_exact_scalar_bytes(value) for value in row.values())


def test_exact_original_reference_uses_only_closed_bounded_provenance(setup, monkeypatch):
    s = setup
    read_ref = s.owner.bind_request(s.projection, s.args)
    event, _ = s.owner._stored_request(read_ref)
    ceiling = 65536
    # An unrelated/oversized aggregate member must not turn reference-only
    # recovery into COMMIT validation or full reply-evidence acquisition.
    with s.runtime.store.transaction() as connection:
        s.runtime.store.append_event(
            connection, aggregate_type=event.aggregate_type, aggregate_id=event.aggregate_id,
            event_type='TEST_REFERENCE_ONLY_NOISE', actor='m' * (ceiling + 1),
            job_id=event.job_id, attempt_id=event.attempt_id, worker_id=event.worker_id,
            command_id='test-exact-reference-only-noise', payload={'fixture': True})
    before = events(s)
    s.service.calls.clear()
    with monkeypatch.context() as patch:
        patch.setattr(er, 'BOUNDED_ROLE_RESULT_MAX_CELL_BYTES', ceiling)
        patch.setattr(s.owner, '_request', lambda *_: pytest.fail('reference revived current writer'))
        trace = _capture_exact_read_ownership(patch)
        assert _call_exact_read_public(s, read_ref, 'reference') == read_ref
        _assert_exact_read_closed(trace)
        assert [kind for kind, _ in trace['selections']] == ['original']
    assert not s.service.calls and events(s) == before


@pytest.mark.parametrize('entry', ['read_ref', 'operation_key'])
def test_exact_committed_reply_owns_before_after_acquisition_and_accepts_unknown(
        setup, monkeypatch, entry):
    s = setup
    read_ref = _seed_committed_exact_reply_fixture(s)
    before = events(s)
    dialogue_observations = []
    with monkeypatch.context() as patch:
        trace = _capture_exact_read_ownership(patch)

        def at_dialogue():
            # This callback runs inside the actual fixture service coroutine.
            # No observation may survive into either owner's awaited READ.
            _assert_exact_read_closed(trace)
            dialogue_observations.append(len(trace['observations']))

        s.service.on_read = at_dialogue
        try:
            result = _call_exact_read_public(s, read_ref, entry)
        finally:
            s.service.on_read = None
        assert result['ok'] is True
        assert result['data']['read_ref'] == read_ref
        assert result['data']['text'] == 'The bounded finding is confirmed.'
        assert result['data']['reply_committed'] is True
        assert result['data']['parent_consumed'] is False
        _assert_exact_read_closed(trace)
        kinds = [kind for kind, _ in trace['selections']]
        assert kinds == (['reply'] * 4 if entry == 'read_ref'
                         else ['original', 'reply', 'reply', 'reply', 'reply', 'original'])
        assert dialogue_observations == ([1, 2, 3] if entry == 'read_ref' else [2, 3, 4])
    assert [call['operation'] for call in s.service.calls] == ['read_thread'] * 3
    assert events(s) == before


@pytest.mark.parametrize('entry', ['reference', 'read_ref'])
def test_exact_read_request_and_root_share_one_material_budget(setup, monkeypatch, entry):
    s = setup
    read_ref = _seed_committed_exact_reply_fixture(s)
    rows = _exact_fixture_rows(s, read_ref)
    request_bytes, root_bytes = (_exact_row_bytes(rows[key]) for key in ('request', 'root'))
    root_metadata = (_exact_scalar_bytes(rows['root']['event_id'])
                     + _exact_scalar_bytes(len(rows['root']['payload_json'].encode('utf-8'))))
    ceiling = max(request_bytes + root_metadata, root_metadata + root_bytes) + 1
    total = request_bytes + root_metadata + root_bytes
    assert request_bytes < ceiling and root_metadata + root_bytes < ceiling < total
    before = events(s)
    convert, decoded = er._event_from_row, []

    def decode(row):
        decoded.append(row['event_id'])
        return convert(row)

    with monkeypatch.context() as patch:
        patch.setattr(er, 'BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES', ceiling)
        patch.setattr(er, '_event_from_row', decode)
        trace = _capture_exact_read_ownership(patch)
        _expect_exact_read_unavailable(s, read_ref, entry)
        _assert_exact_read_closed(trace, finalized=0)
        assert len(trace['loaders']) == 1
        assert trace['loaders'][0]._total_bytes == total > ceiling
        assert decoded == [rows['request']['event_id']]
    assert not s.service.calls and events(s) == before


def test_exact_reply_aggregate_and_both_global_indexes_share_material_budget(setup, monkeypatch):
    import json

    s = setup
    read_ref = _seed_committed_exact_reply_fixture(s)
    rows = _exact_fixture_rows(s, read_ref)
    root_metadata = (_exact_scalar_bytes(rows['root']['event_id'])
                     + _exact_scalar_bytes(len(rows['root']['payload_json'].encode('utf-8'))))
    original = _exact_row_bytes(rows['request']) + root_metadata + _exact_row_bytes(rows['root'])
    aggregate_metadata = sum(_exact_scalar_bytes(value) for value in (
        len(rows['aggregate']),
        sum(len(row['payload_json'].encode('utf-8')) for row in rows['aggregate']),
        json.dumps([row['event_id'] for row in rows['aggregate']], separators=(',', ':')),
    ))
    aggregate = aggregate_metadata + sum(_exact_row_bytes(row) for row in rows['aggregate'])
    continued, native = (_exact_row_bytes(rows[key]) for key in ('continue', 'native'))
    stages = (original, aggregate, continued, native)
    ceiling = sum(stages[:-1]) + 1
    assert max(stages) < ceiling < sum(stages) < er.BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES
    before = events(s)
    convert, decoded = er._event_from_row, []

    def decode(row):
        decoded.append(row['event_id'])
        return convert(row)

    with monkeypatch.context() as patch:
        patch.setattr(er, 'BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES', ceiling)
        patch.setattr(er, '_event_from_row', decode)
        trace = _capture_exact_read_ownership(patch)
        _expect_exact_read_unavailable(s, read_ref, 'read_ref')
        _assert_exact_read_closed(trace, finalized=0)
        assert len(trace['loaders']) == 1
        assert trace['loaders'][0]._total_bytes == sum(stages) > ceiling
        # The aggregate's native Event was legitimately decoded once. Its
        # independently indexed second materialization is refused beforehand.
        assert decoded.count(rows['native']['event_id']) == 1
        assert decoded.count(rows['continue']['event_id']) == 2
    assert not s.service.calls and events(s) == before


@pytest.mark.parametrize('entry,site', [
    ('reference', 'request'), ('reference', 'root'),
    ('read_ref', 'request'), ('read_ref', 'root'),
    ('read_ref', 'aggregate'), ('read_ref', 'continue_index'), ('read_ref', 'native_index'),
])
def test_exact_read_bounds_selected_nonpayload_before_event_conversion(
        request, monkeypatch, entry, site):
    from integrations.session_bridge import runtime_return as bridge

    ceiling = 65536
    append = er.RuntimeStore.append_event
    register = er.WorkerRegistry.register_worker

    def register_metadata_class(self, worker_id, **kwargs):
        # Event(worker_id, quota_class) retains its real foreign key. Add the
        # fixture's metadata class through the existing registration owner,
        # before the original setup claims its ordinary default Attempt.
        assert kwargs['quota_classes'] == ['default']
        return register(self, worker_id,
                        **{**kwargs, 'quota_classes': ['default', 'm' * (ceiling + 1)]})

    def append_oversized_metadata(self, connection, **kwargs):
        selected_type = 'JOB_CREATED' if site == 'root' else bridge._EVENT
        if kwargs.get('event_type') == selected_type:
            kwargs = {**kwargs, 'quota_class': 'm' * (ceiling + 1)}
        return append(self, connection, **kwargs)

    # Get the incumbent fixture lazily so the root/request metadata exists at
    # its original append. Immutable-Event triggers and schema remain intact;
    # bind_request computes the genuine resulting root and request digests.
    with monkeypatch.context() as fixture_patch:
        if site in {'request', 'root'}:
            fixture_patch.setattr(er.RuntimeStore, 'append_event', append_oversized_metadata)
        if site == 'request':
            fixture_patch.setattr(er.WorkerRegistry, 'register_worker', register_metadata_class)
        s = request.getfixturevalue('setup')
        foreign_index = ({'continue_index': 'continue', 'native_index': 'native'}.get(site))
        read_ref = _seed_committed_exact_reply_fixture(
            s, foreign_index=foreign_index,
            indexed_actor=('m' * (ceiling + 1) if foreign_index is not None else None))
    rows = _exact_fixture_rows(s, read_ref)
    if site in {'request', 'root'}:
        bad_id = rows[site]['event_id']
        assert rows[site]['quota_class'] == 'm' * (ceiling + 1)
        # The metadata is canonical, not a malformed-provenance shortcut.
        # Ordinary caps permit the same exact public READ before lowering only
        # the material ceiling; its result remains a fixture, never live proof.
        positive = _call_exact_read_public(s, read_ref, entry)
        if entry == 'reference':
            assert positive == read_ref
        else:
            assert positive['ok'] is True
        s.service.calls.clear()
    elif site == 'aggregate':
        original_request = rows['request']
        with s.runtime.store.transaction() as connection:
            s.runtime.store.append_event(
                connection, aggregate_type=original_request['aggregate_type'],
                aggregate_id=original_request['aggregate_id'], event_type='TEST_OVERSIZED_AGGREGATE',
                actor='m' * (ceiling + 1), job_id=original_request['job_id'],
                attempt_id=original_request['attempt_id'], worker_id=original_request['worker_id'],
                command_id='test-exact-oversized-aggregate', payload={'small': True})
            bad_id = connection.execute(
                'SELECT event_id FROM events WHERE command_id=?',
                ('test-exact-oversized-aggregate',)).fetchone()[0]
    else:
        name = 'continue' if site == 'continue_index' else 'native'
        bad_id = rows[name]['event_id']
        # The exact command Event was initially appended outside this
        # aggregate. Its separately indexed material is the only bad cell.
        assert rows[name]['aggregate_id'] != rows['request']['aggregate_id']
        assert bad_id not in {row['event_id'] for row in rows['aggregate']}
        assert rows[name]['command_id'].startswith(
            bridge._COMMIT_PREFIX if name == 'continue' else bridge._NATIVE_COMMIT_PREFIX)
    before = events(s)
    convert, decoded = er._event_from_row, []

    def decode(row):
        decoded.append(row['event_id'])
        return convert(row)

    with monkeypatch.context() as patch:
        patch.setattr(er, 'BOUNDED_ROLE_RESULT_MAX_CELL_BYTES', ceiling)
        patch.setattr(er, '_event_from_row', decode)
        trace = _capture_exact_read_ownership(patch)
        _expect_exact_read_unavailable(s, read_ref, entry)
        # Refusing malformed evidence after conversion is insufficient: the
        # selected oversized Event must never have reached Python decoding.
        assert bad_id not in decoded
        _assert_exact_read_closed(trace, finalized=0)
    assert not s.service.calls and events(s) == before


@pytest.mark.parametrize('entry', ['reference', 'read_ref'])
def test_exact_read_exhausts_real_sqlite_vm_budget_without_result(setup, monkeypatch, entry):
    s = setup
    read_ref = _seed_committed_exact_reply_fixture(s)
    before = events(s)
    initialize = er._RuntimeReadProgressGuard.__init__

    def limited_guard(self):
        initialize(self, limit=32)

    with monkeypatch.context() as patch:
        patch.setattr(er._RuntimeReadProgressGuard, '__init__', limited_guard)
        trace = _capture_exact_read_ownership(patch)
        _expect_exact_read_unavailable(s, read_ref, entry)
        _assert_exact_read_closed(trace, finalized=0)
        [observation] = trace['observations']
        assert observation._vm_progress.tripped
        assert observation._vm_progress.steps == 32
    assert not s.service.calls and events(s) == before


@pytest.mark.parametrize('fault', ['close', 'finalize'])
@pytest.mark.parametrize('entry,fail_at,dialogue_reads', [
    ('reference', 1, 0), ('read_ref', 1, 0), ('read_ref', 2, 1),
    ('operation_key', 1, 0), ('operation_key', 3, 1), ('operation_key', 6, 3),
])
def test_exact_read_never_releases_failed_close_or_final_receipt(
        setup, monkeypatch, fault, entry, fail_at, dialogue_reads):
    s = setup
    read_ref = _seed_committed_exact_reply_fixture(s)
    before = events(s)
    failures = []
    with monkeypatch.context() as patch:
        trace = _capture_exact_read_ownership(patch)
        if fault == 'close':
            close = s.runtime.store._close_read_connection

            def fail_close(connection):
                close(connection)
                failures.append(connection)
                if len(failures) == fail_at:
                    raise er.RuntimeReadUnavailable('fixture exact-read close failure')

            patch.setattr(s.runtime.store, '_close_read_connection', fail_close)
        else:
            finalize = er.BoundedRuntimeReadObservation._finalize

            def fail_finalize(self):
                finalize(self)
                failures.append(self)
                if len(failures) == fail_at:
                    raise er.RuntimeReadUnavailable('fixture exact-read finalization failure')

            patch.setattr(er.BoundedRuntimeReadObservation, '_finalize', fail_finalize)
        _expect_exact_read_unavailable(s, read_ref, entry)
        assert len(failures) == len(trace['observations']) == fail_at
        _assert_exact_read_closed(trace, finalized=fail_at - 1)
    assert [call['operation'] for call in s.service.calls] == ['read_thread'] * dialogue_reads
    assert events(s) == before

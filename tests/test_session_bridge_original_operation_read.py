"""Original-operation recovery over real Runtime provenance; no live proof."""
import asyncio
import dataclasses
from pathlib import Path

import pytest

from integrations.business_mcp_auth.principal_projection import principal_projection
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
    with pytest.raises(BridgeError):
        s.owner.session_reply_references(principal=s.projection,
            work_ref=work_ref, cursor=page["next_cursor"] + "Z")
    stranger = dataclasses.replace(s.projection, subject_digest="f" * 64)
    assert s.owner.session_reply_references(
        principal=stranger, work_ref=work_ref)["references"] == []
    with pytest.raises(BridgeError):
        s.owner.session_reply_references(
            principal=stranger, work_ref=work_ref, cursor=page["next_cursor"])
    assert events(s) == before


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

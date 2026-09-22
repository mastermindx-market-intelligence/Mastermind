"""Signed web/Mac requests through real Service, broker socket and installed Reader."""
import asyncio
from dataclasses import asdict
import hashlib
import json
import os
from types import SimpleNamespace

import jwt
import pytest
from control_plane.executive_content_observer import ExecutiveContentObserver, ContentRefused
from control_plane.executive_worker_broker import WorkerBrokerClient, BrokerStateError
from control_plane.executive_service import ExecutiveControlService, CONTROL_PROTOCOL_VERSION
from control_plane.visible_turn_projection import TurnKey, VisibleTurnProjection
from integrations.executive_content_contract import (
    ContentObserverProfile, ContentProfileKey, ACCESS_SCHEMA, canonical, digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_steward_app.installed import (
    LiveWindowProfilesConfig, build_installed_steward_app_with_profiles,
)
from test_steward_content_integration import fixture
from test_executive_content_observer_reconcile import _terminal_run_absent
from test_executive_content_service_socket import _content_binding, _same_runtime_provider
from tests.test_executive_ceo_ingress import (
    _FakeSupervisor, _FakeGrounding, _config, _raw_ceo_request, short_socket_root,
)
from test_mastermind_steward_app_live_window import (
    _key, _cache, _content_policy, _steward_policy, _steward_verifier,
    _Sink, _invoke, _headers, WINDOW_PATH, ORIGIN, CONTENT_ISSUER,
    CONTENT_SUBJECT, CONTENT_CLIENT, KID,
)


def test_signed_concurrent_clients_withdrawal_history_and_restart(tmp_path, short_socket_root):
    clock, runtime, web, adapter, broker = fixture(tmp_path)
    mac_data = asdict(web)
    mac_data.update(
        client_ref=hashlib.sha256((CONTENT_ISSUER + '\nclient\nfixture-mac-client').encode()).hexdigest(),
        permission_digest='f' * 64, operation_id='qualified-mac-operation',
    )
    mac_data['viewer_binding_digest'] = digest({key: mac_data[key] for key in (
        'policy_id', 'issuer_digest', 'subject_digest', 'client_ref',
    )})
    mac_data['profile_digest'] = digest({key: value for key, value in mac_data.items() if key != 'profile_digest'})
    mac = ContentObserverProfile.from_mapping(mac_data)
    envelope = {
        'schema': 'mastermind.executive_content_profiles.v1',
        'profiles': {
            'web': {'enabled': True, 'profile': asdict(web)},
            'mac': {'enabled': True, 'profile': asdict(mac)},
        },
    }

    async def exercise():
        broker_path = short_socket_root / 'broker.sock'
        operations = []
        withdraw_on_web_page = False
        async def serve_broker(reader, writer):
            frame = json.loads(await reader.readline())
            operations.append((frame['operation'], frame['payload']['profile_digest']))
            try:
                result = await broker._dispatch(frame['operation'], frame['payload'])
                if (withdraw_on_web_page and frame['operation'] == 'ohf-observe-turn'
                        and frame['payload']['profile_digest'] == web.profile_digest):
                    envelope['profiles']['web']['enabled'] = False
                reply = dict(schema_version='mastermind.executive_worker_broker_response/v1',
                             request_id=frame['request_id'], operation=frame['operation'], ok=True, result=result)
            except Exception:
                reply = dict(schema_version='mastermind.executive_worker_broker_response/v1',
                             request_id=frame['request_id'], operation=frame['operation'], ok=False,
                             error={'code': 'state_conflict', 'message': 'refused'})
            writer.write(canonical(reply) + b'\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(serve_broker, path=str(broker_path))
        observer = ExecutiveContentObserver(
            runtime=runtime, broker_client=WorkerBrokerClient(broker_path),
            profile_loader=lambda: envelope, now=lambda: clock.value // 1000,
        )
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root, socket_path=short_socket_root / 'control.sock',
                    runtime_root=runtime.store.root),
            runtime_factory=lambda _: runtime, supervisor_factory=lambda _: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / 'ceo.sock',
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=_content_binding(
                content_provider_factory=_same_runtime_provider(runtime, observer),
            ),
        )
        async def lifecycle(operation, key):
            args = {} if key is None else {'profile_key': key}
            return await _raw_ceo_request(service.config.socket_path, canonical({
                'version': CONTROL_PROTOCOL_VERSION, 'command': 'content-observer-' + operation, 'args': args,
            }) + b'\n')

        async with server:
            await service.start()
            try:
                # Read cannot enroll; wire commands require an exact closed key.
                assert not (await observer.handle_frame(web.frame(ACCESS_SCHEMA)))['ok']
                assert not (await lifecycle('enroll', None))['ok']
                assert not (await lifecycle('enroll', 'other'))['ok']
                for key in ('web', 'mac'):
                    assert (await lifecycle('enroll', key))['result']['status'] == 'ACTIVE'
                grants = [await observer.status(key) for key in (ContentProfileKey.web, ContentProfileKey.mac)]
                assert grants[0]['reader_grant'] != grants[1]['reader_grant']
                assert grants[0]['turn_key'] == grants[1]['turn_key']
                turn = TurnKey(**grants[0]['turn_key'])
                for index in range(4):
                    adapter.visible_turn_projection.publish(
                        turn, method='item/updated', native_turn_id='NATIVE-G1',
                        params={'item': {'type': 'agentMessage', 'id': str(index), 'sequence': index, 'text': 'x' * 12000}},
                    )
                key_material = _key()
                policy = _content_policy()
                audit = _Sink()
                config = LiveWindowProfilesConfig(
                    authenticator=JwtAuthenticator(policy=policy, jwks_cache=_cache(policy, key_material)),
                    content_policy=policy, profile_loader=lambda: envelope,
                    ceo_ingress_socket_path=service.ceo_ingress_socket_path,
                    now=lambda: clock.value // 1000, allowed_origin=ORIGIN, audit_sink=audit,
                )
                app = build_installed_steward_app_with_profiles(
                    profiles_config=config, steward_policy=_steward_policy(),
                    steward_token_verifier=_steward_verifier(_steward_policy(), key_material),
                )
                def token(client, **changes):
                    claims = dict(iss=CONTENT_ISSUER, sub=CONTENT_SUBJECT, aud=web.content_resource,
                                  iat=clock.value // 1000 - 5, nbf=clock.value // 1000 - 5,
                                  exp=clock.value // 1000 + 600, scope=web.content_scope,
                                  client_id=client, jti='fixture-' + client)
                    claims.update(changes)
                    return jwt.encode(claims, key_material, algorithm='RS256', headers={'kid': KID, 'typ': 'at+jwt'})
                tokens = [token(CONTENT_CLIENT), token('fixture-mac-client')]
                async def read(bearer):
                    return await _invoke(app, path=WINDOW_PATH, headers=_headers(token=bearer))
                responses = await asyncio.gather(*(read(bearer) for bearer in tokens))
                for response in responses:
                    assert response[0] == 200, response[2]
                    assert len(response[2]) > 32768
                    assert len(json.loads(response[2])['view']['items']) == 4
                    assert b'NATIVE-G1' not in response[2] and b'reader_grant' not in response[2]
                assert {binding for op, binding in operations if op == 'ohf-observe-turn'} == {web.profile_digest, mac.profile_digest}
                enroll_count = sum(op == 'ohf-observer-enroll' for op, _ in operations)
                before = len(operations)
                for bearer in ('invalid', token('unknown-client'), token(CONTENT_CLIENT, sub='wrong-subject'), token(CONTENT_CLIENT, client_id=None)):
                    assert (await read(bearer))[0] == 401
                assert len(operations) == before
                withdraw_on_web_page = True
                responses = await asyncio.gather(*(read(bearer) for bearer in tokens))
                assert responses[0][0] in (401, 403) and b'xxxxxxxx' not in responses[0][2]
                assert responses[1][0] == 200
                assert not (await lifecycle('enroll', 'web'))['ok']
                assert (await lifecycle('status', 'web'))['result']['status'] == 'ACTIVE'
                assert (await lifecycle('revoke', 'web'))['result']['status'] == 'REVOKED'
                assert (await read(tokens[1]))[0] == 200
                # An invalid disabled slot still rejects the whole installation.
                envelope['profiles']['web']['extra'] = True
                before = len(operations)
                assert (await read(tokens[1]))[0] == 401
                assert len(operations) == before
                del envelope['profiles']['web']['extra']
                # Owner retirement clears content and metadata remains bounded.
                await _terminal_run_absent(broker, adapter)
                assert not adapter.visible_turn_projection._turns
                assert not adapter.visible_turn_projection._viewers_by_turn
                old_history = broker._operator_terminal[web.process_generation_id]
                assert old_history[3] is adapter.visible_turn_projection
                assert all(item is not adapter for item in old_history)
                broker._operator_run = SimpleNamespace(
                    epoch=SimpleNamespace(attempt_id='new-attempt', session_epoch_id='new-epoch'),
                    generation=SimpleNamespace(process_generation_id='new-generation'),
                    adapter=SimpleNamespace(visible_turn_projection=VisibleTurnProjection()),
                )
                clock.advance(3)
                with runtime.store.transaction() as connection:
                    connection.execute(
                        "UPDATE process_generations SET executive_writer_held=0, "
                        "provider_writer_state='RELEASED', ended_at_ms=? "
                        "WHERE process_generation_id=?",
                        (clock.value, web.process_generation_id),
                    )
                assert (await lifecycle('status', 'web'))['result']['status'] == 'INVALIDATED'
                assert (await lifecycle('revoke', 'web'))['result']['status'] == 'INVALIDATED'
                wrong = dict(web.broker_payload(), permission_digest='0' * 64)
                with pytest.raises(BrokerStateError, match='OBSERVER_CONFLICT'):
                    await broker._dispatch('ohf-observer-status', wrong)
                assert (await read(tokens[1]))[0] == 401
                # Remove only after an exact terminal status/revoke receipt.
                envelope['profiles']['web']['profile'] = None
                assert not (await lifecycle('status', 'web'))['ok']
                broker._operator_terminal.clear()  # lost/evicted broker history
                assert (await observer.status(ContentProfileKey.mac))['status'] == 'ABSENT'
                assert sum(op == 'ohf-observer-enroll' for op, _ in operations) == enroll_count
            finally:
                await service.close()
    asyncio.run(exercise())


def test_sealed_config_parser_accepts_pair_and_refuses_stale_disabled_release(tmp_path):
    from scripts import executive_os_phase1c as entry
    from test_c1_ceo_ingress_composition import _raw, _write_config
    from test_content_profile_profiles import pair
    from test_executive_content_observer import profile

    raw = _raw(tmp_path)
    raw.update(ceo_ingress_app_peer_uid=os.geteuid() + 10,
               ceo_ingress_app_armed=True, ceo_ingress_app_macro_root=tmp_path / 'macro')
    web, mac, envelope = pair(profile(client_ref='a' * 64, release_sha=raw['proof_base_sha']))
    raw['content_observer'] = envelope
    config_path = _write_config(tmp_path, raw)
    assert entry.load_control_config(config_path)['content_observer'] == envelope
    parsed = entry._parser().parse_args(['content-observer-status', '--profile-key', 'web'])
    assert parsed.profile_key == 'web'
    envelope['profiles']['web']['enabled'] = False
    envelope['profiles']['mac']['enabled'] = False
    for slot in envelope['profiles'].values():
        slot['profile']['release_sha'] = 'b' * 40
        slot['profile']['profile_digest'] = digest({
            key: value for key, value in slot['profile'].items() if key != 'profile_digest'
        })
    with pytest.raises(entry.ServiceError, match='release differs'):
        entry.load_control_config(_write_config(tmp_path, raw))

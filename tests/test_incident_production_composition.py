"""Actual composer/core interfaces; only native leaves and temporary roots.

No service command, UID transition, installed path, provider or production DB
is accessed. The connected case uses real anonymous pipes/socketpair and the
existing isolated durable-core fixture. It is source integration, not host proof.
"""
import dataclasses
import json
import os
import socket
import sys
import threading
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest
from control_plane import executive_incident_composition as composition
from control_plane import executive_incident_origin as origin
from control_plane import executive_incident_forward_host as host
from control_plane import executive_privileged_broker as broker
from ops.executive_os import provider_incident_forward as forward
from scripts import executive_os_incident_foreground_client as client
from scripts import executive_os_incident_forward as entry
from tests.test_incident_origin_composition import (
    world, BOOT, COMMIT, ORIGIN, CHILD, SOURCE, Connected, release, budget,
)
from tests.test_provider_incident_forward import forward_env, forward_args
from tests.test_provider_incident_recovery import recovery, state, custody_root


@pytest.fixture
def prepared(world, forward_env, monkeypatch):
    events = []
    native_state = {'bootstrapped': False}
    monkeypatch.setattr(composition, 'sys', S(platform='darwin'))
    monkeypatch.setattr(composition, 'os', S(geteuid=lambda: 0))
    monkeypatch.setattr(composition, '_loaded_source', Mock(return_value=SOURCE))
    monkeypatch.setattr(origin, 'sys', S(platform='darwin'))
    native_os = S(**{name: getattr(os, name) for name in dir(os)})
    native_os.geteuid = lambda: 0
    native_os.getpid = lambda: ORIGIN.pid
    monkeypatch.setattr(origin, 'os', native_os)
    monkeypatch.setattr(origin.host, '_instance', Mock(return_value=ORIGIN))
    monkeypatch.setattr(origin.host, '_observe_old_owner_exclusion', Mock())
    monkeypatch.setattr(origin.incident_release, '_observe_incident_release', Mock(side_effect=lambda **kw:
        release(state='RUNNING' if native_state['bootstrapped'] else 'UNLOADED')))
    def command(argv, context):
        assert argv in origin._ORIGIN_COMMANDS
        context.check(force=True)
        events.append(argv)
        if argv == origin._BOOTSTRAP_ARGV:
            native_state['bootstrapped'] = True
        return 0, b'loaded', b''
    monkeypatch.setattr(origin, '_run_origin_command', Mock(side_effect=command))
    monkeypatch.setattr(origin, '_sealed_client_entrypoint', Mock(return_value=
        str(broker._RELEASE_PREFIX / COMMIT / origin._ORIGIN_CLIENT_RELATIVE)))
    # Any unexpected actual subprocess is a test failure, not a host probe.
    monkeypatch.setattr(origin, 'subprocess', S(PIPE=-1,
        Popen=Mock(side_effect=AssertionError('no native subprocess permitted'))))
    intervals = []
    actual_enter = origin._enter_origin_interval
    def enter(**kw):
        value = actual_enter(**kw)
        intervals.append(value)
        return value
    monkeypatch.setattr(origin, '_enter_origin_interval', Mock(side_effect=enter))
    return S(world=world, core=forward_env.fwd_broker, events=events,
             intervals=intervals, env=forward_env, state=native_state)


def test_dormant_entry_refuses_before_native_acquisition_or_source_read(monkeypatch, capsys):
    monkeypatch.setattr(forward, 'PRODUCTION_FORWARD_RECOVERY_POLICY', None)
    acquire = Mock(side_effect=AssertionError('no acquisition'))
    read = Mock(side_effect=AssertionError('no source read'))
    monkeypatch.setattr(origin, '_enter_origin_interval', acquire)
    monkeypatch.setattr(composition, '_loaded_source', read)
    assert entry.main([]) == 65
    report = json.loads(capsys.readouterr().out)
    assert report['forward_state'] == 'NOT_SUBMITTED'
    assert report['original_status'] == 'EFFECT_UNKNOWN'
    assert report['error']['code'] == 'FORWARD_PRODUCTION_POLICY_DORMANT'
    assert report['bootstrap_attempted'] is False
    assert report['retry_authorized'] is False
    acquire.assert_not_called()
    read.assert_not_called()


def test_entry_rejects_all_arguments_without_entering_composer(monkeypatch):
    call = Mock(side_effect=AssertionError('no composer'))
    monkeypatch.setattr(entry, '_run_foreground_forward', call)
    assert entry.main(['--policy', 'anything']) == 64
    call.assert_not_called()


def test_wrong_principal_refuses_before_source_or_custody(prepared, monkeypatch):
    monkeypatch.setattr(composition.os, 'geteuid', lambda: 501)
    with pytest.raises(composition._ForegroundRunError, match='PRINCIPAL_UNQUALIFIED'):
        composition._run_foreground_forward()
    composition._loaded_source.assert_not_called()
    origin._enter_origin_interval.assert_not_called()
    assert not prepared.events


def test_missing_custody_never_bootstraps_or_spawns(prepared, monkeypatch):
    monkeypatch.setattr(origin.namespace, '_require_socket_absent', Mock(
        side_effect=origin.namespace.NamespaceObservationError('SOCKET_PREEXISTS')))
    with pytest.raises(composition._ForegroundRunError, match='SOCKET_PREEXISTS'):
        composition._run_foreground_forward()
    assert not prepared.events
    origin.subprocess.Popen.assert_not_called()
    assert len(prepared.world.handles) == 1 and prepared.world.handles[0].closed


def test_source_drift_before_bootstrap_closes_only_acquired_context(prepared, monkeypatch):
    monkeypatch.setattr(composition, '_loaded_source', Mock(side_effect=[SOURCE,
        dict(SOURCE, manifest_sha256='c' * 64)]))
    with pytest.raises(composition._ForegroundRunError, match='PREFLIGHT_DRIFT') as caught:
        composition._run_foreground_forward()
    assert caught.value.bootstrap_attempted is False
    assert not prepared.events
    origin.subprocess.Popen.assert_not_called()
    origin.namespace._release_namespace.assert_called_once()


def test_source_drift_after_bootstrap_never_submits_or_restarts(prepared, monkeypatch):
    monkeypatch.setattr(composition, '_loaded_source', Mock(side_effect=[SOURCE, SOURCE,
        dict(SOURCE, manifest_sha256='c' * 64)]))
    with pytest.raises(composition._ForegroundRunError, match='PRESUBMISSION_DRIFT') as caught:
        composition._run_foreground_forward()
    assert caught.value.bootstrap_attempted and caught.value.bootstrapped
    assert not caught.value.child_born and not caught.value.pump_entered
    assert prepared.events == [origin._ENABLE_ARGV, origin._BOOTSTRAP_ARGV,
                               origin._PRINT_BROKER_ARGV]
    origin.subprocess.Popen.assert_not_called()
    origin.namespace._release_namespace.assert_called_once()


def test_cleanup_failure_is_retained_not_reported_as_clean_refusal(prepared, monkeypatch):
    monkeypatch.setattr(composition, '_loaded_source', Mock(side_effect=[SOURCE,
        dict(SOURCE, manifest_sha256='c' * 64)]))
    monkeypatch.setattr(origin.namespace, '_release_namespace', Mock(side_effect=OSError('failed close')))
    with pytest.raises(composition._ForegroundRunError, match='CLEANUP_UNPROVEN'):
        composition._run_foreground_forward()
    origin.namespace._release_namespace.assert_called_once()
    assert prepared.intervals[0].closed
    assert not prepared.events


def test_closed_request_preserves_original_identity_and_distinct_forward_digest(prepared):
    raw = composition._closed_request(SOURCE)
    request, digest = forward.validate_forward_request(raw)
    assert request.request_id == forward.ORIGINAL_ISSUER_REQUEST_ID
    assert raw['args']['original_request_sha256'] == forward.ORIGINAL_REQUEST_SHA256
    assert raw['args']['successor_request_id'] == forward.SUCCESSOR_REQUEST_ID
    assert digest != forward.ORIGINAL_REQUEST_SHA256
    assert raw == forward_args()


def test_production_broker_hook_routes_active_policy_to_exact_private_factory(prepared, monkeypatch):
    # This seam stubs construction only; a weak-referenceable mock preserves
    # the production owner-lifetime registry contract without authenticating it.
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(broker, 'PrivilegedActionBroker', constructor)
    listener = Mock()
    listener.accept.side_effect = TimeoutError
    config = dataclasses.replace(prepared.core.config,
        release_root=broker._RELEASE_PREFIX / COMMIT)
    broker.run_broker(config, activated_socket=listener)
    assert constructor.call_args.kwargs.get('forward_host_guard') is host._make_forward_host_context
    assert constructor.call_args.args == (config,)
    assert 'release_owner' not in constructor.call_args.kwargs


def _break_optional_forward_import(monkeypatch, error):
    # Exercise the actual importer after removing the cached optional module;
    # do not replace the production resolver with a test double.
    name = 'ops.executive_os.provider_incident_forward'
    monkeypatch.delitem(sys.modules, name)
    package = sys.modules['ops.executive_os']
    monkeypatch.delattr(package, 'provider_incident_forward')
    class MissingOptional:
        def find_spec(self, fullname, path, target=None):
            if fullname == name:
                raise error
            return None
    monkeypatch.setattr(sys, 'meta_path', [MissingOptional(), *sys.meta_path])


def test_production_startup_missing_optional_module_keeps_ordinary_broker(monkeypatch):
    name = 'ops.executive_os.provider_incident_forward'
    _break_optional_forward_import(monkeypatch, ModuleNotFoundError(name, name=name))
    # This seam stubs construction only; a weak-referenceable mock preserves
    # the production owner-lifetime registry contract without authenticating it.
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(broker, 'PrivilegedActionBroker', constructor)
    listener = Mock()
    listener.accept.side_effect = TimeoutError
    config = object()
    broker.run_broker(config, activated_socket=listener)
    constructor.assert_called_once_with(config)
    listener.accept.assert_called_once()


@pytest.mark.parametrize('failure', [
    ModuleNotFoundError('missing transitive dependency', name='unrelated_dependency'),
    ImportError('optional module internal import failed'),
])
def test_production_startup_does_not_swallow_unrelated_import_failures(monkeypatch, failure):
    _break_optional_forward_import(monkeypatch, failure)
    constructor = Mock(side_effect=AssertionError('constructor must not run'))
    monkeypatch.setattr(broker, 'PrivilegedActionBroker', constructor)
    with pytest.raises(type(failure)) as caught:
        broker.run_broker(object(), activated_socket=Mock())
    assert caught.value is failure
    constructor.assert_not_called()


def test_real_foreground_composes_first_generation_seven_stages_and_once_settlement(prepared, monkeypatch):
    server, client_socket = socket.socketpair()
    connected = Connected(client_socket)
    monkeypatch.setattr(client, 'socket', S(socket=lambda *a: connected,
        AF_UNIX=socket.AF_UNIX, SOCK_STREAM=socket.SOCK_STREAM, timeout=socket.timeout))
    owned, errors, processes, threads = [], [], [], []
    def pipe():
        rd, wr = os.pipe()
        pair = os.fdopen(rd, 'rb', buffering=0), os.fdopen(wr, 'wb', buffering=0)
        owned.extend(pair)
        return pair
    def spawn(argv, **kwargs):
        assert argv == origin._CHILD_ARGV_PREFIX + (
            str(broker._RELEASE_PREFIX / COMMIT / origin._ORIGIN_CLIENT_RELATIVE),)
        assert (kwargs['user'], kwargs['group'], kwargs['extra_groups']) == (450, 450, [])
        assert kwargs['close_fds'] is True
        child_in, parent_out = pipe()
        parent_in, child_out = pipe()
        parent_err, child_err = pipe()
        def child_run():
            try:
                client._run_origin_client(stdin=child_in, stdout=child_out)
            except BaseException as failure:
                errors.append(failure)
            finally:
                child_out.close()
                child_err.close()
        def server_run():
            try:
                server.settimeout(3)
                raw = host._read_frame(server, budget())
                assert raw == composition._closed_request(SOURCE)
                core = prepared.core
                # Use the actual production selector with an inert canonical
                # config; the durable core's roots remain pytest temporaries.
                selector_config = dataclasses.replace(core.config,
                    release_root=broker._RELEASE_PREFIX / COMMIT)
                core._forward_host_guard = composition._resolve_production_forward_host_guard(selector_config)
                assert core._forward_host_guard is host._make_forward_host_context
                core.config = dataclasses.replace(core.config, allowed_peer_uids=(450,))
                receipt, replayed = core._handle_forward_outcome(raw, peer_uid=450, connection=server)
                host._send_frame(server, broker._wire_success(receipt, replayed=replayed), budget())
            except BaseException as failure:
                errors.append(failure)
            finally:
                server.close()
        ct = threading.Thread(target=child_run)
        st = threading.Thread(target=server_run)
        threads.extend((ct, st))
        def wait(timeout):
            ct.join(timeout)
            if ct.is_alive():
                raise TimeoutError('fixture child not settled')
            return 0 if not errors else 3
        process = S(pid=CHILD.pid, stdin=parent_out, stdout=parent_in,
                    stderr=parent_err, wait=Mock(side_effect=wait), kill=Mock())
        processes.append(process)
        st.start()
        ct.start()
        return process
    origin.subprocess.Popen.side_effect = spawn
    try:
        result = composition._run_foreground_forward()
    finally:
        client_socket.close()
        server.close()
        for stream in owned:
            stream.close()
        for thread in threads:
            thread.join(4)
    assert not errors, errors
    assert all(not thread.is_alive() for thread in threads)
    assert result.classification == 'SUCCEEDED', result
    assert result.exchanges == 7 and connected.submissions == 1
    interval = prepared.intervals[0]
    assert interval.closed and interval.child.settled and interval.child.instance == CHILD
    assert origin._enter_origin_interval.call_args.kwargs['deadline_monotonic_ns'] >= interval.deadline_monotonic_ns
    assert interval._budget().endpoint == interval.deadline_monotonic_ns
    assert prepared.events == [origin._ENABLE_ARGV, origin._BOOTSTRAP_ARGV,
                               origin._PRINT_BROKER_ARGV]
    assert len(processes) == 1
    processes[0].wait.assert_called_once()
    processes[0].kill.assert_not_called()
    # Origin and broker context each own a distinct namespace acquisition.
    # Each closes its own handles once; neither transfers the other's custody.
    released = [call.args[0] for call in origin.namespace._release_namespace.call_args_list]
    assert len(released) == 2 and len({id(value) for value in released}) == 2
    assert all(value.closed for value in released)
    assert forward.reservation_path(prepared.core.receipt_root).exists()
    assert forward.terminal_path(prepared.core.receipt_root).exists()
    assert not forward.guard_path(prepared.core.receipt_root).exists()

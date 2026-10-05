"""Deployment boundary: dedicated identity, exact source and durable auth audit."""
from __future__ import annotations
import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from tests.test_executive_ceo_ingress import _config, _FakeGrounding, short_socket_root


def _module():
    path=Path(__file__).parents[1]/'ops/executive_os/executive_mcp_entry.py'
    spec=importlib.util.spec_from_file_location('executive_mcp_entry_test', path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_additional_executive_resources_are_closed_exact_tunnel_urls():
    module = _module()
    first = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_" + "1" * 32
    )
    second = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_" + "2" * 32
    )
    assert module.validate_additional_resources(
        {"executive_additional_resources": [first, second]}
    ) == (first, second)

    for values in (
        [second, first],
        [first, first],
        ["https://example.test/v1/mcp/tunnel_" + "1" * 32],
        ["https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
         "v1/mcp/not-a-tunnel"],
    ):
        with pytest.raises(ValueError, match="additional Executive OAuth resources"):
            module.validate_additional_resources(
                {"executive_additional_resources": values}
            )


def test_additional_executive_resources_bound_types_count_and_legacy_empty():
    module = _module()
    prefix = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_"
    )
    seventeen = [prefix + f"{index:032x}" for index in range(17)]

    assert module.validate_additional_resources({}) == ()
    assert module.validate_additional_resources(
        {"executive_additional_resources": []}
    ) == ()
    for value in (None, (), "", {}, seventeen, [1], [True]):
        with pytest.raises(
            ValueError, match="additional Executive OAuth resources"
        ):
            module.validate_additional_resources(
                {"executive_additional_resources": value}
            )


def test_installed_launcher_refuses_user_owned_configuration(tmp_path):
    path=tmp_path/'policy.json'
    path.write_text('{}')
    path.chmod(0o600)
    with pytest.raises(ValueError, match='ownership'):
        _module().require_sealed_path(path)


@pytest.mark.skipif(sys.platform!='darwin', reason='macOS named-user ACL integration')
def test_app_socket_acl_preserves_modes_groups_and_does_not_expand_operator_access(tmp_path, short_socket_root):
    import pwd
    uid=pwd.getpwnam('_mastermind_worker').pw_uid
    service=ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root),
        ceo_ingress_socket_path=short_socket_root/'ceo.sock',
        ceo_ingress_peer_uid=os.geteuid()+1000, ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=uid,armed=False,grounding_provider=_FakeGrounding()),
    )
    short_socket_root.chmod(0o700)
    listener=socket.socket(socket.AF_UNIX)
    neighbor=socket.socket(socket.AF_UNIX)
    try:
        listener.bind(str(service.ceo_ingress_socket_path))
        neighbor.bind(str(short_socket_root/'operator.sock'))
        service.ceo_ingress_socket_path.chmod(0o600)
        before=service.ceo_ingress_socket_path.stat()
        service._grant_app_socket_access()
        first=subprocess.check_output(['/bin/ls','-le',str(service.ceo_ingress_socket_path)],text=True)
        service._grant_app_socket_access()
        second=subprocess.check_output(['/bin/ls','-le',str(service.ceo_ingress_socket_path)],text=True)
        assert first == second, 'restart must not duplicate the ACL'
        assert 'user:_mastermind_worker allow read,write' in second
        assert 'user:_mastermind_worker' not in subprocess.check_output(['/bin/ls','-le',str(short_socket_root/'operator.sock')],text=True)
        after=service.ceo_ingress_socket_path.stat()
        assert (before.st_uid,before.st_gid,before.st_mode,before.st_ino)==(after.st_uid,after.st_gid,after.st_mode,after.st_ino)
    finally:
        listener.close()
        neighbor.close()


def test_installed_auth_audit_retains_both_policy_facts(tmp_path):
    from types import SimpleNamespace
    from integrations.business_mcp_auth.contracts import AuthAuditEvent, AUTH_AUDIT_SCHEMA
    policies=SimpleNamespace(read=SimpleNamespace(policy_id='executive-read'),submit=SimpleNamespace(policy_id='executive-submit'))
    for name in ('read','submit'):
        (tmp_path/name).mkdir(mode=0o700)
    sink=_module().PolicyAuditSink(policies,tmp_path)
    try:
        for policy in (policies.read, policies.submit):
            sink.emit(AuthAuditEvent(schema=AUTH_AUDIT_SCHEMA,policy_id=policy.policy_id,code='accepted',accepted=True))
    finally:
        sink.close()
    for name, policy in (('read',policies.read),('submit',policies.submit)):
        rows=[json.loads(line) for line in (tmp_path/name/'auth-audit.jsonl').read_text().splitlines()]
        assert len(rows)==1 and rows[0]['policy_id']==policy.policy_id
        assert rows[0]['accepted'] is True


@pytest.mark.parametrize('parent_uid,parent_mode,accepted', [
    (0, 0o755, True),
    (0, 0o777, False),
    (0, 0o775, False),
    (123456, 0o755, False),
])
def test_app_acl_respects_bootstrap_root_owned_socket_directory(
    tmp_path, short_socket_root, monkeypatch, parent_uid, parent_mode, accepted,
):
    """The existing bootstrap owns the shared parent; only the socket needs an ACL."""
    from types import SimpleNamespace
    from control_plane.executive_service import ServiceError
    import control_plane.executive_service as service_module

    service = ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root),
        ceo_ingress_socket_path=short_socket_root/'ceo.sock',
        ceo_ingress_peer_uid=os.geteuid()+1000,
        ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_app_binding=CeoIngressAppBinding(
            peer_uid=os.geteuid()+2000, armed=False, grounding_provider=_FakeGrounding(),
        ),
    )
    short_socket_root.chmod(parent_mode)
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(service.ceo_ingress_socket_path))
    service.ceo_ingress_socket_path.chmod(0o660)
    real_lstat = Path.lstat
    socket_parent = service.ceo_ingress_socket_path.parent
    calls = []

    def observed_lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if path == socket_parent:
            fields = list(info)
            fields[4] = parent_uid
            return os.stat_result(fields)
        return info

    def command(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout='')

    monkeypatch.setattr(service_module.sys, 'platform', 'darwin')
    monkeypatch.setattr(service_module.pwd, 'getpwuid',
                        lambda uid: SimpleNamespace(pw_name='_mastermind_executive_mcp'))
    monkeypatch.setattr(Path, 'lstat', observed_lstat)
    monkeypatch.setattr(service_module.subprocess, 'run', command)
    try:
        if not accepted:
            with pytest.raises(ServiceError, match='custody'):
                service._grant_app_socket_access()
            assert calls == []
            return
        service._grant_app_socket_access()
        assert all(str(socket_parent) != argv[-1] for argv in calls)
        assert [argv for argv in calls if argv[0] == '/bin/chmod'] == [[
            '/bin/chmod', '+a', 'user:_mastermind_executive_mcp allow read,write',
            str(service.ceo_ingress_socket_path),
        ]]
        assert service.ceo_ingress_socket_path.stat().st_mode & 0o777 == 0o660
    finally:
        listener.close()


@pytest.mark.parametrize('profile,builder_name,mounted,os_enabled', [
    ('legacy', 'build_executive_mcp_app', True, False),
    ('web_ceo_v2', 'build_web_ceo_v2_mcp_app', True, False),
    ('web_ceo_v3', 'build_web_ceo_v3_mcp_app', True, False),
    ('web_ceo_v3', 'build_web_ceo_v3_mcp_app', True, True),
    ('web_ceo_sessions_v1', 'build_web_ceo_sessions_mcp_app', True, False),
    ('release_control_v1', 'build_release_control_mcp_app', False, False),
    ('personal_read', 'build_personal_read_mcp_app', False, False),
    ('web_ceo_release_v1', 'build_web_ceo_release_mcp_app', True, False),
])
def test_launcher_selects_one_existing_listener_and_preserves_optional_mounts(
    tmp_path, monkeypatch, profile, builder_name, mounted, os_enabled,
):
    from types import SimpleNamespace
    from integrations.executive_mcp import server
    from integrations.mastermind_executive_app import gateway
    import uvicorn

    module = _module()
    release = 'a' * 40
    source = tmp_path / release
    module.__file__ = str(source / 'ops/executive_os/executive_mcp_entry.py')
    # Test the installed dispatch function without root files, sockets or a listener.
    monkeypatch.setattr(module, 'sys', SimpleNamespace(
        flags=SimpleNamespace(isolated=True), dont_write_bytecode=True, path=[]))
    monkeypatch.setattr(module, 'require_sealed_path', lambda *a, **k: None)
    monkeypatch.setattr(module.os, 'geteuid', lambda: 458)
    raw = {
        'schema': module.CONFIG_SCHEMA, 'release_sha': release, 'service_uid': 458,
        'ceo_ingress_socket_path': '/var/run/mastermind-executive/ceo-ingress.sock',
        'port': 8443, 'policies': {},
        'audit_root': '/var/log/mastermind-executive/mcp-auth',
        'executive_mcp_profile': profile,
    }
    if os_enabled:
        raw['os_executive_transport'] = True
        raw['os_executive_resource'] = module.OS_EXECUTIVE_RESOURCE
    config = tmp_path / 'installed.json'
    config.write_text(json.dumps(raw))
    from tests.test_executive_mcp_app_composition import fixture
    policies = gateway.AppPolicies(read=fixture._read_policy(), submit=fixture._submit_policy())
    monkeypatch.setattr(gateway, 'load_app_policies', lambda supplied: policies)
    mounts = {'workspace_app': object(), 'content_app': object(), 'os_app': object()}
    mount_calls = []
    def optional(*args):
        mount_calls.append(args)
        return mounts
    monkeypatch.setattr(module, 'build_optional_apps', optional)
    closed = []
    sink = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(module, 'PolicyAuditSink', lambda *a, **k: sink)
    calls = []
    app = object()
    def selected(settings, **kwargs):
        calls.append((settings, kwargs))
        return app
    def wrong(*a, **k):
        pytest.fail('wrong MCP builder selected')
    for name in ('build_executive_mcp_app', 'build_web_ceo_v2_mcp_app',
                 'build_web_ceo_v3_mcp_app', 'build_web_ceo_sessions_mcp_app', 'build_personal_read_mcp_app',
                 'build_release_control_mcp_app', 'build_web_ceo_release_mcp_app'):
        monkeypatch.setattr(server, name, selected if name == builder_name else wrong)
    launches = []
    monkeypatch.setattr(uvicorn, 'run', lambda *a, **k: launches.append((a, k)))

    assert module.main(['--config', str(config)]) == 0
    assert len(calls) == len(launches) == 1
    settings, kwargs = calls[0]
    assert settings.policies is policies
    assert settings.mastermind_root == source
    assert settings.read_from_ceo_ingress is True
    assert settings.ceo_ingress_socket_path == raw['ceo_ingress_socket_path']
    if profile == 'web_ceo_v3':
        assert kwargs.pop('enable_os_executive_transport') is os_enabled
        assert kwargs.pop('os_executive_resource') == (module.OS_EXECUTIVE_RESOURCE if os_enabled else None)
        assert tuple(pair.submit.resource for pair in settings.additional_policies) == ((module.OS_EXECUTIVE_RESOURCE,) if os_enabled else ())
        from integrations.mosyle_mdm.client import MosyleInventoryClient
        assert isinstance(kwargs.pop('mdm_reader'), MosyleInventoryClient)
    if profile in {'web_ceo_v3', 'web_ceo_sessions_v1'}:
        from integrations.session_bridge.return_tools import NativeReplyReadTool
        assert type(kwargs.pop('session_reply_read_tool')) is NativeReplyReadTool
        assert callable(kwargs.pop('session_target_projector'))
        assert callable(kwargs.pop('session_reply_handler'))
        assert callable(kwargs.pop('session_summon_handler'))
    assert kwargs == {'audit_sink': sink, **(mounts if mounted else {})}
    assert len(mount_calls) == int(mounted)
    assert launches == [((app,), dict(host='127.0.0.1', port=8443, access_log=False,
                                      proxy_headers=True, forwarded_allow_ips='127.0.0.1'))]
    assert closed == [True]


@pytest.mark.parametrize('value', [None, True, [], {}, 'web_ceo_release_v2',
                                  'web_ceo_release_v1 ', 'WEB_CEO_RELEASE_V1'])
def test_combined_profile_selector_is_closed(value):
    from integrations.executive_mcp.web_ceo_v3 import validate_installed_mcp_profile_current
    with pytest.raises(ValueError):
        validate_installed_mcp_profile_current(value)


def test_combined_profile_does_not_expand_frozen_v2_selector():
    from integrations.executive_mcp.web_ceo import validate_installed_mcp_profile
    from integrations.executive_mcp.web_ceo_v3 import validate_installed_mcp_profile_current
    assert validate_installed_mcp_profile_current('web_ceo_release_v1') == 'web_ceo_release_v1'
    with pytest.raises(ValueError):
        validate_installed_mcp_profile('web_ceo_release_v1')


@pytest.mark.parametrize('value', [None, 0, 1, 'true', {}, []])
def test_os_transport_opt_in_requires_real_boolean(value):
    from tests.test_executive_workspace_mount import document
    raw = document(); raw['executive_mcp_profile'] = 'web_ceo_v3'; raw['os_executive_transport'] = value
    with pytest.raises(ValueError, match='boolean opt-in'): _module().validate_document(raw)


@pytest.mark.parametrize('profile', ['legacy', 'web_ceo_v2', 'web_ceo_sessions_v1', 'release_control_v1', 'personal_read', 'web_ceo_release_v1'])
def test_os_transport_cannot_enable_other_profiles(profile):
    from tests.test_executive_workspace_mount import document
    raw = document(); raw['executive_mcp_profile'] = profile; raw['os_executive_transport'] = True
    with pytest.raises(ValueError, match='boolean opt-in'): _module().validate_document(raw)


@pytest.mark.parametrize('resource', [None, '', False, [], {},
    'https://mcp.mastermind-x.com', 'https://mcp.mastermind-x.com/os/executive/',
    'https://mcp.mastermind-x.com/os/executive?x=1',
    'https://mcp.mastermind-x.com/os/executive#fragment',
    'https://mcp.mastermind-x.com:443/os/executive',
    'https://user@mcp.mastermind-x.com/os/executive',
    'http://mcp.mastermind-x.com/os/executive',
    'https://foreign.test/os/executive',
    'https://tunnel-service.gateway.unified-0.internal.api.openai.org/v1/mcp/tunnel_' + '1' * 32])
def test_os_audience_is_exact_and_not_a_connector_tunnel(resource):
    from tests.test_executive_workspace_mount import document
    raw = document()
    raw.update(executive_mcp_profile='web_ceo_v3', os_executive_transport=True,
               os_executive_resource=resource)
    with pytest.raises(ValueError, match='exact installed OS audience'):
        _module().validate_document(raw)


def test_os_audience_requires_explicit_opt_in_and_rejects_missing_value():
    module = _module()
    assert module.validate_os_executive_resource({}) is None
    for raw in ({'os_executive_resource': module.OS_EXECUTIVE_RESOURCE},
                {'os_executive_transport': False, 'os_executive_resource': module.OS_EXECUTIVE_RESOURCE},
                {'os_executive_transport': True, 'executive_mcp_profile': 'web_ceo_v3'}):
        with pytest.raises(ValueError, match='OS Executive resource'):
            module.validate_os_executive_resource(raw)


def test_os_audience_preserves_existing_tunnels_and_all_policy_grants():
    from tests.test_executive_mcp_app_composition import fixture
    from integrations.mastermind_executive_app.gateway import AppPolicies
    module = _module()
    policies = AppPolicies(read=fixture._read_policy(), submit=fixture._submit_policy())
    tunnel = 'https://tunnel-service.gateway.unified-0.internal.api.openai.org/v1/mcp/tunnel_' + '2' * 32
    raw = dict(executive_mcp_profile='web_ceo_v3', os_executive_transport=True,
               os_executive_resource=module.OS_EXECUTIVE_RESOURCE,
               executive_additional_resources=[tunnel])
    variants = module.build_additional_policies(raw, policies)
    assert [pair.submit.resource for pair in variants] == [tunnel, module.OS_EXECUTIVE_RESOURCE]
    for pair in variants:
        assert dataclasses.replace(pair.read, resource=policies.read.resource) == policies.read
        assert dataclasses.replace(pair.submit, resource=policies.submit.resource) == policies.submit
    assert policies.read.resource == fixture._read_policy().resource
    duplicate = AppPolicies(read=variants[1].read, submit=variants[1].submit)
    with pytest.raises(ValueError, match='cannot be duplicated'):
        module.build_additional_policies(raw, duplicate)

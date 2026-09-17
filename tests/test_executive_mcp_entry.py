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

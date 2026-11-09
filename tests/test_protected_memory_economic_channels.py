"""Actual local Unix captures reject ordinary callers before private/effect IO.

These negatives exercise the current Mac's kernel peer, NOT installed root or
Control authority. Positive installed/process qualification remains an explicit
premise of the joined disposable-owner tests; nothing is enrolled here.
"""
import os
import socket
import sys
import json
from pathlib import Path
import subprocess
import pytest

from scripts import protected_memory_economic_helper as helper
from scripts import protected_memory_model_runner as runner
from control_plane import protected_memory_economic_owner as root
from control_plane import protected_memory_economic_client as client
from control_plane import protected_memory_peer as peer
from control_plane import executive_installed_peer
from control_plane import executive_memory_issuer as issuer


def _ordinary_cli(mode, *, unsupported=False):
    """Actual executable exit closes child-owned FDs, including early refusal.

    Only the runner's outer UID predicate is substituted in its isolated child;
    the AF_UNIX kernel peer remains the genuine ordinary parent. The optional
    unsupported observation is a negative capability premise, never identity.
    """
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    code = r'''import json, os, runpy, sys, urllib.request
from pathlib import Path
from control_plane import protected_memory_economic_owner as economic
from control_plane import executive_installed_peer as installed
from control_plane import executive_peer_identity as peers
from control_plane import codex_provider_realm as realm
from control_plane import protected_memory_profile as profile
calls=[]
def blocked(name):
 def stop(*a,**k):
  calls.append(name)
  raise AssertionError("fixture prohibited IO")
 return stop
economic.qualify_helper_source=blocked("source")
installed.qualify_installed_peer=blocked("installed")
profile._read_config=blocked("config")
realm._native_open=blocked("credential")
urllib.request.build_opener=blocked("provider")
fd,mode,unsupported=int(sys.argv[1]),sys.argv[2],sys.argv[3]
if mode=="runner":os.geteuid=lambda:450
if unsupported=="1":
 def unavailable(*a):raise peers.PeerIdentityError("PEER_PLATFORM_UNSUPPORTED")
 peers._observe_socket=unavailable
name="protected_memory_model_runner.py" if mode=="runner" else "protected_memory_economic_helper.py"
path=Path.cwd()/"scripts"/name
sys.argv=[str(path),str(fd)]
try:runpy.run_path(str(path),run_name="__main__")
finally:print("FIXTURE_CALLS="+json.dumps(calls))
'''
    try:
        result = subprocess.run([sys.executable, '-c', code, str(a.fileno()), mode,
            '1' if unsupported else '0'], cwd=Path(__file__).resolve().parents[1],
            pass_fds=(a.fileno(),), capture_output=True, timeout=15)
        assert result.returncode == 75
        assert result.stdout == b'FIXTURE_CALLS=[]\n'
        assert result.stderr in (b'', b'PROTECTED_MEMORY_MODEL_UNAVAILABLE\n')
        a.close(); b.settimeout(.05)
        assert b.recv(1) == b''
    finally:
        a.close(); b.close()


def test_real_ordinary_unix_parent_cannot_reach_economic_owner_or_its_source_reader():
    assert os.geteuid() not in (0,450)
    _ordinary_cli('economic')


@pytest.mark.parametrize('unsupported', [False, True])
def test_real_foreign_peer_refuses_before_runner_ready_identity_config_or_credential(unsupported):
    assert os.geteuid() not in (0,450)
    _ordinary_cli('runner', unsupported=unsupported)


def test_early_wrong_uid_refusal_does_not_adopt_the_callers_duplicate(monkeypatch):
    # Causal preimage: Linux's ordinary1001 fails the M2-only501 prerequisite
    # BEFORE main adopts this FD. The caller still owns it until process exit.
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    fd=os.dup(a.fileno()); calls=[]
    monkeypatch.setattr(sys,'argv',['protected_memory_economic_helper.py',str(fd)])
    monkeypatch.setattr(helper.os,'geteuid',lambda:1001)
    monkeypatch.setattr(root,'qualify_helper_source',lambda:calls.append('source'))
    try:
        assert helper.main()==75 and calls==[]
        assert (os.fstat(fd).st_dev,os.fstat(fd).st_ino)==(os.fstat(a.fileno()).st_dev,os.fstat(a.fileno()).st_ino)
        a.close(); b.settimeout(.05)
        with pytest.raises(TimeoutError):b.recv(1)
        os.close(fd); fd=-1
        assert b.recv(1)==b''
    finally:
        a.close(); b.close()
        if fd>=0:os.close(fd)


@pytest.mark.parametrize('operation',['describe','qualify_transport','exchange','completed_result','economic'])
def test_genuine_ordinary_local_peer_cannot_reach_fixed_source_key_or_exchange(monkeypatch,operation):
    assert os.geteuid() not in (0,450) # genuine ordinary Mac/Linux caller, never Control/root
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM);calls=[]
    # Only the receiver process UID is substituted. The accepted socket's
    # kernel UID remains the genuine local ordinary user, never Control450.
    monkeypatch.setattr(issuer.os,'geteuid',lambda:0)
    monkeypatch.setattr(issuer,'_enrollment',lambda *_a:calls.append('key'))
    monkeypatch.setattr(issuer,'_exchange',lambda *_a:calls.append('ssh'))
    try:
        assert issuer.handle_memory_exchange({'schema':issuer.SCHEMA,'operation':operation},a)=={
            'schema':issuer.SCHEMA,'state':'REFUSED'}
        assert calls==[]
    finally:a.close();b.close()


@pytest.mark.parametrize('shape',['dict','clone','subclass'])
def test_no_public_receipt_or_nominal_clone_can_spend_current_paid_permission(monkeypatch,shape):
    calls=[]
    monkeypatch.setattr(client,'_exchange',lambda *_a,**_k:calls.append('root'))
    if shape=='dict':value={'phase':'ADMITTED','lease_id':'forged'}
    elif shape=='clone':value=object.__new__(client.EconomicAdmission)
    else:
        class Foreign(client.EconomicAdmission):pass
        value=object.__new__(Foreign)
    with pytest.raises(peer.ProtectedMemoryRefused):client.require(value,object())
    assert calls==[]

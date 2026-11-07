"""Actual local Unix captures reject ordinary callers before private/effect IO.

These negatives exercise the current Mac's kernel peer, NOT installed root or
Control authority. Positive installed/process qualification remains an explicit
premise of the joined disposable-owner tests; nothing is enrolled here.
"""
import os
import socket
import sys
import pytest

from scripts import protected_memory_economic_helper as helper
from scripts import protected_memory_model_runner as runner
from control_plane import protected_memory_economic_owner as root
from control_plane import protected_memory_economic_client as client
from control_plane import protected_memory_peer as peer
from control_plane import executive_installed_peer
from control_plane import executive_memory_issuer as issuer


def test_real_ordinary_unix_parent_cannot_reach_economic_owner_or_its_source_reader(monkeypatch):
    assert os.geteuid() not in (0,450) # genuine ordinary Mac/Linux caller, never Control/root
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    fd=os.dup(a.fileno());calls=[]
    monkeypatch.setattr(sys,'argv',['protected_memory_economic_helper.py',str(fd)])
    monkeypatch.setattr(root,'qualify_helper_source',lambda:calls.append('source'))
    try:
        assert helper.main()==75
        assert calls==[]
        a.close();b.settimeout(.05)
        assert b.recv(1)==b''
    finally:
        a.close();b.close()
        try:os.close(fd)
        except OSError:pass


def test_real_foreign_peer_refuses_before_runner_ready_identity_config_or_credential(monkeypatch):
    assert os.geteuid() not in (0,450) # genuine ordinary Mac/Linux caller, never Control/root
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    fd=os.dup(a.fileno());calls=[]
    monkeypatch.setattr(sys,'argv',['protected_memory_model_runner.py',str(fd)])
    # Test only the first outer UID prerequisite; the socket capture itself is
    # genuine ordinary-user UID and cannot be promoted by this Python function override.
    monkeypatch.setattr(runner.os,'geteuid',lambda:450)
    monkeypatch.setattr(executive_installed_peer,'qualify_installed_peer',lambda *_a,**_k:calls.append('installed'))
    monkeypatch.setattr(runner,'_credential',lambda *_a:calls.append('credential'))
    monkeypatch.setattr(runner,'_post',lambda *_a:calls.append('provider'))
    try:
        assert runner.main()==75 and calls==[]
        a.close();b.settimeout(.05)
        assert b.recv(1)==b''
    finally:
        a.close();b.close()
        try:os.close(fd)
        except OSError:pass


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

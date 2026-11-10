import importlib.util
import json
from pathlib import Path
import socket
import struct
import threading

import pytest

_PATH = Path(__file__).parents[1] / 'ops/native_fabric/quota_continuity/candidate/paid_controller_channel.py'
_SPEC = importlib.util.spec_from_file_location('paid_controller_channel', _PATH)
m = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(m)
NONCE = 'a' * 64


def test_single_exchange_closes_client_descriptor():
    left, right = socket.socketpair()
    found = []
    def server():
        found.append(m.receive_lease(left, run_id='Attempt-1', nonce=NONCE))
        m.answer_lease(left, run_id='Attempt-1', lease_id='lease-1', nonce=NONCE,
                       capsule={'token': 'v2.synthetic-fixture'})
        assert left.recv(1) == b''
        left.close()
    thread = threading.Thread(target=server)
    thread.start()
    assert m.request_lease(right, run_id='Attempt-1', lease_id='lease-1', nonce=NONCE) == {
        'token': 'v2.synthetic-fixture'}
    thread.join(2)
    assert not thread.is_alive()
    assert found == ['lease-1']
    assert right.fileno() == -1


@pytest.mark.parametrize('mutate', [
    lambda d: {**d, 'pid': 42},
    lambda d: {**d, 'run_id': 'other'},
    lambda d: {**d, 'nonce': 'b' * 64},
    lambda d: {**d, 'lease_id': 'credential\nsecret'},
    lambda d: {**d, 'lease_id': 'x' * 129},
    lambda d: {**d, 'lease_id': True},
    lambda d: {**d, 'schema': 'other'},
])
def test_request_closed_binding(mutate):
    left, right = socket.socketpair()
    try:
        m.send(right, mutate(dict(schema=m.REQUEST_SCHEMA, run_id='Attempt-1',
                                 lease_id='lease-1', nonce=NONCE)), limit=m.MAX_REQUEST)
        with pytest.raises(m.ChannelRefused):
            m.receive_lease(left, run_id='Attempt-1', nonce=NONCE)
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize('raw', [b'{}', b'[]', b'{"a":1,"a":2}', b'{"a":NaN}',
                                 b'{"a":1e999}', b'\xff', b''])
def test_bad_frames_fail_closed(raw):
    left, right = socket.socketpair()
    try:
        right.sendall(struct.pack('!I', len(raw)) + raw)
        right.shutdown(socket.SHUT_WR)
        with pytest.raises(m.ChannelRefused):
            if raw == b'{}':
                m.receive_lease(left, run_id='Attempt-1', nonce=NONCE)
            else:
                m.receive(left, limit=m.MAX_REQUEST)
    finally:
        left.close()
        right.close()


def test_bound_checked_before_body_read():
    left, right = socket.socketpair()
    try:
        right.sendall(struct.pack('!I', m.MAX_REQUEST + 1))
        with pytest.raises(m.ChannelRefused, match='frame_refused'):
            m.receive(left, limit=m.MAX_REQUEST)
    finally:
        left.close()
        right.close()


def test_timeout_closes_client():
    left, right = socket.socketpair()
    try:
        right.settimeout(.01)
        with pytest.raises(TimeoutError):
            m.request_lease(right, run_id='Attempt-1', lease_id='lease-1', nonce=NONCE)
        assert right.fileno() == -1
    finally:
        left.close()


def test_cli_diagnostic_does_not_echo_input(capsys):
    secret = 'credential-shaped-fake\x1b[31m/secret/path'
    assert m.main([secret, secret, secret, secret]) == 78
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err == 'CANONICAL_PAID_PRIVATE_CHANNEL_REFUSED before_provider=1\n'
    assert secret not in captured.err


def _intent(tmp_path, *, prefix=None):
    import os
    p=tmp_path/'original.log'
    fd=os.open(p,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    os.write(fd, prefix if prefix is not None else (
        'CANONICAL_PAID_REQUIRED schema=1 payload_sha256='+'b'*64+'\n').encode())
    os.fsync(fd)
    intent=m.ProviderIntent(fd,payload_sha256='b'*64)
    os.close(fd)
    return p,intent


def test_provider_intent_consumed_once_in_original_file(tmp_path):
    p,intent=_intent(tmp_path)
    try:
        intent.consume()
        with pytest.raises(m.ChannelRefused):intent.consume()
        assert p.read_bytes().count(b'CANONICAL_PAID_PROVIDER_INTENT')==1
    finally:intent.close()


def test_provider_intent_concurrent_calls_have_one_winner(tmp_path):
    p,intent=_intent(tmp_path);out=[]
    def consume():
        try:intent.consume();out.append('consumed')
        except m.ChannelRefused:out.append('refused')
    threads=[threading.Thread(target=consume) for _ in range(8)]
    try:
        for t in threads:t.start()
        for t in threads:t.join(2)
        assert sorted(out)==['consumed']+['refused']*7
        assert p.read_bytes().count(b'CANONICAL_PAID_PROVIDER_INTENT')==1
    finally:intent.close()


def test_partial_intent_write_permanently_holds_same_owner(tmp_path,monkeypatch):
    import os
    p,intent=_intent(tmp_path)
    real=os.write
    def partial(fd,raw):return real(fd,raw[:3])
    monkeypatch.setattr(m.os,'write',partial)
    try:
        with pytest.raises(m.ChannelRefused):intent.consume()
        monkeypatch.setattr(m.os,'write',real)
        with pytest.raises(m.ChannelRefused):intent.consume()
        assert p.read_bytes().endswith(b'CAN')
    finally:intent.close()


def test_prior_or_wrong_original_record_refuses(tmp_path):
    p,intent=_intent(tmp_path,prefix=b'legacy run or forged text\n')
    try:
        with pytest.raises(m.ChannelRefused):intent.consume()
        assert p.read_bytes()==b'legacy run or forged text\n'
    finally:intent.close()

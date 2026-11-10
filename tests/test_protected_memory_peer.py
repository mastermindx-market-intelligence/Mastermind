"""Fixture-explicit protected installation/kernel plus real temporary Runtime.

Kernel/installed-service observations are inert explicit premises using the
incumbent private fixture issuer. They are NOT host enrollment, source rights,
actual SSH, provider execution or scientific admission. Production has no such
callback port. Actual Runtime/opaque token/Event reads remain genuine SQLite.
"""
import dataclasses
import hashlib
import json
import socket

import pytest

from control_plane import protected_memory_peer as owner
from control_plane import executive_peer_identity as peer
from control_plane import native_memory_admission as admission
from tests.test_native_memory_admission import claimed
from tests.test_executive_peer_identity import owner_observation, bind_fixture


@pytest.fixture
def installed(monkeypatch):
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    current = {'observation': peer._KernelObservation(b'A'*32, 450, 1234, 5678,
        peer._descriptor_identity(a)), 'label': 'com.mastermind.executive.control'}
    monkeypatch.setattr(peer, '_observe_socket', lambda conn: current['observation'])
    def qualify(capture, *, role):
        assert role == 'control'
        observation = dataclasses.replace(owner_observation(capture), service_label=current['label'])
        return bind_fixture(capture, observation)
    monkeypatch.setattr(owner, 'qualify_installed_peer', qualify)
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 0)
    try: yield a, current
    finally: a.close(); b.close()


def prepare(runtime, lease, connection, monkeypatch):
    # Root's observation is DATA. The opaque Runtime claim remains in Control;
    # only canonical JSON is sent to the root receiver, which requalifies peer.
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 0)
    observed = owner.observe_control_owner(connection)
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 450)
    claim = admission.capture_memory_runtime_claim(runtime, lease)
    control = owner.capture_control_memory_intent(claim, observed)
    projection = json.loads(owner.canonical(owner.require_control_memory_intent(control)))
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 0)
    root = owner.accept_protected_memory_intent(projection, connection)
    return control, root


def test_preinput_is_derived_from_actual_claim_without_future_input_cycle(claimed, installed, monkeypatch):
    runtime, job, lease = claimed
    connection, _ = installed
    before = runtime.events.list_events()
    control, value = prepare(runtime, lease, connection, monkeypatch)
    request, ref = owner.require_protected_memory_intent(value)
    raw = owner._ISSUED[value].original
    material = json.loads(raw)
    assert ref == {'schema': owner.SCHEMA, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    assert request['intent']['participant_binding_sha256'] == ref['sha256']
    assert material['owner']['mode'] == owner.MODE
    assert material['native_source_locator']['root_id'] != job.root_job_id
    assert material['runtime_admission']['job_id'] == job.job_id
    assert material['runtime_admission']['attempt_id'] == lease.attempt.attempt_id
    assert material['runtime_admission']['claim_ref']['event_id'] > 0
    assert 'input_sha256' not in raw.decode() and 'result_sha256' not in raw.decode()
    assert lease.lease_token not in raw.decode()
    assert runtime.events.list_events() == before


@pytest.mark.parametrize('shape', ['dict', 'clone', 'subclass'])
def test_claimed_opaque_shape_cannot_issue_source_request(claimed, installed, monkeypatch, shape):
    runtime, _, lease = claimed
    _, cap = prepare(runtime, lease, installed[0], monkeypatch)
    if shape == 'dict': forged = {'schema': owner.SCHEMA}
    elif shape == 'clone': forged = object.__new__(owner.ProtectedMemoryIntent)
    else:
        class Other(owner.ProtectedMemoryIntent): pass
        forged = object.__new__(Other)
    with pytest.raises(owner.ProtectedMemoryRefused): owner.require_protected_memory_intent(forged)
    assert owner.require_protected_memory_intent(cap)[0]['action'] == 'prepare_case'


@pytest.mark.parametrize('change', ['unqualified_cli', 'peer_epoch', 'role', 'closed_socket'])
def test_current_protected_context_loss_refuses_existing_handle(claimed, installed, monkeypatch, change):
    runtime, _, lease = claimed
    connection, current = installed
    _, cap = prepare(runtime, lease, connection, monkeypatch)
    if change == 'unqualified_cli': monkeypatch.setattr(owner.os, 'geteuid', lambda: 501)
    elif change == 'peer_epoch':
        current['observation'] = dataclasses.replace(current['observation'], audit_token=b'B'*32, pidversion=5679)
    elif change == 'role': current['label'] = 'com.mastermind.executive.mcp'
    else: connection.close()
    with pytest.raises(owner.ProtectedMemoryRefused): owner.require_protected_memory_intent(cap)


def test_non_socket_or_current_uid_alone_never_replaces_peer(claimed, monkeypatch):
    runtime, _, lease = claimed
    claim = admission.capture_memory_runtime_claim(runtime, lease)
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 0)
    for value in ({'uid': 450}, True, None):
        with pytest.raises(owner.ProtectedMemoryRefused): owner.accept_protected_memory_intent({'schema': owner.SCHEMA}, value)


def test_control_rereads_actual_runtime_and_does_not_export_opaque_lease(claimed, installed, monkeypatch):
    runtime, job, lease = claimed
    control, root = prepare(runtime, lease, installed[0], monkeypatch)
    assert lease.lease_token not in owner._ISSUED[root].original.decode()
    with runtime.store.transaction() as con:
        con.execute("UPDATE jobs SET status='CANCELLED' WHERE job_id=?", (job.job_id,))
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 450)
    with pytest.raises(owner.ProtectedMemoryRefused): owner.require_control_memory_intent(control)


def test_other_service_cannot_submit_a_copied_control_projection(claimed, installed, monkeypatch):
    runtime, _, lease = claimed
    control, root = prepare(runtime, lease, installed[0], monkeypatch)
    copied = json.loads(owner._ISSUED[root].original)
    installed[1]['observation'] = dataclasses.replace(installed[1]['observation'], euid=501)
    with pytest.raises(owner.ProtectedMemoryRefused): owner.accept_protected_memory_intent(copied, installed[0])

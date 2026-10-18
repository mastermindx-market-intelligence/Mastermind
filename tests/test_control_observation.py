"""Closed projection/equivalence and original-owner recovery; no host effects."""
import dataclasses
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_control_observation as c
from control_plane import executive_installed_peer as peer
from ops.executive_os import autonomy_control as owner
from ops.executive_os import control_observation as publisher

SHA = 'a' * 40


def control():
    return json.dumps(dict(schema_version='mastermind.executive_control_config/v1',
        proof_base_sha=SHA, control_uid=c.CONTROL_UID,
        python_runtime_provenance_digest='b' * 64,
        private_account_secret='never-project-this')).encode()


def identity(raw):
    return (7, 10, 0o100440, 0, c.CONTROL_UID, 1, len(raw), 100, 200)


def stat_value(values):
    return SimpleNamespace(**dict(zip(('st_dev','st_ino','st_mode','st_uid','st_gid',
        'st_nlink','st_size','st_mtime_ns','st_ctime_ns'), values)))


def test_projection_contains_only_closed_nonsecret_values():
    raw = control(); result = c.encode_observation(raw, identity(raw), SHA)
    parsed = c.parse_observation(result)
    assert set(parsed) == c.FIELDS
    assert parsed['control_sha256'] == hashlib.sha256(raw).hexdigest()
    assert b'never-project-this' not in result and b'private_account_secret' not in result


@pytest.mark.parametrize('change', [
    {'control_uid': True}, {'control_uid': c.CONTROL_UID + 1},
    {'control_acl_absent': 1}, {'control_acl_absent': False},
    {'source_release_sha': '0'*40}, {'source_release_sha': 'b'*64},
    {'control_sha256': 'g'*64}, {'python_runtime_provenance_digest': None},
    {'arbitrary': 'field'}, {'control_identity': [True]*9},
    {'control_identity': [0]*9}, {'schema': 'another-schema'},
])
def test_malformed_or_authority_shaped_projection_refuses(change):
    raw = control(); value = c.parse_observation(c.encode_observation(raw, identity(raw), SHA))
    value.update(change)
    with pytest.raises(c.ControlObservationError): c.parse_observation(json.dumps(value).encode())


@pytest.mark.parametrize('raw', [b'', b'{}'*5000, b'{"schema":1,"schema":2}',
                               b'{"a":NaN}', b'[]', b'{"a":"\xff"}'])
def test_unbounded_duplicate_nonascii_or_nonobject_refuses(raw):
    with pytest.raises(c.ControlObservationError): c.parse_observation(raw)


@pytest.fixture
def observed(monkeypatch):
    raw = control(); ident = identity(raw)
    state = dict(raw=raw, identity=ident, sealed=c.encode_observation(raw, ident, SHA),
                 busy=False, private_reads=0, deny_private=False, reads=0)
    ancestors = (('/fixed/root', (1, 2, 0o40755, 0, 0, 2, 10, 11, 12)),)
    monkeypatch.setattr(peer, '_observe_ancestors', lambda path, budget: ancestors)
    def lstat(path):
        if path == c.TRANSACTION_PATH:
            if state['busy']: return stat_value(ident)
            raise FileNotFoundError()
        assert path == c.CONTROL_PATH
        return stat_value(state['identity'])
    def read(path, **kwargs):
        state['reads'] += 1
        if path == c.CONTROL_PATH:
            state['private_reads'] += 1
            assert not state['deny_private'], 'Studio opened private Control content'
            assert kwargs['expected_gid'] == c.CONTROL_UID and kwargs['expected_mode'] == 0o440
            return state['raw'], stat_value(state['identity'])
        assert path == c.OBSERVATION_PATH
        assert kwargs['maximum'] == c.MAX_BYTES and kwargs['expected_gid'] == 0
        assert kwargs['expected_mode'] == 0o444
        if state.get('sealed_untrusted'): raise peer.PeerIdentityError('SERVICE_OBJECT_NOT_ROOT_OWNED')
        return state['sealed'], stat_value(ident)
    monkeypatch.setattr(peer, '_lstat', lstat)
    monkeypatch.setattr(peer, '_read_trusted_bytes', read)
    return state


def test_exact_direct_projection_equivalence_without_private_content_open(observed):
    direct = peer._verify_control_projection(peer._Budget(10))
    role = peer._verify_role_config(peer._role_topology('control'), SHA, peer._Budget(10))
    observed['deny_private'] = True
    sealed = peer._verify_studio_control_observation(peer._Budget(10))
    assert sealed == direct
    assert dataclasses.replace(sealed, provenance_digest='') == role
    assert observed['private_reads'] == 2


@pytest.mark.parametrize('index,value', [(0,8),(1,11),(2,0o100644),(3,501),
    (4,0),(5,2),(6,1),(7,101),(8,201)])
def test_any_live_identity_drift_refuses_even_with_identical_sealed_bytes(observed,index,value):
    changed = list(observed['identity']); changed[index] = value
    observed['identity'] = tuple(changed); observed['deny_private'] = True
    with pytest.raises(peer.PeerIdentityError):
        peer._verify_studio_control_observation(peer._Budget(10))
    assert observed['private_reads'] == 0


@pytest.mark.parametrize('flag', ['busy', 'sealed_untrusted'])
def test_busy_transaction_and_untrusted_projection_refuse(observed, flag):
    observed[flag] = True; observed['deny_private'] = True
    with pytest.raises(peer.PeerIdentityError):
        peer._verify_studio_control_observation(peer._Budget(10))


def test_metadata_changes_during_read_refuse(observed,monkeypatch):
    original = peer._read_trusted_bytes
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        observed['identity'] = (*observed['identity'][:8], 999)
        return result
    monkeypatch.setattr(peer, '_read_trusted_bytes', read)
    with pytest.raises(peer.PeerIdentityError):
        peer._verify_studio_control_observation(peer._Budget(10))


def test_new_qualifier_is_fixed_control_and_public_reader_is_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr(peer, '_qualify_installed_peer_core', lambda p,**kw:calls.append(kw))
    peer.qualify_installed_peer(object(), role='gateway')
    peer.qualify_installed_peer(object(), role='control')
    peer._qualify_installed_control_for_studio(object(), deadline_monotonic_ns=10)
    assert calls == [{'role':'gateway'}, {'role':'control'},
        {'role':'control','deadline_monotonic_ns':10,'studio_control':True}]
    with pytest.raises(TypeError):
        peer._qualify_installed_control_for_studio(object(), role='gateway',deadline_monotonic_ns=10)


@pytest.fixture
def publication(monkeypatch):
    raw = control(); sealed = c.encode_observation(raw, identity(raw), SHA)
    state = dict(sealed=None, expected=sealed, writes=0, lose_reply=False)
    monkeypatch.setattr(publisher, '_snapshot', lambda sha:(state['expected'], ('custody',)))
    monkeypatch.setattr(publisher, '_retained', lambda:state['sealed'])
    def write(path, value, **kw):
        assert str(path) == c.OBSERVATION_PATH
        assert kw == dict(mode=0o444,uid=0,gid=0,replace=state['sealed'] is not None)
        state['writes'] += 1; state['sealed'] = value
        if state['lose_reply']: raise OSError('lost original publication reply')
    monkeypatch.setattr(owner, '_atomic_file', write)
    return state


def test_exact_projection_is_verified_without_a_second_write(publication):
    publisher._publish(SHA, allow_publication=True)
    publisher._publish(SHA, allow_publication=True)
    publisher._publish(SHA, allow_publication=False)
    assert publication['writes'] == 1


def test_lost_projection_reply_recovers_by_readback_only(publication):
    publication['lose_reply'] = True
    with pytest.raises(owner.TransactionEffectUnknown): publisher._publish(SHA, allow_publication=True)
    publisher._publish(SHA, allow_publication=False)
    assert publication['writes'] == 1


@pytest.mark.parametrize('old', [None, b'original stale projection'])
def test_recovery_never_publishes_missing_or_stale_projection(publication, old):
    publication['sealed'] = old
    with pytest.raises(owner.TransactionEffectUnknown): publisher._publish(SHA, allow_publication=False)
    assert publication['writes'] == 0


def test_publication_target_drift_is_unknown_and_never_accepted(publication,monkeypatch):
    original = owner._atomic_file
    def write(*args, **kwargs):
        original(*args, **kwargs); publication['expected'] = b'changed actual config'
    monkeypatch.setattr(owner,'_atomic_file',write)
    with pytest.raises(owner.TransactionEffectUnknown): publisher._publish(SHA,allow_publication=True)
    assert publication['writes'] == 1


def test_publisher_requires_root_and_its_exact_installed_source(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda:501)
    with pytest.raises(Exception): publisher.publish_for_install(SHA)
    monkeypatch.setattr(os, 'geteuid', lambda:0)
    with pytest.raises(c.ControlObservationError,match='installed_source'):
        publisher.publish_for_install(SHA)


def test_transaction_cannot_be_supplied_as_unowned_data(monkeypatch):
    monkeypatch.setattr(publisher,'_source',lambda *a:pytest.fail('unowned source reached'))
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher.publish_for_transaction(SimpleNamespace(),{})


def test_direct_file_lookalike_classes_cannot_bypass_canonical_guard(monkeypatch):
    import runpy
    # Import definitions only, never invoke main or any host operation.
    duplicate = runpy.run_path(owner.__file__, run_name='inert_foreign_owner')
    host = duplicate['ProductionTransactionHost']()
    prior = duplicate['ConfigEvidence']('c'*64, 'd'*64, {}, {})
    candidate = duplicate['CandidateConfigs']({}, {}, b'{}', b'{}', 'c'*64, 'd'*64)
    tx = duplicate['TransactionContext']('autonomy-'+'1'*12, SHA, prior, candidate, None)
    host._active_transaction = tx
    host._transaction_owner_fd = 123
    monkeypatch.setattr(publisher, '_source', lambda *a: pytest.fail('foreign class admitted'))
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher.publish_for_transaction(host, tx)


@pytest.fixture
def original_transaction(monkeypatch):
    raw = control(); digest = hashlib.sha256(raw).hexdigest()
    prior = owner.ConfigEvidence(control_sha256=digest, worker_sha256='c'*64,
        control=json.loads(raw), worker={}, control_bytes=raw, worker_bytes=b'{}')
    candidates = owner.CandidateConfigs(prior.control, prior.worker, raw, b'{}', digest, 'c'*64)
    tx = owner.TransactionContext('autonomy-'+'1'*12,SHA,prior,candidates,None)
    host = owner.ProductionTransactionHost()
    host._active_transaction = tx; host._transaction_owner_fd = 123
    journal = dict(transaction_id=tx.transaction_id,expected_sha=SHA,
                   prior_control_sha256=digest,target_control_sha256=digest)
    monkeypatch.setattr(publisher,'_source',lambda sha:None)
    monkeypatch.setattr(host,'_config_root_safe',lambda:None)
    monkeypatch.setattr(host,'_verify_published_inode',lambda fd:None)
    monkeypatch.setattr(host,'_manifest',lambda:journal)
    monkeypatch.setattr(host,'_persist_phase',lambda tx,phase:journal.update(phase=phase))
    monkeypatch.setattr(owner,'_read_root_file',lambda *args,**kw:(raw,None))
    return host,tx,journal


@pytest.mark.parametrize('phase', ['RECEIPT_REPLACED', publisher.PUBLICATION_PHASE])
@pytest.mark.parametrize('retained', [None, b'stale observation'])
def test_reconstructed_disarm_cannot_turn_phase_or_equal_config_into_publication(
        original_transaction, publication, phase, retained):
    host, tx, journal = original_transaction
    journal.update(operation='DISARM', phase=phase)
    before = dict(journal)
    publication['sealed'] = retained
    # Even authentic classes, the original ID and an acquired owner descriptor
    # do not recreate the exited process's publication provenance.
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher.publish_for_transaction(host, tx)
    assert publication['writes'] == 0
    assert publication['sealed'] == retained
    assert journal == before


def test_reconstructed_disarm_exact_observation_is_readback_only(
        original_transaction, publication):
    host, tx, journal = original_transaction
    journal.update(operation='DISARM', phase=publisher.PUBLICATION_PHASE)
    before = dict(journal)
    publication['sealed'] = publication['expected']
    publisher.publish_for_transaction(host, tx)
    assert publication['writes'] == 0
    assert journal == before


@pytest.mark.parametrize('fresh', [False,True])
def test_real_original_context_only_grants_publication_after_its_config_write(original_transaction,monkeypatch,fresh):
    host,tx,journal = original_transaction
    if fresh:
        host._control_observation_fresh_transaction = tx
        host._control_observation_origin = (os.getpid(),123,tx.transaction_id,SHA)
    calls = []
    monkeypatch.setattr(publisher,'_publish',lambda sha,**kw:calls.append((sha,kw)))
    publisher.publish_for_transaction(host,tx)
    assert calls == [(SHA,dict(allow_publication=fresh,control_sha256=tx.candidates.control_sha256))]


@pytest.mark.parametrize('changed', ['context','owner','journal','current_bytes'])
def test_changed_original_context_cannot_publish(original_transaction,monkeypatch,changed):
    host,tx,journal = original_transaction
    host._control_observation_fresh_transaction = tx
    monkeypatch.setattr(publisher,'_publish',lambda *a,**kw:pytest.fail('foreign context published'))
    if changed == 'context': host._active_transaction = dataclasses.replace(tx)
    elif changed == 'owner': host._transaction_owner_fd = None
    elif changed == 'journal': journal['transaction_id'] = 'foreign'
    else: monkeypatch.setattr(owner,'_read_root_file',lambda *a,**kw:(b'foreign',None))
    with pytest.raises(owner.TransactionEffectUnknown): publisher.publish_for_transaction(host,tx)


def test_failed_projection_keeps_original_marker_and_archives(monkeypatch,tmp_path):
    from tests.test_executive_autonomy_control import _inprocess_marker_host,_harness_configs
    _,marker = _inprocess_marker_host(monkeypatch,tmp_path)
    host = owner.ProductionTransactionHost(); prior = _harness_configs(host)
    tx = owner.TransactionContext(host.new_transaction_id(),SHA,prior,
        owner.derive_candidate_configs(prior,armed=True),None)
    try:
        host.begin_transaction(tx)
        before = {p.name:p.read_bytes() for p in marker.iterdir()}
        def unknown(*args): raise owner.TransactionEffectUnknown()
        monkeypatch.setattr(publisher,'publish_for_transaction',unknown)
        with pytest.raises(owner.TransactionEffectUnknown): host.complete_transaction(tx)
        assert {p.name:p.read_bytes() for p in marker.iterdir()} == before
        assert host._transaction_owner_fd is not None
    finally:
        host._release_transaction_owner()


@pytest.mark.parametrize('origin', [None, (999,123,'wrong','a'*40)])
def test_a_reclaimed_context_cannot_publish_even_after_a_config_write(original_transaction,monkeypatch,origin):
    host,tx,journal = original_transaction
    host._control_observation_fresh_transaction = tx
    host._control_observation_origin = origin
    calls = []
    monkeypatch.setattr(publisher,'_publish',lambda sha,**kw:calls.append(kw))
    publisher.publish_for_transaction(host,tx)
    assert calls == [dict(allow_publication=False,control_sha256=tx.candidates.control_sha256)]


def test_original_owner_restored_preimage_joins_archive_and_retained_target(original_transaction,monkeypatch):
    host,tx,journal = original_transaction
    journal.update(target_control_sha256='d'*64,prior_worker_sha256=tx.prior_configs.worker_sha256,
                   operation='CEO_SUBMIT_ARM',phase='CONTROL_OVERRIDE_RESTORED')
    monkeypatch.setattr(host,'_archived_configs',lambda sha:tx.prior_configs)
    host._control_observation_fresh_transaction = tx
    host._control_observation_origin = (os.getpid(),123,tx.transaction_id,SHA)
    calls = []
    monkeypatch.setattr(publisher,'_publish',lambda sha,**kw:calls.append(kw))
    publisher.publish_for_transaction(host,tx)
    assert calls == [dict(allow_publication=True,control_sha256=tx.prior_configs.control_sha256)]
    assert journal['target_control_sha256'] == 'd'*64
    journal['phase'] = 'LOCKED'
    with pytest.raises(owner.TransactionEffectUnknown): publisher.publish_for_transaction(host,tx)
    assert len(calls) == 1


def test_qualification_failure_at_closeout_is_unknown_never_ordinary_rollback(original_transaction,monkeypatch):
    host,tx,journal = original_transaction
    def unavailable(sha): raise OSError('source unavailable')
    monkeypatch.setattr(publisher,'_source',unavailable)
    with pytest.raises(owner.TransactionEffectUnknown): publisher.publish_for_transaction(host,tx)


def test_publisher_rejects_different_config_digest_before_effect(publication):
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher._publish(SHA,allow_publication=True,control_sha256='c'*64)
    assert publication['writes'] == 0


@pytest.mark.parametrize('phase', [publisher.PUBLICATION_PHASE, publisher.ROLLBACK_PUBLICATION_PHASE])
def test_projection_uncertainty_cannot_repeat_original_restore(monkeypatch, phase):
    from tests.test_executive_autonomy_control import (
        _ceo_submit_evidence, FakeCeoSubmitHost, SHA as release, NOW,
    )
    prior = _ceo_submit_evidence(armed=False)
    host = owner.ProductionCeoSubmitHost()
    manifest = dict(operation='CEO_SUBMIT_ARM', phase=phase,
        transaction_id='autonomy-7a7a7a7a7a7a', expected_sha=release,
        **{owner._CONTROL_LAUNCHD_PREIMAGE_FIELD:True})
    monkeypatch.setattr(host,'effective_uid',lambda:0)
    monkeypatch.setattr(host,'require_exact_install',lambda sha:release)
    monkeypatch.setattr(host,'_claim_transaction_owner',lambda:None)
    monkeypatch.setattr(host,'_manifest',lambda:dict(manifest))
    monkeypatch.setattr(host,'_archived_configs',lambda sha:prior)
    monkeypatch.setattr(host,'executive_app_binding',FakeCeoSubmitHost().executive_app_binding)
    monkeypatch.setattr(host,'ceo_submit_separation',lambda cfg:owner.CeoSubmitSeparation(
        True,458,452,False,False,False))
    monkeypatch.setattr(host,'rollback_ceo_submit',lambda *a:pytest.fail('restore replay'))
    monkeypatch.setattr(host,'complete_transaction',lambda *a:pytest.fail('uncertain marker cleared'))
    def unavailable(*a): raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(publisher,'verify_ceo_rollback_readback',unavailable)
    with pytest.raises(owner.TransactionEffectUnknown):
        host.recover_ceo_submit_effect_unknown(owner.CeoSubmitRequest(release),now=NOW)


@pytest.mark.parametrize('retained', [True, False])
def test_original_publication_lost_response_is_readback_only_even_in_same_process(
        original_transaction, publication, monkeypatch, retained):
    host,tx,journal = original_transaction
    host._control_observation_fresh_transaction = tx
    host._control_observation_origin = (os.getpid(),123,tx.transaction_id,SHA)
    publication['lose_reply'] = True
    with pytest.raises(owner.TransactionEffectUnknown): publisher.publish_for_transaction(host,tx)
    assert journal['phase'] == publisher.PUBLICATION_PHASE
    assert publication['writes'] == 1
    if not retained:
        publication['sealed'] = None
        with pytest.raises(owner.TransactionEffectUnknown): publisher.publish_for_transaction(host,tx)
    else:
        publisher.publish_for_transaction(host,tx)
    assert publication['writes'] == 1


@pytest.mark.parametrize('proven', [True, False])
def test_independent_original_recovery_only_publishes_after_completed_restore_proofs(
        original_transaction, monkeypatch, proven):
    host,tx,journal = original_transaction
    journal.update(phase='CONTROL_OVERRIDE_RESTORED', operation='CEO_SUBMIT_ARM')
    host._control_observation_fresh_transaction = tx
    host._control_observation_recovery_owner = (os.getpid(),123,tx.transaction_id,SHA)
    if proven: host._control_observation_rollback_proven = tx
    calls = []
    monkeypatch.setattr(publisher,'_publish',lambda sha,**kw:calls.append(kw))
    publisher.publish_for_transaction(host,tx)
    assert calls[0]['allow_publication'] is proven
    assert journal['phase'] == (publisher.ROLLBACK_PUBLICATION_PHASE if proven else 'CONTROL_OVERRIDE_RESTORED')


def test_recovered_rollback_requires_prior_current_projection_before_live_proof(original_transaction,monkeypatch):
    host,tx,journal = original_transaction
    journal.update(phase='CONTROL_OVERRIDE_RESTORED',
                   **{owner._CONTROL_LAUNCHD_PREIMAGE_FIELD:False})
    monkeypatch.setattr(host,'load_ceo_submit_configs',lambda sha:tx.prior_configs,raising=False)
    monkeypatch.setattr(host,'_read_control_launchd_disabled_override',lambda:False,raising=False)
    monkeypatch.setattr(host,'existing_ceo_submit_receipt',lambda:{'observed_at':'2026-10-14T00:00:00Z'},raising=False)
    monkeypatch.setattr(owner,'validate_ceo_submit_receipt_document',lambda *a,**kw:True)
    monkeypatch.setattr(owner,'build_ceo_submit_receipt',lambda *a,**kw:{'observed_at':'2026-10-14T00:00:00Z'})
    tx.prior_configs.control['ceo_submit_armed'] = False
    monkeypatch.setattr(host,'_loaded',lambda label:pytest.fail('missing observation reached live probe'),raising=False)
    def absent(*args): raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(publisher,'publish_for_transaction',absent)
    with pytest.raises(owner.TransactionEffectUnknown): publisher.verify_ceo_rollback_readback(host,tx,None)


@pytest.fixture
def publication_custody(monkeypatch):
    """Real snapshot/publish logic; only trusted I/O is an inert fixture."""
    raw = control()
    parent = str(Path(c.OBSERVATION_PATH).parent)
    ancestors = (('/', (7, 2, 0o40755, 0, 0, 20, 10, 11, 12)),
                 (parent, (7, 3, 0o40755, 0, 0, 2, 10, 11, 12)))
    state = dict(raw=raw, identity=identity(raw), ancestors=ancestors,
                 sealed=None, writes=0, mutate=lambda: None)
    monkeypatch.setattr(peer, '_observe_ancestors',
                        lambda path, budget: state['ancestors'])
    def read(path, **kwargs):
        assert path == c.CONTROL_PATH
        assert kwargs['expected_mode'] == 0o440
        assert kwargs['expected_gid'] == c.CONTROL_UID
        result = state['raw'], stat_value(state['identity'])
        state.get('during_read', lambda: None)()
        return result
    monkeypatch.setattr(peer, '_read_trusted_bytes', read)
    monkeypatch.setattr(publisher, '_retained', lambda: state['sealed'])
    def write(path, value, **kwargs):
        assert str(path) == c.OBSERVATION_PATH
        assert kwargs == dict(mode=0o444, uid=0, gid=0,
                              replace=state['sealed'] is not None)
        state['writes'] += 1
        state['sealed'] = value
        state['mutate']()
    monkeypatch.setattr(owner, '_atomic_file', write)
    def change_ancestor(ancestor, index, delta=1):
        changed = list(state['ancestors'])
        path, values = changed[ancestor]
        values = list(values); values[index] += delta
        changed[ancestor] = path, tuple(values)
        state['ancestors'] = tuple(changed)
    state['change_ancestor'] = change_ancestor
    return state


@pytest.mark.parametrize('delta', [0, 1])
def test_first_receipt_creation_accepts_its_own_directory_entry(publication_custody, delta):
    state = publication_custody
    def publish_changes():
        for index in (5, 6, 7, 8):
            state['change_ancestor'](1, index, delta if index == 5 else 1)
    state['mutate'] = publish_changes
    digest = publisher._publish(SHA, allow_publication=True)
    assert digest == hashlib.sha256(state['sealed']).hexdigest()
    assert state['writes'] == 1
    assert publisher._publish(SHA, allow_publication=False) == digest
    assert state['writes'] == 1


@pytest.mark.parametrize('ancestor,index',
    [(ancestor, index) for ancestor in (0, 1) for index in range(5)] + [(0, 5)])
def test_publication_still_rejects_directory_custody_drift(publication_custody, ancestor, index):
    state = publication_custody
    state['mutate'] = lambda: state['change_ancestor'](ancestor, index)
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher._publish(SHA, allow_publication=True)
    assert state['writes'] == 1


@pytest.mark.parametrize('old,delta', [(None, -1), (None, 2), (b'stale', 1)])
def test_only_one_new_entry_for_first_publication_is_permitted(publication_custody, old, delta):
    state = publication_custody; state['sealed'] = old
    state['mutate'] = lambda: state['change_ancestor'](1, 5, delta)
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher._publish(SHA, allow_publication=True)
    assert state['writes'] == 1


@pytest.mark.parametrize('index', range(9))
def test_full_directory_identity_join_is_retained_during_read(publication_custody, index):
    state = publication_custody
    state['during_read'] = lambda: state['change_ancestor'](1, index)
    with pytest.raises(c.ControlObservationError, match='publisher_ancestor_changed'):
        publisher._publish(SHA, allow_publication=True)
    assert state['writes'] == 0


@pytest.mark.parametrize('index', range(9))
def test_control_regular_file_identity_is_never_normalized(publication_custody, index):
    state = publication_custody
    def change_control():
        values = list(state['identity']); values[index] += 1
        state['identity'] = tuple(values)
    state['mutate'] = change_control
    with pytest.raises((owner.TransactionEffectUnknown, c.ControlObservationError)):
        publisher._publish(SHA, allow_publication=True)
    assert state['writes'] == 1


def test_no_write_reconciliation_rejects_ancestor_drift(publication_custody, monkeypatch):
    state = publication_custody
    state['sealed'] = c.encode_observation(state['raw'], state['identity'], SHA)
    def retained():
        state['change_ancestor'](1, 5)
        return state['sealed']
    monkeypatch.setattr(publisher, '_retained', retained)
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher._publish(SHA, allow_publication=False)
    assert state['writes'] == 0


def test_exact_receipt_is_still_required_after_directory_creation(publication_custody):
    state = publication_custody
    def lose_receipt():
        state['change_ancestor'](1, 5)
        state['sealed'] = None
    state['mutate'] = lose_receipt
    with pytest.raises(owner.TransactionEffectUnknown):
        publisher._publish(SHA, allow_publication=True)
    assert state['writes'] == 1

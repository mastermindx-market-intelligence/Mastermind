"""R8 input-boundary regressions using real Session Truth normalizers."""
import copy
import itertools
import pytest

from control_plane.project_recovery import assess_recovery
from control_plane.project_recovery_contract import ProjectRecoveryContractError, validate_inputs
from control_plane.session_truth_snapshots import (
    GITHUB_SCHEMA, EXECUTIVE_SCHEMA, normalize_github, normalize_executive,
)

STAMP = '2026-09-26T12:00:00Z'

def pr(**changes):
    row = dict(repository='o/r', number=1, state='open', draft=True,
               head_sha='1'*40, base_sha='2'*40, merge_sha=None, ci='pending',
               workstream='WS:ALPHA', linear=None, portfolio_mode=None, wave=None,
               authority=None, completion=None, proof_state=None,
               operation_key=None, pickup_head_sha=None)
    row.update(changes)
    return row

def operation(**changes):
    row = dict(operation_key='one-operation', payload_hash='sha256:'+'3'*64,
               status='RUNNING', effect_unknown=False, carrier=None)
    row.update(changes)
    return row

def documents():
    github = normalize_github(dict(schema=GITHUB_SCHEMA, available=True,
                                  observed_at=STAMP, pull_requests=[]))
    executive = normalize_executive(dict(schema=EXECUTIVE_SCHEMA, available=True,
        observed_at=STAMP, fresh=True, do_not_submit=False, grounding_sha='1'*40,
        operations=[]))
    st = dict(schema='mastermind.session_truth_receipt.v1',
        scope=dict(workstreams=['WS:ALPHA'], repositories=['o/r'], linear=[],
                   operation_key=None, requires_executive=True),
        skillpack={}, observation={}, findings=[], admission={},
        observations=dict(agentos=dict(available=True, source_sha='1'*40),
                          github=github, executive=executive),
        semantic_hash='sha256:'+'a'*64)
    ao = dict(schema='agent_os_state.v1',
        workstreams=[dict(key='ALPHA', status='active', program='alpha')],
        program_registry=dict(schema='agentos.program_registry.v1', available=True,
                              programs=[dict(key='alpha', lifecycle_state='building')]))
    return st, ao

def assess(st, ao):
    return assess_recovery(st, ao, as_of='2026-09-26', observed_at=STAMP)

def codes(result):
    return {row['code'] for row in result['findings']}

def assert_unknown(result):
    assert 'ACTIVE_WITHOUT_CARRIER' not in codes(result)
    assert 'RUNTIME_OWNERSHIP_UNKNOWN' in codes(result)

@pytest.mark.parametrize('source,collection', [('github','pull_requests'),('executive','operations')])
@pytest.mark.parametrize('bad', ['MISSING', None, {}, '', [None]])
def test_incomplete_collection_is_not_observed_zero(source, collection, bad):
    st, ao = documents()
    if bad == 'MISSING': st['observations'][source].pop(collection)
    else: st['observations'][source][collection] = bad
    with pytest.raises(ProjectRecoveryContractError): assess(st, ao)

@pytest.mark.parametrize('field', ['repository','number','state','workstream'])
@pytest.mark.parametrize('mode', ['missing','wrong_type'])
def test_pr_identity_or_state_cannot_be_silently_discarded(field, mode):
    st, ao = documents(); row = pr()
    if mode == 'missing': row.pop(field)
    else: row[field] = True
    st['observations']['github']['pull_requests'] = [row]
    with pytest.raises(ProjectRecoveryContractError): assess(st, ao)

@pytest.mark.parametrize('field', ['operation_key','status','effect_unknown'])
@pytest.mark.parametrize('mode', ['missing','wrong_type'])
def test_operation_identity_or_state_cannot_be_silently_discarded(field, mode):
    st, ao = documents(); row = operation()
    if mode == 'missing': row.pop(field)
    else: row[field] = 0
    st['observations']['executive']['operations'] = [row]
    with pytest.raises(ProjectRecoveryContractError): assess(st, ao)

@pytest.mark.parametrize('source,collection,row', [
    ('github','pull_requests',pr(state='unrecognized')),
    ('executive','operations',operation(status='unrecognized')),
])
def test_unknown_enum_is_not_terminal_absence(source, collection, row):
    st, ao = documents(); st['observations'][source][collection] = [row]
    with pytest.raises(ProjectRecoveryContractError): assess(st, ao)

@pytest.mark.parametrize('source,collection,row', [
    ('github','pull_requests',pr()),('executive','operations',operation()),
])
def test_duplicate_source_rows_refuse(source, collection, row):
    st, ao = documents(); st['observations'][source][collection] = [row, copy.deepcopy(row)]
    with pytest.raises(ProjectRecoveryContractError): assess(st, ao)

@pytest.mark.parametrize('reverse',[False,True])
def test_normalized_workstream_aliases_refuse_in_both_orders(reverse):
    st, ao = documents()
    rows = [dict(key='ALPHA',status='active',program='alpha'),
            dict(key='WS:ALPHA',status='done',program='alpha')]
    ao['workstreams'] = rows[::-1] if reverse else rows
    with pytest.raises(ProjectRecoveryContractError): assess(st, ao)

@pytest.mark.parametrize('state',['ADMITTED','UNKNOWN','QUEUED','RUNNING','BLOCKED'])
def test_owner_accepted_nonterminal_states_do_not_prove_no_work(state):
    st, ao = documents(); st['observations']['executive']['operations'] = [operation(status=state)]
    assert_unknown(assess(st, ao))

@pytest.mark.parametrize('state',['SUCCEEDED','FAILED','CANCELED','CANCELLED','REJECTED'])
def test_unknown_effect_stays_uncertain_even_with_terminal_status(state):
    st, ao = documents(); st['observations']['executive']['operations'] = [operation(status=state,effect_unknown=True)]
    assert_unknown(assess(st, ao))

@pytest.mark.parametrize('state',['SUCCEEDED','FAILED','CANCELED','CANCELLED','REJECTED'])
def test_explicit_terminal_operation_with_known_effect_preserves_negative_evidence(state):
    st, ao = documents(); st['observations']['executive']['operations'] = [operation(status=state)]
    assert codes(assess(st, ao)) == {'ACTIVE_WITHOUT_CARRIER'}

@pytest.mark.parametrize('source,schema',[('github',GITHUB_SCHEMA),('executive',EXECUTIVE_SCHEMA)])
def test_explicit_unavailable_owner_remains_unknown(source,schema):
    st, ao = documents(); st['observations'][source] = dict(available=False,reason='not observable')
    assert_unknown(assess(st, ao))

def test_valid_empty_owner_lists_still_have_same_meaning():
    st, ao = documents(); assert codes(assess(st, ao)) == {'ACTIVE_WITHOUT_CARRIER'}

def test_exact_open_pr_and_unbound_open_pr_remain_distinct():
    st, ao = documents(); st['observations']['github']['pull_requests'] = [pr()]
    assert codes(assess(st, ao)) == set()
    st['observations']['github']['pull_requests'][0]['workstream'] = None
    assert_unknown(assess(st, ao))

def test_valid_inputs_are_not_mutated_and_unique_row_permutations_are_stable():
    st, ao = documents()
    ao['workstreams'].append(dict(key='BETA',status='done',program='beta'))
    st['scope']['workstreams'].append('WS:BETA')
    ao['program_registry']['programs'].append(dict(key='beta',lifecycle_state='operating'))
    before = copy.deepcopy((st,ao)); first = assess(st, ao)
    assert (st,ao) == before
    ao['workstreams'].reverse(); ao['program_registry']['programs'].reverse()
    assert assess(st,ao)['semantic_hash'] == first['semantic_hash']

def test_unavailable_runtime_preserves_valid_wait_without_claiming_execution():
    st, ao = documents(); st['observations']['executive'] = dict(available=False,reason='not observable')
    ao['workstreams'][0]['wait'] = dict(kind='natural_evidence',review_after='2026-10-01',condition='Wait for the sample')
    result=assess(st,ao)
    assert result['summary']['VALID_INTENTIONAL_WAIT']==1
    assert 'ACTIVE_WITHOUT_CARRIER' not in codes(result)

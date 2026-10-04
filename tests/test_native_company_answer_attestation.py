"""Stable answer evidence survives delivery, but never answer or identity drift."""
import copy
import pytest
from control_plane.native_company_receipt import company_answer_attestation_sha256
from tests.test_native_company_receipt import make_data, make_envelope, make_item, make_params, result_for, call


def test_delivery_changes_historical_hash_but_preserves_exact_answer_attestation():
    data = make_data(wake_state='ACCEPTED', owed_turn='REQUESTER')
    before = call(make_params(item=make_item(result=result_for(make_envelope(data=data)))))
    data.update(wake_state='TARGET_ACKNOWLEDGED', owed_turn=None)
    after = call(make_params(item=make_item(result=result_for(make_envelope(data=data)))))
    assert before and after
    assert before['result_sha256'] != after['result_sha256']
    assert before['native_item_sha256'] != after['native_item_sha256']
    assert before['answer_attestation_sha256'] == after['answer_attestation_sha256']


@pytest.mark.parametrize('field,value', [
    ('actor_digest', '1'*64), ('counterpart_digest', '2'*64),
    ('peer_digest', '3'*64), ('question_digest', '4'*64),
    ('evidence_revision_digest', '5'*64),
    ('consultation_ref', 'consult-'+'a'*32), ('obligation_id', 'WAKE-'+'a'*32),
    ('deadline', '2026-10-04T05:00:00Z'),
    ('answer', {'text':'different answer', 'evidence_refs':['ev-1', 'ev-2']}),
    ('answer', {'text':'Here is the answer.', 'evidence_refs':['different-evidence']}),
    ('evidence_refs', [{'kind':'INTENT','event_ids':[1]},
                       {'kind':'ANSWER_AVAILABLE','event_ids':[3]}]),
])
def test_answer_identity_drift_never_inherits_read_credit(field, value):
    before = company_answer_attestation_sha256(make_data())
    after = company_answer_attestation_sha256(make_data(**{field:value}))
    assert before is not None and after is not None and before != after


@pytest.mark.parametrize('mutation', [
    {'role':'RECIPIENT'}, {'state':'CONSUMED'}, {'blocker':'CARRIER_INTEGRITY'},
    {'body_status':'UNAVAILABLE'}, {'schema':'foreign'}, {'actor_digest':'A'*64},
    {'evidence_refs':[]},
    {'evidence_refs':[{'kind':'INTENT','event_ids':[1]},
                      {'kind':'ANSWER_AVAILABLE','event_ids':[True]}]},
    {'evidence_refs':[{'kind':'INTENT','event_ids':[1]},
                      {'kind':'ANSWER_AVAILABLE','event_ids':[2,3]}]},
    {'evidence_refs':[{'kind':'INTENT','event_ids':[1]},
                      {'kind':'ANSWER_AVAILABLE','event_ids':[2]},
                      {'kind':'CONSUMED_BY_REQUESTER','event_ids':[3]}]},
    {'evidence_refs':[{'kind':'INTENT','event_ids':[1]},
                      {'kind':'ANSWER_AVAILABLE_HISTORICAL','event_ids':[2]}]},
])
def test_unavailable_historical_consumed_or_ambiguous_answer_has_no_attestation(mutation):
    assert company_answer_attestation_sha256(make_data(**mutation)) is None


def test_mutation_of_native_input_does_not_rewrite_returned_digest():
    data = make_data()
    saved = copy.deepcopy(data)
    digest = company_answer_attestation_sha256(data)
    data['answer']['text'] = 'changed later'
    assert digest == company_answer_attestation_sha256(saved)
    assert digest != company_answer_attestation_sha256(data)

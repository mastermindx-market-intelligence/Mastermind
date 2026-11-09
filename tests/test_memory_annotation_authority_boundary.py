"""One S10 declaration-collision discriminator; no annotation authority.

Uses the existing disposable OperatorOwner/SQLite fixture. Its kernel/source/
qualification facts are NOT authenticated reviewer facts. No dispatch/provider,
real grant, private study data or completed Memory attempt is exercised.
"""
import hashlib
import json
from tests import test_fabric_participant_owner as owner_fixture
from tests.test_fabric_participant_owner import (
    _native_owner_modules, case, participant, canonical, memory,
)


def test_two_declared_principals_can_share_one_execution_identity_without_becoming_independent(case):
    # Exactly the gap: these bytes can be structurally valid declarations while
    # both refs describe the SAME execution. The real owner keeps every flag
    # false; distinct strings are never an independent-rating witness.
    value = participant(case)
    execution = {'source_schema': 'mastermind.execution_principal_snapshot/v1',
        'attempt_id': 'same-attempt', 'worker_id': 'same-worker', 'quota_class': 'same-quota',
        'provider': 'glm', 'placement_snapshot_digest': 'a' * 64}
    plan = json.loads(value['reviewer_plan_bytes'])
    for reviewer in plan['reviewers']:
        ref = reviewer['principal_ref']
        body = json.loads(value['metadata_payloads'][ref['object_id']])
        body['execution_identity'] = execution
        raw = canonical(body)
        value['metadata_payloads'][ref['object_id']] = raw
        ref.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    plan_raw = canonical(plan)
    scope = value['binding']['scope']
    scope['reviewer_plan_ref'].update(sha256=hashlib.sha256(plan_raw).hexdigest(), bytes=len(plan_raw))
    value['reviewer_plan_bytes'] = plan_raw
    value['binding']['read_plan'] = memory.plan_review_metadata_reads(scope, plan_raw)
    reads = value['binding']['read_plan']['reads']
    observed = []
    for descriptor in reads:
        if descriptor['participant_role'] in ('reviewer_1', 'reviewer_2') and descriptor['evidence_role'] == 'principal_ref':
            # The actual owner is created by the imported scoped fixture, not at
            # collection. Keep its real import lifetime and restoration law.
            body = owner_fixture.port.validate_payload(descriptor,
                value['metadata_payloads'][descriptor['reference']['object_id']], reads)
            observed.append(body)
    assert len(observed) == 2
    assert observed[0]['participant_id'] != observed[1]['participant_id']
    assert observed[0]['execution_identity'] == observed[1]['execution_identity'] == execution
    assert all(not flag for body in observed for flag in body['verification'].values())

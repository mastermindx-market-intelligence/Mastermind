"""Independent canonical mapper -> real publication -> Workspace admission proof."""
import pytest
from control_plane import chairman_control_room as composer
from tests.test_workspace_programs_qualification import empty_inputs, publish
from tests.test_workspace_read_service import STAMP


def canonical(*, status='active', observed_at=STAMP, mixed=False):
    inputs = empty_inputs()
    inputs['agent_os_state']['generated_at'] = observed_at
    inputs['agent_os_state']['workstreams'] = [
        {'key': 'ONE', 'title': 'One', 'owner': 'ceo-sol', 'status': status}]
    inputs['runtime_jobs'] = [{'job_id': 'JOB-001', 'workstream_id': 'ONE', 'parent_job_id': None}]
    if mixed:
        # A distinct stale Agent OS dependency is not fabricated as fresh.
        inputs['inbox']['generated_at'] = '2020-01-01T00:00:00Z'
        inputs['inbox']['attention'] = [{'attention_id': 'old', 'target': 'chairman',
            'kind': 'decision', 'reason': 'An old attributed fact', 'workstream': 'WS:TWO'}]
        inputs['agent_os_state']['workstreams'].append(
            {'key': 'TWO', 'title': 'Two', 'owner': 'ceo-sol', 'status': 'active'})
        inputs['runtime_jobs'].append({'job_id': 'JOB-002', 'workstream_id': 'TWO', 'parent_job_id': None})
    return composer.compose_control_room(**inputs)


@pytest.mark.parametrize('status', ['active', 'done', 'proposed', 'blocked'])
def test_fresh_nonactionable_unknown_dispatch_cards_are_readable(status, tmp_path):
    doc = canonical(status=status)
    card = doc['autonomy']['responsibilities'][0]
    assert card['freshness'] == 'current'
    assert card['validity']['card']['valid_for_ms'] > 0
    assert card['is_actionable'] is False
    assert card['dispatch']['dispatch_state'] == 'UNKNOWN'
    assert card['validity']['owed_open_age']['valid_for_ms'] is None
    result = publish(tmp_path, doc)
    assert result['availability'] == 'AVAILABLE'
    assert result['control_room'] == doc


def test_mixed_current_and_canonical_unavailable_rows_are_unchanged(tmp_path):
    doc = canonical(mixed=True)
    rows = doc['autonomy']['responsibilities']
    assert {r['freshness'] for r in rows} == {'current', 'stale'}
    result = publish(tmp_path, doc)
    assert result['availability'] == 'AVAILABLE'
    assert result['control_room'] == doc


def test_unresolved_program_root_is_readable_without_inventing_identity(tmp_path):
    inputs = empty_inputs()
    inputs['agent_os_state']['workstreams'] = [
        {'key': 'ONE', 'title': 'One', 'owner': 'ceo-sol', 'status': 'active'}]
    inputs['runtime_jobs'] = None
    doc = composer.compose_control_room(**inputs)
    card = doc['autonomy']['responsibilities'][0]
    assert card['root_job_id'] is None
    assert card['validity']['card']['valid_for_ms'] > 0
    result = publish(tmp_path, doc)
    assert result['availability'] == 'AVAILABLE'
    assert result['control_room'] == doc


@pytest.mark.parametrize('mutation', ['invalid_freshness', 'contradictory_current', 'duplicate_work', 'foreign_generation'])
def test_current_facts_cannot_escape_with_malformed_or_foreign_qualification(tmp_path, mutation):
    doc = canonical()
    card = doc['autonomy']['responsibilities'][0]
    if mutation == 'invalid_freshness':
        card['freshness'] = 'not-a-canonical-state'
        card['validity']['card']['valid_for_ms'] = None
    elif mutation == 'contradictory_current':
        card['validity']['card']['valid_for_ms'] = None
    elif mutation == 'duplicate_work':
        doc['work'] *= 2
    elif mutation == 'foreign_generation':
        card['validity']['card']['qualified_at'] = '2026-09-20T00:00:00Z'
    assert publish(tmp_path, doc)['availability'] == 'UNAVAILABLE'

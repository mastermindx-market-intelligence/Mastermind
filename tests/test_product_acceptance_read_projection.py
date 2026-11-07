"""Actual final receipt owner + bounded Runtime; external sources are fixtures."""
import copy
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from common import product_acceptance_read_contract as contract
from control_plane import fabric_job_view
from control_plane.executive_runtime import Runtime, RuntimeReadBinding
from integrations.product_acceptance_read import read_acceptance
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_product_acceptance_ruling_owner import ready, qualify, complete_parent
from tests.test_product_acceptance_basis_continuity import restamp


@contextmanager
def case(tmp_path, monkeypatch, *, complete=True, consume=True):
    values = ready(tmp_path, monkeypatch)
    runtime, requester, _binding, target, basis, prepared, *_ = values
    qualified = qualify(values)
    if complete:
        complete_parent(runtime, requester, [qualified['evidence_digest']],
                        issuer_digests=None if consume else [])
    selected = {'work_ref': basis.entry['workstream'], 'root_job_id': requester._test_root.job_id,
                'request_message_key': prepared.message['message_key']}
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute('SELECT 1 FROM jobs').fetchone()
    binding = RuntimeReadBinding(ObservationNamespace(runtime.store.path))
    def run(callback):
        return Runtime.read_bound(tmp_path, binding=binding, reader=callback)
    try:
        yield runtime, requester, target, basis, selected, run
    finally:
        keeper.close()


def companion(runtime, root):
    return fabric_job_view.read_fabric_view_v3_from_runtime(runtime, root,
        armed={}, runtime_identity={'root': None, 'db_present': True, 'identity': None})


def test_actual_final_read_is_bound_to_selected_original_request_and_scope(tmp_path, monkeypatch):
    with case(tmp_path, monkeypatch) as (runtime, owner, target, basis, selected, run):
        before = runtime.events.list_events()
        def read(bound):
            first = companion(bound, selected['root_job_id'])
            view = read_acceptance(bound, owner.reader, selected)
            after = companion(bound, selected['root_job_id'])
            return fabric_job_view.compose_fabric_view_v4(before=first, after=after, acceptance=view)
        result = run(read)
        assert result['product_acceptance']['state'] == 'ACCEPTED'
        assert result['product_acceptance']['receipt']['subject_job_id'] == target.job_id
        assert result['fabric_view']['fabric_view']['root']['acceptance']['state'] == 'NOT_PROJECTED'
        assert runtime.events.list_events() == before
        for changed in ({'work_ref': 'WS:OTHER'}, {'root_job_id': 'JOB-999'}):
            wrong = run(lambda bound: read_acceptance(bound, owner.reader, {**selected, **changed}))
            assert wrong == contract.unavailable({**selected, **changed}, 'SELECTION_MISMATCH')


@pytest.mark.parametrize(('complete', 'consume', 'reason'), [
    (False, True, 'PARENT_RETURN_UNVERIFIED'),
    (True, False, 'PARENT_CONSUMPTION_UNPROVEN'),
])
def test_ruling_or_parent_summary_without_both_exact_returns_is_not_acceptance(
    tmp_path, monkeypatch, complete, consume, reason,
):
    with case(tmp_path, monkeypatch, complete=complete, consume=consume) as (_, owner, _, _, selected, run):
        assert run(lambda bound: read_acceptance(bound, owner.reader, selected)) == contract.unavailable(selected, reason)


def test_corrected_source_is_not_displayed_as_accepted(tmp_path, monkeypatch):
    with case(tmp_path, monkeypatch) as (_, owner, _, basis, selected, run):
        basis.entry['current_intent_revision'] = 'chairman-correction-v2'
        restamp(basis.entry)
        assert run(lambda bound: read_acceptance(bound, owner.reader, selected)) == contract.unavailable(selected, 'SOURCE_CHANGED')


@pytest.mark.parametrize('defect', ['snapshot', 'parent_digest', 'parent_attempt', 'subject_digest', 'unknown_generation'])
def test_receipt_cannot_outlive_or_replace_current_bounded_result_identity(tmp_path, monkeypatch, defect):
    with case(tmp_path, monkeypatch) as (_, owner, target, _, selected, run):
        def read(bound):
            first = companion(bound, selected['root_job_id'])
            view = read_acceptance(bound, owner.reader, selected)
            after = companion(bound, selected['root_job_id'])
            if defect == 'snapshot':
                after['result_refs']['snapshot_digest'] = 'f' * 64
            elif defect == 'unknown_generation':
                # Valid UNKNOWN, not a re-stamped SAME receipt.
                after['result_refs']['generation'].update(state='UNKNOWN', source_identity=None, before=None, after=None)
            else:
                receipt = view['receipt']
                if defect == 'parent_digest': receipt['parent_result_envelope_digest'] = 'f' * 64
                elif defect == 'subject_digest': receipt['subject_result_envelope_digest'] = 'f' * 64
                else: receipt['parent_attempt_id'] = 'ATT-' + 'f' * 32
            return fabric_job_view.compose_fabric_view_v4(before=first, after=after, acceptance=view)
        output = run(read)
        assert output['product_acceptance']['state'] == 'UNAVAILABLE'
        assert output['product_acceptance']['receipt'] is None


def test_unbound_runtime_cannot_claim_current_acceptance(tmp_path, monkeypatch):
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, _):
        assert read_acceptance(runtime, owner.reader, selected) == contract.unavailable(selected, 'ACCEPTANCE_NOT_COMPOSED')


@pytest.mark.parametrize('defect', ['reason_object', 'disposition_array', 'false_unchanged', 'false_changed'])
def test_closed_view_rejects_malformed_or_contradictory_source_evidence(defect):
    fixture = Path(__file__).parents[1] / 'app/mastermind_os/src/fixtures/mission-v4-owner-accepted.json'
    view = json.loads(fixture.read_text())['product_acceptance']
    source = view['receipt']['source_continuity']
    if defect == 'reason_object':
        view.update(state='UNAVAILABLE', receipt=None, reason_codes=[{}])
    elif defect == 'disposition_array':
        source['disposition'] = [source['disposition']]
    elif defect == 'false_unchanged':
        source.update(disposition='UNCHANGED_SOURCE', current_basis_digest='f' * 64)
    else:
        source.update(disposition='SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED',
                      current_basis_digest=source['issued_basis_digest'])
    with pytest.raises(ValueError, match='invalid_acceptance_projection'):
        contract.validate_view(view, selected=view['selection'])


def test_changed_source_observation_with_unchanged_declaration_remains_supported():
    fixture = Path(__file__).parents[1] / 'app/mastermind_os/src/fixtures/mission-v4-owner-accepted.json'
    view = json.loads(fixture.read_text())['product_acceptance']
    view['receipt']['source_continuity'].update(
        disposition='SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED', current_basis_digest='f' * 64)
    assert contract.validate_view(view, selected=view['selection']) == view

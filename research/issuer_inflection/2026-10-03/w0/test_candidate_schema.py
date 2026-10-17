#!/usr/bin/env python3
"""Shape/compatibility tests for the UNADMITTED W0 candidate.

All OwnerRefs in this module are deliberately non-resolving synthetic references.
They are not real data, accepted rights, financial owner receipts or I3 emissions.
Passing JSON shape is explicitly NOT semantic admission or an I3 validation gate.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / 'issuer_state_transition.candidate.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
TIME = '2026-10-03T00:00:00Z'

def owner_ref(label: str) -> dict:
    return {'owner_ref': 'TEST_ONLY_NON_RESOLVING', 'schema': 'test.shape_only.v1',
            'object_id': 'TEST_ONLY_' + label, 'revision_id': 'TEST_ONLY_r1',
            'content_sha256': hashlib.sha256(('TEST_ONLY_' + label).encode()).hexdigest(),
            'selector': None}

def clock() -> dict:
    return {'lower': None, 'upper': None, 'precision': 'unknown',
            'owner_clock_name': 'TEST_ONLY_unknown', 'policy_ref': owner_ref('clock')}

def sample() -> dict:
    return {
        'schema': 'issuer_state_transition.v1', 'transition_id': 'TEST_ONLY_NOT_AN_I3_TRANSITION',
        'issuer_ref': owner_ref('issuer'), 'definition_ref': owner_ref('definition'),
        'baseline': {'cutoff_ref': owner_ref('cutoff'), 'variables': [
            {'variable_ref': owner_ref('variable'), 'state': 'missing', 'value_ref': None,
             'reason': 'TEST_ONLY no owner value has been admitted'}]},
        'inputs': [{'role': 'context', 'ref': owner_ref('input'),
                    'source_refs': [owner_ref('source')], 'period_ref': owner_ref('period'),
                    'basis_ref': owner_ref('basis'), 'source_available': clock(), 'system_admitted': clock()}],
        'cutoffs': {'source_snapshot_at': TIME, 'recorded_at': TIME,
                    'selection_policy_ref': owner_ref('selection')},
        'clocks': {'earliest_public_support': clock(), 'earliest_system_support': clock(),
                   'reconstructed_at': TIME, 'emitted_at': None,
                   'reconstruction_mode': 'development_reconstruction'},
        'comparison': {'state': 'not_evaluable', 'before_ref': None, 'after_ref': None,
                       'admission_ref': None, 'unit_ref': None, 'before_value': None, 'after_value': None,
                       'absolute_change': None, 'relative_change_exact': None, 'relative_change_percent': None,
                       'percentage_reason': None, 'refusal_reason': 'TEST_ONLY no owner admission'},
        'meaning': {'economic_family': 'TEST_ONLY_unknown', 'measurement_shape': 'TEST_ONLY_unknown',
                    'interpretation_ref': None, 'evidence_maturity': 'development_golden',
                    'lifecycle': 'current', 'limitations': ['Synthetic shape fixture, never data or admission.']},
        'evidence': [{'role': 'missing', 'ref': None, 'dependence_group_ref': None,
                     'limitation': 'TEST_ONLY non-resolving references'}],
        'mechanism': [], 'materiality': [],
        'correction': {'relation': 'original', 'previous_derived_refs': [],
                       'source_correction_refs': [], 'reason': None},
        'rights': {'state': 'not_admitted', 'decision_refs': [], 'consumer_purpose_refs': []},
        'authority': {'class': 'context_only', **{k: False for k in (
            'may_rank', 'may_gate', 'may_size', 'may_originate', 'may_open_entry',
            'may_trade', 'may_modify_prophet')}},
        'reproducibility': {'source_refs': [owner_ref('source')],
            'method_sha256': '0' * 64, 'definition_sha256': '1' * 64,
            'semantic_projection_sha256': '2' * 64, 'canonicalization_ref': owner_ref('canonicalization'),
            'narrative_ref': None},
    }

def comparable_shape() -> dict:
    value = sample()
    value['comparison'].update(state='comparable', before_ref=owner_ref('before'),
        after_ref=owner_ref('after'), admission_ref=owner_ref('admission'), unit_ref=owner_ref('unit'),
        before_value='10', after_value='12.25', absolute_change='2.25',
        relative_change_exact={'numerator': '45', 'denominator': '2'},
        relative_change_percent='22.50', percentage_reason=None, refusal_reason=None)
    return value

class CandidateShapeTests(unittest.TestCase):
    def valid(self, value: dict) -> None:
        VALIDATOR.validate(value)
    def invalid(self, value: dict) -> None:
        with self.assertRaises(ValidationError): VALIDATOR.validate(value)
    def test_schema_is_valid_and_every_object_closed(self) -> None:
        Draft202012Validator.check_schema(SCHEMA)
        objects = []
        def visit(node: object) -> None:
            if isinstance(node, dict):
                if node.get('type') == 'object': objects.append(node)
                for item in node.values(): visit(item)
            elif isinstance(node, list):
                for item in node: visit(item)
        visit(SCHEMA)
        self.assertGreater(len(objects), 10)
        self.assertTrue(all(o.get('additionalProperties') is False for o in objects))
    def test_nonresolving_refusal_shape(self) -> None:
        self.valid(sample())
    def test_nonresolving_comparable_shape(self) -> None:
        self.valid(comparable_shape())
    def test_missing_baseline_cannot_be_erased(self) -> None:
        value = sample(); value['baseline']['variables'] = []; self.invalid(value)
    def test_available_baseline_needs_value_ref(self) -> None:
        value = sample(); value['baseline']['variables'][0].update(state='available', reason=None)
        self.invalid(value)
    def test_unchanged_baseline_retains_ref(self) -> None:
        value = sample(); value['baseline']['variables'][0].update(state='unchanged', reason=None, value_ref=owner_ref('before'))
        self.valid(value)
    def test_unknown_top_level_keys_refused(self) -> None:
        for key in ('issuer_score', 'financial_fact_store', 'trial_registry', 'portfolio_rank'):
            with self.subTest(key=key):
                value = sample(); value[key] = 1; self.invalid(value)
    def test_unknown_nested_keys_refused(self) -> None:
        for key in ('baseline', 'comparison', 'clocks', 'rights', 'authority'):
            with self.subTest(key=key):
                value = sample(); value[key]['hidden_override'] = True; self.invalid(value)
    def test_action_permissions_cannot_be_true(self) -> None:
        for key in sample()['authority']:
            if key == 'class': continue
            with self.subTest(key=key):
                value = sample(); value['authority'][key] = True; self.invalid(value)
    def test_unadmitted_and_revoked_cannot_emit(self) -> None:
        for state in ('not_admitted', 'revoked'):
            with self.subTest(state=state):
                value = sample(); value['rights']['state'] = state
                value['meaning']['evidence_maturity'] = 'source_observed'
                value['clocks'].update(emitted_at=TIME, reconstruction_mode='prospective_context')
                self.invalid(value)
    def test_golden_cannot_emit_even_with_rights_shaped_as_admitted(self) -> None:
        value = sample(); value['rights'].update(state='admitted', decision_refs=[owner_ref('rights')], consumer_purpose_refs=[owner_ref('purpose')])
        value['clocks']['emitted_at'] = TIME; self.invalid(value)
    def test_rights_shape_needs_decision_and_purpose(self) -> None:
        value = sample(); value['rights']['state'] = 'admitted'; self.invalid(value)
    def test_refusal_cannot_carry_numeric_delta(self) -> None:
        for key in ('absolute_change', 'relative_change_percent'):
            with self.subTest(key=key):
                value = sample(); value['comparison'][key] = '0'; self.invalid(value)
    def test_comparable_shape_needs_admission_ref(self) -> None:
        value = comparable_shape(); value['comparison']['admission_ref'] = None; self.invalid(value)
    def test_unchanged_shape_forbids_nonzero_absolute_change(self) -> None:
        value = comparable_shape(); value['comparison']['state'] = 'unchanged'; self.invalid(value)
    def test_absent_percentage_requires_reason(self) -> None:
        value = comparable_shape(); value['comparison']['relative_change_percent'] = None; self.invalid(value)
    def test_superseding_shape_needs_previous_ref_and_reason(self) -> None:
        value = sample(); value['correction']['relation'] = 'supersedes'; self.invalid(value)
    def test_unknown_time_has_no_invented_exact_bounds(self) -> None:
        value = sample(); value['clocks']['earliest_public_support']['lower'] = TIME; self.invalid(value)
    def test_knowledge_cutoff_requires_timezone(self) -> None:
        value = sample(); value['cutoffs']['recorded_at'] = '2026-10-03T00:00:00'; self.invalid(value)
    def test_owner_digest_shape(self) -> None:
        value = sample(); value['issuer_ref']['content_sha256'] = 'unverified'; self.invalid(value)
    def test_decimal_strings_not_float_nan_or_scientific(self) -> None:
        for invalid in (float('nan'), 'NaN', 'Infinity', '1e4', '01', 2.25):
            with self.subTest(value=invalid):
                value = comparable_shape(); value['comparison']['absolute_change'] = invalid; self.invalid(value)
    def test_display_requires_exact_rational_pair(self) -> None:
        value = comparable_shape(); value['comparison']['relative_change_exact'] = None; self.invalid(value)
    def test_refusal_cannot_carry_an_exact_rational(self) -> None:
        value = sample(); value['comparison']['relative_change_exact'] = {'numerator': '0', 'denominator': '1'}; self.invalid(value)
    def test_rational_denominator_is_positive(self) -> None:
        for denominator in ('0', '-2', '01'):
            with self.subTest(denominator=denominator):
                value = comparable_shape(); value['comparison']['relative_change_exact']['denominator'] = denominator; self.invalid(value)
    def test_percentage_display_has_exactly_two_decimal_places(self) -> None:
        for display in ('22.5', '22.500', '22', '2.25e1'):
            with self.subTest(display=display):
                value = comparable_shape(); value['comparison']['relative_change_percent'] = display; self.invalid(value)
    def test_negative_zero_display_is_noncanonical(self) -> None:
        value = comparable_shape(); value['comparison']['relative_change_percent'] = '-0.00'; self.invalid(value)
    def test_materiality_is_empty_only_until_owner_admission(self) -> None:
        for category in ('BUY', 'SELL', 'OPEN_ENTRY', 'RANK_1', 'high_materiality'):
            with self.subTest(category=category):
                value = sample()
                value['materiality'] = [{
                    'definition_ref': owner_ref('materiality'),
                    'component': 'TEST_ONLY_component',
                    'measured_value': None,
                    'unit_ref': None,
                    'categorical_state': category,
                    'explanation': 'TEST_ONLY not admitted',
                }]
                self.invalid(value)

    def test_shape_does_not_resolve_an_owner(self) -> None:
        # Deliberate proof of a required later semantic gate, not trusted data.
        value = comparable_shape(); self.valid(value)
        self.assertEqual(value['issuer_ref']['owner_ref'], 'TEST_ONLY_NON_RESOLVING')
    def test_shape_does_not_validate_arithmetic(self) -> None:
        # A composer must reject this; JSON shape intentionally cannot certify it.
        value = comparable_shape(); value['comparison']['absolute_change'] = '999'
        self.valid(value)
    def test_shape_does_not_verify_rights_or_clock_ordering(self) -> None:
        # A caller-controlled admitted label is never sufficient for publication.
        value = sample(); value['rights'].update(state='admitted', decision_refs=[owner_ref('rights')], consumer_purpose_refs=[owner_ref('purpose')])
        value['meaning']['evidence_maturity'] = 'source_observed'
        value['clocks'].update(emitted_at='2020-01-01T00:00:00Z', reconstruction_mode='prospective_context')
        self.valid(value)

if __name__ == '__main__': unittest.main()

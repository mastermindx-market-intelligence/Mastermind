"""Pure descriptive arithmetic only: synthetic curves, no producers or decision gates."""
from copy import deepcopy
from datetime import date
import math
import unittest
from brain import benchmark_comparison as C
D1, D2, D3, D4 = (f'2026-10-{n:02d}' for n in range(1, 5))

def compare(curves, cohort=('book', 'spy'), **kwargs):
    return C.compare_curves(curves, cohort=cohort, asof=kwargs.pop('asof', D4), **kwargs)

def envelope(spy, defense, **kwargs):
    return C.aligned_regime_envelope(spy, defense, start=kwargs.pop('start', D1), end=kwargs.pop('end', D3), asof=kwargs.pop('asof', D4), regime=kwargs.pop('regime', {'state': 'risk_off'}), **kwargs)

def _close(actual, expected):
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all((_close(actual[k], v) for k, v in expected.items()))
    if isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all((_close(a, b) for a, b in zip(actual, expected)))
    return math.isclose(actual, expected, rel_tol=1e-09, abs_tol=1e-09)

class TestBenchmarkComparison(unittest.TestCase):

    def test_malformed_selected_curve_is_not_hidden_by_missing_peer(self):
        for malformed in ([], 123, "curve"):
            for peer in ({}, {"spy": None}, {"spy": {D1: 1, D2: 1.1}}):
                with self.subTest(malformed=malformed, peer=peer):
                    with self.assertRaises(ValueError):
                        compare({"book": malformed, **peer})

    def test_unselected_malformed_curve_does_not_affect_explicit_cohort(self):
        result = compare({"book": {D1: 1, D2: 1.2}, "spy": {D1: 1, D2: 1.1},
                          "unrelated": []})
        assert result["status"] == "descriptive"

    def test_unequal_starts_use_one_explicit_cohort_window_and_delta(self):
        curves = {'spy': {D1: 100, D2: 200, D3: 220}, 'defense': {D2: 100, D3: 110}, 'book': {D2: 1, D3: 1.15}, 'unrelated': {D3: 10}}
        result = compare(curves, ('book', 'spy', 'defense'), delta_pairs=(('book', 'spy'), ('book', 'defense')))
        assert result['status'] == 'descriptive'
        assert (result['start'], result['end']) == (D2, D3)
        assert result['cohort'] == ('book', 'spy', 'defense')
        assert _close(result['returns_pct'], {'book': 15, 'spy': 10, 'defense': 10})
        assert _close([r['delta_pp'] for r in result['deltas_pp']], [5, 5])

    def test_unequal_ends_and_asof_are_cutoffs_not_observation_claims(self):
        curves = {'book': {D1: 1, D2: 1.06}, 'spy': {D1: 100, D2: 110, D3: 220}}
        result = compare(curves)
        assert (result['start'], result['end'], result['asof']) == (D1, D2, D4)
        assert _close(result['returns_pct'], {'book': 6, 'spy': 10})

    def test_disjoint_one_point_and_empty_are_unavailable(self):
        for spy, reason, count in [({D3: 2, D4: 3}, 'insufficient_common_dates', 0), ({D2: 2, D3: 3}, 'insufficient_common_dates', 1), ({}, 'insufficient_common_dates', 0)]:
            with self.subTest(spy=spy, reason=reason, count=count):
                result = compare({'book': {D1: 1, D2: 2}, 'spy': spy})
                assert result['status'] == 'unavailable'
                assert result['reason'] == reason
                assert result['common_point_count'] == count
                assert result['returns_pct'] is None and result['deltas_pp'] is None

    def test_missing_curve_is_unavailable_without_affecting_unrelated_pair(self):
        curves = {'book': {D1: 1, D2: 2}, 'spy': {D1: 1, D2: 1.1}}
        assert compare(curves, ('book', 'carry:autonomous'))['reason'] == 'missing_curve'
        assert compare(curves)['status'] == 'descriptive'

    def test_future_and_invalid_observations_never_enter_common_dates(self):
        invalid = {'2026-02-30': 10, '20261003': 10, '2026-10-3': 10, date(2026, 10, 3): 10, '2026-10-03T00:00:00': 10, '2026-09-30': True, '2026-09-29': float('nan'), '2026-09-28': float('inf'), '2026-09-27': -1, '2026-09-26': 0, '2026-09-25': '12', '2026-09-24': complex(1, 1), '2026-09-23': None}
        curves = {'book': {**invalid, D1: 1, D2: 2, D3: 4}, 'spy': {**invalid, D1: 1, D2: 1.1, D3: 8}}
        result = compare(curves, asof=D2)
        assert result['common_dates'] == (D1, D2)
        assert result['common_point_count'] == 2
        assert _close(result['returns_pct'], {'book': 100, 'spy': 10})

    def test_internal_missing_date_is_not_filled_or_counted(self):
        result = compare({'book': {D1: 1, D3: 1.15}, 'spy': {D1: 1, D2: 9, D3: 1.1}})
        assert result['common_dates'] == (D1, D3)
        assert result['common_point_count'] == 2
        assert not {'fresh', 'complete', 'eligible', 'effective_n', 'rank'} & result.keys()

    def test_existing_wealth_curve_rebase_does_not_reset_equal_weights(self):
        result = compare({'book': {D2: 1, D3: 1.2}, 'defense': {D1: 1, D2: 1.5, D3: 2.5}}, ('book', 'defense'))
        assert _close(result['returns_pct']['defense'], 66.66666666666667)
        assert not _close(result['returns_pct']['defense'], 50)

    def test_explicit_named_identity_is_preserved_without_aliasing(self):
        for identity in ['carry:autonomous:inception-holdings', 'china:000300.SS:CNY:native', 'hk:^HSI:HKD:native']:
            with self.subTest(identity=identity):
                result = compare({'book': {D2: 1, D3: 1.15}, identity: {D1: 1, D2: 1.5, D3: 1.65}}, ('book', identity))
                assert result['cohort'] == ('book', identity)
                assert tuple(result['returns_pct']) == ('book', identity)
                assert _close(result['returns_pct'][identity], 10)

    def test_inputs_are_unchanged_and_result_does_not_alias_inputs(self):
        curves = {'book': {D1: 1, D2: 1.2}, 'spy': {D1: 1, D2: 1.1}}
        before = deepcopy(curves)
        result = compare(curves, delta_pairs=(('book', 'spy'),))
        result['returns_pct']['book'] = -999
        assert curves == before
        first, second = (curves['book'], curves['spy'])
        env = envelope(first, second, end=D2)
        env['curve'][D2] = -999
        assert curves == before

    def test_invalid_cohort_is_configuration_error(self):
        for cohort in [(), ('book',), ('book', 'book'), 'book', {'book', 'spy'}, ('book', ''), ('book', 1)]:
            with self.subTest(cohort=cohort):
                with self.assertRaises(ValueError):
                    compare({}, cohort)

    def test_invalid_delta_pairs_are_configuration_errors(self):
        for pairs in [(('book', 'missing'),), (('book', 'book'),), (('book', 'spy'), ('book', 'spy')), 'book', ('book',), (('book',),)]:
            with self.subTest(pairs=pairs):
                with self.assertRaises(ValueError):
                    compare({}, delta_pairs=pairs)

    def test_invalid_asof_is_configuration_error(self):
        for asof in ['2026-02-30', '20261003', None, True, date(2026, 10, 3)]:
            with self.subTest(asof=asof):
                with self.assertRaises(ValueError):
                    compare({}, asof=asof)

    def test_nonfinite_or_underflowed_computed_returns_are_unavailable(self):
        for start_value, end_value in [(1e-308, 1e+308), (1, 1e+308), (1e+308, 1e-308)]:
            with self.subTest(start_value=start_value, end_value=end_value):
                result = compare({'book': {D1: start_value, D2: end_value}, 'spy': {D1: 1, D2: 1.1}})
                assert result['status'] == 'unavailable'
                assert result['reason'] == 'numeric_range'
                assert result['returns_pct'] is None and result['deltas_pp'] is None

    def test_huge_integer_observation_is_excluded_without_exception(self):
        result = compare({'book': {D1: 10 ** 1000, D2: 1, D3: 2}, 'spy': {D1: 1, D2: 1, D3: 1.1}})
        assert result['common_dates'] == (D2, D3)

    def test_pairwise_windows_remain_distinct_and_cannot_be_implicitly_ranked(self):
        curves = {'book': {D1: 1, D2: 2, D3: 2.2}, 'spy': {D1: 1, D2: 1.1}, 'defense': {D2: 1, D3: 1.5}}
        first = compare(curves)
        second = compare(curves, ('book', 'defense'))
        whole = compare(curves, ('book', 'spy', 'defense'))
        assert (first['start'], first['end']) != (second['start'], second['end'])
        assert whole['status'] == 'unavailable'
        assert 'rank' not in first and 'max' not in first

    def test_regime_winner_switch_aligns_components_before_taking_max(self):
        spy = {D1: 1, D2: 2, D3: 2.2}
        defense = {D2: 1, D3: 1.5}
        result = envelope(spy, defense, start=D2)
        assert result['status'] == 'descriptive'
        assert _close(result['curve'], {D2: 1, D3: 1.5})
        assert _close(result['return_pct'], 50)
        assert not _close(result['return_pct'], (max(2.2, 1.5) / max(2, 1) - 1) * 100)

    def test_risk_on_and_missing_regime_are_plain_spy(self):
        for regime in [None, {}, {'state': 'risk_on'}, {'risk_state': 'RISK_ON'}]:
            with self.subTest(regime=regime):
                result = envelope({D1: 1, D3: 1.1}, {D1: 1, D3: 9}, regime=regime)
                assert _close(result['curve'], {D1: 1, D3: 1.1})
                assert set(result['coverage'].values()) == {'spy_only_regime'}

    def test_weakening_preserves_existing_regime_switch(self):
        result = envelope({D1: 1, D3: 1.1}, {D1: 1, D3: 1.5}, regime={'state': 'risk_on', 'transition_state': 'WEAKENING'})
        assert _close(result['return_pct'], 50)

    def test_missing_defensive_base_keeps_entire_envelope_explicitly_spy_only(self):
        result = envelope({D1: 1, D2: 1.1, D3: 1.2}, {D2: 1, D3: 9})
        assert _close(result['curve'], {D1: 1, D2: 1.1, D3: 1.2})
        assert set(result['coverage'].values()) == {'spy_only_missing_defensive_base'}
        assert result['defensive_return_pct'] is None

    def test_missing_interior_or_endpoint_defense_has_per_date_fallback(self):
        result = envelope({D1: 1, D2: 1.1, D3: 1.2}, {D1: 4, D2: 8})
        assert _close(result['curve'], {D1: 1, D2: 2, D3: 1.2})
        assert result['coverage'][D2] == 'spy_and_defensive'
        assert result['coverage'][D3] == 'spy_only_missing_defensive_point'
        assert result['defensive_return_pct'] is None
        interior = envelope({D1: 1, D2: 1.1, D3: 1.2}, {D1: 4, D3: 8})
        assert interior['coverage'][D2] == 'spy_only_missing_defensive_point'
        assert _close(interior['defensive_return_pct'], 100)

    def test_missing_spy_endpoint_blocks_envelope(self):
        for spy in [{D2: 1, D3: 1.2}, {D1: 1, D2: 1.2}, {D1: 1, D3: True}, {}]:
            with self.subTest(spy=spy):
                result = envelope(spy, {D1: 1, D3: 1.5})
                assert result['status'] == 'unavailable'
                assert result['curve'] is None and result['return_pct'] is None

    def test_envelope_never_adds_defensive_only_or_future_dates(self):
        result = envelope({D1: 1, D3: 1.2, D4: 100}, {D1: 1, D2: 2, D3: 3, D4: 400}, asof=D3)
        assert tuple(result['curve']) == (D1, D3)

    def test_invalid_envelope_window_is_configuration_error(self):
        for kwargs in [{'start': D3, 'end': D1}, {'start': D1, 'end': D1}, {'end': D4, 'asof': D3}, {'start': 'd1'}]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    envelope({D1: 1, D3: 1.2}, {}, **kwargs)

    def test_envelope_numeric_overflow_is_unavailable_without_fallback_masking(self):
        for spy, defense in [({D1: 1e-308, D3: 1e+308}, {}), ({D1: 1, D3: 1.1}, {D1: 1e-308, D3: 1e+308}), ({D1: 1, D3: 1e+308}, {})]:
            with self.subTest(spy=spy, defense=defense):
                result = envelope(spy, defense)
                assert result['status'] == 'unavailable'
                assert result['reason'] == 'numeric_range'
                assert result['curve'] is None

    def test_repeated_requests_do_not_invent_observation_count(self):
        curves = {'book': {D1: 1, D3: 1.15}, 'spy': {D1: 1, D3: 1.1}}
        results = [compare(curves) for _ in range(8)]
        assert all((r['common_point_count'] == 2 and r == results[0] for r in results))
if __name__ == '__main__':
    unittest.main()

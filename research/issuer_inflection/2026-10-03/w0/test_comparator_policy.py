#!/usr/bin/env python3
"""Executable W0 numeric-policy witness. NOT an I3 composer or runtime library.

The witness accepts test numbers only. It resolves no issuer/owner/metric/source,
unit, basis, period, rights or admission. No caller may treat its math result as an
accepted transition. Production I3 code must not import this research test module.
"""
from __future__ import annotations
from decimal import Decimal, localcontext, ROUND_HALF_EVEN, ROUND_UP
from fractions import Fraction
from math import gcd
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / 'COMPARATOR_DEFINITION_CANDIDATE.json').read_text())
SCHEMA = json.loads((ROOT / 'issuer_state_transition.candidate.schema.json').read_text())
NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', re.ASCII)
BEFORE = '391035000000'
AFTER = '416161000000'
REQUIRED_POLICY = {
    'representation': 'reduced_exact_rational',
    'max_input_characters': 96,
    'max_input_coefficient_digits': 64,
    'max_input_fractional_digits': 24,
    'max_rational_integer_digits': 128,
    'max_derived_decimal_characters': 96,
    'display_scale': 2,
    'display_rounding': 'single_integer_divmod_half_even',
    'caller_decimal_context': 'not_used',
    'input_exponent_notation': 'refused',
    'nonpositive_baseline_percentage': 'null_with_reason',
    'negative_zero_output': 'canonical_positive_zero',
}

class PolicyInputError(ValueError):
    pass

def _scaled(value: str) -> tuple[int, int]:
    if not isinstance(value, str): raise PolicyInputError('input_type')
    if len(value) > 96: raise PolicyInputError('input_character_bound')
    if NUMBER.fullmatch(value) is None: raise PolicyInputError('input_format')
    unsigned = value[1:] if value.startswith('-') else value
    whole, dot, fraction = unsigned.partition('.')
    if len(whole) + len(fraction) > 64: raise PolicyInputError('input_coefficient_bound')
    if len(fraction) > 24: raise PolicyInputError('input_fractional_bound')
    coefficient = int(whole + fraction)
    return (-coefficient if value.startswith('-') else coefficient), len(fraction)

def _fixed(coefficient: int, scale: int) -> str:
    if coefficient == 0: return '0'
    sign = '-' if coefficient < 0 else ''
    digits = str(abs(coefficient))
    if scale:
        digits = digits.rjust(scale + 1, '0')
        fraction = digits[-scale:].rstrip('0')
        result = sign + digits[:-scale] + ('.' + fraction if fraction else '')
    else:
        result = sign + digits
    if len(result) > 96: raise PolicyInputError('derived_decimal_bound')
    return result

def _display_two(numerator: int, denominator: int) -> str:
    quotient, remainder = divmod(abs(numerator) * 100, denominator)
    if remainder * 2 > denominator or (remainder * 2 == denominator and quotient % 2):
        quotient += 1
    digits = str(quotient).rjust(3, '0')
    result = ('-' if numerator < 0 and quotient else '') + digits[:-2] + '.' + digits[-2:]
    if len(result) > 96: raise PolicyInputError('derived_decimal_bound')
    return result

def _reference_math(before: str, after: str) -> dict:
    """Test-only arithmetic: no owner semantics, authority, side effects or Decimal."""
    b, bs = _scaled(before); a, ass = _scaled(after)
    scale = max(bs, ass)
    b *= 10 ** (scale - bs); a *= 10 ** (scale - ass)
    difference = a - b
    result = {'absolute_change': _fixed(difference, scale), 'relative_change_exact': None,
              'relative_change_percent': None, 'percentage_reason': None}
    if b <= 0:
        result['percentage_reason'] = 'nonpositive_baseline'
        return result
    numerator, denominator = difference * 100, b
    divisor = gcd(abs(numerator), denominator)
    numerator //= divisor; denominator //= divisor
    if max(len(str(abs(numerator))), len(str(denominator))) > 128:
        raise PolicyInputError('rational_integer_bound')
    result.update(relative_change_exact={'numerator': str(numerator), 'denominator': str(denominator)},
                  relative_change_percent=_display_two(numerator, denominator))
    return result

class ComparatorPolicyTests(unittest.TestCase):
    def test_candidate_freezes_context_independent_exact_policy(self) -> None:
        self.assertEqual(POLICY.get('arithmetic_policy'), REQUIRED_POLICY)
        self.assertEqual(POLICY.get('version'), '1.0.2-candidate')
        self.assertIs(POLICY['admitted'], False)
    def test_candidate_identity_does_not_self_authorize_annual_semantics(self) -> None:
        self.assertEqual(POLICY.get('id'), 'I3-EQUAL-DURATION-REVENUE-SAME-FILING-1')
        self.assertNotIn('ANNUAL', POLICY.get('id', ''))
        self.assertEqual(POLICY.get('owner_period_kind_required'), 'duration')
        self.assertIs(POLICY.get('owner_typed_annual'), False)
        self.assertEqual(POLICY.get('annual_or_yoy_semantics'), 'not_admitted')
        self.assertNotIn('annual columns', POLICY.get('period_admission', '').lower())

    def test_candidate_has_explicit_exact_and_display_representations(self) -> None:
        comparison = SCHEMA['properties']['comparison']
        self.assertIn('relative_change_exact', comparison['required'])
        self.assertIn('ExactRational', SCHEMA['$defs'])
    def test_old_unspecified_decimal_policy_reproduces_R1(self) -> None:
        displays = []
        for precision in (4, 28, 100):
            with localcontext() as context:
                context.prec = precision; context.rounding = ROUND_HALF_EVEN
                result = Decimal(100) * (Decimal(AFTER) / Decimal(BEFORE) - 1)
                displays.append(str(result.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)))
        self.assertEqual(displays, ['6.40', '6.43', '6.43'])
    def test_AAPL_policy_witness_is_exact_not_an_I3_emission(self) -> None:
        self.assertEqual(_reference_math(BEFORE, AFTER), {
            'absolute_change': '25126000000',
            'relative_change_exact': {'numerator': '502520', 'denominator': '78207'},
            'relative_change_percent': '6.43', 'percentage_reason': None})
    def test_hostile_decimal_context_does_not_change_any_output(self) -> None:
        expected = _reference_math(BEFORE, AFTER)
        for precision in (1, 4, 28, 100):
            with self.subTest(precision=precision), localcontext() as context:
                context.prec = precision; context.rounding = ROUND_UP
                context.Emax = 1; context.Emin = -1
                for trap in context.traps: context.traps[trap] = True
                self.assertEqual(_reference_math(BEFORE, AFTER), expected)
    def test_positive_half_even_ties(self) -> None:
        self.assertEqual(_reference_math('20000', '20001')['relative_change_percent'], '0.00')
        self.assertEqual(_reference_math('20000', '20003')['relative_change_percent'], '0.02')
    def test_negative_half_even_ties_and_no_negative_zero(self) -> None:
        self.assertEqual(_reference_math('20000', '19999')['relative_change_percent'], '0.00')
        self.assertEqual(_reference_math('20000', '19997')['relative_change_percent'], '-0.02')
    def test_either_side_of_rounding_boundary(self) -> None:
        self.assertEqual(_reference_math('200000', '200029')['relative_change_percent'], '0.01')
        self.assertEqual(_reference_math('200000', '200031')['relative_change_percent'], '0.02')
    def test_zero_change_canonical_fraction(self) -> None:
        got = _reference_math('1.00', '1')
        self.assertEqual(got['absolute_change'], '0')
        self.assertEqual(got['relative_change_exact'], {'numerator': '0', 'denominator': '1'})
        self.assertEqual(got['relative_change_percent'], '0.00')
    def test_finite_absolute_change_keeps_exact_fractional_information(self) -> None:
        self.assertEqual(_reference_math('10', '12.2500')['absolute_change'], '2.25')
        self.assertEqual(_reference_math('0.001', '0.00101')['absolute_change'], '0.00001')
    def test_no_percentage_for_zero_or_negative_baseline(self) -> None:
        for before in ('0', '-0.00', '-10'):
            with self.subTest(before=before):
                got = _reference_math(before, '5')
                self.assertIsNone(got['relative_change_exact'])
                self.assertIsNone(got['relative_change_percent'])
                self.assertEqual(got['percentage_reason'], 'nonpositive_baseline')
    def test_no_float_nonfinite_exponent_or_noncanonical_input(self) -> None:
        for bad in (1.0, True, None, 'NaN', 'Infinity', '1e9', '+1', '01', ' 1', '1 ', '.5', '1.', '１'):
            with self.subTest(value=bad), self.assertRaises(PolicyInputError): _reference_math(bad, '1')
    def test_input_size_bound(self) -> None:
        with self.assertRaisesRegex(PolicyInputError, 'character'): _reference_math('1' * 97, '1')
        with self.assertRaisesRegex(PolicyInputError, 'coefficient'): _reference_math('1' * 65, '1')
        with self.assertRaisesRegex(PolicyInputError, 'fractional'): _reference_math('0.' + '1' * 25, '1')
    def test_boundary_sized_inputs_remain_bounded_and_exact(self) -> None:
        got = _reference_math('0.' + '0' * 23 + '1', '9' * 64)
        exact = got['relative_change_exact']
        self.assertLessEqual(len(exact['numerator'].lstrip('-')), 128)
        self.assertLessEqual(len(exact['denominator']), 128)
        self.assertLessEqual(len(got['relative_change_percent']), 96)
    def test_fraction_reference_and_rounding_error_bound(self) -> None:
        pairs = [('3', '4'), ('3', '2'), ('0.25', '0.2501'), ('10.125', '12.75'), ('1000000', '-5'), (BEFORE, AFTER)]
        for before, after in pairs:
            with self.subTest(before=before, after=after):
                got = _reference_math(before, after); exact = got['relative_change_exact']
                value = Fraction(int(exact['numerator']), int(exact['denominator']))
                self.assertEqual(value, 100 * (Fraction(after) - Fraction(before)) / Fraction(before))
                self.assertEqual(gcd(abs(int(exact['numerator'])), int(exact['denominator'])), 1)
                self.assertGreater(int(exact['denominator']), 0)
                self.assertLessEqual(abs(Fraction(got['relative_change_percent']) - value), Fraction(1, 200))
    def test_no_broad_near_zero_or_materiality_policy_is_inferred(self) -> None:
        # A bounded arithmetic result is not permission to compare this input economically.
        got = _reference_math('0.' + '0' * 23 + '1', '1')
        self.assertNotIn('issuer_ref', got)
        self.assertNotIn('transition_id', got)
        self.assertNotIn('materiality', got)
        self.assertNotIn('authority', got)
        self.assertNotIn('emitted_at', got)

if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""Research-only counterexamples for Commission 7; no Mastermind imports or I/O.

Run: python verify_mathematics.py --output verification_results.json
These checks do not implement or qualify an evidence consumer, market model,
conditional-independence test, historical backtest, or production policy.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction as F
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import unittest


def mean(values: list[F]) -> F:
    if not values:
        raise ValueError("A population is required")
    return sum(values, F(0)) / len(values)


def covariance(x: list[F], y: list[F]) -> F:
    if len(x) != len(y) or not x:
        raise ValueError("Matched nonempty populations are required")
    mx, my = mean(x), mean(y)
    return mean([(a - mx) * (b - my) for a, b in zip(x, y)])


def correlation(x: list[F], y: list[F]) -> float | None:
    vx, vy = covariance(x, x), covariance(y, y)
    if vx == 0 or vy == 0:
        return None  # Undefined is not zero correlation.
    return float(covariance(x, y)) / math.sqrt(float(vx * vy))


def independent_pair(rows: list[tuple[int, int]]) -> bool:
    """Exact enumeration only: each row has equal probability."""
    n = len(rows)
    left, right, joint = Counter(x for x, _ in rows), Counter(y for _, y in rows), Counter(rows)
    return all(F(joint[x, y], n) == F(nx, n) * F(ny, n)
               for x, nx in left.items() for y, ny in right.items())


def determinant3(a: F, b: F, c: F) -> F:
    """Determinant of [[1,a,b],[a,1,c],[b,c,1]]."""
    return 1 + 2 * a * b * c - a * a - b * b - c * c


class MathematicalChecks(unittest.TestCase):
    def test_01_zero_correlation_nonlinear_dependence(self):
        x = [F(-1), F(0), F(1)]
        y = [v * v for v in x]
        self.assertEqual(covariance(x, y), 0)
        self.assertEqual(correlation(x, y), 0.0)
        rows = list(zip(x, y))
        joint_zero = F(sum(a == 0 and b == 0 for a, b in rows), len(rows))
        marginal_x = F(sum(a == 0 for a in x), len(x))
        marginal_y = F(sum(b == 0 for b in y), len(y))
        self.assertNotEqual(joint_zero, marginal_x * marginal_y)

    def test_02_zero_correlation_does_not_zero_mutual_information(self):
        # Y=X^2: H(Y|X)=0, H(Y)>0.
        hy = -(1 / 3) * math.log2(1 / 3) - (2 / 3) * math.log2(2 / 3)
        self.assertAlmostEqual(hy, 0.9182958340544896)
        self.assertGreater(hy, 0)

    def test_03_xor_all_pairs_independent(self):
        rows = [(a, b, a ^ b) for a in (0, 1) for b in (0, 1)]
        for i, j in ((0, 1), (0, 2), (1, 2)):
            self.assertTrue(independent_pair([(r[i], r[j]) for r in rows]))

    def test_04_xor_not_mutually_independent(self):
        self.assertNotEqual(F(1, 4), F(1, 2) ** 3)  # P(0,0,0) vs product.

    def test_05_xor_pairwise_target_screen_misses_synergy(self):
        rows = [(a, b, a ^ b) for a in (0, 1) for b in (0, 1)]
        self.assertTrue(independent_pair([(a, y) for a, b, y in rows]))
        self.assertTrue(independent_pair([(b, y) for a, b, y in rows]))
        self.assertTrue(all(y == (a ^ b) for a, b, y in rows))

    def test_06_exact_positive_clone(self):
        x = [F(-1), F(0), F(1)]
        self.assertEqual(correlation(x, [2 * a for a in x]), 1.0)

    def test_07_negative_clone_is_one_dimension(self):
        x = [F(-1), F(0), F(1)]
        self.assertEqual(correlation(x, [-a for a in x]), -1.0)
        self.assertEqual(F(2) ** 2 / (F(2) ** 2 + F(0) ** 2), 1)

    def test_08_high_correlation_can_retain_target_information(self):
        rows = [(F(x), F(z)) for x in (-1, 1) for z in (-1, 1)]
        x, z = [r[0] for r in rows], [r[1] for r in rows]
        f2 = [a + F(1, 100) * b for a, b in rows]
        self.assertGreater(correlation(x, f2), 0.9999)
        self.assertEqual([(b - a) * 100 for a, b in zip(x, f2)], z)
        self.assertEqual(covariance(x, z), 0)

    def test_09_equal_weight_variance_and_effective_count(self):
        n, rho = 5, F(4, 5)
        var_mean = (n + n * (n - 1) * rho) / (n * n)
        self.assertEqual(var_mean, F(21, 25))
        self.assertEqual(1 / var_mean, F(25, 21))

    def test_10_spectral_rank_is_not_same_effective_count(self):
        eigenvalues = [F(21, 5)] + [F(1, 5)] * 4
        rank = sum(eigenvalues) ** 2 / sum(e * e for e in eigenvalues)
        self.assertEqual(rank, F(125, 89))
        self.assertNotEqual(rank, F(25, 21))

    def test_11_pairwise_matrix_can_fail_psd(self):
        self.assertEqual(determinant3(F(9, 10), F(9, 10), F(-9, 10)), F(-361, 125))

    def test_12_zero_variance_correlation_is_undefined(self):
        self.assertIsNone(correlation([F(1)] * 3, [F(1), F(2), F(3)]))

    def test_13_independent_noise_need_not_add_prediction(self):
        rows = [(x, z) for x in (0, 1) for z in (0, 1)]
        self.assertTrue(independent_pair(rows))
        # Y=X already has zero squared prediction error from X alone.
        self.assertEqual(sum((x - x) ** 2 for x, z in rows), 0)
        self.assertEqual(sum(((x + 0 * z) - x) ** 2 for x, z in rows), 0)

    def test_14_duplicate_likelihood_multiplies_false_confidence(self):
        once = F(4, 1 + 4)
        tripled = F(4 ** 3, 1 + 4 ** 3)
        self.assertEqual(once, F(4, 5))
        self.assertEqual(tripled, F(64, 65))
        self.assertGreater(tripled, once)

    def test_15_invertible_transform_adds_no_new_observation(self):
        rows = [(F(x), F(y)) for x in (-1, 0, 1) for y in (-1, 0, 1)]
        for x, y in rows:
            u, v = x + y, x - y
            self.assertEqual(((u + v) / 2, (u - v) / 2), (x, y))

    def test_16_training_decorrelation_does_not_constrain_future_covariance(self):
        def transpose(m):
            return [list(row) for row in zip(*m)]
        def multiply(a, b):
            return [[sum(x * y for x, y in zip(row, col))
                     for col in zip(*b)] for row in a]
        q = [[F(3, 5), F(-4, 5)], [F(4, 5), F(3, 5)]]
        diagonal = [[F(1), F(0)], [F(0), F(4)]]
        train = multiply(multiply(q, diagonal), transpose(q))
        train_projected = multiply(multiply(transpose(q), train), q)
        future_projected = multiply(multiply(transpose(q), diagonal), q)
        self.assertEqual(train_projected, diagonal)
        self.assertEqual(future_projected[0][1], F(36, 25))
        self.assertNotEqual(future_projected[0][1], 0)

    def test_17_threshold_connectivity_is_not_pairwise_equivalence(self):
        ab, ac, bc, threshold = F(9, 10), F(13, 20), F(9, 10), F(4, 5)
        self.assertGreater(ab, threshold)
        self.assertGreater(bc, threshold)
        self.assertLess(ac, threshold)
        self.assertGreater(determinant3(ab, ac, bc), 0)

    def test_18_negative_correlation_can_reduce_risk_not_create_independent_origins(self):
        x = [F(-1), F(0), F(1)]
        avg = [(a - a) / 2 for a in x]
        self.assertEqual(covariance(avg, avg), 0)
        self.assertEqual(correlation(x, [-a for a in x]), -1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MathematicalChecks)
    names = [t.id().split('.')[-1] for t in suite]
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    source = Path(__file__).read_bytes()
    receipt = {
        'schema': 'commission7.mathematical_verification.v1',
        'scope': 'finite_synthetic_mathematical_counterexamples_only',
        'python_version': platform.python_version(),
        'source_sha256': hashlib.sha256(source).hexdigest(),
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'successful': result.wasSuccessful(),
        'test_ids': names,
        'illustrations': {
            'x_squared_covariance': 0,
            'x_squared_mutual_information_bits': 0.9182958340544896,
            'near_clone_correlation': 1 / math.sqrt(1.0001),
            'five_signal_rho_0_8_variance_effective_count': 25 / 21,
            'same_matrix_spectral_participation_ratio': 125 / 89,
            'three_clone_naive_posterior': 64 / 65,
            'single_observation_posterior': 0.8,
            'invalid_pairwise_matrix_determinant': -361 / 125,
        },
        'limits': [
            'No Mastermind or Macro production code imported or executed.',
            'No repository suite, source accessor, historical data, or market outcomes executed.',
            'No model fitting, independence certification, alpha claim, or production acceptance.',
            'This is author-run verification, not an independent reviewer sign-off.',
        ],
    }
    if args.output:
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(stream.getvalue(), end='')
    print(json.dumps({k: receipt[k] for k in ('tests_run', 'failures', 'errors', 'successful', 'source_sha256')}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Diagnostics only: tests do not start providers or change router policy."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('pool_stats_audit',
    Path(__file__).with_name('analyze_pool_stats.py'))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
HEADER = ('provider model task_class n n_outcome n_quality_verdict '
          'evaluated_first_pass_acceptance n_admission_refused')


def run(row):
    return AUDIT.analyze(HEADER + '\n' + row)['cohorts'][0]


class PoolStatsAuditTests(unittest.TestCase):
    def test_no_verdict_is_not_zero_quality(self):
        row = run('cursor composer-2.5 build 99 0 0 n/a 1')
        self.assertIsNone(row['evaluated_first_pass_acceptance'])
        self.assertIn('OUTCOME_COVERAGE_GAP', row['flags'])
        self.assertNotIn('INVESTIGATE_MATCHED_TASK_PERFORMANCE_NOT_AUTO_DEMOTION', row['flags'])

    def test_tiny_cursor_sample_is_not_general_quality_proof(self):
        row = run('cursor cursor-grok-4.6-high review 3 3 3 1.000 0')
        self.assertIn('INSUFFICIENT_EVALUATED_SAMPLE', row['flags'])
        self.assertEqual(row['evaluated_run_coverage'], 1)

    def test_glm_build_mixed_outcomes_are_not_all_evaluated_runs(self):
        row = run('glm glm-5.3-flash build 193 26 22 0.045 34')
        self.assertAlmostEqual(row['evaluated_run_coverage'], 22 / 193)
        self.assertAlmostEqual(row['outcome_coverage'], 26 / 193)
        self.assertIn('INVESTIGATE_MATCHED_TASK_PERFORMANCE_NOT_AUTO_DEMOTION', row['flags'])
        self.assertEqual(row['admission_refusals'], 34)

    def test_admission_is_separate_from_acceptance(self):
        row = run('grok grok-4.6 review 412 191 184 0.957 19')
        self.assertEqual(row['evaluated_first_pass_acceptance'], 0.957)
        self.assertIn('ADMISSION_FAILURES_SEPARATE_FROM_MODEL_QUALITY', row['flags'])

    def test_read_only_contract(self):
        result = AUDIT.analyze(HEADER + '\n')
        self.assertFalse(result['routing_changed'])
        self.assertFalse(result['model_ranking_established'])
        self.assertEqual(result['cohorts'], [])

    def test_missing_or_duplicate_columns_refused(self):
        for header in ('provider model task_class n', HEADER + ' n'):
            with self.subTest(header=header), self.assertRaises(ValueError):
                AUDIT.analyze(header)

    def test_multiple_export_tables_refused(self):
        with self.assertRaises(ValueError):
            AUDIT.analyze(HEADER + '\n' + HEADER)

    def test_malformed_or_inconsistent_rows_refused(self):
        rows = [
            'glm m build 10 5 6 0.5 1', 'glm m build 10 11 2 0.5 1',
            'glm m build 10 2 2 0.5 11', 'glm m build -1 0 0 n/a 0',
            'glm m build 1.0 0 0 n/a 0', 'glm m build 10 0 0 0.0 0',
            'glm m build 10 2 2 nan 0', 'glm m build 10 2 2 inf 0',
            'glm m build 10 2 2 1.1 0', 'glm m build 10 2 2 -0.1 0',
            'glm m build 10 2 2 0.5',
        ]
        for row in rows:
            with self.subTest(row=row), self.assertRaises(ValueError):
                run(row)

    def test_comments_and_additive_columns(self):
        text = '# costs are estimates\n' + HEADER + ' extra\n' + 'glm m review 20 20 20 0.9 0 v1\n'
        self.assertEqual(len(AUDIT.analyze(text)['cohorts']), 1)

    def test_report_size_and_count_bounds(self):
        with self.assertRaises(ValueError):
            AUDIT.analyze('x' * (AUDIT.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            AUDIT.analyze(HEADER, minimum_verdicts=True)
        with self.assertRaises(ValueError):
            run('glm m review 1000000001 0 0 n/a 0')


if __name__ == '__main__':
    unittest.main()

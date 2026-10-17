"""Regression tests for the existing perception metric, not a market backtest.

AUC counts a tied positive/negative pair as one half. The independent pairwise
oracle deliberately does not sort or rank, so it cannot share the ordinal-rank
bug. No detector parameter, historical verdict, or consumer authority is changed.
"""
from __future__ import annotations

from itertools import permutations, product

import numpy as np
import pytest

from scripts import validate_perception as VP


def _pairwise_auc(labels, scores):
    positive = [score for label, score in zip(labels, scores) if label == 1]
    negative = [score for label, score in zip(labels, scores) if label == 0]
    if not positive or not negative:
        return None
    twice_wins = sum(
        2 * int(pos > neg) + int(pos == neg)
        for pos in positive for neg in negative
    )
    return round(twice_wins / (2 * len(positive) * len(negative)), 4)


@pytest.mark.parametrize("labels,scores,expected", [
    ([0, 0, 1, 1], [0, 0, 0, 0], 0.5),
    ([1, 1, 0, 0], [0, 0, 0, 0], 0.5),
    ([0, 1, 0, 1], [0, 0, 1, 1], 0.5),
    ([0, 0, 1, 1], [0, 1, 2, 3], 1.0),
    ([0, 0, 1, 1], [3, 2, 1, 0], 0.0),
    ([0, 1], [-0.0, 0.0], 0.5),
    ([1, 0, 1, 0, 0], [0, 1, 2, 3, 4], 0.1667),
    ([False, True], [-4.0, 8.0], 1.0),
])
def test_auc_known_rank_and_tie_cases(labels, scores, expected):
    assert VP._auc(labels, scores) == expected
    assert VP._auc(labels, scores) == _pairwise_auc(labels, scores)


def test_auc_is_invariant_to_joint_row_permutation_with_mixed_ties():
    labels = np.array([0, 1, 0, 1, 0, 1])
    scores = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 2.0])
    expected = _pairwise_auc(labels, scores)
    for order in permutations(range(len(labels))):
        indices = list(order)
        assert VP._auc(labels[indices], scores[indices]) == expected


def test_auc_exhaustive_small_binary_populations_match_pairwise_oracle():
    comparisons = 0
    for size in range(2, 6):
        for labels in product((0, 1), repeat=size):
            if len(set(labels)) != 2:
                continue
            for scores in product((-1.0, 0.0, 1.0), repeat=size):
                assert VP._auc(labels, scores) == _pairwise_auc(labels, scores)
                comparisons += 1
    assert comparisons == 8604


def test_auc_large_zero_score_population_is_chance_not_row_order():
    labels = np.concatenate((np.zeros(10000), np.ones(10000)))
    scores = np.zeros(len(labels))
    assert VP._auc(labels, scores) == 0.5
    assert VP._auc(labels[::-1], scores) == 0.5


@pytest.mark.parametrize("labels,scores", [
    ([], []),
    ([1, 1], [0.1, 0.2]),
    ([0, 0], [0.1, 0.2]),
    ([0, 1], [0.1]),
    ([0, 1], [0.1, 0.2, 0.3]),
    (0, 0.5),
    ([[0], [1]], [0.1, 0.2]),
    ([0, 1], [[0.1], [0.2]]),
    ([0, 1], [np.nan, 0.2]),
    ([0, 1], [0.1, np.inf]),
    ([0, 1], [-np.inf, 0.2]),
    ([0, 1, np.nan], [0.1, 0.2, 0.3]),
    ([0, 1, np.inf], [0.1, 0.2, 0.3]),
    ([0, 1, 0.5], [0.1, 0.2, 0.3]),
    ([0, 1, 2], [0.1, 0.2, 0.3]),
    ([0, 1, -1], [0.1, 0.2, 0.3]),
    ([0, 1], ["not-a-score", 0.2]),
    ([0, "not-a-label"], [0.1, 0.2]),
    ([0, 1], np.array([1 + 2j, 2 + 1j])),
    (np.array([0 + 1j, 1 + 0j]), [0.1, 0.2]),
])
def test_auc_undefined_or_invalid_population_is_none(labels, scores):
    assert VP._auc(labels, scores) is None


def test_auc_does_not_modify_caller_arrays():
    labels = np.array([1, 0, 1, 0])
    scores = np.array([1.0, 0.0, 0.0, 1.0])
    original_labels, original_scores = labels.copy(), scores.copy()
    assert VP._auc(labels, scores) == 0.5
    np.testing.assert_array_equal(labels, original_labels)
    np.testing.assert_array_equal(scores, original_scores)

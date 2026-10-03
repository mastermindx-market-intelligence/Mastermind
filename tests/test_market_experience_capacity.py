"""Planning arithmetic and malformed-input checks; not market-performance proof."""
from dataclasses import replace
import ast
import json
from pathlib import Path

import pytest

from research.market_experience_capacity import (
    Workload, TokenPrice, estimate, report, token_cost,
)


def test_full_coverage_dimensions_and_cost():
    result = estimate(Workload(500, 30), TokenPrice(1.25, 2.5))
    assert result['stock_day_rows'] == 3_780_000
    assert result['quarterly_event_opportunities'] == 60_000
    assert result['assumed_unique_documents'] == 120_000
    assert result['numeric_dense_gb'] == pytest.approx(7.74144)
    assert result['input_tokens_one_pass'] == 1_440_000_000
    assert result['billed_output_tokens_one_pass'] == 120_000_000
    assert result['document_token_cost_one_pass_usd'] == pytest.approx(2100)
    assert result['document_token_cost_with_processing_allowance_usd'] == pytest.approx(6300)
    assert result['naive_daily_reanalysis_token_cost_with_same_allowance_usd'] == pytest.approx(198450)


def test_pilot_and_processing_factor():
    work = Workload(50, 5)
    result = estimate(work, TokenPrice(.15, .5))
    assert result['stock_day_rows'] == 63_000
    assert result['assumed_unique_documents'] == 2_000
    assert result['document_token_cost_with_processing_allowance_usd'] == pytest.approx(13.8)
    one = estimate(replace(work, processing_multiplier=1), TokenPrice(.15, .5))
    assert result['document_token_cost_with_processing_allowance_usd'] == pytest.approx(
        3 * one['document_token_cost_with_processing_allowance_usd'])


@pytest.mark.parametrize('bad', [-1, 0, True, 1.5, '50', None])
def test_invalid_counts_fail(bad):
    with pytest.raises(ValueError):
        Workload(bad, 5)


@pytest.mark.parametrize('bad', [0, .99, float('nan'), float('inf'), True, '3'])
def test_invalid_processing_multiplier_fails(bad):
    with pytest.raises(ValueError):
        Workload(50, 5, processing_multiplier=bad)


@pytest.mark.parametrize('bad', [-1, float('nan'), float('inf'), True, '1'])
def test_invalid_prices_fail(bad):
    with pytest.raises(ValueError):
        TokenPrice(bad, 1)


@pytest.mark.parametrize('bad', [-1, 1.5, True, None])
def test_invalid_token_counts_fail(bad):
    with pytest.raises(ValueError):
        token_cost(bad, 1, TokenPrice(1, 1))


def test_zero_prices_and_tokens_are_valid():
    assert token_cost(0, 0, TokenPrice(0, 0)) == 0


def test_serializable_disclaims_and_deterministic():
    first = report()
    assert first == report()
    assert json.loads(json.dumps(first, allow_nan=False)) == first
    assert first['status'] == 'PLANNING_ONLY_NO_SPEND_AUTHORITY'
    result = first['scenarios']['pilot_50_issuers_5_years']['grok_4_3']
    assert 'data licenses' in result['not_included']
    assert result['evidence_class'] == 'ARITHMETIC_SCENARIO_NOT_MEASURED_CAPACITY'


def test_tool_has_only_pure_standard_library_imports():
    source = Path(__file__).resolve().parents[1] / 'research/market_experience_capacity.py'
    tree = ast.parse(source.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {'__future__', 'dataclasses', 'json', 'math'}

"""Offline workload arithmetic, not a benchmark, budget grant or runtime scheduler.

Run: python3 research/market_experience_capacity.py
Prices are planning observations dated 2026-09-24; refresh before procurement.
No network, provider calls, data reads, training or persistent state writes.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math


@dataclass(frozen=True)
class Workload:
    issuers: int
    years: int
    sessions_per_year: int = 252
    features: int = 512
    bytes_per_feature: int = 4
    documents_per_issuer_year: int = 8
    input_tokens_per_document: int = 12000
    billed_output_tokens_per_document: int = 1000
    processing_multiplier: float = 3.0

    def __post_init__(self) -> None:
        for field, value in asdict(self).items():
            if field == 'processing_multiplier':
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f'{field} must be a finite number >= 1')
                if not math.isfinite(value) or value < 1:
                    raise ValueError(f'{field} must be a finite number >= 1')
            elif isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f'{field} must be a positive integer')


@dataclass(frozen=True)
class TokenPrice:
    input_usd_per_million: float
    output_usd_per_million: float

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError('prices must be finite nonnegative numbers')
            if not math.isfinite(value) or value < 0:
                raise ValueError('prices must be finite nonnegative numbers')


def token_cost(input_tokens: int, output_tokens: int, price: TokenPrice) -> float:
    for value in (input_tokens, output_tokens):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('token counts must be nonnegative integers')
    return (input_tokens * price.input_usd_per_million
            + output_tokens * price.output_usd_per_million) / 1_000_000


def estimate(workload: Workload, price: TokenPrice) -> dict:
    rows = workload.issuers * workload.years * workload.sessions_per_year
    docs = workload.issuers * workload.years * workload.documents_per_issuer_year
    inputs = docs * workload.input_tokens_per_document
    outputs = docs * workload.billed_output_tokens_per_document
    one_pass = token_cost(inputs, outputs, price)
    naive_one_pass = token_cost(
        rows * workload.input_tokens_per_document,
        rows * workload.billed_output_tokens_per_document, price)
    return {
        'stock_day_rows': rows,
        'quarterly_event_opportunities': workload.issuers * workload.years * 4,
        'assumed_unique_documents': docs,
        'numeric_dense_gb': rows * workload.features * workload.bytes_per_feature / 1e9,
        'input_tokens_one_pass': inputs,
        'billed_output_tokens_one_pass': outputs,
        'document_token_cost_one_pass_usd': one_pass,
        'document_token_cost_with_processing_allowance_usd':
            one_pass * workload.processing_multiplier,
        'naive_daily_reanalysis_token_cost_with_same_allowance_usd':
            naive_one_pass * workload.processing_multiplier,
        'assumptions': asdict(workload),
        'price': asdict(price),
        'not_included': ['data licenses', 'engineering', 'human review', 'search tools',
                         'storage and requests', 'electricity', 'training', 'tax',
                         'unmodeled billed reasoning tokens', 'news/options/tick corpus'],
        'evidence_class': 'ARITHMETIC_SCENARIO_NOT_MEASURED_CAPACITY',
    }


PRICES = {
    'glm_5_3_flash': TokenPrice(0.15, 0.50),
    'grok_4_3': TokenPrice(1.25, 2.50),
    'glm_5_3': TokenPrice(1.40, 4.40),
}
PRICE_SOURCES = {
    'glm': 'https://docs.z.ai/guides/overview/pricing',
    'grok': 'https://docs.x.ai/developers/models/grok-4.3',
}


def report() -> dict:
    scenarios = {'pilot_50_issuers_5_years': Workload(50, 5),
                 'coverage_500_slots_30_years': Workload(500, 30)}
    return {
        'as_of': '2026-09-24',
        'status': 'PLANNING_ONLY_NO_SPEND_AUTHORITY',
        'price_sources': PRICE_SOURCES,
        'scenarios': {name: {provider: estimate(work, price)
                            for provider, price in PRICES.items()}
                      for name, work in scenarios.items()},
    }


if __name__ == '__main__':
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))

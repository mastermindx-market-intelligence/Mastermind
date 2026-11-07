#!/usr/bin/env python3
"""Deterministic metadata-only issuer preselection for I3 W0.

This module selects a *candidate discovery pool* from a pinned current industry
map.  It does not certify historical eligibility, assign events, inspect source
bodies, grant rights, or register a trial.  Historical beta assignment requires
separate event-date PIT membership plus event-time business-family evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SOURCE_REPOSITORY = "mastermindx-market-intelligence/macro"
SOURCE_COMMIT = "94e5865e13fc42063f9c7d1e9b485958ccaee5b1"
INDUSTRY_MAP_PATH = "data/sp500_heatmap/industry_map.json"
INDUSTRY_MAP_BLOB = "d33e40ae40040efd21fe1895cf3544a89d5b3637"
PIT_MEMBERSHIP_PATH = "data/breadth/sp1500_pit_membership.parquet"
PIT_MEMBERSHIP_BLOB = "ec7085bc7460aca4a07661fa5983c424e1559be8"
FREEZE_TIME = "2026-10-04T05:35:05.807358+00:00"
EXCLUDED_DEVELOPMENT_EXPOSED = frozenset({"AAPL", "PG"})

# Exact, closed predicates over the pinned industry-map fields.  These are
# sampling proxies only; they are not owner economic classifications.
PROXY_PREDICATES: dict[str, tuple[str, frozenset[str]]] = {
    "bank": ("Financial", frozenset({"Banks - Diversified", "Banks - Regional"})),
    "consumer_price_mix_proxy": (
        "Consumer Defensive",
        frozenset({"Packaged Foods", "Household & Personal Products"}),
    ),
    "homebuilder": ("Consumer Cyclical", frozenset({"Residential Construction"})),
    "industrial_backlog_proxy": (
        "Industrials",
        frozenset({"Farm & Heavy Construction Machinery", "Specialty Industrial Machinery"}),
    ),
    "saas_proxy": ("Technology", frozenset({"Software - Application"})),
    "semiconductor_channel": ("Technology", frozenset({"Semiconductors"})),
}

# One-based positions within the ticker-lexical eligible list after the explicit
# development-exposed exclusions above.
ROLE_POSITIONS: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("beta_validation_candidate", "bank", (1, 2, 3)),
    ("beta_validation_candidate", "industrial_backlog_proxy", (1, 2, 3)),
    ("beta_validation_candidate", "saas_proxy", (1, 2, 3)),
    ("beta_validation_candidate", "semiconductor_channel", (1, 2, 3)),
    ("prospective_temporal_holdout_candidate", "bank", (4, 5)),
    ("prospective_temporal_holdout_candidate", "consumer_price_mix_proxy", (1, 2, 3)),
    ("prospective_temporal_holdout_candidate", "industrial_backlog_proxy", (4, 5)),
    ("prospective_temporal_holdout_candidate", "saas_proxy", (4, 5)),
    ("prospective_temporal_holdout_candidate", "semiconductor_channel", (4, 5, 6)),
    ("broad_reserve_candidate", "consumer_price_mix_proxy", (4, 5)),
    ("broad_reserve_candidate", "homebuilder", (1, 2, 3, 4)),
)

EXPECTED_TICKERS: tuple[str, ...] = (
    "BAC", "C", "CFG", "AME", "AOS", "CAT", "ADSK", "APP", "CRM", "ADI", "AMD", "AVGO",
    "FITB", "HBAN", "CAG", "CHD", "CL", "CMI", "DE", "DASH", "FICO", "INTC", "MCHP", "MPWR",
    "CLX", "EL", "DHI", "LEN", "NVR", "PHM",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _eligible(industry_map: Mapping[str, Any], proxy: str) -> list[str]:
    sector, subindustries = PROXY_PREDICATES[proxy]
    out: list[str] = []
    for ticker, row in industry_map.items():
        if ticker in EXCLUDED_DEVELOPMENT_EXPOSED or not isinstance(row, Mapping):
            continue
        if row.get("sector") == sector and row.get("sub_industry") in subindustries:
            out.append(str(ticker))
    return sorted(out)


def select_candidates(industry_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(industry_map, Mapping):
        raise ValueError("industry map must be an object keyed by ticker")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role, proxy, positions in ROLE_POSITIONS:
        eligible = _eligible(industry_map, proxy)
        for position in positions:
            if position < 1 or position > len(eligible):
                raise ValueError(f"proxy {proxy} does not contain position {position}")
            ticker = eligible[position - 1]
            if ticker in seen:
                raise ValueError(f"ticker selected twice: {ticker}")
            seen.add(ticker)
            rows.append({"role": role, "proxy": proxy, "position": position, "ticker": ticker})
    if tuple(row["ticker"] for row in rows) != EXPECTED_TICKERS:
        raise ValueError("pinned industry map no longer reproduces the frozen candidate sequence")
    return rows


def receipt(industry_map: Mapping[str, Any]) -> dict[str, Any]:
    rows = select_candidates(industry_map)
    payload = {
        "schema": "issuer_inflection.corpus_preselection_method/v1",
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "industry_map_path": INDUSTRY_MAP_PATH,
        "industry_map_blob": INDUSTRY_MAP_BLOB,
        "pit_membership_path": PIT_MEMBERSHIP_PATH,
        "pit_membership_blob": PIT_MEMBERSHIP_BLOB,
        "freeze_time": FREEZE_TIME,
        "development_exposed_exclusions": sorted(EXCLUDED_DEVELOPMENT_EXPOSED),
        "historical_beta_eligibility": (
            "current industry proxy is discovery-only; historical assignment requires event-date PIT membership "
            "and event-time owner-qualified business-family metadata, otherwise use a post-freeze event"
        ),
        "prospective_holdout_eligibility": "event must occur strictly after freeze and before body inspection",
        "rows": rows,
    }
    payload["selection_sha256"] = hashlib.sha256(_canonical(rows)).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("industry_map", type=Path)
    args = parser.parse_args()
    raw = args.industry_map.read_bytes()
    parsed = json.loads(raw)
    result = receipt(parsed)
    result["industry_map_sha256"] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

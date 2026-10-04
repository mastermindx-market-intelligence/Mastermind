#!/usr/bin/env python3
from __future__ import annotations

import unittest

from corpus_preselection_protocol import EXPECTED_TICKERS, select_candidates


class CorpusPreselectionProtocolTests(unittest.TestCase):
    def source(self):
        # Minimal synthetic map that preserves the real pinned predicate/order
        # shape while proving selection is driven by exact fields, not prose.
        rows = {}
        values = {
            "bank": ("Financial", ["Banks - Diversified", "Banks - Regional"], ["BAC", "C", "CFG", "FITB", "HBAN", "JPM"]),
            "consumer": ("Consumer Defensive", ["Packaged Foods", "Household & Personal Products"], ["CAG", "CHD", "CL", "CLX", "EL", "GIS", "PG"]),
            "home": ("Consumer Cyclical", ["Residential Construction"], ["DHI", "LEN", "NVR", "PHM"]),
            "industrial": ("Industrials", ["Specialty Industrial Machinery", "Farm & Heavy Construction Machinery"], ["AME", "AOS", "CAT", "CMI", "DE", "DOV"]),
            "software": ("Technology", ["Software - Application"], ["ADSK", "APP", "CRM", "DASH", "FICO", "INTU"]),
            "semis": ("Technology", ["Semiconductors"], ["ADI", "AMD", "AVGO", "INTC", "MCHP", "MPWR", "NVDA"]),
        }
        for _, (sector, subs, tickers) in values.items():
            for i, ticker in enumerate(tickers):
                rows[ticker] = {"sector": sector, "sub_industry": subs[i % len(subs)]}
        rows["AAPL"] = {"sector": "Technology", "sub_industry": "Consumer Electronics"}
        rows["ZZZ"] = {"sector": "Utilities", "sub_industry": "Utilities - Regulated Electric"}
        return rows

    def test_exact_frozen_sequence(self):
        actual = tuple(row["ticker"] for row in select_candidates(self.source()))
        self.assertEqual(actual, EXPECTED_TICKERS)

    def test_unrelated_rows_do_not_change_selection(self):
        source = self.source()
        source["AAA"] = {"sector": "Utilities", "sub_industry": "Utilities - Diversified"}
        self.assertEqual(tuple(row["ticker"] for row in select_candidates(source)), EXPECTED_TICKERS)

    def test_predicate_change_is_not_silently_accepted(self):
        source = self.source()
        source["BAC"]["sub_industry"] = "Capital Markets"
        with self.assertRaisesRegex(ValueError, "frozen candidate sequence"):
            select_candidates(source)

    def test_development_exposed_pg_is_excluded_before_positions(self):
        source = self.source()
        source["PG"] = {"sector": "Consumer Defensive", "sub_industry": "Household & Personal Products"}
        actual = {row["ticker"] for row in select_candidates(source)}
        self.assertNotIn("PG", actual)


if __name__ == "__main__":
    unittest.main()

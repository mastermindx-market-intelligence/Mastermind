"""Offline unit tests for the capacity policy (no network, no credentials).

Run: python3 -m unittest ops/native_fabric/anthropic_oauth_proxy/test_budget.py
"""
from __future__ import annotations

import unittest

from ops.native_fabric.anthropic_oauth_proxy.budget import (
    DEFAULT_WEIGHTS,
    SlidingBudget,
    model_weight,
    parse_model_weights,
)


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class WeightTests(unittest.TestCase):
    def test_default_weights(self) -> None:
        self.assertEqual(model_weight("claude-fable-5.1", DEFAULT_WEIGHTS), 2.0)
        self.assertEqual(model_weight("claude-fable-5", DEFAULT_WEIGHTS), 2.0)
        self.assertEqual(model_weight("claude-opus-5-5", DEFAULT_WEIGHTS), 1.5)
        self.assertEqual(model_weight("claude-opus-5", DEFAULT_WEIGHTS), 1.5)
        self.assertEqual(model_weight("claude-opus-4-8", DEFAULT_WEIGHTS), 1.0)
        self.assertEqual(model_weight("claude-haiku-4-5-20251001", DEFAULT_WEIGHTS), 1.0)

    def test_parse_order_and_catch_all(self) -> None:
        weights = parse_model_weights("claude-sonnet-5*=1.25,claude-fable-5*=2.0")
        self.assertEqual(weights[-1], ("*", 1.0))
        self.assertEqual(model_weight("claude-sonnet-5-5", weights), 1.25)
        self.assertEqual(model_weight("claude-fable-5.1", weights), 2.0)
        self.assertEqual(model_weight("claude-opus-5", weights), 1.0)


class BudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()

    def budget(self, **kwargs) -> SlidingBudget:
        base = dict(
            five_hour_budget=5.0,
            weekly_budget=100.0,
            weights=DEFAULT_WEIGHTS,
            clock=self.clock,
        )
        base.update(kwargs)
        return SlidingBudget(**base)

    def test_fable_costs_double_and_is_skipped_when_it_does_not_fit(self) -> None:
        ledger = self.budget(five_hour_budget=4.0)
        for _ in range(3):
            ledger.record("max-1", 1.0)
        # 3.0 used + 1.0 haiku fits, 3.0 + 2.0 fable does not.
        self.assertTrue(ledger.affordable("max-1", 1.0, self.clock()))
        self.assertFalse(ledger.affordable("max-1", 2.0, self.clock()))
        chosen, next_ready = ledger.choose(["max-1"], 2.0, self.clock())
        self.assertIsNone(chosen)
        self.assertGreater(next_ready, self.clock())

    def test_two_fables_exhaust_a_four_point_window(self) -> None:
        ledger = self.budget(five_hour_budget=4.0)
        ledger.record("max-1", 2.0)
        ledger.record("max-1", 2.0)
        self.assertFalse(ledger.affordable("max-1", 1.0, self.clock()))
        self.assertAlmostEqual(ledger.remaining("max-1")["five_hour"], 0.0)

    def test_round_robin_alternates_across_accounts(self) -> None:
        ledger = self.budget()
        ids = ["max-1", "max-2", "max-3", "max-4"]
        seen = []
        for _ in range(4):
            account, _ = ledger.choose(ids, 1.0, self.clock())
            self.assertIsNotNone(account)
            seen.append(account)
            ledger.record(account, 1.0)
        self.assertEqual(seen, ids)

    def test_cooldown_account_is_skipped_until_expiry(self) -> None:
        ledger = self.budget()
        ids = ["max-1", "max-2"]
        ledger.cool("max-1", self.clock() + 60, "429")
        account, _ = ledger.choose(ids, 1.0, self.clock())
        self.assertEqual(account, "max-2")
        self.clock.advance(61)
        chosen = set()
        for _ in range(2):
            account, _ = ledger.choose(ids, 1.0, self.clock())
            chosen.add(account)
        self.assertEqual(chosen, {"max-1", "max-2"})

    def test_fable_exhaustion_preserves_haiku_capacity(self) -> None:
        ledger = self.budget(five_hour_budget=5.0)
        ids = ["max-1", "max-2"]
        served = []
        for _ in range(4):
            account, _ = ledger.choose(ids, 2.0, self.clock())
            self.assertIsNotNone(account)
            served.append(account)
            ledger.record(account, 2.0)
        # 4 fable requests at 2.0 fill both 5.0 windows to 4.0 of 5.0.
        self.assertEqual(served.count("max-1"), 2)
        self.assertEqual(served.count("max-2"), 2)
        self.assertIsNone(ledger.choose(ids, 2.0, self.clock())[0])
        # A haiku request still fits on each account (4.0 + 1.0 <= 5.0).
        self.assertEqual(ledger.choose(ids, 1.0, self.clock())[0] is not None, True)

    def test_weekly_window_blocks_after_five_hour_rollover(self) -> None:
        ledger = self.budget(five_hour_budget=10.0, weekly_budget=3.0)
        ledger.record("max-1", 2.0)
        self.clock.advance(5 * 3600 + 1)
        # Out of the 5h window but still inside the weekly budget.
        self.assertAlmostEqual(ledger.remaining("max-1")["five_hour"], 10.0)
        self.assertFalse(ledger.affordable("max-1", 2.0, self.clock()))

    def test_unrecord_refunds_a_rejected_reservation(self) -> None:
        ledger = self.budget(five_hour_budget=2.0)
        ledger.record("max-1", 2.0, at=self.clock())
        self.assertFalse(ledger.affordable("max-1", 1.0, self.clock()))
        ledger.unrecord("max-1", self.clock(), 2.0)
        self.assertTrue(ledger.affordable("max-1", 1.0, self.clock()))


if __name__ == "__main__":
    unittest.main()

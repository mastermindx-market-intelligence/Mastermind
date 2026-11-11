"""Settlement learning finalization must bind to the exact retained paper receipt."""
from __future__ import annotations

import importlib

import pytest


def test_republish_helper_forwards_exact_settlement_receipt_id(monkeypatch) -> None:
    from bot import settle

    transaction_id = "a" * 64
    observed = []

    class _Module:
        @staticmethod
        def republish(asof, *, submission=None, settlement_prices=None,
                      settlement_receipt_id=None):
            observed.append((asof, settlement_receipt_id))
            return {"ok": True}

    monkeypatch.setattr(importlib, "import_module", lambda name: _Module)

    out = settle._republish(
        "autonomous",
        "2026-09-16",
        submission={"holdings": []},
        settlement_prices={"AAPL": 100.0},
        settlement_receipt_id=transaction_id,
    )

    assert out == {"ok": True}
    assert observed == [("2026-09-16", transaction_id)]


@pytest.mark.parametrize("module_name", ["bot.autonomous", "bot.china", "bot.hk"])
def test_active_republish_finalization_is_bound_to_exact_receipt(
    monkeypatch, module_name
) -> None:
    from brain import portfolio_learning
    from bridge import build_portfolio
    from portfolio import paper_account

    module = importlib.import_module(module_name)
    transaction_id = "b" * 64
    submission = {"holdings": [], "summary": "receipt-bound republish"}
    observed = []

    monkeypatch.setattr(paper_account, "_load_account", lambda *a, **k: {"positions": {}})
    monkeypatch.setattr(module, "_build_payload", lambda *a, **k: {})
    monkeypatch.setattr(build_portfolio, "write", lambda *a, **k: None)
    monkeypatch.setattr(
        portfolio_learning,
        "settle_application",
        lambda *a, **k: {
            "ok": False,
            "transitioned": False,
            "error": "application_settlement_transaction_conflict",
        },
    )

    def finalization(book, sub, *, settlement_receipt_id=None):
        observed.append(settlement_receipt_id)
        # A stale prior application could satisfy the old unbound check. The exact receipt must fail.
        if settlement_receipt_id is None:
            return {"ok": True, "required": True, "settlement_transaction_id": "c" * 64}
        assert settlement_receipt_id == transaction_id
        return {"ok": False, "required": True, "error": "lesson_application_receipt_mismatch"}

    monkeypatch.setattr(
        portfolio_learning, "application_finalization_status", finalization
    )

    out = module.republish(
        "2026-09-16",
        submission=submission,
        settlement_prices={},
        settlement_receipt_id=transaction_id,
    )

    assert observed == [transaction_id]
    assert out["ok"] is False
    assert out["error"] == "lesson_application_not_durable"

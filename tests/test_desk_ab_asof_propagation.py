"""Regression for desk A/B point-in-time price propagation.

`desk_ab.run(asof)` is a replay/forward-evaluation surface. Its mark request must carry the exact
same `asof` into the shared shadow-book price gatherer instead of silently defaulting to today.
"""
from __future__ import annotations

from portfolio import desk_ab
from portfolio import shadow_books as S


def test_run_propagates_exact_asof_to_shared_price_gatherer(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "_BOOKS", tmp_path / "shadow_books")
    monkeypatch.setattr(S, "_INPUTS", tmp_path / "inputs")
    monkeypatch.setattr(desk_ab, "_DESK_AB", tmp_path / "desk_ab")

    observed = []

    def fake_gather(tickers, seed, asof=None):
        observed.append({"tickers": set(tickers), "seed": seed, "asof": asof})
        return {}

    monkeypatch.setattr(S, "_gather_prices", fake_gather)

    result = desk_ab.run("2026-06-21", prices={}, inputs=[])

    assert result["as_of"] == "2026-06-21"
    assert len(observed) == 1
    assert observed[0]["asof"] == "2026-06-21"
    assert "SPY" in observed[0]["tickers"]

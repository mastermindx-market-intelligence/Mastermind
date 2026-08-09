"""Phase 1 acceptance — the one-name paper thesis runs end-to-end on fixed evidence."""
import bot  # noqa: F401

from bot import phase1


def test_phase1_end_to_end(monkeypatch):
    fixtures = {
        "data/regime/latest.json": {
            "date": "2026-06-18",
            "quad": "Q1",
            "quad_name": "Goldilocks",
            "liquidity_overlay": "neutral",
            "macro_risk": {"score": 0.28},
            "sector_rs": [
                {"ticker": "SMH", "rank": 1, "pctile_252d": 99.2},
                {"ticker": "XLK", "rank": 2, "pctile_252d": 87.0},
            ],
        },
        "site/stockdata/NVDA.json": {
            "tech": {"price": 120.0, "pct_vs_200dma": 12.0},
        },
        "site/basketdata/baskets.json": {"baskets": []},
    }
    monkeypatch.setattr(phase1, "_j", fixtures.__getitem__)
    monkeypatch.setattr(
        phase1,
        "leading_order",
        lambda chain, rs: {
            "chain": chain,
            "leading_order": 1,
            "next_baskets": ["power_grid"],
        },
    )
    monkeypatch.setattr(phase1.ledger, "append", lambda doc: True)
    monkeypatch.setattr(
        phase1.scorer,
        "track_record",
        lambda asof: {"status": "building", "as_of": asof.isoformat()},
    )
    monkeypatch.setattr(phase1, "write", lambda payload: {"hub": "isolated"})

    out = phase1.run()
    d = out["decision"]

    # a valid falsifiable decision was produced
    assert d["schema"] == "brain_decision.v1"
    assert d["lean"] == "add" and d["subject"] == "NVDA"
    assert 0.50 <= d["prob_correct"] <= 0.85
    assert d["falsifier"]["check"]["kind"] == "rel_return"   # ENGINE-derived, not model-authored
    assert d["check_by"] and d["time_stop_by"]               # both stops set

    # the confluence gate is honest: RS+regime confirmed, the new-leaf dims unverified
    g = out["gate"]
    assert g["size"] in ("none", "initial", "full")
    assert "rs" in g["confirmed"] and "catalyst" in g["unverified"]
    # doctrine discipline: no full size without the catalyst gate
    assert not (g["size"] == "full" and not g["catalyst_present"])

    # bottleneck baton-pass produced an order layer
    assert out["bottleneck"]["leading_order"] in (1, 2, 3)

    # paper-only / building track record until a thesis resolves
    assert out["track_record"]["status"] in ("building", "scoring")

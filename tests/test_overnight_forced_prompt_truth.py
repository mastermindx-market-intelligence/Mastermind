"""A manually forced but properly qualified calm tape is NOT a material move.

This tests prompt phrasing only. Actual provider enrollment remains disabled;
test-owned synthetic evidence never grants market access or trading authority.
"""
from __future__ import annotations

from datetime import datetime, timezone

from tests.test_overnight_source_admission import synthetic


def test_manual_reconsideration_never_claims_calm_market_moved_materially(
    monkeypatch,
):
    from bot import overnight as watcher
    from data_layer import overnight as source

    monkeypatch.setattr(source, "_host_live_source_admitted", lambda _: True)
    tape=synthetic(datetime.now(timezone.utc),change=0.1)
    assert source.qualifies_live_risk(tape) is True
    assert source.is_material(tape) is False
    prompt=watcher._overnight_directive("autonomous",tape,forced=True)
    assert "OVERNIGHT REVIEW" in prompt
    assert "manual" in prompt.lower()
    assert "calm" in prompt.lower()
    assert "moved materially" not in prompt
    assert "source-qualified" in prompt


def test_material_nonforced_stress_can_still_be_stated_as_material(monkeypatch):
    from bot import overnight as watcher
    from data_layer import overnight as source

    monkeypatch.setattr(source, "_host_live_source_admitted",lambda _: True)
    tape=synthetic(datetime.now(timezone.utc),change=-2.0)
    assert source.qualifies_live_risk(tape)
    assert source.is_material(tape)
    prompt=watcher._overnight_directive("autonomous",tape,forced=False)
    assert "OVERNIGHT REVIEW" in prompt
    assert "moved materially" in prompt
    assert "stressed" in prompt

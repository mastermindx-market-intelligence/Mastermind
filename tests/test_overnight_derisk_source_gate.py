"""Fast de-risk must not accept raw stale overnight labels as hard risk.

Only the overnight input channel is gated. Independent Macro Risk Officer,
dealer gamma, credit and distribution warnings retain existing severity law.
These tests run against mocked channels and never mutate any paper portfolio.
"""
from __future__ import annotations

from datetime import datetime, timezone

from tests.test_overnight_source_admission import synthetic


def _standalone_channels(monkeypatch, *, macro_state="risk_on"):
    from bot import derisk
    from brain import macro_risk

    monkeypatch.setattr(macro_risk, "risk_state",
                        lambda _asof, _regime: {
                            "state": macro_state, "gross_cap": 0.6,
                            "drivers": [],
                        })
    monkeypatch.setattr(derisk, "_gex_flip", lambda: (False, ""))
    monkeypatch.setattr(derisk, "_credit_gap", lambda: (False, ""))
    monkeypatch.setattr(derisk, "_theme_drop", lambda _drivers: (False, ""))
    monkeypatch.setattr(derisk, "_distribution_escalation",
                        lambda _pid: (0, ""))


def test_fast_derisk_cannot_use_forged_live_stress_as_hard_confirmation(
    monkeypatch,
):
    from bot import derisk
    from data_layer import overnight

    _standalone_channels(monkeypatch)
    packet=synthetic(datetime.now(timezone.utc), change=-2.0)
    monkeypatch.setattr(overnight, "tape", lambda: packet)
    assert not overnight.qualifies_live_risk(packet)
    result=derisk.tripwire("autonomous", "2026-10-15", regime={})
    assert result["severity"]==0
    assert result["trigger"] is False
    assert not any("overnight" in reason for reason in result["reasons"])


def test_fast_derisk_respects_test_only_authorized_overnight_stress(
    monkeypatch,
):
    from bot import derisk
    from data_layer import overnight

    _standalone_channels(monkeypatch)
    monkeypatch.setattr(overnight, "_host_live_source_admitted", lambda _: True)
    packet=synthetic(datetime.now(timezone.utc), change=-2.0)
    monkeypatch.setattr(overnight, "tape", lambda: packet)
    assert overnight.qualifies_live_risk(packet)
    result=derisk.tripwire("autonomous", "2026-10-15", regime={})
    assert result["severity"]==2
    assert result["trigger"] is True
    assert "overnight tape STRESSED" in result["reasons"]


def test_fast_derisk_independent_macro_confirmation_still_applies(
    monkeypatch,
):
    from bot import derisk
    from data_layer import overnight

    _standalone_channels(monkeypatch, macro_state="risk_off")
    monkeypatch.setattr(overnight, "tape", lambda: {
        "live": False, "risk": {"state": "stressed"},
        "source_quality": {"classification": "EOD_NOT_LIVE"},
    })
    result=derisk.tripwire("autonomous", "2026-10-15", regime={})
    assert result["trigger"] is True
    assert result["severity"]==2
    assert "macro RISK-OFF state" in result["reasons"]
    assert not any("overnight" in reason for reason in result["reasons"])

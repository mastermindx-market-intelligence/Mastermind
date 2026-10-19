"""An unqualified replacement tape cannot initiate even forced paper redecisions.

Only synthetic, test-owned source-authority probes are used. The actual
production source adapter is deliberately NOT admitted; a string or boolean
claim is never an entitlement or a provider-authenticated receipt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def synthetic(now: datetime, *, change: float = -0.8) -> dict:
    from data_layer import overnight
    groups = {
        "us_futures": [{"ticker": "ES=F", "name": "S&P 500 fut", "change_pct": change}],
        "international": [], "vol": [],
    }
    return {
        "live": True,
        "groups": groups,
        "risk": overnight.risk_read(groups),
        "source_quality": {
            "classification": "LIVE_QUALIFIED",
            "source_vendor": "synthetic-test-source",
            "source_receipt_id": "SYNTHETICRECEIPT1234",
            "source_observed_at_utc": now.isoformat(),
            "dataos_identity_admitted": True,
            "source_rights_admitted": True,
            "realtime_venue_admitted": True,
            "risk_qualified": True,
        },
    }


def test_asserted_source_quality_without_trusted_host_receipt_never_triggers():
    from data_layer import overnight
    packet = synthetic(datetime.now(timezone.utc))
    assert not overnight.is_material(packet)
    assert not overnight.qualifies_live_risk(packet)


@pytest.mark.parametrize("mutation", [
    "missing_live", "old_eod_label", "rights_false", "dataos_false",
    "venue_false", "risk_false", "missing_receipt", "missing_vendor",
    "stale_2020", "future_observation", "naive_clock",
    "contradictory_risk", "no_risk_rows", "nan_risk",
])
def test_even_trusted_synthetic_host_rejects_bad_source_evidence(monkeypatch, mutation):
    from data_layer import overnight
    now = datetime.now(timezone.utc)
    packet = synthetic(now)
    monkeypatch.setattr(overnight, "_host_live_source_admitted", lambda _evidence: True)
    quality = packet["source_quality"]
    if mutation == "missing_live":
        packet.pop("live")
    elif mutation == "old_eod_label":
        quality["classification"] = "EOD_NOT_LIVE"
    elif mutation == "rights_false":
        quality["source_rights_admitted"] = False
    elif mutation == "dataos_false":
        quality["dataos_identity_admitted"] = False
    elif mutation == "venue_false":
        quality["realtime_venue_admitted"] = False
    elif mutation == "risk_false":
        quality["risk_qualified"] = False
    elif mutation == "missing_receipt":
        quality.pop("source_receipt_id")
    elif mutation == "missing_vendor":
        quality["source_vendor"] = ""
    elif mutation == "stale_2020":
        quality["source_observed_at_utc"] = "2020-01-01T00:00:00+00:00"
    elif mutation == "future_observation":
        quality["source_observed_at_utc"] = (now+timedelta(minutes=20)).isoformat()
    elif mutation == "naive_clock":
        quality["source_observed_at_utc"] = now.replace(tzinfo=None).isoformat()
    elif mutation == "contradictory_risk":
        packet["risk"] = {"state": "calm"}
    elif mutation == "no_risk_rows":
        packet["groups"] = {"us_futures": [], "international": [], "vol": []}
    elif mutation == "nan_risk":
        packet["groups"]["us_futures"][0]["change_pct"] = float("nan")
    assert not overnight.qualifies_live_risk(packet)
    assert not overnight.is_material(packet)


@pytest.mark.parametrize("force", [False, True])
def test_watch_cannot_turn_unqualified_stress_into_a_model_call(
    monkeypatch, force,
):
    from bot import overnight as watcher, settle, autonomous, derisk
    from data_layer import overnight as source
    from portfolio import registry, autonomous_migration, paper_account
    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    monkeypatch.setattr(autonomous_migration, "is_pending_migration", lambda: False)
    monkeypatch.setattr(settle, "is_open", lambda _pid: False)
    monkeypatch.setattr(paper_account, "preflight_pending_target",
                        lambda _pid: {"ok": True, "pending": True})
    monkeypatch.setattr(derisk, "enabled", lambda: False)
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    # A forged claimed admission is not enough: default owner still denies.
    monkeypatch.setattr(source, "tape", lambda force=False:t)
    def cannot_run(*_args,**_kwargs):
        raise AssertionError("unqualified source attempted model")
    monkeypatch.setattr(autonomous,"run_autonomous",cannot_run)
    result=watcher.watch("autonomous","2026-10-15",force=force)
    assert result["skipped"]=="tape_unavailable"
    assert "refined" not in result
    assert "error" not in result


def test_synthetic_trusted_and_fresh_source_still_exercises_positive_tripwire(monkeypatch):
    from data_layer import overnight
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(overnight, "_host_live_source_admitted", lambda _evidence: True)
    t=synthetic(now,change=-2.0)
    assert overnight.qualifies_live_risk(t)
    assert overnight.is_material(t)
    t["groups"]["us_futures"][0]["change_pct"]=0.0
    t["risk"]=overnight.risk_read(t["groups"])
    assert overnight.qualifies_live_risk(t)
    assert not overnight.is_material(t)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("mutation", [
    "missing_live", "claimed_live_daily", "expired", "future",
    "bad_source_rights", "inconsistent_risk",
])
def test_watch_rejects_bad_tape_even_when_test_host_verifier_would_approve(
    monkeypatch, force, mutation,
):
    """Explicit adversarial replacement payload, original caller and clock."""
    from bot import overnight as watcher, settle, autonomous, derisk
    from data_layer import overnight as source
    from portfolio import registry, autonomous_migration, paper_account
    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    monkeypatch.setattr(autonomous_migration, "is_pending_migration", lambda: False)
    monkeypatch.setattr(settle, "is_open", lambda _pid: False)
    monkeypatch.setattr(paper_account, "preflight_pending_target",
                        lambda _pid: {"ok": True, "pending": True})
    monkeypatch.setattr(derisk, "enabled", lambda: False)
    monkeypatch.setattr(source, "_host_live_source_admitted", lambda _: True)
    now=datetime.now(timezone.utc)
    packet=synthetic(now, change=-2.0)
    quality=packet["source_quality"]
    if mutation=="missing_live":
        del packet["live"]
    elif mutation=="claimed_live_daily":
        quality["classification"]="EOD_NOT_LIVE"
        quality["risk_qualified"]=False
    elif mutation=="expired":
        quality["source_observed_at_utc"]=(now-timedelta(minutes=15)).isoformat()
    elif mutation=="future":
        quality["source_observed_at_utc"]=(now+timedelta(minutes=15)).isoformat()
    elif mutation=="bad_source_rights":
        quality["source_rights_admitted"]=False
    elif mutation=="inconsistent_risk":
        packet["risk"]["state"]="calm"

    monkeypatch.setattr(source, "tape", lambda force=False: packet)
    def _not_called(*_args, **_kwargs):
        raise AssertionError("unqualified original tape attempted model submission")
    monkeypatch.setattr(autonomous, "run_autonomous", _not_called)
    result=watcher.watch("autonomous", "2026-10-15", force=force)
    assert result["skipped"]=="tape_unavailable"
    assert "refined" not in result and "error" not in result


@pytest.mark.parametrize("force,change,should_run", [
    (False, -2.0, True),
    (False, 0.1, False),
    (True, 0.1, True),
])
def test_original_watch_uses_fresh_synthetic_admission_and_force_only_after_qualification(
    monkeypatch, force, change, should_run,
):
    from bot import overnight as watcher, settle, autonomous, derisk
    from data_layer import overnight as source
    from portfolio import registry, autonomous_migration, paper_account
    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    monkeypatch.setattr(autonomous_migration, "is_pending_migration", lambda: False)
    monkeypatch.setattr(settle, "is_open", lambda _pid: False)
    monkeypatch.setattr(paper_account, "preflight_pending_target",
                        lambda _pid: {"ok": True, "pending": True})
    monkeypatch.setattr(derisk, "enabled", lambda: False)
    monkeypatch.setattr(source, "_host_live_source_admitted", lambda _: True)
    packet=synthetic(datetime.now(timezone.utc),change=change)
    monkeypatch.setattr(source, "tape", lambda force=False: packet)
    started=[]
    def fake_run(asof=None,directive=None):
        started.append((asof,directive))
        return {"decided": True, "queued_for_open": True,
                "holdings":1, "brain":{"ok": True}}
    monkeypatch.setattr(autonomous,"run_autonomous",fake_run)
    outcome=watcher.watch("autonomous","2026-10-15",force=force)
    assert len(started)==int(should_run)
    if should_run:
        assert outcome["refined"]["decided"] is True
        assert started[0][0]=="2026-10-15"
        assert "LIVE overnight tape" in started[0][1]
    else:
        assert outcome["skipped"]=="tape_calm"
        assert "refined" not in outcome


@pytest.mark.parametrize("field,value", [
    ("source_observed_at_utc", "2026-10-15T03:00:00"),
    ("source_receipt_id", "weak"),
    ("source_vendor", "http://example.com/other"),
])
def test_malformed_provenance_cannot_use_authoritative_synthetic_verdict(
    monkeypatch, field, value,
):
    from data_layer import overnight
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    packet["source_quality"][field]=value
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda _: True)
    assert not overnight.qualifies_live_risk(packet)
    assert not overnight.is_material(packet)


@pytest.mark.parametrize("group,ticker", [
    ("fx_rates", "JPY=X"), ("commodities", "CL=F"), ("crypto", "BTC-USD"),
])
def test_supplemental_model_visible_fields_must_be_finite(
    monkeypatch, group, ticker,
):
    from data_layer import overnight
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    t["groups"][group]=[{"ticker":ticker,"name":"forged provider label",
                         "change_pct":float("nan")}]
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda _:True)
    assert not overnight.qualifies_live_risk(t)


def test_missing_vendor_supplied_name_does_not_break_reviewed_display(
    monkeypatch,
):
    from data_layer import overnight
    from bot import overnight as watcher
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    t["groups"]["us_futures"][0].pop("name")
    monkeypatch.setattr(overnight, "_host_live_source_admitted", lambda _:True)
    assert overnight.qualifies_live_risk(t)
    directive=watcher._overnight_directive("autonomous",t)
    assert "S&P 500 fut -2.00%" in directive
    assert "forged provider label" not in directive


@pytest.mark.parametrize("huge", [10**400, 1e308])
def test_large_numeric_values_never_make_live_risk_or_raise(
    monkeypatch, huge,
):
    from data_layer import overnight
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    t["groups"]["us_futures"][0]["change_pct"]=huge
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda _:True)
    assert overnight.qualifies_live_risk(t) is False
    assert overnight.is_material(t) is False
    if isinstance(huge,int):
        assert overnight.risk_read(t["groups"])["state"]=="unknown"


def test_authentication_owner_must_bind_full_observation_not_just_receipt(
    monkeypatch,
):
    import copy
    from data_layer import overnight
    approved=synthetic(datetime.now(timezone.utc),change=0.1)
    reference=copy.deepcopy(approved)
    seen=[]
    def original_source_owner(observation):
        seen.append(observation)
        return observation==reference
    monkeypatch.setattr(overnight,"_host_live_source_admitted",original_source_owner)
    assert overnight.qualifies_live_risk(approved) is True
    assert seen[-1] is approved
    modified=copy.deepcopy(approved)
    modified["groups"]["us_futures"][0]["change_pct"]=-20.0
    modified["risk"]=overnight.risk_read(modified["groups"])
    assert modified["source_quality"]==reference["source_quality"]
    assert overnight.qualifies_live_risk(modified) is False
    assert seen[-1] is modified

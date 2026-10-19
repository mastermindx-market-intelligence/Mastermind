"""Revocation after source admission may not produce live-qualified output.

No real provider/market data, paper book or model is exercised here. The host
source hook is synthetic and remains default DENY in production.
"""
from datetime import datetime, timezone

import pytest

from tests.test_overnight_source_admission import synthetic


def test_actual_directive_refuses_rights_revoked_during_macro_lookup(monkeypatch):
    from bot import overnight as watcher
    from brain import macro_risk
    from data_layer import overnight
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    grant={"valid":True}
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda _:grant["valid"])
    def macro_wakes_with_revocation(*_args,**_kwargs):
        grant["valid"]=False
        return {"state":"risk_on"}
    monkeypatch.setattr(macro_risk,"risk_state",macro_wakes_with_revocation)
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        watcher._overnight_directive("autonomous",packet)


def test_revoked_observation_is_reported_unknown_not_stressed(monkeypatch):
    from bot import overnight as watcher, autonomous, settle, derisk
    from data_layer import overnight
    from portfolio import registry,autonomous_migration,paper_account
    grant={"valid":True}
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda _:grant["valid"])
    monkeypatch.setattr(overnight,"tape",lambda force=False:packet)
    monkeypatch.setattr(registry,"is_archived",lambda _pid:False)
    monkeypatch.setattr(autonomous_migration,"is_pending_migration",lambda:False)
    monkeypatch.setattr(settle,"is_open",lambda _pid:False)
    monkeypatch.setattr(paper_account,"preflight_pending_target",
                        lambda _pid:{"ok":True,"pending":True})
    monkeypatch.setattr(derisk,"enabled",lambda:False)
    def revoke_at_prompt(*args,**kwargs):
        grant["valid"]=False
        return "synthetic directive never delivered"
    monkeypatch.setattr(watcher,"_overnight_directive",revoke_at_prompt)
    monkeypatch.setattr(autonomous,"run_autonomous",
                        lambda *_a,**_k:pytest.fail("revoked source started a model"))
    result=watcher.watch("autonomous","2026-10-15",force=True)
    assert result["skipped"]=="tape_unavailable"
    assert result["overnight_risk"]=="unknown"
    assert "refined" not in result


def _watched_book(monkeypatch,packet):
    from data_layer import overnight
    from bot import settle,derisk
    from portfolio import registry,autonomous_migration,paper_account
    monkeypatch.setattr(overnight,"tape",lambda force=False:packet)
    monkeypatch.setattr(registry,"is_archived",lambda _pid:False)
    monkeypatch.setattr(autonomous_migration,"is_pending_migration",lambda:False)
    monkeypatch.setattr(settle,"is_open",lambda _pid:False)
    monkeypatch.setattr(paper_account,"preflight_pending_target",
                        lambda _pid:{"ok":True,"pending":True})
    monkeypatch.setattr(derisk,"enabled",lambda:False)


def test_real_macro_lookup_revocation_returns_unknown_not_stressed_or_error(monkeypatch):
    from bot import overnight as watcher,autonomous
    from brain import macro_risk
    from data_layer import overnight
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    grant={"valid":True}
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda _:grant["valid"])
    _watched_book(monkeypatch,packet)
    def revoke_from_macro(*_a,**_k):
        grant["valid"]=False
        return {"state":"risk_on"}
    monkeypatch.setattr(macro_risk,"risk_state",revoke_from_macro)
    monkeypatch.setattr(autonomous,"run_autonomous",
                        lambda *_a,**_k:pytest.fail("revoked source started runner"))
    actual=watcher.watch("autonomous","2026-10-15")
    assert actual["skipped"]=="tape_unavailable"
    assert actual["overnight_risk"]=="unknown"
    assert "stressed" not in actual["tape_brief"].lower()
    assert "error" not in actual and "refined" not in actual


def test_caught_source_revocation_in_existing_runner_is_not_a_refined_result(monkeypatch):
    from bot import overnight as watcher,autonomous
    from data_layer import overnight
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    grant={"valid":True}
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda _:grant["valid"])
    _watched_book(monkeypatch,packet)
    monkeypatch.setattr(watcher,"_overnight_directive",
                        lambda *_a,**_k:"OVERNIGHT REVIEW — synthetically verified")
    def runner_that_catches_failure(*_a,**kwargs):
        directive=kwargs["directive"]
        grant["valid"]=False
        try:
            watcher.require_overnight_source_at_dispatch(directive)
        except ValueError:
            return {"brain":{"error":"source revoked"},"decided":False}
        pytest.fail("revoked observation was accepted")
    monkeypatch.setattr(autonomous,"run_autonomous",runner_that_catches_failure)
    result=watcher.watch("autonomous","2026-10-15")
    assert result["skipped"]=="tape_unavailable"
    assert result["overnight_risk"]=="unknown"
    assert "error" not in result and "refined" not in result


def test_initial_monotonic_deadline_cannot_be_extended_by_wall_clock_rollback(monkeypatch):
    from datetime import timedelta
    from bot import overnight as watcher
    from data_layer import overnight
    wall=datetime.now(timezone.utc)
    packet=synthetic(wall-timedelta(seconds=290),change=-2.0)
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda _:True)
    before=overnight._monotonic_clock()
    qualified=overnight.qualified_live_snapshot(packet)
    assert qualified is not None
    deadline=overnight._initial_source_deadline(qualified,wall,before)
    assert deadline is not None and 0 < deadline-before < 13
    # Subsequent wall-clock changes are irrelevant to the original window.
    monkeypatch.setattr(overnight,"_monotonic_clock",lambda:deadline+1)
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        watcher.QualifiedOvernightDirective(
            "OVERNIGHT REVIEW — initially authorized",qualified,
            source_deadline=deadline)


def test_original_expiry_during_final_host_verification_refuses_dispatch(monkeypatch):
    from bot import overnight as watcher
    from data_layer import overnight
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda _:True)
    directive=watcher.QualifiedOvernightDirective(
        "OVERNIGHT REVIEW — sealed synthetic only",packet)
    expiry=directive._source_deadline
    clock={"now":expiry-.1}
    monkeypatch.setattr(overnight,"_monotonic_clock",lambda:clock["now"])
    def host_crosses_deadline(_source):
        # Source was initially admitted. Verification itself consumes the
        # remaining 100ms; wall time may jump backward but elapsed time wins.
        clock["now"]=expiry+1
        return True
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        host_crosses_deadline)
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        watcher.require_overnight_source_at_dispatch(directive)
    assert directive._source_revoked is True


def test_failed_materiality_reverification_is_unavailable_not_calm(monkeypatch):
    from bot import overnight as watcher,autonomous
    from data_layer import overnight
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    _watched_book(monkeypatch,packet)
    state={"calls":0}
    def host(_source):
        state["calls"]+=1
        return state["calls"]<=2
    monkeypatch.setattr(overnight,"_host_live_source_admitted",host)
    monkeypatch.setattr(autonomous,"run_autonomous",
                        lambda *_a,**_k:pytest.fail("source-lost materiality started a model"))
    outcome=watcher.watch("autonomous","2026-10-15")
    assert state["calls"]>=3
    assert outcome["skipped"]=="tape_unavailable"
    assert outcome["overnight_risk"]=="unknown"
    assert "stressed" not in outcome["tape_brief"].lower()
    assert "refined" not in outcome and "error" not in outcome

"""Future live source must not cross snapshot/publication boundaries by reference.

The host verdict is synthetic test control only. It does NOT grant real data
rights, venue clock, identity, provider access or paper-trading permission.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

from tests.test_overnight_source_admission import synthetic


def verified(monkeypatch, *, change=-2.0):
    from data_layer import overnight
    payload = synthetic(datetime.now(timezone.utc), change=change)
    monkeypatch.setattr(overnight, "_host_live_source_admitted", lambda _: True)
    assert overnight.qualifies_live_risk(payload)
    return payload


def test_admitted_public_projection_is_closed_bounded_and_detached(monkeypatch):
    from data_layer import overnight
    raw=verified(monkeypatch)
    raw["private_credential"] = "DO_NOT_EXPORT_TOKEN"
    raw["internal_host_path"] = "/private/active-source"
    raw["groups"]["us_futures"][0]["name"] = "BAD PROVIDER-SUPPLIED NAME"
    raw["groups"]["us_futures"][0]["internal"] = "DO_NOT_EXPORT_INTERNAL"
    projected=overnight.public_tape(raw)
    assert projected is not raw
    assert set(projected)=={
        "as_of","as_of_kind","groups","risk","n_symbols","live","source_quality"
    }
    assert projected["live"] is True
    assert projected["risk"]["state"]=="stressed"
    assert projected["as_of_kind"]=="source_observed_at"
    assert projected["as_of"]==raw["source_quality"]["source_observed_at_utc"]
    assert projected["groups"]["us_futures"][0]["name"]=="S&P 500 fut"
    assert "source_receipt_id" not in projected["source_quality"]
    assert "DO_NOT_EXPORT" not in json.dumps(projected)
    assert len(json.dumps(projected)) < 8192
    raw["groups"]["us_futures"][0]["change_pct"]=+5.0
    raw["risk"]=overnight.risk_read(raw["groups"])
    assert projected["risk"]["state"]=="stressed"
    assert projected["groups"]["us_futures"][0]["change_pct"]==-2.0


def test_snapshot_is_independent_of_host_caller_mutation(monkeypatch):
    from data_layer import overnight
    original=synthetic(datetime.now(timezone.utc),change=-2.0)
    seen=[]
    def host(source):
        seen.append(source)
        original["groups"]["us_futures"][0]["change_pct"]=+4.0
        original["risk"]=overnight.risk_read(original["groups"])
        return source["risk"]["state"]=="stressed"
    monkeypatch.setattr(overnight,"_host_live_source_admitted",host)
    snap=overnight.qualified_live_snapshot(original)
    assert snap is not None
    assert snap is not original and snap["groups"] is not original["groups"]
    # Host authentication sees a temporary verified decode; the consumer
    # receives a separate copy of the exact same sealed bytes.
    assert seen[-1] is not snap and seen[-1] is not original
    assert snap["groups"]["us_futures"][0]["change_pct"]==-2.0
    assert snap["risk"]["state"]=="stressed"
    assert original["risk"]["state"]=="calm"
    assert overnight.is_material(original) is False


@pytest.mark.parametrize("invalid",[
    {"private":{"huge":"X"*40000}},
    {"non_jsonable":object()},
    {"source_quality":{"source_observed_at_utc":float("nan")}},
])
def test_invalid_or_oversized_source_fails_before_host_authorization(monkeypatch,invalid):
    from data_layer import overnight
    original=synthetic(datetime.now(timezone.utc))
    original.update(invalid)
    called=[]
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda x:called.append(x) or True)
    assert overnight.qualified_live_snapshot(original) is None
    assert called==[]


def test_overnight_watch_rerules_expired_source_before_model_run(monkeypatch):
    from bot import overnight as watcher, autonomous, settle, derisk
    from data_layer import overnight
    from portfolio import registry, autonomous_migration, paper_account
    source=synthetic(datetime.now(timezone.utc),change=-2.0)
    owner={"valid":True}
    def host(_packet):
        return owner["valid"]
    monkeypatch.setattr(overnight,"_host_live_source_admitted",host)
    monkeypatch.setattr(overnight,"tape",lambda force=False:source)
    monkeypatch.setattr(registry,"is_archived",lambda _pid:False)
    monkeypatch.setattr(autonomous_migration,"is_pending_migration",lambda:False)
    monkeypatch.setattr(settle,"is_open",lambda _pid:False)
    monkeypatch.setattr(paper_account,"preflight_pending_target",
                        lambda _pid:{"ok":True,"pending":True})
    monkeypatch.setattr(derisk,"enabled",lambda:False)
    def revoke_during_prompt(*_args, **_kwargs):
        # Qualifying earlier in the tick cannot authorize later model entry.
        owner["valid"]=False
        return "SYNTHETIC CONFIDENTIAL PROMPT"
    monkeypatch.setattr(watcher,"_overnight_directive",revoke_during_prompt)
    monkeypatch.setattr(autonomous,"run_autonomous",
                        lambda *args,**kwargs:pytest.fail("revoked risk started a model"))
    result=watcher.watch("autonomous","2026-10-15")
    assert result["skipped"]=="tape_unavailable"
    assert "refined" not in result
    assert "error" not in result


@pytest.mark.parametrize("price", [10**400, -7.0])
def test_admitted_public_projection_drops_unusable_optional_prices(monkeypatch, price):
    from data_layer import overnight
    t=verified(monkeypatch)
    t["groups"]["us_futures"][0]["price"]=price
    out=overnight.public_tape(t)
    assert out["live"] is True
    assert out["risk"]["state"]=="stressed"
    assert out["groups"]["us_futures"][0]["price"] is None
    assert out["groups"]["us_futures"][0]["change_pct"]==-2.0


def test_mutating_host_cannot_reclassify_the_verified_input(monkeypatch):
    from data_layer import overnight
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    def untrusted_mutating_verifier(body):
        body["risk"]["state"]="calm"
        return True
    monkeypatch.setattr(overnight,"_host_live_source_admitted",untrusted_mutating_verifier)
    # The host must attest the exact original canonical bytes, not a body
    # altered while a verifier callback is executing.
    assert overnight.qualified_live_snapshot(t) is None


def test_retained_host_verifier_alias_cannot_modify_returned_evidence(monkeypatch):
    from data_layer import overnight
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    stored=[]
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda body: stored.append(body) or True)
    snapshot=overnight.qualified_live_snapshot(t)
    assert snapshot is not None and snapshot["risk"]["state"]=="stressed"
    assert stored[-1] is not snapshot
    stored[-1]["risk"]["state"]="calm"
    stored[-1]["groups"]["us_futures"][0]["change_pct"]=4.0
    assert snapshot["risk"]["state"]=="stressed"
    assert snapshot["groups"]["us_futures"][0]["change_pct"]==-2.0


def test_slow_authentication_cannot_qualify_observation_after_expiry(monkeypatch):
    import time
    from datetime import timedelta
    from data_layer import overnight
    monkeypatch.setattr(overnight,"_TTL",2.0)
    t=synthetic(datetime.now(timezone.utc)-timedelta(seconds=1.5),change=-2.0)
    def slow_positive(_body):
        time.sleep(0.8)
        return True
    monkeypatch.setattr(overnight,"_host_live_source_admitted",slow_positive)
    assert overnight.qualified_live_snapshot(t) is None


def test_shared_exponential_graph_is_rejected_before_json_output_expands(monkeypatch):
    from data_layer import overnight
    t=synthetic(datetime.now(timezone.utc),change=-2.0)
    nested="x"
    for _ in range(18):
        nested=[nested,nested]
    t["private_untrusted_graph"]=nested
    called=[]
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda body: called.append(body) or True)
    # Shared container identities are refused in a bounded pre-traversal;
    # their 2**18 JSON expansion must never be constructed.
    assert overnight._bounded_observation_json(t) is None
    assert overnight.qualified_live_snapshot(t) is None
    assert called==[]

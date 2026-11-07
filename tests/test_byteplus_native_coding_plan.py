"""Original lease, exact credential and provider-enforced quota contract."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest
import yaml

CANDIDATE = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/candidate"
sys.path.insert(0, str(CANDIDATE))
import byteplus_coding_plan as plan
from native_plan_worker import PlanLeaseRefused as BindingRefused


def account(name="plan-one", scope="1" * 64):
    reference = "subscription-" + scope
    return {"name": name, "enabled": True, "per_account_cap": 1,
            "quota_scope": "byteplus:" + reference,
            "coding_plan": {
                "schema": plan.ACCOUNT_SCHEMA, "subscription_ref": reference,
                "binding_id": plan.BINDING_ID, "base_url": plan.BASE_URL,
                "models": sorted(plan.MODELS), "scope": "individual_supported_coding_tools",
                "quota_enforcement": "provider_hard_stop_no_payg",
                "entitlement_source": "chairman_declared_plan", "plan_price_usd_per_month": 50,
                "concurrency_source": "operator_limit_not_provider_entitlement",
                "launcher_sha256": hashlib.sha256(Path(plan.__file__).read_bytes()).hexdigest(),
                "credential_ref": "provider-home:" + name, "provider_home": "/private/provider/" + name,
                "owner_uid": os.getuid(), "owner_gid": os.getgid(), "quota_observation": None,
            }}


def observed(row, percent=20):
    return {"schema": "mastermind.byteplus_personal_plan_readback_projection/v1",
            "subscription_ref": row["coding_plan"]["subscription_ref"],
            "acquisition_source": "authenticated_arkcli", "usage_observed_at_unix": 100,
            "windows": {name: {"used_percent_rounded": percent,
                                "reset_at": None if name == "session" else "2099-01-01T00:00:00+00:00"}
                        for name in ("session", "weekly", "monthly")}}


def test_unknown_quota_does_not_claim_available_or_change_operator_cap():
    row = account()
    bound, quota = plan._closed_account(row, now=100)
    assert quota["state"] == "UNKNOWN"
    assert quota["remaining_requests"] is None
    assert quota["enforced_by"] == "provider"
    assert quota["admission_basis"] == "bounded_attempt_under_provider_enforcement"
    assert row["per_account_cap"] == 1


@pytest.mark.parametrize("window", ["session", "weekly", "monthly"])
def test_each_exhausted_window_holds_same_subscription_even_when_old(window):
    row = account()
    value = observed(row)
    value["windows"][window]["used_percent_rounded"] = 100
    row["coding_plan"]["quota_observation"] = value
    assert not plan.account_eligible(row, now=5000)
    with pytest.raises(plan.BytePlusBindingRefused, match="WINDOW_EXHAUSTED"):
        plan._closed_account(row, now=100)


def test_fresh_rounded_readback_is_not_a_request_count_and_stale_becomes_unknown():
    row = account()
    row["coding_plan"]["quota_observation"] = observed(row)
    assert plan._closed_account(row, now=100)[1]["state"] == "NOT_EXHAUSTED_ROUNDED"
    assert plan._closed_account(row, now=500)[1]["state"] == "UNKNOWN"
    assert plan._closed_account(row, now=100)[1]["windows"]["session"]["reset_at"] is None


@pytest.mark.parametrize("field,value", [
    ("base_url", "https://ark.ap-southeast.bytepluses.com/api/v3"),
    ("launcher_sha256", "0" * 64),
    ("subscription_ref", "key-derived-alias"),
    ("credential_ref", "provider-home:other-account"),
    ("quota_enforcement", "unknown_means_unlimited"),
])
def test_mismatched_enrollment_is_nongrantable(field, value):
    row = account()
    row["coding_plan"][field] = value
    assert plan.account_eligible(row, now=100) is False


def fixture_lease(tmp_path, monkeypatch, *, pool="byteplus", model="deepseek-v4.1-flash", name="plan-one"):
    row = account(name)
    registry = tmp_path / "accounts.yaml"
    registry.write_text(yaml.safe_dump({"schema": "mastermind.provider_accounts.v1", "providers": {
        "byteplus": {"enabled": True, "accounts": [row]}}}))
    monkeypatch.setitem(sys.modules, "lease_broker", SimpleNamespace(DEFAULT_ACCOUNTS=str(registry)))
    db = tmp_path / "leases.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE leases (id TEXT, account TEXT, pool TEXT, model TEXT, orchestrator_id TEXT, state TEXT, last_heartbeat REAL, ttl INT, granted_at REAL, renewable INT, purpose TEXT)")
        conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     ("lease-one", name, pool, model, "root-one", "held", 90, 30, 80, 1, "WORKER"))
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Write a pure addition function.")
    env = {"POOL_ACCOUNT": name, "POOL_LEASE_ID": "lease-one", "POOL_ORCHESTRATOR_ID": "root-one", "POOL_TASK_CLASS": "fix_build",
           "ANTHROPIC_BASE_URL": "https://wrong.invalid", "ANTHROPIC_API_KEY": "wrong-secret",
           "ARK_API_KEY": "wrong-key", "PATH": os.environ["PATH"]}
    return row, registry, db, prompt, env


@pytest.mark.parametrize("model", sorted(plan.MODELS))
def test_supported_cli_uses_only_the_original_leased_account_and_model(tmp_path, monkeypatch, model):
    row, registry, db, prompt, env = fixture_lease(tmp_path, monkeypatch, model=model)
    reads = []
    def credential(home, **owner):
        reads.append((str(home), owner))
        return "fixture-byteplus-secret"
    argv, scoped = plan.launch(str(tmp_path), model, str(prompt), "1", environ=env,
        accounts_path=registry, db_path=db, now=100, credential_loader=credential,
        exec_fn=lambda argv, env: (argv, env))
    assert len(reads) == 1 and reads[0][0].endswith("plan-one")
    assert argv[0] == "claude" and argv[1] == "-p"
    assert "fixture-byteplus-secret" not in argv
    assert scoped["ANTHROPIC_BASE_URL"] == plan.BASE_URL
    assert scoped["ANTHROPIC_AUTH_TOKEN"] == "fixture-byteplus-secret"
    assert scoped["ANTHROPIC_MODEL"] == scoped["CLAUDE_CODE_SUBAGENT_MODEL"] == model
    assert "ANTHROPIC_API_KEY" not in scoped and "ARK_API_KEY" not in scoped
    assert "--max-turns" in argv and argv[argv.index("--max-turns") + 1] == "1"


@pytest.mark.parametrize("field,value", [("POOL_ACCOUNT", "other"), ("POOL_ORCHESTRATOR_ID", "other-root"), ("POOL_LEASE_ID", "other-lease")])
def test_wrong_original_lease_refuses_before_secret_read(tmp_path, monkeypatch, field, value):
    _, registry, db, prompt, env = fixture_lease(tmp_path, monkeypatch)
    env[field] = value
    def no_secret(*args, **kwargs):
        pytest.fail("credential must not be read")
    with pytest.raises(BindingRefused):
        plan.launch(str(tmp_path), "deepseek-v4.1-flash", str(prompt), "1", environ=env,
                    accounts_path=registry, db_path=db, now=100, credential_loader=no_secret,
                    exec_fn=lambda *_: pytest.fail("must not exec"))


def test_glm_lease_cannot_be_reused_for_byteplus(tmp_path, monkeypatch):
    _, registry, db, prompt, env = fixture_lease(tmp_path, monkeypatch, pool="glm")
    with pytest.raises(BindingRefused):
        plan.launch(str(tmp_path), "deepseek-v4.1-flash", str(prompt), "1", environ=env,
                    accounts_path=registry, db_path=db, now=100,
                    credential_loader=lambda *_a, **_kw: pytest.fail("secret read"), exec_fn=lambda *_: None)


def test_two_subscriptions_have_independent_scopes_and_two_models_share_one():
    first, second = account(), account("plan-two", "2" * 64)
    assert first["quota_scope"] != second["quota_scope"]
    assert first["coding_plan"]["models"] == sorted(plan.MODELS)
    assert plan.account_eligible(first, now=100) and plan.account_eligible(second, now=100)


@pytest.mark.parametrize("column,value", [
    ("purpose", "APPLICATION"), ("pool", "experiential"), ("state", "released"),
    ("ttl", 0), ("last_heartbeat", 101), ("model", "glm-5.3-flash"),
    ("orchestrator_id", "other-root"), ("renewable", 3),
])
def test_plan_validator_cannot_borrow_other_custody(tmp_path, monkeypatch, column, value):
    from native_plan_worker import validate_plan_lease
    _, _, db, _, env = fixture_lease(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE leases SET " + column + "=?", (value,))
    with pytest.raises(BindingRefused):
        validate_plan_lease(env, "deepseek-v4.1-flash", expected_pool="byteplus", db_path=db, now=100)

"""Offline cross-repository proof: real parser, selector and transport; fake I/O.

This is not a provider canary, installed worker proof, or permission to pool seats.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os

import pytest
from engine import provider_account_pool as pool
from engine.provider_subscription_usage_opencode import observe_opencode_go_usage
from control_plane import opencode_go_pooled_transport as wire

NOW = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
MEMBERS = ("acct-a", "acct-b", "acct-c")


def iso(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def native_payload(percent=0):
    return {"usage": {
        "rolling": {"status": "ok", "percent": percent, "resetsAt": iso(NOW + timedelta(hours=5))},
        "weekly": {"status": "ok", "percent": 0, "resetsAt": iso(NOW + timedelta(days=6))},
        "monthly": {"status": "ok", "percent": 0, "resetsAt": iso(NOW + timedelta(days=29))},
    }}


class SyntheticProvider:
    """Test-only state, NOT a second production quota/account authority."""
    def __init__(self):
        self.payloads = {name: native_payload(index * 5) for index, name in enumerate(MEMBERS)}
        self.clock = NOW
        self.read_accounts = []

    def snapshot(self):
        rows = []
        for account in MEMBERS:
            def fake_get(url, headers, timeout, account=account):
                assert url == "https://opencode.ai/zen/go/v1/usage"
                assert headers["Authorization"] == "Bearer synthetic-" + account
                self.read_accounts.append(account)
                return deepcopy(self.payloads[account])
            native = observe_opencode_go_usage(
                lambda account=account: "synthetic-" + account,
                http_get=fake_get, observed_at=self.clock,
            )
            rows.append(pool.observation_from_usage_rows(
                account_id=account, state="available", observed_at=native.observed_at,
                stale_after=iso(self.clock + timedelta(minutes=2)), quota_rows=native.quota_rows,
            ))
        return pool.build_snapshot(pool_id="opencode-go", provider="opencode", product="go",
                                   generated_at=iso(self.clock), members=rows)

    def resolve(self, request):
        snapshot = self.snapshot()
        selected = pool.select_account(
            snapshot, sticky_account_id=request.sticky_account_id,
            session_id=request.session_id, excluded_account_ids=request.excluded_account_ids,
            now=iso(self.clock),
        )
        if selected.account_id is None:
            return None
        return wire.AccountChoice(selected.pool_id, selected.pool_generation, selected.account_id)

    def exhaust(self, account):
        self.payloads[account]["usage"]["rolling"].update(status="rate-limited", percent=100)
        return wire.UpstreamResponse(429, {"retry-after": "18000"}, json.dumps({
            "type": "error", "error": {"type": "GoUsageLimitError", "message": "synthetic quota"},
            "metadata": {"workspace": "synthetic-" + account, "limitName": "5 hour"},
        }).encode())


def test_three_turn_native_parser_pool_wire_continuity(tmp_path):
    provider = SyntheticProvider()
    generation = provider.snapshot().generation
    marker = tmp_path / "worktree-marker.txt"
    marker.write_text("alpha-tool-result")
    pid = os.getpid()
    history = [{"role": "user", "content": "Use alpha-tool-result and keep this context."}]
    sent = []
    successes = []
    phase = [0]

    def sender(request):
        sent.append((phase[0], request.account_id, request.body, request.headers["x-opencode-session"]))
        payload = json.loads(request.body)
        assert payload["model"] == "deepseek-v4.1-flash"
        if phase[0] == 1 and request.account_id == "acct-a":
            return provider.exhaust("acct-a")
        if phase[0] == 2 and request.account_id == "acct-b":
            return provider.exhaust("acct-b")
        # This assertion proves request custody, not a real model's reasoning/recall.
        assert "alpha-tool-result" in request.body.decode()
        return wire.UpstreamResponse(200, {"content-type": "application/json"}, b'{"synthetic":true}')

    transport = wire.OpenCodeGoPooledTransport(pool_id="opencode-go", resolver=provider.resolve,
        credential_loader=lambda account: "synthetic-" + account, sender=sender, max_rollovers=2)
    sticky = "acct-a"
    for index in range(3):
        phase[0] = index
        if index:
            history.extend([
                {"role": "assistant", "tool_calls": [{"id": "call-" + str(index), "type": "function",
                    "function": {"name": "read_marker", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call-" + str(index), "content": marker.read_text()},
                {"role": "user", "content": "Continue the same workspace."},
            ])
        body = json.dumps({"model": "deepseek-v4.1-flash", "messages": history}).encode()
        result = transport.execute(wire.ProviderRequest("chat/completions", "Session-Case-Continuity",
            {"Content-Type": "application/json"}, body), sticky_account_id=sticky,
            expected_pool_generation=generation)
        assert result.response.status == 200
        assert result.pool_generation == generation
        assert marker.read_text() == "alpha-tool-result"
        assert os.getpid() == pid
        sticky = result.account_id
        successes.append(sticky)
    assert successes == ["acct-a", "acct-b", "acct-c"]
    assert [entry[1] for entry in sent] == ["acct-a", "acct-a", "acct-b", "acct-b", "acct-c"]
    assert sent[1][2] == sent[2][2] and sent[3][2] == sent[4][2]
    assert {entry[3] for entry in sent} == {"Session-Case-Continuity"}
    assert set(provider.read_accounts) == set(MEMBERS)


def test_real_parser_float_shape_reaches_selector():
    provider = SyntheticProvider()
    provider.payloads["acct-a"] = native_payload(20.25)
    provider.payloads["acct-b"] = native_payload(20.1)
    provider.payloads["acct-c"] = native_payload(50)
    snapshot = provider.snapshot()
    assert snapshot.members[0].five_hour.used_percent == 20.25
    assert pool.select_account(snapshot, now=iso(NOW)).account_id == "acct-b"


def test_missing_weekly_cannot_become_fresh_free_capacity():
    provider = SyntheticProvider()
    del provider.payloads["acct-a"]["usage"]["weekly"]
    snapshot = provider.snapshot()
    assert snapshot.members[0].weekly.used_percent is None
    assert pool.select_account(snapshot, sticky_account_id="acct-a", now=iso(NOW)).account_id == "acct-b"


def test_one_exhausted_window_dominates_inconsistent_percent_and_state():
    provider = SyntheticProvider()
    provider.payloads["acct-a"]["usage"]["weekly"].update(status="rate-limited", percent=37)
    snapshot = provider.snapshot()
    assert snapshot.members[0].state == "cooling"
    assert pool.select_account(snapshot, sticky_account_id="acct-a", now=iso(NOW)).account_id == "acct-b"


def test_reset_is_not_renewal_without_a_new_provider_observation():
    provider = SyntheticProvider()
    provider.exhaust("acct-a")
    first = provider.snapshot()
    provider.clock += timedelta(hours=5, seconds=1)
    assert pool.select_account(first, now=iso(provider.clock)).account_id is None
    # Same stale upstream reset values do not become fresh merely by rewrapping.
    assert pool.select_account(provider.snapshot(), now=iso(provider.clock)).account_id is None
    provider.payloads["acct-a"]["usage"]["rolling"].update(
        status="ok", percent=0, resetsAt=iso(provider.clock + timedelta(hours=5)))
    refreshed = provider.snapshot()
    assert refreshed.generation == first.generation
    assert pool.select_account(refreshed, now=iso(provider.clock)).account_id == "acct-a"


def test_pinned_generation_drift_refuses_before_any_credential_read():
    touched = []
    provider = SyntheticProvider()
    client = wire.OpenCodeGoPooledTransport(pool_id="opencode-go", resolver=provider.resolve,
        credential_loader=lambda account: touched.append(account) or "synthetic",
        sender=lambda request: pytest.fail("must not send"), max_rollovers=2)
    request = wire.ProviderRequest("chat/completions", "Session-1", {}, b'{"model":"test","messages":[]}')
    with pytest.raises(wire.OpenCodeGoTransportContractError, match="generation changed"):
        client.execute(request, expected_pool_generation="f" * 64)
    assert touched == []


def test_all_exhausted_provider_readings_never_reach_inference():
    provider = SyntheticProvider()
    for account in MEMBERS:
        provider.exhaust(account)
    client = wire.OpenCodeGoPooledTransport(pool_id="opencode-go", resolver=provider.resolve,
        credential_loader=lambda account: pytest.fail("must not load inference key"),
        sender=lambda request: pytest.fail("must not send"), max_rollovers=2)
    with pytest.raises(wire.OpenCodeGoPoolUnavailable):
        client.execute(wire.ProviderRequest("chat/completions", "Session-1", {}, b'{"model":"test","messages":[]}'))

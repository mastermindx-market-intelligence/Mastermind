"""V5 advisory quota must not outlive the quota window it describes.

Exact complete quota source, synthetic cache and temporary broker only. No live
account, credential, provider endpoint, host, original denied test or installer.
"""
from __future__ import annotations

import ast
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys

import pytest

from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, FIXTURES, _apply, _module, broker, complete_broker,
)
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests.test_native_fabric_quota_pinned_reclaim_composition import joined_candidate

NOW = 2_000_000_000.0
V5_SECTION_SHA = "b35b466d7a4b19073c19a774e84cb369a7911993e85634ba269379f3add092eb"
V5_POSTIMAGE = "42f3a5f9b4d820ab5fafd9b739944a685dab4ebe254fb9c190f9ab75129ebfab"


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


@pytest.fixture
def advisory_reader(tmp_path, monkeypatch):
    root = tmp_path / "advisory-reset-source"
    ext = root / "ext"
    ext.mkdir(parents=True)
    target = ext / "quota_remote.py"
    shutil.copyfile(FIXTURES / "quota_remote.py.txt", target)
    section = FIXTURES / "advisory_quota_v5_section.patch"
    assert hashlib.sha256(section.read_bytes()).hexdigest() == V5_SECTION_SHA
    _apply(root, section)
    before = target.read_bytes()
    assert hashlib.sha256(before).hexdigest() == V5_POSTIMAGE
    if os.environ.get("FABRIC_ADVISORY_RESET_PREIMAGE") != "1":
        _apply(root, BUNDLE / "quota_reset/advisory_reset_boundary.patch")
    name = "_fabric_advisory_reset_reader_test"
    previous = sys.modules.get(name)
    try:
        value = _module(name, target)
        value._before_reset = before.decode()
        value._after_reset = target.read_text()
        def forbidden(*args, **kwargs):
            raise AssertionError("advisory reset test attempted provider/credential/write I/O")
        for attribute in ("_live_glm", "_json_get", "_glm_key", "_minimax_key", "_glm_accounts_dict", "_atomic_write"):
            monkeypatch.setattr(value, attribute, forbidden)
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(socket, "create_connection", forbidden)
        # Keep canonical READERS identity so this remains the real multi-account
        # path, rather than inadvertently switching to the legacy test branch.
        assert not value._legacy_glm_mode()
        yield value
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def state(reader, *, window="weekly", reset=NOW + 3600, observed=NOW - 30,
          remaining=2.0, provider="glm"):
    return reader.ProviderQuotaState(provider=provider, window=window, used=100 - remaining,
        cap=100.0, remaining_pct=remaining, reset_at=stamp(reset) if isinstance(reset, (int, float)) else reset,
        source="PROVIDER_AUTHORITATIVE", observed_at=stamp(observed), confidence=1.0,
        detail="synthetic quota-window boundary")


def cache_for(reader, tmp_path, monkeypatch, *, reset=NOW + 3600,
              observed=NOW - 30, remaining=2.0, short_reset=None, refreshed=NOW - 1):
    short_reset = reset if short_reset is None else short_reset
    rows = [asdict(state(reader, window="5h", reset=short_reset, observed=observed, remaining=remaining)),
            asdict(state(reader, reset=reset, observed=observed, remaining=remaining))]
    cache = tmp_path / "synthetic-advisory-cache.json"
    cache.write_text(json.dumps({
        "glm": {"accounts": {"enrolled": {"refreshed_at": refreshed, "states": rows}}},
        "minimax": {"refreshed_at": refreshed, "states": [{**row, "provider": "minimax"} for row in rows]},
    }))
    monkeypatch.setattr(reader, "_glm_accounts_dict", lambda: {"enrolled": {}})
    monkeypatch.setattr(reader, "CACHE_PATH", str(cache))
    return cache


@pytest.mark.parametrize("reset", [NOW - 1, NOW, "not-a-date", ""])
def test_expired_or_malformed_reset_cannot_be_authoritative(advisory_reader, reset):
    row = state(advisory_reader, reset=reset)
    assert advisory_reader._advisory_fresh_states([row], NOW) == []


@pytest.mark.parametrize("provider", ["glm", "minimax"])
@pytest.mark.parametrize("reset", [NOW - 1, NOW])
def test_cache_only_reader_drops_previous_window_without_refresh(advisory_reader, tmp_path, monkeypatch, provider, reset):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=reset)
    before = cache.read_bytes()
    answer = advisory_reader.read_provider(provider, now_ts=NOW, cache_path=str(cache), allow_remote=False)
    assert answer == []
    assert cache.read_bytes() == before


@pytest.mark.parametrize("reset", [NOW - 1, NOW])
def test_advisory_cannot_park_after_account_admission_hold_expires(advisory_reader, tmp_path, monkeypatch, reset):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=reset)
    before = cache.read_bytes()
    assert advisory_reader.cached_glm_account_parked("enrolled", now_ts=NOW, cache_path=str(cache)) is False
    decision = advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)
    assert decision["state"] == "UNKNOWN", decision
    assert decision["source"] == "UNKNOWN"
    assert cache.read_bytes() == before


def test_expired_short_window_prevents_invented_complete_pool_observation(advisory_reader, tmp_path, monkeypatch):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, short_reset=NOW - 1, remaining=80)
    decision = advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)
    assert decision["state"] == "UNKNOWN", decision
    rows = advisory_reader.glm_accounts_state(now_ts=NOW, cache_path=str(cache), allow_remote=False)
    assert [row.window for row in rows[0]["states"]] == ["weekly"]


@pytest.mark.parametrize("remaining,expected", [(2.0, "PARKED"), (80.0, "OK")])
def test_fresh_unexpired_quota_keeps_actual_decision(advisory_reader, tmp_path, monkeypatch, remaining, expected):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, remaining=remaining)
    decision = advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)
    assert decision["state"] == expected
    assert decision["source"] == "PROVIDER_AUTHORITATIVE"
    assert advisory_reader.cached_glm_account_parked("enrolled", now_ts=NOW, cache_path=str(cache)) is (remaining <= 5)


def test_absent_reset_retains_existing_observation_contract(advisory_reader, tmp_path, monkeypatch):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=None)
    assert len(advisory_reader.read_provider("glm", now_ts=NOW, cache_path=str(cache), allow_remote=False)) == 2
    assert advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)["state"] == "PARKED"


@pytest.mark.parametrize("observed", [NOW - 601, NOW + 1])
def test_stale_and_future_measurements_remain_unknown(advisory_reader, tmp_path, monkeypatch, observed):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, observed=observed)
    assert advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)["state"] == "UNKNOWN"


@pytest.mark.parametrize("refreshed", [NOW - 301, NOW + 1])
def test_stale_and_future_cache_timestamps_remain_unknown(advisory_reader, tmp_path, monkeypatch, refreshed):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, refreshed=refreshed)
    assert advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)["state"] == "UNKNOWN"


def test_explicit_reader_mode_is_not_changed_by_advisory_fix(advisory_reader, tmp_path, monkeypatch):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=NOW - 1)
    original = cache.read_bytes()
    # The existing non-advisory reader may still return its cached historical
    # observation. This repair does not silently change explicit refresh law.
    assert len(advisory_reader.read_provider("glm", now_ts=NOW, cache_path=str(cache), allow_remote=True)) == 2
    assert cache.read_bytes() == original


def test_expired_window_local_fallback_never_claims_provider_authority(advisory_reader, tmp_path, monkeypatch):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=NOW - 1)
    answer = advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False,
        local_estimate={"state": "FILL", "confidence": 0.7})
    assert answer["state"] == "FILL" and answer["source"] == "LOCAL_RECONSTRUCTION"


def test_reset_expiry_does_not_override_other_accounts_current_exhaustion(advisory_reader, tmp_path, monkeypatch):
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=NOW - 1)
    doc = json.loads(cache.read_text())
    doc["glm"]["accounts"]["other"] = {"refreshed_at": NOW - 1, "states": [
        asdict(state(advisory_reader, window="5h")), asdict(state(advisory_reader))]}
    cache.write_text(json.dumps(doc))
    monkeypatch.setattr(advisory_reader, "_glm_accounts_dict", lambda: {"enrolled": {}, "other": {}})
    assert advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)["state"] == "UNKNOWN"
    assert advisory_reader.cached_glm_account_parked("other", now_ts=NOW, cache_path=str(cache)) is True


@pytest.mark.parametrize("reset,remaining,eligible", [(NOW - 1, 2.0, True), (NOW + 3600, 2.0, False), (NOW + 3600, 80.0, True)])
def test_same_complete_reader_serves_composed_broker_and_advisory(joined_candidate, advisory_reader, tmp_path, monkeypatch, reset, remaining, eligible):
    import yaml
    module, _old_reader = joined_candidate
    monkeypatch.setitem(sys.modules, "quota_remote", advisory_reader)
    cache = cache_for(advisory_reader, tmp_path, monkeypatch, reset=reset, remaining=remaining)
    br, _ = broker(module, tmp_path)
    Path(br.accounts_path).write_text(yaml.safe_dump({"providers": {"glm": {
        "enabled": True, "accounts": [{"name": "enrolled", "per_account_cap": 3,
                                        "per_model_caps": {"glm-5.3": 2}}]}}}))
    br.external_gates = True
    assert bool(br.grantable_accounts("glm")) is eligible
    with br._conn() as conn:
        assert len(br._active_leases(conn)) == 0
    answer = advisory_reader.glm_quota_decision(now_ts=NOW, cache_path=str(cache), allow_remote=False)
    assert answer["state"] == ("UNKNOWN" if reset <= NOW else "PARKED" if remaining <= 5 else "OK")


def test_only_advisory_window_filter_changes(advisory_reader):
    def funcs(source):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(source).body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    before, after = funcs(advisory_reader._before_reset), funcs(advisory_reader._after_reset)
    assert before.keys() == after.keys()
    assert {name for name in before if before[name] != after[name]} == {"_advisory_fresh_states"}
    assert before["cached_glm_account_parked"] == after["cached_glm_account_parked"]

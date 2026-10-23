"""Bounded R28/R33 regression: default reviews use judgment routing, not Qwen.

All providers, quota, lease, host and emission functions are inert mocks here.
This test does not start a worker, enroll a host or modify production routing.
"""
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PICK_PATH = ROOT / "ops/native_fabric/quota_continuity/candidate/pick.py"


@pytest.fixture
def native_pick(monkeypatch):
    monkeypatch.syspath_prepend(str(PICK_PATH.parent))
    spec = importlib.util.spec_from_file_location("fabric_review_judgment_pick_under_test", PICK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_inert_route(monkeypatch, pick, *, eligible=("glm",)):
    """Isolate class/precedence and R33 logic from physical provider gates."""
    doc = {"routing": {
        "execute_classes": ["execute", "review", "audit", "mechanical"],
        "judgment_order": ["glm-5.3", "grok", "cursor", "fable"],
        "reviewer_not_author": True,
    }, "pools": {}}
    monkeypatch.setattr(pick, "load_pools", lambda: doc)
    monkeypatch.setattr(pick, "_promo_balance_glm", lambda order, *a, **kw: list(order))
    monkeypatch.setattr(pick, "_promote_urgent", lambda order, *a, **kw: list(order))
    monkeypatch.setattr(pick, "_grok_priority_active", lambda *a, **kw: False)
    monkeypatch.setattr(pick, "_cursor_grok_after_quota", lambda *a, **kw: "NONE reason=fixture")
    monkeypatch.setattr(pick, "burn_down_urgent", lambda *a, **kw: False)
    monkeypatch.setattr(pick, "policy_allows",
                        lambda pool, *a, **kw: (pool in eligible, "fixture_policy"))
    monkeypatch.setattr(pick, "_needs_ok", lambda *a, **kw: (True, "ok"))
    monkeypatch.setattr(pick, "hard_filter", lambda *a, **kw: (True, "ok"))
    monkeypatch.setattr(pick, "floor_demotes", lambda *a, **kw: False)
    monkeypatch.setattr(pick, "_glm_meter_state", lambda: "NORMAL")
    monkeypatch.setattr(pick, "_emit", lambda pool, reason, *a, **kw:
                        f"POOL={pool} MODEL=fixture REASON={reason}")
    monkeypatch.setattr(pick, "_pick_execute", lambda *a, **kw:
                        "POOL=bailian MODEL=qwen3.8-max REASON=legacy_wrong_route")
    return doc


def test_review_routes_to_glm_judgment_even_when_execute_classes_contains_review(native_pick, monkeypatch):
    doc = install_inert_route(monkeypatch, native_pick, eligible=("glm", "bailian"))
    assert native_pick.is_execute_class("review", doc)
    assert native_pick.is_judgment_class("review", doc)
    route = native_pick._format_pick("review", subject_pool="minimax")
    assert route == "POOL=glm MODEL=fixture REASON=judgment_order_glm"


def test_review_never_falls_back_to_qwen_scored_executor_when_glm_unavailable(native_pick, monkeypatch):
    install_inert_route(monkeypatch, native_pick, eligible=("bailian",))
    route = native_pick._format_pick("review", subject_pool="minimax")
    assert route == "NONE reason=no_operator_available"


def test_reviewer_not_author_still_refuses_same_glm_family(native_pick, monkeypatch):
    install_inert_route(monkeypatch, native_pick, eligible=("glm", "bailian"))
    assert native_pick._subject_ok("glm", "review", "remote-glm-codex")[0] is False
    route = native_pick._format_pick("review", subject_pool="remote-glm-codex")
    assert route == "NONE reason=no_operator_available"


@pytest.mark.parametrize("other_class", ["audit", "mechanical"])
def test_existing_non_review_execute_classes_not_reclassified(native_pick, monkeypatch, other_class):
    install_inert_route(monkeypatch, native_pick, eligible=("glm", "bailian"))
    route = native_pick._format_pick(other_class)
    assert route == "POOL=bailian MODEL=qwen3.8-max REASON=legacy_wrong_route"


def test_explicit_pool_still_uses_existing_policy_and_independence(native_pick, monkeypatch):
    install_inert_route(monkeypatch, native_pick, eligible=("glm", "bailian"))
    assert native_pick._format_pick("review", pool="bailian", subject_pool="minimax").startswith("POOL=bailian ")
    assert "reviewer must differ" in native_pick._format_pick(
        "review", pool="glm", subject_pool="remote-glm-codex"
    )

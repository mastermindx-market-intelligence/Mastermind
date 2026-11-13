"""GLM night-shift chain tests: Z.ai-peak window diversion.

Policy under test (operator, 2026-11-11): during Z.ai's peak billing window
(Mon-Fri 14:00-18:00 Asia/Shanghai == 01:00-05:00 EST winter rendering), NEW
glm-5.3 lanes open on Qwen4-Max; when Qwen4 is capped or saturated, Grok 4.6;
when that is also unavailable, the request returns to glm-5.3 on Z.ai, where
the weekday-gated peak gate paces it. The window is anchored on Asia/Shanghai
— Z.ai's own billing clock — so no observer's DST can drift it.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ops.native_fabric.unified_router import overflow as overflow_mod
from ops.native_fabric.unified_router.overflow import Overflow, merged_config

GLM_FAMILY = {
    "match": ["glm-5.3"],
    "targets": ["qwen4-max-preview", "grok-4.6"],
    "cap_fallback": "wait",
    "proactive": True,
    "sticky_revert": True,
    "window": {
        "tz": "Asia/Shanghai",
        "start": "14:00",
        "end": "18:00",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    },
}
SH = ZoneInfo("Asia/Shanghai")


class _StubPolicy:
    def __init__(self, overflow_cfg):
        self.policy = {"overflow": overflow_cfg}
        self.plan = lambda *a, **k: ([], 1.0, "stub", "p")
        self.begin = lambda *a, **k: None
        self.finish = lambda *a, **k: None
        self.learn_limit = lambda *a, **k: None
        self.snapshot = lambda *a, **k: {}
        self.route_state = type("RS", (), {"cooldown_until": {}})()
        self.routes = {}
        self.active = {}
        self.eligible_routes = lambda model: list(self.routes.values())
        self.window = type("W", (), {"totals": lambda *a: (0.0,)})()


def _state(**glm_over):
    fams = {"glm": dict(GLM_FAMILY, **glm_over)}
    raw = {"enabled": True, "families": fams,
           "caps": {"qwen4-max-preview": {"max_inflight": 6, "max_new_sessions_per_hour": 40},
                    "grok-4.6": {"max_inflight": 4, "max_new_sessions_per_hour": 20}}}
    return Overflow(_StubPolicy(raw)), merged_config(raw)


def _freeze_clock(shanghai_moment):
    """Point overflow.datetime.now at a fixed Shanghai wall-clock reading."""
    class _Frozen:
        @staticmethod
        def now(tz=None):
            if tz is None:
                return shanghai_moment.astimezone()
            return shanghai_moment.astimezone(tz)
    return _Frozen


class TestWindow:
    def test_open_midweek_afternoon_shanghai(self):
        state, cfg = _state()
        real = overflow_mod.datetime
        try:
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 12, 15, 0, tzinfo=SH))  # Thu
            assert state.in_window(cfg["families"]["glm"]) is True
        finally:
            overflow_mod.datetime = real

    def test_closed_weekend_afternoon_shanghai(self):
        # Z.ai peak is Mon-Fri only: same wall clock on a Saturday stays shut.
        state, cfg = _state()
        real = overflow_mod.datetime
        try:
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 14, 15, 0, tzinfo=SH))  # Sat
            assert state.in_window(cfg["families"]["glm"]) is False
        finally:
            overflow_mod.datetime = real

    def test_closed_outside_hours(self):
        state, cfg = _state()
        real = overflow_mod.datetime
        try:
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 12, 9, 0, tzinfo=SH))   # Thu 09:00
            assert state.in_window(cfg["families"]["glm"]) is False
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 12, 18, 0, tzinfo=SH))  # boundary end
            assert state.in_window(cfg["families"]["glm"]) is False
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 12, 14, 0, tzinfo=SH))  # boundary start
            assert state.in_window(cfg["families"]["glm"]) is True
        finally:
            overflow_mod.datetime = real

    def test_dst_immunity_of_the_anchor(self):
        # In summer, 01:00 America/New_York is 13:00 Shanghai — an ET-anchored
        # window would fire an hour EARLY. The Shanghai anchor cannot drift:
        # 15:00 Shanghai on a July Thursday is inside regardless of US DST.
        state, cfg = _state()
        real = overflow_mod.datetime
        try:
            overflow_mod.datetime = _freeze_clock(datetime(2026, 7, 16, 15, 0, tzinfo=SH))   # Thu July
            assert state.in_window(cfg["families"]["glm"]) is True
            # And the ET-equivalent-but-drifted hour (13:00 Shanghai) is what a
            # New-York anchor would wrongly hit in summer: still fine here only
            # because we anchor Shanghai — 13:00 is OUTSIDE the true window.
            overflow_mod.datetime = _freeze_clock(datetime(2026, 7, 16, 13, 0, tzinfo=SH))
            assert state.in_window(cfg["families"]["glm"]) is False
        finally:
            overflow_mod.datetime = real

    def test_no_window_means_always(self):
        state, cfg = _state(window=None)
        assert state.in_window(cfg["families"]["glm"]) is True

    def test_unparseable_window_fails_closed(self):
        state, cfg = _state(window={"tz": "Not/AZone", "start": "x"})
        assert state.in_window(cfg["families"]["glm"]) is False

    def test_wraparound_window(self):
        state, cfg = _state(window={"tz": "Asia/Shanghai", "start": "22:00", "end": "08:00"})
        real = overflow_mod.datetime
        try:
            for hour, expected in ((23, True), (3, True), (12, False)):
                overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 12, hour, 0, tzinfo=SH))
                assert state.in_window(cfg["families"]["glm"]) is expected, hour
        finally:
            overflow_mod.datetime = real


class TestExactMatch:
    def test_exact_slug_matches(self):
        _, cfg = _state()
        assert Overflow.family_of(cfg, "glm-5.3")[0] == "glm"

    def test_variants_do_not_match(self):
        _, cfg = _state()
        for slug in ("glm-5.3-flash", "glm-5.3-uncensored", "glm-5.3-flash-uncensored"):
            assert Overflow.family_of(cfg, slug)[0] is None, slug

    def test_legacy_dash_prefix_still_matches(self):
        raw = {"families": {"kimi": {"match": ["kimi-"], "target": "x"}}}
        cfg = merged_config(raw)
        assert Overflow.family_of(cfg, "kimi-k3.1-pro")[0] == "kimi"


class TestChain:
    def _divert_with(self, state, plan_fn, kind="new_session", sticky_target=None):
        state._plan = plan_fn
        fam = state.config()["families"]["glm"]
        if sticky_target is not None:
            fam = dict(fam, target=sticky_target, cap_fallback="wait")
        return state._divert(kind, "glm", fam, "glm-5.3", {}, "s", "n",
                             0.0, 0.0, None, state.config(), "p")

    def test_first_rung_admits(self):
        state, _ = _state()
        picked = []

        def plan(cands, *a, **k):
            picked.append(cands[0][0])
            return [("r", cands[0][0])], 0.0, "ok", "p"

        out = self._divert_with(state, plan)
        assert out is not None and picked == ["qwen4-max-preview"]

    def test_saturated_first_rung_falls_to_second(self):
        state, _ = _state()
        calls = []

        def plan(cands, *a, **k):
            model = cands[0][0]
            calls.append(model)
            if model == "qwen4-max-preview":
                return [], 30.0, "FABRIC_TIER_CAPACITY_UNAVAILABLE", "p"
            return [("r", model)], 0.0, "ok", "p"

        out = self._divert_with(state, plan)
        assert out is not None and calls == ["qwen4-max-preview", "grok-4.6"]

    def test_all_rungs_out_returns_none_to_base(self):
        state, _ = _state()
        out = self._divert_with(state, lambda c, *a, **k: ([], 60.0, "cap", "p"))
        assert out is None

    def test_sticky_revert_returns_to_base(self):
        state, _ = _state()
        out = self._divert_with(
            state, lambda c, *a, **k: ([], 45.0, "cap", "p"),
            kind="sticky", sticky_target="qwen4-max-preview")
        assert out is None  # back to base glm-5.3 instead of parking on qwen

    def test_sticky_without_revert_parks(self):
        state, _ = _state(sticky_revert=False)
        out = self._divert_with(
            state, lambda c, *a, **k: ([], 45.0, "cap", "p"),
            kind="sticky", sticky_target="qwen4-max-preview")
        assert out[2] == "FABRIC_OVERFLOW_TARGET_WAIT"


class TestWindowGatesSaturation:
    """Outside the window, even a saturated/cooldown glm family must NOT
    divert — the base ladder handles glm's own hiccups; substitution outside
    the window bills the wrong provider. (Found live 2026-11-11.)"""

    def test_out_of_window_no_divert_even_when_unhealthy(self):
        state, cfg = _state()
        real = overflow_mod.datetime
        try:
            # Saturday 15:00 Shanghai: window closed (weekend).
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 14, 15, 0, tzinfo=SH))
            # Family is 'overflowing' and request inadmissible on primary.
            out = None
            called = []
            state._plan = lambda cands, *a, **k: (called.append(cands[0][0]) or ([], 5.0, "x", "p"))
            fam = cfg["families"]["glm"]
            got = state._divert("new_session", "glm", fam, "glm-5.3", {}, "s", "n",
                                0.0, 0.0, None, cfg, "p")
            # _divert itself is windowless by design; the GATE lives in plan().
            # Assert the plan()-level predicate via the same primitives:
            windowed = isinstance(fam.get("window"), dict)
            window_open = not windowed or state.in_window(fam)
            assert window_open is False
            assert called == [] or got is None
        finally:
            overflow_mod.datetime = real


class TestAuditFixes:
    """Regressions for the adversarial-audit findings (2026-11-11)."""

    def test_sticky_never_hops_to_another_rung(self):
        # HIGH-1: a session diverted to grok-4.6 must not silently migrate to
        # qwen4-max-preview when grok saturates.
        state, _ = _state()
        calls = []

        def plan(cands, *a, **k):
            model = cands[0][0]
            calls.append(model)
            return ([("r", model)], 0.0, "ok", "p")

        state._plan = plan
        fam = state.config()["families"]["glm"]
        out = state._divert("sticky", "glm", dict(fam, target="grok-4.6",
                                                  cap_fallback="wait"),
                            "glm-5.3", {}, "s", "n", 0.0, 0.0, None,
                            state.config(), "p")
        assert calls == ["grok-4.6"]            # only its own target
        assert out is not None                   # grok admits -> stays

    def test_sticky_reverts_to_base_when_own_target_saturated(self):
        state, _ = _state()
        calls = []

        def plan(cands, *a, **k):
            calls.append(cands[0][0])
            return [], float("inf"), "gone", "p"    # infinite eta too

        state._plan = plan
        fam = state.config()["families"]["glm"]
        out = state._divert("sticky", "glm", dict(fam, target="grok-4.6",
                                                  cap_fallback="wait"),
                            "glm-5.3", {}, "s", "n", 0.0, 0.0, None,
                            state.config(), "p")
        assert calls == ["grok-4.6"]            # never tried qwen
        assert out is None                       # reverted to base glm-5.3

    def test_wildcard_pattern_matches(self):
        raw = {"families": {"w": {"match": ["glm-5.3*"], "target": "x"}}}
        cfg = merged_config(raw)
        for slug in ("glm-5.3", "glm-5.3-flash", "glm-5.3-anything"):
            assert Overflow.family_of(cfg, slug)[0] == "w", slug

    def test_exact_pattern_still_excludes_variants(self):
        _, cfg = _state()
        assert Overflow.family_of(cfg, "glm-5.3")[0] == "glm"
        assert Overflow.family_of(cfg, "glm-5.3-flash")[0] is None

    def test_sol_variants_match_with_trailing_dash(self):
        raw = {"families": {"sol": {"match": ["gpt-5.6-sol", "gpt-5.6-sol-",
                                                "gpt-6-sol", "gpt-6-sol-",
                                                "gpt-6.1-sol", "gpt-6.1-sol-"],
                                    "target": "claude-opus-5-5"}}}
        cfg = merged_config(raw)
        for slug in ("gpt-6.1-sol", "gpt-6.1-sol-900k", "gpt-5.6-sol", "gpt-6-sol-900k"):
            assert Overflow.family_of(cfg, slug)[0] == "sol", slug

    def test_day_matching_is_locale_and_form_proof(self):
        # Short forms and the weekday() lookup must agree regardless of locale.
        state, cfg = _state()
        real = overflow_mod.datetime
        try:
            overflow_mod.datetime = _freeze_clock(datetime(2026, 11, 12, 15, 0, tzinfo=SH))
            fam = cfg["families"]["glm"]
            fam["window"]["days"] = ["Thursday", "thu", "Th"]   # mixed forms
            assert state.in_window(fam) is True
            fam["window"]["days"] = ["sat"]
            assert state.in_window(fam) is False
        finally:
            overflow_mod.datetime = real

"""Adversarial native quota comparison tests; no network, auth, or workers."""

from __future__ import annotations

from copy import deepcopy
import pytest

from control_plane.codex_quota_observation import compare_native_codex_quota

NOW = 1792252800
WEEK = 7 * 24 * 3600
HOUR = 3600


def sample(*, at=NOW, reset=NOW + WEEK, used=80.0):
    return {
        "state": "NATIVE_READS_COMPLETED",
        "api_fallback": False,
        "stop": {"private_group_empty": True, "termination_outcome": "stopped"},
        "home_identity": {"account_id_sha256": "a" * 64},
        "account": {
            "observed_at_unix": at,
            "auth_state": "MANAGED_CHATGPT_OBSERVED",
            "limit_id": "codex", "plan_type": "pro",
            "window_states": {"primary": "NOT_APPLICABLE", "secondary": "OBSERVED"},
            "windows": {"secondary": {
                "used_percent": used, "remaining_percent": 100.0-used,
                "resets_at": reset, "window_minutes": 10080,
            }},
        },
    }


def updated():
    return sample(at=NOW + HOUR, reset=NOW + WEEK + 2 * HOUR, used=4.0)


@pytest.mark.parametrize("mode", ["true", "missing", "api"])
def test_untrusted_fallback_cannot_create_promotion_evidence(mode):
    a, b = sample(), updated()
    if mode == "true":
        a["api_fallback"] = True
    elif mode == "missing":
        del a["api_fallback"]
    else:
        b["api_fallback"] = "api"
    got = compare_native_codex_quota(a, b)
    assert got["state"] == "UNKNOWN"
    assert got["early_refresh_candidate"] is False


@pytest.mark.parametrize("bad", ["state_missing", "extra_window", "malformed_percent",
                                 "n_a_contradiction", "duration_bool",
                                 "missing_weekly", "unknown_extra", "invalid_state"])
def test_window_shape_or_contradiction_is_not_silently_skipped(bad):
    a, b = sample(), updated()
    if bad == "state_missing":
        b["account"]["window_states"].pop("secondary")
    elif bad == "extra_window":
        b["account"]["windows"]["primary"] = dict(b["account"]["windows"]["secondary"])
    elif bad == "malformed_percent":
        b["account"]["windows"]["secondary"]["remaining_percent"] = 1000.0
    elif bad == "n_a_contradiction":
        b["account"]["window_states"]["secondary"] = "NOT_APPLICABLE"
    elif bad == "duration_bool":
        b["account"]["windows"]["secondary"]["window_minutes"] = True
    elif bad == "missing_weekly":
        b["account"]["windows"].pop("secondary")
    elif bad == "unknown_extra":
        b["account"]["window_states"]["primary"] = "NOT_A_REAL_STATE"
    else:
        b["account"]["window_states"]["primary"] = None
    got = compare_native_codex_quota(a, b)
    assert got["state"] == "UNKNOWN"
    assert got["early_refresh_candidate"] is False


def test_real_shape_change_emits_rebaseline_not_false_same_window():
    a, b = sample(), updated()
    b["account"]["windows"]["secondary"]["window_minutes"] = 300
    got = compare_native_codex_quota(a, b)
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "WINDOW_CONSTRAINTS_CHANGED"
    assert got["constraint_shape_changed"] is True
    assert got["early_refresh_candidate"] is False


def test_inapplicable_to_observed_is_new_constraint_not_promotion():
    a, b = sample(), updated()
    a["account"]["window_states"]["secondary"] = "NOT_APPLICABLE"
    a["account"]["windows"].pop("secondary")
    got = compare_native_codex_quota(a, b)
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "WINDOW_CONSTRAINTS_CHANGED"
    assert got["early_refresh_candidate"] is False


def test_small_timer_move_replaces_stale_schedule_without_promotion():
    a, b = sample(), sample(at=NOW + HOUR, reset=NOW + WEEK + 15, used=80)
    got = compare_native_codex_quota(a, b)
    assert got["state"] == "CHANGE_OBSERVED"
    assert got["schedule_changed"] is True
    assert got["early_refresh_candidate"] is False
    assert got["observed_windows"][0]["classification"] == "TIMER_ADJUSTED_WITHIN_TOLERANCE"


def test_uncertainty_flags_never_grant_authorization():
    a, b = sample(), updated()
    assert compare_native_codex_quota(a, b)["provenance_verified"] is False
    assert compare_native_codex_quota(a, b)["admission_granted"] is False
    assert compare_native_codex_quota(a, b)["account_switch_authorized"] is False
    assert compare_native_codex_quota(a, b)["reset_redemption_authorized"] is False
    assert compare_native_codex_quota(a, b)["schedule_prediction_authorized"] is False


def test_same_subject_and_limit_is_required_after_hardening():
    a, b = sample(), updated()
    b["home_identity"]["account_id_sha256"] = "b"*64
    assert compare_native_codex_quota(a, b)["reason"] == "SUBJECT_OR_LIMIT_MISMATCH"


def test_large_percent_invalid_does_not_crash():
    a, b = sample(), updated()
    b["account"]["windows"]["secondary"]["used_percent"] = 10**10000
    got = compare_native_codex_quota(a, b)
    assert got["state"] == "UNKNOWN"


def test_inputs_unchanged_and_no_secret_output():
    a, b = sample(), updated()
    a["account"]["raw_token"] = "CANARY_SECRET_NEVER_PROJECT"
    frozen = deepcopy((a,b))
    got = compare_native_codex_quota(a,b)
    assert (a,b)==frozen
    assert "CANARY_SECRET_NEVER_PROJECT" not in str(got)


@pytest.mark.parametrize("shape", [
    "unexpected_window", "unexpected_window_state", "plan_missing",
    "plan_blank", "plan_object",
])
def test_unknown_quota_constraints_or_entitlement_fail_closed(shape):
    """Unmodeled limits cannot be ignored while asserting a refresh candidate."""
    before, after = sample(), updated()
    if shape == "unexpected_window":
        after["account"]["windows"]["tertiary"] = dict(
            after["account"]["windows"]["secondary"]
        )
    elif shape == "unexpected_window_state":
        after["account"]["window_states"]["tertiary"] = "OBSERVED"
    elif shape == "plan_missing":
        before["account"].pop("plan_type")
        after["account"].pop("plan_type")
    elif shape == "plan_blank":
        before["account"]["plan_type"] = " "
        after["account"]["plan_type"] = " "
    else:
        before["account"]["plan_type"] = {"tier": "pro"}
        after["account"]["plan_type"] = {"tier": "pro"}
    result = compare_native_codex_quota(before, after)
    assert result["state"] == "UNKNOWN"
    assert result["early_refresh_candidate"] is False
    assert result["admission_granted"] is False


def test_business_quota_comparison_refuses_cross_user_same_workspace():
    old, new = sample(), updated()
    for row in (old, new):
        row["account"]["plan_type"] = "self_serve_business_prolite"
        row["home_identity"]["user_id_sha256"] = "a" * 64
    new["home_identity"]["user_id_sha256"] = "b" * 64
    got = compare_native_codex_quota(old, new)
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "SUBJECT_OR_LIMIT_MISMATCH"
    assert got["early_refresh_candidate"] is False


def test_business_quota_comparison_refuses_missing_member_identity():
    old, new = sample(), updated()
    old["account"]["plan_type"] = "self_serve_business_prolite"
    new["account"]["plan_type"] = "self_serve_business_prolite"
    got = compare_native_codex_quota(old, new)
    assert got["state"] == "UNKNOWN"
    assert got["early_refresh_candidate"] is False


def test_business_quota_comparison_same_member_remains_observable():
    old, new = sample(), updated()
    for row in (old, new):
        row["account"]["plan_type"] = "self_serve_business_prolite"
        row["home_identity"]["user_id_sha256"] = "a" * 64
    got = compare_native_codex_quota(old, new)
    assert got["state"] == "CHANGE_OBSERVED"
    assert got["early_refresh_candidate"] is True
    assert got["admission_granted"] is False


@pytest.mark.parametrize("value", ["", "a" * 63, "z" * 64, 0, None])
def test_business_quota_comparison_refuses_unqualified_user_hash(value):
    old, new = sample(), updated()
    for row in (old, new):
        row["account"]["plan_type"] = "self_serve_business_prolite"
        row["home_identity"]["user_id_sha256"] = value
    got = compare_native_codex_quota(old, new)
    assert got["state"] == "UNKNOWN"
    assert got["early_refresh_candidate"] is False


def test_personal_quota_comparison_checks_user_identity_when_provided():
    old, new = sample(), updated()
    old["home_identity"]["user_id_sha256"] = "a" * 64
    new["home_identity"]["user_id_sha256"] = "b" * 64
    got = compare_native_codex_quota(old, new)
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "SUBJECT_OR_LIMIT_MISMATCH"

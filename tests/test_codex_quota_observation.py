"""Provider-free, account-bound evidence tests: no quota API or worker calls."""

from __future__ import annotations

from copy import deepcopy

import pytest

from control_plane.codex_quota_observation import compare_native_codex_quota

T = 1792252800
HOUR = 3600
WEEK = 7 * 24 * HOUR


def probe(*, at=T, subject="a" * 64, weekly_reset=T + WEEK,
          used=50.0, weekly=True, primary=None, state="NATIVE_READS_COMPLETED"):
    windows = {}
    states = {"primary": "NOT_APPLICABLE", "secondary": "NOT_APPLICABLE"}
    if primary is not None:
        windows["primary"] = {
            "used_percent": primary,
            "remaining_percent": 100 - primary,
            "resets_at": int(at + 5 * HOUR),
            "window_minutes": 300,
        }
        states["primary"] = "OBSERVED"
    if weekly:
        windows["secondary"] = {
            "used_percent": used,
            "remaining_percent": 100 - used,
            "resets_at": int(weekly_reset),
            "window_minutes": 10080,
        }
        states["secondary"] = "OBSERVED"
    return {
        "state": state,
        "api_fallback": False,
        "stop": {"private_group_empty": True, "termination_outcome": "stopped"},
        "home_identity": {"account_id_sha256": subject, "ignored": "secret-do-not-copy"},
        "account": {
            "observed_at_unix": at, "auth_state": "MANAGED_CHATGPT_OBSERVED",
            "limit_id": "codex", "plan_type": "pro",
            "windows": windows, "window_states": states,
            "arbitrary_provider_text": "access_token=must-never-escape",
        },
    }


def test_unexpected_early_reset_is_candidate_only_and_does_not_admit():
    before = probe(used=84)
    after = probe(at=T + HOUR, weekly_reset=T + WEEK + 5 * HOUR, used=1)
    frozen = deepcopy((before, after))
    result = compare_native_codex_quota(before, after)
    assert (before, after) == frozen
    assert result["state"] == "CHANGE_OBSERVED"
    assert result["early_refresh_candidate"] is True
    assert result["observed_windows"][0]["classification"] == "EARLY_REFRESH_CANDIDATE"
    assert result["schedule_changed"] is True
    assert result["provider_cause"] == "UNATTRIBUTED"
    for field in ("admission_granted", "account_switch_authorized",
                  "reset_redemption_authorized", "schedule_prediction_authorized"):
        assert result[field] is False
    assert "secret-do-not-copy" not in str(result)
    assert "access_token" not in str(result)


def test_normal_window_turnover_is_not_falsely_classified_early():
    prior = probe(at=T, weekly_reset=T + HOUR, used=99)
    later = probe(at=T + 2 * HOUR, weekly_reset=T + WEEK, used=0)
    got = compare_native_codex_quota(prior, later)
    assert got["state"] == "CHANGE_OBSERVED"
    assert got["early_refresh_candidate"] is False
    assert got["observed_windows"][0]["classification"] == "PRIOR_WINDOW_DUE"


def test_timer_move_without_proven_headroom_is_not_reset_proof():
    before = probe(used=1)
    after = probe(at=T + HOUR, weekly_reset=T + WEEK + HOUR, used=2)
    got = compare_native_codex_quota(before, after)
    assert got["early_refresh_candidate"] is False
    assert got["observed_windows"][0]["classification"] == "TIMER_CHANGED_CAUSE_UNKNOWN"


def test_headroom_increase_without_timer_move_is_not_reset_proof():
    before = probe(used=65)
    after = probe(at=T + HOUR, weekly_reset=T + WEEK, used=5)
    got = compare_native_codex_quota(before, after)
    assert got["state"] == "CHANGE_OBSERVED"
    assert got["schedule_changed"] is False
    assert got["early_refresh_candidate"] is False
    assert got["observed_windows"][0]["classification"] == "HEADROOM_GAIN_WITHOUT_TIMER_PROOF"


def test_same_seat_no_material_change():
    got = compare_native_codex_quota(probe(used=5), probe(at=T + HOUR, used=8))
    assert got["state"] == "NO_MATERIAL_CHANGE"
    assert got["observed_windows"][0]["classification"] == "NO_TIMER_CHANGE"


@pytest.mark.parametrize("replacement,reason", [
    ({"subject": "b" * 64}, "SUBJECT_OR_LIMIT_MISMATCH"),
    ({"state": "QUOTA_UNAVAILABLE"}, "UNVERIFIED_OBSERVATIONS"),
    ({"state": "NATIVE_CLEANUP_UNPROVEN"}, "UNVERIFIED_OBSERVATIONS"),
    ({"at": T - 10}, "NONMONOTONIC_OBSERVATION"),
    ({"at": T + 7 * HOUR}, "GAP_TOO_LONG_TO_INFER_RESET"),
])
def test_cross_account_failure_or_stale_observation_refused(replacement, reason):
    got = compare_native_codex_quota(probe(), probe(**replacement))
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == reason
    assert got["early_refresh_candidate"] is False


@pytest.mark.parametrize("corrupt", ["bad_hash", "no_stop", "wrong_auth", "bad_percent",
                                     "missing_limit", "different_limit", "invalid_reset"])
def test_identity_and_window_validation_fails_closed(corrupt):
    old = probe()
    new = probe(at=T + HOUR, weekly_reset=T + WEEK + HOUR, used=1)
    if corrupt == "bad_hash":
        new["home_identity"]["account_id_sha256"] = "not-a-hash"
    elif corrupt == "no_stop":
        new["stop"]["private_group_empty"] = False
    elif corrupt == "wrong_auth":
        new["account"]["auth_state"] = "LOGIN_REQUIRED"
    elif corrupt == "bad_percent":
        new["account"]["windows"]["secondary"]["remaining_percent"] = 200
    elif corrupt == "missing_limit":
        new["account"]["limit_id"] = None
    elif corrupt == "different_limit":
        new["account"]["limit_id"] = "different"
    elif corrupt == "invalid_reset":
        new["account"]["windows"]["secondary"]["resets_at"] = "timestamp"
    result = compare_native_codex_quota(old, new)
    assert result["state"] == "UNKNOWN"
    assert result["early_refresh_candidate"] is False


def test_weekly_only_business_shape_is_comparable_without_five_hour_window():
    before = probe(used=80, primary=None)
    after = probe(at=T + HOUR, weekly_reset=T + WEEK + 2 * HOUR, used=0, primary=None)
    result = compare_native_codex_quota(before, after)
    assert [x["window"] for x in result["observed_windows"]] == ["secondary"]
    assert result["early_refresh_candidate"] is True


def test_missing_weekly_window_does_not_establish_available_weekly_capacity():
    old = probe(weekly=False, primary=30)
    new = probe(at=T + HOUR, weekly=False, primary=30)
    got = compare_native_codex_quota(old, new)
    assert got["early_refresh_candidate"] is False
    assert got["admission_granted"] is False
    assert not any(x["window"] == "secondary" for x in got["observed_windows"])


def test_no_comparable_windows_stays_unknown():
    got = compare_native_codex_quota(probe(weekly=False), probe(at=T + HOUR, weekly=False))
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "NO_COMPARABLE_WINDOWS"


def test_two_missing_limit_ids_never_compare():
    before, after = probe(), probe(at=T + HOUR)
    before["account"]["limit_id"] = None
    after["account"]["limit_id"] = None
    got = compare_native_codex_quota(before, after)
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "UNVERIFIED_OBSERVATIONS"


def test_oversized_numeric_input_stays_unknown_without_raising():
    after = probe(at=T + HOUR)
    after["account"]["observed_at_unix"] = 10 ** 1000
    got = compare_native_codex_quota(probe(), after)
    assert got["state"] == "UNKNOWN"


def test_changed_plan_is_not_promotional_reset_evidence():
    before = probe(used=85)
    after = probe(at=T + HOUR, weekly_reset=T + WEEK + HOUR, used=0)
    before["account"]["plan_type"] = "pro"
    after["account"]["plan_type"] = "business"
    # Preserve the same native person across the plan/context transition.
    before["home_identity"]["user_id_sha256"] = "a" * 64
    after["home_identity"]["user_id_sha256"] = "a" * 64
    got = compare_native_codex_quota(before, after)
    assert got["state"] == "UNKNOWN"
    assert got["reason"] == "ENTITLEMENT_CHANGED"
    assert got["early_refresh_candidate"] is False


@pytest.mark.parametrize("cleanup_ok", [True, False])
def test_native_probe_publishes_comparison_after_cleanup(tmp_path, monkeypatch, cleanup_ok):
    from control_plane import codex_account_environment as native
    from scripts.ohf import laboratory

    before = probe(used=85)
    before["account"]["plan_type"] = "pro"
    monkeypatch.setattr(native.time, "time", lambda: T + HOUR)
    calls = []

    class Environment:
        home = tmp_path
        def auth_metadata(self):
            return {"account_id_sha256": "a" * 64}
        def process_environment(self):
            return {}

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        def request(self, method, *args, **kwargs):
            calls.append(method)
            if method == "initialize":
                return {"userAgent": "fixture"}
            if method == "account/read":
                return {"account": {"type": "chatgpt", "planType": "pro"}}
            assert method == "account/rateLimits/read"
            return {"rateLimitsByLimitId": {"codex": {"primary": None,
                "secondary": {"usedPercent": 1, "windowDurationMins": 10080,
                              "resetsAt": T + WEEK + HOUR}}}}
        def notify(self, *args):
            pass
        def graceful_close(self):
            return laboratory.AppServerStopProof(
                controller_returncode=0, private_group_id=12345,
                private_group_empty=cleanup_ok, leader_exit_confirmed_graceful=True,
                survivors_detected_after_controller_exit=not cleanup_ok,
                termination_outcome="fixture")

    monkeypatch.setattr(laboratory, "AppServerClient", Client)
    result = native.probe_native_account(Environment(), tmp_path / "not-launched",
                                        previous_observation=before)
    assert calls == ["initialize", "account/read", "account/rateLimits/read"]
    assert result["quota_change"]["early_refresh_candidate"] is cleanup_ok
    assert result["quota_change"]["admission_granted"] is False
    assert result["state"] == ("NATIVE_READS_COMPLETED" if cleanup_ok else "NATIVE_CLEANUP_UNPROVEN")


def test_readiness_cli_rejects_invalid_previous_input_before_account_access(monkeypatch, capsys):
    import io
    from scripts import executive_codex_account as cli
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("not valid JSON"))
    def forbidden(*args, **kwargs):
        raise AssertionError("account access must not begin")
    monkeypatch.setattr(cli, "native_codex_account_scope", forbidden)
    code = cli.main(["--provider-home", "/not-opened", "readiness",
                     "--binary", "/not-launched", "--previous-observation-stdin"])
    assert code == 2
    assert "PRIOR_OBSERVATION_INVALID" in capsys.readouterr().out


def test_readiness_cli_passes_previous_probe_without_new_store(monkeypatch, capsys):
    import io
    import json
    from contextlib import nullcontext
    from scripts import executive_codex_account as cli
    before = probe()
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps(before)))
    monkeypatch.setattr(cli, "native_codex_account_scope", lambda *a: nullcontext(object()))
    def observed(environment, binary, **kwargs):
        assert kwargs["previous_observation"] == before
        return {"state": "NATIVE_READS_COMPLETED", "quota_change": {"state": "NO_MATERIAL_CHANGE"}}
    monkeypatch.setattr(cli, "probe_native_account", observed)
    code = cli.main(["--provider-home", "/not-opened", "readiness",
                     "--binary", "/not-launched", "--previous-observation-stdin"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["quota_change"]["state"] == "NO_MATERIAL_CHANGE"


@pytest.mark.parametrize("with_catalog,model_rpc_fails", [
    (False, False), (True, False), (True, True),
])
def test_readiness_cli_opt_in_models_uses_same_appserver_and_refuses_unknown(
    tmp_path, monkeypatch, capsys, with_catalog, model_rpc_fails,
):
    """CLI-to-actual-probe test: never opens a real provider home or starts Codex."""
    import json
    import time
    from contextlib import nullcontext
    from scripts import executive_codex_account as cli
    from scripts.ohf import laboratory

    calls = []
    class FakeEnvironment:
        home = tmp_path
        def auth_metadata(self):
            return {"account_id_sha256": "a" * 64}
        def process_environment(self):
            return {"PATH": "/usr/bin:/bin"}

    class FakeAppServer:
        def __init__(self, argv, *, env, cwd, start_new_session):
            assert argv[1] == "app-server"
            assert start_new_session and cwd == tmp_path
            assert "OPENAI_API_KEY" not in env
            calls.append("created")
        def start(self):
            calls.append("started")
        def request(self, method, *args, **kwargs):
            calls.append(method)
            if method == "initialize":
                return {"userAgent": "fixture-only"}
            if method == "account/read":
                return {"account": {"type": "chatgpt", "planType": "pro"}}
            if method == "account/rateLimits/read":
                return {"rateLimitsByLimitId": {"codex": {
                    "primary": {
                        "usedPercent": 10,
                        "windowDurationMins": 10080,
                        "resetsAt": int(time.time()) + 3600,
                    },
                    "secondary": None,
                }}}
            if method == "model/list":
                assert args[0] == {"limit": 100, "includeHidden": False}
                if model_rpc_fails:
                    raise RuntimeError("Bearer SENSITIVE-SENTINEL")
                return {"data": [{"id": "gpt-6-astra"}, {"id": "gpt-6.1-sol"}]}
            raise AssertionError("unexpected native RPC")
        def notify(self, *args):
            calls.append("notify")
        def graceful_close(self):
            calls.append("closed")
            return laboratory.AppServerStopProof(
                controller_returncode=0, private_group_id=12345,
                private_group_empty=True, leader_exit_confirmed_graceful=True,
                survivors_detected_after_controller_exit=False,
                termination_outcome="fixture",
            )

    monkeypatch.setattr(cli, "native_codex_account_scope",
                        lambda *args: nullcontext(FakeEnvironment()))
    monkeypatch.setattr(laboratory, "AppServerClient", FakeAppServer)
    argv = ["--provider-home", str(tmp_path), "readiness", "--binary",
            "/not-launched-codex"]
    if with_catalog:
        argv.append("--include-models")
    code = cli.main(argv)
    output = capsys.readouterr().out
    result = json.loads(output)
    assert code == 0 and result["state"] == "NATIVE_READS_COMPLETED"
    assert result["stop"]["private_group_empty"] is True
    assert result["account"]["capacity_state"] == "AVAILABLE_OBSERVED"
    assert "SENSITIVE-SENTINEL" not in output
    rpc_order = [name for name in calls if name in (
        "initialize", "account/read", "account/rateLimits/read", "model/list",
    )]
    expected = ["initialize", "account/read", "account/rateLimits/read"]
    if with_catalog:
        expected.append("model/list")
    assert rpc_order == expected
    assert calls.count("created") == calls.count("closed") == 1
    if not with_catalog:
        assert "model_visibility" not in result
    elif model_rpc_fails:
        assert result["model_visibility"]["state"] == "UNKNOWN"
        assert result["model_visibility"]["supported_models"] == []
        assert result["model_visibility"]["admission_granted"] is False
    else:
        assert result["model_visibility"]["state"] == "OBSERVED"
        assert result["model_visibility"]["supported_models"] == [
            "gpt-6-astra", "gpt-6.1-sol",
        ]
        assert result["model_visibility"]["admission_granted"] is False

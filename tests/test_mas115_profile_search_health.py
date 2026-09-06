from __future__ import annotations

import importlib.util
import io
import json
import os
import signal
from types import SimpleNamespace

import pytest

from integrations.chairman_surfaces import nonseat_canary as core
from integrations.chairman_surfaces import nonseat_canary_vendors as vendors

health = None
if importlib.util.find_spec(
    "integrations.chairman_surfaces.mas115_profile_search_health"
) is not None:
    from integrations.chairman_surfaces import mas115_profile_search_health as health

_FOLDER = "00000000-0000-4000-8000-000000000002"
_PROFILE = "00000000-0000-4000-8000-000000000001"
_SECRET = "header.payload.signature"
_KEYS = {
    "schema", "operation", "verdict", "effect", "code", "detail",
    "read_surface_usable", "initial_peer_census_diagnostic",
    "initial_peer_census_decode_context",
}
_NONE_CONTEXT = {
    "status_class": "NONE",
    "declared_media_type_class": "NONE",
    "decoder_class": "NONE",
}


def _provision():
    return {
        "vendor": "multilogin",
        "browser_type": "mimic",
        "profile_id": _PROFILE,
        "folder_id": _FOLDER,
    }


def _payload(profiles, total):
    return {
        "status": {"error_code": "", "http_code": 200, "message": "ok"},
        "data": {"profiles": profiles, "total_count": total},
    }


class _FakeHttp:
    def __init__(self, responses, events=None, *, close_error=False):
        self.responses = list(responses)
        self.events = events if events is not None else []
        self.close_error = close_error
        self.search_calls = 0
        self.closed = 0

    def search(self, credential, folder_id, offset, diagnostic_sink):
        assert credential.expose() == _SECRET
        assert folder_id == _FOLDER
        self.events.append(f"search:{offset}")
        self.search_calls += 1
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def close(self):
        self.events.append("client_close")
        self.closed += 1
        if self.close_error:
            raise RuntimeError("private close error")


def _run(
    responses,
    *,
    preflight=(_provision(), None),
    credential_present=True,
    pipe_close=True,
    client_close_error=False,
):
    events = []
    out = io.StringIO()
    pipe = SimpleNamespace()
    credential = core.Credential(
        _SECRET if credential_present else None,
        "stdin" if credential_present else "absent",
    )
    fake_http = _FakeHttp(responses, events, close_error=client_close_error)
    bounded = vendors.BoundedHttpClient(client=fake_http)
    code = health._run_profile_search_health(
        stdout=out,
        preflight_loader=lambda: preflight,
        pipe_factory=lambda: events.append("pipe_open") or pipe,
        credential_reader=lambda actual: events.append("credential_read") or credential,
        pipe_closer=lambda actual: events.append("pipe_close") or pipe_close,
        client_factory=lambda: events.append("client_open") or bounded,
        client_closer=lambda actual: health._checked_close_http_client(actual),
    )
    return code, json.loads(out.getvalue()), events, fake_http


def test_profile_search_health_module_exists():
    assert health is not None, "Profile Search health source module is missing"


def test_receipt_schema_is_exact_and_success_is_narrow():
    receipt = health._receipt("OK")
    assert set(receipt) == _KEYS
    assert receipt == {
        "schema": "mastermind.mas115_profile_search_health.v1",
        "operation": "web-sol-realm1-profile-search-read-health-20260905-sol-001",
        "verdict": "PASS",
        "effect": "NONE",
        "code": "OK",
        "detail": core.DETAILS["OK"],
        "read_surface_usable": True,
        "initial_peer_census_diagnostic": "NONE",
        "initial_peer_census_decode_context": _NONE_CONTEXT,
    }


def test_preflight_refusal_precedes_pipe_and_http():
    code, receipt, events, http = _run(
        [], preflight=(None, "BINDINGS_UNAVAILABLE")
    )
    assert code == 2
    assert receipt["code"] == "BINDINGS_UNAVAILABLE"
    assert events == []
    assert http.search_calls == 0


def test_pipe_cleanup_must_be_exact_true_before_http_construction():
    code, receipt, events, http = _run([], pipe_close=False)
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert events == ["pipe_open", "credential_read", "pipe_close"]
    assert http.search_calls == 0


def test_absent_credential_is_classified_only_after_pipe_cleanup():
    code, receipt, events, http = _run([], credential_present=False)
    assert code == 2
    assert receipt["code"] == "AUTH_MISSING"
    assert events == ["pipe_open", "credential_read", "pipe_close"]
    assert http.search_calls == 0


def test_complete_two_page_census_discards_all_rows_and_passes_after_cleanup():
    rows = [
        {
            "id": f"00000000-0000-4000-8000-{i:012d}",
            "folder_id": _FOLDER,
            "name": f"profile-{i}",
        }
        for i in range(11)
    ]
    code, receipt, events, http = _run([
        vendors._BoundedResponse(200, _payload(rows[:10], 11)),
        vendors._BoundedResponse(200, _payload(rows[10:], 11)),
    ])
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert receipt["read_surface_usable"] is True
    assert events == [
        "pipe_open", "credential_read", "pipe_close", "client_open",
        "search:0", "search:10", "client_close",
    ]
    assert http.search_calls == 2
    assert http.closed == 1
    rendered = json.dumps(receipt, sort_keys=True)
    for forbidden in (
        "profile-0", _PROFILE, _FOLDER, "total_count", "page_count", "candidate",
    ):
        assert forbidden not in rendered


def test_http_cleanup_failure_overrides_a_successful_census():
    code, receipt, events, http = _run([
        vendors._BoundedResponse(200, _payload([], 0)),
    ], client_close_error=True)
    assert code == 2
    assert receipt["verdict"] == "REFUSED"
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["read_surface_usable"] is False
    assert events[-1] == "client_close"
    assert http.closed == 1


def test_transport_failure_is_single_attempt_and_closed():
    code, receipt, _events, http = _run([
        RuntimeError("private transport detail")
    ])
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["initial_peer_census_diagnostic"] == "TRANSPORT_FAILURE"
    assert http.search_calls == 1
    assert "private transport detail" not in json.dumps(receipt)


@pytest.mark.parametrize(
    ("status", "diagnostic"),
    [
        (429, "HTTP_RATE_LIMITED"),
        (422, "HTTP_REQUEST_REJECTED"),
        (503, "HTTP_SERVICE_UNAVAILABLE"),
        (299, "HTTP_UNEXPECTED"),
    ],
)
def test_non_success_statuses_remain_closed(status, diagnostic):
    code, receipt, _events, http = _run([
        vendors._BoundedResponse(status, {})
    ])
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["initial_peer_census_diagnostic"] == diagnostic
    assert http.search_calls == 1


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejection_is_not_recovery_or_refresh(status):
    code, receipt, _events, http = _run([
        vendors._BoundedResponse(status, {})
    ])
    assert code == 2
    assert receipt["code"] == "AUTH_EXPIRED"
    assert receipt["effect"] == "NONE"
    assert http.search_calls == 1


def test_profile_only_client_exposes_no_mutator_or_fallback_surface():
    bounded = vendors.BoundedHttpClient(client=_FakeHttp([]))
    narrowed = health._ProfileSearchOnlyClient(bounded)
    assert callable(narrowed._mlx_profile_search_with_diagnostic)
    for forbidden in (
        "_mlx_profile_search", "_mlx_profile_create", "_mlx_profile_remove",
        "_mlx_profile_start", "_mlx_profile_stop", "_mlx_configure_canary_port",
    ):
        assert not hasattr(narrowed, forbidden)
    assert not hasattr(narrowed, "__dict__")


def test_proxy_exposes_only_parser_requirements_not_full_multilogin_client():
    credential = core.Credential(_SECRET, "stdin")
    bounded = vendors.BoundedHttpClient(client=_FakeHttp([]))
    proxy = health._ProfileSearchProxy(
        credential, health._ProfileSearchOnlyClient(bounded)
    )
    assert type(proxy) is not vendors.MultiloginClient
    assert not hasattr(proxy, "create_peer_profile")
    assert not hasattr(proxy, "remove_peer_profile")
    assert not hasattr(proxy, "configure_canary_port")
    assert not hasattr(proxy, "start")
    assert not hasattr(proxy, "stop")
    assert not hasattr(proxy, "__dict__")


def test_checked_http_close_is_one_shot_and_exact_boolean():
    fake = _FakeHttp([])
    client = vendors.BoundedHttpClient(client=fake)
    assert health._checked_close_http_client(client) is True
    assert health._checked_close_http_client(client) is False
    assert fake.closed == 1


def test_checked_pipe_close_reaps_without_signal_and_is_one_shot():
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    waits = iter([(4242, 0)])
    pipe = vendors._KeychainCredentialPipe(
        read_fd,
        4242,
        waitpid=lambda pid, flags: next(waits),
        kill=lambda *_: pytest.fail("no signal should be sent"),
    )
    assert health._checked_close_keychain_pipe(pipe) is True
    assert health._checked_close_keychain_pipe(pipe) is False


def test_checked_pipe_close_term_then_reap_is_bounded():
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    signals = []

    def _waitpid(pid, flags):
        return (pid, 0) if signals else (0, 0)

    pipe = vendors._KeychainCredentialPipe(
        read_fd,
        4242,
        waitpid=_waitpid,
        kill=lambda pid, sig: signals.append(sig),
    )
    assert health._checked_close_keychain_pipe(pipe) is True
    assert signals == [signal.SIGTERM]


def test_live_wrapper_fixes_all_dependency_owners(monkeypatch):
    observed = {}
    monkeypatch.setattr(
        health,
        "_run_profile_search_health",
        lambda **kwargs: observed.update(kwargs) or 2,
    )
    out = io.StringIO()
    assert health.run_coordinator_profile_search_health(stdout=out) == 2
    assert observed["stdout"] is out
    assert observed["preflight_loader"] is health._load_live_preflight
    assert observed["pipe_factory"] is vendors._open_keychain_credential_pipe
    assert observed["credential_reader"] is vendors._read_direct_pipe_credential
    assert observed["client_factory"] is vendors.BoundedHttpClient
    assert observed["pipe_closer"] is health._checked_close_keychain_pipe
    assert observed["client_closer"] is health._checked_close_http_client


def test_setup_gologin_refuses_before_prompt_or_health(monkeypatch):
    from scripts import mas115_setup as setup

    calls = []
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: pytest.fail("must not prompt")
    )
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main(["profile-search-health", "--vendor", "gologin"]) == 2
    assert calls == []


def test_setup_wrong_confirmation_refuses_before_health(monkeypatch):
    from scripts import mas115_setup as setup

    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt: "wrong")
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main([
        "profile-search-health", "--vendor", "multilogin"
    ]) == 2
    assert calls == []


def test_setup_exact_confirmation_dispatches_only_fixed_health_entry(monkeypatch):
    from scripts import mas115_setup as setup

    calls = []
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: setup._CONFIRM_PROFILE_SEARCH_HEALTH
    )
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main([
        "profile-search-health", "--vendor", "multilogin"
    ]) == 0
    assert calls == ["health"]

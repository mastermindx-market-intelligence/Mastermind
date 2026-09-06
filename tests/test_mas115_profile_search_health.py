from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

import pytest

from integrations.chairman_surfaces import nonseat_canary as core
from integrations.chairman_surfaces import nonseat_canary_vendors as vendors
health = None
if importlib.util.find_spec("integrations.chairman_surfaces.mas115_profile_search_health") is not None:
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


def _rendered(receipt):
    return json.dumps(receipt, separators=(",", ":"), sort_keys=True) + "\n"


class _FakeHeaders:
    def __init__(self, content_type="application/json"):
        self.content_type = content_type

    def get_list(self, key):
        if key.lower() != "content-type" or self.content_type is None:
            return []
        return [self.content_type]


class _FakeWireResponse:
    def __init__(self, response):
        self.status_code = response.status_code
        self.headers = _FakeHeaders()
        self._payload = response.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_bytes(self):
        yield json.dumps(self._payload).encode("utf-8")


class _RawWireResponse:
    def __init__(self, status_code, body: bytes, content_type):
        self.status_code = status_code
        self.headers = _FakeHeaders(content_type)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_bytes(self):
        yield self._body


class _FakeHttp:
    def __init__(self, responses, events=None, *, close_error=False):
        self.responses = list(responses)
        self.events = events if events is not None else []
        self.close_error = close_error
        self.search_calls = 0
        self.closed = 0

    def stream(self, method, url, *, headers=None, params=None, json=None):
        assert method == "POST"
        assert url.endswith("/profile/search")
        assert headers == {"Authorization": f"Bearer {_SECRET}"}
        assert params is None
        assert isinstance(json, dict)
        assert json["folder_id"] == _FOLDER
        offset = json["offset"]
        self.events.append(f"search:{offset}")
        self.search_calls += 1
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, _RawWireResponse):
            return response
        return _FakeWireResponse(response)

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
    credential = core.Credential(_SECRET if credential_present else None, "stdin" if credential_present else "absent")
    fake_http = _FakeHttp(responses, events, close_error=client_close_error)
    code = health._run_profile_search_health(
        stdout=out,
        preflight_loader=lambda: preflight,
        pipe_factory=lambda: events.append("pipe_open") or pipe,
        credential_reader=lambda actual: events.append("credential_read") or credential,
        pipe_closer=lambda actual: events.append("pipe_close") or pipe_close,
        client_factory=lambda: events.append("client_open") or health._ProfileSearchOnlyClient(client=fake_http),
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
        "operation": "web-sol-realm1-profile-search-read-health-source-20260905-sol-001",
        "verdict": "PASS",
        "effect": "NONE",
        "code": "OK",
        "detail": core.DETAILS["OK"],
        "read_surface_usable": True,
        "initial_peer_census_diagnostic": "NONE",
        "initial_peer_census_decode_context": _NONE_CONTEXT,
    }


def test_pretrusted_cli_refusal_is_fixed_closed_receipt_only():
    out = io.StringIO()
    assert health.run_coordinator_profile_search_health_refusal(stdout=out) == 2
    receipt = json.loads(out.getvalue())
    assert set(receipt) == _KEYS
    assert receipt == health._receipt("UNSUPPORTED_SURFACE")


def test_preflight_refusal_precedes_pipe_and_http():
    code, receipt, events, http = _run([], preflight=(None, "BINDINGS_UNAVAILABLE"))
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


def test_truthy_non_boolean_pipe_cleanup_refuses_before_http_construction():
    code, receipt, events, http = _run([], pipe_close=1)
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert events == ["pipe_open", "credential_read", "pipe_close"]
    assert http.search_calls == 0


def test_malformed_preflight_without_anchor_identity_refuses_before_secret():
    malformed = _provision()
    malformed.pop("profile_id")
    code, receipt, events, http = _run([], preflight=(malformed, None))
    assert code == 2
    assert receipt["code"] == "PROVISION_MISSING"
    assert events == []
    assert http.search_calls == 0


def test_absent_credential_is_classified_only_after_pipe_cleanup():
    code, receipt, events, http = _run([], credential_present=False)
    assert code == 2
    assert receipt["code"] == "AUTH_MISSING"
    assert events == ["pipe_open", "credential_read", "pipe_close"]
    assert http.search_calls == 0


def test_credential_reader_cancellation_still_closes_pipe_before_refusal():
    events = []
    out = io.StringIO()
    pipe = SimpleNamespace()
    code = health._run_profile_search_health(
        stdout=out,
        preflight_loader=lambda: (_provision(), None),
        pipe_factory=lambda: events.append("pipe_open") or pipe,
        credential_reader=lambda actual: (_ for _ in ()).throw(KeyboardInterrupt()),
        pipe_closer=lambda actual: events.append("pipe_close") or True,
        client_factory=lambda: pytest.fail("HTTP must not be constructed"),
        client_closer=lambda actual: pytest.fail("HTTP close is not applicable"),
    )
    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["code"] == "AUTH_MISSING"
    assert events == ["pipe_open", "pipe_close"]


def test_complete_two_page_census_discards_all_rows_and_passes_after_cleanup():
    rows = [
        {"id": f"00000000-0000-4000-8000-{i:012d}", "folder_id": _FOLDER, "name": f"profile-{i}"}
        for i in range(11)
    ]
    code, receipt, events, http = _run([
        vendors._BoundedResponse(200, _payload(rows[:10], 11)),
        vendors._BoundedResponse(200, _payload(rows[10:], 11)),
    ])
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert receipt["read_surface_usable"] is True
    assert events == ["pipe_open", "credential_read", "pipe_close", "client_open", "search:0", "search:10", "client_close"]
    assert http.search_calls == 2
    assert http.closed == 1
    rendered = json.dumps(receipt, sort_keys=True)
    for forbidden in ("profile-0", _PROFILE, _FOLDER, "total_count", "page_count", "candidate"):
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


def test_diagnostic_sink_construction_failure_still_closes_http_and_refuses(monkeypatch):
    monkeypatch.setattr(
        vendors,
        "_InitialPeerCensusDiagnosticSink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("private sink error")),
    )
    code, receipt, events, http = _run([
        vendors._BoundedResponse(200, _payload([], 0)),
    ])
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["read_surface_usable"] is False
    assert events[-1] == "client_close"
    assert http.closed == 1
    assert "private sink error" not in json.dumps(receipt)


def test_transport_failure_is_single_attempt_and_closed():
    code, receipt, events, http = _run([RuntimeError("private transport detail")])
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["initial_peer_census_diagnostic"] == "TRANSPORT_FAILURE"
    assert http.search_calls == 1
    assert "private transport detail" not in json.dumps(receipt)


@pytest.mark.parametrize(
    ("status", "diagnostic"),
    [(429, "HTTP_RATE_LIMITED"), (422, "HTTP_REQUEST_REJECTED"), (503, "HTTP_SERVICE_UNAVAILABLE"), (299, "HTTP_UNEXPECTED")],
)
def test_non_success_statuses_remain_closed(status, diagnostic):
    code, receipt, _, http = _run([vendors._BoundedResponse(status, {})])
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["initial_peer_census_diagnostic"] == diagnostic
    assert http.search_calls == 1


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejection_is_not_recovery_or_refresh(status):
    code, receipt, _, http = _run([vendors._BoundedResponse(status, {})])
    assert code == 2
    assert receipt["code"] == "AUTH_EXPIRED"
    assert receipt["effect"] == "NONE"
    assert http.search_calls == 1


def test_profile_only_client_exposes_no_mutator_or_fallback_surface():
    narrowed = health._ProfileSearchOnlyClient(client=_FakeHttp([]))
    assert type(narrowed) is not vendors.BoundedHttpClient
    assert callable(narrowed._mlx_profile_search_with_diagnostic)
    assert not hasattr(narrowed, "_delegate")
    for forbidden in (
        "_mlx_profile_search", "_mlx_profile_create", "_mlx_profile_remove",
        "_mlx_profile_start", "_mlx_profile_stop", "_mlx_configure_canary_port",
    ):
        assert not hasattr(narrowed, forbidden)
    assert not hasattr(narrowed, "__dict__")
    for name in dir(narrowed):
        value = getattr(narrowed, name, None)
        owner = getattr(value, "__self__", None)
        assert type(owner) is not vendors.BoundedHttpClient


def test_profile_only_client_rejects_full_bounded_constructor_input():
    bounded = vendors.BoundedHttpClient(client=_FakeHttp([]))
    with pytest.raises(TypeError):
        health._ProfileSearchOnlyClient(bounded)


def test_proxy_exposes_only_parser_requirements_not_full_multilogin_client():
    credential = core.Credential(_SECRET, "stdin")
    narrowed = health._ProfileSearchOnlyClient(client=_FakeHttp([]))
    proxy = health._ProfileSearchProxy(credential, narrowed)
    assert type(proxy) is not vendors.MultiloginClient
    assert not hasattr(proxy, "create_peer_profile")
    assert not hasattr(proxy, "remove_peer_profile")
    assert not hasattr(proxy, "configure_canary_port")
    assert not hasattr(proxy, "start")
    assert not hasattr(proxy, "stop")
    assert not hasattr(proxy, "__dict__")


def test_health_source_ast_has_no_mutation_peer_state_or_retry_calls():
    tree = ast.parse(Path(health.__file__).read_text())
    forbidden = {
        "_mlx_profile_create", "_mlx_profile_remove", "_mlx_profile_start",
        "_mlx_profile_stop", "_mlx_configure_canary_port", "create_peer_profile",
        "remove_peer_profile", "_commit_peer_intent", "_transition_peer_intent",
        "_write_peer_provision", "_exclusive_private_json", "atomic_private_json",
        "run_coordinator_peer_create", "run_coordinator_peer_rollback",
        "LoopbackBenignOrigin", "WebDriverNavigator", "PEER_INTENT_PATH",
        "PEER_GENESIS_WITNESS_PATH", "PEER_BOOTSTRAP_FENCE_PATH",
        "PEER_PROVISION_PATH", "PEER_OWNERSHIP_RECEIPT_PATH", "sleep",
    }
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            hits.append((node.id, node.lineno))
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            hits.append((node.attr, node.lineno))
    assert hits == []


def test_success_path_never_calls_other_bounded_http_endpoints(monkeypatch):
    forbidden = (
        "_mlx_profile_create", "_mlx_profile_remove", "_mlx_profile_start",
        "_mlx_profile_stop", "_mlx_configure_canary_port", "_mlx_profile_status",
        "_mlx_profile_metas", "_webdriver_create_session", "_webdriver_navigate",
    )

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("forbidden endpoint reached")

    for name in forbidden:
        monkeypatch.setattr(vendors.BoundedHttpClient, name, _forbidden, raising=False)
    code, receipt, _events, http = _run([
        vendors._BoundedResponse(200, _payload([], 0)),
    ])
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert http.search_calls == 1


def test_profile_only_request_guard_refuses_non_search_shapes_before_http():
    fake = _FakeHttp([])
    narrowed = health._ProfileSearchOnlyClient(client=fake)
    canonical_body = {
        "is_removed": False,
        "limit": vendors._PROFILE_PAGE_SIZE,
        "offset": 0,
        "search_text": "",
        "storage_type": "all",
        "order_by": "created_at",
        "sort": "asc",
        "folder_id": _FOLDER,
    }
    attempts = (
        ("GET", vendors._MLX_CLOUD_ORIGIN, "/profile/search", canonical_body),
        ("POST", "https://example.invalid", "/profile/search", canonical_body),
        ("POST", vendors._MLX_CLOUD_ORIGIN, "/profile/create", canonical_body),
        ("POST", vendors._MLX_CLOUD_ORIGIN, "/profile/search", {**canonical_body, "search_text": "x"}),
    )
    for method, origin, path, body in attempts:
        with pytest.raises(core.CanaryRefusal):
            narrowed._request(
                method,
                origin,
                path,
                headers={"Authorization": f"Bearer {_SECRET}"},
                params=None,
                json_body=body,
                diagnostic_sink=None,
            )
    assert fake.search_calls == 0


def test_checked_http_close_is_one_shot_and_exact_boolean():
    fake = _FakeHttp([])
    client = health._ProfileSearchOnlyClient(client=fake)
    assert health._checked_close_http_client(client) is True
    assert health._checked_close_http_client(client) is False
    assert fake.closed == 1


def test_truthy_non_boolean_client_cleanup_cannot_produce_pass():
    events = []
    out = io.StringIO()
    pipe = SimpleNamespace()
    fake_http = _FakeHttp(
        [vendors._BoundedResponse(200, _payload([], 0))], events,
    )
    code = health._run_profile_search_health(
        stdout=out,
        preflight_loader=lambda: (_provision(), None),
        pipe_factory=lambda: events.append("pipe_open") or pipe,
        credential_reader=lambda actual: events.append("credential_read") or core.Credential(_SECRET, "stdin"),
        pipe_closer=lambda actual: events.append("pipe_close") or True,
        client_factory=lambda: events.append("client_open") or health._ProfileSearchOnlyClient(client=fake_http),
        client_closer=lambda actual: actual._client.close() or 1,
    )
    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["read_surface_usable"] is False
    assert events[-1] == "client_close"


def test_checked_pipe_close_reaps_without_signal_and_is_one_shot():
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    waits = iter([(4242, 0)])
    pipe = vendors._KeychainCredentialPipe(
        read_fd, 4242,
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
        read_fd, 4242,
        waitpid=_waitpid,
        kill=lambda pid, sig: signals.append(sig),
    )
    assert health._checked_close_keychain_pipe(pipe) is True
    assert signals == [signal.SIGTERM]


def test_checked_pipe_term_error_still_attempts_kill_and_refuses():
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    signals = []

    def _kill(pid, sig):
        signals.append(sig)
        if sig == signal.SIGTERM:
            raise OSError("synthetic TERM failure")

    pipe = vendors._KeychainCredentialPipe(
        read_fd, 4242,
        waitpid=lambda pid, flags: (0, 0),
        kill=_kill,
    )
    assert health._checked_close_keychain_pipe(pipe) is False
    assert signals == [signal.SIGTERM, signal.SIGKILL]


def test_checked_pipe_initial_wait_error_still_attempts_term_and_kill_and_refuses(monkeypatch):
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    signals = []
    waits = iter((RuntimeError("initial wait failed"), False, True))

    def _wait_until(_self, _deadline):
        outcome = next(waits)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(vendors._KeychainCredentialPipe, "_wait_until", _wait_until)
    pipe = vendors._KeychainCredentialPipe(
        read_fd, 4242,
        waitpid=lambda _pid, _flags: (0, 0),
        kill=lambda _pid, sig: signals.append(sig),
    )
    assert health._checked_close_keychain_pipe(pipe) is False
    assert signals == [signal.SIGTERM, signal.SIGKILL]


@pytest.mark.parametrize(
    ("wire", "status_class", "media_class", "decoder_class"),
    (
        (_RawWireResponse(503, b"<html>private</html>", "text/html"), "HTTP_5XX", "HTML", "JSON_VALUE_REJECTED"),
        (_RawWireResponse(302, b"not-json", None), "HTTP_3XX", "MISSING", "JSON_VALUE_REJECTED"),
        (_RawWireResponse(429, b"\xff", "text/plain"), "HTTP_RATE_LIMITED", "TEXT", "UNICODE_REJECTED"),
    ),
)
def test_decode_failure_context_projects_closed_wire_classes_without_raw_leak(
    wire, status_class, media_class, decoder_class,
):
    code, receipt, _events, http = _run([wire])
    assert code == 2
    assert receipt["code"] == "VENDOR_ERROR"
    assert receipt["initial_peer_census_diagnostic"] == "RESPONSE_DECODE_FAILURE"
    assert receipt["initial_peer_census_decode_context"] == {
        "status_class": status_class,
        "declared_media_type_class": media_class,
        "decoder_class": decoder_class,
    }
    rendered = json.dumps(receipt, sort_keys=True)
    assert "private" not in rendered
    assert "not-json" not in rendered
    assert http.search_calls == 1


def test_live_wrapper_fixes_all_dependency_owners(monkeypatch):
    observed = {}
    monkeypatch.setattr(health, "_run_profile_search_health", lambda **kwargs: observed.update(kwargs) or 2)
    out = io.StringIO()
    assert health.run_coordinator_profile_search_health(stdout=out) == 2
    assert observed["stdout"] is out
    assert observed["preflight_loader"] is health._load_live_preflight
    assert observed["pipe_factory"] is vendors._open_keychain_credential_pipe
    assert observed["credential_reader"] is vendors._read_direct_pipe_credential
    assert observed["client_factory"] is health._ProfileSearchOnlyClient
    assert observed["pipe_closer"] is health._checked_close_keychain_pipe
    assert observed["client_closer"] is health._checked_close_http_client


def test_setup_gologin_refuses_before_prompt_or_health(monkeypatch, capsys):
    from scripts import mas115_setup as setup
    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("must not prompt"))
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main(["profile-search-health", "--vendor", "gologin"]) == 2
    captured = capsys.readouterr()
    assert captured.out == _rendered(health._receipt("UNSUPPORTED_SURFACE"))
    assert captured.err == ""
    assert calls == []


def test_setup_wrong_confirmation_refuses_before_health(monkeypatch, capsys):
    from scripts import mas115_setup as setup
    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt: "wrong")
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main(["profile-search-health", "--vendor", "multilogin"]) == 2
    captured = capsys.readouterr()
    assert captured.out == _rendered(health._receipt("UNSUPPORTED_SURFACE"))
    assert captured.err == (
        f"Type {setup._CONFIRM_PROFILE_SEARCH_HEALTH!r} to perform one read-only "
        "Profile Search health observation: "
    )
    assert calls == []


def test_setup_eof_confirmation_refuses_with_closed_receipt(monkeypatch, capsys):
    from scripts import mas115_setup as setup
    calls = []

    def _eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main(["profile-search-health", "--vendor", "multilogin"]) == 2
    captured = capsys.readouterr()
    assert captured.out == _rendered(health._receipt("UNSUPPORTED_SURFACE"))
    assert captured.err == (
        f"Type {setup._CONFIRM_PROFILE_SEARCH_HEALTH!r} to perform one read-only "
        "Profile Search health observation: "
    )
    assert calls == []


@pytest.mark.parametrize(
    "confirmation",
    (
        " OBSERVE MULTILOGIN PROFILE SEARCH HEALTH ONCE",
        "OBSERVE MULTILOGIN PROFILE SEARCH HEALTH ONCE ",
        "OBSERVE MULTILOGIN PROFILE SEARCH HEALTH ONCE\t",
        "observe multilogin profile search health once",
        "",
    ),
)
def test_setup_confirmation_is_byte_exact_without_whitespace_normalization(monkeypatch, confirmation):
    from scripts import mas115_setup as setup
    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt: confirmation)
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main(["profile-search-health", "--vendor", "multilogin"]) == 2
    assert calls == []


def test_setup_valid_health_invocation_keeps_prompt_off_stdout(monkeypatch, capsys):
    from scripts import mas115_setup as setup
    expected_receipt = health._receipt("BINDINGS_UNAVAILABLE")
    rendered = _rendered(expected_receipt)
    monkeypatch.setattr(sys, "stdin", io.StringIO(setup._CONFIRM_PROFILE_SEARCH_HEALTH + "\n"))

    def _fake_health():
        sys.stdout.write(rendered)
        return 2

    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        _fake_health,
    )
    assert setup.main(["profile-search-health", "--vendor", "multilogin"]) == 2
    captured = capsys.readouterr()
    assert captured.out == rendered
    assert captured.err == (
        f"Type {setup._CONFIRM_PROFILE_SEARCH_HEALTH!r} to perform one read-only "
        "Profile Search health observation: "
    )


def test_setup_exact_confirmation_dispatches_only_fixed_health_entry(monkeypatch):
    from scripts import mas115_setup as setup
    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt: setup._CONFIRM_PROFILE_SEARCH_HEALTH)
    monkeypatch.setattr(
        setup.profile_search_health,
        "run_coordinator_profile_search_health",
        lambda: calls.append("health") or 0,
    )
    assert setup.main(["profile-search-health", "--vendor", "multilogin"]) == 0
    assert calls == ["health"]

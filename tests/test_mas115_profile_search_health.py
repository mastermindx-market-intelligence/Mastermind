from __future__ import annotations

import ast
import functools
import importlib.util
import inspect
import io
import json
import math
import os
from pathlib import Path
import signal
import sys
import types
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


def _profile_row(
    profile_id=_PROFILE,
    folder_id=_FOLDER,
    name="peer",
    **extra,
):
    return {
        "id": profile_id,
        "folder_id": folder_id,
        "name": name,
        "browser_type": "mimic",
        "os_type": "macos",
        **extra,
    }


def _census_state(*, folder_id=_FOLDER, peer_name="peer"):
    return vendors._ProfileSearchCensusState(  # noqa: SLF001
        folder_id=folder_id,
        peer_name=peer_name,
    )


def _consume_census(state, response):
    sink = vendors._InitialPeerCensusDiagnosticSink(
        vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,
    )
    state.consume(response, diagnostic_sink=sink)
    return sink


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
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            vendors.httpx,
            "Client",
            lambda **_kwargs: events.append("client_open") or fake_http,
        )
        code = health._run_profile_search_health(
            stdout=out,
            preflight_loader=lambda: preflight,
            pipe_factory=lambda: events.append("pipe_open") or pipe,
            credential_reader=lambda actual: events.append("credential_read") or credential,
            pipe_closer=lambda actual: events.append("pipe_close") or pipe_close,
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


def test_hermetic_run_rejects_injected_raw_transport_before_any_effect():
    events = []

    class MutationCapableRawTransport:
        def stream(self, *_args, **_kwargs):
            events.append("request")
            raise AssertionError("raw transport request was reached")

        def close(self):
            events.append("close")

        def mutate_profile(self, *_args, **_kwargs):
            events.append("mutator")
            raise AssertionError("raw transport mutator was reached")

    raw_transport = MutationCapableRawTransport()

    def hostile_factory():
        events.append("factory")
        return raw_transport

    def hostile_closer(client):
        events.append("closer")
        client.close()

    rejected_before_invocation = False
    try:
        health._run_profile_search_health(  # noqa: SLF001
            stdout=io.StringIO(),
            preflight_loader=lambda: (None, "BINDINGS_UNAVAILABLE"),
            pipe_factory=SimpleNamespace,
            credential_reader=lambda _pipe: core.Credential(_SECRET, "stdin"),
            pipe_closer=lambda _pipe: True,
            client_factory=hostile_factory,
            client_closer=hostile_closer,
        )
    except TypeError:
        rejected_before_invocation = True

    assert events == []
    assert rejected_before_invocation is True
    assert "_ProfileSearchOnlyClient" not in health.__dict__
    assert "_ProfileSearchProxy" not in health.__dict__


def test_health_module_exports_no_injectable_transport_or_proxy_surface():
    for forbidden in (
        "_ProfileSearchOnlyClient",
        "_ProfileSearchProxy",
        "_checked_close_http_client",
    ):
        assert forbidden not in health.__dict__


def test_hermetic_run_rejects_subclassed_client_factory_before_invocation():
    events = []

    class SubclassedClient(vendors.BoundedHttpClient):
        def __init__(self):
            events.append("subclass_constructed")

    def hostile_factory():
        events.append("factory")
        return SubclassedClient()

    with pytest.raises(TypeError):
        health._run_profile_search_health(  # noqa: SLF001
            stdout=io.StringIO(),
            preflight_loader=lambda: (_provision(), None),
            pipe_factory=SimpleNamespace,
            credential_reader=lambda _pipe: core.Credential(_SECRET, "stdin"),
            pipe_closer=lambda _pipe: True,
            client_factory=hostile_factory,
        )
    assert events == []


def test_h2_uses_transport_free_vendor_census_state(monkeypatch):
    observed = {}
    original_init = vendors._ProfileSearchCensusState.__init__

    def record_init(state, *args, **kwargs):
        original_init(state, *args, **kwargs)
        observed["state"] = state

    monkeypatch.setattr(vendors._ProfileSearchCensusState, "__init__", record_init)
    code, receipt, _events, _http = _run([
        vendors._BoundedResponse(200, _payload([], 0)),
    ])
    state = observed["state"]
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert not hasattr(state, "_client")
    assert not hasattr(state, "_credential")
    assert not hasattr(state, "_mlx_profile_search_with_diagnostic")
    assert not hasattr(state, "__dict__")
    assert state._folder_id is None  # noqa: SLF001
    assert state._matches == []  # noqa: SLF001
    assert "_ProfileSearchParserFacade" not in health.__dict__


def test_h2_parser_boundary_retains_no_transport_or_authority(monkeypatch):
    captured = {}
    events = []
    out = io.StringIO()
    raw_transport = _FakeHttp([
        vendors._BoundedResponse(200, _payload([], 0)),
    ], events)
    credential = core.Credential(_SECRET, "stdin")

    original_client_init = vendors.BoundedHttpClient.__init__

    def record_client_init(client, *args, **kwargs):
        original_client_init(client, *args, **kwargs)
        captured["client"] = client

    original_request = vendors.BoundedHttpClient._request

    def record_request(client, *args, **kwargs):
        response = original_request(client, *args, **kwargs)
        captured["response"] = response
        return response

    original_sink_init = vendors._InitialPeerCensusDiagnosticSink.__init__

    def record_sink_init(sink, *args, **kwargs):
        original_sink_init(sink, *args, **kwargs)
        captured["sink"] = sink

    state_type = getattr(vendors, "_ProfileSearchCensusState", None)
    if state_type is not None:
        original_state_init = state_type.__init__

        def record_state_init(state, *args, **kwargs):
            original_state_init(state, *args, **kwargs)
            captured["state"] = state

        monkeypatch.setattr(state_type, "__init__", record_state_init)

    original_peer_candidates = vendors.MultiloginClient._peer_candidates

    def capture_peer_candidates(parser, **kwargs):
        captured["parser"] = parser
        captured["bound_callable"] = parser._mlx_profile_search_with_diagnostic
        return original_peer_candidates(parser, **kwargs)

    monkeypatch.setattr(vendors.BoundedHttpClient, "__init__", record_client_init)
    monkeypatch.setattr(vendors.BoundedHttpClient, "_request", record_request)
    monkeypatch.setattr(
        vendors._InitialPeerCensusDiagnosticSink,
        "__init__",
        record_sink_init,
    )
    monkeypatch.setattr(
        vendors.MultiloginClient,
        "_peer_candidates",
        capture_peer_candidates,
    )
    monkeypatch.setattr(vendors.httpx, "Client", lambda **_kwargs: raw_transport)

    assert health._run_profile_search_health(  # noqa: SLF001
        stdout=out,
        preflight_loader=lambda: (_provision(), None),
        pipe_factory=SimpleNamespace,
        credential_reader=lambda _pipe: credential,
        pipe_closer=lambda _pipe: True,
    ) == 0
    assert json.loads(out.getvalue())["verdict"] == "PASS"

    def authority_path(value, target, path=(), seen=None):
        seen = set() if seen is None else seen
        if value is target:
            return path
        value_id = id(value)
        if value_id in seen:
            return None
        seen.add(value_id)

        children = []
        if type(value) is dict:
            children.extend((f"key:{key!r}", item) for key, item in value.items())
        elif type(value) in (list, tuple, set, frozenset):
            children.extend((str(index), item) for index, item in enumerate(value))
        elif isinstance(value, functools.partial):
            children.extend((("partial.func", value.func), ("partial.args", value.args)))
            children.append(("partial.keywords", value.keywords))
        elif isinstance(value, types.MethodType):
            children.extend((("bound_owner", value.__self__), ("bound_function", value.__func__)))
        elif isinstance(value, types.FunctionType):
            children.extend((("defaults", value.__defaults__), ("kwdefaults", value.__kwdefaults__)))
            if value.__closure__ is not None:
                children.extend(
                    (f"closure:{index}", cell.cell_contents)
                    for index, cell in enumerate(value.__closure__)
                )
        else:
            value_dict = getattr(value, "__dict__", None)
            if type(value_dict) is dict:
                children.append(("__dict__", value_dict))
            for owner in type(value).__mro__:
                slots = owner.__dict__.get("__slots__", ())
                if type(slots) is str:
                    slots = (slots,)
                for slot in slots:
                    try:
                        children.append((f"slot:{slot}", object.__getattribute__(value, slot)))
                    except AttributeError:
                        pass

        for label, child in children:
            found = authority_path(child, target, path + (label,), seen)
            if found is not None:
                return found
        return None

    parser_roots = [
        captured[key]
        for key in ("bound_callable", "parser", "state")
        if key in captured
    ]
    assert parser_roots
    for parser_root in parser_roots:
        for target in (
            captured["client"],
            raw_transport,
            credential,
            captured["sink"],
            captured["response"],
        ):
            assert authority_path(parser_root, target) is None


def test_shared_census_state_has_transactional_two_page_parity_and_scrubs():
    first_id = "00000000-0000-4000-8000-00000000000a"
    second_id = "00000000-0000-4000-8000-00000000000b"
    state = _census_state()
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row(first_id)], 2),
    ))
    assert state.next_offset == 1
    assert state.complete is False
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row(second_id)], 2),
    ))
    assert state.complete is True
    assert state.finish() == [
        _profile_row(first_id),
        _profile_row(second_id),
    ]
    assert state._folder_id is None  # noqa: SLF001
    assert state._peer_name is None  # noqa: SLF001
    assert state._offset is None  # noqa: SLF001
    assert state._expected_total is None  # noqa: SLF001
    assert state._seen_ids == set()  # noqa: SLF001
    assert state._matches == []  # noqa: SLF001
    assert state._complete is False  # noqa: SLF001
    with pytest.raises(core.CanaryRefusal):
        state.finish()
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(200, _payload([], 0)))


def test_shared_census_state_h2_discard_mode_retains_no_rows():
    state = _census_state(peer_name=None)
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row(name="unrelated")], 1),
    ))
    assert state.finish() == []


def test_shared_census_state_is_transactional_after_a_malformed_later_row():
    state = _census_state()
    malformed = _profile_row(
        "00000000-0000-4000-8000-00000000000a",
    )
    malformed["id"] = "not-a-uuid"
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(
            200,
            _payload([
                _profile_row("00000000-0000-4000-8000-00000000000b"),
                malformed,
            ], 2),
        ))
    assert state._expected_total is None  # noqa: SLF001
    assert state.next_offset == 0
    assert state._seen_ids == set()  # noqa: SLF001
    assert state._matches == []  # noqa: SLF001
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row("00000000-0000-4000-8000-00000000000c")], 1),
    ))
    assert state.finish() == [_profile_row("00000000-0000-4000-8000-00000000000c")]


@pytest.mark.parametrize(
    ("response", "diagnostic", "code"),
    (
        (vendors._BoundedResponse(401, {}), "NONE", "AUTH_EXPIRED"),
        (vendors._BoundedResponse(403, {}), "NONE", "AUTH_EXPIRED"),
        (vendors._BoundedResponse(429, {}), "HTTP_RATE_LIMITED", "VENDOR_ERROR"),
        (vendors._BoundedResponse(422, {}), "HTTP_REQUEST_REJECTED", "VENDOR_ERROR"),
        (vendors._BoundedResponse(503, {}), "HTTP_SERVICE_UNAVAILABLE", "VENDOR_ERROR"),
        (vendors._BoundedResponse(299, {}), "HTTP_UNEXPECTED", "VENDOR_ERROR"),
        (vendors._BoundedResponse(200, {"status": {}, "data": {}}), "STATUS_ENVELOPE_INVALID", "VENDOR_ERROR"),
        (vendors._BoundedResponse(200, _payload("not-a-list", 0)), "DATA_SCHEMA_INVALID", "VENDOR_ERROR"),
        (vendors._BoundedResponse(200, _payload([], True)), "DATA_SCHEMA_INVALID", "VENDOR_ERROR"),
        (vendors._BoundedResponse(200, _payload([], -1)), "DATA_SCHEMA_INVALID", "VENDOR_ERROR"),
        (vendors._BoundedResponse(200, _payload([], vendors._MAX_PROFILE_CENSUS + 1)), "DATA_SCHEMA_INVALID", "VENDOR_ERROR"),
    ),
)
def test_shared_census_state_preserves_closed_status_and_shape_diagnostics(
    response, diagnostic, code,
):
    state = _census_state()
    sink = vendors._InitialPeerCensusDiagnosticSink(
        vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,
    )
    with pytest.raises(core.CanaryRefusal) as raised:
        state.consume(response, diagnostic_sink=sink)
    assert raised.value.code == code
    assert sink.value == diagnostic
    assert state.next_offset == 0


def test_shared_census_state_rejects_total_drift_duplicate_and_incomplete_pages():
    state = _census_state()
    first_id = "00000000-0000-4000-8000-00000000000a"
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row(first_id)], 2),
    ))
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(
            200,
            _payload([_profile_row("00000000-0000-4000-8000-00000000000b")], 3),
        ))
    assert state.next_offset == 1
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(
            200,
            _payload([_profile_row(first_id)], 2),
        ))
    assert state.next_offset == 1

    empty_page = _census_state()
    with pytest.raises(core.CanaryRefusal):
        _consume_census(empty_page, vendors._BoundedResponse(200, _payload([], 1)))
    assert empty_page.next_offset == 0

    over_page = _census_state()
    rows = [
        _profile_row(f"00000000-0000-4000-8000-{index:012x}")
        for index in range(vendors._PROFILE_PAGE_SIZE + 1)
    ]
    with pytest.raises(core.CanaryRefusal):
        _consume_census(over_page, vendors._BoundedResponse(
            200,
            _payload(rows, len(rows)),
        ))


def test_shared_census_state_canonicalizes_uppercase_ids_and_completes_at_cap():
    upper_folder = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"
    upper_profile = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDE0"
    state = _census_state(folder_id=upper_folder)
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row(upper_profile, upper_folder)], 1),
    ))
    assert state.finish()[0]["id"] == upper_profile.lower()

    at_cap = _census_state(peer_name=None)
    for offset in range(0, vendors._MAX_PROFILE_CENSUS, vendors._PROFILE_PAGE_SIZE):
        rows = [
            _profile_row(
                f"00000000-0000-4000-8000-{index:012x}",
                name="discard",
            )
            for index in range(offset, offset + vendors._PROFILE_PAGE_SIZE)
        ]
        _consume_census(at_cap, vendors._BoundedResponse(
            200,
            _payload(rows, vendors._MAX_PROFILE_CENSUS),
        ))
    assert at_cap.complete is True
    assert at_cap.finish() == []


@pytest.mark.parametrize(
    "extra",
    (
        {"custom": object()},
        {"callable": lambda: None},
        {"nan": math.nan},
        {"nested": {"deep": [object()]}},
    ),
)
def test_shared_census_state_rejects_non_json_matching_values(extra):
    state = _census_state()
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(
            200,
            _payload([_profile_row(**extra)], 1),
        ))
    assert state.next_offset == 0


def test_shared_census_state_rejects_matching_aliases_but_not_unmatched_extras():
    shared = []
    aliased = _profile_row(nested={"left": shared, "right": shared})
    state = _census_state()
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(200, _payload([aliased], 1)))

    discard = _census_state(peer_name=None)
    _consume_census(discard, vendors._BoundedResponse(
        200,
        _payload([_profile_row(name="other", hostile=object())], 1),
    ))
    assert discard.finish() == []


def test_shared_census_state_copies_nested_matching_rows_at_consume_time():
    source = _profile_row(nested={"metadata": {"value": "before"}})
    state = _census_state()
    _consume_census(state, vendors._BoundedResponse(200, _payload([source], 1)))

    source["nested"]["metadata"]["value"] = "after"
    source["nested"]["metadata"]["new"] = "mutated"

    assert state.finish() == [
        _profile_row(nested={"metadata": {"value": "before"}}),
    ]


def _matching_row_with_exact_json_nodes(nodes):
    assert nodes >= 7
    return _profile_row(payload=[None] * (nodes - 7))


def _matching_row_with_exact_json_depth(depth):
    assert depth >= 1
    value = None
    for _ in range(depth - 1):
        value = {"next": value}
    return _profile_row(payload=value)


@pytest.mark.parametrize(
    "row",
    (
        _matching_row_with_exact_json_nodes(vendors._PROFILE_ITEM_COPY_MAX_NODES),
        _matching_row_with_exact_json_depth(vendors._PROFILE_ITEM_COPY_MAX_DEPTH),
    ),
    ids=("exact_node_limit", "exact_depth_limit"),
)
def test_shared_census_state_finish_preserves_exact_per_item_copy_limits(row):
    state = _census_state()
    _consume_census(state, vendors._BoundedResponse(200, _payload([row], 1)))
    assert state.finish() == [row]


def test_shared_census_state_finish_accepts_full_matching_census_without_aggregate_limit():
    state = _census_state()
    for offset in range(0, vendors._MAX_PROFILE_CENSUS, vendors._PROFILE_PAGE_SIZE):
        rows = [
            _profile_row(f"00000000-0000-4000-8000-{index:012x}")
            for index in range(offset, offset + vendors._PROFILE_PAGE_SIZE)
        ]
        _consume_census(state, vendors._BoundedResponse(
            200,
            _payload(rows, vendors._MAX_PROFILE_CENSUS),
        ))
    result = state.finish()
    assert len(result) == vendors._MAX_PROFILE_CENSUS
    assert result[0]["id"] == "00000000-0000-4000-8000-000000000000"
    assert result[-1]["id"] == "00000000-0000-4000-8000-0000000003e7"


@pytest.mark.parametrize(
    "row",
    (
        _matching_row_with_exact_json_nodes(vendors._PROFILE_ITEM_COPY_MAX_NODES + 1),
        _matching_row_with_exact_json_depth(vendors._PROFILE_ITEM_COPY_MAX_DEPTH + 1),
    ),
    ids=("one_over_node_limit", "one_over_depth_limit"),
)
def test_shared_census_state_rejects_one_over_per_item_copy_limits(row):
    state = _census_state()
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(200, _payload([row], 1)))
    assert state.next_offset == 0
    assert state._matches == []  # noqa: SLF001


@pytest.mark.parametrize(
    "extra",
    (
        {"scalar_subclass": type("ExactStringSubclass", (str,), {})("value")},
        {"container_subclass": type("ExactListSubclass", (list,), {})([None])},
        {"mapping_subclass": type("ExactDictSubclass", (dict,), {})(value="value")},
    ),
)
def test_shared_census_state_rejects_matching_exact_json_subclasses(extra):
    state = _census_state()
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(
            200,
            _payload([_profile_row(**extra)], 1),
        ))
    assert state.next_offset == 0
    assert state._matches == []  # noqa: SLF001


def test_shared_census_state_refuses_before_and_after_exact_completion():
    state = _census_state()
    with pytest.raises(core.CanaryRefusal):
        state.finish()
    assert state.next_offset == 0

    row = _profile_row()
    _consume_census(state, vendors._BoundedResponse(200, _payload([row], 1)))
    with pytest.raises(core.CanaryRefusal):
        _consume_census(state, vendors._BoundedResponse(200, _payload([], 1)))
    assert state.finish() == [row]


def test_shared_census_state_scrubs_on_unexpected_finish_copy_failure():
    state = _census_state()
    _consume_census(state, vendors._BoundedResponse(
        200,
        _payload([_profile_row()], 1),
    ))
    state._matches = [object()]  # noqa: SLF001 - deliberate private-state corruption
    with pytest.raises(core.CanaryRefusal) as raised:
        state.finish()
    assert raised.value.code == "VENDOR_ERROR"
    assert state._finished is True  # noqa: SLF001
    assert state._folder_id is None  # noqa: SLF001
    assert state._matches == []  # noqa: SLF001


def test_profile_search_request_builder_matches_canonical_vendor_dispatch(monkeypatch):
    credential = core.Credential(_SECRET, "stdin")
    sink = vendors._InitialPeerCensusDiagnosticSink(
        vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,
    )
    expected = vendors._mlx_profile_search_request_arguments(  # noqa: SLF001
        credential,
        _FOLDER,
        offset=0,
        diagnostic_sink=sink,
    )
    observed = {}

    def record_request(_client, *args, **kwargs):
        observed["arguments"] = (*args, kwargs)
        return vendors._BoundedResponse(200, _payload([], 0))

    monkeypatch.setattr(vendors.BoundedHttpClient, "_request", record_request)
    client = vendors.BoundedHttpClient(client=_FakeHttp([]))
    client._mlx_profile_search_request(
        credential,
        _FOLDER,
        offset=0,
        diagnostic_sink=sink,
    )
    method, origin, path, headers, params, body, actual_sink = expected
    assert observed["arguments"] == (
        method,
        origin,
        path,
        {
            "headers": headers,
            "params": params,
            "json_body": body,
            "diagnostic_sink": actual_sink,
        },
    )


def test_h2_uses_the_shared_profile_search_request_builder(monkeypatch):
    calls = []
    original_builder = vendors._mlx_profile_search_request_arguments

    def record_builder(*args, **kwargs):
        request = original_builder(*args, **kwargs)
        calls.append(request)
        return request

    monkeypatch.setattr(
        vendors,
        "_mlx_profile_search_request_arguments",
        record_builder,
    )
    code, receipt, _events, _http = _run([
        vendors._BoundedResponse(200, _payload([], 0)),
    ])
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert len(calls) == 1
    method, origin, path, headers, params, body, sink = calls[0]
    assert health._is_exact_profile_search_request(  # noqa: SLF001
        method,
        origin,
        path,
        headers=headers,
        params=params,
        json_body=body,
        diagnostic_sink=sink,
    ) is True


def test_h2_refuses_malformed_shared_builder_result_before_any_dispatch(monkeypatch):
    class PermissiveRawTransport:
        def __init__(self):
            self.calls = []
            self.closed = 0

        def stream(self, method, url, *, headers=None, params=None, json=None):
            self.calls.append((method, url, headers, params, json))
            return _FakeWireResponse(vendors._BoundedResponse(200, _payload([], 0)))

        def close(self):
            self.closed += 1

    raw_transport = PermissiveRawTransport()
    original_builder = vendors._mlx_profile_search_request_arguments

    def malformed_builder(*args, **kwargs):
        request = list(original_builder(*args, **kwargs))
        request[0] = "GET"
        return tuple(request)

    monkeypatch.setattr(vendors.httpx, "Client", lambda **_kwargs: raw_transport)
    monkeypatch.setattr(
        vendors,
        "_mlx_profile_search_request_arguments",
        malformed_builder,
    )
    out = io.StringIO()
    assert health._run_profile_search_health(  # noqa: SLF001
        stdout=out,
        preflight_loader=lambda: (_provision(), None),
        pipe_factory=SimpleNamespace,
        credential_reader=lambda _pipe: core.Credential(_SECRET, "stdin"),
        pipe_closer=lambda _pipe: True,
    ) == 2
    assert json.loads(out.getvalue()) == health._receipt("VENDOR_ERROR")
    assert raw_transport.calls == []
    assert raw_transport.closed == 1


def test_h2_refuses_subclassed_builder_before_hooks_or_dispatch(monkeypatch):
    events = []

    class HostileHeaders(dict):
        def get(self, *args, **kwargs):
            events.append("headers_get")
            return super().get(*args, **kwargs)

        def __iter__(self):
            events.append("headers_iter")
            return super().__iter__()

        def items(self):
            events.append("headers_items")
            return super().items()

    class PermissiveRawTransport:
        def __init__(self):
            self.calls = []
            self.closed = 0

        def stream(self, method, url, *, headers=None, params=None, json=None):
            self.calls.append((method, url, headers, params, json))
            return _FakeWireResponse(vendors._BoundedResponse(200, _payload([], 0)))

        def close(self):
            self.closed += 1

    raw_transport = PermissiveRawTransport()
    original_builder = vendors._mlx_profile_search_request_arguments

    def malicious_builder(*args, **kwargs):
        request = list(original_builder(*args, **kwargs))
        request[3] = HostileHeaders(request[3])
        return tuple(request)

    monkeypatch.setattr(vendors.httpx, "Client", lambda **_kwargs: raw_transport)
    monkeypatch.setattr(
        vendors,
        "_mlx_profile_search_request_arguments",
        malicious_builder,
    )
    out = io.StringIO()
    result = health._run_profile_search_health(  # noqa: SLF001
        stdout=out,
        preflight_loader=lambda: (_provision(), None),
        pipe_factory=SimpleNamespace,
        credential_reader=lambda _pipe: core.Credential(_SECRET, "stdin"),
        pipe_closer=lambda _pipe: True,
    )
    assert events == []
    assert result == 2
    assert json.loads(out.getvalue()) == health._receipt("VENDOR_ERROR")
    assert raw_transport.calls == []
    assert raw_transport.closed == 1


@pytest.mark.parametrize(
    ("responses", "expected_code"),
    (
        ([vendors._BoundedResponse(200, _payload([], 0))], "OK"),
        ([RuntimeError("private transport failure")], "VENDOR_ERROR"),
    ),
)
def test_h2_scrubs_authority_from_the_final_emission_frame(
    monkeypatch, responses, expected_code,
):
    target_ids = set()
    leaks = []
    raw_transport = _FakeHttp(responses, [])
    credential = core.Credential(_SECRET, "stdin")
    provision = _provision()
    target_ids.update((id(raw_transport), id(credential), id(provision)))

    class InspectingStdout:
        __slots__ = ("_target_ids", "_leaks", "_rendered")

        def __init__(self):
            self._target_ids = target_ids
            self._leaks = leaks
            self._rendered = ""

        def write(self, text):
            frame = inspect.currentframe().f_back
            while frame is not None and frame.f_code.co_name != "_run_profile_search_health":
                frame = frame.f_back
            assert frame is not None

            def finds_target(value, seen=None):
                seen = set() if seen is None else seen
                if id(value) in self._target_ids:
                    return True
                value_id = id(value)
                if value_id in seen:
                    return False
                seen.add(value_id)
                if type(value) is dict:
                    return any(finds_target(item, seen) for item in value.values())
                if type(value) in (list, tuple, set, frozenset):
                    return any(finds_target(item, seen) for item in value)
                if isinstance(value, functools.partial):
                    return (
                        finds_target(value.func, seen)
                        or finds_target(value.args, seen)
                        or finds_target(value.keywords, seen)
                    )
                if isinstance(value, types.MethodType):
                    return (
                        finds_target(value.__self__, seen)
                        or finds_target(value.__func__, seen)
                    )
                if isinstance(value, types.FunctionType):
                    if finds_target(value.__defaults__, seen) or finds_target(value.__kwdefaults__, seen):
                        return True
                    return value.__closure__ is not None and any(
                        finds_target(cell.cell_contents, seen)
                        for cell in value.__closure__
                    )
                value_dict = getattr(value, "__dict__", None)
                if type(value_dict) is dict and finds_target(value_dict, seen):
                    return True
                for owner in type(value).__mro__:
                    slots = owner.__dict__.get("__slots__", ())
                    if type(slots) is str:
                        slots = (slots,)
                    for slot in slots:
                        try:
                            if finds_target(object.__getattribute__(value, slot), seen):
                                return True
                        except AttributeError:
                            pass
                return False

            self._leaks.extend(
                name for name, value in frame.f_locals.items()
                if finds_target(value)
            )
            self._rendered += text
            return len(text)

    original_client_init = vendors.BoundedHttpClient.__init__

    def record_client_init(client, *args, **kwargs):
        original_client_init(client, *args, **kwargs)
        target_ids.add(id(client))

    original_sink_init = vendors._InitialPeerCensusDiagnosticSink.__init__

    def record_sink_init(sink, *args, **kwargs):
        original_sink_init(sink, *args, **kwargs)
        target_ids.add(id(sink))

    original_state_init = vendors._ProfileSearchCensusState.__init__

    def record_state_init(state, *args, **kwargs):
        original_state_init(state, *args, **kwargs)
        target_ids.add(id(state))

    original_request = vendors.BoundedHttpClient._request

    def record_request(client, *args, **kwargs):
        response = original_request(client, *args, **kwargs)
        if response is not None:
            target_ids.add(id(response))
        return response

    original_builder = vendors._mlx_profile_search_request_arguments

    def record_builder(*args, **kwargs):
        request = original_builder(*args, **kwargs)
        target_ids.update((id(request[3]), id(request[5])))
        return request

    monkeypatch.setattr(vendors.BoundedHttpClient, "__init__", record_client_init)
    monkeypatch.setattr(vendors.BoundedHttpClient, "_request", record_request)
    monkeypatch.setattr(vendors._InitialPeerCensusDiagnosticSink, "__init__", record_sink_init)
    monkeypatch.setattr(vendors._ProfileSearchCensusState, "__init__", record_state_init)
    monkeypatch.setattr(vendors.httpx, "Client", lambda **_kwargs: raw_transport)
    monkeypatch.setattr(vendors, "_mlx_profile_search_request_arguments", record_builder)

    stdout = InspectingStdout()
    assert health._run_profile_search_health(  # noqa: SLF001
        stdout=stdout,
        preflight_loader=lambda: (provision, None),
        pipe_factory=SimpleNamespace,
        credential_reader=lambda _pipe: credential,
        pipe_closer=lambda _pipe: True,
    ) == (0 if expected_code == "OK" else 2)
    assert json.loads(stdout._rendered)["code"] == expected_code
    assert leaks == []


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


def test_profile_search_request_guard_refuses_non_search_shapes_before_http():
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
    canonical = {
        "method": "POST",
        "origin": vendors._MLX_CLOUD_ORIGIN,
        "path": "/profile/search",
        "headers": {"Authorization": f"Bearer {_SECRET}"},
        "params": None,
        "json_body": canonical_body,
    }

    def invoke(request):
        sink = vendors._InitialPeerCensusDiagnosticSink(
            vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,
        )
        return health._is_exact_profile_search_request(  # noqa: SLF001
            **request,
            diagnostic_sink=sink,
        )

    assert invoke(canonical) is True

    attempts = [
        {**canonical, "method": "GET"},
        {**canonical, "origin": "https://example.invalid"},
        {**canonical, "path": "/profile/create"},
        {**canonical, "params": {}},
        {**canonical, "headers": {}},
        {**canonical, "headers": {**canonical["headers"], "X-Extra": "x"}},
    ]
    for key, value in (
        ("is_removed", True), ("limit", 1), ("offset", -1),
        ("offset", True), ("offset", vendors._MAX_PROFILE_CENSUS),
        ("search_text", "x"), ("storage_type", "local"),
        ("order_by", "name"), ("sort", "desc"), ("folder_id", ""),
        ("extra", "x"),
    ):
        attempts.append({**canonical, "json_body": {**canonical_body, key: value}})
    attempts.append({
        **canonical,
        "json_body": {key: value for key, value in canonical_body.items() if key != "folder_id"},
    })
    for request in attempts:
        assert invoke(request) is False


def test_profile_search_request_guard_refuses_subclass_hooks_before_behavior():
    events = []

    class HostileText(str):
        def __eq__(self, other):
            events.append("text_eq")
            return super().__eq__(other)

        def __hash__(self):
            events.append("text_hash")
            return super().__hash__()

        def startswith(self, prefix, *args):
            events.append("text_startswith")
            return super().startswith(prefix, *args)

        def __bool__(self):
            events.append("text_bool")
            return super().__bool__()

    class HostileDict(dict):
        def get(self, *args, **kwargs):
            events.append("dict_get")
            return super().get(*args, **kwargs)

        def __iter__(self):
            events.append("dict_iter")
            return super().__iter__()

        def items(self):
            events.append("dict_items")
            return super().items()

        def __getitem__(self, key):
            events.append("dict_getitem")
            return super().__getitem__(key)

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
    canonical = {
        "method": "POST",
        "origin": vendors._MLX_CLOUD_ORIGIN,
        "path": "/profile/search",
        "headers": {"Authorization": f"Bearer {_SECRET}"},
        "params": None,
        "json_body": canonical_body,
    }

    def invoke(request):
        sink = vendors._InitialPeerCensusDiagnosticSink(
            vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,
        )
        return health._is_exact_profile_search_request(  # noqa: SLF001
            **request,
            diagnostic_sink=sink,
        )

    hostile_header_key = HostileText("Authorization")
    hostile_key_headers = {hostile_header_key: canonical["headers"]["Authorization"]}
    attempts = [
        {**canonical, "method": HostileText("POST")},
        {**canonical, "headers": HostileDict(canonical["headers"])},
        {**canonical, "headers": hostile_key_headers},
        {**canonical, "headers": {"Authorization": HostileText(f"Bearer {_SECRET}")}},
        {**canonical, "json_body": HostileDict(canonical_body)},
        {
            **canonical,
            "json_body": {**canonical_body, "search_text": HostileText("")},
        },
    ]
    for request in attempts:
        events.clear()
        refused = invoke(request)
        assert events == []
        assert refused is False


def test_hermetic_run_closes_the_exact_canonical_client_once():
    code, receipt, events, http = _run([
        vendors._BoundedResponse(200, _payload([], 0)),
    ])
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert events[-1] == "client_close"
    assert http.closed == 1


def test_hermetic_run_rejects_client_cleanup_injection_before_transport():
    events = []

    def hostile_closer(_client):
        events.append("close")
        return True

    with pytest.raises(TypeError):
        health._run_profile_search_health(  # noqa: SLF001
            stdout=io.StringIO(),
            preflight_loader=lambda: (_provision(), None),
            pipe_factory=SimpleNamespace,
            credential_reader=lambda _pipe: core.Credential(_SECRET, "stdin"),
            pipe_closer=lambda _pipe: True,
            client_closer=hostile_closer,
        )
    assert events == []


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
    assert observed["pipe_closer"] is health._checked_close_keychain_pipe
    assert set(observed) == {
        "stdout",
        "preflight_loader",
        "pipe_factory",
        "credential_reader",
        "pipe_closer",
    }


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


def test_request_cancellation_emits_one_closed_receipt_after_http_cleanup():
    code, receipt, events, fake_http = _run([
        KeyboardInterrupt("private cancellation detail"),
    ])
    assert code == 2
    assert receipt == health._receipt("VENDOR_ERROR")
    assert set(receipt) == _KEYS
    assert events == ["pipe_open", "credential_read", "pipe_close", "client_open", "search:0", "client_close"]
    assert fake_http.search_calls == 1
    assert fake_http.closed == 1

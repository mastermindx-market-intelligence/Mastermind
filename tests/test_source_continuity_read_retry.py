"""Bounded in-place retry of idempotent GitHub reads; no real HTTP or token."""
from __future__ import annotations

import email.message
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
from http.client import BadStatusLine, IncompleteRead, InvalidURL, RemoteDisconnected
from urllib.error import HTTPError, URLError

import pytest

import test_source_continuity as fx
import test_source_continuity_census_budget as budget
import test_source_continuity_macro_scale as scale
import test_source_continuity_writer_gate as gate


SUBJECT = f"repos/{fx.REPOSITORY}/pulls/{fx.PR_NUMBER}"
SUBJECT_URL = f"{fx.API_ROOT}/{SUBJECT}"
HEAD_COMMIT = f"repos/{fx.REPOSITORY}/git/commits/{fx.HEAD_SHA}"
HEAD_COMMIT_URL = f"{fx.API_ROOT}/{HEAD_COMMIT}"


class Sleeper:
    """Stands in for `time.sleep`: records each backoff and advances the clock."""

    def __init__(self, clock):
        self.clock = clock
        self.delays = []

    def __call__(self, delay):
        self.delays.append(delay)
        self.clock.now += delay


def _patch_time(module, monkeypatch):
    clock = budget.Clock()
    sleeper = Sleeper(clock)
    monkeypatch.setattr(module, "monotonic", clock)
    monkeypatch.setattr(module, "sleep", sleeper)
    return clock, sleeper


def _error(module, cause, *, transient=False, kind="probe"):
    error_type = {
        "probe": module._RemoteProbeError,
        "auth": module._AuthProbeError,
        "missing": module._RemoteResourceMissing,
    }[kind]
    return module._labelled(error_type(), cause, transient=transient)


class Flaky:
    """Raises queued failures on reads of one URL, then delegates to `base`."""

    def __init__(self, base, url, failures, *, conditional_only=False, on_failure=None):
        self.base = base
        self.url = url
        self.failures = list(failures)
        self.conditional_only = conditional_only
        self.on_failure = on_failure
        self.target_reads = 0
        for name in ("_source_continuity_conditional", "_source_continuity_parallel_safe"):
            if getattr(base, name, False) is True:
                setattr(self, name, True)

    def __call__(self, url, **kwargs):
        if url == self.url and (
            not self.conditional_only or kwargs.get("if_none_match") is not None
        ):
            self.target_reads += 1
            if self.failures:
                failure = self.failures.pop(0)
                if self.on_failure is not None:
                    self.on_failure()
                raise failure
        return self.base(url, **kwargs)


def _subject_reads(http):
    return sum(1 for url, _, _ in http.calls if url == SUBJECT_URL)


def _diagnostic(cause, attempts, retryable, *, endpoint=SUBJECT, failed=1, recovered=0):
    return {
        "endpoint": endpoint,
        "cause": cause,
        "attempts": attempts,
        "retryable": retryable,
        "failed_reads": failed,
        "recovered_reads": recovered,
    }


def _baseline(module, capsys, monkeypatch):
    _patch_time(module, monkeypatch)
    control = budget.EstateHTTP(1)
    rc, payload = budget.run_cli(module, capsys, control)
    assert rc == 0, payload
    return control, payload


# --- CLI: a transient failure is repeated in place and leaves the receipt unchanged.


@pytest.mark.parametrize(
    "causes",
    [("timeout",), ("connection",), ("http_502",), ("incomplete_response", "http_503")],
)
def test_transient_failure_recovers_with_identical_receipt(causes, capsys, monkeypatch):
    module = fx._cli_module()
    control, expected = _baseline(module, capsys, monkeypatch)
    _, sleeper = _patch_time(module, monkeypatch)
    base = budget.EstateHTTP(1)
    http = Flaky(
        base, SUBJECT_URL, [_error(module, cause, transient=True) for cause in causes]
    )
    rc, payload = budget.run_cli(module, capsys, http)

    assert rc == 0, payload
    assert payload == expected
    assert sleeper.delays == [1.0, 2.0][: len(causes)]
    assert len(base.calls) == len(control.calls)
    assert http.target_reads == _subject_reads(control) + len(causes)


def test_three_transient_failures_refuse_and_name_the_read(capsys, monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    http = Flaky(
        budget.EstateHTTP(1),
        SUBJECT_URL,
        [_error(module, "http_503", transient=True) for _ in range(3)],
    )
    rc, payload = budget.run_cli(
        module, capsys, http, read_failure=_diagnostic("http_503", 3, True)
    )
    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert http.target_reads == 3
    assert sleeper.delays == [1.0, 2.0]


@pytest.mark.parametrize(
    ("kind", "cause", "code"),
    [
        ("auth", "http_401", "AUTH_UNAVAILABLE"),
        ("auth", "http_403", "AUTH_UNAVAILABLE"),
        ("probe", "http_429", "REMOTE_PROBE_FAILED"),
        ("probe", "http_422", "REMOTE_PROBE_FAILED"),
        ("probe", "http_501", "REMOTE_PROBE_FAILED"),
        ("probe", "body_too_large", "REMOTE_PROBE_FAILED"),
        ("probe", "invalid_json", "REMOTE_PROBE_FAILED"),
        ("probe", "missing_etag", "REMOTE_PROBE_FAILED"),
        ("probe", "tls_verify", "REMOTE_PROBE_FAILED"),
        # A required resource that is absent fails; only optional reads may be absent.
        ("missing", "http_404", "REMOTE_PROBE_FAILED"),
    ],
)
def test_non_transient_failure_is_read_once(kind, cause, code, capsys, monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    http = Flaky(budget.EstateHTTP(1), SUBJECT_URL, [_error(module, cause, kind=kind)])
    rc, payload = budget.run_cli(
        module, capsys, http, read_failure=_diagnostic(cause, 1, False)
    )
    assert rc == 2 and payload["code"] == code
    assert http.target_reads == 1
    assert sleeper.delays == []


@pytest.mark.parametrize(
    ("make_error", "code"),
    [
        (lambda module: module._RemoteProbeError(), "REMOTE_PROBE_FAILED"),
        (lambda module: RuntimeError("transport bug"), "PROBE_INTERNAL_ERROR"),
    ],
)
def test_unlabelled_failure_is_unclassified_and_read_once(
    make_error, code, capsys, monkeypatch
):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    http = Flaky(budget.EstateHTTP(1), SUBJECT_URL, [make_error(module)])
    rc, payload = budget.run_cli(
        module, capsys, http, read_failure=_diagnostic("unclassified", 1, False)
    )
    assert rc == 2 and payload["code"] == code
    assert http.target_reads == 1
    assert sleeper.delays == []


def test_diagnostic_never_carries_the_token_or_a_foreign_cause(capsys, monkeypatch):
    module = fx._cli_module()
    _patch_time(module, monkeypatch)
    error = module._labelled(
        module._RemoteProbeError(f"Bearer {fx.TOKEN}"), fx.TOKEN, transient=True
    )
    http = Flaky(budget.EstateHTTP(1), SUBJECT_URL, [error, error, error])
    exit_code = fx._run_cli(module, fx._cli_argv(), http=http)
    captured = capsys.readouterr()
    assert exit_code == 2
    assert fx.TOKEN not in captured.err and fx.TOKEN not in captured.out
    assert json.loads(captured.err) == {
        "diagnostic": "READ_FAILED",
        **_diagnostic("unclassified", 3, True),
    }


class _BrokenStream:
    def write(self, _text):
        raise BrokenPipeError()

    def flush(self):
        raise BrokenPipeError()


@pytest.mark.parametrize("stream", [None, _BrokenStream()])
def test_unwritable_stderr_keeps_the_single_receipt(stream, capsys, monkeypatch):
    module = fx._cli_module()
    _patch_time(module, monkeypatch)
    http = Flaky(
        budget.EstateHTTP(1),
        SUBJECT_URL,
        [_error(module, "http_503", transient=True) for _ in range(3)],
    )
    monkeypatch.setattr(module.sys, "stderr", stream)
    exit_code = fx._run_cli(module, fx._cli_argv(), http=http)
    monkeypatch.undo()
    lines = capsys.readouterr().out.splitlines()
    assert exit_code == 2
    assert len(lines) == 1
    assert json.loads(lines[0])["code"] == "REMOTE_PROBE_FAILED"


_CLOSED_PIPE_CHILD = """
import sys
sys.path.insert(0, {tests!r})
import test_source_continuity as fx
import test_source_continuity_census_budget as budget
import test_source_continuity_read_retry as retry
module = fx._cli_module()
module.sleep = lambda _delay: None
http = retry.Flaky(
    budget.EstateHTTP(1),
    retry.SUBJECT_URL,
    [retry._error(module, "http_503", transient=True) for _ in range(3)],
)
raise SystemExit(fx._run_cli(module, fx._cli_argv(), http=http))
"""


def test_closed_stderr_pipe_keeps_the_refusal_exit_code():
    # A real pipe with no reader: the failed diagnostic stays buffered, and
    # without the repair the exit-time flush turns rc 2 into rc 120.
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-W",
                "ignore",
                "-c",
                _CLOSED_PIPE_CHILD.format(tests=str(Path(__file__).resolve().parent)),
            ],
            stdout=subprocess.PIPE,
            stderr=write_end,
            timeout=120,
            check=False,
        )
    finally:
        os.close(write_end)
    lines = completed.stdout.decode().splitlines()
    assert completed.returncode == 2
    assert len(lines) == 1
    assert json.loads(lines[0])["code"] == "REMOTE_PROBE_FAILED"


# --- The shared call and time budgets bound every attempt.


def test_retry_attempts_are_calls_against_the_shared_budget(capsys, monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    monkeypatch.setattr(module, "_MAX_HTTP_CALLS", 2)
    http = Flaky(
        budget.EstateHTTP(1),
        SUBJECT_URL,
        [_error(module, "timeout", transient=True) for _ in range(3)],
    )
    rc, payload = budget.run_cli(
        module, capsys, http, read_failure=_diagnostic("timeout", 2, True)
    )
    # The retry that cannot be afforded keeps the refusal the failure earned.
    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert http.target_reads == 2
    assert sleeper.delays == [1.0]


def test_recovered_attempt_spends_exactly_one_more_call(capsys, monkeypatch):
    module = fx._cli_module()
    control, _ = _baseline(module, capsys, monkeypatch)
    for cap, expected_rc in ((len(control.calls), 2), (len(control.calls) + 1, 0)):
        _patch_time(module, monkeypatch)
        monkeypatch.setattr(module, "_MAX_HTTP_CALLS", cap)
        http = Flaky(
            budget.EstateHTTP(1), SUBJECT_URL, [_error(module, "timeout", transient=True)]
        )
        rc, payload = budget.run_cli(module, capsys, http)
        assert rc == expected_rc, (cap, payload)
        if rc:
            assert payload["code"] == "REMOTE_CENSUS_INCOMPLETE"


def test_backoff_that_would_cross_the_deadline_refuses_without_sleeping(
    capsys, monkeypatch
):
    module = fx._cli_module()
    # Backoff 1.0 s plus the 2.0 s minimum call window must stay short of the deadline.
    window = 1.0 + module._HTTP_RETRY_MIN_CALL_SECONDS
    for remaining, affordable in ((window, False), (window + 0.01, True)):
        clock, sleeper = _patch_time(module, monkeypatch)

        def late(clock=clock, remaining=remaining):
            clock.now = module._HTTP_READ_BUDGET_SECONDS - remaining

        http = Flaky(
            budget.EstateHTTP(1),
            SUBJECT_URL,
            [_error(module, "timeout", transient=True)],
            on_failure=late,
        )
        if affordable:
            rc, payload = budget.run_cli(module, capsys, http)
            assert rc == 0, payload
            assert sleeper.delays == [1.0]
            assert http.target_reads == _subject_reads(http.base) + 1
        else:
            rc, payload = budget.run_cli(
                module, capsys, http, read_failure=_diagnostic("timeout", 1, True)
            )
            assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
            assert sleeper.delays == []
            assert http.target_reads == 1


# --- Conditional replays, parallel census reads and lawful absences.


def test_conditional_replay_is_retried(capsys, monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    base = scale.ConditionalEstateHTTP(module, 1)
    http = Flaky(
        base,
        HEAD_COMMIT_URL,
        [_error(module, "connection", transient=True)],
        conditional_only=True,
    )
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 0, payload
    assert sleeper.delays == [1.0]
    assert http.target_reads == 2
    assert base.conditional_calls.count(HEAD_COMMIT_URL) == 1


def test_conditional_replay_exhaustion_names_the_replayed_read(capsys, monkeypatch):
    module = fx._cli_module()
    _patch_time(module, monkeypatch)
    http = Flaky(
        scale.ConditionalEstateHTTP(module, 1),
        HEAD_COMMIT_URL,
        [_error(module, "http_500", transient=True) for _ in range(3)],
        conditional_only=True,
    )
    rc, payload = budget.run_cli(
        module,
        capsys,
        http,
        read_failure=_diagnostic("http_500", 3, True, endpoint=HEAD_COMMIT),
    )
    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert http.target_reads == 3


def _foreign_files(number):
    return f"repos/{fx.REPOSITORY}/pulls/{number}/files?per_page=100&page=1"


def test_parallel_census_read_recovers(capsys, monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    url = f"{fx.API_ROOT}/{_foreign_files(1100)}"
    http = Flaky(
        scale.ConditionalEstateHTTP(module, 200),
        url,
        [_error(module, "timeout", transient=True)],
    )
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 0, payload
    assert payload["collision_state"] == "DISJOINT"
    assert sleeper.delays == [1.0]


def test_parallel_census_read_exhaustion_names_the_foreign_read(capsys, monkeypatch):
    module = fx._cli_module()
    _patch_time(module, monkeypatch)
    url = f"{fx.API_ROOT}/{_foreign_files(1100)}"
    http = Flaky(
        scale.ConditionalEstateHTTP(module, 200),
        url,
        [_error(module, "http_502", transient=True) for _ in range(3)],
    )
    rc, payload = budget.run_cli(
        module,
        capsys,
        http,
        read_failure=_diagnostic("http_502", 3, True, endpoint=_foreign_files(1100)),
    )
    assert rc == 2 and payload["code"] == "REMOTE_PROBE_FAILED"
    assert http.target_reads == 3


def test_writer_gate_lawful_absence_is_neither_recorded_nor_retried(capsys, monkeypatch):
    module = gate._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    http = gate._active_http()
    assert gate._run(module, gate._argv(), http=http) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["legacy_branch_protected"] is False
    protection = f"{gate.API_ROOT}/{gate._protection_endpoint()}"
    assert [url for url, _, _ in http.calls].count(protection) == http.protection_reads == 2
    assert sleeper.delays == []


def test_writer_gate_names_its_failed_read(capsys, monkeypatch):
    module = gate._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    url = f"{gate.API_ROOT}/{gate._branch_endpoint()}"
    http = Flaky(
        gate._active_http(),
        url,
        [_error(module, "timeout", transient=True) for _ in range(3)],
    )
    assert gate._run(module, gate._argv(), http=http) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["code"] == "REMOTE_PROBE_FAILED"
    assert json.loads(captured.err) == {
        "diagnostic": "READ_FAILED",
        **_diagnostic("timeout", 3, True, endpoint=gate._branch_endpoint()),
    }
    assert gate.TOKEN not in captured.err
    assert sleeper.delays == [1.0, 2.0]


def test_writer_gate_recovers_with_empty_stderr(capsys, monkeypatch):
    module = gate._cli_module()
    _patch_time(module, monkeypatch)
    url = f"{gate.API_ROOT}/{gate._branch_endpoint()}"
    http = Flaky(gate._active_http(), url, [_error(module, "http_504", transient=True)])
    assert gate._run(module, gate._argv(), http=http) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"


# --- The reader in isolation.


def test_optional_read_absence_is_not_a_failure(monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    calls = []

    def absent(url, **_kwargs):
        calls.append(url)
        raise _error(module, "http_404", kind="missing")

    reader = module._BoundedHTTPGet(absent)
    assert reader.get_optional(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0) is (
        module._MISSING
    )
    assert calls == [HEAD_COMMIT_URL]
    assert reader.read_failure() is None
    assert sleeper.delays == []
    with pytest.raises(module._RemoteResourceMissing):
        reader(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert reader.read_failure() == _diagnostic(
        "http_404", 1, False, endpoint=HEAD_COMMIT
    )


def test_first_failure_is_kept_and_every_failure_is_counted(monkeypatch):
    module = fx._cli_module()
    _patch_time(module, monkeypatch)
    reader = module._BoundedHTTPGet(lambda url, **_kwargs: {})
    reader._record_read_failure(SUBJECT_URL, _error(module, "timeout", transient=True), 3)
    reader._record_read_failure(HEAD_COMMIT_URL, _error(module, "http_422"), 1)
    assert reader.read_failure() == _diagnostic("timeout", 3, True, failed=2)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/repos/a/b/pulls/1",
        "http://api.github.com/repos/a/b",
        f"{fx.API_ROOT}/repos/a/b/pulls/1 Bearer",
        f"{fx.API_ROOT}/repos/a/b\n",
        f"{fx.API_ROOT}/repos/a/\"b\"",
        f"{fx.API_ROOT}/" + "a" * 1025,
        f"{fx.API_ROOT}/",
        None,
    ],
)
def test_diagnostic_endpoint_refuses_unrecognized_urls(url):
    module = fx._cli_module()
    assert module._diagnostic_endpoint(url) == "unrecognized"


def test_diagnostic_endpoint_keeps_a_github_api_path_and_query():
    module = fx._cli_module()
    endpoint = f"repos/{fx.REPOSITORY}/pulls?state=open&per_page=100&page=16"
    assert module._diagnostic_endpoint(f"{fx.API_ROOT}/{endpoint}") == endpoint


@pytest.mark.parametrize("cause", ["http_999", "http_42", "TIMEOUT", "timeout ", 504, None])
def test_read_cause_outside_the_closed_list_is_unclassified(cause):
    module = fx._cli_module()
    error = module._RemoteProbeError()
    error.source_continuity_read_cause = cause
    assert module._read_cause(error) == "unclassified"


# --- The production transport labels each failure.


class _Response:
    def __init__(self, body=b"{}", *, etag='"abc"', read_error=None):
        self.headers = email.message.Message()
        if etag is not None:
            self.headers["ETag"] = etag
        self.body = body
        self.read_error = read_error

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, _limit):
        if self.read_error is not None:
            raise self.read_error
        return self.body


def _http_error(code, body=b"", etag=None):
    headers = email.message.Message()
    if etag is not None:
        headers["ETag"] = etag
    return HTTPError(HEAD_COMMIT_URL, code, "status", headers, io.BytesIO(body))


def _opener(*outcomes):
    calls = []
    queue = list(outcomes)

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    urlopen.calls = calls
    return urlopen


@pytest.mark.parametrize(
    ("outcome", "cause", "transient"),
    [
        (TimeoutError(), "timeout", True),
        (URLError(TimeoutError()), "timeout", True),
        (URLError(ConnectionRefusedError()), "connection", True),
        (ConnectionResetError(), "connection", True),
        (RemoteDisconnected("closed"), "connection", True),
        (_Response(read_error=IncompleteRead(b"")), "incomplete_response", True),
        (BadStatusLine("garbage"), "protocol", True),
        (_http_error(500), "http_500", True),
        (_http_error(502), "http_502", True),
        (_http_error(503), "http_503", True),
        (_http_error(504), "http_504", True),
        (URLError(ssl.SSLCertVerificationError()), "tls_verify", False),
        (URLError("unknown url type"), "invalid_url", False),
        (InvalidURL("bad port"), "invalid_url", False),
        (URLError(object()), "connection", False),
        (_http_error(501), "http_501", False),
        (_http_error(422), "http_422", False),
        (_http_error(429), "http_429", False),
        (_Response(etag=None), "missing_etag", False),
        (_Response(b"{not json"), "invalid_json", False),
        (_Response(b"\xff"), "invalid_json", False),
        (_http_error(304, etag='"abc"', body=b"x"), "not_modified_body", False),
        (_http_error(304), "missing_etag", False),
    ],
)
def test_stdlib_transport_labels_probe_failures(outcome, cause, transient, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "urlopen", _opener(outcome))
    with pytest.raises(module._RemoteProbeError) as raised:
        module._stdlib_http_get(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert type(raised.value) is module._RemoteProbeError
    assert module._read_cause(raised.value) == cause
    assert module._is_transient(raised.value) is transient
    assert fx.TOKEN not in str(raised.value)


@pytest.mark.parametrize("code", [401, 403])
def test_stdlib_transport_labels_auth_failures(code, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "urlopen", _opener(_http_error(code)))
    with pytest.raises(module._AuthProbeError) as raised:
        module._stdlib_http_get(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert module._read_cause(raised.value) == f"http_{code}"
    assert module._is_transient(raised.value) is False


def test_stdlib_transport_labels_absence(monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "urlopen", _opener(_http_error(404)))
    with pytest.raises(module._RemoteResourceMissing) as raised:
        module._stdlib_http_get(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert module._is_resource_missing(raised.value)
    assert module._read_cause(raised.value) == "http_404"
    assert module._is_transient(raised.value) is False


def test_stdlib_transport_labels_oversized_body(monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "_MAX_HTTP_BODY_BYTES", 4)
    monkeypatch.setattr(module, "urlopen", _opener(_Response(b'"12345"')))
    with pytest.raises(module._RemoteProbeError) as raised:
        module._stdlib_http_get(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert module._read_cause(raised.value) == "body_too_large"
    assert module._is_transient(raised.value) is False


@pytest.mark.parametrize(
    ("url", "token", "if_none_match", "error", "cause"),
    [
        ("https://evil.example/repos/a/b", fx.TOKEN, None, "_RemoteProbeError", "invalid_url"),
        (HEAD_COMMIT_URL, "", None, "_AuthProbeError", "no_token"),
        (HEAD_COMMIT_URL, fx.TOKEN, "not-an-etag", "_RemoteProbeError", "invalid_validator"),
    ],
)
def test_stdlib_transport_labels_refused_requests_before_any_io(
    url, token, if_none_match, error, cause, monkeypatch
):
    module = fx._cli_module()
    opener = _opener(_Response())
    monkeypatch.setattr(module, "urlopen", opener)
    with pytest.raises(getattr(module, error)) as raised:
        module._stdlib_http_get(url, token=token, timeout=20.0, if_none_match=if_none_match)
    assert module._read_cause(raised.value) == cause
    assert module._is_transient(raised.value) is False
    assert opener.calls == []


def test_stdlib_transport_not_modified_is_a_representation(monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "urlopen", _opener(_http_error(304, etag='"abc"')))
    payload = module._stdlib_http_get(
        HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0, if_none_match='"abc"'
    )
    assert payload == module._HTTPRepresentation(payload=None, etag='"abc"', not_modified=True)


class _RaisingBody:
    def __init__(self, error):
        self.error = error

    def read(self, *_args):
        raise self.error

    def close(self):
        pass


@pytest.mark.parametrize(
    ("read_error", "cause", "transient"),
    [
        (TimeoutError(), "timeout", True),
        (ConnectionResetError(), "connection", True),
        (IncompleteRead(b""), "incomplete_response", True),
    ],
)
def test_stdlib_transport_labels_a_failed_not_modified_read(
    read_error, cause, transient, monkeypatch
):
    module = fx._cli_module()
    headers = email.message.Message()
    headers["ETag"] = '"abc"'
    not_modified = HTTPError(HEAD_COMMIT_URL, 304, "status", headers, _RaisingBody(read_error))
    monkeypatch.setattr(module, "urlopen", _opener(not_modified))
    with pytest.raises(module._RemoteProbeError) as raised:
        module._stdlib_http_get(
            HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0, if_none_match='"abc"'
        )
    assert module._read_cause(raised.value) == cause
    assert module._is_transient(raised.value) is transient


@pytest.mark.parametrize(
    ("representation", "cause"),
    [
        ({"payload": {"sha": "x"}, "etag": '"abc"', "not_modified": True}, "not_modified_body"),
        ({"payload": None, "etag": '"other"', "not_modified": True}, "invalid_validator"),
        ({"payload": None, "etag": "", "not_modified": True}, "invalid_representation"),
    ],
)
def test_replay_check_labels_each_refusal(representation, cause):
    module = fx._cli_module()
    with pytest.raises(module._RemoteProbeError) as raised:
        module._replay_check('"abc"')(module._HTTPRepresentation(**representation))
    assert module._read_cause(raised.value) == cause
    assert module._is_transient(raised.value) is False


# --- The production transport inside the bounded reader.


def test_production_reader_recovers_from_one_timeout(monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    opener = _opener(TimeoutError(), _Response(b'{"tree": {"sha": "abc"}}'))
    monkeypatch.setattr(module, "urlopen", opener)
    reader = module._BoundedHTTPGet(module._stdlib_http_get)
    assert reader(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0) == {"tree": {"sha": "abc"}}
    assert len(opener.calls) == 2 and reader._calls == 2
    assert reader._recovered_reads == 1
    assert reader.read_failure() is None
    assert sleeper.delays == [1.0]


def test_production_reader_exhausts_on_repeated_503(monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    opener = _opener(_http_error(503))
    monkeypatch.setattr(module, "urlopen", opener)
    reader = module._BoundedHTTPGet(module._stdlib_http_get)
    with pytest.raises(module._RemoteProbeError):
        reader(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert len(opener.calls) == reader._calls == 3
    assert reader.read_failure() == _diagnostic("http_503", 3, True, endpoint=HEAD_COMMIT)
    assert sleeper.delays == [1.0, 2.0]


def test_production_reader_never_repeats_a_rate_limit(monkeypatch):
    module = fx._cli_module()
    _, sleeper = _patch_time(module, monkeypatch)
    opener = _opener(_http_error(429))
    monkeypatch.setattr(module, "urlopen", opener)
    reader = module._BoundedHTTPGet(module._stdlib_http_get)
    with pytest.raises(module._RemoteProbeError):
        reader(HEAD_COMMIT_URL, token=fx.TOKEN, timeout=20.0)
    assert len(opener.calls) == 1
    assert reader.read_failure() == _diagnostic("http_429", 1, False, endpoint=HEAD_COMMIT)
    assert sleeper.delays == []


def test_retry_profile_is_closed():
    module = fx._cli_module()
    assert module._HTTP_READ_ATTEMPTS == 3
    assert module._HTTP_RETRY_BACKOFF_SECONDS == (1.0, 2.0)
    assert module._HTTP_RETRY_MIN_CALL_SECONDS == 2.0
    assert len(module._HTTP_RETRY_BACKOFF_SECONDS) == module._HTTP_READ_ATTEMPTS - 1
    assert module._TRANSIENT_HTTP_STATUSES == frozenset({500, 502, 503, 504})

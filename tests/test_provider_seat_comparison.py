"""Hermetic acceptance for the opt-in, enum-only account-email diagnostic."""
from __future__ import annotations

import copy
import io
import json
import os
import queue
import stat
from types import SimpleNamespace

import pytest

from ops.executive_os import provider_identity_policy as policy
from ops.executive_os import provider_identity_probe as probe


EMAIL = "seat@example.invalid"
SENTINEL = "never-emit-account-or-token"
BINARY = {
    "path": "/synthetic/codex", "version": probe.PINNED_CODEX_VERSION,
    "sha256": probe.PINNED_CODEX_SHA256, "team_identifier": probe.PINNED_CODEX_TEAM_ID,
    "device": 1, "inode": 2, "uid": 0, "gid": 0, "mode": 0o555,
    "size": 10, "mtime_ns": 11, "ctime_ns": 12, "nlink": 1,
}
CREDENTIAL = {
    "device": 1, "inode": 3, "uid": probe.WORKER_UID, "gid": probe.WORKER_GID,
    "mode": 0o600, "size": 20, "mtime_ns": 21, "ctime_ns": 22, "nlink": 1,
}


def account(email=EMAIL):
    return {"account": {"type": "chatgpt", "planType": "pro", "email": email,
                        "accountId": SENTINEL, "token": SENTINEL},
            "requiresOpenaiAuth": True}


def argv(*extra):
    return ["--expected-kind", "device-auth", "--workspace-binding-class",
            policy.PERSONAL_PRO_WORKER_BINDING_CLASS, *extra]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """All live boundaries are fakes; only private synthetic pipes are real."""
    h = SimpleNamespace(
        events=[], processes=[], requests=[], errors={}, account=account(),
        binary_before=dict(BINARY), binary_after=dict(BINARY),
        credential_before=dict(CREDENTIAL), credential_after=dict(CREDENTIAL),
        status_before=b"Logged in using ChatGPT\n", status_after=b"Logged in using ChatGPT\n",
        config={"config": {"cli_auth_credentials_store": "file"},
                "origins": {"cli_auth_credentials_store": {"name": {"type": "sessionFlags"}}},
                "layers": [{"name": {"type": "sessionFlags"},
                            "config": {"cli_auth_credentials_store": "file"}}]},
        binary_calls=0, credential_calls=0, status_calls=0,
    )

    def event(label):
        h.events.append(label)
        if label in h.errors:
            raise h.errors[label]

    def binary(_path):
        label = "binary_before" if h.binary_calls == 0 else "binary_after"
        h.binary_calls += 1
        event(label)
        return copy.deepcopy(getattr(h, label))

    def credential(_path, **_kwargs):
        label = "credential_before" if h.credential_calls == 0 else "credential_after"
        h.credential_calls += 1
        event(label)
        return copy.deepcopy(getattr(h, label))

    def status(command, **kwargs):
        label = "status_before" if h.status_calls == 0 else "status_after"
        h.status_calls += 1
        event(label)
        h.processes.append((list(command), kwargs))
        assert command[-4:] == ["login", "status", "-c", 'cli_auth_credentials_store="file"']
        return SimpleNamespace(returncode=0, stderr=getattr(h, label))

    class Client:
        def __init__(self, command, env, cwd):
            event("client")
            h.processes.append((list(command), {"env": dict(env), "cwd": str(cwd)}))

        def request(self, request_id, method, params):
            event(method)
            h.requests.append((request_id, method, copy.deepcopy(params)))
            return copy.deepcopy({"initialize": {}, "config/read": h.config,
                                  "account/read": h.account}[method])

        def notify(self, method):
            event(method)

        def close(self):
            event("close")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unexpected real subprocess or credential-content read")

    monkeypatch.setattr(probe, "binary_identity", binary)
    monkeypatch.setattr(probe, "credential_identity", credential)
    monkeypatch.setattr(probe.subprocess, "run", status)
    monkeypatch.setattr(probe.subprocess, "Popen", forbidden)
    monkeypatch.setattr(probe, "_Client", Client)
    monkeypatch.setattr(probe.sys, "platform", "darwin")
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    monkeypatch.setattr(probe, "now_iso", lambda: "2026-09-29T00:00:00Z")
    h.kwargs = dict(binary=tmp_path / "binary", provider_home=tmp_path / "provider-home",
                    expected_kind="device-auth",
                    workspace_binding_class=policy.PERSONAL_PRO_WORKER_BINDING_CLASS)
    return h


def invoke(monkeypatch, capsys, arguments, payload=b"seat@example.invalid\n"):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    with os.fdopen(read_fd, "rb", buffering=0) as stream:
        monkeypatch.setattr(probe.sys, "stdin", stream)
        code = probe.main(arguments)
    captured = capsys.readouterr()
    assert captured.err == ""
    return code, captured.out


@pytest.mark.parametrize("value", [
    None, True, 1, {}, [], "", "codex-pro-01", "a@b", "a@@b.invalid",
    "a b@example.invalid", " a@example.invalid", "a@example.invalid ",
    "a\x00@example.invalid", "a\n@example.invalid", "a\r@example.invalid",
    ".a@example.invalid", "a.@example.invalid", "a..b@example.invalid",
    '"a"@example.invalid', "Person <a@example.invalid>", "a(comment)@example.invalid",
    "a@-example.invalid", "a@example-.invalid", "a@example..invalid", "a@example.invalid.",
    "a@ex_ample.invalid", "a@" + "b" * 64 + ".invalid", "a" * 65 + "@example.invalid",
    "é@example.invalid", "a@例.invalid", "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 63,
])
def test_unsupported_identifiers_are_unknown(value):
    assert probe._compare_expected_seat(account_read=account(), expected_email=value) == "UNKNOWN"
    assert probe._compare_expected_seat(account_read=account(value), expected_email=EMAIL) == "UNKNOWN"


@pytest.mark.parametrize("observed,expected,result", [
    (EMAIL, EMAIL, "MATCH"), ("other@example.invalid", EMAIL, "MISMATCH"),
    ("Seat@example.invalid", EMAIL, "MISMATCH"), ("seat@EXAMPLE.invalid", EMAIL, "MISMATCH"),
    ("seat+alias@example.invalid", EMAIL, "MISMATCH"),
    ("a.b+tag@example.invalid", "a.b+tag@example.invalid", "MATCH"),
    ("!#$%&'*+-/=?^_`{|}~@example.invalid", "!#$%&'*+-/=?^_`{|}~@example.invalid", "MATCH"),
])
def test_comparison_is_exact(observed, expected, result):
    assert probe._compare_expected_seat(account_read=account(observed), expected_email=expected) == result


@pytest.mark.parametrize("frame", [None, [], {}, {"account": None},
    {"account": {"email": EMAIL}, "requiresOpenaiAuth": True},
    {**account(), "authMode": "chatgpt"}, {**account(), "requiresOpenaiAuth": "true"},
    {"account": {"type": "apiKey", "email": EMAIL}, "requiresOpenaiAuth": True}])
def test_malformed_account_frame_cannot_match(frame):
    assert probe._compare_expected_seat(account_read=frame, expected_email=EMAIL) == "UNKNOWN"


@pytest.mark.parametrize("payload,expected", [
    (b"seat@example.invalid", EMAIL), (b"seat@example.invalid\n", EMAIL),
    (b"seat@example.invalid\r\n", None), (b"seat@example.invalid\n\n", None),
    (b"seat@example.invalid\nother@example.invalid", None), (b"", None),
    (b"a" * 256, None), (b"\xff@example.invalid", None),
])
def test_private_pipe_input(payload, expected):
    r, w = os.pipe()
    os.write(w, payload)
    os.close(w)
    with os.fdopen(r, "rb", buffering=0) as stream:
        assert probe._read_expected_seat_email(stream) == expected


def test_email_total_length_boundary():
    longest = "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 61
    assert len(longest) == 254
    assert probe._decode_seat_input(longest.encode() + b"\n") == longest
    assert probe._decode_seat_input((longest + "d").encode()) is None


def test_pipe_requires_eof_even_after_lf():
    r, w = os.pipe()
    try:
        os.write(w, b"seat@example.invalid\n")
        with os.fdopen(r, "rb", buffering=0) as stream:
            assert probe._read_expected_seat_email(stream, timeout_seconds=0.01) is None
    finally:
        os.close(w)


def test_fragmented_second_line_is_not_ignored(monkeypatch):
    r, w = os.pipe()
    chunks = iter([b"seat@example.invalid\n", b"other@example.invalid\n", b""])
    monkeypatch.setattr(probe.select, "select", lambda *_args: ([r], [], []))
    monkeypatch.setattr(probe.os, "read", lambda *_args: next(chunks))
    try:
        with os.fdopen(r, "rb", buffering=0) as stream:
            assert probe._read_expected_seat_email(stream) is None
    finally:
        os.close(w)


def test_input_read_size_is_bounded(monkeypatch):
    r, w = os.pipe()
    sizes = []
    monkeypatch.setattr(probe.select, "select", lambda *_args: ([r], [], []))

    def read(_fd, size):
        sizes.append(size)
        return b"x" * size

    monkeypatch.setattr(probe.os, "read", read)
    try:
        with os.fdopen(r, "rb", buffering=0) as stream:
            assert probe._read_expected_seat_email(stream) is None
        assert sizes == [256]
    finally:
        os.close(w)


def test_regular_file_and_tty_are_refused(tmp_path):
    p = tmp_path / "synthetic-input"
    p.write_bytes(b"seat@example.invalid\n")
    with p.open("rb") as stream:
        assert probe._read_expected_seat_email(stream) is None
    assert probe._read_expected_seat_email(SimpleNamespace(isatty=lambda: True)) is None
    assert probe._read_expected_seat_email(io.StringIO(EMAIL)) is None


@pytest.mark.parametrize("arguments", [
    [probe.COMPARE_SEAT_FLAG], [probe.COMPARE_SEAT_FLAG, "--help"],
    [probe.COMPARE_SEAT_FLAG, "--unknown", SENTINEL],
    [probe.COMPARE_SEAT_FLAG, "--expected-kind", SENTINEL],
    argv(probe.COMPARE_SEAT_FLAG, "--worker-uid", SENTINEL),
    argv(probe.COMPARE_SEAT_FLAG + "=" + SENTINEL),
    argv("--compare-seat", "--unknown", SENTINEL),
    argv(probe.COMPARE_SEAT_FLAG, probe.COMPARE_SEAT_FLAG),
])
def test_parser_refusals_are_enum_only(harness, monkeypatch, capsys, arguments):
    assert invoke(monkeypatch, capsys, arguments) == (2, "UNKNOWN\n")
    assert harness.events == []


@pytest.mark.parametrize("observed,expected,code", [(EMAIL, "MATCH", 0),
    ("other@example.invalid", "MISMATCH", 2), (None, "UNKNOWN", 2)])
def test_complete_fake_live_path(harness, monkeypatch, capsys, observed, expected, code):
    harness.account = account(observed)
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG)) == (code, expected + "\n")
    assert harness.events == ["binary_before", "credential_before", "status_before", "client",
                              "initialize", "initialized", "config/read", "account/read",
                              "status_after", "binary_after", "credential_after", "close"]
    assert harness.requests[-1] == (3, "account/read", {"refreshToken": False})
    child_input = repr(harness.processes) + repr(harness.requests)
    assert EMAIL not in child_input and SENTINEL not in child_input
    assert all("forced_chatgpt_workspace_id" not in str(x) for x in harness.processes)


@pytest.mark.parametrize("kind,field", [("binary", key) for key in BINARY] +
                         [("credential", key) for key in CREDENTIAL])
def test_every_metadata_drift_vetoes_match(harness, monkeypatch, capsys, kind, field):
    metadata = getattr(harness, kind + "_after")
    value = metadata[field]
    metadata[field] = value + 1 if isinstance(value, int) else value + "-changed"
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG)) == (2, "UNKNOWN\n")
    assert harness.events[-1] == "close"


@pytest.mark.parametrize("step", ["binary_before", "credential_before", "status_before", "client",
    "initialize", "initialized", "config/read", "account/read", "status_after",
    "binary_after", "credential_after", "close"])
def test_all_boundary_errors_are_private(harness, monkeypatch, capsys, step):
    harness.errors[step] = RuntimeError(EMAIL + SENTINEL)
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG)) == (2, "UNKNOWN\n")


@pytest.mark.parametrize("error", [OSError(SENTINEL), ValueError(SENTINEL),
                                   SystemExit(SENTINEL), KeyboardInterrupt(SENTINEL)])
def test_error_classes_do_not_leak(harness, monkeypatch, capsys, error):
    harness.errors["account/read"] = error
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG)) == (2, "UNKNOWN\n")
    assert harness.events[-1] == "close"


@pytest.mark.parametrize("mutation", ["forced", "config_missing", "plan", "requires", "type",
                                     "login_before", "login_after", "login_drift"])
def test_policy_config_and_auth_vetoes(harness, monkeypatch, capsys, mutation):
    if mutation == "forced":
        harness.config["config"]["forced_login_method"] = "chatgpt"
    elif mutation == "config_missing":
        harness.config = {}
    elif mutation == "plan":
        harness.account["account"]["planType"] = EMAIL + SENTINEL
    elif mutation == "requires":
        harness.account["requiresOpenaiAuth"] = False
    elif mutation == "type":
        harness.account["account"]["type"] = "apiKey"
    elif mutation == "login_before":
        harness.status_before = SENTINEL.encode()
    elif mutation == "login_after":
        harness.status_after = SENTINEL.encode()
    else:
        harness.status_after = b"Logged in using access token\n"
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG)) == (2, "UNKNOWN\n")


def test_no_stdout_before_cleanup(harness, monkeypatch):
    class Output(io.StringIO):
        def write(self, value):
            assert harness.events[-1] == "close"
            return super().write(value)
    output = Output()
    monkeypatch.setattr(probe.sys, "stdout", output)
    monkeypatch.setattr(probe, "_read_expected_seat_email", lambda: EMAIL)
    assert probe.main(argv(probe.COMPARE_SEAT_FLAG)) == 0
    assert output.getvalue() == "MATCH\n"


def test_direct_comparison_result_has_no_identity_dictionary(harness):
    assert probe.live_probe(**harness.kwargs, expected_seat_email=EMAIL) == "MATCH"
    assert harness.events[-1] == "close"


def test_failed_output_delivery_is_not_success(harness, monkeypatch):
    class BrokenOutput:
        def write(self, _value):
            raise OSError(SENTINEL)
    monkeypatch.setattr(probe.sys, "stdout", BrokenOutput())
    monkeypatch.setattr(probe, "_read_expected_seat_email", lambda: EMAIL)
    assert probe.main(argv(probe.COMPARE_SEAT_FLAG)) == 2


def test_default_identity_json_contract_is_unchanged(harness, monkeypatch, capsys):
    def no_read():
        raise AssertionError("default mode must not read expected identity")
    monkeypatch.setattr(probe, "_read_expected_seat_email", no_read)
    code = probe.main(argv())
    output = capsys.readouterr()
    expected = probe.evaluate_identity(account_read=account(), auth_mode="chatgpt",
        expected_kind="device-auth", workspace_binding_class=policy.PERSONAL_PRO_WORKER_BINDING_CLASS)
    expected.update(observed_at="2026-09-29T00:00:00Z", codex_binary=BINARY,
                    credential_lstat=CREDENTIAL, forced_chatgpt_workspace_id_applied=False)
    assert code == 0 and output.err == ""
    assert output.out == json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n"
    assert EMAIL not in output.out and SENTINEL not in output.out and "seat_comparison" not in output.out
    assert probe._account_read(account()) == ("chatgpt", "pro", True)


def test_nonroot_and_bad_expected_input_never_reach_probe(harness, monkeypatch, capsys):
    monkeypatch.setattr(probe.os, "geteuid", lambda: probe.WORKER_UID)
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG)) == (2, "UNKNOWN\n")
    assert harness.events == []
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    assert invoke(monkeypatch, capsys, argv(probe.COMPARE_SEAT_FLAG), b"codex-pro-01") == (2, "UNKNOWN\n")
    assert harness.events == []


def test_credential_observation_does_not_read_contents(monkeypatch):
    class MetadataOnly:
        def lstat(self):
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=probe.WORKER_UID,
                st_gid=probe.WORKER_GID, st_nlink=1, st_size=20, st_dev=1, st_ino=3,
                st_mtime_ns=21, st_ctime_ns=22)
        def open(self, *_args, **_kwargs):
            pytest.fail("credential content was opened")
        def read_bytes(self):
            pytest.fail("credential bytes were read")
    monkeypatch.setattr(probe, "_assert_no_macos_acl", lambda _path: None)
    assert probe.credential_identity(MetadataOnly()) == CREDENTIAL


@pytest.mark.parametrize("failure", [OSError(SENTINEL), RuntimeError(EMAIL)])
def test_reader_thread_failure_is_bounded_and_private(capsys, failure):
    class BrokenStream:
        def __iter__(self):
            raise failure
    client = object.__new__(probe._Client)
    client._proc = SimpleNamespace(stdout=BrokenStream())
    client._messages = queue.Queue()
    client._read()
    assert client._messages.get_nowait() == {"_malformed": True}
    assert client._messages.get_nowait() is None
    assert client._messages.empty()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""

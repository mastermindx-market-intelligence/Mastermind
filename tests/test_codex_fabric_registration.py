from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.codex_fabric.register_executive_mcp import (
    RegistrationError,
    register,
)

SERVER = "mastermind-executive"
URL = "http://127.0.0.1:8766/mcp"


def _read_calls(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]
def _fake_codex(tmp_path: Path, *, existing_url: str | None = None, auth_status: str = "not_logged_in") -> tuple[Path, Path]:
    state = tmp_path / "state.json"
    calls = tmp_path / "calls.jsonl"
    if existing_url is not None:
        state.write_text(json.dumps({"url": existing_url, "auth_status": auth_status}))
    script = tmp_path / "codex"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"state=pathlib.Path({str(state)!r})\n"
        f"calls=pathlib.Path({str(calls)!r})\n"
        "args=sys.argv[1:]\n"
        "with calls.open('a') as h: h.write(json.dumps(args)+'\\n')\n"
        "current=json.loads(state.read_text()) if state.exists() else None\n"
        "if args[:2] == ['mcp','add']:\n"
        "    url=args[args.index('--url')+1]; state.write_text(json.dumps({'url':url,'auth_status':'not_logged_in'})); raise SystemExit(0)\n"
        "if args[:2] == ['mcp','list']:\n"
        "    if current is None and not state.exists(): print('[]'); raise SystemExit(0)\n"
        "    row=json.loads(state.read_text()); print(json.dumps([{'name':'mastermind-executive','enabled':True,'transport':{'type':'streamable_http','url':row['url'],'bearer_token_env_var':None,'http_headers':None,'env_http_headers':None},'auth_status':row.get('auth_status')} ])); raise SystemExit(0)\n"
        "raise SystemExit(64)\n"
    )
    script.chmod(0o755)
    return script, calls
def test_new_registration_uses_streamable_http_without_secret_arguments(tmp_path: Path):
    codex, calls = _fake_codex(tmp_path)

    receipt = register(URL, codex_bin=str(codex))

    assert receipt.server_name == SERVER
    assert receipt.url == URL
    assert receipt.created is True
    assert receipt.auth_status == "not_logged_in"
    observed = _read_calls(calls)
    assert observed[0] == ["mcp", "list", "--json"]
    assert observed[1] == ["mcp", "add", SERVER, "--url", URL]
    assert observed[2] == ["mcp", "list", "--json"]
    flat = " ".join(item for row in observed for item in row).lower()
    assert "bearer" not in flat
    assert "token" not in flat
    assert "login" not in flat


def test_matching_registration_is_idempotent_and_does_not_re_add(tmp_path: Path):
    codex, calls = _fake_codex(tmp_path, existing_url=URL, auth_status="authenticated")

    receipt = register(URL, codex_bin=str(codex))

    assert receipt.created is False
    assert receipt.auth_status == "authenticated"
    assert _read_calls(calls) == [
        ["mcp", "list", "--json"],
    ]
def test_existing_different_url_refuses_instead_of_overwriting(tmp_path: Path):
    codex, calls = _fake_codex(tmp_path, existing_url="http://127.0.0.1:9000/mcp")

    with pytest.raises(RegistrationError, match="different configuration"):
        register(URL, codex_bin=str(codex))

    assert _read_calls(calls) == [["mcp", "list", "--json"]]


@pytest.mark.parametrize(
    "url",
    [
        "https://executive.example.com/mcp",
        "http://127.0.0.1/mcp",
        "http://127.0.0.1:8766/not-mcp",
        "http://user@127.0.0.1:8766/mcp",
        "http://127.0.0.1:8766/mcp?x=1",
        "http://127.0.0.1:8766/mcp#fragment",
    ],
)
def test_non_loopback_or_ambiguous_url_refuses_before_running_codex(tmp_path: Path, url: str):
    codex, calls = _fake_codex(tmp_path)

    with pytest.raises(RegistrationError, match="Executive MCP URL"):
        register(url, codex_bin=str(codex))

    assert _read_calls(calls) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8766/mcp",
        "http://[::1]:8766/mcp",
    ],
)
def test_registration_requires_literal_ipv4_loopback_used_by_installed_server(
    tmp_path: Path, url: str
):
    codex, calls = _fake_codex(tmp_path)

    with pytest.raises(RegistrationError, match="Executive MCP URL"):
        register(url, codex_bin=str(codex))

    assert _read_calls(calls) == []


def test_missing_codex_binary_is_closed_error():
    with pytest.raises(RegistrationError, match="Codex MCP command is unavailable"):
        register(URL, codex_bin="/definitely/missing/codex")


def test_cli_emits_secret_free_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    import ops.codex_fabric.register_executive_mcp as registration

    codex, _calls = _fake_codex(tmp_path)
    code = registration.main(["--url", URL, "--codex-bin", str(codex)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "auth_status": "not_logged_in",
        "created": True,
        "server_name": SERVER,
        "url": URL,
    }
    serialized = json.dumps(payload).lower()
    assert "token" not in serialized
    assert "bearer" not in serialized


def test_codex_command_timeout_covers_observed_slow_mcp_census(monkeypatch: pytest.MonkeyPatch):
    import ops.codex_fabric.register_executive_mcp as registration

    observed: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        observed.update(kwargs)
        return registration.subprocess.CompletedProcess(args[0], 0, "[]", "")

    monkeypatch.setattr(registration.subprocess, "run", fake_run)
    registration._run("codex", "mcp", "list", "--json")

    assert observed["timeout"] >= 60


def test_ambiguous_add_timeout_reconciles_exact_registration_without_second_add(
    monkeypatch: pytest.MonkeyPatch,
):
    import ops.codex_fabric.register_executive_mcp as registration

    calls: list[list[str]] = []
    census_count = 0

    def fake_run(argv, **_kwargs):
        nonlocal census_count
        args = list(argv[1:])
        calls.append(args)
        if args == ["mcp", "list", "--json"]:
            census_count += 1
            if census_count == 1:
                return registration.subprocess.CompletedProcess(argv, 0, "[]", "")
            row = {
                "name": SERVER,
                "enabled": True,
                "transport": {
                    "type": "streamable_http",
                    "url": URL,
                    "bearer_token_env_var": None,
                    "http_headers": None,
                    "env_http_headers": None,
                    "http_headers_helper": None,
                },
                "auth_status": "unknown",
            }
            return registration.subprocess.CompletedProcess(argv, 0, json.dumps([row]), "")
        if args == ["mcp", "add", SERVER, "--url", URL]:
            raise registration.subprocess.TimeoutExpired(argv, timeout=60)
        raise AssertionError(args)

    monkeypatch.setattr(registration.subprocess, "run", fake_run)
    receipt = registration.register(URL)

    assert receipt.created is True
    assert receipt.url == URL
    assert calls == [
        ["mcp", "list", "--json"],
        ["mcp", "add", SERVER, "--url", URL],
        ["mcp", "list", "--json"],
    ]
    assert sum(call[:2] == ["mcp", "add"] for call in calls) == 1


def test_existing_http_headers_helper_refuses_as_configuration_drift(monkeypatch: pytest.MonkeyPatch):
    import ops.codex_fabric.register_executive_mcp as registration

    row = {
        "name": SERVER,
        "enabled": True,
        "transport": {
            "type": "streamable_http",
            "url": URL,
            "bearer_token_env_var": None,
            "http_headers": None,
            "env_http_headers": None,
            "http_headers_helper": "/foreign/helper",
        },
        "auth_status": "unknown",
    }
    monkeypatch.setattr(registration, "_list_servers", lambda _codex: [row])

    with pytest.raises(RegistrationError, match="different configuration"):
        registration.register(URL)


def test_unknown_transport_field_refuses_as_configuration_drift(monkeypatch: pytest.MonkeyPatch):
    import ops.codex_fabric.register_executive_mcp as registration

    row = {
        "name": SERVER,
        "enabled": True,
        "transport": {
            "type": "streamable_http",
            "url": URL,
            "bearer_token_env_var": None,
            "http_headers": None,
            "env_http_headers": None,
            "http_headers_helper": None,
            "future_secret_field": "opaque",
        },
        "auth_status": "unknown",
    }
    monkeypatch.setattr(registration, "_list_servers", lambda _codex: [row])
    with pytest.raises(RegistrationError, match="different configuration"):
        register(URL)

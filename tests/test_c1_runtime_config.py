from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


SCHEMA = "mastermind.sol_state_relay_config.v1"
EXECUTIVE_SOCKET = "/var/run/mastermind-executive/ceo-ingress.sock"
WORKSPACE = "T0BRD2AQXQV"
CHANNEL = "C0BSGABKBFY"
TOKEN_FILE = "/Library/Application Support/MastermindExecutive/config/sol-state-relay.token"


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.c1_runtime")
    except ModuleNotFoundError:
        pytest.fail("C1 production runtime/config module is not implemented")


def _document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "executive_socket": EXECUTIVE_SOCKET,
        "slack_workspace_id": WORKSPACE,
        "slack_channel_id": CHANNEL,
        "slack_bot_user_id": "U0C1BOTFIX1",
        "slack_token_file": TOKEN_FILE,
        "poll_seconds": 30,
        "heartbeat_seconds": 60,
        "max_executive_age_seconds": 120,
        "relay_version": "c1-production-fixture",
    }


def _write_test_config(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "relay.json"
    path.unlink(missing_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o440)
    return path


def _write_token(path: Path, text: str, mode: int) -> None:
    path.unlink(missing_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def _load_for_test(c1_runtime, path: Path):
    return c1_runtime.load_config(
        path,
        expected_path=path,
        expected_owner_uid=os.geteuid(),
        expected_group_gid=os.getegid(),
    )


def _read_token_for_test(c1_runtime, path: Path):
    return c1_runtime.read_token_file(path, expected_path=path)


def test_load_config_accepts_only_exact_nonsecret_runtime_policy(tmp_path: Path):
    c1_runtime = _module()
    document = _document()
    path = _write_test_config(tmp_path, document)

    config = _load_for_test(c1_runtime, path)

    assert config.executive_socket == Path(EXECUTIVE_SOCKET)
    assert config.slack_workspace_id == WORKSPACE
    assert config.slack_channel_id == CHANNEL
    assert config.slack_bot_user_id == document["slack_bot_user_id"]
    assert config.slack_token_file == Path(TOKEN_FILE)
    assert config.poll_seconds == 30
    assert config.heartbeat_seconds == 60
    assert config.max_executive_age_seconds == 120
    assert config.relay_version == "c1-production-fixture"
    assert not hasattr(config, "slack_token")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("executive_socket", "/tmp/other.sock"),
        ("slack_workspace_id", "T-WRONG"),
        ("slack_channel_id", "C-WRONG"),
        ("slack_token_file", "/tmp/relay.token"),
        ("poll_seconds", 15),
        ("heartbeat_seconds", 30),
        ("max_executive_age_seconds", 240),
    ],
)
def test_load_config_rejects_fixed_policy_drift(tmp_path: Path, field: str, value):
    c1_runtime = _module()
    document = _document()
    document[field] = value
    path = _write_test_config(tmp_path, document)

    with pytest.raises(ValueError, match="invalid C1 config"):
        _load_for_test(c1_runtime, path)


def test_load_config_rejects_inline_token_unknown_fields_and_unsafe_metadata(tmp_path: Path):
    c1_runtime = _module()
    document = _document()
    document["slack_token"] = "FORBIDDEN-INLINE-SECRET-FIXTURE"
    path = _write_test_config(tmp_path, document)

    with pytest.raises(ValueError, match="invalid C1 config"):
        _load_for_test(c1_runtime, path)

    good_path = _write_test_config(tmp_path, _document())
    good_path.chmod(0o640)
    with pytest.raises(ValueError, match="invalid C1 config"):
        _load_for_test(c1_runtime, good_path)


def test_load_config_rejects_symlink_even_when_target_metadata_is_private(tmp_path: Path):
    c1_runtime = _module()
    target = _write_test_config(tmp_path, _document())
    link = tmp_path / "relay-link.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="invalid C1 config"):
        c1_runtime.load_config(
            link,
            expected_path=link,
            expected_owner_uid=os.geteuid(),
            expected_group_gid=os.getegid(),
        )


def test_read_token_file_accepts_exact_same_uid_gid_mode0400_single_link(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.token"
    _write_token(path, "INERT-C1-TOKEN-FIXTURE\n", 0o400)

    token = _read_token_for_test(c1_runtime, path)

    assert token == "INERT-C1-TOKEN-FIXTURE"
    info = path.stat()
    assert info.st_uid == os.geteuid()
    assert info.st_gid == os.getegid()
    assert info.st_nlink == 1


def test_read_token_file_distinguishes_missing_from_unsafe_and_invalid(tmp_path: Path):
    c1_runtime = _module()
    missing = tmp_path / "missing.token"
    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_UNAVAILABLE"):
        _read_token_for_test(c1_runtime, missing)

    path = tmp_path / "relay.token"
    _write_token(path, "INERT-C1-TOKEN-FIXTURE\n", 0o600)
    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_UNSAFE"):
        _read_token_for_test(c1_runtime, path)

    _write_token(path, "has whitespace inside\n", 0o400)
    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_INVALID"):
        _read_token_for_test(c1_runtime, path)


def test_read_token_file_rejects_symlink_and_hardlink(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.token"
    _write_token(path, "INERT-C1-TOKEN-FIXTURE\n", 0o400)
    link = tmp_path / "relay-link.token"
    link.symlink_to(path)
    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_UNSAFE"):
        c1_runtime.read_token_file(link, expected_path=link)

    hard = tmp_path / "relay-hard.token"
    os.link(path, hard)
    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_UNSAFE"):
        _read_token_for_test(c1_runtime, path)


def test_read_token_file_refuses_path_override_even_if_private(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.token"
    _write_token(path, "INERT-C1-TOKEN-FIXTURE\n", 0o400)

    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_UNSAFE"):
        c1_runtime.read_token_file(path)


def test_assert_relay_principal_refuses_root(monkeypatch):
    c1_runtime = _module()
    monkeypatch.setattr(c1_runtime.os, "geteuid", lambda: 0)

    with pytest.raises(RuntimeError, match="C1_RELAY_PRINCIPAL_REFUSED"):
        c1_runtime.assert_relay_principal()


def test_assert_relay_principal_accepts_only_reviewed_groups(monkeypatch):
    c1_runtime = _module()
    monkeypatch.setattr(c1_runtime.os, "geteuid", lambda: 452)
    monkeypatch.setattr(
        c1_runtime.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_name="_mastermind_sol_relay", pw_gid=452),
    )

    reviewed = {
        452: "_mastermind_sol_relay",
        12: "everyone",
        61: "localaccounts",
        100: "_lpoperator",
        396: "com.apple.access_disabled",
    }
    monkeypatch.setattr(c1_runtime.os, "getgroups", lambda: list(reviewed))
    monkeypatch.setattr(
        c1_runtime.grp,
        "getgrgid",
        lambda gid: SimpleNamespace(gr_name=reviewed[gid]),
    )
    c1_runtime.assert_relay_principal()

    for unexpected in (
        "admin",
        "wheel",
        "_mastermind_worker",
        "_mastermind_exec",
        "_mastermind_ops",
        "_mastermind_codex_01",
    ):
        group_names = dict(reviewed)
        group_names[499] = unexpected
        monkeypatch.setattr(c1_runtime.os, "getgroups", lambda: list(group_names))
        monkeypatch.setattr(
            c1_runtime.grp,
            "getgrgid",
            lambda gid, group_names=group_names: SimpleNamespace(gr_name=group_names[gid]),
        )
        with pytest.raises(RuntimeError, match="C1_RELAY_PRINCIPAL_REFUSED"):
            c1_runtime.assert_relay_principal()

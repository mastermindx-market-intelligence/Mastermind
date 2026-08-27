from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest


SCHEMA = "mastermind.sol_state_relay_config.v1"


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.c1_runtime")
    except ModuleNotFoundError:
        pytest.fail("C1 production runtime/config module is not implemented")


def _document(tmp_path: Path) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "executive_socket": "/var/run/mastermind-executive/ceo-ingress.sock",
        "slack_workspace_id": "T-C1-WORKSPACE-FIXTURE",
        "slack_channel_id": "C-SOL-RUNTIME-FIXTURE",
        "slack_bot_user_id": "U-SOL-RELAY-FIXTURE",
        "slack_token_file": str(tmp_path / "relay.token"),
        "poll_seconds": 30,
        "heartbeat_seconds": 60,
        "max_executive_age_seconds": 120,
        "relay_version": "c1-production-fixture",
    }


def test_load_config_accepts_only_nonsecret_fixed_runtime_fields(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.json"
    document = _document(tmp_path)
    path.write_text(json.dumps(document), encoding="utf-8")

    config = c1_runtime.load_config(path)

    assert config.executive_socket == Path(document["executive_socket"])
    assert config.slack_workspace_id == document["slack_workspace_id"]
    assert config.slack_channel_id == document["slack_channel_id"]
    assert config.slack_bot_user_id == document["slack_bot_user_id"]
    assert config.slack_token_file == Path(document["slack_token_file"])
    assert config.poll_seconds == 30
    assert config.heartbeat_seconds == 60
    assert config.max_executive_age_seconds == 120
    assert config.relay_version == "c1-production-fixture"
    assert not hasattr(config, "slack_token")


def test_load_config_rejects_inline_token_and_unknown_fields(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.json"
    document = _document(tmp_path)
    document["slack_token"] = "FORBIDDEN-INLINE-SECRET-FIXTURE"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid C1 config"):
        c1_runtime.load_config(path)


def test_read_token_file_accepts_same_uid_private_regular_file(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.token"
    path.write_text("INERT-C1-TOKEN-FIXTURE\n", encoding="utf-8")
    path.chmod(0o600)

    token = c1_runtime.read_token_file(path)

    assert token == "INERT-C1-TOKEN-FIXTURE"
    assert path.stat().st_uid == os.geteuid()


def test_read_token_file_rejects_group_or_world_permissions(tmp_path: Path):
    c1_runtime = _module()
    path = tmp_path / "relay.token"
    path.write_text("INERT-C1-TOKEN-FIXTURE\n", encoding="utf-8")
    path.chmod(0o640)

    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_UNSAFE"):
        c1_runtime.read_token_file(path)

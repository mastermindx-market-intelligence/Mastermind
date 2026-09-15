from __future__ import annotations

import copy
import hashlib
import json

import pytest

from integrations.devbox_mcp import contracts


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_tool_surface_is_exactly_four_bounded_attended_tools() -> None:
    assert contracts.TOOL_NAMES == (
        "devbox_status",
        "start_devbox_command",
        "read_devbox_process",
        "cancel_devbox_process",
    )
    assert tuple(spec.name for spec in contracts.TOOL_SPECS) == contracts.TOOL_NAMES
    assert contracts.EFFECT_STATES == ("NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN")


def test_model_cannot_supply_target_root_host_environment_or_credentials() -> None:
    forbidden = {
        "target",
        "target_ref",
        "host",
        "hostname",
        "repository",
        "repo",
        "root",
        "cwd",
        "environment",
        "env",
        "shell",
        "executable",
        "account",
        "token",
        "credential",
        "credentials",
        "branch",
        "worktree",
    }
    for spec in contracts.TOOL_SPECS:
        properties = set(spec.input_schema.get("properties", {}))
        assert not properties & forbidden, spec.name
        assert spec.input_schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("tool", "arguments", "field"),
    [
        ("devbox_status", {"host": "attacker"}, "host"),
        (
            "start_devbox_command",
            {"operation_key": "op-1", "command_text": "true", "cwd": "/tmp"},
            "cwd",
        ),
        (
            "read_devbox_process",
            {"process_ref": "process:" + "a" * 64, "target_ref": "elsewhere"},
            "target_ref",
        ),
        (
            "cancel_devbox_process",
            {"process_ref": "process:" + "a" * 64, "env": {"GH_TOKEN": "x"}},
            "env",
        ),
    ],
)
def test_authority_shaped_extra_fields_are_refused(tool: str, arguments: dict, field: str) -> None:
    with pytest.raises(contracts.DevBoxContractError) as exc_info:
        contracts.validate_tool_arguments(tool, arguments)
    assert exc_info.value.code == "INVALID_REQUEST"
    assert field in exc_info.value.message


def test_start_command_validation_is_closed_and_bounded() -> None:
    valid = contracts.validate_tool_arguments(
        "start_devbox_command",
        {
            "operation_key": "codespace-canary-001",
            "command_text": "python -m pytest tests/devbox_mcp -q",
            "timeout_seconds": 300,
            "output_limit_bytes": 65536,
        },
    )
    assert valid == {
        "operation_key": "codespace-canary-001",
        "command_text": "python -m pytest tests/devbox_mcp -q",
        "timeout_seconds": 300,
        "output_limit_bytes": 65536,
    }

    for bad in (
        {"operation_key": "", "command_text": "true"},
        {"operation_key": "a" * 97, "command_text": "true"},
        {"operation_key": "bad space", "command_text": "true"},
        {"operation_key": "op", "command_text": ""},
        {"operation_key": "op", "command_text": "x" * 16385},
        {"operation_key": "op", "command_text": "true", "timeout_seconds": 0},
        {"operation_key": "op", "command_text": "true", "timeout_seconds": 1801},
        {"operation_key": "op", "command_text": "true", "output_limit_bytes": 1023},
        {"operation_key": "op", "command_text": "true", "output_limit_bytes": 262145},
    ):
        with pytest.raises(contracts.DevBoxContractError):
            contracts.validate_tool_arguments("start_devbox_command", bad)


def test_process_read_has_independent_stdout_and_stderr_cursors() -> None:
    request = contracts.validate_tool_arguments(
        "read_devbox_process",
        {
            "process_ref": "process:" + "b" * 64,
            "stdout_cursor": 123,
            "stderr_cursor": 456,
            "max_bytes": 32768,
        },
    )
    assert request["stdout_cursor"] == 123
    assert request["stderr_cursor"] == 456
    assert request["max_bytes"] == 32768

    for key in ("stdout_cursor", "stderr_cursor"):
        bad = dict(request)
        bad[key] = -1
        with pytest.raises(contracts.DevBoxContractError):
            contracts.validate_tool_arguments("read_devbox_process", bad)


def test_cancel_requires_exact_opaque_process_ref() -> None:
    accepted = contracts.validate_tool_arguments(
        "cancel_devbox_process",
        {"process_ref": "process:" + "c" * 64, "reason": "attended stop"},
    )
    assert accepted["process_ref"] == "process:" + "c" * 64

    for bad in ("123", "process:123", "process:" + "g" * 64, "process:" + "a" * 65):
        with pytest.raises(contracts.DevBoxContractError):
            contracts.validate_tool_arguments("cancel_devbox_process", {"process_ref": bad})


def test_annotations_distinguish_reads_from_modifying_actions() -> None:
    by_name = {spec.name: spec for spec in contracts.TOOL_SPECS}
    assert by_name["devbox_status"].annotations == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert by_name["read_devbox_process"].annotations == by_name["devbox_status"].annotations
    for name in ("start_devbox_command", "cancel_devbox_process"):
        assert by_name[name].annotations["readOnlyHint"] is False
        assert by_name[name].annotations["openWorldHint"] is False


def test_schema_digest_detects_authority_widening() -> None:
    snapshot = contracts.schema_snapshot()
    assert _digest(snapshot) == contracts.SCHEMA_SNAPSHOT_SHA256
    widened = copy.deepcopy(snapshot)
    widened["tools"][1]["input_schema"]["properties"]["cwd"] = {"type": "string"}
    assert _digest(widened) != contracts.SCHEMA_SNAPSHOT_SHA256


def test_unknown_tool_is_refused_without_repair_or_guessing() -> None:
    with pytest.raises(contracts.DevBoxContractError) as exc_info:
        contracts.validate_tool_arguments("shell", {"command_text": "true"})
    assert exc_info.value.code == "TOOL_NOT_AVAILABLE"

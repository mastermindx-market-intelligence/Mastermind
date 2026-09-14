"""Targeted tests for the strictly additive channel audit event encoding.

The OAuth ``AuthAuditEvent`` encoding must stay byte-for-byte unchanged; the
``ChannelAuditEvent`` is a distinct closed schema on the same sink mechanics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from integrations.business_mcp_auth.audit import (
    AuditSinkPoisoned,
    DurableAuthAuditSink,
)
from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    CHANNEL_AUDIT_SCHEMA,
    AuthAuditEvent,
    ChannelAuditEvent,
)

POLICY_ID = "workbench-action-tunnel-c1"
CHANNEL_REF = "a" * 64
ACTION_DIGEST = "b" * 64
CHANNEL_TOOLS = (
    "workspace_manifest",
    "read_project_file",
    "preview_text_replace",
    "prepare_text_patch",
    "commit_text_patch",
    "reconcile_text_patch",
    "prepare_project_command",
    "run_project_command",
    "read_action_result",
    "reconcile_action",
)


def oauth_event(code: str = "accepted", accepted: bool = True) -> AuthAuditEvent:
    return AuthAuditEvent(
        schema=AUTH_AUDIT_SCHEMA,
        policy_id=POLICY_ID,
        code=code,
        accepted=accepted,
    )


def channel_event(
    *,
    code: str = "accepted",
    accepted: bool | None = None,
    tool: str = "prepare_text_patch",
    channel_ref: object = CHANNEL_REF,
    action_digest: object = None,
    policy_id: str = POLICY_ID,
    schema: object = CHANNEL_AUDIT_SCHEMA,
) -> ChannelAuditEvent:
    return ChannelAuditEvent(
        schema=schema,  # type: ignore[arg-type]
        policy_id=policy_id,  # type: ignore[arg-type]
        code=code,  # type: ignore[arg-type]
        accepted=(code == "accepted") if accepted is None else accepted,
        channel_ref=channel_ref,  # type: ignore[arg-type]
        tool=tool,  # type: ignore[arg-type]
        action_digest=action_digest,  # type: ignore[arg-type]
    )


def open_directory(path: Path) -> int:
    path.mkdir(mode=0o700)
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def canonical(payload: dict) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_channel_events_append_canonical_lines_without_changing_oauth_rows(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        sink.emit(oauth_event())
        sink.emit(
            channel_event(
                code="accepted",
                tool="commit_text_patch",
                action_digest=ACTION_DIGEST,
            )
        )
        sink.emit(channel_event(code="channel_refused", tool="prepare_text_patch"))
        sink.emit(oauth_event("scope_refused", False))
        sink.close()
    finally:
        os.close(host_fd)

    raw = (directory / "auth-audit.jsonl").read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert lines == [
        canonical(
            {
                "accepted": True,
                "code": "accepted",
                "policy_id": POLICY_ID,
                "schema": AUTH_AUDIT_SCHEMA,
            }
        ),
        canonical(
            {
                "accepted": True,
                "action_digest": ACTION_DIGEST,
                "channel_ref": CHANNEL_REF,
                "code": "accepted",
                "policy_id": POLICY_ID,
                "schema": CHANNEL_AUDIT_SCHEMA,
                "tool": "commit_text_patch",
            }
        ),
        canonical(
            {
                "accepted": False,
                "action_digest": None,
                "channel_ref": CHANNEL_REF,
                "code": "channel_refused",
                "policy_id": POLICY_ID,
                "schema": CHANNEL_AUDIT_SCHEMA,
                "tool": "prepare_text_patch",
            }
        ),
        canonical(
            {
                "accepted": False,
                "code": "scope_refused",
                "policy_id": POLICY_ID,
                "schema": AUTH_AUDIT_SCHEMA,
            }
        ),
    ]
    # The channel row never borrows the OAuth schema and carries no free text.
    for line in lines[1:3]:
        observed = json.loads(line)
        assert set(observed) == {
            "accepted",
            "action_digest",
            "channel_ref",
            "code",
            "policy_id",
            "schema",
            "tool",
        }


def test_foreign_event_type_is_refused_without_append(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(
                {
                    "schema": CHANNEL_AUDIT_SCHEMA,
                    "policy_id": POLICY_ID,
                    "code": "accepted",
                    "accepted": True,
                    "channel_ref": CHANNEL_REF,
                    "tool": "prepare_text_patch",
                    "action_digest": None,
                }  # type: ignore[arg-type]
            )
        assert (directory / "auth-audit.jsonl").read_bytes() == b""
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(channel_event())
    finally:
        os.close(host_fd)


@pytest.mark.parametrize("tool", CHANNEL_TOOLS)
def test_exact_unified_channel_tool_names_are_accepted(tmp_path: Path, tool: str) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        sink.emit(channel_event(tool=tool))
        sink.close()
    finally:
        os.close(host_fd)
    assert json.loads((directory / "auth-audit.jsonl").read_text())["tool"] == tool


@pytest.mark.parametrize(
    "event_builder",
    [
        lambda: channel_event(schema=AUTH_AUDIT_SCHEMA),
        lambda: channel_event(code="accepted", accepted=False),
        lambda: channel_event(code="channel_refused", accepted=True),
        lambda: channel_event(code="oauth_accepted", accepted=True),
        lambda: channel_event(tool="preview_project_command"),
        lambda: channel_event(tool=7),
        lambda: channel_event(channel_ref="workspace:ws-01"),
        lambda: channel_event(channel_ref="a" * 63),
        lambda: channel_event(action_digest="the-action-token"),
        lambda: channel_event(action_digest=123),
        lambda: channel_event(policy_id="mastermind-workbench-read-v1"),
    ],
    ids=[
        "wrong_schema",
        "accepted_code_with_false_bool",
        "refused_code_with_true_bool",
        "oauth_accepted_code_is_not_a_channel_code",
        "unknown_tool",
        "tool_is_not_a_string",
        "readable_channel_ref",
        "channel_ref_wrong_length",
        "plaintext_action_digest",
        "action_digest_wrong_type",
        "foreign_policy_id",
    ],
)
def test_invalid_channel_events_poison_without_any_append(
    tmp_path: Path, event_builder
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(event_builder())
        target = directory / "auth-audit.jsonl"
        assert target.read_bytes() == b""
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(channel_event())
        assert target.read_bytes() == b""
    finally:
        os.close(host_fd)


def test_channel_event_exceeding_line_budget_poisons_without_append(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID, max_line_bytes=128)
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(channel_event())
        assert (directory / "auth-audit.jsonl").read_bytes() == b""
    finally:
        os.close(host_fd)

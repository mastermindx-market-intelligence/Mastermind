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


# ---------------------------------------------------------------------------
# Durable admission read-back (#670): the sink is the only reader of its own
# ledger, and only exact refused-before-dispatch history may ever support a
# NOT_APPLIED reconciliation.
# ---------------------------------------------------------------------------

from integrations.business_mcp_auth.audit import (  # noqa: E402
    ADMISSION_ABSENT,
    ADMISSION_ACCEPTED,
    ADMISSION_REFUSED_ONLY,
    ADMISSION_UNCERTAIN,
    classify_channel_admissions,
)

OTHER_DIGEST = "c" * 64
OTHER_CHANNEL_REF = "d" * 64


def _seed_ledger(sink: DurableAuthAuditSink) -> None:
    sink.emit(oauth_event())
    sink.emit(channel_event(code="accepted", tool="prepare_text_patch"))
    sink.emit(
        channel_event(
            code="channel_refused", tool="commit_text_patch", action_digest=ACTION_DIGEST
        )
    )
    sink.emit(
        channel_event(code="accepted", tool="commit_text_patch", action_digest=OTHER_DIGEST)
    )
    sink.emit(
        channel_event(
            code="accepted", tool="reconcile_text_patch", action_digest=ACTION_DIGEST
        )
    )
    sink.emit(oauth_event("scope_refused", False))


def test_read_channel_admissions_returns_exact_digest_rows_in_order_and_after_reopen(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        _seed_ledger(sink)
        before = (directory / "auth-audit.jsonl").read_bytes()
        rows = sink.read_channel_admissions(ACTION_DIGEST)
        assert [(row.tool, row.code, row.accepted) for row in rows] == [
            ("commit_text_patch", "channel_refused", False),
            ("reconcile_text_patch", "accepted", True),
        ]
        assert all(row.action_digest == ACTION_DIGEST for row in rows)
        assert sink.read_channel_admissions("e" * 64) == ()
        # A read appends nothing and leaves the sink live for its next append.
        assert (directory / "auth-audit.jsonl").read_bytes() == before
        sink.emit(channel_event(code="accepted", tool="workspace_manifest"))
        sink.close()

        # Restart: a freshly opened sink over the same named ledger reads the
        # identical durable history; nothing lives only in memory.
        reopened = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        try:
            again = reopened.read_channel_admissions(ACTION_DIGEST)
            assert again == rows
        finally:
            reopened.close()
    finally:
        os.close(host_fd)


def test_read_channel_admissions_refuses_when_not_live(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        with pytest.raises(AuditSinkPoisoned):
            sink.read_channel_admissions("not-a-digest")
        sink.close()
        with pytest.raises(AuditSinkPoisoned):
            sink.read_channel_admissions(ACTION_DIGEST)
    finally:
        os.close(host_fd)


@pytest.mark.parametrize(
    "injected",
    [
        pytest.param(b'{"accepted":false,"code":"channel_refused"', id="torn-tail"),
        pytest.param(b"\n", id="blank-line"),
        pytest.param(b"[" * 2000 + b"]" * 2000 + b"\n", id="deeply-nested-line"),
        pytest.param(
            canonical(
                {
                    "accepted": False,
                    "action_digest": ACTION_DIGEST,
                    "channel_ref": CHANNEL_REF,
                    "code": "channel_refused",
                    "policy_id": "some-other-policy",
                    "schema": CHANNEL_AUDIT_SCHEMA,
                    "tool": "commit_text_patch",
                }
            ).encode("ascii")
            + b"\n",
            id="off-policy-row",
        ),
        pytest.param(
            canonical(
                {
                    "accepted": False,
                    "action_digest": ACTION_DIGEST,
                    "channel_ref": CHANNEL_REF,
                    "code": "channel_refused",
                    "extra": 1,
                    "policy_id": POLICY_ID,
                    "schema": CHANNEL_AUDIT_SCHEMA,
                    "tool": "commit_text_patch",
                }
            ).encode("ascii")
            + b"\n",
            id="extra-key",
        ),
        pytest.param(
            (
                canonical(
                    {
                        "accepted": False,
                        "action_digest": ACTION_DIGEST,
                        "channel_ref": CHANNEL_REF,
                        "code": "channel_refused",
                        "policy_id": POLICY_ID,
                        "schema": CHANNEL_AUDIT_SCHEMA,
                        "tool": "commit_text_patch",
                    }
                ).replace(",", ", ")
            ).encode("ascii")
            + b"\n",
            id="non-canonical-whitespace",
        ),
        pytest.param(
            canonical(
                {
                    "accepted": True,
                    "action_digest": ACTION_DIGEST,
                    "channel_ref": CHANNEL_REF,
                    "code": "channel_refused",
                    "policy_id": POLICY_ID,
                    "schema": CHANNEL_AUDIT_SCHEMA,
                    "tool": "commit_text_patch",
                }
            ).encode("ascii")
            + b"\n",
            id="accepted-flag-contradicts-code",
        ),
        pytest.param(
            canonical(
                {
                    "accepted": False,
                    "code": "channel_refused",
                    "policy_id": POLICY_ID,
                    "schema": CHANNEL_AUDIT_SCHEMA,
                }
            ).encode("ascii")
            + b"\n",
            id="channel-code-in-oauth-shape",
        ),
    ],
)
def test_read_channel_admissions_refuses_torn_foreign_or_off_contract_lines(
    tmp_path: Path, injected: bytes
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        _seed_ledger(sink)
        sink.close()
        # The ledger is edited while no sink owns it (a restart gap).  Reopen
        # sees only a size; the read must refuse to speak for any action.
        with open(directory / "auth-audit.jsonl", "ab") as handle:
            handle.write(injected)
        reopened = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        try:
            with pytest.raises(AuditSinkPoisoned):
                reopened.read_channel_admissions(ACTION_DIGEST)
            with pytest.raises(AuditSinkPoisoned):
                reopened.read_channel_admissions(OTHER_DIGEST)
        finally:
            reopened.close()
    finally:
        os.close(host_fd)


def test_read_channel_admissions_refuses_size_or_identity_drift(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        _seed_ledger(sink)
        assert len(sink.read_channel_admissions(ACTION_DIGEST)) == 2
        named = directory / "auth-audit.jsonl"
        content = named.read_bytes()
        # Out-of-band append: the named file is larger than the owned size.
        with open(named, "ab") as handle:
            handle.write(b"\n")
        with pytest.raises(AuditSinkPoisoned):
            sink.read_channel_admissions(ACTION_DIGEST)
        # Identity replacement with byte-identical content: the owned
        # description no longer names the file, so nothing is readable.
        forged = directory / "forged.jsonl"
        forged.write_bytes(content)
        os.chmod(forged, 0o600)
        os.replace(forged, named)
        with pytest.raises(AuditSinkPoisoned):
            sink.read_channel_admissions(ACTION_DIGEST)
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(channel_event(code="accepted", tool="workspace_manifest"))
        with pytest.raises(AuditSinkPoisoned):
            sink.close()
    finally:
        os.close(host_fd)


def _row(
    *,
    tool: str,
    code: str,
    digest: str = ACTION_DIGEST,
    channel_ref: str = CHANNEL_REF,
    policy_id: str = POLICY_ID,
    accepted: bool | None = None,
    schema: str = CHANNEL_AUDIT_SCHEMA,
) -> ChannelAuditEvent:
    return channel_event(
        code=code,
        accepted=accepted,
        tool=tool,
        channel_ref=channel_ref,
        action_digest=digest,
        policy_id=policy_id,
        schema=schema,
    )


@pytest.mark.parametrize(
    "rows,expected",
    [
        pytest.param((), ADMISSION_ABSENT, id="empty"),
        pytest.param(
            (_row(tool="reconcile_text_patch", code="accepted"),),
            ADMISSION_ABSENT,
            id="only-read-side-admissions",
        ),
        pytest.param(
            (_row(tool="commit_text_patch", code="channel_refused"),),
            ADMISSION_REFUSED_ONLY,
            id="single-refusal",
        ),
        pytest.param(
            (
                _row(tool="commit_text_patch", code="channel_refused"),
                _row(tool="reconcile_text_patch", code="accepted"),
                _row(tool="commit_text_patch", code="channel_refused"),
            ),
            ADMISSION_REFUSED_ONLY,
            id="repeated-refusals-with-reconcile-reads",
        ),
        pytest.param(
            (
                _row(tool="commit_text_patch", code="channel_refused"),
                _row(tool="commit_text_patch", code="accepted"),
            ),
            ADMISSION_ACCEPTED,
            id="refused-then-accepted",
        ),
        pytest.param(
            (
                _row(tool="commit_text_patch", code="accepted"),
                _row(tool="commit_text_patch", code="channel_refused"),
            ),
            ADMISSION_ACCEPTED,
            id="accepted-then-refused",
        ),
        pytest.param(
            (
                _row(tool="commit_text_patch", code="channel_refused"),
                _row(
                    tool="commit_text_patch",
                    code="accepted",
                    channel_ref=OTHER_CHANNEL_REF,
                ),
            ),
            ADMISSION_ACCEPTED,
            id="another-channel-accepted-the-same-digest",
        ),
        pytest.param(
            (
                _row(tool="commit_text_patch", code="channel_refused"),
                _row(tool="run_project_command", code="accepted"),
            ),
            ADMISSION_ACCEPTED,
            id="other-modifying-tool-accepted-the-same-digest",
        ),
        pytest.param(
            (_row(tool="run_project_command", code="channel_refused"),),
            ADMISSION_ABSENT,
            id="refusal-of-a-different-modifying-tool-is-not-evidence",
        ),
        pytest.param(
            (_row(tool="commit_text_patch", code="channel_refused", digest=OTHER_DIGEST),),
            ADMISSION_ABSENT,
            id="refusal-of-a-different-digest-is-not-evidence",
        ),
        pytest.param(
            (
                _row(
                    tool="commit_text_patch",
                    code="channel_refused",
                    channel_ref=OTHER_CHANNEL_REF,
                ),
            ),
            ADMISSION_UNCERTAIN,
            id="refusal-under-another-channel-identity",
        ),
        pytest.param(
            (
                _row(
                    tool="commit_text_patch",
                    code="channel_refused",
                    policy_id="some-other-policy",
                ),
            ),
            ADMISSION_UNCERTAIN,
            id="refusal-under-another-policy-identity",
        ),
        pytest.param(
            (_row(tool="commit_text_patch", code="request_refused"),),
            ADMISSION_UNCERTAIN,
            id="non-channel-refusal-code-on-a-modifying-tool",
        ),
        pytest.param(
            (_row(tool="commit_text_patch", code="channel_refused", accepted=True),),
            ADMISSION_UNCERTAIN,
            id="contradictory-accepted-flag",
        ),
        pytest.param(
            (
                _row(tool="commit_text_patch", code="channel_refused"),
                _row(
                    tool="reconcile_text_patch",
                    code="accepted",
                    schema=AUTH_AUDIT_SCHEMA,
                ),
            ),
            ADMISSION_UNCERTAIN,
            id="wrong-schema-on-any-row-for-the-digest",
        ),
    ],
)
def test_classify_channel_admissions_verdicts(rows, expected) -> None:
    assert (
        classify_channel_admissions(
            rows,
            action_digest=ACTION_DIGEST,
            channel_ref=CHANNEL_REF,
            policy_id=POLICY_ID,
            modifying_tool="commit_text_patch",
        )
        == expected
    )


def test_classify_channel_admissions_refuses_invalid_identity_inputs() -> None:
    rows = (_row(tool="commit_text_patch", code="channel_refused"),)
    assert (
        classify_channel_admissions(
            rows,
            action_digest="short",
            channel_ref=CHANNEL_REF,
            policy_id=POLICY_ID,
            modifying_tool="commit_text_patch",
        )
        == ADMISSION_UNCERTAIN
    )
    assert (
        classify_channel_admissions(
            rows,
            action_digest=ACTION_DIGEST,
            channel_ref=CHANNEL_REF,
            policy_id=POLICY_ID,
            modifying_tool="reconcile_text_patch",
        )
        == ADMISSION_UNCERTAIN
    )

"""Pre-dispatch channel refusal is reconcilable as NOT_APPLIED (#670).

Production observed a stable lease expiring between ``prepare_text_patch`` and
``commit_text_patch``: the tunnel durably recorded ``channel_refused`` for the
exact action digest before any dispatch, no artifact existed, the source stayed
at its preimage, yet ``reconcile_text_patch`` after a same-carrier lease refresh
answered ``EFFECT_UNKNOWN`` forever.  These tests pin the repaired contract:
the existing durable admission ledger is the only evidence consumed, only exact
refused-before-dispatch history yields ``NOT_APPLIED``, any accepted modifying
admission or ledger doubt stays ``EFFECT_UNKNOWN``, restarts retain the
evidence, and no second effect can follow.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import time

import pytest

import integrations.workbench_action_mcp.tunnel as tunnel_module
from integrations.business_mcp_auth.contracts import CHANNEL_AUDIT_SCHEMA
from integrations.workbench_action_mcp.runtime import (
    StableWorkbenchActionLease,
    WorkbenchActionRuntime,
    channel_binding_ref,
)
from integrations.workbench_action_mcp.tunnel import (
    create_tunnel_action_server,
    parse_tunnel_config,
)
from integrations.workbench_read_mcp.runtime import RuntimeCloseUncertain
from tests.workbench_action_mcp.test_tunnel import (
    CHANNEL,
    KEY_A,
    _audit_lines,
    _call,
    _document,
    _error_code,
    _lease,
    _tools,
)
from tests.workbench_action_mcp.test_tunnel_unified_composition import (
    RECIPE_ROOT,
    _file_sha256,
    _install_boot_observer,
)

POLICY_ID = "workbench-action-tunnel-fixture"
LEASE_MS = 30_000
ACTION_TTL_MS = 60_000
_PRIVATE_PYTHON = ""


@pytest.fixture(scope="module", autouse=True)
def _bind_private_python(private_python_executable: str):
    global _PRIVATE_PYTHON
    _PRIVATE_PYTHON = private_python_executable
    yield
    _PRIVATE_PYTHON = ""


@pytest.fixture
def stable_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boot_observer(monkeypatch, "test-stable-boot-session")


def _digest(action_ref: str) -> str:
    return hashlib.sha256(action_ref.encode("utf-8")).hexdigest()


def _rows_for(audit: Path, action_ref: str) -> list[tuple[str, str]]:
    digest = _digest(action_ref)
    return [
        (row["tool"], row["code"])
        for row in _audit_lines(audit)
        if row["action_digest"] == digest
    ]


class Carrier:
    """One fixed channel over persistent project/audit/artifact directories.

    ``open`` composes a fresh runtime (a restart) over the same descriptors
    with a controllable clock; ``refresh`` issues the same-carrier lease with a
    later expiry, changing nothing else the prepared action is bound to.
    """

    def __init__(self, tmp_path: Path) -> None:
        self.project = tmp_path / "project"
        self.audit = tmp_path / "audit"
        self.artifact = tmp_path / "artifacts"
        for directory in (self.project, self.audit, self.artifact):
            directory.mkdir(mode=0o700)
        self.now_ms = int(time.time() * 1000)
        self.clock = {"ms": self.now_ms}
        self.fds = [
            os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            for directory in (self.project, self.audit, self.artifact)
        ]
        document, _, _, _ = _document(tmp_path, tag="command-binding")
        assert _PRIVATE_PYTHON
        document.update(
            {
                "python_executable": _PRIVATE_PYTHON,
                "python_sha256": _file_sha256(_PRIVATE_PYTHON),
                "recipe_root": RECIPE_ROOT,
            }
        )
        self.config = parse_tunnel_config(document)
        self.lease = dataclasses.replace(
            _lease(CHANNEL, self.now_ms), lease_expires_at_ms=self.now_ms + LEASE_MS
        )
        self.project_ref = self.lease.project_ref

    def refresh(self) -> None:
        self.lease = dataclasses.replace(
            self.lease, lease_expires_at_ms=self.clock["ms"] + LEASE_MS
        )

    def expire_lease(self) -> None:
        self.clock["ms"] = self.lease.lease_expires_at_ms

    def open(self, *, policy_id: str = POLICY_ID) -> WorkbenchActionRuntime:
        runtime = WorkbenchActionRuntime.open_channel(
            channel=CHANNEL,
            clock_ms=lambda: self.clock["ms"],
            project_directory_fd=self.fds[0],
            audit_directory_fd=self.fds[1],
            host_artifact_fd=self.fds[2],
            host_id="a" * 64,
            audit_policy_id=policy_id,
            lease=self.lease,
            action_token_key=bytes.fromhex(KEY_A),
            max_concurrency=1,
            io_timeout_seconds=5.0,
            action_ttl_ms=ACTION_TTL_MS,
        )
        tunnel_module._bind_command_host(runtime, self.config)
        return runtime

    def close(self) -> None:
        for fd in self.fds:
            os.close(fd)


@pytest.fixture
def carrier(tmp_path: Path):
    value = Carrier(tmp_path)
    try:
        yield value
    finally:
        value.close()


async def _with_runtime(carrier: Carrier, body, **kwargs):
    runtime = carrier.open(**kwargs)
    try:
        return await body(create_tunnel_action_server(runtime))
    finally:
        await runtime.aclose(timeout=5.0)


def _prepare_patch(carrier: Carrier, original: bytes):
    async def body(server):
        prepared = await _call(
            server,
            "prepare_text_patch",
            {
                "project_ref": carrier.project_ref,
                "relative_path": "sample.py",
                "mode": "REPLACE",
                "expected_sha256": hashlib.sha256(original).hexdigest(),
                "old_text": "value = 1",
                "new_text": "value = 2",
            },
        )
        assert prepared.isError is False
        return prepared.structuredContent["action_ref"]

    return body


def _refused_patch_phase(carrier: Carrier, original: bytes):
    """Prepare, expire the lease on the same runtime, then have commit refused."""

    async def body(server):
        action_ref = await _prepare_patch(carrier, original)(server)
        carrier.expire_lease()
        refused = await _call(server, "commit_text_patch", {"action_ref": action_ref})
        assert _error_code(refused) == "CHANNEL_ADMISSION_REFUSED"
        return action_ref

    return body


def test_channel_refused_commit_reconciles_not_applied_after_same_carrier_refresh(
    carrier: Carrier,
) -> None:
    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    preimage = hashlib.sha256(original).hexdigest()

    action_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))

    # Durable refusal is recorded before any effect dispatch: no artifact, no
    # claim, source at the exact preimage, and the ledger names the digest.
    assert os.listdir(carrier.artifact) == []
    assert hashlib.sha256(target.read_bytes()).hexdigest() == preimage
    assert _rows_for(carrier.audit, action_ref) == [("commit_text_patch", "channel_refused")]
    assert all(
        row["channel_ref"] == channel_binding_ref(CHANNEL)
        and row["policy_id"] == POLICY_ID
        and row["schema"] == CHANNEL_AUDIT_SCHEMA
        for row in _audit_lines(carrier.audit)
    )

    # Same-carrier lease refresh on a fresh runtime (restart): the reconcile
    # consumes the durable refusal and classifies NOT_APPLIED, twice, without
    # writing anything.
    carrier.refresh()

    async def reconcile_twice(server):
        first = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
        second = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
        return first, second

    first, second = asyncio.run(_with_runtime(carrier, reconcile_twice))
    for observed in (first, second):
        assert observed.isError is False
        assert observed.structuredContent["effect_state"] == "NOT_APPLIED"
        assert observed.structuredContent["observed_sha256"] == preimage
        assert observed.structuredContent["cleanup_state"] == "CLEAN"
    assert os.listdir(carrier.artifact) == []
    assert target.read_bytes() == original
    assert _rows_for(carrier.audit, action_ref) == [
        ("commit_text_patch", "channel_refused"),
        ("reconcile_text_patch", "accepted"),
        ("reconcile_text_patch", "accepted"),
    ]


def test_not_applied_action_is_recovered_by_one_replacement_without_second_write(
    carrier: Carrier,
) -> None:
    """Same-action replay rules are intact.  An action prepared under the
    expired lease expires with it (its expiry is bounded by the lease), so
    recovery is a replacement action against the same preimage: it applies
    exactly once, replays without a second write, and the stale action never
    gains an artifact."""

    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    stale_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))
    carrier.refresh()

    async def recover(server):
        before = await _call(server, "reconcile_text_patch", {"action_ref": stale_ref})
        assert before.structuredContent["effect_state"] == "NOT_APPLIED"
        replacement_ref = await _prepare_patch(carrier, original)(server)
        assert replacement_ref != stale_ref
        committed = await _call(
            server, "commit_text_patch", {"action_ref": replacement_ref}
        )
        assert committed.isError is False
        assert committed.structuredContent["effect_state"] == "APPLIED"
        applied_stat = target.stat()
        replayed = await _call(
            server, "commit_text_patch", {"action_ref": replacement_ref}
        )
        assert replayed.structuredContent["effect_state"] == "APPLIED"
        # The stale reference expired with its lease: it can never apply, and
        # its reconcile now reads a moved-on source, which is not NOT_APPLIED.
        stale_commit = await _call(server, "commit_text_patch", {"action_ref": stale_ref})
        assert _error_code(stale_commit) == "ACTION_EXPIRED"
        stale = await _call(server, "reconcile_text_patch", {"action_ref": stale_ref})
        assert stale.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
        assert stale.structuredContent["observed_sha256"] == hashlib.sha256(
            b"value = 2\n"
        ).hexdigest()
        return applied_stat, replacement_ref

    applied_stat, replacement_ref = asyncio.run(_with_runtime(carrier, recover))
    final = target.stat()
    assert target.read_bytes() == b"value = 2\n"
    assert (final.st_ino, final.st_mtime_ns, final.st_size) == (
        applied_stat.st_ino,
        applied_stat.st_mtime_ns,
        applied_stat.st_size,
    )
    assert len([name for name in os.listdir(carrier.artifact) if "claim" in name]) == 1
    assert _rows_for(carrier.audit, replacement_ref) == [
        ("commit_text_patch", "accepted"),
        ("commit_text_patch", "accepted"),
    ]


def test_any_accepted_modifying_admission_returns_the_action_to_effect_unknown(
    carrier: Carrier,
) -> None:
    """An accepted commit admission the port later refused (expired action) is
    not durably distinguishable from one lost before its claim, so the
    conservative classification is EFFECT_UNKNOWN, not NOT_APPLIED."""

    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    action_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))
    carrier.clock["ms"] += ACTION_TTL_MS
    carrier.refresh()

    async def expired_commit(server):
        before = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
        assert before.structuredContent["effect_state"] == "NOT_APPLIED"
        expired = await _call(server, "commit_text_patch", {"action_ref": action_ref})
        assert _error_code(expired) == "ACTION_EXPIRED"
        after = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
        return after

    after = asyncio.run(_with_runtime(carrier, expired_commit))
    assert after.isError is False
    assert after.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
    assert target.read_bytes() == original
    assert os.listdir(carrier.artifact) == []
    assert ("commit_text_patch", "accepted") in _rows_for(carrier.audit, action_ref)


def test_source_drift_after_refusal_stays_effect_unknown(carrier: Carrier) -> None:
    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    action_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))
    target.write_bytes(b"value = 3\n")
    carrier.refresh()

    async def reconcile(server):
        return await _call(server, "reconcile_text_patch", {"action_ref": action_ref})

    observed = asyncio.run(_with_runtime(carrier, reconcile))
    assert observed.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
    assert observed.structuredContent["observed_sha256"] == hashlib.sha256(
        b"value = 3\n"
    ).hexdigest()


def _canonical(payload: dict) -> bytes:
    return (
        json.dumps(
            payload, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        + b"\n"
    )


def _forged_row(action_ref: str, **overrides) -> bytes:
    payload = {
        "accepted": False,
        "action_digest": _digest(action_ref),
        "channel_ref": channel_binding_ref(CHANNEL),
        "code": "channel_refused",
        "policy_id": POLICY_ID,
        "schema": CHANNEL_AUDIT_SCHEMA,
        "tool": "commit_text_patch",
    }
    payload.update(overrides)
    return _canonical(payload)


@pytest.mark.parametrize(
    "poison",
    [
        pytest.param(lambda ref: b'{"accepted":false,"code":"chan', id="torn-tail"),
        pytest.param(
            lambda ref: _forged_row(ref, policy_id="workbench-action-tunnel-other"),
            id="refusal-under-another-policy-identity",
        ),
        pytest.param(
            lambda ref: _forged_row(ref, channel_ref="f" * 64),
            id="refusal-under-another-channel-identity",
        ),
        pytest.param(
            lambda ref: _forged_row(ref, accepted=True, code="accepted", channel_ref="f" * 64),
            id="another-channel-accepted-the-digest",
        ),
        pytest.param(
            lambda ref: _forged_row(ref, accepted=True, code="accepted", tool="run_project_command"),
            id="another-modifying-tool-accepted-the-digest",
        ),
    ],
)
def test_ledger_poison_or_identity_change_between_restarts_fails_closed(
    carrier: Carrier, poison
) -> None:
    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    action_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))
    with open(carrier.audit / "auth-audit.jsonl", "ab") as handle:
        handle.write(poison(action_ref))
    carrier.refresh()

    async def reconcile(server):
        return await _call(server, "reconcile_text_patch", {"action_ref": action_ref})

    observed = asyncio.run(_with_runtime(carrier, reconcile))
    assert observed.isError is False
    assert observed.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
    assert target.read_bytes() == original
    assert os.listdir(carrier.artifact) == []


def test_refusal_recorded_under_a_different_audit_policy_is_not_consumed(
    carrier: Carrier,
) -> None:
    """The restarted composition's audit identity must match the ledger that
    recorded the refusal.  A rotated policy still appends to the same named
    ledger, so the rows under the old identity make the ledger unreadable for
    the new one: the action fails closed to EFFECT_UNKNOWN."""

    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    action_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))
    carrier.refresh()

    async def reconcile(server):
        return await _call(server, "reconcile_text_patch", {"action_ref": action_ref})

    observed = asyncio.run(
        _with_runtime(carrier, reconcile, policy_id="workbench-action-tunnel-rotated")
    )
    assert observed.isError is False
    assert observed.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
    assert target.read_bytes() == original
    assert os.listdir(carrier.artifact) == []


def test_live_ledger_identity_change_blocks_reconcile_and_every_effect(
    carrier: Carrier,
) -> None:
    target = carrier.project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
    action_ref = asyncio.run(_with_runtime(carrier, _refused_patch_phase(carrier, original)))
    carrier.refresh()

    async def replace_then_reconcile(server):
        first = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
        assert first.structuredContent["effect_state"] == "NOT_APPLIED"
        named = carrier.audit / "auth-audit.jsonl"
        forged = carrier.audit / "forged.jsonl"
        forged.write_bytes(named.read_bytes())
        os.chmod(forged, 0o600)
        os.replace(forged, named)
        second = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
        commit = await _call(server, "commit_text_patch", {"action_ref": action_ref})
        return second, commit

    async def exercise():
        runtime = carrier.open()
        try:
            return await replace_then_reconcile(create_tunnel_action_server(runtime))
        finally:
            # The owned ledger no longer names the file: closing it is
            # uncertain by design, and that is the sink's own contract.
            with pytest.raises(RuntimeCloseUncertain):
                await runtime.aclose(timeout=5.0)

    second, commit = asyncio.run(exercise())
    assert _error_code(second) == "CHANNEL_AUDIT_UNAVAILABLE"
    assert _error_code(commit) == "CHANNEL_AUDIT_UNAVAILABLE"
    assert target.read_bytes() == original
    assert os.listdir(carrier.artifact) == []


def _prepare_command(carrier: Carrier, content: bytes):
    async def body(server):
        prepared = await _call(
            server,
            "prepare_project_command",
            {
                "project_ref": carrier.project_ref,
                "relative_path": "sample.py",
                "recipe_id": "canary_checksum",
                "expected_sha256": hashlib.sha256(content).hexdigest(),
            },
        )
        assert prepared.isError is False
        return prepared.structuredContent["action_ref"]

    return body


def _refused_run_phase(carrier: Carrier, content: bytes):
    async def body(server):
        action_ref = await _prepare_command(carrier, content)(server)
        carrier.expire_lease()
        refused = await _call(server, "run_project_command", {"action_ref": action_ref})
        assert _error_code(refused) == "CHANNEL_ADMISSION_REFUSED"
        return action_ref

    return body


def test_channel_refused_run_reconciles_not_applied_with_patch_parity(
    carrier: Carrier, stable_boot: None
) -> None:
    target = carrier.project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)
    stale_ref = asyncio.run(_with_runtime(carrier, _refused_run_phase(carrier, content)))
    assert os.listdir(carrier.artifact) == []
    assert _rows_for(carrier.audit, stale_ref) == [("run_project_command", "channel_refused")]
    carrier.refresh()

    async def reconcile_read_then_recover(server):
        reconciled = await _call(server, "reconcile_action", {"action_ref": stale_ref})
        page = await _call(
            server,
            "read_action_result",
            {"action_ref": stale_ref, "stream": "stdout"},
        )
        # Recovery is one replacement run; the stale reference expired with
        # its lease and can never spawn.
        replacement_ref = await _prepare_command(carrier, content)(server)
        ran = await _call(server, "run_project_command", {"action_ref": replacement_ref})
        replayed = await _call(
            server, "run_project_command", {"action_ref": replacement_ref}
        )
        after = await _call(server, "reconcile_action", {"action_ref": replacement_ref})
        stale_run = await _call(server, "run_project_command", {"action_ref": stale_ref})
        stale = await _call(server, "reconcile_action", {"action_ref": stale_ref})
        return reconciled, page, ran, replayed, after, stale_run, stale

    reconciled, page, ran, replayed, after, stale_run, stale = asyncio.run(
        _with_runtime(carrier, reconcile_read_then_recover)
    )
    for receipt in (reconciled, page):
        assert receipt.isError is False
        assert receipt.structuredContent["effect_state"] == "NOT_APPLIED"
        assert receipt.structuredContent["cleanup_state"] == "CLEAN"
        assert "exit_code" not in receipt.structuredContent
    # One admitted run is the only spawn; the replay and the later reconcile
    # read the same retained evidence without a second process.
    assert ran.isError is False
    assert ran.structuredContent["effect_state"] == "APPLIED"
    assert ran.structuredContent["exit_code"] == 0
    identity = ran.structuredContent["process_identity"]
    assert replayed.structuredContent["process_identity"] == identity
    assert after.structuredContent["process_identity"] == identity
    assert _error_code(stale_run) == "ACTION_EXPIRED"
    # The stale reference now carries an accepted run admission the port
    # refused before any claim: conservatively unknown, never a second spawn.
    assert stale.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
    assert len([name for name in os.listdir(carrier.artifact) if "claim" in name]) == 1
    assert target.read_bytes() == content


def test_run_reconcile_stays_unknown_after_an_accepted_run_admission(
    carrier: Carrier, stable_boot: None
) -> None:
    target = carrier.project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)
    action_ref = asyncio.run(_with_runtime(carrier, _refused_run_phase(carrier, content)))
    carrier.clock["ms"] += ACTION_TTL_MS
    carrier.refresh()

    async def expired_run(server):
        before = await _call(server, "reconcile_action", {"action_ref": action_ref})
        assert before.structuredContent["effect_state"] == "NOT_APPLIED"
        expired = await _call(server, "run_project_command", {"action_ref": action_ref})
        assert _error_code(expired) == "ACTION_EXPIRED"
        return await _call(server, "reconcile_action", {"action_ref": action_ref})

    after = asyncio.run(_with_runtime(carrier, expired_run))
    assert after.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
    assert os.listdir(carrier.artifact) == []


def test_eleven_tool_inventory_and_effect_vocabulary_are_closed(carrier: Carrier) -> None:
    async def inventory(server):
        return await _tools(server)

    tools = asyncio.run(_with_runtime(carrier, inventory))
    assert {tool.name for tool in tools} == {
        "workspace_manifest",
        "read_project_file",
        "preview_text_replace",
        "prepare_text_patch",
        "commit_text_patch",
        "reconcile_text_patch",
        "prepare_project_command",
        "run_project_command",
        "read_action_result",
        "read_action_artifact",
        "reconcile_action",
    }
    by_name = {tool.name: tool for tool in tools}
    for name in ("reconcile_text_patch", "reconcile_action"):
        assert by_name[name].annotations.readOnlyHint is True
        assert by_name[name].outputSchema["properties"]["effect_state"]["enum"] == [
            "NOT_APPLIED",
            "APPLIED",
            "EFFECT_UNKNOWN",
        ]

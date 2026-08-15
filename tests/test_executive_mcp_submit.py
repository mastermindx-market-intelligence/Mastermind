"""EXEC-MCP-A modifying-path acceptance (commission §20 — all 21 items).

Every test here drives a **real** temporary ``ExecutiveControlService`` over a
temporary AF_UNIX socket, backed by a real ``Runtime``.  The
adapter → service → ``ceo_intent`` → runtime chain is NOT mocked: the only
injected seams are the boot-packet source (an environment fact, so tests do not
have to build two git checkouts per case) and, in the failure-injection cases,
the transport WRAPPER around the real client.

The supervisor is ``_NoExecutionSupervisor``: it raises if anything on this path
ever tries to start or finish work, so "submission is not execution" is proven
by making execution impossible to perform quietly rather than by asserting its
absence afterwards.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from control_plane import ceo_boot_packet
from control_plane.executive_runtime import JobStatus, Runtime
from control_plane.executive_service import (
    ExecutiveControlService,
    ServiceConfig,
    send_control_request,
)
from integrations.executive_mcp import schemas
from integrations.executive_mcp.adapter import (
    ExecutiveMcpGateway,
    FixtureBackend,
    GatewayConfig,
)
from integrations.executive_mcp.schemas import MODIFYING_TOOL, ServerMode

_FROZEN_NOW = "2026-08-15T00:00:00Z"
_MASTERMIND_SHA = "1" * 40
_MACRO_SHA = "2" * 40


# ---------------------------------------------------------------------------
# harness — mirrors tests/test_ceo_intent.py's _config/_service/_request
# ---------------------------------------------------------------------------


@pytest.fixture
def short_socket_root():
    # Darwin's sockaddr_un path ceiling is only 104 bytes; pytest's native
    # temporary path is intentionally much longer than a production /var/run path.
    value = Path(tempfile.mkdtemp(prefix="mmx-mcp-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


class _NoExecutionSupervisor:
    """Fails loudly if anything on this path tries to run work."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def reconcile_restart(self, *, requeue_lost: bool = False):
        return []

    async def start_job(self, job_id: str):  # pragma: no cover - assertion hook
        raise AssertionError(f"MCP submission must never start job {job_id}")

    async def finish_job(self, active):  # pragma: no cover - assertion hook
        raise AssertionError("MCP submission must never finish a job")


def _workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspaces"


def _service_config(tmp_path: Path, socket_root: Path) -> ServiceConfig:
    source = tmp_path / "proof-source"
    source.mkdir(parents=True, exist_ok=True)
    return ServiceConfig(
        runtime_root=tmp_path / "runtime",
        socket_path=socket_root / "executive.sock",
        proof_source_repository=source,
        proof_workspace_root=_workspace_root(tmp_path),
        proof_base_sha="a" * 40,
        proof_shared_gid=os.getegid(),
        backup_root=tmp_path / "backups",
        allowed_peer_uids=(os.geteuid(),),
        shutdown_grace_seconds=0.1,
    )


def _service(tmp_path: Path, socket_root: Path) -> ExecutiveControlService:
    return ExecutiveControlService(
        _service_config(tmp_path, socket_root),
        supervisor_factory=_NoExecutionSupervisor,
    )


def _packet(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schema": ceo_boot_packet.SCHEMA,
        "generated_at": _FROZEN_NOW,
        "mastermind": {"root": str(tmp_path), "sha": _MASTERMIND_SHA, "branch": "master"},
        "macro": {
            "root": str(tmp_path / "macro"),
            "sha": _MACRO_SHA,
            "resolved_via": "env",
            "candidates_tried": [],
        },
        "strategic_state": None,
        "brief": None,
        "handoffs": [],
        "degraded": [],
        "next_recommended_act": "fixture",
    }
    for key, value in overrides.items():
        if key in ("mastermind", "macro") and isinstance(value, dict):
            packet[key] = {**packet[key], **value}
        else:
            packet[key] = value
    return packet


@pytest.fixture(autouse=True)
def stable_head_shas(monkeypatch: pytest.MonkeyPatch):
    """Make the R3 re-read deterministic and, crucially, MOVABLE.

    ``_reread_identities`` routes through ``ceo_boot_packet.git_sha`` — a public
    wrapper that delegates on every call precisely so a test can move it.  The
    default mapping agrees with the injected packet; a test that wants the
    TOCTOU seam makes it disagree.
    """

    heads = {"mastermind": _MASTERMIND_SHA, "macro": _MACRO_SHA}

    def fake_git_sha(path: Path | str) -> str | None:
        return heads["macro"] if str(path).endswith("macro") else heads["mastermind"]

    monkeypatch.setattr(ceo_boot_packet, "git_sha", fake_git_sha)
    return heads


def _gateway(
    tmp_path: Path,
    service: ExecutiveControlService,
    *,
    packet: dict[str, Any] | None = None,
    transport: Any = None,
) -> ExecutiveMcpGateway:
    document = packet if packet is not None else _packet(tmp_path)
    config = GatewayConfig(
        mode=ServerMode.FIXTURE,
        repo_root=tmp_path,
        fixture=FixtureBackend(
            socket_path=str(service.socket_path),
            runtime_root=str(service.config.runtime_root),
            workspace_root=str(service.config.proof_workspace_root),
        ),
        now=_FROZEN_NOW,
    )
    return ExecutiveMcpGateway(
        config,
        packet_builder=lambda **_kw: dict(document),
        clock=lambda: _FROZEN_NOW,
        transport=transport or send_control_request,
    )


def _run(tmp_path: Path, socket_root: Path, exercise, *, packet=None, transport=None):
    async def main():
        service = _service(tmp_path, socket_root)
        await service.start()
        try:
            gateway = _gateway(tmp_path, service, packet=packet, transport=transport)
            return await exercise(gateway, service)
        finally:
            await service.close()

    return asyncio.run(main())


def _args(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation_key": "options-chain-browser-closure-001",
        "objective": "Implement the assigned bounded deliverable and return evidence.",
        "department": "executive-infrastructure",
        "priority": 10,
        "execution_profile": "research_only",
    }
    payload.update(overrides)
    return payload


def _bounded_args(**overrides: Any) -> dict[str, Any]:
    payload = _args(
        execution_profile="bounded_code_change",
        allowed_write_paths=["control_plane/example.py", "tests/test_example.py"],
        validation={
            "pytest_targets": ["tests/test_example.py"],
            "compileall_paths": ["control_plane"],
            "git_diff_check": True,
        },
        attempt_limit=2,
    )
    payload.update(overrides)
    return payload


def _reader(service: ExecutiveControlService) -> Runtime:
    return Runtime.at(service.config.runtime_root, create=False)


def _jobs(service: ExecutiveControlService) -> list[Any]:
    return _reader(service).jobs.list_jobs()


# ===========================================================================
# §20.1 – §20.4 — acceptance shape
# ===========================================================================


def test_20_01_research_only_submission_creates_exactly_one_queued_job(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["ok"] is True, envelope
        receipt = envelope["data"]
        assert receipt["schema"] == "mastermind.ceo_intent_receipt.v1"
        assert receipt["accepted"] is True
        assert receipt["duplicate"] is False
        assert receipt["status"] == JobStatus.QUEUED.value

        jobs = _jobs(service)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.job_id == receipt["job_id"]
        assert job.status is JobStatus.QUEUED
        assert job.requested_authorities == ["READ", "RESEARCH"]
        assert job.allowed_write_paths == []
        assert job.validation_commands == []
        assert job.branch == f"codex/{receipt['intent_id']}"
        assert receipt["intent_id"].startswith("mcp-")
        assert receipt["grounding"] == {
            "mastermind_sha": _MASTERMIND_SHA,
            "macro_sha": _MACRO_SHA,
            "boot_packet_schema": ceo_boot_packet.SCHEMA,
        }
        return receipt

    _run(tmp_path, short_socket_root, exercise)


def test_20_02_bounded_code_change_carries_only_the_derived_capabilities(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _bounded_args())
        assert envelope["ok"] is True, envelope
        receipt = envelope["data"]
        jobs = _jobs(service)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.requested_authorities == ["READ", "RUN_TESTS", "WRITE_BRANCH"]
        assert receipt["authority"]["requested"] == ["READ", "RUN_TESTS", "WRITE_BRANCH"]
        assert job.allowed_write_paths == ["control_plane/example.py", "tests/test_example.py"]
        # Gateway-constructed argv only — no caller string ever reaches argv[0].
        assert job.validation_commands == [
            ["python3", "-m", "pytest", "-q", "tests/test_example.py"],
            ["python3", "-m", "compileall", "control_plane"],
            ["git", "diff", "--check"],
        ]
        # The worktree is fenced under the reviewed workspace root.
        assert job.worktree is not None
        assert Path(job.worktree).parent == Path(
            str(service.config.proof_workspace_root)
        ).resolve()
        assert Path(job.worktree).name == receipt["intent_id"]
        assert job.attempt_limit == 2
        assert receipt["authority"]["policy_sha256"]
        for forbidden in ("OPEN_PR", "PUSH_BRANCH", "MERGE", "DEPLOY", "CROSS_REPO_PUBLISH"):
            assert forbidden not in job.requested_authorities

    _run(tmp_path, short_socket_root, exercise)


def test_20_03_receipt_reports_dispatched_false(tmp_path: Path, short_socket_root: Path):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["data"]["dispatched"] is False

    _run(tmp_path, short_socket_root, exercise)


def test_20_04_no_worker_or_supervisor_invocation_occurs(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _bounded_args())
        assert envelope["ok"] is True
        runtime = _reader(service)
        job_id = envelope["data"]["job_id"]
        # The supervisor raises on any start/finish; additionally prove the
        # durable state carries no attempt, no worker, and no lease.
        assert runtime.attempts.list_attempts(job_id) == []
        assert runtime.workers.list_workers() == []
        job = runtime.jobs.get_job(job_id)
        assert job.attempt_count == 0
        assert job.current_attempt_id is None
        assert job.assigned_worker_id is None

    _run(tmp_path, short_socket_root, exercise)


# ===========================================================================
# §20.5 – §20.8 — idempotency and conflict
# ===========================================================================


def test_20_05_same_key_same_envelope_returns_the_same_job(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        first = await gateway.call(MODIFYING_TOOL, _args())
        second = await gateway.call(MODIFYING_TOOL, _args())
        assert first["ok"] is True and second["ok"] is True
        assert first["data"]["job_id"] == second["data"]["job_id"]
        assert first["data"]["intent_id"] == second["data"]["intent_id"]
        assert first["data"]["fingerprint"] == second["data"]["fingerprint"]
        assert first["data"]["duplicate"] is False
        assert second["data"]["duplicate"] is True
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"objective": "a completely different objective"}, id="objective"),
        pytest.param({"priority": 11}, id="priority"),
        pytest.param({"department": "product-engineering"}, id="department"),
        pytest.param({"workstream": "WS:EXECUTIVE_OS"}, id="workstream"),
        pytest.param({"attempt_limit": 3}, id="attempt-limit"),
    ],
)
def test_20_06_same_key_changed_envelope_refuses(
    tmp_path: Path, short_socket_root: Path, mutation: dict[str, Any]
):
    async def exercise(gateway, service):
        first = await gateway.call(MODIFYING_TOOL, _args())
        assert first["ok"] is True
        second = await gateway.call(MODIFYING_TOOL, _args(**mutation))
        assert second["ok"] is False, second
        assert second["error"]["code"] == "backend_refused"
        assert "already accepted" in second["error"]["message"]
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


def test_20_07_same_key_changed_write_paths_refuses(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        first = await gateway.call(MODIFYING_TOOL, _bounded_args())
        assert first["ok"] is True
        second = await gateway.call(
            MODIFYING_TOOL,
            _bounded_args(allowed_write_paths=["control_plane/other.py", "tests/test_other.py"]),
        )
        assert second["ok"] is False
        assert second["error"]["code"] == "backend_refused"
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


def test_20_08_same_key_changed_profile_refuses(tmp_path: Path, short_socket_root: Path):
    async def exercise(gateway, service):
        first = await gateway.call(MODIFYING_TOOL, _args())
        assert first["ok"] is True
        second = await gateway.call(MODIFYING_TOOL, _bounded_args())
        assert second["ok"] is False
        assert second["error"]["code"] == "backend_refused"
        assert "already accepted" in second["error"]["message"]
        jobs = _jobs(service)
        assert len(jobs) == 1
        # The surviving Job kept the FIRST profile's authority — a conflicting
        # retry must never quietly upgrade an accepted intent.
        assert jobs[0].requested_authorities == ["READ", "RESEARCH"]

    _run(tmp_path, short_socket_root, exercise)


# ===========================================================================
# §20.9 – §20.12 — authority and grounding fail closed
# ===========================================================================


def test_20_09_authority_refusal_creates_no_job(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """The DOWNSTREAM policy is the adjudicator, and its denial creates no Job.

    The gateway's own ceiling is lifted here on purpose: this test must prove
    that ``config/authority_map.yml`` refuses ``MERGE``, not merely that the
    gateway refused to ask for it (which is proven separately in the mutation
    battery).
    """

    monkeypatch.setattr(
        schemas, "PROFILE_CAPABILITY_CEILING", frozenset({"READ", "RESEARCH", "MERGE"})
    )
    monkeypatch.setattr(
        schemas,
        "EXECUTION_PROFILES",
        {**schemas.EXECUTION_PROFILES, "research_only": ("READ", "MERGE")},
    )

    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["ok"] is False, envelope
        assert envelope["error"]["code"] == "authority_refused"
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


@pytest.mark.parametrize(
    "packet_override,expected_fragment",
    [
        pytest.param({"mastermind": {"sha": None}}, "mastermind grounding", id="no-mastermind-sha"),
        pytest.param({"macro": {"sha": None}}, "macro grounding", id="no-macro-sha"),
        pytest.param({"macro": {"sha": "abc"}}, "macro grounding", id="short-macro-sha"),
        pytest.param({"macro": {"sha": "A" * 40}}, "macro grounding", id="uppercase-sha"),
        pytest.param({"macro": {"root": None}}, "Macro checkout", id="unresolved-macro"),
    ],
)
def test_20_10_missing_grounding_creates_no_job(
    tmp_path: Path, short_socket_root: Path, packet_override: dict, expected_fragment: str
):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["ok"] is False, envelope
        assert envelope["error"]["code"] == "grounding_unavailable"
        assert expected_fragment in envelope["error"]["message"]
        assert _jobs(service) == []

    _run(
        tmp_path,
        short_socket_root,
        exercise,
        packet=_packet(tmp_path, **packet_override),
    )


def test_20_11_unknown_boot_packet_schema_creates_no_job(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "grounding_unavailable"
        assert "boot packet schema" in envelope["error"]["message"]
        assert _jobs(service) == []

    _run(
        tmp_path,
        short_socket_root,
        exercise,
        packet=_packet(tmp_path, schema="mastermind.ceo_boot_packet.v99"),
    )


@pytest.mark.parametrize("moved", ["mastermind", "macro"])
def test_20_12_grounding_changed_between_snapshot_and_send_creates_no_job(
    tmp_path: Path, short_socket_root: Path, stable_head_shas: dict, moved: str
):
    """R3 — the TOCTOU seam is closed, and closing it is observable."""

    stable_head_shas[moved] = "9" * 40

    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["ok"] is False, envelope
        assert envelope["error"]["code"] == "grounding_changed"
        assert "no Job was created" in envelope["error"]["message"]
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


def test_20_12b_the_second_grounding_read_is_a_real_git_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The re-read shells out to git rather than replaying the snapshot."""

    # Undo the harness stub: this one case must exercise the REAL git path, or
    # every other case would be proving a fixture rather than the re-read.
    monkeypatch.setattr(ceo_boot_packet, "git_sha", ceo_boot_packet._git_sha)

    repo = tmp_path / "repo"
    macro = tmp_path / "macro"
    shas: dict[str, str] = {}
    for name, root in (("repo", repo), ("macro", macro)):
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "F"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "f@example.invalid"], check=True
        )
        (root / "a.txt").write_text(name, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", name], check=True)
        shas[name] = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.strip()

    config = GatewayConfig(mode=ServerMode.READONLY, repo_root=repo, now=_FROZEN_NOW)
    gateway = ExecutiveMcpGateway(config, clock=lambda: _FROZEN_NOW)
    assert gateway._reread_identities(str(macro)) == (shas["repo"], shas["macro"])


# ===========================================================================
# §20.13 – §20.18 — the input surface fails closed
# ===========================================================================


@pytest.mark.parametrize(
    "path,label",
    [
        ("/etc/passwd", "absolute"),
        ("/Users/someone/.ssh/authorized_keys", "absolute-home"),
        ("~/notes.md", "tilde"),
        ("../macro/engine/thing.py", "parent"),
        ("control_plane/../../escape.py", "embedded-parent"),
        (".git/config", "git-dir"),
        ("control_plane/.git/hooks/pre-commit", "nested-git-dir"),
        (".gitmodules", "git-internals"),
        ("--output=/tmp/pwn", "flag-shaped"),
        ("control_plane/x\x00y.py", "nul"),
        ("control_plane\\example.py", "backslash"),
    ],
)
def test_20_13_14_15_unsafe_write_paths_refuse(
    tmp_path: Path, short_socket_root: Path, path: str, label: str
):
    async def exercise(gateway, service):
        envelope = await gateway.call(
            MODIFYING_TOOL,
            _bounded_args(allowed_write_paths=[path, "tests/test_example.py"]),
        )
        assert envelope["ok"] is False, (label, envelope)
        assert envelope["error"]["code"] == "invalid_input"
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


def test_20_16_model_supplied_argv_is_impossible_by_schema():
    """R4 — there is no schema position, and no code path, for caller argv."""

    submit_schema = schemas.tool_spec(MODIFYING_TOOL).input_schema
    assert "validation_commands" not in submit_schema["properties"]
    validation = submit_schema["properties"]["validation"]
    assert set(validation["properties"]) == {
        "pytest_targets",
        "compileall_paths",
        "git_diff_check",
    }
    assert validation["additionalProperties"] is False

    for payload in (
        {"validation_commands": [["bash", "-c", "id"]]},
        {"validation": {"argv": ["sh", "-c", "id"]}},
        {"validation": {"command": "rm -rf /"}},
        {"validation": {"pytest_targets": ["tests/x.py"], "shell": True}},
    ):
        with pytest.raises(schemas.GatewayError) as excinfo:
            schemas.validate_tool_arguments(MODIFYING_TOOL, _bounded_args(**payload))
        assert excinfo.value.code == "invalid_input"

    # Every constructed command starts with a gateway-owned program name and
    # carries no caller-supplied flag.
    commands = schemas.build_validation_commands(
        {
            "pytest_targets": ["tests/test_a.py", "tests/test_b.py"],
            "compileall_paths": ["control_plane", "common"],
            "git_diff_check": True,
        }
    )
    assert [command[0] for command in commands] == ["python3", "python3", "git"]
    assert commands[0][:4] == ["python3", "-m", "pytest", "-q"]
    assert commands[1][:3] == ["python3", "-m", "compileall"]
    assert commands[2] == ["git", "diff", "--check"]
    for command in commands:
        assert command[0] not in {"sh", "bash", "zsh", "env", "command"}
        assert "-c" not in command


@pytest.mark.parametrize(
    "target",
    [
        "control_plane/test_thing.py",
        "tests_extra/test_thing.py",
        "../tests/test_thing.py",
        "/tests/test_thing.py",
        "tests/test_thing.txt",
        "tests",
        "-p no:cacheprovider",
        "tests/../control_plane/x.py",
    ],
)
def test_20_17_invalid_pytest_target_refuses(
    tmp_path: Path, short_socket_root: Path, target: str
):
    async def exercise(gateway, service):
        envelope = await gateway.call(
            MODIFYING_TOOL, _bounded_args(validation={"pytest_targets": [target]})
        )
        assert envelope["ok"] is False, (target, envelope)
        assert envelope["error"]["code"] == "invalid_input"
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


@pytest.mark.parametrize("attempt_limit", [0, -1, 4, 20, 21, True, 1.5, "2", None])
def test_20_18_attempt_limit_outside_the_mcp_bound_refuses(
    tmp_path: Path, short_socket_root: Path, attempt_limit: Any
):
    async def exercise(gateway, service):
        envelope = await gateway.call(
            MODIFYING_TOOL, _args(attempt_limit=attempt_limit)
        )
        assert envelope["ok"] is False, (attempt_limit, envelope)
        assert envelope["error"]["code"] == "invalid_input"
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


@pytest.mark.parametrize(
    "override",
    [
        {"priority": True},
        {"priority": 101},
        {"priority": -101},
        {"priority": "10"},
        {"operation_key": "AB"},
        {"operation_key": "Has-Capitals"},
        {"operation_key": "has_underscore"},
        {"objective": ""},
        {"objective": "x" * 4001},
        {"department": "Executive"},
        {"workstream": "EXECUTIVE_OS"},
        {"execution_profile": "full_access"},
    ],
)
def test_20_18b_out_of_bound_scalars_refuse(
    tmp_path: Path, short_socket_root: Path, override: dict
):
    async def exercise(gateway, service):
        envelope = await gateway.call(MODIFYING_TOOL, _args(**override))
        assert envelope["ok"] is False, (override, envelope)
        assert envelope["error"]["code"] == "invalid_input"
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


def test_20_18c_profile_coherence_is_enforced(tmp_path: Path, short_socket_root: Path):
    async def exercise(gateway, service):
        # research_only may not carry write paths or validation...
        for override in (
            {"allowed_write_paths": ["control_plane/x.py"]},
            {"validation": {"git_diff_check": True}},
        ):
            envelope = await gateway.call(MODIFYING_TOOL, _args(**override))
            assert envelope["ok"] is False
            assert envelope["error"]["code"] == "invalid_input"
        # ...and bounded_code_change requires both.
        for override in (
            {"allowed_write_paths": []},
            {"validation": {}},
        ):
            envelope = await gateway.call(MODIFYING_TOOL, _bounded_args(**override))
            assert envelope["ok"] is False
            assert envelope["error"]["code"] == "invalid_input"
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


# ===========================================================================
# §20.19 – §20.21 — failure recovery and concurrency
# ===========================================================================


def test_20_19_process_death_after_commit_recovers_one_job(
    tmp_path: Path, short_socket_root: Path
):
    """The service commits, the reply never arrives, the caller retries.

    The retry runs through a FRESH gateway object — a new process would have a
    new write lock and no memory of the first call — and must reconcile onto the
    Job that already exists rather than create a second one.
    """

    async def exercise(gateway, service):
        async def dying_transport(socket_path, command, args=None, **kwargs):
            # The durable commit happens, and THEN the response is lost.
            await send_control_request(socket_path, command, args, **kwargs)
            raise ConnectionResetError("MCP process died before replying")

        gateway._transport = dying_transport
        lost = await gateway.call(MODIFYING_TOOL, _args())
        assert lost["ok"] is False
        assert lost["error"]["code"] == "backend_unavailable"

        # The Job is already durable even though ChatGPT never saw a receipt.
        jobs_after_loss = _jobs(service)
        assert len(jobs_after_loss) == 1

        fresh = _gateway(tmp_path, service)
        recovered = await fresh.call(MODIFYING_TOOL, _args())
        assert recovered["ok"] is True, recovered
        assert recovered["data"]["duplicate"] is True
        assert recovered["data"]["job_id"] == jobs_after_loss[0].job_id
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


def test_20_20_two_concurrent_identical_calls_yield_one_durable_job(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        # Two INDEPENDENT gateways: a single process's write lock would
        # serialize the race away and prove nothing about the durable index.
        second = _gateway(tmp_path, service)
        first_result, second_result = await asyncio.gather(
            gateway.call(MODIFYING_TOOL, _args()),
            second.call(MODIFYING_TOOL, _args()),
        )
        assert first_result["ok"] is True, first_result
        assert second_result["ok"] is True, second_result
        assert first_result["data"]["job_id"] == second_result["data"]["job_id"]
        duplicates = [
            result["data"]["duplicate"] for result in (first_result, second_result)
        ]
        assert sorted(duplicates) == [False, True]
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


def test_20_21_two_concurrent_conflicting_calls_yield_one_job_and_one_conflict(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        second = _gateway(tmp_path, service)
        results = await asyncio.gather(
            gateway.call(MODIFYING_TOOL, _args()),
            second.call(MODIFYING_TOOL, _args(objective="a conflicting objective")),
        )
        accepted = [result for result in results if result["ok"]]
        refused = [result for result in results if not result["ok"]]
        assert len(accepted) == 1, results
        assert len(refused) == 1, results
        assert refused[0]["error"]["code"] == "backend_refused"
        assert "already accepted" in refused[0]["error"]["message"]
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


def test_write_lock_serializes_modifying_calls_within_one_process(
    tmp_path: Path, short_socket_root: Path
):
    """R12/§16 — at most one modifying call in flight per MCP process."""

    async def exercise(gateway, service):
        in_flight = 0
        peak = 0

        async def counting_transport(socket_path, command, args=None, **kwargs):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            try:
                await asyncio.sleep(0.05)
                return await send_control_request(socket_path, command, args, **kwargs)
            finally:
                in_flight -= 1

        gateway._transport = counting_transport
        await asyncio.gather(
            gateway.call(MODIFYING_TOOL, _args()),
            gateway.call(MODIFYING_TOOL, _args()),
            gateway.call(MODIFYING_TOOL, _args()),
        )
        assert peak == 1
        assert len(_jobs(service)) == 1

    _run(tmp_path, short_socket_root, exercise)


def test_submit_never_retries_a_modifying_call(tmp_path: Path, short_socket_root: Path):
    async def exercise(gateway, service):
        calls: list[str] = []

        async def failing_transport(socket_path, command, args=None, **kwargs):
            calls.append(command)
            raise ConnectionRefusedError("service is down")

        gateway._transport = failing_transport
        envelope = await gateway.call(MODIFYING_TOOL, _args())
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "backend_unavailable"
        assert calls == ["submit-ceo-intent"], calls
        assert schemas.MAX_SUBMIT_RETRIES == 0
        assert _jobs(service) == []

    _run(tmp_path, short_socket_root, exercise)


def test_intent_identity_is_derived_from_the_operation_key_alone():
    """§10.6 — a changed payload must COLLIDE, not fork into a second Job."""

    a = schemas.derive_intent_id("options-chain-browser-closure-001")
    b = schemas.derive_intent_id("options-chain-browser-closure-001")
    c = schemas.derive_intent_id("options-chain-browser-closure-002")
    assert a == b != c
    assert a.startswith("mcp-") and len(a) == 36
    assert schemas.derive_branch(a) == f"codex/{a}"
    assert schemas.derive_worktree("/tmp/ws", a) == f"/tmp/ws/{a}"


def test_ceo_intent_status_reads_back_a_submitted_intent(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        submitted = await gateway.call(MODIFYING_TOOL, _args())
        assert submitted["ok"] is True
        status = await gateway.call(
            "ceo_intent_status", {"intent_id": submitted["data"]["intent_id"]}
        )
        assert status["ok"] is True, status
        assert status["data"]["job_id"] == submitted["data"]["job_id"]
        assert status["data"]["dispatched"] is False
        assert status["data"]["duplicate"] is False

        job = await gateway.call("executive_job", {"job_id": submitted["data"]["job_id"]})
        assert job["ok"] is True
        assert job["data"]["job"]["status"] == "QUEUED"
        assert job["data"]["attempt_count"] == 0

    _run(tmp_path, short_socket_root, exercise)


def test_fixture_mode_states_the_read_write_root_split(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise(gateway, service):
        envelope = await gateway.call("executive_state", {})
        assert envelope["ok"] is True
        assert any("mode=fixture" in entry for entry in envelope["degraded"]), envelope[
            "degraded"
        ]

    _run(tmp_path, short_socket_root, exercise)

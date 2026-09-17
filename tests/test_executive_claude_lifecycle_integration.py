"""Integration proof: the real ClaudeCodeWorkerAdapter through the real
ExecutiveSupervisor lifecycle, with a real launched subprocess.

Scope (PF1 frozen spec, 2026-09-17). This module proves that
``control_plane.claude_worker.ClaudeCodeWorkerAdapter`` satisfies the
canonical ``control_plane.executive_supervisor.ExecutiveSupervisor`` worker
contract end to end: one real subprocess (the committed deterministic fake,
``scripts/ohf/fake_claude_cli.py``, never a native Claude binary), a real
pid/pgid/process-start-identity recorded by the supervisor via its own
real ``ProcessInspector``, a real evidence chain (launch attestation +
collection receipt), and a terminal state that survives a ``Runtime.at(...)``
reopen.

It is deliberately NOT the native canary and does NOT prove a successful
round trip. The one driving call, ``asyncio.run(supervisor.run_once(job_id))``,
is measured to terminate in a REFUSAL on the result-content leg: the fake
CLI's frozen protocol can only ever return the derived
``{"decision": "HOLD", "evidence_sha256": ...}`` shape (see
``control_plane/claude_cli_protocol.py``), which shares no keys with the
Executive supervisor's twelve-key generated result schema. That refusal is
the designed outcome of PF1-F0's fake-only effect ceiling -- a Job-conformant
result can only come from a real model turn, which the fake forbids by
construction and which the adjudicated principal/auth decision blocks for
the real binary. It is not a defect in this slice, in the adapter, or in the
supervisor, and every assertion below pins the *measured* value of that
refusal rather than engineering around it.

Template: reuses the shapes of ``tests/test_executive_supervisor.py``'s
``_runtime_and_job``/``_supervisor`` helpers and the assertion pattern of its
``test_run_once_persists_process_checkpoint_result_receipt_and_reopens``.
``tests/test_w6b_native_round_trip.py`` is deliberately not used as a
template -- its own embedded FINDING already records that the work leg
cannot complete hermetically for any provider.
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

import control_plane.claude_cli_protocol as protocol
import control_plane.claude_worker as cw
from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    worker_result_schema,
)
from control_plane.worker_adapter import adapter_descriptor
from control_plane.worker_execution_contract import WorkerRunStatus


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "scripts" / "ohf" / "fake_claude_cli.py"
MODEL = "claude-opus-4-6"
VERSION = "2.1.259"


@pytest.fixture(autouse=True)
def _scrub_ambient_credentials(monkeypatch: pytest.MonkeyPatch):
    """Never depend on the caller's shell for a clean environment.

    Same rationale as ``tests/test_executive_claude_worker.py``'s fixture of
    the same name: a shell inside a Claude Code session exports ~29
    ANTHROPIC_*/CLAUDE_* variables, and the adapter correctly fails closed
    with ``PROVIDER_ENV_REFUSED`` if any leak through. Scrubbing here is
    about keeping this suite robust under a contaminated shell -- it is not
    what causes the result-content refusal measured below, which is a
    protocol/schema mismatch, not an environment rejection.
    """

    for key in list(os.environ):
        if key.startswith("ANTHROPIC") or key.startswith("CLAUDE"):
            monkeypatch.delenv(key, raising=False)
    yield


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _runtime_and_claude_job(tmp_path: Path) -> tuple[Runtime, str, Path]:
    """Register a claude-code worker and create one profile-less legacy Job.

    Mirrors ``tests/test_executive_supervisor.py::_runtime_and_job`` shape by
    shape, with provider/model relabelled for this adapter. The Job's
    ``constraints`` carry no ``execution_profile_id`` -- per
    ``executive_supervisor.py:980-982`` that keeps it on the legacy path and
    skips ``_validate_execution_profile`` entirely, which is required here
    because the closed ``_EXECUTION_SURFACES`` choice
    (``executive_agent_capabilities.py:70``) has no Claude surface at all.
    """

    runtime = Runtime.at(tmp_path, lease_seconds=30)
    runtime.workers.register_worker(
        "claude-01",
        provider="claude-code",
        account_label="manually-authenticated",
        worker_type="claude-code-cli",
        capabilities=["research", "code", "tests"],
        quota_classes={
            "claude-native": {
                "capabilities": ["research", "code", "tests"],
                "model": MODEL,
                "effort": "xhigh",
                "cost_class": "standard",
            }
        },
    )
    workspace = tmp_path / "workspaces" / "isolated-workspace"
    workspace.mkdir(mode=0o700, parents=True)
    job = runtime.jobs.create_job(
        "Prove the Claude Code worker adapter satisfies the Executive "
        "supervisor contract end to end",
        worktree=str(workspace.resolve()),
        requested_authorities=["READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"],
        allowed_write_paths=["research/proof.md"],
        validation_commands=[["/usr/bin/true"]],
        constraints={
            "provider": "claude-code",
            "model": MODEL,
            "effort": "xhigh",
            "cost_class": "standard",
            "base_sha": "c" * 40,
            "eligible_quota_classes": ["claude-native"],
            "required_capabilities": ["research", "code", "tests"],
        },
        attempt_limit=3,
    )
    return runtime, job.job_id, workspace


def _claude_adapter(tmp_path: Path) -> cw.ClaudeCodeWorkerAdapter:
    """Construct the real adapter over the committed deterministic fake.

    ``isolated_home``/``isolated_tmp`` only pin one private isolation base
    (their shared parent) at construction time; the adapter mints a fresh
    per-run ``<isolation_base>/<run_id>/{home,tmp,claude_fake_state.json}``
    triad inside ``start()`` (``claude_worker.py:500-509``), so this base
    directory is never itself the run's HOME/TMPDIR.
    """

    base = tmp_path / "claude-adapter-base"
    home = base / "home"
    tmp = base / "tmp"
    home.mkdir(parents=True, mode=0o700)
    tmp.mkdir(parents=True, mode=0o700)
    return cw.ClaudeCodeWorkerAdapter(
        FAKE.resolve(),
        isolated_home=home,
        isolated_tmp=tmp,
        model=MODEL,
        version=VERSION,
        fake_controls={"MMX_FAKE_CLAUDE_SCENARIO": "ok"},
    )


def _claude_supervisor(
    runtime: Runtime, tmp_path: Path, adapter: cw.ClaudeCodeWorkerAdapter
) -> ExecutiveSupervisor:
    """Bind the real adapter directly into the real supervisor.

    Deliberately never routes through ``ExecutiveWorkerBroker`` -- its
    ``implemented`` gate for ``claude-code`` stays closed so autonomous
    Claude routing remains disarmed (see ``tests/test_worker_adapter.py``).

    ``inspector=``/``process_controller=`` are omitted so
    ``executive_supervisor.py:570-571`` binds its real defaults
    (``adapter.inspector`` -- a real, ``ps``-based
    ``control_plane.claude_worker.ProcessInspector`` -- and a real
    ``IdentitySafeProcessController``): letting the real ones bind is the
    point of this proof.

    ``require_complete_launch_attestation`` is left at its default
    (``False``), which is a deliberate departure from
    ``test_executive_supervisor.py::_supervisor``'s ``True``. That template
    value is only satisfiable by an adapter exposing a
    ``launch_attestation(ref)`` method; ``ClaudeCodeWorkerAdapter`` has none
    (confirmed: no such method exists on the class). Leaving the require
    flag ``True`` would make ``_launch_metadata`` raise
    ``SupervisorError("worker adapter did not provide a complete launch
    attestation")`` immediately after a successful real launch and BEFORE
    ``record_process``/``mark_running`` -- i.e. before any pid or
    ATTEMPT_PROCESS_RECORDED event exists -- which would substitute a
    launch-attestation-shaped refusal for the result-content refusal this
    slice exists to measure. With the default ``False``, the adapter's
    legacy-partial attestation (still carrying the real pid/pgid/start
    identity/boot id) is accepted and the run proceeds all the way to the
    real result-content leg.
    """

    return ExecutiveSupervisor(
        runtime,
        adapter,  # type: ignore[arg-type]
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        heartbeat_interval_seconds=0.02,
        secret_canary_verdict={
            "schema_version": "mastermind.executive_secret_canary/v1",
            "passed": True,
            "checks": {
                "control_service_environment": "DENIED",
                "administrative_checkout": "DENIED",
                "executive_database": "DENIED",
                "other_worker_home": "DENIED",
                "forbidden_production_path": "DENIED",
            },
            "receipt_sha256": "a" * 64,
            "control_environment_probe_sha256": "b" * 64,
            "observed_at": "2026-09-17T00:00:00Z",
            "worker_auth_exception": "DEDICATED_CLAUDE_HOME_ONLY",
        },
        instance_id="claude-lifecycle-fixture",
    )


def test_claude_code_adapter_drives_real_supervisor_lifecycle_to_measured_result_content_refusal(
    tmp_path: Path,
):
    """Real ClaudeCodeWorkerAdapter, real ExecutiveSupervisor, real subprocess.

    This is the integration proof itself. It drives
    ``asyncio.run(supervisor.run_once(job_id))`` over a profile-less legacy
    Job and asserts every measured artifact of a genuine claim -> launch ->
    real process record -> RUNNING -> collect -> validate -> terminalize
    sequence: a real pid and process_start_identity recorded by the
    supervisor (never fabricated -- the pid is independently confirmed dead
    by the time collection completes, exactly as a real one-shot child
    should be), ATTEMPT_PROCESS_RECORDED preceding ATTEMPT_RUNNING in the
    durable event stream, a private (0600) launch attestation file that
    never contains the Job's prompt-bearing objective text, and a private
    (0600) collection evidence file whose recorded result status is the
    measured refusal.

    The terminal REFUSAL itself -- ``WorkerRunStatus.INVALID_RESULT``
    surfacing as ``JobStatus.FAILED``/``AttemptStatus.FAILED`` with a reason
    naming the Executive result schema's twelve missing required keys -- is
    the designed outcome of PF1-F0's fake-only effect ceiling: the fake CLI
    can only ever return its frozen ``{"decision": "HOLD",
    "evidence_sha256": ...}`` derived result (``claude_cli_protocol.py:
    557-558``), which was never going to satisfy the supervisor's generated,
    ``additionalProperties: False`` result schema. This is not a bug in the
    adapter, the supervisor, or this test; a Job-conformant result can only
    come from a real model turn, which this slice deliberately cannot
    produce.
    """

    runtime, job_id, _workspace = _runtime_and_claude_job(tmp_path)
    job_before = runtime.jobs.get_job(job_id)
    assert job_before is not None
    objective = job_before.objective
    assert "execution_profile_id" not in job_before.constraints

    adapter = _claude_adapter(tmp_path)
    supervisor = _claude_supervisor(runtime, tmp_path, adapter)

    receipt = asyncio.run(supervisor.run_once(job_id))

    # -- Real process identity, recorded by the supervisor, never fabricated.
    assert isinstance(receipt.attempt.pid, int)
    assert receipt.attempt.pid > 1
    assert isinstance(receipt.attempt.process_start_identity, str)
    assert receipt.attempt.process_start_identity
    assert receipt.attempt.boot_id == adapter.inspector.boot_session_id()
    # The fake CLI is a genuine one-shot child: by the time collection has
    # completed it has already exited and been reaped, which a fabricated
    # or stubbed pid could never demonstrate.
    assert _pid_alive(receipt.attempt.pid) is False

    # -- ATTEMPT_PROCESS_RECORDED precedes ATTEMPT_RUNNING in the event stream.
    event_types = [
        event.event_type
        for event in runtime.events.list_events(attempt_id=receipt.attempt.attempt_id)
    ]
    assert "ATTEMPT_PROCESS_RECORDED" in event_types
    assert "ATTEMPT_RUNNING" in event_types
    assert event_types.index("ATTEMPT_PROCESS_RECORDED") < event_types.index(
        "ATTEMPT_RUNNING"
    )

    # -- Launch attestation: private, real process identity, no prompt leak.
    launch_metadata = receipt.attempt.launch_metadata
    assert launch_metadata is not None
    launch_evidence = Path(launch_metadata["launch_attestation_path"])
    assert launch_evidence.is_file()
    assert stat.S_IMODE(launch_evidence.stat().st_mode) == 0o600
    launch_evidence_text = launch_evidence.read_text(encoding="utf-8")
    assert objective not in launch_evidence_text
    attestation = launch_metadata["launch_attestation"]
    # ClaudeCodeWorkerAdapter exposes no launch_attestation(ref) method, so
    # the supervisor's own legacy-partial fallback is what is measured here
    # -- it still carries the real process identity the fallback exists to
    # preserve.
    assert (
        attestation["schema_version"]
        == "mastermind.executive_launch_attestation/legacy-partial"
    )
    assert attestation["process_identity"]["pid"] == receipt.attempt.pid
    assert (
        attestation["process_identity"]["start_identity"]
        == receipt.attempt.process_start_identity
    )

    # -- Collection evidence: private, records the measured refusal status.
    collection_evidence = Path(receipt.collection_receipt_path)
    assert collection_evidence.is_file()
    assert stat.S_IMODE(collection_evidence.stat().st_mode) == 0o600
    persisted = json.loads(collection_evidence.read_text(encoding="utf-8"))
    # ClaudeCodeWorkerAdapter exposes no uid_sweep_receipt() method, so
    # _persist_collection's wrapped-with-uid_sweep branch never applies here
    # -- the persisted evidence is the bare collection-receipt dict, not the
    # {"collection": ..., "uid_sweep": ...} envelope a UID-sweep-capable
    # adapter (e.g. the real Codex adapter) would produce.
    assert "collection" not in persisted
    measured_result_status = persisted["result"]["status"]
    assert measured_result_status == WorkerRunStatus.INVALID_RESULT.value

    # -- Terminal Job/Attempt statuses, measured (not assumed) and asserted
    #    at their measured value.
    assert receipt.job.status is JobStatus.FAILED
    assert receipt.attempt.status is AttemptStatus.FAILED

    # -- Refusal reason names the missing required keys.
    assert receipt.job.result is not None
    reason_text = " ".join(receipt.job.result.get("errors") or [])
    assert "structured output missing required keys" in reason_text
    for required_key in worker_result_schema(
        job_id=job_id, run_id=receipt.attempt.attempt_id, worker_id="claude-01"
    )["required"]:
        assert required_key in reason_text

    # -- Terminal state survives a fresh Runtime reopen.
    reopened = Runtime.at(tmp_path)
    reopened_job = reopened.jobs.get_job(job_id)
    reopened_attempt = reopened.attempts.get_attempt(receipt.attempt.attempt_id)
    assert reopened_job is not None
    assert reopened_job.status is JobStatus.FAILED
    assert reopened_attempt is not None
    assert reopened_attempt.status is AttemptStatus.FAILED
    assert reopened_attempt.result == reopened_job.result


def test_claude_derived_result_key_set_is_incompatible_with_supervisor_schema(
    tmp_path: Path,
):
    """Pin the exact incompatibility that produces the refusal above.

    This does not drive the supervisor at all; it directly compares the two
    frozen shapes whose mismatch is the entire reason
    ``test_claude_code_adapter_drives_real_supervisor_lifecycle_to_measured_result_content_refusal``
    above terminates in ``INVALID_RESULT``/``FAILED``: the fake CLI's
    protocol-derived result (``claude_cli_protocol.py:557-558``, always
    exactly ``{"decision": "HOLD", "evidence_sha256": "<64 hex>"}``) against
    the Executive supervisor's generated, ``additionalProperties: False``,
    twelve-required-key result schema (``executive_supervisor.py:373-390``).

    This mismatch is the designed edge of PF1-F0's fake-only effect ceiling,
    not a defect: the derived result is deliberately the only thing the
    frozen protocol will ever produce without a real model turn, and the
    supervisor schema is deliberately closed. If a future change to either
    shape ever makes their key sets compatible, this test starts failing --
    which is exactly the point: it exists to surface that change, not to be
    "fixed" by loosening either shape.
    """

    derived_result = json.loads(protocol._derived_result("a" * 64))
    schema = worker_result_schema(job_id="job", run_id="run", worker_id="worker")

    assert set(derived_result) == {"decision", "evidence_sha256"}
    assert set(schema["required"]) == {
        "schema_version",
        "job_id",
        "run_id",
        "worker_id",
        "status",
        "summary",
        "completed_steps",
        "current_state",
        "artifacts",
        "next_actions",
        "errors",
        "validations",
    }
    # The two key sets share nothing, so every one of the schema's required
    # keys is unconditionally missing from any result the fake protocol can
    # ever derive -- this is what forces the INVALID_RESULT refusal.
    assert set(derived_result).isdisjoint(set(schema["required"]))


def test_claude_code_descriptor_remains_unimplemented_after_this_proof():
    """This integration proof must never quietly arm broker-routed Claude work.

    Kept alongside the refusal-pinning tests above for the same reason: the
    ``claude-code`` descriptor's ``implemented=False`` gate is what keeps
    ``ExecutiveWorkerBroker`` routing disarmed while the result-content leg
    cannot pass a real model turn (see the module docstring and
    ``tests/test_worker_adapter.py``). This test does not touch
    ``control_plane/worker_adapter.py``; it only measures that this file's
    real-adapter proof above -- which binds the adapter directly into
    ``ExecutiveSupervisor`` and never through the broker -- leaves that gate
    exactly where it found it.
    """

    descriptor = adapter_descriptor("claude-code")
    assert descriptor.adapter_id == "claude-code"
    assert descriptor.implemented is False

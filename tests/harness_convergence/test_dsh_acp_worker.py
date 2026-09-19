"""N1: actual pinned DSH ACP process through existing Worker v1 owners.

The native path is opt-in because its exact external supply is independently
qualified. Absence skips native proof; when MMX_DSH_N1_SUPPLY is set, missing
or altered supply is a hard failure rather than an implied pass.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from control_plane.worker_execution_contract import BinaryAttestation, WorkerLaunchSpec, WorkerRunStatus
from control_plane.executive_worker_broker import BrokerEffectUnknownError
from integrations.acp_worker.adapter import AcpWorkerAdapter
from integrations.acp_worker.native import AcpNativeProcessOwner, AcpNativeProfile
from integrations.acp_worker.turn import AcpProfile


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _native_supply() -> tuple[Path, Path, Path]:
    value = os.environ.get("MMX_DSH_N1_SUPPLY")
    if value is None:
        pytest.skip("MMX_DSH_N1_SUPPLY absent: real DSH ACP Worker proof NOT executed")
    root = Path(value).resolve(strict=True)
    node = (root / "node" / "bin" / "node").resolve(strict=True)
    bundle = (root / "build" / "dsh_acp_fixture.mjs").resolve(strict=True)
    manifest = (root / "supply-manifest.json").resolve(strict=True)
    return root, node, bundle


def _binary(path: Path) -> BinaryAttestation:
    info = path.stat()
    version = subprocess.run(
        [str(path), "--version"], check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    return BinaryAttestation(
        str(path), str(path), version, _sha256(path), None, info.st_size,
        info.st_dev, info.st_ino, info.st_mode & 0o7777, info.st_uid, info.st_gid,
        info.st_mtime_ns,
    )


def _git(workspace: Path, *args: str) -> str:
    env = {
        "PATH": os.defpath,
        "HOME": str(workspace.parent),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", *args], cwd=workspace, env=env, check=True,
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()


async def _exercise_real_dsh_acp_process(
    tmp_path: Path, *, behavior: str = "ok", cancel: bool = False,
    expect_effect_unknown: bool = False,
):
    root, node, bundle = _native_supply()
    manifest = json.loads((root / "supply-manifest.json").read_text(encoding="utf-8"))
    assert manifest["upstream_commit"] == "0d1f50007f9bca3f52b06e1c3074fa14d5fb0720"
    assert manifest["bundle_sha256"] == _sha256(bundle)
    assert manifest["node_sha256"] == _sha256(node)

    workspace = tmp_path / "workspace"
    run_dir = tmp_path / "run"
    workspace.mkdir(mode=0o700)
    run_dir.mkdir(mode=0o700)
    (run_dir / "input").mkdir(mode=0o700)
    os.chmod(workspace, 0o700)
    os.chmod(run_dir, 0o700)
    os.chmod(run_dir / "input", 0o700)
    _git(workspace, "init", "--template=", "-q")
    _git(
        workspace, "-c", "user.name=N1 Fixture", "-c",
        "user.email=n1@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "--allow-empty", "-qm", "fixture base",
    )
    base = _git(workspace, "rev-parse", "HEAD")
    schema_path = run_dir / "input" / "result.schema.json"
    schema_path.write_text(json.dumps({
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "fixture_model_calls": {"type": "integer", "const": 1},
        },
        "required": ["answer", "fixture_model_calls"],
        "additionalProperties": False,
    }), encoding="utf-8")

    home = tmp_path / "home"
    scratch = tmp_path / "scratch"
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    native_profile = AcpNativeProfile(
        "dsh-acp-n1-fixture", _binary(node), (str(node), str(bundle)),
    )
    owner = AcpNativeProcessOwner(
        native_profile,
        environment_loader=lambda: {
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(scratch),
            "LANG": "C",
            "TZ": "UTC",
            "MMX_N1_BEHAVIOR": behavior,
        },
    )
    adapter = AcpWorkerAdapter(
        AcpProfile(
            agent_name="deepseek-harness-acp",
            agent_version="0.0.1",
            model_option_provider="fixture",
        ),
        inspector=owner.inspector,
        open_run=owner.open_run,
    )
    spec = WorkerLaunchSpec(
        run_id="n1-run",
        job_id="N1-JOB",
        worker_id="n1-worker",
        workspace_path=workspace,
        run_dir=run_dir,
        prompt="Return the fixed N1 research result as the admitted JSON object.",
        result_schema_path=schema_path,
        authorities=("READ", "RESEARCH"),
        model="fixture-model",
        reasoning_effort="medium",
        timeout_seconds=10,
        cancel_grace_seconds=3,
        expected_base_sha=base,
        expected_worker_uid=os.geteuid(),
        expected_worker_gid=os.getegid(),
    )

    ref = await adapter.start(spec)
    receipt = None
    unknown = None
    try:
        if cancel:
            # DSH projects committed semantic updates, not raw streaming deltas.
            # The provider-free fixture emits this fixed nonsecret stderr marker
            # exactly when its hanging model stream is entered.
            stderr_path = Path(ref.stderr_path)
            for _ in range(100):
                if stderr_path.exists() and b"N1_PROMPT_IN_FLIGHT" in stderr_path.read_bytes():
                    break
                await asyncio.sleep(0.02)
            else:
                # Preserve the operation by cancelling through its original owner
                # before failing the readiness assertion.
                try:
                    await asyncio.wait_for(adapter.cancel(ref, "n1 readiness probe cleanup"), timeout=15)
                except Exception:
                    pass
                raise AssertionError("real DSH prompt did not reach the cancellable in-flight state")
            cancellation = await asyncio.wait_for(
                adapter.cancel(ref, "n1 requested cancellation"), timeout=15,
            )
            assert cancellation.run_id == ref.run_id
            assert cancellation.reason == "n1 requested cancellation"
            receipt = adapter._runs[ref.run_id].receipt
            assert receipt is not None
        else:
            try:
                receipt = await asyncio.wait_for(adapter.collect_result(ref), timeout=15)
            except BrokerEffectUnknownError as exc:
                if not expect_effect_unknown:
                    raise
                unknown = exc
    finally:
        assert owner._active is None
        assert adapter.unsettled_tasks == ()
    attestation = adapter.launch_attestation(ref)
    assert attestation["profile_id"] == "dsh-acp-n1-fixture"
    assert attestation["credential_values_persisted"] is False
    if receipt is not None:
        assert receipt.result.provider_session_id
        assert receipt.result.git_manifest["base_sha"] == base
        assert tuple(receipt.result.git_manifest["changed_paths"]) == ()
        assert receipt.result.exit_code == 0
        assert receipt.stdout_sha256 != hashlib.sha256(b"").hexdigest()
        expected_stderr = (
            hashlib.sha256(b"N1_PROMPT_IN_FLIGHT\n").hexdigest()
            if behavior == "hang"
            else hashlib.sha256(b"").hexdigest()
        )
        assert receipt.stderr_sha256 == expected_stderr
    return receipt, adapter._runs[ref.run_id], unknown


def test_real_dsh_acp_process_returns_existing_worker_result(tmp_path: Path) -> None:
    receipt, _, unknown = asyncio.run(_exercise_real_dsh_acp_process(tmp_path))
    assert unknown is None and receipt is not None
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    assert dict(receipt.result.structured_output or {}) == {
        "answer": "n1-dsh-acp",
        "fixture_model_calls": 1,
    }
    assert receipt.result.error is None
    assert receipt.result.git_manifest["head_sha"] is not None


def test_real_dsh_acp_invalid_result_never_becomes_success(tmp_path: Path) -> None:
    receipt, _, unknown = asyncio.run(_exercise_real_dsh_acp_process(tmp_path, behavior="invalid-result"))
    assert unknown is None and receipt is not None
    assert receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert receipt.result.structured_output is None
    assert receipt.result.error == "ACP_RESULT_REJECTED"


def test_real_dsh_acp_cancel_settles_original_prompt_and_process(tmp_path: Path) -> None:
    receipt, _, unknown = asyncio.run(_exercise_real_dsh_acp_process(
        tmp_path, behavior="hang", cancel=True,
    ))
    assert unknown is None and receipt is not None
    assert receipt.result.status is WorkerRunStatus.CANCELLED
    assert receipt.result.structured_output is None


def test_real_dsh_acp_tool_call_is_refused_by_read_only_profile(tmp_path: Path) -> None:
    receipt, run, unknown = asyncio.run(_exercise_real_dsh_acp_process(
        tmp_path, behavior="tool-call", expect_effect_unknown=True,
    ))
    assert receipt is None
    assert isinstance(unknown, BrokerEffectUnknownError)
    assert run.uncertain is True
    assert run.candidate is not None
    assert run.candidate.error in {"ACP_UNADMITTED_UPDATE", "ACP_FRAME_BOUNDARY_REFUSED"}
    assert run.candidate.effect_unknown is True

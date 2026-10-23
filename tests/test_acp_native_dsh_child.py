"""Real inherited native ACP FD consumed by an unprivileged Node child.

No installed DSH or model/provider call: this tests only the exact v2
parent-to-child socket boundary, without claiming an activated WorkerResult.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from control_plane.worker_execution_contract import BinaryAttestation
from integrations.acp_worker.native import AcpNativeProcessOwner, AcpNativeProfile
from integrations.acp_worker.tool_admission import AcpNativeToolGate, AcpObservedTool
from test_acp_native_startup import launch


def _build(launch, tmp_path, *, bad_digest=False, false_ready=False,
           abort_during_activation=False, late_dispose=False, expire_during_activation=False):
    profile, spec = launch
    node_cmd = shutil.which("node")
    assert node_cmd is not None, "Node is required for native DSH child proof"
    node = Path(node_cmd).resolve(strict=True)
    info = node.stat()
    version = subprocess.run([str(node), "--version"], capture_output=True,
                             text=True, check=True, timeout=4).stdout.strip()
    attested = BinaryAttestation(
        str(node), str(node), version, hashlib.sha256(node.read_bytes()).hexdigest(),
        None, info.st_size, info.st_dev, info.st_ino, info.st_mode & 0o7777,
        info.st_uid, info.st_gid, info.st_mtime_ns,
    )
    original = Path(__file__).resolve().parents[1]
    helper = original / "integrations/acp_worker/dsh_native_attempt.mjs"
    scenario = "deny" if false_ready else "normal"
    script = tmp_path / "attempt-reader.mjs"
    script.write_text("""
import { acceptNativeDshAttempt } from %s
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
const expectedProjectionSha256 = 'a'.repeat(64)
const expectedArtifactSha256 = %s
const controller = new AbortController()
try {
  const result = await acceptNativeDshAttempt({
    fd: Number(process.env.MMX_ACP_ATTEST_FD),
    signal: controller.signal,
    projectionDigest: expectedProjectionSha256,
    artifactDigest: expectedArtifactSha256,
    async activate(overlay, tools) {
      if (tools.length !== 1 || tools[0].name !== 'mcp__granted__read_file')
        throw new Error('TOOL_GRANT_MISMATCH')
      if (%s || %s) {
        console.log(JSON.stringify({ phase: 'activation-started' }))
        if (%s) setTimeout(() => controller.abort('fixture-activation-abort'), 40)
        if (%s) return new Promise(resolve => setTimeout(() => resolve({
          ready: true,
          dispose() { console.log(JSON.stringify({ phase: 'late-disposed' })) },
        }), 160))
        return new Promise(() => {})
      }
      if (%s) return { ready: false }
      console.log(JSON.stringify({ phase: 'after-native-v2', cwd: overlay.cwd,
        job: overlay.env.MMX_ACP_JOB_ID, run: overlay.env.MMX_ACP_RUN_ID,
        worker: overlay.env.MMX_ACP_WORKER_ID,
        hostHome: process.env.HOME, ambientKey: process.env.OPENAI_API_KEY ?? null,
        overlayKeys: Object.keys(overlay.env).sort() }))
      return { ready: true }
    },
  })
  if (!result.activation.ready) throw Error('NO_READINESS')
  process.stdin.resume()
  await new Promise(resolve => process.stdin.once('end', resolve))
} catch {
  process.stderr.write('NATIVE_DSH_V2_CHILD_REFUSED\\n')
  process.exitCode = 65
}
""" % (json.dumps(helper.as_uri()), "'f'.repeat(64)" if bad_digest else "createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex')",
       "true" if abort_during_activation else "false",
       "true" if expire_during_activation else "false",
       "true" if abort_during_activation else "false",
       "true" if late_dispose else "false",
       "true" if false_ready else "false"), encoding="utf-8")
    bootstrap_sha = hashlib.sha256(script.read_bytes()).hexdigest()
    helper_sha = hashlib.sha256(helper.read_bytes()).hexdigest()
    gate = AcpNativeToolGate(
        "a" * 64, bootstrap_sha,
        (AcpObservedTool("mcp__granted__read_file", "c" * 64),),
        ((str(script), bootstrap_sha), (str(helper), helper_sha)),
    )
    effective = AcpNativeProfile(
        "native-v2-node-fixture", attested, (str(node), str(script)),
        private_startup=True, allowed_environment_keys=("PATH",),
    )

    def render_overlay(row, workspace, run_dir):
        assert row == spec
        return {"cwd": str(workspace), "env": {
            "MMX_ACP_WORKSPACE_PATH": str(workspace),
            "MMX_ACP_WORKSPACE_BASE_SHA": row.expected_base_sha,
            "MMX_ACP_RUN_ID": row.run_id, "MMX_ACP_JOB_ID": row.job_id,
            "MMX_ACP_WORKER_ID": row.worker_id,
            "MMX_ACP_DEADLINE_MS": str(int(time.time() * 1000) + (
                2400 if expire_during_activation else int(row.timeout_seconds * 1000)
            )),
        }}

    # This test runs an actual Node child, but not an installed DSH/ACP worker.
    owner = AcpNativeProcessOwner(
        effective, environment_loader=lambda: {"PATH": "/usr/bin:/bin"},
        tool_gate=gate,
        launch_argv_builder=lambda *_: effective.argv,
        attempt_overlay_builder=render_overlay,
    )
    return owner, spec


def test_real_node_child_consumes_exact_native_v2_before_ack(launch, tmp_path, monkeypatch):
    owner, spec = _build(launch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-must-not-be-inherited")
    monkeypatch.setenv("NODE_OPTIONS", "--require /fixture-not-admitted-by-native-owner.js")
    async def run():
        resources = await owner.open_run(spec)
        try:
            observed = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=5))
            assert observed["phase"] == "after-native-v2"
            assert (observed["job"], observed["run"], observed["worker"]) == (
                spec.job_id, spec.run_id, spec.worker_id,
            )
            assert observed["cwd"] == str(spec.workspace_path.resolve(strict=True))
            assert observed["ambientKey"] is None
            assert observed["hostHome"] == str(spec.run_dir / "startup/home")
            receipt = await asyncio.wait_for(resources.prepare_prompt("native-v2", spec.model), 5)
            assert receipt.matches(spec, resources.process_ref, "native-v2", spec.model)
        finally:
            finished = await resources.finish(None)
        assert finished.settled and owner._active is None
    asyncio.run(run())


@pytest.mark.parametrize("case", ("false_ready", "wrong_artifact"))
def test_unreviewed_child_cannot_claim_native_readiness(launch, tmp_path, case):
    owner, spec = _build(
        launch, tmp_path,
        false_ready=case == "false_ready",
        bad_digest=case == "wrong_artifact",
    )
    async def run():
        resources = await owner.open_run(spec)
        try:
            with pytest.raises(ValueError):
                await asyncio.wait_for(resources.prepare_prompt("native-v2", spec.model), 5)
        finally:
            finished = await resources.finish("child not ready")
        assert finished.settled and owner._active is None
    asyncio.run(run())


def test_cancel_during_unresolved_child_activation_refuses_before_native_ack(launch, tmp_path):
    """The actual inherited v2 channel must not hang on an aborted MCP activation.

    This is a provider-free child/socket/process cancellation case, not a
    dedicated-UID/Seatbelt or Executive WorkerResult acceptance test.
    """
    owner, spec = _build(launch, tmp_path, abort_during_activation=True)

    async def run():
        resources = await owner.open_run(spec)
        try:
            phase = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=2))
            assert phase == {"phase": "activation-started"}
            try:
                await asyncio.wait_for(resources.prepare_prompt("native-v2", spec.model), timeout=1.5)
            except Exception as exc:
                assert not isinstance(exc, asyncio.TimeoutError), (
                    "aborted native activation never settled its pending socket"
                )
            else:
                pytest.fail("aborted child was incorrectly admitted to prompt")
        finally:
            finished = await resources.finish("aborted before governed discovery")
        assert finished.settled and owner._active is None
        assert finished.cancellation is not None
        assert not owner._identity_matches(resources.process_ref)

    asyncio.run(run())


def test_expired_attempt_interrupts_stalled_activation_before_ack(launch, tmp_path):
    """Attempt deadline, not a model callback, bounds the owned native socket."""
    owner, spec = _build(launch, tmp_path, expire_during_activation=True)

    async def run():
        resources = await owner.open_run(spec)
        try:
            phase = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=2))
            assert phase == {"phase": "activation-started"}
            try:
                await asyncio.wait_for(resources.prepare_prompt("native-v2", spec.model), timeout=4)
            except Exception as exc:
                assert not isinstance(exc, asyncio.TimeoutError), "deadline never closed native readiness"
            else:
                pytest.fail("expired native Attempt admitted a prompt")
        finally:
            finished = await resources.finish("expired before tool discovery")
        assert finished.settled and owner._active is None
        assert not owner._identity_matches(resources.process_ref)

    asyncio.run(run())


def test_late_activation_after_abort_is_disposed_without_ack(launch, tmp_path):
    """Late result of an abandoned callback cannot become a live MCP profile."""
    owner, spec = _build(launch, tmp_path, abort_during_activation=True, late_dispose=True)

    async def run():
        resources = await owner.open_run(spec)
        try:
            phase = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=2))
            assert phase == {"phase": "activation-started"}
            try:
                await asyncio.wait_for(resources.prepare_prompt("native-v2", spec.model), timeout=2)
            except Exception as exc:
                assert not isinstance(exc, asyncio.TimeoutError), "aborted callback hung"
            else:
                pytest.fail("aborted callback admitted a prompt")
            proof = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=2))
            assert proof == {"phase": "late-disposed"}
            assert await asyncio.wait_for(resources.reader.readline(), timeout=2) == b""
        finally:
            finished = await resources.finish("late activation refused")
        assert finished.settled and owner._active is None
        assert not owner._identity_matches(resources.process_ref)

    asyncio.run(run())

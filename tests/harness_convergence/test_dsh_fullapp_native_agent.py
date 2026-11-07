"""Real current-donor Agent + native ACP v3 + workspace reader, test grant only.

The synthetic target launches the actual source server in a test environment.
It is not an installed canonical target, dedicated-UID proof or paid provider.
"""
from __future__ import annotations
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from test_dsh_acp_worker import _binary, _git
from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerRunStatus
from control_plane.executive_worker_broker import BrokerEffectUnknownError
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest,
)
from control_plane.dsh_mcp_client_projection import project_dsh_mcp_tools
from control_plane.executive_supervisor import worker_result_schema
from integrations.acp_worker.adapter import AcpWorkerAdapter
from integrations.acp_worker.native import AcpNativeProcessOwner, AcpNativeProfile
from integrations.acp_worker.tool_admission import AcpNativeToolGate, AcpObservedTool
from integrations.acp_worker.turn import AcpProfile
from integrations.acp_worker.workspace_read_mcp import tool_catalog

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supplied():
    value = os.environ.get("MMX_DSH_FULLAPP_NATIVE_SUPPLY")
    if not value:
        pytest.skip("current full-app fixture absent: real native journey NOT executed")
    root = Path(value).resolve(strict=True)
    manifest = json.loads((root / ".cache/build/build-manifest.json").read_text())
    assert manifest["schema"] == "mastermind.dsh_fullapp_native_fixture.v1"
    assert manifest["donor_sha"] == "687f282e8625c6b8d11ff58211a90524be2e4317"
    assert manifest["production_armed"] is False
    for path, sha in manifest["sources_sha256"].items():
        assert digest(root / path) == sha, f"rebuild changed fixture source: {path}"
    for path, sha in manifest["output_sha256"].items():
        assert digest(root / ".cache/build" / path) == sha
    node = Path(manifest["node"]).resolve(strict=True)
    assert digest(node) == manifest["node_sha256"]
    return root, manifest, node


async def exercise(tmp_path, mode="ok"):
    root, manifest, node = supplied()
    tmp_path = tmp_path.resolve()
    workspace, run_dir, inputs = (tmp_path / name for name in ("workspace", "run", "fixture"))
    for path in (workspace, run_dir, inputs):
        path.mkdir(mode=0o700)
    (run_dir / "input").mkdir(mode=0o700)
    memo = "fullapp-native-needle\nActual admitted source bytes\nfullapp-native-needle again\n"
    (workspace / "memo.txt").write_text(memo)
    _git(workspace, "init", "--template=", "-q")
    _git(workspace, "add", "memo.txt")
    _git(workspace, "-c", "user.name=Fullapp Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    base = _git(workspace, "rev-parse", "HEAD")
    schema = run_dir / "input/result.schema.json"
    schema.write_text(json.dumps(worker_result_schema(
        job_id="fullapp-job", run_id="fullapp-run", worker_id="fullapp-worker")))
    # Keep production registry immutable. These explicitly synthetic digests
    # cannot become an AcpInstalledHostPacket or authorize the real fixed target.
    profile = ExecutionCapabilityRegistry.load().resolve("worker.acp.providerfree.readonly.v1")
    original = next(grant for grant in profile.mcp_server_grants
                    if grant.capability_id == "mastermind-acp-workspace-read-v1")
    catalog = tool_catalog()
    grant = dataclasses.replace(
        original, command=sys.executable, args=("-B", str(ROOT / "scripts/acp_workspace_read_mcp.py")),
        grant_digest=hashlib.sha256(b"SYNTHETIC_FULLAPP_NATIVE_FIXTURE_NOT_AUTHORITY").hexdigest(),
        tool_schema_digest=observed_mcp_tool_schema_digest({"tools": {t["name"]: t for t in catalog}}),
    )
    profile = dataclasses.replace(
        profile, mcp_server_grants=(grant,),
        profile_digest=hashlib.sha256(b"SYNTHETIC_FULLAPP_NATIVE_PROFILE_NOT_AUTHORITY").hexdigest(),
    )
    projection = project_dsh_mcp_tools(profile, capability_id=grant.capability_id,
                                      observed_tool_catalog={"tools": catalog}).configuration()
    projection_path = inputs / "projection.json"
    projection_path.write_text(json.dumps(projection, sort_keys=True, separators=(",", ":")))
    config = {**projection["target"], "failOnStartupError": True, "reconnect": {"enabled": False},
              "toolCallTimeoutMs": 5000}
    (inputs / "config.json").write_text(json.dumps(config))
    tools = tuple(AcpObservedTool(
        f"mcp__{projection['target']['serverName']}__{tool['name']}",
        observed_mcp_tool_schema_digest({"tools": {tool["name"]: tool}}),
    ) for tool in projection["tools"])
    (inputs / "tools.json").write_text(json.dumps([
        {"name": row.name, "contract_sha256": row.contract_sha256} for row in tools]))
    bundle = root / ".cache/build/native-agent-fixture.mjs"
    files = [root / ".cache/build" / path for path in manifest["output_sha256"]]
    files += list(inputs.iterdir())
    gate = AcpNativeToolGate(digest(projection_path), digest(bundle), tools,
                            tuple((str(path), digest(path)) for path in files),
                            native_session_required=True)
    native = AcpNativeProfile(
        "fullapp-native-fixture", _binary(node), (str(node), str(bundle)), private_startup=True,
        allowed_environment_keys=("PATH", "MMX_FULLAPP_FIXTURE_INPUT", "MMX_FULLAPP_FIXTURE_MODE"),
    )
    def overlay(spec, admitted_workspace, _run_dir):
        return {"cwd": str(admitted_workspace), "env": {
            "MMX_ACP_WORKSPACE_PATH": str(admitted_workspace),
            "MMX_ACP_WORKSPACE_BASE_SHA": spec.expected_base_sha,
            "MMX_ACP_RUN_ID": spec.run_id, "MMX_ACP_JOB_ID": spec.job_id,
            "MMX_ACP_WORKER_ID": spec.worker_id,
            "MMX_ACP_DEADLINE_MS": str(int(time.time() * 1000) + int(spec.timeout_seconds * 1000)), 
        }}
    owner = AcpNativeProcessOwner(
        native, environment_loader=lambda: {
            "PATH": "/usr/bin:/bin", "MMX_FULLAPP_FIXTURE_INPUT": str(inputs),
            "MMX_FULLAPP_FIXTURE_MODE": "ok" if mode == "wrong-native-session" else mode,
        }, tool_gate=gate, launch_argv_builder=lambda *_: native.argv,
        attempt_overlay_builder=overlay,
    )
    admissions = []

    async def open_original(row):
        resources = await owner.open_run(row)
        original = resources.prepare_prompt
        assert original is not None

        async def prepare_prompt(session_id, model):
            # Fault injection at the existing pre-prompt boundary: an ACP
            # selected ID cannot borrow this actual Agent's readiness receipt.
            selected = "foreign-acp-session" if mode == "wrong-native-session" else session_id
            admitted = await original(selected, model)
            assert admitted.native_session_id == session_id
            admissions.append(admitted)
            return admitted

        return dataclasses.replace(resources, prepare_prompt=prepare_prompt)

    adapter = AcpWorkerAdapter(
        AcpProfile("deepseek-harness-acp", "0.0.1", model_option_provider="fixture"),
        inspector=owner.inspector, open_run=open_original,
    )
    spec = WorkerLaunchSpec(
        "fullapp-run", "fullapp-job", "fullapp-worker", workspace, run_dir,
        "Read memo.txt, search its observed first line, return the actual read/search result.",
        schema, authorities=("READ", "RESEARCH"), model="fixture-model",
        timeout_seconds=18, cancel_grace_seconds=3, expected_base_sha=base,
        expected_worker_uid=os.geteuid(), expected_worker_gid=os.getegid(),
    )
    ref = await adapter.start(spec)
    try:
        if mode == "hang":
            for _ in range(400):
                if b"FULLAPP_MODEL_CALL 2" in Path(ref.stderr_path).read_bytes():
                    break
                await asyncio.sleep(0.02)
            else:
                pytest.fail("native model did not enter cancellable turn: " + Path(ref.stderr_path).read_text())
            await asyncio.wait_for(adapter.cancel(ref, "native fixture cancellation"), 12)
            receipt = adapter._runs[spec.run_id].receipt
        elif mode in ("wrong-tool-contract", "wrong-native-session", "abort-before-ready"):
            # Refusal before prompt has no successful result. Keep the existing
            # adapter's conservative classification; independently prove cleanup.
            with pytest.raises(BrokerEffectUnknownError, match="original operation is unresolved"):
                await asyncio.wait_for(adapter.collect_result(ref), 25)
            receipt = None
        else:
            receipt = await asyncio.wait_for(adapter.collect_result(ref), 25)
    finally:
        if owner._active is not None:
            pending = adapter._runs[spec.run_id].task
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        assert owner._active is None
        assert adapter.unsettled_tasks == ()
        assert not owner._identity_matches(ref)
    if receipt is not None:
        assert len(admissions) == 1
        native_id = owner._runs[spec.run_id].admission_channel.native_session_id
        assert admissions[0].native_session_id == native_id == receipt.result.provider_session_id
        observations = [json.loads(line.removeprefix("FULLAPP_NATIVE_SESSION "))
                        for line in Path(ref.stderr_path).read_text().splitlines()
                        if line.startswith("FULLAPP_NATIVE_SESSION ")]
        assert observations == [{"session_id": native_id}]
    else:
        assert admissions == []
    assert _git(workspace, "status", "--porcelain") == ""
    assert (workspace / "memo.txt").read_text() == memo
    return receipt, ref, memo


def test_current_fullapp_native_v3_read_search_returns_actual_result(tmp_path):
    receipt, ref, memo = asyncio.run(exercise(tmp_path))
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED, Path(ref.stderr_path).read_text()
    envelope = receipt.result.structured_output
    assert envelope["status"] == "COMPLETED"
    value = json.loads(envelope["summary"])
    assert value["read"]["data"]["content"] == memo
    assert value["read"]["job_id"] == "fullapp-job"
    assert len(value["search"]["data"]["matches"]) == 2
    assert value["model_calls"] == 3
    evidence = receipt.result.usage["acp_tool_observation"]
    assert evidence["observations"]["calls"] == evidence["observations"]["terminal"] == 2
    assert evidence["session_id"] == receipt.result.provider_session_id


def test_current_fullapp_revocation_refuses_second_tool(tmp_path):
    receipt, ref, _ = asyncio.run(exercise(tmp_path, "revoked"))
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED, Path(ref.stderr_path).read_text()
    value = json.loads(receipt.result.structured_output["summary"])
    assert value["read"]["ok"] is True and value["search"]["error"] is True
    assert receipt.result.structured_output["status"] == "FAILED"


def test_current_fullapp_cancel_settles_original_native_owner(tmp_path):
    receipt, _, _ = asyncio.run(exercise(tmp_path, "hang"))
    assert receipt.result.status is WorkerRunStatus.CANCELLED


def test_current_fullapp_wrong_tool_contract_never_starts_model(tmp_path):
    receipt, ref, _ = asyncio.run(exercise(tmp_path, "wrong-tool-contract"))
    assert receipt is None
    assert b"FULLAPP_MODEL_CALL" not in Path(ref.stderr_path).read_bytes()


def test_current_fullapp_owner_abort_keeps_inherited_tools_hidden(tmp_path):
    receipt, ref, _ = asyncio.run(exercise(tmp_path, "owner-revoked"))
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED, Path(ref.stderr_path).read_text()
    value = json.loads(receipt.result.structured_output["summary"])
    assert value["read"]["ok"] is True and value["search"]["error"] is True
    assert receipt.result.structured_output["status"] == "FAILED"
    assert b"INHERITED_SENTINEL_EXECUTED" not in Path(ref.stderr_path).read_bytes()


def test_current_fullapp_foreign_acp_session_never_reaches_model(tmp_path):
    receipt, ref, _ = asyncio.run(exercise(tmp_path, "wrong-native-session"))
    assert receipt is None
    log = Path(ref.stderr_path).read_bytes()
    assert b"FULLAPP_NATIVE_SESSION " in log
    assert b"FULLAPP_MODEL_CALL" not in log


def test_current_fullapp_abort_before_readiness_never_reaches_model(tmp_path):
    receipt, ref, _ = asyncio.run(exercise(tmp_path, "abort-before-ready"))
    assert receipt is None
    log = Path(ref.stderr_path).read_bytes()
    assert b"FULLAPP_NATIVE_SESSION " not in log
    assert b"FULLAPP_MODEL_CALL" not in log

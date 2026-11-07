"""Original full native Web profile plus private ACP in one Context.

Explicit isolated supply only: no installed target, live account, model prompt,
or inferred Executive authorization. Cold resume uses the original JSONL owner.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import socket

import pytest

from acp import PROTOCOL_VERSION, connect_to_agent
from acp.schema import ClientCapabilities, Implementation, RequestPermissionResponse
from integrations.deepseek_harness.package_attended import inventory

ROOT = Path(__file__).resolve().parents[2]
COMPAT = ROOT / "integrations/deepseek_harness/runtime_compat"
PIN = "687f282e8625c6b8d11ff58211a90524be2e4317"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supplied():
    value = os.environ.get("MMX_DSH_COMPANY_PROFILE_SUPPLY")
    if not value:
        pytest.skip("full native company profile supply absent: real journey NOT executed")
    supply = Path(value).resolve(strict=True)
    manifest = json.loads((supply / "build-manifest.json").read_bytes())
    assert manifest["schema"] == "mastermind.dsh_native_company_fixture.v1"
    assert manifest["donor_sha"] == PIN
    assert manifest["installed"] is False and manifest["production_armed"] is False
    for name, receipt in (("native-host-source.json", "host_preparation"),
                          ("native-session-source.json", "session_preparation")):
        expected = json.loads((COMPAT / name).read_bytes())
        assert manifest[receipt]["patch_sha256"] == expected["patch_sha256"]
        assert manifest[receipt]["output_sha256"] == expected["output_sha256"]
        for relative, digest in expected["output_sha256"].items():
            assert sha(supply / "app" / relative) == digest
    for relative, digest in manifest["output_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(supply / "app" / relative) == digest, relative
    closure = manifest["runtime_inventory"]
    assert closure["file"] == "runtime-inventory.json"
    inventory_path = supply / closure["file"]
    assert sha(inventory_path) == closure["sha256"]
    expected_entries = json.loads(inventory_path.read_bytes())
    assert len(expected_entries) == closure["entries"]
    assert inventory(supply / "app") == expected_entries
    node = Path(manifest["node"]).resolve(strict=True)
    assert sha(node) == manifest["node_sha256"]
    return supply, node


def redact(value: str) -> str:
    # The original web launcher prints a one-time sign-in URL. It is private
    # fixture output, never an assertion message or canonical evidence token.
    value = re.sub(r"https?://[^\s\x1b]+", "[native fixture URL redacted]", value)
    return re.sub(r"(?i)(token|cookie|authorization)([=:]\s*)[^\s]+", r"\1\2[redacted]", value)


class FixtureClient:
    def __init__(self):
        self.updates = []
        self.permission_requests = 0

    def on_connect(self, _connection):
        pass

    async def session_update(self, session_id, update, **_kwargs):
        assert len(self.updates) < 100, "unexpected unbounded native notifications"
        self.updates.append((session_id, type(update).__name__))

    async def request_permission(self, **_kwargs):
        self.permission_requests += 1
        return RequestPermissionResponse.model_validate({"outcome": {"outcome": "cancelled"}})


async def capture(stream):
    data = bytearray()
    exceeded = False
    while chunk := await stream.read(8192):
        if len(data) + len(chunk) > 262144:
            exceeded = True
        data.extend(chunk)
        if len(data) > 262144:
            del data[:-262144]
    return bytes(data), exceeded


async def one_generation(supply, node, state, workspace, mode, session_id=None):
    report_path = state / ("native-" + mode + ".json")
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    parent.setblocking(False)
    env = {
        "PATH": str(node.parent) + ":/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(state / "home"), "DSH_HOME": str(state / "dsh"),
        "DSH_AGENTS_HOME": str(state / "agents"), "DSH_TELEMETRY_DISABLED": "1",
        "LANG": "C", "MMX_NATIVE_COMPANY_FD": str(child.fileno()),
    }
    args = [str(node), str(COMPAT / "native-company-profile-fixture.mjs"),
            str(supply), str(state), str(report_path), mode]
    if session_id is not None:
        args.append(session_id)
    process = None
    connection = None
    writer = None
    captures = []
    forced = False
    client = FixtureClient()
    phase = "launch"
    try:
        process = await asyncio.create_subprocess_exec(
            *args, cwd=workspace, env=env, pass_fds=(child.fileno(),),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        child.close()
        captures = [asyncio.create_task(capture(stream))
                    for stream in (process.stdout, process.stderr)]
        reader, writer = await asyncio.open_connection(sock=parent)
        connection = connect_to_agent(client, writer, reader)
        phase = "initialize"
        await asyncio.wait_for(connection.initialize(
            protocol_version=PROTOCOL_VERSION, client_capabilities=ClientCapabilities(),
            client_info=Implementation(name="mastermind-native-profile-fixture", version="1"),
        ), 60)
        phase = mode + "-session"
        if mode == "new":
            selected = await asyncio.wait_for(connection.new_session(
                cwd=str(workspace), mcp_servers=[]), 20)
            session_id = selected.session_id
            assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", session_id)
            try:
                await asyncio.wait_for(connection.new_session(cwd=str(workspace), mcp_servers=[]), 15)
            except Exception as exc:
                assert type(exc).__name__ == "RequestError", type(exc).__name__
            else:
                raise AssertionError("original host admitted a second Session owner")
        else:
            await asyncio.wait_for(connection.resume_session(
                session_id=session_id, cwd=str(workspace), mcp_servers=[]), 20)
        phase = "close-session"
        await asyncio.wait_for(connection.close_session(session_id=session_id), 20)
        await connection.close()
        connection = None
        # SDK protocol close does not own the caller-supplied socket writer.
        # The original child observes this transport EOF before native shutdown.
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), 5)
        phase = "native-process-exit"
        await asyncio.wait_for(process.wait(), 30)
    except Exception as exc:
        failure = exc
    else:
        failure = None
    finally:
        child.close()
        if connection is not None:
            try:
                await asyncio.wait_for(connection.close(), 5)
            except Exception:
                pass
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 5)
            except Exception:
                pass
        else:
            parent.close()
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), 15)
            except TimeoutError:
                forced = True
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        captured = await asyncio.gather(*captures)
        logs = "\n".join(redact(data.decode("utf-8", errors="replace"))
                         for data, _overflow in captured)
        (state / ("native-" + mode + ".log")).write_text(logs)
    # Report only the original private fixture's redacted diagnostics.
    if failure is not None:
        raise AssertionError(f"{phase}: {type(failure).__name__}: {redact(str(failure))}\n{logs[-12000:]}") from None
    assert not forced, "native shutdown required an external signal"
    assert process is not None and process.returncode == 0, logs[-12000:]
    assert all(not overflow for _data, overflow in captured), "native capture exceeded its bound"
    assert client.permission_requests == 0
    report = json.loads(report_path.read_bytes())
    assert "failure" not in report, report.get("failure")
    assert report["schema"] == "mastermind.dsh_native_company_profile_proof.v1"
    assert report["production_armed"] is False and report["donor_sha"] == PIN
    assert report["actual_session_id"] == session_id
    assert report["mode"] == mode and report["agent_creates"] == 1
    assert report["native_start_source"] == ("resume" if mode == "resume" else "startup")
    assert report["model_calls"] == 0
    for key in ("shared_agent", "shared_session", "pre_ready_owner_denied",
                "company_page_observed", "reader_retirement_keeps_owner", "native_close_settled",
                "root_teardown_settled", "pre_admission_absent", "isolated_native_home"):
        assert report[key] is True, key
    assert report["http"] == {
        "unauthenticated": 401, "index": 200, "held_file": 403,
        "foreign_origin": 403, "title": True, "owner_baseline_held": True,
    }
    return session_id, report


def test_original_profile_new_close_and_exact_cold_resume(tmp_path):
    supply, node = supplied()
    state = tmp_path.resolve()
    for name in ("home", "dsh", "agents", "workspace"):
        (state / name).mkdir(mode=0o700)
    workspace = state / "workspace"

    async def exercise():
        session_id, created = await one_generation(supply, node, state, workspace, "new")
        stored = list((state / "dsh/sessions").rglob("session.v4.jsonl.zstd"))
        assert len(stored) == 1, "original compressed native Session log was not persisted"
        assert stored[0].parent.name == session_id
        created["native_storage"] = {"path": str(stored[0].relative_to(state)),
                                     "sha256": sha(stored[0])}
        resumed_id, resumed = await one_generation(
            supply, node, state, workspace, "resume", session_id)
        assert resumed_id == created["actual_session_id"] == resumed["actual_session_id"]
        assert stored[0].is_file()
        resumed["native_storage"] = {"path": str(stored[0].relative_to(state)),
                                     "sha256": sha(stored[0])}
        return created, resumed

    created, resumed = asyncio.run(exercise())
    (state / "native-company-lifecycle-proof.json").write_text(json.dumps(
        {"schema": "mastermind.dsh_native_company_lifecycle_proof.v1",
         "production_armed": False, "new": created, "cold_resume": resumed},
        indent=2) + "\n")


async def native_claim_generation(supply, node, state, mode, session_id=None):
    """Retained SDK consumer on the extracted physical resource, no fake Worker spec."""
    from control_plane.worker_execution_contract import BinaryAttestation
    from integrations.acp_worker.turn import AcpProfile
    from integrations.deepseek_harness.native_connection import NativeAcpProcess, NativeClient
    expected = json.loads((COMPAT/"native-acp-source.json").read_bytes())
    manifest = json.loads((supply/"build-manifest.json").read_bytes())
    assert manifest["native_acp_preparation"]["patch_sha256"] == expected["patch_sha256"]
    for relative, digest in expected["output_sha256"].items():
        assert sha(supply/"app"/relative) == digest
    info = node.stat()
    binary = BinaryAttestation(str(node), str(node), "26.5.0", sha(node), None,
        info.st_size, info.st_dev, info.st_ino, info.st_mode & 0o7777,
        info.st_uid, info.st_gid, info.st_mtime_ns)
    report_path = state/("native-lifecycle-"+mode+".json")
    capture_dir = state/("capture-"+mode)
    capture_dir.mkdir(mode=0o700)
    args = [str(node), str(COMPAT/"native-company-profile-fixture.mjs"),
            str(supply), str(state), str(report_path), mode]
    if session_id is not None:
        args.append(session_id)
    environment = {
        "PATH": str(node.parent)+":/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(state/"home"), "DSH_HOME": str(state/"dsh"),
        "DSH_AGENTS_HOME": str(state/"agents"), "DSH_TELEMETRY_DISABLED": "1",
        "LANG": "C", "MMX_NATIVE_ACP_EXERCISE": "claim-stop-resume",
    }
    observations = []
    native = NativeAcpProcess(NativeClient(observations.append))
    settlement = None
    failure = None
    async def wait_report(predicate):
        deadline = asyncio.get_running_loop().time()+20
        while asyncio.get_running_loop().time() < deadline:
            try:
                report = json.loads(report_path.read_bytes())
            except (FileNotFoundError, json.JSONDecodeError):
                report = {}
            if "failure" in report:
                raise AssertionError(report["failure"])
            if predicate(report):
                return report
            await asyncio.sleep(0.02)
        raise AssertionError("original native observation did not arrive")
    try:
        await native.open(binary=binary, argv=args, environment=environment,
            cwd=state/"workspace", capture_directory=capture_dir,
            protocol_profile=AcpProfile("deepseek-harness-acp", "0.0.1", model_option_provider="fixture"),
            model="fixture", provider_session_id=session_id)
        actual_id = native.provider_session_id
        if session_id is not None:
            assert actual_id == session_id
            await wait_report(lambda row: row.get("recovered_interrupted") is True)
        claim = await native.begin_prompt("fixture-native-turn-"+mode, "Exercise the original native conversation.")
        assert claim.session_id == actual_id
        if mode == "new":
            await wait_report(lambda row: row.get("stream_partial") is True)
            assert await native.interrupt(claim) == "requested"
        result = await native.result(claim)
        assert result.terminal.claim == claim
        assert result.stop_reason == ("cancelled" if mode == "new" else "end_turn")
        if mode == "new":
            live = await wait_report(lambda row: row.get("interrupted_history") is True)
            assert result.terminal.through_seq >= live["interrupted_seq"]
        assert observations and native.client.violation is None
        settlement = await native.close()
    except Exception as exc:
        failure = exc
    finally:
        if native.resource is not None and native._closing is None:
            settlement = await native.close("fixture cleanup")
        logs = "\n".join(redact(path.read_text(errors="replace")) for path in capture_dir.glob("native-app.*"))
        (state/("native-lifecycle-"+mode+".log")).write_text(logs)
    if failure is not None:
        raise AssertionError(f"{type(failure).__name__}: {redact(str(failure))}\n{logs[-12000:]}") from None
    assert settlement is not None and settlement.protocol_settled
    assert settlement.physical.settled and settlement.physical.exit_code == 0
    assert not settlement.physical.signal_sent and not native.resource.identity_matches()
    report = json.loads(report_path.read_bytes())
    assert report["actual_session_id"] == actual_id and report["agent_creates"] == 1
    assert report["model_calls"] == 1 and report["model_stream_settled"] and report["stream_partial"]
    assert report["native_signal_aborted"] == (mode == "new")
    assert report["native_close_settled"] and report["root_teardown_settled"]
    assert report["pre_ready_owner_denied"] and report["reader_retirement_keeps_owner"]
    assert report["shared_agent"] and report["shared_session"] and report["isolated_native_home"]
    report.update(native_claim=claim.to_wire(), native_result=result.to_wire(),
                  native_result_digest=result.artifact_digest, provider_calls=0,
                  sdk_frame_guard="original StrictFrameReader", physical_signal_sent=False)
    return actual_id, report


def test_original_profile_claim_stop_flush_and_exact_cold_resume(tmp_path):
    supply, node = supplied()
    state = tmp_path.resolve()
    for name in ("home", "dsh", "agents", "workspace"):
        (state/name).mkdir(mode=0o700)
    async def exercise():
        session_id, first = await native_claim_generation(supply, node, state, "new")
        stored = list((state/"dsh/sessions").rglob("session.v4.jsonl.zstd"))
        assert len(stored) == 1 and stored[0].parent.name == session_id
        first["native_storage_sha256"] = sha(stored[0])
        resumed_id, resumed = await native_claim_generation(supply, node, state, "resume", session_id)
        assert session_id == resumed_id and resumed["recovered_interrupted"]
        resumed["native_storage_sha256"] = sha(stored[0])
        return {"schema": "mastermind.dsh_native_claim_profile_proof.v1", "new": first, "resume": resumed,
                "production_armed": False, "provider_calls": 0}
    proof = asyncio.run(exercise())
    (state/"native-claim-lifecycle-proof.json").write_text(json.dumps(proof, indent=2)+"\n")

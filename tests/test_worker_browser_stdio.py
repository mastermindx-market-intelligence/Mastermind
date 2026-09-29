"""Synthetic Attempts over real private stdio; no provider or browser canary."""
from __future__ import annotations

import base64
import json
import sys

from control_plane.executive_runtime import Runtime
from integrations.workbench_browser_mcp.tunnel import load_browser_tunnel_config
from tests.test_mcp_stdio_boundary import child, initialize

SERVER = '''
import asyncio, sys
from pathlib import Path
from tests.test_worker_browser_admission import _setup
from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp.worker import serve_worker_browser_stdio
root = Path(sys.argv[1])
root.mkdir(mode=0o700)
api, executive, lease, epoch, generation, profile, requested, config = _setup(root)
async def main():
    runtime = await create_runtime_channel(config.action)
    admission = api.WorkerBrowserAdmission(executive.store, lease, epoch,
        generation, requested, profile, "worker-browser-isolated", runtime)
    await serve_worker_browser_stdio(runtime, config.browser, admission,
        close_timeout_seconds=config.action.close_timeout_seconds)
asyncio.run(main())
'''


def _call(process, identifier, name, arguments):
    process.send({"jsonrpc": "2.0", "id": identifier, "method": "tools/call",
                  "params": {"name": name, "arguments": arguments}})
    response = process.receive()
    assert response["id"] == identifier
    return response["result"]


def _prepare(process, root, identifier):
    config = load_browser_tunnel_config(str(root / "browser-tunnel.json"))
    return _call(process, identifier, "prepare_browser_resource", {
        "project_ref": config.action.lease.project_ref, "mode": "isolated"})


def _payload(token):
    part = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def test_two_private_attempt_channels_revoke_independently_and_close(tmp_path):
    roots = [tmp_path / "one", tmp_path / "two"]
    with child([sys.executable, "-c", SERVER, str(roots[0])]) as one:
        with child([sys.executable, "-c", SERVER, str(roots[1])]) as two:
            for process in (one, two):
                initialize(process)
                process.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                assert [x["name"] for x in process.receive()["result"]["tools"]] == [
                    "prepare_browser_resource"]
            assert one.process.poll() is None and two.process.poll() is None
            prepared = [_prepare(process, root, 3)["structuredContent"]
                        for process, root in zip((one, two), roots)]
            assert all(x["status"] == "PREPARED" for x in prepared)
            scopes = [_payload(x["start_ref"]) for x in prepared]
            assert scopes[0]["responsibility_ref"] != scopes[1]["responsibility_ref"]
            assert scopes[0]["generation"] != scopes[1]["generation"]
            refused = _call(two, 4, "start_browser_resource", {
                "start_ref": prepared[0]["start_ref"]})
            assert refused["isError"]
            assert json.loads(refused["content"][0]["text"])["code"] == "TOOL_NOT_AVAILABLE"
            # The trusted test controller cancels one synthetic Runtime Job.
            runtime = Runtime.at(roots[0] / "executive")
            with runtime.store.read() as connection:
                row = connection.execute("SELECT job_id,lease_token FROM attempts").fetchone()
            runtime.jobs.cancel_job(row["job_id"])
            rejected = _prepare(one, roots[0], 5)
            assert json.loads(rejected["content"][0]["text"])["code"] == "CHANNEL_ADMISSION_REFUSED"
            assert _prepare(two, roots[1], 5)["structuredContent"]["status"] == "PREPARED"
            for process in (one, two):
                process.assert_exit(0)
                assert row["lease_token"].encode() not in process.wire + process.stderr()
            assert all(not list((root / "relay").iterdir()) for root in roots)

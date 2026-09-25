from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile

from control_plane.codex_worker import ProcessInspector
from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding,
    adopt_artifact_store,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ActionScope,
    ProjectActionBinding,
)
from integrations.workbench_browser_mcp.contracts import BrowserRefCodec
from integrations.workbench_browser_mcp.resource_port import (
    BrowserHostConfig,
    BrowserResourcePort,
)


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _fake_relay(tmp_path: Path) -> Path:
    script = tmp_path / "fake-relay.py"
    script.write_text(
        r"""
import argparse,json,os,signal,socket
p=argparse.ArgumentParser()
p.add_argument("--barrier-fd",type=int,required=True)
p.add_argument("--socket-path",required=True)
p.add_argument("--resource-id",required=True)
a=p.parse_args()
if os.read(a.barrier_fd,1) != b"\x01":
    raise SystemExit(5)
os.close(a.barrier_fd)
stop=False
def handler(*_):
    global stop
    stop=True
signal.signal(signal.SIGTERM,handler)
signal.signal(signal.SIGINT,handler)
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.bind(a.socket_path)
os.chmod(a.socket_path,0o600)
s.listen(4)
s.settimeout(0.1)
try:
    while not stop:
        try:
            c,_=s.accept()
        except socket.timeout:
            continue
        with c:
            data=b""
            while b"\n" not in data:
                part=c.recv(65536)
                if not part:
                    break
                data += part
            if not data:
                continue
            req=json.loads(data.split(b"\n",1)[0])
            out={
              "schema":"mastermind.workbench_browser_relay_response.v1",
              "request_id":req["request_id"],
              "resource_id":a.resource_id,
              "ok":True,
              "tool_schema_digest":"d"*64,
              "allowed_tools":["browser_snapshot"],
              "child_pid":os.getpid(),
            }
            c.sendall(json.dumps(out,separators=(",",":")).encode()+b"\n")
finally:
    s.close()
    try: os.unlink(a.socket_path)
    except FileNotFoundError: pass
""",
        encoding="utf-8",
    )
    return script


def _port(tmp_path: Path):
    root = _private(tmp_path / "artifacts")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    store = adopt_artifact_store(fd)

    source = _private(tmp_path / "source")
    relay_root = Path(tempfile.mkdtemp(prefix="mmxb-", dir="/tmp"))
    os.chmod(relay_root, 0o700)
    output = _private(tmp_path / "output")
    home = _private(tmp_path / "home")
    tmp = _private(tmp_path / "tmp")
    script = _fake_relay(tmp_path)

    caller = ActionCaller(
        subject_digest="a" * 64,
        client_ref="client:browser",
        resource="https://workbench.example/browser",
        scopes=("workbench.browser",),
        expires_at=1000,
    )
    scope = ActionScope(
        root_fd=99,
        root_device=1,
        root_inode=2,
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:browser",
        allowed_paths=(),
        expires_at_ms=60_000,
    )
    binding = ProjectActionBinding(caller=caller, project_ref="project:browser", scope=scope)
    host = ActionHostBinding(host_id="b" * 64, boot_session_id=ProcessInspector().boot_session_id())

    config = BrowserHostConfig(
        source_root=source,
        python_executable=sys.executable,
        node_executable="/usr/bin/true",
        mcp_cli_path="/private/fake/node_modules/@playwright/mcp/cli.js",
        chrome_executable="/usr/bin/true",
        relay_root=relay_root,
        output_root=output,
        home_dir=str(home),
        tmp_dir=str(tmp),
        expected_tool_schema_digest="d" * 64,
        startup_timeout_seconds=3,
    )

    def command_builder(*, config, prepared, barrier_fd, socket_path, output_dir, profile_dir):
        assert profile_dir is None
        return (
            sys.executable,
            str(script),
            "--barrier-fd",
            str(barrier_fd),
            "--socket-path",
            str(socket_path),
            "--resource-id",
            prepared.action_id,
        )

    port = BrowserResourcePort(
        resolve_binding=lambda actual, project: binding
        if actual == caller and project == binding.project_ref
        else None,
        clock_ms=lambda: 2000,
        codec=BrowserRefCodec(b"k" * 32),
        artifact_store=store,
        host_binding=host,
        host_config=config,
        profile_resolver=lambda _ref: None,
        relay_command_builder=command_builder,
        start_ttl_ms=20_000,
    )
    return fd, caller, port, relay_root


def test_start_replay_reconciles_same_relay_and_cleanup_is_owner_gated(tmp_path: Path):
    fd, caller, port, relay_root = _port(tmp_path)
    try:
        start_ref = port.prepare_resource(
            caller,
            project_ref="project:browser",
            mode="isolated",
        )
        first = port.start_resource(caller, start_ref)
        assert first["effect_state"] == "APPLIED"
        assert first["reconciled"] is False
        browser_ref = first["browser_ref"]
        decoded = port.codec.decode_resource(browser_ref, now_ms=2000)
        assert ProcessInspector().inspect(decoded.relay_pid).start_identity == decoded.relay_start_identity

        second = port.start_resource(caller, start_ref)
        assert second["effect_state"] == "APPLIED"
        assert second["reconciled"] is True
        assert second["browser_ref"] == browser_ref
        assert port.codec.decode_resource(second["browser_ref"], now_ms=2000).relay_pid == decoded.relay_pid

        blocked = port.cleanup_resource(
            browser_ref,
            owner_state="expired",
            effect_state="EFFECT_UNKNOWN",
        )
        assert blocked["cleanup_action"] == "block_effect_unknown"
        assert blocked["released"] is False
        ProcessInspector().inspect(decoded.relay_pid)

        released = port.cleanup_resource(
            browser_ref,
            owner_state="released",
            effect_state="APPLIED",
        )
        assert released["released"] is True
        assert released["profile_deleted"] is False
        assert not (relay_root / f"{decoded.start_action_id}.sock").exists()
    finally:
        os.close(fd)
        shutil.rmtree(relay_root, ignore_errors=True)


def test_reconcile_before_start_is_not_applied_and_does_not_spawn(tmp_path: Path):
    fd, caller, port, relay_root = _port(tmp_path)
    try:
        start_ref = port.prepare_resource(
            caller,
            project_ref="project:browser",
            mode="isolated",
        )
        receipt = port.reconcile_resource(caller, start_ref)
        assert receipt == {
            "status": "OK",
            "effect_state": "NOT_APPLIED",
            "browser_ref": None,
            "reconciled": True,
        }
        assert list(relay_root.iterdir()) == []
    finally:
        os.close(fd)
        shutil.rmtree(relay_root, ignore_errors=True)

"""Actual relay entry/parent/MCP subprocesses with synthetic protocol and owner records.

No Chrome, provider, credentials or real website is used. This qualifies process
retention and descriptor confinement, not authenticated browser production.
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import pytest

from control_plane.codex_worker import ProcessInspector, ProcessIdentityError
from integrations.workbench_action_mcp import action_artifacts as aa
from test_workbench_browser_relay import _digest, _fake_child


PARENT = r'''
import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from integrations.workbench_browser_mcp.relay import relay_request, RELAY_REQUEST_SCHEMA
root, sock, source, digest, mode = sys.argv[2:]
fd=os.open(root, os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
info=os.fstat(fd)
entry="import sys;sys.path.insert(0,sys.argv[1]);from integrations.workbench_browser_mcp import relay;relay.WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST=sys.argv[2];relay.ALLOWED_BROWSER_TOOLS=frozenset(['browser_snapshot','browser_click']);raise SystemExit(relay.main(sys.argv[3:]))"
expiry=int(time.time()*1000)+(1500 if mode == "expiry" else 60000)
argv=[sys.executable,"-I","-c",entry,sys.argv[1],digest,
      "--resource-id","a"*32,"--socket-path",sock,
      "--node-executable",sys.executable,"--mcp-cli-path",source,
      "--chrome-executable","/usr/bin/true","--output-dir",str(Path(root).parent),
      "--mode","isolated","--home-dir",str(Path(root).parent),"--tmp-dir",str(Path(root).parent),
      "--expires-at-ms",str(expiry),"--artifact-store-fd",str(fd),
      "--artifact-store-device",str(info.st_dev),"--artifact-store-inode",str(info.st_ino)]
r,w=os.pipe()
argv += ["--barrier-fd",str(r)]
err=Path(root).parent/"relay-fixture.stderr"
with err.open("wb") as stream:
    child=subprocess.Popen(argv, stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                           stderr=stream,pass_fds=(r,fd),start_new_session=True)
os.close(r);os.write(w,b"\x01");os.close(w);os.close(fd)
end=time.monotonic()+5
while True:
    try:
        result=relay_request(Path(sock),{"schema":RELAY_REQUEST_SCHEMA,"kind":"status",
            "resource_id":"a"*32,"request_id":"b"*32}, timeout=0.3)
        break
    except Exception:
        if child.poll() is not None or time.monotonic()>=end:
            if child.poll() is None:
                child.terminate();child.wait(timeout=3)
            raise SystemExit("fixture relay did not become ready: "+err.read_text()[:3000])
        time.sleep(0.03)
print(json.dumps({"relay_pid":child.pid,"native_pid":result["child_pid"],"expiry":expiry}),flush=True)
sys.stdin.buffer.read(1)
'''


@pytest.mark.parametrize("trigger", ["parent_loss", "expiry"])
def test_real_relay_retains_original_native_process_until_owner_evidence_is_terminal(tmp_path, trigger):
    short = Path(tempfile.mkdtemp(prefix="mmxr3-", dir="/tmp"))
    root = short / "artifacts"
    root.mkdir(mode=0o700)
    store_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    store = aa.adopt_artifact_store(store_fd)
    identity = aa.ActionArtifactIdentity(
        action_id="a"*32,purpose="browser_resource",subject_digest="b"*64,
        client_ref="client:test",resource="https://example.invalid/browser",project_ref="project:test",
        context_ref="context:test",responsibility_ref="responsibility:test",operation_ref="operation:test",
        owner_ref="owner:test",generation="generation:test",root_device=1,root_inode=2,
        store_device=store.device,store_inode=store.inode,host_id="c"*64,boot_session_id="boot:test",
        relative_path="browser:resource",source_identity="d"*64,
    )
    pending = dataclasses.replace(identity, action_id="f"*32,purpose="browser_action",relative_path="browser:action")
    with aa.acquire_store_writer(store):
        aa.claim_action(store,identity,claimed_at_ms=1000)
        aa.finalize_action(store,identity,effect_state="APPLIED",observed_sha256=None,
                           completed_at_ms=2000,durability="durable")
        aa.claim_action(store,pending,claimed_at_ms=2000)
    template = Path(_fake_child(tmp_path)[-1])
    child_script = short / "node_modules" / "@playwright" / "mcp" / "cli.js"
    child_script.parent.mkdir(parents=True)
    child_script.write_text(template.read_text())
    marker = short / "native-fd-check"
    # Compare underlying store identity, not just an fd number that could be reused.
    prefix = f'''import os
found=False
for name in range(3,256):
    try:
        s=os.fstat(name)
        found=found or (s.st_dev,s.st_ino)==({store.device},{store.inode})
    except OSError:
        pass
open({str(marker)!r},"w").write("LEAKED" if found else "NO_OWNER_FD")
'''
    child_script.write_text(prefix + child_script.read_text())
    socket_path = short / "relay.sock"
    project_root = str(Path(__file__).resolve().parents[1])
    parent = subprocess.Popen(
        [sys.executable,"-I","-c",PARENT,project_root,str(root),str(socket_path),str(child_script),_digest(),trigger],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
    )
    relay_pid = None
    relay_identity = None
    try:
        assert select.select([parent.stdout],[],[],7)[0], "fixture parent produced no readiness"
        line = parent.stdout.readline()
        assert line, parent.stderr.read(2000)
        ready = json.loads(line)
        relay_pid, native_pid = ready["relay_pid"], ready["native_pid"]
        inspector = ProcessInspector()
        relay_identity = inspector.inspect(relay_pid)
        native_identity = inspector.inspect(native_pid)
        assert marker.read_text() == "NO_OWNER_FD"
        if trigger == "parent_loss":
            parent.terminate()
            parent.wait(timeout=3)
        else:
            deadline=time.monotonic()+3
            while int(time.time()*1000) < ready["expiry"]:
                assert time.monotonic()<deadline
                time.sleep(0.02)
        # Observe beyond several relay iterations after the real trigger.
        deadline=time.monotonic()+0.5
        while time.monotonic()<deadline:
            assert socket_path.exists()
            assert inspector.inspect(relay_pid).start_identity == relay_identity.start_identity
            assert inspector.inspect(native_pid).start_identity == native_identity.start_identity
            time.sleep(0.05)
        assert sorted(p.name for p in root.iterdir()) == ["a"*32+".claim","a"*32+".result","f"*32+".claim"]
        # The existing owner resolves its original synthetic pending action.
        with aa.acquire_store_writer(store):
            aa.finalize_action(store,pending,effect_state="NOT_APPLIED",observed_sha256=None,
                               completed_at_ms=3000,durability="durable")
        deadline=time.monotonic()+4
        while socket_path.exists() and time.monotonic()<deadline:
            time.sleep(0.03)
        assert not socket_path.exists(), "terminal owner evidence did not release the held target"
        with pytest.raises((ProcessIdentityError, ProcessLookupError, OSError, ValueError)):
            inspector.inspect(native_pid)
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=3)
        for stream in (parent.stdin,parent.stdout,parent.stderr):
            if stream is not None:
                stream.close()
        if relay_pid is not None and relay_identity is not None:
            try:
                current=ProcessInspector().inspect(relay_pid)
                if current.start_identity==relay_identity.start_identity and current.pgid==relay_pid:
                    os.killpg(relay_pid,signal.SIGTERM)
            except (ProcessIdentityError,ProcessLookupError,OSError,ValueError):
                pass
        os.close(store_fd)
        shutil.rmtree(short,ignore_errors=True)

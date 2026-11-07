"""Cold-process native history and single-writer proof, with a deterministic model.

The existing ACP/Agent/tool fixture writes the donor's actual JSONL store.
These tests exercise that original store after the ACP process has settled.
They do not authorize a company session, resume a model turn, install a service,
or substitute a native session identifier for an authenticated principal.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import selectors
import subprocess

from control_plane.worker_execution_contract import WorkerRunStatus
from test_dsh_fullapp_native_agent import exercise, supplied


def _history_command(tmp_path, session_id, mode):
    root, _manifest, node = supplied()
    return [
        str(node), str(root / ".cache/build/native-history-fixture.mjs"),
        str(tmp_path.resolve() / "fixture/sessions"), session_id, mode,
    ]


def _recover(tmp_path, session_id, mode="read"):
    result = subprocess.run(
        _history_command(tmp_path, session_id, mode),
        text=True, capture_output=True, timeout=12,
        env={"PATH": "/usr/bin:/bin", "LANG": "C"},
    )
    assert result.returncode == 0, result.stderr
    assert "FULLAPP_MODEL_CALL" not in result.stderr
    return json.loads(result.stdout)


def _stored_bytes(tmp_path):
    root = tmp_path / "fixture/sessions"
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in root.rglob("*.jsonl*") if path.is_file()}
    assert files, "native durable session did not materialize"
    return files


def _completed_session(tmp_path):
    receipt, ref, _memo = asyncio.run(exercise(tmp_path, "durable"))
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED, Path(ref.stderr_path).read_text()
    assert receipt.result.structured_output["status"] == "COMPLETED"
    session_id = receipt.result.provider_session_id
    assert session_id
    marker = "FULLAPP_MODEL_OUTPUT_SHA256 "
    digests = [line[len(marker):] for line in Path(ref.stderr_path).read_text().splitlines()
               if line.startswith(marker)]
    assert len(digests) == 1 and len(digests[0]) == 64
    return session_id, digests[0]


def test_current_fullapp_history_recovers_original_stream_in_new_process(tmp_path):
    session_id, original_sha256 = _completed_session(tmp_path)
    before = _stored_bytes(tmp_path)
    first = _recover(tmp_path, session_id)
    second = _recover(tmp_path, session_id)
    assert first == second
    assert first["state"] == "READ_RECOVERED"
    assert first["header"]["id"] == first["session_id"] == session_id
    assert first["header"]["cwd"] == str(tmp_path.resolve() / "workspace")
    events = first["events"]
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert sum(event["type"] == "assistant/message" for event in events) >= 3
    # The donor persists compact streams on each durable assistant settlement.
    # Its own decoder must recover all three original model delta boundaries.
    final_chunks = first["streams"][-1]["chunks"]
    deltas = [row["chunk"]["text"] for row in final_chunks
              if row["chunk"]["type"] == "text-delta"]
    assert len(deltas) == 3
    assert hashlib.sha256("".join(deltas).encode()).hexdigest() == original_sha256
    transcript = json.dumps(events)
    assert "fullapp-native-needle" in transcript
    assert "read_file" in transcript and "search_text" in transcript
    assert _stored_bytes(tmp_path) == before


def test_current_fullapp_history_preserves_active_native_writer(tmp_path):
    session_id, _output = _completed_session(tmp_path)
    before = _stored_bytes(tmp_path)
    holder = subprocess.Popen(
        _history_command(tmp_path, session_id, "hold"),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
    )
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(holder.stdout, selectors.EVENT_READ)
            assert ready.select(timeout=12), "native history writer did not become ready"
        line = holder.stdout.readline()
        assert line, "native history writer exited before ownership"
        assert json.loads(line) == {"state": "WRITE_HELD", "session_id": session_id}
        # An original reader may observe while a live writer retains its lease.
        observed = _recover(tmp_path, session_id)
        assert observed["state"] == "READ_RECOVERED"
        assert _recover(tmp_path, session_id, "probe") == {
            "state": "ACTIVE_WRITER_REFUSED", "session_id": session_id,
        }
        assert _stored_bytes(tmp_path) == before
        stdout, stderr = holder.communicate("release\n", timeout=12)
        assert holder.returncode == 0, stderr
        assert json.loads(stdout) == {"state": "WRITE_RELEASED", "session_id": session_id}
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.communicate(timeout=12)
    # Only the original holder's actual close makes the native lease available.
    resumed = _recover(tmp_path, session_id, "acquire")
    assert resumed["state"] == "WRITE_ACQUIRED"
    assert resumed["events"] == observed["events"]
    assert _stored_bytes(tmp_path) == before

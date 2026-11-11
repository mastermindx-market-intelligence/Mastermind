"""Check the task-tool qualification verdict against a deterministic CLI transcript."""
import http.client
import json
import subprocess
from urllib.parse import urlsplit

import pytest

from scripts import qualify_t3_task_tools as fixture


def init(tools):
    return {"type": "system", "subtype": "init", "tools": tools}


SUCCESS = {"type": "result", "subtype": "success", "is_error": False}


@pytest.mark.parametrize(("records", "passed", "count"), [
    ([init(["Read"]), SUCCESS], True, 1),
    ([init([]), SUCCESS], True, 0),
    ([SUCCESS], False, None),
    ([{"type": "system", "subtype": "init"}, SUCCESS], False, None),
    ([init("Read"), SUCCESS], False, None),
    ([init([None]), SUCCESS], False, None),
    ([init([]), init(["Read"]), SUCCESS], False, None),
    ([init(["Read"])], False, 1),
    ([init([]), {"type": "result", "is_error": True, "subtype": "error"}], False, 0),
])
def test_baseline_requires_observed_init_and_successful_result(monkeypatch, tmp_path, records, passed, count):
    def fake_cli(command, *, env, **kwargs):
        target = urlsplit(env["ANTHROPIC_BASE_URL"])
        conn = http.client.HTTPConnection(target.hostname, target.port, timeout=3)
        try:
            conn.request("POST", "/v1/messages", json.dumps({"model": fixture.MODEL, "tools": []}),
                         {"x-api-key": env["ANTHROPIC_API_KEY"], "content-type": "application/json"})
            response = conn.getresponse()
            assert response.status == 200
            response.read()
        finally:
            conn.close()
        return subprocess.CompletedProcess(command, 0, "\n".join(map(json.dumps, records)), "")

    monkeypatch.setattr(fixture.subprocess, "run", fake_cli)
    row = fixture.run_variant(tmp_path / "fixture-cli", "baseline_eager")
    assert row["messages_requests"] == 1
    assert row["passed"] is passed
    assert row["init_tool_count"] == count

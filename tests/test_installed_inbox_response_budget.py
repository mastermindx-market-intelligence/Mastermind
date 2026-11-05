"""Installed Inbox uses the existing whole-frame budget without losing rows."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from control_plane.executive_ceo_ingress import MAX_RESPONSE_BYTES
from control_plane.executive_inbox import classify_job
from control_plane.executive_runtime import AttemptStatus, JobStatus
from integrations.executive_mcp.installed import InstalledExecutiveReaders
from integrations.executive_mcp.schemas import GatewayError, bound_document, canonical_json
from integrations.mastermind_executive_app.gateway import CeoIngressClient, CeoIngressReadGateway
from test_executive_read_transport_diagnostics import _canonical_inbox_data, canonical_result


def inbox_rows(count):
    data = _canonical_inbox_data()
    rows = []
    for index in range(count):
        job_id = f"JOB-{index + 1:03}"
        job = SimpleNamespace(
            job_id=job_id, attempt_count=1, attempt_limit=1,
            status=JobStatus.FAILED, result=None, checkpoint=None,
            parent_job_id=None, root_job_id=job_id, depth=0,
            owner_seat="coo", escalation_target="coo", business_impact="ordinary",
            review_required=False, reviews_job_id=None, updated_at="2026-10-15T08:14:25Z",
        )
        attempt = SimpleNamespace(
            attempt_id=f"ATT-{index + 1:03}", status=AttemptStatus.FAILED, exit_code=1,
        )
        row, bucket = classify_job(job, last_attempt=attempt)
        assert row and bucket is None
        rows.append(row)
    data["attention"] = rows
    for group in ("jobs", "attempts"):
        data["runtime_counts"][group]["total"] = count
        for status in data["runtime_counts"][group]["by_status"]:
            data["runtime_counts"][group]["by_status"][status] = count if status == "FAILED" else 0
    data["suppressed"] = {key: 0 for key in data["suppressed"]}
    return data


def read_inbox(tmp_path, monkeypatch, data, *, grounding=None, degraded=()):
    readers = InstalledExecutiveReaders(
        repo_root=tmp_path, macro_root=tmp_path / "macro", runtime_root=tmp_path / "runtime",
    )
    grounding = canonical_result()["grounding"] if grounding is None else grounding
    monkeypatch.setattr(readers, "_executive_inbox", lambda: (data, grounding, list(degraded)))

    async def call():
        try:
            return await readers.call("executive_inbox", {})
        finally:
            await readers.aclose()

    return asyncio.run(call())


@pytest.mark.parametrize("count", [10, 15, 20, 25])
def test_installed_inbox_keeps_all_ordinary_rows(tmp_path, monkeypatch, count):
    data = inbox_rows(count)
    original = copy.deepcopy(data)
    result = read_inbox(tmp_path, monkeypatch, data)
    assert result["ok"], result
    assert result["data"] == original == data
    assert result["bounded"] == []
    assert len(canonical_json({"ok": True, "result": result})) + 1 <= MAX_RESPONSE_BYTES
    assert CeoIngressReadGateway("/tmp/unused.sock", CeoIngressClient())._is_canonical_read_result(
        result, tool="executive_inbox", arguments={}
    )


def test_installed_inbox_bounds_long_text_with_receipts_in_same_frame(tmp_path, monkeypatch):
    data = inbox_rows(25)
    data["attention"][0]["reason"] = "界" * 20_000
    result = read_inbox(tmp_path, monkeypatch, data)
    assert result["ok"], result
    assert len(result["data"]["attention"]) == 25
    assert result["data"]["attention"][0]["reason"]["bounded"] is True
    assert result["data"]["attention"][0]["job_id"] == "JOB-001"
    assert result["bounded"]
    assert len(canonical_json({"ok": True, "result": result})) + 1 <= MAX_RESPONSE_BYTES
    assert CeoIngressReadGateway("/tmp/unused.sock", CeoIngressClient())._is_canonical_read_result(
        result, tool="executive_inbox", arguments={}
    )


def test_unboundable_inbox_refuses_without_dropping_rows(tmp_path, monkeypatch):
    data = inbox_rows(100)
    original = copy.deepcopy(data)
    result = read_inbox(tmp_path, monkeypatch, data)
    assert result["ok"] is False
    assert result["error"]["code"] == "output_too_large"
    assert result["data"] is None
    assert data == original


def test_installed_inbox_accounts_for_outer_grounding_and_warnings(tmp_path, monkeypatch):
    result = read_inbox(
        tmp_path, monkeypatch, inbox_rows(10),
        grounding={"diagnostic": "界" * 9_000}, degraded=["warning" * 1_000],
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "output_too_large"
    assert len(canonical_json({"ok": True, "result": result})) + 1 <= MAX_RESPONSE_BYTES


def test_small_leaves_are_not_enlarged_into_bounding_objects():
    with pytest.raises(GatewayError) as exc:
        bound_document({"rows": ["small"] * 100}, limit=100)
    assert "bounding 0 field(s)" in exc.value.message


def test_unboundable_small_leaves_do_not_reencode_whole_document_per_leaf(monkeypatch):
    from integrations.executive_mcp import schemas
    actual = schemas.canonical_json
    whole_documents = []

    def counted(value):
        if isinstance(value, dict) and "rows" in value:
            whole_documents.append(len(value["rows"]))
        return actual(value)

    monkeypatch.setattr(schemas, "canonical_json", counted)
    with pytest.raises(GatewayError, match="ceiling"):
        bound_document({"rows": ["small"] * 500}, limit=100)
    # A refused wide document must not cause quadratic whole-frame encoding.
    assert len(whole_documents) <= 2


def test_bounding_budget_includes_receipts():
    data = {"a": "x" * 10_000, "b": "y" * 10_000}
    bounded, receipts = bound_document(data, limit=1_350)
    assert len(canonical_json(bounded)) + len(canonical_json(receipts)) - 2 == 1_350
    with pytest.raises(GatewayError, match="ceiling"):
        bound_document(data, limit=1_349)


@pytest.mark.parametrize("code", ["output_too_large", "response_too_large"])
def test_size_failure_remains_distinct_from_permission_failure(code):
    public_code, message = CeoIngressReadGateway._classified_upstream_failure(code)
    assert public_code == "output_too_large"
    assert "byte limit" in message
    assert "permission" not in message
    assert CeoIngressReadGateway._classified_upstream_failure("authority_refused")[0] == "backend_refused"


@pytest.mark.parametrize("count", [25, 100])
def test_installed_inbox_crosses_real_private_socket_once(tmp_path, monkeypatch, count):
    result = read_inbox(tmp_path, monkeypatch, inbox_rows(count))
    if count == 100:
        assert result["error"]["code"] == "output_too_large", result
    wire = canonical_json({"ok": True, "result": result}) + b"\n"

    async def exercise():
        requests = []

        async def backend(stream, writer):
            try:
                requests.append(json.loads(await stream.readline()))
                writer.write(wire)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        with tempfile.TemporaryDirectory(prefix="inbox-", dir="/tmp") as directory:
            path = str(Path(directory) / "reader.sock")
            server = await asyncio.start_unix_server(backend, path=path)
            async with server:
                gateway = CeoIngressReadGateway(path, CeoIngressClient())
                try:
                    observed = await gateway.call("executive_inbox", {})
                finally:
                    await gateway.aclose()
            assert len(requests) == 1
            assert requests[0]["tool"] == "executive_inbox"
            return observed

    observed = asyncio.run(exercise())
    if count == 25:
        assert observed == result
    else:
        assert observed["ok"] is False
        assert observed["error"]["code"] == "output_too_large"

"""Focused tests for the read-only ``GET /api/decision-snapshot`` route.

Exercises the real FastAPI app through ``TestClient`` (no scheduler/background threads —
mirrors the pattern in ``tests/test_web.py``). The route may only import
``portfolio.decision_snapshot`` and call ``read_projection``; it must never compose,
persist, or otherwise mutate a snapshot. Most cases monkeypatch
``decision_snapshot.read_projection``/``create_snapshot`` directly; a few use a real,
sealed snapshot persisted under an isolated ``tmp_path`` root to prove end-to-end behavior
and that a GET never touches the filesystem store.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portfolio import decision_snapshot as snapshots
from portfolio import decision_snapshot_contracts as c

_HARD_FALSE_AUTHORITY = {
    "write_permitted": False,
    "execution_authority": False,
    "numeric_target_authority": False,
}


def _client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Mocked-payload fixtures (shape-compatible with the real read_projection contract)
# ---------------------------------------------------------------------------

def _manifest_stub(**overrides) -> dict:
    base = {
        "schema": c.SNAPSHOT_SCHEMA,
        "snapshot_id": "sha256:" + "1" * 64,
        "book": "autonomous",
        "decision_cutoff": "2026-09-15T20:00:00Z",
        "recorded_at": "2026-09-15T20:01:00Z",
        "state": "COMPLETE",
        "coverage_state": "COMPLETE",
        "summary": {
            "sources_total": 0, "sources_available": 0,
            "domains_complete": 0, "domains_partial": 0, "domains_blocked": 0,
        },
        "source_generation_set": [],
        "sources": [],
        "gaps": [],
        "correction": {"status": "ORIGINAL", "same_cutoff_prior_snapshot_ids": []},
        "authority": dict(_HARD_FALSE_AUTHORITY),
    }
    base.update(overrides)
    return {"snapshot": base}


def _section_page_stub(section_id: str = "book_truth", rows=None, **overrides) -> dict:
    rows = rows if rows is not None else [{"value": section_id}]
    page = {
        "schema": c.SECTION_SCHEMA,
        "section_id": section_id,
        "coverage_state": "COMPLETE",
        "source_ids": [f"source.{section_id}"],
        "rows_total": len(rows),
        "rows_returned": len(rows),
        "omitted_rows": 0,
        "gaps": [],
        "rows": rows,
        "next_offset": None,
    }
    result = {
        "snapshot_id": "sha256:" + "1" * 64,
        "book": "autonomous",
        "decision_cutoff": "2026-09-15T20:00:00Z",
        "recorded_at": "2026-09-15T20:01:00Z",
        "state": "COMPLETE",
        "coverage_state": "COMPLETE",
        "correction": {"status": "ORIGINAL", "same_cutoff_prior_snapshot_ids": []},
        "section": page,
    }
    result.update(overrides)
    return result


# ---------------------------------------------------------------------------
# Real, sealed-snapshot fixtures for filesystem-integration tests
# ---------------------------------------------------------------------------

def _receipt(source_id: str, section_id: str, *, generation: str = "sha256:" + "0" * 64) -> dict:
    return {
        "schema": c.SOURCE_RECEIPT_SCHEMA,
        "source_id": source_id,
        "domains": [section_id],
        "producer": "test_fixture",
        "owner": "test_fixture",
        "artifact": f"test/{source_id}",
        "source_schema": None,
        "schema_version": None,
        "definition_id": None,
        "artifact_digest": "sha256:" + "0" * 64,
        "observed_at": "2026-09-15T20:01:00Z",
        "known_at": "2026-09-15T19:00:00Z",
        "as_of": "2026-09-15",
        "generated_at": None,
        "filesystem_observed_at": "2026-09-15T19:00:00Z",
        "correction_generation": generation,
        "freshness_state": "FRESH",
        "coverage_state": "COMPLETE",
        "rights_class": "FIRST_PARTY_INTERNAL",
        "authority_class": "BOOK_STATE",
        "status": "AVAILABLE",
        "required": False,
        "bytes": 10,
        "rows_total": 1,
        "rows_returned": 1,
        "omitted_rows": 0,
        "clock_basis": "FILE_MTIME_FIRST_PARTY_STATE",
        "error_code": None,
    }


def _section_row(section_id: str, source_ids: list) -> dict:
    rows = [{"value": section_id}]
    return {
        "schema": c.SECTION_SCHEMA,
        "section_id": section_id,
        "coverage_state": "COMPLETE",
        "source_ids": list(source_ids),
        "rows_total": len(rows),
        "rows_returned": len(rows),
        "omitted_rows": 0,
        "rows": rows,
        "gaps": [],
    }


def _capture() -> dict:
    sources_out = [_receipt(f"source.{sid}", sid) for sid in c.SECTION_IDS]
    sections_out = {sid: _section_row(sid, [f"source.{sid}"]) for sid in c.SECTION_IDS}
    return {"sources": sources_out, "sections": sections_out, "gaps": []}


def _persist_real_snapshot() -> dict:
    composed = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(),
        same_cutoff_prior_snapshot_ids=[],
    )
    result = snapshots.persist_snapshot(composed)
    return result["snapshot"]


@pytest.fixture()
def snapshot_root(tmp_path, monkeypatch) -> Path:
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setattr(snapshots, "_ROOT", storage)
    return storage


def _tree_fingerprint(root: Path) -> dict:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# Never composes / no-snapshot is a normal 200
# ---------------------------------------------------------------------------

def test_get_never_calls_create_snapshot(snapshot_root, monkeypatch):
    _persist_real_snapshot()
    calls = []
    monkeypatch.setattr(snapshots, "create_snapshot", lambda *a, **k: calls.append((a, k)))

    client = _client()
    client.get("/api/decision-snapshot")
    client.get("/api/decision-snapshot", params={"section": "book_truth"})
    client.get("/api/decision-snapshot", params={"offset": "-1"})
    client.get("/api/decision-snapshot", params={"book": "flagship"})

    assert calls == []


def test_no_existing_snapshot_is_a_normal_200_no_snapshot_state(snapshot_root, monkeypatch):
    calls = []
    monkeypatch.setattr(snapshots, "create_snapshot", lambda *a, **k: calls.append((a, k)))

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NO_SNAPSHOT"
    assert body["book"] == "autonomous"
    for key, value in _HARD_FALSE_AUTHORITY.items():
        assert body[key] is value
    assert response.headers.get("cache-control") == "no-store"
    assert calls == []


# ---------------------------------------------------------------------------
# Argument forwarding / unsupported book rejected before storage read
# ---------------------------------------------------------------------------

def test_exact_read_projection_args_are_forwarded(monkeypatch):
    recorded = {}

    def _fake(**kwargs):
        recorded.update(kwargs)
        return _manifest_stub()

    monkeypatch.setattr(snapshots, "read_projection", _fake)

    response = _client().get(
        "/api/decision-snapshot",
        params={"snapshot_id": "sha256:" + "1" * 64, "offset": "5", "limit": "10"},
    )

    assert response.status_code == 200
    assert recorded == {
        "book": "autonomous",
        "snapshot_id": "sha256:" + "1" * 64,
        "section_id": None,
        "offset": 5,
        "limit": 10,
    }


@pytest.mark.parametrize("book", ["flagship", "AUTONOMOUS", "../autonomous", "not-a-book"])
def test_rejects_non_s0_book_before_storage_read(book, monkeypatch):
    def _fail(**kwargs):
        pytest.fail("invalid book reached storage")

    monkeypatch.setattr(snapshots, "read_projection", _fail)

    response = _client().get("/api/decision-snapshot", params={"book": book})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "unsupported_snapshot_book"
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Real end-to-end manifest / section reads
# ---------------------------------------------------------------------------

def test_exact_snapshot_manifest_response(snapshot_root):
    persisted = _persist_real_snapshot()

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["book"] == "autonomous"
    assert body["status"] == persisted["state"]
    assert body["snapshot"]["snapshot_id"] == persisted["snapshot_id"]
    assert "sections" not in body["snapshot"]
    for key, value in _HARD_FALSE_AUTHORITY.items():
        assert body[key] is value
    assert response.headers.get("cache-control") == "no-store"


def test_section_page_response(snapshot_root):
    persisted = _persist_real_snapshot()

    response = _client().get(
        "/api/decision-snapshot",
        params={"snapshot_id": persisted["snapshot_id"], "section": "book_truth"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["section"]["section_id"] == "book_truth"
    assert body["section"]["rows"] == [{"value": "book_truth"}]
    for key, value in _HARD_FALSE_AUTHORITY.items():
        assert body[key] is value
    assert len(response.content) <= 65_536
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Validation: invalid request shapes never reach storage / never write
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("params", [
    {"snapshot_id": "../../secret"},
    {"section": "../../secret"},
    {"offset": "-1"},
    {"limit": "0"},
    {"limit": "101"},
])
def test_invalid_request_is_4xx_and_never_writes(params, snapshot_root, monkeypatch):
    _persist_real_snapshot()
    calls = []
    monkeypatch.setattr(snapshots, "create_snapshot", lambda *a, **k: calls.append((a, k)))

    response = _client().get("/api/decision-snapshot", params=params)

    assert response.status_code in {400, 404, 422}
    assert response.headers.get("cache-control") == "no-store"
    assert calls == []


def test_boolean_offset_query_is_rejected(monkeypatch):
    def _fail(**kwargs):
        pytest.fail("boolean offset reached storage")

    monkeypatch.setattr(snapshots, "read_projection", _fail)

    response = _client().get("/api/decision-snapshot", params={"offset": True})

    assert response.status_code in {400, 404, 422}
    assert response.headers.get("cache-control") == "no-store"


def test_wrong_type_offset_text_is_rejected(monkeypatch):
    def _fail(**kwargs):
        pytest.fail("non-numeric offset reached storage")

    monkeypatch.setattr(snapshots, "read_projection", _fail)

    response = _client().get("/api/decision-snapshot", params={"offset": "not-a-number"})

    assert response.status_code in {400, 404, 422}
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Not found / corrupt / unexpected — closed error envelopes, no leakage
# ---------------------------------------------------------------------------

def test_explicit_snapshot_id_not_found_is_404_without_leaking(monkeypatch):
    canary = "/Volumes/secret-root/deadbeef-canary.json"

    def _raise(**kwargs):
        raise snapshots.SnapshotNotFound(f"snapshot not found at {canary}")

    monkeypatch.setattr(snapshots, "read_projection", _raise)

    response = _client().get(
        "/api/decision-snapshot", params={"snapshot_id": "sha256:" + "9" * 64}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "snapshot_not_found"
    assert canary not in response.text
    assert response.headers.get("cache-control") == "no-store"


def test_corrupt_snapshot_returns_503_without_leaking_exception_text(monkeypatch):
    canary = "tamper-detected-at-/Volumes/Mastermind/secret-path"

    def _raise(**kwargs):
        raise snapshots.SnapshotCorrupt(canary)

    monkeypatch.setattr(snapshots, "read_projection", _raise)

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "corrupt_snapshot"
    for key, value in _HARD_FALSE_AUTHORITY.items():
        assert body[key] is value
    assert canary not in response.text
    assert response.headers.get("cache-control") == "no-store"


def test_unexpected_exception_returns_500_without_leaking(monkeypatch):
    canary = "internal-secret-token-abc123"

    def _raise(**kwargs):
        raise RuntimeError(canary)

    monkeypatch.setattr(snapshots, "read_projection", _raise)

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert canary not in response.text
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Cache-Control: no-store on every path (mutation proof: omit it on one branch)
# ---------------------------------------------------------------------------

def test_all_response_paths_carry_no_store(monkeypatch):
    scenarios = []

    def _ok(**kwargs):
        return _manifest_stub()

    monkeypatch.setattr(snapshots, "read_projection", _ok)
    scenarios.append(_client().get("/api/decision-snapshot"))
    scenarios.append(_client().get("/api/decision-snapshot", params={"book": "flagship"}))
    scenarios.append(_client().get("/api/decision-snapshot", params={"limit": "0"}))

    def _not_found(**kwargs):
        raise snapshots.SnapshotNotFound("none")

    monkeypatch.setattr(snapshots, "read_projection", _not_found)
    scenarios.append(_client().get("/api/decision-snapshot"))
    scenarios.append(
        _client().get("/api/decision-snapshot", params={"snapshot_id": "sha256:" + "2" * 64})
    )

    def _invalid(**kwargs):
        raise snapshots.SnapshotInvalidRequest("bad")

    monkeypatch.setattr(snapshots, "read_projection", _invalid)
    scenarios.append(_client().get("/api/decision-snapshot"))

    def _corrupt(**kwargs):
        raise snapshots.SnapshotCorrupt("bad bytes")

    monkeypatch.setattr(snapshots, "read_projection", _corrupt)
    scenarios.append(_client().get("/api/decision-snapshot"))

    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(snapshots, "read_projection", _boom)
    scenarios.append(_client().get("/api/decision-snapshot"))

    for response in scenarios:
        assert response.headers.get("cache-control") == "no-store", response.request.url


# ---------------------------------------------------------------------------
# Authority fence: never serve a payload that lacks/contradicts hard-false authority
# ---------------------------------------------------------------------------

def test_contradictory_authority_is_refused_not_served(monkeypatch):
    def _tampered(**kwargs):
        return _manifest_stub(authority={
            "write_permitted": True,
            "execution_authority": False,
            "numeric_target_authority": False,
        })

    monkeypatch.setattr(snapshots, "read_projection", _tampered)

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "corrupt_snapshot"
    for key, value in _HARD_FALSE_AUTHORITY.items():
        assert body[key] is value


def test_missing_authority_field_is_refused_not_served(monkeypatch):
    def _tampered(**kwargs):
        stub = _manifest_stub()
        del stub["snapshot"]["authority"]
        return stub

    monkeypatch.setattr(snapshots, "read_projection", _tampered)

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 503
    assert response.json()["error"] == "corrupt_snapshot"


# ---------------------------------------------------------------------------
# Section response byte ceiling: refuse rather than silently truncate
# ---------------------------------------------------------------------------

def test_oversize_section_response_is_refused_not_truncated(monkeypatch):
    big_rows = [{"value": "x" * 200} for _ in range(2000)]

    def _oversize(**kwargs):
        return _section_page_stub(rows=big_rows)

    monkeypatch.setattr(snapshots, "read_projection", _oversize)

    response = _client().get(
        "/api/decision-snapshot",
        params={"snapshot_id": "sha256:" + "1" * 64, "section": "book_truth"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "invalid_projection"
    assert "rows" not in body
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Route import/call boundary
# ---------------------------------------------------------------------------

def test_route_only_imports_and_calls_decision_snapshot_read_projection():
    from app import web

    source = inspect.getsource(web.api_decision_snapshot)

    assert "from portfolio import decision_snapshot" in source
    for forbidden in (
        "decision_snapshot_sources",
        "decision_snapshot_cli",
        "portfolio_decision_snapshot",
        "paper_account",
        "scheduler",
        "quote",
        "settlement",
        "compose_snapshot",
        "capture_all",
        "persist_snapshot",
    ):
        assert forbidden not in source, f"route source references forbidden {forbidden!r}"

    calls = set(re.findall(r"decision_snapshot\.(\w+)\(", source))
    assert calls == {"read_projection"}, calls


# ---------------------------------------------------------------------------
# Real filesystem integration: GETs never create/modify a snapshot file
# ---------------------------------------------------------------------------

def test_gets_never_create_or_modify_snapshot_files(snapshot_root):
    _persist_real_snapshot()
    before = _tree_fingerprint(snapshot_root)
    assert before, "fixture must have persisted at least one real snapshot file"

    client = _client()
    client.get("/api/decision-snapshot")
    client.get("/api/decision-snapshot", params={"section": "book_truth"})
    client.get("/api/decision-snapshot", params={"snapshot_id": "sha256:" + "0" * 64})
    client.get("/api/decision-snapshot", params={"offset": "-1"})
    client.get("/api/decision-snapshot", params={"limit": "101"})
    client.get("/api/decision-snapshot", params={"book": "flagship"})

    after = _tree_fingerprint(snapshot_root)
    assert after == before

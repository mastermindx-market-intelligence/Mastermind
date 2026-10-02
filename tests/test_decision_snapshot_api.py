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

import hashlib
import inspect
import io
import os
import re
import stat
import tokenize
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
    """A complete, type-aware fingerprint of every node under ``root``.

    Uses ``lstat`` (never following symlinks) so a file-to-symlink swap changes the
    recorded mode even when the link's target has identical size/mtime, and hashes
    regular-file content so a same-size, mtime-restored rewrite is still caught.
    Directories and any other node type are included (no ``is_file()`` filter).
    """
    if not root.exists():
        return {}
    out: dict[str, tuple] = {}
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        digest = None
        symlink_target = None
        if p.is_symlink():
            symlink_target = os.readlink(p)
        elif stat.S_ISREG(st.st_mode):
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        out[str(p.relative_to(root))] = (
            st.st_mode, st.st_mtime_ns, st.st_size, symlink_target, digest,
        )
    return out


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
    body = response.json()
    assert body["error"] == "snapshot_not_found"
    assert body["status"] == "not_found"
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
    assert body["status"] == "INVALID"
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
    body = response.json()
    assert body["error"] == "internal_error"
    assert body["status"] == "internal_error"
    assert canary not in response.text
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Blocking finding: request/resource/internal errors must not overload the
# closed snapshot-state vocabulary. A COMPLETE snapshot must never be reported
# as "INVALID" just because the *request* was bad or the ID didn't exist.
# ---------------------------------------------------------------------------

def test_invalid_request_status_is_not_snapshot_state(snapshot_root):
    persisted = _persist_real_snapshot()
    assert persisted["state"] == "COMPLETE"

    response = _client().get("/api/decision-snapshot", params={"limit": "101"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["status"] == "invalid_request"
    assert body["status"] != "INVALID"


def test_snapshot_invalid_request_exception_status_is_not_snapshot_state(monkeypatch):
    def _raise(**kwargs):
        raise snapshots.SnapshotInvalidRequest("bad section id")

    monkeypatch.setattr(snapshots, "read_projection", _raise)

    response = _client().get("/api/decision-snapshot", params={"section": "book_truth"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["status"] == "invalid_request"


def test_oversize_section_response_status_is_snapshot_invalid(monkeypatch):
    big_rows = [{"value": "x" * 200} for _ in range(2000)]

    def _oversize(**kwargs):
        return _section_page_stub(rows=big_rows)

    monkeypatch.setattr(snapshots, "read_projection", _oversize)

    response = _client().get(
        "/api/decision-snapshot",
        params={"snapshot_id": "sha256:" + "1" * 64, "section": "book_truth"},
    )

    assert response.status_code == 503
    assert response.json()["status"] == "INVALID"


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

    monkeypatch.setattr(snapshots, "read_projection", _ok)
    scenarios.append(_client().get("/api/decision-snapshot?offset=1&offset=2"))
    scenarios.append(_client().get("/api/decision-snapshot", params={"offset": "9" * 4301}))

    def _contradictory(**kwargs):
        return _manifest_stub(authority={
            "write_permitted": True, "execution_authority": False,
            "numeric_target_authority": False,
        })

    monkeypatch.setattr(snapshots, "read_projection", _contradictory)
    scenarios.append(_client().get("/api/decision-snapshot"))

    def _missing_authority(**kwargs):
        stub = _manifest_stub()
        del stub["snapshot"]["authority"]
        return stub

    monkeypatch.setattr(snapshots, "read_projection", _missing_authority)
    scenarios.append(_client().get("/api/decision-snapshot"))

    for response in scenarios:
        assert response.headers.get("cache-control") == "no-store", response.request.url


def test_repeated_query_param_is_closed_and_no_store(monkeypatch):
    """A repeated ``offset`` resolves to FastAPI's last-value-wins behavior — the
    response must still be one of our closed envelopes with no-store, never a raw,
    unheadered framework validation error."""
    def _ok(**kwargs):
        return _manifest_stub()

    monkeypatch.setattr(snapshots, "read_projection", _ok)

    response = _client().get("/api/decision-snapshot?offset=1&offset=2")

    assert response.headers.get("cache-control") == "no-store"
    assert response.status_code == 200
    assert response.json()["schema"] == "mastermind.portfolio_decision_snapshot.status.v1"


def test_oversized_integer_query_text_is_rejected_closed_and_no_store(monkeypatch):
    """Python 3.11+ caps int(<str>) conversion at 4300 digits; an oversized offset must
    still resolve to our closed invalid_request envelope, not an unheadered crash."""
    def _fail(**kwargs):
        pytest.fail("oversized offset text reached storage")

    monkeypatch.setattr(snapshots, "read_projection", _fail)

    response = _client().get("/api/decision-snapshot", params={"offset": "9" * 4301})

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["status"] == "invalid_request"
    assert response.headers.get("cache-control") == "no-store"


def test_nan_in_manifest_is_refused_not_an_unheadered_crash(monkeypatch):
    """JSONResponse.render defaults to allow_nan=False; without a guard this would
    raise ValueError while constructing the response, escaping the handler with no
    Cache-Control header at all."""
    def _nan_payload(**kwargs):
        return _manifest_stub(summary={
            "sources_total": float("nan"), "sources_available": 0,
            "domains_complete": 0, "domains_partial": 0, "domains_blocked": 0,
        })

    monkeypatch.setattr(snapshots, "read_projection", _nan_payload)

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    assert body["status"] == "internal_error"
    assert response.headers.get("cache-control") == "no-store"


def test_nan_in_section_row_is_refused_not_an_unheadered_crash(monkeypatch):
    def _nan_section(**kwargs):
        return _section_page_stub(rows=[{"value": float("nan")}])

    monkeypatch.setattr(snapshots, "read_projection", _nan_section)

    response = _client().get(
        "/api/decision-snapshot",
        params={"snapshot_id": "sha256:" + "1" * 64, "section": "book_truth"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    assert body["status"] == "internal_error"
    assert response.headers.get("cache-control") == "no-store"


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
    assert response.headers.get("cache-control") == "no-store"


def test_missing_authority_field_is_refused_not_served(monkeypatch):
    def _tampered(**kwargs):
        stub = _manifest_stub()
        del stub["snapshot"]["authority"]
        return stub

    monkeypatch.setattr(snapshots, "read_projection", _tampered)

    response = _client().get("/api/decision-snapshot")

    assert response.status_code == 503
    assert response.json()["error"] == "corrupt_snapshot"
    assert response.headers.get("cache-control") == "no-store"


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

    source = "\n".join([
        inspect.getsource(web.api_decision_snapshot),
        inspect.getsource(web._decision_snapshot_envelope),
        inspect.getsource(web._decision_snapshot_error),
        inspect.getsource(web._decision_snapshot_response),
    ])

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


def test_route_uses_named_http_status_constants_not_reserved_numeric_literals():
    from app import web

    source = "\n".join([
        inspect.getsource(web.api_decision_snapshot),
        inspect.getsource(web._decision_snapshot_envelope),
        inspect.getsource(web._decision_snapshot_error),
        inspect.getsource(web._decision_snapshot_response),
    ])
    reserved = []
    for line in source.splitlines():
        try:
            tokens = tokenize.generate_tokens(io.StringIO(line + "\n").readline)
            for token in tokens:
                if token.type != tokenize.NUMBER:
                    continue
                try:
                    value = int(token.string, 0)
                except ValueError:
                    continue
                if 400 <= value <= 999:
                    reserved.append(token.string)
        except (IndentationError, tokenize.TokenError):
            continue

    assert reserved == []


# ---------------------------------------------------------------------------
# Closed envelope: `extra` must never be able to override the fixed keys
# ---------------------------------------------------------------------------

def test_envelope_extra_cannot_override_reserved_keys():
    from app.web import _decision_snapshot_envelope

    body = _decision_snapshot_envelope(
        book="autonomous",
        status="COMPLETE",
        error=None,
        extra={
            "schema": "evil-schema",
            "book": "hacked-book",
            "status": "OWNED",
            "error": "should-not-appear",
            "write_permitted": True,
            "execution_authority": True,
            "numeric_target_authority": True,
            "snapshot": {"legit": "payload"},
        },
    )

    assert body["schema"] == "mastermind.portfolio_decision_snapshot.status.v1"
    assert body["book"] == "autonomous"
    assert body["status"] == "COMPLETE"
    assert "error" not in body
    for key, value in _HARD_FALSE_AUTHORITY.items():
        assert body[key] is value
    assert body["snapshot"] == {"legit": "payload"}


def test_envelope_extra_error_key_does_not_leak_when_error_param_is_none():
    from app.web import _decision_snapshot_envelope

    body = _decision_snapshot_envelope(
        book="autonomous", status="NO_SNAPSHOT", error=None,
        extra={"error": "leaked-if-not-filtered"},
    )

    assert "error" not in body


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


# ---------------------------------------------------------------------------
# Fingerprint discriminator strength: same-size/mtime-restored rewrite and a
# file-to-symlink type swap must both be caught (mutation proof for the fixture
# itself, not the route) — confined to tmp_path and restored byte-identically.
# ---------------------------------------------------------------------------

def test_fingerprint_detects_same_size_mtime_restored_rewrite(snapshot_root):
    persisted = _persist_real_snapshot()
    path = snapshots._snapshot_path("autonomous", persisted["snapshot_id"])
    before = _tree_fingerprint(snapshot_root)

    original_bytes = path.read_bytes()
    original_stat = path.stat()
    tampered = bytes(b ^ 0xFF for b in original_bytes)
    assert len(tampered) == len(original_bytes)
    try:
        path.write_bytes(tampered)
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        after = _tree_fingerprint(snapshot_root)
        assert after != before, "same-size, mtime-restored content rewrite must be caught"
    finally:
        path.write_bytes(original_bytes)
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert _tree_fingerprint(snapshot_root) == before


def test_fingerprint_detects_file_to_symlink_swap(snapshot_root):
    persisted = _persist_real_snapshot()
    path = snapshots._snapshot_path("autonomous", persisted["snapshot_id"])
    before = _tree_fingerprint(snapshot_root)

    original_bytes = path.read_bytes()
    original_stat = path.stat()
    parent_dir = path.parent
    parent_original_stat = parent_dir.stat()
    target = snapshot_root.parent / "decision-snapshot-symlink-target.json"
    assert snapshot_root not in target.parents
    assert not target.exists()
    try:
        target.write_bytes(original_bytes)
        os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        path.unlink()
        path.symlink_to(target)

        after = _tree_fingerprint(snapshot_root)
        assert after != before, "a file-to-symlink swap must be caught even with identical bytes"
    finally:
        if path.is_symlink():
            path.unlink()
        path.write_bytes(original_bytes)
        path.chmod(stat.S_IMODE(original_stat.st_mode))
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        target.unlink(missing_ok=True)
        # Creating/removing directory entries above moves the parent directory's own
        # mtime, which the fingerprint also tracks (directories are not filtered out).
        os.utime(parent_dir, ns=(parent_original_stat.st_atime_ns, parent_original_stat.st_mtime_ns))

    assert _tree_fingerprint(snapshot_root) == before

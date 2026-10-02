import json
import os
from pathlib import Path

import pytest

from control_plane.wake_events import canonical_json_bytes
from portfolio import decision_snapshot as snapshots
from portfolio import decision_snapshot_contracts as c
from portfolio import decision_snapshot_sources as sources


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _receipt(source_id: str, section_id: str, *, generation: str) -> dict:
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


def _capture(*, generation: str = "sha256:" + "0" * 64) -> dict:
    sources_out = [
        _receipt(f"source.{sid}", sid, generation=generation) for sid in c.SECTION_IDS
    ]
    sections_out = {sid: _section_row(sid, [f"source.{sid}"]) for sid in c.SECTION_IDS}
    return {"sources": sources_out, "sections": sections_out, "gaps": []}


def _sealed_snapshot(*, generation: str = "sha256:" + "a" * 64, prior: list | None = None) -> dict:
    return snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(generation=generation),
        same_cutoff_prior_snapshot_ids=prior or [],
    )


@pytest.fixture
def snapshot_root(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    macro = tmp_path / "macro"
    storage = tmp_path / "storage"
    repo.mkdir()
    macro.mkdir()
    storage.mkdir()
    monkeypatch.setattr(sources, "_ROOT", repo)
    monkeypatch.setattr(sources, "_V", macro)
    monkeypatch.setattr(snapshots, "_ROOT", storage)
    return storage


# ---------------------------------------------------------------------------
# Step 1: deterministic composition
# ---------------------------------------------------------------------------

def test_same_capture_and_clocks_produce_same_snapshot_id():
    first = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(),
        same_cutoff_prior_snapshot_ids=[],
    )
    second = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(),
        same_cutoff_prior_snapshot_ids=[],
    )
    assert first == second
    assert first["snapshot_id"] == second["snapshot_id"]


def test_state_is_partial_when_any_required_domain_is_unqualified():
    capture = _capture()
    capture["sections"]["risk_truth"]["coverage_state"] = "PARTIAL"
    capture["gaps"].append({
        "code": "UNQUALIFIED_CLOCK",
        "source_id": "macro.risk_envelope",
        "section_id": "risk_truth",
        "owner": "macro",
        "detail": "known_at unavailable",
    })
    result = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=capture,
        same_cutoff_prior_snapshot_ids=[],
    )
    assert result["state"] == "PARTIAL"
    assert result["coverage_state"] == "PARTIAL"


def test_same_cutoff_same_generation_reuses_existing_snapshot_despite_later_recorded_at(
    snapshot_root,
):
    first = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    second = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["created"] is False
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 1


def test_same_cutoff_new_generation_is_explicit_correction():
    # Controller ruling overrides the plan's example: correction.status must stay inside
    # the closed CORRECTION_STATUSES vocabulary ("CORRECTED"), not duplicate the root
    # "state" label ("CORRECTED_GENERATION_AVAILABLE").
    original = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(generation="sha256:" + "a" * 64),
        same_cutoff_prior_snapshot_ids=[],
    )
    corrected = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
        capture=_capture(generation="sha256:" + "b" * 64),
        same_cutoff_prior_snapshot_ids=[original["snapshot_id"]],
    )
    assert corrected["state"] == "CORRECTED_GENERATION_AVAILABLE"
    assert corrected["coverage_state"] == "COMPLETE"
    assert corrected["correction"] == {
        "status": "CORRECTED",
        "same_cutoff_prior_snapshot_ids": [original["snapshot_id"]],
    }
    assert corrected["snapshot_id"] != original["snapshot_id"]


def test_gaps_are_sealed_as_sorted_canonical_strings():
    capture = _capture()
    gap_b = {"code": "B", "source_id": "z", "section_id": None, "owner": None, "detail": None}
    gap_a = {"code": "A", "source_id": "y", "section_id": None, "owner": None, "detail": None}
    capture["gaps"] = [gap_b, gap_a]
    result = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=capture,
        same_cutoff_prior_snapshot_ids=[],
    )
    assert result["gaps"] == [
        canonical_json_bytes(gap_a).decode("ascii"),
        canonical_json_bytes(gap_b).decode("ascii"),
    ]


def test_recorded_at_before_decision_cutoff_is_invalid():
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.compose_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T19:59:00Z",
            capture=_capture(),
            same_cutoff_prior_snapshot_ids=[],
        )


def test_capture_shape_outside_exact_keys_is_invalid():
    capture = _capture()
    capture["extra"] = {}
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.compose_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T20:01:00Z",
            capture=capture,
            same_cutoff_prior_snapshot_ids=[],
        )


def test_duplicate_source_id_is_invalid():
    capture = _capture()
    capture["sources"].append(dict(capture["sources"][0]))
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.compose_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T20:01:00Z",
            capture=capture,
            same_cutoff_prior_snapshot_ids=[],
        )


def test_missing_section_is_invalid():
    capture = _capture()
    del capture["sections"]["book_truth"]
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.compose_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T20:01:00Z",
            capture=capture,
            same_cutoff_prior_snapshot_ids=[],
        )


def test_extra_section_is_invalid():
    capture = _capture()
    capture["sections"]["not_a_real_section"] = capture["sections"]["book_truth"]
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.compose_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T20:01:00Z",
            capture=capture,
            same_cutoff_prior_snapshot_ids=[],
        )


def test_section_key_mismatch_is_invalid():
    capture = _capture()
    capture["sections"]["book_truth"]["section_id"] = "risk_truth"
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.compose_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at="2026-09-15T20:01:00Z",
            capture=capture,
            same_cutoff_prior_snapshot_ids=[],
        )


# ---------------------------------------------------------------------------
# Step 2: immutable persistence
# ---------------------------------------------------------------------------

def test_persist_is_create_once_and_exact_retry_is_noop(snapshot_root):
    payload = _sealed_snapshot()
    first = snapshots.persist_snapshot(payload)
    before = Path(first["path"]).read_bytes()
    second = snapshots.persist_snapshot(payload)
    assert second["created"] is False
    assert Path(second["path"]).read_bytes() == before


def test_existing_content_address_with_wrong_bytes_freezes(snapshot_root):
    payload = _sealed_snapshot()
    path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{}")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.persist_snapshot(payload)
    assert path.read_bytes() == b"{}"


def test_old_snapshot_remains_byte_identical_after_correction(snapshot_root):
    original = _sealed_snapshot(generation="sha256:" + "a" * 64)
    corrected = _sealed_snapshot(
        generation="sha256:" + "b" * 64, prior=[original["snapshot_id"]]
    )
    snapshots.persist_snapshot(original)
    old_path = snapshots._snapshot_path("autonomous", original["snapshot_id"])
    old_bytes = old_path.read_bytes()
    snapshots.persist_snapshot(corrected)
    assert old_path.read_bytes() == old_bytes
    assert snapshots.load_snapshot("autonomous", original["snapshot_id"]) == original


@pytest.mark.parametrize(
    "book,snapshot_id",
    [
        ("../autonomous", "sha256:" + "a" * 64),
        ("AUTONOMOUS", "sha256:" + "a" * 64),
        ("autonomous", "../../secret"),
        ("autonomous", "sha256:" + "g" * 64),
    ],
)
def test_storage_identity_rejects_path_control(book, snapshot_id):
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.load_snapshot(book, snapshot_id)


def test_load_missing_snapshot_raises_not_found(snapshot_root):
    with pytest.raises(snapshots.SnapshotNotFound):
        snapshots.load_snapshot("autonomous", "sha256:" + "c" * 64)


def test_load_rejects_symlinked_snapshot_file(snapshot_root):
    payload = _sealed_snapshot()
    real_path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])
    real_path.parent.mkdir(parents=True, exist_ok=True)
    real_path.write_bytes(canonical_json_bytes(payload))

    decoy_id = "sha256:" + "d" * 64
    decoy_path = snapshots._snapshot_path("autonomous", decoy_id)
    decoy_path.symlink_to(real_path)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.load_snapshot("autonomous", decoy_id)


def test_load_rejects_tampered_bytes(snapshot_root):
    payload = _sealed_snapshot()
    snapshots.persist_snapshot(payload)
    path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])
    raw = path.read_bytes()
    tampered = raw.replace(b'"COMPLETE"', b'"BLOCKED"', 1)
    assert tampered != raw
    # Bypass persist_snapshot's create-once guard directly to simulate on-disk corruption.
    path.unlink()
    path.write_bytes(tampered)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.load_snapshot("autonomous", payload["snapshot_id"])


# ---------------------------------------------------------------------------
# Step 6: listing and section paging
# ---------------------------------------------------------------------------

def test_list_snapshots_refuses_symlinked_sibling(snapshot_root):
    payload = _sealed_snapshot()
    snapshots.persist_snapshot(payload)
    directory = snapshots.snapshot_dir("autonomous")
    decoy = directory / ("f" * 64 + ".json")
    decoy.symlink_to(directory / (payload["snapshot_id"].split(":", 1)[1] + ".json"))
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")


def test_list_snapshots_clamps_limit_and_sorts_descending(snapshot_root):
    first = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T19:00:00Z", recorded_at="2026-09-15T19:01:00Z",
    )
    second = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z",
    )
    clamped = snapshots.list_snapshots("autonomous", limit=0)
    assert [r["snapshot_id"] for r in clamped] == [second["snapshot_id"]]
    full = snapshots.list_snapshots("autonomous", limit=1000)
    assert [r["snapshot_id"] for r in full] == [second["snapshot_id"], first["snapshot_id"]]


def test_section_page_rejects_boolean_offset_and_limit():
    snap = _sealed_snapshot()
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.section_page(snap, "book_truth", offset=True, limit=10)
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.section_page(snap, "book_truth", offset=0, limit=True)


def test_section_page_rejects_unknown_section_id():
    snap = _sealed_snapshot()
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.section_page(snap, "not_a_section", offset=0, limit=10)


def test_section_page_paginates_and_reports_next_offset():
    rows = [{"i": i} for i in range(5)]
    capture = _capture()
    capture["sections"]["book_truth"]["rows"] = rows
    capture["sections"]["book_truth"]["rows_total"] = 5
    capture["sections"]["book_truth"]["rows_returned"] = 5
    snap = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=capture,
        same_cutoff_prior_snapshot_ids=[],
    )
    page = snapshots.section_page(snap, "book_truth", offset=0, limit=2)
    assert page["rows"] == rows[:2]
    assert page["next_offset"] == 2

    last_page = snapshots.section_page(snap, "book_truth", offset=4, limit=2)
    assert last_page["rows"] == rows[4:5]
    assert last_page["next_offset"] is None


# ---------------------------------------------------------------------------
# read_projection
# ---------------------------------------------------------------------------

def test_read_projection_defaults_to_latest_snapshot_and_full_root(snapshot_root):
    created = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z",
    )
    result = snapshots.read_projection(
        "autonomous", snapshot_id=None, section_id=None, offset=0, limit=10,
    )
    assert result["snapshot"]["snapshot_id"] == created["snapshot_id"]
    assert "sections" not in result["snapshot"]


def test_read_projection_raises_not_found_when_no_snapshot_exists(snapshot_root):
    with pytest.raises(snapshots.SnapshotNotFound):
        snapshots.read_projection(
            "autonomous", snapshot_id=None, section_id=None, offset=0, limit=10,
        )


def test_read_projection_section_page_by_explicit_snapshot_id(snapshot_root):
    created = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z",
    )
    result = snapshots.read_projection(
        "autonomous", snapshot_id=created["snapshot_id"], section_id="book_truth",
        offset=0, limit=10,
    )
    assert result["section"]["section_id"] == "book_truth"


# ---------------------------------------------------------------------------
# Boundary: no caller path/root/url/filename parameters anywhere in the module
# ---------------------------------------------------------------------------

def test_no_public_function_accepts_a_path_or_root_argument():
    import inspect

    for fn in (
        snapshots.compose_snapshot,
        snapshots.create_snapshot,
        snapshots.persist_snapshot,
        snapshots.load_snapshot,
        snapshots.list_snapshots,
        snapshots.latest_snapshot,
        snapshots.section_page,
        snapshots.read_projection,
        snapshots.snapshot_dir,
    ):
        assert not {"path", "root", "url", "filename"} & set(
            inspect.signature(fn).parameters
        )


# ---------------------------------------------------------------------------
# Fix round 1 — independent review repairs
# ---------------------------------------------------------------------------

# Critical 1: same-cutoff/same-generation reuse must survive an existing correction.

# Fixed, pre-cutoff epoch (2026-09-15T19:00:00Z) so account.json's mtime never depends on
# the host wall clock landing before the "2026-09-15T20:00:00Z" decision_cutoff used below.
_PRE_CUTOFF_EPOCH = 1_789_498_800


def _account_receipt(snapshot: dict) -> dict:
    return next(r for r in snapshot["sources"] if r["source_id"] == "book.account")


def test_same_cutoff_same_generation_after_correction_reuses_corrected_snapshot(
    snapshot_root,
):
    account_path = sources._ROOT / "data" / "portfolios" / "autonomous" / "account.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(json.dumps({"cash": 1.0}), encoding="utf-8")
    os.utime(account_path, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))

    original = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert _account_receipt(original)["status"] == "AVAILABLE"

    account_path.write_text(json.dumps({"cash": 2.0}), encoding="utf-8")
    os.utime(account_path, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    corrected = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert corrected["snapshot_id"] != original["snapshot_id"]
    assert corrected["created"] is True
    assert corrected["correction"]["same_cutoff_prior_snapshot_ids"] == [original["snapshot_id"]]
    assert _account_receipt(corrected)["status"] == "AVAILABLE"

    # account.json is unchanged since the correction — a later retry of the same (already
    # corrected) generation must return the corrected snapshot, not mint a third one.
    retry = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:20:00Z",
    )
    assert retry["snapshot_id"] == corrected["snapshot_id"]
    assert retry["created"] is False
    assert _account_receipt(retry)["status"] == "AVAILABLE"
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 2


# Important 2: create-once durability — no poisoned files, no silent short writes.

def test_create_once_completes_after_forced_short_write(snapshot_root, monkeypatch):
    payload = _sealed_snapshot(generation="sha256:" + "1" * 64)
    encoded = canonical_json_bytes(payload)
    real_write = os.write
    calls = {"n": 0}

    def short_write(fd, data):
        calls["n"] += 1
        if calls["n"] == 1 and len(data) > 1:
            return real_write(fd, data[:1])
        return real_write(fd, data)

    monkeypatch.setattr(snapshots.os, "write", short_write)
    result = snapshots.persist_snapshot(payload)
    assert result["created"] is True
    assert Path(result["path"]).read_bytes() == encoded
    assert calls["n"] > 1


def test_create_once_cleans_up_poisoned_file_after_write_failure(snapshot_root, monkeypatch):
    payload = _sealed_snapshot(generation="sha256:" + "2" * 64)
    real_write = os.write

    def failing_write(fd, data):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(snapshots.os, "write", failing_write)
    with pytest.raises(OSError):
        snapshots.persist_snapshot(payload)

    path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])
    assert not path.exists()

    monkeypatch.setattr(snapshots.os, "write", real_write)
    result = snapshots.persist_snapshot(payload)
    assert result["created"] is True


def test_create_once_cleans_up_poisoned_file_after_fsync_failure(snapshot_root, monkeypatch):
    payload = _sealed_snapshot(generation="sha256:" + "3" * 64)
    real_fsync = os.fsync
    calls = {"n": 0}

    def failing_fsync(fd):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(snapshots.os, "fsync", failing_fsync)
    with pytest.raises(OSError):
        snapshots.persist_snapshot(payload)

    path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])
    assert not path.exists()

    monkeypatch.setattr(snapshots.os, "fsync", real_fsync)
    result = snapshots.persist_snapshot(payload)
    assert result["created"] is True


# Important 3(a): section-page byte ceiling.

def test_section_page_response_ceiling_is_enforced():
    rows = [{"blob": "x" * 2000} for _ in range(100)]
    capture = _capture()
    capture["sections"]["book_truth"]["rows"] = rows
    capture["sections"]["book_truth"]["rows_total"] = len(rows)
    capture["sections"]["book_truth"]["rows_returned"] = len(rows)
    snap = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=capture,
        same_cutoff_prior_snapshot_ids=[],
    )
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.section_page(snap, "book_truth", offset=0, limit=100)


# Important 3(b): noncanonical-but-digest-valid persisted bytes must still be rejected —
# this must depend on the canonical-byte comparison, not the digest recomputation.

def test_load_rejects_noncanonical_but_digest_valid_bytes(snapshot_root):
    payload = _sealed_snapshot(generation="sha256:" + "4" * 64)
    snapshots.persist_snapshot(payload)
    path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])

    pretty = json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")
    assert pretty != path.read_bytes()
    # verify_snapshot would recompute the same digest from this re-serialization; only the
    # canonical-bytes comparison catches the noncanonical on-disk representation.
    c.verify_snapshot(json.loads(pretty))

    path.unlink()
    path.write_bytes(pretty)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.load_snapshot("autonomous", payload["snapshot_id"])


# Important 3(c): section-level structured gaps must be sorted and sealed exactly like root gaps.

def test_section_gaps_are_sorted_and_sealed_like_root_gaps():
    capture = _capture()
    gap_z = {"code": "Z", "source_id": "z", "section_id": "book_truth", "owner": None, "detail": None}
    gap_a = {"code": "A", "source_id": "a", "section_id": "book_truth", "owner": None, "detail": None}
    capture["sections"]["book_truth"]["gaps"] = [gap_z, gap_a]
    result = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=capture,
        same_cutoff_prior_snapshot_ids=[],
    )
    assert result["sections"]["book_truth"]["gaps"] == [
        canonical_json_bytes(gap_a).decode("ascii"),
        canonical_json_bytes(gap_z).decode("ascii"),
    ]


# ---------------------------------------------------------------------------
# Task 8 repair R1 — changed evidence always mints a correction, never a reuse
# ---------------------------------------------------------------------------

def _seed_account(cash: float = 1.0) -> Path:
    account_path = sources._ROOT / "data" / "portfolios" / "autonomous" / "account.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(json.dumps({"cash": cash, "positions": {}}), encoding="utf-8")
    os.utime(account_path, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    return account_path


def _artifacts() -> list:
    return sorted(p.name for p in snapshots.snapshot_dir("autonomous").glob("*.json"))


def test_changed_malformed_evidence_at_one_cutoff_mints_a_correction(snapshot_root):
    """Two different malformed bodies are two different states of the world. Reusing the
    first snapshot for the second would report stale evidence as current."""
    _seed_account()
    betas = sources._V / "site" / "factor_betas.json"
    betas.parent.mkdir(parents=True, exist_ok=True)

    def compose(body: bytes, recorded_at: str) -> dict:
        betas.write_bytes(body)
        os.utime(betas, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
        return snapshots.create_snapshot(
            "autonomous",
            decision_cutoff="2026-09-15T20:00:00Z",
            recorded_at=recorded_at,
        )

    original = compose(b"{broken-one", "2026-09-15T20:01:00Z")
    assert original["created"] is True

    corrected = compose(b"{broken-two", "2026-09-15T20:10:00Z")
    assert corrected["created"] is True
    assert corrected["snapshot_id"] != original["snapshot_id"]
    assert corrected["correction"]["status"] == "CORRECTED"
    assert corrected["correction"]["same_cutoff_prior_snapshot_ids"] == [original["snapshot_id"]]

    # The original bytes are preserved, not replaced: corrections are additive.
    assert len(_artifacts()) == 2
    preserved = snapshots.load_snapshot("autonomous", original["snapshot_id"])
    assert preserved["snapshot_id"] == original["snapshot_id"]

    # Identical malformed bytes at the same cutoff stay idempotent.
    retry = compose(b"{broken-two", "2026-09-15T20:20:00Z")
    assert retry["created"] is False
    assert retry["snapshot_id"] == corrected["snapshot_id"]
    assert len(_artifacts()) == 2


def test_optional_source_going_absent_to_oversize_is_not_reusable_truth(snapshot_root):
    _seed_account()
    original = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert original["created"] is True

    pending = sources._ROOT / "data" / "portfolios" / "autonomous" / "pending_target.json"
    pending.write_bytes(b"x" * (c.MAX_SOURCE_BYTES + 1))
    os.utime(pending, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))

    corrected = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert corrected["created"] is True
    assert corrected["snapshot_id"] != original["snapshot_id"]
    assert corrected["correction"]["same_cutoff_prior_snapshot_ids"] == [original["snapshot_id"]]
    assert len(_artifacts()) == 2


# ---------------------------------------------------------------------------
# Task 8 repair 2 — first-party clock/status are generation truth (Finding A)
# ---------------------------------------------------------------------------

_FUTURE_EPOCH = 1_789_502_700  # 2026-09-15T20:05:00Z — strictly after the fixture cutoff


def test_account_bytes_crossing_the_cutoff_at_unchanged_content_mints_a_correction(snapshot_root):
    """Same account bytes, only the clock moved: a same-cutoff retry after the file crosses
    the cutoff must mint a new, CORRECTED snapshot, never reuse the eligible one."""
    account_path = _seed_account()
    original = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert original["created"] is True

    os.utime(account_path, (_FUTURE_EPOCH, _FUTURE_EPOCH))
    corrected = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert corrected["created"] is True
    assert corrected["snapshot_id"] != original["snapshot_id"]
    assert corrected["correction"]["status"] == "CORRECTED"
    assert corrected["correction"]["same_cutoff_prior_snapshot_ids"] == [original["snapshot_id"]]
    assert len(_artifacts()) == 2

    # The original bytes are preserved, not replaced: corrections are additive.
    preserved = snapshots.load_snapshot("autonomous", original["snapshot_id"])
    assert preserved["snapshot_id"] == original["snapshot_id"]


def test_account_bytes_returning_from_future_to_eligible_mints_a_correction(snapshot_root):
    """The reverse direction: a file first observed future, then observed eligible at an
    unchanged cutoff (e.g. a corrected mtime), must equally mint a new correction."""
    account_path = _seed_account()
    os.utime(account_path, (_FUTURE_EPOCH, _FUTURE_EPOCH))
    original = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert original["created"] is True

    os.utime(account_path, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    corrected = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert corrected["created"] is True
    assert corrected["snapshot_id"] != original["snapshot_id"]
    assert corrected["correction"]["status"] == "CORRECTED"
    assert len(_artifacts()) == 2


def test_settlement_directory_clock_alone_reuses_the_same_generation(snapshot_root):
    """Task 8 repair 3, finding A: the settlement manifest's known_at/generation are now
    bound to each entry's own mtime, never the directory's — so a directory mtime touch
    with no entry change (e.g. an unrelated sibling write) must reuse the same snapshot,
    not spuriously mint a correction."""
    _seed_account()
    settlement_dir = (
        sources._ROOT / "data" / "portfolios" / "autonomous" / "settlement_receipts"
    )
    settlement_dir.mkdir(parents=True, exist_ok=True)
    entry = settlement_dir / "r001.json"
    entry.write_text("{}", encoding="utf-8")
    os.utime(entry, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    os.utime(settlement_dir, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))

    original = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert original["created"] is True

    os.utime(settlement_dir, (_FUTURE_EPOCH, _FUTURE_EPOCH))
    retry = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert retry["created"] is False
    assert retry["snapshot_id"] == original["snapshot_id"]
    assert len(_artifacts()) == 1


def test_settlement_new_future_receipt_has_zero_effect_and_reuses_the_snapshot(snapshot_root):
    """Task 8 repair 4, finding A (principal reproduction): a settlement receipt landing
    *after* an already-composed cutoff must have zero effect on that cutoff's snapshot — a
    same-cutoff recompose must reuse the exact prior snapshot, not mint a spurious
    correction from evidence that did not exist at the cutoff."""
    _seed_account()
    settlement_dir = (
        sources._ROOT / "data" / "portfolios" / "autonomous" / "settlement_receipts"
    )
    settlement_dir.mkdir(parents=True, exist_ok=True)
    entry = settlement_dir / "r001.json"
    entry.write_text("{}", encoding="utf-8")
    os.utime(entry, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    os.utime(settlement_dir, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))

    original = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert original["created"] is True

    future_entry = settlement_dir / "r002.json"
    future_entry.write_text("{}", encoding="utf-8")
    os.utime(future_entry, (_FUTURE_EPOCH, _FUTURE_EPOCH))
    os.utime(settlement_dir, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    recomposed = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert recomposed["created"] is False
    assert recomposed["snapshot_id"] == original["snapshot_id"]
    assert len(_artifacts()) == 1


def test_settlement_eligible_mtime_change_at_same_cutoff_mints_a_correction(snapshot_root):
    """Task 8 repair 4, finding A (second reproduction): moving an *eligible* receipt's own
    mtime (both old and new values still <= cutoff) is a real change to the evidence this
    receipt attests to and must mint a correction — the settlement generation must hash
    (name, mtime_ns), not names alone."""
    _seed_account()
    settlement_dir = (
        sources._ROOT / "data" / "portfolios" / "autonomous" / "settlement_receipts"
    )
    settlement_dir.mkdir(parents=True, exist_ok=True)
    entry = settlement_dir / "r001.json"
    entry.write_text("{}", encoding="utf-8")
    os.utime(entry, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    os.utime(settlement_dir, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))

    original = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert original["created"] is True

    later_still_eligible = _PRE_CUTOFF_EPOCH + 1_800  # +30m, still well before the cutoff
    os.utime(entry, (later_still_eligible, later_still_eligible))
    os.utime(settlement_dir, (later_still_eligible, later_still_eligible))
    corrected = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:40:00Z",
    )
    assert corrected["created"] is True
    assert corrected["snapshot_id"] != original["snapshot_id"]
    assert corrected["correction"]["status"] == "CORRECTED"
    assert len(_artifacts()) == 2


def test_account_bytes_crossing_the_cutoff_at_an_unchanged_mtime_reuses_exactly(snapshot_root):
    """Determinism guard at the create_snapshot level: an unchanged future state, retried at
    the same cutoff with no byte or clock change, must reuse the same snapshot — no
    wall-clock or random identity was smuggled into the generation."""
    account_path = _seed_account()
    os.utime(account_path, (_FUTURE_EPOCH, _FUTURE_EPOCH))
    first = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert first["created"] is True

    second = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:20:00Z",
    )
    assert second["created"] is False
    assert second["snapshot_id"] == first["snapshot_id"]
    assert len(_artifacts()) == 1


# ---------------------------------------------------------------------------
# Task 8 repair R2 — a non-finite number degrades one source, not the vertical
# ---------------------------------------------------------------------------

def test_non_finite_number_in_a_source_still_seals_a_snapshot(snapshot_root):
    _seed_account()
    betas = sources._V / "site" / "factor_betas.json"
    betas.parent.mkdir(parents=True, exist_ok=True)
    betas.write_text(
        '{"schema":"factor_betas.v1","known_at":"2026-09-15T19:00:00Z","betas":{"AAPL":NaN}}',
        encoding="utf-8",
    )
    os.utime(betas, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))

    result = snapshots.create_snapshot(
        "autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert result["snapshot_id"].startswith("sha256:")
    receipt = next(r for r in result["sources"] if r["source_id"] == "macro.factor_betas")
    assert receipt["status"] == "MALFORMED"
    assert result["state"] in ("PARTIAL", "BLOCKED")
    c.verify_snapshot(snapshots.load_snapshot("autonomous", result["snapshot_id"]))


# ---------------------------------------------------------------------------
# Task 8 repair R7 — the sibling read path is bounded and fails closed
# ---------------------------------------------------------------------------

def _decoy_path(directory: Path, char: str = "f") -> Path:
    return directory / (char * 64 + ".json")


def _read_request_recorder(monkeypatch) -> list:
    """Record every ``os.read`` length the snapshot store asks for, so a test can prove the
    ceiling is enforced *before* allocation rather than after a full read."""
    requested: list = []
    real_read = snapshots.os.read

    def recording_read(fd, n):
        requested.append(n)
        return real_read(fd, n)

    monkeypatch.setattr(snapshots.os, "read", recording_read)
    return requested


def test_oversize_snapshot_sibling_is_refused_before_it_is_read(snapshot_root, monkeypatch):
    snapshots.persist_snapshot(_sealed_snapshot())
    decoy = _decoy_path(snapshots.snapshot_dir("autonomous"))
    decoy.write_bytes(b"{" + b"x" * c.MAX_SNAPSHOT_BYTES)
    requested = _read_request_recorder(monkeypatch)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.latest_snapshot("autonomous")
    assert max(requested, default=0) <= c.MAX_SNAPSHOT_BYTES


def test_sparse_snapshot_sibling_is_refused_without_allocating_its_size(snapshot_root, monkeypatch):
    """A sparse file advertises an enormous ``st_size`` while occupying almost no blocks —
    the ceiling must be enforced on the advertised size, before any allocation."""
    snapshots.persist_snapshot(_sealed_snapshot())
    decoy = _decoy_path(snapshots.snapshot_dir("autonomous"), "e")
    with open(decoy, "wb") as handle:
        handle.truncate(1 << 30)
    assert decoy.stat().st_size == 1 << 30
    requested = _read_request_recorder(monkeypatch)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")
    assert max(requested, default=0) <= c.MAX_SNAPSHOT_BYTES


def test_corrupt_regular_sibling_is_never_silently_hidden_by_list_or_latest(snapshot_root):
    snapshots.persist_snapshot(_sealed_snapshot())
    decoy = _decoy_path(snapshots.snapshot_dir("autonomous"), "b")
    decoy.write_bytes(b'{"schema": "not-a-snapshot"}')
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.latest_snapshot("autonomous")


# ---------------------------------------------------------------------------
# Task 8 repair 3 — structural path confinement (CodeQL py/path-injection)
# ---------------------------------------------------------------------------

def test_snapshot_dir_uses_the_closed_literal_never_the_validated_book_variable():
    """Behaviorally, joining ``book`` or ``_BOOK_ID`` produces the same path once the
    equality check above has passed — so this must be a structural check, not a runtime
    one, to actually catch a regression back to interpolating the validated variable."""
    import inspect

    source = inspect.getsource(snapshots.snapshot_dir)
    assert "/ _BOOK_ID" in source
    assert "/ book" not in source
    assert snapshots.snapshot_dir("autonomous").name == snapshots._BOOK_ID


def test_load_and_persist_reject_traversal_and_absolute_snapshot_ids(snapshot_root):
    payload = _sealed_snapshot()
    snapshots.persist_snapshot(payload)
    for bad_id in (
        "../../secret",
        "/etc/passwd",
        "sha256:" + "a" * 63 + "/",
        "sha256:" + "a" * 62 + "/x",
        "sha256:" + "A" * 64,  # uppercase hex is not the closed lowercase form
    ):
        with pytest.raises(snapshots.SnapshotInvalidRequest):
            snapshots.load_snapshot("autonomous", bad_id)


def test_persist_rejects_hostile_snapshot_id_before_any_filesystem_write(snapshot_root):
    """Task 8 repair 5, I2: a caller-supplied ``snapshot_id`` carrying a traversal/absolute/
    hostile string must never reach the create sink — it is rejected by contract validation
    (malformed shape) or the digest-equality check (well-formed but wrong), and no file is
    ever created under the snapshot directory either way."""
    base = _sealed_snapshot()
    for bad_id in (
        "../../secret",
        "/etc/passwd",
        "sha256:" + "a" * 63 + "/",
        "sha256:" + "a" * 62 + "/x",
        "sha256:" + "A" * 64,
        "sha256:" + "f" * 64,  # well-formed shape, but does not match the recomputed digest
    ):
        tampered = {**base, "snapshot_id": bad_id}
        with pytest.raises(c.DecisionSnapshotContractError):
            snapshots.persist_snapshot(tampered)
    directory = snapshots.snapshot_dir("autonomous")
    assert not directory.exists() or list(directory.glob("*.json")) == []


def test_create_once_sink_only_ever_receives_the_sanitized_basename():
    """Structural regression for Task 8 repair 5, I2: ``_create_once`` must sanitize
    ``filename`` through ``_sanitize_snapshot_filename`` (a basename-based barrier) before
    either the ``os.open`` create or the ``os.unlink`` cleanup — never pass the parameter
    straight through. Fails if a future edit restores a direct caller-string flow into
    either sink."""
    import inspect

    source = inspect.getsource(snapshots._create_once)
    sanitize_line = next(
        i for i, line in enumerate(source.splitlines())
        if "_sanitize_snapshot_filename(filename)" in line
    )
    open_line = next(
        i for i, line in enumerate(source.splitlines()) if "os.open(filename" in line
    )
    unlink_line = next(
        i for i, line in enumerate(source.splitlines()) if "os.unlink(filename" in line
    )
    assert sanitize_line < open_line < unlink_line

    sanitizer_source = inspect.getsource(snapshots._sanitize_snapshot_filename)
    assert "os.path.basename(filename)" in sanitizer_source
    assert "_SNAPSHOT_FILENAME_RE.fullmatch(sanitized)" in sanitizer_source


def test_persist_snapshot_derives_filename_from_a_locally_recomputed_digest():
    """Task 8 repair 5, I2: ``persist_snapshot`` must not read ``snapshot["snapshot_id"]``
    straight off the caller's mapping to build the filename — even though
    ``verify_snapshot`` already proves the two equal at runtime, CodeQL's default taint
    model does not credit that proof, so the filename must trace only to a digest this
    function recomputes itself."""
    import inspect

    source = inspect.getsource(snapshots.persist_snapshot)
    assert "c.content_digest(" in source
    assert '_snapshot_filename(recomputed_id)' in source
    assert '_snapshot_filename(snapshot["snapshot_id"])' not in source
    assert "_snapshot_filename(snapshot_id)" not in source


def test_sanitize_snapshot_filename_rejects_anything_off_the_closed_form():
    for hostile in (
        "../escape.json",
        "/etc/passwd",
        "a" * 63 + ".json",  # 63 hex chars, not 64
        "a" * 64 + ".JSON",
        "a" * 64,  # missing .json suffix
        "a" * 64 + ".json/../x",
    ):
        with pytest.raises(snapshots.SnapshotCorrupt):
            snapshots._sanitize_snapshot_filename(hostile)
    valid = "a" * 64 + ".json"
    assert snapshots._sanitize_snapshot_filename(valid) == valid


def test_snapshot_dir_symlinked_root_is_rejected_and_nothing_outside_is_touched(
    snapshot_root, tmp_path,
):
    """A storage root replaced by a symlink to an arbitrary directory must never be
    followed for reads, scans, or writes — and nothing in the symlink target may be
    touched."""
    outside = tmp_path / "outside"
    outside.mkdir()
    leaf = snapshots.snapshot_dir("autonomous")
    leaf.parent.mkdir(parents=True, exist_ok=True)
    leaf.symlink_to(outside, target_is_directory=True)

    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.load_snapshot("autonomous", "sha256:" + "a" * 64)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.persist_snapshot(_sealed_snapshot())

    assert list(outside.iterdir()) == []


def test_parent_component_symlink_cannot_escape_the_snapshot_root(snapshot_root, tmp_path):
    """Task 8 repair 4, finding B (principal reproduction): a symlink swapped in for a
    *parent* component of the snapshot path — not the leaf — must be refused exactly like a
    symlinked leaf. Before the fix, ``_open_snapshot_directory`` opened the whole path by
    string, following any symlinked parent; only the leaf's own lstat was checked."""
    outside = tmp_path / "outside"
    (outside / "autonomous").mkdir(parents=True)
    (outside / "autonomous" / "planted.json").write_text("{}", encoding="utf-8")

    decision_snapshots_dir = snapshot_root / "data" / "shadow" / "decision_snapshots"
    decision_snapshots_dir.parent.mkdir(parents=True, exist_ok=True)
    decision_snapshots_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.load_snapshot("autonomous", "sha256:" + "a" * 64)
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.persist_snapshot(_sealed_snapshot())

    # Nothing under the symlink target was read, written, or listed through.
    assert sorted(p.name for p in (outside / "autonomous").iterdir()) == ["planted.json"]
    assert (outside / "autonomous" / "planted.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("component_index", [0, 1, 2])
def test_every_intermediate_path_component_symlink_is_refused(
    snapshot_root, tmp_path, component_index,
):
    """Every component between ``_ROOT`` and the leaf — not just ``decision_snapshots`` —
    must be walked descriptor-relative with O_NOFOLLOW. Parametrized over ``data``,
    ``data/shadow``, and ``data/shadow/decision_snapshots`` each swapped for a symlink."""
    components = ["data", "shadow", "decision_snapshots"]
    outside = tmp_path / f"outside_{component_index}"
    outside.mkdir()

    target_path = snapshot_root
    for name in components[:component_index]:
        target_path = target_path / name
        target_path.mkdir(exist_ok=True)
    symlinked_component = target_path / components[component_index]
    symlinked_component.symlink_to(outside, target_is_directory=True)

    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.persist_snapshot(_sealed_snapshot())
    assert list(outside.iterdir()) == []


def test_snapshot_dir_non_directory_root_is_rejected(snapshot_root):
    """A storage root that exists as a plain file (not a directory, not a symlink) must
    fail closed the same way a symlinked root does."""
    leaf = snapshots.snapshot_dir("autonomous")
    leaf.parent.mkdir(parents=True, exist_ok=True)
    leaf.write_text("not a directory", encoding="utf-8")

    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.list_snapshots("autonomous")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.persist_snapshot(_sealed_snapshot())


def test_exact_id_read_path_never_joins_a_caller_string_into_a_filesystem_call():
    """Structural regression guard: the exact-ID load path must resolve its target only by
    enumerating the fixed directory and matching a filesystem-sourced entry name — never by
    handing a caller-derived Path straight to lstat/open. Fails if a future edit reintroduces
    ``directory / snapshot_id``-style construction ahead of a filesystem call in
    ``load_snapshot``."""
    import inspect

    source = inspect.getsource(snapshots.load_snapshot)
    assert "_snapshot_path(" not in source
    assert "_read_regular_file_bytes(" not in source
    assert "_find_regular_entry(" in source

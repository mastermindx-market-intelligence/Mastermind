"""Real temporary-filesystem proof for immutable snapshot storage, not live proof."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib import import_module, util
import json
from pathlib import Path

import pytest
from test_decision_snapshot_contracts import unsealed


def snapshots():
    assert util.find_spec("portfolio.decision_snapshot") is not None, "missing immutable snapshot store"
    return import_module("portfolio.decision_snapshot")


def capture():
    c = import_module("portfolio.decision_snapshot_contracts")
    p = unsealed(); sections = deepcopy(p["sections"]); gaps = []
    for name in c.SECTION_IDS:
        if name in sections:
            continue
        gap = {"code": "MISSING", "source_id": "fixture." + name, "owner": "fixture", "detail": "fixture has no such evidence"}
        sections[name] = {"schema": c.SECTION_SCHEMA, "section_id": name, "coverage_state": "UNKNOWN",
                          "source_ids": [], "rows_total": 0, "rows_returned": 0, "omitted_rows": 0, "rows": [], "gaps": [gap]}
        gaps.append(gap)
    return {"sources": deepcopy(p["sources"]), "sections": sections, "gaps": gaps}


def sealed(*, prior=(), generation="a", recorded_at="2026-09-15T20:01:00Z"):
    bundle = capture(); bundle["sources"][0]["correction_generation"] = "sha256:" + generation * 64
    return snapshots().compose_snapshot("autonomous", decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at=recorded_at, capture=bundle, same_cutoff_prior_snapshot_ids=list(prior))


@pytest.fixture
def store(tmp_path, monkeypatch):
    m = snapshots(); monkeypatch.setattr(m, "_ROOT", tmp_path)
    return m


def test_same_capture_and_clocks_are_deterministic_and_complete_domain_inventory():
    m = snapshots(); first = sealed(); assert first == sealed()
    assert first["state"] == "PARTIAL"
    assert len(first["sections"]) == 12
    assert first["summary"]["domains_partial"] == 11
    bad = capture(); bad["sections"].pop("risk_truth")
    with pytest.raises(m.SnapshotInvalidRequest):
        m.compose_snapshot("autonomous", decision_cutoff="2026-09-15T20:00:00Z", recorded_at="2026-09-15T20:01:00Z", capture=bad, same_cutoff_prior_snapshot_ids=[])


def test_persist_create_once_exact_retry_is_noop_and_permissions_are_private(store):
    p = sealed(); first = store.persist_snapshot(p); path = Path(first["path"]); before = path.read_bytes()
    second = store.persist_snapshot(p)
    assert first["created"] is True and second["created"] is False
    assert path.read_bytes() == before
    assert path.stat().st_mode & 0o777 == 0o600
    assert store.load_snapshot("autonomous", p["snapshot_id"]) == p
    assert not list(path.parent.glob("*.tmp"))


def test_existing_wrong_bytes_freeze_without_overwrite(store):
    p = sealed(); path = store._snapshot_path("autonomous", p["snapshot_id"])
    path.parent.mkdir(parents=True); path.write_bytes(b"{}")
    with pytest.raises(store.SnapshotCorrupt): store.persist_snapshot(p)
    assert path.read_bytes() == b"{}"


def test_corruption_is_detected_on_load_not_just_when_persisting(store):
    p = sealed(); r = store.persist_snapshot(p); path = Path(r["path"])
    modified = deepcopy(p); modified["sections"]["book_truth"]["rows"][0]["cash"] = 1
    path.write_text(json.dumps(modified))
    with pytest.raises(store.SnapshotCorrupt): store.load_snapshot("autonomous", p["snapshot_id"])


def test_correction_keeps_predecessor_byte_identical(store):
    original = sealed(); first = store.persist_snapshot(original); before = Path(first["path"]).read_bytes()
    corrected = sealed(prior=[original["snapshot_id"]], generation="b", recorded_at="2026-09-15T20:10:00Z")
    store.persist_snapshot(corrected)
    assert corrected["state"] == "CORRECTED_GENERATION_AVAILABLE"
    assert corrected["coverage_state"] == "PARTIAL"
    assert Path(first["path"]).read_bytes() == before
    assert store.latest_snapshot("autonomous")["snapshot_id"] == corrected["snapshot_id"]


@pytest.mark.parametrize("book,identity", [("../autonomous", "sha256:" + "a" * 64), ("AUTONOMOUS", "sha256:" + "a" * 64), ("autonomous", "../../secret"), ("autonomous", "sha256:" + "g" * 64)])
def test_storage_identity_refuses_path_control(store, book, identity):
    with pytest.raises(store.SnapshotInvalidRequest): store.load_snapshot(book, identity)


def test_missing_read_creates_no_directories(store, tmp_path):
    with pytest.raises(store.SnapshotNotFound): store.load_snapshot("autonomous", "sha256:" + "a" * 64)
    assert not (tmp_path / "data").exists()
    assert store.list_snapshots("autonomous") == []
    assert store.latest_snapshot("autonomous") is None
    assert not (tmp_path / "data").exists()


def test_symlink_snapshot_never_reads_or_overwrites_target(store, tmp_path):
    p = sealed(); path = store._snapshot_path("autonomous", p["snapshot_id"])
    path.parent.mkdir(parents=True); target = tmp_path / "do-not-touch"; target.write_bytes(b"private")
    path.symlink_to(target)
    with pytest.raises(store.SnapshotCorrupt): store.load_snapshot("autonomous", p["snapshot_id"])
    with pytest.raises(store.SnapshotCorrupt): store.persist_snapshot(p)
    assert target.read_bytes() == b"private"


def test_symlink_parent_is_refused(store, tmp_path):
    (tmp_path / "data").mkdir(); outside = tmp_path / "outside"; outside.mkdir()
    (tmp_path / "data" / "shadow").symlink_to(outside, target_is_directory=True)
    with pytest.raises(store.SnapshotCorrupt): store.persist_snapshot(sealed())
    assert list(outside.iterdir()) == []


def test_parallel_same_content_has_one_creator_and_no_partial_records(store):
    p = sealed()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: store.persist_snapshot(p), range(12)))
    assert sum(r["created"] for r in results) == 1
    assert len(store.list_snapshots("autonomous")) == 1
    assert store.load_snapshot("autonomous", p["snapshot_id"]) == p


@pytest.mark.parametrize("offset,limit", [(True, 1), (-1, 1), (0, True), (0, 0), (0, 101), (0.0, 10)])
def test_section_paging_rejects_noninteger_or_unbounded_requests(store, offset, limit):
    with pytest.raises(store.SnapshotInvalidRequest): store.section_page(sealed(), "book_truth", offset=offset, limit=limit)


def test_section_page_verifies_digest_and_handles_end_of_rows(store):
    p = sealed(); page = store.section_page(p, "book_truth", offset=0, limit=1)
    assert len(page["rows"]) == 1 and page["next_offset"] is None
    assert store.section_page(p, "book_truth", offset=1, limit=1)["rows"] == []
    p["sections"]["book_truth"]["rows"][0]["cash"] = 0
    with pytest.raises(store.SnapshotCorrupt): store.section_page(p, "book_truth", offset=0, limit=1)


def test_listing_verifies_all_manifest_rows_and_has_no_latest_file(store):
    store.persist_snapshot(sealed()); rows = store.list_snapshots("autonomous", limit=10)
    assert len(rows) == 1 and "sections" not in rows[0]
    assert not (store.snapshot_dir("autonomous") / "latest.json").exists()
    for value in [True, 0, 101, "10"]:
        with pytest.raises(store.SnapshotInvalidRequest): store.list_snapshots("autonomous", limit=value)


def test_record_disappearing_during_manifest_scan_is_not_an_empty_store(store, monkeypatch):
    store.persist_snapshot(sealed())
    def missing(*args):
        raise store.SnapshotNotFound("record disappeared after enumeration")
    monkeypatch.setattr(store, "_read_at", missing)
    with pytest.raises(store.SnapshotCorrupt):
        store.list_snapshots("autonomous")


def test_directory_sync_failure_preserves_uncertain_publication_identity(store, monkeypatch):
    import os
    import stat
    p = sealed(); original = os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected directory sync failure")
        return original(fd)
    with monkeypatch.context() as patch:
        patch.setattr(store.os, "fsync", fail_directory)
        with pytest.raises(store.SnapshotWriteUncertain, match=p["snapshot_id"]):
            store.persist_snapshot(p)
    assert store.load_snapshot("autonomous", p["snapshot_id"]) == p


def test_correction_cannot_invent_a_predecessor_or_create_an_empty_store(store, tmp_path):
    p = sealed(prior=["sha256:" + "f" * 64], generation="b")
    with pytest.raises(store.SnapshotInvalidRequest, match="predecessor"):
        store.persist_snapshot(p)
    assert not (tmp_path / "data").exists()


def test_correction_predecessor_must_have_the_same_decision_cutoff(store):
    original = sealed(); store.persist_snapshot(original)
    p = store.compose_snapshot("autonomous", decision_cutoff="2026-09-16T20:00:00Z",
        recorded_at="2026-09-16T20:01:00Z", capture=capture(),
        same_cutoff_prior_snapshot_ids=[original["snapshot_id"]])
    with pytest.raises(store.SnapshotInvalidRequest, match="cutoff"):
        store.persist_snapshot(p)
    assert len(store.list_snapshots("autonomous")) == 1

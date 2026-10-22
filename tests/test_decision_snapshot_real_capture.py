"""Real-capture journey tests for the byte-bounded Decision Snapshot.

These tests run ONLY against the orchestrator-provided read-only capture bundle located
through the ``PBR_CAPTURE_DIR`` environment variable (skipped when it is unset). The
capture is never written to: every file is copied into ``tmp_path``, verified against the
bundle's own ``MANIFEST.json`` sha256 before use, re-verified after each test, and staged
with the manifest's ``host_mtime_utc`` so the first-party file-mtime clock law sees the
production wall clock, not the local checkout's.

Repository rule honoured here: no byte, row, field value, ticker, or memo from the capture
is written into any repository file — this file only compares digests and statuses at run
time.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane.wake_events import canonical_json_bytes
from portfolio import decision_snapshot as snapshots
from portfolio import decision_snapshot_contracts as c
from portfolio import decision_snapshot_sources as sources
from portfolio import registry


def _capture_dir() -> Path | None:
    raw = os.environ.get("PBR_CAPTURE_DIR")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


pytestmark = pytest.mark.skipif(
    _capture_dir() is None,
    reason=(
        "PBR_CAPTURE_DIR is not set: the read-only production capture bundle is not "
        "available, so the real-capture journey tests cannot run"
    ),
)

# The capture instants recorded in the packet / MANIFEST (verify against MANIFEST below).
_CAPTURE_CUTOFF = "2026-10-22T07:35:49Z"   # host_sha256_before_at
_CAPTURE_RECORDED = "2026-10-22T07:36:57Z"  # host_sha256_after_at
_HISTORICAL_CUTOFF = "2026-10-02T23:15:00Z"

_AUTONOMOUS_SOURCES = (
    "book.decisions",
    "book.fills",
    "book.pending_target",
    "book.positions_ledger",
)


def _epoch(utc: str) -> int:
    parsed = datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _manifest_entry(manifest: dict, local_suffix: str) -> dict:
    matches = [
        entry for entry in manifest["files"]
        if entry["local_path"].endswith(local_suffix)
    ]
    assert len(matches) == 1, local_suffix
    return matches[0]


def _verify_capture_untouched(capture_dir: Path, manifest: dict) -> None:
    """Every retained capture file's sha256 is unchanged — the bundle stays read-only."""
    for entry in manifest["files"]:
        source = capture_dir / entry["local_path"]
        if not source.is_file():
            continue  # listed in the manifest but not retained in this local bundle
        raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["local_path"]


def _stage_capture_files(repo: Path, capture_dir: Path, manifest: dict) -> dict:
    """Copy each retained MANIFEST file into the module's staged repo layout, verifying
    sha256 and byte count against the manifest and pinning its mtime to
    ``host_mtime_utc``.

    ``host/<book>/<file>`` mirrors production ``data/portfolios/<book>/<file>`` (the
    layout ``portfolio.registry.data_dir`` owns); ``host/brain/runs/...`` mirrors
    ``data/brain/runs/...``. Nothing is ever written back into ``capture_dir``. A
    manifest entry whose local copy is not retained in the bundle is recorded as absent
    rather than staged.
    """
    staged: dict[str, Path] = {}
    for entry in manifest["files"]:
        source = capture_dir / entry["local_path"]
        if not source.is_file():
            continue  # listed in the manifest but not retained in this local bundle
        raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["local_path"]
        assert len(raw) == entry["bytes"], entry["local_path"]
        relative = Path(*Path(entry["local_path"]).parts[1:])  # drop the leading "host/"
        destination = repo / "data" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        mtime = _epoch(entry["host_mtime_utc"])
        os.utime(destination, (mtime, mtime))
        staged[entry["local_path"]] = destination
    return staged


@pytest.fixture
def capture_root(tmp_path, monkeypatch):
    capture_dir = _capture_dir()
    assert capture_dir is not None  # guaranteed by pytestmark
    if not capture_dir.is_dir():
        pytest.fail(f"PBR_CAPTURE_DIR={capture_dir} is not a directory")
    manifest = json.loads(
        (capture_dir / "MANIFEST.json").read_text(encoding="utf-8")
    )
    # The cutoffs this module asserts are the manifest's own recorded instants.
    assert manifest["host_sha256_before_at"] == _CAPTURE_CUTOFF
    assert manifest["host_sha256_after_at"] == _CAPTURE_RECORDED

    repo = tmp_path / "repo"
    macro = tmp_path / "macro"  # empty: no consumed Macro context is part of this capture
    storage = tmp_path / "storage"
    for directory in (repo, macro, storage):
        directory.mkdir()
    staged = _stage_capture_files(repo, capture_dir, manifest)
    monkeypatch.setattr(sources, "_ROOT", repo)
    monkeypatch.setattr(sources, "_V", macro)
    monkeypatch.setattr(snapshots, "_ROOT", storage)
    try:
        yield {
            "capture_dir": capture_dir,
            "manifest": manifest,
            "repo": repo,
            "storage": storage,
            "staged": staged,
        }
    finally:
        _verify_capture_untouched(capture_dir, manifest)


def _receipts(snapshot: dict) -> dict:
    return {r["source_id"]: r for r in snapshot["sources"]}


# ---------------------------------------------------------------------------
# Capture-time composition: the real autonomous book seals, bounded, non-COMPLETE
# ---------------------------------------------------------------------------

def test_real_autonomous_capture_seals_non_complete_at_capture_time(capture_root):
    manifest = capture_root["manifest"]
    sealed = snapshots.create_snapshot(
        "autonomous", decision_cutoff=_CAPTURE_CUTOFF, recorded_at=_CAPTURE_RECORDED,
    )
    assert sealed["snapshot_id"].startswith("sha256:")
    assert sealed["state"] != "COMPLETE"
    assert sealed["coverage_state"] != "COMPLETE"
    assert len(canonical_json_bytes(sealed)) <= c.MAX_SNAPSHOT_BYTES

    receipts = _receipts(sealed)

    # The pending target is available point-in-time and digests to the captured bytes.
    entry = _manifest_entry(manifest, "autonomous/pending_target.json")
    pending = receipts["book.pending_target"]
    assert pending["status"] == "AVAILABLE"
    assert pending["artifact_digest"] == "sha256:" + entry["sha256"]

    # The ~10 KB-per-row real decision tail is byte-bounded with counted omissions.
    decisions = receipts["book.decisions"]
    assert decisions["status"] == "AVAILABLE"
    assert decisions["omitted_rows"] > 0
    assert decisions["rows_total"] == decisions["rows_returned"] + decisions["omitted_rows"]

    # The captured book has no account.json: required source MISSING, book truth BLOCKED.
    assert receipts["book.account"]["status"] == "MISSING"
    assert sealed["sections"]["book_truth"]["coverage_state"] == "BLOCKED"

    sizes = {
        section_id: len(canonical_json_bytes(section))
        for section_id, section in sealed["sections"].items()
    }
    print("REAL_CAPTURE snapshot_id=" + sealed["snapshot_id"])
    print("REAL_CAPTURE state=" + sealed["state"]
          + " coverage_state=" + sealed["coverage_state"])
    print("REAL_CAPTURE section_canonical_bytes=" + json.dumps(sizes, sort_keys=True))
    print("REAL_CAPTURE decisions rows_returned=%s omitted_rows=%s rows_total=%s"
          % (decisions["rows_returned"], decisions["omitted_rows"], decisions["rows_total"]))
    print("REAL_CAPTURE pending_target=%s %s"
          % (pending["status"], pending["artifact_digest"]))


# ---------------------------------------------------------------------------
# Historical cutoff: the current append-only files are all future evidence there
# ---------------------------------------------------------------------------

def test_real_autonomous_capture_historical_cutoff_is_future_blocked(capture_root):
    sealed = snapshots.create_snapshot(
        "autonomous", decision_cutoff=_HISTORICAL_CUTOFF, recorded_at=_CAPTURE_RECORDED,
    )
    receipts = _receipts(sealed)
    for source_id in _AUTONOMOUS_SOURCES:
        receipt = receipts[source_id]
        assert receipt["status"] == "FUTURE_AT_CUTOFF", source_id
        assert receipt["coverage_state"] == "BLOCKED", source_id
    assert sealed["sections"]["book_truth"]["coverage_state"] == "BLOCKED"
    assert sealed["sections"]["historical_memory"]["coverage_state"] == "BLOCKED"
    assert sealed["state"] != "COMPLETE"
    print("REAL_CAPTURE historical="
          + ",".join(f"{sid}:{receipts[sid]['status']}" for sid in _AUTONOMOUS_SOURCES))


# ---------------------------------------------------------------------------
# The china book at the same capture-time cutoff
# ---------------------------------------------------------------------------

def test_real_china_capture_seals_non_complete(capture_root):
    # The china book directory is owned by the registry allowlist: portfolio/registry.py
    # canonical_id accepts exactly "china" (registry.py:169-170) and data_dir's china
    # branch returns _ROOT / "data" / "portfolios" / "china" (registry.py:273-274) — the
    # layout the capture was staged into above. Verified structurally against the
    # registry's own source because the suite's autouse book-isolation fixture re-roots
    # registry._ROOT at a tmp copy: the relative layout, not the absolute root, is the
    # registry-owned contract.
    import inspect

    assert registry.canonical_id("china") == "china"
    data_dir_source = inspect.getsource(registry.data_dir)
    assert 'pid == "china"' in data_dir_source
    assert '_ROOT / "data" / "portfolios" / "china"' in data_dir_source
    china_dir = registry.data_dir("china")
    assert china_dir.as_posix().endswith("data/portfolios/china")
    staged_china = sources._ROOT / "data" / "portfolios" / "china"
    assert staged_china == sources._book_dir("china")
    assert (staged_china / "decisions.jsonl").is_file()
    assert (staged_china / "fills.jsonl").is_file()
    assert (staged_china / "positions_ledger.json").is_file()

    # compose/persist is autonomous-only by contract (decision_snapshot's fixed book
    # literal), so the deepest lawful layer for china is the capture itself: it must
    # complete without raising and produce exactly the closed section set the composer
    # seals over — with coverage that is not COMPLETE.
    capture = sources.capture_all(
        "china", decision_cutoff=_CAPTURE_CUTOFF, recorded_at=_CAPTURE_RECORDED,
    )
    assert set(capture["sections"]) == set(c.SECTION_IDS)
    receipts = _receipts(capture)
    for source_id in ("book.decisions", "book.fills", "book.positions_ledger"):
        receipt = receipts[source_id]
        assert receipt["status"] == "AVAILABLE", source_id
        assert receipt["rows_total"] == receipt["rows_returned"] + receipt["omitted_rows"], source_id
    # The 1.3 MB decision tail is byte-bounded with counted omissions; the fill blotter is
    # row-count bounded; the ledger is a single raw-object row with nothing omitted.
    assert receipts["book.decisions"]["omitted_rows"] > 0
    assert receipts["book.fills"]["omitted_rows"] > 0
    assert receipts["book.positions_ledger"]["rows_returned"] == 1
    assert receipts["book.positions_ledger"]["omitted_rows"] == 0

    coverage_states = {section["coverage_state"] for section in capture["sections"].values()}
    assert coverage_states != {"COMPLETE"}
    print("REAL_CAPTURE china coverage_states=" + json.dumps(sorted(coverage_states)))

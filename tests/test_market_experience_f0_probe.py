"""Unit checks for F0 instrumentation; market-owner semantics are measured separately."""
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from research import market_experience_f0_probe as probe


@pytest.mark.parametrize("value", [True, False, 0, -1, 100001, 1.5, "2", None])
def test_invalid_workload_refused(value):
    with pytest.raises(ValueError):
        probe.positive_count(value)


def test_known_git_blob_hash():
    assert probe.git_blob_id(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_rows_are_explicit_synthetic_and_deterministic():
    rows = probe.synthetic_rows(5)
    assert rows == probe.synthetic_rows(5)
    assert [r["synthetic_record_id"] for r in rows] == list(range(5))
    assert sum(r["published_at"] == probe.EARLY for r in rows) == 3
    assert all(r["ingested_at"] == probe.LATE for r in rows)


@pytest.mark.parametrize("ref", ["main", "HEAD", "a" * 39, "a" * 41, "--help"])
def test_only_immutable_ref_is_accepted(tmp_path, ref):
    with pytest.raises(ValueError, match="immutable"):
        probe.load_owner(tmp_path, ref)


def _owner_file(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / probe.OWNER_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return path


def test_owner_load_verifies_bytes_and_writes_no_cache(tmp_path, monkeypatch):
    content = b"VALUE = 7\n"
    path = _owner_file(tmp_path, content)
    monkeypatch.setattr(probe.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=content))
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    owner, identity = probe.load_owner(tmp_path, "a" * 40)
    assert owner.VALUE == 7
    assert identity["git_blob"] == probe.git_blob_id(content)
    assert identity["commit"] == "a" * 40
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
    assert path.read_bytes() == content


def test_owner_mismatch_is_refused_before_execution(tmp_path, monkeypatch):
    _owner_file(tmp_path, b"raise AssertionError('must not run')\n")
    monkeypatch.setattr(probe.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=b"VALUE = 7\n"))
    with pytest.raises(ValueError, match="differ"):
        probe.load_owner(tmp_path, "a" * 40)


def test_symlink_owner_is_refused(tmp_path):
    other = tmp_path / "other.py"
    other.write_text("VALUE = 7\n")
    path = tmp_path / probe.OWNER_PATH
    path.parent.mkdir(parents=True)
    path.symlink_to(other)
    with pytest.raises(ValueError, match="symlink"):
        probe.load_owner(tmp_path, "a" * 40)


def test_instrumentation_reports_counts_and_scope():
    # Instrumentation stub, not a second temporal implementation.
    owner = SimpleNamespace(TemporalProfile=SimpleNamespace(EVENT="EVENT"),
                            as_of_filter=lambda rows, cutoff, profile: rows[::2])
    receipt = probe.measure(owner, 5, repeats=2)
    assert len(receipt["trials"]) == 2
    assert all(t["retained_rows"] == 3 and t["cpu_seconds"] >= 0 for t in receipt["trials"])
    assert receipt["median_filter_wall_seconds"] >= 0
    assert receipt["process_lifetime_peak_rss_bytes"] > 0
    assert receipt["dataset_class"] == "SYNTHETIC_TEMPORAL_METADATA_NOT_MARKET_HISTORY"


def test_bad_cardinality_is_not_reported_as_success():
    owner = SimpleNamespace(TemporalProfile=SimpleNamespace(EVENT="EVENT"),
                            as_of_filter=lambda rows, cutoff, profile: [])
    with pytest.raises(ValueError, match="cardinality"):
        probe.measure(owner, 5)

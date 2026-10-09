"""Instrumentation tests use synthetic data; real source checks have their own receipt."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import pytest

from research import market_experience_f0_cpi_audit as audit


def manifest() -> dict:
    return {
        "schema": "release_target_vintage_collection.v1", "source": "FRED/ALFRED",
        "status": "ok", "publication_status": "complete", "dry_run": False,
        "integrity_profile": "release_target_artifact_sha256_bytes.v1",
        "source_output_type": 2, "realtime_start": "1997-01-01",
        "collected_at": "2026-09-23T21:18:17+00:00",
        "completed_at": "2026-09-23T21:19:16+00:00",
        "series": {audit.SERIES: {
            "status": "written", "path": audit.ARTIFACT,
            "artifact_bytes": 3, "artifact_sha256": hashlib.sha256(b"abc").hexdigest(),
            "rows": 2, "periods": 2, "release_dates": 1,
            "period_min": "2020-01-01", "period_max": "2020-02-01",
        }},
    }


def encoded(value: dict) -> bytes:
    return json.dumps(value).encode()


def test_manifest_and_artifact_match():
    _, entry = audit.parse_manifest(encoded(manifest()))
    audit.verify_artifact(b"abc", entry)


@pytest.mark.parametrize(("key", "value"), [
    ("schema", "unknown"), ("source", "other"), ("status", "partial"),
    ("publication_status", "pending"), ("dry_run", True), ("dry_run", 0),
    ("source_output_type", 4), ("source_output_type", 2.0),
    ("integrity_profile", "none"), ("collected_at", "2026-09-23T21:18:17"),
    ("completed_at", "2026-09-22T21:19:16+00:00"),
])
def test_manifest_refuses_wrong_profile_or_clock(key, value):
    doc = manifest()
    doc[key] = value
    with pytest.raises(ValueError):
        audit.parse_manifest(encoded(doc))


@pytest.mark.parametrize(("key", "value"), [
    ("rows", 0), ("rows", True), ("rows", audit.MAX_ROWS + 1),
    ("artifact_bytes", audit.MAX_BYTES + 1), ("artifact_sha256", "not-a-digest"),
    ("path", "../other.parquet"), ("status", "unavailable"),
    ("period_min", "2021-01-01"), ("periods", -1), ("release_dates", False),
])
def test_manifest_refuses_bad_source_entry(key, value):
    doc = manifest()
    doc["series"][audit.SERIES][key] = value
    with pytest.raises(ValueError):
        audit.parse_manifest(encoded(doc))


def test_no_fallback_when_fixed_source_missing():
    doc = manifest()
    doc["series"] = {"CPILFESL": doc["series"][audit.SERIES]}
    with pytest.raises(ValueError, match="no source substitution"):
        audit.parse_manifest(encoded(doc))


@pytest.mark.parametrize("body", [b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b''])
def test_strict_json(body):
    with pytest.raises(ValueError):
        audit.parse_manifest(body)


@pytest.mark.parametrize("body", [b"abd", b"ab", b"abcd"])
def test_artifact_digest_and_size_are_both_bound(body):
    entry = manifest()["series"][audit.SERIES]
    with pytest.raises(ValueError):
        audit.verify_artifact(body, entry)


def frames():
    raw = pd.DataFrame({
        "series": [audit.SERIES] * 2, "source_output_type": [2, 2],
        "period": ["2020-01-01", "2020-02-01"],
        "realtime_start": ["2020-03-15"] * 2, "value": [100.0, 101.0],
    })
    normalized = raw.copy()
    normalized["period"] = pd.to_datetime(normalized["period"])
    normalized["realtime_start"] = pd.to_datetime(normalized["realtime_start"])
    return raw, normalized


def test_counts_keep_original_denominator():
    raw, normalized = frames()
    result = audit.frame_counts(raw, normalized, manifest()["series"][audit.SERIES])
    assert result["raw_rows"] == result["normalized_rows"] == 2
    assert result["normalization_row_reduction"] == 0
    assert result["vintage_min"] == "2020-03-15"
    assert "value" not in result


def test_normalizer_row_loss_is_not_silently_accepted():
    raw, normalized = frames()
    with pytest.raises(ValueError, match="denominator"):
        audit.frame_counts(raw, normalized.iloc[:1], manifest()["series"][audit.SERIES])


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), -float("inf")])
def test_nonfinite_normalized_values_refused(bad):
    raw, normalized = frames()
    normalized.loc[0, "value"] = bad
    with pytest.raises(ValueError, match="non-finite"):
        audit.frame_counts(raw, normalized, manifest()["series"][audit.SERIES])


def good_case() -> dict:
    return {"status": "ok", "period": "2020-01", "as_of": "2020-04-01",
            "release_date": "2020-02-15", "cross_vintage_fallback_used": False,
            "published_proxy_is_official_release": False,
            "provenance": {"same_release_vintage": True,
                           "cross_vintage_fallback_used": False, "value": 999.12345},
            "current_level": 999.12345, "latent_change": 999.12345}


def test_case_projection_never_publishes_levels_or_targets():
    projected = audit.project_case(good_case(), "2020-01", "2020-04-01", True)
    text = json.dumps(projected)
    assert "999.12345" not in text
    assert "current_level" not in text and "latent_change" not in text
    assert projected["passed"] is True


@pytest.mark.parametrize(("key", "value"), [
    ("status", "unavailable"), ("period", "2021-01"),
    ("cross_vintage_fallback_used", True), ("release_date", "2020-05-01"),
    ("published_proxy_is_official_release", True), ("provenance", {}),
])
def test_native_result_must_meet_fixed_structural_case(key, value):
    result = good_case()
    result[key] = value
    with pytest.raises(ValueError):
        audit.project_case(result, "2020-01", "2020-04-01", True)


def test_before_period_case_has_specific_typed_absence():
    result = {"status": "unavailable", "period": "2019-01", "as_of": "2018-12-31",
              "reason": "current_period_not_available_by_as_of", "cross_vintage_fallback_used": False}
    assert audit.project_case(result, "2019-01", "2018-12-31", False)["passed"]
    result["reason"] = "other"
    with pytest.raises(ValueError):
        audit.project_case(result, "2019-01", "2018-12-31", False)


def test_git_reader_uses_no_lazy_fetch_and_checks_blob(monkeypatch, tmp_path):
    calls = []
    def output(command, **kwargs):
        calls.append((command, kwargs))
        return b"3\n" if "-s" in command else b"abc"
    monkeypatch.setattr(subprocess, "check_output", output)
    assert audit.read_blob(tmp_path, audit.MANIFEST, expected=audit.git_hash(b"abc")) == b"abc"
    assert all(k["env"]["GIT_NO_LAZY_FETCH"] == "1" for _, k in calls)
    with pytest.raises(ValueError, match="identity mismatch"):
        audit.read_blob(tmp_path, audit.MANIFEST, expected="0" * 40)


@pytest.mark.parametrize(("commit", "path"), [
    ("main", audit.MANIFEST), (audit.COMMIT, "../../secrets"),
    ("a" * 39, audit.OWNER),
])
def test_unregistered_git_reference_is_refused_before_subprocess(commit, path):
    with pytest.raises(ValueError, match="unregistered"):
        audit.read_blob(Path("."), path, commit=commit)


def test_modified_native_owner_is_not_executed():
    with pytest.raises(ValueError, match="unreviewed"):
        audit.native_owner(b'raise RuntimeError("must not run")')


def test_fixed_cases_and_protocol_exist():
    assert audit.REQUESTS == tuple((f"{y}-01", f"{y}-04-01", True) for y in range(2019, 2024)) + (("2019-01", "2018-12-31", False),)
    assert Path(audit.__file__).with_name(audit.PROTOCOL).is_file()

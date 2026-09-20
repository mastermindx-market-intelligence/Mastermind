"""Rights-safety and reference-integrity guard for the Fiscal.ai Run 01 packet.

The reconnaissance itself was accepted; what this guards is the *packaging*.
Canonical Git must not become a durable copy of paid-seat competitor or
third-party corpora, so the raw authenticated captures were removed and only
tight, data-free crops were retained. These tests fail if that boundary erodes:
if a raw capture directory reappears, if a retained image grows back toward a
full-page capture, or if an observation points at evidence that is not there.
"""

from __future__ import annotations

import json
import pathlib

import pytest

PACKET = (
    pathlib.Path(__file__).resolve().parents[1]
    / "research/competitive_intelligence/fiscal/2026-08-22/recon01"
)
OBSERVATIONS = PACKET / "observations.jsonl"
MANIFEST = PACKET / "evidence/removed_assets.jsonl"
SANITIZED = PACKET / "evidence/screens_sanitized"

EXPECTED_OBSERVATIONS = 32
EXPECTED_REMOVED = 25
EXPECTED_RETAINED = 5

# A full-frame 1565x1121 capture of this product ran 61-260 KB. Retained crops
# must stay far below that; anything larger is no longer a tight crop.
MAX_RETAINED_BYTES = 150_000

VALID_DISPOSITIONS = {
    "retained_sanitized_crop",
    "removed_for_rights_safety",
    "removed_as_duplicate",
    "no_capture_taken",
}


def _records() -> list[dict]:
    return [
        json.loads(line)
        for line in OBSERVATIONS.read_text().splitlines()
        if line.strip()
    ]


def test_observation_file_parses_with_unique_ids() -> None:
    records = _records()
    assert len(records) == EXPECTED_OBSERVATIONS
    ids = [r["id"] for r in records]
    assert len(set(ids)) == len(ids), "duplicate observation ids"
    assert ids == sorted(ids), "observation ids are not in stable order"


def test_every_record_declares_an_evidence_disposition() -> None:
    for record in _records():
        assert record.get("evidence_disposition") in VALID_DISPOSITIONS, record["id"]


def test_retained_evidence_references_resolve() -> None:
    retained = [
        r
        for r in _records()
        if r["evidence_disposition"] == "retained_sanitized_crop"
    ]
    assert len(retained) == EXPECTED_RETAINED
    for record in retained:
        path = PACKET / record["screenshot_path"]
        assert path.is_file(), f"{record['id']} points at missing {path}"
        assert path.parent == SANITIZED, f"{record['id']} escapes the sanitized dir"


def test_removed_evidence_is_marked_not_silently_dropped() -> None:
    """A removed capture must say so and stay provable by hash."""
    for record in _records():
        disposition = record["evidence_disposition"]
        if not disposition.startswith("removed_"):
            continue
        assert record["screenshot_path"] is None, record["id"]
        digest = record.get("removed_asset_sha256", "")
        assert len(digest) == 64, f"{record['id']} lacks a usable sha256"
        assert record.get("evidence_note"), f"{record['id']} lacks an omission note"


def test_removal_manifest_matches_the_observation_records() -> None:
    manifest = [
        json.loads(line) for line in MANIFEST.read_text().splitlines() if line.strip()
    ]
    assert len(manifest) == EXPECTED_REMOVED
    by_id = {entry["observation_id"]: entry for entry in manifest}
    assert len(by_id) == len(manifest), "duplicate manifest entries"

    for record in _records():
        if not record["evidence_disposition"].startswith("removed_"):
            assert record["id"] not in by_id
            continue
        entry = by_id[record["id"]]
        assert entry["sha256"] == record["removed_asset_sha256"]
        assert entry["bytes"] > 0
        assert entry["reason"], f"{record['id']} removal has no stated reason"


def test_no_raw_capture_directory_returns() -> None:
    raw = PACKET / "evidence/screens"
    assert not raw.exists(), (
        "evidence/screens holds the raw authenticated captures and must stay "
        "removed from canonical Git"
    )


def test_retained_crops_stay_tight() -> None:
    images = sorted(SANITIZED.glob("*.png"))
    assert len(images) == EXPECTED_RETAINED
    for image in images:
        size = image.stat().st_size
        assert size <= MAX_RETAINED_BYTES, (
            f"{image.name} is {size} bytes; a retained crop this large is no "
            "longer tightly cropped"
        )


def test_packet_carries_no_other_binary_evidence() -> None:
    allowed = {p.resolve() for p in SANITIZED.glob("*.png")}
    for path in PACKET.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".pdf",
            ".mp3",
            ".mp4",
            ".wav",
        }:
            continue
        assert path.resolve() in allowed, f"unreviewed binary evidence: {path}"


@pytest.mark.parametrize("name", ["README.md", "interaction_ledger.md"])
def test_prose_does_not_advertise_removed_assets(name: str) -> None:
    text = (PACKET / name).read_text()
    assert "evidence/screens/" not in text, (
        f"{name} still points readers at the removed raw capture directory"
    )

#!/usr/bin/env python3
"""Read one existing, source-pinned development reconstruction; never publish it.

This is a consumer of the existing fixture evidence, not an API, trial/exposure
registry, financial interpreter or production I3 reader. It resolves no live
issuer or entitlement. Its trust anchor is the named, already-committed capture,
not a digest supplied by the document being read. Production adoption requires
independent owner, rights, runtime and source-custody admission.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType
from typing import Any

from baseline_replay import ReplayRefusal, _load, canonical, compare_snapshots, digest

ROOT = Path(__file__).resolve().parent
CAPTURE_COMMIT = "b95a7ddcb24f74a81b9486620c219217518d6f20"
CASES = ("first_admission", "later_admission_refusal", "source_cutoff_refusal", "identical_cutoff")
_CAPTURE_HASHES = MappingProxyType({
    "method-before-execution.json": "03bed81b4c1e64cc9a663611e767c6c403f67ba44e1d5a65f8cefe4019d3881f",
    "owner-queries.json": "00fdff03faea8551f9b44c0c9fff086b3114d2c95dcbc9a815f15253a84fdcd5",
    "result-r2.json": "e1f36d74dfd12a885cdc9ece9dc6f784048ed7f85f3ded12a607618e412ffbc1",
})
_MAX_BYTES = 1_048_576

class ReaderRefusal(ValueError):
    """A typed, non-content-bearing refusal at this fixed development reader."""

def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ReaderRefusal(reason)

def _read_at(directory: int, name: str) -> bytes:
    """Single-descriptor bounded read. Never follow a file symlink or block on FIFO."""
    _require(type(name) is str and name and Path(name).name == name and "/" not in name and "\\" not in name, "invalid_evidence_name")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= _MAX_BYTES, "evidence_file_bound")
        chunks = []
        remaining = _MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        _require(0 < len(raw) <= _MAX_BYTES, "evidence_file_bound")
        return raw
    finally:
        os.close(fd)

def _capture(directory: int, name: str) -> Any:
    raw = _read_at(directory, name)
    _require(digest(raw) == _CAPTURE_HASHES[name], "capture_identity_mismatch")
    # These bytes have matched a fixed committed capture before parsing.
    return json.loads(raw)

def load_verified(case: str, evidence_dir: Path | None = None) -> dict:
    """Resolve the existing artifact identity and replay it against exact inputs.

    Return detached original semantic bytes, including all refusal/maturity flags.
    No current timestamp or replacement identifier is minted. No write occurs.
    """
    _require(type(case) is str and case in CASES, "unsupported_fixture_case")
    root = Path(evidence_dir) if evidence_dir is not None else ROOT / "evidence/baseline-replay"
    directory = None
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        method = _capture(directory, "method-before-execution.json")
        receipts = _capture(directory, "owner-queries.json")
        recorded = _capture(directory, "result-r2.json")
        pair = next(p for p in method["comparison_pairs"] if p["name"] == case)
        expected = next(p for p in recorded["comparisons"] if p["name"] == case)
        owners = {r["name"]: r for r in receipts}
        before, after = pair["before"], pair["after"]
        before_raw = _read_at(directory, before + ".response.json")
        after_raw = _read_at(directory, after + ".response.json")
        # Before extracting any content, bind both exact owner byte streams to
        # the original captured receipt, rather than caller-supplied hashes.
        _require(digest(before_raw) == owners[before]["response_sha256"] and digest(after_raw) == owners[after]["response_sha256"], "owner_capture_mismatch")
        stored_raw = _read_at(directory, case + ".comparison.json")
        stored = _load(stored_raw, digest(stored_raw))
        _require(set(stored) == {"artifact_sha256", "payload"}, "comparison_shape")
        _require(stored["artifact_sha256"] == expected["artifact_sha256"] and digest(canonical(stored["payload"])) == expected["artifact_sha256"], "comparison_identity_mismatch")
        replayed = compare_snapshots(before_raw, after_raw,
            before_sha256=owners[before]["response_sha256"], after_sha256=owners[after]["response_sha256"],
            before_request=method["requests"][before], after_request=method["requests"][after])
        _require(canonical(replayed) == canonical(stored), "reconstruction_replay_mismatch")
        return json.loads(canonical(stored))
    except ReaderRefusal:
        raise
    except ReplayRefusal as exc:
        raise ReaderRefusal("owner_or_artifact_refused") from exc
    except (OSError, ValueError, TypeError, KeyError, StopIteration, OverflowError, RecursionError) as exc:
        raise ReaderRefusal("evidence_unavailable_or_malformed") from exc
    finally:
        if directory is not None:
            os.close(directory)

def _text(artifact: dict) -> str:
    p = artifact["payload"]
    lines = ["AAPL · What changed in the available evidence?",
        "DEVELOPMENT FIXTURE — not a live issuer service or an investment signal.",
        "Artifact: " + artifact["artifact_sha256"],
        "Source cutoff: " + p["baseline_cutoffs"]["source_snapshot_at"] + " -> " + p["target_cutoffs"]["source_snapshot_at"],
        "System cutoff: " + p["baseline_cutoffs"]["recorded_at"] + " -> " + p["target_cutoffs"]["recorded_at"],
        "All " + str(p["requested_variable_count"]) + " requested slots are retained. Economic interpretation and emission are absent.", ""]
    for row in p["variables"]:
        v = row["variable"]
        lines.append(v["metric_id"] + " / " + v["period"]["label"] + " / " + v["period"]["kind"])
        for side in ("baseline", "target"):
            cell = row[side]
            value = cell["value"] + " " + cell["unit"] if cell["state"] == "value" else cell["state"] + ": " + cell["reason"]
            lines.append("  " + side.capitalize() + ": " + value)
        lines.append("  Evidence state: " + row["reconstruction_state"])
        lines.append("  Receipts: " + row["baseline"]["cell_id"] + " -> " + row["target"]["cell_id"])
        lines.append("")
    lines.append("Rights, publication, trial registration and product integration have NOT been admitted.")
    return "\n".join(lines) + "\n"

def read_fixture(case: str, *, output_format: str = "json", evidence_dir: Path | None = None) -> bytes:
    """Machine JSON and human text consume the exact same verified identity."""
    _require(output_format in ("json", "text"), "unsupported_output_format")
    artifact = load_verified(case, evidence_dir)
    return canonical(artifact) + b"\n" if output_format == "json" else _text(artifact).encode("utf-8")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    try:
        data = read_fixture(args.case, output_format=args.format, evidence_dir=args.evidence_dir)
    except ReaderRefusal as exc:
        print("FIXTURE_REFUSED: " + str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(data)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

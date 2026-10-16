"""Read-only, pinned CPI source-component audit; never a corpus admission service.

Run with --macro-root pointing to the existing Macro checkout. Git objects must
already be present. No vendor/network calls, source writes, training or forecasts.
Only bounded provenance, counts and resource measurements are printed.
"""
from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import time
from types import ModuleType
from typing import Any, Callable

COMMIT = "b9d23ca4bce4308fa7466c4e0f5d318168a50f6f"
SERIES = "CPIAUCSL"
MANIFEST = "data/fred_vintage/release_targets/manifest.json"
ARTIFACT = "data/fred_vintage/release_targets/CPIAUCSL_all_vintages.parquet"
OWNER = "engine/release_target_truth.py"
MANIFEST_BLOB = "b4fe4314097c93847b691060beeb8adc35a79546"
OWNER_BLOB = "c9da53421cc8ab2ed7cdef2f3097a64f5e8ee222"
PROTOCOL = "MARKET_EXPERIENCE_F0_CPI_PROTOCOL_2026-09-24.md"
MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 1_000_000
REQUESTS = tuple((f"{year}-01", f"{year}-04-01", True) for year in range(2019, 2024)) + (
    ("2019-01", "2018-12-31", False),
)


def git_hash(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()


def read_blob(root: Path, path: str, *, commit: str = COMMIT,
              expected: str | None = None) -> bytes:
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or path not in {MANIFEST, ARTIFACT, OWNER}:
        raise ValueError("unregistered source reference")
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    command = ["git", "--no-pager", "-C", str(root), "cat-file"]
    spec = f"{commit}:{path}"
    size = int(subprocess.check_output(command + ["-s", spec], env=env, timeout=30))
    if not 0 < size <= MAX_BYTES:
        raise ValueError("source object exceeds audit bound")
    body = subprocess.check_output(command + ["blob", spec], env=env, timeout=30)
    if len(body) != size or (expected is not None and git_hash(body) != expected):
        raise ValueError("source identity mismatch")
    return body


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate manifest key")
        output[key] = value
    return output


def _nonfinite(_value: str) -> None:
    raise ValueError("non-finite manifest value")


def parse_manifest(body: bytes) -> tuple[dict, dict]:
    if not 0 < len(body) <= 512 * 1024:
        raise ValueError("manifest size out of bounds")
    manifest = json.loads(body, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    required = {
        "schema": "release_target_vintage_collection.v1",
        "source": "FRED/ALFRED", "status": "ok", "publication_status": "complete",
        "integrity_profile": "release_target_artifact_sha256_bytes.v1",
    }
    if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in required.items()):
        raise ValueError("incomplete or incompatible collector manifest")
    if manifest.get("dry_run") is not False or type(manifest.get("source_output_type")) is not int or manifest["source_output_type"] != 2:
        raise ValueError("not an actual full-vintage collection")
    clocks = [datetime.fromisoformat(manifest[k].replace("Z", "+00:00"))
              for k in ("collected_at", "completed_at")]
    if any(c.tzinfo is None or c.utcoffset() is None for c in clocks) or clocks[1] < clocks[0]:
        raise ValueError("collector clocks invalid")
    date.fromisoformat(manifest["realtime_start"])
    entry = manifest.get("series", {}).get(SERIES)
    if not isinstance(entry, dict) or entry.get("status") != "written" or entry.get("path") != ARTIFACT:
        raise ValueError("fixed CPI component is unavailable; no source substitution")
    for field in ("artifact_bytes", "rows", "periods", "release_dates"):
        if type(entry.get(field)) is not int or entry[field] <= 0:
            raise ValueError("invalid source count")
    if entry["artifact_bytes"] > MAX_BYTES or entry["rows"] > MAX_ROWS:
        raise ValueError("artifact exceeds benchmark envelope")
    if not isinstance(entry.get("artifact_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", entry["artifact_sha256"]):
        raise ValueError("missing exact artifact digest")
    if date.fromisoformat(entry["period_min"]) > date.fromisoformat(entry["period_max"]):
        raise ValueError("inverted source period range")
    return manifest, entry


def verify_artifact(body: bytes, entry: dict) -> None:
    if len(body) != entry["artifact_bytes"] or hashlib.sha256(body).hexdigest() != entry["artifact_sha256"]:
        raise ValueError("artifact bytes differ from collector manifest")


def native_owner(body: bytes) -> ModuleType:
    if git_hash(body) != OWNER_BLOB:
        raise ValueError("unreviewed native owner")
    tree = ast.parse(body)
    allowed = {"__future__", "collections.abc", "datetime", "decimal", "math", "pathlib", "pandas"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module not in allowed:
            raise ValueError("unexpected native import")
        if isinstance(node, ast.Import) and any(n.name not in allowed for n in node.names):
            raise ValueError("unexpected native import")
    module = ModuleType("market_experience_verified_release_owner")
    module.__file__ = OWNER
    exec(compile(body, OWNER, "exec"), module.__dict__)
    return module


def frame_counts(raw: Any, normalized: Any, entry: dict) -> dict:
    if "series" not in raw or set(raw["series"]) != {SERIES}:
        raise ValueError("raw source is not exactly CPI")
    if "source_output_type" not in raw or set(raw["source_output_type"]) != {2}:
        raise ValueError("raw full-vintage marker missing or wrong")
    result = {
        "raw_rows": len(raw), "normalized_rows": len(normalized),
        "normalization_row_reduction": len(raw) - len(normalized),
        "periods": int(normalized["period"].nunique()),
        "vintage_dates": int(normalized["realtime_start"].nunique()),
        "period_min": normalized["period"].min().date().isoformat(),
        "period_max": normalized["period"].max().date().isoformat(),
        "vintage_min": normalized["realtime_start"].min().date().isoformat(),
        "vintage_max": normalized["realtime_start"].max().date().isoformat(),
        "raw_dataframe_deep_bytes": int(raw.memory_usage(index=True, deep=True).sum()),
        "normalized_dataframe_deep_bytes": int(normalized.memory_usage(index=True, deep=True).sum()),
    }
    expected = {"raw_rows": entry["rows"], "normalized_rows": entry["rows"],
                "periods": entry["periods"], "vintage_dates": entry["release_dates"],
                "period_min": entry["period_min"], "period_max": entry["period_max"]}
    if any(result[k] != value for k, value in expected.items()):
        raise ValueError("source counts differ; do not silently change the denominator")
    if not all(math.isfinite(float(value)) for value in normalized["value"]):
        raise ValueError("non-finite normalized observation")
    return result


def project_case(result: dict, period: str, cutoff: str, expected_ok: bool) -> dict:
    if result.get("status") != ("ok" if expected_ok else "unavailable"):
        raise ValueError("native result contradicts preregistered structural case")
    if result.get("period") != period or result.get("as_of") != cutoff:
        raise ValueError("native response identity/cutoff mismatch")
    if result.get("cross_vintage_fallback_used") is not False:
        raise ValueError("cross-vintage substitution")
    if expected_ok:
        provenance = result.get("provenance", {})
        if (provenance.get("same_release_vintage") is not True
                or provenance.get("cross_vintage_fallback_used") is not False
                or result.get("published_proxy_is_official_release") is not False
                or date.fromisoformat(result["release_date"]) > date.fromisoformat(cutoff)):
            raise ValueError("native vintage/proxy provenance mismatch")
    elif result.get("reason") != "current_period_not_available_by_as_of":
        raise ValueError("unexpected native absence reason")
    # Explicit allowlist: never emit levels, values, targets or nested source rows.
    return {"period": period, "as_of": cutoff, "status": result["status"],
            "release_date": result.get("release_date"), "reason": result.get("reason"),
            "same_vintage_provenance_checked": expected_ok, "passed": True}


def measured(function: Callable[[], Any]) -> tuple[Any, dict]:
    wall, cpu = time.perf_counter(), time.process_time()
    result = function()
    return result, {"wall_seconds": time.perf_counter() - wall,
                    "cpu_seconds": time.process_time() - cpu, "passes": 1}


def run(root: Path) -> dict:
    # Bind the on-disk pre-read protocol, not an unrecorded selection decision.
    protocol = Path(__file__).with_name(PROTOCOL).read_bytes()
    manifest_body = read_blob(root, MANIFEST, expected=MANIFEST_BLOB)
    manifest, entry = parse_manifest(manifest_body)
    artifact, git_read = measured(lambda: read_blob(root, ARTIFACT))
    verify_artifact(artifact, entry)
    owner_body = read_blob(root, OWNER, expected=OWNER_BLOB)
    owner = native_owner(owner_body)
    import pandas as pd
    import pyarrow
    import pyarrow.parquet as pq
    parquet = pq.ParquetFile(io.BytesIO(artifact))
    metadata = parquet.metadata
    if metadata.num_rows != entry["rows"] or sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups)) > 256 * 1024 * 1024:
        raise ValueError("parquet footer exceeds source count or decode budget")
    raw, decode = measured(lambda: parquet.read(use_threads=False).to_pandas(use_threads=False))
    normalized, normalization = measured(lambda: owner.normalize_full_vintage_frame(raw, series_id=SERIES))
    counts = frame_counts(raw, normalized, entry)
    cases = []
    for period, cutoff, expected_ok in REQUESTS:
        result, timing = measured(lambda: owner.reconstruct_release_target(
            raw, series_id=SERIES, period=period, as_of=cutoff))
        cases.append(dict(project_case(result, period, cutoff, expected_ok), measurement=timing))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "schema": "market_experience.f0_cpi_source_audit.v1",
        "evidence_class": "REAL_INPUT_INTERNAL_TECHNICAL_AUDIT_NOT_PILOT_ADMISSION",
        "status": "source_component_checks_passed", "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": {"repository": "mastermindx-market-intelligence/macro", "commit": COMMIT,
                   "manifest_path": MANIFEST, "manifest_git_blob": git_hash(manifest_body),
                   "manifest_sha256": hashlib.sha256(manifest_body).hexdigest(),
                   "artifact_path": ARTIFACT, "artifact_bytes": len(artifact),
                   "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
                   "owner_path": OWNER, "owner_git_blob": git_hash(owner_body),
                   "owner_sha256": hashlib.sha256(owner_body).hexdigest(),
                   "collector_completed_at": manifest["completed_at"],
                   "requested_vintage_start": manifest["realtime_start"]},
        "protocol_sha256": hashlib.sha256(protocol).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "counts": counts, "native_structural_cases": cases,
        "measurements": {"git_object_read": git_read, "parquet_decode": decode,
                         "native_normalization": normalization,
                         "process_lifetime_peak_rss_bytes": int(rss if sys.platform == "darwin" else rss * 1024),
                         "rss_scope": "lifetime high-water mark; not incremental or fleet capacity"},
        "environment": {"platform": sys.platform, "python": sys.version.split()[0],
                        "pandas": pd.__version__, "pyarrow": pyarrow.__version__},
        "production_data_admitted": 0, "model_calls": 0, "provider_spend_usd": 0,
        "training_eligible": False, "promotion_eligible": False,
        "source_values_published": False, "stock_pilot_admitted": False,
        "unproven": ["historical operational possession", "intraday publication time",
                     "stock universe and membership", "earnings source coverage",
                     "ML training and redistribution rights", "product consumer proof",
                     "forecast value", "LLM extraction cost", "fleet throughput"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macro-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.macro_root)
    except Exception as exc:
        # Native errors can embed source values; expose their type only.
        print(f"CPI_SOURCE_AUDIT_FAILED:{type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

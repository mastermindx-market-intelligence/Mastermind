"""F0 read-only probe of the existing Data OS temporal owner.

This is a contract/throughput microbenchmark, NOT a data-admission service,
forecast evaluator, historical corpus, model benchmark, or spending grant.
It imports only a hash-verified owner module from an existing checkout and
prints a receipt. Synthetic rows never become market observations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import statistics
import subprocess
import sys
import time
from types import ModuleType
from typing import Any

OWNER_PATH = "lib/dataos/temporal.py"
CUTOFF = "2020-06-30T20:00:00+00:00"
EARLY = "2020-06-30T19:00:00+00:00"
LATE = "2020-06-30T21:00:00+00:00"
MAX_ROWS = 100_000


def git_blob_id(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def positive_count(value: int, *, maximum: int = MAX_ROWS) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"count must be an integer from 1 to {maximum}")
    return value


def load_owner(root: Path, commit: str) -> tuple[ModuleType, dict[str, str]]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("an immutable 40-character commit is required")
    root = root.resolve(strict=True)
    path = root / OWNER_PATH
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError("owner module may not escape its checkout through symlinks")
    pinned = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{OWNER_PATH}"],
        check=True, capture_output=True, timeout=30,
    ).stdout
    current = path.read_bytes()
    if current != pinned:
        raise ValueError("owner bytes differ from the pinned commit; no import performed")
    module = ModuleType("market_experience_f0_verified_temporal_owner")
    module.__file__ = str(path)
    # Execute the exact reviewed repository bytes, never a stale .pyc. The
    # existing stdlib-only owner stays authoritative; no copy is persisted.
    exec(compile(pinned, str(path), "exec"), module.__dict__)
    # Protect the measured identity against concurrent edits during import.
    if path.read_bytes() != pinned:
        raise ValueError("owner changed during import; discard this measurement")
    return module, {
        "repository": "mastermindx-market-intelligence/macro", "commit": commit,
        "path": OWNER_PATH, "git_blob": git_blob_id(pinned),
        "sha256": hashlib.sha256(pinned).hexdigest(),
    }


def contract_cases(owner: ModuleType) -> list[dict[str, Any]]:
    p = owner.TemporalProfile
    early = {"event_at": EARLY, "published_at": EARLY, "ingested_at": LATE}
    revisions = [dict(early, revision_seq=0, period_end="2020-03-31"),
                 dict(early, published_at=LATE, revision_seq=1, period_end="2020-03-31")]
    cases = []

    def count_case(name: str, rows: list[dict], cutoff: str, profile: Any,
                   expected: int, interpretation: str) -> None:
        actual = len(owner.as_of_filter(rows, cutoff, profile))
        cases.append({"case": name, "expected_count": expected, "actual_count": actual,
                      "passed": actual == expected, "interpretation": interpretation})

    count_case("public_before_acquisition", [early], CUTOFF, p.EVENT, 1,
               "Publication-first read; this is NOT proof of operational possession.")
    count_case("unknown_publication_uses_acquisition", [{"ingested_at": LATE}], CUTOFF,
               p.EVENT, 0, "Missing public clock cannot be backdated to event time.")
    count_case("future_revision_excluded", revisions, CUTOFF, p.REVISABLE_RELEASE, 1,
               "Later revision is not available at the earlier cutoff.")
    count_case("eligible_revisions_are_not_collapsed", revisions, LATE,
               p.REVISABLE_RELEASE, 2,
               "This filter does not select the authoritative vintage; use its dataset owner.")
    count_case("served_output_not_yet_available", [{"computed_at": EARLY, "served_at": LATE}],
               CUTOFF, p.INTELLIGENCE, 0, "Computed output is not yet actual served output.")
    for name, rows, profile in [
        ("derived_is_not_operational_replay", [{"computed_at": EARLY}], p.DERIVED),
        ("naive_timestamp_refused", [{"published_at": "2020-06-30T19:00:00"}], p.EVENT),
        ("missing_both_clocks_refused", [{"event_at": EARLY}], p.EVENT),
    ]:
        try:
            owner.as_of_filter(rows, CUTOFF, profile)
        except owner.TemporalError as exc:
            cases.append({"case": name, "passed": True, "exception": type(exc).__name__})
        else:
            cases.append({"case": name, "passed": False, "exception": None})
    return cases


def synthetic_rows(count: int) -> list[dict[str, Any]]:
    positive_count(count)
    return [{"synthetic_record_id": i, "event_at": EARLY,
             "published_at": EARLY if i % 2 == 0 else LATE,
             "ingested_at": LATE, "value": (i % 101) / 100.0} for i in range(count)]


def measure(owner: ModuleType, count: int, repeats: int = 3) -> dict[str, Any]:
    positive_count(count)
    positive_count(repeats, maximum=5)
    build_start = time.perf_counter()
    rows = synthetic_rows(count)
    build_seconds = time.perf_counter() - build_start
    trials = []
    for _ in range(repeats):
        cpu_start, wall_start = time.process_time(), time.perf_counter()
        result = owner.as_of_filter(rows, CUTOFF, owner.TemporalProfile.EVENT)
        wall, cpu = time.perf_counter() - wall_start, time.process_time() - cpu_start
        if len(result) != (count + 1) // 2:
            raise ValueError("canonical owner returned unexpected synthetic cardinality")
        trials.append({"wall_seconds": wall, "cpu_seconds": cpu, "retained_rows": len(result)})
        del result
    hwm = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"synthetic_rows": count, "construction_wall_seconds": build_seconds,
            "trials": trials, "median_filter_wall_seconds": statistics.median(t["wall_seconds"] for t in trials),
            "process_lifetime_peak_rss_bytes": int(hwm if sys.platform == "darwin" else hwm * 1024),
            "rss_scope": "process lifetime high-water mark, not per-stage incremental memory",
            "dataset_class": "SYNTHETIC_TEMPORAL_METADATA_NOT_MARKET_HISTORY"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macro-root", type=Path, required=True)
    parser.add_argument("--macro-commit", required=True)
    parser.add_argument("--rows", type=int, nargs="+", default=[2000, 63000])
    args = parser.parse_args()
    for count in args.rows:
        positive_count(count)
    owner, identity = load_owner(args.macro_root, args.macro_commit)
    cases = contract_cases(owner)
    report = {"schema": "market_experience.f0_probe.v1", "evidence_class": "OWNER_CONTRACT_MICROBENCHMARK_ONLY",
              "observed_at": datetime.now(timezone.utc).isoformat(), "owner": identity,
              "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "python": sys.version.split()[0], "platform": sys.platform,
              "contract_cases": cases, "measurements": [measure(owner, n) for n in args.rows],
              "production_data_admitted": 0, "model_calls": 0, "spend_usd": 0,
              "unmeasured": ["licensed corpus coverage", "document extraction", "token distribution",
                             "real source bytes", "per-accepted-record cost", "graph query performance",
                             "feature construction", "forecast quality", "fleet throughput"]}
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if all(case["passed"] for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only T3 attempt-fleet snapshot (``mastermind.t3_attempt_fleet/v1``).

Composes the closed projection with one real process census against the
default durable adapter state path (or ``--adapter-state``), optionally with a
saved thread read (``--thread-read-json``) and/or a saved census
(``--census-json``) instead of a live ``ps``.

This tool NEVER launches, interrupts, kills or sends to anything: it opens the
adapter state SQLite file read-only (``mode=ro``), runs one bounded ``ps``
(argv only), and prints the projection as JSON on stdout.  Exit code is 0
always — unknowns and typed refusals are printed honestly in the document
(``refusal`` key), never signaled by crash or non-zero exit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.t3_attempt_fleet_projection import (  # noqa: E402
    FLEET_SCHEMA,
    T3AttemptFleetError,
    T3ThreadReadPort,
    project_fleet,
    read_adapter_attempt_rows,
)
from control_plane.t3_execution_adapter import default_t3_adapter_state_path
from control_plane.t3_process_census import take_census


def _saved_thread_reads(path: str | None) -> T3ThreadReadPort | None:
    """Saved ``t3_thread_read`` results as a port.

    Accepted shapes (closed): ``{"threads": {<thread_id>: {thread_id, run_id,
    native_status, read_at_utc}, ...}}`` or one single such object.
    """
    if path is None:
        return None
    from control_plane.t3_attempt_fleet_projection import SavedThreadReads

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("threads"), dict):
        facts = raw["threads"]
    elif isinstance(raw, dict):
        facts = {str(raw.get("thread_id")): raw}
    else:
        raise SystemExit("t3_attempt_fleet: THREAD_READ_FILE_INVALID")
    try:
        return SavedThreadReads(facts)
    except T3AttemptFleetError as exc:
        raise SystemExit(f"t3_attempt_fleet: {exc.code}") from None


def _saved_census(path: str | None):
    if path is None:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("t3_attempt_fleet: CENSUS_FILE_INVALID")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="t3_attempt_fleet_snapshot",
        description="Read-only per-attempt T3 fleet projection; never "
        "launches, interrupts or sends to anything.",
    )
    parser.add_argument(
        "--adapter-state",
        default=str(default_t3_adapter_state_path()),
        help="Durable t3 adapter state SQLite file (read-only open).",
    )
    parser.add_argument(
        "--thread-read-json",
        default=None,
        help="Saved t3_thread_read result(s) as JSON (offline composition).",
    )
    parser.add_argument(
        "--census-json",
        default=None,
        help="Saved mastermind.t3_process_census/v1 document instead of a "
        "live ps observation.",
    )
    parser.add_argument(
        "--freshness-window-s",
        type=float,
        default=45.0,
        help="Evidence freshness window in seconds (default 45).",
    )
    args = parser.parse_args(argv)

    document: dict
    try:
        rows = read_adapter_attempt_rows(args.adapter_state)
        census = (
            _saved_census(args.census_json)
            if args.census_json is not None
            else take_census()
        )
        thread_reads = _saved_thread_reads(args.thread_read_json)
        document = project_fleet(
            rows,
            thread_read_port=thread_reads,
            census=census,
            freshness_window_s=args.freshness_window_s,
        )
    except T3AttemptFleetError as exc:
        # Fail-closed, honest refusal: no partial projection of corrupt or
        # unreadable evidence.  Still exit 0 (documented contract).
        document = {
            "schema": FLEET_SCHEMA,
            "refusal": exc.code,
            "attempts": [],
        }
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

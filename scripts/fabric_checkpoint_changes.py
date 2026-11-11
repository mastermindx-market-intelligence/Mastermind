"""Compare two existing Fabric JSON exports; no Runtime or provider access.

Run: python -m scripts.fabric_checkpoint_changes --before old.json --after new.json
Exit 0: complete net comparison; 2: partial/unavailable; 1: invalid input.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any
from control_plane.fabric_checkpoint_changes import MAX_CHANGES, MAX_INPUT_BYTES, compare_fabric_snapshots


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite_json_number")


def _read_export(path: str) -> dict:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("export_over_budget")
    document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_reject_constant)
    if not isinstance(document, dict):
        raise ValueError("export_must_be_object")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare one Executive root's existing Fabric v2 exports. "
        "Net changes only; not event replay, a native-session census, or an action grant.")
    parser.add_argument("--before", required=True, help="Earlier authorized Fabric v2 JSON export")
    parser.add_argument("--after", required=True, help="Later authorized export of the same root/source")
    parser.add_argument("--limit", type=int, default=MAX_CHANGES, help="Maximum changes, 1..128")
    args = parser.parse_args(argv)
    try:
        result = compare_fabric_snapshots(_read_export(args.before), _read_export(args.after), limit=args.limit)
    except (OSError, UnicodeError, ValueError, RecursionError):
        print(json.dumps({"schema": "mastermind.fabric_checkpoint_changes.error.v1",
                          "state": "INVALID_INPUT", "reason": "invalid_or_unreadable_snapshot_export"}))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["state"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

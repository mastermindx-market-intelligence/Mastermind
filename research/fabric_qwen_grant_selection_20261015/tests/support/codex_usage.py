"""Parse cumulative token usage from a private Codex scratch home."""

import argparse
import json
import pathlib
import sys


def _result(
    reason,
    session_ids=(),
    status="unknown",
    counters=None,
    *,
    include_compactions=False,
    native_compaction_records=None,
):
    counters = counters or {}
    result = {
        "schema": "mastermind.codex_usage.v1",
        "status": status,
        "reason": reason,
        "session_ids": sorted(session_ids),
        "input_tokens": counters.get("input_tokens"),
        "cached_tokens": counters.get("cached_tokens"),
        "output_tokens": counters.get("output_tokens"),
        "total_tokens": counters.get("total_tokens"),
        "source": "codex_native_session",
        "served_model": None,
    }
    # Explicit v2 opt-in preserves every incumbent v1 caller and its strict
    # validator until the matching transport revision is tested and admitted.
    if include_compactions:
        result["schema"] = "mastermind.codex_usage.v2"
        result["native_compaction_records"] = (
            native_compaction_records if status == "observed" else None
        )
    return result


def _nonnegative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _snapshot(info):
    usage = info.get("total_token_usage")
    if not isinstance(usage, dict):
        return None

    names = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
    )
    if any(name not in usage for name in names):
        return None

    values = {name: usage.get(name) for name in names}
    if any(not _nonnegative_integer(value) for value in values.values()):
        return None
    if values["cached_input_tokens"] > values["input_tokens"]:
        return None
    expected_total = values["input_tokens"] + values["output_tokens"]
    if values["total_tokens"] != expected_total:
        return None

    return {
        "total_tokens": values["total_tokens"],
        "input_tokens": values["input_tokens"],
        "cached_tokens": values["cached_input_tokens"],
        "output_tokens": values["output_tokens"],
    }


def _iter_session_files(sessions_root):
    for path in sessions_root.rglob("*.jsonl"):
        if path.is_symlink():
            continue
        path = path.resolve(strict=True)
        if not path.is_relative_to(sessions_root):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def summarize_usage(root: pathlib.Path, *, include_compactions: bool = False) -> dict:
    """Return a strict v1 receipt, or explicitly requested v2 native-event receipt."""
    def finish(reason, session_ids=(), status="unknown", counters=None, compactions=None):
        return _result(
            reason, session_ids, status=status, counters=counters,
            include_compactions=include_compactions,
            native_compaction_records=compactions,
        )

    try:
        supplied_root = pathlib.Path(root)
        if supplied_root.is_symlink():
            return finish("root_symlink")
        resolved_root = pathlib.Path(root).resolve(strict=True)
        if resolved_root.is_symlink():
            return finish("root_symlink")
        sessions_root = resolved_root / "sessions"
        if not sessions_root.is_dir() or sessions_root.is_symlink():
            return finish("missing_sessions_dir")

        identities = set()
        snapshots = {}
        native_compactions = {}
        saw_path = False
        for path in _iter_session_files(sessions_root):
            saw_path = True
            session_id = None
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if not isinstance(event, dict):
                        continue

                    if event.get("type") == "session_meta":
                        payload = event.get("payload")
                        if (
                            isinstance(payload, dict)
                            and isinstance(payload.get("id"), str)
                            and payload["id"]
                        ):
                            session_id = payload["id"]
                            identities.add(session_id)
                            snapshots.setdefault(session_id, [])
                            native_compactions.setdefault(session_id, 0)

                    # Count only native durable rollout checkpoint records.
                    # A token_count event or a claimed report is not proof of
                    # compaction. Unknown / malformed payloads do not count.
                    if session_id is not None and event.get("type") == "compacted":
                        payload = event.get("payload")
                        if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                            native_compactions[session_id] += 1
                        continue
                    if session_id is None or event.get("type") != "event_msg":
                        continue
                    payload = event.get("payload")
                    if not isinstance(payload, dict) or payload.get("type") != "token_count":
                        continue
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue
                    snapshot = _snapshot(info)
                    if snapshot is not None:
                        snapshots[session_id].append(snapshot)

        if not saw_path:
            return finish("empty_sessions_dir")
        if not identities:
            return finish("no_valid_snapshot")
        if len(identities) > 1:
            return finish("multiple_session_ids", identities)

        session_id = next(iter(identities))
        session_snapshots = snapshots[session_id]
        if not session_snapshots:
            return finish("no_valid_snapshot", [session_id])

        max_total = max(snapshot["total_tokens"] for snapshot in session_snapshots)
        best = [snapshot for snapshot in session_snapshots if snapshot["total_tokens"] == max_total]
        if any(snapshot != best[0] for snapshot in best[1:]):
            return finish("contradictory_snapshots", [session_id])
        return finish(
            "cumulative_native_session",
            [session_id],
            status="observed",
            counters=best[0],
            compactions=native_compactions[session_id],
        )
    except (OSError, ValueError, RuntimeError):
        return finish("io_error")


def main() -> None:
    """Emit one JSON result without a traceback."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=pathlib.Path)
    parser.add_argument("--run-id", default=None)
    # Explicit opt-in; legacy callers keep the exact v1 schema.
    parser.add_argument("--with-native-compactions", action="store_true")
    args = parser.parse_args()
    result = summarize_usage(args.root, include_compactions=args.with_native_compactions)
    if args.run_id is not None:
        result["run_id"] = args.run_id
    print(json.dumps(result))


if __name__ == "__main__":
    main()

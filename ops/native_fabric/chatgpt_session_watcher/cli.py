#!/usr/bin/env python3
"""Spawn and run the ChatGPT web session watcher.

Default mode is observe. Live browser effects require MMX_WATCHER_ALLOW_LIVE=1
on m2studio and are still refused here when that variable is unset.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loop import run_cycle
from registration import KIND, MODEL, POOL, TASK_CLASS
from stores import RUN_SCHEMA, WatcherStores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChatGPT web session watcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_state(command: argparse.ArgumentParser) -> None:
        command.add_argument("--state-dir", required=True)

    status = sub.add_parser("status")
    add_state(status)
    status.add_argument("--run-id", required=True)

    result = sub.add_parser("result")
    add_state(result)
    result.add_argument("--run-id", required=True)

    register = sub.add_parser("register")

    spawn = sub.add_parser("spawn")
    add_state(spawn)
    spawn.add_argument("--run-id", required=True)
    spawn.add_argument("--root", required=True)
    spawn.add_argument("--parent", required=True)
    spawn.add_argument("--stdin", action="store_true")
    spawn.add_argument("--fixtures")

    cycle = sub.add_parser("cycle")
    add_state(cycle)
    cycle.add_argument("--mode", default="observe", choices=("observe", "live"))
    cycle.add_argument("--fixtures")

    serve = sub.add_parser("serve")
    add_state(serve)
    serve.add_argument("--mode", default="observe", choices=("observe", "live"))
    serve.add_argument("--fixtures")
    serve.add_argument("--max-cycles", type=int, default=1)
    serve.add_argument("--interval-seconds", type=int, default=1800)

    args = parser.parse_args(argv)
    if args.cmd == "register":
        _json({
            "schema": "mastermind.fabric_worker_kind.v1",
            "kind": KIND,
            "task_class": TASK_CLASS,
            "pool": POOL,
            "model": MODEL,
            "default_mode": "observe",
        })
        return 0
    state = Path(args.state_dir)
    stores = WatcherStores(state)
    if args.cmd == "status":
        _json(stores.runs.read(args.run_id))
        return 0
    if args.cmd == "result":
        path = state / "results" / f"{args.run_id}.json"
        if not path.exists():
            _json({"schema": RUN_SCHEMA, "run_id": args.run_id, "state": "RESULT_UNAVAILABLE", "result_available": False})
            return 2
        sys.stdout.write(path.read_text(encoding="utf-8"))
        return 0
    if args.cmd == "spawn":
        return _spawn(stores, state, args)
    observations = _load_fixtures(args.fixtures) if args.fixtures else {}
    cycles = 1 if args.cmd == "cycle" else max(1, args.max_cycles)
    report = None
    for index in range(cycles):
        report = run_cycle(stores, observations, mode=args.mode)
        if index + 1 < cycles and args.interval_seconds > 0:
            import time
            time.sleep(args.interval_seconds)
    _json(report)
    return 0


def _spawn(stores: WatcherStores, state: Path, args) -> int:
    packet = _packet(sys.stdin.read() if args.stdin else "")
    current = stores.runs.read(args.run_id)
    if current.get("state") != "NOT_FOUND":
        if current.get("root_id") not in (None, args.root):
            current["state"] = "EFFECT_UNKNOWN"
        else:
            current["state"] = "RUN_EXISTS"
        _json(current)
        return 2
    stores.runs.write(args.run_id, _status(args, "ACTIVE_OR_WAITING", result=False))
    observations = _load_fixtures(args.fixtures) if args.fixtures else {}
    try:
        report = run_cycle(stores, observations, mode=packet["mode"])
    except Exception:
        stores.runs.write(args.run_id, _status(args, "EFFECT_UNKNOWN", result=False))
        _json({"schema": RUN_SCHEMA, "run_id": args.run_id, "state": "EFFECT_UNKNOWN", "result_available": False})
        return 1
    report["brief"] = packet.get("brief") or ""
    result_path = state / "results" / f"{args.run_id}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stores.runs.write(args.run_id, _status(args, "TERMINAL", result=True, rc=0, signal="ok"))
    _json(report)
    return 0


def _status(args, state: str, *, result: bool, rc: int | None = None, signal: str | None = None) -> dict:
    return {
        "schema": RUN_SCHEMA,
        "run_id": args.run_id,
        "root_id": args.root,
        "parent_run_id": args.parent,
        "state": state,
        "rc": rc,
        "signal": signal,
        "result_available": result,
        "accepted": False,
        "worker_kind": KIND,
        "pool": POOL,
        "model": MODEL,
        "mode": "observe",
    }


def _packet(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {"mode": "observe", "brief": ""}
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return {"mode": "observe", "brief": raw[:2000]}
    if not isinstance(doc, dict):
        return {"mode": "observe", "brief": ""}
    mode = doc.get("mode") if doc.get("mode") in {"observe", "live"} else "observe"
    brief = doc.get("brief") if isinstance(doc.get("brief"), str) else ""
    return {"mode": mode, "brief": brief[:2000]}


def _load_fixtures(path: str) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("fixtures must be an object of profile to rows")
    return doc


def _json(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

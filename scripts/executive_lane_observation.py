"""Fixture-only consumer for the Executive recorded-lane source proposal.

No installed path, socket, provider session, MCP connection or daemon option.
Run: python -m scripts.executive_lane_observation demo --format text
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Sequence

from control_plane.executive_lane_observation import observe_root_lanes
from control_plane.executive_runtime import Runtime


def demonstration() -> dict:
    """Exercise real Runtime APIs in a temporary fixture and remove it on return."""
    with tempfile.TemporaryDirectory(prefix="mmx-lane-demo-") as temporary:
        root = Path(temporary)
        writer = Runtime.at(root)
        parent = writer.jobs.create_job("Synthetic office parent")
        first = writer.jobs.create_job("Synthetic first lane", parent_job_id=parent.job_id)
        writer.jobs.create_job("Synthetic second lane", parent_job_id=parent.job_id)
        writer.workers.register_worker("fixture-worker", provider="codex",
            account_label="fixture-account", worker_type="fixture", capabilities=["research"])
        lease = writer.attempts.claim_job(first.job_id, worker_id="fixture-worker")
        if lease is None:
            raise RuntimeError("fixture claim failed")
        observation = observe_root_lanes(Runtime.at(root, create=False), parent.job_id)
        return {"proof_class": "FIXTURE_ONLY_NO_PROVIDER_EXECUTION", "observation": observation}


def render_text(payload: dict) -> str:
    document = payload["observation"]
    coverage = document["coverage"]
    count = coverage["returned_count"]
    lines = [payload["proof_class"],
        f"Recorded Executive lanes: {document['status']}; root {document['root_job_id']}",
        f"Coverage: {coverage['completeness']}; rows {count if count is not None else 'unknown'}"]
    for lane in document["lanes"] or []:
        attempt = lane["current_attempt"]
        detail = (f"{attempt['attempt_id']} {attempt['status']} worker={attempt['worker_id']}"
                  if attempt is not None else "no current Attempt recorded")
        lines.append("  " * lane["depth"] + f"{lane['job_id']} {lane['job_status']} | {detail}")
        if lane["issues"]:
            lines.append("  " * lane["depth"] + "  gaps: " + ", ".join(lane["issues"]))
    lines.append("Native sessions, bindings, effects and current permission are NOT ATTESTED.")
    if document["issues"]:
        lines.append("Read issues: " + ", ".join(document["issues"]))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run only a disposable synthetic Runtime.")
    demo.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)
    try:
        payload = demonstration()
    except Exception:
        print(json.dumps({"proof_class": "FIXTURE_ONLY_NO_PROVIDER_EXECUTION",
                          "error": "DEMO_UNAVAILABLE"}, sort_keys=True))
        return 1
    print(json.dumps(payload, sort_keys=True) if args.format == "json" else render_text(payload))
    return 0 if payload["observation"]["status"] == "OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

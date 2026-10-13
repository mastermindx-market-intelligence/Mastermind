#!/usr/bin/env python3
"""Read-only consistency checks for this design package, not runtime acceptance.

Uses local Git objects; no network, provider, credential, installation or dispatch.
Reports explicit held deliverables instead of manufacturing complete-design PASS.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIN = "17b9fa1363db6071d338be3373a4fdb11fc0076d"
BRIEF = ROOT / "docs/CLAUDE_CAPABILITY_HARDENING_BUILD_HANDOFFS_2026-10-04.md"
BRIEF_SHA = "07d74eae587c4b7649dcaab87f57222a4274f8759e76ba94225fd36789556dfc"
PACKETS = {
    "H1": "H1_RICH_PRINCIPAL.md", "H2": "H2_PROJECTION_PARITY.md",
    "H3": "H3_COO_PLUGIN.md", "H4": "H4_FABRIC.md",
    "H5": "H5_CI_CONTINUATION.md", "H6": "H6_CONTEXT_DIALOGUE.md",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(name: str) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value
    return json.loads((HERE / name).read_text(), object_pairs_hook=unique)


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], timeout=15)


def verify() -> dict:
    sources = read_json("SOURCE_REGISTER.json")
    require(sources["protected_source_pin"] == PIN, "source pin drift")
    entries = sources["entries"]
    source_ids = {row["id"] for row in entries}
    require(len(entries) == len(source_ids) == 36, "expected 36 verified source anchors")
    for row in entries:
        require(row["commit"] == PIN, "mixed source revisions")
        data = git("show", f"{PIN}:{row['path']}")
        require(hashlib.sha256(data).hexdigest() == row["sha256"], "source content drift")
        require(git("rev-parse", f"{PIN}:{row['path']}").decode().strip() == row["blob_sha"], "blob drift")
        require(1 <= row["start_line"] <= row["end_line"] <= len(data.decode().splitlines()), "bad source range")
    require(hashlib.sha256(BRIEF.read_bytes()).hexdigest() == BRIEF_SHA, "original handoff changed")
    for filename in PACKETS.values():
        require((HERE / filename).is_file(), f"missing packet {filename}")
    # The denied browser packet was not recreated via another carrier.
    require(not (HERE / "H7_BROWSER.md").exists(), "held browser-packet state changed: reconcile explicitly")
    cases = read_json("ACCEPTANCE_CASES.json")
    require(cases["cases_are_executed"] is False, "planned cases cannot claim execution")
    rows = cases["cases"]
    require(len(rows) == len({r["id"] for r in rows}) == 80, "case inventory drift")
    counts = collections.Counter(r["handoff"] for r in rows)
    require(counts == {**{h: 12 for h in PACKETS}, "H7": 8}, "handoff coverage differs")
    for row in rows:
        require(row["execution_result"] == "NOT_RUN", "unproven planned result")
        require(set(row["source_ids"]) <= source_ids, "unknown source reference")
        require(row["level"] in {"unit", "integration", "native"}, "unknown test level")
        require(bool(row["scenario"]) and bool(row["expected"]), "empty acceptance case")
        if row["handoff"] == "H7":
            require(row["basis"] == "original_handoff_only_detailed_packet_write_held", "H7 overclaim")
    graph = read_json("EXECUTION_GRAPH.json")
    require(graph["runtime_effects_authorized"] is False, "design cannot authorize dispatch")
    nodes = {row["id"]: row for row in graph["nodes"]}
    require(len(nodes) == len(graph["nodes"]) == 16, "graph identity mismatch")
    require({"W05", "W06", "W07"} <= set(nodes["W11"]["depends_on"]), "joint proof needs current admission and dialogue")
    require("W11" in nodes["W12"]["depends_on"], "dialogue evidence review must follow the live joint proof")
    visited, active, order = set(), set(), []
    def visit(key):
        require(key in nodes, f"unknown dependency {key}")
        require(key not in active, "dependency cycle")
        if key in visited:
            return
        active.add(key)
        for dep in nodes[key]["depends_on"]:
            visit(dep)
        active.remove(key)
        visited.add(key)
        order.append(key)
    for key, row in nodes.items():
        require(row["execution_state"] == "NOT_DISPATCHED_BY_THIS_PACKAGE", "fictional dispatch")
        visit(key)
    links = 0
    for path in HERE.glob("*.md"):
        text = path.read_text()
        require(text.count("```") % 2 == 0, f"unbalanced code fence: {path.name}")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://", "#")):
                continue
            relative = target.split("#", 1)[0]
            require((path.parent / relative).resolve().exists(), f"missing local link {path.name}: {target}")
            links += 1
    return {
        "structural_verification": "PASS_WITH_EXPLICIT_HOLDS",
        "source_pin": PIN, "verified_source_anchors": len(entries),
        "original_handoff_sha256": BRIEF_SHA, "detailed_packets": sorted(PACKETS),
        "planned_acceptance_cases": len(rows), "new_acceptance_cases_executed": 0,
        "dependency_nodes": len(nodes), "topological_order": order,
        "verified_local_links": links, "design_complete": False,
        "native_acceptance_proven": False,
        "held": ["detailed H7 source-file write denied before dispatch",
                 "two-entry source-register extension denied before dispatch"],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), sort_keys=True, indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"structural_verification": "FAIL", "error": str(exc)}))
        sys.exit(1)

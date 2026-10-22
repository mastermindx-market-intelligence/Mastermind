#!/usr/bin/env python3
"""Read-only, deterministic migration planning for an observed Paper file inventory.

Never connects to Paper, opens a browser, performs a mutation, or authorizes deletion.
Node/artboard budgets are planning heuristics, NOT vendor limits or transfer proof.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SOURCE_FILE_ID = "01M2WGNCX9475G79JRKJTCM08P"
SOURCE_PREFIX = f"https://app.paper.design/file/{SOURCE_FILE_ID}/"
EXPECTED_STATUS = "SOURCE_OBSERVED_NOT_MIGRATED"
DEFAULT_NODE_TARGET = 6000
DEFAULT_ARTBOARD_TARGET = 32


class InventoryError(ValueError):
    """Inventory or planning evidence is incomplete, inconsistent, or stale."""


def inventory_fingerprint(inventory: dict) -> str:
    canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_inventory(inventory: dict) -> list[dict]:
    if not isinstance(inventory, dict) or inventory.get("source_file_id") != SOURCE_FILE_ID:
        raise InventoryError("Incorrect original Paper file identity")
    pages = inventory.get("pages")
    if not isinstance(pages, list) or not pages:
        raise InventoryError("Expected a nonempty page inventory")
    seen = set()
    nodes = boards = 0
    for row in pages:
        if not isinstance(row, dict):
            raise InventoryError("Invalid page inventory row")
        page_id = row.get("source_page_id")
        if not isinstance(page_id, str) or not re.fullmatch(r"p-[A-Za-z0-9]+-[0-9]+", page_id):
            raise InventoryError("Malformed source page ID")
        if page_id in seen:
            raise InventoryError(f"Duplicate source page: {page_id}")
        seen.add(page_id)
        if row.get("source_file_id") != SOURCE_FILE_ID or row.get("source_url") != SOURCE_PREFIX + page_id:
            raise InventoryError(f"Wrong exact-file link: {page_id}")
        if row.get("status") != EXPECTED_STATUS:
            raise InventoryError(f"Unexpected transfer status or invented migration proof: {page_id}")
        for field in ("suggested_destination", "name_transcribed"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                raise InventoryError(f"Invalid {field} on {page_id}")
        n = row.get("node_count")
        b = row.get("artboard_count")
        if type(n) is not int or type(b) is not int or n < 1 or b < 1:
            raise InventoryError(f"Invalid observed node/artboard count on {page_id}")
        nodes += n
        boards += b
    if (inventory.get("inventory_count"), inventory.get("total_observed_nodes"),
            inventory.get("total_observed_artboards")) != (len(pages), nodes, boards):
        raise InventoryError("Inventory totals mismatch observed page rows")
    if "p-19-0" in seen:
        raise InventoryError("p-19-0 was not reconciled; do not silently reintroduce")
    return pages


def slugify(text: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    if not result:
        raise InventoryError("Destination name has no usable slug")
    return result


def make_plan(inventory: dict, node_target: int = DEFAULT_NODE_TARGET,
              artboard_target: int = DEFAULT_ARTBOARD_TARGET) -> dict:
    pages = validate_inventory(inventory)
    if type(node_target) is not int or type(artboard_target) is not int or node_target <= 0 or artboard_target <= 0:
        raise InventoryError("Planning targets must be positive integer heuristics")
    groups = defaultdict(list)
    for row in pages:
        groups[row["suggested_destination"]].append(row)
    destinations = []
    assignments = []
    held = []
    for family in sorted(groups, key=str.casefold):
        slug = slugify(family)
        volumes = []
        # FFD is deterministic even if the input row ordering changes.
        ordered = sorted(groups[family], key=lambda r: (-r["node_count"], -r["artboard_count"], r["source_page_id"]))
        for row in ordered:
            page_id, n, b = row["source_page_id"], row["node_count"], row["artboard_count"]
            if n > node_target or b > artboard_target:
                held.append({
                    "source_page_id": page_id,
                    "source_url": row["source_url"],
                    "destination_family": family,
                    "observed_nodes": n,
                    "observed_artboards": b,
                    "reason": "ARTBOARD_LEVEL_CENSUS_AND_SPLIT_REQUIRED",
                    "minimum_node_partitions_only": (n + node_target - 1) // node_target,
                    "minimum_board_partitions_only": (b + artboard_target - 1) // artboard_target,
                    "note": "Lower bounds are not a feasible transfer plan; actual per-artboard sizes and dependencies are unknown."
                })
                continue
            chosen = next((v for v in volumes if v["planned_nodes"] + n <= node_target
                           and v["planned_artboards"] + b <= artboard_target), None)
            if chosen is None:
                chosen = {"volume": len(volumes) + 1, "planned_nodes": 0,
                          "planned_artboards": 0, "source_page_ids": []}
                volumes.append(chosen)
            chosen["planned_nodes"] += n
            chosen["planned_artboards"] += b
            chosen["source_page_ids"].append(page_id)
            assignments.append({"source_page_id": page_id, "source_url": row["source_url"],
                                "destination_family": family,
                                "proposed_volume": chosen["volume"],
                                "state": "PLANNED_ONLY_NO_PAPER_EFFECT"})
        for volume in volumes:
            volume["source_page_ids"].sort()
            volume["proposed_file_title"] = f"MASTERMIND | {slug} | Vol {volume['volume']:02d}"
        destinations.append({"family": family, "family_slug": slug, "volumes": volumes,
                             "held_pages_for_artboard_census": sorted(
                                 h["source_page_id"] for h in held if h["destination_family"] == family)})
    assigned_ids = {row["source_page_id"] for row in assignments}
    held_ids = {row["source_page_id"] for row in held}
    expected_ids = {row["source_page_id"] for row in pages}
    if assigned_ids & held_ids or assigned_ids | held_ids != expected_ids:
        raise InventoryError("Planner omitted, duplicated, or misclassified a source page")
    if len({d["family_slug"] for d in destinations}) != len(destinations):
        raise InventoryError("Colliding destination slugs")
    assignments.sort(key=lambda r: r["source_page_id"])
    held.sort(key=lambda r: r["source_page_id"])
    return {
        "schema": "mastermind.paper-migration-offline-plan.v1",
        "classification": "READ_ONLY_PREFLIGHT_NOT_TRANSFER_OR_DELETE_AUTHORITY",
        "source_file_id": SOURCE_FILE_ID,
        "source_inventory_sha256": inventory_fingerprint(inventory),
        "source_observed_date": inventory.get("observed_date"),
        "source_warning": inventory.get("warning_observed"),
        "planning_heuristics_not_vendor_limits": {
            "max_nodes_per_proposed_volume": node_target,
            "max_artboards_per_proposed_volume": artboard_target},
        "counts": {"source_pages": len(pages), "whole_page_planning_candidates": len(assignments),
                   "pages_requiring_artboard_census": len(held),
                   "proposed_whole_page_volumes": sum(len(d["volumes"]) for d in destinations),
                   "source_nodes": inventory["total_observed_nodes"],
                   "source_artboards": inventory["total_observed_artboards"]},
        "destinations": destinations,
        "whole_page_assignments": assignments,
        "pages_requiring_artboard_census": held,
        "unresolved_drift": [{"source_page_id": "p-19-0",
                              "classification": "ABSENT_FROM_LATER_SOURCE_READ_NOT_PROVEN_DELETED",
                              "required_action": "Reconcile vendor history and concurrent Paper editor before any source cleanup"}],
        "required_before_any_mutation": [
            "Fresh exact-source read, explicit live editor coordination and source snapshot guard",
            "Independently verified source backup/version history and recovery test",
            "Qualified exact adapter or vendor UI tool for the precise copy/move/delete operation",
            "Confirmed empty or independently readback-verifiable destination file and immutable target ID",
            "A single admitted modifying carrier and correlation ID per logical effect"],
        "required_before_source_removal": [
            "Every destination content copied as editable native nodes, not exported JSX or screenshots",
            "Exact artboard mapping including hidden, states, sizes, nesting, components and typography",
            "Token, image, external asset, link, interaction and comment fidelity inspected",
            "Screenshot comparisons independently reviewed; file reopened using actual target ID",
            "All downstream page/artboard links rewritten and independently verified",
            "No unresolved effects, stale snapshots or p-19-0 anomaly; backup recovery verified",
            "Source delete supported by a separately reviewed vendor tool and approved target scope"],
        "source_deletion_authorized": False,
        "paper_files_created": 0,
        "paper_pages_moved": 0
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Write only the offline JSON plan; never contacts Paper")
    parser.add_argument("--check-plan", type=Path, help="Compare a saved plan to regenerated source fingerprint")
    parser.add_argument("--node-target", type=int, default=DEFAULT_NODE_TARGET)
    parser.add_argument("--artboard-target", type=int, default=DEFAULT_ARTBOARD_TARGET)
    args = parser.parse_args(argv)
    if args.out and args.check_plan:
        parser.error("--out and --check-plan cannot be combined")
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        plan = make_plan(inventory, args.node_target, args.artboard_target)
        if args.check_plan:
            observed = json.loads(args.check_plan.read_text(encoding="utf-8"))
            if observed != plan:
                raise InventoryError("Plan mismatch/stale inventory or altered destination plan")
            print("PASS: offline plan reproduces exactly; NOT transfer or source-deletion permission")
        else:
            serialized = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
            if args.out:
                args.out.write_text(serialized, encoding="utf-8")
                print(f"Wrote read-only proposal: {args.out}")
            else:
                print(serialized, end="")
        return 0
    except (OSError, json.JSONDecodeError, InventoryError) as exc:
        print(f"MIGRATION_PREFLIGHT_REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

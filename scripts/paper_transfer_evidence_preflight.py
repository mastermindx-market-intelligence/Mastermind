#!/usr/bin/env python3
"""Read-only structural preflight for Paper cross-file transfer mapping claims.

This is intentionally not a deletion gate or live Paper proof. It cannot accept
source cleanup. A passing report only shows internally consistent identifiers
against the observed source/visibility/artboard inventories.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from paper_migration_planner import inventory_fingerprint, validate_inventory, validate_visibility_delta, InventoryError

FILE_ID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
PAGE_ID = re.compile(r"^p-[A-Za-z0-9]+-[0-9]+$")
ARTBOARD_ID = re.compile(r"^[A-Z0-9]{3,5}-[0-9]+$")
SCHEMA = "mastermind.paper-transfer-evidence-preflight.v1"


def validate_evidence_manifest(inventory: dict, visibility_delta: dict, artboard_index: dict, claim: dict) -> dict:
    pages = validate_inventory(inventory)
    absent = validate_visibility_delta(inventory, visibility_delta)
    known_pages = {p["source_page_id"] for p in pages}
    if not isinstance(artboard_index, dict) or artboard_index.get("schema") != "mastermind.paper-oversize-artboard-index.v1" or artboard_index.get("source_file_id") != inventory["source_file_id"]:
        raise InventoryError("Wrong or unqualified heavy-page artboard identity index")
    artboards = {}
    for page in artboard_index.get("pages", []):
        pid = page.get("source_page_id")
        if pid not in known_pages:
            raise InventoryError("Heavy-page index refers to an unknown source page")
        declared = page.get("artboard_count")
        rows = page.get("artboards")
        if type(declared) is not int or not isinstance(rows, list) or len(rows) != declared:
            raise InventoryError("Heavy-page artboard index is incomplete or capped")
        if pid in artboards:
            raise InventoryError("Repeated heavy page in artboard index")
        ids = [r.get("source_artboard_id") for r in rows]
        if len(ids) != len(set(ids)) or any(not isinstance(x, str) or not ARTBOARD_ID.fullmatch(x) for x in ids):
            raise InventoryError("Duplicate or invalid indexed source artboard ID")
        artboards[pid] = set(ids)
    if len(artboards) < 1:
        raise InventoryError("No qualified source artboard index")
    if not isinstance(claim, dict) or claim.get("schema") != SCHEMA:
        raise InventoryError("Unknown transfer evidence schema")
    if claim.get("source_file_id") != inventory["source_file_id"]:
        raise InventoryError("Wrong source file ID")
    if claim.get("source_inventory_sha256") != inventory_fingerprint(inventory):
        raise InventoryError("Stale source inventory digest")
    if claim.get("source_visibility_delta_sha256") != inventory_fingerprint(visibility_delta):
        raise InventoryError("Stale source visibility delta digest")
    units = claim.get("units")
    if not isinstance(units, list) or len(units) < 1:
        raise InventoryError("No transfer mapping units")
    source_keys, target_keys, operation_keys = set(), set(), set()
    held = []
    for i, unit in enumerate(units):
        if not isinstance(unit, dict):
            raise InventoryError(f"Unit {i}: invalid object")
        src_page = unit.get("source_page_id")
        src_board = unit.get("source_artboard_id")
        dst_file = unit.get("destination_file_id")
        dst_page = unit.get("destination_page_id")
        dst_board = unit.get("destination_artboard_id")
        if src_page not in known_pages:
            raise InventoryError(f"Unit {i}: unknown source page")
        if src_page in absent:
            raise InventoryError(f"Unit {i}: source page absent in later file; reconcile incumbent effect")
        if not isinstance(src_board, str) or not ARTBOARD_ID.fullmatch(src_board):
            raise InventoryError(f"Unit {i}: invalid source artboard ID")
        if src_page in artboards and src_board not in artboards[src_page]:
            raise InventoryError(f"Unit {i}: source artboard not in observed heavy-page index")
        if not isinstance(dst_file, str) or not FILE_ID.fullmatch(dst_file) or dst_file == inventory["source_file_id"]:
            raise InventoryError(f"Unit {i}: destination must be independent exact Paper file ID")
        if not isinstance(dst_page, str) or not PAGE_ID.fullmatch(dst_page):
            raise InventoryError(f"Unit {i}: destination page ID missing/invalid")
        if not isinstance(dst_board, str) or not ARTBOARD_ID.fullmatch(dst_board):
            raise InventoryError(f"Unit {i}: destination artboard ID missing/invalid")
        # Source artboard/page ID may be preserved by vendor; composite target identity is sufficient.
        source_key = (src_page, src_board)
        target_key = (dst_file, dst_page, dst_board)
        if source_key in source_keys or target_key in target_keys:
            raise InventoryError(f"Unit {i}: duplicate source or target mapping")
        source_keys.add(source_key)
        target_keys.add(target_key)
        op = unit.get("operation_id")
        if not isinstance(op, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", op) or op in operation_keys:
            raise InventoryError(f"Unit {i}: invalid/duplicate logical operation ID")
        operation_keys.add(op)
        if unit.get("transfer_mechanism") not in ("REVIEWED_NATIVE_EDITABLE_COPY",):
            raise InventoryError(f"Unit {i}: flattened/export/HTML/unknown mechanism is not lossless native transfer")
        if unit.get("effect_state") not in ("RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION", "READBACK_OBSERVED"):
            raise InventoryError(f"Unit {i}: uncertain, denied, or fabricated transfer effect state")
        proof = unit.get("evidence_refs")
        if not isinstance(proof, dict) or not isinstance(proof.get("source_read"), str) or not isinstance(proof.get("target_read"), str) or not proof["source_read"].strip() or not proof["target_read"].strip():
            raise InventoryError(f"Unit {i}: source and target read evidence references required")
        missing_kinds = [k for k in ("native_editability", "visual_comparison", "tokens", "assets", "components", "comments", "interactions")
                         if not isinstance(proof.get(k), str) or not proof[k].strip()]
        held.append({"source_page_id": src_page, "source_artboard_id": src_board,
                     "target_file_id": dst_file, "target_page_id": dst_page, "target_artboard_id": dst_board,
                     "source_index_qualified": src_page in artboards,
                     "evidence_kinds_still_missing": missing_kinds,
                     "requires_independent_native_verification": True})
    return {"schema": "mastermind.paper-transfer-structure-review.v1",
            "classification": "STRUCTURALLY_REVIEWED_NOT_NATIVE_OR_VISUAL_ACCEPTANCE",
            "source_file_id": inventory["source_file_id"],
            "units_checked": len(units), "units_needing_source_artboard_census": sum(not x["source_index_qualified"] for x in held),
            "units_needing_fidelity_evidence": sum(bool(x["evidence_kinds_still_missing"]) for x in held),
            "source_deletion_authorized": False,
            "unresolved_source_drift": True,
            "paper_effects_executed_by_validator": 0,
            "required_live_acceptance": "Independent source/target exact-ID reopened native proof, artifact verification and separate source cleanup authorization",
            "units": held}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("inventory", "visibility-delta", "heavy-artboards", "claim"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        load = lambda p: json.loads(p.read_text(encoding="utf-8"))
        result = validate_evidence_manifest(load(args.inventory), load(args.visibility_delta),
                                            load(args.heavy_artboards), load(args.claim))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, InventoryError) as exc:
        print(f"PAPER_TRANSFER_PREFLIGHT_REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

"""Read-only evidence guard for native Paper file clone + UI page-prune.

This module NEVER creates, moves, renames, or deletes any file/page/node. It
only binds the exact source and clone to a preflight plan, and independently
checks post-prune metadata. UI actuation is owned by the existing authorized
interactive carrier. This is NOT a second Paper gateway or deletion API.

Use the host's reviewed bridge.py on that same Paper Desktop installation.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable

# Reuse the repository's existing Paper bridge identity. Executing the helper
# as a module keeps the unrelated top-level `bridge` package untouched.
from integrations.paper_desktop import bridge

SCHEMA = "mastermind.paper_clone_prune_evidence.v1"
FILE_ID_RE = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}\Z")
OPERATION_RE = re.compile(r"[A-Za-z0-9_.:-]{1,120}\Z")


def _require_file_id(value: str) -> str:
    if not isinstance(value, str) or not FILE_ID_RE.fullmatch(value):
        raise bridge.Refusal("FILE_ID_REQUIRED")
    return value


def _pages(info: dict) -> list[dict]:
    raw = info.get("pages")
    if not isinstance(raw, list) or not raw:
        raise bridge.Refusal("PAGES_UNAVAILABLE")
    pages = []
    for page in raw:
        if not isinstance(page, dict) or page.get("type") != "page":
            raise bridge.Refusal("PAGE_LIST_UNSUPPORTED", "Dividers require separate planning.")
        page_id, name = page.get("id"), page.get("name")
        if not isinstance(page_id, str) or not page_id or not isinstance(name, str) or not name:
            raise bridge.Refusal("PAGE_SCHEMA_UNVERIFIED")
        pages.append({"type": "page", "id": page_id, "name": name, "icon": page.get("icon")})
    ids = [page["id"] for page in pages]
    if len(set(ids)) != len(ids):
        raise bridge.Refusal("DUPLICATE_PAGE_IDS")
    return pages


def _tokens_hash(info: dict):
    hashes = info.get("contentHash")
    if isinstance(hashes, dict) and isinstance(hashes.get("tokens"), str):
        return hashes["tokens"]
    return None


def _read(file_id: str, *, reader: Callable[[str], dict] | None = None) -> dict:
    file_id = _require_file_id(file_id)
    if reader is not None:
        info = reader(file_id)
    else:
        result = bridge.execute("read", tool="get_basic_info", arguments={"fileId": file_id})
        if result.get("state") != "OBSERVED":
            raise bridge.Refusal("DOCUMENT_UNAVAILABLE")
        info = (result.get("document") or {}).get("basic_info")
    if not isinstance(info, dict) or info.get("fileId") != file_id:
        raise bridge.Refusal("FILE_ID_MISMATCH")
    if not isinstance(info.get("fileName"), str) or not info["fileName"]:
        raise bridge.Refusal("FILE_NAME_REQUIRED")
    _pages(info)
    return info


def _read_native_page(file_id: str, page: dict, *,
                      page_reader: Callable[[str, str], dict] | None = None) -> dict:
    """Exact-page structural census, not complete style/asset equivalence."""
    page_id = page["id"]
    if page_reader is None:
        result = bridge.execute("read", tool="get_basic_info", arguments={
            "fileId": file_id, "pageId": page_id,
        })
        if result.get("state") != "OBSERVED":
            raise bridge.Refusal("NATIVE_PAGE_READ_UNAVAILABLE")
        info = (result.get("document") or {}).get("basic_info")
    else:
        info = page_reader(file_id, page_id)
    if (not isinstance(info, dict) or info.get("fileId") != file_id
            or info.get("pageId") != page_id or info.get("pageName") != page["name"]):
        raise bridge.Refusal("NATIVE_PAGE_IDENTITY_MISMATCH")
    nodes, count = info.get("nodeCount"), info.get("artboardCount")
    rows = info.get("artboards")
    if (type(nodes) is not int or nodes < 1 or type(count) is not int
            or count < 0 or not isinstance(rows, list)
            or len(rows) != count or info.get("truncated") is True):
        raise bridge.Refusal("NATIVE_PAGE_CENSUS_INCOMPLETE")
    boards = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not isinstance(row.get("name"), str)
                or type(row.get("childCount")) is not int or row["childCount"] < 0):
            raise bridge.Refusal("NATIVE_ARTBOARD_SCHEMA_UNVERIFIED")
        boards.append({"id": row["id"], "name": row["name"],
                       "childCount": row["childCount"]})
    if len({x["id"] for x in boards}) != len(boards):
        raise bridge.Refusal("NATIVE_ARTBOARD_ID_DUPLICATE")
    fonts = info.get("fontFamilies")
    if fonts is not None and (not isinstance(fonts, list)
                             or any(not isinstance(x, str) for x in fonts)):
        raise bridge.Refusal("NATIVE_FONT_FAMILY_SCHEMA_UNVERIFIED")
    return {"page_id": page_id, "node_count": nodes,
            "artboard_count": count, "artboards": boards,
            "font_families": sorted(fonts) if fonts is not None else None}


def make_plan(source_id: str, clone_id: str, keep_ids: list[str],
              operation_id: str, *, reader: Callable[[str], dict] | None = None,
              page_reader: Callable[[str, str], dict] | None = None) -> dict:
    source_id, clone_id = _require_file_id(source_id), _require_file_id(clone_id)
    if source_id == clone_id:
        raise bridge.Refusal("SOURCE_EQUALS_CLONE")
    if not isinstance(operation_id, str) or not OPERATION_RE.fullmatch(operation_id):
        raise bridge.Refusal("OPERATION_ID_REQUIRED")
    if not isinstance(keep_ids, list) or not keep_ids or any(not isinstance(p, str) for p in keep_ids):
        raise bridge.Refusal("KEEP_PAGE_IDS_REQUIRED")
    if len(keep_ids) != len(set(keep_ids)):
        raise bridge.Refusal("DUPLICATE_KEEP_PAGE_IDS")
    source, clone = _read(source_id, reader=reader), _read(clone_id, reader=reader)
    source_pages, clone_pages = _pages(source), _pages(clone)
    if source_pages != clone_pages:
        raise bridge.Refusal("CLONE_PAGE_LIST_MISMATCH",
                             "Preflight requires an intact full-file clone before pruning.")
    known_ids = {p["id"] for p in source_pages}
    if not set(keep_ids).issubset(known_ids):
        raise bridge.Refusal("UNKNOWN_KEEP_PAGE")
    removed = [p for p in source_pages if p["id"] not in keep_ids]
    if not removed:
        raise bridge.Refusal("NO_PAGES_TO_PRUNE")
    names = [p["name"] for p in source_pages]
    if any(names.count(p["name"]) != 1 for p in removed):
        raise bridge.Refusal("UI_TARGET_AMBIGUOUS",
                             "A deletion target's page name is not unique in this file.")
    source_token_hash, clone_token_hash = _tokens_hash(source), _tokens_hash(clone)
    if source_token_hash is not None and clone_token_hash is not None:
        if source_token_hash != clone_token_hash:
            raise bridge.Refusal("CLONE_TOKENS_MISMATCH")
    # Only retained pages need native parity: pages pruned from a copy never
    # become authoritative, and may continue receiving legitimate source edits.
    kept_pages = [p for p in source_pages if p["id"] in keep_ids]
    retained_census = []
    for page in kept_pages:
        source_native = _read_native_page(source_id, page, page_reader=page_reader)
        clone_native = _read_native_page(clone_id, page, page_reader=page_reader)
        if source_native != clone_native:
            raise bridge.Refusal("RETAINED_PAGE_NATIVE_STRUCTURE_MISMATCH",
                                 "Do not prune a stale or structurally divergent clone.")
        retained_census.append({"page_id": page["id"],
                                "native_metadata_sha256": bridge.digest(source_native)})
    return {
        "schema": SCHEMA,
        "state": "CLONE_PRUNE_PLAN_READY",
        "operation_id": operation_id,
        "source_file_id": source_id,
        "source_file_name": source["fileName"],
        "clone_file_id": clone_id,
        "clone_file_name": clone["fileName"],
        "original_pages": source_pages,
        "keep_page_ids": [p["id"] for p in source_pages if p["id"] in keep_ids],
        "remove_pages": removed,
        "source_token_hash": source_token_hash,
        "clone_token_hash_before": clone_token_hash,
        "source_page_list_sha256": bridge.digest(source_pages),
        "clone_page_list_sha256": bridge.digest(clone_pages),
        "retained_native_census": retained_census,
        "retained_native_census_sha256": bridge.digest(retained_census),
        "native_metadata_only_not_full_visual_fidelity": True,
        "actuation": "FIRST_PARTY_PAPER_UI_ONLY_SEPARATE_CARRIER_PROOF_REQUIRED",
        "original_deletion_authorized": False,
        "image_component_comment_fidelity_verified": False,
    }


def _read_jsx(file_id: str, node_id: str, *,
              reader: Callable[[str, str], str] | None = None) -> str:
    if reader is not None:
        body = reader(file_id, node_id)
    else:
        result = bridge.execute("read", tool="get_jsx", arguments={
            "fileId": file_id, "nodeId": node_id,
            "format": "inline-styles", "includeNodeIds": True,
        })
        raw = result.get("result") or {}
        if result.get("state") != "OBSERVED" or raw.get("isError"):
            raise bridge.Refusal("JSX_READ_UNAVAILABLE")
        blocks = [x.get("text") for x in raw.get("content", [])
                  if isinstance(x, dict) and x.get("type") == "text"]
        # Paper emits an identity/header record and a separate JSX body.
        # Never compare two identical tool-error messages as design proof.
        if len(blocks) != 2 or not isinstance(blocks[1], str):
            raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
        body = blocks[1]
    if not isinstance(body, str) or not body.lstrip().startswith("(") or "<" not in body:
        raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
    return body


def verify_plan(plan: dict, *, reader: Callable[[str], dict] | None = None,
                page_reader: Callable[[str, str], dict] | None = None,
                evidence_node_ids: list[str] | None = None,
                jsx_reader: Callable[[str, str], str] | None = None) -> dict:
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA or plan.get("state") != "CLONE_PRUNE_PLAN_READY":
        raise bridge.Refusal("INVALID_PRUNE_PLAN")
    source_id = _require_file_id(plan.get("source_file_id"))
    clone_id = _require_file_id(plan.get("clone_file_id"))
    if source_id == clone_id:
        raise bridge.Refusal("SOURCE_EQUALS_CLONE")
    originals = plan.get("original_pages")
    if not isinstance(originals, list) or originals != _pages({"pages": originals}):
        raise bridge.Refusal("INVALID_PRUNE_PLAN")
    if bridge.digest(originals) != plan.get("source_page_list_sha256") or (
        plan.get("clone_page_list_sha256") != plan.get("source_page_list_sha256")
    ):
        raise bridge.Refusal("PLAN_PAGE_HASH_MISMATCH")
    keep = plan.get("keep_page_ids")
    removed = plan.get("remove_pages")
    if not isinstance(keep, list) or not isinstance(removed, list):
        raise bridge.Refusal("INVALID_PRUNE_PLAN")
    expected_kept = [p for p in originals if p["id"] in keep]
    expected_removed = [p for p in originals if p["id"] not in keep]
    if (not expected_kept or not expected_removed
            or keep != [p["id"] for p in expected_kept]
            or removed != expected_removed):
        raise bridge.Refusal("PLAN_PAGE_TARGET_MISMATCH")
    source, clone = _read(source_id, reader=reader), _read(clone_id, reader=reader)
    if _pages(source) != originals or source["fileName"] != plan.get("source_file_name"):
        raise bridge.Refusal("SOURCE_CHANGED", "Source file must remain unchanged.")
    if _pages(clone) != expected_kept or clone["fileName"] != plan.get("clone_file_name"):
        raise bridge.Refusal("CLONE_PRUNE_UNVERIFIED")
    src_tokens = _tokens_hash(source)
    clone_tokens = _tokens_hash(clone)
    if plan.get("source_token_hash") is not None and src_tokens != plan["source_token_hash"]:
        raise bridge.Refusal("SOURCE_TOKENS_CHANGED")
    if (plan.get("clone_token_hash_before") is not None
            and clone_tokens != plan["clone_token_hash_before"]):
        raise bridge.Refusal("CLONE_TOKENS_CHANGED")
    retained_census = plan.get("retained_native_census")
    if (not isinstance(retained_census, list)
            or len(retained_census) != len(expected_kept)
            or bridge.digest(retained_census) != plan.get("retained_native_census_sha256")
            or [x.get("page_id") for x in retained_census if isinstance(x, dict)]
                != [p["id"] for p in expected_kept]):
        raise bridge.Refusal("NATIVE_PAGE_CENSUS_PLAN_INVALID")
    for page, baseline in zip(expected_kept, retained_census):
        current_source = _read_native_page(source_id, page, page_reader=page_reader)
        current_clone = _read_native_page(clone_id, page, page_reader=page_reader)
        if bridge.digest(current_source) != baseline["native_metadata_sha256"]:
            raise bridge.Refusal("SOURCE_NATIVE_PAGE_DRIFT")
        if bridge.digest(current_clone) != baseline["native_metadata_sha256"]:
            raise bridge.Refusal("CLONE_NATIVE_PAGE_DRIFT")
    node_ids = evidence_node_ids or []
    if (not isinstance(node_ids, list)
            or any(not isinstance(x, str) or not OPERATION_RE.fullmatch(x) for x in node_ids)
            or len(set(node_ids)) != len(node_ids) or len(node_ids) > 24):
        raise bridge.Refusal("INVALID_JSX_EVIDENCE_TARGETS")
    for node_id in node_ids:
        original_jsx = _read_jsx(source_id, node_id, reader=jsx_reader)
        cloned_jsx = _read_jsx(clone_id, node_id, reader=jsx_reader)
        if original_jsx != cloned_jsx:
            raise bridge.Refusal("CLONE_JSX_MISMATCH",
                                 "Source and retained native node JSX differ.")
    return {
        "schema": SCHEMA,
        "state": "CLONE_PRUNE_METADATA_VERIFIED",
        "operation_id": plan.get("operation_id"),
        "source_file_id": source_id,
        "clone_file_id": clone_id,
        "source_page_list_unchanged_ids": [p["id"] for p in originals],
        "retained_native_metadata_verified_ids": [p["id"] for p in expected_kept],
        "retained_native_metadata_only_not_full_fidelity": True,
        "clone_retained_page_ids": [p["id"] for p in expected_kept],
        "clone_removed_page_ids": [p["id"] for p in expected_removed],
        "page_metadata_verified": True,
        "exact_jsx_node_ids_verified": node_ids,
        "full_page_visual_fidelity_verified": False,
        "original_deletion_authorized": False,
        "image_component_comment_fidelity_verified": False,
        "production_migration_accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("plan")
    prepare.add_argument("--source-file-id", required=True)
    prepare.add_argument("--clone-file-id", required=True)
    prepare.add_argument("--keep-page-id", action="append", required=True)
    prepare.add_argument("--operation-id", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--verify-node-id", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.action == "plan":
            receipt = make_plan(args.source_file_id, args.clone_file_id,
                                args.keep_page_id, args.operation_id)
        else:
            receipt = verify_plan(bridge.load_json(args.plan.read_bytes()),
                                  evidence_node_ids=args.verify_node_id)
        print(json.dumps(receipt, sort_keys=True, indent=2))
        return 0
    except (bridge.Refusal, OSError) as exc:
        state = exc.code if isinstance(exc, bridge.Refusal) else "PLAN_FILE_UNAVAILABLE"
        print(json.dumps({"state": state, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

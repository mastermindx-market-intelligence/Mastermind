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
    if (info.get("truncated") is True or ("pageCount" in info and (
            type(info["pageCount"]) is not int or info["pageCount"] != len(raw)))):
        raise bridge.Refusal("PAGE_LIST_INCOMPLETE")
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
    if isinstance(hashes, dict) and isinstance(hashes.get("tokens"), str) and hashes["tokens"]:
        return hashes["tokens"]
    return None


def _basic_read(file_id: str, page_id: str | None = None, *,
                warnings: list[dict] | None = None) -> dict:
    arguments = {"fileId": file_id}
    if page_id is not None:
        arguments["pageId"] = page_id
    response = bridge.execute("read", tool="get_basic_info", arguments=arguments)
    raw = response.get("result") if isinstance(response, dict) else None
    if (not isinstance(response, dict) or response.get("state") != "OBSERVED"
            or not isinstance(raw, dict) or ("isError" in raw and raw["isError"] is not False)):
        raise bridge.Refusal("DOCUMENT_UNAVAILABLE")
    # An explicitly truncated envelope is a partial observation. Refuse it
    # before normalization, as the JSX reader refuses its own envelope flags.
    if (raw.get("truncated") is True or response.get("truncated") is True
            or not isinstance(raw.get("content"), list) or raw.get("structuredContent") is not None):
        raise bridge.Refusal("DOCUMENT_SCHEMA_UNVERIFIED")
    # Explicit reads must use the requested tool result, not the separately
    # captured active-file/page snapshot in response.document.
    info = bridge.basic_object(raw)
    if info.get("fileId") != file_id:
        raise bridge.Refusal("FILE_ID_MISMATCH")
    for block in raw.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "text":
            raise bridge.Refusal("DOCUMENT_SCHEMA_UNVERIFIED")
        text = block.get("text")
        if not isinstance(text, str):
            raise bridge.Refusal("DOCUMENT_SCHEMA_UNVERIFIED")
        if text.startswith("Warning: ") and text[9:].strip():
            if warnings is not None:
                warnings.append({"file_id": file_id, "page_id": page_id, "text": text})
            continue
        value = bridge.load_json(text)
        if not isinstance(value, dict):
            raise bridge.Refusal("DOCUMENT_SCHEMA_UNVERIFIED")
        ids = [value[key] for key in ("fileId", "documentId") if key in value]
        if isinstance(value.get("file"), dict) and "id" in value["file"]:
            ids.append(value["file"]["id"])
        if any(identity != file_id for identity in ids):
            raise bridge.Refusal("FILE_ID_MISMATCH")
    return info


def _read(file_id: str, *, reader: Callable[[str], dict] | None = None,
          warnings: list[dict] | None = None) -> dict:
    file_id = _require_file_id(file_id)
    if reader is not None:
        info = reader(file_id)
    else:
        info = _basic_read(file_id, warnings=warnings)
    if not isinstance(info, dict) or info.get("fileId") != file_id:
        raise bridge.Refusal("FILE_ID_MISMATCH")
    if not isinstance(info.get("fileName"), str) or not info["fileName"]:
        raise bridge.Refusal("FILE_NAME_REQUIRED")
    _pages(info)
    return info


def _read_native_page(file_id: str, page: dict, *,
                      page_reader: Callable[[str, str], dict] | None = None,
                      warnings: list[dict] | None = None) -> dict:
    """Exact-page structural census, not complete style/asset equivalence."""
    page_id = page["id"]
    if page_reader is None:
        info = _basic_read(file_id, page_id, warnings=warnings)
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


def _jsx_ids(node_ids: list[str] | None) -> list[str]:
    if node_ids is None:
        return []
    if (not isinstance(node_ids, list)
            or any(not isinstance(x, str) or not OPERATION_RE.fullmatch(x) for x in node_ids)
            or len(set(node_ids)) != len(node_ids) or len(node_ids) > 24):
        raise bridge.Refusal("INVALID_JSX_EVIDENCE_TARGETS")
    return node_ids


def make_plan(source_id: str, clone_id: str, keep_ids: list[str],
              operation_id: str, *, reader: Callable[[str], dict] | None = None,
              page_reader: Callable[[str, str], dict] | None = None,
              evidence_node_ids: list[str] | None = None,
              jsx_reader: Callable[[str, str], str] | None = None) -> dict:
    source_id, clone_id = _require_file_id(source_id), _require_file_id(clone_id)
    if source_id == clone_id:
        raise bridge.Refusal("SOURCE_EQUALS_CLONE")
    if not isinstance(operation_id, str) or not OPERATION_RE.fullmatch(operation_id):
        raise bridge.Refusal("OPERATION_ID_REQUIRED")
    if not isinstance(keep_ids, list) or not keep_ids or any(not isinstance(p, str) for p in keep_ids):
        raise bridge.Refusal("KEEP_PAGE_IDS_REQUIRED")
    if len(keep_ids) != len(set(keep_ids)):
        raise bridge.Refusal("DUPLICATE_KEEP_PAGE_IDS")
    warnings = []
    source = _read(source_id, reader=reader, warnings=warnings)
    if warnings:
        raise bridge.Refusal("NATIVE_READ_WARNING_REQUIRES_REVIEW")
    clone = _read(clone_id, reader=reader, warnings=warnings)
    if warnings:
        raise bridge.Refusal("NATIVE_READ_WARNING_REQUIRES_REVIEW")
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
    retained_artboard_ids = set()
    for page in kept_pages:
        source_native = _read_native_page(source_id, page, page_reader=page_reader, warnings=warnings)
        clone_native = _read_native_page(clone_id, page, page_reader=page_reader, warnings=warnings)
        if warnings:
            raise bridge.Refusal("NATIVE_READ_WARNING_REQUIRES_REVIEW")
        if source_native != clone_native:
            raise bridge.Refusal("RETAINED_PAGE_NATIVE_STRUCTURE_MISMATCH",
                                 "Do not prune a stale or structurally divergent clone.")
        retained_census.append({"page_id": page["id"],
                                "native_metadata_sha256": bridge.digest(source_native)})
        retained_artboard_ids.update(board["id"] for board in source_native["artboards"])
    sample_ids = _jsx_ids(evidence_node_ids)
    if any(node_id not in retained_artboard_ids for node_id in sample_ids):
        raise bridge.Refusal("JSX_TARGET_NOT_RETAINED_ARTBOARD")
    pre_prune_jsx = []
    for node_id in sample_ids:
        source_jsx = _read_jsx(source_id, node_id, reader=jsx_reader)
        clone_jsx = _read_jsx(clone_id, node_id, reader=jsx_reader)
        if source_jsx != clone_jsx:
            raise bridge.Refusal("CLONE_JSX_MISMATCH",
                                 "Selected native style differs before any deletion.")
        pre_prune_jsx.append({"node_id": node_id,
                              "native_jsx_sha256": bridge.digest(source_jsx)})
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
        "pre_prune_native_jsx": pre_prune_jsx,
        "pre_prune_native_jsx_sha256": bridge.digest(pre_prune_jsx),
        "native_metadata_only_not_full_visual_fidelity": True,
        "actuation": "FIRST_PARTY_PAPER_UI_ONLY_SEPARATE_CARRIER_PROOF_REQUIRED",
        "original_deletion_authorized": False,
        "image_component_comment_fidelity_verified": False,
    }


def _parse_jsx_observation(result: dict, file_id: str, node_id: str) -> dict:
    """Validate the observed header / warnings / JSX grammar, without actuation.

    The optional warning is NOT JSX and is never discarded. An exact-file
    header and the exported root's first id attribute bind the content to the
    requested artboard. This checks the known export envelope, not JSX syntax
    completeness, a native document revision, or restoration fidelity.
    """
    _require_file_id(file_id)
    _jsx_ids([node_id])
    if not isinstance(result, dict) or result.get("state") != "OBSERVED":
        raise bridge.Refusal("JSX_READ_UNAVAILABLE")
    raw = result.get("result")
    if not isinstance(raw, dict) or ("isError" in raw and raw["isError"] is not False):
        raise bridge.Refusal("JSX_READ_UNAVAILABLE")
    # No structured JSX response is in the observed vendor contract. Do not
    # silently prefer one representation when a second may contradict it.
    blocks = raw.get("content")
    if (raw.get("structuredContent") is not None or raw.get("truncated") is True
            or result.get("truncated") is True or not isinstance(blocks, list)
            or not 2 <= len(blocks) <= 32
            or any(not isinstance(x, dict) or x.get("type") != "text"
                   or not isinstance(x.get("text"), str) for x in blocks)):
        raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
    header = bridge.load_json(blocks[0]["text"])
    if (not isinstance(header, dict)
            or set(header) - {"file", "fileId", "documentId", "contentHash"}
            or not isinstance(header.get("file"), dict)
            or set(header["file"]) != {"id", "name"}
            or not isinstance(header["file"].get("name"), str)
            or not header["file"]["name"]
            or ("contentHash" in header and not isinstance(header["contentHash"], dict))):
        raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
    ids = [header["file"].get("id")]
    ids.extend(header[key] for key in ("fileId", "documentId") if key in header)
    if any(value != file_id for value in ids):
        raise bridge.Refusal("JSX_FILE_ID_MISMATCH")
    warnings = [x["text"] for x in blocks[1:-1]]
    if any(not text.startswith("Warning: ") or not text[9:].strip() for text in warnings):
        raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
    body = blocks[-1]["text"]
    root = re.match(r"\s*\(\s*<([A-Za-z][A-Za-z0-9:_-]*)\s+id=([\"'])([^\"']+)\2(?=\s|/?>)", body)
    if root is None or root.group(3) != node_id:
        raise bridge.Refusal("JSX_ROOT_ID_MISMATCH")
    # Do not accept a second root id hidden after the expected first one.
    # Skip quoted strings and style expressions so descendant IDs and text
    # inside CSS values cannot masquerade as root attributes.
    cursor, depth, quote, escaped = root.end(), 0, None, False
    while cursor < len(body):
        char = body[cursor]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            if depth == 0:
                raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
            depth -= 1
        elif depth == 0:
            if char == ">":
                break
            if char == "<" or (body[cursor - 1].isspace()
                               and re.match(r"id\s*=", body[cursor:])):
                raise bridge.Refusal("JSX_ROOT_ID_MISMATCH")
        cursor += 1
    if cursor == len(body):
        raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
    # Every observed Paper artboard export closes its root and parentheses.
    # A truncated prefix must not become parity evidence.
    if not re.search(r"</" + re.escape(root.group(1)) + r">\s*\)\s*\Z", body):
        raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
    return {"file_id": file_id, "node_id": node_id,
            "body": body, "warnings": warnings}


def _read_jsx_observation(file_id: str, node_id: str) -> dict:
    _require_file_id(file_id)
    _jsx_ids([node_id])
    result = bridge.execute("read", tool="get_jsx", arguments={
        "fileId": file_id, "nodeId": node_id,
        "format": "inline-styles", "includeNodeIds": True,
        "includeRootPositioning": False,
    })
    return _parse_jsx_observation(result, file_id, node_id)


def _read_jsx(file_id: str, node_id: str, *,
              reader: Callable[[str, str], str] | None = None) -> str:
    if reader is not None:
        body = reader(file_id, node_id)
    else:
        observation = _read_jsx_observation(file_id, node_id)
        if observation["warnings"]:
            # Reading a warning successfully cannot turn an oversized source
            # into CLONE_PRUNE_PLAN_READY. The read-only compare path below
            # retains useful evidence while plan/verify stay fail-closed.
            raise bridge.Refusal("JSX_WARNING_REQUIRES_REVIEW",
                                 "Native warning retained; no prune readiness from this response.")
        body = observation["body"]
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
    warnings = []
    source = _read(source_id, reader=reader, warnings=warnings)
    if warnings:
        raise bridge.Refusal("NATIVE_READ_WARNING_REQUIRES_REVIEW")
    clone = _read(clone_id, reader=reader, warnings=warnings)
    if warnings:
        raise bridge.Refusal("NATIVE_READ_WARNING_REQUIRES_REVIEW")
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
        current_source = _read_native_page(source_id, page, page_reader=page_reader, warnings=warnings)
        current_clone = _read_native_page(clone_id, page, page_reader=page_reader, warnings=warnings)
        if warnings:
            raise bridge.Refusal("NATIVE_READ_WARNING_REQUIRES_REVIEW")
        if bridge.digest(current_source) != baseline["native_metadata_sha256"]:
            raise bridge.Refusal("SOURCE_NATIVE_PAGE_DRIFT")
        if bridge.digest(current_clone) != baseline["native_metadata_sha256"]:
            raise bridge.Refusal("CLONE_NATIVE_PAGE_DRIFT")
    requested_ids = _jsx_ids(evidence_node_ids)
    pre_prune = plan.get("pre_prune_native_jsx", [])
    if (not isinstance(pre_prune, list)
            or bridge.digest(pre_prune) != plan.get("pre_prune_native_jsx_sha256")
            or any(not isinstance(x, dict)
                   or not isinstance(x.get("node_id"), str)
                   or not OPERATION_RE.fullmatch(x["node_id"])
                   or not isinstance(x.get("native_jsx_sha256"), str)
                   or not re.fullmatch(r"[a-f0-9]{64}", x["native_jsx_sha256"])
                   for x in pre_prune)):
        raise bridge.Refusal("PRE_PRUNE_JSX_PLAN_INVALID")
    pre_ids = [x["node_id"] for x in pre_prune]
    if len(set(pre_ids)) != len(pre_ids):
        raise bridge.Refusal("PRE_PRUNE_JSX_PLAN_INVALID")
    if pre_ids and requested_ids and requested_ids != pre_ids:
        raise bridge.Refusal("PRE_PRUNE_JSX_TARGET_MISMATCH")
    node_ids = pre_ids or requested_ids
    for index, node_id in enumerate(node_ids):
        original_jsx = _read_jsx(source_id, node_id, reader=jsx_reader)
        cloned_jsx = _read_jsx(clone_id, node_id, reader=jsx_reader)
        if original_jsx != cloned_jsx:
            raise bridge.Refusal("CLONE_JSX_MISMATCH",
                                 "Source and retained native node JSX differ.")
        if pre_ids and bridge.digest(original_jsx) != pre_prune[index]["native_jsx_sha256"]:
            raise bridge.Refusal("RETAINED_NATIVE_JSX_DRIFT",
                                 "Selected retained artboard content changed since pre-prune read.")
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
        "pre_prune_native_jsx_verified_ids": pre_ids,
        "post_only_native_jsx_ids": [x for x in node_ids if x not in pre_ids],
        "full_page_visual_fidelity_verified": False,
        "original_deletion_authorized": False,
        "image_component_comment_fidelity_verified": False,
        "production_migration_accepted": False,
    }


def compare_file_pair(source_id: str, clone_id: str, *,
                      page_ids: list[str] | None = None,
                      evidence_node_ids: list[str] | None = None,
                      reader: Callable[[str], dict] | None = None,
                      page_reader: Callable[[str, str], dict] | None = None) -> dict:
    """Compare an unpruned pair, with explicit scope and no resource actions.

    Page lists are compared for both whole files. By default native metadata
    is read for every shared page; --page-id narrows that expensive census.
    JSX remains explicitly selected, never implied by matching node counts.
    Observations are non-atomic and establish neither restore nor authority.
    """
    source_id, clone_id = _require_file_id(source_id), _require_file_id(clone_id)
    if source_id == clone_id:
        raise bridge.Refusal("SOURCE_EQUALS_CLONE")
    nodes = _jsx_ids(evidence_node_ids)
    warnings = []
    source = _read(source_id, reader=reader, warnings=warnings)
    clone = _read(clone_id, reader=reader, warnings=warnings)
    source_pages, clone_pages = _pages(source), _pages(clone)
    source_map = {p["id"]: p for p in source_pages}
    clone_map = {p["id"]: p for p in clone_pages}
    common = [p["id"] for p in source_pages if p["id"] in clone_map]
    if page_ids is None:
        selected = common
    elif (not isinstance(page_ids, list) or not page_ids
          or any(not isinstance(p, str) or p not in common for p in page_ids)
          or len(set(page_ids)) != len(page_ids)):
        raise bridge.Refusal("COMPARISON_PAGE_SCOPE_INVALID")
    else:
        selected = [p for p in common if p in page_ids]
    missing = [p for p in source_map if p not in clone_map]
    extra = [p for p in clone_map if p not in source_map]
    page_results, shared_boards, all_boards = [], set(), set()
    for page_id in selected:
        before = _read_native_page(source_id, source_map[page_id],
                                   page_reader=page_reader, warnings=warnings)
        after = _read_native_page(clone_id, clone_map[page_id],
                                  page_reader=page_reader, warnings=warnings)
        src_boards = {b["id"] for b in before["artboards"]}
        dst_boards = {b["id"] for b in after["artboards"]}
        if all_boards & (src_boards | dst_boards):
            raise bridge.Refusal("CROSS_PAGE_ARTBOARD_ID_AMBIGUOUS")
        shared_boards.update(src_boards & dst_boards)
        all_boards.update(src_boards | dst_boards)
        page_results.append({"page_id": page_id, "native_metadata_equal": before == after,
                             "source": before, "candidate": after})
    if any(node not in shared_boards for node in nodes):
        raise bridge.Refusal("JSX_TARGET_OUTSIDE_SHARED_COMPARISON_SCOPE")
    jsx_results = []
    for node in nodes:
        before = _read_jsx_observation(source_id, node)
        after = _read_jsx_observation(clone_id, node)
        for observed in (before, after):
            warnings.extend({"file_id": observed["file_id"], "node_id": node, "text": warning}
                            for warning in observed["warnings"])
        jsx_results.append({"node_id": node, "exact_jsx_equal": before["body"] == after["body"],
                            "source_jsx_sha256": bridge.digest(before["body"]),
                            "candidate_jsx_sha256": bridge.digest(after["body"]),
                            "digest_encoding": "bridge.canonical_json_string_utf8",
                            "source_characters": len(before["body"]),
                            "candidate_characters": len(after["body"])})
    # Recheck only what this observation window can honestly establish. An
    # unchanged token/page-list hash is not an immutable native revision.
    for file_id, initial in ((source_id, source), (clone_id, clone)):
        current = _read(file_id, reader=reader, warnings=warnings)
        if (_pages(current) != _pages(initial) or _tokens_hash(current) != _tokens_hash(initial)
                or current["fileName"] != initial["fileName"]):
            raise bridge.Refusal("FILE_METADATA_DRIFT_DURING_COMPARE")
    token_available = _tokens_hash(source) is not None and _tokens_hash(clone) is not None
    token_equal = token_available and _tokens_hash(source) == _tokens_hash(clone)
    metadata_equal = source_pages == clone_pages
    divergence = (not metadata_equal or (token_available and not token_equal)
                  or any(not row["native_metadata_equal"] for row in page_results)
                  or any(not row["exact_jsx_equal"] for row in jsx_results))
    full_census = not missing and not extra and set(selected) == set(source_map)
    return {
        "schema": "mastermind.paper_native_pair_observation.v1",
        "state": ("OBSERVED_SCOPE_DIVERGENCE" if divergence else
                  "OBSERVED_SCOPE_PARITY" if token_available else "OBSERVED_SCOPE_INCOMPLETE"),
        "source_file_id": source_id, "candidate_file_id": clone_id,
        "source_page_count": len(source_pages), "candidate_page_count": len(clone_pages),
        "missing_source_page_ids": missing, "unexpected_candidate_page_ids": extra,
        "ordered_page_metadata_equal": metadata_equal,
        "token_hash_equal": token_equal if token_available else None,
        "native_page_scope_ids": selected, "native_page_comparisons": page_results,
        "selected_artboard_jsx_comparisons": jsx_results,
        "complete_file_native_census_observed": full_census,
        "all_artboards_jsx_compared": full_census and set(nodes) == all_boards,
        "warnings": warnings,
        "file_list_token_stability_observed": True,
        "atomic_native_revision_bound": False,
        "native_restore_verified": False,
        "resource_actions_authorized": False,
        "paper_mutations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("plan")
    prepare.add_argument("--source-file-id", required=True)
    prepare.add_argument("--clone-file-id", required=True)
    prepare.add_argument("--keep-page-id", action="append", required=True)
    prepare.add_argument("--operation-id", required=True)
    prepare.add_argument("--verify-node-id", action="append", default=[])
    verify = sub.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--verify-node-id", action="append", default=[])
    compare = sub.add_parser("compare", help="Read-only unpruned-pair comparison; never a prune plan")
    compare.add_argument("--source-file-id", required=True)
    compare.add_argument("--clone-file-id", required=True)
    compare.add_argument("--page-id", action="append")
    compare.add_argument("--verify-node-id", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.action == "plan":
            receipt = make_plan(args.source_file_id, args.clone_file_id,
                                args.keep_page_id, args.operation_id,
                                evidence_node_ids=args.verify_node_id)
        elif args.action == "verify":
            receipt = verify_plan(bridge.load_json(args.plan.read_bytes()),
                                  evidence_node_ids=args.verify_node_id)
        else:
            receipt = compare_file_pair(args.source_file_id, args.clone_file_id,
                                        page_ids=args.page_id,
                                        evidence_node_ids=args.verify_node_id)
        print(json.dumps(receipt, sort_keys=True, indent=2))
        if receipt.get("state") == "OBSERVED_SCOPE_DIVERGENCE":
            return 3
        return 4 if receipt.get("state") == "OBSERVED_SCOPE_INCOMPLETE" else 0
    except (bridge.Refusal, OSError) as exc:
        state = exc.code if isinstance(exc, bridge.Refusal) else "PLAN_FILE_UNAVAILABLE"
        print(json.dumps({"state": state, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

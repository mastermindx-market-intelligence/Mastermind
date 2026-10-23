"""One-shot, guarded first-party Paper UI page pruning on an already-verified clone.

No new MCP server, document writer, login/auth plane, transport, queue or retry
ledger. The existing guarded Paper bridge owns exact reads and host serialization;
Peekaboo invokes only the first-party Paper UI. This candidate MUST be reviewed
and installed before enabling worker-facing destructive tools.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

from integrations.paper_desktop import bridge
from integrations.paper_desktop import clone_prune_guard as guard

SCHEMA = "mastermind.paper_native_clone_prune_ui.v1"
PAGE_LINK_RE = re.compile(r"/file/([0-9A-HJKMNP-TV-Z]{26})/([A-Za-z0-9_.:-]{1,120})\Z")
OCR_MIN_CONFIDENCE = 0.5
MAX_CLIPBOARD = 4096


def native_page_identity(link: str) -> tuple[str, str]:
    if not isinstance(link, str) or len(link) > MAX_CLIPBOARD:
        raise bridge.Refusal("PAGE_LINK_INVALID")
    value = urlsplit(link.strip())
    if (value.scheme != "https" or value.netloc != "app.paper.design"
            or value.username or value.password or value.port
            or value.query or value.fragment):
        raise bridge.Refusal("PAGE_LINK_INVALID")
    matched = PAGE_LINK_RE.fullmatch(value.path)
    if not matched:
        raise bridge.Refusal("PAGE_LINK_INVALID")
    return matched.group(1), matched.group(2)


def _reviewed_read(client, tool: str, arguments: dict) -> dict:
    """Use the canonical bridge read allowlist inside main's existing mutex.

    bridge.execute acquires the same host-global desktop lock, so calling it
    recursively inside a locked UI transaction would deadlock. The outer
    main has already admitted the exact reviewed catalog and server before
    this function can perform its first read. This is not a second tool gate.
    """
    if tool not in bridge.READ_TOOLS:
        raise bridge.Refusal("TOOL_NOT_ALLOWED")
    response = client.call(tool, arguments)
    if not isinstance(response, dict) or response.get("isError"):
        raise bridge.Refusal("TOOL_ERROR")
    return response


def _basic(client, file_id: str | None = None,
           page_id: str | None = None) -> dict:
    args = {"fileId": file_id} if file_id else {}
    if page_id:
        args["pageId"] = page_id
    raw = _reviewed_read(client, "get_basic_info", args)
    info = bridge.basic_object(raw)
    if not isinstance(info, dict) or not isinstance(info.get("fileId"), str):
        raise bridge.Refusal("FILE_ID_REQUIRED")
    if file_id is not None and info["fileId"] != file_id:
        raise bridge.Refusal("FILE_ID_MISMATCH")
    return info


def _clone_resource_proof(client, source_id: str, clone_id: str) -> None:
    # Require Paper's own inventory to establish an actual newer duplicate.
    # A caller-supplied plan is not authority to label an original file a clone.
    raw = _reviewed_read(client, "list_resources", {"limit": 200})
    candidates = bridge._basic_candidates(raw)
    inventories = [x["resources"] for x in candidates
                   if isinstance(x.get("resources"), list)]
    if len(inventories) != 1:
        raise bridge.Refusal("FILE_INVENTORY_UNVERIFIED")
    records = [r for r in inventories[0]
               if isinstance(r, dict) and r.get("type") == "file"
               and r.get("id") in (source_id, clone_id)]
    if len(records) != 2 or {r["id"] for r in records} != {source_id, clone_id}:
        raise bridge.Refusal("SOURCE_CLONE_INVENTORY_MISSING")
    source = next(r for r in records if r["id"] == source_id)
    clone = next(r for r in records if r["id"] == clone_id)
    created_source, created_clone = source.get("createdAt"), clone.get("createdAt")
    if (not isinstance(created_source, (int, float))
            or not isinstance(created_clone, (int, float))
            or created_source >= created_clone
            or not isinstance(clone.get("name"), str)
            or not clone["name"].endswith(" (copy)")):
        raise bridge.Refusal("NATIVE_CLONE_PROVENANCE_REQUIRED")


def _retained_native_proof(plan: dict, client, originals: list[dict]) -> None:
    keep_ids = plan["keep_page_ids"]
    expected = plan.get("retained_native_census")
    if (not isinstance(expected, list) or len(expected) != len(keep_ids)
            or bridge.digest(expected) != plan.get("retained_native_census_sha256")):
        raise bridge.Refusal("PLAN_NATIVE_FINGERPRINT_UNVERIFIED")
    pages = {p["id"]: p for p in originals}
    for record, pid in zip(expected, keep_ids):
        if not isinstance(record, dict) or record.get("page_id") != pid:
            raise bridge.Refusal("PLAN_NATIVE_FINGERPRINT_UNVERIFIED")
        if pid not in pages:
            raise bridge.Refusal("PLAN_PAGE_TARGET_MISMATCH")
        original = guard._read_native_page(
            plan["source_file_id"], pages[pid],
            page_reader=lambda f, p: _basic(client, f, p))
        clone = guard._read_native_page(
            plan["clone_file_id"], pages[pid],
            page_reader=lambda f, p: _basic(client, f, p))
        fingerprint = record.get("native_metadata_sha256")
        if (not isinstance(fingerprint, str) or
                bridge.digest(original) != fingerprint or
                bridge.digest(clone) != fingerprint):
            raise bridge.Refusal("RETAINED_PAGE_NATIVE_STRUCTURE_MISMATCH")
    samples = plan.get("pre_prune_native_jsx")
    if (not isinstance(samples, list)
            or bridge.digest(samples) != plan.get("pre_prune_native_jsx_sha256")):
        raise bridge.Refusal("PLAN_JSX_FINGERPRINT_UNVERIFIED")
    for row in samples:
        if not isinstance(row, dict) or not isinstance(row.get("node_id"), str):
            raise bridge.Refusal("PLAN_JSX_FINGERPRINT_UNVERIFIED")
        native_id = row["node_id"]
        body = []
        for file_id in (plan["source_file_id"], plan["clone_file_id"]):
            response = _reviewed_read(client, "get_jsx", {
                "fileId": file_id, "nodeId": native_id,
                "format": "inline-styles", "includeNodeIds": True,
            })
            text_values = [x.get("text") for x in response.get("content", [])
                           if isinstance(x, dict) and x.get("type") == "text"]
            if len(text_values) != 2 or not isinstance(text_values[1], str):
                raise bridge.Refusal("JSX_SCHEMA_UNVERIFIED")
            body.append(text_values[1])
        fingerprint = row.get("native_jsx_sha256")
        if (not isinstance(fingerprint, str) or
                any(bridge.digest(x) != fingerprint for x in body)):
            raise bridge.Refusal("CLONE_JSX_MISMATCH")


def _validate_plan_and_current(plan: dict, client, page_id: str) -> tuple[dict, dict, list[dict]]:
    if (not isinstance(plan, dict)
            or plan.get("schema") != guard.SCHEMA
            or plan.get("state") != "CLONE_PRUNE_PLAN_READY"):
        raise bridge.Refusal("INVALID_PRUNE_PLAN")
    source_id = guard._require_file_id(plan.get("source_file_id"))
    clone_id = guard._require_file_id(plan.get("clone_file_id"))
    if source_id == clone_id:
        raise bridge.Refusal("SOURCE_EQUALS_CLONE")
    _clone_resource_proof(client, source_id, clone_id)
    source, clone = _basic(client, source_id), _basic(client, clone_id)
    originals = plan.get("original_pages")
    if not isinstance(originals, list) or originals != guard._pages({"pages": originals}):
        raise bridge.Refusal("INVALID_PRUNE_PLAN")
    if (bridge.digest(originals) != plan.get("source_page_list_sha256")
            or plan.get("clone_page_list_sha256") != plan.get("source_page_list_sha256")):
        raise bridge.Refusal("PLAN_PAGE_HASH_MISMATCH")
    if source["fileName"] != plan.get("source_file_name") or guard._pages(source) != originals:
        raise bridge.Refusal("SOURCE_CHANGED")
    if clone["fileName"] != plan.get("clone_file_name"):
        raise bridge.Refusal("CLONE_CHANGED")
    if guard._tokens_hash(source) != plan.get("source_token_hash"):
        raise bridge.Refusal("SOURCE_TOKENS_CHANGED")
    if guard._tokens_hash(clone) != plan.get("clone_token_hash_before"):
        raise bridge.Refusal("CLONE_TOKENS_CHANGED")
    keep_ids = plan.get("keep_page_ids")
    remove = plan.get("remove_pages")
    if not isinstance(keep_ids, list) or not isinstance(remove, list):
        raise bridge.Refusal("INVALID_PRUNE_PLAN")
    valid_keep = [p["id"] for p in originals if p["id"] in keep_ids]
    valid_remove = [p for p in originals if p["id"] not in keep_ids]
    if not valid_keep or not valid_remove or valid_keep != keep_ids or remove != valid_remove:
        raise bridge.Refusal("PLAN_PAGE_TARGET_MISMATCH")
    page_targets = {p["id"]: p for p in remove}
    if page_id not in page_targets:
        raise bridge.Refusal("PAGE_NOT_APPROVED_FOR_PRUNE")
    if sum(1 for p in originals if p["name"] == page_targets[page_id]["name"]) != 1:
        raise bridge.Refusal("UI_TARGET_AMBIGUOUS")
    current = guard._pages(clone)
    original_by_id = {p["id"]: p for p in originals}
    if (not current or len(current) < 2
            or any(original_by_id.get(p["id"]) != p for p in current)
            or [p["id"] for p in current] != [
                p["id"] for p in originals if p["id"] in {q["id"] for q in current}]
            ):
        raise bridge.Refusal("CLONE_CHANGED")
    present = {p["id"] for p in current}
    if any(p not in present for p in keep_ids):
        raise bridge.Refusal("CLONE_KEEP_PAGE_MISSING")
    if page_id not in present:
        raise bridge.Refusal("TARGET_ALREADY_REMOVED")
    _retained_native_proof(plan, client, originals)
    foreground = _basic(client)
    if foreground["fileId"] != clone_id:
        raise bridge.Refusal("CLONE_NOT_FOREGROUND")
    return source, clone, current


class NativePeekaboo:
    def __init__(self, *, binary: str = "peekaboo"):
        self.binary = binary

    def _json(self, args: list[str], *, timeout: float = 14) -> dict:
        try:
            p = subprocess.run([self.binary, *args, "--json"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, timeout=timeout, check=False)
            obj = json.loads(p.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise bridge.Refusal("UI_TOOL_RESPONSE_UNKNOWN") from exc
        if p.returncode != 0 or not isinstance(obj, dict) or obj.get("success") is not True:
            raise bridge.Refusal("UI_TOOL_FAILED")
        return obj

    def click(self, window_id: int, x: int, y: int, *, right: bool = False) -> dict:
        args = ["click", "--foreground", "--input-strategy", "synthOnly",
                "--window-id", str(window_id), "--at", f"{x},{y}"]
        if right:
            args.append("--right")
        return self._json(args)

    def menu(self, window_id: int, private_dir: Path, *,
             row_x: int, row_y: int) -> dict:
        # Native first-party screenshot is ephemeral inside a 0700 dir.
        shot = private_dir / "paper-menu.png"
        args = ["see", "--window-id", str(window_id), "--ocr",
                "--path", str(shot)]
        # Never accept a previous menu capture if Peekaboo reports success
        # but silently fails to refresh the PNG on this invocation.
        try:
            shot.unlink(missing_ok=True)
        except OSError as exc:
            raise bridge.Refusal("UI_ROW_VISUAL_UNAVAILABLE") from exc
        obj = self._json(args, timeout=18)
        data = obj.get("data")
        if not isinstance(data, dict):
            raise bridge.Refusal("UI_OBSERVATION_UNAVAILABLE")
        data["_row_visual_sha256"] = _row_visual_fingerprint(
            shot, data.get("coordinate_context"), row_x, row_y,
            private_dir / "sidebar-row.png")
        return data

def _row_visual_fingerprint(image_path: Path, context: dict,
                            row_x: int, row_y: int, crop_path: Path) -> str:
    """Fingerprint the left sidebar row AND nearby visible page list.

    Live Paper v0.5.15 proved identical SHA across independently opened
    menus and a different digest when the crop shifts to another row on M1.
    Including neighboring labels detects scroll/reorder even if two page
    titles share the same visible prefix. Menu geometry alone is insufficient.
    A matching screenshot is not an atomic Paper page-ID binding; all work
    remains on verified disposable clones until a stronger API exists.
    """
    if (type(row_x) is not int or type(row_y) is not int
            or not 85 <= row_x <= 190 or row_y < 24):
        raise bridge.Refusal("UI_ROW_VISUAL_UNVERIFIED")
    context = context if isinstance(context, dict) else {}
    bounds = context.get("logical_bounds")
    frame = context.get("delivered_image_size")
    scale = context.get("output_scale")
    if (not isinstance(bounds, list) or len(bounds) != 2
            or not isinstance(bounds[1], list) or len(bounds[1]) != 2
            or not isinstance(frame, list) or len(frame) != 2
            or type(scale) is not int or scale != 1
            or any(type(x) is not int or x <= 0 for x in frame)
            or any(not _finite_number(x) or x <= 0 for x in bounds[1])
            or any(abs(frame[i] - bounds[1][i]) > 2 for i in (0, 1))):
        raise bridge.Refusal("UI_ROW_VISUAL_UNVERIFIED")
    x, y, width = 15, max(0, row_y - 60), row_x - 25
    height = min(140, frame[1] - y)
    if (width < 60 or x + width > frame[0] or height < 60
            or not (y <= row_y - 10 and y + height >= row_y + 10)
            or not image_path.is_file()):
        raise bridge.Refusal("UI_ROW_VISUAL_UNVERIFIED")
    try:
        # sips can return success without rewriting its output on a partial
        # failure; a leftover crop must never become fresh visual evidence.
        crop_path.unlink(missing_ok=True)
        p = subprocess.run(["/usr/bin/sips", "-s", "format", "png",
                            "-c", str(height), str(width), "--cropOffset",
                            str(y), str(x), str(image_path),
                            "--out", str(crop_path)],
                           capture_output=True, timeout=6, check=False)
        raw = crop_path.read_bytes() if p.returncode == 0 else b""
    except (OSError, subprocess.TimeoutExpired):
        raise bridge.Refusal("UI_ROW_VISUAL_UNAVAILABLE") from None
    if len(raw) < 100 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise bridge.Refusal("UI_ROW_VISUAL_UNAVAILABLE")
    return hashlib.sha256(raw).hexdigest()


def _assert_same_row_visual(*snapshots: dict) -> None:
    digests = [s.get("_row_visual_sha256") for s in snapshots]
    if (len(digests) < 2
            or any(not isinstance(v, str)
                   or not re.fullmatch(r"[0-9a-f]{64}", v) for v in digests)):
        raise bridge.Refusal("UI_ROW_VISUAL_UNVERIFIED")
    if len(set(digests)) != 1:
        raise bridge.Refusal("UI_PAGE_ROW_CHANGED")


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _menu_target(snapshot: dict, expected_file_name: str, label: str,
                 window_id: int, *, row_x: int | None = None,
                 row_y: int | None = None) -> tuple[int, int]:
    if snapshot.get("window_title") != expected_file_name or snapshot.get("is_dialog") is True:
        raise bridge.Refusal("UI_FILE_CONTEXT_CHANGED")
    context = snapshot.get("coordinate_context") or {}
    limits = context.get("logical_bounds")
    win = context.get("window") or {}
    if (not isinstance(limits, list) or len(limits) != 2
            or not isinstance(limits[0], list) or len(limits[0]) != 2
            or not isinstance(limits[1], list) or len(limits[1]) != 2
            or win.get("window_id") != window_id):
        raise bridge.Refusal("UI_WINDOW_UNVERIFIED")
    origin_x, origin_y = limits[0]
    width, height = limits[1]
    if not all(_finite_number(v) for v in (origin_x, origin_y, width, height)):
        raise bridge.Refusal("UI_WINDOW_UNVERIFIED")
    matches = [
        z for z in snapshot.get("ui_elements", []) or []
        if isinstance(z, dict)
        and str(z.get("id", "")).startswith("ocr_")
        and str(z.get("label", "")).strip().casefold() == label.casefold()
        and _finite_number(z.get("confidence"))
        and OCR_MIN_CONFIDENCE <= z["confidence"] <= 1
    ]
    if len(matches) == 0 and label.casefold() == "copy link":
        # OCR may miss the first context-menu line. The non-destructive
        # Copy link click can be inferred ONLY from two individually observed
        # later rows of the *same* first-party menu. Any ambiguity refuses.
        def anchor(name):
            a = [q for q in snapshot.get("ui_elements", []) or []
                 if isinstance(q, dict)
                 and str(q.get("id", "")).startswith("ocr_")
                 and str(q.get("label", "")).strip().casefold() == name
                 and _finite_number(q.get("confidence"))
                 and OCR_MIN_CONFIDENCE <= q["confidence"] <= 1]
            if len(a) != 1:
                raise bridge.Refusal("UI_MENU_ITEM_UNVERIFIED")
            b = a[0].get("bounds") or {}
            if not all(_finite_number(b.get(k))
                       for k in ("x", "y", "width", "height")):
                raise bridge.Refusal("UI_MENU_BOUNDS_UNVERIFIED")
            return b
        add, delete = anchor("add divider"), anchor("delete page")
        add_y = add["y"] + add["height"] / 2
        delete_y = delete["y"] + delete["height"] / 2
        step = delete_y - add_y
        add_x = add["x"] + add["width"] / 2
        delete_x = delete["x"] + delete["width"] / 2
        if (not 42 <= step <= 80 or abs(add_x - delete_x) > 16
                or not 6 <= add["height"] <= 20
                or not 6 <= delete["height"] <= 20):
            raise bridge.Refusal("UI_MENU_ITEM_UNVERIFIED")
        # Only infer Copy link inside the context menu opened against the
        # actual sidebar row. Two unrelated labels elsewhere in the document
        # must not authorize any coordinate click before clipboard proof.
        if type(row_x) is not int or type(row_y) is not int:
            raise bridge.Refusal("UI_MENU_ROW_UNVERIFIED")
        click_x, click_y = origin_x + row_x, origin_y + row_y
        if (not -30 <= add_x - click_x <= 240
                or not 15 <= add_y - click_y <= 150
                or not -30 <= delete_x - click_x <= 240
                or not 45 <= delete_y - click_y <= 220):
            raise bridge.Refusal("UI_MENU_ROW_UNVERIFIED")
        rect = {"x": add_x, "y": add_y - step, "width": 0, "height": 0}
    elif len(matches) == 1:
        rect = matches[0].get("bounds") or {}
    else:
        raise bridge.Refusal("UI_MENU_ITEM_UNVERIFIED")
    if not all(_finite_number(rect.get(k)) for k in ("x", "y", "width", "height")):
        raise bridge.Refusal("UI_MENU_BOUNDS_UNVERIFIED")
    if label.casefold() == "delete page":
        # A lone OCR string on a design canvas is not a first-party menu.
        # The live context menu places Add divider 42-80px above Delete
        # page, sharing its column; both anchors must be unique and coherent.
        anchors = [
            z for z in snapshot.get("ui_elements", []) or []
            if isinstance(z, dict) and str(z.get("id", "")).startswith("ocr_")
            and str(z.get("label", "")).strip().casefold() == "add divider"
            and _finite_number(z.get("confidence"))
            and OCR_MIN_CONFIDENCE <= z["confidence"] <= 1
        ]
        if len(anchors) != 1:
            raise bridge.Refusal("UI_MENU_STRUCTURE_UNVERIFIED")
        add = anchors[0].get("bounds") or {}
        if (not all(_finite_number(add.get(k))
                    for k in ("x", "y", "width", "height"))
                or not 6 <= add["height"] <= 20
                or not 6 <= rect["height"] <= 20
                or abs((add["x"] + add["width"] / 2)
                       - (rect["x"] + rect["width"] / 2)) > 16
                or not 42 <= (rect["y"] + rect["height"] / 2
                              - add["y"] - add["height"] / 2) <= 80):
            raise bridge.Refusal("UI_MENU_STRUCTURE_UNVERIFIED")
    x = round(rect["x"] + rect["width"] / 2 - origin_x)
    y = round(rect["y"] + rect["height"] / 2 - origin_y)
    if not (0 <= x < width and 0 <= y < height):
        raise bridge.Refusal("UI_MENU_BOUNDS_UNVERIFIED")
    if row_x is not None or row_y is not None:
        if (type(row_x) is not int or type(row_y) is not int
                or not -30 <= x - row_x <= 250
                or not -55 <= y - row_y <= 230):
            raise bridge.Refusal("UI_MENU_ROW_UNVERIFIED")
    return x, y


def read_clipboard() -> str:
    try:
        p = subprocess.run(["pbpaste"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True,
                           timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise bridge.Refusal("UI_CLIPBOARD_UNAVAILABLE") from exc
    if p.returncode != 0 or len(p.stdout) > MAX_CLIPBOARD:
        raise bridge.Refusal("UI_CLIPBOARD_UNAVAILABLE")
    return p.stdout.strip()


def write_clipboard(value: str) -> None:
    """Mark pasteboard before second Copy link; stale text is not proof."""
    if type(value) is not str or not value or len(value) > MAX_CLIPBOARD:
        raise bridge.Refusal("UI_CLIPBOARD_MARKER_INVALID")
    try:
        p = subprocess.run(["pbcopy"], input=value, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, text=True,
                           timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise bridge.Refusal("UI_CLIPBOARD_UNAVAILABLE") from exc
    if p.returncode != 0:
        raise bridge.Refusal("UI_CLIPBOARD_UNAVAILABLE")


def prune_one(plan: dict, page_id: str, operation_id: str,
              window_id: int, row_x: int, row_y: int, *,
              client, ui, clipboard, clipboard_set) -> dict:
    if not isinstance(operation_id, str) or not guard.OPERATION_RE.fullmatch(operation_id):
        raise bridge.Refusal("OPERATION_ID_REQUIRED")
    if not isinstance(window_id, int) or window_id <= 0:
        raise bridge.Refusal("UI_WINDOW_REQUIRED")
    if not all(isinstance(x, int) and 0 <= x < 16384 for x in (row_x, row_y)):
        raise bridge.Refusal("UI_ROW_COORDINATES_INVALID")
    delete_dispatched = False
    try:
        source, clone, current = _validate_plan_and_current(plan, client, page_id)
        before_clip = clipboard()
        with tempfile.TemporaryDirectory(prefix="paper-clone-ui-", dir=str(bridge.state_root())) as tmp:
            private_dir = Path(tmp)
            ui.click(window_id, row_x, row_y, right=True)
            opened = ui.menu(window_id, private_dir, row_x=row_x, row_y=row_y)
            copy_xy = _menu_target(opened, plan["clone_file_name"], "Copy link", window_id,
                                   row_x=row_x, row_y=row_y)
            _menu_target(opened, plan["clone_file_name"], "Delete page", window_id,
                         row_x=row_x, row_y=row_y)
            ui.click(window_id, *copy_xy)
            copied = clipboard()
            if before_clip == copied:
                raise bridge.Refusal("STALE_CLIPBOARD")
            link_file, link_page = native_page_identity(copied)
            if link_file != plan["clone_file_id"] or link_page != page_id:
                raise bridge.Refusal("UI_PAGE_ID_MISMATCH")
            _validate_plan_and_current(plan, client, page_id)
            # First menu identity is not enough: sidebar scrolling or focus
            # changes can make the next right-click target a different page.
            # Copy the link from the *second* menu before re-arming delete.
            ui.click(window_id, row_x, row_y, right=True)
            reopened = ui.menu(window_id, private_dir, row_x=row_x, row_y=row_y)
            _assert_same_row_visual(opened, reopened)
            second_copy_xy = _menu_target(reopened, plan["clone_file_name"], "Copy link", window_id,
                                          row_x=row_x, row_y=row_y)
            second_delete_xy = _menu_target(reopened, plan["clone_file_name"], "Delete page", window_id,
                                            row_x=row_x, row_y=row_y)
            marker = "paper-native-copy-check:" + operation_id
            clipboard_set(marker)
            if clipboard() != marker:
                raise bridge.Refusal("UI_CLIPBOARD_MARKER_NOT_SET")
            ui.click(window_id, *second_copy_xy)
            second_link = clipboard()
            if second_link == marker:
                raise bridge.Refusal("STALE_CLIPBOARD")
            second_file, second_page = native_page_identity(second_link)
            if second_file != plan["clone_file_id"] or second_page != page_id:
                raise bridge.Refusal("UI_PAGE_ID_MISMATCH")
            _validate_plan_and_current(plan, client, page_id)

            # Finish all Paper RPCs BEFORE opening the destructive menu.
            # The final screenshot is compared against two independently
            # observed sidebar-row pixels; same menu geometry alone would
            # miss a different target page after a reorder/scroll.
            ui.click(window_id, row_x, row_y, right=True)
            final_menu = ui.menu(window_id, private_dir, row_x=row_x, row_y=row_y)
            _assert_same_row_visual(opened, reopened, final_menu)
            _menu_target(final_menu, plan["clone_file_name"], "Copy link", window_id,
                         row_x=row_x, row_y=row_y)
            delete_xy = _menu_target(final_menu, plan["clone_file_name"], "Delete page", window_id,
                                     row_x=row_x, row_y=row_y)
            if (abs(delete_xy[0] - second_delete_xy[0]) > 12
                    or abs(delete_xy[1] - second_delete_xy[1]) > 12):
                raise bridge.Refusal("UI_MENU_RELOCATED")
            # No Paper RPC between exact-row visual proof and Delete.
            delete_dispatched = True
            try:
                ui.click(window_id, *delete_xy)
            except bridge.Refusal:
                # The UI might still have dispatched; compare original objects.
                pass
            source_after = _basic(client, plan["source_file_id"])
            clone_after = _basic(client, plan["clone_file_id"])
            expected = [p for p in current if p["id"] != page_id]
            if (guard._pages(source_after) != guard._pages(source)
                    or source_after["fileName"] != source["fileName"]
                    or guard._tokens_hash(source_after) != guard._tokens_hash(source)
                    or guard._pages(clone_after) != expected
                    or clone_after["fileName"] != clone["fileName"]
                    or guard._tokens_hash(clone_after) != guard._tokens_hash(clone)):
                raise bridge.Refusal("CLONE_PRUNE_EFFECT_UNKNOWN")
            # Verify retained native structure on BOTH source and clone after
            # the irreversible click. A stable page list/token digest is not
            # evidence that native content stayed intact.
            _retained_native_proof(plan, client, guard._pages(source))
            return {
                "schema": SCHEMA,
                "state": "CLONE_PAGE_UI_DELETE_VERIFIED",
                "operation_id": operation_id,
                "source_file_id": plan["source_file_id"],
                "clone_file_id": plan["clone_file_id"],
                "removed_page_id": page_id,
                "retained_page_ids": [p["id"] for p in expected],
                "source_page_list_unchanged": True,
                "retained_native_structure_reverified": True,
                "ui_copy_link_exact_target_verified": True,
                "retry_allowed": False,
                "production_migration_accepted": False,
                "original_deletion_authorized": False,
            }
    except Exception as exc:
        reason = exc.code if isinstance(exc, bridge.Refusal) else "UI_OPERATION_OR_READ_FAILED"
        return {
            "schema": SCHEMA,
            "state": "EFFECT_UNKNOWN" if delete_dispatched else reason,
            "reason": reason,
            "operation_id": operation_id,
            "retry_allowed": False,
            "original_deletion_authorized": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--window-id", type=int, required=True)
    parser.add_argument("--row-x", type=int, required=True)
    parser.add_argument("--row-y", type=int, required=True)
    parser.add_argument("--execute-ui-prune", action="store_true")
    args = parser.parse_args()
    if not args.execute_ui_prune:
        print(json.dumps({"schema": SCHEMA, "state": "UI_PRUNE_NOT_AUTHORIZED",
                          "retry_allowed": False}))
        return 2
    try:
        plan = bridge.load_json(args.plan.read_bytes())
        with bridge.desktop_lock(wait_seconds=30):
            client = bridge.PaperClient()
            client.initialize()
            schema = bridge.schema_receipt(client, client.catalog())
            if not schema["accepted_for_write"]:
                raise bridge.Refusal("UPSTREAM_SCHEMA_UNREVIEWED")
            result = prune_one(
                plan, args.page_id, args.operation_id,
                args.window_id, args.row_x, args.row_y,
                client=client, ui=NativePeekaboo(), clipboard=read_clipboard,
                clipboard_set=write_clipboard)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["state"] == "CLONE_PAGE_UI_DELETE_VERIFIED" else 2
    except (bridge.Refusal, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, bridge.Refusal) else "UI_PRUNE_PREPARE_FAILED"
        print(json.dumps({"schema": SCHEMA, "state": code, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

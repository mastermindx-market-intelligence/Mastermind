"""One real, owned Chrome fixture journey through an already-connected MCP client.

Opens one background tab only in the explicitly selected enrolled profile. No
permission changes, existing-tab navigation, model inference or action replay.
"""
from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading

HTML = b'''<!doctype html><html lang="en"><meta charset="utf-8"><title>T3 owned browser qualification</title>
<style>body{font:20px system-ui;margin:48px;max-width:750px}button{font:inherit;padding:14px 22px}output{display:block;margin:24px 0}</style>
<h1>Mastermind T3 browser qualification</h1><p>This isolated page contains no personal or production data.</p>
<button id="verify" onclick="document.querySelector('output').textContent='T3 BROWSER PROOF PASSED'">Verify continuity</button>
<output role="status" aria-live="polite">Waiting for the owned test action</output></html>'''


class JourneyBoundary(RuntimeError):
    pass


def structured(result):
    value = result.structured_content
    if type(value) is not dict:
        raise JourneyBoundary("MCP_RESULT_NOT_STRUCTURED")
    return value


async def exercise(session, base: dict, status_data: dict, log_path: Path) -> dict:
    if not log_path.is_absolute() or log_path.exists() or log_path.is_symlink():
        raise ValueError("New absolute operation log required before native effects")
    connection = status_data.get("connection_id")
    if type(connection) is not str or not connection:
        raise ValueError("Actual selected native connection required")
    path = "/t3-proof-" + secrets.token_hex(12)
    served = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != path:
                self.send_error(404);return
            self.send_response(200);self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store");self.end_headers();self.wfile.write(HTML);served.set()
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, name="owned-t3-browser-fixture", daemon=True)
    url = f"http://127.0.0.1:{server.server_port}" + path
    state = {"state": "STARTING", "checks": [], "tab_id": None, "cleanup": "NOT_REQUIRED",
             "native_model_calls": 0, "browser_profile": base.get("browser_id"), "fixture_contains_private_data": False}
    target, snapshot = None, None
    worker.start()
    with log_path.open("x", encoding="utf-8") as log:
        async def call(action, extra=None):
            arguments = {**base, "connection_id": connection, "action": action, **(extra or {})}
            # Native transport generates the actual operation key; this pre-call
            # line only identifies the original test action in a lost host return.
            log.write(json.dumps({"event": "CALL", "action": action, "tab_id": arguments.get("tab_id")}) + "\n");log.flush()
            result = await session.call_tool("mmx_browser", arguments)
            value = structured(result);receipt = value.get("receipt") or {}
            log.write(json.dumps({"event": "RETURN", "action": action, "state": value.get("state"),
                "reason": value.get("reason"), "status": receipt.get("status"), "effect": receipt.get("effect"),
                "request_ref": value.get("t3_request_ref"), "tab_id": (receipt.get("data") or {}).get("tab_id")}) + "\n");log.flush()
            if (value.get("state") != "RECEIPT" or receipt.get("status") not in {"OK", "ACTION_DISPATCHED"}):
                raise JourneyBoundary(str(receipt.get("status") or value.get("reason") or value.get("state")))
            return result, receipt.get("data") or {}
        try:
            _, opened = await call("open", {"url": url})
            state["tab_id"] = opened.get("tab_id")
            if type(state["tab_id"]) is not int:
                raise JourneyBoundary("OPEN_TAB_ID_NOT_OBSERVED")
            state["cleanup"] = "OWED_ORIGINAL_TAB"
            if not await asyncio.to_thread(served.wait, 10):
                raise JourneyBoundary("OWNED_PAGE_HTTP_REQUEST_NOT_OBSERVED")
            _, listed = await call("tabs")
            matches = [t for t in listed.get("tabs", []) if t.get("tab_id") == state["tab_id"]]
            if len(matches) != 1 or matches[0].get("url") != url:
                raise JourneyBoundary("OWNED_TAB_URL_MISMATCH")
            target = {"tab_id": state["tab_id"], "url_fingerprint": matches[0]["url_fingerprint"]}
            _, initial = await call("snapshot", target);snapshot = initial.get("snapshot_id")
            elements = [e for e in initial.get("elements", []) if e.get("name") == "Verify continuity"]
            if len(elements) != 1 or type(snapshot) is not str:
                raise JourneyBoundary("OWNED_ACTION_REFERENCE_NOT_OBSERVED")
            state["checks"].append("real_owned_background_tab_and_scoped_snapshot")
            await call("click", {**target, "snapshot_id": snapshot, "ref": elements[0]["ref"]})
            _, observed = await call("snapshot", target);snapshot = observed.get("snapshot_id")
            if "T3 BROWSER PROOF PASSED" not in observed.get("text", ""):
                raise JourneyBoundary("CLICK_POSTCONDITION_NOT_OBSERVED")
            state["checks"].append("real_native_click_and_fresh_dom_postcondition")
            capture, _ = await call("screenshot", {**target, "snapshot_id": snapshot})
            images = [item for item in capture.content if getattr(item, "type", None) == "image"]
            if len(images) != 1 or not images[0].data:
                raise JourneyBoundary("REAL_MCP_SCREENSHOT_ATTACHMENT_MISSING")
            state["checks"].append("real_selected_tab_screenshot_as_mcp_image")
            state["state"] = "PASS"
        except JourneyBoundary as error:
            state["state"], state["boundary"] = "PARTIAL", str(error)
        finally:
            if target is not None and snapshot is not None:
                try:
                    await call("close", {**target, "snapshot_id": snapshot})
                    _, listed = await call("tabs")
                    state["cleanup"] = ("VERIFIED_CLOSED" if not any(t.get("tab_id") == state["tab_id"]
                        for t in listed.get("tabs", [])) else "CLOSE_NOT_VERIFIED")
                except Exception:
                    state["cleanup"] = "ORIGINAL_CLOSE_EFFECT_REQUIRES_RECONCILIATION"
            server.shutdown();server.server_close();worker.join(timeout=2)
            log.write(json.dumps({"event": "FINAL", **state}) + "\n");log.flush()
    if state["cleanup"] != "VERIFIED_CLOSED":
        state["state"] = "PARTIAL"
    return state

"""Synthetic protocol and safety proof; NOT evidence of a real Paper installation."""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]

def load_local(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

b = load_local("mastermind_paper_bridge", ROOT / "integrations/paper_desktop/bridge.py")
install = load_local("mastermind_paper_install", ROOT / "integrations/paper_desktop/install.py")

INFO = {"fileName": "Mastermind scratch", "pageName": "Design", "nodeCount": 1,
        "artboards": [{"id": "board-a", "name": "Anchor", "width": 1200, "height": 800}]}

PAPER_0511_HEADER = {"file": {"id": "file-0511", "name": "Mastermind scratch"},
                     "contentHash": {"tokens": "token-hash"}}
PAPER_0511_DETAIL = {"fileName": "Mastermind scratch", "pageName": "Page 1",
                     "pageId": "p-1-0", "rootNodeId": "root-node", "nodeCount": 1,
                     "artboardCount": 0, "artboards": [],
                     "pages": [{"id": "p-1-0", "name": "Page 1", "isActive": True}],
                     "fontFamilies": [], "tokens": {"items": []}}
PAPER_0511_RESULT = {"structuredContent": PAPER_0511_HEADER,
                     "content": [{"type": "text", "text": json.dumps(PAPER_0511_HEADER)},
                                 {"type": "text", "text": json.dumps(PAPER_0511_DETAIL)}]}


class Fake:
    def __init__(self):
        self.info, self.calls, self.server = copy.deepcopy(INFO), [], {"name": "fixture"}
        self.error = self.drift = self.tool_error = False
    def initialize(self):
        return {}
    def catalog(self):
        return {n: {"name": n, "inputSchema": {"type": "object"}} for n in b.READ_TOOLS | b.EDIT_TOOLS | {"delete_nodes", "export", "launch_shell"}}
    def call(self, name, arguments):
        self.calls.append(name)
        if name == "get_basic_info":
            return {"structuredContent": copy.deepcopy(self.info)}
        if name in b.EDIT_TOOLS:
            self.info["nodeCount"] = self.info.get("nodeCount", 0) + 1
            if self.drift:
                self.info["fileName"] = "Another file"
            if self.error:
                raise TimeoutError()
            if self.tool_error:
                return {"isError": True, "content": [{"type": "text", "text": "partial failure"}]}
        return {"content": [{"type": "text", "text": "ok"}]}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = Fake()
    def tearDown(self):
        self.tmp.cleanup()
    def call(self, action="edit", **kwargs):
        params = dict(tool="create_artboard", arguments={}, expected_snapshot=b.digest(INFO),
                      operation_id="paper-proof-1", allow_write=True, client=self.client, lock_root=self.root)
        params.update(kwargs)
        return b.execute(action, **params)
    def test_write_requires_opt_in(self):
        with self.assertRaisesRegex(b.Refusal, "WRITE_DISABLED"):
            self.call(allow_write=False)
        self.assertEqual(self.client.calls, [])
    def test_write_requires_operation(self):
        with self.assertRaisesRegex(b.Refusal, "OPERATION_ID_REQUIRED"):
            self.call(operation_id=None)
    def test_write_requires_snapshot(self):
        with self.assertRaisesRegex(b.Refusal, "SNAPSHOT_REQUIRED"):
            self.call(expected_snapshot=None)
    def test_changed_document_refuses_before_edit(self):
        self.client.info["fileName"] = "Other"
        with self.assertRaisesRegex(b.Refusal, "DOCUMENT_CHANGED"):
            self.call()
        self.assertNotIn("create_artboard", self.client.calls)
    def test_unanchored_document_refuses(self):
        self.client.info["artboards"] = []
        with self.assertRaisesRegex(b.Refusal, "DOCUMENT_ANCHOR_REQUIRED"):
            self.call(expected_snapshot=b.digest(self.client.info))
    def test_stable_file_id_permits_empty_document(self):
        self.client.info = {"fileId": "file-a", "artboards": []}
        self.assertEqual(
            self.call(expected_snapshot=b.digest(self.client.info),
                      arguments={"fileId": "file-a"})["state"],
            "APPLIED_RESPONSE_OBSERVED",
        )

    def test_stable_file_id_requires_explicit_target(self):
        self.client.info = {"fileId": "file-a", "artboards": []}
        with self.assertRaisesRegex(b.Refusal, "FILE_ID_REQUIRED"):
            self.call(expected_snapshot=b.digest(self.client.info), arguments={})
        self.assertNotIn("create_artboard", self.client.calls)

    def test_stable_file_id_refuses_cross_file_edit(self):
        self.client.info = {"fileId": "file-a", "artboards": []}
        with self.assertRaisesRegex(b.Refusal, "FILE_ID_MISMATCH"):
            self.call(expected_snapshot=b.digest(self.client.info),
                      arguments={"fileId": "file-b"})
        self.assertNotIn("create_artboard", self.client.calls)

    def test_paper_0511_header_and_detail_merge(self):
        info = b.basic_object(copy.deepcopy(PAPER_0511_RESULT))
        self.assertEqual(info["fileId"], "file-0511")
        self.assertEqual(info["pageId"], "p-1-0")
        self.assertEqual(info["contentHash"], {"tokens": "token-hash"})
        self.assertEqual(b.document_identity(info), {"kind": "file-id", "id": "file-0511"})

    def test_paper_0511_conflicting_file_header_refuses(self):
        result = copy.deepcopy(PAPER_0511_RESULT)
        result["content"][1]["text"] = json.dumps(dict(PAPER_0511_DETAIL, fileName="Other"))
        with self.assertRaisesRegex(b.Refusal, "DOCUMENT_SCHEMA_UNVERIFIED"):
            b.basic_object(result)

    def test_current_safe_tool_classes(self):
        for name in ["list_files", "find_nodes", "get_tokens",
                     "list_comment_threads", "get_comment_thread",
                     "list_comment_thread_authors"]:
            self.assertIn(name, b.READ_TOOLS)
        for name in ["create_page", "create_tokens", "set_tokens",
                     "set_comment_thread_status"]:
            self.assertIn(name, b.EDIT_TOOLS)
        for name in ["create_file", "open_file", "delete_nodes", "export",
                     "export_combined_pdf"]:
            self.assertNotIn(name, b.READ_TOOLS | b.EDIT_TOOLS)

    def test_token_delete_refused_before_dispatch(self):
        self.client.info = {"fileId": "file-a", "artboards": []}
        with self.assertRaisesRegex(b.Refusal, "TOKEN_DELETE_NOT_ALLOWED"):
            self.call(tool="set_tokens", expected_snapshot=b.digest(self.client.info),
                      arguments={"fileId": "file-a",
                                 "tokens": [{"name": "--color-primary", "delete": True}]})
        self.assertNotIn("set_tokens", self.client.calls)
    def test_dispatched_timeout_is_unknown_no_retry(self):
        self.client.error = True
        result = self.call()
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(self.client.calls.count("create_artboard"), 1)
    def test_upstream_tool_error_is_not_safe_to_retry(self):
        self.client.tool_error = True
        self.assertEqual(self.call()["state"], "EFFECT_UNKNOWN")
    def test_postwrite_document_switch_is_unknown(self):
        self.client.drift = True
        self.assertEqual(self.call()["state"], "EFFECT_UNKNOWN")
    def test_applied_is_not_production_acceptance(self):
        result = self.call()
        self.assertEqual(result["state"], "APPLIED_RESPONSE_OBSERVED")
        self.assertFalse(result["production_acceptance"])
    def test_read_cannot_route_write(self):
        with self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
            self.call("read")
    def test_unknown_and_destructive_tools_blocked(self):
        for name in ["delete_nodes", "export", "launch_shell"]:
            with self.subTest(name=name), self.assertRaisesRegex(b.Refusal, "TOOL_NOT_ALLOWED"):
                self.call(tool=name)
    def test_lock_contention_refuses_without_upstream(self):
        with b.desktop_lock(self.root), self.assertRaisesRegex(b.Refusal, "DESKTOP_BUSY"):
            self.call()
        self.assertEqual(self.client.calls, [])
    def test_lock_symlink_refused(self):
        target = self.root / "unrelated"
        target.write_text("unchanged")
        (self.root / "desktop.lock").symlink_to(target)
        with self.assertRaises(OSError):
            self.call()
        self.assertEqual(target.read_text(), "unchanged")
    def test_duplicate_json_rejected(self):
        with self.assertRaisesRegex(b.Refusal, "DUPLICATE_JSON_KEY"):
            b.load_json('{"tool":"read","tool":"edit"}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(b.Refusal, "INVALID_JSON"):
            b.load_json('{"x":NaN}')
    def test_catalog_filters_unknown_tools(self):
        result = self.call("catalog")
        self.assertIn("launch_shell", result["blocked_tools"])
        self.assertNotIn("launch_shell", [x["name"] for x in result["tools"]])
    def test_status_does_not_invent_quota(self):
        result = self.call("status")
        self.assertIsNone(result["quota_remaining"])
        self.assertEqual(result["plan"], "UNKNOWN")
    def test_unknown_document_schema_refuses_writes(self):
        self.client.info = {"arbitrary": "data"}
        with self.assertRaisesRegex(b.Refusal, "DOCUMENT_SCHEMA_UNVERIFIED"):
            self.call(expected_snapshot=b.digest(self.client.info))
    def test_image_artifact_no_overwrite(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        value = {"result": {"content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()}]}}
        directory = self.root / "artifacts"
        saved = b.save_artifacts(value, directory)
        self.assertEqual(Path(saved["artifact_paths"][0]).read_bytes(), png)
        with self.assertRaisesRegex(b.Refusal, "ARTIFACT_EXISTS"):
            b.save_artifacts(value, directory)
    def test_staging_is_scoped_and_no_overwrite(self):
        dest = self.root / "install"
        receipt = install.stage(dest, sys.executable)
        self.assertFalse(receipt["provider_homes_modified"])
        self.assertFalse(receipt["executive_production_armed"])
        with self.assertRaises(ValueError):
            install.stage(dest, sys.executable)
    def test_sse_matching_response(self):
        wire = b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n'
        result = b.PaperClient()._sse(io.BytesIO(wire), 2, b.time.monotonic() + 1)
        self.assertTrue(result["result"]["ok"])
    def test_incomplete_sse_refuses(self):
        with self.assertRaisesRegex(b.Refusal, "INCOMPLETE_SSE_RESPONSE"):
            b.PaperClient()._sse(io.BytesIO(b""), 1, b.time.monotonic() + 1)


class WireTests(unittest.TestCase):
    """Real local HTTP request/response, but the Paper application is SYNTHETIC."""
    def test_handshake_session_json_and_sse(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((request, dict(self.headers)))
                method = request["method"]
                if method == "notifications/initialized":
                    self.send_response(202); self.end_headers(); return
                if method == "initialize":
                    result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "synthetic-paper", "version": "fixture"}, "capabilities": {"tools": {}}}
                elif method == "tools/list":
                    result = {"tools": [{"name": "get_basic_info", "inputSchema": {"type": "object"}}]}
                else:
                    result = {"content": [{"type": "text", "text": json.dumps(INFO)}]}
                data = b.encode({"jsonrpc": "2.0", "id": request["id"], "result": result})
                sse = method == "tools/call"
                if sse:
                    data = b"data: " + data + b"\n\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
                self.send_header("Mcp-Session-Id", "fixture-session")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        actual = b.http.client.HTTPConnection
        def connection(host, port, **kwargs):
            self.assertEqual((host, port), ("127.0.0.1", 29979))
            return actual("127.0.0.1", server.server_port, **kwargs)
        try:
            with patch.object(b.http.client, "HTTPConnection", connection):
                client = b.PaperClient(); client.initialize(); client.catalog()
                result = b.snapshot(client)
            self.assertTrue(result["write_binding_ready"])
            self.assertEqual(seen[1][1]["Mcp-Session-Id"], "fixture-session")
            self.assertEqual(seen[-1][0]["params"]["name"], "get_basic_info")
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == "__main__":
    unittest.main()

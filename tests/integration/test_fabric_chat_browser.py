"""Required real-browser proof for the actual chat asset's recovery protocol."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import unittest


class ChatRecoveryBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("MM_REQUIRE_FABRIC_BROWSER") != "1":
            raise unittest.SkipTest("Run in the required paired Fabric browser step")
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.calls = []
        self.release = threading.Event()
        self.mode = "partial"
        outer = self
        source = Path(__file__).resolve().parents[2] / "app/static/chat.js"

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def reply(self, body, kind="text/html"):
                data = body if isinstance(body, bytes) else body.encode()
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.startswith("/chat/history"):
                    self.reply('{"turns":[]}', "application/json")
                elif self.path == "/chat.js":
                    self.reply(source.read_bytes(), "application/javascript")
                else:
                    self.reply('<!doctype html><html lang="en"><body class="page-mm"><script src="/chat.js"></script></body></html>')

            def do_POST(self):
                packet = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.calls.append(packet)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()

                def event(value):
                    self.wfile.write(("data: " + json.dumps(value) + "\n\n").encode())
                    self.wfile.flush()

                start = {"type": "start", "backend": "fabric", "conversation_id": packet["conversation_id"],
                         "turn_id": packet["turn_id"]}
                if packet.get("recover_only"):
                    event(start)
                    if outer.mode == "unknown":
                        event({"type": "error", "error": "fabric_turn_receipt_missing", "unsettled": True})
                    else:
                        event({"type": "text", "text": "The saved result."})
                        event({"type": "done", "replayed": True})
                elif outer.mode == "partial":
                    event(start)
                    event({"type": "text", "text": "Known partial observation."})
                    event({"type": "tool", "name": "mcp__bot__propose_thesis", "args": {"subject": "TEST"}})
                    outer.release.wait(10)
                    # A real socket EOF without done/tool_result leaves an
                    # unresolved request, not a completed proposal chip.
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.release.set()
        self.context.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def open(self):
        self.page.goto(self.url)
        self.page.locator("#bc-launch").click()

    def send(self, text):
        self.page.locator("#bc-in").fill(text)
        self.page.locator("#bc-send").click()

    def test_partial_stream_preserves_text_and_unknown_tool_then_recovers_original_receipt(self):
        self.open()
        self.send("Explain the observation.")
        self.page.get_by_text("Known partial observation.", exact=True).wait_for()
        self.assertTrue(self.page.locator("#bc-new").is_disabled())
        self.release.set()
        recover = self.page.get_by_role("button", name="Recover this request", exact=True)
        recover.wait_for()
        self.assertEqual(self.page.locator(".bc-chip.unconfirmed").count(), 1)
        self.assertEqual(self.page.locator(".bc-chip.done").count(), 0)
        self.assertTrue(self.page.get_by_text("Known partial observation.", exact=True).is_visible())
        original = dict(self.calls[0])
        saved = self.page.evaluate("id => JSON.parse(localStorage.getItem('bc_pending_turn:' + id))", original["conversation_id"])
        self.assertEqual(saved["turn_id"], original["turn_id"])
        self.assertTrue(self.page.locator("#bc-send").is_disabled())
        recover.click()
        self.page.get_by_text("The saved result.", exact=True).wait_for()
        self.page.wait_for_function("!document.querySelector('#bc-send').disabled")
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(self.calls[1]["recover_only"])
        self.assertEqual({key: self.calls[1][key] for key in original}, original)
        self.assertIsNone(self.page.evaluate("id => localStorage.getItem('bc_pending_turn:' + id)", original["conversation_id"]))

    def test_missing_start_keeps_original_request_reachable_after_new_conversation_and_reload(self):
        self.mode = "unknown"
        self.open()
        self.send("Original unconfirmed question.")
        self.page.get_by_role("button", name="Recover this request", exact=True).wait_for()
        original = dict(self.calls[0])
        self.page.locator("#bc-new").click()
        self.page.reload()
        self.page.locator("#bc-launch").click()
        self.page.get_by_role("button", name="Unconfirmed request: Original unconfirmed question.", exact=True).click()
        self.page.get_by_role("button", name="Recover this request", exact=True).click()
        self.page.get_by_text("Error: fabric_turn_receipt_missing", exact=True).wait_for()
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(self.calls[1]["recover_only"])
        self.assertEqual({key: self.calls[1][key] for key in original}, original)
        self.assertIsNotNone(self.page.evaluate("id => localStorage.getItem('bc_pending_turn:' + id)", original["conversation_id"]))

    def test_failed_identity_storage_sends_no_http_request(self):
        self.page.add_init_script("Storage.prototype.setItem = function () { throw new Error('unavailable'); };")
        self.open()
        self.send("Do not send without an identity.")
        self.page.get_by_text("The request ID could not be saved. Nothing was sent.", exact=True).wait_for()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

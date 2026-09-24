"""Isolated real-code Agenda/API/browser proof, not a deployed-service claim."""
from __future__ import annotations

from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pytest import MonkeyPatch
from playwright.sync_api import sync_playwright
from brain import improvement_agenda as agenda
from app import web


def main() -> None:
    evidence = Path(__file__).parent
    bundle = json.loads((evidence / "GMI_SOURCE_CANARY_2026-09-24.input.json").read_text())
    expected = json.loads((evidence / "GMI_SOURCE_CANARY_2026-09-24.result.json").read_text())
    with tempfile.TemporaryDirectory(prefix="mmx-improvement-browser-") as temp, MonkeyPatch.context() as patch:
        root = Path(temp)
        patch.setattr(agenda, "_OUT", root / "agenda")
        patch.setattr(agenda, "_ROOT", root)
        patch.setattr(agenda, "_VALIDATION_DIR", root / "validation")
        for name in ("_from_calibration", "_from_journal", "_from_shadow", "_from_benchmark",
                     "_from_book_lifecycle", "_from_validation", "_from_cost_guard", "_from_deploy_lag",
                     "_from_model_drift", "_from_nw_reflection", "_from_experiment_registry",
                     "_from_accruing_experiments", "_from_experiment_tristate"):
            patch.setattr(agenda, name, lambda *args: [])
        patch.setattr(agenda, "_load_agentos_readiness", lambda: ({}, {
            "available": False, "degraded": ["Isolated browser proof: other sources not evaluated"],
            "schema": None}, "macro_unavailable"))
        report = agenda.build(date(2026, 9, 24), cio_rep={}, discovery_bundle=bundle,
                              discovery_now=expected["as_of"])
        assert agenda.write(date(2026, 9, 24), prebuilt=report)["ok"]
        # Actual application endpoint calls actual latest(), not a manufactured JSON answer.
        api = web.api_agenda()
        assert api.status_code == 200
        assert json.loads(api.body)["discovery"]["n_expectations"] == 7
        assert "finance-preflight" not in api.body.decode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/agenda":
                    response = web.api_agenda()
                    status, data, content_type = response.status_code, response.body, "application/json"
                elif self.path.split("?")[0] in {"/agenda", "/theme.css", "/theme.js"}:
                    name = "agenda.html" if self.path == "/agenda" else self.path[1:].split("?")[0]
                    path = ROOT / "app" / "static" / name
                    status, data = (200, path.read_bytes()) if path.exists() else (404, b"")
                    content_type = "text/css" if name.endswith("css") else "text/javascript" if name.endswith("js") else "text/html"
                else:
                    status, data, content_type = 404, b"", "text/plain"
                self.send_response(status); self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        checks = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                for width in (1440, 390):
                    for theme in ("dark", "light"):
                        context = browser.new_context(viewport={"width": width, "height": 1000})
                        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith("http://127.0.0.1:") else route.abort())
                        page = context.new_page()
                        page.goto(f"http://127.0.0.1:{server.server_port}/agenda", wait_until="networkidle")
                        page.evaluate("theme => document.documentElement.setAttribute('data-theme', theme)", theme)
                        page.locator("#root .note").first.wait_for()
                        assert "7 expectations reviewed" in page.locator("#root").inner_text()
                        assert "independent discovery unproven" in page.locator("#root").inner_text()
                        assert "finance-preflight" not in page.content()
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                        image = evidence / f"agenda-discovery-{width}-{theme}.png"
                        page.screenshot(path=str(image), full_page=True)
                        checks.append({"width": width, "theme": theme, "screenshot": image.name,
                                       "visible_discovery": True, "private_prose_excluded": True,
                                       "no_horizontal_overflow": True})
                        context.close()
                browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        # Existing API also serves an honestly unavailable sensor without hiding the agenda.
        unavailable = agenda.build(date(2026, 9, 24), cio_rep={})
        assert agenda.write(date(2026, 9, 24), prebuilt=unavailable)["ok"]
        api_unknown = json.loads(web.api_agenda().body)
        assert api_unknown["discovery"]["state"] == "UNAVAILABLE"
        assert "zero gaps cannot be inferred" in api_unknown["note"]
        receipt = {
            "scope": "LOCAL_ISOLATED_REAL_CODE_AND_PINNED_SOURCE_SNAPSHOT",
            "production_proven": False, "independent_discovery_proven": False,
            "other_portfolio_agentos_sources": "ISOLATED_NOT_EVALUATED",
            "source_report_digest": expected["digest"], "browser_checks": checks,
            "actual_api_reader": "app.web.api_agenda -> brain.improvement_agenda.latest",
            "code_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in [ROOT / "brain/improvement_discovery.py", ROOT / "brain/improvement_agenda.py",
                                         ROOT / "app/static/agenda.html"]},
        }
        (evidence / "BROWSER_PROOF_2026-09-24.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

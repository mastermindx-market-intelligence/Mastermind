"""Isolated real-code Agenda/API/browser proof, not a deployed-service claim."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("gmi-snapshot", "owner-coverage"), default="gmi-snapshot")
    owner_case = parser.parse_args().case == "owner-coverage"
    expected_count = 1 if owner_case else 7
    image_prefix = "agenda-owner" if owner_case else "agenda-discovery"
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
        if owner_case:
            from brain import nw_reflection, neural_web_context, ledger
            from brain import improvement_discovery_nw
            now = datetime.now(timezone.utc).isoformat()
            asof = date.fromisoformat(now[:10])
            # Production is a Git archive. The same existing deploy marker must
            # qualify the default read without adding .git or a discovery marker.
            import subprocess
            release_root = root / "release"; (release_root / "brain").mkdir(parents=True)
            (release_root / "brain/nw_reflection.py").write_bytes((ROOT / "brain/nw_reflection.py").read_bytes())
            release_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
            (release_root / ".deployed_git_sha").write_text(release_sha + "\n")
            assert not (release_root / ".git").exists()
            patch.setattr(agenda, "_ROOT", release_root)
            patch.setattr(nw_reflection, "_ROOT", root)
            owner_path = root / "owner-latest.json"
            patch.setattr(nw_reflection, "_LATEST", owner_path)
            thesis_path = root / "data/brain/theses.jsonl"
            thesis_path.parent.mkdir(parents=True)
            thesis_path.write_text('\n'.join(json.dumps({"subject": x, "status": "open"}) for x in ("AAA", "BBB")))
            thesis_path.with_name("outcome_ledger.jsonl").write_text(json.dumps({"subject": "CCC"}))
            patch.setattr(ledger, "_LEDGER", thesis_path)
            patch.setattr(neural_web_context, "context", lambda: {"candidate_context": {"AAA": {}}})
            owner_snapshot = {"schema": nw_reflection.SCHEMA, "asof": asof.isoformat(),
                "generated_at": now, "coverage": nw_reflection.coverage(), "nudges": [],
                "private_note": "PRIVATE_OWNER_PROOF_SENTINEL"}
            owner_path.write_text(json.dumps(owner_snapshot))  # synthetic owner fixture only
            revision, contract_digest = improvement_discovery_nw._source_identity(release_root)
            expected = improvement_discovery_nw.evaluate_owner_snapshot(owner_snapshot,
                source_revision=revision, contract_sha256=contract_digest, observed_at=now)
            report = agenda.build(asof, cio_rep={})  # no injected discovery bundle or projection
            assert report["discovery"]["diagnosis_counts"] == {"EVIDENCED_GAP": 1}
        else:
            asof = date(2026, 9, 24)
            report = agenda.build(asof, cio_rep={}, discovery_bundle=bundle,
                                  discovery_now=expected["as_of"])
        assert agenda.write(asof, prebuilt=report)["ok"]
        # Actual application endpoint calls actual latest(), not a manufactured JSON answer.
        api = web.api_agenda()
        assert api.status_code == 200
        assert json.loads(api.body)["discovery"]["n_expectations"] == expected_count
        assert "PRIVATE_OWNER_PROOF_SENTINEL" not in api.body.decode()
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
                        assert f"{expected_count} expectations reviewed" in page.locator("#root").inner_text()
                        assert "PRIVATE_OWNER_PROOF_SENTINEL" not in page.content()
                        assert "independent discovery unproven" in page.locator("#root").inner_text()
                        assert "finance-preflight" not in page.content()
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                        image = evidence / f"{image_prefix}-{width}-{theme}.png"
                        page.screenshot(path=str(image), full_page=True)
                        checks.append({"width": width, "theme": theme, "screenshot": image.name,
                                       "visible_discovery": True, "private_prose_excluded": True,
                                       "no_horizontal_overflow": True})
                        context.close()
                browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        # Existing API also serves an honestly unavailable sensor without hiding the agenda.
        if owner_case:
            owner_snapshot.update(asof="2026-07-21", generated_at="2026-07-21T07:00:00Z")
            owner_path.write_text(json.dumps(owner_snapshot))
            stale = agenda.build(asof, cio_rep={})
            assert stale["discovery"]["diagnosis_counts"] == {"HELD_SOURCE": 1}
            assert agenda.write(asof, prebuilt=stale)["ok"]
            assert json.loads(web.api_agenda().body)["discovery"]["diagnosis_counts"] == {"HELD_SOURCE": 1}
            owner_path.write_text('{"broken"')
        unavailable = agenda.build(asof, cio_rep={})
        assert agenda.write(asof, prebuilt=unavailable)["ok"]
        api_unknown = json.loads(web.api_agenda().body)
        assert api_unknown["discovery"]["state"] == "UNAVAILABLE"
        assert "zero gaps cannot be inferred" in api_unknown["note"]
        receipt = {
            "scope": "LOCAL_SYNTHETIC_OWNER_INPUTS_REAL_OWNER_AND_AGENDA_CODE" if owner_case else "LOCAL_ISOLATED_REAL_CODE_AND_PINNED_SOURCE_SNAPSHOT",
            "language": "EN", "automatic_owner_input": owner_case,
            "archive_root_without_git": owner_case,
            "stale_and_malformed_owner_rechecked": owner_case,
            "production_proven": False, "independent_discovery_proven": False,
            "other_portfolio_agentos_sources": "ISOLATED_NOT_EVALUATED",
            "source_report_digest": expected["digest"], "browser_checks": checks,
            "actual_api_reader": "app.web.api_agenda -> brain.improvement_agenda.latest",
            "code_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in [ROOT / "brain/improvement_discovery.py", ROOT / "brain/improvement_agenda.py",
                                         ROOT / "app/static/agenda.html", ROOT / "brain/nw_reflection.py",
                                         ROOT / "brain/improvement_discovery_nw.py", Path(__file__)]},
        }
        (evidence / ("OWNER_BROWSER_PROOF_2026-09-24.json" if owner_case else "BROWSER_PROOF_2026-09-24.json")).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

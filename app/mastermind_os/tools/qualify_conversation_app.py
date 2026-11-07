"""Prove the actual App navigation/draft/reader path with isolated synthetic reads.

No real authenticated profile, command transport, provider, session or parent
consumption is involved. Run only against the compiled loopback proof artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:5193")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = urlparse(args.origin)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        parser.error("a dedicated loopback origin is required")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for name, width, height in [("desktop", 1440, 1100), ("mobile", 390, 844)]:
                context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
                page = context.new_page()
                errors, external = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                def guard(route):
                    host = urlparse(route.request.url).hostname
                    if host not in {"127.0.0.1", "localhost", "::1"}:
                        external.append(host)
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", guard)
                page.goto(args.origin.rstrip("/") + "/os/conversation-app-proof.html", wait_until="networkidle")
                direction = page.get_by_role("textbox", name="Direction to Meta-CEO", exact=True)
                direction.fill("Office direction stays separate")
                page.get_by_role("button", name="Conversations", exact=True).click()
                search = page.get_by_role("searchbox", name="Search observed responses", exact=True)
                search.wait_for()
                page.get_by_role("button", name="Unsent notes", exact=True).click()
                notes = page.get_by_role("textbox", name="Unsent notes", exact=True)
                notes.fill("Retain this conversation draft")
                search.fill("source integration")
                page.get_by_text("1 of 1 visible responses match", exact=True).wait_for()
                page.get_by_role("button", name="Formatted responses", exact=True).click()
                viewport = page.get_by_role("region", name="Observed response list", exact=True)
                viewport.scroll_into_view_if_needed()
                page.get_by_role("heading", name="Source integration is ready for review", exact=True).wait_for()
                assert notes.input_value() == "Retain this conversation draft"
                assert page.locator(".source-markdown a,.source-markdown img,.source-markdown iframe").count() == 0
                assert not viewport.evaluate("e=>e.scrollWidth>e.clientWidth+1")
                assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
                page.get_by_role("button", name="Review evidence", exact=True).click()
                page.get_by_role("region", name="Conversation evidence", exact=True).wait_for()
                assert notes.input_value() == "Retain this conversation draft"
                page.get_by_role("button", name="Close evidence", exact=True).click()
                assert page.get_by_role("button", name="Review evidence", exact=True).evaluate("e=>document.activeElement===e")
                page.get_by_role("button", name="Knowledge", exact=True).click()
                page.get_by_role("region", name="Knowledge source", exact=True).wait_for()
                page.get_by_role("button", name="Conversations", exact=True).click()
                page.get_by_role("searchbox").wait_for()
                page.get_by_role("button", name="Unsent notes", exact=True).click()
                assert page.get_by_role("textbox", name="Unsent notes", exact=True).input_value() == "Retain this conversation draft"
                page.get_by_role("button", name="Today", exact=True).click()
                assert page.get_by_role("textbox", name="Direction to Meta-CEO", exact=True).input_value() == "Office direction stays separate"
                page.get_by_role("button", name="Conversations", exact=True).click()
                page.get_by_role("button", name="Formatted responses", exact=True).click()
                viewport = page.get_by_role("region", name="Observed response list", exact=True)
                viewport.scroll_into_view_if_needed()
                page.get_by_role("heading", name="Source integration is ready for review", exact=True).wait_for()
                page.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(args.output / f"app-{name}.png"), full_page=True)
                assert page.get_by_role("button", name="Send message", exact=True).count() == 0
                telemetry = page.locator("#fixture-read-counts").inner_text()
                counts = json.loads(telemetry.split(": ", 1)[1])
                assert counts.get("read_current_window", 0) >= 1
                assert not any("submit" in command or "session_send" in command for command in counts)
                page.get_by_role("button", name="Fixture: withdraw authenticated projection", exact=True).click()
                page.get_by_role("heading", name="Source integration is ready for review", exact=True).wait_for(state="detached")
                assert page.get_by_role("searchbox").count() == 0
                assert "Retain this conversation draft" not in page.locator("#root").inner_text()
                assert not errors, errors
                assert not external, external
                results.append({"viewport": name, "width": width, "height": height,
                    "actual_app_shell": True, "reader_and_draft_navigation": True,
                    "office_and_conversation_drafts_separate": True, "evidence_return_focus": True,
                    "source_withdrawal_hides_reader": True, "document_horizontal_overflow": False,
                    "transcript_horizontal_overflow": False, "synthetic_command_counts": counts,
                    "page_errors": errors, "external_requests": external})
                context.close()
        finally:
            browser.close()
    result = {"schema": "mastermind.conversation_app.browser_fixture.v1", "proof_scope": "SOURCE_FIXTURE_ONLY",
        "production_authentication": False, "real_send": False, "provider_calls": 0,
        "parent_consumption": False, "results": results,
        "screenshot_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.glob("app-*.png"))}}
    (args.output / "app-browser-proof.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

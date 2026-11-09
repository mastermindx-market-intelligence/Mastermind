"""Loopback-only browser qualification of actual ConversationWindow components.

Requires the existing Python Playwright install and a dedicated Vite dev server.
This deliberately uses synthetic fixtures, never a signed-in profile or real SEND.
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
    origin = urlparse(args.origin)
    if origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"} or origin.username or origin.password:
        parser.error("only a dedicated loopback HTTP origin is allowed")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, width, height in [("desktop", 1440, 1100), ("mobile", 390, 844)]:
            context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
            page = context.new_page()
            errors, external = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            def guard(route):
                target = urlparse(route.request.url)
                if target.hostname not in {"127.0.0.1", "localhost", "::1"}:
                    external.append(target.hostname)
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", guard)
            page.goto(args.origin.rstrip("/") + "/os/conversation-reading-proof.html", wait_until="networkidle")
            viewport = page.get_by_role("region", name="Observed response list")
            viewport.wait_for()
            page.wait_for_function("""() => { const e=document.querySelector('.observed-transcript-viewport');
                return e && e.scrollHeight>e.clientHeight && Math.abs(e.scrollTop-(e.scrollHeight-e.clientHeight))<2; }""")
            viewport.evaluate("e => { e.scrollTop=200; }")
            page.get_by_text("Reading earlier responses", exact=True).wait_for()
            before = viewport.evaluate("e=>e.scrollTop")
            page.get_by_role("button", name="Fixture: append observation", exact=True).click()
            page.wait_for_function("document.querySelectorAll('.conversation-response').length===20")
            after = viewport.evaluate("e=>e.scrollTop")
            assert abs(before-after) < 2, {"before": before, "after": after}
            page.get_by_role("button", name="Jump to latest observed response", exact=True).click()
            page.wait_for_function("""() => { const e=document.querySelector('.observed-transcript-viewport');
                return Math.abs(e.scrollTop-(e.scrollHeight-e.clientHeight))<2; }""")
            assert viewport.evaluate("e=>document.activeElement===e")
            search = page.get_by_role("searchbox")
            original_notes = page.get_by_role("textbox").input_value()
            search.fill("observed-1-1.")
            page.get_by_text("1 of 19 visible responses match", exact=True).wait_for()
            assert page.get_by_role("textbox").input_value() == original_notes
            page.get_by_role("button", name="Formatted responses", exact=True).click()
            page.get_by_role("heading", name="Observation 1-1", exact=True).wait_for()
            assert page.locator(".source-markdown a,.source-markdown img,.source-markdown iframe").count() == 0
            assert page.get_by_text("Content withheld by its owner.", exact=True).count() == 1
            search.press("Escape")
            assert search.input_value() == ""
            assert search.evaluate("e=>document.activeElement===e")
            search.fill("scope must reset")
            page.get_by_role("button", name="Fixture: change source epoch", exact=True).click()
            page.wait_for_function("document.querySelector('input[type=search]').value===''")
            assert page.get_by_role("textbox").input_value() == original_notes
            page.get_by_role("button", name="Fixture: toggle withheld", exact=True).click()
            assert page.get_by_role("searchbox").count() == 0
            assert page.locator(".conversation-response").count() == 0
            page.get_by_role("button", name="Fixture: toggle withheld", exact=True).click()
            page.get_by_role("searchbox").wait_for()
            page.get_by_role("button", name="Formatted responses", exact=True).click()
            viewport.evaluate("e=>{e.scrollTop=0;}")
            page.get_by_role("heading", name="Observation 2-1", exact=True).wait_for()
            page.get_by_text("Reading earlier responses", exact=True).wait_for()
            page.evaluate("window.scrollTo(0,0)")
            dark = page.locator("main.shell").evaluate("e=>getComputedStyle(e).backgroundColor")
            overflow = page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
            assert not overflow
            internal_overflow = viewport.evaluate("e=>e.scrollWidth>e.clientWidth+1")
            assert not internal_overflow, "The transcript must not hide content behind horizontal viewport scrolling"
            page.screenshot(path=str(args.output / f"{name}-dark.png"), full_page=True)
            page.get_by_role("button", name="Fixture: toggle theme", exact=True).click()
            light = page.locator("main.shell").evaluate("e=>getComputedStyle(e).backgroundColor")
            assert dark != light, {"dark": dark, "light": light}
            page.screenshot(path=str(args.output / f"{name}-light.png"), full_page=True)
            if name == "mobile":
                page.get_by_role("button", name="Fixture: toggle language", exact=True).click()
                page.get_by_role("searchbox", name="搜索已观察的回复", exact=True).wait_for()
                page.screenshot(path=str(args.output / "mobile-zh.png"), full_page=True)
            assert not errors, errors
            assert not external, external
            results.append({"viewport": name, "width": width, "height": height,
                "preserved_reading_top_before": before, "preserved_reading_top_after": after,
                "jump_to_latest": True, "search_and_literal_scope": True, "notes_unchanged": True,
                "source_epoch_resets_search": True, "withdrawn_source_hidden": True,
                "inert_markdown": True, "horizontal_overflow": overflow, "transcript_horizontal_overflow": internal_overflow,
                "dark_background": dark, "light_background": light,
                "page_errors": errors, "external_requests": external})
            context.close()
        browser.close()
    screenshots = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.glob("*.png"))}
    result = {"schema": "mastermind.observed_transcript.browser_fixture.v1", "proof_scope": "SOURCE_FIXTURE_ONLY",
        "production_authentication": False, "real_provider_calls": 0, "real_send": False,
        "parent_consumption": False, "results": results, "screenshot_sha256": screenshots}
    (args.output / "browser-proof.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

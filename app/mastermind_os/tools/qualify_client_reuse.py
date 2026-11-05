#!/usr/bin/env python3
"""Qualify actual client components on a dedicated loopback SOURCE FIXTURE.

Requires the existing Playwright Python installation and Chromium. Start the
app's Vite server on 127.0.0.1:5192, then run this script. This never authenticates,
uses a real provider, submits a real message, or opens an existing browser profile.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5192")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    address = urlparse(args.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in {"127.0.0.1", "localhost", "::1"}
        or address.username is not None
        or address.password is not None
        or address.path not in {"", "/"}
        or address.query
        or address.fragment
    ):
        parser.error("Use a dedicated unauthenticated loopback origin only.")
    origin = args.base_url.rstrip("/")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for name, width, height in (("desktop", 1440, 1100), ("mobile", 390, 844)):
                context = browser.new_context(
                    viewport={"width": width, "height": height}, device_scale_factor=1
                )
                blocked = []
                errors = []

                def route(request):
                    if request.request.url.startswith((origin + "/", "data:", "blob:")):
                        request.continue_()
                    else:
                        blocked.append(request.request.url)
                        request.abort()

                context.route("**/*", route)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin + "/os/client-reuse-proof.html", wait_until="networkidle")
                page.get_by_role("heading", name="Read clearly. Continue deliberately.").wait_for()
                assert page.locator("#fixture-banner").is_visible()
                assert page.locator(".source-markdown a,.source-markdown img,.source-markdown iframe").count() == 0
                assert page.locator(".source-markdown table").count() == 1
                assert page.locator(".source-code-block pre code").inner_text().startswith("const result =")
                instruction = page.get_by_label("What would you like done?")
                condition = page.get_by_label("How will we know it is done?")
                instruction.fill("Inspect the exact result and continue the original project.")
                condition.fill("Return source-backed findings without starting another operation.")
                instruction.press("Enter")
                assert "count: 0." in page.locator("#fixture-send-count").inner_text()
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                dark = page.locator("main").evaluate("node => getComputedStyle(node).backgroundColor")
                page.evaluate("scrollTo(0, 0)")
                page.screenshot(path=str(args.output / f"{name}-dark.png"), full_page=True)
                instruction.press("Control+Enter")
                assert "count: 1." in page.locator("#fixture-send-count").inner_text()
                assert page.get_by_role("button", name="Sending", exact=False).is_disabled()
                page.get_by_role("button", name="Toggle theme").click()
                light = page.locator("main").evaluate("node => getComputedStyle(node).backgroundColor")
                assert light != dark, "The actual shell light tokens must be applied."
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                page.evaluate("scrollTo(0, 0)")
                page.screenshot(path=str(args.output / f"{name}-light.png"), full_page=True)
                assert not blocked, blocked
                assert not errors, errors
                results.append({
                    "viewport": name, "width": width, "height": height,
                    "horizontal_overflow": False, "page_errors": errors,
                    "external_requests": blocked, "plain_enter_sends": 0,
                    "ctrl_enter_fixture_callbacks": 1, "inert_markdown": True,
                    "dark_background": dark, "light_background": light,
                })
                context.close()
        finally:
            browser.close()
    receipt = {
        "schema": "mastermind.client_reuse.browser_fixture.v1",
        "proof_scope": "SOURCE_FIXTURE_ONLY",
        "base_sha": "d31aade92b969e8897513d8634ecd59dba00e1e3",
        "upstream_sha": "687f282e8625c6b8d11ff58211a90524be2e4317",
        "production_authentication": False, "real_provider_calls": 0,
        "real_send": False, "parent_consumption": False, "results": results,
    }
    (args.output / "browser-proof.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

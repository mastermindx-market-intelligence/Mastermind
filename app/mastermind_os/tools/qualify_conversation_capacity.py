"""Bounded, loopback-only capacity probe for the compiled conversation fixture.

Synthetic input matches existing visible-window count/byte ceilings. This does not
validate runtime provenance or make a production responsiveness guarantee.
"""
from __future__ import annotations
import argparse
import json
import time
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
        parser.error("a dedicated loopback origin is required")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
            page.set_default_timeout(15000)
            errors, external = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            def guard(route):
                host = urlparse(route.request.url).hostname
                if host not in {"localhost", "127.0.0.1", "::1"}:
                    external.append(host)
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", guard)
            page.goto(args.origin.rstrip("/") + "/os/conversation-reading-proof.html?stress=bounded-markdown", wait_until="networkidle")
            viewport = page.get_by_role("region", name="Observed response list")
            viewport.wait_for()
            rows = page.locator(".conversation-response").count()
            raw_bytes = page.locator(".conversation-answer").evaluate_all("rows=>rows.reduce((n,e)=>n+new TextEncoder().encode(e.textContent).length,0)")
            assert rows == 256 and 1000000 < raw_bytes <= 1048576
            start = time.monotonic()
            page.get_by_role("button", name="Formatted responses", exact=True).click()
            viewport.scroll_into_view_if_needed()
            page.wait_for_function("document.querySelectorAll('.source-markdown').length > 0")
            page.evaluate("() => new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
            duration = time.monotonic() - start
            initial_mounted = page.locator(".source-markdown").count()
            initial_nodes = page.locator(".source-markdown *").count()
            deferred = page.locator('[data-format="deferred"]').count()
            assert initial_mounted <= 8 and initial_nodes < 10000 and deferred >= 247
            viewport.evaluate("e=>{e.scrollTop=0;}")
            page.get_by_role("heading", name="Bounded stress 1", exact=True).wait_for()
            assert page.locator(".source-markdown").count() <= 12
            page.get_by_role("button", name="Exact source", exact=True).click()
            restored_bytes = page.locator(".conversation-answer").evaluate_all("rows=>rows.reduce((n,e)=>n+new TextEncoder().encode(e.textContent).length,0)")
            assert restored_bytes == raw_bytes
            assert not errors and not external
            result = {"schema": "mastermind.observed_transcript.capacity_fixture.v1",
                "proof_scope": "SOURCE_FIXTURE_ONLY", "source_rows": rows, "source_text_bytes": raw_bytes,
                "initial_rich_responses": initial_mounted, "initial_rich_nodes": initial_nodes,
                "deferred_responses": deferred, "format_and_first_visible_render_seconds": round(duration, 3),
                "offscreen_response_formats_on_scroll": True, "exact_source_bytes_restored": restored_bytes,
                "page_errors": errors, "external_requests": external,
                "latency_is_single_local_observation_not_sla": True,
                "production_authentication": False, "provider_calls": 0, "real_send": False}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
        finally:
            browser.close()


if __name__ == "__main__":
    main()

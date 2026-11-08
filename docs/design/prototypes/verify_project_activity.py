"""Behavior checks for the local design reference, not production acceptance.

Requires Python Playwright and Chromium. Run beside project-activity.html:
    python verify_project_activity.py
Optional: CHROMIUM_EXECUTABLE=/path/to/chromium PROTOTYPE_QA_DIR=/tmp/qa
No production services or credentials are used.
"""
import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("PROTOTYPE_QA_DIR", "/tmp/project-activity-qa"))
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + str(os.getpid())
OUTPUT = OUTPUT_ROOT / RUN_ID
STATES = ["active", "result", "stale", "disconnected", "partial", "unreadable", "unknown", "loading", "empty"]

def record_result(result):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {**result, "run_id": RUN_ID}
    text = json.dumps(result, indent=2) + "\n"
    (OUTPUT / "verification.json").write_text(text)
    (OUTPUT_ROOT / "latest.json").write_text(text)


async def verify():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    async with async_playwright() as pw:
        executable = os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium")
        browser = await pw.chromium.launch(executable_path=executable, headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1280, "height": 1100}, reduced_motion="no-preference")
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.add_init_script("""
          window.motionStarts = 0;
          window.liveRegionMutations = 0;
          const originalAnimate = Element.prototype.animate;
          Element.prototype.animate = function(...args) {
            window.motionStarts += 1;
            return originalAnimate.apply(this,args);
          };
          addEventListener('DOMContentLoaded', () => {
            const region = document.getElementById('announcement');
            new MutationObserver(records => { window.liveRegionMutations += records.length; })
              .observe(region,{childList:true,subtree:true,characterData:true});
          });
        """)
        external = []

        async def route(request_route):
            if request_route.request.url.startswith("file:"):
                await request_route.continue_()
            else:
                external.append(request_route.request.url)
                await request_route.abort()

        await page.route("**/*", route)
        await page.goto((HERE / "project-activity.html").as_uri())
        await page.wait_for_function("document.documentElement.dataset.observation === 'active'")

        async def apply(state, mode="attended"):
            await page.select_option("#scenario", state)
            await page.select_option("#execution-mode", mode)
            await page.click("#apply-observation")
            assert await page.locator("html").get_attribute("data-observation") == state

        await page.screenshot(path=str(OUTPUT / "desktop-active.png"), full_page=True)
        assert await page.locator("#mode-consequence").inner_text() == "Keep this session open"
        starts = await page.evaluate("window.motionStarts")
        await apply("active", "durable")
        assert await page.evaluate("window.motionStarts") == starts + 1
        assert await page.locator("#mode-consequence").inner_text() == "Continues after you close the app"
        await apply("active", "unavailable")
        assert await page.locator("#mode-consequence").inner_text() == "Execution mode unavailable"
        checks.append("Qualified execution mode never defaults missing data to durable.")

        await page.fill("#draft", "Keep my wording and cursor.")
        await page.locator("#draft").evaluate("(node) => { window.originalComposer = node; node.setSelectionRange(5, 12); }")
        await page.click("#details-button")
        await page.click('[data-section="plan"]')
        assert await page.locator("#owner-plan").is_visible()
        assert await page.evaluate("document.activeElement.id") == "owner-plan"
        await page.keyboard.press("Escape")
        assert await page.evaluate("document.activeElement.dataset.section") == "plan"
        await page.keyboard.press("Escape")
        assert await page.evaluate("document.activeElement.id") == "details-button"
        assert await page.locator("#draft").input_value() == "Keep my wording and cursor."
        assert await page.locator("#draft").evaluate("(node) => node === window.originalComposer && node.selectionStart === 5 && node.selectionEnd === 12")
        checks.append("Details/section/Escape preserves the composer node, draft, selection and exact focus return.")

        await apply("result")
        assert await page.locator("#result-card").is_visible()
        assert await page.locator("#open-designs").get_attribute("href") == "https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-H-0"
        await page.click("#continue-result")
        assert await page.locator("#draft").input_value() == "Keep my wording and cursor."
        assert "draft is kept" in await page.locator("#composer-message").inner_text()
        await page.fill("#draft", "")
        await page.click("#continue-result")
        assert "Refine the project workspace designs." == await page.locator("#draft").input_value()
        assert "Continuing from" in await page.locator("#draft-basis").inner_text()
        await page.click("#preview-draft")
        assert await page.locator("#preview-panel").is_visible()
        assert "New follow-up" in await page.locator("#preview-context").inner_text()
        assert await page.get_by_role("button", name="Submit", exact=True).count() == 0
        await apply("unknown")
        assert await page.locator("#preview-panel").is_visible()
        assert await page.locator("#preview-panel").get_attribute("data-qualified") == "false"
        assert "needs verification" in await page.locator("#preview-heading").inner_text()
        assert await page.evaluate("document.activeElement.id") == "apply-observation"
        await apply("result")
        assert await page.locator("#preview-panel").get_attribute("data-qualified") == "false"
        await page.locator("#preview-panel [data-close]").click()
        assert await page.evaluate("document.activeElement.id") == "preview-draft"
        checks.append("Continuation preserves drafts; an open follow-up preview becomes explicitly unqualified on invalidation without stealing focus.")

        multiline = "Keep these details:\n\n  - First point\n  - Second point\n" + "reference" * 30
        await page.fill("#draft", multiline)
        await page.click("#preview-draft")
        assert await page.locator("#preview-copy").inner_text() == multiline
        await page.locator("#preview-panel [data-close]").click()
        preserved = multiline
        await apply("unknown")
        await page.click("#preview-draft")
        assert await page.locator("#draft").input_value() == preserved
        assert "verified again" in await page.locator("#composer-message").inner_text()
        assert await page.locator("#preview-panel").is_hidden()
        assert await page.locator("#continue-result").is_hidden()
        assert await page.get_by_role("button", name="Resend", exact=True).count() == 0
        await page.click("#state-action")
        assert "example-operation-17" in await page.locator("#activity-panel").inner_text()
        await page.locator("#activity-panel [data-close]").click()
        checks.append("Unknown effects retain the original operation and cannot preview a stale follow-up or offer resend.")

        await apply("partial")
        assert await page.locator("#review-task").is_hidden()
        assert await page.locator("#review-edge").get_attribute("visibility") == "hidden"
        assert await page.locator("#coverage").is_visible()
        await apply("stale")
        assert await page.evaluate("document.getAnimations().length") == 0
        assert "Last observed" in await page.locator("#design-state").inner_text()
        await apply("disconnected")
        assert await page.evaluate("document.getAnimations().length") == 0
        assert "does not mean the worker stopped" in await page.locator("#coverage").inner_text()
        checks.append("Partial coverage omits unknown tasks; stale/disconnected observations rest and retain historical meaning.")

        await apply("unreadable")
        await page.click("#state-action")
        assert "original run is retained" in await page.locator("#state-feedback").inner_text()
        assert await page.locator("#continue-result").is_hidden()
        await page.check("#reduce-motion")
        await apply("result")
        assert await page.evaluate("document.getAnimations().length") == 0
        await page.uncheck("#reduce-motion")
        await page.emulate_media(reduced_motion="reduce")
        await apply("active")
        assert await page.evaluate("document.getAnimations().length") == 0
        checks.append("Unreadable results use read recovery; manual and system reduced-motion preferences remove motion.")

        await page.emulate_media(reduced_motion="no-preference")
        await apply("stale")
        starts = await page.evaluate("window.motionStarts")
        await apply("active")
        assert await page.evaluate("window.motionStarts") == starts + 1
        starts = await page.evaluate("window.motionStarts")
        mutations = await page.evaluate("window.liveRegionMutations")
        unchanged = await page.locator("#announcement").inner_text()
        await page.click("#apply-observation")
        assert await page.locator("#announcement").inner_text() == unchanged
        assert await page.evaluate("window.motionStarts") == starts
        assert await page.evaluate("window.liveRegionMutations") == mutations
        checks.append("Repeated unchanged observations produce no new announcement or animation.")

        expected = {
            "active": ("activity", True, True, True),
            "result": ("result", True, True, True),
            "stale": ("activity", True, True, True),
            "disconnected": ("activity", True, True, True),
            "partial": ("activity", True, True, True),
            "unreadable": ("state", True, True, True),
            "unknown": ("state", False, True, False),
            "loading": ("state", False, False, False),
            "empty": ("state", False, False, False),
        }
        for width in [320, 390, 768, 1280]:
            await page.set_viewport_size({"width": width, "height": 1000})
            for state in STATES:
                await apply(state)
                assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (width, state)
                assert await page.locator("#draft").input_value() == preserved, (width, state, "draft lost")
                card, current_row, previous_row, run = expected[state]
                for kind in ["activity", "result", "state"]:
                    assert await page.locator("#" + kind + "-card").is_visible() == (kind == card), (state, kind)
                assert await page.locator("#continue-result").is_visible() == (state == "result")
                assert (await page.locator("#history-current-row").get_attribute("hidden") is None) == current_row
                assert (await page.locator("#history-previous-row").get_attribute("hidden") is None) == previous_row
                assert (await page.locator("#inspector-run-row").get_attribute("hidden") is None) == run
                assert await page.locator("#state-card").get_attribute("aria-busy") == str(state == "loading").lower()
            await apply("result" if width == 390 else "active")
            if width in [320, 390]:
                await page.screenshot(path=str(OUTPUT / ("mobile-" + str(width) + ".png")), full_page=True)
        checks.append("Nine states at four widths match card/action/history/inspector/busy-state expectations without overflow or draft loss.")

        await page.set_viewport_size({"width": 1280, "height": 1100})
        await page.click("#details-button")
        await page.screenshot(path=str(OUTPUT / "desktop-details.png"), full_page=True)
        assert not errors, errors
        assert not external, external
        checks.append("No JavaScript errors, external asset requests or runtime submissions.")
        await browser.close()
    result = {"status": "PASS", "checks": checks, "screenshots": str(OUTPUT), "production_acceptance": False}
    record_result(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    record_result({"status": "RUNNING", "production_acceptance": False})
    try:
        if not __debug__:
            raise RuntimeError("Run without Python -O; verification assertions must remain enabled.")
        asyncio.run(verify())
    except BaseException as error:
        record_result({"status": "FAIL", "error": str(error), "production_acceptance": False})
        raise

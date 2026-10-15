"""Bounded browser qualification against an explicitly labelled local fixture entry.
No production credentials, worker launches, endpoint changes or automatic retry.
Run while the owned loopback Vite preview is active; the entry is not published.
"""
from pathlib import Path
import datetime
import hashlib
import json
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:5199/os/fabric-proof.local.html"
results = {}
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.goto(URL, wait_until="networkidle")
    page.evaluate("const el=document.getElementById('root');el.classList.add('shell');el.dataset.theme='dark';el.style.display='block';")
    page.get_by_text("Subagent Fabric · inspect execution", exact=True).click()
    disclosure = page.locator(".fi-disclosure")
    disclosure.evaluate("""el => {
      const label = document.createElement('div');
      label.textContent = 'FIXTURE PREVIEW · Synthetic mission data · Actual app components · Not deployed';
      label.style.cssText = 'padding:12px 0;font-size:12px;border-bottom:1px dashed currentColor;margin-bottom:12px';
      el.querySelector('summary').after(label);
    }""")
    selected = page.get_by_role("button", name="JOB-9103 · COMPLETED · work")
    selected.focus()
    selected.press("Enter")
    assert page.get_by_role("complementary", name="Selected worker").get_by_text("worker-browser", exact=True).is_visible()
    results["keyboard_selection"] = selected.evaluate("e => e === document.activeElement")
    disclosure.screenshot(path=str(OUT / "fabric-desktop-dark.png"))
    page.get_by_text("Direct M2 Fabric · inspect an existing run", exact=True).click()
    page.get_by_label("Original root", exact=True).fill("fabric-mcp-web-20261011-c3")
    page.get_by_label("Existing run ID", exact=True).fill("fabric-mcp-web-20261011-c3-check-01")
    page.get_by_role("button", name="Inspect run", exact=True).click()
    page.get_by_text("NOT_ACCEPTED", exact=True).wait_for()
    assert page.get_by_text("3672", exact=True).is_visible()
    results["retained_real_status_rendered"] = True
    page.locator(".fi-attended").evaluate("""el => {
      const label = document.createElement('div');
      label.textContent = 'RETAINED M2 OBSERVATION · Fixture transport · Not live authenticated access';
      label.style.cssText = 'padding:12px 0;font-size:12px;border-bottom:1px dashed currentColor;margin-bottom:12px';
      el.querySelector('summary').after(label);
    }""")
    page.locator(".fi-attended").screenshot(path=str(OUT / "fabric-direct-status.png"))
    page.get_by_text("Direct M2 Fabric · inspect an existing run", exact=True).click()
    page.set_viewport_size({"width": 390, "height": 844})
    results["mobile_overflow"] = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    disclosure.screenshot(path=str(OUT / "fabric-mobile-dark.png"))
    page.set_viewport_size({"width": 1440, "height": 1050})
    page.evaluate("document.getElementById('root').dataset.theme='light';document.body.style.background='#f7f7f5';document.body.style.color='#202020'")
    results["light_computed_style"] = page.locator(".fi-workspace").first.evaluate("e => ({color:getComputedStyle(e).color,background:getComputedStyle(e).backgroundColor})")
    disclosure.screenshot(path=str(OUT / "fabric-desktop-light.png"))
    results["desktop_overflow"] = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    results["page_errors"] = errors
    results["proof_kind"] = "Actual MetaCeoOffice consumer with synthetic Mission and retained real M2 status. Not live authenticated access or deployment."
    results["observed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    results["screenshots"] = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in (
        "fabric-desktop-dark.png", "fabric-direct-status.png", "fabric-mobile-dark.png", "fabric-desktop-light.png")}
    browser.close()
(OUT / "browser-proof.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
assert results["keyboard_selection"] and not results["mobile_overflow"] and not results["desktop_overflow"] and not errors

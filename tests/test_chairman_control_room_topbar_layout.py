"""Read-only browser geometry proof for the shipped Control Room header.

No server, account, provider or network is used. Browser-capable CI/local lanes
must set MMX_REQUIRE_LAYOUT_BROWSER=1; otherwise unavailable browser support is
an explicit skip, never a substituted layout pass.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app/static/chairman_control"
WIDTHS = (1281, 1366, 1440, 1600, 1920)
CLOCKS = (
    ("Agent OS · 19h", "Executive · DB absent", "GitHub · live cache · 2h"),
    ("Agent OS · unknown age", "Executive · DB unknown", "GitHub · snapshot · unknown age"),
)


_SCRIPT_TAGS = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.I | re.S)

def require_or_skip(reason):
    if os.environ.get("MMX_REQUIRE_LAYOUT_BROWSER") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        require_or_skip("playwright is unavailable; rendered geometry NOT_RUN")
    with sync_playwright() as runtime:
        candidates = [os.environ.get("MMX_BROWSER_EXECUTABLE"),
                      runtime.chromium.executable_path,
                      shutil.which("chromium"), shutil.which("google-chrome")]
        executable = next((p for p in candidates if p and Path(p).is_file()), None)
        if executable is None:
            require_or_skip("Chromium is unavailable; rendered geometry NOT_RUN")
        instance = runtime.chromium.launch(headless=True, executable_path=executable)
        try:
            yield instance
        finally:
            instance.close()


def render(browser, width, theme, clocks, *, remote=False):
    context = browser.new_context(viewport={"width": width, "height": 900},
                                  service_workers="block")
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    name = "remote.html" if remote else "index.html"
    html = (ASSETS / name).read_text()
    # Keep the real markup; clocks are the only synthetic dynamic input.
    html = _SCRIPT_TAGS.sub("", html)
    html = re.sub(r"<link\b[^>]*>", "", html, flags=re.I)
    page.set_content(html)
    page.add_style_tag(content=(ASSETS / "control_room.css").read_text())
    page.evaluate("""({theme, clocks}) => {
        document.documentElement.dataset.theme = theme;
        const pulse = document.getElementById('ccr-source-pulse');
        pulse.replaceChildren(...clocks.map(text => {
            const node = document.createElement('span');
            node.className = 'ccr-pulse-pill'; node.textContent = text;
            return node;
        }));
    }""", {"theme": theme, "clocks": clocks})
    return context, page


GEOMETRY = """() => {
  const rect = node => {
    const r = node.getBoundingClientRect();
    return {left:r.left, right:r.right, top:r.top, bottom:r.bottom,
            width:r.width, height:r.height};
  };
  const nodes = [...document.querySelectorAll(
    '.ccr-brand, .ccr-command, .ccr-pulse-pill, .ccr-local-badge, #ccr-theme')]
    .filter(n => n.getClientRects().length && getComputedStyle(n).visibility !== 'hidden');
  const bounds = rect(document.querySelector('.ccr-topbar'));
  return {bounds, nodes:nodes.map(n => ({...rect(n), name:n.className || n.id,
      text:n.textContent.trim(), scroll:n.scrollWidth, client:n.clientWidth,
      overflow:getComputedStyle(n).overflowX,
      textOverflow:getComputedStyle(n).textOverflow})),
    clocks:[...document.querySelectorAll('.ccr-pulse-pill')]
      .filter(n => n.getClientRects().length).map(n => n.textContent),
    expectedHeight:parseFloat(getComputedStyle(document.documentElement)
      .getPropertyValue('--topbar'))};
}"""


def assert_geometry(measured, width):
    bounds = measured["bounds"]
    assert abs(bounds["height"] - measured["expectedHeight"]) < 1
    assert bounds["right"] <= width + 1
    for index, item in enumerate(measured["nodes"]):
        assert item["left"] >= -1 and item["right"] <= width + 1, item
        assert item["top"] >= bounds["top"] - 1, item
        assert item["bottom"] <= bounds["bottom"] + 1, item
        assert item["scroll"] <= item["client"] + 1, item
        for other in measured["nodes"][index + 1:]:
            overlap_x = min(item["right"], other["right"]) - max(item["left"], other["left"])
            overlap_y = min(item["bottom"], other["bottom"]) - max(item["top"], other["top"])
            assert overlap_x <= 1 or overlap_y <= 1, (item, other)


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("theme", ("dark", "light"))
@pytest.mark.parametrize("clocks", CLOCKS)
def test_desktop_source_clocks_are_readable_without_collisions(browser, width, theme, clocks):
    context, page = render(browser, width, theme, clocks)
    try:
        measured = page.evaluate(GEOMETRY)
        assert measured["clocks"] == list(clocks)
        assert_geometry(measured, width)
        assert page.locator('#ccr-theme').is_visible()
        assert page.locator('.ccr-local-badge').is_visible()
    finally:
        context.close()


@pytest.mark.parametrize("width", (375, 760, 1050, 1280))
@pytest.mark.parametrize("theme", ("dark", "light"))
def test_existing_compact_header_behavior_is_preserved(browser, width, theme):
    context, page = render(browser, width, theme, CLOCKS[1])
    try:
        measured = page.evaluate(GEOMETRY)
        assert measured["clocks"] == []  # Existing compact design, not a new hiding rule.
        assert_geometry(measured, width)
        assert page.locator('#ccr-theme').is_visible()
    finally:
        context.close()


@pytest.mark.parametrize("width", (375, 1440, 1920))
@pytest.mark.parametrize("theme", ("dark", "light"))
def test_remote_projection_keeps_its_existing_header_boundary(browser, width, theme):
    context, page = render(browser, width, theme, CLOCKS[1], remote=True)
    try:
        measured = page.evaluate(GEOMETRY)
        assert measured["clocks"] == (list(CLOCKS[1]) if width > 1600 else [])
        assert_geometry(measured, width)
    finally:
        context.close()


def test_shipped_header_has_distinct_source_and_control_regions():
    """Always runs even in lanes without a browser; not a geometry substitute."""
    html = (ASSETS / "index.html").read_text()
    assert html.count('id="ccr-source-pulse"') == 1
    assert html.count('id="ccr-theme"') == 1
    assert 'aria-label="Source clocks"' in html
    assert 'Local · canonical read-only' in html


@pytest.mark.parametrize("closing", ("</script>", "</script >", "</script\t>", "</SCRIPT\n>"))
def test_fixture_script_filter_accepts_legal_closing_tag_whitespace(closing):
    html = "<script>window.unwanted = true;" + closing + "<header>Header</header>"
    assert _SCRIPT_TAGS.sub("", html) == "<header>Header</header>"

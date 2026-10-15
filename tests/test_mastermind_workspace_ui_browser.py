from __future__ import annotations

from pathlib import Path

import pytest

from integrations.mastermind_workspace_content.ui import WORKSPACE_HTML

playwright = pytest.importorskip("playwright.sync_api")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
pytestmark = pytest.mark.skipif(not CHROME.is_file(), reason="system Chrome unavailable")


def envelope(*, text: str, state: str = "partial", gaps=()):
    return {
        "schema": "mastermind.workspace.content_read.v1",
        "selection_ref": "managed-window:test-turn",
        "mode": "observed-turn-window",
        "view": {
            "schema": "mastermind.workspace.visible_window.v1",
            "source_ref": "managed-window:test-turn",
            "scope": "one-managed-turn-window",
            "observed_at": "2026-09-16T22:00:00+00:00",
            "epoch": "0" * 64,
            "terminal": state == "completed",
            "coverage": "GAP_PRESENT" if gaps else "OBSERVED_WINDOW",
            "history": "NOT_PROVEN",
            "acceptance": "NOT_PROJECTED",
            "capabilities": {"send": False, "provider_control": False, "history": False},
            "items": [
                {
                    "id": "visible:" + "1" * 64,
                    "source_sequence": 1,
                    "publication_sequence": 2 if state == "completed" else 1,
                    "state": state,
                    "kind": "visible-response",
                    "text": text,
                    "representation": "VISIBLE_TEXT",
                    "display_sha256": "2" * 64,
                }
            ],
            "gaps": list(gaps),
        },
    }


def test_real_browser_updates_one_message_and_clears_on_disconnect(tmp_path) -> None:
    requests: list[str] = []
    with playwright.sync_playwright() as engine:
        browser = engine.chromium.launch(
            executable_path=str(CHROME),
            headless=True,
            args=["--disable-background-networking", "--no-default-browser-check"],
        )
        page = browser.new_page(viewport={"width": 1365, "height": 900})
        page.on("request", lambda request: requests.append(request.url))
        page.set_content(WORKSPACE_HTML, wait_until="domcontentloaded")

        assert page.locator(".message").count() == 0
        assert page.locator("#connectionText").inner_text() == "DISCONNECTED"

        page.evaluate(
            """async (payload) => {
              window.__workspacePayload = payload;
              await window.mastermindWorkspace.connect(async () => window.__workspacePayload);
            }""",
            envelope(text="Draft response"),
        )
        assert page.locator(".message").count() == 1
        assert page.locator(".message-body").inner_text() == "Draft response"
        assert page.locator("#connectionText").inner_text() == "CONNECTED"

        page.evaluate(
            """async (payload) => {
              window.__workspacePayload = payload;
              await window.mastermindWorkspace.refresh();
            }""",
            envelope(text="Corrected final response", state="completed"),
        )
        assert page.locator(".message").count() == 1
        assert page.locator(".message-body").inner_text() == "Corrected final response"
        assert page.locator(".message-state").inner_text() == "COMPLETED"
        assert page.locator("#terminal").inner_text() == "Provider turn terminal"

        page.locator("#evidenceButton").click()
        assert page.locator("#evidenceDialog").get_attribute("open") is not None
        assert "NOT_PROJECTED" in page.locator("#evidence").inner_text()
        page.locator("#evidenceClose").click()

        page.evaluate("window.mastermindWorkspace.disconnect()")
        assert page.locator(".message").count() == 0
        assert page.locator("#connectionText").inner_text() == "DISCONNECTED"
        assert requests == []
        page.screenshot(path=str(tmp_path / "workspace-window.png"), full_page=True)
        browser.close()


def test_real_browser_treats_source_markup_as_text_and_discloses_gaps() -> None:
    malicious = '<img src="https://invalid.example.test/leak"> literal source text'
    gap = {"first": 1, "last": 2, "reason": "SOURCE_REPORTED_GAP"}
    with playwright.sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page()
        requests: list[str] = []
        page.on("request", lambda request: requests.append(request.url))
        page.set_content(WORKSPACE_HTML, wait_until="domcontentloaded")
        page.evaluate(
            """async (payload) => {
              await window.mastermindWorkspace.connect(async () => payload);
            }""",
            envelope(text=malicious, gaps=(gap,)),
        )

        assert page.locator(".message-body").inner_text() == malicious
        assert page.locator(".message img").count() == 0
        assert page.locator("#connectionText").inner_text() == "DEGRADED"
        assert "not complete history" in page.locator("#gapNotice").inner_text().lower()
        assert requests == []
        browser.close()


def test_late_result_cannot_repopulate_after_disconnect() -> None:
    with playwright.sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page()
        page.set_content(WORKSPACE_HTML, wait_until="domcontentloaded")
        page.evaluate(
            """() => {
              window.__resolveWorkspace = null;
              window.mastermindWorkspace.connect(() => new Promise((resolve) => {
                window.__resolveWorkspace = resolve;
              }));
            }"""
        )
        page.wait_for_function("window.__resolveWorkspace !== null")
        page.evaluate("window.mastermindWorkspace.disconnect()")
        page.evaluate("(payload) => window.__resolveWorkspace(payload)", envelope(text="Late"))
        page.wait_for_timeout(50)

        assert page.locator(".message").count() == 0
        assert page.locator("#connectionText").inner_text() == "DISCONNECTED"
        browser.close()


def test_source_unavailable_keeps_last_qualified_window() -> None:
    with playwright.sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page()
        page.set_content(WORKSPACE_HTML, wait_until="domcontentloaded")
        page.evaluate(
            """async (payload) => {
              await window.mastermindWorkspace.connect(async () => payload);
            }""",
            envelope(text="Last qualified response"),
        )
        page.evaluate(
            """async () => {
              await window.mastermindWorkspace.connect(async () => {
                const error = new Error("unavailable");
                error.code = "SOURCE_UNAVAILABLE";
                throw error;
              });
            }"""
        )

        assert page.locator(".message-body").inner_text() == "Last qualified response"
        assert page.locator("#connectionText").inner_text() == "DEGRADED"
        assert "last qualified" in page.locator("#subtitle").inner_text().lower()
        browser.close()

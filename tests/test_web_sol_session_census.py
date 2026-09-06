"""Executable tests for the local reader, not proof of a live ChatGPT account."""
import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "integrations/chairman_surfaces/web_sol_extension"


def test_manifest_exposes_the_reader_without_permission_widening():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest.get("action", {}).get("default_popup") == "census.html"
    assert set(manifest["permissions"]) == {"nativeMessaging", "alarms"}
    assert set(manifest["host_permissions"]) == {
        "https://chat.openai.com/*", "https://chatgpt.com/*"
    }
    assert manifest["background"] == {"service_worker": "background.js"}
    assert manifest["content_scripts"][0]["js"] == ["content.js"]
    assert "externally_connectable" not in manifest
    assert "web_accessible_resources" not in manifest


class _Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.ids = set()
        self.inline_script = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "script":
            if "src" not in values:
                self.inline_script = True
            self.scripts.append(values.get("src"))


def test_reader_is_a_real_local_consumer_with_no_remote_or_inline_scripts():
    assert (EXTENSION / "census.html").exists(), "the census needs a user-visible consumer"
    page = _Assets()
    page.feed((EXTENSION / "census.html").read_text())
    assert page.scripts == ["instance_config.js", "census_core.js", "census.js"]
    assert not page.inline_script
    assert {"refresh", "rows", "summary", "scope", "status", "timestamp"} <= page.ids
    source = (EXTENSION / "census.js").read_text()
    assert "MMXWebSolCensus.collect" in source
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "setInterval" not in source
    for forbidden in ("fetch(", "XMLHttpRequest", "connectNative", "chrome.storage", "localStorage",
                      "tabs.update", "tabs.create", "tabs.remove", "tabs.reload"):
        assert forbidden not in source
    assert (EXTENSION / "census.css").is_file()


def test_node_census_behavior_suite():
    node = shutil.which("node")
    assert node is not None, "Node is required; this behavior gate must not be skipped"
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests/web_sol_session_census.test.cjs")],
        cwd=ROOT, capture_output=True, text=True, timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def run_synthetic_browser_proof(output_dir):
    """Optional local proof; deliberately excludes the production native background.

    Run: python tests/test_web_sol_session_census.py --browser-proof <output-dir>
    This is not a live ChatGPT, installed-native, managed-profile, or account test.
    """
    import base64
    import hashlib
    import tempfile
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("chromium") or shutil.which("google-chrome")
    assert executable, "A local Chromium executable is required for synthetic browser proof"
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest.pop("background") == {"service_worker": "background.js"}
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).digest()[:16]
    extension_id = "".join(chr(97 + int(c, 16)) for c in digest.hex())
    page_errors = []

    def fulfill_fixture(route):
        parsed = urlparse(route.request.url)
        if parsed.scheme == "chrome-extension":
            route.continue_()
            return
        if parsed.scheme != "https" or parsed.hostname != "chatgpt.com":
            route.abort()
            return
        if parsed.path == "/favicon.ico":
            route.fulfill(status=204, body="")
            return
        composer = "" if "fixture-project" in parsed.path else '<div id="prompt-textarea" contenteditable="true">PRIVATE_FIXTURE_SENTINEL</div>'
        stop = '<button data-testid="stop-button">Stop</button>' if "fixture-active" in parsed.path else ""
        route.fulfill(status=200, content_type="text/html", body=(
            '<!doctype html><html><head><title>PRIVATE_FIXTURE_SENTINEL</title></head>'
            f'<body><main>{composer}{stop}</main></body></html>'
        ))

    def stage(directory, instance):
        directory.mkdir()
        for name in ("census.html", "census.css", "census.js", "census_core.js", "content.js"):
            shutil.copyfile(EXTENSION / name, directory / name)
        (directory / "manifest.json").write_text(json.dumps(manifest))
        (directory / "instance_config.js").write_text(
            "globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze(" + json.dumps({"instanceId": instance}) + ");\n"
        )

    with tempfile.TemporaryDirectory(prefix="mmx-census-synthetic-") as temporary, sync_playwright() as playwright:
        temporary = Path(temporary)
        stage(temporary / "a", "a" * 64)
        stage(temporary / "b", "b" * 64)
        contexts = []

        def launch(name):
            extension = temporary / name
            context = playwright.chromium.launch_persistent_context(
                str(temporary / f"profile-{name}"), executable_path=executable, headless=True,
                viewport={"width": 760, "height": 680},
                args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                      "--disable-background-networking", "--disable-component-update", "--disable-sync",
                      "--no-first-run", "--no-sandbox"],
            )
            contexts.append(context)
            context.set_offline(True)
            context.route("**/*", fulfill_fixture)
            return context

        try:
            context = launch("a")
            pages = []
            for path in ("/c/fixture-active", "/c/fixture-active", "/c/fixture-idle",
                         "/g/g-p-FIXTURE/c/fixture-project", "/", "/c/fixture-dormant"):
                page = context.new_page()
                page.goto("https://chatgpt.com" + path, wait_until="load")
                pages.append(page)
            popup = context.new_page()
            popup.on("pageerror", lambda _: page_errors.append("POPUP_SCRIPT_ERROR"))
            popup.goto(f"chrome-extension://{extension_id}/census.html", wait_until="load")
            popup.wait_for_function("!document.getElementById('refresh').disabled")
            discarded = popup.evaluate("""async () => {
                const tabs = await chrome.tabs.query({url: 'https://chatgpt.com/*'});
                const target = tabs.find(t => t.url.endsWith('/c/fixture-dormant'));
                const result = await chrome.tabs.discard(target.id);
                return result && result.discarded === true;
            }""")
            assert discarded, "The synthetic discarded-tab fixture was not established"
            popup.locator("#refresh").click()
            popup.wait_for_function("!document.getElementById('refresh').disabled")
            metrics = popup.locator(".metric strong").all_text_contents()
            assert metrics == ["6", "2", "3", "1"], metrics
            body = popup.locator("body").inner_text()
            assert "Discarded" in body and "No conversation locator" in body
            assert "PRIVATE_FIXTURE_SENTINEL" not in body
            assert "Served model: unknown" in body
            popup.screenshot(path=str(output / "census-synthetic-wide.png"), full_page=True)
            popup.set_viewport_size({"width": 560, "height": 780})
            assert popup.evaluate("document.body.scrollWidth <= window.innerWidth"), "Narrow UI overflows"
            popup.screenshot(path=str(output / "census-synthetic-narrow.png"), full_page=True)
            popup.set_viewport_size({"width": 760, "height": 680})
            # Change only our own synthetic DOM, never a provider session.
            pages[0].evaluate("document.querySelector('[data-testid=stop-button]').remove()")
            popup.locator("#refresh").click()
            popup.wait_for_function("!document.getElementById('refresh').disabled")
            assert popup.locator(".metric strong").all_text_contents()[1] == "1"
            assert "Cue observations differ" in popup.locator("body").inner_text()
            second = launch("b")
            p = second.new_page(); p.goto("https://chatgpt.com/c/fixture-idle", wait_until="load")
            second_popup = second.new_page()
            second_popup.goto(f"chrome-extension://{extension_id}/census.html", wait_until="load")
            second_popup.wait_for_function("!document.getElementById('refresh').disabled")
            assert second_popup.locator(".metric strong").all_text_contents()[0] == "1"
            assert popup.locator(".metric strong").all_text_contents()[0] == "6"
            assert second_popup.evaluate("MMX_WEB_SOL_INSTANCE.instanceId") == "b" * 64
            assert not page_errors
            report = {
                "schema": "mastermind.web_sol_census_synthetic_browser_proof.v1",
                "browser_version": subprocess.run([executable, "--version"], capture_output=True, text=True, check=True).stdout.strip(),
                "proof_class": "SYNTHETIC_BROWSER_PROOF_NOT_PROVIDER_PROOF",
                "native_background": "OMITTED_FROM_TEST_MANIFEST",
                "instance_config": "SYNTHETIC",
                "provider_network": "OFFLINE_CONTEXT_FIXTURE_RESPONSES_ONLY",
                "fixture_tab_count": 6, "initial_metrics": metrics,
                "duplicate_cue_conflict_after_refresh": True,
                "profile_isolation_counts": [6, 1], "narrow_overflow": False,
                "private_fixture_marker_absent": True, "popup_script_errors": page_errors,
                "current_chatgpt_model_effort_proven": False,
            }
            (output / "synthetic-browser-proof.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
        finally:
            for context in reversed(contexts):
                context.close()



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Optional offline Web-Sol census browser fixture proof")
    parser.add_argument("--browser-proof", required=True, metavar="OUTPUT_DIR")
    run_synthetic_browser_proof(parser.parse_args().browser_proof)

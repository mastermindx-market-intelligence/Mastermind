from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "integrations" / "chairman_surfaces" / "web_sol_extension"
MANIFEST = EXTENSION / "manifest.json"
BACKGROUND = EXTENSION / "background.js"
CONTENT = EXTENSION / "content.js"

CHATGPT_MATCHES = {"https://chatgpt.com/*", "https://chat.openai.com/*"}
EXPECTED_EXTENSION_ID = "kmpbpccecbofdnhpcmjogofgmdodpnko"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _extension_id(public_key_b64: str) -> str:
    der = base64.b64decode(public_key_b64, validate=True)
    digest = hashlib.sha256(der).digest()[:16]
    alphabet = "abcdefghijklmnop"
    return "".join(alphabet[byte >> 4] + alphabet[byte & 15] for byte in digest)


def test_manifest_is_mv3_exact_host_and_least_privilege():
    manifest = _manifest()

    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "Mastermind Web Sol Surface Adapter"
    assert manifest["version"] == "0.1.0"
    assert set(manifest["host_permissions"]) == CHATGPT_MATCHES

    permissions = set(manifest.get("permissions", []))
    assert "nativeMessaging" in permissions
    assert permissions <= {"nativeMessaging", "tabs"}

    forbidden_permissions = {
        "activeTab",
        "bookmarks",
        "browsingData",
        "clipboardRead",
        "clipboardWrite",
        "contentSettings",
        "cookies",
        "debugger",
        "downloads",
        "geolocation",
        "history",
        "management",
        "notifications",
        "privacy",
        "proxy",
        "scripting",
        "storage",
        "webNavigation",
        "webRequest",
    }
    assert permissions.isdisjoint(forbidden_permissions)
    assert "externally_connectable" not in manifest
    assert "web_accessible_resources" not in manifest


def test_manifest_binds_one_deterministic_extension_identity():
    manifest = _manifest()
    public_key = manifest["key"]
    assert isinstance(public_key, str) and public_key
    assert _extension_id(public_key) == EXPECTED_EXTENSION_ID


def test_manifest_has_one_background_and_one_exact_chatgpt_content_script():
    manifest = _manifest()
    assert manifest["background"] == {"service_worker": "background.js"}
    assert manifest["content_scripts"] == [
        {
            "matches": sorted(CHATGPT_MATCHES),
            "js": ["content.js"],
            "run_at": "document_idle",
        }
    ]


def test_extension_files_are_present_and_small():
    for path in (BACKGROUND, CONTENT):
        payload = path.read_bytes()
        assert payload
        assert len(payload) <= 24 * 1024


def test_extension_source_contains_no_content_extraction_or_powerful_browser_api():
    source = (BACKGROUND.read_text(encoding="utf-8") + "\n" + CONTENT.read_text(encoding="utf-8")).lower()

    forbidden_fragments = {
        "innertext",
        "textcontent",
        "outerhtml",
        "innerhtml",
        "document.body",
        "clipboard",
        "localstorage",
        "sessionstorage",
        "chrome.cookies",
        "chrome.debugger",
        "chrome.scripting",
        "executescript",
        "xmlhttprequest",
        "websocket",
        "fetch(",
        "eval(",
        "new function",
        "document.cookie",
    }
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_content_script_uses_only_bounded_probe_vocabulary():
    source = CONTENT.read_text(encoding="utf-8")
    assert "MMX_WEB_SOL_PROBE" in source
    for required in (
        "target_present",
        "exact_conversation_loaded",
        "page_responsive",
        "document_ready_state",
        "visibility",
        "composer_available",
        "generation_state",
        "auth_required",
        "provider_error_present",
    ):
        assert required in source

    for forbidden in ("transcript", "output", "raw_dom", "message_text", "conversation_text"):
        assert forbidden not in source.lower()


def test_content_script_does_not_emit_url_or_dom_content():
    source = CONTENT.read_text(encoding="utf-8")
    assert "location.href" not in source
    assert "document.documentElement" not in source
    assert "querySelectorAll(\"*\")" not in source
    assert "querySelectorAll('*')" not in source


def test_background_uses_one_fixed_native_host_and_no_generic_action_vocabulary():
    source = BACKGROUND.read_text(encoding="utf-8")
    assert 'NATIVE_HOST = "com.mastermind.web_sol_surface"' in source
    assert "chrome.runtime.connectNative(NATIVE_HOST)" in source
    for forbidden in (
        "CLICK",
        "TYPE",
        "SEND",
        "NAVIGATE",
        "RELOAD",
        "EXECUTE",
        "SHELL",
        "RETRY",
        "FAILOVER",
    ):
        assert forbidden not in source

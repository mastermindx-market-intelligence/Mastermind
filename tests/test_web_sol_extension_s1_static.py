from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "integrations" / "chairman_surfaces" / "web_sol_extension"
BACKGROUND = EXTENSION / "background.js"
CONTENT = EXTENSION / "content.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_background_has_closed_native_action_listener_and_exact_request_schema():
    text = source(BACKGROUND)
    assert 'ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1"' in text
    assert 'RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1"' in text
    assert 'importScripts("instance_config.js")' in text
    assert "nativePort = chrome.runtime.connectNative(INSTANCE_CONFIG.nativeHost)" in text
    assert "const port = nativePort" in text
    assert "port.onMessage.addListener" in text
    assert "if (!transportHandshakeReady)" in text
    assert "handleNativeRequest(request, port)" in text
    assert "validActionRequest" in text
    assert 'accepted.action === "INSPECT"' in text
    assert 'accepted.action === "FOREGROUND"' in text

    for forbidden in (
        'accepted.action === "CLICK"',
        'accepted.action === "TYPE"',
        'accepted.action === "SEND"',
        'accepted.action === "NAVIGATE"',
        'accepted.action === "RELOAD"',
    ):
        assert forbidden not in text


def test_background_uses_ephemeral_exact_fingerprint_to_tab_mapping_only():
    text = source(BACKGROUND)
    assert "const targets = new Map()" in text
    assert "const tabFingerprints = new Map()" in text
    assert "conversation_fingerprint" in text
    assert "sender.tab.id" in text
    assert "sender.tab.windowId" in text
    assert "AMBIGUOUS_TARGET" in text
    assert "TARGET_NOT_FOUND" in text
    assert "TARGET_CHANGED" in text

    for forbidden in (
        "chrome.tabs.query",
        ".title",
        "lastAccessed",
        "activeInfo",
        "location.href",
        "sender.tab.url",
    ):
        assert forbidden not in text


def test_background_foreground_is_activation_and_focus_only():
    text = source(BACKGROUND)
    assert "chrome.tabs.update(tabId, {active: true})" in text
    assert "chrome.windows.update(windowId, {focused: true})" in text
    assert "chrome.tabs.sendMessage(tabId" in text
    assert 'REPROBE_KIND = "MMX_WEB_SOL_REPROBE"' in text
    assert "kind: REPROBE_KIND" in text

    for forbidden in (
        "chrome.tabs.create",
        "chrome.tabs.reload",
        "chrome.tabs.remove",
        "chrome.windows.create",
        "chrome.windows.remove",
        "chrome.scripting",
        "executeScript",
        "url:",
    ):
        assert forbidden not in text


def test_content_script_supports_request_aware_reprobe_without_content_export():
    text = source(CONTENT)
    assert 'REPROBE_KIND = "MMX_WEB_SOL_REPROBE"' in text
    assert "chrome.runtime.onMessage.addListener" in text
    assert "expected_conversation_fingerprint" in text
    assert "exact_conversation_loaded" in text
    assert (
        "conversationFingerprint === expectedConversationFingerprint" in text
    )

    for forbidden in (
        "innerText",
        "textContent",
        "innerHTML",
        "outerHTML",
        "document.body",
        "document.cookie",
        "localStorage",
        "sessionStorage",
        "clipboard",
    ):
        assert forbidden not in text


def test_background_receipts_copy_request_identity_and_never_expose_browser_handles():
    text = source(BACKGROUND)
    for field in (
        "binding_id",
        "conversation_fingerprint",
        "binding_fingerprint",
        "binding_revision",
        "action",
        "operation_key",
        "nonce",
    ):
        assert f"{field}: request.{field}" in text

    assert "tab_id:" not in text
    assert "window_id:" not in text
    assert "tabId:" not in text
    assert "windowId:" not in text


def test_background_has_no_persistent_browser_state_or_retry_fallback_loop():
    text = source(BACKGROUND).lower()
    for forbidden in (
        "chrome.storage",
        "localstorage",
        "sessionstorage",
        "indexeddb",
        "setinterval",
        "settimeout",
        "retry",
        "failover",
        "openclaw",
    ):
        assert forbidden not in text

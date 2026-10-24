"""Browser audience identity crosses auth, signed references, and fleet discovery."""
from __future__ import annotations

from dataclasses import replace

import pytest

from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.tab_ref import (
    BROWSER_SESSION_SCHEMA, TAB_REF_SCHEMA, BROKER_ACTION_SCHEMA,
    BrowserSessionRef, BrowserTabRef, BrokeredBrowserActionRef,
    BrowserTabRefCodec, BrowserTabRefError,
)

NOW = 1_800_000_000_000
AUDIENCE = "https://browser.example/mcp"
SUBJECT = "b" * 64
CLIENT = "c" * 64


def refs(resource):
    common = dict(
        backend="managed", browser_ref="browser-" + "a" * 64,
        subject_digest=SUBJECT, client_ref=CLIENT, resource=resource,
        host_ref="host-a", boot_ref="boot-a", profile_ref="profile-a",
        browser_instance_ref="instance-a", connection_generation="connection-a",
        consent_ref=None, allowed_actions=("snapshot",),
        catalog_schema_digest="d" * 64, backend_schema_digest="e" * 64,
        issued_at_ms=NOW, expires_at_ms=NOW + 60_000,
    )
    return (
        BrowserCallerBinding(SUBJECT, CLIENT, resource),
        BrowserSessionRef(schema=BROWSER_SESSION_SCHEMA, **common),
        BrowserTabRef(schema=TAB_REF_SCHEMA, tab_locator=7, document_revision=3, **common),
        BrokeredBrowserActionRef(
            schema=BROKER_ACTION_SCHEMA, subject_digest=SUBJECT,
            client_ref=CLIENT, resource=resource, tab_ref_sha256="f" * 64,
            owner_action_ref="owner-action", issued_at_ms=NOW,
            expires_at_ms=NOW + 60_000,
        ),
    )


@pytest.mark.parametrize("resource", [
    "browser-resource", "browser:resource",
    AUDIENCE, "https://browser.example/mcp/",
    "https://browser.example:443/mcp", "https://browser.example/MCP",
])
def test_all_reference_types_preserve_exact_audience(resource):
    for item in refs(resource):
        assert item.resource == resource


@pytest.mark.parametrize("resource", [
    "", None, 12, True, " https://browser.example/mcp",
    "https://browser.example/mcp\n", "https://browser.example/mcp\x00",
    "http://browser.example/mcp", "file:///tmp/browser",
    "https://user:password@browser.example/mcp",
    "https://browser.example/mcp?token=value",
    "https://browser.example/mcp#fragment",
    "https://browser.example:wrong/mcp",
    "https://browser.example:444/mcp",
    "https://browser.example\\evil/mcp",
    "https://browser.example/" + "a" * 2048,
])
def test_invalid_resources_fail_in_every_reference_type(resource):
    valid = refs(AUDIENCE)
    for item in valid:
        with pytest.raises(ValueError):
            replace(item, resource=resource)


def test_other_identity_fields_stay_opaque():
    for item in refs(AUDIENCE):
        with pytest.raises(ValueError):
            replace(item, client_ref="https://browser.example/client")


def test_https_session_and_tab_roundtrip_and_cross_audience_refusal():
    _, session, tab, _ = refs(AUDIENCE)
    codec = BrowserTabRefCodec(b"k" * 32)
    kwargs = dict(now_ms=NOW, subject_digest=SUBJECT, client_ref=CLIENT, resource=AUDIENCE)
    assert codec.decode_session(codec.encode_session(session), **kwargs) == session
    assert codec.decode_for_call(codec.encode(tab), action="snapshot", **kwargs) == tab
    for other in [
        "https://browser.example/mcp/", "https://browser.example/MCP",
        "https://browser.example:443/mcp", "https://other.example/mcp",
    ]:
        with pytest.raises(BrowserTabRefError, match="CALLER_BINDING_CHANGED"):
            codec.decode_session(codec.encode_session(session), **{**kwargs, "resource": other})
        with pytest.raises(BrowserTabRefError, match="CALLER_BINDING_CHANGED"):
            codec.decode_for_call(codec.encode(tab), action="snapshot", **{**kwargs, "resource": other})

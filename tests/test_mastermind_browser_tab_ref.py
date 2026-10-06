from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from integrations.mastermind_browser_plugin.tab_ref import (
    HIGH_LEVEL_ACTIONS,
    MAX_TAB_REF_LIFETIME_MS,
    BrowserTabRef,
    BrowserTabRefCodec,
    BrowserTabRefError,
    TabBackend,
)

KEY = b"k" * 32
NOW = 1_800_000_000_000


def binding(**changes):
    value = BrowserTabRef(
        schema="mastermind.browser_tab_ref.v1",
        backend=TabBackend.MANAGED.value,
        browser_ref="browser-resource-" + "a" * 64,
        subject_digest="b" * 64,
        client_ref="client-a",
        resource="browser-resource",
        host_ref="host-" + "c" * 64,
        boot_ref="boot-a",
        profile_ref="profile-a",
        browser_instance_ref="browser-a",
        connection_generation="generation-a",
        tab_locator=7,
        document_revision=3,
        consent_ref=None,
        allowed_actions=("click", "navigate", "screenshot", "snapshot", "type"),
        catalog_schema_digest="d" * 64,
        backend_schema_digest="e" * 64,
        issued_at_ms=NOW,
        expires_at_ms=NOW + 60_000,
    )
    return value if not changes else BrowserTabRef(**{**value.__dict__, **changes})


def codec():
    return BrowserTabRefCodec(KEY)


def test_managed_tab_ref_roundtrips_and_is_stateless():
    row = binding()
    token = codec().encode(row)
    observed = codec().decode(token, now_ms=NOW + 1)
    assert observed == row
    assert not hasattr(codec(), "__dict__") or "registry" not in repr(codec()).lower()
    assert token.startswith("v1.")


def test_shared_human_tab_requires_exact_consent_generation():
    shared = binding(
        backend=TabBackend.SHARED_HUMAN.value,
        consent_ref="consent-a",
    )
    assert codec().decode(codec().encode(shared), now_ms=NOW) == shared
    with pytest.raises(BrowserTabRefError, match="CONSENT_REQUIRED"):
        binding(backend=TabBackend.SHARED_HUMAN.value, consent_ref=None)


def test_managed_tab_cannot_smuggle_human_consent_identity():
    with pytest.raises(BrowserTabRefError, match="CONSENT_NOT_ALLOWED"):
        binding(consent_ref="consent-a")


def test_every_high_level_action_is_closed_and_sorted():
    assert HIGH_LEVEL_ACTIONS == frozenset(
        {"snapshot", "screenshot", "click", "type", "scroll", "navigate"}
    )
    with pytest.raises(BrowserTabRefError, match="ACTIONS_INVALID"):
        binding(allowed_actions=("snapshot", "shell"))
    with pytest.raises(BrowserTabRefError, match="ACTIONS_INVALID"):
        binding(allowed_actions=("snapshot", "click"))
    with pytest.raises(BrowserTabRefError, match="ACTIONS_INVALID"):
        binding(allowed_actions=("click", "click"))


def test_exact_caller_and_resource_are_rechecked_per_call():
    token = codec().encode(binding())
    ok = codec().decode_for_call(
        token,
        now_ms=NOW + 1,
        subject_digest="b" * 64,
        client_ref="client-a",
        resource="browser-resource",
        action="snapshot",
    )
    assert ok.tab_locator == 7
    for field, value in (
        ("subject_digest", "e" * 64),
        ("client_ref", "client-b"),
        ("resource", "other-resource"),
    ):
        kwargs = dict(
            token=token,
            now_ms=NOW + 1,
            subject_digest="b" * 64,
            client_ref="client-a",
            resource="browser-resource",
            action="snapshot",
        )
        kwargs[field] = value
        with pytest.raises(BrowserTabRefError, match="CALLER_BINDING_CHANGED"):
            codec().decode_for_call(**kwargs)


def test_action_must_be_granted_by_the_exact_tab_ref():
    token = codec().encode(binding(allowed_actions=("snapshot",)))
    assert codec().decode_for_call(
        token,
        now_ms=NOW,
        subject_digest="b" * 64,
        client_ref="client-a",
        resource="browser-resource",
        action="snapshot",
    ).allowed_actions == ("snapshot",)
    with pytest.raises(BrowserTabRefError, match="ACTION_NOT_GRANTED"):
        codec().decode_for_call(
            token,
            now_ms=NOW,
            subject_digest="b" * 64,
            client_ref="client-a",
            resource="browser-resource",
            action="click",
        )


def test_token_payload_and_signature_tampering_are_refused():
    token = codec().encode(binding())
    prefix, payload, signature = token.split(".")
    raw = bytearray(base64.urlsafe_b64decode(payload + "=="))
    raw[-2] ^= 1
    changed = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(BrowserTabRefError, match="TAB_REF_SIGNATURE_INVALID"):
        codec().decode(f"{prefix}.{changed}.{signature}", now_ms=NOW)

    sig = bytearray(base64.urlsafe_b64decode(signature + "=="))
    sig[0] ^= 1
    changed_sig = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    with pytest.raises(BrowserTabRefError, match="TAB_REF_SIGNATURE_INVALID"):
        codec().decode(f"{prefix}.{payload}.{changed_sig}", now_ms=NOW)


def test_time_window_is_short_exact_and_bool_safe():
    with pytest.raises(BrowserTabRefError, match="TIME_WINDOW_INVALID"):
        binding(expires_at_ms=NOW + MAX_TAB_REF_LIFETIME_MS + 1)
    with pytest.raises(BrowserTabRefError, match="TIME_WINDOW_INVALID"):
        binding(issued_at_ms=True)
    token = codec().encode(binding())
    with pytest.raises(BrowserTabRefError, match="TAB_REF_EXPIRED"):
        codec().decode(token, now_ms=NOW + 60_000)
    with pytest.raises(BrowserTabRefError, match="TIME_WINDOW_INVALID"):
        codec().decode(token, now_ms=NOW - 1)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("subject_digest", "B" * 64, "SUBJECT_INVALID"),
        ("client_ref", "person@example.com", "REFERENCE_INVALID"),
        ("resource", "/private/path", "REFERENCE_INVALID"),
        ("host_ref", "host x", "REFERENCE_INVALID"),
        ("profile_ref", "", "REFERENCE_INVALID"),
        ("boot_ref", "x\n", "REFERENCE_INVALID"),
        ("browser_instance_ref", "x\n", "REFERENCE_INVALID"),
        ("connection_generation", True, "REFERENCE_INVALID"),
        ("tab_locator", True, "TAB_LOCATOR_INVALID"),
        ("tab_locator", -1, "TAB_LOCATOR_INVALID"),
        ("document_revision", -1, "DOCUMENT_REVISION_INVALID"),
        ("catalog_schema_digest", "g" * 64, "CATALOG_SCHEMA_DIGEST_INVALID"),
        ("backend_schema_digest", "g" * 64, "BACKEND_SCHEMA_DIGEST_INVALID"),
        ("browser_ref", "", "BROWSER_REF_INVALID"),
    ],
)
def test_binding_shape_is_strict_and_secret_safe(field, value, code):
    with pytest.raises(BrowserTabRefError, match=code):
        binding(**{field: value})


def test_ref_contains_no_socket_cdp_path_or_credential_field():
    names = set(BrowserTabRef.__dataclass_fields__)
    for forbidden in {
        "socket_path",
        "cdp_endpoint",
        "user_data_dir",
        "credential",
        "access_token",
        "api_key",
        "cookie",
        "password",
    }:
        assert forbidden not in names


def test_reconnect_requires_new_signed_generation():
    first = codec().encode(binding(connection_generation="generation-a"))
    second = codec().encode(binding(connection_generation="generation-b"))
    assert first != second
    assert codec().decode(first, now_ms=NOW).connection_generation == "generation-a"
    assert codec().decode(second, now_ms=NOW).connection_generation == "generation-b"


def test_duplicate_json_fields_are_refused_even_with_a_valid_hmac():
    row = binding()
    canonical = codec()._payload(row)
    raw = canonical[:-1] + b',"tab_locator":99}'
    signature = hmac.new(KEY, b"mastermind.browser-tab-ref.v1\0" + raw, hashlib.sha256).digest()
    token = (
        "v1."
        + base64.urlsafe_b64encode(raw).decode().rstrip("=")
        + "."
        + base64.urlsafe_b64encode(signature).decode().rstrip("=")
    )
    with pytest.raises(BrowserTabRefError, match="TAB_REF_INVALID"):
        codec().decode(token, now_ms=NOW)


def test_unsupported_backend_and_forged_object_are_refused():
    with pytest.raises(BrowserTabRefError, match="BACKEND_INVALID"):
        binding(backend="raw_cdp")
    token = codec().encode(binding())
    with pytest.raises(BrowserTabRefError, match="TAB_REF_INVALID"):
        codec().decode({"token": token}, now_ms=NOW)

def test_tab_ref_binds_host_boot_and_both_schema_layers_explicitly():
    names = set(BrowserTabRef.__dataclass_fields__)
    assert {"boot_ref", "catalog_schema_digest", "backend_schema_digest"} <= names
    assert "tool_schema_digest" not in names

def test_boot_and_schema_generations_are_covered_by_the_signature():
    base = codec().encode(binding())
    variants = (
        binding(boot_ref="boot-b"),
        binding(catalog_schema_digest="f" * 64),
        binding(backend_schema_digest="0" * 64),
    )
    assert all(codec().encode(value) != base for value in variants)

from __future__ import annotations

import hashlib
import json

import pytest

from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA, VerifiedPrincipal
from integrations.mastermind_executive_app.coo_binding import (
    BINDING_SCHEMA,
    COO_SCOPES,
)
from ops.executive_os import executive_mcp_entry as entry


RESOURCE = "https://mcp.mastermind-x.com/mcp"
METADATA = "https://mcp.mastermind-x.com/.well-known/oauth-protected-resource"
ISSUER = "https://issuer.example.com"
SUBJECT = "1" * 64
CLIENT = "2" * 64
PERMISSION = "3" * 64


def policy(policy_id: str, scopes: list[str]) -> dict:
    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": policy_id,
        "resource": RESOURCE,
        "resource_metadata_url": METADATA,
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "required_scopes": scopes,
        "allowed_subject_digests": [SUBJECT],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 600,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 30,
    }


def base_document() -> dict:
    return {
        "schema": entry.CONFIG_SCHEMA,
        "release_sha": "a" * 40,
        "service_uid": 458,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8443,
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "policies": {
            "schema": "mastermind.executive_app_policy_example.v1",
            "read": policy("executive-read", ["mastermind.executive.read"]),
            "submit": policy(
                "executive-submit",
                ["mastermind.executive.intent.submit", "mastermind.executive.read"],
            ),
        },
    }


def coo_binding(*, client_ref: str = CLIENT, enabled: bool = True) -> dict:
    if not enabled:
        return {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
    return {
        "schema": BINDING_SCHEMA,
        "enabled": True,
        "binding": {
            "policy_id": "executive-coo",
            "issuer_digest": hashlib.sha256(ISSUER.encode()).hexdigest(),
            "subject_digest": SUBJECT,
            "client_ref": client_ref,
            "resource": RESOURCE,
            "scopes": list(COO_SCOPES),
            "permission_digest": PERMISSION,
        },
    }


def coo_block(*, binding: dict | None = None) -> dict:
    return {
        "policy": policy("executive-coo", list(COO_SCOPES)),
        "binding": binding if binding is not None else coo_binding(),
    }


def principal(*, client_ref: str = CLIENT) -> VerifiedPrincipal:
    return VerifiedPrincipal(
        policy_id="executive-coo",
        issuer=ISSUER,
        issuer_digest=hashlib.sha256(ISSUER.encode()).hexdigest(),
        resource=RESOURCE,
        subject_digest=SUBJECT,
        client_ref=client_ref,
        scopes=COO_SCOPES,
        issued_at=100,
        expires_at=200,
        jti_digest="4" * 64,
    )


def test_existing_install_document_accepts_exact_optional_coo_policy_and_binding():
    raw = base_document()
    raw["coo"] = coo_block()
    assert entry.validate_document(raw) == raw
    policies = entry.optional_policies(raw)
    assert set(policies) == {"coo"}
    assert policies["coo"].required_scopes == COO_SCOPES


@pytest.mark.parametrize("fault", ["extra", "missing_binding", "wrong_scope", "wrong_resource", "policy_id_collision"])
def test_optional_coo_install_block_fails_closed(fault):
    raw = base_document()
    raw["coo"] = coo_block()
    if fault == "extra":
        raw["coo"]["extra"] = True
    elif fault == "missing_binding":
        del raw["coo"]["binding"]
    elif fault == "wrong_scope":
        raw["coo"]["policy"]["required_scopes"] = ["mastermind.executive.read"]
    elif fault == "wrong_resource":
        raw["coo"]["policy"]["resource"] = "https://other.example.com/mcp"
    else:
        raw["coo"]["policy"]["policy_id"] = raw["policies"]["read"]["policy_id"]
        raw["coo"]["binding"]["policy_id"] = raw["policies"]["read"]["policy_id"]
    with pytest.raises(ValueError):
        entry.validate_document(raw)


def test_coo_binding_projection_can_rotate_but_policy_and_install_cannot(tmp_path, monkeypatch):
    source = tmp_path / ("a" * 40)
    source.mkdir()
    config = tmp_path / "executive-mcp.json"
    raw = base_document()
    raw["coo"] = coo_block()
    config.write_text(json.dumps(raw))

    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(entry.os, "geteuid", lambda: 458)

    loader = entry.current_projection_loader(config, source, raw, "coo", "binding")
    assert loader() == raw["coo"]["binding"]

    rotated = json.loads(json.dumps(raw))
    rotated["coo"]["binding"] = coo_binding(client_ref="f" * 64)
    config.write_text(json.dumps(rotated))
    assert loader() == rotated["coo"]["binding"]

    changed_policy = json.loads(json.dumps(rotated))
    changed_policy["coo"]["policy"]["policy_id"] = "executive-coo-v2"
    changed_policy["coo"]["binding"]["policy_id"] = "executive-coo-v2"
    config.write_text(json.dumps(changed_policy))
    with pytest.raises(ValueError):
        loader()

    config.write_text(json.dumps({key: value for key, value in raw.items() if key != "coo"}))
    with pytest.raises(ValueError, match="optional mount withdrawn"):
        loader()


def test_installed_factory_reloads_binding_for_immediate_revoke_and_rotation(tmp_path, monkeypatch):
    source = tmp_path / ("a" * 40)
    source.mkdir()
    config = tmp_path / "executive-mcp.json"
    raw = base_document()
    raw["coo"] = coo_block()
    config.write_text(json.dumps(raw))

    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(entry.os, "geteuid", lambda: 458)

    gate = entry.build_coo_principal_authorizer(raw, source, config)
    assert gate is not None
    assert gate(principal()) is True
    first_digest = gate.binding_digest(principal())
    assert isinstance(first_digest, str) and len(first_digest) == 64

    disabled = json.loads(json.dumps(raw))
    disabled["coo"]["binding"] = coo_binding(enabled=False)
    config.write_text(json.dumps(disabled))
    assert gate(principal()) is False
    assert gate.binding_digest(principal()) is None

    rotated = json.loads(json.dumps(raw))
    rotated["coo"]["binding"] = coo_binding(client_ref="f" * 64)
    config.write_text(json.dumps(rotated))
    assert gate(principal()) is False
    assert gate(principal(client_ref="f" * 64)) is True
    assert gate.binding_digest(principal(client_ref="f" * 64)) != first_digest


def test_absent_coo_block_preserves_existing_install_behavior(tmp_path, monkeypatch):
    source = tmp_path / ("a" * 40)
    source.mkdir()
    config = tmp_path / "executive-mcp.json"
    raw = base_document()
    config.write_text(json.dumps(raw))
    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(entry.os, "geteuid", lambda: 458)
    assert entry.validate_document(raw) == raw
    assert entry.build_coo_principal_authorizer(raw, source, config) is None

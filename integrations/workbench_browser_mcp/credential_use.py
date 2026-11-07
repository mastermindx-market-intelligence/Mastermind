"""One host-selected credential narrowing of the existing Workbench lease.

This is not an account registry, credential store, unlock service, or effect
owner. The private v3 service config selects one existing Hermes login item.
Only WorkbenchActionRuntime projects it into an actual, live browser dispatch.
No secret is loaded by configuration, preparation, or this projection.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from http.client import HTTPS_PORT
from pathlib import PurePosixPath
from urllib.parse import urlsplit


CREDENTIAL_GRANT_SCHEMA = "mastermind.workbench_browser_credential_grant.v1"
CREDENTIAL_USE_SCHEMA = "mastermind.workbench_browser_credential_use.v1"
CREDENTIAL_RESULT_SCHEMA = "mastermind.workbench_browser_credential_result.v1"
CREDENTIAL_ACTION_SCHEMA = "mastermind.workbench_browser_action.credential.v1"
CREDENTIAL_TOOL = "workbench_credential_fill"
PREPARE_CREDENTIAL_TOOL = "prepare_browser_credential_fill"
_REF = re.compile(r"credential:[a-f0-9]{32}")
_ITEM = re.compile(r"vault_[a-f0-9]{12}")
_HEX64 = re.compile(r"[a-f0-9]{64}")
_HEX32 = re.compile(r"[a-f0-9]{32}")


class CredentialUseRefused(ValueError):
    def __init__(self):
        super().__init__("CREDENTIAL_USE_REFUSED")


@dataclasses.dataclass(frozen=True)
class BrowserCredentialGrant:
    schema: str
    grant_ref: str
    backend: str
    vault_directory: str
    vault_device: int
    vault_inode: int
    item_ref: str
    account_identifier: str
    origin: str
    expires_at_ms: int


@dataclasses.dataclass(frozen=True)
class CredentialRuntimeConfig:
    runtime_root: str
    manifest_sha256: str


def _absolute(value: object) -> str:
    if (type(value) is not str or not value.startswith("/")
            or "\x00" in value or ".." in PurePosixPath(value).parts
            or str(PurePosixPath(value)) != value or value == "/"):
        raise CredentialUseRefused()
    return value


def exact_https_origin(value: object) -> str:
    if type(value) is not str or len(value) > 512 or not value.isascii():
        raise CredentialUseRefused()
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        raise CredentialUseRefused() from None
    if (parsed.scheme != "https" or not hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or any(c.isspace() or ord(c) < 33 for c in value)
            or hostname.endswith(".") or "*" in hostname or "\\" in value):
        raise CredentialUseRefused()
    # URL.origin canonicalization: default port is omitted, host is lowercase.
    host = "[" + hostname + "]" if ":" in hostname else hostname
    canonical = "https://" + host + (":" + str(port) if port not in (None, HTTPS_PORT) else "")
    if value != canonical:
        raise CredentialUseRefused()
    return value


def parse_credential_grant(value: object) -> BrowserCredentialGrant:
    keys = {f.name for f in dataclasses.fields(BrowserCredentialGrant)}
    if type(value) is not dict or set(value) != keys:
        raise CredentialUseRefused()
    if (value["schema"] != CREDENTIAL_GRANT_SCHEMA or value["backend"] != "hermes-fernet-v1"
            or type(value["grant_ref"]) is not str or _REF.fullmatch(value["grant_ref"]) is None
            or type(value["item_ref"]) is not str or _ITEM.fullmatch(value["item_ref"]) is None
            or type(value["account_identifier"]) is not str
            or not 1 <= len(value["account_identifier"].encode("utf-8")) <= 320
            or value["account_identifier"].strip() != value["account_identifier"]
            or any(ord(c) < 32 for c in value["account_identifier"])
            or type(value["vault_device"]) is not int or value["vault_device"] < 0
            or type(value["vault_inode"]) is not int or value["vault_inode"] < 1
            or type(value["expires_at_ms"]) is not int
            or not 0 < value["expires_at_ms"] < 2**53):
        raise CredentialUseRefused()
    _absolute(value["vault_directory"])
    exact_https_origin(value["origin"])
    return BrowserCredentialGrant(**value)


def parse_credential_runtime(value: object) -> CredentialRuntimeConfig:
    if (type(value) is not dict or set(value) != {"runtime_root", "manifest_sha256"}
            or type(value["manifest_sha256"]) is not str
            or _HEX64.fullmatch(value["manifest_sha256"]) is None
            or value["manifest_sha256"] == "0" * 64):
        raise CredentialUseRefused()
    return CredentialRuntimeConfig(_absolute(value["runtime_root"]), value["manifest_sha256"])


_USE_KEYS = {"schema", "grant", "resource_id", "expires_at_ms", "binding_sha256"}


def validate_private_use(value: object, *, resource_id: str, now_ms: int) -> dict:
    if (type(value) is not dict or set(value) != _USE_KEYS
            or value.get("schema") != CREDENTIAL_USE_SCHEMA
            or type(resource_id) is not str or _HEX32.fullmatch(resource_id) is None
            or value.get("resource_id") != resource_id
            or type(now_ms) is not int or now_ms < 0
            or type(value.get("expires_at_ms")) is not int
            or not now_ms < value["expires_at_ms"] < 2**53
            or type(value.get("binding_sha256")) is not str
            or _HEX64.fullmatch(value["binding_sha256"]) is None):
        raise CredentialUseRefused()
    grant = parse_credential_grant(value["grant"])
    if value["expires_at_ms"] > grant.expires_at_ms:
        raise CredentialUseRefused()
    return {**value, "grant": dataclasses.asdict(grant)}


def credential_selection_digest(use: dict) -> str:
    """Freeze the complete enrolled selection, not just its reusable label."""
    selected = {key: use[key] for key in ("grant", "resource_id", "binding_sha256")}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


CREDENTIAL_RESULT_CODES = frozenset({
    "FILLED", "TARGET_REFUSED", "VAULT_UNAVAILABLE", "ITEM_REFUSED",
    "PERMISSION_EXPIRED", "CREDENTIAL_LIMIT", "FILL_UNCERTAIN", "PROTOCOL_REFUSED",
})


def credential_result(effect_state: str, code: str) -> dict:
    allowed = {"APPLIED": {"FILLED"}, "EFFECT_UNKNOWN": {"FILL_UNCERTAIN"},
        "NOT_APPLIED": CREDENTIAL_RESULT_CODES - {"FILLED", "FILL_UNCERTAIN"}}
    if (type(effect_state) is not str or type(code) is not str
            or effect_state not in allowed or code not in allowed[effect_state]):
        raise CredentialUseRefused()
    return {"schema": CREDENTIAL_RESULT_SCHEMA, "effect_state": effect_state, "code": code}


def validate_credential_result(value: object) -> dict:
    if type(value) is not dict or set(value) != {"schema", "effect_state", "code"}:
        raise CredentialUseRefused()
    expected = credential_result(value["effect_state"], value["code"])
    if expected != value:
        raise CredentialUseRefused()
    return expected

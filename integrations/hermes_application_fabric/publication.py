"""Closed nonsecret input to the existing held Hermes installation owner.

This is configuration and source qualification, not an APPLICATION grant. The
incumbent factory still checks current policy/capability before reading its
role credential; the remote APPLICATION owner admits physical capacity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .errors import HermesFabricError

SCHEMA = "mastermind.hermes_primary_application/v1"
AUTO_SCHEMA = "mastermind.hermes_primary_application/v2"
EXACT_SCHEMA = "mastermind.hermes_primary_application/v3"
AUTO_MODEL = "mastermind-fabric/auto"
PROVIDER = "mastermind-fabric"
ROLE_RELATIONS = {
    "mmsecretary": ("hermes-secretary", "hermes_secretary_fabric",
                    "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN", "127.0.0.2"),
    "mmmeta": ("hermes-meta-ceo", "hermes_meta_fabric",
               "HERMES_META_FABRIC_APPLICATION_TOKEN", "127.0.0.3"),
}
APPLICATION_PORT = 50142
PACKAGE_FILES = (
    "__init__.py", "client.py", "codec.py", "errors.py", "host.py", "native.py",
    "publication.py", "structured.py", "requirements.txt",
    "model_provider/__init__.py", "model_provider/plugin.yaml",
)
PACKAGE_ROOT = "integrations/hermes_application_fabric/"


def _refuse():
    raise HermesFabricError("hermes_fabric_publication_invalid")


def _identity(value, maximum=256):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or any(ord(c) < 33 or ord(c) == 127 for c in value)):
        _refuse()
    try:
        if len(value.encode("utf-8")) > maximum:
            _refuse()
    except UnicodeError:
        _refuse()
    return value


@dataclass(frozen=True)
class PrimaryPublication:
    role: str
    enrollment_request_id: str
    principal_id: str
    macro_root: str
    macro_commit_sha: str
    model: str
    max_tokens: int
    package_sha256: str
    automatic: bool = False
    strict_pool: str | None = None
    strict_model: str | None = None


def publication_from_document(document) -> PrimaryPublication:
    keys = {"schema", "role", "enrollment_request_id", "principal_id", "macro_root",
            "macro_commit_sha", "model", "max_tokens", "package_sha256"}
    exact = type(document) is dict and document.get("schema") == EXACT_SCHEMA
    automatic = exact or type(document) is dict and document.get("schema") == AUTO_SCHEMA
    fields = keys | {"routing"} if automatic else keys
    if (type(document) is not dict or set(document) != fields
            or document["schema"] != (EXACT_SCHEMA if exact else AUTO_SCHEMA if automatic else SCHEMA)
            or type(document["role"]) is not str or document["role"] not in ROLE_RELATIONS
            or type(document["macro_commit_sha"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", document["macro_commit_sha"]) is None
            or type(document["package_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", document["package_sha256"]) is None
            or type(document["max_tokens"]) is not int or not 1 <= document["max_tokens"] <= 4096):
        _refuse()
    strict_pool = None
    if automatic:
        routing = document["routing"]
        if (type(routing) is not dict or set(routing) != {"mode", "strict_pool"}
                or routing["mode"] != ("exact" if exact else "auto")
                or not exact and document["model"] != AUTO_MODEL):
            _refuse()
        if exact:
            from .codec import ID
            if (type(document["model"]) is not str or ID.fullmatch(document["model"]) is None
                    or document["model"] == AUTO_MODEL):
                _refuse()
        strict_pool = routing["strict_pool"]
        if strict_pool is not None:
            _identity(strict_pool, 128)
    for key in ("enrollment_request_id", "principal_id", "model"):
        _identity(document[key])
    if re.fullmatch(r"uid:[1-9][0-9]{0,9}", document["principal_id"]) is None:
        _refuse()
    root = document["macro_root"]
    if (type(root) is not str or not root.startswith("/") or len(root) > 1024
            or any(ord(c) < 33 or ord(c) == 127 for c in root)
            or str(Path(root)) != root or ".." in Path(root).parts
            or Path(root).name != document["macro_commit_sha"]):
        _refuse()
    return PrimaryPublication(**{key: document[key] for key in keys - {"schema"}},
                              automatic=automatic, strict_pool=strict_pool,
                              strict_model=document["model"] if exact else None)


def validate_publication(document):
    publication_from_document(document)
    return json.loads(json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False))


def held_package_digest(owner):
    """Use the incumbent held release; never trust a role-home package hash."""
    rows = {name: hashlib.sha256(owner.source(PACKAGE_ROOT + name)).hexdigest()
            for name in PACKAGE_FILES}
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def qualify_installation(document, *, role, enrollment, import_roots, principal_id=None):
    publication = publication_from_document(document)
    if (publication.role != role or type(enrollment) is not dict
            or publication.enrollment_request_id != enrollment.get("request_id")
            or publication.macro_root not in import_roots
            or principal_id is not None and publication.principal_id != principal_id):
        raise HermesFabricError("hermes_fabric_installation_mismatch")
    return publication


def qualify_launch(launch, profile):
    raw = launch.recipe.get("primary_application")
    if raw is None:
        if profile.model_provider == PROVIDER:
            raise HermesFabricError("hermes_fabric_publication_required")
        return None
    publication = qualify_installation(raw, role=profile.role,
        enrollment=launch.recipe.get("session_enrollment"), import_roots=launch.recipe["import_roots"],
        principal_id="uid:" + str(launch.row["uid"]))
    if (profile.model_provider != PROVIDER or profile.model_default != publication.model
            or profile.native_provider_id is not None
            or profile.gateway_backend != "native-session-authority"
            or held_package_digest(launch.owner) != publication.package_sha256):
        raise HermesFabricError("hermes_fabric_installation_mismatch")
    launch.check()
    return publication


def expected_native_config(profile, document, consumer=None):
    """Compose the actual keyless native config with the existing MCP renderer."""
    from integrations.hermes_harness.native_mcp import (
        render_disarmed_native_config, render_consumer_mcp_server, render_consumer_plugin_config)
    from integrations.hermes_steward.config_guard import _load_unique_yaml
    publication = publication_from_document(document)
    if (profile.role != publication.role or profile.model_provider != PROVIDER
            or profile.model_default != publication.model or profile.native_provider_id is not None
            or profile.extension_allowlist or profile.gateway_backend != "native-session-authority"):
        raise HermesFabricError("hermes_fabric_profile_mismatch")
    native = _load_unique_yaml(render_disarmed_native_config(profile).encode())
    native["model"] = {"provider": PROVIDER, "default": publication.model,
                       "api_mode": "chat_completions"}
    native.pop("providers", None)
    native.pop("auxiliary", None)
    native["fallback_providers"] = []
    if consumer is not None:
        from integrations.hermes_harness.native_executive_consumer import publication_from_document as consumer_from
        other = consumer_from(consumer)
        native["mcp_servers"][other.mcp.server] = render_consumer_mcp_server(other)
        native["plugins"] = render_consumer_plugin_config(other)
    import yaml
    rendered = "# Primary inference uses the qualified APPLICATION owner.\n" + yaml.safe_dump(
        native, sort_keys=False, allow_unicode=False)
    if len(rendered.encode()) > 64 * 1024 or _load_unique_yaml(rendered.encode()) != native:
        raise HermesFabricError("hermes_fabric_config_invalid")
    return rendered


def primary_child_env(profile, document, secrets):
    """Select only this role's internal credential from the existing secret owner."""
    publication = publication_from_document(document)
    if profile.role != publication.role:
        raise HermesFabricError("hermes_fabric_profile_mismatch")
    reference = ROLE_RELATIONS[publication.role][2]
    references = {row[2] for row in ROLE_RELATIONS.values()}
    if (references - {reference}).intersection(secrets.values):
        raise HermesFabricError("hermes_fabric_role_credential_conflict")
    value = secrets.values.get(reference)
    if (type(value) is not str or not 32 <= len(value) <= 4096 or not value.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in value)
            or value.startswith(("v1.", "app1.", "app2."))
            or value in {secrets.token, secrets.dashboard_password}
            or any(other == value for name, other in secrets.values.items() if name != reference)):
        raise HermesFabricError("hermes_fabric_role_credential_unqualified")
    return {reference: value, "HERMES_STARTUP_WARMUP_TIMEOUT": "0"}

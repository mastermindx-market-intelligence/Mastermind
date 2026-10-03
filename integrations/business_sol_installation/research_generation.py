"""Successor Mastermind research-generation installation contract.

This module extends the incumbent Business installation owner without changing
frozen BSC-U1 generation-one semantics. It compiles one private app reference
and separates package assembly readiness from fresh-session canary readiness.
It performs no workspace, OAuth, app-publication, GitHub, or research effects.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .bindings import Compilation, canonical_json, sha256_bytes

REQUEST_SCHEMA = "mastermind.business_sol_research_generation_request.v1"
PREFLIGHT_SCHEMA = "mastermind.business_sol_research_generation_preflight.v1"
PUBLIC_RECEIPT_SCHEMA = "mastermind.business_sol_research_generation_receipt.v1"
GENERATION = 2
PLUGIN_NAME = "mastermind-sol"
PLUGIN_DISPLAY_NAME = "Mastermind CEO"
CANDIDATE_PLUGIN_VERSION = "0.3.0"
GENERATED_FILE = ".app.json"
EXPECTED_RESEARCH_SKILL_BLOB_SHA = "006c10283d200b47e4cb816906be5f5db3ce7a0f"
EXPECTED_STEWARD_SERVER_VERSION = "3.0.0"
EXPECTED_STEWARD_TOOL_CONTRACT_DIGEST = (
    "8eec65289bf72818fe8362cb02587b6cc78c6eb526a1f602edbd22ffff030918"
)

REQUIRED_STEWARD_TOOLS = (
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
    "search",
    "fetch",
)

ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "SECRET_SHAPED_INPUT",
        "PLUGIN_IDENTITY_MISMATCH",
        "PLUGIN_SOURCE_MISMATCH",
        "WORKSPACE_MISMATCH",
        "APP_IDENTITY_MISMATCH",
        "APP_CONTRACT_MISMATCH",
        "PREFLIGHT_HELD",
    }
)

_SHA40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_TOKEN_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{0,95}\Z")
_PLUGIN_ID_RE = re.compile(r"\APlugin_[0-9A-Fa-f]{32}\Z")
_APP_ID_RE = re.compile(r"\Aasdk_app_[0-9a-f]{32}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PRIVATE_PATH_RE = re.compile(r"(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Za-z]:\\)")
_SECRET_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:xox[abprs]-|xapp-|ghp_|github_pat_|sk-(?:proj-)?|"
    r"sk-ant-|Bearer\s+|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)

_REQUEST_KEYS = frozenset(
    {
        "schema",
        "generation",
        "source_commit",
        "observed_source_commit",
        "plugin_package_digest",
        "observed_plugin_package_digest",
        "workspace_digest",
        "workspace_role",
        "plugin",
        "steward",
        "github",
    }
)
_PLUGIN_KEYS = frozenset(
    {
        "name",
        "version",
        "registry_id",
        "approved_registry_id_digest",
        "display_name",
        "installation_policy",
        "installed_version",
        "installed_scanned_generation",
        "approved_scanned_generation",
        "installed",
        "enabled",
        "research_skill_loaded",
        "research_skill_blob_sha",
    }
)
_STEWARD_KEYS = frozenset(
    {
        "app_id",
        "approved_app_id_digest",
        "display_name",
        "workspace_digest",
        "publication_state",
        "app_generation",
        "approved_app_generation",
        "server_name",
        "server_version",
        "approved_server_version",
        "resource_digest",
        "approved_resource_digest",
        "oauth_policy_digest",
        "approved_oauth_policy_digest",
        "tool_names",
        "tool_contract_digest",
        "approved_tool_contract_digest",
        "frozen_snapshot_digest",
        "approved_frozen_snapshot_digest",
        "enabled",
        "available",
        "installed",
        "connected",
        "authenticated",
        "deep_research_eligible",
        "company_knowledge_eligible",
        "citation_surface_ready",
    }
)
_GITHUB_KEYS = frozenset({"connected", "repository", "repository_authorized"})


class ResearchGenerationError(ValueError):
    """Fixed, payload-free refusal for successor research-generation input."""

    def __init__(self, code: str) -> None:
        safe = code if code in ERROR_CODES else "INVALID_INPUT"
        super().__init__(safe)
        self.code = safe

@dataclass(frozen=True, order=True)
class ResearchIssue:
    code: str
    logical_name: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "logical_name": self.logical_name}


def _exact_dict(value: object, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ResearchGenerationError("INVALID_INPUT")
    return value


def _exact_list(value: object) -> list[Any]:
    if type(value) is not list:
        raise ResearchGenerationError("INVALID_INPUT")
    return value


def _string(value: object, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _CONTROL_RE.search(value)
    ):
        raise ResearchGenerationError("INVALID_INPUT")
    return value


def _token(value: object) -> str:
    result = _string(value, maximum=96)
    if _TOKEN_RE.fullmatch(result) is None:
        raise ResearchGenerationError("INVALID_INPUT")
    return result

def _digest(value: object) -> str:
    result = _string(value, maximum=64)
    if _DIGEST_RE.fullmatch(result) is None:
        raise ResearchGenerationError("INVALID_INPUT")
    return result


def _sha40(value: object) -> str:
    result = _string(value, maximum=40)
    if _SHA40_RE.fullmatch(result) is None:
        raise ResearchGenerationError("INVALID_INPUT")
    return result


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise ResearchGenerationError("INVALID_INPUT")
    return value


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scan_for_secrets(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            _scan_for_secrets(key)
            _scan_for_secrets(item)
        return
    if type(value) is list:
        for item in value:
            _scan_for_secrets(item)
        return
    if type(value) is str:
        if (
            _SECRET_RE.search(value)
            or _EMAIL_RE.search(value)
            or "://" in value
            or _PRIVATE_PATH_RE.search(value)
        ):
            raise ResearchGenerationError("SECRET_SHAPED_INPUT")
        return
    if value is None or type(value) in {bool, int}:
        return
    raise ResearchGenerationError("INVALID_INPUT")


def _normalize_plugin(raw: object) -> tuple[dict[str, object], list[ResearchIssue]]:
    plugin = _exact_dict(raw, _PLUGIN_KEYS)
    registry_id = _string(plugin["registry_id"], maximum=64)
    if _PLUGIN_ID_RE.fullmatch(registry_id) is None:
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    registry_digest = _digest(plugin["approved_registry_id_digest"])
    if _digest_text(registry_id) != registry_digest:
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    if (
        plugin["name"] != PLUGIN_NAME
        or plugin["version"] != CANDIDATE_PLUGIN_VERSION
        or plugin["display_name"] != PLUGIN_DISPLAY_NAME
        or plugin["installation_policy"] != "INSTALLED_BY_DEFAULT"
    ):
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")

    installed_version = _token(plugin["installed_version"])
    scanned = _token(plugin["installed_scanned_generation"])
    approved_scanned = _token(plugin["approved_scanned_generation"])
    research_skill_blob_sha = _sha40(plugin["research_skill_blob_sha"])
    if research_skill_blob_sha != EXPECTED_RESEARCH_SKILL_BLOB_SHA:
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    issues: list[ResearchIssue] = []
    if installed_version != CANDIDATE_PLUGIN_VERSION:
        issues.append(ResearchIssue("PLUGIN_VERSION_STALE", PLUGIN_NAME))
    if scanned != approved_scanned:
        issues.append(ResearchIssue("PLUGIN_SNAPSHOT_STALE", PLUGIN_NAME))
    if not _bool(plugin["installed"]):
        issues.append(ResearchIssue("PLUGIN_NOT_INSTALLED", PLUGIN_NAME))
    if not _bool(plugin["enabled"]):
        issues.append(ResearchIssue("PLUGIN_DISABLED", PLUGIN_NAME))
    if not _bool(plugin["research_skill_loaded"]):
        issues.append(ResearchIssue("RESEARCH_SKILL_NOT_LOADED", PLUGIN_NAME))

    return {
        "registry_id": registry_id,
        "registry_id_digest": registry_digest,
        "installed_version": installed_version,
        "installed_scanned_generation": scanned,
        "approved_scanned_generation": approved_scanned,
        "installed": bool(plugin["installed"]),
        "enabled": bool(plugin["enabled"]),
        "research_skill_loaded": bool(plugin["research_skill_loaded"]),
        "research_skill_blob_sha": research_skill_blob_sha,
    }, issues


def _normalize_steward(
    raw: object,
    *,
    workspace_digest: str,
) -> tuple[dict[str, object], list[ResearchIssue], list[ResearchIssue]]:
    app = _exact_dict(raw, _STEWARD_KEYS)
    if app["workspace_digest"] != workspace_digest:
        raise ResearchGenerationError("WORKSPACE_MISMATCH")
    app_id_raw = app["app_id"]
    approved_app_id_digest = app["approved_app_id_digest"]
    assembly_issues: list[ResearchIssue] = []
    if app_id_raw is None:
        if approved_app_id_digest is not None:
            raise ResearchGenerationError("APP_IDENTITY_MISMATCH")
        app_id: str | None = None
        app_id_digest: str | None = None
        assembly_issues.append(
            ResearchIssue("APP_ID_MISSING", "mastermind-steward")
        )
    else:
        app_id = _string(app_id_raw, maximum=96)
        if _APP_ID_RE.fullmatch(app_id) is None:
            raise ResearchGenerationError("APP_IDENTITY_MISMATCH")
        app_id_digest = _digest(approved_app_id_digest)
        if _digest_text(app_id) != app_id_digest:
            raise ResearchGenerationError("APP_IDENTITY_MISMATCH")
    if app["display_name"] != "Mastermind Steward":
        raise ResearchGenerationError("APP_IDENTITY_MISMATCH")
    if app["server_name"] != "mastermind-steward":
        raise ResearchGenerationError("APP_CONTRACT_MISMATCH")

    app_generation = _token(app["app_generation"])
    approved_generation = _token(app["approved_app_generation"])
    server_version = _token(app["server_version"])
    approved_server_version = _token(app["approved_server_version"])
    resource_digest = _digest(app["resource_digest"])
    oauth_digest = _digest(app["oauth_policy_digest"])
    tool_digest = _digest(app["tool_contract_digest"])
    snapshot_digest = _digest(app["frozen_snapshot_digest"])
    if (
        app_generation != approved_generation
        or server_version != approved_server_version
        or server_version != EXPECTED_STEWARD_SERVER_VERSION
        or resource_digest != _digest(app["approved_resource_digest"])
        or oauth_digest != _digest(app["approved_oauth_policy_digest"])
        or tool_digest != _digest(app["approved_tool_contract_digest"])
        or tool_digest != EXPECTED_STEWARD_TOOL_CONTRACT_DIGEST
        or snapshot_digest != _digest(app["approved_frozen_snapshot_digest"])
    ):
        raise ResearchGenerationError("APP_CONTRACT_MISMATCH")
    tool_names = tuple(_string(item, maximum=64) for item in _exact_list(app["tool_names"]))
    if tool_names != REQUIRED_STEWARD_TOOLS:
        assembly_issues.append(ResearchIssue("RESEARCH_TOOLS_MISSING", "mastermind-steward"))
    if _string(app["publication_state"], maximum=32) != "PUBLISHED":
        assembly_issues.append(ResearchIssue("APP_NOT_PUBLISHED", "mastermind-steward"))

    canary_issues: list[ResearchIssue] = []
    for condition, code in (
        (_bool(app["enabled"]), "STEWARD_DISABLED"),
        (_bool(app["available"]), "STEWARD_UNAVAILABLE"),
        (_bool(app["installed"]), "STEWARD_NOT_INSTALLED"),
        (_bool(app["connected"]), "STEWARD_CONNECTION_MISSING"),
        (_bool(app["authenticated"]), "STEWARD_AUTH_MISSING"),
        (_bool(app["deep_research_eligible"]), "STEWARD_DEEP_RESEARCH_INELIGIBLE"),
        (_bool(app["company_knowledge_eligible"]), "STEWARD_COMPANY_KNOWLEDGE_INELIGIBLE"),
        (_bool(app["citation_surface_ready"]), "STEWARD_CITATION_SURFACE_MISSING"),
    ):
        if not condition:
            canary_issues.append(ResearchIssue(code, "mastermind-steward"))

    return {
        "app_id": app_id,
        "app_id_digest": app_id_digest,
        "app_generation": app_generation,
        "server_version": server_version,
        "resource_digest": resource_digest,
        "oauth_policy_digest": oauth_digest,
        "tool_names": list(tool_names),
        "tool_contract_digest": tool_digest,
        "frozen_snapshot_digest": snapshot_digest,
    }, assembly_issues, canary_issues


def _normalize_github(raw: object) -> tuple[dict[str, object], list[ResearchIssue]]:
    github = _exact_dict(raw, _GITHUB_KEYS)
    repository = _string(github["repository"], maximum=128)
    connected = _bool(github["connected"])
    authorized = _bool(github["repository_authorized"])
    issues: list[ResearchIssue] = []
    if not connected:
        issues.append(ResearchIssue("GITHUB_NOT_CONNECTED", "github"))
    if repository != "mastermindx-market-intelligence/Mastermind" or not authorized:
        issues.append(ResearchIssue("GITHUB_REPO_UNAUTHORIZED", "github"))
    return {
        "connected": connected,
        "repository": repository,
        "repository_authorized": authorized,
    }, issues


def _normalize(
    request: object,
) -> tuple[dict[str, object], list[ResearchIssue], list[ResearchIssue]]:
    _scan_for_secrets(request)
    value = _exact_dict(request, _REQUEST_KEYS)
    if value["schema"] != REQUEST_SCHEMA:
        raise ResearchGenerationError("INVALID_INPUT")
    if type(value["generation"]) is not int or value["generation"] != GENERATION:
        raise ResearchGenerationError("INVALID_INPUT")
    source_commit = _sha40(value["source_commit"])
    observed_source_commit = _sha40(value["observed_source_commit"])
    package_digest = _digest(value["plugin_package_digest"])
    observed_package_digest = _digest(value["observed_plugin_package_digest"])
    if source_commit != observed_source_commit or package_digest != observed_package_digest:
        raise ResearchGenerationError("PLUGIN_SOURCE_MISMATCH")
    workspace_digest = _digest(value["workspace_digest"])
    workspace_role = _string(value["workspace_role"], maximum=16)
    if workspace_role not in {"ADMIN", "OWNER"}:
        raise ResearchGenerationError("WORKSPACE_MISMATCH")

    plugin, plugin_issues = _normalize_plugin(value["plugin"])
    steward, assembly_issues, steward_canary_issues = _normalize_steward(
        value["steward"],
        workspace_digest=workspace_digest,
    )
    github, github_issues = _normalize_github(value["github"])
    normalized: dict[str, object] = {
        "source_commit": source_commit,
        "plugin_package_digest": package_digest,
        "workspace_digest": workspace_digest,
        "workspace_role": workspace_role,
        "plugin": plugin,
        "steward": steward,
        "github": github,
    }
    return (
        normalized,
        sorted(set(assembly_issues)),
        sorted(set(plugin_issues + steward_canary_issues + github_issues)),
    )


def preflight_research_generation(request: object) -> dict[str, object]:
    """Return separate assembly and fresh-session canary readiness."""
    normalized, assembly_issues, canary_issues = _normalize(request)
    plugin = normalized["plugin"]
    steward = normalized["steward"]
    assert isinstance(plugin, dict)
    assert isinstance(steward, dict)
    assembly_status = "PREFLIGHT_HELD" if assembly_issues else "READY_TO_COMPILE"
    canary_status = (
        "CANARY_HELD" if assembly_issues or canary_issues else "READY_FOR_CANARY"
    )
    return {
        "schema": PREFLIGHT_SCHEMA,
        "generation": GENERATION,
        "assembly_status": assembly_status,
        "canary_status": canary_status,
        "source_commit": normalized["source_commit"],
        "plugin_package_digest": normalized["plugin_package_digest"],
        "workspace_digest": normalized["workspace_digest"],
        "plugin_registry_id_digest": plugin["registry_id_digest"],
        "research_skill_blob_sha": plugin["research_skill_blob_sha"],
        "steward_app_id_digest": steward["app_id_digest"],
        "steward_tool_contract_digest": steward["tool_contract_digest"],
        "steward_frozen_snapshot_digest": steward["frozen_snapshot_digest"],
        "required_steward_tools": list(REQUIRED_STEWARD_TOOLS),
        "assembly_issues": [issue.as_dict() for issue in assembly_issues],
        "canary_issues": [issue.as_dict() for issue in canary_issues],
        "binding_document_digest": None,
        "workspace_effect_applied": False,
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }


def compile_research_binding(request: object) -> Compilation:
    """Compile the private registered-app mapping after assembly preflight."""

    normalized, assembly_issues, canary_issues = _normalize(request)
    if assembly_issues:
        raise ResearchGenerationError("PREFLIGHT_HELD")
    plugin = normalized["plugin"]
    steward = normalized["steward"]
    assert isinstance(plugin, dict)
    assert isinstance(steward, dict)

    installation_plan = {
        "schema": "mastermind.business_sol_research_generation_plan.v1",
        "generation": GENERATION,
        "source": {
            "commit": normalized["source_commit"],
            "plugin_package_digest": normalized["plugin_package_digest"],
        },
        "workspace_digest": normalized["workspace_digest"],
        "plugin": {
            "name": PLUGIN_NAME,
            "version": CANDIDATE_PLUGIN_VERSION,
            "registry_id": plugin["registry_id"],
            "research_skill_blob_sha": plugin["research_skill_blob_sha"],
        },
        "steward": {
            "app_id": steward["app_id"],
            "app_generation": steward["app_generation"],
            "server_name": "mastermind-steward",
            "server_version": steward["server_version"],
            "resource_digest": steward["resource_digest"],
            "oauth_policy_digest": steward["oauth_policy_digest"],
            "tool_names": steward["tool_names"],
            "tool_contract_digest": steward["tool_contract_digest"],
            "frozen_snapshot_digest": steward["frozen_snapshot_digest"],
        },
    }
    document = {
        "apps": {
            "mastermind-steward": {
                "id": steward["app_id"],
                "required": True,
            }
        }
    }
    content = canonical_json(document) + b"\n"
    binding_digest = sha256_bytes(content)
    public_receipt = {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "status": "READY_TO_STAGE",
        "generation": GENERATION,
        "source_commit": normalized["source_commit"],
        "plugin_package_digest": normalized["plugin_package_digest"],
        "workspace_digest": normalized["workspace_digest"],
        "plugin_version": CANDIDATE_PLUGIN_VERSION,
        "plugin_registry_id_digest": plugin["registry_id_digest"],
        "research_skill_blob_sha": plugin["research_skill_blob_sha"],
        "steward_app_id_digest": steward["app_id_digest"],
        "steward_tool_contract_digest": steward["tool_contract_digest"],
        "steward_frozen_snapshot_digest": steward["frozen_snapshot_digest"],
        "installation_plan_digest": sha256_bytes(canonical_json(installation_plan)),
        "binding_document_digest": binding_digest,
        "binding_count": 1,
        "logical_bindings": ["mastermind-steward"],
        "generated_file": GENERATED_FILE,
        "canary_status": "CANARY_HELD" if canary_issues else "READY_FOR_CANARY",
        "canary_issues": [issue.as_dict() for issue in canary_issues],
        "workspace_effect_applied": False,
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }
    return Compilation(
        document=document,
        content=content,
        binding_digest=binding_digest,
        public_receipt=public_receipt,
    )


def compile_research_manifest(manifest: object) -> bytes:
    """Project a reviewed research-generation manifest into the app-bound shape."""

    manifest_keys = frozenset(
        {"name", "version", "description", "author", "skills", "interface"}
    )
    author_keys = frozenset({"name"})
    interface_keys = frozenset(
        {
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
            "capabilities",
        }
    )
    if type(manifest) is not dict or set(manifest) != manifest_keys:
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    author = manifest["author"]
    interface = manifest["interface"]
    if type(author) is not dict or set(author) != author_keys:
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    if type(interface) is not dict or set(interface) != interface_keys:
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    capabilities = interface["capabilities"]
    if (
        manifest["name"] != PLUGIN_NAME
        or manifest["version"] != CANDIDATE_PLUGIN_VERSION
        or manifest["skills"] != "./skills/"
        or author["name"] != "Mastermind-X"
        or interface["displayName"] != PLUGIN_DISPLAY_NAME
        or type(capabilities) is not list
        or capabilities != ["Read"]
    ):
        raise ResearchGenerationError("PLUGIN_IDENTITY_MISMATCH")
    for field in (
        manifest["description"],
        interface["shortDescription"],
        interface["longDescription"],
        interface["developerName"],
        interface["category"],
    ):
        _string(field, maximum=512)

    projected = dict(manifest)
    projected["apps"] = "./.app.json"
    return canonical_json(projected) + b"\n"

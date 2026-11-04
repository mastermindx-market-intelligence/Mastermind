"""Deterministic BSC-U1 plugin/app binding and staging contracts.

The core compiler consumes only caller-supplied, already-approved facts. It
performs no network, browser, OAuth, MCP, Executive OS, Agent OS, workspace, or
registry discovery. The generated ``.app.json`` follows OpenAI's documented
existing-app reference shape. Mastermind validation metadata is bound separately
by the redacted v2 receipt. Neither file creates an app or grants permissions;
workspace-specific identifiers must remain outside protected plugin source.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

TEMPLATE_SCHEMA = "mastermind.plugin_app_bindings_template.v1"
REQUEST_SCHEMA = "mastermind.business_sol_installation_request.v1"
BINDING_SCHEMA = "mastermind.plugin_app_bindings.v1"
PREFLIGHT_SCHEMA = "mastermind.business_sol_installation_preflight.v1"
PUBLIC_RECEIPT_SCHEMA = "mastermind.business_sol_installation_receipt.v2"
STAGE_RECEIPT_SCHEMA = "mastermind.business_sol_installation_stage_receipt.v1"
READBACK_RECEIPT_SCHEMA = "mastermind.business_sol_installation_readback.v1"
ROLLBACK_MANIFEST_SCHEMA = "mastermind.business_sol_installation_rollback.v1"
ROLLBACK_RECEIPT_SCHEMA = "mastermind.business_sol_installation_rollback_receipt.v1"

PLUGIN_NAME = "mastermind-sol"
PLUGIN_DISPLAY_NAME = "Mastermind Sol"
PLUGIN_VERSION = "0.1.0"
PLUGIN_SCOPE = "WORKSPACE"
PLUGIN_STATUS = "ENABLED"
PLUGIN_INSTALLATION_POLICY = "INSTALLED_BY_DEFAULT"
GENERATION = 1
GENERATED_FILE = ".app.json"
GENERATED_BY_WAVE = "BSC-U1"
FILE_MODE = 0o600

STEWARD_TOOLS = (
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
)
EXECUTIVE_TOOLS = (
    "executive_state",
    "executive_inbox",
    "executive_job",
    "ceo_intent_status",
    "submit_ceo_intent",
)

REQUIRED_BINDINGS = ("mastermind-steward", "mastermind-executive")

EXPECTED_CONTRACTS: dict[str, dict[str, object]] = {
    "mastermind-steward": {
        "contract_owner": "integrations/mastermind_secretary_mcp/schemas.py",
        "display_name": "Mastermind Steward",
        "server_name": "mastermind-steward",
        "server_version": "2.0.0",
        "tool_names": STEWARD_TOOLS,
        "tool_contract_digest": (
            "cde13b7d678427a230cfe40159be1d7aa0807df00324995a40d89b2b79c12047"
        ),
    },
    "mastermind-executive": {
        "contract_owner": "integrations/executive_mcp/schemas.py",
        "display_name": "Mastermind Executive",
        "server_name": "mastermind-executive",
        "server_version": "1.0.0",
        "tool_names": EXECUTIVE_TOOLS,
        "tool_contract_digest": (
            "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
        ),
    },
}

ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "SECRET_SHAPED_INPUT",
        "TEMPLATE_MISMATCH",
        "PLUGIN_IDENTITY_MISMATCH",
        "PLUGIN_GENERATION_MISMATCH",
        "PLUGIN_SOURCE_MISMATCH",
        "WORKSPACE_MISMATCH",
        "APP_IDENTITY_MISMATCH",
        "APP_CONTRACT_MISMATCH",
        "DUPLICATE_BINDING",
        "DUPLICATE_APP_ID",
        "UNEXPECTED_BINDING",
        "PREFLIGHT_HELD",
        "OUTPUT_PATH_REFUSED",
        "OUTPUT_SYMLINK_REFUSED",
        "PREIMAGE_CONFLICT",
        "TEMPORARY_PATH_CONFLICT",
        "STAGE_EFFECT_UNKNOWN",
        "READBACK_MISMATCH",
        "ROLLBACK_EFFECT_UNKNOWN",
        "INTERNAL_ERROR",
    }
)

_SHA40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_TOKEN_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{0,95}\Z")
_PLUGIN_ID_RE = re.compile(r"\APlugin_[0-9A-Fa-f]{32}\Z")
# Generation one intentionally binds only the two commissioned custom apps.
# A directory plugin ID is not an app ID, even if its approved digest matches.
_APP_ID_RE = re.compile(r"\Aasdk_app_[0-9a-f]{32}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PRIVATE_PATH_RE = re.compile(r"(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Za-z]:\\)")
_SECRET_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:xox[abprs]-|xapp-|ghp_|github_pat_|sk-(?:proj-)?|sk-ant-|"
    r"sb_secret_|sb_publishable_|sbp_|Bearer\s+|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)

_TEMPLATE_KEYS = frozenset(
    {"schema", "plugin", "plugin_version", "generated_file", "generated_by_wave", "bindings"}
)
_TEMPLATE_BINDING_KEYS = frozenset(
    {"logical_name", "required", "contract_owner", "app_id"}
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
        "apps",
    }
)
_PLUGIN_KEYS = frozenset(
    {
        "name",
        "version",
        "registry_id",
        "approved_registry_id_digest",
        "display_name",
        "scope",
        "status",
        "installation_policy",
        "scanned_generation",
        "approved_scanned_generation",
        "installed",
    }
)
_APP_KEYS = frozenset(
    {
        "logical_name",
        "app_id",
        "approved_app_id_digest",
        "display_name",
        "workspace_digest",
        "scope",
        "publication_state",
        "app_generation",
        "approved_app_generation",
        "server_name",
        "server_version",
        "resource_digest",
        "approved_resource_digest",
        "oauth_policy_digest",
        "approved_oauth_policy_digest",
        "tool_names",
        "tool_contract_digest",
        "status",
        "availability",
        "installed",
        "connected",
    }
)


class InstallationContractError(ValueError):
    """One fixed, payload-free BSC-U1 refusal."""

    def __init__(self, code: str) -> None:
        safe_code = code if code in ERROR_CODES else "INTERNAL_ERROR"
        super().__init__(safe_code)
        self.code = safe_code


@dataclasses.dataclass(frozen=True, order=True)
class PreflightIssue:
    code: str
    logical_name: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "logical_name": self.logical_name}


@dataclasses.dataclass(frozen=True)
class Compilation:
    document: dict[str, object]
    content: bytes
    binding_digest: str
    public_receipt: dict[str, object]


@dataclasses.dataclass(frozen=True)
class StageResult:
    compilation: Compilation
    target_path: Path
    target_path_digest: str
    prior_bytes: bytes | None
    prior_mode: int | None
    stage_receipt: dict[str, object]
    rollback_manifest: dict[str, object]


def canonical_json(value: object) -> bytes:
    """Return the canonical ASCII JSON encoding used by this contract."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _exact_dict(value: object, expected_keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected_keys:
        raise InstallationContractError("INVALID_INPUT")
    return value


def _exact_list(value: object) -> list[Any]:
    if type(value) is not list:
        raise InstallationContractError("INVALID_INPUT")
    return value


def _string(value: object, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _CONTROL_RE.search(value)
    ):
        raise InstallationContractError("INVALID_INPUT")
    return value


def _token(value: object) -> str:
    text = _string(value, maximum=96)
    if _TOKEN_RE.fullmatch(text) is None:
        raise InstallationContractError("INVALID_INPUT")
    return text


def _digest(value: object) -> str:
    text = _string(value, maximum=64)
    if _DIGEST_RE.fullmatch(text) is None:
        raise InstallationContractError("INVALID_INPUT")
    return text


def _sha40(value: object) -> str:
    text = _string(value, maximum=40)
    if _SHA40_RE.fullmatch(text) is None:
        raise InstallationContractError("INVALID_INPUT")
    return text


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise InstallationContractError("INVALID_INPUT")
    return value


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
            raise InstallationContractError("SECRET_SHAPED_INPUT")
        return
    if value is None or type(value) in {bool, int}:
        return
    raise InstallationContractError("INVALID_INPUT")


def validate_template(template: object) -> tuple[str, ...]:
    """Validate the exact protected generation-one symbolic template."""

    value = _exact_dict(template, _TEMPLATE_KEYS)
    if (
        value["schema"] != TEMPLATE_SCHEMA
        or value["plugin"] != PLUGIN_NAME
        or value["plugin_version"] != PLUGIN_VERSION
        or value["generated_file"] != GENERATED_FILE
        or value["generated_by_wave"] != GENERATED_BY_WAVE
    ):
        raise InstallationContractError("TEMPLATE_MISMATCH")

    rows = _exact_list(value["bindings"])
    if len(rows) != len(EXPECTED_CONTRACTS):
        raise InstallationContractError("TEMPLATE_MISMATCH")

    seen: set[str] = set()
    order: list[str] = []
    for raw_row in rows:
        row = _exact_dict(raw_row, _TEMPLATE_BINDING_KEYS)
        logical_name = _string(row["logical_name"], maximum=64)
        if logical_name in seen:
            raise InstallationContractError("TEMPLATE_MISMATCH")
        contract = EXPECTED_CONTRACTS.get(logical_name)
        if contract is None:
            raise InstallationContractError("TEMPLATE_MISMATCH")
        if (
            row["required"] is not True
            or row["contract_owner"] != contract["contract_owner"]
            or row["app_id"] is not None
        ):
            raise InstallationContractError("TEMPLATE_MISMATCH")
        seen.add(logical_name)
        order.append(logical_name)

    if seen != set(EXPECTED_CONTRACTS) or tuple(order) != REQUIRED_BINDINGS:
        raise InstallationContractError("TEMPLATE_MISMATCH")
    return REQUIRED_BINDINGS


def _normalize_plugin(raw: object) -> dict[str, object]:
    plugin = _exact_dict(raw, _PLUGIN_KEYS)
    registry_id = _string(plugin["registry_id"], maximum=64)
    if _PLUGIN_ID_RE.fullmatch(registry_id) is None:
        raise InstallationContractError("PLUGIN_IDENTITY_MISMATCH")
    approved_registry_digest = _digest(plugin["approved_registry_id_digest"])
    if _sha256_text(registry_id) != approved_registry_digest:
        raise InstallationContractError("PLUGIN_IDENTITY_MISMATCH")
    scanned_generation = _token(plugin["scanned_generation"])
    approved_scanned_generation = _token(plugin["approved_scanned_generation"])
    if scanned_generation != approved_scanned_generation:
        raise InstallationContractError("PLUGIN_GENERATION_MISMATCH")
    if (
        plugin["name"] != PLUGIN_NAME
        or plugin["version"] != PLUGIN_VERSION
        or plugin["display_name"] != PLUGIN_DISPLAY_NAME
        or plugin["scope"] != PLUGIN_SCOPE
        or plugin["status"] != PLUGIN_STATUS
        or plugin["installation_policy"] != PLUGIN_INSTALLATION_POLICY
    ):
        raise InstallationContractError("PLUGIN_IDENTITY_MISMATCH")
    return {
        "name": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "registry_id": registry_id,
        "registry_id_digest": approved_registry_digest,
        "display_name": PLUGIN_DISPLAY_NAME,
        "scope": PLUGIN_SCOPE,
        "status": PLUGIN_STATUS,
        "installation_policy": PLUGIN_INSTALLATION_POLICY,
        "scanned_generation": scanned_generation,
        "installed": _bool(plugin["installed"]),
    }


def _normalize_app(
    raw: object,
    *,
    workspace_digest: str,
) -> tuple[dict[str, object], list[PreflightIssue]]:
    app = _exact_dict(raw, _APP_KEYS)
    logical_name = _string(app["logical_name"], maximum=64)
    contract = EXPECTED_CONTRACTS.get(logical_name)
    if contract is None:
        raise InstallationContractError("UNEXPECTED_BINDING")
    if app["workspace_digest"] != workspace_digest:
        raise InstallationContractError("WORKSPACE_MISMATCH")
    if app["scope"] != PLUGIN_SCOPE:
        raise InstallationContractError("APP_IDENTITY_MISMATCH")

    app_id_raw = app["app_id"]
    approved_app_id_digest = app["approved_app_id_digest"]
    issues: list[PreflightIssue] = []
    if app_id_raw is None:
        if approved_app_id_digest is not None:
            raise InstallationContractError("APP_IDENTITY_MISMATCH")
        app_id: str | None = None
        app_id_digest: str | None = None
        issues.append(PreflightIssue("APP_ID_MISSING", logical_name))
    else:
        app_id = _string(app_id_raw, maximum=80)
        if _APP_ID_RE.fullmatch(app_id) is None:
            raise InstallationContractError("APP_IDENTITY_MISMATCH")
        app_id_digest = _digest(approved_app_id_digest)
        if _sha256_text(app_id) != app_id_digest:
            raise InstallationContractError("APP_IDENTITY_MISMATCH")

    app_generation = _token(app["app_generation"])
    approved_generation = _token(app["approved_app_generation"])
    if app_generation != approved_generation:
        raise InstallationContractError("APP_IDENTITY_MISMATCH")

    resource_digest = _digest(app["resource_digest"])
    approved_resource_digest = _digest(app["approved_resource_digest"])
    oauth_policy_digest = _digest(app["oauth_policy_digest"])
    approved_oauth_policy_digest = _digest(app["approved_oauth_policy_digest"])
    tool_contract_digest = _digest(app["tool_contract_digest"])
    tool_names = tuple(_string(item, maximum=64) for item in _exact_list(app["tool_names"]))

    if (
        app["display_name"] != contract["display_name"]
        or app["server_name"] != contract["server_name"]
        or app["server_version"] != contract["server_version"]
        or tool_names != contract["tool_names"]
        or tool_contract_digest != contract["tool_contract_digest"]
        or resource_digest != approved_resource_digest
        or oauth_policy_digest != approved_oauth_policy_digest
    ):
        raise InstallationContractError("APP_CONTRACT_MISMATCH")

    publication_state = _string(app["publication_state"], maximum=32)
    status = _string(app["status"], maximum=32)
    availability = _string(app["availability"], maximum=32)
    if publication_state != "PUBLISHED":
        issues.append(PreflightIssue("APP_NOT_PUBLISHED", logical_name))
    if status != "ENABLED":
        issues.append(PreflightIssue("APP_DISABLED", logical_name))
    if availability != "AVAILABLE":
        issues.append(PreflightIssue("APP_UNAVAILABLE", logical_name))

    return (
        {
            "logical_name": logical_name,
            "app_id": app_id,
            "app_id_digest": app_id_digest,
            "display_name": contract["display_name"],
            "workspace_digest": workspace_digest,
            "scope": PLUGIN_SCOPE,
            "publication_state": publication_state,
            "app_generation": app_generation,
            "server_name": contract["server_name"],
            "server_version": contract["server_version"],
            "resource_digest": resource_digest,
            "oauth_policy_digest": oauth_policy_digest,
            "tool_names": list(tool_names),
            "tool_contract_digest": tool_contract_digest,
            "status": status,
            "availability": availability,
            "installed": _bool(app["installed"]),
            "connected": _bool(app["connected"]),
        },
        issues,
    )


def _normalize(
    template: object,
    request: object,
) -> tuple[tuple[str, ...], dict[str, object], list[PreflightIssue], str]:
    template_order = validate_template(template)
    template_digest = sha256_bytes(canonical_json(template))
    _scan_for_secrets(request)
    value = _exact_dict(request, _REQUEST_KEYS)
    if value["schema"] != REQUEST_SCHEMA:
        raise InstallationContractError("INVALID_INPUT")
    if type(value["generation"]) is not int or value["generation"] != GENERATION:
        raise InstallationContractError("INVALID_INPUT")

    source_commit = _sha40(value["source_commit"])
    observed_source_commit = _sha40(value["observed_source_commit"])
    package_digest = _digest(value["plugin_package_digest"])
    observed_package_digest = _digest(value["observed_plugin_package_digest"])
    if source_commit != observed_source_commit or package_digest != observed_package_digest:
        raise InstallationContractError("PLUGIN_SOURCE_MISMATCH")

    workspace_digest = _digest(value["workspace_digest"])
    workspace_role = _string(value["workspace_role"], maximum=16)
    if workspace_role not in {"ADMIN", "OWNER"}:
        raise InstallationContractError("WORKSPACE_MISMATCH")
    plugin = _normalize_plugin(value["plugin"])

    apps_raw = _exact_list(value["apps"])
    if len(apps_raw) > len(EXPECTED_CONTRACTS):
        raise InstallationContractError("UNEXPECTED_BINDING")
    apps: dict[str, dict[str, object]] = {}
    app_ids: set[str] = set()
    issues: list[PreflightIssue] = []
    for raw_app in apps_raw:
        normalized, app_issues = _normalize_app(raw_app, workspace_digest=workspace_digest)
        logical_name = str(normalized["logical_name"])
        if logical_name in apps:
            raise InstallationContractError("DUPLICATE_BINDING")
        app_id = normalized["app_id"]
        if isinstance(app_id, str):
            if app_id in app_ids:
                raise InstallationContractError("DUPLICATE_APP_ID")
            app_ids.add(app_id)
        apps[logical_name] = normalized
        issues.extend(app_issues)

    for logical_name in template_order:
        if logical_name not in apps:
            issues.append(PreflightIssue("REQUIRED_BINDING_MISSING", logical_name))

    normalized_request: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "generation": GENERATION,
        "source_commit": source_commit,
        "plugin_package_digest": package_digest,
        "workspace_digest": workspace_digest,
        "workspace_role": workspace_role,
        "plugin": plugin,
        "apps": apps,
    }
    return template_order, normalized_request, sorted(set(issues)), template_digest


def preflight_installation(template: object, request: object) -> dict[str, object]:
    """Validate approved facts and return a deterministic, non-writing preflight."""

    order, normalized, issues, template_digest = _normalize(template, request)
    plugin = normalized["plugin"]
    assert isinstance(plugin, dict)
    status = "PREFLIGHT_HELD" if issues else "READY_TO_COMPILE"
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": status,
        "generation": GENERATION,
        "source_commit": normalized["source_commit"],
        "plugin_package_digest": normalized["plugin_package_digest"],
        "workspace_digest": normalized["workspace_digest"],
        "template_digest": template_digest,
        "plugin_registry_id_digest": plugin["registry_id_digest"],
        "required_bindings": list(order),
        "issues": [issue.as_dict() for issue in issues],
        "binding_document_digest": None,
        "workspace_effect_applied": False,
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }


def compile_installation_bindings(template: object, request: object) -> Compilation:
    """Compile native app references and a separate metadata digest after preflight."""

    order, normalized, issues, template_digest = _normalize(template, request)
    if issues:
        raise InstallationContractError("PREFLIGHT_HELD")
    plugin = normalized["plugin"]
    apps = normalized["apps"]
    assert isinstance(plugin, dict)
    assert isinstance(apps, dict)

    binding_rows: list[dict[str, object]] = []
    app_identity_digests: dict[str, str] = {}
    installed_observations: dict[str, bool] = {}
    connected_observations: dict[str, bool] = {}
    for logical_name in order:
        app = apps[logical_name]
        assert isinstance(app, dict)
        app_id = app["app_id"]
        app_id_digest = app["app_id_digest"]
        if not isinstance(app_id, str) or not isinstance(app_id_digest, str):
            raise InstallationContractError("PREFLIGHT_HELD")
        binding_rows.append(
            {
                "logical_name": logical_name,
                "app_id": app_id,
                "app_generation": app["app_generation"],
                "display_name": app["display_name"],
                "scope": app["scope"],
                "server_name": app["server_name"],
                "server_version": app["server_version"],
                "resource_digest": app["resource_digest"],
                "oauth_policy_digest": app["oauth_policy_digest"],
                "tool_names": app["tool_names"],
                "tool_contract_digest": app["tool_contract_digest"],
            }
        )
        app_identity_digests[logical_name] = app_id_digest
        installed_observations[logical_name] = bool(app["installed"])
        connected_observations[logical_name] = bool(app["connected"])

    installation_plan: dict[str, object] = {
        "schema": BINDING_SCHEMA,
        "generation": GENERATION,
        "source": {
            "commit": normalized["source_commit"],
            "plugin_package_digest": normalized["plugin_package_digest"],
        },
        "workspace_digest": normalized["workspace_digest"],
        "plugin": {
            "name": PLUGIN_NAME,
            "version": PLUGIN_VERSION,
            "registry_id": plugin["registry_id"],
            "scanned_generation": plugin["scanned_generation"],
        },
        "bindings": binding_rows,
    }
    # Native plugin references contain app IDs and required bits only. Do not
    # smuggle our private plan/registry/source metadata into the platform file.
    document: dict[str, object] = {
        "apps": {
            row["logical_name"]: {"id": row["app_id"], "required": True}
            for row in binding_rows
        }
    }
    content = canonical_json(document) + b"\n"
    binding_digest = sha256_bytes(content)
    public_receipt: dict[str, object] = {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "status": "READY_TO_STAGE",
        "generation": GENERATION,
        "source_commit": normalized["source_commit"],
        "plugin_package_digest": normalized["plugin_package_digest"],
        "workspace_digest": normalized["workspace_digest"],
        "template_digest": template_digest,
        "plugin_registry_id_digest": plugin["registry_id_digest"],
        "installation_plan_digest": sha256_bytes(canonical_json(installation_plan)),
        "binding_document_digest": binding_digest,
        "binding_count": len(binding_rows),
        "logical_bindings": list(order),
        "app_identity_digests": app_identity_digests,
        "plugin_installed_observed": bool(plugin["installed"]),
        "app_installed_observations": installed_observations,
        "app_connected_observations": connected_observations,
        "generated_file": GENERATED_FILE,
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


def _absolute_path(value: str | Path) -> Path:
    if isinstance(value, Path):
        path = value
    elif type(value) is str:
        path = Path(value)
    else:
        raise InstallationContractError("OUTPUT_PATH_REFUSED")
    text = str(path)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or not text
        or _CONTROL_RE.search(text)
    ):
        raise InstallationContractError("OUTPUT_PATH_REFUSED")
    return path


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise InstallationContractError("OUTPUT_PATH_REFUSED") from exc
        if stat.S_ISLNK(mode):
            raise InstallationContractError("OUTPUT_SYMLINK_REFUSED")


def _validated_roots(
    output_root: str | Path,
    source_root: str | Path,
    *,
    create_output: bool,
) -> tuple[Path, Path, Path]:
    output = _absolute_path(output_root)
    source = _absolute_path(source_root)
    try:
        if not source.exists() or not source.is_dir() or source.is_symlink():
            raise InstallationContractError("OUTPUT_PATH_REFUSED")
        _reject_symlink_components(source)
        _reject_symlink_components(output)
        # Refuse source-tree overlap before mkdir can modify protected source.
        # Keep the post-creation strict check below as a separate readback fence.
        resolved_source = source.resolve(strict=True)
        prospective_output = output.resolve(strict=False)
        if (
            prospective_output == resolved_source
            or resolved_source in prospective_output.parents
            or prospective_output in resolved_source.parents
        ):
            raise InstallationContractError("OUTPUT_PATH_REFUSED")
        if create_output:
            output.mkdir(parents=True, exist_ok=True)
            _reject_symlink_components(output)
        if not output.exists() or not output.is_dir() or output.is_symlink():
            raise InstallationContractError("OUTPUT_PATH_REFUSED")

        resolved_source = source.resolve(strict=True)
        resolved_output = output.resolve(strict=True)
        if (
            resolved_output == resolved_source
            or resolved_source in resolved_output.parents
            or resolved_output in resolved_source.parents
        ):
            raise InstallationContractError("OUTPUT_PATH_REFUSED")
        target = output / GENERATED_FILE
        if target.is_symlink():
            raise InstallationContractError("OUTPUT_SYMLINK_REFUSED")
        return output, source, target
    except InstallationContractError:
        raise
    except OSError as exc:
        raise InstallationContractError("OUTPUT_PATH_REFUSED") from exc


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_temp(path: Path, content: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(content)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("zero progress")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if path.read_bytes() != content or stat.S_IMODE(path.stat().st_mode) != mode:
        raise InstallationContractError("READBACK_MISMATCH")


def _preimage(
    target: Path,
    expected_preimage_digest: str,
) -> tuple[bytes | None, int | None, str | None]:
    if expected_preimage_digest != "ABSENT":
        expected_preimage_digest = _digest(expected_preimage_digest)
    try:
        if target.exists():
            if not target.is_file() or target.is_symlink():
                raise InstallationContractError("OUTPUT_SYMLINK_REFUSED")
            prior_bytes = target.read_bytes()
            prior_digest = sha256_bytes(prior_bytes)
            prior_mode = stat.S_IMODE(target.stat().st_mode)
            if expected_preimage_digest == "ABSENT" or prior_digest != expected_preimage_digest:
                raise InstallationContractError("PREIMAGE_CONFLICT")
            return prior_bytes, prior_mode, prior_digest
        if expected_preimage_digest != "ABSENT":
            raise InstallationContractError("PREIMAGE_CONFLICT")
        return None, None, None
    except InstallationContractError:
        raise
    except OSError as exc:
        raise InstallationContractError("OUTPUT_PATH_REFUSED") from exc


def stage_compilation(
    compilation: Compilation,
    *,
    output_root: str | Path,
    source_root: str | Path,
    expected_preimage_digest: str,
) -> StageResult:
    """Atomically stage a compiled private binding outside the source tree."""

    if not isinstance(compilation, Compilation):
        raise InstallationContractError("INVALID_INPUT")
    output, _source, target = _validated_roots(
        output_root,
        source_root,
        create_output=True,
    )
    prior_bytes, prior_mode, prior_digest = _preimage(target, expected_preimage_digest)
    temporary = output / f"{GENERATED_FILE}.tmp"
    try:
        if temporary.exists() or temporary.is_symlink():
            raise InstallationContractError("TEMPORARY_PATH_CONFLICT")
    except InstallationContractError:
        raise
    except OSError as exc:
        raise InstallationContractError("TEMPORARY_PATH_CONFLICT") from exc

    try:
        _write_temp(temporary, compilation.content, FILE_MODE)
    except InstallationContractError:
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from None
        raise
    except Exception as exc:
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
            if temporary.exists() or temporary.is_symlink():
                raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from exc
        except InstallationContractError:
            raise
        except OSError as cleanup_exc:
            raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from cleanup_exc
        raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from exc

    try:
        os.replace(temporary, target)
        _fsync_directory(output)
    except Exception as exc:
        # Never repeat the rename. Reconcile only against the exact expected
        # postimage, then issue one idempotent directory fsync to establish
        # durability when the rename may already have committed.
        try:
            exact_postimage = (
                target.is_file()
                and not target.is_symlink()
                and target.read_bytes() == compilation.content
                and stat.S_IMODE(target.stat().st_mode) == FILE_MODE
            )
        except OSError as read_exc:
            raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from read_exc
        if not exact_postimage:
            raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from exc
        try:
            # If rename failed before effect while an identical preimage was
            # already present, our exact temporary file may remain. Remove only
            # that exact owned file; never repeat the target rename.
            if temporary.exists() or temporary.is_symlink():
                if (
                    temporary.is_symlink()
                    or not temporary.is_file()
                    or temporary.read_bytes() != compilation.content
                    or stat.S_IMODE(temporary.stat().st_mode) != FILE_MODE
                ):
                    raise InstallationContractError("STAGE_EFFECT_UNKNOWN")
                temporary.unlink()
            _fsync_directory(output)
        except InstallationContractError:
            raise
        except OSError as fsync_exc:
            raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from fsync_exc

    try:
        exact_postimage = (
            target.is_file()
            and not target.is_symlink()
            and target.read_bytes() == compilation.content
            and stat.S_IMODE(target.stat().st_mode) == FILE_MODE
        )
    except OSError as exc:
        raise InstallationContractError("STAGE_EFFECT_UNKNOWN") from exc
    if not exact_postimage:
        raise InstallationContractError("STAGE_EFFECT_UNKNOWN")

    target_digest = _sha256_text(str(target))
    prior_state = "PRESENT" if prior_bytes is not None else "ABSENT"
    stage_receipt = {
        "schema": STAGE_RECEIPT_SCHEMA,
        "status": "STAGED_VERIFIED",
        "binding_document_digest": compilation.binding_digest,
        "target_path_digest": target_digest,
        "mode": FILE_MODE,
        "prior_state": prior_state,
        "prior_digest": prior_digest,
        "workspace_effect_applied": False,
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }
    rollback_manifest = {
        "schema": ROLLBACK_MANIFEST_SCHEMA,
        "binding_document_digest": compilation.binding_digest,
        "target_path_digest": target_digest,
        "prior_state": prior_state,
        "prior_digest": prior_digest,
        "expected_postimage_digest": compilation.binding_digest,
        "production_acceptance_granted": False,
    }
    return StageResult(
        compilation=compilation,
        target_path=target,
        target_path_digest=target_digest,
        prior_bytes=prior_bytes,
        prior_mode=prior_mode,
        stage_receipt=stage_receipt,
        rollback_manifest=rollback_manifest,
    )


def verify_staged_compilation(
    compilation: Compilation,
    *,
    output_root: str | Path,
    source_root: str | Path,
) -> dict[str, object]:
    """Verify exact staged bytes and mode without changing the target."""

    if not isinstance(compilation, Compilation):
        raise InstallationContractError("INVALID_INPUT")
    _output, _source, target = _validated_roots(
        output_root,
        source_root,
        create_output=False,
    )
    try:
        exact_postimage = (
            target.is_file()
            and not target.is_symlink()
            and target.read_bytes() == compilation.content
            and stat.S_IMODE(target.stat().st_mode) == FILE_MODE
        )
    except OSError as exc:
        raise InstallationContractError("READBACK_MISMATCH") from exc
    if not exact_postimage:
        raise InstallationContractError("READBACK_MISMATCH")
    return {
        "schema": READBACK_RECEIPT_SCHEMA,
        "status": "READBACK_VERIFIED",
        "binding_document_digest": compilation.binding_digest,
        "target_path_digest": _sha256_text(str(target)),
        "mode": FILE_MODE,
        "workspace_effect_applied": False,
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }


def rollback_staged_compilation(stage: StageResult) -> dict[str, object]:
    """Restore the exact preimage once, reconciling a lost effect receipt."""

    if not isinstance(stage, StageResult):
        raise InstallationContractError("INVALID_INPUT")
    target = stage.target_path
    output = target.parent
    try:
        if target.is_symlink() or not target.is_file():
            raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN")
        current = target.read_bytes()
    except InstallationContractError:
        raise
    except OSError as exc:
        raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN") from exc
    if sha256_bytes(current) != stage.compilation.binding_digest:
        raise InstallationContractError("PREIMAGE_CONFLICT")

    restored_state = "PRESENT" if stage.prior_bytes is not None else "ABSENT"
    restored_digest = (
        sha256_bytes(stage.prior_bytes) if stage.prior_bytes is not None else None
    )
    temporary = output / f"{GENERATED_FILE}.rollback.tmp"

    try:
        if stage.prior_bytes is None:
            target.unlink()
            _fsync_directory(output)
        else:
            if temporary.exists() or temporary.is_symlink():
                raise InstallationContractError("TEMPORARY_PATH_CONFLICT")
            prior_mode = (
                stage.prior_mode if stage.prior_mode is not None else FILE_MODE
            )
            _write_temp(temporary, stage.prior_bytes, prior_mode)
            os.replace(temporary, target)
            _fsync_directory(output)
    except InstallationContractError:
        raise
    except Exception as exc:
        # Do not repeat unlink/rename. Reconcile the exact intended preimage,
        # clean only an exact owned rollback temp, and fsync once.
        try:
            if stage.prior_bytes is None:
                exact_preimage = not target.exists() and not target.is_symlink()
            else:
                prior_mode = (
                    stage.prior_mode if stage.prior_mode is not None else FILE_MODE
                )
                exact_preimage = (
                    target.is_file()
                    and not target.is_symlink()
                    and target.read_bytes() == stage.prior_bytes
                    and stat.S_IMODE(target.stat().st_mode) == prior_mode
                )
            if not exact_preimage:
                raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN") from exc
            if temporary.exists() or temporary.is_symlink():
                prior_mode = (
                    stage.prior_mode if stage.prior_mode is not None else FILE_MODE
                )
                if (
                    stage.prior_bytes is None
                    or temporary.is_symlink()
                    or not temporary.is_file()
                    or temporary.read_bytes() != stage.prior_bytes
                    or stat.S_IMODE(temporary.stat().st_mode) != prior_mode
                ):
                    raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN") from exc
                temporary.unlink()
            _fsync_directory(output)
        except InstallationContractError:
            raise
        except OSError as reconcile_exc:
            raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN") from reconcile_exc

    try:
        if stage.prior_bytes is None:
            exact_preimage = not target.exists() and not target.is_symlink()
        else:
            prior_mode = stage.prior_mode if stage.prior_mode is not None else FILE_MODE
            exact_preimage = (
                target.is_file()
                and not target.is_symlink()
                and target.read_bytes() == stage.prior_bytes
                and stat.S_IMODE(target.stat().st_mode) == prior_mode
            )
    except OSError as exc:
        raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN") from exc
    if not exact_preimage:
        raise InstallationContractError("ROLLBACK_EFFECT_UNKNOWN")

    return {
        "schema": ROLLBACK_RECEIPT_SCHEMA,
        "status": "ROLLBACK_VERIFIED",
        "binding_document_digest": stage.compilation.binding_digest,
        "target_path_digest": stage.target_path_digest,
        "restored_state": restored_state,
        "restored_digest": restored_digest,
        "workspace_effect_applied": False,
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }


__all__ = [
    "BINDING_SCHEMA",
    "Compilation",
    "ERROR_CODES",
    "EXECUTIVE_TOOLS",
    "FILE_MODE",
    "GENERATED_FILE",
    "GENERATION",
    "InstallationContractError",
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "PREFLIGHT_SCHEMA",
    "PUBLIC_RECEIPT_SCHEMA",
    "REQUEST_SCHEMA",
    "READBACK_RECEIPT_SCHEMA",
    "ROLLBACK_MANIFEST_SCHEMA",
    "ROLLBACK_RECEIPT_SCHEMA",
    "STAGE_RECEIPT_SCHEMA",
    "STEWARD_TOOLS",
    "StageResult",
    "TEMPLATE_SCHEMA",
    "canonical_json",
    "compile_installation_bindings",
    "preflight_installation",
    "rollback_staged_compilation",
    "sha256_bytes",
    "stage_compilation",
    "validate_template",
    "verify_staged_compilation",
]

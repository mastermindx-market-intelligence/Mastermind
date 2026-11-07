"""Revision and change inspection for the existing ModelRouter owner.

This module is not a pool registry, selector, publisher or credential loader.
ModelRouter remains the only routing validator. Physical accounts, capacity,
leases, application recipes and key rotation belong to their incumbent owners.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from control_plane.model_router import ModelRouter

SCHEMA = "mastermind.model_router_configuration.v1"
CHANGE_SCHEMA = "mastermind.model_router_configuration_change.v1"
MAX_DOCUMENT_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 262_144
MAX_ROWS = 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z")
_SECRET = re.compile(r"(?i)(?:xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,}|bearer\s)")


class ConfigurationError(ValueError):
    """Fixed non-disclosing code for an invalid or moving observation."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ConfigurationError("DUPLICATE_CONFIGURATION_KEY")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ConfigurationError("NONFINITE_CONFIGURATION_VALUE")


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


@dataclass(frozen=True)
class ConfigurationSource:
    """Host-private source read; never serialize the path or raw document."""

    path: Path = field(repr=False)
    document: dict[str, Any] = field(repr=False)
    identity: tuple[int, int, int, int, int] = field(repr=False)
    source_sha256: str

    def require_current(self) -> None:
        try:
            current = os.stat(self.path, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or _identity(current) != self.identity:
                raise ConfigurationError("CONFIGURATION_CHANGED_DURING_READ")
        except OSError:
            raise ConfigurationError("CONFIGURATION_SOURCE_UNAVAILABLE") from None


def read_configuration_source(path: Path) -> ConfigurationSource:
    """Read one resolved regular source file with size, shape and drift bounds.

    The existing owner selects and resolves the path. This helper follows no
    final symlink, reads no credentials, caches nothing and performs no writes.
    """
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_DOCUMENT_BYTES:
            raise ConfigurationError("CONFIGURATION_SOURCE_INVALID")
        chunks, size = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, MAX_DOCUMENT_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_DOCUMENT_BYTES:
                raise ConfigurationError("CONFIGURATION_SOURCE_OVER_BUDGET")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        retained = os.stat(path, follow_symlinks=False)
        if (_identity(before) != _identity(after)
                or _identity(before) != _identity(retained) or size != before.st_size):
            raise ConfigurationError("CONFIGURATION_CHANGED_DURING_READ")
        raw = b"".join(chunks)
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_nonfinite)
        if type(document) is not dict:
            raise ConfigurationError("CONFIGURATION_ROOT_INVALID")
        pending, count = [(document, 0)], 0
        while pending:
            value, depth = pending.pop()
            count += 1
            if count > 32768 or depth > 24:
                raise ConfigurationError("CONFIGURATION_SHAPE_OVER_BUDGET")
            if type(value) is dict:
                pending.extend((item, depth + 1) for item in value.values())
            elif type(value) is list:
                pending.extend((item, depth + 1) for item in value)
            elif type(value) is float and not math.isfinite(value):
                raise ConfigurationError("NONFINITE_CONFIGURATION_VALUE")
            elif type(value) is str:
                value.encode("utf-8", errors="strict")
        result = ConfigurationSource(path, document, _identity(before),
                                     hashlib.sha256(raw).hexdigest())
        result.require_current()
        return result
    except ConfigurationError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise ConfigurationError("CONFIGURATION_SOURCE_INVALID") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _token(value: Any) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None or _SECRET.search(value):
        raise ConfigurationError("NONPUBLIC_CONFIGURATION_VALUE")
    return value


def _strings(values) -> list[str]:
    if not isinstance(values, (list, tuple)) or len(values) > 64:
        raise ConfigurationError("CONFIGURATION_LIST_INVALID")
    return [_token(value) for value in values]


def _bound(document: dict[str, Any]) -> dict[str, Any]:
    if len(_canonical(document)) > MAX_OUTPUT_BYTES:
        raise ConfigurationError("CONFIGURATION_OUTPUT_OVER_BUDGET")
    return document


def describe_configuration(router: ModelRouter) -> dict[str, Any]:
    """Derive one public view from a validated owner, never from raw YAML/keys.

    Provider aliases here are logical adapter groups, NOT paid account pools.
    Runtime enablement, live capacity and serving-model facts are not inferred.
    """
    from control_plane.model_router import ModelRouter
    if type(router) is not ModelRouter:
        raise ConfigurationError("VALIDATED_ROUTER_REQUIRED")
    if len(router.providers) > 128 or len(router.model_aliases) > MAX_ROWS:
        raise ConfigurationError("CONFIGURATION_ROW_BOUND_EXCEEDED")
    providers = {
        _token(name): {
            "adapter_id": _token(value.adapter_id),
            "enabled": value.enabled,
            "autonomous_allowed": value.autonomous_allowed,
        } for name, value in sorted(router.providers.items())
    }
    models = {
        _token(name): {
            "provider_alias": _token(value.provider_alias),
            "adapter_id": _token(value.adapter_id),
            "model": _token(value.model),
            "effort": _token(value.effort),
            "cost_class": _token(value.cost_class),
            "capabilities": _strings(value.capabilities),
            "worker_eligible": value.worker_eligible,
            "execution_profile_id": _token(value.execution_profile_id),
            "execution_profile_digest": value.execution_profile_digest,
        } for name, value in sorted(router.model_aliases.items())
    }
    routes = {
        _token(kind): {
            "required_capabilities": _strings(value["required_capabilities"]),
            **{risk: [{"tier_id": _token(tier.tier_id),
                       "model_aliases": _strings(tier.model_aliases)}
                      for tier in value[risk]] for risk in ("routine", "elevated")},
        } for kind, value in sorted(router.routes.items())
    }
    facts = {
        "policy_version": _token(router.policy_version),
        "capability_policy_version": _token(router.capability_registry.policy_version),
        "capability_policy_digest": router.capability_registry.policy_digest,
        "providers": providers, "models": models, "routes": routes,
    }
    if (_HEX.fullmatch(str(facts["capability_policy_digest"])) is None
            or any(_HEX.fullmatch(str(row["execution_profile_digest"])) is None
                   for row in models.values())):
        raise ConfigurationError("CONFIGURATION_DIGEST_INVALID")
    revision = hashlib.sha256(_canonical(facts)).hexdigest()
    return _bound({
        "schema": SCHEMA, "owner": "model_router",
        "scope": "EXECUTIVE_ROUTING_POLICY", "revision": revision,
        "physical_account_pools": "NOT_JOINED",
        "live_capacity": "NOT_OBSERVED", "admission_authorized": False,
        "writes_applied": False, "credential_resolution_performed": False, **facts,
    })


def _capability_identity(path: Path):
    value = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(value.st_mode) or not 0 < value.st_size <= 2 * 1024 * 1024:
        raise ConfigurationError("CAPABILITY_POLICY_SOURCE_INVALID")
    return _identity(value)


def load_configuration(path: str | Path | None = None, *,
                       capability_policy_path: str | Path | None = None) -> dict[str, Any]:
    """Use the actual owner validator and bracket both source observations."""
    from control_plane.executive_agent_capabilities import DEFAULT_CAPABILITY_POLICY_PATH
    from control_plane.model_router import DEFAULT_POLICY_PATH, ModelRouter
    try:
        policy_path = Path(path or DEFAULT_POLICY_PATH).expanduser().resolve(strict=True)
        capability_path = Path(capability_policy_path or DEFAULT_CAPABILITY_POLICY_PATH).expanduser().resolve(strict=True)
        policy_before = read_configuration_source(policy_path)
        # Capabilities have their own larger byte/parser budget. We only retain
        # identity before and after their incumbent loader; no alternate decoder.
        cap_before = _capability_identity(capability_path)
        owner = ModelRouter.load(policy_path, capability_policy_path=capability_path)
        result = describe_configuration(owner)
        policy_before.require_current()
        if owner._configuration_source_sha256 != policy_before.source_sha256:
            raise ConfigurationError("CONFIGURATION_CHANGED_DURING_READ")
        if _capability_identity(capability_path) != cap_before:
            raise ConfigurationError("CAPABILITY_POLICY_CHANGED_DURING_READ")
        return result
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError("OWNER_CONFIGURATION_REFUSED") from None


def preview_configuration_change(current: ModelRouter, candidate: ModelRouter, *,
                                 expected_revision: str) -> dict[str, Any]:
    """Compare two owner-validated configurations; perform NO activation.

    Empty changes are idempotent. An affected alias remains bound to original
    Jobs/Attempts until their actual owner settles/drains it. This preview never
    invents proof that no operations are active and never rewrites those bindings.
    """
    old, new = describe_configuration(current), describe_configuration(candidate)
    if type(expected_revision) is not str or _HEX.fullmatch(expected_revision) is None:
        raise ConfigurationError("EXPECTED_CONFIGURATION_REVISION_REQUIRED")
    if expected_revision != old["revision"]:
        raise ConfigurationError("STALE_CONFIGURATION_REVISION")
    changes = {}
    for section in ("providers", "models", "routes"):
        before, after = old[section], new[section]
        changes[section] = {
            "added": sorted(after.keys() - before.keys()),
            "removed": sorted(before.keys() - after.keys()),
            "changed": sorted(name for name in before.keys() & after.keys()
                              if before[name] != after[name]),
        }
    affected_providers = set(changes["providers"]["removed"] + changes["providers"]["changed"])
    affected_aliases = set(changes["models"]["removed"] + changes["models"]["changed"])
    affected_aliases.update(name for name, row in old["models"].items()
                            if row["provider_alias"] in affected_providers)
    capability_change = old["capability_policy_digest"] != new["capability_policy_digest"]
    if capability_change:
        affected_aliases.update(old["models"])
    activated = sorted(name for name, row in new["models"].items()
                       if row["worker_eligible"] and (
                           name not in old["models"] or not old["models"][name]["worker_eligible"]
                           or name in affected_aliases))
    no_change = old["revision"] == new["revision"]
    requirements = []
    if not no_change:
        requirements.append("EXISTING_CONFIGURATION_PUBLISHER_CAS")
    if affected_aliases:
        requirements.append("ORIGINAL_BINDING_DRAIN_OR_REVISION_PRESERVATION")
    if activated:
        requirements.append("EXISTING_RUNTIME_CAPACITY_AND_PROFILE_QUALIFICATION")
    return _bound({
        "schema": CHANGE_SCHEMA, "owner": "model_router",
        "scope": "EXECUTIVE_ROUTING_POLICY", "status": "UNCHANGED" if no_change else "CHANGE_PREVIEW",
        "expected_revision": expected_revision, "candidate_revision": new["revision"],
        "changes": changes, "capability_policy_changed": capability_change,
        "affected_existing_aliases": sorted(affected_aliases),
        "aliases_requiring_qualification": activated,
        "requirements": requirements, "active_bindings": "NOT_OBSERVED",
        "credential_rotation": "EXISTING_ACCOUNT_OWNER_ONLY",
        "activation_authorized": False, "writes_applied": False,
        "original_operations_rebound": False,
    })


def preview_configuration_paths(candidate_path: str | Path, *,
                                expected_revision: str,
                                current_path: str | Path | None = None,
                                capability_policy_path: str | Path | None = None,
                                candidate_capability_path: str | Path | None = None) -> dict[str, Any]:
    """Resolve a local operator preview through both actual policy validators.

    Paths are host-admin inputs, not model-facing API arguments. All four
    selected source identities are rechecked before releasing the preview.
    No document, private key, runtime state or source file is changed.
    """
    from control_plane.executive_agent_capabilities import DEFAULT_CAPABILITY_POLICY_PATH
    from control_plane.model_router import DEFAULT_POLICY_PATH, ModelRouter
    try:
        old_path = Path(current_path or DEFAULT_POLICY_PATH).expanduser().resolve(strict=True)
        new_path = Path(candidate_path).expanduser().resolve(strict=True)
        old_cap = Path(capability_policy_path or DEFAULT_CAPABILITY_POLICY_PATH).expanduser().resolve(strict=True)
        new_cap = Path(candidate_capability_path or old_cap).expanduser().resolve(strict=True)
        old_source, new_source = (read_configuration_source(path)
                                  for path in (old_path, new_path))
        capabilities = [(path, _capability_identity(path)) for path in (old_cap, new_cap)]
        current = ModelRouter.load(old_path, capability_policy_path=old_cap)
        candidate = ModelRouter.load(new_path, capability_policy_path=new_cap)
        result = preview_configuration_change(current, candidate,
                                               expected_revision=expected_revision)
        for source, owner in ((old_source, current), (new_source, candidate)):
            source.require_current()
            if owner._configuration_source_sha256 != source.source_sha256:
                raise ConfigurationError("CONFIGURATION_CHANGED_DURING_READ")
        if any(_capability_identity(path) != before for path, before in capabilities):
            raise ConfigurationError("CAPABILITY_POLICY_CHANGED_DURING_READ")
        return result
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError("OWNER_CONFIGURATION_REFUSED") from None

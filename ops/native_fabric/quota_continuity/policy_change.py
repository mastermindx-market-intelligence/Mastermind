"""Operate the incumbent native Fabric policy owner without a parallel registry.

Inspect/preview/status are read-only; stage authors one private candidate.
Compatible publication delegates to the selected verified native publisher,
with original revision, retained rollback and admission-lock checks. Nothing
opens accounts, resolves credentials, acquires a lease, selects a generation or
makes a provider request. Critical model/pool changes remain generation-owned.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from ops.native_fabric.quota_continuity.source import fabric_policy_snapshot as owner

SCHEMA = "mastermind.native_pool_policy_change.v1"
INSPECT_SCHEMA = "mastermind.native_pool_policy_observation.v1"
MAX_POOLS = 128
MAX_EVENTS = 65536
MAX_DEPTH = 32
MAX_OUTPUT_BYTES = 65536
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_POOL_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_SECRET_VALUE = re.compile(r"(?i)(?:\bbearer\s+|xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,})")
_SECRET_FIELDS = frozenset({
    "api_key", "apikey", "authorization", "auth_token", "access_token",
    "refresh_token", "password", "secret", "credentials", "cookie", "bearer_token",
})


class PolicyChangeError(ValueError):
    """Fixed non-disclosing failure code; never include source excerpts or paths."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _checked_document(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= owner.LIMIT:
        raise PolicyChangeError("POLICY_INPUT_OVER_BUDGET_OR_INVALID")
    try:
        import yaml
        # Bound composition before the incumbent constructor sees a YAML graph.
        # Alias/merge documents require the existing owner to review them, not
        # expansion or reinterpretation by this operator-only preflight.
        depth = 0
        for index, event in enumerate(yaml.parse(raw.decode("utf-8"))):
            if index >= MAX_EVENTS or isinstance(event, yaml.events.AliasEvent):
                raise PolicyChangeError("POLICY_GRAPH_REFUSED")
            if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
                depth += 1
                if depth > MAX_DEPTH:
                    raise PolicyChangeError("POLICY_GRAPH_REFUSED")
            elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
                depth -= 1
            elif isinstance(event, yaml.events.ScalarEvent):
                if len(event.value) > 65536 or event.value == "<<":
                    raise PolicyChangeError("POLICY_GRAPH_REFUSED")
        document = owner.parse_policy(raw)
        pools = document.get("pools")
        if (type(pools) is not dict or not 1 <= len(pools) <= MAX_POOLS
                or any(type(key) is not str or _POOL_ID.fullmatch(key) is None
                       or type(value) is not dict for key, value in pools.items())):
            raise PolicyChangeError("POLICY_POOL_SHAPE_INVALID")
        # These files are public routing policy, never a credential container.
        # Known credential fields/material refuse before producing fingerprints.
        pending = [document]
        while pending:
            value = pending.pop()
            if type(value) is dict:
                if any(key.lower().replace("-", "_") in _SECRET_FIELDS for key in value):
                    raise PolicyChangeError("CREDENTIAL_MATERIAL_REFUSED")
                pending.extend(value.keys())
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)
            elif type(value) is str:
                value.encode("utf-8", errors="strict")
                if _SECRET_VALUE.search(value):
                    raise PolicyChangeError("CREDENTIAL_MATERIAL_REFUSED")
        # Reuse the actual owner's schema/critical-field semantics. No alternate
        # pool/model suitability, grant, quota or account validator lives here.
        owner.critical_fingerprint(raw)
        return document
    except PolicyChangeError:
        raise
    except Exception:
        raise PolicyChangeError("POLICY_OWNER_VALIDATION_REFUSED") from None


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@dataclass(frozen=True)
class _Source:
    path: Path = field(repr=False)
    raw: bytes = field(repr=False)
    identity: tuple[int, ...] = field(repr=False)


def _read_source(path: Path | str) -> _Source:
    descriptor = None
    try:
        selected = Path(path).expanduser().absolute()
        descriptor = os.open(selected, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= owner.LIMIT:
            raise PolicyChangeError("POLICY_SOURCE_INVALID")
        chunks, size = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, owner.LIMIT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > owner.LIMIT:
                raise PolicyChangeError("POLICY_SOURCE_OVER_BUDGET")
        expected = _identity(before)
        if (size != before.st_size or _identity(os.fstat(descriptor)) != expected
                or _identity(os.stat(selected, follow_symlinks=False)) != expected):
            raise PolicyChangeError("POLICY_SOURCE_CHANGED")
        return _Source(selected, b"".join(chunks), expected)
    except PolicyChangeError:
        raise
    except (OSError, TypeError, ValueError):
        raise PolicyChangeError("POLICY_SOURCE_UNAVAILABLE") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _require_current(source: _Source) -> None:
    current = _read_source(source.path)
    if current.identity != source.identity or current.raw != source.raw:
        raise PolicyChangeError("POLICY_SOURCE_CHANGED")


def _bound(value: dict[str, Any]) -> dict[str, Any]:
    if len(_canonical(value)) > MAX_OUTPUT_BYTES:
        raise PolicyChangeError("POLICY_PREVIEW_OVER_BUDGET")
    return value


def observe_policy(raw: bytes) -> dict[str, Any]:
    document = _checked_document(raw)
    return _bound({
        "schema": INSPECT_SCHEMA, "owner": "native_fabric_policy_snapshot",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "critical_sha256": owner.critical_fingerprint(raw),
        "configured_pool_ids": sorted(document["pools"]),
        "live_capacity": "NOT_OBSERVED", "credential_resolution_performed": False,
        "writes_applied": False, "admission_authorized": False,
    })


def preview_change(current: bytes, candidate: bytes, *, expected_source_sha256: str) -> dict[str, Any]:
    if type(expected_source_sha256) is not str or _HEX.fullmatch(expected_source_sha256) is None:
        raise PolicyChangeError("EXPECTED_SOURCE_DIGEST_INVALID")
    before, after = _checked_document(current), _checked_document(candidate)
    current_hash = hashlib.sha256(current).hexdigest()
    if current_hash != expected_source_sha256:
        raise PolicyChangeError("EXPECTED_SOURCE_REVISION_CHANGED")
    old_critical = owner.critical_fingerprint(current)
    new_critical = owner.critical_fingerprint(candidate)
    old_pools, new_pools = before["pools"], after["pools"]
    added, removed = sorted(new_pools.keys() - old_pools.keys()), sorted(old_pools.keys() - new_pools.keys())
    changed = sorted(key for key in old_pools.keys() & new_pools.keys()
                     if _canonical(old_pools[key]) != _canonical(new_pools[key]))
    routing_changed = _canonical(before["routing"]) != _canonical(after["routing"])
    critical = old_critical != new_critical
    status = ("UNCHANGED" if current == candidate else "CRITICAL_POLICY_CHANGE" if critical
              else "NONCRITICAL_POLICY_CHANGE" if _canonical(before) != _canonical(after)
              else "SOURCE_ONLY_CHANGE")
    requirements = []
    if current != candidate:
        requirements.append("INCUMBENT_PUBLISHER_SOURCE_RECHECK")
    if critical:
        requirements.extend(("REVIEWED_NATIVE_GENERATION_REQUIRED", "RETAIN_ORIGINAL_OPERATION_GENERATIONS",
                             "REVALIDATE_NEW_ADMISSIONS"))
        if added:
            requirements.append("QUALIFY_ADDED_POOLS_AND_MODELS")
        if changed:
            requirements.append("REQUALIFY_CHANGED_POOLS_AND_MODELS")
        if removed or changed or routing_changed:
            requirements.append("DRAIN_OR_RETAIN_ACTIVE_BINDINGS")
    return _bound({
        "schema": SCHEMA, "owner": "native_fabric_policy_snapshot", "status": status,
        "expected_source_sha256": current_hash,
        "candidate_source_sha256": hashlib.sha256(candidate).hexdigest(),
        "current_critical_sha256": old_critical, "candidate_critical_sha256": new_critical,
        "existing_snapshot_compatible": not critical,
        "changes": {"pools": {"added": added, "removed": removed, "changed": changed},
                    "routing_changed": routing_changed,
                    "other_policy_changed": _canonical({k:v for k,v in before.items() if k not in {"pools", "routing"}})
                        != _canonical({k:v for k,v in after.items() if k not in {"pools", "routing"}})},
        "requirements": requirements, "active_bindings": "NOT_OBSERVED",
        "account_configuration": "NOT_READ", "credential_rotation": "EXISTING_ACCOUNT_OWNER_ONLY",
        "credential_resolution_performed": False, "original_operations_rebound": False,
        "writes_applied": False, "activation_authorized": False,
    })


def observe_path(path: Path | str) -> dict[str, Any]:
    source = _read_source(path)
    result = observe_policy(source.raw)
    _require_current(source)
    return result


def preview_paths(current_path: Path | str, candidate_path: Path | str, *, expected_source_sha256: str) -> dict[str, Any]:
    current, candidate = _read_source(current_path), _read_source(candidate_path)
    result = preview_change(current.raw, candidate.raw, expected_source_sha256=expected_source_sha256)
    _require_current(current)
    _require_current(candidate)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    inspect = actions.add_parser("inspect", help="Read public routing policy only; never account files")
    inspect.add_argument("--policy", required=True, type=Path)
    preview = actions.add_parser("preview", help="Compare exact source/candidate; never apply either")
    preview.add_argument("--current-policy", required=True, type=Path)
    preview.add_argument("--candidate-policy", required=True, type=Path)
    preview.add_argument("--expected-source-sha256", required=True)
    stage = actions.add_parser("stage", help="Author a new private candidate; never modify live policy")
    stage.add_argument("--policy", required=True, type=Path)
    stage.add_argument("--edits", required=True, type=Path)
    stage.add_argument("--output", required=True, type=Path)
    stage.add_argument("--expected-source-sha256", required=True)
    verify = actions.add_parser("verify-candidate", help="Read back an original candidate after uncertain publication")
    verify.add_argument("--candidate", required=True, type=Path)
    verify.add_argument("--expected-candidate-sha256", required=True)
    for name in ("publish-compatible", "publication-status"):
        command = actions.add_parser(name, help=(
            "Delegate compatible policy publication to the selected native owner" if name == "publish-compatible"
            else "Observe original target bytes without replaying a publication"))
        command.add_argument("--stable-ext", required=True, type=Path)
        command.add_argument("--expected-native-generation", required=True)
        command.add_argument("--expected-current-sha256", required=True)
        command.add_argument("--expected-candidate-sha256", required=True)
        if name == "publish-compatible":
            command.add_argument("--candidate", required=True, type=Path)
            command.add_argument("--rollback-source", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command in {"publish-compatible", "publication-status"}:
        from ops.native_fabric.quota_continuity import policy_publication
        return policy_publication.run_cli(args)
    if args.command in {"stage", "verify-candidate"}:
        from ops.native_fabric.quota_continuity import policy_edit
        return policy_edit.run_cli(args)
    try:
        result = (observe_path(args.policy) if args.command == "inspect" else
                  preview_paths(args.current_policy, args.candidate_policy,
                                expected_source_sha256=args.expected_source_sha256))
    except PolicyChangeError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "REFUSED", "code": str(exc), "writes_applied": False}))
        return 2
    print(_canonical(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

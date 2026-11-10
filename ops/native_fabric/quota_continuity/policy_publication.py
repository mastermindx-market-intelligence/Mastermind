"""Operator delegation to the selected, verified native policy publisher.

This is not an installer, another publication authority or a live-reload loop.
Only the current immutable native generation may write its existing policy via
its existing support_bundle owner and physical admission lock. A checkout's new
source is never substituted for an older installed publisher.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from ops.native_fabric.quota_continuity import policy_change as policy
from ops.native_fabric.quota_continuity.rollout import native_generation as generation

SCHEMA = "mastermind.native_policy_publication.v1"
MAX_REPLY_BYTES = 16384
_OWNER = "ext/support_bundle.py"
_VALIDATOR = "ext/fabric_policy_snapshot.py"
_CODES = frozenset({
    "POLICY_EXPECTED_DIGEST_INVALID", "POLICY_FILE_INVALID", "POLICY_FILE_OVER_BUDGET",
    "POLICY_FILE_CHANGED", "POLICY_FILE_UNAVAILABLE", "POLICY_PATH_NOT_CANONICAL",
    "POLICY_PATH_UNAVAILABLE", "POLICY_DIRECTORY_CHANGED", "POLICY_ADMISSION_LOCK_CHANGED",
    "POLICY_STABLE_ROOT_INVALID", "POLICY_DIRECTORY_UNSAFE", "POLICY_ADMISSION_LOCK_INVALID",
    "POLICY_VALIDATOR_SOURCE_MISMATCH", "POLICY_PUBLIC_DATA_INVALID",
    "POLICY_CREDENTIAL_MATERIAL_REFUSED", "CRITICAL_CHANGE_REQUIRES_NATIVE_GENERATION",
    "POLICY_ACTIVE_BINDINGS_NOT_CLOSED", "POLICY_ARTIFACT_DIGEST_MISMATCH",
    "POLICY_EXPECTED_CURRENT_CHANGED", "POLICY_RETAINED_ARTIFACT_REQUIRED",
    "POLICY_PREIMAGE_CHANGED", "POLICY_STAGED_BYTES_CHANGED", "POLICY_POSTIMAGE_CHANGED",
    "POLICY_ARTIFACT_CHANGED_AFTER_PUBLICATION", "POLICY_PUBLICATION_PREFLIGHT_REFUSED",
    "POLICY_STATUS_UNAVAILABLE", "POLICY_PUBLICATION_UNCERTAIN", "POLICY_ROLLBACK_DIRECTORY_UNSAFE",
})


class PublicationUnavailable(ValueError):
    """A closed operator/installed-owner gap, with no new publication attempted."""


def _digest(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PublicationUnavailable("EXPECTED_DIGEST_INVALID")
    return value


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate reply key")
        value[key] = item
    return value


def _outcome(state: str, code: str, *, candidate: str, attempted: bool) -> dict[str, Any]:
    public_candidate = candidate if type(candidate) is str and re.fullmatch(r"[0-9a-f]{64}", candidate) else None
    return {"schema": SCHEMA, "state": state, "code": code,
            "candidate_sha256": public_candidate, "writes_applied": None if attempted else False,
            "retry_authorized": False, "original_target_reconciliation_required": attempted}


def _reply(raw: bytes, returncode: int, *, modifying: bool, previous: str, candidate: str) -> dict[str, Any]:
    if not 0 < len(raw) <= MAX_REPLY_BYTES:
        raise ValueError("invalid reply size")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    if type(value) is not dict or value.get("schema") != SCHEMA or value.get("retry_authorized") is not False:
        raise ValueError("invalid owner reply")
    state = value.get("state")
    if state == "REFUSED":
        if returncode != 2 or value.get("writes_applied") is not False or value.get("code") not in _CODES:
            raise ValueError("unqualified refusal")
        return {key: value[key] for key in ("schema", "state", "code", "writes_applied", "retry_authorized")}
    if state == "EFFECT_UNKNOWN":
        if (not modifying or returncode != 75 or value.get("writes_applied") is not None
                or value.get("candidate_sha256") != candidate):
            raise ValueError("unqualified uncertainty")
        return _outcome("EFFECT_UNKNOWN", "POLICY_PUBLICATION_UNCERTAIN", candidate=candidate, attempted=True)
    common = {"schema", "state", "expected_previous_sha256", "candidate_sha256",
              "observed_policy_sha256", "writes_applied", "model_activation_authorized",
              "generation_selected", "original_operations_rebound", "account_configuration",
              "credential_resolution_performed", "retry_authorized"}
    optional = {"directory_synced"} if modifying else {"original_publication_proven"}
    if (set(value) - common - optional or not common <= set(value) or returncode != 0
            or value["expected_previous_sha256"] != previous or value["candidate_sha256"] != candidate
            or value["account_configuration"] != "NOT_READ"
            or any(value[key] is not False for key in ("model_activation_authorized", "generation_selected",
                "original_operations_rebound", "credential_resolution_performed"))):
        raise ValueError("unqualified successful reply")
    if modifying:
        if state == "POLICY_PUBLISHED":
            if (value["writes_applied"] is not True or value.get("directory_synced") is not True
                    or value["observed_policy_sha256"] != candidate):
                raise ValueError("unqualified write receipt")
        elif state == "UNCHANGED":
            if value["writes_applied"] is not False or previous != candidate or value["observed_policy_sha256"] != previous:
                raise ValueError("unqualified no-op receipt")
        else:
            raise ValueError("unexpected write state")
    else:
        wanted = {"CANDIDATE_BYTES_OBSERVED": candidate, "PREVIOUS_BYTES_OBSERVED": previous,
                  "OTHER_POLICY_OBSERVED": None}
        if (state not in wanted or value["writes_applied"] is not False
                or value.get("original_publication_proven") is not False
                or value["observed_policy_sha256"] != wanted[state]):
            raise ValueError("unqualified observation")
    return value


def _qualified_owner(store: Path, expected_generation: str):
    selected = generation.current(store)
    if selected is None or selected["generation"] != expected_generation:
        raise PublicationUnavailable("NATIVE_GENERATION_CHANGED")
    root, metadata = generation.verify(store, expected_generation)
    if _OWNER not in metadata["files"] or _VALIDATOR not in metadata["files"]:
        raise PublicationUnavailable("NATIVE_POLICY_PUBLISHER_NOT_ENROLLED")
    raw = generation.regular_bytes(root / _OWNER)
    if hashlib.sha256(raw).hexdigest() != metadata["files"][_OWNER]:
        raise PublicationUnavailable("NATIVE_POLICY_PUBLISHER_CHANGED")
    declarations = [node.value.value for node in ast.parse(raw).body
                    if isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "NATIVE_POLICY_PUBLICATION_API"
                    and isinstance(node.value, ast.Constant)]
    if len(declarations) != 1 or type(declarations[0]) is not int or declarations[0] != 1:
        raise PublicationUnavailable("NATIVE_POLICY_PUBLISHER_UPGRADE_REQUIRED")
    return selected, root / _OWNER, metadata


def publish_or_observe(*, stable_ext: Path, expected_generation: str, previous: str,
                       candidate: str, candidate_path: Path | None = None,
                       rollback_source: Path | None = None) -> dict[str, Any]:
    """One qualified owner call; uncertain modification is never resent."""
    expected_generation, previous, candidate = (_digest(expected_generation), _digest(previous), _digest(candidate))
    modifying = candidate_path is not None
    attempted = False
    try:
        stable = Path(stable_ext).expanduser().absolute()
        if stable.resolve(strict=True) != stable:
            raise PublicationUnavailable("NATIVE_STABLE_PATH_NOT_CANONICAL")
        store = generation.store_path(stable, create=False)
        # An absent original lock means this is not a qualified installed
        # publication owner. Never bootstrap it from this operator action.
        if not (store / ".publication.lock").exists():
            raise PublicationUnavailable("NATIVE_PUBLICATION_OWNER_UNAVAILABLE")
        with generation.publication_lock(store):
            selected, owner_path, metadata = _qualified_owner(store, expected_generation)
            if metadata["stable_ext"] != str(stable):
                raise PublicationUnavailable("NATIVE_OWNER_BINDING_CHANGED")
            if modifying:
                if rollback_source is None:
                    raise PublicationUnavailable("RETAINED_PREIMAGE_REQUIRED")
                new_source, old_source = policy._read_source(candidate_path), policy._read_source(rollback_source)
                policy._checked_document(new_source.raw)
                policy._checked_document(old_source.raw)
                if hashlib.sha256(new_source.raw).hexdigest() != candidate or hashlib.sha256(old_source.raw).hexdigest() != previous:
                    raise PublicationUnavailable("PUBLICATION_ARTIFACT_CHANGED")
                command = [sys.executable, "-B", str(owner_path), "--policy-compatible",
                           str(new_source.path), str(stable), candidate, previous, str(old_source.path)]
            else:
                command = [sys.executable, "-B", str(owner_path), "--policy-status", str(stable), previous, candidate]
            if generation.current(store) != selected:
                raise PublicationUnavailable("NATIVE_GENERATION_CHANGED")
            environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
            environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
            attempted = modifying
            result = subprocess.run(command, capture_output=True, timeout=20, check=False, env=environment)
            value = _reply(result.stdout, result.returncode, modifying=modifying, previous=previous, candidate=candidate)
            if generation.current(store) != selected:
                raise ValueError("native owner moved during call")
            value["native_generation"] = expected_generation
            value["publisher_source_sha256"] = metadata["files"][_OWNER]
            return value
    except BaseException as exc:
        if attempted:
            return _outcome("EFFECT_UNKNOWN", "ORIGINAL_PUBLISHER_REPLY_UNQUALIFIED", candidate=candidate, attempted=True)
        if isinstance(exc, (PublicationUnavailable, KeyboardInterrupt, SystemExit)):
            raise
        raise PublicationUnavailable("ORIGINAL_PUBLISHER_UNAVAILABLE") from None


def run_cli(args) -> int:
    try:
        value = publish_or_observe(stable_ext=args.stable_ext, expected_generation=args.expected_native_generation,
            previous=args.expected_current_sha256, candidate=args.expected_candidate_sha256,
            candidate_path=args.candidate if args.command == "publish-compatible" else None,
            rollback_source=args.rollback_source if args.command == "publish-compatible" else None)
    except PublicationUnavailable as exc:
        value = _outcome("REFUSED", str(exc), candidate=args.expected_candidate_sha256, attempted=False)
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 75 if value["state"] == "EFFECT_UNKNOWN" else 2 if value["state"] == "REFUSED" else 0

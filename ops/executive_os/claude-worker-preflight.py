"""Provider-work-free Claude Worker realm/auth preflight.

This executable is the single Claude preflight family reserved by PF1 and
advanced by Operator Continuity OCR-1 V3.  It owns only non-secret binary/auth
readiness observations.  It does not perform login, execute a model turn,
select capacity, create Executive lifecycle state, or persist provider identity.

V1 intentionally permits only two provider commands:

* ``claude --version``
* ``claude auth status``

The public receipt is a closed, secret-free contract.  Provider account PII is
never copied into it.  A concrete host/principal identity is supplied by the
existing canonical owner; ``local-unbound`` is a refusal, never a host identity.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "mastermind.claude_worker_preflight.v1"
EXECUTION_CONTEXTS = frozenset({"INTERACTIVE_PRINCIPAL", "WORKER_BROKER"})
AUTH_IDENTITY_CONFIDENCE = frozenset({"SLOT_ONLY", "PROVIDER_REPORTED"})
ISOLATION_BASES = frozenset(
    {"OS_PRINCIPAL_KEYCHAIN", "NON_MACOS_PROVIDER_PATH", "UNKNOWN"}
)
AUTH_METHODS = frozenset({"claudeai", "non_native", "unknown"})
API_PROVIDERS = frozenset({"first_party", "non_native", "unknown"})
VERDICTS = frozenset(
    {
        "INTERACTIVE_AUTH_READY",
        "WORKER_CONTEXT_AUTH_READY",
        "LOGIN_REQUIRED",
        "NATIVE_AUTH_NOT_SELECTED",
        "WORKER_CONTEXT_AUTH_UNAVAILABLE",
        "EXECUTION_CONTEXT_UNPROVEN",
        "HOST_IDENTITY_SEAM_UNAVAILABLE",
        "PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE",
        "PRINCIPAL_CONTEXT_MISMATCH",
        "BINARY_UNAVAILABLE",
        "AUTH_STATUS_UNSUPPORTED",
    }
)
REASON_CODES = VERDICTS | frozenset(
    {
        "COMMAND_NOT_ALLOWED",
        "BINARY_INVALID",
        "PROVIDER_TIMEOUT",
        "PROVIDER_COMMAND_FAILED",
    }
)

_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "realm_label",
        "host_ref",
        "os_principal_ref",
        "observed_at",
        "claude_binary_sha256",
        "claude_version",
        "auth_ready",
        "auth_method",
        "api_provider",
        "auth_identity_confidence",
        "macos_credential_isolation_basis",
        "execution_context",
        "worker_id",
        "quota_class",
        "verdict",
        "reason_codes",
    }
)
_REALM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_HOST_RE = re.compile(r"^host-[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")
_PRINCIPAL_RE = re.compile(r"^principal-[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")
_WORKER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_QUOTA_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})"
)
_RAW_AUTH_ALLOWED_KEYS = frozenset(
    {
        "loggedIn",
        "authMethod",
        "apiProvider",
        "subscriptionType",
        "apiKeySource",
        # Known provider PII is explicitly tolerated as INPUT only so it can be
        # discarded.  It is never returned or persisted by this module.
        "email",
        "organization",
        "accountId",
        "organizationId",
    }
)
_PROVIDER_TIMEOUT_SECONDS = 15.0


class PreflightError(RuntimeError):
    """Bounded fail-closed preflight refusal."""


@dataclasses.dataclass(frozen=True)
class AuthObservation:
    auth_ready: bool
    auth_method: str
    api_provider: str
    reason_codes: tuple[str, ...] = ()


def _raise(code: str) -> None:
    raise PreflightError(code)


def _reject_secret_shaped(value: Any) -> None:
    if isinstance(value, str):
        if _SECRET_RE.search(value):
            _raise("SECRET_SHAPED_VALUE")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_shaped(str(key))
            _reject_secret_shaped(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_shaped(item)


def _bounded_text(value: Any, *, maximum: int = 128) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or _CONTROL_RE.search(text):
        _raise("RECEIPT_INVALID")
    _reject_secret_shaped(text)
    return text


def _require_utc(value: Any) -> str:
    text = _bounded_text(value, maximum=40)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        _raise("RECEIPT_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() != datetime.now(UTC).utcoffset():
        _raise("RECEIPT_INVALID")
    return text


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def require_canonical_identity(host_ref: str, os_principal_ref: str) -> tuple[str, str]:
    host = str(host_ref or "").strip()
    principal = str(os_principal_ref or "").strip()
    if not host or host == "local-unbound" or _HOST_RE.fullmatch(host) is None:
        _raise("HOST_IDENTITY_SEAM_UNAVAILABLE")
    if not principal or _PRINCIPAL_RE.fullmatch(principal) is None:
        _raise("PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE")
    return host, principal


def _require_binary(binary: Path) -> Path:
    raw = Path(binary)
    if not raw.is_absolute():
        _raise("BINARY_INVALID")
    try:
        info = raw.lstat()
    except OSError:
        _raise("BINARY_UNAVAILABLE")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _raise("BINARY_INVALID")
    if not os.access(raw, os.X_OK):
        _raise("BINARY_INVALID")
    return raw


def build_allowed_argv(binary: Path, operation: str) -> tuple[str, ...]:
    resolved = _require_binary(binary)
    if operation == "version":
        return (str(resolved), "--version")
    if operation == "auth_status":
        return (str(resolved), "auth", "status")
    _raise("COMMAND_NOT_ALLOWED")


def normalize_auth_status(raw: Mapping[str, Any]) -> AuthObservation:
    if not isinstance(raw, Mapping) or not set(raw).issubset(_RAW_AUTH_ALLOWED_KEYS):
        _raise("AUTH_STATUS_UNSUPPORTED")
    logged_in = raw.get("loggedIn")
    if type(logged_in) is not bool:
        _raise("AUTH_STATUS_UNSUPPORTED")

    method_raw = raw.get("authMethod")
    provider_raw = raw.get("apiProvider")
    if not logged_in:
        return AuthObservation(
            auth_ready=False,
            auth_method="unknown",
            api_provider="unknown",
            reason_codes=("LOGIN_REQUIRED",),
        )
    if not isinstance(method_raw, str) or not isinstance(provider_raw, str):
        _raise("AUTH_STATUS_UNSUPPORTED")

    method = method_raw.strip()
    provider = provider_raw.strip()
    if method == "claude.ai" and provider == "firstParty":
        return AuthObservation(
            auth_ready=True,
            auth_method="claudeai",
            api_provider="first_party",
            reason_codes=(),
        )
    return AuthObservation(
        auth_ready=False,
        auth_method="non_native",
        api_provider="non_native",
        reason_codes=("NATIVE_AUTH_NOT_SELECTED",),
    )


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    _reject_secret_shaped(value)
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        _raise("RECEIPT_INVALID")
    result = dict(value)
    if result["schema"] != SCHEMA:
        _raise("RECEIPT_INVALID")

    realm = _bounded_text(result["realm_label"], maximum=64)
    if _REALM_RE.fullmatch(realm) is None:
        _raise("RECEIPT_INVALID")
    host, principal = require_canonical_identity(
        str(result["host_ref"]), str(result["os_principal_ref"])
    )
    result["host_ref"], result["os_principal_ref"] = host, principal
    _require_utc(result["observed_at"])
    if not isinstance(result["claude_binary_sha256"], str) or _SHA256_RE.fullmatch(
        result["claude_binary_sha256"]
    ) is None:
        _raise("RECEIPT_INVALID")
    _bounded_text(result["claude_version"], maximum=128)
    if type(result["auth_ready"]) is not bool:
        _raise("RECEIPT_INVALID")
    if result["auth_method"] not in AUTH_METHODS:
        _raise("RECEIPT_INVALID")
    if result["api_provider"] not in API_PROVIDERS:
        _raise("RECEIPT_INVALID")
    if result["auth_identity_confidence"] not in AUTH_IDENTITY_CONFIDENCE:
        _raise("RECEIPT_INVALID")
    if result["macos_credential_isolation_basis"] not in ISOLATION_BASES:
        _raise("RECEIPT_INVALID")
    context = result["execution_context"]
    if context not in EXECUTION_CONTEXTS:
        _raise("RECEIPT_INVALID")
    worker_id, quota_class = result["worker_id"], result["quota_class"]
    if context == "INTERACTIVE_PRINCIPAL":
        if worker_id is not None or quota_class is not None:
            _raise("RECEIPT_INVALID")
    else:
        if (
            not isinstance(worker_id, str)
            or _WORKER_RE.fullmatch(worker_id) is None
            or not isinstance(quota_class, str)
            or _QUOTA_RE.fullmatch(quota_class) is None
        ):
            _raise("RECEIPT_INVALID")
    if result["verdict"] not in VERDICTS:
        _raise("RECEIPT_INVALID")
    reasons = result["reason_codes"]
    if (
        not isinstance(reasons, list)
        or len(reasons) > 8
        or len(reasons) != len(set(reasons))
        or any(not isinstance(item, str) or item not in REASON_CODES for item in reasons)
    ):
        _raise("RECEIPT_INVALID")
    if result["auth_ready"]:
        if result["auth_method"] != "claudeai" or result["api_provider"] != "first_party":
            _raise("RECEIPT_INVALID")
        expected = (
            "INTERACTIVE_AUTH_READY"
            if context == "INTERACTIVE_PRINCIPAL"
            else "WORKER_CONTEXT_AUTH_READY"
        )
        if result["verdict"] != expected or reasons:
            _raise("RECEIPT_INVALID")
    return result


def _run(argv: tuple[str, ...], *, timeout_seconds: float = _PROVIDER_TIMEOUT_SECONDS) -> str:
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        _raise("PROVIDER_TIMEOUT")
    if completed.returncode != 0:
        _raise("PROVIDER_COMMAND_FAILED")
    return completed.stdout


def observe_binary(binary: Path) -> tuple[str, str]:
    resolved = _require_binary(binary)
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    version = _run(build_allowed_argv(resolved, "version")).strip()
    if not version or len(version) > 128 or _CONTROL_RE.search(version):
        _raise("BINARY_INVALID")
    _reject_secret_shaped(version)
    return digest, version


def observe_auth(binary: Path) -> AuthObservation:
    raw_text = _run(build_allowed_argv(binary, "auth_status"))
    try:
        parsed = json.loads(raw_text)
    except (TypeError, ValueError):
        _raise("AUTH_STATUS_UNSUPPORTED")
    if not isinstance(parsed, dict):
        _raise("AUTH_STATUS_UNSUPPORTED")
    return normalize_auth_status(parsed)


def build_ready_receipt(
    *,
    realm_label: str,
    host_ref: str,
    os_principal_ref: str,
    execution_context: str,
    binary_sha256: str,
    version: str,
    auth: AuthObservation,
    worker_id: str | None = None,
    quota_class: str | None = None,
    isolation_basis: str = "OS_PRINCIPAL_KEYCHAIN",
    observed_at: str | None = None,
) -> dict[str, Any]:
    if not auth.auth_ready:
        _raise(auth.reason_codes[0] if auth.reason_codes else "AUTH_STATUS_UNSUPPORTED")
    verdict = (
        "INTERACTIVE_AUTH_READY"
        if execution_context == "INTERACTIVE_PRINCIPAL"
        else "WORKER_CONTEXT_AUTH_READY"
    )
    return validate_receipt(
        {
            "schema": SCHEMA,
            "realm_label": realm_label,
            "host_ref": host_ref,
            "os_principal_ref": os_principal_ref,
            "observed_at": observed_at or now_iso(),
            "claude_binary_sha256": binary_sha256,
            "claude_version": version,
            "auth_ready": True,
            "auth_method": auth.auth_method,
            "api_provider": auth.api_provider,
            "auth_identity_confidence": "SLOT_ONLY",
            "macos_credential_isolation_basis": isolation_basis,
            "execution_context": execution_context,
            "worker_id": worker_id,
            "quota_class": quota_class,
            "verdict": verdict,
            "reason_codes": [],
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-work-free Claude Worker preflight")
    parser.add_argument("--realm-label", required=True)
    parser.add_argument("--host-ref", required=True)
    parser.add_argument("--os-principal-ref", required=True)
    parser.add_argument(
        "--execution-context",
        required=True,
        choices=sorted(EXECUTION_CONTEXTS),
    )
    parser.add_argument("--worker-id")
    parser.add_argument("--quota-class")
    parser.add_argument("--claude-binary", required=True, type=Path)
    args = parser.parse_args(argv)

    # Refuse missing canonical identity before touching the provider binary.
    require_canonical_identity(args.host_ref, args.os_principal_ref)
    digest, version = observe_binary(args.claude_binary)
    auth = observe_auth(args.claude_binary)
    receipt = build_ready_receipt(
        realm_label=args.realm_label,
        host_ref=args.host_ref,
        os_principal_ref=args.os_principal_ref,
        execution_context=args.execution_context,
        worker_id=args.worker_id,
        quota_class=args.quota_class,
        binary_sha256=digest,
        version=version,
        auth=auth,
    )
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        # Stable low-cardinality refusal only. Never echo provider stdout/stderr.
        print(json.dumps({"schema": SCHEMA, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2) from None

"""Read-only exact-model prelaunch witness for the existing Fabric router.

The installed provider/host owner must supply this witness from its authenticated,
complete model catalog. This module never queries providers, grants admission,
selects alternatives, owns a queue, or retries an existing worker. In particular,
a code-level model allowlist is NOT proof that a model is actually available.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MAX_MODELS = 256
MAX_AGE = timedelta(minutes=5)


@dataclass(frozen=True)
class ModelWitness:
    """Snapshot produced by an already-authorized exact host/provider owner."""

    provider: str
    host: str
    observed_at: datetime
    complete: bool
    models: tuple[str, ...]
    source_verified: bool
    # Existing broker lease identity, verified by the incumbent native owner.
    # Caller-supplied text does not by itself prove the lease is genuine.
    lease_id: str


@dataclass(frozen=True)
class ModelPreflight:
    eligible: bool
    code: str
    # A positive result is only MODEL_ID_LISTED, never dispatch authorization.
    # All remaining admission, budget, lease and effect checks still apply.
    dispatch_authorized: bool = False
    retry_authorized: bool = False


def _valid_identifier(value: object, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def qualify_model(
    requested_model: str,
    witness: ModelWitness | None,
    *,
    provider: str,
    host: str,
    lease_id: str,
    now: datetime,
) -> ModelPreflight:
    """Fail closed on unknown, stale, cross-host or incomplete model evidence.

    This is suitable only for a new request, after its incumbent broker has
    assigned an exact lease and BEFORE provider/task execution. The same
    native owner must verify that lease covers the selected host, account,
    provider and installed credential realm. Merely passing matching lease
    strings is not authentication and does not grant a new effect. Never
    apply this to prior RUNNING/TERMINAL/EFFECT_UNKNOWN attempts.
    """
    if not all(_valid_identifier(v, _OWNER) for v in (provider, host)):
        return ModelPreflight(False, "MODEL_PREFLIGHT_SCOPE_INVALID")
    if not _valid_identifier(requested_model, _MODEL):
        return ModelPreflight(False, "MODEL_PREFLIGHT_REQUEST_INVALID")
    if not _valid_identifier(lease_id, _OWNER):
        return ModelPreflight(False, "MODEL_PREFLIGHT_LEASE_UNBOUND")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return ModelPreflight(False, "MODEL_PREFLIGHT_CLOCK_INVALID")
    if not isinstance(witness, ModelWitness):
        return ModelPreflight(False, "MODEL_PREFLIGHT_EVIDENCE_MISSING")
    if witness.provider != provider or witness.host != host:
        return ModelPreflight(False, "MODEL_PREFLIGHT_ORIGIN_MISMATCH")
    if witness.lease_id != lease_id or not _valid_identifier(witness.lease_id, _OWNER):
        return ModelPreflight(False, "MODEL_PREFLIGHT_LEASE_MISMATCH")
    if witness.source_verified is not True or witness.complete is not True:
        return ModelPreflight(False, "MODEL_PREFLIGHT_UNQUALIFIED")
    if (not isinstance(witness.observed_at, datetime)
            or witness.observed_at.tzinfo is None
            or witness.observed_at.utcoffset() is None):
        return ModelPreflight(False, "MODEL_PREFLIGHT_CLOCK_INVALID")
    age = now.astimezone(timezone.utc) - witness.observed_at.astimezone(timezone.utc)
    if age < timedelta(0) or age > MAX_AGE:
        return ModelPreflight(False, "MODEL_PREFLIGHT_STALE")
    if (type(witness.models) is not tuple or not 0 < len(witness.models) <= MAX_MODELS
            or any(not _valid_identifier(v, _MODEL) for v in witness.models)
            or len(witness.models) != len(set(witness.models))):
        return ModelPreflight(False, "MODEL_PREFLIGHT_CATALOG_INVALID")
    if requested_model not in witness.models:
        return ModelPreflight(False, "MODEL_PREFLIGHT_MODEL_UNAVAILABLE")
    return ModelPreflight(True, "MODEL_ID_LISTED")


def qualify_grok_native_route(
    route: dict[str, str] | None,
    witness: ModelWitness | None,
    *,
    now: datetime,
    lease_id: str,
    original_state: str,
) -> ModelPreflight:
    """Adapt an incumbent native pick to the read-only model-identity guard.

    This function cannot reconcile or retry a prior native run. A real caller
    must prove NEW_UNATTEMPTED from its existing operation/ledger owner, not
    from a request argument. The selected host must *also* supply its own
    authenticated complete catalog evidence through its existing native
    owner. No caller-supplied dataclass or source_verified flag is trusted
    without that owner-bound proof. The same applies to lease_id: the
    incumbent broker/host owner must prove its current lease/account binding;
    a matching caller-supplied string is not trustworthy evidence.
    """
    if original_state != "NEW_UNATTEMPTED":
        return ModelPreflight(False, "MODEL_PREFLIGHT_EXISTING_OPERATION")
    if type(route) is not dict:
        return ModelPreflight(False, "MODEL_PREFLIGHT_ROUTE_INVALID")
    if route.get("POOL") != "grok" or route.get("MODE") != "grok":
        return ModelPreflight(False, "MODEL_PREFLIGHT_MODE_UNSUPPORTED")
    for field in ("HOST", "MODEL"):
        if not _valid_identifier(route.get(field), _OWNER if field == "HOST" else _MODEL):
            return ModelPreflight(False, "MODEL_PREFLIGHT_ROUTE_INVALID")
    return qualify_model(
        route["MODEL"], witness, provider="grok", host=route["HOST"],
        lease_id=lease_id, now=now
    )


# Grok Build's documented "grok models" display is an ACP model-list
# observation, not a provider-call/authorization proof. See
# https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/src/models.rs
_GROK_LOGIN = re.compile(r"You are logged in with [A-Za-z0-9][A-Za-z0-9.:-]{0,127}\.\Z")
_GROK_MODEL_CREDENTIAL = re.compile(
    r"Model '([A-Za-z0-9][A-Za-z0-9._:-]{0,95})' is using its own API key\.\Z"
)


@dataclass(frozen=True)
class ParsedGrokCatalog:
    models: tuple[str, ...]
    default_model: str
    auth_banner: str
    # This parse cannot certify executable, credentials, host, account,
    # exit code, complete capture, timing, or launch permission.


def parse_grok_models_output(output: bytes) -> ParsedGrokCatalog:
    """Parse only a complete documented, bounded CLI model-list display.

    An original trusted host owner must separately attest the actual binary,
    argv, identity, credential realm, zero exit, untruncated capture, cleanup,
    and UTC observation time. Parsing a caller-supplied string is never
    source verification; do not set ModelWitness.source_verified from it.
    """
    if type(output) is not bytes or not 0 < len(output) <= 8192 or not output.endswith(b"\n"):
        raise ValueError("GROK_CATALOG_CAPTURE_INVALID")
    try:
        lines = output.decode("ascii", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("GROK_CATALOG_CAPTURE_INVALID") from exc
    if len(lines) < 6 or lines[1:2] != [""] or lines[3:4] != [""] or lines[4] != "Available models:":
        raise ValueError("GROK_CATALOG_LAYOUT_INVALID")
    banner = lines[0]
    if banner in ("You are using XAI_API_KEY.", "You are authenticated via deployment key."):
        auth = "API_KEY" if banner.startswith("You are using") else "DEPLOYMENT_KEY"
    elif _GROK_LOGIN.fullmatch(banner):
        auth = "LOGIN"
    elif _GROK_MODEL_CREDENTIAL.fullmatch(banner):
        auth = "MODEL_KEY"
    else:
        raise ValueError("GROK_CATALOG_AUTH_UNVERIFIED")
    if not lines[2].startswith("Default model: "):
        raise ValueError("GROK_CATALOG_DEFAULT_INVALID")
    default = lines[2][len("Default model: "):]
    if not _valid_identifier(default, _MODEL):
        raise ValueError("GROK_CATALOG_DEFAULT_INVALID")
    if not 1 <= len(lines) - 5 <= MAX_MODELS:
        raise ValueError("GROK_CATALOG_SIZE_INVALID")
    available: list[str] = []
    marked_default = 0
    for line in lines[5:]:
        if line.startswith("  * ") and line.endswith(" (default)"):
            value = line[4:-len(" (default)")]
            marked_default += 1
            if value != default:
                raise ValueError("GROK_CATALOG_MARKER_INVALID")
        elif line.startswith("  - "):
            value = line[4:]
        else:
            raise ValueError("GROK_CATALOG_ROW_INVALID")
        if not _valid_identifier(value, _MODEL) or value in available:
            raise ValueError("GROK_CATALOG_ROW_INVALID")
        available.append(value)
    if marked_default != 1 or default not in available:
        raise ValueError("GROK_CATALOG_DEFAULT_NOT_LISTED")
    return ParsedGrokCatalog(models=tuple(available), default_model=default, auth_banner=auth)

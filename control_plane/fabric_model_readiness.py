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
    now: datetime,
) -> ModelPreflight:
    """Fail closed on unknown, stale, cross-host or incomplete model evidence.

    This is suitable only at the *new-request pre-effect boundary*. Callers
    must not apply it to a prior RUNNING/TERMINAL/EFFECT_UNKNOWN Attempt to
    justify another launch. The original runtime remains authority on custody.
    """
    if not all(_valid_identifier(v, _OWNER) for v in (provider, host)):
        return ModelPreflight(False, "MODEL_PREFLIGHT_SCOPE_INVALID")
    if not _valid_identifier(requested_model, _MODEL):
        return ModelPreflight(False, "MODEL_PREFLIGHT_REQUEST_INVALID")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return ModelPreflight(False, "MODEL_PREFLIGHT_CLOCK_INVALID")
    if not isinstance(witness, ModelWitness):
        return ModelPreflight(False, "MODEL_PREFLIGHT_EVIDENCE_MISSING")
    if witness.provider != provider or witness.host != host:
        return ModelPreflight(False, "MODEL_PREFLIGHT_ORIGIN_MISMATCH")
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
    original_state: str,
) -> ModelPreflight:
    """Adapt an incumbent native pick to the read-only model-identity guard.

    This function cannot reconcile or retry a prior native run. A real caller
    must prove NEW_UNATTEMPTED from its existing operation/ledger owner, not
    from a request argument. The selected host must *also* supply its own
    authenticated complete catalog evidence through its existing native
    owner. No caller-supplied dataclass or source_verified flag is trusted
    without that owner-bound proof.
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
        route["MODEL"], witness, provider="grok", host=route["HOST"], now=now
    )

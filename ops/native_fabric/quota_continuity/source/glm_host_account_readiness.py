"""Pure GLM host/account readiness predicate: telemetry filter, no effects.

Filters incumbent broker policy candidate rows against per-host telemetry
(``document["glm_local_account_readiness"]``). Every input is caller data,
including the clock; this module never prints and never reads config, env,
files, clocks, network, credentials or installed runtime state, and never
computes capacity, picks a host or grants a lease. ``source_verified`` must
be literally True from actual incumbent bounded owned/no-follow stable-file
provenance checks already performed by the caller; it is never derived from
``document`` fields and is not authentication or custody evidence produced
here. ``config_scope`` is a mechanical schema/version label; matching it does
not prove the readiness producer exists, was adopted, or resolves the same
launch config. Key readiness is model-independent; ``candidate_model`` only
binds the caller's exact model-policy projection.
"""

import math

__all__ = ["filter_glm_host_accounts", "filter_bailian_host_accounts"]

SCHEMA = "mastermind.glm_local_account_readiness.v1"
CONFIG_SCOPE = "launcher_glm_config.v1"
STATUS_KNOWN = "known"
SUPPORTED_MODE = "glm"
SUPPORTED_MODELS = ("glm-5.3", "glm-5.3-flash")

MAX_ENTRIES = 64
MAX_NAME_LEN = 128
BAD_NAME_CHARS = "\r\n\0"
FUTURE_SLACK = 1  # timestamps may lead the passed clock by at most this many seconds
DEFAULT_MAX_AGE = 600

# Static reasons are fixed literals: they never echo account, host or any
# other worker-controlled or credential-bearing value.
REASON_OK = "ok"
REASON_MODE = "mode out of scope"
REASON_MODEL = "model out of scope"
REASON_CANDIDATE_MODEL = "candidate model mismatch"
REASON_SOURCE_UNVERIFIED = "source not verified"
REASON_CLOCK_INVALID = "clock arguments invalid"
REASON_PREFERENCE_INVALID = "preference argument invalid"
REASON_ROWS_INVALID = "candidate rows invalid"
REASON_DOCUMENT_INVALID = "telemetry document invalid"
REASON_DOCUMENT_STALE = "telemetry stale or timestamp invalid"
REASON_ENVELOPE_INVALID = "readiness envelope invalid"
REASON_ENVELOPE_STALE = "readiness observation stale"
REASON_NO_READY = "no ready accounts"
REASON_PREFERRED_UNAVAILABLE = "preferred account unavailable"


def _is_number(value):
    """Finite int/float but never bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _fresh(value, now, max_age):
    """Exact, unfloored freshness: value > 0, future slack, within max_age."""
    if not _is_number(value) or value <= 0:
        return False
    if value > now + FUTURE_SLACK:
        return False
    return now - value <= max_age


def _valid_name(name):
    """Nonempty str <= MAX_NAME_LEN without CR/LF/NUL; other characters allowed."""
    if not isinstance(name, str) or not name or len(name) > MAX_NAME_LEN:
        return False
    return not any(ch in name for ch in BAD_NAME_CHARS)


def _valid_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _exact_str(value, expected):
    """Exact string equality with no coercion; refuses None/None matches."""
    return isinstance(value, str) and value == expected


def _candidate_rows(accounts):
    """Original row objects in input order, or None when rows are malformed."""
    if not isinstance(accounts, (list, tuple)) or len(accounts) > MAX_ENTRIES:
        return None
    rows = []
    seen = set()
    for row in accounts:
        if not isinstance(row, dict):
            return None
        name = row.get("name")
        if not _valid_name(name) or name in seen:
            return None
        seen.add(name)
        rows.append(row)
    return rows


def _readiness_flags(envelope):
    """Exact alias -> literal True/False/None mapping within bounds, else None."""
    flags = envelope.get("accounts")
    if not isinstance(flags, dict) or len(flags) > MAX_ENTRIES:
        return None
    for alias, flag in flags.items():
        if not _valid_name(alias):
            return None
        if flag is not True and flag is not False and flag is not None:
            return None
    return flags


def _filter_host_accounts(
    accounts,
    document,
    *,
    host,
    transport_alias,
    mode,
    model,
    candidate_model,
    validator_sha256,
    now,
    max_age=DEFAULT_MAX_AGE,
    preferred=None,
    source_verified=False,
    expected_mode,
):
    """Return (ready original candidate rows in input order, static reason).

    Malformed envelope/entry/row input, unknown or missing readiness and stale
    or invalid timestamps can never qualify an account; a preference never
    silently falls back.
    """
    if mode != expected_mode or mode not in (SUPPORTED_MODE, "qwen"):
        return [], REASON_MODE
    provider = "glm" if mode == "glm" else "bailian"
    supported_models = SUPPORTED_MODELS if mode == "glm" else ("qwen3.8-flash", "qwen3.8-max")
    if model not in supported_models:
        return [], REASON_MODEL
    if candidate_model != model:
        return [], REASON_CANDIDATE_MODEL
    if source_verified is not True:
        return [], REASON_SOURCE_UNVERIFIED
    if not _is_number(now) or not _is_number(max_age) or max_age < 0:
        return [], REASON_CLOCK_INVALID
    preference = None
    if preferred is not None:
        if not isinstance(preferred, str):
            return [], REASON_PREFERENCE_INVALID
        preference = preferred or None  # "" follows incumbent no-preference truthiness
    rows = _candidate_rows(accounts)
    if rows is None:
        return [], REASON_ROWS_INVALID
    if not isinstance(document, dict):
        return [], REASON_DOCUMENT_INVALID
    if not _exact_str(document.get("host"), host):
        return [], REASON_DOCUMENT_INVALID
    if document.get("reachable") is not True:
        return [], REASON_DOCUMENT_INVALID
    if not _fresh(document.get("ts"), now, max_age):
        return [], REASON_DOCUMENT_STALE
    envelope = document.get(provider + "_local_account_readiness")
    if not isinstance(envelope, dict):
        return [], REASON_ENVELOPE_INVALID
    if (
        envelope.get("schema") != "mastermind." + provider + "_local_account_readiness.v1"
        or not _exact_str(envelope.get("host"), host)
        or not _exact_str(envelope.get("transport_alias"), transport_alias)
        or envelope.get("mode") != mode
        or envelope.get("config_scope") != "launcher_" + provider + "_config.v1"
        or envelope.get("status") != STATUS_KNOWN
    ):
        return [], REASON_ENVELOPE_INVALID
    sha = envelope.get("validator_sha256")
    if not _valid_sha256(sha) or sha != validator_sha256:
        return [], REASON_ENVELOPE_INVALID
    # Old configured-key-only observations cannot qualify a remote Qwen
    # account whose host-local hard cooldown was never inspected.
    if mode == "qwen" and envelope.get("cooldown_checked") is not True:
        return [], REASON_ENVELOPE_INVALID
    flags = _readiness_flags(envelope)
    if flags is None:
        return [], REASON_ENVELOPE_INVALID
    if not _fresh(envelope.get("observed_at"), now, max_age):
        return [], REASON_ENVELOPE_STALE
    ready = {alias for alias, flag in flags.items() if flag is True}
    if preference is not None:
        for row in rows:
            if row.get("name") == preference:
                if preference in ready:
                    return [row], REASON_OK
                break
        return [], REASON_PREFERRED_UNAVAILABLE
    selected = [row for row in rows if row.get("name") in ready]
    if not selected:
        return [], REASON_NO_READY
    return selected, REASON_OK


def filter_glm_host_accounts(accounts, document, *, host, transport_alias, mode,
        model, candidate_model, validator_sha256, now, max_age=DEFAULT_MAX_AGE,
        preferred=None, source_verified=False):
    """Preserve the original GLM-only public contract."""
    return _filter_host_accounts(**locals(), expected_mode="glm")


def filter_bailian_host_accounts(accounts, document, *, host, transport_alias, mode,
        model, candidate_model, validator_sha256, now, max_age=DEFAULT_MAX_AGE,
        preferred=None, source_verified=False):
    """Bailian/Qwen configured-account intersection, not a capacity grant."""
    return _filter_host_accounts(**locals(), expected_mode="qwen")

"""Provider quota observation (MMOS OQ-3): real readback, honest unknowns.

One ``QuotaObservation`` is the unit of provider quota knowledge. It is either
a live, typed result of an HTTP readback against a provider endpoint that
actually exposes usage/limit facts (``observed=True``), or a typed refusal to
claim any number (``observed=False`` with exactly one ``reason_code``).
Numbers are never invented: where the provider does not expose usage, limit or
reset facts, the corresponding record field stays ``None`` and the verdict
stays ``unknown`` with the typed reason.

Security/authority constants:

* Usage, limits, reset and cooldown surfaces only. Nothing here ever issues
  an inference/chat/completions request, never mutates provider state and
  never makes a purchase or account change.
* Credentials arrive as the ``credential`` argument, are used exactly once to
  build the authorization header, and are never stored, logged or emitted.
* ``PROVIDER_OBSERVATION_SOURCES`` declares one entry per real, verifiable
  provider readback surface. An empty/absent entry means the provider exposes
  no known HTTP usage surface; such a provider can only ever produce
  ``NOT_EXPOSED`` — not silence, not a guessed number.

Error mapping (type, not prose): 401/403 → ``UNAUTHORIZED``; 404/405 →
``NOT_EXPOSED``; connect/read timeout → ``UNREACHABLE``; no credential →
``NO_CREDENTIAL``; subscription-routed (non-API) providers →
``SUBSCRIPTION_NOT_API``; native OAuth pools whose usage is visible only
inside inference response headers → ``NATIVE_OAUTH_OPAQUE``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

OBSERVATION_SCHEMA = "mastermind.provider_quota_observation/v1"

SOURCE_KINDS = frozenset({"provider_api"})

#: Typed refusals. An ``observed=False`` record carries exactly one of these
#: and NO usage/limit numbers at all.
REASON_CODES = frozenset(
    {
        "NOT_EXPOSED",
        "NO_CREDENTIAL",
        "UNAUTHORIZED",
        "UNREACHABLE",
        "SUBSCRIPTION_NOT_API",
        "NATIVE_OAUTH_OPAQUE",
    }
)

#: Short TTL: a live provider observation expires quickly and must be
#: re-observed before the consumer acts on it.
OBSERVATION_TTL_SECONDS = 900

MAX_OBSERVATIONS = 256
MAX_ENDPOINT = 256
MAX_BODY_BYTES = 64 * 1024
REDACTED_MARKERS = ("<REDACTED",)
_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

#: Real, verifiable provider readback surfaces. Every entry names an endpoint
#: that demonstrably implements the documented usage shape on this estate
#: (documented in orch/fabric/go/GO_ROUTER_SPEC.md §1 and live-observed
#: 2026-09-14; fixture copy ext/go_shim/fixtures/usage_observed_2026-09-14.json).
#: A provider with NO verifiable endpoint is deliberately absent: absent ⇒ the
#: only honest record is ``NOT_EXPOSED``.
PROVIDER_OBSERVATION_SOURCES: dict[str, tuple[dict[str, Any], ...]] = {
    "go": (
        {
            "name": "opencode_zen_go_usage",
            "method": "GET",
            "url": "https://opencode.ai/zen/go/v1/usage",
            "auth": "bearer",
            "shape": "opencode_zen_usage",
            "documented": "orch/fabric/go/GO_ROUTER_SPEC.md §1 (measured 2026-09-14)",
        },
    ),
    "ocfree": (
        {
            "name": "opencode_zen_usage",
            "method": "GET",
            "url": "https://opencode.ai/zen/v1/usage",
            "auth": "bearer",
            "shape": "opencode_zen_usage",
            "documented": "ext/oc_free_exec.sh free-tier route on opencode.ai/zen/v1",
        },
    ),
}

__all__ = [
    "MAX_BODY_BYTES",
    "MAX_ENDPOINT",
    "MAX_OBSERVATIONS",
    "OBSERVATION_SCHEMA",
    "OBSERVATION_TTL_SECONDS",
    "PROVIDER_OBSERVATION_SOURCES",
    "QuotaObservation",
    "QuotaObservationError",
    "REASON_CODES",
    "SOURCE_KINDS",
    "build_observation_document",
    "load_quota_observation_document",
    "load_quota_observations",
    "observe_provider",
    "parse_opencode_zen_usage",
]


class QuotaObservationError(ValueError):
    """A quota observation input is invalid or violates its schema."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _refuse(code: str, detail: str | None = None) -> NoReturn:
    raise QuotaObservationError(code, detail)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID")


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso_z(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_seconds(value: object) -> datetime:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        _refuse("PROVIDER_QUOTA_OBSERVATION_TIMESTAMP_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _refuse("PROVIDER_QUOTA_OBSERVATION_TIMESTAMP_INVALID")


def _friendly_number(value: object) -> float | int | None:
    """Bounded number acceptance; anything else is not a number we claim."""
    if type(value) in (int, float) and -1e15 < value < 1e15:
        return round(value, 2) if isinstance(value, float) else value
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class QuotaObservation:
    """One typed provider quota observation — or one typed honest unknown."""

    provider: str
    account: str
    shared_quota_resource_ref: str
    observed: bool
    usage: float | int | None
    usage_unit: str | None
    limit: float | int | None
    limit_unit: str | None
    reset_at: str | None
    cooldown_until: str | None
    reason_code: str | None
    provenance: dict[str, Any] | None
    details: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "account": self.account,
            "shared_quota_resource_ref": self.shared_quota_resource_ref,
            "observed": self.observed,
        }
        for field in (
            "usage",
            "usage_unit",
            "limit",
            "limit_unit",
            "reset_at",
            "cooldown_until",
            "reason_code",
            "provenance",
            "details",
        ):
            value = getattr(self, field)
            payload[field] = dict(value) if isinstance(value, Mapping) else value
        return payload

    @classmethod
    def not_observed(
        cls,
        *,
        provider: str,
        account: str,
        reason_code: str,
        shared_quota_resource_ref: str | None = None,
        probes: list[dict[str, Any]] | None = None,
    ) -> "QuotaObservation":
        """A typed unknown: no numbers, no provenance claim, one reason."""
        if reason_code not in REASON_CODES:
            _refuse("PROVIDER_QUOTA_OBSERVATION_REASON_INVALID", reason_code)
        resource_ref = shared_quota_resource_ref or f"{provider}:{account}"
        details = None
        if probes:
            details = {"probes": list(probes)}
        return cls(
            provider=provider,
            account=account,
            shared_quota_resource_ref=resource_ref,
            observed=False,
            usage=None,
            usage_unit=None,
            limit=None,
            limit_unit=None,
            reset_at=None,
            cooldown_until=None,
            reason_code=reason_code,
            provenance=None,
            details=details,
        )


def _observation_document_digest(document: Mapping[str, Any]) -> str:
    body = {key: value for key, value in document.items() if key != "digest"}
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def parse_opencode_zen_usage(
    body: Mapping[str, Any],
) -> tuple[float | int, str | None, dict[str, Any]]:
    """Parse the documented opencode zen ``/usage`` shape.

    ``{"usage": {"rolling": {"status", "percent", "resetsAt"}, "weekly": {...},
    "monthly": {...}}}``. The provider exposes percent USED per window; the
    remaining percent is the exact arithmetic complement (100 − used), which
    is a derivation from a real response, never an invention. No limit is part
    of this shape, so ``limit`` stays unknown (``None``). Reset times come
    verbatim from the provider's ``resetsAt``.
    """
    usage_frame = body.get("usage")
    if not isinstance(usage_frame, Mapping):
        _refuse("PROVIDER_QUOTA_OBSERVATION_SHAPE_INVALID", "usage frame missing")
    windows: dict[str, Any] = {}
    used_primary: float | int | None = None
    resets_primary: str | None = None
    for name in ("rolling", "weekly", "monthly"):
        window = usage_frame.get(name)
        if not isinstance(window, Mapping):
            continue
        used = _friendly_number(window.get("percent"))
        entry: dict[str, Any] = {
            "status": str(window.get("status")) if window.get("status") else None,
            "used_pct": used if used is not None and 0 <= used <= 100 else None,
            "reset_at": (
                _normalize_provider_timestamp(window.get("resetsAt"))
                if window.get("resetsAt")
                else None
            ),
        }
        windows[name] = entry
        if name == "rolling":
            used_primary = entry["used_pct"]
            resets_primary = entry["reset_at"]
    if used_primary is None:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SHAPE_INVALID",
            "rolling window percent missing",
        )
    remaining = round(100.0 - float(used_primary), 2)
    return remaining, resets_primary, {"windows": windows}


def _normalize_provider_timestamp(value: object) -> str | None:
    """Normalize a provider timestamp to UTC Z seconds form; never invent."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    for form in (candidate, candidate + ":00"):
        try:
            parsed = datetime.fromisoformat(form)
        except ValueError:
            continue
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        try:
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, ValueError):
            return None
    return None


#: Explicit, declared user agent: providers' bot-walls (e.g. Cloudflare 1010)
#: reject the default client signature; this observes, it never sneaks.
USER_AGENT = "mastermind-rev5-quota-observation/1"


def _fetch(
    url: str,
    *,
    credential: str,
    auth_kind: str,
    timeout_s: float,
) -> tuple[int, bytes, dict[str, str]]:
    """One GET; usage/limits surfaces only; credential used once, never stored."""
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if auth_kind == "bearer":
        headers["Authorization"] = f"Bearer {credential}"
    elif auth_kind == "x-api-key":
        headers["x-api-key"] = credential
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(response.status)
            body_bytes = response.read(MAX_BODY_BYTES + 1)
            response_headers = {
                name.lower(): value
                for name, value in response.headers.items()
                if isinstance(name, str)
            }
    except urllib.error.HTTPError as error:
        response_headers = {}
        if error.headers is not None:
            response_headers = {
                name.lower(): value for name, value in error.headers.items()
            }
        return int(error.code), b"", response_headers
    if len(body_bytes) > MAX_BODY_BYTES:
        _refuse("PROVIDER_QUOTA_OBSERVATION_BODY_TOO_LARGE")
    return status, body_bytes, response_headers


def observe_provider(
    provider: str,
    account: str,
    credential: str | None,
    *,
    timeout_s: float = 10,
) -> QuotaObservation:
    """Observe one (provider, account) through its declared real endpoints.

    Only endpoints declared in ``PROVIDER_OBSERVATION_SOURCES`` are tried. A
    provider with no declared surface returns ``NOT_EXPOSED`` — the record
    stays fully null, no number is invented. The credential is used exactly
    once per attempt for the auth header and is never kept.
    """
    if not isinstance(provider, str) or not provider:
        _refuse("PROVIDER_QUOTA_OBSERVATION_INPUT_INVALID", "provider")
    if not isinstance(account, str) or not account:
        _refuse("PROVIDER_QUOTA_OBSERVATION_INPUT_INVALID", "account")
    sources = PROVIDER_OBSERVATION_SOURCES.get(provider)
    if not sources:
        return QuotaObservation.not_observed(
            provider=provider, account=account, reason_code="NOT_EXPOSED"
        )
    if not isinstance(credential, str):
        return QuotaObservation.not_observed(
            provider=provider, account=account, reason_code="NO_CREDENTIAL"
        )
    credential = credential.strip()
    if not credential or any(marker in credential for marker in REDACTED_MARKERS):
        # A redaction placeholder is not a credential; never send it upstream.
        return QuotaObservation.not_observed(
            provider=provider, account=account, reason_code="NO_CREDENTIAL"
        )

    observed_at = _utc_now()
    probes: list[dict[str, Any]] = []
    last_status: int | None = None
    for source in sources:
        endpoint_host_path = _endpoint_ref(source["url"])
        try:
            status, body_bytes, headers = _fetch(
                source["url"],
                credential=credential,
                auth_kind=str(source["auth"]),
                timeout_s=timeout_s,
            )
        except TimeoutError:
            return QuotaObservation.not_observed(
                provider=provider,
                account=account,
                reason_code="UNREACHABLE",
                probes=[{"endpoint": endpoint_host_path, "status": "timeout"}],
            )
        except (urllib.error.URLError, OSError, ValueError):
            return QuotaObservation.not_observed(
                provider=provider,
                account=account,
                reason_code="UNREACHABLE",
                probes=[{"endpoint": endpoint_host_path, "status": "unreachable"}],
            )
        probes.append({"endpoint": endpoint_host_path, "status": status})
        last_status = status
        if status == 200:
            if source["shape"] != "opencode_zen_usage":
                return QuotaObservation.not_observed(
                    provider=provider,
                    account=account,
                    reason_code="NOT_EXPOSED",
                    probes=probes,
                )
            try:
                body = json.loads(body_bytes or b"{}")
            except ValueError:
                body = None
            if not isinstance(body, Mapping):
                return QuotaObservation.not_observed(
                    provider=provider,
                    account=account,
                    reason_code="NOT_EXPOSED",
                    probes=probes,
                )
            remaining, reset_at, details = parse_opencode_zen_usage(body)
            ratelimit_headers = {
                name: headers[name]
                for name in headers
                if name.startswith(
                    ("x-ratelimit-", "anthropic-ratelimit-", "x-remaining-")
                )
            }
            if ratelimit_headers:
                details["rate_limit_headers"] = {
                    name: _friendly_number(value)
                    for name, value in ratelimit_headers.items()
                }
            expires_at = observed_at + timedelta(seconds=OBSERVATION_TTL_SECONDS)
            return QuotaObservation(
                provider=provider,
                account=account,
                shared_quota_resource_ref=f"{provider}:{account}",
                observed=True,
                usage=remaining,
                usage_unit="percent_of_window_remaining",
                limit=None,
                limit_unit=None,
                reset_at=reset_at,
                cooldown_until=None,
                reason_code=None,
                provenance={
                    "source_kind": "provider_api",
                    "endpoint_host_path": endpoint_host_path,
                    "http_status": status,
                    "observed_at": _iso_z(observed_at),
                    "expires_at": _iso_z(expires_at),
                    "confidence": "documented_endpoint_live_response",
                },
                details={**details, "probes": list(probes)},
            )
        if status in (401, 403):
            return QuotaObservation.not_observed(
                provider=provider,
                account=account,
                reason_code="UNAUTHORIZED",
                probes=probes,
            )
        if status in (404, 405):
            # Try the next declared surface; if none answers, not exposed.
            continue
        if status >= 500:
            return QuotaObservation.not_observed(
                provider=provider,
                account=account,
                reason_code="UNREACHABLE",
                probes=probes,
            )
        return QuotaObservation.not_observed(
            provider=provider,
            account=account,
            reason_code="NOT_EXPOSED",
            probes=probes,
        )
    reason = "NOT_EXPOSED"
    if last_status is not None and last_status not in (404, 405) and last_status >= 500:
        reason = "UNREACHABLE"
    return QuotaObservation.not_observed(
        provider=provider,
        account=account,
        reason_code=reason,
        probes=probes,
    )


def _endpoint_ref(url: object) -> str:
    """host+path of the endpoint; query strings (auth-bearing) are dropped."""
    if not isinstance(url, str):
        _refuse("PROVIDER_QUOTA_OBSERVATION_INPUT_INVALID", "url")
    split = urllib.parse.urlsplit(url)
    if split.scheme not in ("http", "https") or not split.hostname:
        _refuse("PROVIDER_QUOTA_OBSERVATION_INPUT_INVALID", "url")
    return f"{split.hostname}{split.path or ''}"


def load_quota_observation_document(path: object) -> tuple[
    dict[tuple[str, str], QuotaObservation], dict[str, Any]
]:
    """Validated observations lookup keyed by (provider, account) + document meta."""
    record_path = Path(str(path))
    try:
        raw = record_path.read_bytes()
    except OSError as error:
        _refuse("PROVIDER_QUOTA_OBSERVATION_UNAVAILABLE", str(error))
    try:
        document = json.loads(raw)
    except ValueError as error:
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", str(error))
    observations = _validated_document(document)
    meta = {
        "schema": OBSERVATION_SCHEMA,
        "observed_at": document["observed_at"],
        "path": str(record_path),
    }
    return {
        (observation.provider, observation.account): observation
        for observation in observations
    }, meta


def load_quota_observations(path: object) -> dict[tuple[str, str], QuotaObservation]:
    """Load and fully validate a ``mastermind.provider_quota_observation/v1`` doc.

    Bounded document: schema pinned, ≤ MAX_OBSERVATIONS entries, canonical
    digest must match exactly, provider/account strings bounded, observed
    records must carry a provider_api provenance block inside the TTL window,
    and unobserved records must carry exactly one typed reason with NO numbers.
    """
    record_path = Path(path)
    try:
        raw = record_path.read_bytes()
    except OSError as error:
        _refuse("PROVIDER_QUOTA_OBSERVATION_UNAVAILABLE", str(error))
    try:
        document = json.loads(raw)
    except ValueError as error:
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", str(error))
    observations = _validated_document(document)
    return {
        (observation.provider, observation.account): observation
        for observation in observations
    }


def _validated_document(document: object) -> list[QuotaObservation]:
    if not isinstance(document, Mapping):
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "not an object")
    if document.get("schema") != OBSERVATION_SCHEMA:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            f"expected {OBSERVATION_SCHEMA}",
        )
    entries = document.get("observations")
    if not isinstance(entries, list) or len(entries) > MAX_OBSERVATIONS:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            "observations must be a bounded list",
        )
    digest = document.get("digest")
    if not isinstance(digest, str) or len(digest) != 64:
        _refuse("PROVIDER_QUOTA_OBSERVATION_DIGEST_INVALID")
    if _observation_document_digest(
        {key: value for key, value in document.items() if key != "digest"}
    ) != digest:
        _refuse("PROVIDER_QUOTA_OBSERVATION_DIGEST_MISMATCH")
    _parse_utc_seconds(document.get("observed_at"))
    result: list[QuotaObservation] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "entry not an object")
        provider = entry.get("provider")
        account = entry.get("account")
        for value, bound in ((provider, 64), (account, 128)):
            if not isinstance(value, str) or not 0 < len(value) <= bound:
                _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "identity")
        resource_ref = entry.get("shared_quota_resource_ref")
        if (
            not isinstance(resource_ref, str)
            or not 0 < len(resource_ref) <= 256
            or resource_ref != f"{provider}:{account}"
        ):
            _refuse(
                "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
                "shared_quota_resource_ref identity",
            )
        key = (provider, account)
        if key in seen:
            _refuse(
                "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
                f"duplicate resource {provider}:{account}",
            )
        seen.add(key)
        observed = entry.get("observed")
        if not isinstance(observed, bool):
            _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "observed not boolean")
        if observed:
            result.append(_observed_entry(entry, provider, account, document))
        else:
            result.append(_unobserved_entry(entry, provider, account))
    return result


def _observed_entry(
    entry: Mapping[str, Any], provider: str, account: str, document: Mapping[str, Any]
) -> QuotaObservation:
    provenance = entry.get("provenance")
    if not isinstance(provenance, Mapping):
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            f"{provider}:{account} observed entry lacks provenance",
        )
    if provenance.get("source_kind") != "provider_api":
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            "source_kind must be provider_api",
        )
    endpoint = provenance.get("endpoint_host_path")
    if not isinstance(endpoint, str) or not 0 < len(endpoint) <= MAX_ENDPOINT:
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "endpoint_host_path")
    status = provenance.get("http_status")
    if type(status) is not int or status != 200:
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "http_status")
    observed_at = _parse_utc_seconds(provenance.get("observed_at"))
    expires_at = _parse_utc_seconds(provenance.get("expires_at"))
    expected_expiry = observed_at + timedelta(seconds=OBSERVATION_TTL_SECONDS)
    if abs((expires_at - expected_expiry).total_seconds()) > 5:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            f"expires_at must be observed_at + {OBSERVATION_TTL_SECONDS}s",
        )
    doc_observed_at = _parse_utc_seconds(document.get("observed_at"))
    if abs((doc_observed_at - observed_at).total_seconds()) > 5:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            "entry observed_at must match document observed_at",
        )
    confidence = provenance.get("confidence")
    if not isinstance(confidence, str) or not 0 < len(confidence) <= 64:
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "confidence")
    limit = _friendly_number(entry.get("limit"))
    usage = _friendly_number(entry.get("usage"))
    if usage is None or not 0 <= usage <= 100:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            f"{provider}:{account} usage must be a bounded 0..100 percent",
        )
    reset_at = entry.get("reset_at")
    if reset_at is not None:
        reset_at = _iso_z(_parse_utc_seconds(reset_at))
    cooldown_until = entry.get("cooldown_until")
    if cooldown_until is not None:
        cooldown_until = _iso_z(_parse_utc_seconds(cooldown_until))
    if entry.get("usage_unit") != "percent_of_window_remaining":
        _refuse("PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID", "usage_unit")
    details = entry.get("details")
    return QuotaObservation(
        provider=provider,
        account=account,
        shared_quota_resource_ref=f"{provider}:{account}",
        observed=True,
        usage=usage,
        usage_unit="percent_of_window_remaining",
        limit=limit,
        limit_unit="unknown_unit" if limit is not None else None,
        reset_at=reset_at,
        cooldown_until=cooldown_until,
        reason_code=None,
        provenance={
            "source_kind": "provider_api",
            "endpoint_host_path": endpoint,
            "http_status": int(status),
            "observed_at": _iso_z(observed_at),
            "expires_at": _iso_z(expires_at),
            "confidence": str(confidence),
        },
        details=dict(details) if isinstance(details, Mapping) else None,
    )


def _unobserved_entry(
    entry: Mapping[str, Any], provider: str, account: str
) -> QuotaObservation:
    reason = entry.get("reason_code")
    if reason not in REASON_CODES:
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            f"{provider}:{account} unknown typed reason {reason!r}",
        )
    if "provenance" in entry and entry["provenance"] is not None:
        # Unknown records carry a reason, never a provenance claim.
        _refuse(
            "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
            f"{provider}:{account} unobserved entry must be provenance-free",
        )
    for field in (
        "usage",
        "usage_unit",
        "limit",
        "limit_unit",
        "reset_at",
        "cooldown_until",
    ):
        if field in entry and entry[field] is not None:
            _refuse(
                "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
                f"{provider}:{account} unobserved entry must keep {field} null",
            )
    details = entry.get("details")
    probes = None
    if isinstance(details, Mapping) and isinstance(details.get("probes"), list):
        probes = list(details["probes"])
        for probe in probes:
            if (
                not isinstance(probe, Mapping)
                or not set(probe) <= {"endpoint", "status", "body_note"}
                or not isinstance(probe.get("endpoint"), str)
                or (
                    "body_note" in probe
                    and (
                        not isinstance(probe["body_note"], str)
                        or len(probe["body_note"]) > 48
                    )
                )
            ):
                _refuse(
                    "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID",
                    "probe entries are bounded to endpoint+status(+body_note)",
                )
    return QuotaObservation.not_observed(
        provider=provider,
        account=account,
        reason_code=str(reason),
        shared_quota_resource_ref=f"{provider}:{account}",
        probes=probes,
    )


def build_observation_document(
    observations: list[QuotaObservation], *, observed_at: datetime | None = None
) -> dict[str, Any]:
    """Canonical ``mastermind.provider_quota_observation/v1`` wire document."""
    moment = observed_at or _utc_now()
    stamps = _iso_z(moment)
    expires = _iso_z(moment + timedelta(seconds=OBSERVATION_TTL_SECONDS))
    entries: list[dict[str, Any]] = []
    for observation in observations:
        entry = observation.to_dict()
        provenance = entry.get("provenance")
        if isinstance(provenance, dict):
            entry["provenance"] = {
                **provenance,
                "observed_at": stamps,
                "expires_at": expires,
            }
        entries.append(entry)
    document: dict[str, Any] = {
        "schema": OBSERVATION_SCHEMA,
        "observed_at": stamps,
        "observations": entries,
    }
    document["digest"] = hashlib.sha256(
        _canonical_bytes(document)
    ).hexdigest()
    return document

"""Pure GLM adapter lease capability codec and validator."""

import base64
import hashlib
import hmac
import json
import math
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TOKEN = re.compile(r"^v1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")
_MAX_TOKEN_LENGTH = 4096
_DOMAIN = b"mastermind.glm.worker-lease-capability/v1\x00"
_LEASE_FIELDS = frozenset(
    (
        "id",
        "orchestrator_id",
        "pool",
        "account",
        "pid",
        "granted_at",
        "ttl",
        "last_heartbeat",
        "state",
        "renewable",
    )
)
_CLAIM_FIELDS = frozenset(
    (
        "v",
        "lease_id",
        "root",
        "account",
        "model",
        "run_id",
        "host",
        "issued_at",
        "expires_at",
        "granted_at",
        "pid",
    )
)


class CapabilityError(ValueError):
    """Generic, secret-free capability refusal."""


def _identifier(value, label):
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CapabilityError(f"invalid {label}")


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CapabilityError(f"invalid {label}")
    try:
        finite = math.isfinite(value)
    except (OverflowError, ValueError):
        finite = False
    if not finite:
        raise CapabilityError(f"invalid {label}")


def _timestamp(value, label):
    _finite_number(value, label)
    if value <= 0:
        raise CapabilityError(f"invalid {label}")


def _validate_now(value):
    _finite_number(value, "clock")
    if value < 0:
        raise CapabilityError("invalid capability")


def _validate_key(value):
    if not isinstance(value, bytes) or len(value) < 32:
        raise CapabilityError("invalid signing key")


def _base64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def _base64url_decode(value):
    padding = (-len(value)) % 4
    try:
        return base64.b64decode(
            value + b"=" * padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error):
        raise CapabilityError("invalid capability") from None


def _canonical_json_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _reject_json_constant(_value):
    raise CapabilityError("invalid capability")


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CapabilityError("invalid capability")
        value[key] = item
    return value


def _parse_payload(payload_bytes):
    try:
        payload = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except CapabilityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise CapabilityError("invalid capability") from None
    if not isinstance(payload, dict):
        raise CapabilityError("invalid capability")
    return payload


def _validate_payload(payload):
    if set(payload) != _CLAIM_FIELDS:
        raise CapabilityError("invalid capability")
    if type(payload["v"]) is not int or payload["v"] != 1:
        raise CapabilityError("invalid capability")

    for field in ("lease_id", "root", "account", "model", "run_id", "host"):
        _identifier(payload[field], "capability")
    for field in ("issued_at", "expires_at", "granted_at"):
        _timestamp(payload[field], "capability")

    if type(payload["pid"]) is not int or payload["pid"] <= 1:
        raise CapabilityError("invalid capability")
    requested_ttl = payload["expires_at"] - payload["issued_at"]
    if not 1 <= requested_ttl <= 7500 or requested_ttl != int(requested_ttl):
        raise CapabilityError("invalid capability")
    if payload["granted_at"] > payload["issued_at"]:
        raise CapabilityError("invalid capability")


def _validate_scope(payload, model, run_id, host):
    if payload["model"] != model or payload["run_id"] != run_id or payload["host"] != host:
        raise CapabilityError("invalid capability")


def _validate_lease_common(lease, now, requested_expiry):
    if not isinstance(lease, dict) or not _LEASE_FIELDS.issubset(lease):
        raise CapabilityError("lease unavailable")

    for field in ("id", "orchestrator_id", "pool", "account"):
        _identifier(lease[field], "lease")
    if lease["pool"] not in ("glm", "glm-frontier") or lease["state"] not in ("held", "rented"):
        raise CapabilityError("lease unavailable")
    if type(lease["pid"]) is not int or lease["pid"] <= 1:
        raise CapabilityError("lease unavailable")
    if type(lease["renewable"]) is not int or lease["renewable"] not in (0, 1):
        raise CapabilityError("lease unavailable")

    for field in ("granted_at", "last_heartbeat"):
        _timestamp(lease[field], "lease")
    _finite_number(lease["ttl"], "lease ttl")
    if lease["ttl"] <= 0:
        raise CapabilityError("lease unavailable")

    granted_at = lease["granted_at"]
    last_heartbeat = lease["last_heartbeat"]
    if now < granted_at or last_heartbeat < granted_at or last_heartbeat > now:
        raise CapabilityError("lease unavailable")
    if now >= last_heartbeat + lease["ttl"]:
        raise CapabilityError("lease unavailable")
    deadline = last_heartbeat + lease["ttl"]
    if lease["renewable"] == 0:
        deadline = min(deadline, granted_at + lease["ttl"])
        if requested_expiry > deadline:
            raise CapabilityError("lease unavailable")
    # Renewable leases are continuously revalidated against the broker on every
    # request. Their signed capability may span multiple heartbeat windows, but
    # it becomes unusable as soon as the heartbeat lease itself is stale.
    if now >= deadline:
        raise CapabilityError("lease unavailable")


def mint(signing_key, lease, *, root, model, run_id, host, now, ttl=300):
    _validate_key(signing_key)
    _validate_now(now)
    if type(ttl) is not int or not 1 <= ttl <= 7500:
        raise CapabilityError("invalid capability")
    for value in (root, model, run_id, host):
        _identifier(value, "capability")

    expires_at = now + ttl
    _validate_lease_common(lease, now, expires_at)
    if lease["orchestrator_id"] != root:
        raise CapabilityError("lease unavailable")

    payload = {
        "v": 1,
        "lease_id": lease["id"],
        "root": root,
        "account": lease["account"],
        "model": model,
        "run_id": run_id,
        "host": host,
        "issued_at": now,
        "expires_at": expires_at,
        "granted_at": lease["granted_at"],
        "pid": lease["pid"],
    }
    _validate_payload(payload)
    try:
        payload_bytes = _canonical_json_bytes(payload)
    except (ValueError, OverflowError, RecursionError):
        raise CapabilityError("invalid capability") from None
    signature = hmac.new(signing_key, _DOMAIN + payload_bytes, hashlib.sha256).digest()
    token = b"v1." + _base64url_encode(payload_bytes) + b"." + _base64url_encode(signature)
    if len(token) > _MAX_TOKEN_LENGTH:
        raise CapabilityError("invalid capability")
    return token.decode("ascii")


def authorize(token, signing_key, lease_lookup, *, model, run_id, host, now):
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH:
        raise CapabilityError("invalid capability")
    _validate_key(signing_key)
    _validate_now(now)

    match = _TOKEN.fullmatch(token)
    if match is None:
        raise CapabilityError("invalid capability")
    encoded_payload = match.group(1).encode("ascii")
    encoded_signature = match.group(2).encode("ascii")
    payload_bytes = _base64url_decode(encoded_payload)
    signature = _base64url_decode(encoded_signature)
    if encoded_payload != _base64url_encode(payload_bytes):
        raise CapabilityError("invalid capability")
    if encoded_signature != _base64url_encode(signature):
        raise CapabilityError("invalid capability")
    if len(signature) != hashlib.sha256().digest_size:
        raise CapabilityError("invalid capability")

    expected_signature = hmac.new(signing_key, _DOMAIN + payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise CapabilityError("invalid capability")
    payload = _parse_payload(payload_bytes)
    _validate_payload(payload)
    if payload_bytes != _canonical_json_bytes(payload):
        raise CapabilityError("invalid capability")
    _validate_scope(payload, model, run_id, host)
    if now < payload["issued_at"] or now >= payload["expires_at"]:
        raise CapabilityError("invalid capability")

    if not callable(lease_lookup):
        raise CapabilityError("lease unavailable")
    try:
        lease = lease_lookup(payload["lease_id"])
    except Exception:
        raise CapabilityError("lease unavailable") from None
    _validate_lease_for_authorize(lease, payload, now)
    return dict(payload)


def _validate_lease_for_authorize(lease, claims, now):
    _validate_lease_common(lease, now, claims["expires_at"])
    if (
        lease["id"] != claims["lease_id"]
        or lease["orchestrator_id"] != claims["root"]
        or lease["account"] != claims["account"]
        or lease["pid"] != claims["pid"]
        or lease["granted_at"] != claims["granted_at"]
    ):
        raise CapabilityError("lease unavailable")
    if lease["renewable"] == 0 and now >= lease["granted_at"] + lease["ttl"]:
        raise CapabilityError("lease unavailable")


# ── v2: closed canonical paid model-only scope (domain-separated) ──────────────
# Same gateway signing key material, different HMAC domain and token version.
# A v1 path can neither mint nor accept this scope, and vice versa.

_DOMAIN_V2 = b"mastermind.glm.paid-canonical-capability/v2\x00"
_TOKEN_V2 = re.compile(r"^v2\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CLAIM_FIELDS_V2 = frozenset(
    (
        "v",
        "lease_id",
        "root",
        "job_id",
        "attempt_id",
        "parent_job_id",
        "effective_grant_digest",
        "commission_sha256",
        "physical_binding_sha256",
        "model",
        "host",
        "account",
        "fence",
        "pin_version",
        "payload_sha256",
        "request_body_sha256",
        "result_schema_sha256",
        "issued_at",
        "expires_at",
        "granted_at",
        "pid",
    )
)


def _hex64(value, label):
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise CapabilityError(f"invalid {label}")


def _validate_payload_v2(payload):
    if set(payload) != _CLAIM_FIELDS_V2:
        raise CapabilityError("invalid capability")
    if type(payload["v"]) is not int or payload["v"] != 2:
        raise CapabilityError("invalid capability")

    for field in (
        "lease_id", "root", "job_id", "attempt_id",
        "model", "host", "account",
    ):
        _identifier(payload[field], "capability")
    if (payload['parent_job_id'] is None and payload['job_id'] != payload['root']
            or payload['parent_job_id'] is not None and not isinstance(payload['parent_job_id'], str)):
        raise CapabilityError('invalid capability')
    if payload['parent_job_id'] is not None:
        _identifier(payload['parent_job_id'], 'capability')
    if type(payload['fence']) is not int or payload['fence'] <= 0:
        raise CapabilityError('invalid capability')
    for field in (
        "effective_grant_digest", "commission_sha256",
        "physical_binding_sha256", "payload_sha256",
        "request_body_sha256", "result_schema_sha256",
    ):
        _hex64(payload[field], "capability")

    if type(payload["pin_version"]) is not int or payload["pin_version"] <= 0:
        raise CapabilityError("invalid capability")
    if type(payload["pid"]) is not int or payload["pid"] <= 1:
        raise CapabilityError("invalid capability")
    for field in ("issued_at", "expires_at", "granted_at"):
        _timestamp(payload[field], "capability")
    requested_ttl = payload["expires_at"] - payload["issued_at"]
    if not 1 <= requested_ttl <= 7500 or requested_ttl != int(requested_ttl):
        raise CapabilityError("invalid capability")
    if payload["granted_at"] > payload["issued_at"]:
        raise CapabilityError("invalid capability")


def mint_canonical(
    signing_key,
    lease,
    *,
    root,
    job_id,
    attempt_id,
    parent_job_id,
    effective_grant_digest,
    commission_sha256,
    physical_binding_sha256,
    model,
    host,
    fence,
    pin_version,
    payload_sha256,
    request_body_sha256,
    result_schema_sha256,
    now,
    ttl=300,
):
    """Mint a v2 canonical paid capability bound to the full Control scope."""
    _validate_key(signing_key)
    _validate_now(now)
    if type(ttl) is not int or not 1 <= ttl <= 7500:
        raise CapabilityError("invalid capability")
    for value in (root, job_id, attempt_id, model, host):
        _identifier(value, "capability")
    for value in (
        effective_grant_digest, commission_sha256, physical_binding_sha256,
        payload_sha256, request_body_sha256, result_schema_sha256,
    ):
        _hex64(value, "capability")
    if type(pin_version) is not int or pin_version <= 0:
        raise CapabilityError("invalid capability")

    if type(fence) is not int or fence <= 0:
        raise CapabilityError('invalid capability')
    expires_at = now + ttl
    _validate_lease_common(lease, now, expires_at)
    if (lease['pool'] not in {'glm', 'glm-frontier'}
            or lease.get('host') != host or lease.get('model') != model
            or (lease['pool'] == 'glm-frontier' and model != 'glm-5.3')):
        raise CapabilityError('lease unavailable')
    if lease["orchestrator_id"] != root:
        raise CapabilityError("lease unavailable")

    payload = {
        "v": 2,
        "lease_id": lease["id"],
        "root": root,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "parent_job_id": parent_job_id,
        "effective_grant_digest": effective_grant_digest,
        "commission_sha256": commission_sha256,
        "physical_binding_sha256": physical_binding_sha256,
        "model": model,
        "host": host,
        "account": lease["account"],
        "fence": fence,
        "pin_version": pin_version,
        "payload_sha256": payload_sha256,
        "request_body_sha256": request_body_sha256,
        "result_schema_sha256": result_schema_sha256,
        "issued_at": now,
        "expires_at": expires_at,
        "granted_at": lease["granted_at"],
        "pid": lease["pid"],
    }
    _validate_payload_v2(payload)
    try:
        payload_bytes = _canonical_json_bytes(payload)
    except (ValueError, OverflowError, RecursionError):
        raise CapabilityError("invalid capability") from None
    signature = hmac.new(signing_key, _DOMAIN_V2 + payload_bytes, hashlib.sha256).digest()
    token = b"v2." + _base64url_encode(payload_bytes) + b"." + _base64url_encode(signature)
    if len(token) > _MAX_TOKEN_LENGTH:
        raise CapabilityError("invalid capability")
    return token.decode("ascii")


def authorize_canonical(token, signing_key, lease_lookup, *, model, run_id, host, now):
    """Verify a v2 canonical capability and revalidate the current lease."""
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH:
        raise CapabilityError("invalid capability")
    _validate_key(signing_key)
    _validate_now(now)

    match = _TOKEN_V2.fullmatch(token)
    if match is None:
        raise CapabilityError("invalid capability")
    encoded_payload = match.group(1).encode("ascii")
    encoded_signature = match.group(2).encode("ascii")
    payload_bytes = _base64url_decode(encoded_payload)
    signature = _base64url_decode(encoded_signature)
    if encoded_payload != _base64url_encode(payload_bytes):
        raise CapabilityError("invalid capability")
    if encoded_signature != _base64url_encode(signature):
        raise CapabilityError("invalid capability")
    if len(signature) != hashlib.sha256().digest_size:
        raise CapabilityError("invalid capability")

    expected_signature = hmac.new(signing_key, _DOMAIN_V2 + payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise CapabilityError("invalid capability")
    payload = _parse_payload(payload_bytes)
    _validate_payload_v2(payload)
    if payload_bytes != _canonical_json_bytes(payload):
        raise CapabilityError("invalid capability")
    if payload["model"] != model or payload["host"] != host or payload["attempt_id"] != run_id:
        raise CapabilityError("invalid capability")
    if now < payload["issued_at"] or now >= payload["expires_at"]:
        raise CapabilityError("invalid capability")

    if not callable(lease_lookup):
        raise CapabilityError("lease unavailable")
    try:
        lease = lease_lookup(payload["lease_id"])
    except Exception:
        raise CapabilityError("lease unavailable") from None
    _validate_lease_for_authorize(lease, payload, now)
    if (lease['pool'] not in {'glm', 'glm-frontier'}
            or lease.get('host') != host or lease.get('model') != model
            or (lease['pool'] == 'glm-frontier' and model != 'glm-5.3')):
        raise CapabilityError('lease unavailable')
    return dict(payload)

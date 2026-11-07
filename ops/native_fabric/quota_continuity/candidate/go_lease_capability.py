"""Pure Go adapter lease capability codec and validator."""

import base64
import hashlib
import hmac
import json
import math
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TOKEN = re.compile(r"^v1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")
_MAX_TOKEN_LENGTH = 4096
_DOMAIN = b"mastermind.go.worker-lease-capability/v1\x00"
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
    if not 1 <= requested_ttl <= 900 or requested_ttl != int(requested_ttl):
        raise CapabilityError("invalid capability")
    if payload["granted_at"] > payload["issued_at"]:
        raise CapabilityError("invalid capability")


def _validate_scope(payload, model, run_id, host):
    if payload["model"] != model or payload["run_id"] != run_id or payload["host"] != host:
        raise CapabilityError("invalid capability")


def _validate_lease_common(lease, now, requested_expiry):
    if not isinstance(lease, dict) or not _LEASE_FIELDS.issubset(lease):
        raise CapabilityError("lease unavailable")
    if lease.get("purpose", "WORKER") != "WORKER":
        raise CapabilityError("lease unavailable")

    for field in ("id", "orchestrator_id", "pool", "account"):
        _identifier(lease[field], "lease")
    if lease["pool"] != "go" or lease["state"] not in ("held", "rented"):
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
    if now >= deadline or requested_expiry > deadline:
        raise CapabilityError("lease unavailable")


def mint(signing_key, lease, *, root, model, run_id, host, now, ttl=300):
    _validate_key(signing_key)
    _validate_now(now)
    if type(ttl) is not int or not 1 <= ttl <= 900:
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


_APPLICATION_TOKEN = re.compile(r"^app1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")
_APPLICATION_DOMAIN = b"mastermind.go.application-lease-capability/v1\x00"
_APPLICATION_HTTP_TOKEN = re.compile(r"^app2\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")
_APPLICATION_HTTP_DOMAIN = b"mastermind.bailian.application-lease-capability/v2\x00"
_APPLICATION_FIELDS = frozenset({
    "v", "purpose", "lease_id", "root", "pool", "account", "model", "principal_id", "host",
    "workload", "turn_id", "grant_digest", "issued_at", "expires_at", "lease_generation",
})


def _validate_application_claims(claims):
    if not isinstance(claims, dict):
        raise CapabilityError("invalid application capability")
    http = claims.get("pool") == "bailian"
    fields = _APPLICATION_FIELDS | {"recipe_digest"} if http else _APPLICATION_FIELDS
    if (set(claims) != fields
            or type(claims["v"]) is not int or claims["v"] != (2 if http else 1)
            or claims["purpose"] != "APPLICATION" or claims["pool"] != ("bailian" if http else "go")):
        raise CapabilityError("invalid application capability")
    if http and (not isinstance(claims["recipe_digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", claims["recipe_digest"]) is None):
        raise CapabilityError("invalid application capability")
    for key in ("lease_id", "root", "pool", "account", "principal_id", "host", "workload", "turn_id"):
        _identifier(claims[key], "application capability")
    if (not isinstance(claims["model"], str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}", claims["model"]) is None
            or not isinstance(claims["grant_digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", claims["grant_digest"]) is None):
        raise CapabilityError("invalid application capability")
    for key in ("issued_at", "expires_at", "lease_generation"):
        _timestamp(claims[key], "application capability")
    if (claims["lease_generation"] > claims["issued_at"]
            or not 0 < claims["expires_at"] - claims["issued_at"] <= 900):
        raise CapabilityError("invalid application capability")


def _validate_application_binding(lease, turn, claims, now, *, recovery_only=False):
    if not isinstance(lease, dict) or not isinstance(turn, dict):
        raise CapabilityError("application lease unavailable")
    try:
        if (lease["purpose"] != "APPLICATION" or lease["pid"] != 0
                or lease["state"] not in {"held", "rented", "released", "expired"}
                or turn["state"] not in {"open", "closing", "closed"}
                or lease["id"] != claims["lease_id"] or turn["lease_id"] != claims["lease_id"]
                or lease["orchestrator_id"] != claims["root"]
                or turn["admission_root"] != claims["root"]
                or lease["granted_at"] != claims["lease_generation"]
                or turn["created_at"] != claims["lease_generation"]
                or turn["caller_host"] != claims["host"] or lease["host"] != claims["host"]):
            raise CapabilityError("application lease unavailable")
        for key in ("pool", "account", "model"):
            if lease[key] != claims[key] or turn[key] != claims[key]:
                raise CapabilityError("application lease unavailable")
        for key in ("principal_id", "turn_id", "workload", "grant_digest"):
            if turn[key] != claims[key]:
                raise CapabilityError("application lease unavailable")
        if claims["pool"] == "bailian" and turn["recipe_digest"] != claims["recipe_digest"]:
            raise CapabilityError("application lease unavailable")
        _timestamp(lease["granted_at"], "application lease")
        _finite_number(lease["ttl"], "application lease")
        _timestamp(turn["expires_at"], "application lease")
        deadline = min(turn["expires_at"], lease["granted_at"] + lease["ttl"])
        if (lease["ttl"] <= 0 or now < lease["granted_at"]
                or claims["expires_at"] > deadline):
            raise CapabilityError("application lease unavailable")
        if not recovery_only and (now >= deadline or lease["state"] not in {"held", "rented"}
                                  or turn["state"] != "open"):
            raise CapabilityError("application lease unavailable")
    except (KeyError, TypeError, OverflowError):
        raise CapabilityError("application lease unavailable") from None


def mint_application(signing_key, lease, turn, *, now):
    """Application purpose, without worker run IDs or fabricated PIDs."""
    _validate_key(signing_key)
    _validate_now(now)
    try:
        claims = {"v": 1, "purpose": "APPLICATION", "lease_id": turn["lease_id"],
                  "root": turn["admission_root"], "pool": turn["pool"], "account": turn["account"],
                  "model": turn["model"], "principal_id": turn["principal_id"], "host": turn["caller_host"],
                  "workload": turn["workload"], "turn_id": turn["turn_id"], "grant_digest": turn["grant_digest"],
                  "issued_at": now, "expires_at": min(turn["expires_at"], lease["granted_at"] + lease["ttl"]),
                  "lease_generation": lease["granted_at"]}
        if turn["pool"] == "bailian":
            claims.update(v=2, recipe_digest=turn["recipe_digest"])
        _validate_application_claims(claims)
        _validate_application_binding(lease, turn, claims, now)
        raw = _canonical_json_bytes(claims)
        domain = _APPLICATION_HTTP_DOMAIN if claims["v"] == 2 else _APPLICATION_DOMAIN
        prefix = b"app2." if claims["v"] == 2 else b"app1."
        signature = hmac.new(signing_key, domain + raw, hashlib.sha256).digest()
        token = prefix + _base64url_encode(raw) + b"." + _base64url_encode(signature)
        if len(token) > _MAX_TOKEN_LENGTH:
            raise CapabilityError("invalid application capability")
        return token.decode("ascii")
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise CapabilityError("invalid application capability") from None


def authorize_application(token, signing_key, lease_lookup, turn_lookup, *, principal_id, host, turn_id, model, now,
                          recovery_only=False, expected_pool="go"):
    _validate_key(signing_key)
    _validate_now(now)
    if (type(recovery_only) is not bool or not isinstance(token, str) or len(token) > _MAX_TOKEN_LENGTH
            or expected_pool not in ("go", "bailian")):
        raise CapabilityError("invalid application capability")
    pattern = _APPLICATION_TOKEN if expected_pool == "go" else _APPLICATION_HTTP_TOKEN
    domain = _APPLICATION_DOMAIN if expected_pool == "go" else _APPLICATION_HTTP_DOMAIN
    match = pattern.fullmatch(token)
    if match is None:
        raise CapabilityError("invalid application capability")
    encoded, signature_part = (part.encode("ascii") for part in match.groups())
    raw, signature = _base64url_decode(encoded), _base64url_decode(signature_part)
    if (encoded != _base64url_encode(raw) or signature_part != _base64url_encode(signature)
            or len(signature) != hashlib.sha256().digest_size
            or not hmac.compare_digest(signature, hmac.new(signing_key, domain + raw, hashlib.sha256).digest())):
        raise CapabilityError("invalid application capability")
    claims = _parse_payload(raw)
    _validate_application_claims(claims)
    if (claims["pool"] != expected_pool or raw != _canonical_json_bytes(claims) or now < claims["issued_at"]
            or (not recovery_only and now >= claims["expires_at"])
            or any(claims[key] != value for key, value in (("principal_id", principal_id),
                    ("host", host), ("turn_id", turn_id), ("model", model)))):
        raise CapabilityError("invalid application capability")
    try:
        lease = lease_lookup(claims["lease_id"])
        turn = turn_lookup(principal_id, turn_id)
    except Exception:
        raise CapabilityError("application lease unavailable") from None
    # Recovery authenticates only the immutable original scope. It never grants
    # dispatch permission, even if the original execution authority has expired.
    _validate_application_binding(lease, turn, claims, now, recovery_only=recovery_only)
    return dict(claims)

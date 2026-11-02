"""Controller-side gateway for the Go adapter lease capability codec."""

import hashlib
import json
import math
import secrets
import re
import sqlite3
import time
from pathlib import Path

from glm_lease_capability import authorize, mint, authorize_canonical, mint_canonical


class LeaseGatewayError(ValueError):
    """A generic, secret-free lease gateway refusal."""


class GlmLeaseGateway:
    def __init__(self, db_path, accounts, models, *, clock=time.time, signing_key=None):
        self._db_path = Path(db_path)
        if not self._db_path.is_absolute():
            raise LeaseGatewayError("lease capability refused")
        self._accounts = frozenset(accounts)
        self._models = frozenset(models)
        self._clock = clock

        if signing_key is None:
            self._signing_key = secrets.token_bytes(32)
        else:
            if not isinstance(signing_key, bytes) or len(signing_key) < 32:
                raise LeaseGatewayError("lease capability refused")
            self._signing_key = signing_key

        # Do not expose lease-v1 on /health unless its read-only broker
        # source exists and contains the exact fields needed to authenticate
        # leased workers. Runtime lease/heartbeat checks remain authoritative.
        self._validate_broker_store()

    def _connection(self):
        try:
            return sqlite3.connect(
                self._db_path.as_uri() + "?mode=ro",
                uri=True,
                timeout=0.25,
            )
        except Exception:
            raise LeaseGatewayError("lease capability refused") from None

    def _validate_broker_store(self):
        # Prevent a missing, swapped, or incompatible source from making the
        # HTTP shim advertise a worker capability it cannot actually use.
        if self._db_path.is_symlink() or not self._db_path.is_file():
            raise LeaseGatewayError("lease capability refused")
        connection = self._connection()  # SQLite mode=ro; no broker writes.
        try:
            connection.execute(
                "SELECT id, orchestrator_id, pool, account, pid, "
                "granted_at, ttl, last_heartbeat, state, renewable "
                "FROM leases WHERE 0"
            ).fetchone()
        except sqlite3.Error:
            raise LeaseGatewayError("lease capability refused") from None
        finally:
            connection.close()

    def broker_ready(self):
        """Read-only capability readiness, reflecting later broker loss or drift."""
        try:
            self._validate_broker_store()
            return True
        except (LeaseGatewayError, OSError):
            return False

    @staticmethod
    def _lease_lookup(connection, lease_id):
        cursor = connection.execute(
            "SELECT * FROM leases WHERE id = ? LIMIT 1",
            (lease_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LeaseGatewayError("lease capability refused")
        return dict(zip((column[0] for column in cursor.description), row))

    def issue(self, request):
        try:
            if not isinstance(request, dict) or set(request) != {
                "lease_id",
                "root",
                "model",
                "run_id",
                "host",
                "ttl",
            }:
                raise LeaseGatewayError("lease capability refused")
            if not isinstance(request["lease_id"], str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request["lease_id"]) is None:
                raise LeaseGatewayError("lease capability refused")
            ttl = request["ttl"]
            if (
                type(ttl) is not int
                or not 1 <= ttl <= 7500
                or request["model"] not in self._models
            ):
                raise LeaseGatewayError("lease capability refused")

            connection = self._connection()
            try:
                lease = self._lease_lookup(connection, request["lease_id"])
            finally:
                connection.close()

            if lease.get("account") not in self._accounts:
                raise LeaseGatewayError("lease capability refused")
            now = self._clock()
            token = mint(
                self._signing_key,
                lease,
                root=request["root"],
                model=request["model"],
                run_id=request["run_id"],
                host=request["host"],
                now=now,
                ttl=ttl,
            )
            return {
                "token": token,
                "expires_at": now + ttl,
                "account": lease["account"],
                "lease_id": request["lease_id"],
                "model": request["model"],
                "run_id": request["run_id"],
                "host": request["host"],
                "root": request["root"],
            }
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("lease capability refused") from None

    def authorize(self, token, *, model, run_id, host):
        try:
            connection = self._connection()
            try:
                claims = authorize(
                    token,
                    self._signing_key,
                    lambda lease_id: self._lease_lookup(connection, lease_id),
                    model=model,
                    run_id=run_id,
                    host=host,
                    now=self._clock(),
                )
            finally:
                connection.close()
            if claims["model"] not in self._models or claims["account"] not in self._accounts:
                raise LeaseGatewayError("lease capability refused")
            return claims
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("lease capability refused") from None

    def _issue_canonical(self, payload, *, authority, lease_id, ttl, request_body):
        """Private issuer on the actual canonical Control/paid-owner chain."""
        try:
            cls = _control_start_authority_class()
            if type(authority) is not cls:
                raise _canonical_refuse()
            authority.require(payload)
            from control_plane.paid_model_execution_contract import compile_request
            raw = compile_request(payload)
            derived = json.loads(raw)
            if _canonical_json_bytes(request_body) != raw:
                raise _canonical_refuse()
            if (type(ttl) is not int or not 1 <= ttl <= 7500
                    or derived['model'] not in self._models
                    or not _canonical_identifier(lease_id)):
                raise _canonical_refuse()
            connection = self._connection()
            try:
                lease = self._lease_lookup(connection, lease_id)
            finally:
                connection.close()
            binding, route = payload['binding'], payload['paid_route']
            from control_plane.paid_fabric_wire import require_paid_physical
            physical=require_paid_physical(payload)
            transport_host=physical['qualification']['registry_key']
            _require_canonical_lease_route(lease, root=binding['root_id'],
                route={**route,'host_ref':transport_host})
            if (lease.get('account') not in self._accounts
                    or lease.get('account') != payload.get('paid_account')):
                raise _canonical_refuse()
            owner = _original_canonical_owner(self)
            observed = owner.require_original_controller(payload, lease)
            owner.begin_capsule_issue(payload, authority, lease)
            now = self._clock()
            if now + ttl > authority.expires_at:
                raise _canonical_refuse()
            authority.require(payload)
            token = mint_canonical(self._signing_key, lease,
                root=binding['root_id'], job_id=binding['job_id'],
                attempt_id=binding['attempt_id'], parent_job_id=route['parent_job_id'],
                effective_grant_digest=binding['effective_grant_digest'],
                commission_sha256=binding['commission_sha256'],
                physical_binding_sha256=payload['physical_binding_sha256'],
                model=route['model'], host=transport_host,
                fence=authority.fence_generation, pin_version=authority.pin_version,
                payload_sha256=authority.payload_sha256,
                request_body_sha256=_sha256_hex(raw),
                result_schema_sha256=_sha256_hex(_canonical_json_bytes(payload['paid_input']['result_schema'])),
                now=now, ttl=ttl)
            authority.require(payload)
            owner.require_original_controller(payload, lease, expected=observed)
            return dict(token=token, expires_at=now+ttl, account=lease['account'],
                lease_id=lease_id, model=route['model'], host=transport_host,
                root=binding['root_id'], run_id=binding['attempt_id'])
        except Exception:
            raise _canonical_refuse() from None

    def authorize_canonical(self, token, *, model, run_id, host):
        """Verify signature/current lease and original live controller ownership."""
        try:
            connection = self._connection()
            try:
                claims = authorize_canonical(token, self._signing_key,
                    lambda lease_id: self._lease_lookup(connection, lease_id),
                    model=model, run_id=run_id, host=host, now=self._clock())
                lease = self._lease_lookup(connection, claims['lease_id'])
                _require_canonical_lease_route(lease, root=claims['root'],
                    route=dict(provider='glm', host_ref=claims['host'], model=claims['model']))
            finally:
                connection.close()
            if claims['model'] not in self._models or claims['account'] not in self._accounts:
                raise _canonical_refuse()
            _original_canonical_owner(self).require_canonical_request(claims)
            return claims
        except Exception:
            raise _canonical_refuse() from None

    def _consume_canonical_provider_intent(self, claims):
        """Actual original owner consumes before any provider credential/IO."""
        try:
            _original_canonical_owner(self).consume_provider_intent(claims)
        except Exception:
            raise _canonical_refuse() from None


# ── v2: closed canonical paid model-only scope ────────────────────────────────
# Issuance is PRIVATE: only a real control_plane.fabric_control_start
# ControlStartAuthority instance whose require(payload) accepts the full
# authenticated payload may reach it. No HTTP route, header or body can
# request canonical issuance — /worker-capabilities keeps the v1 schema only.


_CANONICAL_BODY_FIELDS = frozenset(("model", "input", "stream", "max_output_tokens"))
_CANONICAL_CAPABILITIES = frozenset(("READ", "RESEARCH"))
_CANONICAL_POOL = "glm"
_CANONICAL_PROVIDER = "glm"
_CANONICAL_MAX_OUTPUT_TOKENS = 8192
_CANONICAL_INPUT_LIMIT = 1024 * 1024
_PAID_DIGEST_FIELDS = frozenset(("effective_grant_digest", "commission_sha256", "physical_binding_sha256"))
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class CanonicalCapabilityError(LeaseGatewayError):
    """A generic, secret-free canonical paid capability refusal."""


def _canonical_refuse():
    return CanonicalCapabilityError("canonical capability refused")


def _canonical_json_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _canonical_identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is not None


def _canonical_hex64(value):
    return isinstance(value, str) and _HEX64_RE.fullmatch(value) is not None


def _canonical_exact_fields(value, fields):
    return isinstance(value, dict) and set(value) == fields


def _canonical_text(value):
    """A bounded, nonempty, valid UTF-8 string (<=1MiB as UTF-8 bytes)."""
    if not isinstance(value, str) or not value:
        return False
    try:
        return len(value.encode("utf-8")) <= _CANONICAL_INPUT_LIMIT
    except (UnicodeEncodeError, OverflowError):
        return False


def _canonical_finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _control_start_authority_class():
    """Resolve the ACTUAL ControlStartAuthority class, lazily and read-only.

    Constructor fields, plain dicts and bearer strings are never accepted as
    proof of Control authority: the instance must be of the real class and its
    require(payload) must accept the full payload before and after the
    read-only lease observation.
    """
    try:
        import control_plane.fabric_control_start as _control_start
    except Exception:
        raise _canonical_refuse() from None
    cls = getattr(_control_start, "ControlStartAuthority", None)
    if not isinstance(cls, type):
        raise _canonical_refuse()
    return cls








def _require_canonical_lease_route(lease, *, root, route):
    pool = lease.get('pool')
    if (lease.get('orchestrator_id') != root
            or lease.get('host') != route['host_ref']
            or lease.get('model') != route['model']
            or pool not in {'glm', 'glm-frontier'}
            or (pool == 'glm-frontier' and route['model'] != 'glm-5.3')):
        raise _canonical_refuse()


def _original_canonical_owner(gateway):
    # Only the same-shim production constructor binds this actual owner. No
    # HTTP payload/callback/boolean may manufacture or select it.
    from control_plane.paid_fabric_backend import CanonicalPaidBackend
    owner = getattr(gateway, '_canonical_owner', None)
    if type(owner) is not CanonicalPaidBackend:
        raise _canonical_refuse()
    owner.require_gateway(gateway)
    return owner

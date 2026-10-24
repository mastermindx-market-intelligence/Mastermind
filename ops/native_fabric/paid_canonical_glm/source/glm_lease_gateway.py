"""Controller-side gateway for the Go adapter lease capability codec."""

import secrets
import re
import sqlite3
import time
from pathlib import Path

from glm_lease_capability import authorize, mint


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

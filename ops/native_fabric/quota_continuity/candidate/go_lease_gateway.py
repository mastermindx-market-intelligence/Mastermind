"""Controller-side gateway for the Go adapter lease capability codec."""

import secrets
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from go_lease_capability import authorize, mint, authorize_application, mint_application


class LeaseGatewayError(ValueError):
    """A generic, secret-free lease gateway refusal."""


class GoLeaseGateway:
    def __init__(self, db_path, accounts, models, *, clock=time.time, signing_key=None,
                 application_broker=None):
        db_path = Path(db_path)
        if not db_path.is_absolute():
            raise LeaseGatewayError("lease capability refused")
        self._db_path = db_path.resolve()
        self._accounts = frozenset(accounts)
        self._models = frozenset(models)
        self._clock = clock
        self._application_broker = application_broker
        self._application_db_identity = None
        if application_broker is not None:
            from lease_broker import Broker
            if not isinstance(application_broker, Broker):
                raise LeaseGatewayError("application owner unavailable")
            try:
                if (self._db_path != Path(application_broker.db_path).resolve()
                        or not os.path.samefile(self._db_path, application_broker.db_path)):
                    raise LeaseGatewayError("application owner unavailable")
                info = self._db_path.stat()
                self._application_db_identity = (info.st_dev, info.st_ino)
            except OSError:
                raise LeaseGatewayError("application owner unavailable") from None

        if signing_key is None:
            self._signing_key = secrets.token_bytes(32)
        else:
            if not isinstance(signing_key, bytes) or len(signing_key) < 32:
                raise LeaseGatewayError("lease capability refused")
            self._signing_key = signing_key

    def _connection(self):
        try:
            return sqlite3.connect(
                self._db_path.as_uri() + "?mode=ro",
                uri=True,
                timeout=0.25,
            )
        except Exception:
            raise LeaseGatewayError("lease capability refused") from None

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
                or not 1 <= ttl <= 300
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

    def _application_owner(self):
        try:
            broker = self._application_broker
            info = self._db_path.stat()
            if (broker is None or self._db_path != Path(broker.db_path).resolve()
                    or not os.path.samefile(self._db_path, broker.db_path)
                    or (info.st_dev, info.st_ino) != self._application_db_identity):
                raise LeaseGatewayError("application owner unavailable")
            return broker
        except (OSError, AttributeError):
            raise LeaseGatewayError("application owner unavailable") from None

    @staticmethod
    def _application_turn_lookup(connection, principal_id, turn_id):
        cursor = connection.execute("SELECT * FROM application_turns WHERE principal_id=? AND turn_id=?",
                                    (principal_id, turn_id))
        row = cursor.fetchone()
        if row is None:
            raise LeaseGatewayError("application turn unavailable")
        return dict(zip((column[0] for column in cursor.description), row))

    def begin_application(self, request, *, principal_id, host, deadline_ns=None):
        """Internal authenticated service context; never caller-supplied identity."""
        try:
            broker = self._application_owner()
            if (not isinstance(request, dict) or set(request) != {"workload", "turn_id", "pool", "model"}
                    or request["pool"] != "go" or request["model"] not in self._models):
                raise LeaseGatewayError("application admission refused")
            result = broker.begin_application_turn(principal_id=principal_id, caller_host=host,
                workload=request["workload"], turn_id=request["turn_id"], pool=request["pool"],
                model=request["model"], deadline_ns=deadline_ns, transport_accounts=self._accounts)
            if not result["ok"] or result["disposition"] not in {"admitted", "existing"}:
                return result
            connection = self._connection()
            try:
                connection.execute("BEGIN")
                lease = self._lease_lookup(connection, result["lease_id"])
                turn = self._application_turn_lookup(connection, principal_id, request["turn_id"])
                token = mint_application(self._signing_key, lease, turn, now=self._clock())
            finally:
                connection.close()
            return {**result, "token": token}
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("application admission refused") from None

    def recover_application(self, request, *, principal_id, host, request_id, path, payload):
        """Recover through the same authenticated service after handler restart.

        The handler supplies principal and host from its private authentication
        owner. Recovery never mints a token or authorizes another upstream call.
        """
        try:
            broker = self._application_owner()
            if (not isinstance(request, dict) or set(request) != {"workload", "turn_id", "pool", "model"}
                    or request["pool"] != "go" or path != "/v1/chat/completions"
                    or not isinstance(payload, dict) or payload.get("stream", False) is not False
                    or payload.get("model") != request["model"]):
                raise LeaseGatewayError("application recovery refused")
            for value in (principal_id, host, request["workload"], request["turn_id"], request_id):
                if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is None:
                    raise LeaseGatewayError("application recovery refused")
            raw = json.dumps({"path": path, "payload": payload}, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(raw) > 1024 * 1024:
                raise LeaseGatewayError("application recovery refused")
            connection = self._connection()
            try:
                connection.row_factory = sqlite3.Row
                turn = connection.execute("SELECT * FROM application_turns WHERE principal_id=? AND turn_id=?",
                                          (principal_id, request["turn_id"])).fetchone()
            finally:
                connection.close()
            if turn is None:
                return None
            if (turn["caller_host"] != host
                    or any(turn[key] != request[key] for key in ("workload", "pool", "model"))):
                raise LeaseGatewayError("application recovery refused")
            return broker.recover_application_request(principal_id=principal_id, turn_id=request["turn_id"],
                request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest())
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("application recovery refused") from None

    def prepare_application(self, token, *, principal_id, host, turn_id, request_id, path, payload):
        try:
            broker = self._application_owner()
            if (path != "/v1/chat/completions" or not isinstance(payload, dict)
                    or payload.get("stream", False) is not False):
                raise LeaseGatewayError("application request refused")
            raw = json.dumps({"path": path, "payload": payload}, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(raw) > 1024 * 1024:
                raise LeaseGatewayError("application request refused")
            connection = self._connection()
            try:
                connection.execute("BEGIN")
                claims = authorize_application(token, self._signing_key,
                    lambda lease_id: self._lease_lookup(connection, lease_id),
                    lambda principal, turn: self._application_turn_lookup(connection, principal, turn),
                    principal_id=principal_id, host=host, turn_id=turn_id,
                    model=payload["model"], now=self._clock(), recovery_only=True)
                recovered = broker.recover_application_request(principal_id=principal_id, turn_id=turn_id,
                    request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest())
                if recovered is not None:
                    return recovered
                # Only a new step requires current execution permission. A prior
                # request stays recoverable after closure, expiry or revocation.
                authorize_application(token, self._signing_key,
                    lambda lease_id: self._lease_lookup(connection, lease_id),
                    lambda principal, turn: self._application_turn_lookup(connection, principal, turn),
                    principal_id=principal_id, host=host, turn_id=turn_id,
                    model=payload["model"], now=self._clock())
            finally:
                connection.close()
            if claims["account"] not in self._accounts or claims["model"] not in self._models:
                raise LeaseGatewayError("application request refused")
            prepared = broker.prepare_application_request(principal_id=principal_id, turn_id=turn_id,
                request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest())
            if prepared.get("dispatch_permitted"):
                # The original handler sends these immutable, digest-bound bytes.
                # They are internal dispatch material, never a public receipt/log.
                frozen = json.loads(raw)["payload"]
                prepared["payload_bytes"] = json.dumps(frozen, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8")
            return prepared
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("application request refused") from None

    def complete_application(self, dispatch_id, *, terminal_receipt):
        """Original handler only; this is not a caller-facing settlement route."""
        return self._application_owner().complete_application_request(
            dispatch_id=dispatch_id, terminal_receipt=terminal_receipt)

    def mark_application_unknown(self, dispatch_id, *, reason):
        return self._application_owner().mark_application_request_unknown(dispatch_id=dispatch_id, reason=reason)

    def close_application_turn(self, *, principal_id, turn_id):
        return self._application_owner().close_application_turn(principal_id=principal_id, turn_id=turn_id)

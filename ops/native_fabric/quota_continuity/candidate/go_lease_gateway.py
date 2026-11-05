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


class ApplicationSelectionRefused(LeaseGatewayError):
    """Known selection-condition refusal before a new admission effect."""


class ApplicationSelectionProfile:
    """Source-owned Go transport metadata supplied by verified startup.

    This identifies the existing buffered chat implementation. It creates no
    H recipe, qualification, credential or alternative transport. Grants remain
    the sole source of qualification and ordinary application permission.
    """
    __slots__ = ("_encoded",)

    def __init__(self, *, source_generation, ingress_digest, account_profile):
        for value in (source_generation, ingress_digest):
            if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise LeaseGatewayError("application selection source unavailable")
        path = Path(account_profile)
        if not path.is_absolute() or ".." in path.parts:
            raise LeaseGatewayError("application selection profile unavailable")
        # The handler carries chat tool declarations/results without changing
        # their wire identity. Media remains outside this selected profile.
        document = {"pool": "go", "mode": "go", "protocol": "chat", "streaming": False,
            "driver": "go-http-v1", "profile": "go-application-chat-v1",
            "source": "native-" + ingress_digest, "capabilities": {"tools": True, "vision": False},
            "source_generation": source_generation, "ingress_digest": ingress_digest,
            "account_owner_digest": hashlib.sha256(str(path).encode()).hexdigest()}
        object.__setattr__(self, "_encoded", json.dumps(document, sort_keys=True, separators=(",", ":")))

    def __setattr__(self, name, value):
        raise AttributeError("application selection profile is immutable")

    @property
    def document(self):
        return json.loads(self._encoded)


class GoLeaseGateway:
    def __init__(self, db_path, accounts, models, *, clock=time.time, signing_key=None,
                 application_broker=None, application_http_recipes=(), application_http_accounts=(),
                 application_selection_profile=None):
        db_path = Path(db_path)
        if not db_path.is_absolute():
            raise LeaseGatewayError("lease capability refused")
        self._db_path = db_path.resolve()
        self._accounts = frozenset(accounts)
        self._models = frozenset(models)
        # Application-only projections never broaden the worker capability
        # account/model sets above. Fresh grants remain the admission authority.
        self._application_http_recipes = {}
        self._application_http_accounts = frozenset(application_http_accounts)
        if any(not isinstance(account, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", account) is None
               for account in self._application_http_accounts):
            raise LeaseGatewayError("application transport refused")
        for recipe in application_http_recipes:
            try:
                from lease_broker import _application_http_recipe
                encoded, digest = _application_http_recipe(recipe, pool=recipe["pool"], model=recipe["model"])
                key = (recipe["pool"], recipe["model"])
                if key in self._application_http_recipes:
                    raise ValueError("duplicate application recipe")
                self._application_http_recipes[key] = (encoded, digest)
            except Exception:
                raise LeaseGatewayError("application transport refused") from None
        if bool(self._application_http_recipes) != bool(self._application_http_accounts):
            raise LeaseGatewayError("application transport refused")
        self._clock = clock
        self._application_broker = application_broker
        if application_selection_profile is not None and type(application_selection_profile) is not ApplicationSelectionProfile:
            raise LeaseGatewayError("application selection profile unavailable")
        self._application_selection_profile = application_selection_profile
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

    def application_recipe(self, pool, model):
        """Fresh immutable copy of the sealed transport projection, not authority."""
        try:
            encoded, digest = self._application_http_recipes[(pool, model)]
            return json.loads(encoded), digest
        except (KeyError, TypeError):
            raise LeaseGatewayError("application transport unavailable") from None

    def _application_scope(self, pool, model):
        if pool == "go" and model in self._models:
            return self._accounts, None, None
        recipe, digest = self.application_recipe(pool, model)
        return self._application_http_accounts, recipe, digest

    def application_pool_view(self, *, principal_id, host, workload, credential_ref,
                              bound_pool, source, go_models):
        """Observe the original DB inode through mode=ro; never construct an owner."""
        try:
            broker = self._application_owner()
            profile = self._application_selection_profile
            if type(go_models) is not frozenset:
                raise LeaseGatewayError("application metadata transport unavailable")
            transports = {"go": [{"model": model, "protocol": "chat",
                "capabilities": {"text": True, "tools": bool(profile), "vision": False,
                                 "upstream_streaming": False},
                "qualified": profile is not None and model in go_models, "accounts": self._accounts}
                for model in sorted(self._models)]}
            for (pool, model), (_, digest) in sorted(self._application_http_recipes.items()):
                recipe, _ = self.application_recipe(pool, model)
                transports.setdefault(pool, []).append({"model": model,
                    "protocol": recipe["protocol"], "qualified": True,
                    "capabilities": {"text": True, "tools": False, "vision": False,
                                     "upstream_streaming": False},
                    "accounts": self._application_http_accounts, "recipe_digest": digest})
            if sum(len(rows) for rows in transports.values()) > 128:
                raise LeaseGatewayError("application metadata bound exceeded")
            connection = self._connection()
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN")
                result = broker.application_pool_view(connection, principal_id=principal_id,
                    caller_host=host, workload=workload, credential_ref=credential_ref,
                    bound_pool=bound_pool, transports=transports, source=source)
                self._application_owner()
            finally:
                connection.close()
            return result
        except Exception:
            raise LeaseGatewayError("application metadata unavailable") from None

    @staticmethod
    def application_selection_task(purpose, payload):
        """Derive capability needs; the caller cannot supply routing authority."""
        from lease_broker import _application_selection_purpose
        encoded, _ = _application_selection_purpose(purpose)
        task = json.loads(encoded)["task"]
        needs = set(task.get("needs") or [])
        if payload.get("tools") or payload.get("tool_choice") or payload.get("parallel_tool_calls"):
            needs.add("tools")
        for message in payload["messages"]:
            if type(message) is not dict:
                raise ApplicationSelectionRefused("application selection payload refused")
            if message.get("tool_calls") or message.get("role") == "tool" or message.get("tool_call_id"):
                needs.add("tools")
            content = message.get("content")
            if type(content) is list:
                if any(type(part) is not dict or part.get("type") != "text" for part in content):
                    needs.add("vision")
            elif content is not None and type(content) is not str:
                raise ApplicationSelectionRefused("application selection payload refused")
        return {"task_class": task["task_class"].lower(),
            "route_key": task["route_key"], "task_complexity": str(task.get("task_complexity") or "").upper(),
            "needs": sorted(needs), "subject_pool": task.get("subject_pool"),
            "escalation_reason": str(task.get("escalation_reason") or ""),
            "requested_model": payload["model"]}

    def select_application(self, request, *, principal_id, host, credential_ref, purpose, payload):
        """Produce fresh owner inputs for the incumbent pure selector, once per new turn attempt."""
        try:
            import pick
            import pool_ledger
            from lease_broker import _application_json, _application_selection_purpose
            broker = self._application_owner()
            if request["pool"] != "go" or self._application_selection_profile is None:
                raise ValueError("unqualified selection transport")
            profile = self._application_selection_profile.document
            task = self.application_selection_task(purpose, payload)
            policy = pick.read_application_policy()
            quality = pool_ledger.read_recent(limit=10000, strict=True)
            connection = self._connection()
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN")
                grant, grant_digest, observation = broker.application_selection_facts(connection,
                    principal_id=principal_id, caller_host=host, workload=request["workload"],
                    pool=request["pool"], model=request["model"], credential_ref=credential_ref,
                    transport_accounts=self._accounts)
            finally:
                connection.close()
            recipe = {key: profile[key] for key in
                ("mode", "protocol", "streaming", "driver", "profile", "source", "capabilities")}
            recipe.update(model=request["model"], order_rank=0,
                max_turn_seconds=grant["max_turn_seconds"], max_steps=grant["max_steps"],
                qualification_ref=grant["qualification_ref"],
                application_permission_ref=grant["application_permission_ref"],
                grant_ref={"grant_id": grant["grant_id"], "digest": grant_digest})
            catalogue = {"schema": "mastermind.fabric_application_catalogue.v1", "pool_order": ["go"],
                "pools": {"go": {"enabled": True, "recipes": [recipe]}}}
            selected = pick.select_application(task, policy=policy, catalogue=catalogue,
                observations={"go": observation}, quality_records=quality, now=self._clock(),
                expected_identity={"pool": "go", "model": request["model"], "source": profile["source"]})
            if not selected["ok"]:
                raise ValueError("selection refused")
            purpose_json, purpose_digest = _application_selection_purpose(purpose)
            return {"schema": "mastermind.application_turn_selection.v1",
                "purpose": json.loads(purpose_json), "purpose_digest": purpose_digest,
                "profile": profile, "profile_digest": hashlib.sha256(_application_json(profile).encode()).hexdigest(),
                "identity": selected["identity"], "commitments": selected["commitments"],
                "quality_records_sha256": hashlib.sha256(_application_json(quality).encode()).hexdigest(),
                "fresh_s": 5.0}
        except Exception:
            raise ApplicationSelectionRefused("application selection unavailable") from None

    def begin_application(self, request, *, principal_id, host, deadline_ns=None,
                          expected_credential_ref=None, expected_recipe_digest=None,
                          expected_selection=None, selection_purpose=None, selection_payload=None):
        """Internal authenticated service context; never caller-supplied identity."""
        try:
            broker = self._application_owner()
            if not isinstance(request, dict) or set(request) != {"workload", "turn_id", "pool", "model"}:
                raise LeaseGatewayError("application admission refused")
            accounts, recipe, digest = self._application_scope(request["pool"], request["model"])
            if digest != expected_recipe_digest:
                raise LeaseGatewayError("application recipe refused")
            selection_args = {}
            if expected_selection is not None or selection_purpose is not None:
                selection_args = dict(expected_selection=expected_selection, selection_purpose=selection_purpose,
                    selection_profile=(self._application_selection_profile.document
                        if self._application_selection_profile is not None else None),
                    selection_task=self.application_selection_task(selection_purpose, selection_payload))
            result = broker.begin_application_turn(principal_id=principal_id, caller_host=host,
                workload=request["workload"], turn_id=request["turn_id"], pool=request["pool"],
                model=request["model"], deadline_ns=deadline_ns, transport_accounts=accounts,
                expected_credential_ref=expected_credential_ref, application_recipe=recipe,
                expected_recipe_digest=expected_recipe_digest, **selection_args)
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
        except Exception as error:
            from lease_broker import ApplicationSelectionError
            if isinstance(error, ApplicationSelectionError):
                raise ApplicationSelectionRefused("application selection condition refused") from None
            raise LeaseGatewayError("application admission refused") from None

    def recover_application(self, request, *, principal_id, host, request_id, path, payload,
                            expected_recipe_digest=None, include_turn=False):
        """Recover through the same authenticated service after handler restart.

        The handler supplies principal and host from its private authentication
        owner. Recovery never mints a token or authorizes another upstream call.
        """
        try:
            broker = self._application_owner()
            if (not isinstance(request, dict) or set(request) != {"workload", "turn_id", "pool", "model"}
                    or request["pool"] not in ("go", "bailian") or path != "/v1/chat/completions"
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
            if type(include_turn) is not bool:
                raise LeaseGatewayError("application recovery refused")
            # Use the original pool and recipe after authentication, even if
            # today's service projection has rotated. Recovery grants no send.
            connection = self._connection()
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN")
                context = broker.recover_application_context(principal_id=principal_id,
                    caller_host=host, workload=request["workload"], turn_id=request["turn_id"],
                    model=request["model"], request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest(),
                    expected_recipe_digest=expected_recipe_digest, connection=connection)
            finally:
                connection.close()
            return context if include_turn else context.get("request")
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("application recovery refused") from None

    def prepare_application(self, token, *, principal_id, host, turn_id, request_id, path, payload,
                            expected_pool="go", transport_commitment=None):
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
                    model=payload["model"], now=self._clock(), recovery_only=True, expected_pool=expected_pool)
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
                    model=payload["model"], now=self._clock(), expected_pool=expected_pool)
            finally:
                connection.close()
            accounts, recipe, digest = self._application_scope(expected_pool, claims["model"])
            if (claims["account"] not in accounts
                    or expected_pool != "go" and claims["recipe_digest"] != digest):
                raise LeaseGatewayError("application request refused")
            prepared = broker.prepare_application_request(principal_id=principal_id, turn_id=turn_id,
                request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest(),
                transport_commitment=transport_commitment)
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

    def close_application_turn(self, *, principal_id, turn_id, expected_host=None,
                               expected_workload=None):
        broker = self._application_owner()
        if expected_host is not None or expected_workload is not None:
            connection = self._connection()
            try:
                turn = self._application_turn_lookup(connection, principal_id, turn_id)
                if (turn["caller_host"] != expected_host
                        or turn["workload"] != expected_workload):
                    raise LeaseGatewayError("application close scope refused")
            finally:
                connection.close()
        # Turn scope is immutable in the same owner database; this is not an
        # eligibility recheck that could block original uncertain settlement.
        return broker.close_application_turn(principal_id=principal_id, turn_id=turn_id)

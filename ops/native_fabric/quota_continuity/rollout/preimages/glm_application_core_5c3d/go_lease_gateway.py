"""Controller-side gateway for the Go adapter lease capability codec."""

import secrets
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from go_lease_capability import (authorize, mint, authorize_application, mint_application,
    mint_native_dispatch, authorize_native_dispatch, NATIVE_APPLICATION_KIND, NATIVE_APPLICATION_POOLS)


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


_APPLICATION_NATIVE_PICKER_MODES = {
    "codex-native": ("codex-native",), "claude-native": ("claude-native",),
    "ocfree": ("oc-free",), "glm": ("glm", "glm-codex"),
    "minimax": ("minimax",), "grok": ("grok",), "cursor": ("cursor",)}


class ApplicationNativeSelection:
    """Closed immutable picker projection for one actual native recipe.

    A native recipe carries no picker mode, so verified startup supplies this
    optional projection bound to that exact recipe's pool, model and source
    generation. Absence only excludes the route from selection; fixed native
    transport and recovery are unchanged. This is a name projection: it never
    infers a pool, mode, qualification, credential or provider read.
    """
    __slots__ = ("_encoded",)

    def __init__(self, *, pool, model, mode, source_generation):
        from pick import _APPLICATION_MODES
        modes = _APPLICATION_NATIVE_PICKER_MODES.get(pool)
        if (modes is None or pool not in NATIVE_APPLICATION_POOLS
                or mode not in _APPLICATION_MODES or mode not in modes
                or type(model) is not str or not model or len(model) > 128
                or type(source_generation) is not str
                or re.fullmatch(r"[0-9a-f]{64}", source_generation) is None):
            raise LeaseGatewayError("native selection projection refused")
        document = {"pool": pool, "model": model, "mode": mode, "protocol": "harness",
            "streaming": False, "capabilities": {"text": True, "tools": False, "vision": False},
            "source": "native-" + source_generation, "source_generation": source_generation}
        object.__setattr__(self, "_encoded", json.dumps(document, sort_keys=True, separators=(",", ":")))

    def __setattr__(self, name, value):
        raise AttributeError("native selection projection is immutable")

    @property
    def document(self):
        return json.loads(self._encoded)

    @property
    def encoded(self):
        return self._encoded


class GoLeaseGateway:
    def __init__(self, db_path, accounts, models, *, clock=time.time, signing_key=None,
                 application_broker=None, application_http_recipes=(), application_http_accounts=(),
                 application_selection_profile=None, application_native_recipes=(),
                 application_native_accounts=None, application_native_selection=None):
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
        self._application_native_recipes = {}
        self._application_native_accounts = {}
        self._application_native_selection = {}
        try:
            from lease_broker import _application_native_recipe, _application_id
            for recipe in application_native_recipes:
                encoded, digest = _application_native_recipe(recipe, pool=recipe["pool"], model=recipe["model"])
                key = (recipe["pool"], recipe["model"])
                if key in self._application_native_recipes:
                    raise ValueError("duplicate native recipe")
                self._application_native_recipes[key] = (encoded, digest)
            accounts = {} if application_native_accounts is None else application_native_accounts
            if type(accounts) is not dict or set(accounts) != {key[0] for key in self._application_native_recipes}:
                raise ValueError("native account envelope mismatch")
            for pool, names in accounts.items():
                if type(names) not in (list, tuple, set, frozenset) or not names or len(names) > 128:
                    raise ValueError("native account envelope invalid")
                self._application_native_accounts[pool] = frozenset(_application_id(name) for name in names)
            if self._application_native_recipes and type(self) is not GoLeaseGateway:
                raise ValueError("native owner context unavailable")
            # Selection projections are optional per registered route and are
            # bound to that recipe's exact pool, model and source generation.
            projections = {} if application_native_selection is None else application_native_selection
            if type(projections) is not dict:
                raise ValueError("native selection envelope invalid")
            for key, projection in projections.items():
                if (type(key) is not tuple or len(key) != 2
                        or key not in self._application_native_recipes
                        or type(projection) is not ApplicationNativeSelection):
                    raise ValueError("native selection projection invalid")
                document = projection.document
                encoded, _ = self._application_native_recipes[key]
                if (document["pool"] != key[0] or document["model"] != key[1]
                        or document["source_generation"] != json.loads(encoded)["source_generation"]):
                    raise ValueError("native selection projection conflicts with recipe")
                self._application_native_selection[key] = projection.encoded
        except Exception:
            raise LeaseGatewayError("application native transport refused") from None
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
            if self._application_native_recipes and type(application_broker) is not Broker:
                raise LeaseGatewayError("application native owner unavailable")
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
            recipes = self._application_native_recipes if pool in NATIVE_APPLICATION_POOLS else self._application_http_recipes
            encoded, digest = recipes[(pool, model)]
            return json.loads(encoded), digest
        except (KeyError, TypeError):
            raise LeaseGatewayError("application transport unavailable") from None

    def _application_scope(self, pool, model):
        if pool == "go" and model in self._models:
            return self._accounts, None, None
        recipe, digest = self.application_recipe(pool, model)
        accounts = self._application_native_accounts[pool] if pool in NATIVE_APPLICATION_POOLS else self._application_http_accounts
        return accounts, recipe, digest

    def _application_route(self, pool, model):
        """The one actual registered route for a pool and model, or None.

        Registered startup transport only: configuration, inventory or any
        catalogue alone never offers a route. The returned projection is the
        immutable transport identity that atomic admission later compares, and
        the picker grammar stays inside what that transport actually accepts.
        """
        if pool == "go":
            if self._application_selection_profile is None or model not in self._models:
                return None, None, None
            return self._accounts, None, self._application_selection_profile.document
        if pool == "bailian":
            try:
                recipe, digest = self.application_recipe(pool, model)
            except LeaseGatewayError:
                return None, None, None
            # The H driver accepts chat tool declarations and results over its
            # responses protocol; no media, no upstream streaming.
            projection = {"pool": pool, "model": model, "mode": "bailian",
                "protocol": recipe["protocol"], "streaming": False,
                "driver": recipe["driver_id"], "profile": recipe["realm_id"],
                "source": "bailian-" + recipe["source_projection_sha256"],
                "capabilities": {"text": True, "tools": True, "vision": False}}
            return self._application_http_accounts, digest, projection
        if pool in NATIVE_APPLICATION_POOLS:
            encoded = self._application_native_selection.get((pool, model))
            if encoded is None:
                return None, None, None
            try:
                recipe, digest = self.application_recipe(pool, model)
            except LeaseGatewayError:
                return None, None, None
            stated = json.loads(encoded)
            projection = {"pool": pool, "model": model, "mode": stated["mode"],
                "protocol": stated["protocol"], "streaming": False,
                "driver": recipe["driver_id"], "profile": recipe["profile"],
                "source": stated["source"], "capabilities": dict(stated["capabilities"])}
            return self._application_native_accounts[pool], digest, projection
        return None, None, None

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
                accounts, route_digest, projection = self._application_route(pool, model)
                if projection is None or route_digest != digest:
                    raise LeaseGatewayError("application metadata transport unavailable")
                transports.setdefault(pool, []).append({"model": model,
                    "protocol": projection["protocol"], "qualified": True,
                    "capabilities": {**projection["capabilities"],
                                     "upstream_streaming": projection["streaming"]},
                    "accounts": accounts, "recipe_digest": digest})
            for (pool, model), (_, digest) in sorted(self._application_native_recipes.items()):
                # A native row stays unqualified without its optional startup
                # selection projection; the fixed transport itself is unchanged.
                route = self._application_route(pool, model)
                transports.setdefault(pool, []).append({"model": model,
                    "protocol": "harness", "qualified": route[0] is not None,
                    "capabilities": {"text": True, "tools": False, "vision": False,
                                     "upstream_streaming": False},
                    "accounts": self._application_native_accounts[pool], "recipe_digest": digest})
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
        """Use the same pure request-needs interpretation as atomic admission."""
        from lease_broker import _application_selection_task
        return _application_selection_task(purpose, payload)

    def application_registered_routes(self):
        """Names from the actual startup projections; no eligibility or account read."""
        pairs = ({("go", model) for model in self._models}
                 | set(self._application_http_recipes) | set(self._application_native_recipes))
        return frozenset(pair for pair in pairs if self._application_route(*pair)[0] is not None)

    def select_application(self, request, *, principal_id, host, credential_ref, purpose, payload,
                           route_scope=None, transport_candidates=None):
        """Select once from registered, granted routes inside trusted service scope."""
        try:
            import pick
            import pool_ledger
            from lease_broker import (_application_json, _application_selection_purpose,
                                      _read_application_accounts, _application_native_payload,
                                      _application_route_scope, _application_model)
            broker = self._application_owner()
            if (type(request) is not dict or set(request) != {"workload", "turn_id", "pool", "model"}
                    or type(payload) is not dict or "model" not in payload
                    or payload["model"] != request["model"]):
                raise ValueError("selection request identity")
            requested = request["model"]
            scope_document = scope_digest = None
            eligible_pools = {request["pool"]}
            if route_scope is not None:
                scope_json, scope_digest = _application_route_scope(route_scope)
                scope_document = json.loads(scope_json)
                if (type(transport_candidates) is not frozenset
                        or len(transport_candidates) > 128):
                    raise ValueError("invalid scoped transport projection")
                if requested is not None:
                    _application_model(requested)
                for pair in transport_candidates:
                    if (type(pair) is not tuple or len(pair) != 2
                            or pair[0] not in ({"go", "bailian"} | NATIVE_APPLICATION_POOLS)):
                        raise ValueError("invalid AUTO candidate")
                    _application_model(pair[1])
                eligible_pools = set(scope_document["pools"])
            elif transport_candidates is not None:
                raise ValueError("transport projection requires route scope")
            task = self.application_selection_task(purpose, payload)
            policy = pick.read_application_policy()
            quality = pool_ledger.read_recent(limit=10000, strict=True)
            document = _read_application_accounts(broker.accounts_path)
            pools, observations, projections = {}, {}, {}
            connection = self._connection()
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN")
                for pool in pick._APPLICATION_POOL_ORDER:
                    if pool not in eligible_pools:
                        continue
                    if requested is not None:
                        models = (requested,)
                    elif pool == "go":
                        models = sorted(self._models)
                    elif pool == "bailian":
                        models = sorted(model for candidate_pool, model in self._application_http_recipes
                                        if candidate_pool == pool)
                    else:
                        models = sorted(model for candidate_pool, model in self._application_native_recipes
                                        if candidate_pool == pool)
                    for model in models:
                        if transport_candidates is not None and (pool, model) not in transport_candidates:
                            continue
                        accounts, digest, projection = self._application_route(pool, model)
                        if accounts is None:
                            continue
                        projections[(pool, model)] = projection
                        try:
                            if requested is None and pool in NATIVE_APPLICATION_POOLS:
                                recipe = json.loads(self._application_native_recipes[(pool, model)][0])
                                concrete = dict(payload, model=model)
                                _application_native_payload(recipe, concrete)
                            grant, grant_digest, observation = broker.application_selection_facts(
                                connection, principal_id=principal_id, caller_host=host,
                                workload=request["workload"], pool=pool, model=model,
                                credential_ref=credential_ref, transport_accounts=accounts,
                                mode=projection["mode"], expected_recipe_digest=digest,
                                document=document)
                        except Exception:
                            continue
                        recipe = {key: projection[key] for key in
                            ("mode", "protocol", "streaming", "driver", "profile", "source", "capabilities")}
                        # Equal ranks assert no model preference. The existing
                        # policy default wins; unqualified alternatives still tie.
                        recipe.update(model=model, order_rank=0,
                            max_turn_seconds=grant["max_turn_seconds"], max_steps=grant["max_steps"],
                            qualification_ref=grant["qualification_ref"],
                            application_permission_ref=grant["application_permission_ref"],
                            grant_ref={"grant_id": grant["grant_id"], "digest": grant_digest})
                        pools.setdefault(pool, {"enabled": True, "recipes": []})["recipes"].append(recipe)
                        if pool not in observations:
                            observations[pool] = dict(observation, model_room=dict(observation["model_room"]))
                        else:
                            previous = observations[pool]
                            if any(previous[key] != observation[key] for key in ("source", "host", "cooldown")):
                                raise ValueError("incoherent room observations")
                            if set(previous["model_room"]) & set(observation["model_room"]):
                                raise ValueError("duplicate model room")
                            previous["model_room"].update(observation["model_room"])
                            previous["observed_at"] = min(previous["observed_at"], observation["observed_at"])
                            previous["fresh_s"] = min(previous["fresh_s"], observation["fresh_s"])
                            if previous.get("mode") != observation.get("mode"):
                                previous.pop("mode", None)
            finally:
                connection.close()
            expected = None if scope_document is not None else {"pool": request["pool"]}
            if requested is not None:
                if scope_document is not None:
                    expected = {"model": requested}
                else:
                    bound = projections.get((request["pool"], requested))
                    if bound is None:
                        raise ValueError("unqualified selection transport")
                    expected.update(model=requested, source=bound["source"])
            catalogue = {"schema": "mastermind.fabric_application_catalogue.v1",
                "pool_order": list(pick._APPLICATION_POOL_ORDER), "pools": pools}
            selected = pick.select_application(task, policy=policy, catalogue=catalogue,
                observations=observations, quality_records=quality, now=self._clock(),
                expected_identity=expected)
            if not selected["ok"]:
                raise ValueError("selection refused")
            identity = selected["identity"]
            bound = projections[(identity["pool"], identity["model"])]
            if identity["source"] != bound["source"]:
                raise ValueError("selected source changed")
            purpose_json, purpose_digest = _application_selection_purpose(purpose)
            result = {"schema": "mastermind.application_turn_selection.v1",
                "purpose": json.loads(purpose_json), "purpose_digest": purpose_digest,
                "profile": bound, "profile_digest": hashlib.sha256(_application_json(bound).encode()).hexdigest(),
                "identity": identity, "commitments": selected["commitments"],
                "quality_records_sha256": hashlib.sha256(_application_json(quality).encode()).hexdigest(),
                "fresh_s": 5.0}
            if scope_document is not None:
                result.update(schema=("mastermind.application_turn_selection.v2" if requested is None
                                      else "mastermind.application_turn_selection.v3"),
                              route_scope=scope_document, route_scope_digest=scope_digest)
            return result
        except Exception:
            raise ApplicationSelectionRefused("application selection unavailable") from None

    def begin_application(self, request, *, principal_id, host, deadline_ns=None,
                          expected_credential_ref=None, expected_recipe_digest=None,
                          expected_selection=None, selection_purpose=None, selection_payload=None,
                          selection_route_scope=None):
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
                route = self._application_route(request["pool"], request["model"])
                if route is None:
                    raise ApplicationSelectionRefused("application selection condition refused")
                selection_args = dict(expected_selection=expected_selection, selection_purpose=selection_purpose,
                    selection_profile=route[2], selection_route_scope=selection_route_scope,
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
                    or request["pool"] not in ({"go", "bailian"} | NATIVE_APPLICATION_POOLS) or path != "/v1/chat/completions"
                    or not isinstance(payload, dict) or "model" not in payload
                    or payload.get("stream", False) is not False or payload["model"] != request["model"]):
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
                    expected_recipe_digest=expected_recipe_digest, connection=connection,
                    original_payload=json.loads(raw)["payload"])
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
                from lease_broker import _application_routed_request, _application_stored_scope
                turn = self._application_turn_lookup(connection, principal_id, turn_id)
                original_payload = json.loads(raw)["payload"]
                scoped = _application_stored_scope(turn) is not None
                frozen, original_digest, routed_digest = _application_routed_request(turn, original_payload)
                if original_digest != hashlib.sha256(raw).hexdigest():
                    raise LeaseGatewayError("application original request changed")
                claims = authorize_application(token, self._signing_key,
                    lambda lease_id: self._lease_lookup(connection, lease_id),
                    lambda principal, turn: self._application_turn_lookup(connection, principal, turn),
                    principal_id=principal_id, host=host, turn_id=turn_id,
                    model=frozen["model"], now=self._clock(), recovery_only=True, expected_pool=expected_pool)
                recovered = broker.recover_application_request(principal_id=principal_id, turn_id=turn_id,
                    request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest(),
                    transport_commitment=transport_commitment, verify_native_commitment=True,
                    routed_request_digest=routed_digest)
                if recovered is not None:
                    return recovered
                # Only a new step requires current execution permission. A prior
                # request stays recoverable after closure, expiry or revocation.
                authorize_application(token, self._signing_key,
                    lambda lease_id: self._lease_lookup(connection, lease_id),
                    lambda principal, turn: self._application_turn_lookup(connection, principal, turn),
                    principal_id=principal_id, host=host, turn_id=turn_id,
                    model=frozen["model"], now=self._clock(), expected_pool=expected_pool)
            finally:
                connection.close()
            accounts, recipe, digest = self._application_scope(expected_pool, claims["model"])
            if (claims["account"] not in accounts
                    or expected_pool != "go" and claims["recipe_digest"] != digest):
                raise LeaseGatewayError("application request refused")
            prepared = broker.prepare_application_request(principal_id=principal_id, turn_id=turn_id,
                request_id=request_id, request_digest=hashlib.sha256(raw).hexdigest(),
                transport_commitment=transport_commitment,
                native_payload=frozen if expected_pool in NATIVE_APPLICATION_POOLS else None,
                original_payload=original_payload if routed_digest is not None or scoped else None)
            if prepared.get("dispatch_permitted"):
                # The original handler sends these immutable, digest-bound bytes.
                # They are internal dispatch material, never a public receipt/log.
                prepared["payload_bytes"] = json.dumps(frozen, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8")
                if expected_pool in NATIVE_APPLICATION_POOLS:
                    from lease_broker import _application_native_payload
                    if type(self) is not GoLeaseGateway:
                        raise LeaseGatewayError("application native owner unavailable")
                    connection = self._connection()
                    try:
                        connection.row_factory = sqlite3.Row
                        connection.execute("BEGIN")
                        turn = self._application_turn_lookup(connection, principal_id, turn_id)
                        lease = self._lease_lookup(connection, turn["lease_id"])
                        request = connection.execute("SELECT * FROM application_requests WHERE dispatch_id=?",
                            (prepared["dispatch_id"],)).fetchone()
                        if request is None:
                            raise LeaseGatewayError("application native dispatch unavailable")
                        token = mint_native_dispatch(self._signing_key, lease, turn, dict(request), now=self._clock())
                        stored_invocation = json.loads(request["invocation_json"])
                        stored_invocation["invocation_digest"] = request["invocation_digest"]
                        if stored_invocation != prepared["native_invocation"]:
                            raise LeaseGatewayError("application native dispatch changed")
                    finally:
                        connection.close()
                    # These bytes are private launch material. Recovery neither
                    # remints the capability nor returns another launch permit.
                    prepared["native_dispatch_capability"] = token
                    prepared["native_input_bytes"] = _application_native_payload(recipe, frozen)[0]
            return prepared
        except LeaseGatewayError:
            raise
        except Exception:
            raise LeaseGatewayError("application request refused") from None

    def authorize_native_dispatch(self, token, *, principal_id, caller_host, turn_id, request_id, invocation):
        """The incumbent authenticated controller join; no caller-selected key."""
        try:
            from lease_broker import Broker
            if type(self) is not GoLeaseGateway or type(self._application_owner()) is not Broker:
                raise LeaseGatewayError("application native owner unavailable")
            connection = self._connection()
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN")
                def request_lookup(principal, turn, request):
                    row = connection.execute("SELECT * FROM application_requests WHERE principal_id=? AND turn_id=? AND request_id=?",
                        (principal, turn, request)).fetchone()
                    return dict(row) if row is not None else None
                return authorize_native_dispatch(token, self._signing_key,
                    lambda lease: self._lease_lookup(connection, lease),
                    lambda principal, turn: self._application_turn_lookup(connection, principal, turn),
                    request_lookup, principal_id=principal_id, caller_host=caller_host, turn_id=turn_id,
                    request_id=request_id, invocation=invocation, now=self._clock())
            finally:
                connection.close()
        except Exception:
            raise LeaseGatewayError("application native dispatch refused") from None

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

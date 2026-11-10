"""Sealed HTTP realm/driver metadata compiler for the existing native generation.

Pure bytes-in/data-out: derives the immutable transport metadata of the
accepted fixed drivers in
``ops/native_fabric/quota_continuity/candidate/application_http_transports.py``
from the exact hash-pinned ``control_plane`` declarations, so the flat sealed
native generation carries the same source-bound identity without importing
the repository ``control_plane`` package at runtime.

Metadata only: no account, credential, capacity, readiness, grant,
enabled/qualified/requestable flag, permission or availability claim. The
input closure is exactly the three pinned byte strings; declarations are read
structurally with ``ast`` (no import/exec/eval, no caller-selected pin), and
``env_key`` carries the declared NAME whose value is never read. A schema,
commitment or closed-shape mismatch is a real refusal, never a weakened pin.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

SCHEMA = "mastermind.application_http_realms.v1"
SOURCE_COMMIT = "1fc6ebfc1ed340861feca069540d89a5a3288c27"

REALM_SOURCE_PATH = "control_plane/codex_provider_realm.py"
PROTOCOL_SOURCE_PATH = "control_plane/provider_protocols.py"
TRANSPORT_SOURCE_PATH = (
    "ops/native_fabric/quota_continuity/candidate/application_http_transports.py")

# Exact closed input closure: three full byte strings keyed by normalized
# repository-relative paths, pinned by complete Git blob identity and by the
# exact SHA-256 of those pinned bytes (the packet-supplied transports pin and
# the two values the pinned blobs themselves determine).
INPUT_SOURCES = (
    {"path": REALM_SOURCE_PATH,
     "git_blob_sha1": "eeea4c0fafc7e6df5c534c731cb6046bbe4d3f37",
     "sha256": "8587cdd50407b48e0f82ffe468ce0435a365b1ba97da8a2403d72c500c633ac6"},
    {"path": PROTOCOL_SOURCE_PATH,
     "git_blob_sha1": "92452237ac3956e8104e45ab9ee386c2fa016b76",
     "sha256": "1f4a51e4d7edbac3f4d1edd6205ca1a45e85c435952a64b891eeff4d4e2432f5"},
    {"path": TRANSPORT_SOURCE_PATH,
     "git_blob_sha1": "a116d8c671594552dd5c14f46f91981cd7c15f43",
     "sha256": "c009d7341d3abb83d1bd19f26465850fae375c5615b553924adfb9ae4bec4099"},
)

RESPONSES_PROTOCOL = "responses"
ENDPOINT_SUFFIX = "/responses"

MAX_OUTPUT_BYTES = 16384
MAX_STRING_CHARS = 256
MAX_MODELS = 16

_REALM_CLASS = "CodexProviderRealm"
_REVIEWED_REALMS = "REVIEWED_CODEX_PROVIDER_REALMS"
_PROTOCOL_SET = "PROVIDER_PROTOCOLS"
_TRANSPORT_PROTOCOL = "RESPONSES_PROTOCOL"
_IDENTITY_CALL = "DriverIdentity"
_FIXED_BASE = "_FixedResponsesDriver"
_DRIVER_CLASSES = ("BailianResponsesDriver", "MiniMaxResponsesDriver")
_REALM_STR_FIELDS = ("realm_id", "provider_alias", "display_name", "base_url",
                     "env_key", "wire_api")
_REALM_EMITTED_STR_FIELDS = ("realm_id", "provider_alias", "base_url",
                             "env_key", "wire_api")
_REALM_POLICY_FIELDS = ("requires_codex_auth_file", "interactive_subscription_only",
                        "request_max_retries", "stream_max_retries")
_DRIVER_STR_FIELDS = ("driver_id", "realm_id", "pool")
_ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_DRIVER_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class ProjectionRefused(ValueError):
    """A bounded refusal: malformed, drifted, ambiguous or unsupported input."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_inputs(inputs: Mapping[str, bytes]) -> dict[str, bytes]:
    """Snapshot once; every later parse and commitment uses these exact bytes."""
    if not isinstance(inputs, Mapping):
        raise ProjectionRefused("invalid_inputs")
    expected_paths = {entry["path"] for entry in INPUT_SOURCES}
    try:
        supplied_paths = set(inputs)
    except Exception:
        raise ProjectionRefused("invalid_inputs") from None
    if supplied_paths != expected_paths:
        raise ProjectionRefused("input_closure_mismatch")
    snapshot = {}
    for entry in INPUT_SOURCES:
        try:
            data = inputs[entry["path"]]
        except Exception:
            raise ProjectionRefused("invalid_inputs") from None
        if not isinstance(data, (bytes, bytearray)) or isinstance(data, memoryview):
            raise ProjectionRefused("invalid_input_bytes", entry["path"])
        data = bytes(data)
        if _git_blob_sha1(data) != entry["git_blob_sha1"]:
            raise ProjectionRefused("source_blob_mismatch", entry["path"])
        if _sha256(data) != entry["sha256"]:
            raise ProjectionRefused("source_sha256_mismatch", entry["path"])
        snapshot[entry["path"]] = data
    return snapshot


# ── bounded structural readers ───────────────────────────────────────────────


def _str_const(node: ast.AST, code: str) -> str:
    if isinstance(node, ast.Constant) and type(node.value) is str \
            and len(node.value) <= MAX_STRING_CHARS:
        return node.value
    raise ProjectionRefused(code, "non_constant_string")


def _opt_str_const(node: ast.AST, code: str):
    if isinstance(node, ast.Constant) and node.value is None:
        return None
    return _str_const(node, code)


def _typed_const(node: ast.AST, kind: type, code: str):
    if isinstance(node, ast.Constant) and type(node.value) is kind:
        return node.value
    raise ProjectionRefused(code, "non_constant_" + kind.__name__)


def _str_frozenset(node: ast.AST, code: str) -> frozenset:
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset" and not node.keywords
            and len(node.args) == 1
            and isinstance(node.args[0], (ast.Set, ast.List, ast.Tuple))):
        values = [_str_const(item, code) for item in node.args[0].elts]
        if values and len(set(values)) == len(values) <= MAX_MODELS:
            return frozenset(values)
    raise ProjectionRefused(code, "unsupported_collection")


def _module_bindings(tree: ast.Module, watched: tuple) -> dict:
    """Top-level single-binding map. Duplicate or shadowed watched names refuse."""
    bindings = {}
    watched_set = set(watched)
    for stmt in tree.body:
        names = []
        if isinstance(stmt, ast.Assign):
            names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) \
                and stmt.value is not None:
            names = [stmt.target.id]
        elif isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [stmt.name]
        for name in names:
            if name in bindings:
                if name in watched_set:
                    raise ProjectionRefused("duplicate_binding", name)
                continue
            bindings[name] = stmt
    return bindings


def _keyword_map(call: ast.Call, allowed: tuple) -> dict:
    """Constant-keyword arguments of one constructor call. No *args/**kwargs."""
    if call.args or any(kw.arg is None for kw in call.keywords):
        raise ProjectionRefused("positional_or_dynamic_argument")
    kwargs = {}
    for keyword in call.keywords:
        if keyword.arg in kwargs or keyword.arg not in allowed:
            raise ProjectionRefused("unsupported_keyword", keyword.arg or "")
        kwargs[keyword.arg] = keyword.value
    return kwargs


def _dataclass_flag(node: ast.ClassDef, code: str) -> None:
    for decorator in node.decorator_list:
        inner = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = inner.attr if isinstance(inner, ast.Attribute) else \
            inner.id if isinstance(inner, ast.Name) else None
        if name == "dataclass":
            return
    raise ProjectionRefused(code, "missing_dataclass_decorator")


# ── realm source extraction ──────────────────────────────────────────────────


def _realm_class_defaults(tree: ast.Module, bindings: dict) -> dict:
    stmt = bindings.get(_REALM_CLASS)
    if not isinstance(stmt, ast.ClassDef):
        raise ProjectionRefused("unsupported_realm_class")
    _dataclass_flag(stmt, "unsupported_realm_class")
    defaults = {}
    for member in stmt.body:
        if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name) \
                and member.target.id in _REALM_POLICY_FIELDS and member.value is not None:
            if member.target.id in defaults:
                raise ProjectionRefused("duplicate_class_attribute", member.target.id)
            kind = bool if member.target.id in _REALM_POLICY_FIELDS[:2] else int
            defaults[member.target.id] = _typed_const(member.value, kind,
                                                      "unsupported_realm_default")
    if set(defaults) != set(_REALM_POLICY_FIELDS):
        raise ProjectionRefused("missing_realm_policy_defaults")
    return defaults


def _realm_call(node: ast.AST, code: str, defaults: dict) -> dict:
    """One CodexProviderRealm(...) constructor with constant keyword values.

    Policy fields absent from the call keep the class's declared default;
    explicit overrides are read from the same declaration. No caller value.
    """
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == _REALM_CLASS):
        raise ProjectionRefused(code, "unsupported_realm_construct")
    kwargs = _keyword_map(node, _REALM_STR_FIELDS + _REALM_POLICY_FIELDS)
    record = {}
    for field in _REALM_EMITTED_STR_FIELDS:
        if field not in kwargs:
            raise ProjectionRefused(code, "missing_realm_field")
        record[field] = _str_const(kwargs[field], code)
    # display_name is declared but never emitted; read it to validate shape.
    if "display_name" in kwargs:
        _str_const(kwargs["display_name"], code)
    record["wire_api"] = record["wire_api"].strip().lower()
    policy = {}
    for field in _REALM_POLICY_FIELDS:
        kind = bool if field in _REALM_POLICY_FIELDS[:2] else int
        if field in kwargs:
            policy[field] = _typed_const(kwargs[field], kind,
                                         "unsupported_realm_policy")
        else:
            policy[field] = defaults[field]
    record["declared_realm_policy"] = policy
    return record


def _comprehension_realm_names(node: ast.AST) -> tuple:
    """Exactly ``{r.realm_id: r for r in (NAME, NAME)}`` over a literal tuple."""
    if not isinstance(node, ast.DictComp) or len(node.generators) != 1:
        raise ProjectionRefused("unsupported_reviewed_realms")
    generator = node.generators[0]
    if generator.ifs or not isinstance(generator.target, ast.Name):
        raise ProjectionRefused("unsupported_reviewed_realms")
    loop_var = generator.target.id
    if not isinstance(generator.iter, ast.Tuple):
        raise ProjectionRefused("dynamic_reviewed_realms")
    names = []
    for element in generator.iter.elts:
        if not isinstance(element, ast.Name):
            raise ProjectionRefused("dynamic_reviewed_realms")
        names.append(element.id)
    key = node.key
    if not (isinstance(key, ast.Attribute) and key.attr == "realm_id"
            and isinstance(key.value, ast.Name) and key.value.id == loop_var):
        raise ProjectionRefused("unsupported_reviewed_key")
    if not (isinstance(node.value, ast.Name) and node.value.id == loop_var):
        raise ProjectionRefused("unsupported_reviewed_value")
    return tuple(names)


def _extract_realms(tree: ast.Module) -> dict:
    bindings = _module_bindings(
        tree, (_REALM_CLASS, _REVIEWED_REALMS) + _DRIVER_CLASSES)
    reviewed = bindings.get(_REVIEWED_REALMS)
    if not isinstance(reviewed, ast.Assign) or len(reviewed.targets) != 1:
        raise ProjectionRefused("unsupported_reviewed_realms")
    names = _comprehension_realm_names(reviewed.value)
    defaults = _realm_class_defaults(tree, bindings)
    if len(set(names)) != len(names) or not names:
        raise ProjectionRefused("duplicate_reviewed_realm")
    realms = {}
    for name in names:
        stmt = bindings.get(name)
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            raise ProjectionRefused("unresolved_realm_binding", name)
        record = _realm_call(stmt.value, "unsupported_realm_construct", defaults)
        if record["realm_id"] in realms:
            raise ProjectionRefused("duplicate_realm_id", record["realm_id"])
        realms[record["realm_id"]] = {
            "realm_id": record["realm_id"],
            "provider_alias": record["provider_alias"],
            "base_url": record["base_url"],
            "env_key": record["env_key"],
            "wire_api": record["wire_api"],
            "declared_realm_policy": dict(record["declared_realm_policy"]),
        }
    return realms


def _extract_protocols(tree: ast.Module) -> frozenset:
    bindings = _module_bindings(tree, (_PROTOCOL_SET,))
    stmt = bindings.get(_PROTOCOL_SET)
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        raise ProjectionRefused("unsupported_protocol_vocabulary")
    return _str_frozenset(stmt.value, "unsupported_protocol_vocabulary")


# ── transport source extraction ──────────────────────────────────────────────


def _driver_class_record(node: ast.ClassDef, code: str) -> dict:
    seen = {}
    for member in node.body:
        if isinstance(member, ast.Assign):
            targets = [t.id for t in member.targets if isinstance(t, ast.Name)]
        elif isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name) \
                and member.value is not None:
            targets = [member.target.id]
        else:
            targets = []
        for name in targets:
            if name in seen:
                raise ProjectionRefused("duplicate_class_attribute", name)
            seen[name] = member
    record = {}
    for field in _DRIVER_STR_FIELDS:
        if field not in seen:
            raise ProjectionRefused(code, "missing_driver_attribute")
        record[field] = _str_const(seen[field].value, code)
    for field, reader in (("allowed_models", _str_frozenset),
                          ("default_model", _opt_str_const)):
        if field not in seen:
            raise ProjectionRefused(code, "missing_driver_attribute")
        record[field] = reader(seen[field].value, code)
    return record


def _extract_transports(tree: ast.Module) -> dict:
    bindings = _module_bindings(
        tree, (_TRANSPORT_PROTOCOL, _FIXED_BASE) + _DRIVER_CLASSES)
    protocol_const = bindings.get(_TRANSPORT_PROTOCOL)
    if not isinstance(protocol_const, ast.Assign) or len(protocol_const.targets) != 1 \
            or _str_const(protocol_const.value, "unsupported_transport_protocol") \
            != RESPONSES_PROTOCOL:
        raise ProjectionRefused("unsupported_transport_protocol")
    base = bindings.get(_FIXED_BASE)
    if not isinstance(base, ast.ClassDef):
        raise ProjectionRefused("unsupported_fixed_driver_base")
    init = next((m for m in base.body
                 if isinstance(m, ast.FunctionDef) and m.name == "__init__"), None)
    if init is None:
        raise ProjectionRefused("unsupported_fixed_driver_base")
    identities = [n for n in ast.walk(init)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == _IDENTITY_CALL]
    if len(identities) != 1:
        raise ProjectionRefused("ambiguous_identity_construction")
    keywords = identities[0].keywords
    endpoint = next((k.value for k in keywords if k.arg == "endpoint"), None)
    protocol_kw = next((k.value for k in keywords if k.arg == "protocol"), None)
    if not (isinstance(endpoint, ast.BinOp) and isinstance(endpoint.op, ast.Add)
            and isinstance(endpoint.left, ast.Attribute)
            and endpoint.left.attr == "base_url"
            and isinstance(endpoint.right, ast.Constant)
            and endpoint.right.value == ENDPOINT_SUFFIX):
        raise ProjectionRefused("unsupported_endpoint_derivation")
    if not isinstance(protocol_kw, ast.Name):
        raise ProjectionRefused("unsupported_protocol_derivation")
    drivers = {}
    for class_name in _DRIVER_CLASSES:
        stmt = bindings.get(class_name)
        if not isinstance(stmt, ast.ClassDef):
            raise ProjectionRefused("missing_driver_class", class_name)
        if not any(isinstance(b, ast.Name) and b.id == _FIXED_BASE
                   for b in stmt.bases):
            raise ProjectionRefused("unsupported_driver_base", class_name)
        record = _driver_class_record(stmt, "unsupported_driver_class")
        if record["driver_id"] in drivers:
            raise ProjectionRefused("duplicate_driver_id", record["driver_id"])
        drivers[record["driver_id"]] = record
    declared = sorted(n.name for n in ast.walk(tree)
                      if isinstance(n, ast.ClassDef)
                      and any(isinstance(b, ast.Name) and b.id == _FIXED_BASE
                              for b in n.bases))
    if declared != sorted(_DRIVER_CLASSES):
        raise ProjectionRefused("unexpected_driver_subclass")
    return {"drivers": drivers, "protocol": RESPONSES_PROTOCOL}


# ── projection assembly ──────────────────────────────────────────────────────


def _driver_projection(driver: dict, realm: dict, protocols: frozenset) -> dict:
    if realm["wire_api"] != RESPONSES_PROTOCOL or RESPONSES_PROTOCOL not in protocols:
        raise ProjectionRefused("unsupported_wire_protocol", realm["realm_id"])
    if _ENV_KEY_RE.fullmatch(realm["env_key"]) is None:
        raise ProjectionRefused("invalid_env_key_name", realm["realm_id"])
    base_url = realm["base_url"]
    if not base_url.startswith("https://") or base_url.endswith("/"):
        raise ProjectionRefused("invalid_base_url", realm["realm_id"])
    return {
        "driver_id": driver["driver_id"],
        "realm_id": realm["realm_id"],
        "provider": realm["provider_alias"],
        "pool": driver["pool"],
        "base_url": base_url,
        "endpoint": base_url + ENDPOINT_SUFFIX,
        "protocol": RESPONSES_PROTOCOL,
        "env_key": realm["env_key"],
        "allowed_models": sorted(driver["allowed_models"]),
        "default_model": driver["default_model"],
        "declared_realm_policy": dict(realm["declared_realm_policy"]),
    }


def _canonical_bytes(projection: Mapping[str, Any]) -> bytes:
    return json.dumps(projection, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _unfreeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {k: _unfreeze(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze(item) for item in value]
    return value


def _parse(data: bytes, path: str) -> ast.Module:
    try:
        return ast.parse(data.decode("utf-8"))
    except (ValueError, SyntaxError, UnicodeError, RecursionError):
        raise ProjectionRefused("unparsable_source", path) from None


def compile_projection(inputs: Mapping[str, bytes]) -> Mapping[str, Any]:
    """Compile the exact pinned source bytes into the frozen projection.

    Pure: bytes in, immutable mapping out. Any missing, extra, relabelled or
    drifted input, and any dynamic or ambiguous declaration in the closed
    source form, is a bounded refusal before any result exists.
    """
    inputs = _verify_inputs(inputs)
    realms = _extract_realms(_parse(inputs[REALM_SOURCE_PATH], REALM_SOURCE_PATH))
    protocols = _extract_protocols(
        _parse(inputs[PROTOCOL_SOURCE_PATH], PROTOCOL_SOURCE_PATH))
    transports = _extract_transports(
        _parse(inputs[TRANSPORT_SOURCE_PATH], TRANSPORT_SOURCE_PATH))
    compiled = {}
    for driver_id, driver in transports["drivers"].items():
        realm = realms.get(driver["realm_id"])
        if realm is None:
            raise ProjectionRefused("realm_owner_unavailable", driver["realm_id"])
        compiled[driver_id] = _driver_projection(driver, realm, protocols)
    if {record["realm_id"] for record in compiled.values()} != set(realms):
        raise ProjectionRefused("driver_realm_coverage")
    projection = {
        "schema": SCHEMA,
        "source_commit": SOURCE_COMMIT,
        "sources": [
            {"path": entry["path"], "git_blob_sha1": entry["git_blob_sha1"],
             "sha256": _sha256(inputs[entry["path"]])}
            for entry in sorted(INPUT_SOURCES, key=lambda item: item["path"])],
        "drivers": [compiled[driver_id] for driver_id in sorted(compiled)],
    }
    if len(_canonical_bytes(projection)) > MAX_OUTPUT_BYTES:
        raise ProjectionRefused("projection_too_large")
    return _freeze(projection)


def compile_projection_bytes(inputs: Mapping[str, bytes]) -> bytes:
    """Deterministic canonical UTF-8 JSON bytes of the projection."""
    return _canonical_bytes(_unfreeze(compile_projection(inputs)))


# ── strict readback validation ───────────────────────────────────────────────


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ProjectionRefused("duplicate_output_key", key)
        value[key] = item
    return value


def _exact_keys(value: Any, keys: tuple, code: str) -> None:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ProjectionRefused(code)


def _bounded_str(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING_CHARS:
        raise ProjectionRefused(code)
    return value


def _validate_v1_projection(payload: bytes, *, expected_sha256: str) -> Mapping[str, Any]:
    """Read generated bytes against a trusted exact artifact commitment.

    The existing builder must compile the pinned inputs and seal the resulting
    digest in the existing generation manifest. Startup supplies that digest
    only after verifying the generation. A digest taken from the supplied
    payload itself, a request or an unverified sidecar supplies no such trust.
    Source labels alone cannot authenticate the derived endpoint/model data.

    After the exact-byte check, verify the schema, source inventory, closed
    shapes, bounded values and ordering. This parser grants no execution or
    application permission and creates no durable owner.
    """
    if not isinstance(payload, (bytes, bytearray)) or isinstance(payload, memoryview):
        raise ProjectionRefused("invalid_projection_payload")
    payload = bytes(payload)
    if not payload or len(payload) > MAX_OUTPUT_BYTES:
        raise ProjectionRefused("projection_size")
    if (type(expected_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
        raise ProjectionRefused("invalid_projection_commitment")
    if _sha256(payload) != expected_sha256:
        raise ProjectionRefused("projection_commitment_mismatch")
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=lambda _v: (_ for _ in ()).throw(
                                  ProjectionRefused("nonfinite_output")))
    except ProjectionRefused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProjectionRefused("unparsable_projection") from None
    _exact_keys(document, ("schema", "source_commit", "sources", "drivers"),
                "unsupported_projection_shape")
    if document["schema"] != SCHEMA:
        raise ProjectionRefused("schema_mismatch")
    if document["source_commit"] != SOURCE_COMMIT:
        raise ProjectionRefused("source_commit_mismatch")
    sources = document["sources"]
    if not isinstance(sources, list) or len(sources) != len(INPUT_SOURCES):
        raise ProjectionRefused("unsupported_source_inventory")
    paths = []
    for entry, expected in zip(sources, sorted(INPUT_SOURCES,
                                               key=lambda item: item["path"])):
        _exact_keys(entry, ("path", "git_blob_sha1", "sha256"),
                    "unsupported_source_entry")
        path = _bounded_str(entry["path"], "unsupported_source_entry")
        paths.append(path)
        if path != expected["path"] or entry["git_blob_sha1"] != expected["git_blob_sha1"] \
                or entry["sha256"] != expected["sha256"]:
            raise ProjectionRefused("source_commitment_mismatch", path)
    if paths != sorted(paths):
        raise ProjectionRefused("unsorted_source_inventory")
    drivers = document["drivers"]
    if not isinstance(drivers, list) or len(drivers) != len(_DRIVER_CLASSES):
        raise ProjectionRefused("unsupported_driver_inventory")
    driver_ids = []
    for record in drivers:
        _exact_keys(record, _DRIVER_STR_FIELDS
                    + ("provider", "base_url", "endpoint", "protocol", "env_key",
                       "allowed_models", "default_model", "declared_realm_policy"),
                    "unsupported_driver_record")
        for field in _DRIVER_STR_FIELDS + ("provider", "base_url", "endpoint",
                                           "protocol"):
            _bounded_str(record[field], "unsupported_driver_record")
        for field in ("driver_id", "realm_id", "pool", "provider"):
            if _DRIVER_ID_RE.fullmatch(record[field]) is None \
                    and _ID_RE.fullmatch(record[field]) is None:
                raise ProjectionRefused("unsupported_driver_field", field)
        if (not isinstance(record["env_key"], str)
                or _ENV_KEY_RE.fullmatch(record["env_key"]) is None):
            raise ProjectionRefused("unsupported_env_key_name")
        if record["protocol"] != RESPONSES_PROTOCOL \
                or record["endpoint"] != record["base_url"] + ENDPOINT_SUFFIX:
            raise ProjectionRefused("unsupported_endpoint", record["driver_id"])
        models = record["allowed_models"]
        if not isinstance(models, list) or not models or len(models) > MAX_MODELS \
                or any(not isinstance(m, str) or not m or len(m) > MAX_STRING_CHARS
                       for m in models) or models != sorted(set(models)):
            raise ProjectionRefused("unsupported_allowed_models")
        default_model = record["default_model"]
        if default_model is not None:
            _bounded_str(default_model, "unsupported_default_model")
            if default_model not in models:
                raise ProjectionRefused("default_model_unqualified")
        _exact_keys(record["declared_realm_policy"], _REALM_POLICY_FIELDS,
                    "unsupported_realm_policy")
        policy = record["declared_realm_policy"]
        for field in _REALM_POLICY_FIELDS[:2]:
            if type(policy[field]) is not bool:
                raise ProjectionRefused("unsupported_realm_policy", field)
        # Preserved CodexProviderRealm constraints: no auth file,
        # interactive-subscription-only, and both retry budgets at zero.
        if policy["requires_codex_auth_file"] is not False \
                or policy["interactive_subscription_only"] is not True:
            raise ProjectionRefused("unsupported_realm_policy", "constraint")
        for field in _REALM_POLICY_FIELDS[2:]:
            if type(policy[field]) is not int or policy[field] != 0:
                raise ProjectionRefused("unsupported_realm_policy", field)
        driver_ids.append(record["driver_id"])
    if driver_ids != sorted(driver_ids) or len(set(driver_ids)) != len(driver_ids):
        raise ProjectionRefused("unsorted_driver_inventory")
    return _freeze(document)


__all__ = [
    "INPUT_SOURCES", "MAX_OUTPUT_BYTES", "ProjectionRefused", "SCHEMA",
    "SOURCE_COMMIT", "compile_projection", "compile_projection_bytes",
    "validate_projection",
]


# v2 extends this same projection owner; the v1 source commitment stays intact.
GLM_SCHEMA = "mastermind.application_http_realms.v2"
GLM_INPUT_PINS = (('ops/native_fabric/quota_continuity/source/glm_keys.py', '0d84fe666e8e2c1e29297a31a99ce225a30a832c20e9514a5afcb2816a38d458', 'd2c97617e60c85dfb463aaa8c03f09f7ffd37986'), ('ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py', 'd680789e7a184b7b882a57f6cc7b0337b6bebc4e27069ac8263aeffd456c5fed', '46693bd2b62f969879c94eb8f139b26d66ac6480'), ('ops/native_fabric/quota_continuity/candidate/application_http_transports.py', 'dab7542087c3bb19a74e35541f807c0aa4e791919e6f6286a371c12bccca8a1d', '63e3d9820d205eac31e471a0e3ddc86c04524111'))


def _glm_driver_record():
    return {
        "driver_id": "zai-coding-plan.chat-completions",
        "realm_id": "zai-coding-plan",
        "pool": "glm",
        "provider": "glm",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "endpoint": "https://api.z.ai/api/coding/paas/v4/chat/completions",
        "protocol": "openai-chat",
        "env_key": None,
        "credential_owner": "glm_keys.selected_account_key",
        "allowed_models": ["glm-5.3", "glm-5.3-flash"],
        "default_model": None,
    }


def _glm_sources():
    return [
        {"path": path, "sha256": digest, "git_blob_sha1": blob}
        for path, digest, blob in GLM_INPUT_PINS
    ]


def compile_glm_projection(
    inputs: Mapping[str, bytes], *, legacy_projection: bytes,
    legacy_sha256: str, source_commit: str,
) -> Mapping[str, Any]:
    """Compile the closed GLM successor with separate truthful source pins."""
    legacy = _unfreeze(_validate_v1_projection(legacy_projection, expected_sha256=legacy_sha256))
    if not isinstance(inputs, Mapping) or set(inputs) != {item[0] for item in GLM_INPUT_PINS}:
        raise ProjectionRefused("glm_source_inventory_mismatch")
    for path, digest, blob in GLM_INPUT_PINS:
        data = inputs[path]
        if (not isinstance(data, bytes) or _sha256(data) != digest
                or _git_blob_sha1(data) != blob):
            raise ProjectionRefused("glm_source_pin_mismatch")
    document = {
        "schema": GLM_SCHEMA,
        "legacy_projection": legacy,
        "glm_source_commit": source_commit,
        "glm_sources": _glm_sources(),
        "drivers": legacy["drivers"] + [_glm_driver_record()],
    }
    payload = _canonical_bytes(document)
    return validate_projection(payload, expected_sha256=_sha256(payload))


def compile_glm_projection_bytes(
    inputs: Mapping[str, bytes], *, legacy_projection: bytes,
    legacy_sha256: str, source_commit: str,
) -> bytes:
    return _canonical_bytes(_unfreeze(compile_glm_projection(
        inputs, legacy_projection=legacy_projection,
        legacy_sha256=legacy_sha256, source_commit=source_commit,
    )))


def _projection_nonfinite(_value):
    raise ProjectionRefused("projection_nonfinite")


def validate_projection(payload: bytes, *, expected_sha256: str) -> Mapping[str, Any]:
    """Verify the trusted full payload before selecting the versioned grammar."""
    if not isinstance(payload, (bytes, bytearray)) or isinstance(payload, memoryview):
        raise ProjectionRefused('invalid_projection_payload')
    payload = bytes(payload)
    if not payload or len(payload) > MAX_OUTPUT_BYTES:
        raise ProjectionRefused('projection_size')
    if type(expected_sha256) is not str or re.fullmatch('[0-9a-f]{64}', expected_sha256) is None:
        raise ProjectionRefused('invalid_projection_commitment')
    if _sha256(payload) != expected_sha256:
        raise ProjectionRefused('projection_commitment_mismatch')
    try:
        document = json.loads(payload.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=lambda _v: (_ for _ in ()).throw(ProjectionRefused('nonfinite_output')))
    except ProjectionRefused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProjectionRefused('unparsable_projection') from None
    if not isinstance(document, dict) or document.get('schema') != GLM_SCHEMA:
        return _validate_v1_projection(payload, expected_sha256=expected_sha256)
    _exact_keys(document, ('schema', 'legacy_projection', 'glm_source_commit', 'glm_sources', 'drivers'), 'schema_mismatch')
    commit = document['glm_source_commit']
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit) or commit == '0' * 40:
        raise ProjectionRefused('glm_source_commit_invalid')
    legacy_payload = _canonical_bytes(document['legacy_projection'])
    legacy = _unfreeze(_validate_v1_projection(legacy_payload, expected_sha256=_sha256(legacy_payload)))
    if document['glm_sources'] != _glm_sources():
        raise ProjectionRefused('glm_source_inventory_mismatch')
    if document['drivers'] != legacy['drivers'] + [_glm_driver_record()]:
        raise ProjectionRefused('glm_driver_identity_mismatch')
    return _freeze(document)

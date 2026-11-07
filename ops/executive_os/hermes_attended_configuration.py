"""Data-only Hermes configuration projection for the existing root installer.

The original native enrollment owner supplies current eligibility evidence.
This module neither issues grants nor publishes/selects configuration. The
incumbent installer and Control observation retain those responsibilities.
No projected Python is executed, and Broker admission remains mandatory.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import time

SCHEMA = "mastermind.hermes_attended_configuration/v1"
OBSERVATION_SCHEMA = "mastermind.application_consumer_observation.v1"
CONTROL_FIELD = "hermes_attended_configuration_sha256"
DIRECTORY = "hermes-attended"
CAPSULE_FILE = ".hermes-attended-configuration.json"
INVENTORY_FILE = ".hermes-attended-configuration-inventory.json"
MAX_BYTES = 4 * 1024 * 1024
FILES = (
    "config/capability_manifest.yml",
    "config/provider_production_modes.v1.json",
    "config/provider_workloads.v1.json",
)
INPUTS = (
    "engine/provider_production_modes.py",
    "engine/fabric_inference_client.py",
    "config/provider_production_modes.v1.json",
    "config/provider_workloads.v1.json",
)
_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


class ConfigurationError(ValueError):
    pass


def _refuse():
    raise ConfigurationError("hermes_attended_configuration_invalid")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def parse_json(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _refuse()
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                _refuse()
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: _refuse())
        canonical(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()


def _digest(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _identifier(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= 253402300799


def validate_observation(value, expected_digest, *, now=None):
    """Check a finite source-linked observation; its digest is not authority."""
    now = time.time() if now is None else now
    if (type(value) is not dict or set(value) != {
            "schema", "enrollment", "selected_source", "scope", "selection",
            "eligibility", "authority", "observation_sha256"}
            or value["schema"] != OBSERVATION_SCHEMA
            or not _digest(expected_digest)
            or value["observation_sha256"] != expected_digest
            or hashlib.sha256(canonical({k: v for k, v in value.items()
                                        if k != "observation_sha256"})).hexdigest() != expected_digest):
        _refuse()
    scope = value["scope"]
    if (type(scope) is not dict or set(scope) != {
            "service_profile", "principal_id", "caller_host", "native_host",
            "workload", "credential_ref", "capability_lane", "workload_profile"}
            or any(not _identifier(v) for v in scope.values())
            or scope["service_profile"] != "hermes-attended"
            or scope["principal_id"] != scope["service_profile"]
            or scope["capability_lane"] != scope["service_profile"]
            or scope["workload"] != "hermes_attended"
            or scope["workload_profile"] != scope["workload"]):
        _refuse()
    enrollment = value["enrollment"]
    if (type(enrollment) is not dict or set(enrollment) != {
            "owner", "schema", "operation_id", "plan_digest", "source_generation", "ingress_digest"}
            or enrollment["owner"] != "native_go_service_enrollment"
            or not _identifier(enrollment["operation_id"])
            or type(enrollment["schema"]) is not str
            or enrollment["schema"] != "native-go-service-enrollment-completed.v9"
            or any(not _digest(enrollment[k]) for k in
                   ("plan_digest", "source_generation", "ingress_digest"))):
        _refuse()
    selected = value["selected_source"]
    if (type(selected) is not dict or set(selected) != {"generation", "ingress_sha256", "selection"}
            or any(not _digest(selected[k]) for k in ("generation", "ingress_sha256"))):
        _refuse()
    if canonical(value["authority"]) != canonical({
            "grant_issued": False, "credential_included": False,
            "capacity_reserved": False, "provider_readiness_proven": False,
            "admission_required": True}):
        _refuse()
    eligibility = value["eligibility"]
    if (type(eligibility) is not dict or set(eligibility) != {
            "observed_at", "qualified_until", "routes"}
            or not _timestamp(eligibility["observed_at"])
            or not _timestamp(eligibility["qualified_until"])
            or not eligibility["observed_at"] <= now < eligibility["qualified_until"]
            or type(eligibility["routes"]) is not list
            or not 1 <= len(eligibility["routes"]) <= 256):
        _refuse()
    seen = set()
    for row in eligibility["routes"]:
        if (type(row) is not dict or set(row) != {
                "pool", "model", "grant_id", "grant_sha256", "expires_at",
                "qualification_ref", "application_permission_ref"}
                or any(not _identifier(row[k]) for k in
                       ("pool", "model", "grant_id", "qualification_ref", "application_permission_ref"))
                or not _digest(row["grant_sha256"])
                or not _timestamp(row["expires_at"])
                or row["expires_at"] <= now
                or (row["pool"], row["model"]) in seen):
            _refuse()
        seen.add((row["pool"], row["model"]))
    if eligibility["qualified_until"] != min(row["expires_at"] for row in eligibility["routes"]):
        _refuse()
    selection = value["selection"]
    if type(selection) is not dict or selection.get("kind") not in {"fixed", "auto"}:
        _refuse()
    if selection["kind"] == "fixed":
        if set(selection) != {"kind", "pool"} or selection["pool"] != "go":
            _refuse()
    else:
        route_scope = selection.get("route_scope")
        if (set(selection) != {"kind", "route_scope"} or type(route_scope) is not dict
                or set(route_scope) != {"schema", "pools"}
                or route_scope["schema"] != "mastermind.application_route_scope.v1"
                or type(route_scope["pools"]) is not list
                or not 1 <= len(route_scope["pools"]) <= 32
                or any(not _identifier(p) for p in route_scope["pools"])
                or route_scope["pools"] != sorted(set(route_scope["pools"]))
                or any(row["pool"] not in route_scope["pools"] for row in eligibility["routes"])):
            _refuse()
    return value


def _declarations(source):
    if type(source) is not bytes or not 0 < len(source) <= MAX_BYTES:
        _refuse()
    try:
        tree = ast.parse(source)
    except (ValueError, SyntaxError, RecursionError):
        _refuse()
    values, classes = {}, {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            values[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            values[node.target.id] = node.value
    return values, classes


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, RecursionError):
        _refuse()


def _record(values, classes, mapping, key, class_name):
    """Read literal owner declarations; do not import/execute source payload."""
    node = values.get(mapping)
    definition = classes.get(class_name)
    if not isinstance(node, ast.Dict) or not isinstance(definition, ast.ClassDef):
        _refuse()
    fields, defaults = [], {}
    for entry in definition.body:
        if isinstance(entry, ast.AnnAssign) and isinstance(entry.target, ast.Name):
            fields.append(entry.target.id)
            if entry.value is not None:
                defaults[entry.target.id] = _literal(entry.value)
    matches = [v for k, v in zip(node.keys, node.values) if _literal(k) == key]
    if (len(matches) != 1 or not isinstance(matches[0], ast.Call)
            or not isinstance(matches[0].func, ast.Name)
            or matches[0].func.id != class_name):
        _refuse()
    call = matches[0]
    if len(call.args) > len(fields) or any(isinstance(a, ast.Starred) for a in call.args):
        _refuse()
    assigned = dict(zip(fields, (_literal(v) for v in call.args)))
    for keyword in call.keywords:
        if keyword.arg not in fields or keyword.arg in assigned:
            _refuse()
        assigned[keyword.arg] = _literal(keyword.value)
    result = {**defaults, **assigned}
    if set(result) != set(fields):
        _refuse()
    return result


def derive_files(observation, inputs):
    if type(inputs) is not dict or set(inputs) != set(INPUTS):
        _refuse()
    values, classes = _declarations(inputs[INPUTS[0]])
    relation = _record(values, classes, "_SERVICE_FABRIC_RELATIONS",
                       "hermes_attended_fabric", "_ServiceFabricRelation")
    automatic = observation["selection"]["kind"] == "auto"
    transport_id = relation["automatic_transport_id" if automatic else "transport_id"]
    transport = _record(values, classes, "_APPLICATION_FABRIC_TRANSPORTS",
                        transport_id, "_ApplicationFabricTransport")
    identity = _literal(values.get("_APPLICATION_IDENTITY_FIELDS"))
    if (type(identity) is not tuple or len(identity) != 7
            or set(identity) != {"base_url", "secret_ref", "provider_id", "model",
                                 "cost_basis", "cap_id", "capability_id"}
            or relation["lane"] != observation["scope"]["capability_lane"]
            or relation["workload"] != observation["scope"]["workload"]
            or transport["secret_ref"] != observation["scope"]["credential_ref"]
            or transport["qualified"] is not True or transport["application_allowed"] is not True
            or transport["metadata_read"] is not False or transport["automatic"] is not automatic
            or transport["protocol"] != "native_application_v1"):
        _refuse()
    if automatic:
        client_values, _ = _declarations(inputs[INPUTS[1]])
        node = client_values.get("AUTO_POOLS")
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "frozenset" or len(node.args) != 1 or node.keywords:
            _refuse()
        pools = _literal(node.args[0])
        if any(p not in pools for p in observation["selection"]["route_scope"]["pools"]):
            _refuse()
    elif not any(row["pool"] == transport["provider_id"] and row["model"] == transport["model"]
                 for row in observation["eligibility"]["routes"]):
        _refuse()
    modes = parse_json(inputs["config/provider_production_modes.v1.json"])
    if type(modes) is not dict or type(modes.get("modes")) is not dict:
        _refuse()
    record = {key: transport[key] for key in identity}
    record.update(transport_id=transport_id, enabled=True, application_allowed=True,
                  qualification=_literal(values.get("PROFILE_QUALIFIED_CANARY")),
                  qualification_ref="enrollment-observation:" + observation["observation_sha256"],
                  qualified_until=observation["eligibility"]["qualified_until"])
    if automatic:
        record["route_scope"] = observation["selection"]["route_scope"]
    # This consumer view is used only by the attended factory. It does not
    # replace other applications' source or runtime configuration.
    modes["application_fabric_modes"] = {"hermes_attended_fabric": record}
    capability = {"capabilities": [{
        "capability_id": transport["capability_id"],
        "secret_ref": transport["secret_ref"], "kill_state": "active",
        "allowed_lanes": [relation["lane"]],
    }]}
    return {
        FILES[0]: canonical(capability) + b"\n",
        FILES[1]: canonical(modes) + b"\n",
        FILES[2]: inputs["config/provider_workloads.v1.json"],
    }


def build_capsule(observation, expected_observation_digest, source, inputs):
    validate_observation(observation, expected_observation_digest)
    files = derive_files(observation, inputs)
    return canonical({
        "schema": SCHEMA, "source": source, "observation": observation,
        "files": [{"path": name, "size": len(files[name]),
                   "sha256": hashlib.sha256(files[name]).hexdigest(),
                   "base64": base64.b64encode(files[name]).decode("ascii")} for name in FILES],
    }) + b"\n"


def validate_capsule(raw, expected_digest, source, inputs):
    if not _digest(expected_digest) or hashlib.sha256(raw).hexdigest() != expected_digest:
        _refuse()
    value = parse_json(raw)
    if (type(value) is not dict or set(value) != {"schema", "source", "observation", "files"}
            or value["schema"] != SCHEMA or value["source"] != source
            or canonical(value) + b"\n" != raw):
        _refuse()
    observation = value["observation"]
    validate_observation(observation, observation.get("observation_sha256") if type(observation) is dict else None)
    expected = build_capsule(observation, observation["observation_sha256"], source, inputs)
    if raw != expected:
        _refuse()
    return value, derive_files(observation, inputs)


def inventory_bytes(files, version_root):
    rows = [{"path": Path(name).name, "type": "file", "mode": 0o444,
             "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(files.items())]
    return canonical({"schema": "mastermind.hermes_native_dependencies/v1", "roots": [{
        "path": str(Path(version_root) / "config"), "entries": rows,
    }]}) + b"\n"

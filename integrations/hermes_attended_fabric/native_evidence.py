"""Read-only evidence from Hermes's existing profile and native SessionDB.

The execution facade uses this same projection as the native plugin. No
credentials, session rows, permissions, requests or workers are created here.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Mapping

from .native import MANUAL_POOLS, MODEL_ID, SessionGrant, TOOL, run_id_for

ENROLLMENT_SCHEMA = "mastermind.hermes_native_enrollment.v1"
ORIGIN_SCHEMA = "mastermind.hermes_native_origin.v1"
ORIGIN_KIND = "hermes_attended_session"
PLUGIN_ID = "mastermind-fabric-worker"
EXECUTION_SERVER = "mastermind-fabric-exec"
_MAX_COPIES = 256
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def native_root(contract: Mapping[str, Any], origin: str) -> str:
    return "hermes-session-" + digest(
        [contract["namespace"], contract["profile_id"], origin])[:40]


PLUGIN_SOURCE = ("https://github.com/mastermindx-market-intelligence/Mastermind.git"
                 "#integrations/hermes_attended_fabric")
RUNTIME_FILES = tuple(sorted((
    "__init__.py", "plugin.yaml", "native.py", "facade_port.py",
    "hermes_mcp_client.py", "native_session.py", "native_evidence.py",
    "enrollment_check.py",
)))


def package_fingerprint(directory: Path) -> str:
    """Closed runtime file projection; not a second installation manifest."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("HERMES_NATIVE_PACKAGE_PATH_REFUSED")
    if any(p.suffix in {".py", ".so", ".pyd"} and p.name not in RUNTIME_FILES
           for p in directory.iterdir()):
        raise ValueError("HERMES_NATIVE_PACKAGE_MEMBER_REFUSED")
    rows = []
    for name in RUNTIME_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("HERMES_NATIVE_PACKAGE_MEMBER_REFUSED")
        rows.append([name, hashlib.sha256(path.read_bytes()).hexdigest()])
    return digest(rows)


def installed_package_identity(home: Path) -> dict[str, str]:
    """Read the incumbent native installer record and actual package bytes."""
    plugins = home.resolve() / "plugins"
    if plugins.is_symlink() or not plugins.is_dir():
        raise ValueError("HERMES_NATIVE_PACKAGE_PATH_REFUSED")
    metadata_path = plugins / ".install-metadata.json"
    if (metadata_path.is_symlink() or not metadata_path.is_file()
            or metadata_path.stat().st_size > 1024 * 1024):
        raise ValueError("HERMES_NATIVE_INSTALL_RECORD_UNAVAILABLE")
    entry = json.loads(metadata_path.read_text()).get(PLUGIN_ID, {})
    revision = entry.get("revision")
    if (entry.get("source") != PLUGIN_SOURCE or entry.get("pinned") is not True
            or type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}", revision) is None):
        raise ValueError("HERMES_NATIVE_INSTALL_RECORD_REFUSED")
    return {"source_revision": revision,
            "package_sha256": package_fingerprint(plugins / PLUGIN_ID)}


def read_enrollment(home: Path) -> dict[str, Any]:
    from hermes_cli.config import load_config_observational
    from hermes_cli.config_read_errors import FailedConfigRead
    from hermes_cli.profiles import get_active_profile_name
    from hermes_constants import get_hermes_home, hermes_home_key

    if hermes_home_key(get_hermes_home()) != hermes_home_key(home):
        raise ValueError("NATIVE_PROFILE_SCOPE_MISMATCH")
    cfg = load_config_observational()
    if isinstance(cfg, FailedConfigRead) or type(cfg) is not dict:
        raise ValueError("HERMES_NATIVE_CURRENT_CONFIGURATION_UNAVAILABLE")
    plugins = cfg.get("plugins", {})
    if type(plugins) is not dict or type(plugins.get("entries", {})) is not dict:
        raise ValueError("HERMES_NATIVE_CURRENT_CONFIGURATION_UNAVAILABLE")
    entry = plugins.get("entries", {}).get(PLUGIN_ID, {})
    if type(entry) is not dict:
        raise ValueError("HERMES_NATIVE_CURRENT_CONFIGURATION_UNAVAILABLE")
    enabled, disabled, allowlist = (
        plugins.get("enabled", []), plugins.get("disabled", []),
        entry.get("mcp_allowlist", []))
    if any(type(value) is not list
           or any(type(item) is not str or not item or "${" in item for item in value)
           for value in (enabled, disabled, allowlist)):
        raise ValueError("HERMES_NATIVE_CURRENT_CONFIGURATION_UNAVAILABLE")
    origin = entry.get("native_origin", {})
    if (PLUGIN_ID not in enabled
            or PLUGIN_ID in disabled
            or EXECUTION_SERVER not in allowlist
            or type(origin) is not dict
            or origin.get("schema") != ENROLLMENT_SCHEMA
            or origin.get("enabled") is not True
            or type(origin.get("namespace")) is not str
            or _TOKEN.fullmatch(origin["namespace"]) is None):
        raise ValueError("HERMES_NATIVE_ORIGIN_NOT_ENROLLED")
    manual = entry.get("manual_routes", [])
    if (type(manual) is not list or len(manual) > 64
            or any(type(x) is not dict or set(x) != {"pool", "model"}
                   or x.get("pool") not in MANUAL_POOLS
                   or type(x.get("model")) is not str
                   or MODEL_ID.fullmatch(x["model"]) is None for x in manual)):
        raise ValueError("HERMES_NATIVE_MANUAL_ROUTES_INVALID")
    contract = {
        "schema": ENROLLMENT_SCHEMA, "enabled": True, "kind": ORIGIN_KIND,
        "profile_id": get_active_profile_name(),
        "namespace": origin["namespace"],
        "native_session_owner": "Hermes SessionDB",
        "request_admission_owner": "fabric_task.request",
        "root_policy": "native_conversation_namespace_v1",
        "manual_routes": sorted(manual, key=lambda x: (x["pool"], x["model"])),
        **installed_package_identity(home),
    }
    contract["generation"] = digest([hermes_home_key(home), contract])
    return contract


def _native_arguments(call: Any) -> dict[str, Any] | None:
    """Project one native intent without replacing its durable outer identity.

    Hermes's public lazy broker persists tool_call and forwards the original
    call ID with the single local entry's arguments. Batches, nested wrappers
    and legacy coercions are not native intent evidence.
    """
    if type(call) is not dict or type(call.get("function")) is not dict:
        return None
    function = call["function"]
    value = function.get("arguments")
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return None
    if type(value) is not dict:
        return None
    if function.get("name") == TOOL:
        return value
    if function.get("name") != "tool_call" or set(value) != {"calls"}:
        return None
    entries = value["calls"]
    if type(entries) is not list or len(entries) != 1:
        return None
    entry = entries[0]
    if (type(entry) is not dict or set(entry) != {"name", "arguments"}
            or entry["name"] != TOOL or type(entry["arguments"]) is not dict):
        return None
    return entry["arguments"]


def _calls(db: Any, session_ids: list[str], task_key: str,
           action: str) -> list[Any]:
    marks = ",".join("?" for _ in session_ids)
    # Candidate selection is conservative: retain matching broker compatibility
    # forms and batches as conflicts, although _native_arguments admits only the
    # canonical single local call. Filter by task before applying the copy bound.
    # The broker strips Python whitespace from names; SQLite trim needs that set.
    broker_space = (" \t\n\r\v\f\x1c\x1d\x1e\x1f\x85\xa0\u1680"
                    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
                    "\u2028\u2029\u202f\u205f\u3000")
    return db._read_all(
        f"""WITH durable AS (
                SELECT m.id, m.tool_call_uids, call.value AS tool_call,
                       json_extract(call.value, '$.function.name') AS name,
                       json_extract(call.value, '$.function.arguments') AS raw_args
                FROM messages AS m, json_each(m.tool_calls) AS call
                WHERE m.session_id IN ({marks})
            ), payloads AS (
                SELECT *, CASE WHEN json_valid(raw_args)
                               THEN raw_args ELSE '{{}}' END AS args
                FROM durable
            ), broker_raw AS (
                SELECT *, CASE WHEN json_extract(args, '$.calls') IS NULL
                    THEN json_object('name', json_extract(args, '$.name'),
                                     'arguments', json_extract(args, '$.arguments'))
                    ELSE json_extract(args, '$.calls') END AS raw_calls
                FROM payloads WHERE name='tool_call'
            ), broker_json AS (
                SELECT *, CASE WHEN json_valid(raw_calls)
                               THEN raw_calls ELSE '[]' END AS calls
                FROM broker_raw
            ), broker_entries AS (
                SELECT broker_json.id, broker_json.tool_call_uids, broker_json.tool_call,
                       CASE WHEN entry.type='object'
                            THEN entry.value ELSE '{{}}' END AS entry_json
                FROM broker_json, json_each(
                    CASE json_type(calls)
                        WHEN 'object' THEN json_array(json(calls))
                        WHEN 'array' THEN calls ELSE '[]' END) AS entry
            ), broker_args AS (
                SELECT id, tool_call_uids, tool_call,
                       trim(json_extract(entry_json, '$.name'), ?) AS entry_name,
                       CASE WHEN json_valid(json_extract(entry_json, '$.arguments'))
                            THEN json_extract(entry_json, '$.arguments')
                            ELSE '{{}}' END AS entry_args
                FROM broker_entries
            ), matches AS (
                SELECT id, tool_call_uids, tool_call FROM payloads
                WHERE name=? AND json_extract(args, '$.action')=?
                             AND json_extract(args, '$.task_key')=?
                UNION
                SELECT id, tool_call_uids, tool_call FROM broker_args
                WHERE entry_name=? AND json_extract(entry_args, '$.action')=?
                                   AND json_extract(entry_args, '$.task_key')=?
            )
            SELECT id, tool_call_uids, tool_call FROM matches
            ORDER BY id LIMIT ?""",
        (*session_ids, broker_space, TOOL, action, task_key, TOOL,
         action, task_key, _MAX_COPIES + 1))


def qualify_native_intent(db: Any, grant: SessionGrant, call_id: str,
                          arguments: Mapping[str, Any], *,
                          original_submit: bool) -> bool:
    """Qualify a canonical native occurrence; this is not an atomic claim.

    Hermes's single-use tool dispatch/resume lifecycle and Fabric's retained
    O_EXCL request remain the execution fences. Inactive/archived intents count.
    """
    ids = db._resume_lineage_ids(grant.session_id)
    if not ids or len(ids) >= 100 or ids[0] != grant.origin_session_id:
        return False
    rows = _calls(db, ids, arguments["task_key"], arguments["action"])
    if not rows or len(rows) > _MAX_COPIES:
        return False
    identities: dict[str, Any] = {}
    for row in rows:
        call = json.loads(row["tool_call"])
        if call.get("id") != call_id and not original_submit:
            continue
        uid = json.loads(row["tool_call_uids"] or "{}").get(call.get("id"))
        stored = _native_arguments(call)
        if (type(row["id"]) is not int or type(uid) is not str or not uid
                or call.get("id") != call_id or stored != dict(arguments)):
            return False
        if uid in identities and identities[uid] != stored:
            return False
        identities[uid] = stored
    if len(identities) != 1:
        return False
    marks = ",".join("?" for _ in ids)
    return db._read_one(
        f"SELECT 1 FROM messages WHERE session_id IN ({marks}) "
        "AND role='tool' AND tool_call_uid=? LIMIT 1",
        (*ids, next(iter(identities)))) is None


def evidence_for(active: Any, contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ORIGIN_SCHEMA, "kind": ORIGIN_KIND,
        "profile_id": active.grant.profile_id,
        "origin_session_id": active.grant.origin_session_id,
        "session_id": active.grant.session_id,
        "generation": active.grant.generation,
        "turn_id": active.turn_id, "tool_call_id": active.tool_call_id,
        "task_key": active.arguments["task_key"],
        "tool_action": active.arguments["action"],
        "arguments_digest": digest(active.arguments),
        "lease_holder_digest": hashlib.sha256(active.holder.encode()).hexdigest(),
        "enrollment_generation": contract["generation"],
    }


def verify_origin(home: Path, action: str, arguments: Mapping[str, Any],
                  contract: Mapping[str, Any]) -> None:
    """Existing facade's read-only, per-call native origin policy check."""
    from hermes_constants import hermes_home_key
    from hermes_state import SessionDB

    if action not in {"fabric_request", "fabric_status", "fabric_result"}:
        raise ValueError("HERMES_NATIVE_ACTION_REFUSED")
    proof = arguments.get("native_origin")
    fields = {
        "schema", "kind", "profile_id", "origin_session_id", "session_id",
        "generation", "turn_id", "tool_call_id", "task_key", "tool_action",
        "arguments_digest", "lease_holder_digest", "enrollment_generation",
    }
    if (type(proof) is not dict or set(proof) != fields
            or any(type(v) is not str or not 0 < len(v) <= 256 for v in proof.values())
            or proof["schema"] != ORIGIN_SCHEMA or proof["kind"] != ORIGIN_KIND
            or proof["profile_id"] != contract["profile_id"]
            or proof["enrollment_generation"] != contract["generation"]
            or proof["tool_action"] not in {"submit", "status", "result"}
            or (action == "fabric_request" and proof["tool_action"] != "submit")
            or (action == "fabric_result" and proof["tool_action"] != "result")):
        raise ValueError("HERMES_NATIVE_ORIGIN_REFUSED")
    root = native_root(contract, proof["origin_session_id"])
    grant = SessionGrant(
        profile_id=proof["profile_id"], session_id=proof["session_id"],
        root_id=root, parent_id=root, generation=proof["generation"],
        origin_session_id=proof["origin_session_id"])
    if (arguments.get("root_id") != root
            or arguments.get("run_id") != run_id_for(grant, proof["task_key"])
            or ("parent_id" in arguments and arguments["parent_id"] != root)):
        raise ValueError("HERMES_NATIVE_ROOT_REFUSED")
    path = home / "state.db"
    if not path.is_file() or path.is_symlink():
        raise ValueError("HERMES_NATIVE_OWNER_UNAVAILABLE")
    db = SessionDB(path, read_only=True)
    try:
        ids = db._resume_lineage_ids(grant.session_id)
        if (not ids or len(ids) >= 100 or ids[0] != grant.origin_session_id
                or db._session_turn_lease_key(grant.session_id) != grant.origin_session_id):
            raise ValueError("HERMES_NATIVE_LINEAGE_REFUSED")

        def current():
            row = db.get_session(grant.session_id)
            lease = db._read_one(
                "SELECT holder,expires_at FROM session_turn_leases WHERE conversation_id=?",
                (grant.origin_session_id,))
            if (not row or row.get("source") not in {"cli", "tui", "gui", "desktop", "local"}
                    or not lease or lease["expires_at"] <= time.time()
                    or hashlib.sha256(lease["holder"].encode()).hexdigest()
                    != proof["lease_holder_digest"]):
                raise ValueError("HERMES_NATIVE_TURN_REVOKED")
            generation = hashlib.sha256(json.dumps(
                [hermes_home_key(home), lease["holder"], proof["turn_id"],
                 row["runtime_generation"]], separators=(",", ":")).encode()).hexdigest()
            if generation != proof["generation"]:
                raise ValueError("HERMES_NATIVE_GENERATION_REFUSED")

        current()
        rows = _calls(db, ids, proof["task_key"], proof["tool_action"])
        candidates = []
        for row in rows:
            call = json.loads(row["tool_call"])
            if call.get("id") == proof["tool_call_id"]:
                candidates.append(_native_arguments(call))
        if (not candidates or len(rows) > _MAX_COPIES
                or any(type(x) is not dict or digest(x) != proof["arguments_digest"]
                       for x in candidates)):
            raise ValueError("HERMES_NATIVE_INTENT_REFUSED")
        native_args = candidates[0]
        if not qualify_native_intent(
                db, grant, proof["tool_call_id"], native_args,
                original_submit=action == "fabric_request"):
            raise ValueError("HERMES_NATIVE_ORIGINAL_INTENT_REFUSED")
        if action == "fabric_request":
            pool, model = native_args.get("pool"), native_args.get("model")
            routes = contract["manual_routes"]
            if pool is not None and (pool not in {x["pool"] for x in routes}
                    or (model is not None and model.lower() != "auto"
                        and {"pool": pool, "model": model} not in routes)):
                raise ValueError("HERMES_NATIVE_MANUAL_ROUTE_REFUSED")
            expected = {"run_id", "root_id", "parent_id", "task_class",
                        "task_complexity", "work_packet", "native_origin",
                        "escalation_reason", "pool", "model"}
            if set(arguments) - expected:
                raise ValueError("HERMES_NATIVE_REQUEST_FIELDS_REFUSED")
            for field in ("task_class", "task_complexity", "work_packet",
                          "escalation_reason", "pool", "model"):
                default = "" if field == "escalation_reason" else None
                if arguments.get(field, default) != native_args.get(field, default):
                    raise ValueError("HERMES_NATIVE_ARGUMENTS_CHANGED")
        current()
    finally:
        db.close()

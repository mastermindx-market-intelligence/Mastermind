"""Exact adopted Agent OS bytes, issued only by the incumbent installed reader.

This is a content facade, not a grant, compiler, memory store or latest-DATA read.
The integration owns source/runtime qualification and nominal reader issuance.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from common.workspace_project_plan_contract import validate_selection

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SCHEMA = "mastermind.agentos_adopted_context_receipt.v1"
SOURCE_MODE = "ADOPTED_SNAPSHOT"
CURRENT_RECEIPT_SCHEMA = "mastermind.agentos_current_context_receipt.v1"
CURRENT_RECEIPT_SCHEMA_V2 = "mastermind.agentos_current_context_receipt.v2"
CURRENT_SOURCE_MODE = "CANONICAL_PROJECT_DATA"
IMPORT_POLICY = "qualified_runtime_paths_v1"
DEADLINE_SEMANTICS = "cooperative_result_deadline_v1"
TOKEN_BUDGET = 4000
MAX_BUNDLE_BYTES = 128 * 1024
MAX_RECEIPT_BYTES = 16 * 1024
MAX_COMPILER_SOURCE_BYTES = 1024 * 1024
MAX_RECORD_SOURCE_BYTES = MAX_COMPILER_SOURCE_BYTES
MAX_RECORD_INVENTORY_BYTES = 6 * 1024
RECORD_INVENTORY_SCHEMA = "mastermind.agentos_selected_record_sources.v1"
RECORD_INVENTORY_SCOPE = "SELECTED_DIRECT_RECORD_CONTRIBUTIONS"
RECORD_REPOSITORY = "mastermindx-market-intelligence/macro"
REQUIRED_COMPILER_PATHS = frozenset({"scripts/agentos.py", "scripts/agentos_project_plan_contract.py"})
_RECEIPT_FIELDS = frozenset({
    "schema", "owner", "source_mode", "workstream", "token_budget", "bundle_sha256",
    "source_script_sha256", "compiler_sources", "compiler_closure_sha256", "source_inventory_sha256",
    "source_inventory_files", "mastermind_source_sha", "compiler_code_commit", "data_commit", "repo_sha",
    "runtime_commitment", "generated_at", "degraded_count", "omitted_count", "execution_authority",
    "compiler_sources_scope", "import_policy", "source_observation", "deadline_semantics",
})
_RUNTIME_FIELDS = frozenset({"owner", "python_version", "python_binary_sha256", "pyyaml_version",
                             "pyyaml_record_sha256", "runtime_tree_sha256"})
_CURRENT_FIELDS = _RECEIPT_FIELDS | {"data_observation"}
_CURRENT_FIELDS_V2 = _CURRENT_FIELDS | {"selected_record_sources"}
_ITEM_FIELDS = frozenset({"kind", "key", "path", "locator", "authority_class",
                         "status", "updated", "excerpt", "why_included"})
_RECORD_KINDS = {
    "workstream": ("workstream", "workstreams", "WS"),
    "constraint": ("workstream", "workstreams", "WS"),
    "dependency": ("workstream", "workstreams", "WS"),
    "decision": ("decisions", "decisions", "DEC"),
    "discovery": ("discoveries", "discoveries", "DSC"),
    "handoff": ("handoff", "handoffs", "WS"),
}
_INVENTORY_FIELDS = frozenset({"schema", "scope", "coverage", "retention", "overflow_reason",
    "repository", "data_commit", "bundle_sha256", "selected_items", "retained_items",
    "omitted_items", "entries", "inventory_sha256"})


class AgentOsContextUnavailable(ValueError):
    pass


def _refuse():
    raise AgentOsContextUnavailable("SOURCE_UNAVAILABLE")


def _hex(value, size):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8", "strict")).hexdigest()


def compiler_closure_digest(sources, runtime, source_inventory_sha256):
    return canonical_digest({"compiler_sources": sources, "runtime_commitment": runtime,
                             "source_inventory_sha256": source_inventory_sha256})


def selected_record_uses(bundle, *, work_ref):
    """Locate only qualified compiler direct-record contributions, never compile.

    Item paths name the authored source of a contribution, not all provenance
    of that item or proof that the whole document was rendered. Accounting
    tails, auxiliary higher-law joins and artifact pointers are not included.
    """
    if (type(bundle) is not dict or bundle.get("schema") != "context_bundle.v1"
            or type(bundle.get("target")) is not dict or bundle["target"].get("workstream") != work_ref
            or type(bundle.get("sections")) is not list):
        _refuse()
    uses, sections = {}, set()
    for section_index, section in enumerate(bundle["sections"]):
        if (type(section) is not dict or type(section.get("id")) is not str
                or section["id"] in sections or type(section.get("items")) is not list):
            _refuse()
        sections.add(section["id"])
        for item_index, item in enumerate(section["items"]):
            if type(item) is not dict or type(item.get("kind")) is not str:
                _refuse()
            kind = item["kind"]
            if kind not in _RECORD_KINDS:
                if kind in {"dnr", "p0", "program", "artifact"}:
                    continue
                _refuse()
            section_id, directory, prefix = _RECORD_KINDS[kind]
            if (set(item) != _ITEM_FIELDS or section["id"] != section_id
                    or type(item["path"]) is not str or type(item["key"]) is not str
                    or re.fullmatch(prefix + r":[A-Z0-9]+(?:-[A-Z0-9]+)*", item["key"]) is None
                    or any(type(item[key]) is not str for key in
                           ("locator", "excerpt", "authority_class", "status", "why_included"))
                    or item["updated"] is not None and type(item["updated"]) is not str):
                _refuse()
            path = item["path"]
            if (len(path.encode("utf-8", "strict")) > 256 or "\\" in path
                    or any(ord(char) < 32 or ord(char) == 127 for char in path)
                    or len(path.split("/")) != 3 or path.split("/")[:2] != ["agentos", directory]
                    or not path.endswith(".md") or path.split("/")[2] in {".md", "..md"}
                    or item["locator"] not in ({path + "#landmines", path + "#do_not_redo"}
                        if kind == "constraint" else {path + "#frontmatter"})):
                _refuse()
            if kind == "handoff":
                # Handoffs are keyed by their direct-child filename; the item
                # key is the associated workstream, not an invented HND key.
                if item["key"] != work_ref:
                    _refuse()
            elif path != "agentos/" + directory + "/" + item["key"].replace(":", "-", 1) + ".md":
                _refuse()
            if kind in {"workstream", "constraint"} and item["key"] != work_ref:
                _refuse()
            if item["excerpt"].strip():
                uses.setdefault(path, []).append([section_index, item_index])
    return {path: uses[path] for path in sorted(uses)}


def record_source_inventory(*, bundle_sha256, data_commit, selected_items, entries,
                            overflow_reason=None):
    """Seal bounded evidence supplied by the incumbent installed capture."""
    retained = sum(len(entry["uses"]) for entry in entries)
    value = {"schema": RECORD_INVENTORY_SCHEMA, "scope": RECORD_INVENTORY_SCOPE,
        "coverage": "PARTIAL", "retention": "COMPLETE" if overflow_reason is None else "OVERFLOW",
        "overflow_reason": overflow_reason, "repository": RECORD_REPOSITORY,
        "data_commit": data_commit, "bundle_sha256": bundle_sha256,
        "selected_items": selected_items, "retained_items": retained,
        "omitted_items": selected_items - retained, "entries": entries}
    return {**value, "inventory_sha256": canonical_digest(value)}


def validate_retained_record_sources(value, *, bundle_sha256, data_commit):
    """Validate retained evidence without rereading or recreating its context.

    This proves shape, digest and supplied bindings only. Live issuance also
    checks exact selected positions; a historical caller must join original
    delivery/request custody before claiming that any contribution was sent.
    """
    if type(value) is not dict or set(value) != _INVENTORY_FIELDS:
        _refuse()
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8", "strict")
    if (len(encoded) > MAX_RECORD_INVENTORY_BYTES or value["schema"] != RECORD_INVENTORY_SCHEMA
            or value["scope"] != RECORD_INVENTORY_SCOPE or value["coverage"] != "PARTIAL"
            or value["repository"] != RECORD_REPOSITORY or value["data_commit"] != data_commit
            or not _hex(data_commit, 40) or not _hex(bundle_sha256, 64)
            or value["bundle_sha256"] != bundle_sha256
            or not _hex(value["inventory_sha256"], 64)
            or value["inventory_sha256"] != canonical_digest({k: v for k, v in value.items() if k != "inventory_sha256"})
            or type(value["entries"]) is not list
            or any(type(value[key]) is not int or not 0 <= value[key] <= MAX_BUNDLE_BYTES
                   for key in ("selected_items", "retained_items", "omitted_items"))
            or value["selected_items"] != value["retained_items"] + value["omitted_items"]):
        _refuse()
    if value["retention"] == "OVERFLOW":
        # No arbitrary retained prefix can look like a complete source set.
        if (value["overflow_reason"] not in {"INVENTORY_BYTES", "RECORD_BYTES"}
                or not value["selected_items"] or value["entries"] or value["retained_items"]):
            _refuse()
        return value
    if (value["retention"] != "COMPLETE" or value["overflow_reason"] is not None
            or value["omitted_items"]):
        _refuse()
    paths, positions = [], set()
    retained = 0
    for entry in value["entries"]:
        if (type(entry) is not dict or set(entry) != {"path", "mode", "git_blob", "sha256", "bytes", "uses"}
                or type(entry["path"]) is not str or entry["mode"] not in {"100644", "100755"}
                or not _hex(entry["git_blob"], 40) or not _hex(entry["sha256"], 64)
                or type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_RECORD_SOURCE_BYTES
                or type(entry["uses"]) is not list or not entry["uses"]
                or any(type(pair) is not list or len(pair) != 2
                       or any(type(x) is not int or not 0 <= x < MAX_BUNDLE_BYTES for x in pair)
                       for pair in entry["uses"])):
            _refuse()
        path = entry["path"]
        parts = path.split("/")
        if (len(path.encode("utf-8", "strict")) > 256 or "\\" in path
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or len(parts) != 3 or parts[0] != "agentos"
                or parts[1] not in {"workstreams", "decisions", "discoveries", "handoffs"}
                or not parts[2].endswith(".md") or parts[2] in {".md", "..md"}):
            _refuse()
        if parts[1] != "handoffs":
            prefix = {"workstreams": "WS", "decisions": "DEC", "discoveries": "DSC"}[parts[1]]
            if re.fullmatch(prefix + r"-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md", parts[2]) is None:
                _refuse()
        uses = [tuple(pair) for pair in entry["uses"]]
        if uses != sorted(set(uses)) or positions.intersection(uses):
            _refuse()
        paths.append(path)
        positions.update(uses)
        retained += len(uses)
    if paths != sorted(set(paths)) or retained != value["retained_items"]:
        _refuse()
    return value


def validate_record_source_inventory(value, *, raw, bundle, work_ref, data_commit):
    validate_retained_record_sources(value, bundle_sha256=hashlib.sha256(raw).hexdigest(), data_commit=data_commit)
    expected_uses = selected_record_uses(bundle, work_ref=work_ref)
    if value["selected_items"] != sum(map(len, expected_uses.values())):
        _refuse()
    if value["retention"] == "OVERFLOW":
        return value
    if len(value["entries"]) != len(expected_uses):
        _refuse()
    for entry, path in zip(value["entries"], expected_uses):
        if entry["path"] != path or entry["uses"] != expected_uses[path]:
            _refuse()
    return value


def validate_context_read(raw, receipt, *, work_ref):
    """Validate the closed owner receipt without changing the exact bundle bytes."""
    return _validate_context_read(raw, receipt, work_ref=work_ref, current=False)


def validate_current_context_read(raw, receipt, *, work_ref):
    """Validate explicitly current DATA, never reinterpret an adopted v1 read."""
    return _validate_context_read(raw, receipt, work_ref=work_ref, current=True)


def _validate_context_read(raw, receipt, *, work_ref, current):
    validate_selection({"work_ref": work_ref})
    version2 = current and type(receipt) is dict and receipt.get("schema") == CURRENT_RECEIPT_SCHEMA_V2
    fields = _CURRENT_FIELDS_V2 if version2 else _CURRENT_FIELDS if current else _RECEIPT_FIELDS
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE_BYTES
            or type(receipt) is not dict or receipt.keys() != fields):
        _refuse()
    try:
        raw.decode("utf-8", "strict")
        encoded = json.dumps(receipt, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8", "strict")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()
    if (len(encoded) > MAX_RECEIPT_BYTES
            or receipt["schema"] != (CURRENT_RECEIPT_SCHEMA_V2 if version2 else CURRENT_RECEIPT_SCHEMA if current else RECEIPT_SCHEMA)
            or receipt["owner"] != "agent_os"
            or receipt["source_mode"] != (CURRENT_SOURCE_MODE if current else SOURCE_MODE)
            or receipt["compiler_sources_scope"] != "fixed_macro_entry_and_helper"
            or receipt["import_policy"] != IMPORT_POLICY or receipt["deadline_semantics"] != DEADLINE_SEMANTICS
            or receipt["workstream"] != work_ref or type(receipt["token_budget"]) is not int
            or receipt["token_budget"] != TOKEN_BUDGET or receipt["execution_authority"] is not False
            or receipt["bundle_sha256"] != hashlib.sha256(raw).hexdigest()):
        _refuse()
    for field in ("mastermind_source_sha", "compiler_code_commit", "data_commit", "repo_sha"):
        if not _hex(receipt[field], 40): _refuse()
    if (receipt["data_commit"] != receipt["repo_sha"]
            or (not current and receipt["compiler_code_commit"] != receipt["data_commit"])):
        _refuse()
    if current:
        from common.canonical_project_data_observation_contract import validate
        try:
            observation = validate(receipt["data_observation"])
        except (ValueError, TypeError):
            _refuse()
        if (observation["executable_macro_commit"] != receipt["compiler_code_commit"]
                or observation["canonical_data_commit"] != receipt["data_commit"]
                or "data_continuity" in observation):
            _refuse()
        if (observation["source_operation"] is not None
                and observation["source_operation"]["selection"]["work_ref"] != work_ref):
            _refuse()
    if not _hex(receipt["source_inventory_sha256"], 64): _refuse()
    seals = receipt["source_observation"]
    if (type(seals) is not dict or seals.keys() != {"mastermind_generation", "macro_generation", "materialized_generation"}
            or any(not _hex(value, 64) for value in seals.values())): _refuse()
    for field in ("source_inventory_files", "degraded_count", "omitted_count"):
        if type(receipt[field]) is not int or not 0 <= receipt[field] <= 100000: _refuse()
    runtime = receipt["runtime_commitment"]
    if type(runtime) is not dict or runtime.keys() != _RUNTIME_FIELDS or runtime["owner"] != "cf2_capacity_runtime":
        _refuse()
    for field in ("python_binary_sha256", "pyyaml_record_sha256", "runtime_tree_sha256"):
        if not _hex(runtime[field], 64): _refuse()
    for field in ("python_version", "pyyaml_version"):
        if type(runtime[field]) is not str or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", runtime[field]) is None:
            _refuse()
    sources = receipt["compiler_sources"]
    if type(sources) is not list or len(sources) != 2: _refuse()
    paths = []
    for source in sources:
        if type(source) is not dict or source.keys() != {"path", "mode", "git_blob", "sha256", "bytes"}: _refuse()
        path = source["path"]
        if (type(path) is not str or not path or len(path.encode("utf-8", "strict")) > 256
                or "\\" in path or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or PurePosixPath(path).is_absolute() or any(part in ("", ".", "..") for part in path.split("/"))
                or not path.endswith(".py") or source["mode"] not in ("100644", "100755")
                or not _hex(source["git_blob"], 40) or not _hex(source["sha256"], 64)
                or type(source["bytes"]) is not int or not 0 <= source["bytes"] <= MAX_COMPILER_SOURCE_BYTES):
            _refuse()
        paths.append(path)
    if paths != sorted(REQUIRED_COMPILER_PATHS): _refuse()
    script = next(source for source in sources if source["path"] == "scripts/agentos.py")
    if receipt["source_script_sha256"] != script["sha256"]: _refuse()
    if receipt["compiler_closure_sha256"] != compiler_closure_digest(sources, runtime, receipt["source_inventory_sha256"]):
        _refuse()
    stamp = receipt["generated_at"]
    try:
        if type(stamp) is not str or not 0 < len(stamp) <= 40: _refuse()
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.utcoffset() is None: _refuse()
    except (TypeError, ValueError):
        _refuse()
    if version2:
        from ops.fabric_launch.agentos import validate_bundle
        try:
            bundle = validate_bundle(raw, work_ref)
            if (bundle.get("repo_sha") != receipt["data_commit"]
                    or type(bundle.get("token_budget")) is not int or bundle["token_budget"] != receipt["token_budget"]
                    or bundle.get("generated_at") != receipt["generated_at"]
                    or len(bundle["degraded"]) != receipt["degraded_count"]
                    or len(bundle["omitted_due_to_budget"]) != receipt["omitted_count"]):
                _refuse()
            validate_record_source_inventory(receipt["selected_record_sources"], raw=raw,
                bundle=bundle, work_ref=work_ref, data_commit=receipt["data_commit"])
        except (ValueError, TypeError, UnicodeError, RecursionError, KeyError):
            _refuse()
    return raw, receipt


class AgentOsContextBundleReader:
    def __init__(self, *, macro_root: Path):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute(): _refuse()
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in (
            "_source_root", "_macro_root", "_code_root", "_python",
            "_expected_source_sha", "_allow_synthetic_fixture"))

    def read(self, *, work_ref: str):
        from control_plane.installed_project_read_binding import InstalledProjectReadUnavailable, read_installed_project_binding
        validate_selection({"work_ref": work_ref})
        try:
            value = read_installed_project_binding(self, kind="agentos_context", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            _refuse()
        if type(value) is not tuple or len(value) != 2: _refuse()
        return validate_context_read(*value, work_ref=work_ref)

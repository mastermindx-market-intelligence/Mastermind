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
CURRENT_SOURCE_MODE = "CANONICAL_PROJECT_DATA"
IMPORT_POLICY = "qualified_runtime_paths_v1"
DEADLINE_SEMANTICS = "cooperative_result_deadline_v1"
TOKEN_BUDGET = 4000
MAX_BUNDLE_BYTES = 128 * 1024
MAX_RECEIPT_BYTES = 16 * 1024
MAX_COMPILER_SOURCE_BYTES = 1024 * 1024
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


def validate_context_read(raw, receipt, *, work_ref):
    """Validate the closed owner receipt without changing the exact bundle bytes."""
    return _validate_context_read(raw, receipt, work_ref=work_ref, current=False)


def validate_current_context_read(raw, receipt, *, work_ref):
    """Validate explicitly current DATA, never reinterpret an adopted v1 read."""
    return _validate_context_read(raw, receipt, work_ref=work_ref, current=True)


def _validate_context_read(raw, receipt, *, work_ref, current):
    validate_selection({"work_ref": work_ref})
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE_BYTES
            or type(receipt) is not dict or receipt.keys() != (_CURRENT_FIELDS if current else _RECEIPT_FIELDS)):
        _refuse()
    try:
        raw.decode("utf-8", "strict")
        encoded = json.dumps(receipt, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8", "strict")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()
    if (len(encoded) > MAX_RECEIPT_BYTES
            or receipt["schema"] != (CURRENT_RECEIPT_SCHEMA if current else RECEIPT_SCHEMA)
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

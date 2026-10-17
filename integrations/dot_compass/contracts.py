"""Closed Dot R0 public contracts. No filesystem, network, SDK or authority grants."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any, Mapping

SERVER_VERSION = "0.1.0"
RESULT_SCHEMA = "mastermind.dot_read_result.v1"
MAX_OUTPUT_BYTES = 16384
MAX_RESULT_LINES = 150
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,159}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SYMBOL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,95}$")
ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    profile: str
    owner: str
    scope: str
    description: str
    fields: tuple[tuple[str, str, bool], ...] = ()


# One fixed profile per deployed/read-authorized app: never publish a universal
# endpoint whose model-selected arguments can cross privilege domains.
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("dot_company_snapshot", "compass", "executive", "mastermind.executive.read", "Read the current Executive company boot packet through the incumbent Executive reader."),
    ToolSpec("dot_attention_snapshot", "compass", "executive", "mastermind.executive.read", "Read current Executive attention through the incumbent Executive reader."),
    ToolSpec("dot_operation_context", "compass", "agent_os", "mastermind.agentos.read", "Read one exact Agent OS operation context and continuation evidence.", (("operation_ref", "ref", True),)),
    ToolSpec("dot_capability_health", "compass", "cap1", "mastermind.capability.read", "Read owner-attributed CAP1 availability and permitted action class.", (("capability", "token", False),)),
    ToolSpec("dot_changed_since", "compass", "source_diff", "mastermind.source.read", "Read bounded canonical changes between two immutable revisions.", (("baseline_sha", "sha", True), ("current_sha", "sha", True))),
    ToolSpec("dot_code_impact", "code_ci", "codeintel", "mastermind.codeintel.read", "Find bounded, revision-pinned code dependency evidence for one symbol.", (("symbol", "symbol", True), ("revision_sha", "sha", True))),
    ToolSpec("dot_ci_diagnosis", "code_ci", "github", "mastermind.github.read", "Read one workflow run diagnosis from the GitHub evidence owner.", (("run_id", "numeric", True),)),
    ToolSpec("dot_fleet_health", "ops", "fleet", "mastermind.fleet.read", "Read owner-recorded fleet telemetry; no shell, file or credential access."),
    ToolSpec("dot_runner_diagnosis", "ops", "runner", "mastermind.runner.read", "Explain one pinned workflow run's runner eligibility from owner facts.", (("run_id", "numeric", True),)),
    ToolSpec("dot_product_proof", "product", "browser", "mastermind.browser.read", "Read the already-admitted browser proof artifact for one opaque artifact reference.", (("artifact_ref", "ref", True),)),
    ToolSpec("dot_signal_evidence", "market", "data_os", "mastermind.data.read", "Read point-in-time signal evidence with a caller-specified as-of UTC timestamp.", (("signal_ref", "ref", True), ("asof", "utc", True))),
)
PROFILES = tuple(sorted(set(t.profile for t in TOOL_SPECS)))
TOOLS = {t.name: t for t in TOOL_SPECS}


class DotRefusal(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _text(value: Any, kind: str) -> str:
    if type(value) is not str or value != value.strip() or not value:
        raise DotRefusal("invalid_input")
    pat = {"ref": REF_PATTERN, "token": REF_PATTERN, "sha": SHA_PATTERN,
           "symbol": SYMBOL_PATTERN, "numeric": re.compile(r"^[1-9][0-9]{0,17}$"),
           "utc": ISO_PATTERN}[kind]
    if pat.fullmatch(value) is None:
        raise DotRefusal("invalid_input")
    if kind == "utc":
        from datetime import datetime, timezone
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if date.utcoffset() is None or date.utcoffset().total_seconds() != 0:
                raise DotRefusal("invalid_input")
        except ValueError as exc:
            raise DotRefusal("invalid_input") from exc
    if value.startswith(("newest:", "latest:", "fallback:", "file:", "http:")):
        raise DotRefusal("invalid_input")
    return value


def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, str]:
    spec = TOOLS.get(tool_name)
    if spec is None:
        raise DotRefusal("not_found")
    if type(arguments) is not dict:
        raise DotRefusal("invalid_input")
    expected = {k for k, _kind, _required in spec.fields}
    required = {k for k, _kind, required in spec.fields if required}
    if set(arguments) - expected or not required.issubset(arguments):
        raise DotRefusal("invalid_input")
    return {key: _text(arguments[key], kind) for key, kind, _ in spec.fields if key in arguments}


def input_schema(spec: ToolSpec) -> dict[str, Any]:
    props = {}
    for field, kind, required in spec.fields:
        schema: dict[str, Any] = {"type": "string", "minLength": 1}
        if kind == "sha": schema.update({"pattern": SHA_PATTERN.pattern, "maxLength": 40})
        elif kind == "symbol": schema.update({"pattern": SYMBOL_PATTERN.pattern, "maxLength": 96})
        elif kind == "numeric": schema.update({"pattern": r"^[1-9][0-9]{0,17}$", "maxLength": 18})
        elif kind == "utc": schema.update({"pattern": ISO_PATTERN.pattern, "maxLength": 32})
        else: schema.update({"pattern": REF_PATTERN.pattern, "maxLength": 160})
        props[field] = schema
    return {"type": "object", "properties": props,
            "required": [key for key, kind, req in spec.fields if req],
            "additionalProperties": False}


def schema_digest(profile: str, names: tuple[str, ...] | None = None) -> str:
    if profile not in PROFILES: raise DotRefusal("not_found")
    all_names = {t.name for t in TOOL_SPECS if t.profile == profile}
    selected = all_names if names is None else set(names)
    if not selected or selected - all_names:
        raise DotRefusal("invalid_input")
    doc = [{"name": t.name, "owner": t.owner, "scope": t.scope,
            "schema": input_schema(t)} for t in TOOL_SPECS if t.name in selected and t.profile == profile]
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

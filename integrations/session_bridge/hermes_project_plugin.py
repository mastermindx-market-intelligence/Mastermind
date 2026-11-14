"""Hermes-native source-plan context, habits and skill; no new execution owner.

The release pack copies this file as plugin __init__.py and its sibling modules
unchanged. Hermes owns profile settings, native compression lineage, tool scope
and registration leases. No provider, memory, credential or scheduler is changed.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
import logging
from pathlib import Path
import re
from typing import Any, Mapping

from .project_task_context import load_context, PlanContextError
from .long_horizon_guidance import render_context, compact_context

PLUGIN_NAME = "mastermind-long-horizon"
SECTION_ID = "mastermind-long-horizon.execution-habits"
TOOL_NAME = "mmx_project_context"
TOOLSET = "mmx_project_context"
TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": "Read the current native session's explicitly bound source plan. Retains the whole objective, requirements, dependencies, focus, blockers and evidence. Read-only; never dispatches, resumes or accepts work. Use after a task boundary or compaction. No session, path or contract may be supplied in arguments.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}
_BINDING_KEYS = {"workspace_root", "plan_path", "workstream", "plan_contract_sha256"}
_SAFE_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
_LOG = logging.getLogger(__name__)
HABITS = """Mastermind long-horizon workflow, not an execution grant:
Keep the full assigned outcome, requirements, non-goals and original native run identities.
Use one dependency-ready principal task; independently admitted delegates retain their own receipts.
A side question does not replace the mission. Apply explicit steering as a scope delta, not a reset.
Use native todo_list as a view of the source plan; read it before adding items. Never edit its database.
Read mmx_project_context at task boundaries and after compaction when detail is missing. Cached guidance is not current progress.
Verify affected behavior, save to the existing owner, read back, reassess the parent outcome, then advance permitted work.
Two identical no-progress attempts require a changed hypothesis or tactic, not an unchanged retry.
A timeout requires reading the original effect, not resending it. Honor stop, permission, budget and native admission.
Use existing goals/heartbeats only when already authorized. Do not install a second wake or continuation loop.
Task checks, turn completion, CI, merge and product acceptance are distinct. Missing context is not completed work.
Only a currently configured binding or its native compression continuation supplies context. Forks, resets and delegated children do not inherit it.
"""


def _native_lineage(ctx: Any, session_id: str) -> list[str]:
    """Read this plugin manager's existing compression metadata, never transcripts."""
    manager = getattr(ctx, "_manager", None)
    home = getattr(manager, "home_path", None)
    if not isinstance(home, (str, Path)) or not Path(home).is_absolute():
        return []
    path = Path(home) / "state.db"
    if path.is_symlink():
        raise PlanContextError("HERMES_PROFILE_DB_BINDING_INVALID")
    if not path.is_file():
        return []
    from hermes_state import SessionDB
    database = SessionDB(db_path=path, read_only=True)
    try:
        # Native core owns fork/reset/delegate exclusion. No second alias store.
        return database.get_compression_lineage(session_id)
    finally:
        database.close()


def _binding(ctx: Any, session_id: Any, lineage_reader=None) -> tuple[dict, str] | None:
    if type(session_id) is not str or not _SAFE_SESSION.fullmatch(session_id):
        return None
    manager = getattr(ctx, "_manager", None)
    if manager is not None:
        from hermes_cli.plugins_loader import _plugin_home_scope
        home = getattr(manager, "home_path", None)
        if not isinstance(home, (str, Path)) or not Path(home).is_absolute():
            raise PlanContextError("HERMES_PROFILE_BINDING_INVALID")
        # Native tools can be called with an explicit registry scope while the
        # ambient process serves another profile. Read this manager's config.
        with _plugin_home_scope(Path(home)):
            bindings = ctx.get_config("session_bindings", {})
    else:
        bindings = ctx.get_config("session_bindings", {})
    if type(bindings) is not dict or len(bindings) > 128:
        raise PlanContextError("HERMES_BINDINGS_INVALID")
    configured_id = session_id
    value = bindings.get(session_id)
    if value is None and bindings:
        lineage = (lineage_reader(session_id) if lineage_reader is not None
                   else _native_lineage(ctx, session_id))
        if (type(lineage) is not list or len(lineage) > 128
                or any(type(s) is not str or not _SAFE_SESSION.fullmatch(s) for s in lineage)
                or len(set(lineage)) != len(lineage)):
            raise PlanContextError("HERMES_COMPRESSION_LINEAGE_INVALID")
        if session_id in lineage:
            matches = [s for s in lineage[:lineage.index(session_id)] if s in bindings]
            if matches:
                configured_id = matches[-1]
                value = bindings[configured_id]
                if any(bindings[s] != value for s in matches):
                    raise PlanContextError("HERMES_COMPRESSION_BINDING_AMBIGUOUS")
    if value is None:
        return None
    if type(value) is not dict or set(value) != _BINDING_KEYS:
        raise PlanContextError("HERMES_BINDING_INVALID")
    if any(type(v) is not str or not v or len(v.encode("utf-8")) > 1024 for v in value.values()):
        raise PlanContextError("HERMES_BINDING_INVALID")
    if not Path(value["workspace_root"]).is_absolute():
        raise PlanContextError("HERMES_WORKSPACE_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", value["plan_contract_sha256"]):
        raise PlanContextError("HERMES_CONTRACT_INVALID")
    return dict(value), configured_id


def _reason(error: Exception) -> str:
    text = str(error)
    return text if _SAFE_REASON.fullmatch(text) else "HERMES_PLAN_CONTEXT_UNAVAILABLE"


def _gap(error: Exception) -> dict:
    return {"context": "Project plan context unavailable (" + _reason(error) + "). "
            "Retain the original assignment and native stop/effect boundaries. Recover the exact source "
            "through its existing owner; do not guess, silently rebind, or report the project complete. "
            "This plugin did not restart or dispatch work."}


def _skill_path() -> Path:
    packed = Path(__file__).parent / "skill" / "SKILL.md"
    if packed.is_file() and not packed.is_symlink():
        return packed
    if __package__ == "integrations.session_bridge":
        canonical = Path(__file__).resolve().parents[2] / "skills/mastermind-long-horizon/SKILL.md"
        if canonical.is_file() and not canonical.is_symlink():
            return canonical
    raise PlanContextError("HERMES_PACKAGED_SKILL_MISSING")


def register(ctx: Any, *, lineage_reader=None) -> None:
    """Contribute through native leases only; no source read at registration."""
    required = ("get_config", "register_system_prompt_section", "register_hook", "register_skill", "register_tool")
    if any(not callable(getattr(ctx, name, None)) for name in required):
        raise PlanContextError("HERMES_PLUGIN_API_UNSUPPORTED")
    leases = []
    live = {"ready": False}

    def current() -> bool:
        return live["ready"] and all(getattr(lease, "active", False) is True for lease in leases)

    def stable_habits(session_info: Mapping[str, Any]) -> str:
        try:
            if not current():
                return ""
            resolved = _binding(ctx, session_info.get("session_id"), lineage_reader)
            if resolved is None:
                return ""
            binding, configured_id = resolved
            pointer = {k: binding[k] for k in ("plan_path", "workstream", "plan_contract_sha256")}
            content = HABITS + "\nOriginal source pointer: " + json.dumps(pointer, sort_keys=True)
            if len(content) > 4000:
                raise PlanContextError("HERMES_HABITS_TOO_LARGE")
            return content
        except Exception:
            _LOG.warning("Mastermind source-plan binding unavailable; no stable section supplied")
            return ""

    def read_bound(session_id: str) -> dict | None:
        if not current():
            raise PlanContextError("HERMES_REGISTRATION_NOT_CURRENT")
        resolved = _binding(ctx, session_id, lineage_reader)
        if resolved is None:
            return None
        binding, configured_id = resolved
        context = load_context(workspace_root=Path(binding["workspace_root"]),
            relative_path=binding["plan_path"], workstream=binding["workstream"],
            expected_contract_sha256=binding["plan_contract_sha256"], context_detail="frontier")
        # Config revocation/rebinding or unload during IO must not return old data.
        if not current() or _binding(ctx, session_id, lineage_reader) != resolved:
            raise PlanContextError("HERMES_BINDING_CHANGED_DURING_READ")
        context["native_plan_binding"] = {"current_session_id": session_id,
            "configured_session_id": configured_id,
            "relation": "EXACT_CONFIG" if configured_id == session_id else "NATIVE_COMPRESSION_CONTINUATION"}
        return context

    def current_plan(session_id: str = "", **_unused: Any) -> dict | None:
        # Ignore user messages/history/model/platform: no intent guessing, mining or routing.
        try:
            context = read_bound(session_id)
            return {"context": render_context(context)} if context is not None else None
        except Exception as error:
            return _gap(error)

    def read_tool(arguments: Any, *, session_id: Any = None, **_unused: Any) -> str:
        try:
            if type(arguments) is not dict or arguments:
                raise PlanContextError("HERMES_CONTEXT_EMPTY_ARGUMENTS_REQUIRED")
            context = read_bound(session_id)
            if context is None:
                raise PlanContextError("HERMES_SESSION_NOT_BOUND")
            # Validate the shared output bound before returning native JSON.
            render_context(context)
            result = {"ok": True, "context": compact_context(context)}
        except Exception as error:
            result = {"ok": False, "reason": _reason(error), "execution_authority": False}
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    manager = getattr(ctx, "_manager", None)
    registry = None
    guard = nullcontext()
    if manager is not None:
        from tools.registry import registry
        from registration_lifecycle import replacement_coordinator
        guard = replacement_coordinator.transaction()
    with guard:
        if registry is not None and registry.get_entry(TOOL_NAME, scope=manager.scope_key) is not None:
            raise PlanContextError("HERMES_CONTEXT_TOOL_COLLISION")
        try:
            leases.append(ctx.register_skill("execute-project", _skill_path(),
                description="Preserve full project scope, focus one task, verify and continue through compaction."))
            leases.append(ctx.register_system_prompt_section(SECTION_ID, stable_habits,
                position="after_memory", max_chars=4000))
            leases.append(ctx.register_hook("pre_llm_call", current_plan))
            leases.append(ctx.register_tool(name=TOOL_NAME, toolset=TOOLSET,
                schema=TOOL_SCHEMA, handler=read_tool, check_fn=current,
                description=TOOL_SCHEMA["description"], override=False))
            if any(lease is None or not callable(getattr(lease, "dispose", None)) for lease in leases):
                raise PlanContextError("HERMES_REGISTRATION_NOT_OBSERVED")
            live["ready"] = True
            if not current():
                raise PlanContextError("HERMES_REGISTRATION_NOT_OBSERVED")
            if registry is not None:
                entry = registry.get_entry(TOOL_NAME, scope=manager.scope_key)
                if entry is None or entry.handler is not read_tool or entry.schema != TOOL_SCHEMA:
                    raise PlanContextError("HERMES_CONTEXT_TOOL_READBACK_MISMATCH")
        except Exception:
            live["ready"] = False
            for lease in reversed(leases):
                if callable(getattr(lease, "dispose", None)):
                    lease.dispose()
            raise

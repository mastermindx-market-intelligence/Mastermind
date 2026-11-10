"""Explicit v6 help read through the original native session and source plugin.

The existing ConsumerSlot retains one native registration. The original native
claim, source-plan plugin leases and captured MCP connection remain the owners.
There is no client, credential, source fallback, root selection or dispatch here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import inspect
from pathlib import Path

from common import coo_project_help_contract as wire
from integrations.executive_mcp.schemas import RESULT_SCHEMA
from integrations.hermes_runtime.errors import RuntimeRefusal
from .native_agentos_context import decode_native_tool_result, expected_context, _E1_KEYS
from .native_executive_consumer import (
    CONSUMER_SLOT_ATTRIBUTE, ConsumerSlot, ExecutiveContextConsumerPublication,
    PROJECT_HELP_TOOLS_SCHEMA_DIGEST, _NativeMcpCaller, workspace_principal_frame,
)

SOURCE_PLUGIN = "mastermind-long-horizon"
SOURCE_TOOL = "mmx_project_context"
PACKAGE_FILES = (
    "__init__.py", "project_task_context.py", "project_task_contract.py", "long_horizon_guidance.py",
    "plugin.yaml", "skill/SKILL.md", "skill/references/native-t3.md",
    "skill/references/native-hermes.md", "skill/references/continuity-patterns.md",
)


def _refuse():
    raise RuntimeRefusal("NATIVE_PROJECT_HELP_UNAVAILABLE")


def package_digest(root):
    """Fixed installed source package bytes, never manifest-selected code."""
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or root.resolve(strict=True) != root:
        _refuse()
    files = {}
    for name in PACKAGE_FILES:
        path = root / name
        if (any(node.is_symlink() for node in (path, *path.relative_to(root).parents)
                if node.is_absolute()) or path.resolve(strict=True) != path
                or not path.is_file() or path.stat().st_size > 128 * 1024):
            _refuse()
        data = path.read_bytes()
        if len(data) > 128 * 1024:
            _refuse()
        files[name] = hashlib.sha256(data).hexdigest()
    return wire.digest(files)


def decode_help_result(raw, publication):
    try:
        value = decode_native_tool_result(raw, limit=wire.MAX_RESPONSE_BYTES + 4096)
        if (type(value) is not dict or set(value) != _E1_KEYS
                or value["schema"] != RESULT_SCHEMA or value["tool"] != wire.TOOL
                or value["ok"] is not True or value["server_version"] != publication.mcp.server_version
                or value["mode"] != "readonly" or value["grounding"] != {}
                or value["degraded"] != [] or value["bounded"] != [] or value["error"] is not None):
            _refuse()
        generated = value["generated_at"]
        if type(generated) is not str or not 0 < len(generated) <= 64 or not generated.endswith("Z"):
            _refuse()
        stamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            _refuse()
        return wire.validate_result(value["data"], expected_context=expected_context(publication),
            capability_profile_digest=publication.capability_profile_digest,
            expected_workspace_principal=workspace_principal_frame(publication),
            expected_scope=publication.project_help.to_dict())
    except RuntimeRefusal:
        raise
    except Exception:
        _refuse()


class NativeProjectHelpRead:
    """One read-only port on the already qualified original MCP owner."""

    def __init__(self, *, publication, server, session, loop, currentness):
        if (type(publication) is not ExecutiveContextConsumerPublication or publication.project_help is None
                or publication.tools_schema_digest != PROJECT_HELP_TOOLS_SCHEMA_DIGEST or not callable(currentness)):
            _refuse()
        self.publication, self.currentness = publication, currentness
        self.caller = _NativeMcpCaller(server=server, session=session, loop=loop,
            timeout=30.0, currentness=currentness, wait_for_lock=False)

    def read(self, context, *, current):
        selected = self.publication.project_help.to_dict()
        if not callable(current) or current() is not True or self.currentness() is not True:
            _refuse()
        wire.context_matches_source_plan(context, selected["source_plan"])
        raw = self.caller.call(wire.TOOL, {"work_ref": self.publication.work_ref}, currentness=current)
        result = decode_help_result(raw, self.publication)
        if current() is not True or self.currentness() is not True:
            _refuse()
        wire.context_matches_source_plan(context, result["scope"]["source_plan"])
        return result


@dataclass(frozen=True)
class ProjectContextRegistration:
    slot: ConsumerSlot
    context: object
    manifest: object
    reader: object
    lease_current: object
    handler: object
    registry: object
    entry: object
    package_root: Path
    package_sha256: str

    def current(self):
        try:
            from tools.registry import registry
            from hermes_cli.plugins import PluginContext
            from .native_tool_registration import _loading_mode_refusal
            slot, ctx = self.slot, self.context
            loaded = slot.manager._plugins.get(SOURCE_PLUGIN)
            return (type(ctx) is PluginContext and slot.project_help_context is self
                and ctx._manager is slot.manager and getattr(slot.manager, CONSUMER_SLOT_ATTRIBUTE, None) is slot
                and slot.scope == slot.manager.scope_key and ctx.profile_name == slot.profile_id
                and ctx.manifest is self.manifest and loaded is not None
                and loaded.manifest is self.manifest and loaded.enabled is True and loaded.error is None
                and self.manifest.source == "user" and self.manifest.name == SOURCE_PLUGIN
                and Path(self.manifest.path) == self.package_root
                and _loading_mode_refusal(ctx) is None and self.lease_current() is True
                and slot.publication.mcp.server in ctx._mcp_allowlist(ctx.plugin_id)
                and registry is self.registry and registry.get_entry(SOURCE_TOOL, scope=slot.scope) is self.entry
                and self.entry.handler is self.handler
                and package_digest(self.package_root) == self.package_sha256
                and callable(slot.import_current) and slot.import_current() is True)
        except Exception:
            return False

    def read(self, factory, claim, *, expected_context_value=None):
        if (factory.slot is not self.slot or factory.current_claim() is not claim
                or not claim.current(adopted=True) or not self.current()
                or factory.project_help_reader is None):
            _refuse()
        session_id = claim.agent.session_id
        context = self.reader(session_id)
        selected = self.slot.publication.project_help.to_dict()["source_plan"]
        wire.context_matches_source_plan(context, selected)
        if expected_context_value is not None and context != expected_context_value:
            _refuse()

        def current():
            return (claim.current(adopted=True) and factory.local_current()
                and claim.agent.session_id == session_id and self.current())

        result = factory.project_help_reader.read(context, current=current)
        after = self.reader(session_id)
        if after != context or not current() or factory.current_claim() is not claim:
            _refuse()
        wire.context_matches_source_plan(after, selected)
        return result


def register_source_context(ctx, *, reader, lease_current, handler):
    """Called by the existing source plugin after its native leases exist."""
    from hermes_cli.plugins import PluginContext
    from tools.registry import registry
    from .native_tool_registration import _loading_mode_refusal
    manager = getattr(ctx, "_manager", None)
    slot = getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None)
    if type(slot) is not ConsumerSlot or getattr(slot.publication, "project_help", None) is None:
        return None
    publication, manifest = slot.publication, ctx.manifest
    selected = publication.project_context_plugin
    root = Path(manifest.path)
    if (type(ctx) is not PluginContext or slot.manager is not manager or slot.scope != manager.scope_key
            or ctx.profile_name != slot.profile_id or ctx.plugin_id != SOURCE_PLUGIN
            or manifest.name != selected.name or manifest.source != selected.source
            or _loading_mode_refusal(ctx) is not None or not callable(lease_current)
            or lease_current() is not True or publication.mcp.server not in ctx._mcp_allowlist(ctx.plugin_id)
            or not inspect.isfunction(reader) or not inspect.isfunction(handler)
            or Path(reader.__code__.co_filename).resolve() != root / "__init__.py"
            or Path(handler.__code__.co_filename).resolve() != root / "__init__.py"
            or package_digest(root) != selected.digest or slot.project_help_context is not None):
        _refuse()
    entry = registry.get_entry(SOURCE_TOOL, scope=slot.scope)
    if entry is None or entry.handler is not handler:
        _refuse()
    registration = ProjectContextRegistration(slot, ctx, manifest, reader, lease_current,
        handler, registry, entry, root, selected.digest)
    slot.project_help_context = registration
    return registration


def unavailable(reason="CURRENT_PROJECT_HELP_UNAVAILABLE"):
    if reason not in {"CURRENT_PROJECT_HELP_UNAVAILABLE", "PROJECT_HELP_CONTEXT_OVER_BUDGET"}:
        _refuse()
    return {"state": "UNAVAILABLE", "reason": reason,
            "execution_authority": False, "native_origin_attested": False}


def read_for_claim(factory, claim, *, context=None):
    registration = factory.slot.project_help_context
    if type(registration) is not ProjectContextRegistration:
        _refuse()
    return registration.read(factory, claim, expected_context_value=context)


def project_context_help(ctx, session_id, context):
    """Compose only an explicitly enrolled native claim; keep legacy inert."""
    slot = getattr(getattr(ctx, "_manager", None), CONSUMER_SLOT_ATTRIBUTE, None)
    if type(slot) is not ConsumerSlot or getattr(slot.publication, "project_help", None) is None:
        return context
    try:
        factory = slot.memory_factory
        claim = factory.current_claim()
        if claim.agent.session_id != session_id:
            _refuse()
        result = read_for_claim(factory, claim, context=context)
    except Exception:
        result = unavailable()
    return {**context, "project_help": result}


def delivery_identity(value):
    """Compare delivered facts, retaining acquisition receipts separately."""
    if value.get("state") == "UNAVAILABLE":
        if value != unavailable(value.get("reason")):
            _refuse()
        return wire.digest(value)
    return wire.read_identity(value)

"""Root-sealed installed COO source composition; core never imports integrations.

This is an adapter of the existing installation, not an enrollment mechanism.
The caller owns explicit opt-in and exact service identity; network secrets and
MCP SDK remain outside the Control process.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from common.executive_workspace_contract import _check_work_ref
from control_plane.coo_principal_host import _refuse, _authority, validate_missions
from control_plane.coo_principal_mandate import PrincipalFact
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest

DEFAULT_INSTALL_PATH = Path("/Library/Application Support/MastermindExecutive/config/executive-mcp.json")


class CooInstalledSource:
    def __init__(self, load_coo, registry_loader):
        if not callable(load_coo) or not callable(registry_loader):
            _refuse()
        self._load_coo = load_coo
        self._registry_loader = registry_loader

    @classmethod
    def from_path(cls, path, source, *, expected_uid):
        from ops.executive_os import executive_mcp_entry as entry
        path, source = Path(path), Path(source)
        entry.require_sealed_path(source, directory=True)
        entry.require_sealed_path(path)
        initial = entry.validate_document(json.loads(path.read_text()))
        if source.name != initial["release_sha"] or os.geteuid() != expected_uid:
            _refuse()
        loader = entry.current_projection_loader(path, source, initial, "coo", None,
                                                  expected_uid=expected_uid)
        def registry():
            policy = source / "config/executive_agent_capabilities.json"
            entry.require_sealed_path(policy)
            return ExecutionCapabilityRegistry.load(policy, source_root=source)
        return cls(loader, registry)

    def snapshot(self, work_ref):
        from integrations.business_mcp_auth.contracts import load_resource_policy
        from integrations.mastermind_executive_app.coo_binding import validate_coo_binding, _digest
        from integrations.executive_mcp.coo import COO_SERVER_NAME, COO_SERVER_VERSION, COO_TOOL_SPECS
        if not _check_work_ref(work_ref):
            _refuse()
        coo = self._load_coo()
        policy = load_resource_policy(coo["policy"])
        bound = validate_coo_binding(coo["binding"], policy)
        if bound["enabled"] is not True:
            _refuse()
        binding = bound["binding"]
        rows = [r for r in validate_missions(coo.get("missions", [])) if r["work_ref"] == work_ref]
        if len(rows) != 1 or rows[0]["principal_binding_digest"] != _digest(binding):
            _refuse()
        row = rows[0]
        registry = self._registry_loader()
        if type(registry) is not ExecutionCapabilityRegistry:
            _refuse()
        profile = registry.profiles.get(row["capability_profile_id"])
        if profile is None or not profile.enabled or profile.profile_digest != row["capability_profile_digest"]:
            _refuse()
        specs = {s.name: {"name": s.name, "inputSchema": s.input_schema,
                         "annotations": s.annotations} for s in COO_TOOL_SPECS}
        schema_digest = observed_mcp_tool_schema_digest({"tools": specs})
        matches = [g for g in profile.mcp_server_grants
            if g.server_identity == COO_SERVER_NAME and g.server_version == COO_SERVER_VERSION
            and set(g.enabled_tools) == set(specs) and g.tool_schema_digest == schema_digest]
        if len(matches) != 1:
            _refuse()
        fact = PrincipalFact(policy_id=binding["policy_id"], issuer_digest=binding["issuer_digest"],
            subject_digest=binding["subject_digest"], client_ref=binding["client_ref"],
            resource_ref=binding["resource"], scopes=tuple(binding["scopes"]),
            principal_binding_digest=row["principal_binding_digest"])
        return row, fact, _authority(row)

    def for_principal(self, principal, work_ref):
        row, fact, authority = self.snapshot(work_ref)
        expected = {"policy_id": fact.policy_id, "issuer_digest": fact.issuer_digest,
            "subject_digest": fact.subject_digest, "client_ref": fact.client_ref,
            "resource": fact.resource_ref, "scopes": list(fact.scopes)}
        if type(principal) is not dict or principal != expected:
            _refuse()
        return row, fact, authority



def validate_control_coo(raw):
    """Explicit opt-in on the incumbent Control configuration; no new service."""
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    arm = raw.get("coo_principal_armed", False)
    if type(arm) is not bool or (arm and (raw.get("executive_mcp_profile") != WEB_CEO_V2_PROFILE
            or not {"workspace_acquisition", "workspace_resource_policy", "workspace_control_room", "ceo_ingress_app_peer_uid"} <= set(raw))):
        _refuse()
    return arm


"""Root-sealed installed COO source composition; core never imports integrations.

This is an adapter of the existing installation, not an enrollment mechanism.
The caller owns explicit opt-in and exact service identity; network secrets and
MCP SDK remain outside the Control process.
"""
from __future__ import annotations
import json
import os
import hashlib
import stat
from pathlib import Path
from common.executive_workspace_contract import _check_work_ref
from control_plane.coo_principal_host import _refuse, _authority, validate_missions
from control_plane.coo_principal_mandate import PrincipalFact
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest

DEFAULT_INSTALL_PATH = Path("/Library/Application Support/MastermindExecutive/config/executive-mcp.json")


def _fixed_original_target_reader(path, source, initial, *, expected_uid):
    """Bind the incumbent sealed target to this process and file generation.

    This is deliberately not a rotatable registry. Replacement or ABA writes
    require fresh host qualification, even when the JSON returns to old bytes.
    Ordinary COO projection rotation continues through its existing loader.
    """
    from ops.executive_os import executive_mcp_entry as entry
    target = entry.build_installed_principal_ruling_target(initial)
    if target is None:
        return None
    pid = os.getpid()

    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                info.st_gid)

    def file_identity(info):
        return (*identity(info), info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def observe():
        if os.getpid() != pid or os.geteuid() != expected_uid:
            _refuse()
        entry.require_sealed_path(source, directory=True)
        entry.require_sealed_path(path)
        nodes = tuple(dict.fromkeys((source, *source.parents, *path.parents)))
        namespace = tuple(identity(node.lstat()) for node in nodes)
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                _refuse()
            contents = handle.read()
            after = os.fstat(handle.fileno())
            entry.require_sealed_path(source, directory=True)
            entry.require_sealed_path(path)
            if (file_identity(before) != file_identity(after)
                    or file_identity(after) != file_identity(path.lstat())
                    or namespace != tuple(identity(node.lstat()) for node in nodes)):
                _refuse()
        current = entry.validate_document(json.loads(contents))
        if current != initial or source.name != current["release_sha"]:
            _refuse()
        return namespace, file_identity(after), hashlib.sha256(contents).digest()

    generation = observe()

    def read():
        if observe() != generation:
            _refuse()
        return target
    return read


class CooInstalledSource:
    def __init__(self, load_coo, registry_loader):
        if not callable(load_coo) or not callable(registry_loader):
            _refuse()
        self._load_coo = load_coo
        self._registry_loader = registry_loader
        self._original_acceptance_target_reader = None

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
        owner = cls(loader, registry)
        owner._original_acceptance_target_reader = _fixed_original_target_reader(
            path, source, initial, expected_uid=expected_uid)
        return owner

    def original_acceptance_target(self):
        """Only the genuine installed producer can supply this fixed target."""
        reader = self._original_acceptance_target_reader
        return reader() if reader is not None else None

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


    def for_workspace_read_principal(self, principal, work_ref):
        """Read-only, two-resource membership using the *original* installed COO.

        The caller independently verifies an enrolled Workspace bearer for
        its distinct resource. This method only matches that verified
        pseudonymous identity to the installed COO mission's policy/issuer/
        subject/client. COO tools/actions and direct Fabric runs do NOT inherit
        Workspace authorization. Disabled, renamed or rotated owner facts
        always refuse. Never reinterpret a Workspace token as a COO token.
        """
        from common.executive_workspace_contract import RESOURCE, SCOPE
        row, fact, authority = self.snapshot(work_ref)
        # Workspace and COO use distinct resource *and policy* IDs. Each
        # installed authorizer independently validates its own policy ID and
        # original resource/scope; only pseudonymous issuer/subject/client
        # are shared cross-resource membership identities.
        expected = {
            "issuer_digest": fact.issuer_digest,
            "subject_digest": fact.subject_digest, "client_ref": fact.client_ref,
            "resource": RESOURCE, "scopes": [SCOPE],
        }
        if (type(principal) is not dict or set(principal) != set(expected) | {"policy_id"}
                or type(principal["policy_id"]) is not str
                or not 1 <= len(principal["policy_id"]) <= 256
                or {k: principal[k] for k in expected} != expected or row["enabled"] is not True
                or fact.resource_ref == RESOURCE
                or "mastermind.executive.read" not in fact.scopes
                or authority.work_ref != work_ref):
            _refuse()
        return row, fact, authority


def validate_control_coo(raw):
    """Explicit opt-in on the incumbent Control configuration; no new service."""
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
    arm = raw.get("coo_principal_armed", False)
    dialogue_arm = raw.get("coo_principal_dialogue_armed", False)
    supported_profiles = {WEB_CEO_V2_PROFILE, WEB_CEO_V3_PROFILE}
    if (type(dialogue_arm) is not bool or (dialogue_arm and arm is not True)
            or type(arm) is not bool or (arm and (raw.get("executive_mcp_profile") not in supported_profiles
            or not {"workspace_acquisition", "workspace_resource_policy", "workspace_control_room", "ceo_ingress_app_peer_uid"} <= set(raw)))):
        _refuse()
    return arm


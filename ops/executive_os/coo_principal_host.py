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
from common.executive_workspace_contract import canonical, _check_work_ref
from control_plane.coo_principal_host import (
    _refuse, _authority, build_selected_child_publication, validate_missions,
)
from control_plane.coo_principal_mandate import PrincipalFact
from control_plane.executive_agent_capabilities import (
    CLAUDE_PRINCIPAL_AUTH_REALM,
    CLAUDE_PRINCIPAL_EXECUTION_SURFACE,
    HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE,
    HERMES_NATIVE_PRINCIPAL_PROFILE_ID,
    HERMES_NATIVE_CONTEXT_PROFILE_ID,
    HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID,
    HERMES_NATIVE_DISCOVERY_PROFILE_ID,
    PRINCIPAL_COO_CONTEXT_MCP_CAPABILITY_ID,
    PRINCIPAL_COO_CURRENT_CONTEXT_MCP_CAPABILITY_ID,
    PRINCIPAL_COO_DISCOVERY_MCP_CAPABILITY_ID,
    ExecutionCapabilityRegistry,
    observed_mcp_tool_schema_digest,
)

DEFAULT_INSTALL_PATH = Path("/Library/Application Support/MastermindExecutive/config/executive-mcp.json")
CLAUDE_PRINCIPAL_POLICY = Path("config/executive_claude_principal_capabilities.json")


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


def _fixed_selected_child_target_reader(path, source, initial, *, expected_uid):
    """Bind the frozen selected-child publication to this process and file generation.

    The generation-bound law itself is owned ONCE, by the installed entry
    owner, and is shared verbatim with the installed App settings
    constructor. Both installed consumers therefore prove the SAME frozen
    publication generation instead of two different laws: the App's
    rotatable projection loader would have accepted a same-byte
    replacement and an in-place A->B->A rewrite of the installation.

    This is deliberately not a rotatable registry. Replacement or ABA writes
    require fresh host qualification, even when the document returns to old
    bytes. The guard proves the FIXED publication and its legitimate
    read/source identity; it never reruns fresh dispatch eligibility,
    recomputes an ordinal, requires the original child to remain unclaimed,
    or calls guard_dialogue merely to read the original command.
    """
    from ops.executive_os import executive_mcp_entry as entry
    return entry.fixed_selected_child_target_reader(
        path, source, initial, expected_uid=expected_uid)


class CooInstalledSource:
    def __init__(self, load_coo, registry_loader):
        if not callable(load_coo) or not callable(registry_loader):
            _refuse()
        self._load_coo = load_coo
        self._registry_loader = registry_loader
        self._context_source_callbacks = (load_coo, registry_loader)
        self._original_acceptance_target_reader = None
        self._selected_child_target_reader = None

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
            policy = source / CLAUDE_PRINCIPAL_POLICY
            entry.require_sealed_path(policy)
            return ExecutionCapabilityRegistry.load(policy, source_root=source)
        owner = cls(loader, registry)
        owner._original_acceptance_target_reader = _fixed_original_target_reader(
            path, source, initial, expected_uid=expected_uid)
        owner._selected_child_target_reader = _fixed_selected_child_target_reader(
            path, source, initial, expected_uid=expected_uid)
        return owner

    def original_acceptance_target(self):
        """Only the genuine installed producer can supply this fixed target."""
        reader = self._original_acceptance_target_reader
        return reader() if reader is not None else None

    def selected_child_target(self):
        """The same frozen publication, read through a fixed currentness reader."""
        reader = self._selected_child_target_reader
        return reader() if reader is not None else None

    def snapshot(self, work_ref, *, principal_binding_digest=None):
        return self._snapshot(work_ref, self._load_coo(),
            principal_binding_digest=principal_binding_digest)

    def _snapshot(self, work_ref, coo, *, principal_binding_digest=None):
        from integrations.business_mcp_auth.contracts import load_resource_policy
        from integrations.mastermind_executive_app.coo_binding import coo_binding_records, _digest
        if not _check_work_ref(work_ref):
            _refuse()
        policy = load_resource_policy(coo["policy"])
        records = coo_binding_records(coo["binding"], policy)
        rows = [r for r in validate_missions(coo.get("missions", [])) if r["work_ref"] == work_ref]
        if len(rows) != 1:
            _refuse()
        row = rows[0]
        digest = row["principal_binding_digest"]
        matches = [record for record in records if _digest(record) == digest]
        if (len(matches) != 1 or (principal_binding_digest is not None
                and principal_binding_digest != digest)):
            _refuse()
        binding = matches[0]
        registry = self._registry_loader()
        if type(registry) is not ExecutionCapabilityRegistry:
            _refuse()
        profile = registry.profiles.get(row["capability_profile_id"])
        if (profile is None or not profile.enabled
                or profile.profile_digest != row["capability_profile_digest"]
                or profile.execution_surface not in {
                    CLAUDE_PRINCIPAL_EXECUTION_SURFACE, HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE}
                or (profile.execution_surface == HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE
                    and profile.profile_id not in {HERMES_NATIVE_PRINCIPAL_PROFILE_ID, HERMES_NATIVE_CONTEXT_PROFILE_ID,
                                                   HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID, HERMES_NATIVE_DISCOVERY_PROFILE_ID})
                or profile.auth_realm != CLAUDE_PRINCIPAL_AUTH_REALM):
            _refuse()
        self._profile_catalogue(profile)
        fact = PrincipalFact(policy_id=binding["policy_id"], issuer_digest=binding["issuer_digest"],
            subject_digest=binding["subject_digest"], client_ref=binding["client_ref"],
            resource_ref=binding["resource"], scopes=tuple(binding["scopes"]),
            principal_binding_digest=row["principal_binding_digest"])
        return row, fact, _authority(row)

    @staticmethod
    def _profile_catalogue(profile):
        from common import coo_agentos_context_contract as wire
        from integrations.executive_mcp.coo import COO_SERVER_NAME, COO_SERVER_VERSION, catalogue_specs
        found = []
        context_profiles = {
            wire.CATALOGUE: (HERMES_NATIVE_CONTEXT_PROFILE_ID, PRINCIPAL_COO_CONTEXT_MCP_CAPABILITY_ID),
            wire.CURRENT_CATALOGUE: (HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID, PRINCIPAL_COO_CURRENT_CONTEXT_MCP_CAPABILITY_ID),
            wire.DISCOVERY_CATALOGUE: (HERMES_NATIVE_DISCOVERY_PROFILE_ID, PRINCIPAL_COO_DISCOVERY_MCP_CAPABILITY_ID),
        }
        for catalogue in (wire.LEGACY_CATALOGUE, *context_profiles):
            specs = {s.name: {"name": s.name, "inputSchema": s.input_schema, "annotations": s.annotations}
                     for s in catalogue_specs(catalogue)}
            schema_digest = observed_mcp_tool_schema_digest({"tools": specs})
            for grant in profile.mcp_server_grants:
                if (grant.server_identity == COO_SERVER_NAME and grant.server_version == COO_SERVER_VERSION
                        and set(grant.enabled_tools) == set(specs) and grant.tool_schema_digest == schema_digest):
                    if catalogue in context_profiles and (
                            (profile.profile_id, grant.capability_id) != context_profiles[catalogue]):
                        _refuse()
                    found.append(catalogue)
        if len(found) != 1:
            _refuse()
        for catalogue, (profile_id, _) in context_profiles.items():
            if profile.profile_id == profile_id and found[0] != catalogue:
                _refuse()
        return found[0]

    def catalogue_for_principal(self, principal, *, work_ref=None):
        """One fixed catalogue per authenticated binding; never a tool union.

        Active missions select the contract. With no enabled mission, retain the
        legacy reconciliation surface without granting context access. Calling
        existing tools does not require this new projection.
        """
        from common import coo_agentos_context_contract as wire
        from integrations.business_mcp_auth.contracts import load_resource_policy
        from integrations.mastermind_executive_app.coo_binding import select_coo_binding, _digest
        self.require_context_source_current()
        coo = self._load_coo()
        binding = select_coo_binding(coo["binding"], load_resource_policy(coo["policy"]), principal)
        if binding is None:
            _refuse()
        stamp = _digest(binding)
        expected = {key: binding[key] for key in ("policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes")}
        if type(principal) is not dict or principal != expected:
            _refuse()
        rows = [row for row in validate_missions(coo.get("missions", [])) if row["principal_binding_digest"] == stamp]
        selected = [row for row in rows if row["enabled"]]
        if work_ref is not None:
            # Internal per-read permission check, never a tools/list selector.
            # AuthorityFact's generation deliberately excludes enabled.
            scoped = [row for row in selected if row["work_ref"] == work_ref]
            actions = {HERMES_NATIVE_CONTEXT_PROFILE_ID: wire.ACTION,
                       HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID: wire.CURRENT_ACTION,
                       HERMES_NATIVE_DISCOVERY_PROFILE_ID: wire.CURRENT_ACTION}
            if (not _check_work_ref(work_ref) or len(scoped) != 1
                    or scoped[0]["capability_profile_id"] not in actions
                    or actions[scoped[0]["capability_profile_id"]] not in _authority(scoped[0]).principal_actions):
                _refuse()
        catalogues = set()
        for row in selected:
            self.require_context_source_current()
            self._snapshot(row["work_ref"], coo, principal_binding_digest=stamp)
            self.require_context_source_current()
            registry = self._registry_loader()
            if type(registry) is not ExecutionCapabilityRegistry:
                _refuse()
            profile = registry.profiles.get(row["capability_profile_id"])
            if profile is None or not profile.enabled or profile.profile_digest != row["capability_profile_digest"]:
                _refuse()
            catalogues.add(self._profile_catalogue(profile))
        if len(catalogues) > 1 or self._load_coo() != coo:
            _refuse()
        self.require_context_source_current()
        return next(iter(catalogues)) if catalogues else wire.LEGACY_CATALOGUE

    def require_context_source_current(self):
        if (self._load_coo is not self._context_source_callbacks[0]
                or self._registry_loader is not self._context_source_callbacks[1]):
            _refuse()

    def has_context_read_grant(self):
        """Installed composition selector, never an effect-admission arm."""
        from common import coo_agentos_context_contract as wire
        self.require_context_source_current()
        coo = self._load_coo()
        found = False
        for row in validate_missions(coo.get("missions", [])):
            alternatives = {HERMES_NATIVE_CONTEXT_PROFILE_ID: (wire.ACTION, wire.CATALOGUE),
                            HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID: (wire.CURRENT_ACTION, wire.CURRENT_CATALOGUE),
                            HERMES_NATIVE_DISCOVERY_PROFILE_ID: (wire.CURRENT_ACTION, wire.DISCOVERY_CATALOGUE)}
            if (row["enabled"] and row["capability_profile_id"] in alternatives):
                _, fact, authority = self._snapshot(row["work_ref"], coo)
                principal = {"policy_id": fact.policy_id, "issuer_digest": fact.issuer_digest,
                    "subject_digest": fact.subject_digest, "client_ref": fact.client_ref,
                    "resource": fact.resource_ref, "scopes": list(fact.scopes)}
                action, catalogue = alternatives[row["capability_profile_id"]]
                if (action in authority.principal_actions
                        and self.catalogue_for_principal(principal) == catalogue):
                    found = True
        if self._load_coo() != coo:
            _refuse()
        self.require_context_source_current()
        return found

    def for_principal(self, principal, work_ref):
        from integrations.business_mcp_auth.contracts import load_resource_policy
        from integrations.mastermind_executive_app.coo_binding import select_coo_binding, _digest
        coo = self._load_coo()
        binding = select_coo_binding(coo["binding"],
            load_resource_policy(coo["policy"]), principal)
        if binding is None:
            _refuse()
        row, fact, authority = self._snapshot(work_ref, coo,
            principal_binding_digest=_digest(binding))
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


def prepare_selected_child_target(host_provider, *, principal, context, work_ref,
                                  root_job_id, child_job_ids, destination):
    """Capture through the owner and publish the closed material.

    The production preparation hook of the selected-child publication. It
    calls the OWNER capture -- never a local re-derivation -- and writes
    the EXACT publication bytes to ``destination`` through the existing
    exclusive root-owned writer. It never overwrites an existing file and
    never leaves behind a file the publication's own trusted read would
    refuse.
    """
    capture = host_provider.capture_selected_child_target(
        principal=principal, context=context, work_ref=work_ref,
        root_job_id=root_job_id, child_job_ids=child_job_ids)
    publication = build_selected_child_publication(
        work_ref=capture["work_ref"], root_job_id=capture["root_job_id"],
        children=capture["children"], source=capture["source"])
    return write_selected_child_target_input(publication, destination)


def write_selected_child_target_input(publication, destination):
    """The exclusive root-owned 0600 input writer of one publication.

    The writer is the ONLY place a selected-child publication becomes an
    installed input: an exclusive, no-follow create of a root-owned,
    single-link, group-0 file under a root-controlled parent chain, with an
    exact readback of the bytes written.  It never overwrites an existing
    file and never leaves behind a file the publication's own trusted read
    would refuse.
    """
    raw = canonical(publication) + b"\n"
    path = Path(destination)
    if not path.is_absolute() or ".." in path.parts or str(path) != str(destination):
        raise ValueError("selected child target input path is invalid")
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) & 0o022):
            raise ValueError("selected child target input parent is not root-controlled")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise ValueError("selected child target input already exists") from None
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ValueError("selected child target input was not written whole")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError("selected child target input is not the root-owned object the publication reads")
    with open(path, "rb") as handle:
        written_back = handle.read()
    if written_back != raw:
        raise ValueError("selected child target input readback differs")
    return {"publication": publication, "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest()}


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


def load_control_coo_source(raw, source, *, expected_uid, install_path=DEFAULT_INSTALL_PATH):
    """Select the existing installed source for effects or an explicit read grant.

    Unarmed installations retain their old behavior unless the sealed source and
    registry independently prove a context-read mission. Failure of that optional
    read selection never turns on effect admission or chooses another source.
    """
    if validate_control_coo(raw):
        return CooInstalledSource.from_path(install_path, source, expected_uid=expected_uid)
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
    if (raw.get("executive_mcp_profile") not in {WEB_CEO_V2_PROFILE, WEB_CEO_V3_PROFILE}
            or not {"workspace_acquisition", "workspace_resource_policy", "workspace_control_room",
                    "ceo_ingress_app_peer_uid"} <= set(raw)):
        return None
    try:
        candidate = CooInstalledSource.from_path(install_path, source, expected_uid=expected_uid)
        return candidate if candidate.has_context_read_grant() else None
    except (OSError, ValueError):
        return None


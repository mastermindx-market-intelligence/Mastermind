"""Root-configured, dedicated-uid launcher for the existing five-tool MCP App.

Run with the separately provisioned network Python runtime and -I -B. The
sealed control Python remains SDK-free. This launcher never opens Runtime.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import copy
import time
import json
import os
from pathlib import Path
import re
import stat
import sys


CONFIG_SCHEMA = 'mastermind.executive_mcp_install.v1'
CONFIG_KEYS = frozenset({
    'schema', 'release_sha', 'service_uid', 'ceo_ingress_socket_path',
    'port', 'policies', 'audit_root',
})

_EXECUTIVE_TUNNEL_RESOURCE_RE = re.compile(
    r'^https://tunnel-service\.gateway\.unified-0\.internal\.api\.openai\.org/'
    r'v1/mcp/tunnel_[0-9a-f]{32}$'
)


def validate_additional_resources(raw):
    values = raw.get('executive_additional_resources', [])
    if (type(values) is not list or len(values) > 16
            or values != sorted(values) or len(values) != len(set(values))
            or any(type(value) is not str
                   or _EXECUTIVE_TUNNEL_RESOURCE_RE.fullmatch(value) is None
                   for value in values)):
        raise ValueError('additional Executive OAuth resources are invalid')
    return tuple(values)


def validate_document(raw):
    if (type(raw) is not dict or not CONFIG_KEYS <= set(raw)
            or not set(raw) <= CONFIG_KEYS | {'workspace', 'steward', 'coo', 'executive_mcp_profile', 'executive_additional_resources', 'os_executive_transport', 'os_executive_resource', 'os_commission_port', 'principal_ruling_target', 'reply_events_armed', 'public_mcp_resource', 'selected_child_target', 'dot_canary', 'session_web_observation'}):
        raise ValueError('installed MCP configuration fields differ')
    if type(raw.get('reply_events_armed',False)) is not bool:
        raise ValueError('event receiver selection must be boolean')
    if raw.get('reply_events_armed',False) and raw.get('executive_mcp_profile') != 'web_ceo_v3':
        raise ValueError('reply events require explicit Web-CEO v3 receiver')
    from integrations.session_bridge.dot_canary_policy_selection import validate_dot_canary_settings
    validate_dot_canary_settings(raw)
    from integrations.executive_mcp.personal_read import PERSONAL_READ_PROFILE
    from integrations.executive_mcp.web_ceo_v3 import validate_installed_mcp_profile_current
    profile = validate_installed_mcp_profile_current(raw.get('executive_mcp_profile', 'legacy'))
    enabled = raw.get('os_executive_transport', False)
    if type(enabled) is not bool or (enabled and profile != 'web_ceo_v3'):
        raise ValueError('OS Executive transport requires an explicit v3 boolean opt-in')
    from integrations.executive_mcp.release_control import RELEASE_CONTROL_PROFILE
    if profile == PERSONAL_READ_PROFILE and ({'workspace', 'steward', 'coo'} & set(raw)):
        raise ValueError('Personal read profile refuses optional mounts')
    if profile == RELEASE_CONTROL_PROFILE and ({'workspace', 'steward', 'coo'} & set(raw)):
        raise ValueError('Release control profile refuses optional mounts')
    if raw['schema'] != CONFIG_SCHEMA:
        raise ValueError('installed MCP schema differs')
    if not isinstance(raw['release_sha'], str) or re.fullmatch('[0-9a-f]{40}', raw['release_sha']) is None:
        raise ValueError('release identity is invalid')
    if type(raw['service_uid']) is not int or raw['service_uid'] != 458:
        raise ValueError('MCP requires its dedicated service identity')
    if type(raw['port']) is not int or not 1024 <= raw['port'] <= 65535:
        raise ValueError('MCP port is invalid')
    if raw['ceo_ingress_socket_path'] != '/var/run/mastermind-executive/ceo-ingress.sock':
        raise ValueError('MCP requires the canonical CeoIngress socket')
    if raw['audit_root'] != '/var/log/mastermind-executive/mcp-auth':
        raise ValueError('MCP requires its dedicated audit directory')
    validate_additional_resources(raw)
    validate_os_executive_resource(raw)
    validate_public_mcp_resource(raw)
    build_os_commission_client(raw)
    validate_optional_mounts(raw)
    build_installed_principal_ruling_target(raw)
    build_installed_selected_child_target(raw)
    validate_web_observation(raw)
    return raw


def require_sealed_path(path: Path, *, directory: bool = False) -> None:
    """Root-owned direct path, with no writable or symlink ancestor."""
    if not path.is_absolute():
        raise ValueError('sealed path must be absolute')
    for node in (path, *path.parents):
        info = node.lstat()
        if info.st_uid != 0 or stat.S_ISLNK(info.st_mode) or info.st_mode & 0o022:
            raise ValueError('sealed path ownership or permissions differ')
        is_dir = node != path or directory
        if not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode)):
            raise ValueError('sealed path type differs')
        if not is_dir and info.st_nlink != 1:
            raise ValueError('sealed configuration must have one link')


PUBLIC_ORIGIN = 'https://mcp.mastermind-x.com'
OS_EXECUTIVE_RESOURCE = PUBLIC_ORIGIN + '/os/executive'


def validate_os_executive_resource(raw):
    """One opt-in OS audience; existing tunnel resources stay configured beside it.

    Naming an audience here does not pin it to one endpoint: the gateway verifier
    accepts a token for any configured resource, so per-endpoint audience
    restriction is a separate gateway obligation (docs/EXECUTIVE_MCP.md section 8).
    """
    enabled = raw.get('os_executive_transport', False)
    if not enabled:
        if 'os_executive_resource' in raw:
            raise ValueError('OS Executive resource requires enabled v3 transport')
        return None
    if (raw.get('executive_mcp_profile') != 'web_ceo_v3'
            or type(enabled) is not bool
            or raw.get('os_executive_resource') != OS_EXECUTIVE_RESOURCE):
        raise ValueError('OS Executive resource must be the exact installed OS audience')
    return OS_EXECUTIVE_RESOURCE


PUBLIC_MCP_RESOURCE = PUBLIC_ORIGIN + '/mcp'
PUBLIC_MCP_METADATA_URL = PUBLIC_ORIGIN + '/.well-known/oauth-protected-resource/mcp'


def validate_public_mcp_resource(raw):
    """Opt-in public MCP audience: this gateway process serves /mcp for it alone.

    Absent keeps the installed behavior unchanged. Present, the value must be the
    exact public resource on Web-CEO v3, optionally with its explicit COO
    receiver. Release control and every other profile refuse it. A process that offers this
    audience at /mcp offers no other one there (the OS audience stays on its own
    transport routes), so the tunnel entrypoint needs its own gateway instance.
    """
    if 'public_mcp_resource' not in raw:
        return None
    coo = raw.get('coo')
    malformed_coo = 'coo' in raw and (
        type(coo) is not dict or not {'policy', 'binding'} <= set(coo)
        or set(coo) - {'policy', 'binding', 'missions'})
    if (raw.get('executive_mcp_profile') != 'web_ceo_v3'
            or raw['public_mcp_resource'] != PUBLIC_MCP_RESOURCE
            or 'principal_ruling_target' in raw or malformed_coo):
        raise ValueError(
            'public MCP resource must be the exact public audience on the plain v3 profile'
        )
    return PUBLIC_MCP_RESOURCE


def build_public_policies(raw, policies, additional_policies=()):
    """Public MCP audience over the primary grants; only the audience and challenge change."""
    resource = validate_public_mcp_resource(raw)
    if resource is None:
        return None
    from integrations.business_mcp_auth.contracts import validate_resource_policy
    from integrations.mastermind_executive_app.gateway import AppPolicies
    taken = {policies.read.resource, policies.submit.resource}
    for extra in additional_policies:
        taken.update((extra.read.resource, extra.submit.resource))
    if resource in taken:
        raise ValueError('public MCP resource cannot duplicate a configured Executive OAuth resource')
    return AppPolicies(
        read=validate_resource_policy(dataclasses.replace(
            policies.read, resource=resource, resource_metadata_url=PUBLIC_MCP_METADATA_URL)),
        submit=validate_resource_policy(dataclasses.replace(
            policies.submit, resource=resource, resource_metadata_url=PUBLIC_MCP_METADATA_URL)),
    )


def build_os_commission_client(raw):
    if raw.get("os_executive_transport", False) is not True:
        if "os_commission_port" in raw:
            raise ValueError("disabled OS transport refuses commission owner")
        return None
    if "os_commission_port" not in raw:
        raise ValueError("OS transport requires installed commission owner")
    # Keep the optional network client outside the sealed stdlib-only control path.
    from integrations.mastermind_executive_app.os_commission_client import StudioCommissionClient
    return StudioCommissionClient(port=raw["os_commission_port"])


def build_additional_policies(raw, policies):
    """Add sealed resource variants without changing existing principal grants."""
    from integrations.business_mcp_auth.contracts import validate_resource_policy
    from integrations.mastermind_executive_app.gateway import AppPolicies
    resources = validate_additional_resources(raw)
    os_resource = validate_os_executive_resource(raw)
    if os_resource is not None:
        resources += (os_resource,)
    if not resources:
        return ()
    if (len(resources) != len(set(resources))
            or policies.read.resource in resources
            or policies.submit.resource in resources):
        raise ValueError('primary Executive OAuth resource cannot be duplicated')
    return tuple(AppPolicies(
        read=validate_resource_policy(dataclasses.replace(policies.read, resource=resource)),
        submit=validate_resource_policy(dataclasses.replace(policies.submit, resource=resource)),
    ) for resource in resources)


OS_ASSET_SCHEMA = 'mastermind.os_assets.v1'


def optional_policies(raw):
    from integrations.business_mcp_auth.contracts import load_resource_policy
    result = {}
    names = {
        ('workspace', 'policy'): 'workspace',
        ('steward', 'policy'): 'steward',
        ('steward', 'content_policy'): 'content',
        ('coo', 'policy'): 'coo',
    }
    for block, fields in (
        ('workspace', ('policy',)),
        ('steward', ('policy', 'content_policy')),
        ('coo', ('policy',)),
    ):
        if block in raw:
            for field in fields:
                result[names[(block, field)]] = load_resource_policy(raw[block][field])
    return result


def validate_optional_mounts(raw):
    shapes = {
        'workspace': {'policy', 'bindings'},
        'steward': {'policy', 'content_policy', 'content_profiles', 'allowed_origin'},
        'coo': {'policy', 'binding'},
    }
    for name, keys in shapes.items():
        if name in raw and (type(raw[name]) is not dict or not keys <= set(raw[name])
                or set(raw[name]) - keys - ({'missions'} if name == 'coo' else set())):
            raise ValueError('optional mount configuration differs')
    policies = optional_policies(raw)
    if 'workspace' in raw:
        from integrations.mastermind_workspace_app.project_authoring_grant import validate_project_bindings
        validate_project_bindings(raw['workspace']['bindings'], policies['workspace'])
    if 'steward' in raw:
        from integrations.executive_content_contract import ContentObserverProfiles
        content = policies['content']
        if (raw['steward']['allowed_origin'] != PUBLIC_ORIGIN
                or content.resource != PUBLIC_ORIGIN + '/workspace/window/current'
                or content.required_scopes != ('mastermind.workspace.content.read',)):
            raise ValueError('content resource or origin differs')
        from urllib.parse import urlsplit
        if (urlsplit(policies['steward'].resource).netloc != 'mcp.mastermind-x.com'
                or policies['steward'].required_scopes != ('mastermind.steward.read',)):
            raise ValueError('Steward host differs')
        profiles = ContentObserverProfiles.from_mapping(raw['steward']['content_profiles'])
        for slot in (profiles.web, profiles.mac):
            if slot.profile is not None and (slot.profile.policy_id != content.policy_id
                    or slot.profile.content_resource != content.resource
                    or slot.profile.content_scope != content.required_scopes[0]
                    or slot.profile.issuer_digest != hashlib.sha256(content.issuer.encode()).hexdigest()
                    or slot.profile.subject_digest not in content.allowed_subject_digests):
                raise ValueError('content profile policy differs')
    if 'coo' in raw:
        from integrations.mastermind_executive_app.coo_binding import validate_coo_binding
        from integrations.mastermind_executive_app.gateway import (
            _jwks_cache_contract, load_app_policies,
        )
        base = load_app_policies(raw['policies'])
        # Only the explicit public v3 receiver selects this separate resource.
        # Keep the primary pair intact for the other installed transports.
        receiver = build_public_policies(raw, base,
            build_additional_policies(raw, base)) or base
        coo = policies['coo']
        if (coo.resource_metadata_url != receiver.read.resource_metadata_url
                or _jwks_cache_contract(coo) != _jwks_cache_contract(receiver.read)):
            raise ValueError('COO policy must share the Executive resource and JWKS authority')
        if coo.policy_id in {base.read.policy_id, base.submit.policy_id}:
            raise ValueError('COO policy ID must be distinct from CEO policies')
        validate_coo_binding(raw['coo']['binding'], coo)
        if 'missions' in raw['coo']:
            from control_plane.coo_principal_host import validate_missions
            validate_missions(raw['coo']['missions'])
            from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
            from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
            if (raw['coo']['missions']
                    and raw.get('executive_mcp_profile') not in {WEB_CEO_V2_PROFILE, WEB_CEO_V3_PROFILE}):
                raise ValueError('COO mission activation requires an explicit supported Web-CEO profile')
    if len({p.policy_id for p in policies.values()}) != len(policies):
        raise ValueError('optional policy IDs must be distinct')


def current_projection_loader(config_path, source, initial, block, field, *, expected_uid=None):
    """Recheck the same sealed installation, allowing only projection rotation."""
    frozen = copy.deepcopy(initial)
    uid = frozen['service_uid'] if expected_uid is None else expected_uid
    if type(uid) is not int or uid < 0:
        raise ValueError('invalid installed reader identity')
    def load():
        require_sealed_path(source, directory=True)
        require_sealed_path(config_path)
        current = validate_document(json.loads(config_path.read_text()))
        if source.name != current['release_sha'] or os.geteuid() != uid:
            raise ValueError('installed process or release changed')
        if block not in current:
            raise ValueError('optional mount withdrawn')
        left, right = copy.deepcopy(current), copy.deepcopy(frozen)
        # Both public projections may rotate without changing installation/policy.
        for name, projection in (
            ('workspace', 'bindings'),
            ('steward', 'content_profiles'),
            ('coo', 'binding'),
            ('session_web_observation', 'permissions'),
        ):
            for value in (left, right):
                if name in value:
                    value[name][projection] = None
        # Disarming an exact delegation is dynamic; its immutable scope cannot rotate.
        for value in (left, right):
            for mission in value.get('coo', {}).get('missions', []):
                mission['enabled'] = None
        if left != right:
            raise ValueError('installed policy or configuration changed')
        return current[block] if field is None else current[block][field]
    return load



def observation_policies(raw):
    """The existing READ-capable policy variants, never a new identity realm."""
    from integrations.mastermind_executive_app.gateway import load_app_policies
    primary = load_app_policies(raw['policies'])
    additional = build_additional_policies(raw, primary)
    public = build_public_policies(raw, primary, additional)
    pairs = (primary, *additional) + (() if public is None else (public,))
    return tuple(policy for pair in pairs for policy in (pair.read, pair.submit))


def validate_web_observation(raw):
    if 'session_web_observation' not in raw:
        return
    if raw.get('executive_mcp_profile') != 'web_ceo_v3':
        raise ValueError('profile observation requires explicit Web-CEO v3')
    from integrations.session_bridge.installed_web_observation import parse_configuration
    parse_configuration(raw['session_web_observation'], observation_policies(raw))


def _web_observation_install_identity(config_path, source):
    """Use the existing root seal plus descriptor-bound ACL checks and identity."""
    from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
    require_sealed_path(source, directory=True)
    require_sealed_path(config_path)
    seen = set()
    for root in (source, config_path):
        for node in (root, *root.parents):
            if node not in seen:
                seen.add(node)
                try:
                    if has_macos_acl(node):
                        raise ValueError('installed observation seal is unavailable')
                except FilesystemSecurityError:
                    raise ValueError('installed observation seal is unavailable') from None
    info = config_path.lstat()
    if not 0 < info.st_size <= 262144:
        raise ValueError('installed observation source is unavailable')
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def installed_web_observation_owner(config_path, source, *, expected_uid,
                                    initial=None, clock=None):
    """Bind optional permissions to the same root-sealed installation only.

    Only permission rows/generation may rotate. File-instance identity is part
    of every ephemeral revision, so replacing or restoring identical grants
    cannot revive a read captured under an earlier observed file instance.
    No profile/browser/source access occurs in this network-safe constructor.
    """
    if initial is not None and 'session_web_observation' not in initial:
        return None
    from integrations.business_mcp_auth.contracts import AuthError
    from integrations.session_bridge.installed_web_observation import (
        ObservationPermissionReader, observation_state,
    )
    path, source = Path(config_path), Path(source)
    try:
        first = _web_observation_install_identity(path, source)
        raw = validate_document(json.loads(path.read_text()) if initial is None
                                else copy.deepcopy(initial))
        if first != _web_observation_install_identity(path, source):
            raise ValueError('installed observation source changed')
        if 'session_web_observation' not in raw:
            return None
        policies = observation_policies(raw)
        read_projection = current_projection_loader(path, source, raw,
            'session_web_observation', None, expected_uid=expected_uid)

        def load():
            before = _web_observation_install_identity(path, source)
            try:
                value = read_projection()
            except AuthError:
                raise ValueError('installed observation policy is unavailable') from None
            after = _web_observation_install_identity(path, source)
            if before != after:
                raise ValueError('installed observation source changed')
            revision = hashlib.sha256(json.dumps(
                {'file_instance': before, 'observation': value},
                sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                allow_nan=False).encode('ascii')).hexdigest()
            return observation_state(value, policies, revision)

        load()  # Qualify current identity/release/configuration; never cache it.
        return ObservationPermissionReader(load_state=load, clock=clock)
    except AuthError:
        raise ValueError('installed observation policy is unavailable') from None


def build_coo_principal_authorizer(raw, source, config_path):
    """Compose the sealed COO principal gate from the existing install owner.

    The installed config remains the only durable source. The returned
    authorizer reloads only the binding projection on every check; policy,
    process identity, release identity and every other installed field remain
    frozen by current_projection_loader.
    """
    validate_document(raw)
    if 'coo' not in raw:
        return None
    policies = optional_policies(raw)
    loader = current_projection_loader(config_path, source, raw, 'coo', 'binding')
    from integrations.mastermind_executive_app.coo_binding import coo_authorizer
    return coo_authorizer(policy=policies['coo'], load_binding=loader)


def installed_os_session_policy_source(config_path, source, *, expected_uid):
    """Bind the current root-sealed OS OAuth policy pair to the Runtime reader.

    The incumbent network gateway installation is the sole authority for the
    policy IDs and resource. Runtime may inspect that *same* sealed installation
    under its own trusted uid, not derive pairing from a caller's bearer/frame
    or add a second policy configuration. Missing/disabled/moved installations
    are unavailable, never an inferred permission grant.
    """
    from integrations.mastermind_executive_app.gateway import load_app_policies
    from integrations.business_mcp_auth.contracts import AuthError
    from integrations.session_bridge.runtime_return import _trusted_read_pair
    from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

    path, source = Path(config_path), Path(source)

    def require_policy_seal():
        # POSIX mode alone is not an ownership seal on macOS: a non-root
        # inherited ACL can grant directory-entry replacement privileges.
        # Reuse the incumbent descriptor-bound ACL observer on both the
        # installed gateway file and every ancestor of both sealed roots.
        require_sealed_path(source, directory=True)
        require_sealed_path(path)
        seen = set()
        for root in (source, path):
            for node in (root, *root.parents):
                if node in seen:
                    continue
                seen.add(node)
                try:
                    if has_macos_acl(node):
                        raise ValueError("installed OS policy seal unavailable")
                except FilesystemSecurityError:
                    raise ValueError("installed OS policy seal unavailable") from None

    require_policy_seal()
    try:
        raw = validate_document(json.loads(path.read_text()))
    except AuthError:
        # Optional mounted policies are parsed during validate_document and
        # must obey the same bounded Control-factory refusal contract.
        raise ValueError("installed OS policy pair unavailable") from None
    require_policy_seal()
    if (type(expected_uid) is not int or expected_uid < 0
            or os.geteuid() != expected_uid
            or source.name != raw["release_sha"]
            or raw.get("os_executive_transport") is not True):
        raise ValueError("installed OS policy source unavailable")

    def os_pair(base_policies):
        try:
            additional = build_additional_policies(raw, load_app_policies(base_policies))
        except AuthError:
            # The closed OAuth parser uses AuthError(RuntimeError), which the
            # Control factory's fail-dark ValueError guard cannot otherwise
            # catch. A malformed root-sealed policy must not kill Control.
            raise ValueError("installed OS policy pair unavailable") from None
        paired = [pair for pair in additional
                  if pair.read.resource == OS_EXECUTIVE_RESOURCE
                  and pair.submit.resource == OS_EXECUTIVE_RESOURCE]
        if len(paired) != 1:
            raise ValueError("installed OS policy pair unavailable")
        try:
            # Reuse the Runtime owner's exact pairing discriminator, not a
            # second policy-ID/issuer/subject invariant that could drift.
            _trusted_read_pair(paired[0])
        except (ValueError, TypeError, AuthError):
            raise ValueError("installed OS policy pair unavailable") from None
        return paired[0]

    initial = os_pair(raw["policies"])
    read_sealed_policies = current_projection_loader(
        path, source, raw, "policies", None, expected_uid=expected_uid)

    def current():
        require_policy_seal()
        try:
            # The incumbent projection loader can also parse optional mounted
            # policies during a drift check; normalize that closed AuthError
            # instead of taking down the entire Session Bridge at read time.
            pair = os_pair(read_sealed_policies())
        except AuthError:
            raise ValueError("installed OS policy pair unavailable") from None
        require_policy_seal()
        if pair != initial:
            raise ValueError("installed OS policy pair changed")
        return pair

    return current


def build_os_asset_manifest(source):
    """Deterministic build law; returns data, never writes or installs assets."""
    root = Path(source) / 'app/mastermind_os/dist'
    if root.is_symlink() or not root.is_dir() or (root/'assets').is_symlink():
        raise ValueError('OS asset directory differs')
    names, directories = [], set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('OS assets cannot be symlinks')
        if path.is_file() and path != root/'asset-manifest.json':
            names.append(path.relative_to(root).as_posix())
        elif path.is_dir():
            directories.add(path.relative_to(root).as_posix())
    from integrations.mastermind_executive_app.os_assets import os_asset_mimes
    mimes = os_asset_mimes(names)
    # The closed names/MIME owner also determines the exact parent topology;
    # no independent size switch may drop required font or third-party notices.
    expected_directories = {parent.as_posix() for name in mimes for parent in Path(name).parents
                            if parent.as_posix() != '.'}
    if directories != expected_directories:
        raise ValueError('OS asset directory differs')
    css = [name for name, mime in mimes.items() if mime == 'text/css; charset=utf-8']
    js = [name for name, mime in mimes.items() if mime == 'text/javascript; charset=utf-8']
    files = []
    for name in sorted(names):
        data = (root/name).read_bytes()
        if not 0 < len(data) <= 4 * 1024 * 1024:
            raise ValueError('OS asset budget exceeded')
        files.append({'path': name, 'byte_count': len(data),
                      'sha256': hashlib.sha256(data).hexdigest(),
                      'mime': mimes[name]})
    text = (root/'index.html').read_text(encoding='utf-8')
    references = set(re.findall(r'(?:src|href)=["\']([^"\']+)["\']', text))
    if references != {'/os/'+css[0], '/os/'+js[0]}:
        raise ValueError('OS index asset references differ')
    return {'schema': OS_ASSET_SCHEMA, 'files': files}


def load_os_app(source):
    from integrations.executive_mcp.server import OsStaticApp
    root = source/'app/mastermind_os/dist'
    manifest_path = root/'asset-manifest.json'
    require_sealed_path(root, directory=True)
    require_sealed_path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if (type(manifest) is not dict or set(manifest) != {'schema', 'files'}
            or type(manifest['files']) is not list
            or any(type(item) is not dict or set(item) != {'path', 'byte_count', 'sha256', 'mime'}
                   or type(item['byte_count']) is not int for item in manifest['files'])
            or manifest != build_os_asset_manifest(source)):
        raise ValueError('OS manifest or content hash differs')
    assets = {}
    for item in manifest['files']:
        path = root/item['path']
        require_sealed_path(path)
        data = path.read_bytes()
        if len(data) != item['byte_count'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('OS bytes changed during load')
        route = '/os/' if item['path'] == 'index.html' else '/os/'+item['path']
        assets[route] = (data, item['mime'])
    return OsStaticApp(assets)


def build_optional_apps(raw, source, config_path, sink):
    """Compose existing App owners using only sealed public projections."""
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
    from integrations.mastermind_executive_app.gateway import _default_jwks_cache, _jwks_cache_contract
    from integrations.executive_mcp.server import AuditedWorkspaceApp
    policies = optional_policies(raw)
    caches, authenticators, verifiers = {}, {}, {}
    for name, policy in policies.items():
        key = _jwks_cache_contract(policy)
        if key not in caches:
            caches[key] = _default_jwks_cache(policy)
        authenticator = JwtAuthenticator(policy=policy, jwks_cache=caches[key])
        authenticators[name] = authenticator
        verifiers[name] = MastermindTokenVerifier(authenticator=authenticator, policy=policy,
            now=lambda: int(time.time()), audit_sink=sink)
    mounts = {}
    if 'workspace' in raw:
        from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
        from integrations.mastermind_workspace_app.contract import (
            workspace_authorizers, workspace_control_room_authorizers,
        )
        from common.workspace_control_room_action_contract import OPERATIONS
        from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
        workspace_project_bindings_loader = current_projection_loader(config_path, source, raw, 'workspace', 'bindings')
        from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
        def legacy_workspace_loader(current_loader=workspace_project_bindings_loader, project_policy=policies['workspace']):
            return legacy_workspace_document(current_loader(), project_policy)
        gate, _ = workspace_authorizers(policy=policies['workspace'], load_bindings=legacy_workspace_loader)
        from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
        discovery_gate, _ = workspace_control_room_authorizers(
            policy=policies['workspace'], load_bindings=legacy_workspace_loader, action='discover')
        action_gates = {
            operation: workspace_control_room_authorizers(
                policy=policies['workspace'], load_bindings=legacy_workspace_loader, action=operation)[0]
            for operation in OPERATIONS
        }
        workspace_config = WorkspaceAppConfig(authenticator=authenticators['workspace'],
            now=lambda: int(time.time()), authorize_principal=gate,
            authorize_discovery=discovery_gate, authorize_actions=action_gates,
            project_admission_load_bindings=workspace_project_bindings_loader,
            source_operation_context=WorkspaceSourceOperationContextFactory(
                policy=policies['workspace'], load_bindings=workspace_project_bindings_loader),
            client=CeoIngressWorkspaceClient(raw['ceo_ingress_socket_path']))
        app = create_workspace_app(workspace_config)
        mounts['workspace_app'] = AuditedWorkspaceApp(app, verifiers['workspace'],
            authenticator=authenticators['workspace'],authorize_principal=gate,
            fresh_workspace_config=workspace_config)
    if 'steward' in raw:
        from integrations.mastermind_steward_app.installed import (
            LiveWindowProfilesConfig, build_installed_steward_app_with_profiles)
        profiles = LiveWindowProfilesConfig(authenticator=authenticators['content'],
            content_policy=policies['content'],
            profile_loader=current_projection_loader(config_path, source, raw, 'steward', 'content_profiles'),
            ceo_ingress_socket_path=Path(raw['ceo_ingress_socket_path']),
            now=lambda: int(time.time()), allowed_origin=PUBLIC_ORIGIN, audit_sink=sink)
        mounts['content_app'] = build_installed_steward_app_with_profiles(profiles_config=profiles,
            steward_policy=policies['steward'], steward_token_verifier=verifiers['steward'])
    manifest_path = source/'app/mastermind_os/dist/asset-manifest.json'
    if os.path.lexists(manifest_path):
        mounts['os_app'] = load_os_app(source)
    return mounts


class PolicyAuditSink:
    """Route existing A1 audit facts to the corresponding durable A1 sink."""
    def __init__(self, policies, root: Path, *, optional=None):
        from integrations.business_mcp_auth.audit import DurableAuthAuditSink
        self._sinks = {}
        entries = [('read', policies.read), ('submit', policies.submit), *sorted((optional or {}).items())]
        if len({policy.policy_id for _, policy in entries}) != len(entries):
            raise ValueError('audit policy IDs must be distinct')
        try:
            for name, policy in entries:
                fd = os.open(root/name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    self._sinks[policy.policy_id] = DurableAuthAuditSink.open(fd, policy_id=policy.policy_id)
                finally:
                    os.close(fd)
        except BaseException:
            self.close()
            raise

    def emit(self, event):
        self._sinks[event.policy_id].emit(event)

    def close(self):
        for sink in self._sinks.values():
            sink.close()


def build_installed_coo_settings(raw, source, config_path, executive, *, expected_uid=None):
    """Use the canonical App-peer fact transport; never open Runtime in MCP."""
    if not raw.get('coo', {}).get('missions'):
        return None
    validate_document(raw)
    from integrations.mastermind_executive_app.coo import CooAppSettings
    from integrations.mastermind_executive_app.coo_installed import CooFactsClient
    from integrations.mastermind_executive_app.coo_binding import principal_frame
    from ops.executive_os.coo_principal_host import CooInstalledSource, CLAUDE_PRINCIPAL_POLICY
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    public_mcp = executive.public_policies is not None
    if public_mcp and raw.get('executive_mcp_profile') != 'web_ceo_v3':
        raise ValueError('public COO requires the installed Web-CEO v3 profile')
    client = CooFactsClient(raw['ceo_ingress_socket_path'])
    uid = raw['service_uid'] if expected_uid is None else expected_uid
    def registry():
        policy = Path(source) / CLAUDE_PRINCIPAL_POLICY
        require_sealed_path(policy)
        return ExecutionCapabilityRegistry.load(policy, source_root=source)
    catalogue_source = CooInstalledSource(
        current_projection_loader(config_path, source, raw, 'coo', None, expected_uid=uid), registry)
    settings = dict(executive=executive, policy=optional_policies(raw)['coo'],
        public_mcp=public_mcp,
        load_binding=current_projection_loader(config_path, source, raw, 'coo', 'binding'),
        authority_provider=client.authority, mission_provider=client.mission,
        catalogue_provider=lambda principal, work_ref=None: catalogue_source.catalogue_for_principal(
            principal_frame(principal), work_ref=work_ref),
        agentos_context_provider=client.agentos_context,
        agentos_current_context_provider=client.agentos_current_context)
    publication = build_installed_selected_child_target(raw)
    if publication is not None:
        # One frozen publication, read through the SHARED generation-bound
        # reader. The block is not a rotatable projection: a replaced, relinked
        # or rewritten installation refuses instead of silently retargeting a
        # running App, and nothing here rebuilds a target from a model
        # argument. The Control source reads the same publication through the
        # very same reader, so both installed consumers prove one generation.
        uid = raw['service_uid'] if expected_uid is None else expected_uid
        reader = fixed_selected_child_target_reader(
            config_path, source, raw, expected_uid=uid)
        if reader is None:
            raise ValueError('installed selected child target is unavailable')
        settings['selected_child_target'] = reader()
    return CooAppSettings(**settings)


def build_installed_principal_ruling_target(raw):
    """One immutable sealed target; absence preserves every installed route.

    The existing current_projection_loader compares this entire block on each
    principal binding read. A changed target requires new host qualification;
    it cannot silently retarget an already-running App. Control independently
    resolves and admits the original pending obligation at the effect boundary.
    """
    if 'principal_ruling_target' not in raw:
        return None
    target = raw['principal_ruling_target']
    if (type(target) is not dict
            or set(target) != {'work_ref', 'obligation_id', 'reasoning_surface'}
            or raw.get('executive_mcp_profile') not in {'web_ceo_v2', 'web_ceo_v3'}):
        raise ValueError('principal ruling requires an exact supported host target')
    from control_plane.principal_ruling_target import PrincipalRulingTarget
    selected = PrincipalRulingTarget(**target)
    missions = raw.get('coo', {}).get('missions', [])
    if (type(missions) is not list or len([row for row in missions
            if type(row) is dict and row.get('work_ref') == selected.work_ref]) != 1):
        raise ValueError('principal ruling requires the exact installed COO mission')
    return selected


def build_installed_selected_child_target(raw):
    """The frozen selected-child publication and its exact installed mission.

    Absence preserves every installed route and every existing document.
    A present publication is a closed projection whose material digest is
    over exactly the frozen coordinates, and it must name exactly one
    installed COO mission: the installed mission is the host's own
    association, never a supplied selector.
    """
    if 'selected_child_target' not in raw:
        return None
    from control_plane.coo_principal_host import validate_selected_child_target
    publication = validate_selected_child_target(raw['selected_child_target'])
    missions = raw.get('coo', {}).get('missions', [])
    if len([row for row in missions
            if type(row) is dict and row.get('work_ref') == publication['work_ref']]) != 1:
        raise ValueError('selected child target requires the exact installed COO mission')
    return publication


def build_selected_child_target(publication, currentness_guard):
    """Construct the selected-child target from one qualified publication.

    The published material is reconstructed into the target's own frozen
    children, and the target's own material digest must equal the published
    digest. The guard proves the FIXED publication and its legitimate
    read/source identity; it never reruns dispatch eligibility, recomputes
    an ordinal, requires the original child to remain unclaimed or calls
    the dialogue guard merely to read the original command.
    """
    from integrations.hermes_delegate.executive import (
        ExecutiveChildSelection, ExecutiveSelectedChild, ExecutiveSelectedChildTarget,
    )
    children = []
    for item in publication['children']:
        selection = ExecutiveChildSelection(
            root_job_id=item['root_job_id'],
            parent_job_id=item['parent_job_id'],
            job_id=item['job_id'],
            plan_attempt_id=item['plan_attempt_id'],
            plan_digest=item['plan_digest'],
            plan_step_id=item['plan_step_id'],
            repair_round=item['repair_round'],
            expected_current_attempt_id=item['expected_current_attempt_id'],
        )
        children.append(ExecutiveSelectedChild(
            selection=selection, attempt_ordinal=item['attempt_ordinal']))
    target = ExecutiveSelectedChildTarget(
        work_ref=publication['work_ref'], children=tuple(children),
        currentness_guard=currentness_guard)
    digest = getattr(target, 'material_digest', None)
    observed = digest() if callable(digest) else digest
    if type(observed) is not str or observed != publication['material_digest']:
        raise ValueError('installed selected child target differs from its publication')
    return target


def fixed_selected_child_target_reader(config_path, source, initial, *, expected_uid):
    """Bind the frozen selected-child publication to one file generation.

    This is the SHARED owner of the selected-child currentness proof. The
    installed App settings and the installed Control source both read their
    frozen publication through THIS reader, so one generation is proven in
    one place instead of twice with two different laws.

    It is deliberately not a rotatable registry. A replacement, an ABA
    write, a relink, a symlink or a fork requires fresh host qualification,
    even when the document returns to its old bytes. The guard proves the
    FIXED publication and its legitimate read/source identity; it never
    reruns fresh dispatch eligibility, recomputes an ordinal, requires the
    original child to remain unclaimed, or calls the dialogue guard merely
    to read the original command.

    Only the selected-child target is narrowed this way. Every other
    rotatable projection keeps its incumbent ``current_projection_loader``.
    """
    path, source = Path(config_path), Path(source)
    publication = build_installed_selected_child_target(initial)
    if publication is None:
        return None
    pid = os.getpid()

    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                info.st_gid)

    def file_identity(info):
        return (*identity(info), info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def observe():
        if os.getpid() != pid or os.geteuid() != expected_uid:
            raise ValueError('installed selected child target reader is not this identity')
        require_sealed_path(source, directory=True)
        require_sealed_path(path)
        nodes = tuple(dict.fromkeys((source, *source.parents, *path.parents)))
        namespace = tuple(identity(node.lstat()) for node in nodes)
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('installed selected child target is not one sealed object')
            contents = handle.read()
            after = os.fstat(handle.fileno())
            require_sealed_path(source, directory=True)
            require_sealed_path(path)
            if (file_identity(before) != file_identity(after)
                    or file_identity(after) != file_identity(path.lstat())
                    or namespace != tuple(identity(node.lstat()) for node in nodes)):
                raise ValueError('installed selected child target changed during the read')
        current = validate_document(json.loads(contents))
        if current != initial or source.name != current['release_sha']:
            raise ValueError('installed selected child target changed')
        return namespace, file_identity(after), hashlib.sha256(contents).digest()

    generation = observe()

    def currentness_guard():
        if observe() != generation:
            raise ValueError('installed selected child target changed')

    target = build_selected_child_target(publication, currentness_guard)

    def read():
        currentness_guard()
        return target
    return read


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args(argv)
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('MCP launcher requires -I -B')
    source = Path(__file__).absolute().parents[2]
    require_sealed_path(source, directory=True)
    require_sealed_path(args.config)
    sys.path.insert(0, str(source))
    raw = validate_document(json.loads(args.config.read_text()))
    if source.name != raw['release_sha'] or os.geteuid() != raw['service_uid']:
        raise ValueError('MCP source or process identity differs from its installation')
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import load_app_policies
    from integrations.executive_mcp.server import (
        build_executive_mcp_app, build_personal_read_mcp_app,
        build_web_ceo_v2_mcp_app, build_web_ceo_v3_mcp_app,
        build_web_ceo_v2_with_coo_mcp_app, build_web_ceo_v3_with_coo_mcp_app,
        build_web_ceo_sessions_mcp_app,
        build_release_control_mcp_app, build_web_ceo_release_mcp_app,
    )
    from integrations.executive_mcp.personal_read import PERSONAL_READ_PROFILE
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from integrations.executive_mcp.release_control import RELEASE_CONTROL_PROFILE
    from integrations.executive_mcp.web_ceo_release import WEB_CEO_RELEASE_PROFILE
    from integrations.executive_mcp.web_ceo_v3 import (
        WEB_CEO_V3_PROFILE, validate_installed_mcp_profile_current,
    )
    import uvicorn

    policies = load_app_policies(raw['policies'])
    additional_policies = build_additional_policies(raw, policies)
    settings = AppSettings(
        policies=policies, mastermind_root=source, macro_root_flag=None, environ={},
        ceo_ingress_socket_path=raw['ceo_ingress_socket_path'],
        read_from_ceo_ingress=True, additional_policies=additional_policies,
        public_policies=build_public_policies(raw, policies, additional_policies),
        read_timeout=65.0,
    )
    profile = validate_installed_mcp_profile_current(
        raw.get('executive_mcp_profile', 'legacy')
    )
    sink = PolicyAuditSink(policies, Path(raw['audit_root']), optional=optional_policies(raw))
    try:
        mounts = (
            {} if profile in (PERSONAL_READ_PROFILE, RELEASE_CONTROL_PROFILE)
            else build_optional_apps(raw, source, args.config, sink)
        )
        if profile == RELEASE_CONTROL_PROFILE:
            app = build_release_control_mcp_app(settings, audit_sink=sink)
        elif profile == WEB_CEO_RELEASE_PROFILE:
            app = build_web_ceo_release_mcp_app(settings, audit_sink=sink, **mounts)
        elif profile == PERSONAL_READ_PROFILE:
            app = build_personal_read_mcp_app(settings, audit_sink=sink)
        elif profile == WEB_CEO_V3_PROFILE:
            from integrations.session_bridge.return_tools import NativeReplyReadTool
            from integrations.session_bridge.reference_tools import NativeReplyReferencesTool
            from integrations.mosyle_mdm.client import MosyleInventoryClient
            from integrations.mosyle_mdm.credential import FileMosyleCredentialSource
            from integrations.session_bridge.installed import InstalledSessionBridgeClient

            mdm_reader = MosyleInventoryClient(
                FileMosyleCredentialSource(
                    expected_uid=os.geteuid(), expected_gid=os.getegid()
                )
            )
            session_client = InstalledSessionBridgeClient(
                settings.ceo_ingress_socket_path
            )
            coo_settings = build_installed_coo_settings(raw, source, args.config, settings)
            v3_builder = (
                build_web_ceo_v3_mcp_app if coo_settings is None
                else build_web_ceo_v3_with_coo_mcp_app
            )
            v3_kwargs = {}
            web_observation = installed_web_observation_owner(
                args.config, source, expected_uid=raw["service_uid"], initial=raw)
            if web_observation is not None:
                v3_kwargs["session_web_read_tools"] = web_observation.network_tools(session_client)
            if coo_settings is not None:
                v3_kwargs["coo_settings"] = coo_settings
                v3_kwargs["principal_ruling_target"] = build_installed_principal_ruling_target(raw)
            if raw.get("reply_events_armed",False):
                from integrations.session_bridge.installed_reply_events import build_installed_reply_event_rpc
                from integrations.session_bridge.reply_policy_selection import ReplyPolicySelection
                from integrations.session_bridge.dot_canary_policy_selection import validate_dot_canary_settings
                v3_kwargs["reply_event_rpc"] = build_installed_reply_event_rpc(
                    settings.ceo_ingress_socket_path,ReplyPolicySelection((policies,*additional_policies)),
                    clock=lambda:int(settings.clock()),enabled=True,
                    canary_enabled=validate_dot_canary_settings(raw) is not None)
            # One installed client instance; the opt-in OS session transport
            # receives this same object only while the transport is enabled.
            os_transport_enabled = raw.get('os_executive_transport', False)
            app = v3_builder(
                settings,
                audit_sink=sink,
                mdm_reader=mdm_reader,
                session_target_projector=session_client.targets,
                session_reply_handler=session_client.send,
                session_summon_handler=session_client.summon,
                session_reply_read_tool=NativeReplyReadTool(session_client),
                session_reply_references_tool=NativeReplyReferencesTool(session_client),
                enable_os_executive_transport=raw.get('os_executive_transport', False),
                os_executive_resource=validate_os_executive_resource(raw),
                os_commission_preparer=build_os_commission_client(raw),
                os_session_bridge_client=(
                    session_client if os_transport_enabled else None
                ),
                **v3_kwargs,
                **mounts,
            )
        elif profile == WEB_CEO_SESSIONS_PROFILE:
            from integrations.session_bridge.installed import InstalledSessionBridgeClient

            from integrations.session_bridge.return_tools import NativeReplyReadTool
            from integrations.session_bridge.reference_tools import NativeReplyReferencesTool
            session_client = InstalledSessionBridgeClient(
                settings.ceo_ingress_socket_path
            )
            app = build_web_ceo_sessions_mcp_app(
                settings,
                audit_sink=sink,
                session_target_projector=session_client.targets,
                session_reply_handler=session_client.send,
                session_summon_handler=session_client.summon,
                session_reply_read_tool=NativeReplyReadTool(session_client),
                session_reply_references_tool=NativeReplyReferencesTool(session_client),
                **mounts,
            )
        elif profile == WEB_CEO_V2_PROFILE:
            coo_settings = build_installed_coo_settings(raw, source, args.config, settings)
            if coo_settings is None:
                app = build_web_ceo_v2_mcp_app(settings, audit_sink=sink, **mounts)
            else:
                app = build_web_ceo_v2_with_coo_mcp_app(settings, coo_settings=coo_settings,
                    audit_sink=sink,
                    principal_ruling_target=build_installed_principal_ruling_target(raw), **mounts)
        else:
            app = build_executive_mcp_app(settings, audit_sink=sink, **mounts)
        uvicorn.run(app, host='127.0.0.1', port=raw['port'], access_log=False,
                    proxy_headers=True, forwarded_allow_ips='127.0.0.1')
    finally:
        sink.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        print('executive-mcp: installed configuration refused', file=sys.stderr)
        raise SystemExit(2)

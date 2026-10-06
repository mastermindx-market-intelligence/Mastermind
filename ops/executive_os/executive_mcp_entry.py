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
            or not set(raw) <= CONFIG_KEYS | {'workspace', 'steward', 'coo', 'executive_mcp_profile', 'executive_additional_resources', 'os_executive_transport', 'os_executive_resource', 'os_commission_port'}):
        raise ValueError('installed MCP configuration fields differ')
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
    build_os_commission_client(raw)
    validate_optional_mounts(raw)
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
    """One opt-in OS audience; existing tunnel resources remain independent."""
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
        from integrations.mastermind_workspace_app.contract import validate_workspace_bindings
        validate_workspace_bindings(raw['workspace']['bindings'], policies['workspace'])
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
        coo = policies['coo']
        if (coo.resource_metadata_url != base.read.resource_metadata_url
                or _jwks_cache_contract(coo) != _jwks_cache_contract(base.read)):
            raise ValueError('COO policy must share the Executive resource and JWKS authority')
        if coo.policy_id in {base.read.policy_id, base.submit.policy_id}:
            raise ValueError('COO policy ID must be distinct from CEO policies')
        validate_coo_binding(raw['coo']['binding'], coo)
        if 'missions' in raw['coo']:
            from control_plane.coo_principal_host import validate_missions
            validate_missions(raw['coo']['missions'])
            from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
            if raw['coo']['missions'] and raw.get('executive_mcp_profile') != WEB_CEO_V2_PROFILE:
                raise ValueError('COO mission activation requires the explicit Web-CEO v2 profile')
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
    expected_directories = {'assets'} | ({'licenses', 'licenses/fonts'} if len(names) == 9 else set())
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
    """Compose existing read owners using only sealed public projections."""
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
        from integrations.mastermind_workspace_app.contract import workspace_authorizers
        from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
        loader = current_projection_loader(config_path, source, raw, 'workspace', 'bindings')
        gate, _ = workspace_authorizers(policy=policies['workspace'], load_bindings=loader)
        app = create_workspace_app(WorkspaceAppConfig(authenticator=authenticators['workspace'],
            now=lambda: int(time.time()), authorize_principal=gate,
            client=CeoIngressWorkspaceClient(raw['ceo_ingress_socket_path'])))
        mounts['workspace_app'] = AuditedWorkspaceApp(app, verifiers['workspace'])
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


def build_installed_coo_settings(raw, source, config_path, executive):
    """Use the canonical App-peer fact transport; never open Runtime in MCP."""
    if not raw.get('coo', {}).get('missions'):
        return None
    validate_document(raw)
    from integrations.mastermind_executive_app.coo import CooAppSettings
    from integrations.mastermind_executive_app.coo_installed import CooFactsClient
    client = CooFactsClient(raw['ceo_ingress_socket_path'])
    return CooAppSettings(executive=executive, policy=optional_policies(raw)['coo'],
        load_binding=current_projection_loader(config_path, source, raw, 'coo', 'binding'),
        authority_provider=client.authority, mission_provider=client.mission)


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
        build_web_ceo_v2_mcp_app, build_web_ceo_v3_mcp_app, build_web_ceo_v2_with_coo_mcp_app,
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
            app = build_web_ceo_v3_mcp_app(
                settings,
                audit_sink=sink,
                mdm_reader=mdm_reader,
                session_target_projector=session_client.targets,
                session_reply_handler=session_client.send,
                session_summon_handler=session_client.summon,
                session_reply_read_tool=NativeReplyReadTool(session_client),
                enable_os_executive_transport=raw.get('os_executive_transport', False),
                os_executive_resource=validate_os_executive_resource(raw),
                os_commission_preparer=build_os_commission_client(raw),
                **mounts,
            )
        elif profile == WEB_CEO_SESSIONS_PROFILE:
            from integrations.session_bridge.installed import InstalledSessionBridgeClient

            from integrations.session_bridge.return_tools import NativeReplyReadTool
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
                **mounts,
            )
        elif profile == WEB_CEO_V2_PROFILE:
            coo_settings = build_installed_coo_settings(raw, source, args.config, settings)
            if coo_settings is None:
                app = build_web_ceo_v2_mcp_app(settings, audit_sink=sink, **mounts)
            else:
                app = build_web_ceo_v2_with_coo_mcp_app(settings, coo_settings=coo_settings,
                    audit_sink=sink, **mounts)
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

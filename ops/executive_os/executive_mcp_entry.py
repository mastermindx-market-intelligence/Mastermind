"""Root-configured, dedicated-uid launcher for the existing five-tool MCP App.

Run with the separately provisioned network Python runtime and -I -B. The
sealed control Python remains SDK-free. This launcher never opens Runtime.
"""
from __future__ import annotations

import argparse
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


def validate_document(raw):
    if (type(raw) is not dict or not CONFIG_KEYS <= set(raw)
            or not set(raw) <= CONFIG_KEYS | {'workspace', 'steward', 'executive_mcp_profile'}):
        raise ValueError('installed MCP configuration fields differ')
    from integrations.executive_mcp.web_ceo import validate_installed_mcp_profile
    validate_installed_mcp_profile(raw.get('executive_mcp_profile', 'legacy'))
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
OS_ASSET_SCHEMA = 'mastermind.os_assets.v1'
OS_MIMES = {'html': 'text/html; charset=utf-8', 'css': 'text/css; charset=utf-8',
            'js': 'text/javascript; charset=utf-8'}


def optional_policies(raw):
    from integrations.business_mcp_auth.contracts import load_resource_policy
    result = {}
    for block, fields in (('workspace', ('policy',)), ('steward', ('policy', 'content_policy'))):
        if block in raw:
            for field in fields:
                name = 'workspace' if block == 'workspace' else 'steward' if field == 'policy' else 'content'
                result[name] = load_resource_policy(raw[block][field])
    return result


def validate_optional_mounts(raw):
    shapes = {'workspace': {'policy', 'bindings'},
              'steward': {'policy', 'content_policy', 'content_profiles', 'allowed_origin'}}
    for name, keys in shapes.items():
        if name in raw and (type(raw[name]) is not dict or set(raw[name]) != keys):
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
    if len({p.policy_id for p in policies.values()}) != len(policies):
        raise ValueError('optional policy IDs must be distinct')


def current_projection_loader(config_path, source, initial, block, field):
    """Recheck the same sealed installation, allowing only projection rotation."""
    frozen = copy.deepcopy(initial)
    def load():
        require_sealed_path(source, directory=True)
        require_sealed_path(config_path)
        current = validate_document(json.loads(config_path.read_text()))
        if source.name != current['release_sha'] or os.geteuid() != current['service_uid']:
            raise ValueError('installed process or release changed')
        if block not in current:
            raise ValueError('optional mount withdrawn')
        left, right = copy.deepcopy(current), copy.deepcopy(frozen)
        # Both public projections may rotate without changing installation/policy.
        for name, projection in (('workspace', 'bindings'), ('steward', 'content_profiles')):
            for value in (left, right):
                if name in value:
                    value[name][projection] = None
        if left != right:
            raise ValueError('installed policy or configuration changed')
        return current[block][field]
    return load


def build_os_asset_manifest(source):
    """Deterministic build law; returns data, never writes or installs assets."""
    root = Path(source) / 'app/mastermind_os/dist'
    if root.is_symlink() or not root.is_dir() or (root/'assets').is_symlink():
        raise ValueError('OS asset directory differs')
    names = []
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('OS assets cannot be symlinks')
        if path.is_file() and path != root/'asset-manifest.json':
            names.append(path.relative_to(root).as_posix())
        elif path.is_dir() and path != root/'assets':
            raise ValueError('OS asset directory differs')
    css = [n for n in names if re.fullmatch(r'assets/index-[A-Za-z0-9_-]+\.css', n)]
    js = [n for n in names if re.fullmatch(r'assets/index-[A-Za-z0-9_-]+\.js', n)]
    if len(names) != 3 or len(css) != 1 or len(js) != 1 or 'index.html' not in names:
        raise ValueError('OS asset set differs')
    files = []
    for name in sorted(names):
        data = (root/name).read_bytes()
        if not 0 < len(data) <= 4 * 1024 * 1024:
            raise ValueError('OS asset budget exceeded')
        files.append({'path': name, 'byte_count': len(data),
                      'sha256': hashlib.sha256(data).hexdigest(),
                      'mime': OS_MIMES[name.rsplit('.', 1)[1]]})
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
        build_executive_mcp_app, build_web_ceo_v2_mcp_app,
    )
    from integrations.executive_mcp.web_ceo import (
        WEB_CEO_V2_PROFILE, validate_installed_mcp_profile,
    )
    import uvicorn

    policies = load_app_policies(raw['policies'])
    settings = AppSettings(
        policies=policies, mastermind_root=source, macro_root_flag=None, environ={},
        ceo_ingress_socket_path=raw['ceo_ingress_socket_path'],
        read_from_ceo_ingress=True, read_timeout=65.0,
    )
    sink = PolicyAuditSink(policies, Path(raw['audit_root']), optional=optional_policies(raw))
    try:
        mounts = build_optional_apps(raw, source, args.config, sink)
        profile = validate_installed_mcp_profile(raw.get('executive_mcp_profile', 'legacy'))
        builder = (build_web_ceo_v2_mcp_app if profile == WEB_CEO_V2_PROFILE
                   else build_executive_mcp_app)
        app = builder(settings, audit_sink=sink, **mounts)
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

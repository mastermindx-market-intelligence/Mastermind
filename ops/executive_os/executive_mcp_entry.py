"""Root-configured, dedicated-uid launcher for the existing five-tool MCP App.

Run with the separately provisioned network Python runtime and -I -B. The
sealed control Python remains SDK-free. This launcher never opens Runtime.
"""
from __future__ import annotations

import argparse
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
    if not isinstance(raw, dict) or set(raw) != CONFIG_KEYS:
        raise ValueError('installed MCP configuration fields differ')
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


class PolicyAuditSink:
    """Route existing A1 audit facts to the corresponding durable A1 sink."""
    def __init__(self, policies, root: Path):
        from integrations.business_mcp_auth.audit import DurableAuthAuditSink
        self._sinks = {}
        try:
            for name, policy in (('read', policies.read), ('submit', policies.submit)):
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
    raw = validate_document(json.loads(args.config.read_text()))
    if source.name != raw['release_sha'] or os.geteuid() != raw['service_uid']:
        raise ValueError('MCP source or process identity differs from its installation')
    sys.path.insert(0, str(source))
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import load_app_policies
    from integrations.executive_mcp.server import build_executive_mcp_app
    import uvicorn

    policies = load_app_policies(raw['policies'])
    settings = AppSettings(
        policies=policies, mastermind_root=source, macro_root_flag=None, environ={},
        ceo_ingress_socket_path=raw['ceo_ingress_socket_path'],
        read_from_ceo_ingress=True, read_timeout=65.0,
    )
    sink = PolicyAuditSink(policies, Path(raw['audit_root']))
    try:
        app = build_executive_mcp_app(settings, audit_sink=sink)
        uvicorn.run(app, host='127.0.0.1', port=raw['port'], access_log=False)
    finally:
        sink.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        print('executive-mcp: installed configuration refused', file=sys.stderr)
        raise SystemExit(2)

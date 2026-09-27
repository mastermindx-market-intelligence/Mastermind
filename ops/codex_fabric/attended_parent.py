"""Compose #633's attended Codex client; default to a no-login preflight.

This is not an Executive worker launcher. It owns no provider selection,
authentication, lifecycle, retry, or RuntimeBinding. --launch is an explicit
attended action after enrollment; preflight never calls the auth helper.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tomllib
from typing import Any

from ops.codex_fabric.register_executive_mcp import (
    RegistrationError, SERVER_NAME, _run, _matching_row,
    _validate_existing, _validated_url,
)

EXECUTIVE_TOOLS = ('executive_state', 'executive_inbox', 'executive_job',
                   'ceo_intent_status', 'submit_ceo_intent')

class BootstrapError(RuntimeError):
    """Closed, secret-free preparation refusal."""

@dataclass(frozen=True)
class LaunchPlan:
    argv: tuple[str, ...]
    helper_command: str
    source_root: str
    project_dir: str
    profile_sha256: str
    helper_sha256: str
    native_auth_status: str
    launch_allowed: bool
    parent_configuration: tuple[str, ...] = ()
    orchestrator_bundle_digest: str | None = None
    codex_home: str | None = None
    codex_home_identity: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        status = ('PREPARED_NOT_AUTHENTICATED' if self.launch_allowed
                  else 'PREPARED_AUTH_STATUS_UNRESOLVED')
        return {'status': status, 'native_auth_status': self.native_auth_status,
                'launch_allowed': self.launch_allowed,
                'authenticated_tool_discovery_proven': False,
                'argv': list(self.argv), 'source_root': self.source_root,
                'project_dir': self.project_dir,
                'profile_sha256': self.profile_sha256,
                'helper_sha256': self.helper_sha256,
                'orchestrator_bundle_digest': self.orchestrator_bundle_digest,
                'codex_home': self.codex_home,
                'codex_home_identity': self.codex_home_identity,
                'role_selection_proven': False,
                'child_enforcement_proven': False,
                'worker_dispatch_authorized': False}

def _path(value: Path | str, *, directory: bool = False) -> Path:
    try:
        path = Path(value)
        if not path.is_absolute() or any(ord(c) < 32 for c in str(path)):
            raise ValueError
        resolved = path.resolve(strict=True)
        valid = resolved.is_dir() if directory else resolved.is_file() and os.access(path, os.X_OK)
        if not valid:
            raise ValueError
        # Preserve the selected executable entry point: resolving a venv's
        # python symlink would silently switch to the base interpreter.
        return resolved if directory else path.parent.resolve(strict=True) / path.name
    except (OSError, TypeError, ValueError):
        raise BootstrapError('required client path is unavailable') from None


def _source_file(path: Path) -> bytes:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError
        return path.read_bytes()
    except (OSError, ValueError):
        raise BootstrapError('reviewed client source is unavailable') from None


def _profile(raw: bytes) -> dict[str, Any]:
    """Project a reviewed legacy or named-Sol profile onto native-disabled mode.

    #981's named coordinator is selectable only through the separate bundle opt-in.
    Recognizing its source shape never enables that role in the legacy launcher.
    """
    try:
        profile = tomllib.loads(raw.decode('utf-8'))
        if set(profile) != {'model', 'model_reasoning_effort', 'agents'}:
            raise ValueError
        agents = profile['agents']
        base = {'enabled', 'max_concurrent_threads_per_session',
                'default_subagent_model', 'default_subagent_reasoning_effort'}
        if not isinstance(agents, dict) or set(agents) not in (base, base | {'l2_sol_ceo'}):
            raise ValueError
        if 'l2_sol_ceo' in agents:
            role = agents['l2_sol_ceo']
            if (agents['enabled'] is not True or not isinstance(role, dict)
                    or set(role) != {'description', 'config_file'}
                    or role['config_file'] != 'agents/l2-sol-ceo.toml'
                    or not isinstance(role['description'], str) or not role['description'].strip()):
                raise ValueError
        elif agents['enabled'] is not False:
            raise ValueError
        if (type(agents['max_concurrent_threads_per_session']) is not int
                or agents['max_concurrent_threads_per_session'] != 1):
            raise ValueError
        values = {'model': profile['model'],
                  'model_reasoning_effort': profile['model_reasoning_effort'],
                  **{'agents.' + key: value for key, value in agents.items() if key in base}}
        values['agents.enabled'] = False
        for key, value in values.items():
            if key not in {'agents.enabled', 'agents.max_concurrent_threads_per_session'}:
                if not isinstance(value, str) or not value or value != value.strip():
                    raise ValueError
        return values
    except (UnicodeError, ValueError, TypeError, KeyError):
        raise BootstrapError('reviewed parent profile is invalid') from None


def _bundle_configuration(directory: Path, digest: str) -> tuple[str, tuple[str, ...], tuple[int, int]]:
    """Use the effective native home; never select a different credential home."""
    from ops.codex_fabric.orchestrator_bundle import (
        BundleError, configuration_overrides, _directory, _assert_target_binding,
    )
    try:
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError
        raw_home = os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))
        if not raw_home or any(ord(char) < 32 for char in raw_home):
            raise ValueError
        home = Path(raw_home)
        # Reuse the bundle's component-by-component, no-symlink path checks.
        # The path alone cannot distinguish a replaced credential-home directory.
        with _directory(home) as home_fd:
            info = os.fstat(home_fd)
            identity = (info.st_dev, info.st_ino)
            overrides = configuration_overrides(home, expected_bundle_digest=digest,
                                                 source_root=directory)
            _assert_target_binding(home, home_fd, None)
        return str(home), overrides, identity
    except (BundleError, OSError, TypeError, ValueError):
        raise BootstrapError('coordinator bundle is missing, conflicting, or changed') from None


def _validate_prepared_inputs(plan: LaunchPlan) -> None:
    """Recheck local inputs immediately before return/exec; no auth or provider call."""
    try:
        directory = Path(plan.source_root) / 'ops' / 'codex_fabric'
        helper = _source_file(directory / 'executive_mcp_auth.py')
        if hashlib.sha256(helper).hexdigest() != plan.helper_sha256:
            raise BootstrapError('helper changed')
        if plan.orchestrator_bundle_digest is None:
            raw = _source_file(directory / 'mastermind-astra.config.toml')
            overrides = tuple(key + '=' + json.dumps(value, ensure_ascii=False)
                              for key, value in _profile(raw).items())
        else:
            home, overrides, identity = _bundle_configuration(directory, plan.orchestrator_bundle_digest)
            if home != plan.codex_home or identity != plan.codex_home_identity:
                raise BootstrapError('home changed')
            raw = _source_file(directory / 'mastermind-orchestrators.config.toml')
        if (hashlib.sha256(raw).hexdigest() != plan.profile_sha256
                or overrides != plan.parent_configuration):
            raise BootstrapError('configuration changed')
    except BootstrapError:
        raise BootstrapError('prepared client inputs changed; launch refused') from None


def prepare_launch(server_url: str, *, codex_bin: Path | str,
                   python_bin: Path | str, project_dir: Path | str,
                   source_root: Path | str,
                   expected_bundle_digest: str | None = None) -> LaunchPlan:
    """Read local registration and compose argv, without login or launch.

    source_root is reviewed client source, never the arbitrary project cwd.
    Digests identify these inputs; they are not release or authentication proof.
    """
    try:
        if not isinstance(server_url, str) or any(ord(c) < 32 for c in server_url):
            raise RegistrationError('invalid URL')
        url = _validated_url(server_url)
    except RegistrationError:
        raise BootstrapError('Executive MCP URL is invalid') from None
    codex = _path(codex_bin)
    python = _path(python_bin)
    project = _path(project_dir, directory=True)
    source = _path(source_root, directory=True)
    directory = source / 'ops' / 'codex_fabric'
    if expected_bundle_digest is None:
        raw_profile = _source_file(directory / 'mastermind-astra.config.toml')
        parent_configuration = tuple(key + '=' + json.dumps(value, ensure_ascii=False)
                                     for key, value in _profile(raw_profile).items())
        codex_home = None
        codex_home_identity = None
    else:
        codex_home, parent_configuration, codex_home_identity = _bundle_configuration(directory, expected_bundle_digest)
        raw_profile = _source_file(directory / 'mastermind-orchestrators.config.toml')
    raw_helper = _source_file(directory / 'executive_mcp_auth.py')
    try:
        census = _run(str(codex), '--cd', str(project), 'mcp', 'list', '--json')
        if census.returncode != 0:
            raise RegistrationError('census unavailable')
        try:
            rows = json.loads(census.stdout)
        except (ValueError, TypeError):
            raise RegistrationError('census malformed') from None
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise RegistrationError('census malformed')
        row = _matching_row(rows)
        if row is None:
            raise RegistrationError('bare registration required')
        auth_status = _validate_existing(row, url)
        # Native 0.154.0 also reports unknown when no auth observation is available.
        # Preserve the plan, but only the existing not_logged_in route is launchable.
        if auth_status not in {'not_logged_in', 'unsupported', 'unknown'}:
            raise RegistrationError('bare registration required')
        # Native `mcp list` omits tool filters. Read the exact server's
        # detailed configuration before composing an allowlist override.
        detailed = _run(str(codex), '--cd', str(project), 'mcp', 'get',
                        SERVER_NAME, '--json')
        if detailed.returncode != 0:
            raise RegistrationError('detailed configuration unavailable')
        try:
            detail = json.loads(detailed.stdout)
        except (ValueError, TypeError):
            raise RegistrationError('detailed configuration malformed') from None
        if (not isinstance(detail, dict) or detail.get('name') != SERVER_NAME
                or not {'enabled_tools', 'disabled_tools'}.issubset(detail)):
            raise RegistrationError('detailed configuration incomplete')
        _validate_existing(detail, url)
        for observed in (row, detail):
            allowed = observed.get('enabled_tools')
            disabled = observed.get('disabled_tools')
            if allowed is not None and (not isinstance(allowed, list)
                    or not all(isinstance(x, str) for x in allowed)
                    or not set(EXECUTIVE_TOOLS).issubset(allowed)):
                raise RegistrationError('required tools restricted')
            if disabled is not None and (not isinstance(disabled, list)
                    or not all(isinstance(x, str) for x in disabled)
                    or set(EXECUTIVE_TOOLS).intersection(disabled)):
                raise RegistrationError('required tools restricted')
    except RegistrationError:
        raise BootstrapError('Executive registration is missing, conflicting, or ambiguous') from None
    inner = ('cd ' + shlex.quote(str(source)) + ' && exec ' +
             shlex.join([str(python), '-E', '-s', '-B', '-m',
                         'ops.codex_fabric.executive_mcp_auth', 'headers']))
    helper = shlex.join(['/bin/sh', '-c', inner])
    prefix = 'mcp_servers.' + SERVER_NAME + '.'
    overrides = {prefix + 'url': url,
                      prefix + 'http_headers_helper': helper,
                      prefix + 'enabled_tools': list(EXECUTIVE_TOOLS),
                      prefix + 'required': True}
    argv = [str(codex), '--cd', str(project)]
    for value in parent_configuration:
        argv.extend(['-c', value])
    for key, value in overrides.items():
        argv.extend(['-c', key + '=' + json.dumps(value, ensure_ascii=False)])
    plan = LaunchPlan(tuple(argv), helper, str(source), str(project),
                      hashlib.sha256(raw_profile).hexdigest(),
                      hashlib.sha256(raw_helper).hexdigest(),
                      auth_status, auth_status == 'not_logged_in',
                      parent_configuration, expected_bundle_digest, codex_home, codex_home_identity)
    _validate_prepared_inputs(plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--url', required=True)
    parser.add_argument('--codex-bin', default=shutil.which('codex') or 'codex')
    parser.add_argument('--python-bin', default=sys.executable)
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--orchestrator-bundle-digest',
                        help='Opt into the exact complete coordinator bundle in effective CODEX_HOME')
    parser.add_argument('--launch', action='store_true',
                        help='Explicit attended launch after enrollment; never logs in')
    args = parser.parse_args(argv)
    try:
        plan = prepare_launch(args.url, codex_bin=args.codex_bin,
            python_bin=args.python_bin, project_dir=args.project_dir,
            source_root=Path(__file__).resolve().parents[2],
            expected_bundle_digest=args.orchestrator_bundle_digest)
    except BootstrapError as exc:
        print('codex-fabric-bootstrap: ' + str(exc), file=sys.stderr)
        return 2
    if not args.launch:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    if not plan.launch_allowed:
        print('codex-fabric-bootstrap: authentication status is unresolved; launch held',
              file=sys.stderr)
        return 2
    try:
        _validate_prepared_inputs(plan)
    except BootstrapError as exc:
        print('codex-fabric-bootstrap: ' + str(exc), file=sys.stderr)
        return 2
    try:
        os.execv(plan.argv[0], plan.argv)
    except OSError:
        print('codex-fabric-bootstrap: attended launch unavailable; no retry', file=sys.stderr)
        return 127
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

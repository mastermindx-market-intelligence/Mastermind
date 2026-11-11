#!/usr/bin/env python3
"""One command for the existing private gateway and tunnel service helpers."""
# The existing CLI remains the bootstrap trust boundary. Re-exec before any
# path-searchable import; source library imports retain their existing behavior.
import sys as _bootstrap_sys
if __name__ == "__main__" and not (
        _bootstrap_sys.flags.isolated and _bootstrap_sys.flags.no_site
        and _bootstrap_sys.dont_write_bytecode):
    import posix as _bootstrap_os
    _bootstrap_os.execv(
        _bootstrap_sys.executable,
        [_bootstrap_sys.executable, "-I", "-S", "-B", __file__, *_bootstrap_sys.argv[1:]],
    )

import argparse
import json
import os
import stat
import re
import subprocess
import sys
import time
from pathlib import Path


ACCOUNT_RE = re.compile(r'[a-z0-9][a-z0-9_-]{0,47}')
PRIVATE_ROOT = Path.home() / '.local' / 'share' / 'studio-direct-mcp' / 'private'
INSTALLED_CONTROL_ROOT = Path.home() / '.local' / 'share' / 'studio-direct-mcp' / 'control'


_CONTROL_GATEWAY = None


def _load_gateway_bootstrap():
    # This one adjacent source file is trusted bootstrap code, not a selectable
    # dependency. Read bounded, stable regular bytes without following links.
    # Its existing guard owns manifest validation and the process-scoped lock.
    import importlib.util
    path = Path(os.path.abspath(__file__)).with_name("private_service.py")
    fd = None
    try:
        home = Path.home()
        current = path.parent
        while True:
            info = current.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise ValueError("unsafe bootstrap parent")
            if current == home or not path.is_relative_to(home):
                break
            current = current.parent
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        before = os.fstat(fd)
        limit = 2 * 1024 * 1024
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) & 0o022
                or before.st_size > limit):
            raise ValueError("unsafe bootstrap source")
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        identity = lambda item: (
            item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if (len(data) > limit or identity(before) != identity(os.fstat(fd))
                or identity(before) != identity(path.lstat())):
            raise ValueError("bootstrap source changed")
    except (OSError, ValueError):
        raise SystemExit("CONTROL_BUNDLE_CLOSURE_REFUSED") from None
    finally:
        if fd is not None:
            os.close(fd)
    spec = importlib.util.spec_from_file_location("private_service", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        exec(compile(bytes(data), str(path), "exec"), module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
        raise
    return module

def _invoke_from(root, helper, action, account):
    command = [sys.executable, '-I', '-S', '-B', str(Path(root) / helper), action, '--account', account]
    context = (_CONTROL_GATEWAY._INSTALLED_CONTROL_CONTEXT
               if _CONTROL_GATEWAY is not None else None)
    if context is not None and Path(root) != context['root']:
        raise RuntimeError('CONTROL_BUNDLE_CLOSURE_REFUSED')
    # The CLI retains its existing shared lock across this complete sequence.
    # Keep CLOEXEC/default close_fds: no lock may escape into a seat service.
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError(f'{helper} {action} failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


def invoke(helper, action, account):
    return _invoke_from(Path(__file__).parent, helper, action, account)


def _fleet_ready(gateway, tunnel):
    """Match the fail-closed readiness predicate of the existing fleet projection.

    A tunnel transport can be ready while its control-plane poll is not. The
    owner must not mark that seat ready when the fleet reader will reject the
    contradictory receipt. This affects reporting only, not launch admission.
    """
    return (
        gateway.get('loaded') is True
        and gateway.get('running') is True
        and tunnel.get('loaded') is True
        and tunnel.get('running') is True
        and tunnel.get('healthy') is True
        and tunnel.get('ready') is True
        and tunnel.get('configurationDrift') is False
        and tunnel.get('tunnelReady') is True
        and tunnel.get('controlPlanePollReady') is True
        and tunnel.get('gatewayReady') is True
        and tunnel.get('managedAliasRunning') is False
    )


def installed_status(account):
    """Read one installed seat through the installed control-helper generation."""
    gateway = _invoke_from(INSTALLED_CONTROL_ROOT, 'private_service.py', 'status', account)
    tunnel = _invoke_from(INSTALLED_CONTROL_ROOT, 'private_tunnel_service.py', 'status', account)
    return {
        'account': account,
        'action': 'status',
        'steps': [],
        'ready': _fleet_ready(gateway, tunnel),
        'gateway': gateway,
        'tunnel': tunnel,
    }


def operate(action, account):
    if not ACCOUNT_RE.fullmatch(account):
        raise ValueError('Account must be a configured account label, such as chatgpt1')
    steps = []
    if action == 'start':
        steps.append(invoke('private_service.py', 'start', account))
        steps.append(invoke('private_tunnel_service.py', 'start', account))
    elif action == 'stop':
        steps.append(invoke('private_tunnel_service.py', 'stop', account))
        steps.append(invoke('private_service.py', 'stop', account))
    elif action != 'status':
        raise ValueError('Expected start, stop, or status')
    gateway = invoke('private_service.py', 'status', account)
    tunnel = invoke('private_tunnel_service.py', 'status', account)
    if action == 'start':
        deadline = time.monotonic() + 35
        while not (gateway.get('running') and tunnel.get('ready')):
            if time.monotonic() >= deadline:
                raise RuntimeError('Services started but gateway and tunnel did not become ready within 35 seconds; run studio-direct status')
            time.sleep(0.25)
            gateway = invoke('private_service.py', 'status', account)
            tunnel = invoke('private_tunnel_service.py', 'status', account)
    return {'account': account, 'action': action, 'steps': steps,
            'ready': bool(gateway.get('running') and tunnel.get('ready')),
            'gateway': gateway, 'tunnel': tunnel}


def installed_accounts(private_root=None):
    """Return only account installs owned by the existing private-seat installer."""
    root = Path(private_root) if private_root is not None else PRIVATE_ROOT
    if not root.is_dir():
        return []
    accounts = []
    for child in root.iterdir():
        if (child.is_dir() and ACCOUNT_RE.fullmatch(child.name)
                and (child / 'manifest.json').is_file()):
            accounts.append(child.name)
    return sorted(accounts)


def fleet_status(accounts=None, status_reader=None):
    """Aggregate read-only status without adding a fleet lifecycle or bulk action."""
    selected = installed_accounts() if accounts is None else list(accounts)
    read_status = installed_status if status_reader is None else status_reader
    rows = []
    ready_count = 0
    for account in selected:
        try:
            row = read_status(account)
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            row = {'account': account, 'ready': False, 'error': str(error)}
        rows.append(row)
        ready_count += int(bool(row.get('ready')))
    return {
        'schema': 'mastermind.studio_direct_fleet_status.v1',
        'action': 'status',
        'accountCount': len(rows),
        'readyCount': ready_count,
        'allReady': bool(rows) and ready_count == len(rows),
        'accounts': rows,
    }


def main():
    parser = argparse.ArgumentParser(prog='studio-direct')
    parser.add_argument('action', choices=['start', 'stop', 'status'], nargs='?', default='status')
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--account')
    target.add_argument('--all', action='store_true', help='read status for all installed private seats')
    args = parser.parse_args()
    try:
        if args.all:
            if args.action != 'status':
                raise ValueError('--all is read-only and supports status only')
            result = fleet_status()
        else:
            result = operate(args.action, args.account or 'chatgpt1')
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        target_name = 'all' if args.all else (args.account or 'chatgpt1')
        print(json.dumps({'account': target_name, 'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    _CONTROL_GATEWAY = _load_gateway_bootstrap()
    raise SystemExit(main())

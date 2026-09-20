#!/usr/bin/env python3
"""One command for the existing private gateway and tunnel service helpers."""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


ACCOUNT_RE = re.compile(r'[a-z0-9][a-z0-9_-]{0,47}')
PRIVATE_ROOT = Path.home() / '.local' / 'share' / 'studio-direct-mcp' / 'private'


def invoke(helper, action, account):
    command = [sys.executable, str(Path(__file__).with_name(helper)), action,
               '--account', account]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError(f'{helper} {action} failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


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


def fleet_status(accounts=None):
    """Aggregate read-only status without adding a fleet lifecycle or bulk action."""
    selected = installed_accounts() if accounts is None else list(accounts)
    rows = []
    ready_count = 0
    for account in selected:
        try:
            row = operate('status', account)
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
    raise SystemExit(main())

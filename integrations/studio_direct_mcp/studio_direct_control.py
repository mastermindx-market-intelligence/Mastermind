#!/usr/bin/env python3
"""One command for the existing private gateway and tunnel service helpers."""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


def invoke(helper, action, account):
    command = [sys.executable, str(Path(__file__).with_name(helper)), action,
               '--account', account]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError(f'{helper} {action} failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


def operate(action, account):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}', account):
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


def main():
    parser = argparse.ArgumentParser(prog='studio-direct')
    parser.add_argument('action', choices=['start', 'stop', 'status'], nargs='?', default='status')
    parser.add_argument('--account', default='chatgpt1')
    args = parser.parse_args()
    try:
        print(json.dumps(operate(args.action, args.account), indent=2))
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'account': args.account, 'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

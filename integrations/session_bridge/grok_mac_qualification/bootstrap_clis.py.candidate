#!/usr/bin/env python3
"""Idempotent CLI inventory/install for an existing registered host.

Never enrolls a route, copies authentication, changes a cap, or downgrades a CLI.
Login and a real admitted run remain separate, visible readiness steps.
"""
import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

PACKAGES = {
    'grok': '@xai-official/grok@1.0.41',
    'codex': '@openai/codex@0.160.1',
    'claude': '@anthropic-ai/claude-code@2.1.284',
    'opencode': 'opencode-ai@1.18.31',
}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('host')
    p.add_argument('--install-missing', action='store_true')
    p.add_argument('--tool', choices=tuple(PACKAGES) + ('cursor-agent',), action='append')
    a=p.parse_args()
    registry=json.loads((Path(__file__).resolve().parent/'hosts.json').read_text())
    host=registry.get(a.host)
    if not isinstance(host,dict) or host.get('local') is True:
        p.error('choose an existing remote host')
    alias=host.get('ssh_alias','')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',alias):
        p.error('invalid registered SSH alias')
    script=['set -euo pipefail','export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:$PATH"']
    selected = set(a.tool or [*PACKAGES, "cursor-agent"])
    for tool,package in PACKAGES.items():
        if tool not in selected:
            continue
        if a.install_missing:
            script.append(f'if ! command -v {tool} >/dev/null 2>&1; then npm install --global --prefix "$HOME/.local" --allow-scripts={shlex.quote(package.rsplit("@",1)[0])} {shlex.quote(package)} >&2; fi')
        script.append(f'if command -v {tool} >/dev/null 2>&1; then printf "{tool}=installed\\n"; else printf "{tool}=missing\\n"; fi')
    if a.install_missing and "cursor-agent" in selected:
        script.append('if ! command -v cursor-agent >/dev/null 2>&1; then curl --fail --silent --show-error https://cursor.com/install | bash >&2; fi')
    if "cursor-agent" in selected:
        script.append('if command -v cursor-agent >/dev/null 2>&1; then printf "cursor-agent=installed\\n"; else printf "cursor-agent=missing\\n"; fi')
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',alias,'bash -s'],input='\n'.join(script)+'\n',text=True,capture_output=True,timeout=180)
    # Only emit our fixed inventory vocabulary. Vendor output can contain account details.
    tools=dict(line.split('=',1) for line in result.stdout.splitlines()
               if re.fullmatch(r'(grok|codex|claude|opencode|cursor-agent)=(installed|missing)',line))
    print(json.dumps({'host':a.host,'returncode':result.returncode,'tools':tools,
                      'authentication':'separate provider login required unless already signed in',
                      'routing':'unchanged; explicit host mode enrollment and admitted result required'},indent=2))
    return result.returncode

if __name__=='__main__':
    raise SystemExit(main())

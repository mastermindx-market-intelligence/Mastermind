#!/usr/bin/env python3
"""Local principal/controller entrypoint. Never exposed as a remote tool."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from fabric_operator_owner import OperatorOwner, canonical, safe_id, validate_child_admission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('authorize-root')
    p.add_argument('--root', required=True)
    p.add_argument('--child-limit', type=int, required=True)
    p.add_argument('--ttl', type=int, default=7200)
    p = commands.add_parser('child-start')
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--lease-id', required=True)
    for key in ('pool','model','account','host'):p.add_argument('--'+key,required=True)
    p = commands.add_parser('issue')
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--pool', choices=['glm', 'glm-frontier', 'grok'], required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--lease-id', required=True)
    p.add_argument('--account', required=True)
    p.add_argument('--host', required=True)
    p.add_argument('--support-sha256', required=True)
    p.add_argument('--child-budget', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    owner = OperatorOwner()
    if args.command == 'child-start':
        with owner.transaction() as con:
            validate_child_admission(con, args.run_id, args.root, now=time.time(), admitted_lease_id=args.lease_id, start_binding={k:getattr(args,k) for k in ('pool','model','account','host')},packet_sha256=hashlib.sha256(args.packet.read_bytes()).hexdigest())
        print('{"child_start_authorized":true}')
        return
    if args.command == 'authorize-root':
        root = safe_id(args.root)
        actual = os.environ.get('CODEX_THREAD_ID')
        if actual and actual != root:
            raise ValueError('root_authorization_native_principal_conflict')
        print(canonical(owner.authorize_root(root, args.child_limit, time.time() + args.ttl)))
        return
    if os.environ.get('POOL_TASK_CLASS') != 'domain_orchestration':
        raise ValueError('operator_role_required')
    launch = dict(root=args.root, run_id=args.run_id, lease_id=args.lease_id, pool=args.pool,
                  model=args.model, account=args.account, host=args.host,
                  support_sha256=args.support_sha256,
                  packet_sha256=hashlib.sha256(args.packet.read_bytes()).hexdigest(),
                  task_class='domain_orchestration')
    capsule = owner.issue(launch, args.child_budget)
    # The controller supplies its freshly-created 0600 temporary file. Never
    # follow a path or replace a preexisting capability under a different ID.
    fd = os.open(args.out, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600 or st.st_size != 0:
            raise ValueError('capsule_destination_refused')
        with os.fdopen(fd, 'w') as stream:
            fd = -1
            stream.write(canonical(capsule)); stream.flush(); os.fsync(stream.fileno())
    finally:
        if fd != -1: os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Capability values and private filenames never appear in diagnostics.
        raise SystemExit('OPERATOR_CAPABILITY_ISSUE_REFUSED')

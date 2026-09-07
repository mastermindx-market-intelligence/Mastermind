#!/usr/bin/env python3
"""Describe Workbench Read or enter an explicitly owner-injected launch boundary.

Standalone serving refuses until the existing host supplies runtime services and
its serve callback in Python. No dynamic factory, root flag, tunnel or default
executor is provided. The caller owns launch admission, effect reconciliation and
shutdown; this module never closes borrowed roots, pools or shared services.
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None, *, runtime_services=None, serve=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument('--describe', action='store_true')
    parser.add_argument('--host', choices=('127.0.0.1',), default='127.0.0.1')
    parser.add_argument('--port', type=int)
    args = parser.parse_args(argv)
    if args.port is not None and not 1 <= args.port <= 65535:
        print('LAUNCH_CONFIGURATION_INVALID', file=sys.stderr)
        return 2
    if args.describe:
        print(json.dumps({'capability': 'BUILT_NOT_PROVEN', 'mode': 'owner-injected',
                          'tool': 'read_project_file', 'runtime_services': 'required'}, sort_keys=True))
        return 0
    if runtime_services is None:
        print('RUNTIME_SERVICES_REQUIRED', file=sys.stderr)
        return 2
    if args.port is None or not callable(serve):
        print('OWNER_LAUNCH_REQUIRED', file=sys.stderr)
        return 2
    try:
        from integrations.workbench_read_mcp.deployment import create_deployment

        server = create_deployment(runtime_services)
        app = server.streamable_http_app()
    except Exception:
        print('DEPLOYMENT_CONFIGURATION_REFUSED', file=sys.stderr)
        return 2
    # From this point the admitted host owns possible listener/process effects.
    # Do not catch/retry a failed serve call or report it as a pre-bind refusal.
    serve(app, host=args.host, port=args.port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

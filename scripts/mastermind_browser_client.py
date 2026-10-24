#!/usr/bin/env python3
"""Print client-native Browser setup; never install a client or issue credentials."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).absolute().parents[1]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from integrations.mastermind_browser_plugin.client_projection import PUBLIC_CLIENTS, project_public_browser_client
from integrations.mastermind_browser_plugin.ingress import build_browser_ingress_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=sorted(PUBLIC_CLIENTS), required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--internal-url", required=True)
    args = parser.parse_args(argv)
    plan = build_browser_ingress_plan(
        public_resource_url=args.public_url, internal_upstream_url=args.internal_url)
    projection = project_public_browser_client(args.provider, ingress_plan=plan)
    print(json.dumps(projection.to_dict(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

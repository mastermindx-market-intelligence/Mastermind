#!/usr/bin/env python3
"""Plan or apply the bounded Notion Knowledge Surface N0 workspace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from integrations.notion_knowledge_surface.bootstrap import (  # noqa: E402
    BootstrapError,
    NotionClient,
    _prove_parent,
    apply_workspace,
    build_plan,
    load_manifest,
)

DEFAULT_MANIFEST = REPO_ROOT / "config" / "notion_knowledge_surface_n0.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--parent-page-id", default=os.environ.get("NOTION_PARENT_PAGE_ID"))
    parser.add_argument("--apply", action="store_true", help="Create missing N0 children. Default is read-only planning.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        token = os.environ.get("NOTION_API_KEY")
        if args.apply:
            if not token or not args.parent_page_id:
                raise BootstrapError("--apply requires NOTION_API_KEY and NOTION_PARENT_PAGE_ID/--parent-page-id")
            client = NotionClient(token)
            items = apply_workspace(client, args.parent_page_id, manifest)
            payload = {
                "schema": "mastermind.notion_bootstrap_receipt.v1",
                "mode": "apply",
                "parent_page_id": args.parent_page_id,
                "results": [item.to_dict() for item in items],
                "created_count": sum(item.action == "created" for item in items),
                "reconciled_count": sum(item.action == "reconciled" for item in items),
            }
        elif token and args.parent_page_id:
            client = NotionClient(token)
            _prove_parent(client, args.parent_page_id)
            items = build_plan(manifest, client.list_children(args.parent_page_id))
            payload = {
                "schema": "mastermind.notion_bootstrap_receipt.v1",
                "mode": "remote-plan",
                "parent_page_id": args.parent_page_id,
                "results": [item.to_dict() for item in items],
            }
        else:
            items = build_plan(manifest, [])
            payload = {
                "schema": "mastermind.notion_bootstrap_receipt.v1",
                "mode": "offline-plan",
                "parent_page_id": None,
                "results": [item.to_dict() for item in items],
                "degraded": ["live Notion connection and parent page were not supplied; no remote discovery occurred"],
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except BootstrapError as exc:
        print(json.dumps({"schema": "mastermind.notion_bootstrap_receipt.v1", "status": "REFUSED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

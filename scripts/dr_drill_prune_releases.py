#!/usr/bin/env python3
"""Prune ephemeral DR-D1 drill releases (adversarial review M10).

Fixed-count retention: keeps the newest N (default 8) releases that are
BOTH `draft=True` AND whose `tag_name` starts with the drill tag prefix
(default `dr-export/`), deleting the rest. Scope is deliberately narrow and
enforced in code, not just by argument default:

  * Never touches a non-draft release -- the production/vault lane
    (`scripts/executive_dr_cli.py ship`, always `draft=False`) is entirely
    untouched by this script under any argument combination.
  * Never touches a release whose tag does not start with the drill prefix.

This is intentionally a SEPARATE script from `control_plane/executive_dr.py`
-- that module's reviewed transport functions carry no delete capability at
all (see the module docstring and DR_RUNBOOK.md), and this narrowly-scoped,
explicitly-authorized cleanup utility for ephemeral drill artifacts stays
that way rather than growing the reviewed module's surface. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - stdlib signature
        return None


def _request(method: str, url: str, *, token: str, timeout: float = 30.0) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mastermind-executive-dr-prune/1",
        },
    )
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp is not None else b""


def list_drill_releases(api_base: str, repo: str, token: str, *, tag_prefix: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in range(1, 11):
        status, body = _request("GET", f"{api_base}/repos/{repo}/releases?per_page=100&page={page}", token=token)
        if status != 200:
            raise SystemExit(f"release listing failed with status {status}: {body[:512].decode('utf-8', errors='replace')}")
        releases = json.loads(body.decode("utf-8"))
        if not releases:
            break
        results.extend(releases)
        if len(releases) < 100:
            break
    return [
        release
        for release in results
        if release.get("draft") is True and str(release.get("tag_name", "")).startswith(tag_prefix)
    ]


def prune(api_base: str, repo: str, token: str, *, tag_prefix: str, keep: int) -> list[dict[str, Any]]:
    drills = list_drill_releases(api_base, repo, token, tag_prefix=tag_prefix)
    drills.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    to_delete = drills[keep:]
    deleted: list[dict[str, Any]] = []
    for release in to_delete:
        release_id = release["id"]
        status, _body = _request("DELETE", f"{api_base}/repos/{repo}/releases/{release_id}", token=token)
        deleted.append(
            {
                "id": release_id,
                "tag_name": release.get("tag_name"),
                "created_at": release.get("created_at"),
                "status": status,
                "deleted": status == 204,
            }
        )
    return deleted


def _write_summary(path: str, *, keep: int, deleted: list[dict[str, Any]]) -> None:
    lines = [f"# Executive OS DR-D1 drill release pruning (keep newest {keep})", ""]
    if not deleted:
        lines.append("Nothing pruned this run.")
    else:
        lines.append("| tag | id | created_at | deleted |")
        lines.append("|---|---|---|---|")
        for item in deleted:
            lines.append(f"| {item['tag_name']} | {item['id']} | {item['created_at']} | {item['deleted']} |")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune ephemeral DR-D1 drill releases (draft + tag-prefix only).")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--tag-prefix", default="dr-export/")
    parser.add_argument("--keep", type=int, default=8)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--summary-out", default=None, help="Append a markdown table here (e.g. $GITHUB_STEP_SUMMARY).")
    args = parser.parse_args(argv)

    if args.keep < 0:
        parser.error("--keep must be non-negative")

    token = os.environ.get(args.token_env)
    if not token:
        sys.stderr.write(f"credential env var {args.token_env} is not set\n")
        return 65

    deleted = prune(args.api_base, args.repo, token, tag_prefix=args.tag_prefix, keep=args.keep)
    payload = json.dumps({"deleted": deleted, "keep": args.keep, "tag_prefix": args.tag_prefix}, indent=2, sort_keys=True)
    sys.stdout.write(payload + "\n")
    if args.summary_out:
        _write_summary(args.summary_out, keep=args.keep, deleted=deleted)

    failed = [item for item in deleted if not item["deleted"]]
    if failed:
        sys.stderr.write(f"{len(failed)} of {len(deleted)} prune deletions did not confirm (status != 204)\n")
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

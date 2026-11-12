#!/usr/bin/env python3
"""Stage teammate files for the Hermes move. Writes only under --out.

Input: a roster spec (the team server's `team_roster.json` shape) plus a
plan file naming, per teammate, its Hermes notes directory and, for a
teammate not yet moved, its board agent id. Output, all staged for a
person to install later:

  roster/team_roster.staged.json   the roster with a `memory_link` block on
                                   every planned teammate (ruling 20: each
                                   teammate's own instance launches with it)
  memory-link/<slug>.mcp.json      the MCP config its instance launches
  memory-link/<slug>.config.json   the memory-link server's own config
  specs/<slug>.installed.json      a cutover spec (new teammates only), its
                                   primaryThreadId left for the install step

Nothing here reads a conversation, a memory or a credential. Paths in the
output are the install-time paths given in the plan, not the staging dir.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

SLUG_RE = re.compile(r"[a-z0-9-]+")
TOOLS_READ = ["mcp__memory-link__memory_recall"]
TOOL_NOTES = "mcp__memory-link__memory_notes"
TOOL_SAVE = "mcp__memory-link__memory_save"
PRIMARY_PLACEHOLDER = "FILL-AT-INSTALL"


def die(msg: str) -> None:
    print(f"stage_teammates: {msg}", file=sys.stderr)
    raise SystemExit(2)


def write_private(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def tools_for(entry: dict, write_enabled: bool) -> list[str]:
    tools = list(TOOLS_READ)
    if entry.get("notes_dir"):
        tools.append(TOOL_NOTES)
    if write_enabled:
        tools.append(TOOL_SAVE)
    return tools


def stage(roster: dict, plan: dict, out: str) -> dict:
    root = plan["server_root"].rstrip("/")
    link_dir = f"{root}/config/memory-link"
    write_enabled = plan.get("write_enabled") is True
    staged = copy.deepcopy(roster)
    by_slug = {m["slug"]: m for m in staged["teammates"]}
    summary = {"teammates": [], "specs": []}
    for slug, entry in plan["teammates"].items():
        if not SLUG_RE.fullmatch(slug):
            die(f"bad slug {slug!r}")
        mate = by_slug.get(slug)
        if mate is None:
            die(f"{slug} is in the plan but not in the roster")
        if mate.get("instance") != slug:
            die(f"{slug}: instance must equal the slug (ruling 20)")
        mcp_path = f"{link_dir}/{slug}.mcp.json"
        cfg_path = f"{link_dir}/{slug}.config.json"
        mate["memory_link"] = {"mcp_config": mcp_path,
                               "tools": tools_for(entry, write_enabled)}
        server_cfg = {
            "omh_bin": plan["omh_bin"],
            "omh_home": plan["omh_home"],
            "hermes_home_for_omh": f"{link_dir}/home-{slug}",
            "teammate": slug,
            "write_enabled": write_enabled,
            "max_chars": int(plan.get("max_chars", 3000)),
        }
        if entry.get("notes_dir"):
            server_cfg["profile_memory_dir"] = entry["notes_dir"]
        write_private(os.path.join(out, "memory-link", f"{slug}.config.json"),
                      server_cfg)
        write_private(os.path.join(out, "memory-link", f"{slug}.mcp.json"), {
            "mcpServers": {"memory-link": {
                "command": plan["python_bin"],
                "args": ["-I", plan["server_script"], "--config", cfg_path]}}})
        summary["teammates"].append(slug)
        if entry.get("new"):
            if not mate.get("paperclip_agent_id"):
                die(f"{slug}: a new teammate needs paperclip_agent_id")
            spec = copy.deepcopy(plan["spec_template"])
            spec["agent_id"] = mate["paperclip_agent_id"]
            spec["agent_name"] = entry.get("agent_name", mate["name"])
            spec["agent_dir"] = f"{root}/teammates/{slug}"
            spec["binding"] = dict(spec["binding"],
                                   providerInstanceId=slug,
                                   primaryThreadId=PRIMARY_PLACEHOLDER)
            write_private(os.path.join(out, "specs", f"{slug}.installed.json"),
                          spec)
            summary["specs"].append(slug)
    write_private(os.path.join(out, "roster", "team_roster.staged.json"),
                  staged)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--roster", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with open(args.roster, encoding="utf-8") as fh:
        roster = json.load(fh)
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    print(json.dumps(stage(roster, plan, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

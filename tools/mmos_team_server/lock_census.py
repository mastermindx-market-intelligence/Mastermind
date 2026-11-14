#!/usr/bin/env python3
"""Read-only census before switching the team-project picker lock on.

Usage: lock_census.py <roster spec>

Reads the server's state database read-only (team_roster's own reader,
mode=ro), settings.json and the roster state file. Prints the number of
conversations per provider instance, the conversations whose instance no
longer exists in settings, and the teammates whose primary conversation is
not on their roster instance. Exit 0 only when both lists are empty. Writes
nothing; prints no conversation text, title or secret.
"""
import os
import json, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import team_roster as tr
spec = tr.load_spec(sys.argv[1])
project = tr.project_by_root(spec)
instances = set(tr.load_settings(spec).get("providerInstances", {}))
state, _ = tr.load_state(spec)
live = tr.list_threads(spec, project["project_id"])
by_id = {t["threadId"]: t for t in live}
missing = [t["threadId"] for t in live if t["instance"] not in instances]
bad_primary = []
for mate in spec["teammates"]:
    tid = (state["teammates"].get(mate["name"]) or {}).get("threadId")
    got = (by_id.get(tid) or {}).get("instance")
    if got != mate["instance"]:
        bad_primary.append(f'{mate["name"]}: primary {tid} on {got}, roster {mate["instance"]}')
counts = {}
for t in live:
    counts[t["instance"]] = counts.get(t["instance"], 0) + 1
print(json.dumps({"project": project["project_id"], "conversations": len(live),
                  "byInstance": counts, "onMissingInstance": missing,
                  "primaryMismatch": bad_primary,
                  "ok": not missing and not bad_primary}, indent=1))
sys.exit(0 if not missing and not bad_primary else 1)

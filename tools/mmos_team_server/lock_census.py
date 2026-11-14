#!/usr/bin/env python3
"""Read-only census before switching the team-project picker lock on.

Usage: lock_census.py <roster spec>

Reads the server's state database with the census's OWN sqlite connection
opened `file:<db>?mode=ro` (never immutable=1, which could serve a stale
read while the server runs), settings.json and the roster state file.
Prints the number of conversations per provider instance, the conversations
whose instance no longer exists in settings, the teammates whose primary
conversation is not on their roster instance, and the database journal
mode. Exit 0 only when both lists are empty.

Writes: the main database file is NEVER written. On a WAL-mode database
with the server running, the -wal/-shm sidecars already exist and are the
server's; with the server stopped, sqlite may create them when this
read-only connection opens. Prints no conversation text, title or secret;
load_spec's long-title warnings are suppressed so no title text reaches
stderr.
"""
import os
import json, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import team_roster as tr


def die(msg, code=2):
    print(f"lock_census: {msg}", file=sys.stderr)
    sys.exit(code)


# F9: load_spec's long-title warning carries teammate title text; the census
# prints no titles, so suppress warnings for the load (die() errors still
# reach stderr).
_orig_log_warn = tr.log_warn
tr.log_warn = lambda msg: None
try:
    spec = tr.load_spec(sys.argv[1])
finally:
    tr.log_warn = _orig_log_warn

dbp = tr.db_path(spec)
if not os.path.exists(dbp):
    die(f"no state database at {dbp}; is this the team home?")

# F5: the census's own read — mode=ro, never immutable=1. The SQL mirrors
# team_roster.project_by_root / list_threads at this pin; team_roster's
# reader is deliberately unchanged.
try:
    conn = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
except sqlite3.Error as exc:
    die(f"cannot open state database read-only: {exc}")
conn.row_factory = sqlite3.Row
try:
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    root = tr.expand(spec["project"]["workspace_root"])
    row = conn.execute(
        "SELECT project_id, title, workspace_root FROM projection_projects "
        "WHERE workspace_root = ? AND deleted_at IS NULL", (root,)).fetchone()
    if row is None:
        die(f"no live project for workspace root {root} in the state "
            "database")
    project = dict(row)
    rows = conn.execute(
        "SELECT thread_id, "
        "COALESCE(title, json_extract(payload_json, '$.title')) AS title, "
        "json_extract(payload_json, '$.pinnedAt') AS pinned_at, "
        "COALESCE(provider_instance_id, "
        "json_extract(payload_json, '$.providerInstanceId')) AS instance "
        "FROM orchestration_v2_projection_threads "
        "WHERE project_id = ? AND deleted_at IS NULL "
        "ORDER BY created_at, thread_id", (project["project_id"],)).fetchall()
except sqlite3.Error as exc:
    die(f"cannot read state database: {exc}")
finally:
    conn.close()
live = [{"threadId": r["thread_id"], "title": r["title"],
         "pinnedAt": r["pinned_at"], "instance": r["instance"]} for r in rows]

instances = set(tr.load_settings(spec).get("providerInstances", {}))
state, _ = tr.load_state(spec)
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
                  "journalMode": journal_mode,
                  "ok": not missing and not bad_primary}, indent=1))
sys.exit(0 if not missing and not bad_primary else 1)

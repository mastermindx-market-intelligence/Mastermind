#!/usr/bin/env python3
"""Local (Mac-side) checks for INSTALL_RUNBOOK.md. Stdlib only; never contacts a host.

Every subcommand reads files or stdin that the runbook's pipe-only ssh reads
produced, prints one JSON verdict, and exits 0 = PASS, 3 = FAIL, 2 = usage or
unreadable input. Nothing here writes outside the --out/--dir paths it is given.

  t1            installed-tree blob manifest vs `git ls-tree -r <sha>`  -> identity_manifest.tsv
  t4            service start ordering vs installed ctimes and the marker
  health        /health body: commit, reasoning_policy_ok, scheduled_runtime_ok
  events-filter stdin run_events JSONL -> stdout with extra.flags dropped (redaction)
  gates         G1 watch_us 02:20 finished; G2 no open run_started since process start
  app-started   app_started with extra.git_sha == sha after the restart (+ preflight)
  cycle         one job's run chain since a time, with a disposition hint (FAIL = tail too short)
  decisions     trimmed decision rows since a time
  close         manifest.json (sha256 of every evidence file) + redaction scan (tools/ hashed only)
"""

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys

PASS, FAIL, USAGE = 0, 3, 2

# Verbatim from scripts/deploy_code_to_vps.sh EXC (non-anchored basename patterns, any depth).
EXCLUDES = (
    ".git", ".github", ".worktrees", ".venv", "venv", "data", "vendor",
    "vendor_*", "__pycache__", "*.pyc", "*.pyo", "node_modules", "*.sqlite",
    "*.sqlite-*", "*.db", "*.log", ".DS_Store", "*.lock", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".env", ".env.*", "tmp", "catboost_info",
    "{_DB}", "tests", ".deploy_prev", ".deployed_git_sha",
)

DECISION_FIELDS = ("ts", "asof", "run_id", "target_status", "decision_effective",
                   "packet_id", "model", "error", "executed")

REDACTION = re.compile(
    r"sk-ant-|ghp_[A-Za-z0-9]|github_pat_|xox[bpas]-|AKIA[0-9A-Z]{16}"
    r"|BEGIN [A-Z ]*PRIVATE KEY|Bearer\s+[A-Za-z0-9._~+/-]{12,}"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)


def verdict(name, ok, **facts):
    print(json.dumps({"check": name, "verdict": "PASS" if ok else "FAIL", **facts}, sort_keys=True, default=str))
    return PASS if ok else FAIL


def excluded_path(path):
    return any(fnmatch.fnmatchcase(part, pattern) for part in path.split("/") for pattern in EXCLUDES)


def open_in(path):
    return sys.stdin if path == "-" else open(path, encoding="utf-8")


def read_jsonl(path):
    rows, bad = [], 0
    with open_in(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


def parse_ts(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.startswith("@"):
        return float(text[1:])
    # systemctl show --timestamp=us+utc|utc: "Thu 2026-10-22 06:02:22.123456 UTC"
    systemd = re.match(r"^(?:[A-Z][a-z]{2} )?(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?) UTC$", text)
    if systemd:
        text = "%sT%s+00:00" % systemd.groups()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python < 3.11 fromisoformat accepts only 3- or 6-digit fractions: pad/truncate to 6.
    text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    stamp = dt.datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.timestamp()


def iso(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- T1
def cmd_t1(args):
    listing = subprocess.run(["git", "-C", args.repo, "ls-tree", "-r", "-z", args.sha],
                             check=True, capture_output=True).stdout
    expected, excluded_in_commit, non_blob = {}, 0, 0
    for record in listing.split(b"\0"):
        if not record:
            continue
        head, path = record.split(b"\t", 1)
        mode, kind, obj = head.decode().split()
        path = path.decode("utf-8", "surrogateescape")
        if kind != "blob":
            non_blob += 1
            continue
        if excluded_path(path):
            excluded_in_commit += 1
            continue
        expected[path] = obj
    rows, bad = read_jsonl(args.manifest)
    meta, installed = {}, {}
    for row in rows:
        if isinstance(row, dict) and "meta" in row:
            meta = row["meta"]
        else:
            installed[row[0]] = row
    counts = {"equal": 0, "differing": 0, "missing_unexplained": 0, "host_extra": 0,
              "excluded_in_commit": excluded_in_commit, "non_blob_entries": non_blob,
              "unparsed_manifest_lines": bad}
    os.makedirs(args.out, exist_ok=True)
    max_mtime = max_ctime = 0.0
    with open(os.path.join(args.out, "identity_manifest.tsv"), "w", encoding="utf-8") as tsv:
        tsv.write("path\texpected_blob\tinstalled_blob\tstatus\n")
        for path in sorted(set(expected) | set(installed)):
            want = expected.get(path)
            have = installed.get(path)
            if want and have:
                status = "equal" if have[1] == want else "differing"
                max_mtime, max_ctime = max(max_mtime, have[2]), max(max_ctime, have[3])
            elif want:
                status = "missing_unexplained"
            else:
                status = "host_extra"
            counts[status] += 1
            tsv.write("%s\t%s\t%s\t%s\n" % (path, want or "-", have[1] if have else "-", status))
    summary = {
        "sha": args.sha,
        "counts": counts,
        "max_installed_mtime": max_mtime,
        "max_installed_ctime": max_ctime,
        "marker": {k: meta.get(k) for k in ("deployed_git_sha", "marker_mtime", "marker_ctime")},
        "marker_claim_matches": meta.get("deployed_git_sha") == args.sha,
    }
    with open(os.path.join(args.out, "t1_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
    ok = (counts["differing"] == 0 and counts["missing_unexplained"] == 0 and counts["host_extra"] == 0
          and counts["equal"] > 0 and bad == 0)
    return verdict("T1", ok, sha=args.sha, **counts, marker_claim_matches=summary["marker_claim_matches"])


# ---------------------------------------------------------------- T4
def parse_show(path):
    values = {}
    with open_in(path) as handle:
        for line in handle:
            if "=" in line:
                key, _, value = line.rstrip("\n").partition("=")
                values[key] = value
    return values


def cmd_t4(args):
    with open(args.t1_summary, encoding="utf-8") as handle:
        summary = json.load(handle)
    show = parse_show(args.show)
    try:
        started = parse_ts(show["ActiveEnterTimestamp"])
    except (KeyError, ValueError):
        return verdict("T4", False, reason="ActiveEnterTimestamp missing or unparseable (use --timestamp=unix or us+utc)")
    marker = summary.get("marker") or {}
    checks = {
        "active": show.get("ActiveState") == "active" and show.get("SubState") == "running",
        "main_pid_nonzero": show.get("MainPID", "0") not in ("", "0"),
        "after_max_installed_ctime": started > float(summary.get("max_installed_ctime") or 0),
        "after_marker_mtime": marker.get("marker_mtime") is not None and started > float(marker["marker_mtime"]),
        "after_marker_ctime": marker.get("marker_ctime") is not None and started > float(marker["marker_ctime"]),
    }
    if args.not_before:
        checks["after_window_open"] = started >= parse_ts(args.not_before)
    return verdict("T4", all(checks.values()), active_enter=iso(started),
                   max_installed_ctime=iso(float(summary.get("max_installed_ctime") or 0)), **checks)


# ---------------------------------------------------------------- /health
def cmd_health(args):
    try:
        with open_in(args.body) as handle:
            body = json.load(handle)
    except ValueError:
        return verdict("health", False, reason="body is not JSON")
    checks = {
        "commit": body.get("commit") == args.sha,
        "reasoning_policy_ok": body.get("reasoning_policy_ok") is True,
        "scheduled_runtime_ok": body.get("scheduled_runtime_ok") is True,
    }
    return verdict("health", all(checks.values()), observed_commit=body.get("commit"), **checks)


# ---------------------------------------------------------------- run_events
def cmd_events_filter(args):
    kept = bad = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        extra = row.get("extra")
        if isinstance(extra, dict):
            extra.pop("flags", None)
        sys.stdout.write(json.dumps(row, sort_keys=True) + "\n")
        kept += 1
    print(json.dumps({"events_filter": {"kept": kept, "unparsed": bad}}), file=sys.stderr)
    return PASS if bad == 0 else FAIL


def covers(rows, since):
    """True when the tail reaches back to `since` (its oldest event is at or before it)."""
    stamps = [parse_ts(r["ts"]) for r in rows if r.get("ts")]
    return bool(stamps) and min(stamps) <= since


def run_id(row):
    return (row.get("extra") or {}).get("run_id")


def open_runs(rows, since):
    finished = {run_id(r) for r in rows if r.get("kind") == "run_finished" and run_id(r)}
    return [r for r in rows if r.get("kind") == "run_started" and parse_ts(r["ts"]) >= since
            and run_id(r) not in finished]


def cmd_gates(args):
    rows, bad = read_jsonl(args.events)
    day = dt.date.fromisoformat(args.date)
    g1_from = dt.datetime(day.year, day.month, day.day, 2, 20, tzinfo=dt.timezone.utc).timestamp()
    g1_to = dt.datetime(day.year, day.month, day.day, 4, 10, tzinfo=dt.timezone.utc).timestamp()
    watch = [r for r in rows if r.get("job") == "watch_us_overnight" and r.get("kind") == "run_started"
             and g1_from <= parse_ts(r["ts"]) < g1_to]
    finished = {run_id(r): r for r in rows if r.get("kind") == "run_finished"}
    g1 = bool(watch) and all(run_id(r) in finished for r in watch)
    since = parse_ts(args.since_process)
    still_open = open_runs(rows, since)
    covered = covers(rows, min(since, g1_from))
    facts = {
        "tail_covers_window": covered,
        "G1_watch_us_0220_finished": g1,
        "G1_runs": [{"run_id": run_id(r), "started": r["ts"],
                     "finished": (finished.get(run_id(r)) or {}).get("ts")} for r in watch],
        "G2_no_open_run_since_process_start": not still_open,
        "G2_open": [{"job": r.get("job"), "book": r.get("book"), "ts": r["ts"], "run_id": run_id(r)} for r in still_open],
        "process_start": iso(since),
        "events_read": len(rows),
        "unparsed": bad,
    }
    return verdict("gates_G1_G2", g1 and not still_open and bad == 0 and covered, **facts)


def cmd_app_started(args):
    rows, bad = read_jsonl(args.events)
    since = parse_ts(args.since)
    apps = [r for r in rows if r.get("kind") == "app_started" and parse_ts(r["ts"]) >= since]
    match = [r for r in apps if (r.get("extra") or {}).get("git_sha") == args.sha]
    pre = [r for r in rows if r.get("kind") == "pending_target_cutover_preflight" and parse_ts(r["ts"]) >= since]
    preflight = {r.get("book"): (r.get("extra") or {}).get("safe_to_resume") for r in pre}
    outcomes = {r.get("book"): (r.get("extra") or {}).get("outcome") for r in pre}
    covered = covers(rows, since)
    ok = (covered and len(apps) == 1 and len(match) == 1 and bool(preflight)
          and all(v is True for v in preflight.values()))
    # "quarantined" is safe_to_resume (PASS) but is an incident: the runbook routes it to the seat.
    return verdict("app_started", ok, tail_covers_window=covered, app_started_since=len(apps), matching_sha=len(match),
                   app_started_ts=[r["ts"] for r in apps], preflight_safe_to_resume=preflight,
                   preflight_outcome=outcomes,
                   quarantine_incident=any(v == "quarantined" for v in outcomes.values()))


# ---------------------------------------------------------------- cycles
def cmd_cycle(args):
    rows, bad = read_jsonl(args.events)
    since = parse_ts(args.since)
    until = parse_ts(args.until) if args.until else float("inf")
    mine = [r for r in rows if r.get("job") == args.job and since <= parse_ts(r["ts"]) < until
            and (not args.book or r.get("book") in ("", args.book))]
    chain = []
    for r in mine:
        extra = r.get("extra") or {}
        chain.append({k: v for k, v in {
            "ts": r.get("ts"), "kind": r.get("kind"), "book": r.get("book"), "status": r.get("status"),
            "run_id": extra.get("run_id"), "target_status": extra.get("target_status"),
            "reason": extra.get("reason"), "severity": extra.get("severity"), "elapsed_s": extra.get("elapsed_s"),
        }.items() if v not in (None, "")})
    started = [r for r in mine if r.get("kind") == "run_started"]
    finished = [r for r in mine if r.get("kind") == "run_finished"]
    restarts = [r["ts"] for r in rows if r.get("kind") == "app_started" and since <= parse_ts(r["ts"]) < until]
    covered = covers(rows, since)
    if not covered:
        hint = "incomplete_uncertain: the run_events tail does not reach back to --since; re-read a longer tail"
    elif not started:
        hint = "no_run: not_due only with venue-gate evidence, else incomplete_uncertain (incident note)"
    elif open_runs(mine, since):
        hint = "started (incomplete_uncertain if a restart is in the window: %s)" % (restarts or "none")
    else:
        last = (finished[-1].get("extra") or {}) if finished else {}
        status = finished[-1].get("status") if finished else None
        target = str(last.get("target_status") or "")
        if target.startswith("rejected_") or target.startswith("frozen_"):
            hint = "rejected (%s, reason=%s)" % (target, last.get("reason"))
        elif status not in ("ok", None) and not target:
            hint = "failed (status=%s)" % status
        elif target in ("queued", "executed"):
            hint = "accepted: accepted_change only once the settle job shows fills + finalized receipt; else accepted_no_change"
        else:
            hint = "finished status=%s target_status=%s: classify from decision row" % (status, target or "-")
    print(json.dumps({"job": args.job, "book": args.book, "since": args.since, "events": chain,
                      "restarts_in_window": restarts, "disposition_hint": hint, "unparsed": bad,
                      "tail_covers_window": covered}, indent=1, sort_keys=True))
    return PASS if covered and bad == 0 else FAIL


def cmd_decisions(args):
    rows, bad = read_jsonl(args.file)
    since = parse_ts(args.since)
    for row in rows:
        try:
            when = parse_ts(row.get("ts"))
        except (TypeError, ValueError):
            continue
        if when >= since:
            print(json.dumps({k: row.get(k) for k in DECISION_FIELDS}, sort_keys=True, default=str))
    return PASS if bad == 0 else FAIL


# ---------------------------------------------------------------- close
def cmd_close(args):
    entries, hits = {}, []
    for dirpath, dirnames, filenames in os.walk(args.dir):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, args.dir)
            if rel == "manifest.json":
                continue
            with open(full, "rb") as handle:
                data = handle.read()
            entries[rel] = hashlib.sha256(data).hexdigest()
            if rel.split(os.sep)[0] == "tools":
                continue  # the helpers' own source carries the pattern text; pinned by sha256 instead
            for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if REDACTION.search(line):
                    hits.append("%s:%d" % (rel, number))
    with open(os.path.join(args.dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump({"created": iso(dt.datetime.now(dt.timezone.utc).timestamp()), "sha256": entries},
                  handle, indent=1, sort_keys=True)
    return verdict("close", not hits, files=len(entries), redaction_hits=hits[:50])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("t1"); p.add_argument("--repo", required=True); p.add_argument("--sha", required=True)
    p.add_argument("--manifest", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_t1)
    p = sub.add_parser("t4"); p.add_argument("--t1-summary", required=True); p.add_argument("--show", required=True)
    p.add_argument("--not-before"); p.set_defaults(fn=cmd_t4)
    p = sub.add_parser("health"); p.add_argument("--body", required=True); p.add_argument("--sha", required=True)
    p.set_defaults(fn=cmd_health)
    p = sub.add_parser("events-filter"); p.set_defaults(fn=cmd_events_filter)
    p = sub.add_parser("gates"); p.add_argument("--events", required=True); p.add_argument("--date", required=True)
    p.add_argument("--since-process", required=True); p.set_defaults(fn=cmd_gates)
    p = sub.add_parser("app-started"); p.add_argument("--events", required=True); p.add_argument("--sha", required=True)
    p.add_argument("--since", required=True); p.set_defaults(fn=cmd_app_started)
    p = sub.add_parser("cycle"); p.add_argument("--events", required=True); p.add_argument("--job", required=True)
    p.add_argument("--since", required=True); p.add_argument("--until"); p.add_argument("--book")
    p.set_defaults(fn=cmd_cycle)
    p = sub.add_parser("decisions"); p.add_argument("--file", required=True); p.add_argument("--since", required=True)
    p.set_defaults(fn=cmd_decisions)
    p = sub.add_parser("close"); p.add_argument("--dir", required=True); p.set_defaults(fn=cmd_close)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (OSError, subprocess.CalledProcessError, KeyError, IndexError, ValueError) as exc:
        print(json.dumps({"check": args.cmd, "verdict": "ERROR", "error": repr(exc)}))
        return USAGE


if __name__ == "__main__":
    sys.exit(main())

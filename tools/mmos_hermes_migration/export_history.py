#!/usr/bin/env python3
"""Export a COPY of a Hermes agent SQLite state DB into a read-only archive.

Usage:
  export_history.py export --source <copy.db> --profile <name> --out <archive_dir> [--forbid-root PATH ...]
  export_history.py verify --source <copy.db> --archive <archive_dir>

The source must be a copy (never the live store under ~/.hermes), is opened
read-only, and is never written. Every source row is exported (including
inactive/compacted rows, flags kept) with credential redaction on content,
tool_calls and title. reasoning / reasoning_content / api_content are NOT
copied; only their non-empty row counts are recorded in the manifest.
Stdout/stderr carry counts and paths only — never message content or titles.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Run with `python3.12 -I` (isolated): the script dir is not on sys.path then.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact import redact

TOOL_VERSION = "1.0.0"
BATCH = 500
MD_TOOL_LIMIT = 4000

SESSION_SRC_FIELDS = [
    "id", "source", "title", "display_name", "model", "parent_session_id",
    "started_at", "ended_at", "profile_name", "message_count",
]
MESSAGE_SRC_FIELDS = [
    "id", "session_id", "role", "content", "tool_call_id", "tool_calls",
    "tool_name", "timestamp", "finish_reason", "active", "compacted", "display_kind",
]
OMITTED_FIELDS = ["reasoning", "reasoning_content", "api_content"]


def fail(reason):
    print(reason, file=sys.stderr)
    sys.exit(1)


def under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def home_dir():
    return os.path.realpath(os.path.expanduser("~"))


def check_source(source, forbid_roots):
    if os.path.islink(source):
        fail("refusing source: it is a symlink; pass a real copy file")
    real = os.path.realpath(source)
    if not os.path.isfile(real):
        fail(f"refusing source: not a file: {real}")
    if under(real, os.path.join(home_dir(), ".hermes")):
        fail("refusing source: realpath is under ~/.hermes (live store); export a copy instead")
    for root in forbid_roots:
        if under(real, os.path.realpath(root)):
            fail(f"refusing source: under --forbid-root {root}")
    return real


def check_out(out, forbid_roots):
    real = os.path.realpath(out)
    if under(real, os.path.join(home_dir(), ".hermes")):
        fail("refusing --out: realpath is under ~/.hermes")
    if under(real, os.path.join(home_dir(), ".mastermind", "t3-team")):
        fail("refusing --out: realpath is under ~/.mastermind/t3-team")
    for root in forbid_roots:
        if under(real, os.path.realpath(root)):
            fail(f"refusing --out: under --forbid-root {root}")
    if os.path.exists(real):
        if not os.path.isdir(real):
            fail(f"refusing --out: exists and is not a directory: {real}")
        if any(os.scandir(real)):
            fail(f"refusing --out: exists and is non-empty (no overwrite): {real}")
    return real


def ro_connect(path):
    return sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)


def table_cols(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def select_sql(table, fields, present):
    exprs = [f if f in present else f"NULL AS {f}" for f in fields]
    return f"SELECT {', '.join(exprs)} FROM {table}"


def utc_iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def utc_date(ts):
    if ts is None:
        return "unknown-date"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def safe_component(text):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(text))


def session_filename(meta):
    return f"{utc_date(meta['started_at'])}_{safe_component(meta['source'])}_{meta['id'][:12]}.md"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tool_names(tool_calls_json):
    try:
        data = json.loads(tool_calls_json)
    except (ValueError, TypeError):
        return []
    items = data if isinstance(data, list) else data.get("tool_calls", []) if isinstance(data, dict) else []
    names = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        name = fn.get("name") if isinstance(fn, dict) else item.get("name")
        if name:
            names.append(str(name))
    return names


def render_message_md(row, redacted_content):
    src_id, role, content, tool_calls, tool_name, timestamp, active, compacted = row
    heading = f"### {role} · {utc_iso(timestamp)}"
    if compacted == 1 or active == 0:
        heading += " (compacted)"
    body = redacted_content or ""
    if role == "tool" and len(body) > MD_TOOL_LIMIT:
        body = body[:MD_TOOL_LIMIT] + f"… [truncated {len(body) - MD_TOOL_LIMIT} chars; full text in archive.sqlite src_id={src_id}]"
    lines = [heading, "", body]
    if tool_calls:
        names = tool_names(tool_calls)
        lines += ["", "*(tool calls: " + (", ".join(names) if names else "unparsed") + ")*"]
    return "\n".join(lines) + "\n\n"


def write_session_header(fh, meta):
    fh.write(f"# Session {meta['id']}\n\n")
    fh.write(f"- source: {meta['source']}\n")
    fh.write(f"- title: {meta['title'] or ''}\n")
    fh.write(f"- model: {meta['model'] or ''}\n")
    fh.write(f"- started: {utc_iso(meta['started_at'])}\n")
    fh.write(f"- ended: {utc_iso(meta['ended_at'])}\n")
    fh.write(f"- messages: {meta['message_count_src']}\n\n")


def count_rows(con, table):
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    by_role = {}
    if table == "messages":
        by_role = {r: c for r, c in con.execute("SELECT role, COUNT(*) FROM messages GROUP BY role")}
    return n, by_role


def make_count_check(src_con, dst_con):
    s_in, _ = count_rows(src_con, "sessions")
    s_out, _ = count_rows(dst_con, "sessions")
    m_in, role_in = count_rows(src_con, "messages")
    m_out, role_out = count_rows(dst_con, "messages")
    ok = s_in == s_out and m_in == m_out and role_in == role_out
    return {
        "sessions_in": s_in, "sessions_out": s_out,
        "messages_in": m_in, "messages_out": m_out,
        "by_role_in": role_in, "by_role_out": role_out,
        "pass": ok,
    }


def lock_down(out):
    for dirpath, dirnames, filenames in os.walk(out, topdown=False):
        for name in filenames:
            os.chmod(os.path.join(dirpath, name), 0o400)
        os.chmod(dirpath, 0o500)
    os.chmod(out, 0o500)


def cmd_export(args):
    src = check_source(args.source, args.forbid_root)
    out = check_out(args.out, args.forbid_root)
    os.makedirs(out, exist_ok=True)
    os.chmod(out, 0o700)
    (Path(out) / "sessions").mkdir(exist_ok=True)

    src_con = ro_connect(src)
    dst_con = sqlite3.connect(str(Path(out) / "archive.sqlite"))
    dst_con.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT, display_name TEXT, "
        "model TEXT, parent_session_id TEXT, started_at REAL, ended_at REAL, profile_name TEXT, message_count_src INTEGER)"
    )
    dst_con.execute(
        "CREATE TABLE messages (src_id INTEGER, session_id TEXT, role TEXT, content TEXT, tool_call_id TEXT, "
        "tool_calls TEXT, tool_name TEXT, timestamp REAL, finish_reason TEXT, active INTEGER, compacted INTEGER, display_kind TEXT)"
    )
    dst_con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(content, tool_name, content='messages', content_rowid='rowid')")
    dst_con.execute("CREATE VIRTUAL TABLE sessions_fts USING fts5(title, content='sessions', content_rowid='rowid')")

    redactions = Counter()
    omitted = Counter({f: 0 for f in OMITTED_FIELDS})
    by_source = Counter()
    by_role = Counter()
    active_n = inactive_n = 0
    sess_meta = {}
    sess_msg_counts = Counter()
    first_user_snippet = {}

    # --- sessions (metadata only; streamed in batches) ---
    s_fields = SESSION_SRC_FIELDS
    s_present = table_cols(src_con, "sessions")
    s_batch, s_fts_batch = [], []
    for rowid, row in enumerate(src_con.execute(select_sql("sessions", s_fields, s_present) + " ORDER BY started_at, id"), start=1):
        (sid, source, title, display_name, model, parent, started, ended, profile, msg_count) = row
        title_red, tc = redact(title)
        redactions.update(tc)
        meta = {
            "id": sid, "source": source, "title": title_red, "display_name": display_name,
            "model": model, "parent_session_id": parent, "started_at": started, "ended_at": ended,
            "profile_name": profile, "message_count_src": msg_count, "rowid": rowid,
        }
        sess_meta[sid] = meta
        by_source[source] += 1
        s_batch.append((rowid, sid, source, title_red, display_name, model, parent, started, ended, profile, msg_count))
        s_fts_batch.append((rowid, title_red))
        if len(s_batch) >= BATCH:
            dst_con.executemany(
                "INSERT INTO sessions(rowid, id, source, title, display_name, model, parent_session_id, "
                "started_at, ended_at, profile_name, message_count_src) VALUES (?,?,?,?,?,?,?,?,?,?,?)", s_batch)
            dst_con.executemany("INSERT INTO sessions_fts(rowid, title) VALUES (?,?)", s_fts_batch)
            s_batch, s_fts_batch = [], []
    if s_batch:
        dst_con.executemany(
            "INSERT INTO sessions(rowid, id, source, title, display_name, model, parent_session_id, "
            "started_at, ended_at, profile_name, message_count_src) VALUES (?,?,?,?,?,?,?,?,?,?,?)", s_batch)
        dst_con.executemany("INSERT INTO sessions_fts(rowid, title) VALUES (?,?)", s_fts_batch)

    # --- messages (streamed; md written incrementally per session) ---
    m_fields = MESSAGE_SRC_FIELDS + OMITTED_FIELDS
    m_present = table_cols(src_con, "messages")
    m_batch, m_fts_batch = [], []
    cur_sid = None
    cur_fh = None
    rowid = 0
    sql = select_sql("messages", m_fields, m_present) + " ORDER BY session_id, timestamp, id"
    for row in src_con.execute(sql):
        (src_id, sid, role, content, tool_call_id, tool_calls, tool_name, timestamp,
         finish_reason, active, compacted, display_kind) = row[:12]
        reasoning_vals = row[12:]
        for field, val in zip(OMITTED_FIELDS, reasoning_vals):
            if val is not None and val != "":
                omitted[field] += 1
        content_red, cc = redact(content)
        redactions.update(cc)
        calls_red, cc = redact(tool_calls)
        redactions.update(cc)
        rowid += 1
        m_batch.append((rowid, src_id, sid, role, content_red, tool_call_id, calls_red, tool_name,
                        timestamp, finish_reason, active, compacted, display_kind))
        m_fts_batch.append((rowid, content_red, tool_name))
        if len(m_batch) >= BATCH:
            dst_con.executemany(
                "INSERT INTO messages(rowid, src_id, session_id, role, content, tool_call_id, tool_calls, "
                "tool_name, timestamp, finish_reason, active, compacted, display_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", m_batch)
            dst_con.executemany("INSERT INTO messages_fts(rowid, content, tool_name) VALUES (?,?,?)", m_fts_batch)
            m_batch, m_fts_batch = [], []
        by_role[role] += 1
        sess_msg_counts[sid] += 1
        if active == 1:
            active_n += 1
        else:
            inactive_n += 1
        if sid not in sess_meta:  # orphan message: stub header from the message itself
            sess_meta[sid] = {"id": sid, "source": "unknown", "title": None, "display_name": None,
                              "model": None, "parent_session_id": None, "started_at": timestamp,
                              "ended_at": None, "profile_name": None, "message_count_src": None}
        if role == "user" and sid not in first_user_snippet:
            first_user_snippet[sid] = (content_red or "")[:80]
        if sid != cur_sid:
            if cur_fh is not None:
                cur_fh.close()
            cur_sid = sid
            cur_fh = open(Path(out) / "sessions" / session_filename(sess_meta[sid]), "w", encoding="utf-8")
            write_session_header(cur_fh, sess_meta[sid])
        cur_fh.write(render_message_md(
            (src_id, role, content_red, calls_red, tool_name, timestamp, active, compacted), content_red))
    if m_batch:
        dst_con.executemany(
            "INSERT INTO messages(rowid, src_id, session_id, role, content, tool_call_id, tool_calls, "
            "tool_name, timestamp, finish_reason, active, compacted, display_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", m_batch)
        dst_con.executemany("INSERT INTO messages_fts(rowid, content, tool_name) VALUES (?,?,?)", m_fts_batch)
    if cur_fh is not None:
        cur_fh.close()
    # sessions with no messages still get a header-only md file
    for sid, meta in sess_meta.items():
        path = Path(out) / "sessions" / session_filename(meta)
        if not path.exists():
            with open(path, "w", encoding="utf-8") as fh:
                write_session_header(fh, meta)

    # --- INDEX.md ---
    metas = sorted(sess_meta.values(), key=lambda m: (m["started_at"] or 0, m["id"]), reverse=True)
    total_messages = sum(sess_msg_counts.values())
    dates = [m["started_at"] for m in metas if m["started_at"] is not None]
    date_range = {"start": utc_date(min(dates)), "end": utc_date(max(dates))} if dates else {"start": None, "end": None}
    with open(Path(out) / "INDEX.md", "w", encoding="utf-8") as fh:
        fh.write(f"# History archive — profile {args.profile}\n\n")
        fh.write(f"- sessions: {len(metas)}\n- messages: {total_messages}\n")
        fh.write(f"- date range: {date_range['start']} .. {date_range['end']}\n")
        fh.write(f"- redactions: {sum(redactions.values())}\n\n")
        for meta in metas:
            title = meta["title"] or first_user_snippet.get(meta["id"]) or "(no title)"
            title = " ".join(title.split())
            fname = session_filename(meta)
            fh.write(f"- {utc_date(meta['started_at'])} | {meta['source']} | {title} | "
                     f"{sess_msg_counts.get(meta['id'], 0)} msgs | [{fname}](sessions/{fname})\n")

    count_check = make_count_check(src_con, dst_con)
    manifest = {
        "tool_version": TOOL_VERSION,
        "profile": args.profile,
        "source": src,
        "source_sha256": sha256_file(src),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "sessions": len(metas), "messages": total_messages,
            "by_role": dict(by_role), "by_source": dict(by_source),
            "active": active_n, "inactive": inactive_n,
        },
        "redactions": dict(redactions),
        "omitted_fields": dict(omitted),
        "date_range": date_range,
        "count_check": count_check,
    }
    with open(Path(out) / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    dst_con.commit()
    dst_con.close()
    src_con.close()
    lock_down(out)
    print(f"export: sessions={len(metas)} messages={total_messages} "
          f"redactions={sum(redactions.values())} omitted={dict(omitted)} -> {out}")
    if not count_check["pass"]:
        print("count_check: FAIL", file=sys.stderr)
        sys.exit(1)
    print("count_check: PASS")


def cmd_verify(args):
    src = check_source(args.source, [])
    archive = Path(args.archive)
    db = archive / "archive.sqlite"
    if not db.is_file():
        fail(f"verify: archive.sqlite not found in {archive}")
    src_con = ro_connect(src)
    dst_con = ro_connect(str(db))
    cc = make_count_check(src_con, dst_con)
    src_con.close()
    dst_con.close()
    mismatches = []
    if cc["sessions_in"] != cc["sessions_out"]:
        mismatches.append(f"sessions: in={cc['sessions_in']} out={cc['sessions_out']}")
    if cc["messages_in"] != cc["messages_out"]:
        mismatches.append(f"messages: in={cc['messages_in']} out={cc['messages_out']}")
    for role in sorted(set(cc["by_role_in"]) | set(cc["by_role_out"])):
        a, b = cc["by_role_in"].get(role, 0), cc["by_role_out"].get(role, 0)
        if a != b:
            mismatches.append(f"by_role.{role}: in={a} out={b}")
    print(json.dumps({"pass": not mismatches, "mismatches": mismatches}))
    sys.exit(0 if not mismatches else 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_exp = sub.add_parser("export", help="export a copy DB into a read-only archive")
    p_exp.add_argument("--source", required=True)
    p_exp.add_argument("--profile", required=True)
    p_exp.add_argument("--out", required=True)
    p_exp.add_argument("--forbid-root", action="append", default=[])
    p_exp.set_defaults(func=cmd_export)
    p_ver = sub.add_parser("verify", help="recompute counts source vs archive")
    p_ver.add_argument("--source", required=True)
    p_ver.add_argument("--archive", required=True)
    p_ver.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (sqlite3.Error, OSError) as exc:
        fail(f"{args.cmd} failed: {exc}")


if __name__ == "__main__":
    main()

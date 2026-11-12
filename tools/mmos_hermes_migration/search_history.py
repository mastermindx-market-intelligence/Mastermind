#!/usr/bin/env python3
"""Search a read-only Hermes history archive (see export_history.py).

Usage:
  search_history.py <archive_dir> <query...> [--role user|assistant|tool]
      [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--session <id prefix>]
      [--limit N (default 10, max 50)] [--json]
  search_history.py <archive_dir> --show <src_id>

FTS5 MATCH with bm25 ranking; user text is quoted so it can never become
FTS syntax (LIKE fallback on any FTS error). Opens archive.sqlite read-only.
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Run with `python3.12 -I` (isolated): the script dir is not on sys.path then.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_history import ro_connect, session_filename, utc_date, utc_iso

SNIPPET_MAX = 300


def fail(reason):
    print(reason, file=sys.stderr)
    sys.exit(1)


def day_start(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def fts_query_string(query):
    return " ".join('"' + tok.replace('"', '""') + '"' for tok in query.split())


def like_escape(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def clip(snippet):
    return snippet if len(snippet) <= SNIPPET_MAX else snippet[:SNIPPET_MAX]


def like_snippet(content, terms):
    text = content or ""
    low = text.lower()
    pos = -1
    for t in terms:
        pos = low.find(t.lower())
        if pos >= 0:
            break
    if pos < 0:
        return clip(text)
    start = max(0, pos - 60)
    window = text[start:start + SNIPPET_MAX]
    for t in terms:
        idx = window.lower().find(t.lower())
        if idx >= 0:
            window = window[:idx] + "[[" + window[idx:idx + len(t)] + "]]" + window[idx + len(t):]
            break
    return clip(("…" if start > 0 else "") + window)


def hit_meta(row):
    src_id, sid, role, ts, source, started = row
    meta = {"id": sid, "source": source or "unknown", "started_at": started if started is not None else ts}
    return {
        "date": utc_date(ts),
        "session_file": session_filename(meta),
        "role": role,
        "src_id": src_id,
    }


def run_search(con, args):
    query_text = " ".join(args.query)
    terms = query_text.split()
    where, params = [], []
    if args.role:
        where.append("m.role = ?")
        params.append(args.role)
    if args.since:
        where.append("m.timestamp >= ?")
        params.append(day_start(args.since))
    if args.until:
        where.append("m.timestamp < ?")
        params.append(day_start(args.until) + 86400)
    if args.session:
        where.append("substr(m.session_id, 1, ?) = ?")
        params.extend([len(args.session), args.session])
    extra = (" AND " + " AND ".join(where)) if where else ""
    limit = max(1, min(50, args.limit))
    base = (
        "SELECT m.src_id, m.session_id, m.role, m.timestamp, s.source, s.started_at "
        "FROM messages_fts JOIN messages m ON m.rowid = messages_fts.rowid "
        "LEFT JOIN sessions s ON s.id = m.session_id "
        "WHERE messages_fts MATCH ?" + extra + " ORDER BY bm25(messages_fts) LIMIT ?"
    )
    try:
        rows = con.execute(
            "SELECT m.src_id, m.session_id, m.role, m.timestamp, s.source, s.started_at, "
            "snippet(messages_fts, 0, '[[', ']]', '…', 10) "
            "FROM messages_fts JOIN messages m ON m.rowid = messages_fts.rowid "
            "LEFT JOIN sessions s ON s.id = m.session_id "
            "WHERE messages_fts MATCH ?" + extra + " ORDER BY bm25(messages_fts) LIMIT ?",
            [fts_query_string(query_text)] + params + [limit],
        ).fetchall()
        hits = []
        for row in rows:
            hit = hit_meta(row[:6])
            hit["snippet"] = clip(row[6] or "")
            hits.append(hit)
        return hits
    except sqlite3.OperationalError:
        pass  # user text broke FTS despite quoting: fall back to LIKE
    like_where, like_params = [], []
    for t in terms:
        like_where.append("(m.content LIKE ? ESCAPE '\\' OR m.tool_name LIKE ? ESCAPE '\\')")
        pat = "%" + like_escape(t) + "%"
        like_params.extend([pat, pat])
    sql = (
        "SELECT m.src_id, m.session_id, m.role, m.timestamp, s.source, s.started_at, m.content "
        "FROM messages m LEFT JOIN sessions s ON s.id = m.session_id WHERE "
        + " AND ".join(like_where) + extra + " ORDER BY m.timestamp DESC LIMIT ?"
    )
    rows = con.execute(sql, like_params + params + [limit]).fetchall()
    hits = []
    for row in rows:
        hit = hit_meta(row[:6])
        hit["snippet"] = like_snippet(row[6], terms)
        hits.append(hit)
    return hits


def show_message(con, src_id):
    row = con.execute("SELECT session_id FROM messages WHERE src_id = ?", (src_id,)).fetchone()
    if row is None:
        fail(f"no message with src_id={src_id}")
    sid = row[0]
    ids = [r[0] for r in con.execute(
        "SELECT src_id FROM messages WHERE session_id = ? ORDER BY timestamp, src_id", (sid,))]
    i = ids.index(src_id)
    window = ids[max(0, i - 2):i + 3]
    srow = con.execute("SELECT source, started_at FROM sessions WHERE id = ?", (sid,)).fetchone()
    first = con.execute(
        "SELECT timestamp FROM messages WHERE src_id = ?", (window[0],)).fetchone()
    meta = {"id": sid, "source": (srow[0] if srow else "unknown"),
            "started_at": (srow[1] if srow and srow[1] is not None else first[0])}
    print(f"# {session_filename(meta)} (session {sid})")
    for wid in window:
        m = con.execute(
            "SELECT role, content, timestamp, active, compacted FROM messages WHERE src_id = ?", (wid,)).fetchone()
        role, content, ts, active, compacted = m
        heading = f"### {role} · {utc_iso(ts)}"
        if compacted == 1 or active == 0:
            heading += " (compacted)"
        print(heading)
        print()
        print(content or "")
        print()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive_dir")
    parser.add_argument("query", nargs="*")
    parser.add_argument("--role", choices=["user", "assistant", "tool"])
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--session")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show", type=int)
    args = parser.parse_args(argv)
    db = Path(args.archive_dir) / "archive.sqlite"
    if not db.is_file():
        fail(f"archive.sqlite not found in {args.archive_dir}")
    if args.show is None and not args.query:
        fail("empty query: pass search terms or --show <src_id>")
    for name in ("since", "until"):
        val = getattr(args, name)
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                fail(f"--{name} must be YYYY-MM-DD")
    con = ro_connect(str(db))
    try:
        if args.show is not None:
            show_message(con, args.show)
            return
        hits = run_search(con, args)
        if args.json:
            print(json.dumps(hits))
        else:
            for h in hits:
                print(f"{h['date']} | {h['role']} | src_id={h['src_id']} | {h['session_file']} | {h['snippet']}")
    finally:
        con.close()


if __name__ == "__main__":
    main()

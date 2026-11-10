"""One-shot, private Hermes history projection using native export and Paperclip APIs.

Original Hermes databases remain authoritative. No model calls, runtime restarts,
history imports, memory writes, agent assignments, or scheduled synchronization.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import zipfile


COMPANY = "a5f907fc-c4b1-478c-a1b1-1748d32206dd"
PAPERCLIP_VERSION = "2026.1106.0"
API = "http://127.0.0.1:3100/api"
PROFILE_NAMES = (
    "assurance", "autonomy-ceo", "chief-of-staff", "delivery", "design-lead",
    "engineering", "intelligence", "marketing", "mastermind-ceo",
    "meta-ceo-uncensored", "product", "reliability", "secretary",
)
MAX_UPLOAD = 9 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def save_new(path: Path, data: bytes) -> None:
    """Never overwrite a previous snapshot, artifact, or operation receipt."""
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def save_json(path: Path, value) -> None:
    save_new(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def api(path: str, method: str = "GET", body=None, content_type=None):
    data = body if isinstance(body, bytes) else None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": content_type or "application/json"}
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    # Do not follow a redirect carrying private archive data to another origin.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
        payload = response.read()
        return json.loads(payload) if "json" in response.headers.get("Content-Type", "") else payload


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise RuntimeError(f"Archive directory is not private: {path}")


def snapshot(source: Path, destination: Path) -> dict:
    """SQLite's online backup includes the WAL and gives one consistent profile snapshot."""
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("Expected an existing regular profile database")
    save_new(destination, b"")
    started = now()
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10) as origin:
        with sqlite3.connect(destination) as target:
            origin.backup(target, pages=256, sleep=0.05)
            if target.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("Snapshot integrity check failed")
            sessions = target.execute("SELECT count(*) FROM sessions").fetchone()[0]
            messages = target.execute("SELECT count(*) FROM messages").fetchone()[0]
            orphans = target.execute("SELECT count(*) FROM messages m LEFT JOIN sessions s ON s.id=m.session_id WHERE s.id IS NULL").fetchone()[0]
            high_water = target.execute("SELECT max(id), max(timestamp) FROM messages").fetchone()
    return {"snapshot_started_at": started, "snapshot_completed_at": now(),
            "sessions": sessions, "messages": messages, "orphan_messages": orphans,
            "message_high_water": list(high_water), "snapshot_sha256": digest(destination.read_bytes())}


def verify_export(connection, record: dict) -> None:
    """An exporter silently dropping inactive rows must stop the migration."""
    expected = connection.execute("SELECT id FROM messages WHERE session_id=? ORDER BY id", (record["id"],)).fetchall()
    observed = sorted(m["id"] for m in record.get("messages", []))
    if observed != [r[0] for r in expected]:
        raise RuntimeError("Native export omitted or duplicated stored message identities")
    columns = {r[1] for r in connection.execute("PRAGMA table_info(messages)")}
    for flag in ("active", "compacted"):
        if flag in columns:
            flags = dict(connection.execute(f"SELECT id, {flag} FROM messages WHERE session_id=?", (record["id"],)))
            if any(m.get(flag) != flags[m["id"]] for m in record.get("messages", [])):
                raise RuntimeError(f"Native export changed the {flag} flags")


def scrub(value, redact):
    """Use the native secret detector for metadata too, not just message bodies."""
    if isinstance(value, str):
        return redact(value, force=True)
    if isinstance(value, list):
        return [scrub(v, redact) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, redact) for k, v in value.items()}
    return value


def write_bundle(folder: Path, profile: str, number: int, records, render_html) -> dict:
    stem = f"hermes-{profile}-{number:03d}"
    payload = b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode() for r in records)
    rendered = render_html(records).encode()
    summary = {"profile": profile, "sessions": len(records),
               "messages": sum(len(r.get("messages", [])) for r in records),
               "session_ids": [r["id"] for r in records], "redacted": True,
               "projection": "all stored rows; original active/compacted flags retained",
               "history_jsonl_sha256": digest(payload), "reader_html_sha256": digest(rendered)}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        bundle.writestr("manifest.json", json.dumps(summary, ensure_ascii=False, indent=2))
        bundle.writestr("history.jsonl", payload)
        bundle.writestr("reader.html", rendered)
    zipped = buffer.getvalue()
    if len(zipped) > MAX_UPLOAD:
        raise RuntimeError("A history bundle exceeds the existing attachment limit; split it before publication")
    path = folder / (stem + ".zip")
    save_new(path, zipped)
    summary.update({"filename": path.name, "sha256": digest(zipped), "bytes": len(zipped)})
    if len(rendered) <= MAX_UPLOAD:
        html_path = folder / (stem + ".html")
        save_new(html_path, rendered)
        summary["reader"] = {"filename": html_path.name, "sha256": digest(rendered), "bytes": len(rendered)}
    return summary


def export_profile(home: Path, output: Path, name: str, native_db, redact, render_html) -> dict:
    folder = output / name
    private_directory(folder)
    existing = folder / "profile.json"
    if existing.exists():
        result = json.loads(existing.read_text())
        for part in result["bundles"]:
            if digest((folder / part["filename"]).read_bytes()) != part["sha256"]:
                raise RuntimeError("Previously saved archive changed")
        return result
    snap_path = folder / "snapshot.db"
    meta = snapshot(home / "state.db", snap_path)
    if meta["orphan_messages"]:
        raise RuntimeError("Orphaned stored messages require explicit recovery before full-history export")
    db = native_db(snap_path, read_only=True)
    index, bundles, current = [], [], []
    current_size = exported_messages = 0
    try:
        with sqlite3.connect(snap_path.as_uri() + "?mode=ro", uri=True) as raw:
            ids = [row[0] for row in raw.execute("SELECT id FROM sessions ORDER BY started_at,id")]
            for session_id in ids:
                db.assert_export_safe(session_id)
                record = db.export_session(session_id, include_inactive=True)
                if not record or record["id"] != session_id:
                    raise RuntimeError("Native exporter did not return the requested source session")
                verify_export(raw, record)
                clean = scrub(record, redact)
                size = len(json.dumps(clean, ensure_ascii=False).encode())
                if current and (len(current) >= 100 or current_size + size > 2 * 1024 * 1024):
                    bundles.append(write_bundle(folder, name, len(bundles) + 1, current, render_html))
                    current, current_size = [], 0
                current.append(clean)
                current_size += size
                exported_messages += len(record["messages"])
                index.append({"id": session_id, "title": clean.get("title") or session_id,
                              "started_at": clean.get("started_at"), "ended_at": clean.get("ended_at"),
                              "messages": len(record["messages"]), "bundle": len(bundles) + 1})
        if current:
            bundles.append(write_bundle(folder, name, len(bundles) + 1, current, render_html))
    finally:
        db.close()
    if len(index) != meta["sessions"] or exported_messages != meta["messages"]:
        raise RuntimeError("Export totals do not reconcile with the consistent source snapshot")
    result = {"profile": name, "source_home": str(home), **meta, "bundles": bundles, "index": index,
              "media_note": "Original media references remain in the preserved native database and exported records; referenced external bytes are not implicitly copied."}
    save_json(existing, result)
    return result


def prepare(args) -> None:
    private_directory(args.output)
    sys.path.insert(0, str(args.source))
    import hermes_bootstrap  # noqa: F401 - native PM dependency owner
    from hermes_state import SessionDB
    from agent.redact import redact_sensitive_text
    from hermes_cli.session_export_html import generate_multi_session_html_export
    names = [args.profile] if args.profile else ["legacy-default", *PROFILE_NAMES]
    for name in names:
        home = args.home if name == "legacy-default" else args.home / "profiles" / name
        if name not in ("legacy-default", *PROFILE_NAMES):
            raise RuntimeError("Profile is not part of the inspected fleet")
        result = export_profile(home, args.output, name, SessionDB, redact_sensitive_text, generate_multi_session_html_export)
        print(json.dumps({"profile": name, "sessions": result["sessions"], "messages": result["messages"],
                          "bundles": len(result["bundles"]), "verified": True}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile")
    args = parser.parse_args()
    prepare(args)


if __name__ == "__main__":
    main()

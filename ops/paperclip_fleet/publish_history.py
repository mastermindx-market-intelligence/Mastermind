"""Publish a verified history snapshot to one private, unassigned Paperclip archive.

No automatic retry: pending effects reconcile at their original native object.
Original databases and raw snapshots are never uploaded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.error
import uuid
import zipfile

from paperclip_history import API, COMPANY, MAX_UPLOAD, PAPERCLIP_VERSION, PROFILE_NAMES, api, digest, private_directory, save_json

MARKER = "hermes-history-20261110"
TITLE = "Imported Hermes conversations"


def verify_profile(folder: Path, profile: dict) -> None:
    """Reconcile the original snapshot, complete record identities, and every artifact."""
    if digest((folder / "snapshot.db").read_bytes()) != profile["snapshot_sha256"]:
        raise RuntimeError("Preserved snapshot differs from its verified export")
    rows = {row["id"]: row for row in profile["index"]}
    if len(rows) != profile["sessions"]:
        raise RuntimeError("Profile index contains duplicate or missing session identities")
    seen, locations = {}, {}
    for number, bundle in enumerate(profile["bundles"], 1):
        payload = (folder / bundle["filename"]).read_bytes()
        if digest(payload) != bundle["sha256"] or len(payload) != bundle["bytes"]:
            raise RuntimeError("Saved bundle changed")
        with zipfile.ZipFile(folder / bundle["filename"]) as archive:
            if set(archive.namelist()) != {"manifest.json", "history.jsonl", "reader.html"}:
                raise RuntimeError("Unexpected file in published bundle")
            manifest = json.loads(archive.read("manifest.json"))
            records_bytes = archive.read("history.jsonl")
            reader_bytes = archive.read("reader.html")
            if digest(records_bytes) != manifest["history_jsonl_sha256"] or digest(reader_bytes) != manifest["reader_html_sha256"]:
                raise RuntimeError("Bundle contents differ from their integrity manifest")
            records = [json.loads(line) for line in records_bytes.splitlines()]
            if [r["id"] for r in records] != bundle["session_ids"] or sum(len(r["messages"]) for r in records) != bundle["messages"]:
                raise RuntimeError("Bundle record counts differ from the profile manifest")
            for record in records:
                sid = record["id"]
                if sid not in rows:
                    raise RuntimeError("Bundle includes a session absent from the original index")
                prior = seen.setdefault(sid, [])
                segment = record.get("archive_segment")
                if segment and segment["message_offset"] != len(prior):
                    raise RuntimeError("Conversation segments have a gap or overlap")
                prior.extend(m["id"] for m in record["messages"])
                locations.setdefault(sid, []).append(number)
            if "reader" in bundle:
                reader = bundle["reader"]
                standalone = (folder / reader["filename"]).read_bytes()
                if digest(standalone) != reader["sha256"] or standalone != reader_bytes:
                    raise RuntimeError("Standalone reader differs from the bundled reader")
    if set(seen) != set(rows):
        raise RuntimeError("Missing archived sessions")
    for sid, row in rows.items():
        ids = seen[sid]
        if len(ids) != row["messages"] or len(set(ids)) != len(ids) or locations[sid] != row.get("bundles", [row["bundle"]]):
            raise RuntimeError("Session identities, counts, or part locations do not reconcile")
    if sum(len(ids) for ids in seen.values()) != profile["messages"]:
        raise RuntimeError("Profile message total does not reconcile")


def verify_no_execution(issue: dict) -> dict:
    if issue.get("companyId") != COMPANY or issue.get("visibility") != "private" or issue.get("assigneeAgentId") or issue.get("assigneeUserId"):
        raise RuntimeError("Archive is not private and unassigned in the expected company")
    if issue.get("executionRunId") or issue.get("checkoutRunId"):
        raise RuntimeError("Archive unexpectedly acquired an execution owner")
    diagnostic = api(f"/issues/{issue['id']}/diagnostics/wakes")
    if diagnostic.get("wakeRequestCount") != 0 or diagnostic.get("truncatedWakeRequests") or diagnostic.get("truncated"):
        raise RuntimeError("Archive wake history is nonzero or incomplete; reconcile before proceeding")
    return {"wakeRequestCount": 0, "executionRunId": issue.get("executionRunId"), "checkoutRunId": issue.get("checkoutRunId")}


def stamp(value) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return str(value or "unknown")


def label(value) -> str:
    text = " ".join(str(value).split())[:160]
    return re.sub(r"([\\`*_{}\[\]()<>|!])", r"\\\1", text)


def ensure_issue(receipts: Path) -> dict:
    issued = receipts / "issue.json"
    if issued.exists():
        issue = api("/issues/" + json.loads(issued.read_text())["id"])
    else:
        prior = [i for i in api(f"/companies/{COMPANY}/issues") if f"[{MARKER}]" in (i.get("description") or "")]
        if len(prior) > 1:
            raise RuntimeError("Multiple archive identities require reconciliation")
        if prior:
            issue = prior[0]
        else:
            intent = receipts / "issue.pending.json"
            if intent.exists():
                raise RuntimeError("Unreconciled issue creation; no retry attempted")
            body = {"title": TITLE, "status": "backlog", "visibility": "private", "assigneeAgentId": None,
                    "idempotencyKey": MARKER,
                    "description": f"[{MARKER}]\n\nPrivate archive of the existing Hermes conversations. The profile documents link to searchable readers and complete redacted records. Each profile has its own snapshot time. Original history, OMH memory, specialized skills and learning remain with the existing bots. This archive does not replay messages or start agents."}
            save_json(intent, body)
            issue = api(f"/companies/{COMPANY}/issues", "POST", body)
        save_json(issued, {k: issue[k] for k in ("id", "identifier", "companyId")})
    if issue.get("companyId") != COMPANY or issue.get("visibility") != "private" or issue.get("assigneeAgentId") or issue.get("assigneeUserId"):
        raise RuntimeError("Archive is not private and unassigned in the expected company")
    return issue


def attachment(issue: dict, folder: Path, record: dict, receipts: Path) -> dict:
    filename = record["filename"]
    if not re.fullmatch(r"hermes-[a-z0-9.-]+\.(zip|html)", filename):
        raise RuntimeError("Unexpected artifact name")
    payload = (folder / filename).read_bytes()
    if digest(payload) != record["sha256"] or len(payload) != record["bytes"] or len(payload) > MAX_UPLOAD:
        raise RuntimeError("Archive integrity/size changed before publication")
    existing = [a for a in api(f"/issues/{issue['id']}/attachments") if a.get("originalFilename") == filename]
    if len(existing) > 1 or any(a.get("sha256") != record["sha256"] for a in existing):
        raise RuntimeError("Attachment name conflicts with a different or duplicated native object")
    if existing:
        saved = existing[0]
    else:
        intent = receipts / (filename + ".pending.json")
        if intent.exists():
            raise RuntimeError("Unreconciled attachment upload; no retry attempted")
        save_json(intent, {"issueId": issue["id"], "filename": filename, "sha256": record["sha256"]})
        boundary = "paperclip-history-" + uuid.uuid4().hex
        mime = "application/zip" if filename.endswith(".zip") else "text/html"
        multipart = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode() + payload + f"\r\n--{boundary}--\r\n".encode())
        saved = api(f"/companies/{COMPANY}/issues/{issue['id']}/attachments", "POST", multipart, f"multipart/form-data; boundary={boundary}")
    content_path = saved.get("contentPath") or f"/api/attachments/{saved['id']}/content"
    if not content_path.startswith("/api/attachments/"):
        raise RuntimeError("Unexpected attachment origin")
    readback = api(content_path[4:])
    if not isinstance(readback, bytes) or digest(readback) != record["sha256"]:
        raise RuntimeError("Published attachment failed byte-for-byte readback")
    receipt = {"id": saved["id"], "filename": filename, "sha256": record["sha256"], "contentPath": content_path}
    receipt_path = receipts / (filename + ".verified.json")
    if not receipt_path.exists():
        save_json(receipt_path, receipt)
    return receipt


def document(issue_id: str, key: str, title: str, body: str, receipts: Path) -> dict:
    if len(body) > 500000:
        raise RuntimeError("Archive index exceeds the native document limit")
    path = f"/issues/{issue_id}/documents/{key}"
    try:
        current = api(path)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        current = None
    if current:
        if current.get("body") != body:
            raise RuntimeError("Existing archive document has different content; preserve it")
    else:
        pending = receipts / (key + ".pending.json")
        if pending.exists():
            raise RuntimeError("Unreconciled document publication; no retry attempted")
        save_json(pending, {"issueId": issue_id, "key": key, "body_sha256": digest(body.encode())})
        api(path, "PUT", {"title": title, "format": "markdown", "body": body, "baseRevisionId": None,
                           "changeSummary": "Imported original Hermes history snapshot; no messages replayed"})
        current = api(path)
    if current.get("body") != body:
        raise RuntimeError("Document content differs on readback")
    result = {"key": key, "revision": current.get("latestRevisionId"), "body_sha256": digest(body.encode())}
    receipt = receipts / (key + ".verified.json")
    if not receipt.exists():
        save_json(receipt, result)
    return result


def publish(output: Path) -> None:
    health = api("/health")
    if health.get("version") != PAPERCLIP_VERSION or health.get("deploymentMode") != "local_trusted" or health.get("status") != "ok":
        raise RuntimeError("Paperclip instance changed; requalify the native API")
    profiles = []
    for name in ("legacy-default", *PROFILE_NAMES):
        folder = output / name
        result = json.loads((folder / "profile.json").read_text())
        if result["profile"] != name or len(result["index"]) != result["sessions"] or sum(x["messages"] for x in result["index"]) != result["messages"]:
            raise RuntimeError("Profile manifest is incomplete")
        verify_profile(folder, result)
        profiles.append(result)
    receipts = output / "publication"
    private_directory(receipts)
    issue = ensure_issue(receipts)
    baseline = verify_no_execution(issue)
    if not (receipts / "execution-baseline.json").exists():
        save_json(receipts / "execution-baseline.json", baseline)
    print(json.dumps({"issue": issue["identifier"], "id": issue["id"], "visibility": issue["visibility"]}), flush=True)
    documents, attachments = [], []
    for profile in profiles:
        name = profile["profile"]
        folder = output / name
        parts = {}
        for number, bundle in enumerate(profile["bundles"], 1):
            saved = attachment(issue, folder, bundle, receipts)
            reader = attachment(issue, folder, bundle["reader"], receipts) if "reader" in bundle else None
            attachments.append(saved)
            if reader:
                attachments.append(reader)
            parts[number] = (saved, reader)
        header = [f"# {label(name)} conversations", "", f"**{profile['sessions']:,} sessions · {profile['messages']:,} stored messages**", "",
                  f"Snapshot: {profile['snapshot_completed_at']}. Live messages after this boundary remain in the bot's original Hermes history.", "",
                  "Download a reader to browse its conversations. The corresponding ZIP includes the same reader, the full redacted JSONL records, and an integrity manifest. Stored inactive and compacted messages are retained. Referenced media remains at its original location; media bytes are not implicitly included.", "", "## Archive parts", ""]
        for number, (saved, reader) in parts.items():
            links = f"[Complete records]({saved['contentPath']})"
            if reader:
                links = f"[Download reader]({reader['contentPath']}?download=1) · " + links
            header.append(f"- Part {number:03d}: {links}")
        header += ["", "## Conversations", "", "| Started | Conversation | Messages | Part |", "|---|---|---:|---:|"]
        index = profile["index"]
        for offset in range(0, max(1, len(index)), 500):
            rows = [f"| {stamp(row.get('started_at'))} | {label(row['title'])} | {row['messages']} | {', '.join(f'{n:03d}' for n in row.get('bundles',[row['bundle']]))} |" for row in index[offset:offset + 500]]
            key = f"history-{name}-{offset // 500 + 1:02d}"
            documents.append(document(issue["id"], key, f"{name} · conversations {offset + 1}–{min(offset + 500,len(index))}", "\n".join(header + rows) + "\n", receipts))
        print(json.dumps({"profile": name, "sessions": profile["sessions"], "messages": profile["messages"], "published_and_read_back": True}), flush=True)
    final_issue = api("/issues/" + issue["id"])
    final_execution = verify_no_execution(final_issue)
    native_attachments = api(f"/issues/{issue['id']}/attachments")
    if not {a["id"] for a in attachments}.issubset({a["id"] for a in native_attachments}):
        raise RuntimeError("Published attachment is missing from final native index")
    native_documents = api(f"/issues/{issue['id']}/documents")
    if not {d["key"] for d in documents}.issubset({d["key"] for d in native_documents}):
        raise RuntimeError("Published document is missing from final native index")
    completion = {"issueId": issue["id"], "identifier": issue["identifier"], "visibility": "private", "profiles": len(profiles),
                  "sessions": sum(x["sessions"] for x in profiles), "messages": sum(x["messages"] for x in profiles), "documents": documents,
                  "attachments": len(attachments), "execution": final_execution,
                  "source_opened_read_only": True, "continuous_sync": False, "native_chat_import": False}
    final = receipts / "verified-publication.json"
    if not final.exists():
        save_json(final, completion)
    print(json.dumps(completion), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    publish(parser.parse_args().output)

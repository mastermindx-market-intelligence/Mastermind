"""Preserve referenced native assets from the accepted history snapshots.

One passive supplement to the existing private archive. No live DB, model,
admission, cleanup, remote fetch, scheduler or credential owner is invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import zipfile

from paperclip_history import MAX_UPLOAD, PROFILE_NAMES, digest, now, private_directory, save_json, save_new, scrub

ROOTS = (
    "cache/documents", "cache/images", "cache/audio", "cache/videos",
    "cache/screenshots", "cache/generated", "cache/spillover", "cache/web",
    "cache/delegation", "document_cache", "image_cache", "audio_cache",
    "video_cache", "browser_screenshots", "images", "attachments",
    "composer-pastes", "web_cache", "delegation_cache", "downloads/connectors",
)
LAYOUT_PAIRS = (
    ("cache/documents", "document_cache"), ("cache/images", "image_cache"),
    ("cache/audio", "audio_cache"), ("cache/videos", "video_cache"),
    ("cache/screenshots", "browser_screenshots"), ("cache/web", "web_cache"),
    ("cache/delegation", "delegation_cache"),
)
CHUNK = 6 * 1024 * 1024
MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_ASSETS = 20000
MAX_DEPTH = 32
MAX_SPILL_DEPTH = 3


def safe_relative(value: str) -> bool:
    return (isinstance(value, str) and len(value) < 4096
            and not any(c in value for c in ("\x00", "\\", "\n", "\r"))
            and not re.search(r"%(?:2e|2f|5c)", value, re.I)
            and all(p not in ("", ".", "..") and len(p.encode()) <= 255 for p in value.split("/"))
            and any(value.startswith(root + "/") for root in ROOTS))


def map_reference(value: str, source_profile: str, homes: dict) -> dict:
    """Explicit host paths retain their actual owner; aliases stay source-scoped."""
    if not isinstance(value, str):
        return {"status": "unsupported_reference"}
    if value.startswith("data:image/"):
        return {"status": "inline"}
    if value.startswith(("http://", "https://")):
        return {"status": "external_not_fetched"}
    for owner, home in sorted(homes.items(), key=lambda x: len(str(x[1])), reverse=True):
        prefix = str(home) + "/"
        if value.startswith(prefix):
            rel = value[len(prefix):]
            if not safe_relative(rel):
                return {"status": "unsafe_or_outside_root"}
            return {"owner": owner, "candidates": [rel], "mapping": "explicit_host"}
    for prefix in ("/root/.hermes/", "~/.hermes/"):
        if value.startswith(prefix):
            rel = value[len(prefix):]
            if not safe_relative(rel):
                return {"status": "unsafe_or_outside_root"}
            candidates = [rel]
            for new, old in LAYOUT_PAIRS:
                for left, right in ((new, old), (old, new)):
                    if rel.startswith(left + "/"):
                        candidates.append(right + rel[len(left):])
            return {"owner": source_profile, "candidates": candidates, "mapping": "native_alias"}
    return {"status": "unsupported_alias"}


def stable_read(home: Path, relative: str, limit=MAX_FILE) -> tuple[bytes, dict]:
    """Open every component without links; compare the same file descriptor."""
    if not safe_relative(relative):
        raise ValueError("unsafe_or_outside_root")
    descriptors = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(home, directory_flags)
        descriptors.append(fd)
        parts = relative.split("/")
        for part in parts[:-1]:
            fd = os.open(part, directory_flags, dir_fd=fd)
            descriptors.append(fd)
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("nonregular")
        if before.st_nlink != 1:
            raise ValueError("unsafe_hardlink")
        if before.st_size > limit:
            raise ValueError("limit_exceeded")
        chunks, size = [], 0
        while chunk := os.read(file_fd, min(1024 * 1024, limit + 1 - size)):
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise ValueError("limit_exceeded")
        after = os.fstat(file_fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        if any(getattr(before, f) != getattr(after, f) for f in fields) or size != after.st_size:
            raise ValueError("changed_during_read")
        return b"".join(chunks), {f: getattr(after, f) for f in fields}
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


class Collector:
    def __init__(self, homes, decode, spill_names, persisted_path):
        self.homes, self.decode = homes, decode
        self.spill_names, self.persisted_path = spill_names, persisted_path
        self.records, self.observations = {}, Counter()
        prefixes = [re.escape(str(h)) for h in homes.values()]
        prefixes += [r"/root/\.hermes", r"~/\.hermes"]
        roots = "|".join(re.escape(r) for r in ROOTS)
        self.paths = re.compile(r"(?<![A-Za-z0-9_./\\:%-])(?:" + "|".join(prefixes) + r")/(?:" + roots + r")/[^\s\"'<>\x00\x60\\)\]}]+")

    def add(self, value, origin, expected=None, expansion=0):
        scope = origin.get("asset_scope_profile", origin["profile"])
        mapped = map_reference(value, scope, self.homes)
        if mapped.get("status") == "inline":
            return
        identity = json.dumps([mapped, value if "status" in mapped else None], sort_keys=True)
        aid = digest(identity.encode())[:24]
        if aid not in self.records and len(self.records) >= MAX_ASSETS:
            raise RuntimeError("Asset reference limit exceeded; no complete census claimed")
        record = self.records.setdefault(aid, {"asset_id": aid, **mapped, "origins": [], "expected": [], "expansion": expansion})
        if origin not in record["origins"]:
            record["origins"].append(origin)
        if expected and expected not in record["expected"]:
            record["expected"].append(expected)
        record["expansion"] = min(expansion, record["expansion"])

    def scan(self, value, origin, depth=0, expansion=0):
        if depth > MAX_DEPTH:
            self.observations["reference_depth_limit"] += 1
            return
        if isinstance(value, dict):
            expected = None
            if isinstance(value.get("path"), str) and "sha256" in value:
                sha, size = value.get("sha256"), value.get("size")
                if isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{64}", sha) and type(size) is int and size >= 0:
                    expected = {"sha256": sha, "size": size}
                else:
                    self.observations["malformed_native_reference"] += 1
            for key, item in value.items():
                child = dict(origin, field=origin["field"] + "/" + str(key))
                if isinstance(item, str) and (
                    key in ("image", "host_image", "agent_visible_image", "image_url")
                    or (key == "path" and (".hermes/" in item or expected or self.paths.match(item)))
                ):
                    self.add(item, child, expected if key == "path" else None, expansion)
                    if item.startswith("data:image/"):
                        self.observations["inline"] += 1
                    continue
                self.scan(item, child, depth + 1, expansion)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self.scan(item, dict(origin, field=origin["field"] + "/" + str(index)), depth + 1, expansion)
        elif isinstance(value, str):
            if value.startswith("data:image/"):
                self.observations["inline"] += 1
                return
            if value.lstrip().startswith(("{", "[")):
                try:
                    parsed, end = json.JSONDecoder().raw_decode(value.lstrip())
                except (ValueError, RecursionError):
                    pass
                else:
                    self.scan(parsed, dict(origin, field=origin["field"] + "/json"), depth + 1, expansion)
                    remainder = value.lstrip()[end:]
                    if remainder.strip():
                        self.scan(remainder, dict(origin, field=origin["field"] + "/trailing"), depth + 1, expansion)
                    return
            remaining = value
            if origin.get("hosted_admission"):
                for match in re.finditer(r"(?:^|\n)\[Shared attachment\] file: ([^\n]+)", value):
                    path = match.group(1).strip()
                    self.add(path, origin, expansion=expansion)
                    remaining = remaining.replace(path, "")
            pointer = self.persisted_path(value)
            if pointer:
                remaining = remaining.replace(pointer, "")
            # A URL that happens to contain a host-looking substring is never
            # evidence for opening that local path.
            remaining = re.sub(r"(?:https?|file)://[^\s<>\"']+", "", remaining)
            for match in self.paths.finditer(remaining):
                self.add(match.group().rstrip(".,;:"), origin, expansion=expansion)
            scope = origin.get("asset_scope_profile", origin["profile"])
            for name in self.spill_names(remaining):
                # Absolute known paths were already mapped to their actual owner.
                # A basename in an unknown absolute path cannot establish ownership.
                relative_pointer = r"(?<![A-Za-z0-9_./\\-])(?:cache/)?spillover/" + re.escape(name) + r"(?![A-Za-z0-9_.-])"
                if (re.fullmatch(r"[A-Za-z0-9_.-]+", name) and name not in (".", "..")
                        and re.search(relative_pointer, remaining)):
                    self.add(str(self.homes[scope] / "cache/spillover" / name), origin, expansion=expansion)
            if pointer:
                if "/hermes-results/" in pointer:
                    name = pointer.rsplit("/", 1)[-1]
                    if re.fullmatch(r"[A-Za-z0-9_.-]+", name) and name not in (".", ".."):
                        self.add(str(self.homes[scope] / "cache/spillover" / name), dict(origin, field=origin["field"] + "/native_spill_fallback"), expansion=expansion)
                else:
                    self.add(pointer, origin, expansion=expansion)
            self.observations["retained_tokens"] += len(re.findall(r"hermes-retained:[a-f0-9]{64}", value))

    def snapshot(self, folder, meta):
        accepted = {s["id"] for s in meta["index"]}
        path = folder / "snapshot.db"
        if path.is_symlink() or digest(path.read_bytes()) != meta["snapshot_sha256"]:
            raise RuntimeError("Accepted source snapshot changed")
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
            fields = ["id", "session_id", "content"] + (["api_content"] if "api_content" in columns else [])
            count = 0
            for row in db.execute("SELECT " + ",".join(fields) + " FROM messages ORDER BY id"):
                if row[1] not in accepted:
                    raise RuntimeError("Message outside the accepted session set")
                origin = {"profile": meta["profile"], "session_id": row[1], "message_id": row[0], "field": "content"}
                self.scan(self.decode(row[2]), origin)
                if len(row) > 3:
                    self.scan(row[3], dict(origin, field="api_content"))
                count += 1
            if count != meta["messages"]:
                raise RuntimeError("Accepted message count changed")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "session_admissions" in tables:
                for sid, aid, rid, status, payload in db.execute("SELECT target_session_id,admission_id,request_id,status,payload_json FROM session_admissions ORDER BY seq"):
                    if sid not in accepted:
                        continue
                    try:
                        decoded = json.loads(payload)
                    except (TypeError, ValueError):
                        self.observations["malformed_admission"] += 1
                        continue
                    origin = {"profile": meta["profile"], "session_id": sid, "admission_id": aid, "field": "payload_json", "admission_status": status, "hosted_admission": str(rid).startswith("hosted:")}
                    self.scan(decoded, origin)
                    api_turn = decoded.get("api_turn_v1") if isinstance(decoded, dict) else None
                    api_media = api_turn.get("media", []) if isinstance(api_turn, dict) else []
                    if not isinstance(api_media, list):
                        self.observations["malformed_native_reference"] += 1
                        api_media = []
                    known = {r.get("sha256") for r in api_media if isinstance(r, dict)}
                    tokens = set(re.findall(r"hermes-retained:([a-f0-9]{64})", payload))
                    self.observations["retained_without_reference"] += len(tokens - known)


def choose_bytes(record, homes):
    found, outcomes = [], []
    for relative in record["candidates"]:
        try:
            data, identity = stable_read(homes[record["owner"]], relative)
            found.append((relative, data, identity))
        except FileNotFoundError:
            outcomes.append("missing")
        except OSError as error:
            outcomes.append("unsafe_path" if error.errno in (20, 40, 62) else "unreadable")
        except ValueError as error:
            outcomes.append(str(error))
    if not found:
        return {"status": next((s for s in outcomes if s != "missing"), "missing")}
    expected = record["expected"]
    if expected:
        found = [item for item in found if all(digest(item[1]) == e["sha256"] and len(item[1]) == e["size"] for e in expected)]
        if not found:
            return {"status": "hash_or_size_mismatch"}
    if len({digest(item[1]) for item in found}) > 1:
        return {"status": "ambiguous_mapping"}
    relative, data, identity = found[0]
    return {"status": "captured", "relative": relative, "data": data, "source_identity": identity}


def projection(data, relative, redact):
    suffix = Path(relative).suffix.lower()
    binary = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".avif",
              ".mp4", ".mov", ".webm", ".mp3", ".wav", ".ogg", ".flac", ".m4a",
              ".zip", ".gz", ".bz2", ".xz", ".7z", ".tar", ".sqlite", ".db",
              ".docx", ".xlsx", ".pptx", ".woff", ".woff2", ".bin"}
    text_types = {".txt", ".log", ".md", ".json", ".jsonl", ".csv", ".tsv", ".html",
                  ".xml", ".svg", ".yaml", ".yml", ".sql", ".py", ".js", ".ts"}
    if suffix in binary:
        return data, False, None
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        text = data.decode(encoding)
    except UnicodeError:
        if suffix in text_types or relative.startswith(("cache/spillover/", "cache/delegation/", "delegation_cache/")):
            raise ValueError("private_only_undecodable_text") from None
        return data, False, None
    if "\x00" in text:
        raise ValueError("private_only_undecodable_text")
    return redact(text, force=True).encode(encoding), True, encoding


def capture(archive: Path, output: Path, source: Path, home: Path):
    private_directory(output)
    if (output / "capture.pending.json").exists():
        raise RuntimeError("Original capture exists; reconcile it instead of rerunning")
    profiles = {p.parent.name: json.loads(p.read_text()) for p in archive.glob("*/profile.json")}
    if set(profiles) != {"legacy-default", *PROFILE_NAMES}:
        raise RuntimeError("Expected the accepted fourteen-profile archive")
    homes = {name: home if name == "legacy-default" else home / "profiles" / name for name in profiles}
    if any(meta["profile"] != name or Path(meta["source_home"]) != homes[name] for name, meta in profiles.items()):
        raise RuntimeError("Accepted profile owner changed")
    save_json(output / "capture.pending.json", {"started_at": now(), "snapshots": {k: v["snapshot_sha256"] for k, v in profiles.items()}})
    sys.path.insert(0, str(source))
    import hermes_bootstrap  # noqa: F401 - reuse native dependency ownership
    from hermes_state import SessionDB
    from tools.tool_result_storage import spillover_names_in_text, extract_persisted_path
    from agent.redact import redact_sensitive_text
    collector = Collector(homes, SessionDB._decode_content, spillover_names_in_text, extract_persisted_path)
    for name, meta in profiles.items():
        collector.snapshot(archive / name, meta)
    for child in ("private", "projection", "bundles"):
        private_directory(output / child)
    completed, total = set(), 0
    while todo := [r for aid, r in collector.records.items() if aid not in completed]:
        for record in todo:
            completed.add(record["asset_id"])
            if "status" in record:
                continue
            result = choose_bytes(record, homes)
            data = result.pop("data", None)
            record.update(result)
            if data is None:
                continue
            total += len(data)
            if total > MAX_TOTAL:
                raise RuntimeError("Total asset limit exceeded; no complete capture claimed")
            raw_hash = digest(data)
            raw = output / "private" / raw_hash
            if not raw.exists():
                save_new(raw, data)
            elif digest(raw.read_bytes()) != raw_hash:
                raise RuntimeError("Private capture hash conflict")
            record.update({"raw_sha256": raw_hash, "bytes": len(data), "captured_at": now()})
            try:
                published, is_text, encoding = projection(data, record["relative"], redact_sensitive_text)
            except ValueError as error:
                record["status"] = str(error)
                continue
            public_hash = digest(published)
            projected = output / "projection" / public_hash
            if not projected.exists():
                save_new(projected, published)
            elif digest(projected.read_bytes()) != public_hash:
                raise RuntimeError("Projection hash conflict")
            record.update({"projection_sha256": public_hash, "projection_bytes": len(published), "text_redaction_applied": is_text, "text_encoding": encoding})
            if record["relative"].startswith("cache/spillover/") and is_text:
                if record["expansion"] < MAX_SPILL_DEPTH:
                    # Parent linkage retains all source occurrences without
                    # rescanning the same spill once for every referencing turn.
                    origin = record["origins"][0]
                    collector.scan(data.decode(encoding), dict(origin, field="spill/" + record["asset_id"], parent_asset_id=record["asset_id"], asset_scope_profile=record["owner"]), expansion=record["expansion"] + 1)
                else:
                    collector.observations["spill_expansion_limit"] += 1
    records = list(collector.records.values())
    for record in records:
        if record["status"] == "captured" and any(record["raw_sha256"] != e["sha256"] or record["bytes"] != e["size"] for e in record["expected"]):
            record["status"] = "hash_or_size_mismatch"
    raw_manifest = {"captured_at": now(), "source_snapshots": {k: v["snapshot_sha256"] for k, v in profiles.items()}, "records": records, "observations": dict(collector.observations), "total_captured_bytes": total}
    save_json(output / "private-manifest.json", raw_manifest)
    clean = scrub(raw_manifest, redact_sensitive_text)
    for record in clean["records"]:
        record.pop("source_identity", None)
    save_json(output / "manifest.json", clean)
    bundles = build_bundles(output, clean)
    unique_files = {(r["owner"], r["relative"]) for r in records if r["status"] == "captured"}
    save_json(output / "capture.finished.json", {"finished_at": now(), "manifest_sha256": digest((output / "manifest.json").read_bytes()), "counts": dict(Counter(r["status"] for r in records)), "unique_captured_files": len(unique_files), "bundles": bundles, "observations": clean["observations"], "profiles": list(profiles), "total_captured_bytes": total})


def build_bundles(output, manifest):
    bundles = []
    groups = {name: [] for name in manifest["source_snapshots"]}
    for record in manifest["records"]:
        groups[record.get("owner", record["origins"][0]["profile"])].append(record)
    for owner, records in sorted(groups.items()):
        entries = [("references.jsonl", b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode() for r in records))]
        seen = set()
        for r in records:
            if r["status"] != "captured" or r["projection_sha256"] in seen:
                continue
            sha = r["projection_sha256"]
            data = (output / "projection" / sha).read_bytes()
            if digest(data) != sha:
                raise RuntimeError("Projection changed before bundling")
            entries.append(("objects/" + sha, data))
            seen.add(sha)
        batches, batch, size = [], [], 0
        for name, data in entries:
            parts = max(1, (len(data) + CHUNK - 1) // CHUNK)
            for part in range(parts):
                chunk = data[part * CHUNK:(part + 1) * CHUNK]
                info = {"entry": name if parts == 1 else name + f".part-{part + 1:03d}", "original_entry": name, "part": part + 1, "parts": parts, "complete_sha256": digest(data), "part_sha256": digest(chunk), "bytes": len(chunk)}
                if batch and size + len(chunk) > CHUNK:
                    batches.append(batch)
                    batch, size = [], 0
                batch.append((info, chunk))
                size += len(chunk)
        if batch:
            batches.append(batch)
        for number, batch in enumerate(batches, 1):
            info = {"profile": owner, "entries": [i for i, _ in batch], "text_files_redacted": True, "binary_files_original_bytes": True}
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(info, indent=2))
                for entry, chunk in batch:
                    z.writestr(entry["entry"], chunk)
            payload = buf.getvalue()
            if len(payload) > MAX_UPLOAD:
                raise RuntimeError("Asset bundle exceeds native attachment limit")
            filename = f"hermes-assets-{owner}-{number:04d}.zip"
            save_new(output / "bundles" / filename, payload)
            bundles.append({"profile": owner, "filename": filename, "sha256": digest(payload), "bytes": len(payload), "entries": len(batch)})
    return bundles


def publish(archive, output):
    from paperclip_history import api, COMPANY, PAPERCLIP_VERSION
    from publish_history import attachment, document, verify_no_execution, label
    complete = json.loads((output / "capture.finished.json").read_text())
    if digest((output / "manifest.json").read_bytes()) != complete["manifest_sha256"]:
        raise RuntimeError("Capture manifest changed")
    health = api("/health")
    if health.get("version") != PAPERCLIP_VERSION or health.get("deploymentMode") != "local_trusted" or health.get("status") != "ok":
        raise RuntimeError("Native instance changed")
    original = json.loads((archive / "publication/verified-publication.json").read_text())
    issue = api("/issues/" + original["issueId"])
    if issue.get("companyId") != COMPANY or issue.get("identifier") != original["identifier"]:
        raise RuntimeError("Original archive identity changed")
    verify_no_execution(issue)
    receipts = output / "publication"
    private_directory(receipts)
    if (receipts / "verified-publication.json").exists():
        raise RuntimeError("Asset publication already completed; inspect its receipt")
    manifest = json.loads((output / "manifest.json").read_text())
    by_profile = {p: [] for p in complete["profiles"]}
    attachments, documents = [], []
    for bundle in complete["bundles"]:
        saved = attachment(issue, output / "bundles", bundle, receipts)
        attachments.append(saved)
        by_profile[bundle["profile"]].append((bundle, saved))
    for profile, parts in by_profile.items():
        records = [r for r in manifest["records"] if r.get("owner", r["origins"][0]["profile"]) == profile]
        counts = dict(Counter(r["status"] for r in records))
        header = [f"# {profile} referenced files", "", "Files preserved from references in the accepted conversation snapshots. Text files use the same secret-redaction pass as the conversation archive. Images and other binary files retain their original bytes. Missing references are recorded without guessing why the files are absent. No remote URLs were fetched.", "", "Counts: " + ", ".join(f"{k}: {v:,}" for k, v in sorted(counts.items())), "", "ZIP manifests map content hashes to files; references.jsonl maps those hashes to original names and conversations. Join numbered parts in order and verify the complete SHA256 when restoring a split object.", "", "## Downloads", ""]
        for number, (bundle, saved) in enumerate(parts, 1):
            header.append(f"- [File bundle {number:03d}]({saved['contentPath']}) ({bundle['entries']} entries)")
        header += ["", "## Referenced files", "", "| Original relative path | Outcome | Bytes |", "|---|---|---:|"]
        for offset in range(0, max(1, len(records)), 500):
            lines = [f"| {label(r.get('relative') or ', '.join(r.get('candidates', [])) or r['asset_id'])} | {r['status']} | {r.get('bytes', '')} |" for r in records[offset:offset + 500]]
            key = f"assets-{profile}-{offset // 500 + 1:02d}"
            documents.append(document(issue["id"], key, f"{profile} · referenced files", "\n".join(header + lines) + "\n", receipts))
    final = verify_no_execution(api("/issues/" + issue["id"]))
    save_json(receipts / "verified-publication.json", {"issueId": issue["id"], "identifier": issue["identifier"], "counts": complete["counts"], "attachments": attachments, "documents": documents, "execution": final, "manifest_sha256": complete["manifest_sha256"], "completed_at": now()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("capture", "publish"))
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--home", type=Path)
    args = p.parse_args()
    if args.action == "capture":
        if args.source is None or args.home is None:
            p.error("capture requires the inspected native --source and --home")
        capture(args.archive, args.output, args.source, args.home)
    else:
        publish(args.archive, args.output)


if __name__ == "__main__":
    main()

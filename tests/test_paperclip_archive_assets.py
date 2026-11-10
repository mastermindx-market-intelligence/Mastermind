"""Snapshot and file boundaries for the passive Paperclip asset supplement."""
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/paperclip_fleet"))
import archive_assets as assets


def decode(raw):
    return json.loads(raw[6:]) if isinstance(raw, str) and raw.startswith("\x00json:") else raw


def collector(homes):
    return assets.Collector(homes, decode,
        lambda s: set(re.findall(r"spillover/([A-Za-z0-9_.-]+)", s)),
        lambda s: s.partition("Full output saved to: ")[2].splitlines()[0] if "Full output saved to: " in s else None)


def origin(profile="a"):
    return {"profile": profile, "session_id": "s", "message_id": 1, "field": "content"}


def put(home, relative, data):
    p = home / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_snapshot_decodes_nul_and_retains_sidecar_and_inactive_rows(tmp_path):
    home = tmp_path / "home"
    folder = tmp_path / "archive"
    folder.mkdir()
    dbpath = folder / "snapshot.db"
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE messages(id INTEGER, session_id TEXT, content TEXT, api_content TEXT, active INTEGER, compacted INTEGER)")
        db.executemany("INSERT INTO messages VALUES(?,?,?,?,?,?)", [
            (1, "s", "\x00json:" + json.dumps([{"image_url": {"url": str(home / "cache/images/a.png")}}]), None, 1, 0),
            (2, "s", "inactive", str(home / "cache/spillover/b.txt"), 0, 1),
            (3, "s", "\\u0000json:literal", str(home / "cache/spillover/c.txt"), 0, 0),
        ])
    c = collector({"a": home})
    before = assets.digest(dbpath.read_bytes())
    c.snapshot(folder, {"profile": "a", "index": [{"id": "s"}], "messages": 3, "snapshot_sha256": before})
    assert {r["candidates"][0] for r in c.records.values()} == {"cache/images/a.png", "cache/spillover/b.txt", "cache/spillover/c.txt"}
    assert assets.digest(dbpath.read_bytes()) == before
    assert any(o["message_id"] == 2 for r in c.records.values() for o in r["origins"])


def test_all_admission_media_forms_and_hosted_paths_are_scanned(tmp_path):
    home = tmp_path / "home"
    folder = tmp_path / "archive"
    folder.mkdir()
    dbpath = folder / "snapshot.db"
    media = {"path": str(home / "cache/documents/native-inputs" / ("a" * 64) / "doc.pdf"), "sha256": "a" * 64, "size": 4}
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE messages(id INTEGER,session_id TEXT,content TEXT,api_content TEXT)")
        db.execute("CREATE TABLE session_admissions(seq INTEGER,target_session_id TEXT,admission_id TEXT,request_id TEXT,status TEXT,payload_json TEXT)")
        for n, key in enumerate(("attachments_v1", "native_text_v1", "api_turn_v1")):
            payload = {key: {"media": [media]}, "text": "hermes-retained:" + "a" * 64 if key == "api_turn_v1" else ""}
            db.execute("INSERT INTO session_admissions VALUES(?,?,?,?,?,?)", (n, "s", str(n), "api:test", "terminal", json.dumps(payload)))
        db.execute("INSERT INTO session_admissions VALUES(?,?,?,?,?,?)", (4, "s", "4", "hosted:test", "terminal",
            json.dumps({"message": "\n[Shared attachment] file: " + str(home / "cache/documents/native-inputs" / ("b" * 64) / "two words.pdf") + "\n"})))
    c = collector({"a": home})
    c.snapshot(folder, {"profile": "a", "index": [{"id": "s"}], "messages": 0, "snapshot_sha256": assets.digest(dbpath.read_bytes())})
    refs = list(c.records.values())
    assert any(r["expected"] == [{"sha256": "a" * 64, "size": 4}] for r in refs)
    assert any(r["candidates"][0].endswith("two words.pdf") for r in refs)
    assert {o["admission_id"] for r in refs for o in r["origins"]} == {"0", "1", "2", "4"}
    assert c.observations["retained_without_reference"] == 0


def test_aliases_are_scoped_and_explicit_cross_profile_paths_keep_actual_owner(tmp_path):
    homes = {"legacy": tmp_path / "home", "a": tmp_path / "home/profiles/a", "b": tmp_path / "home/profiles/b"}
    assert assets.map_reference("/root/.hermes/cache/images/x", "a", homes)["owner"] == "a"
    assert assets.map_reference("~/.hermes/cache/images/x", "b", homes)["owner"] == "b"
    assert assets.map_reference(str(homes["b"] / "cache/images/x"), "a", homes)["owner"] == "b"
    assert assets.map_reference("/home/unknown/.hermes/cache/images/x", "a", homes)["status"] == "unsupported_alias"
    assert assets.map_reference(str(homes["a"] / "auth.json"), "a", homes)["status"] == "unsafe_or_outside_root"


def test_legacy_ambiguity_requires_matching_digest(tmp_path):
    put(tmp_path, "cache/images/x", b"new")
    put(tmp_path, "image_cache/x", b"old")
    record = {**assets.map_reference("/root/.hermes/cache/images/x", "a", {"a": tmp_path}), "expected": []}
    assert assets.choose_bytes(record, {"a": tmp_path})["status"] == "ambiguous_mapping"
    record["expected"] = [{"sha256": assets.digest(b"old"), "size": 3}]
    assert assets.choose_bytes(record, {"a": tmp_path})["data"] == b"old"
    record["expected"] = [{"sha256": "0" * 64, "size": 3}]
    assert assets.choose_bytes(record, {"a": tmp_path})["status"] == "hash_or_size_mismatch"


@pytest.mark.parametrize("relative", [
    "../secret", "cache/images/../../secret", "cache/images/%2e%2e/secret",
    "cache/images/a\x00b", "cache/images/a\\b", "cache/images/./file",
    "cache/images/" + "a" * 256,
])
def test_traversal_and_malformed_paths_are_rejected(relative, tmp_path):
    with pytest.raises(ValueError, match="unsafe_or_outside_root"):
        assets.stable_read(tmp_path, relative)


def test_symlink_and_special_file_cannot_be_captured(tmp_path):
    target = put(tmp_path, "cache/images/good", b"inside")
    (target.parent / "link").symlink_to(target)
    with pytest.raises(OSError):
        assets.stable_read(tmp_path, "cache/images/link")
    (tmp_path / "cache/other").symlink_to(target.parent, target_is_directory=True)
    (tmp_path / "cache/images/dirlink").symlink_to(target.parent, target_is_directory=True)
    with pytest.raises(OSError):
        assets.stable_read(tmp_path, "cache/images/dirlink/good")
    os.mkfifo(target.parent / "pipe")
    with pytest.raises(ValueError, match="nonregular"):
        assets.stable_read(tmp_path, "cache/images/pipe")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside boundary")
    os.link(outside, target.parent / "hardlink")
    with pytest.raises(ValueError, match="unsafe_hardlink"):
        assets.stable_read(tmp_path, "cache/images/hardlink")


def test_change_during_read_is_refused(tmp_path, monkeypatch):
    put(tmp_path, "cache/spillover/a.txt", b"before")
    original = os.fstat
    calls = 0
    def changed(fd):
        nonlocal calls
        value = original(fd)
        calls += 1
        if calls == 2:
            data = {k: getattr(value, k) for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")}
            data["st_mtime_ns"] += 1
            return SimpleNamespace(**data)
        return value
    monkeypatch.setattr(os, "fstat", changed)
    with pytest.raises(ValueError, match="changed_during_read"):
        assets.stable_read(tmp_path, "cache/spillover/a.txt")


def test_spill_fallback_is_only_resolved_inside_the_owning_profile(tmp_path):
    c = collector({"a": tmp_path})
    c.scan("Full output saved to: /untrusted/remote/hermes-results/call_123.txt", origin())
    r = next(iter(c.records.values()))
    assert r["candidates"] == ["cache/spillover/call_123.txt"]
    assert r["owner"] == "a"
    assert assets.choose_bytes(r, {"a": tmp_path})["status"] == "missing"
    c.scan("data:image/png;base64,aW1hZ2U=", origin())
    assert c.observations["inline"] == 1


def test_projection_redacts_text_and_preserves_binary():
    def redact(value, *, force):
        assert force
        return value.replace("synthetic-private-token", "[redacted]")
    text, applied, encoding = assets.projection(b"synthetic-private-token", "cache/spillover/a.txt", redact)
    assert applied and b"synthetic-private-token" not in text
    binary, applied, encoding = assets.projection(b"\x89PNG\x00\xff", "cache/images/a.png", redact)
    assert not applied and binary == b"\x89PNG\x00\xff"
    ascii_pdf = b"%PDF-1.4\nsynthetic-private-token"
    assert assets.projection(ascii_pdf, "cache/documents/a.pdf", redact) == (ascii_pdf, False, None)
    utf16 = "synthetic-private-token".encode("utf-16")
    projected, applied, encoding = assets.projection(utf16, "cache/spillover/a.txt", redact)
    assert applied and "synthetic-private-token" not in projected.decode(encoding)
    with pytest.raises(ValueError, match="private_only_undecodable_text"):
        assets.projection(b"\xffinvalid", "cache/delegation/a.log", redact)


def test_explicit_spill_owner_and_nested_alias_never_copy_the_callers_namesake(tmp_path):
    homes = {"a": tmp_path / "a", "b": tmp_path / "b"}
    c = collector(homes)
    c.scan(str(homes["b"] / "cache/spillover/x.txt"), origin("a"))
    assert len(c.records) == 1
    r = next(iter(c.records.values()))
    assert r["owner"] == "b"
    c.scan("/root/.hermes/cache/images/result.png", dict(origin("a"), asset_scope_profile=r["owner"]))
    images = [r for r in c.records.values() if r["candidates"][0].endswith("result.png")]
    assert len(images) == 1 and images[0]["owner"] == "b"
    assert images[0]["origins"][0]["profile"] == "a"


def test_structured_path_with_spaces_does_not_create_a_truncated_reference(tmp_path):
    c = collector({"a": tmp_path})
    c.scan({"path": str(tmp_path / "cache/images/two words.png")}, origin())
    assert len(c.records) == 1
    assert next(iter(c.records.values()))["candidates"] == ["cache/images/two words.png"]
    c = collector({"a": tmp_path})
    c.scan(json.dumps({"image": str(tmp_path / "cache/images/two words.png")}), origin())
    assert len(c.records) == 1
    assert next(iter(c.records.values()))["candidates"] == ["cache/images/two words.png"]


def test_url_and_unknown_prefix_cannot_be_mistaken_for_a_local_native_path(tmp_path):
    c = collector({"a": tmp_path})
    path = str(tmp_path / "cache/images/secret.png")
    c.scan("See https://example.invalid/?path=" + path, origin())
    c.scan("file://" + path, origin())
    c.scan("/unknown/prefix" + path, origin())
    assert not c.records


def test_bundle_parts_reassemble_with_safe_names_and_exact_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "CHUNK", 64)
    (tmp_path / "projection").mkdir()
    (tmp_path / "bundles").mkdir()
    data = b"available object " * 20
    sha = assets.digest(data)
    (tmp_path / "projection" / sha).write_bytes(data)
    manifest = {"source_snapshots": {"a": "snapshot"}, "records": [{
        "owner": "a", "origins": [origin()], "status": "captured", "projection_sha256": sha,
        "relative": "cache/images/../../untrusted-name-in-fixture",
    }]}
    bundles = assets.build_bundles(tmp_path, manifest)
    pieces = {}
    for bundle in bundles:
        payload = (tmp_path / "bundles" / bundle["filename"]).read_bytes()
        assert assets.digest(payload) == bundle["sha256"]
        with zipfile.ZipFile(io_bytes(payload)) as z:
            assert all(not n.startswith("/") and ".." not in n.split("/") for n in z.namelist())
            info = json.loads(z.read("manifest.json"))
            for entry in info["entries"]:
                raw = z.read(entry["entry"])
                assert assets.digest(raw) == entry["part_sha256"]
                if entry["original_entry"] == "objects/" + sha:
                    pieces[entry["part"]] = raw
    assert b"".join(pieces[k] for k in sorted(pieces)) == data


def io_bytes(value):
    import io
    return io.BytesIO(value)

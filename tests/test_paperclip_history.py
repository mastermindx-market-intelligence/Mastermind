import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("paperclip_history", Path(__file__).resolve().parents[1] / "ops/paperclip_fleet/paperclip_history.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HistoryContracts(unittest.TestCase):
    def source(self, path):
        db = sqlite3.connect(path)
        db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE sessions(id TEXT PRIMARY KEY, started_at REAL);
          CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, timestamp REAL, active INT, compacted INT);
          INSERT INTO sessions VALUES ('old', 1);
          INSERT INTO messages VALUES (1,'old',1,1,0),(2,'old',2,0,1);
        """)
        return db

    def test_online_snapshot_keeps_wal_and_does_not_follow_later_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = self.source(root / "source.db")
            result = m.snapshot(root / "source.db", root / "snapshot.db")
            live.execute("INSERT INTO messages VALUES (3,'old',3,1,0)")
            live.commit()
            with sqlite3.connect(root / "snapshot.db") as snapshot:
                self.assertEqual(snapshot.execute("SELECT count(*) FROM messages").fetchone()[0], 2)
            self.assertEqual(result["messages"], 2)
            self.assertEqual(live.execute("SELECT count(*) FROM messages").fetchone()[0], 3)
            live.close()

    def test_export_must_preserve_inactive_message_and_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            db = self.source(Path(directory) / "source.db")
            valid = {"id": "old", "messages": [{"id": 1, "active": 1, "compacted": 0}, {"id": 2, "active": 0, "compacted": 1}]}
            m.verify_export(db, valid)
            with self.assertRaisesRegex(RuntimeError, "omitted"):
                m.verify_export(db, {"id": "old", "messages": valid["messages"][:1]})
            valid["messages"][1]["active"] = 1
            with self.assertRaisesRegex(RuntimeError, "active flags"):
                m.verify_export(db, valid)
            db.close()

    def test_native_scrubber_also_covers_title_and_nested_metadata(self):
        def redact(text, force=False):
            self.assertTrue(force)
            return text.replace("private-value", "[REDACTED]")
        original = {"title": "private-value", "metadata": {"url": "private-value"}, "messages": [{"content": "private-value"}]}
        cleaned = m.scrub(original, redact)
        self.assertNotIn("private-value", json.dumps(cleaned))
        self.assertEqual(original["title"], "private-value")

    def test_published_bundle_contains_only_redacted_exports_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "snapshot.db").write_bytes(b"private native database")
            records = [{"id": "same-id", "messages": [{"id": 1, "active": 0, "compacted": 1}]}]
            bundle = m.write_bundle(root, "product", 1, records, lambda records: "<html>reader</html>")
            with zipfile.ZipFile(root / bundle["filename"]) as archive:
                self.assertEqual(set(archive.namelist()), {"manifest.json", "history.jsonl", "reader.html"})
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(m.digest(archive.read("history.jsonl")), manifest["history_jsonl_sha256"])
            with self.assertRaises(FileExistsError):
                m.write_bundle(root, "product", 1, records, lambda records: "<html>reader</html>")

    def test_long_conversation_segments_preserve_all_messages_and_original_title(self):
        messages = [{"id": n, "content": "x" * 150, "active": n % 2} for n in range(17)]
        record = {"id": "same-session", "title": "Original title", "messages": messages}
        parts = list(m.split_record(record, target_bytes=600))
        self.assertGreater(len(parts), 1)
        self.assertEqual([message for part in parts for message in part["messages"]], messages)
        self.assertEqual([part["archive_segment"]["message_offset"] for part in parts], list(range(0,17,2)))
        self.assertTrue(all(part["title"] == "Original title" for part in parts))

    def test_resume_preserves_original_snapshot_and_unpublished_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = self.source(root / "source.db")
            expected = m.snapshot(root / "source.db", root / "snapshot.db")
            m.save_json(root / "snapshot.json", expected)
            partial = root / "hermes-marketing-001.zip"
            partial.write_bytes(b"original partial artifact")
            recovered = m.resume_snapshot(root)
            self.assertEqual(recovered, expected)
            self.assertEqual(m.digest((root / "snapshot.db").read_bytes()), expected["snapshot_sha256"])
            self.assertEqual((root / "interrupted-export-v1" / partial.name).read_bytes(), b"original partial artifact")
            live.close()


if __name__ == "__main__":
    unittest.main()

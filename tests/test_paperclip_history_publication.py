import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "ops/paperclip_fleet"
spec = importlib.util.spec_from_file_location("paperclip_history", SOURCE / "paperclip_history.py")
h = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = h
spec.loader.exec_module(h)
spec = importlib.util.spec_from_file_location("publish_history", SOURCE / "publish_history.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PublicationContracts(unittest.TestCase):
    def issue(self):
        return {"id": "archive", "identifier": "MAS-archive", "companyId": h.COMPANY,
                "visibility": "private", "assigneeAgentId": None, "assigneeUserId": None}

    def test_uncertain_issue_creation_never_replays_post(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            h.save_json(root / "issue.pending.json", {"idempotencyKey": p.MARKER})
            with patch.object(p, "api", return_value=[]) as api:
                with self.assertRaisesRegex(RuntimeError, "Unreconciled issue"):
                    p.ensure_issue(root)
                self.assertEqual(len(api.call_args_list), 1)
                self.assertEqual(api.call_args.args, (f"/companies/{h.COMPANY}/issues",))

    def test_existing_private_issue_is_reconciled_without_creating_another(self):
        with tempfile.TemporaryDirectory() as directory:
            issue = dict(self.issue(), description=f"[{p.MARKER}]")
            with patch.object(p, "api", return_value=[issue]) as api:
                self.assertEqual(p.ensure_issue(Path(directory))["id"], issue["id"])
                api.assert_called_once()
            self.assertEqual(json.loads((Path(directory) / "issue.json").read_text())["id"], issue["id"])

    def test_public_or_assigned_archive_is_not_accepted(self):
        for override in ({"visibility": "open"}, {"assigneeAgentId": "agent"}, {"assigneeUserId": "user"}):
            with patch.object(p, "api") as api:
                with self.assertRaisesRegex(RuntimeError, "private and unassigned"):
                    p.verify_no_execution(dict(self.issue(), **override))
                api.assert_not_called()

    def test_any_wake_or_truncated_history_stops_publication(self):
        for diagnostic in ({"wakeRequestCount": 1, "truncated": False}, {"wakeRequestCount": 0, "truncated": True}):
            with patch.object(p, "api", return_value=diagnostic):
                with self.assertRaisesRegex(RuntimeError, "wake history"):
                    p.verify_no_execution(self.issue())
        with patch.object(p, "api", return_value={"wakeRequestCount": 0, "truncated": False}):
            self.assertEqual(p.verify_no_execution(self.issue())["wakeRequestCount"], 0)

    def test_uncertain_attachment_upload_reconciles_original_native_object(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"redacted archive"
            name = "hermes-product-001.zip"
            (root / name).write_bytes(payload)
            record = {"filename": name, "bytes": len(payload), "sha256": h.digest(payload)}
            h.save_json(root / (name + ".pending.json"), record)
            saved = {"id": "original", "originalFilename": name, "sha256": record["sha256"],
                     "contentPath": "/api/attachments/original/content"}
            with patch.object(p, "api", side_effect=[[saved], payload]) as api:
                result = p.attachment(self.issue(), root, record, root)
                self.assertEqual(result["id"], "original")
                self.assertTrue(all(len(call.args) == 1 for call in api.call_args_list))
            with patch.object(p, "api", return_value=[]) as api:
                with self.assertRaisesRegex(RuntimeError, "Unreconciled attachment"):
                    p.attachment(self.issue(), root, record, root)
                api.assert_called_once()

    def test_segmented_profile_reconciles_and_wrong_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "snapshot.db").write_bytes(b"preserved original")
            records = {"id": "session", "messages": [{"id": n, "content": "x" * 150} for n in range(7)]}
            parts = list(h.split_record(records, target_bytes=600))
            bundles = [h.write_bundle(root, "product", n, [part], lambda records: "<html>reader</html>")
                       for n, part in enumerate(parts, 1)]
            profile = {"sessions": 1, "messages": 7, "snapshot_sha256": h.digest(b"preserved original"),
                       "bundles": bundles, "index": [{"id": "session", "messages": 7, "bundle": 1,
                                                        "bundles": list(range(1, len(parts) + 1))}]}
            p.verify_profile(root, profile)
            profile["index"][0]["bundles"] = [1]
            with self.assertRaisesRegex(RuntimeError, "locations do not reconcile"):
                p.verify_profile(root, profile)


if __name__ == "__main__":
    unittest.main()

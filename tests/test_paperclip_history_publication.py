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


class CompletionContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipts = self.root / "publication"
        self.receipts.mkdir()
        self.issue = {"id": "archive", "companyId": h.COMPANY, "visibility": "private",
                      "status": "backlog", "reviewAttention": {"state": "none"}}
        self.attachments = [{"id": "bundle", "sha256": h.digest(b"redacted records")}]
        self.documents = [{"key": "history-product-01", "body": "Verified snapshot"}]
        self.wakes = 0
        self.interactions = []
        self.live_runs = []
        self.patch_count = 0
        self.lost_response = False
        self.keep_backlog = False
        self.wake_after_patch = False
        self.publication = {"issueId": "archive", "attachments": 1,
                            "documents": [{"key": self.documents[0]["key"],
                                           "body_sha256": h.digest(self.documents[0]["body"].encode())}]}
        h.save_json(self.receipts / "verified-publication.json", self.publication)
        h.save_json(self.receipts / "hermes-product-001.zip.verified.json", self.attachments[0])

    def api(self, path, method="GET", body=None):
        if method == "PATCH":
            self.assertEqual((path, body), ("/issues/archive", {"status": "done"}))
            self.patch_count += 1
            if not self.keep_backlog:
                self.issue.update(status="done", completedAt="completed")
            if self.wake_after_patch:
                self.wakes = 1
            if self.lost_response:
                raise TimeoutError("response lost after commit")
            return dict(self.issue)
        self.assertEqual(method, "GET")
        if path == "/health":
            return {"status": "ok", "version": p.PAPERCLIP_VERSION, "deploymentMode": "local_trusted"}
        if path == "/issues/archive":
            return dict(self.issue)
        if path.endswith("/attachments"):
            return self.attachments
        if path.endswith("/documents"):
            return self.documents
        if path.endswith("/diagnostics/wakes"):
            return {"wakeRequestCount": self.wakes, "truncated": False}
        if path.endswith("/interactions"):
            return self.interactions
        if path.endswith("/live-runs"):
            return self.live_runs
        self.fail("Unexpected API route: " + path)

    def complete(self):
        with patch.object(p, "api", side_effect=self.api):
            return p.complete_archive(self.root)

    def test_verified_archive_closes_once_and_remains_read_only_on_reentry(self):
        self.assertEqual(self.complete()["status"], "done")
        self.assertEqual(self.patch_count, 1)
        self.assertEqual(self.complete()["status"], "done")
        self.assertEqual(self.patch_count, 1)
        saved = json.loads((self.receipts / "completion.verified.json").read_text())
        self.assertEqual((saved["wakeRequestCount"], saved["attachments"], saved["documents"]), (0, 1, 1))

    def test_incomplete_history_or_supplement_never_writes(self):
        (self.receipts / "verified-publication.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "History publication"):
            self.complete()
        h.save_json(self.receipts / "verified-publication.json", self.publication)
        (self.root / "asset-supplement").mkdir()
        with self.assertRaisesRegex(RuntimeError, "Asset publication"):
            self.complete()
        self.assertEqual(self.patch_count, 0)

    def test_changed_attachment_or_document_is_not_complete(self):
        self.attachments[0]["sha256"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "attachment index"):
            self.complete()
        self.attachments[0]["sha256"] = h.digest(b"redacted records")
        self.documents[0]["body"] = "edited"
        with self.assertRaisesRegex(RuntimeError, "document content"):
            self.complete()
        self.assertEqual(self.patch_count, 0)

    def test_supplement_uses_same_issue_and_verified_native_objects(self):
        folder = self.root / "asset-supplement/publication"
        folder.mkdir(parents=True)
        asset = {"id": "asset", "sha256": h.digest(b"asset")}
        document = {"key": "assets-product-01", "body": "File manifest"}
        saved = {"issueId": "other", "attachments": [asset],
                 "documents": [{"key": document["key"], "body_sha256": h.digest(document["body"].encode())}]}
        h.save_json(folder / "verified-publication.json", saved)
        with self.assertRaisesRegex(RuntimeError, "different archive"):
            self.complete()
        (folder / "verified-publication.json").unlink()
        saved["issueId"] = "archive"
        h.save_json(folder / "verified-publication.json", saved)
        self.attachments.append(asset)
        self.documents.append(document)
        result = self.complete()
        self.assertEqual((result["attachments"], result["documents"]), (2, 2))

    def test_changed_workflow_ownership_relations_and_interactions_refuse_completion(self):
        base = dict(self.issue)
        overrides = [{"assigneeAgentId": "agent"}, {"assigneeUserId": "user"},
                     {"visibility": "open"}, {"executionRunId": "run"}, {"checkoutRunId": "run"},
                     {"status": "in_progress"}, {"parentId": "parent"}, {"blocks": ["dependent"]},
                     {"blockedBy": ["blocker"]}, {"scheduledRetry": {"id": "retry"}},
                     {"reviewAttention": {"state": "pending"}}]
        for override in overrides:
            with self.subTest(override=override):
                self.issue = dict(base, **override)
                with self.assertRaises(RuntimeError):
                    self.complete()
        self.issue = base
        for field in ("interactions", "live_runs"):
            setattr(self, field, [{"id": "active"}])
            with self.assertRaisesRegex(RuntimeError, "interactions or live runs"):
                self.complete()
            setattr(self, field, [])
        self.assertEqual(self.patch_count, 0)

    def test_lost_response_reconciles_original_done_issue_without_replaying_patch(self):
        self.lost_response = True
        with self.assertRaises(TimeoutError):
            self.complete()
        self.assertTrue((self.receipts / "completion.pending.json").exists())
        self.assertFalse((self.receipts / "completion.verified.json").exists())
        self.assertEqual(self.complete()["status"], "done")
        self.assertEqual(self.patch_count, 1)

    def test_unresolved_pending_update_is_not_replayed(self):
        h.save_json(self.receipts / "completion.pending.json", {"issueId": "archive", "status": "done"})
        with self.assertRaisesRegex(RuntimeError, "Unreconciled archive completion"):
            self.complete()
        self.assertEqual(self.patch_count, 0)

    def test_failed_status_or_wake_readback_never_claims_completion(self):
        self.keep_backlog = True
        with self.assertRaisesRegex(RuntimeError, "did not persist"):
            self.complete()
        self.assertFalse((self.receipts / "completion.verified.json").exists())
        (self.receipts / "completion.pending.json").unlink()
        self.keep_backlog = False
        self.wake_after_patch = True
        with self.assertRaisesRegex(RuntimeError, "wake history"):
            self.complete()
        self.assertFalse((self.receipts / "completion.verified.json").exists())


if __name__ == "__main__":
    unittest.main()

"""Focused safety/compatibility checks for the one-shot Paperclip installer."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import readiness as r


class ReadinessTests(unittest.TestCase):
    def test_preserve_explicit_versions_and_existing_selections(self):
        original = {"paperclipSkillSync": {"desiredSkills": [
            {"key": r.CORE + "paperclip", "versionId": "kept"},
            r.CORE + "paperclip-board", r.CORE + "para-memory-files",
        ]}}
        before = copy.deepcopy(original)
        selected = r.selected_skills(original, "Product")
        self.assertEqual(selected[r.CORE + "paperclip"]["versionId"], "kept")
        self.assertIn(r.CORE + "paperclip-board", selected)
        self.assertIn(r.CORE + "paperclip-converting-plans-to-tasks", selected)
        self.assertNotIn(r.CORE + "para-memory-files", selected)
        self.assertEqual(original, before)

    def test_gateway_context_never_requests_secret_passthrough(self):
        for key in r.PAPERCLIP_CLIENT_CONTEXT:
            self.assertFalse(any(word in key for word in ("TOKEN", "KEY", "PASSWORD", "SECRET")))
        self.assertIn("PAPERCLIP_RUN_ID", r.PAPERCLIP_CLIENT_CONTEXT)

    def test_beta_pins_are_not_activated_when_the_native_feature_is_disabled(self):
        resolved = [{"key": r.CORE + "paperclip", "versionId": "existing"}]
        self.assertEqual(r.assignment_selections(resolved, False), [r.CORE + "paperclip"])
        self.assertEqual(r.assignment_selections(resolved, True), resolved)

    def test_unmaterialized_version_is_left_to_the_native_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home / "skills").mkdir()
            skill = {"key": r.CORE + "paperclip", "id": "skill", "slug": "paperclip", "currentVersionId": "version"}
            version = {"id": "version", "companyId": r.COMPANY, "companySkillId": "skill"}
            calls = []
            def request(path, body=None, method="GET"):
                calls.append(method)
                return [skill] if path.endswith("/skills") else version
            with patch.object(r, "request", request), patch.object(r, "version_path", return_value=home / "absent"):
                _, rows = r.qualify_versions({r.CORE + "paperclip": r.CORE + "paperclip"}, home, True)
            self.assertEqual(rows[0]["state"], "pending_native_materialization")
            self.assertEqual(list((home / "skills").iterdir()), [])
            self.assertTrue(all(method == "GET" for method in calls))

    def test_disabled_filter_preserves_existing_entries_and_parses_cli_list(self):
        names = r.disabled_names('["existing-private-skill"]') | r.DISABLED_FEEDBACK
        self.assertEqual(names, {"existing-private-skill", "complain", "suggestion-box"})
        with self.assertRaises(ValueError):
            r.disabled_names({"unexpected": True})

    def test_snapshot_tampering_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p / "SKILL.md").write_text("expected")
            v = {"fileInventory": [{"path": "SKILL.md", "content": "expected"}]}
            r.verify_inventory(p, v)
            (p / "SKILL.md").write_text("changed")
            with self.assertRaises(ValueError):
                r.verify_inventory(p, v)
            with self.assertRaises(ValueError):
                r.verify_inventory(p, {"fileInventory": [{"path": "../SKILL.md", "content": "x"}]})
            with self.assertRaises(ValueError):
                r.version_path("../other-company", "also-invalid")

    def test_foreign_paths_and_links_are_never_overwritten(self):
        for kind in ("file", "directory", "link"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                p = Path(root)
                source = p / "version"
                source.mkdir()
                (source / "SKILL.md").write_text("canonical")
                home = p / "profile"
                (home / "skills").mkdir(parents=True)
                target = home / "skills" / "paperclip"
                if kind == "file":
                    target.write_text("foreign")
                elif kind == "directory":
                    target.mkdir()
                    (target / "SKILL.md").write_text("foreign")
                else:
                    other = p / "other"
                    other.mkdir()
                    target.symlink_to(other)
                skill = {"key": r.CORE + "paperclip", "id": "skill", "slug": "paperclip", "currentVersionId": "version"}
                version = {"id": "version", "companyId": r.COMPANY, "companySkillId": "skill",
                           "fileInventory": [{"path": "SKILL.md", "content": "canonical"}]}
                calls = []
                def request(path, body=None, method="GET"):
                    calls.append((path, body, method))
                    return [skill] if path.endswith("/skills") else version
                with patch.object(r, "request", request), patch.object(r, "version_path", return_value=source):
                    with self.assertRaisesRegex(RuntimeError, "Preserving conflicting"):
                        r.qualify_versions({r.CORE + "paperclip": r.CORE + "paperclip"}, home, True)
                self.assertTrue(all(method == "GET" for _, _, method in calls))
                self.assertNotEqual(r.link_state(target, source), "ready")

    def test_native_version_link_is_reusable_without_sync_or_extra_versions(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            source = p / "version"
            source.mkdir()
            (source / "SKILL.md").write_text("canonical")
            home = p / "profile"
            (home / "skills").mkdir(parents=True)
            skill = {"key": r.CORE + "paperclip", "id": "skill", "slug": "paperclip", "currentVersionId": "version"}
            version = {"id": "version", "companyId": r.COMPANY, "companySkillId": "skill",
                       "fileInventory": [{"path": "SKILL.md", "content": "canonical"}]}
            calls = []
            def request(path, body=None, method="GET"):
                calls.append((path, body, method))
                return [skill] if path.endswith("/skills") else version
            with patch.object(r, "request", request), patch.object(r, "version_path", return_value=source):
                pinned, first = r.qualify_versions({r.CORE + "paperclip": r.CORE + "paperclip"}, home, True)
                _, second = r.qualify_versions({pinned[0]["key"]: pinned[0]}, home, True)
            self.assertEqual(first[0]["state"], "ready")
            self.assertEqual(second[0]["state"], "ready")
            self.assertEqual(pinned, [{"key": r.CORE + "paperclip", "versionId": "version"}])
            self.assertTrue(all(method == "GET" for _, _, method in calls))

    def test_cross_company_version_is_rejected_before_materialization(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home / "skills").mkdir()
            skill = {"key": r.CORE + "paperclip", "id": "skill", "slug": "paperclip", "currentVersionId": "version"}
            def request(path, body=None, method="GET"):
                return [skill] if path.endswith("/skills") else {
                    "id": "version", "companyId": "another-company", "companySkillId": "skill"}
            with patch.object(r, "request", request):
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    r.qualify_versions({r.CORE + "paperclip": r.CORE + "paperclip"}, home, True)
            self.assertEqual(list((home / "skills").iterdir()), [])


if __name__ == "__main__":
    unittest.main()

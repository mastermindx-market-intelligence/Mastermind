"""Focused safety/compatibility checks for the one-shot Paperclip installer."""
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

INSTALLER = Path(__file__).resolve().parents[1] / "ops" / "paperclip_fleet" / "paperclip_readiness.py"
SPEC = importlib.util.spec_from_file_location("paperclip_fleet_readiness", INSTALLER)
assert SPEC is not None and SPEC.loader is not None
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class ReadinessTests(unittest.TestCase):
    def test_marked_operator_addition_is_preserved_before_any_write(self):
        aid = next(iter(r.ROSTER))
        name, slug = r.ROSTER[aid]
        home = Path("/Users/chriswong/.hermes/profiles") / slug
        custom = r.instructions(name, slug) + "\nOperator addition: preserve this instruction.\n"
        agent = {"companyId": r.COMPANY, "name": name, "adapterType": "hermes_local",
                 "status": "idle", "adapterConfig": {}, "runtimeConfig": {}}
        responses = {
            f"/agents/{aid}": agent,
            f"/agents/{aid}/skills": {"entries": [
                {"sourcePath": str(home / "skills" / "existing" / "SKILL.md"), "managed": False}]},
            f"/agents/{aid}/instructions-bundle/file?path=AGENTS.md":
                {"content": custom, "contentHash": "observed-custom-preimage"},
        }
        calls = []
        def request(path, body=None, method="GET"):
            calls.append((path, body, method))
            return copy.deepcopy(responses[path])
        profile = {"model": {"provider": "capacity-fabric", "default": "glm-5.3"},
                   "memory": {"provider": "omh"}}
        with patch.object(r, "request", request), patch.object(r, "profile_config", return_value=profile), patch.object(Path, "is_file", return_value=True):
            with self.assertRaisesRegex(ValueError, "custom instructions; preserve and reconcile"):
                r.configure_agent(aid, name, slug, apply=True)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(body is None and method == "GET" for _, body, method in calls))
        self.assertEqual(responses[f"/agents/{aid}/instructions-bundle/file?path=AGENTS.md"]["content"], custom)

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


class ForegroundLearningInstructionTests(unittest.TestCase):
    @contextmanager
    def harness(self, content, slug="product", response="ok"):
        aid, (name, _) = next((aid, role) for aid, role in r.ROSTER.items() if role[1] == slug)
        home = Path("/Users/chriswong/.hermes/profiles") / slug
        entry_path = f"/agents/{aid}/instructions-bundle/file?path=AGENTS.md"
        write_path = f"/agents/{aid}/instructions-bundle/file"
        state = {"content": content, "contentHash": "observed-preimage-hash"}
        calls = []
        agent = {"companyId": r.COMPANY, "name": name, "adapterType": "hermes_local",
                 "status": "idle", "adapterConfig": {}, "runtimeConfig": {}}
        profile = {"model": {"provider": "capacity-fabric", "default": "glm-5.3"},
                   "memory": {"provider": "omh"}}

        def request(path, body=None, method="GET"):
            calls.append((path, copy.deepcopy(body), method))
            if method == "PUT":
                self.assertEqual(path, write_path)
                self.assertEqual(body["baseHash"], "observed-preimage-hash")
                if response == "conflict":
                    raise RuntimeError("native content-hash conflict")
                if response != "mismatch":
                    state.update(content=body["content"], contentHash="saved-hash", revision={"id": "saved-revision"})
                if response == "lost":
                    raise TimeoutError("response lost after native save")
                return copy.deepcopy(state)
            self.assertEqual(method, "GET", "instruction mode must not change another owner")
            if path == entry_path:
                return copy.deepcopy(state)
            if path == f"/agents/{aid}":
                return copy.deepcopy(agent)
            if path == f"/agents/{aid}/skills":
                return {"entries": [{"sourcePath": str(home / "skills/existing/SKILL.md"), "managed": False}]}
            if path.startswith(f"/companies/{r.COMPANY}/heartbeat-runs?"):
                return []
            raise AssertionError(f"Unexpected owner access: {path}")

        with patch.object(r, "request", request), patch.object(r, "profile_config", return_value=profile), patch.object(Path, "is_file", return_value=True), patch.object(r, "qualify_versions", return_value=([], [])) as qualify, patch.object(r, "configure_profile_context") as profile_write:
            yield aid, name, slug, state, calls
            profile_write.assert_not_called()
            if qualify.called:
                self.assertFalse(qualify.call_args.args[2], "native skill materialization must stay read-only")

    def legacy_product(self):
        return (Path(__file__).parent / "fixtures/paperclip_readiness_v1_product.md").read_text()

    def test_exact_predecessor_upgrades_with_cas_and_no_other_owner_writes(self):
        legacy = self.legacy_product()
        self.assertEqual(hashlib.sha256(legacy.encode()).hexdigest(), r.PREVIOUS_MANAGED_V1_SHA256["product"])
        with self.harness(legacy) as (aid, name, slug, state, calls):
            result = r.configure_agent(aid, name, slug, apply=True, instructions_only=True)
            self.assertEqual(state["content"], r.instructions(name, slug))
            self.assertEqual(result["changes"], ["instructions"])
            self.assertEqual(result["instruction_revision"], "saved-revision")
            self.assertEqual([method for _, _, method in calls if method != "GET"], ["PUT"])

    def test_current_instructions_are_idempotent(self):
        with self.harness(r.instructions("Product", "product")) as (aid, name, slug, _, calls):
            result = r.configure_agent(aid, name, slug, apply=True, instructions_only=True)
            self.assertTrue(result["instructions_ready"])
            self.assertEqual(result["changes"], [])
            self.assertTrue(all(method == "GET" for _, _, method in calls))

    def test_modified_legacy_and_another_roles_document_are_preserved(self):
        for content, slug in ((self.legacy_product() + " ", "product"), (self.legacy_product(), "engineering")):
            with self.subTest(slug=slug), self.harness(content, slug) as (aid, name, slug, state, calls):
                with self.assertRaisesRegex(ValueError, "custom instructions; preserve and reconcile"):
                    r.configure_agent(aid, name, slug, apply=True, instructions_only=True)
                self.assertEqual(state["content"], content)
                self.assertTrue(all(method == "GET" for _, _, method in calls))

    def test_cas_conflict_stops_without_retry_or_other_writes(self):
        with self.harness(self.legacy_product(), response="conflict") as (aid, name, slug, state, calls):
            with self.assertRaisesRegex(RuntimeError, "content-hash conflict"):
                r.configure_agent(aid, name, slug, apply=True, instructions_only=True)
            self.assertEqual(state["content"], self.legacy_product())
            self.assertEqual([method for _, _, method in calls if method != "GET"], ["PUT"])

    def test_lost_response_is_not_replayed(self):
        with self.harness(self.legacy_product(), response="lost") as (aid, name, slug, state, calls):
            with self.assertRaisesRegex(TimeoutError, "response lost"):
                r.configure_agent(aid, name, slug, apply=True, instructions_only=True)
            self.assertEqual(state["content"], r.instructions(name, slug))
            self.assertEqual([method for _, _, method in calls if method != "GET"], ["PUT"])

    def test_mismatched_readback_is_not_reported_complete_or_rewritten(self):
        with self.harness(self.legacy_product(), response="mismatch") as (aid, name, slug, _, calls):
            with self.assertRaisesRegex(RuntimeError, "Instruction readback mismatch"):
                r.configure_agent(aid, name, slug, apply=True, instructions_only=True)
            self.assertEqual([method for _, _, method in calls if method != "GET"], ["PUT"])


if __name__ == "__main__":
    unittest.main()

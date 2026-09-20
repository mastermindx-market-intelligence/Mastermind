"""Contracts for reviewed Workspace Agent profiles and pre-activation binding."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import unittest

from integrations.mastermind_secretary_mcp.schemas import TOOL_SPECS as STEWARD_TOOLS
from integrations.workbench_read_mcp.app import TOOL_NAME as WORKBENCH_READ_TOOL
from integrations.workspace_agent_return import TOOL_NAME as RETURN_TOOL
from integrations.workspace_agent_return import tool_spec
from integrations.workspace_agent_profiles import (
    ACTIVATION_SCHEMA,
    CATALOG_SCHEMA,
    ECONOMIC_SCHEMA,
    MAX_ACTIVATION_WINDOW_MS,
    PUBLICATION_STATE,
    WorkspaceProfileError,
    activation_binding_digest,
    build_activation_binding,
    catalog_digest,
    economic_envelope_digest,
    profile_by_id,
    profile_digest,
    validate_activation_binding,
    validate_economic_envelope,
    validate_profile_catalog,
)

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "config" / "workspace_agents" / "profile_catalog.v1.json"
NOW = 1789822800000


def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def economic(**changes):
    value = {
        "schema": ECONOMIC_SCHEMA,
        "authority_ref": "AUTH:workspace-canary-20260919",
        "accounting_source_ref": "COST:workspace-seat-observation-20260919",
        "billing_currency": "USD",
        "incremental_spend_cap_minor_units": 500,
        "usage_unit": "workspace-credit",
        "usage_cap_quantity": 100,
        "max_trigger_count": 1,
        "overflow_policy": "REFUSE",
        "issued_at_ms": NOW,
        "expires_at_ms": NOW + 60 * 60 * 1000,
    }
    value.update(changes)
    return value


class ProfileCatalogTests(unittest.TestCase):
    def test_catalog_is_exact_draft_with_two_reviewed_profiles(self):
        raw = load_catalog()
        catalog = validate_profile_catalog(raw)
        self.assertEqual(catalog["schema"], CATALOG_SCHEMA)
        self.assertEqual(catalog["publication_state"], PUBLICATION_STATE)
        self.assertEqual(
            [row["profile_id"] for row in catalog["profiles"]],
            [
                "program-continuity-adviser",
                "independent-outcome-reviewer",
            ],
        )
        self.assertRegex(catalog_digest(catalog), r"^[0-9a-f]{64}$")
        self.assertEqual(catalog_digest(catalog), catalog_digest(raw))

    def test_catalog_tool_names_join_to_existing_reviewed_surfaces(self):
        catalog = validate_profile_catalog(load_catalog())
        steward = {spec.name for spec in STEWARD_TOOLS}
        known = steward | {WORKBENCH_READ_TOOL, RETURN_TOOL}
        self.assertEqual(RETURN_TOOL, "submit_candidate")
        self.assertEqual(WORKBENCH_READ_TOOL, "read_project_file")
        for profile in catalog["profiles"]:
            self.assertLessEqual(set(profile["permitted_tools"]), known)
            self.assertIn(RETURN_TOOL, profile["permitted_tools"])

    def test_continuity_profile_is_read_supervision_plus_candidate_return_only(self):
        profile = profile_by_id(load_catalog(), "program-continuity-adviser")
        self.assertNotIn(WORKBENCH_READ_TOOL, profile["permitted_tools"])
        self.assertEqual(
            profile["required_app_bindings"],
            ["mastermind-steward", "mastermind-workspace-agent-return"],
        )
        self.assertEqual(profile["output_contract"]["authority_effect"], "NONE")
        self.assertIn("provider_trigger", profile["prohibited_effects"])
        self.assertIn("canonical_result_acceptance", profile["prohibited_effects"])
        self.assertIn("wake_acknowledgement", profile["prohibited_effects"])

    def test_reviewer_gets_bounded_artifact_read_but_no_source_write(self):
        profile = profile_by_id(load_catalog(), "independent-outcome-reviewer")
        self.assertIn(WORKBENCH_READ_TOOL, profile["permitted_tools"])
        self.assertEqual(
            profile["required_app_bindings"],
            [
                "mastermind-steward",
                "mastermind-workbench-read",
                "mastermind-workspace-agent-return",
            ],
        )
        self.assertIn("source_write", profile["prohibited_effects"])
        self.assertIn("parent_self_acceptance", profile["prohibited_effects"])
        self.assertEqual(profile["output_contract"]["max_result_chars"], 900)
        self.assertEqual(
            sorted(profile["output_contract"]["allowed_status"]),
            tool_spec()["input_schema"]["properties"]["status"]["enum"],
        )
        self.assertEqual(
            validate_profile(profile),
            profile,
            "normalized profile must remain canonical input to digest/activation paths",
        )

    def test_profile_digests_change_on_instruction_or_tool_drift(self):
        profile = profile_by_id(load_catalog(), "program-continuity-adviser")
        original = profile_digest(profile)
        changed_instruction = copy.deepcopy(profile)
        changed_instruction["instructions"][0] += " Changed."
        changed_tool = copy.deepcopy(profile)
        changed_tool["permitted_tools"].remove("get_attention")
        self.assertNotEqual(profile_digest(changed_instruction), original)
        self.assertNotEqual(profile_digest(changed_tool), original)

    def test_profile_contract_refuses_privilege_widening(self):
        catalog = load_catalog()
        cases = []
        tool = copy.deepcopy(catalog)
        tool["profiles"][0]["permitted_tools"].append("commit_text_patch")
        cases.append(tool)
        app = copy.deepcopy(catalog)
        app["profiles"][0]["required_app_bindings"].append("mastermind-executive")
        cases.append(app)
        authority = copy.deepcopy(catalog)
        authority["profiles"][0]["output_contract"]["authority_effect"] = "ACCEPT_RESULT"
        cases.append(authority)
        publication = copy.deepcopy(catalog)
        publication["publication_state"] = "PUBLISHED"
        cases.append(publication)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(WorkspaceProfileError):
                validate_profile_catalog(value)

    def test_profile_module_is_sdk_network_and_control_plane_free(self):
        path = ROOT / "integrations" / "workspace_agent_profiles.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        forbidden_roots = {
            "mcp",
            "httpx",
            "requests",
            "aiohttp",
            "sqlite3",
            "keyring",
            "subprocess",
            "control_plane.executive_runtime",
            "control_plane.wake_ack_ingress",
        }
        self.assertFalse(
            any(
                name in forbidden_roots
                or name.startswith(("mcp.", "httpx.", "requests.", "aiohttp."))
                for name in imports
            )
        )


class EconomicEnvelopeTests(unittest.TestCase):
    def test_economic_envelope_requires_spend_usage_trigger_and_expiry_bounds(self):
        value = validate_economic_envelope(economic())
        self.assertEqual(value["incremental_spend_cap_minor_units"], 500)
        self.assertEqual(value["usage_cap_quantity"], 100)
        self.assertEqual(value["max_trigger_count"], 1)
        self.assertEqual(value["overflow_policy"], "REFUSE")
        self.assertRegex(economic_envelope_digest(value), r"^[0-9a-f]{64}$")

    def test_zero_incremental_spend_is_valid_only_with_explicit_usage_cap(self):
        value = validate_economic_envelope(
            economic(incremental_spend_cap_minor_units=0)
        )
        self.assertEqual(value["incremental_spend_cap_minor_units"], 0)
        bad = economic(
            incremental_spend_cap_minor_units=0,
            usage_cap_quantity=0,
        )
        with self.assertRaises(WorkspaceProfileError):
            validate_economic_envelope(bad)

    def test_run_count_cannot_substitute_for_cost_or_usage_accounting(self):
        for mutation in (
            {"incremental_spend_cap_minor_units": -1},
            {"usage_cap_quantity": 0},
            {"max_trigger_count": 0},
            {"overflow_policy": "ALLOW"},
            {"billing_currency": "credits"},
            {"usage_unit": ""},
            {"accounting_source_ref": ""},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(
                WorkspaceProfileError
            ):
                validate_economic_envelope(economic(**mutation))

    def test_economic_window_is_finite(self):
        with self.assertRaises(WorkspaceProfileError):
            validate_economic_envelope(
                economic(expires_at_ms=NOW + MAX_ACTIVATION_WINDOW_MS + 1)
            )
        with self.assertRaises(WorkspaceProfileError):
            validate_economic_envelope(economic(expires_at_ms=NOW))


class ActivationBindingTests(unittest.TestCase):
    def build(self, profile_id="program-continuity-adviser", **changes):
        args = {
            "catalog": load_catalog(),
            "profile_id": profile_id,
            "provider_channel_ref": "agtch_synthetic123",
            "agent_version_ref": "agent-version-20260919-01",
            "economic_envelope": economic(),
        }
        args.update(changes)
        return build_activation_binding(**args)

    def test_activation_freezes_profile_channel_apps_economics_and_non_authority(self):
        binding = self.build()
        self.assertEqual(binding["schema"], ACTIVATION_SCHEMA)
        profile = profile_by_id(load_catalog(), "program-continuity-adviser")
        self.assertEqual(binding["profile_digest"], profile_digest(profile))
        self.assertEqual(
            binding["economic_envelope_digest"],
            economic_envelope_digest(economic()),
        )
        self.assertEqual(binding["concurrency_limit"], 1)
        self.assertFalse(binding["live_source_write_allowed"])
        self.assertFalse(binding["production_release_allowed"])
        self.assertEqual(
            binding["app_bindings"],
            profile["required_app_bindings"],
        )
        self.assertRegex(
            activation_binding_digest(
                binding,
                catalog=load_catalog(),
                now_ms=NOW + 1,
            ),
            r"^[0-9a-f]{64}$",
        )

    def test_reviewer_binding_has_exact_extra_read_app_not_extra_write_authority(self):
        binding = self.build("independent-outcome-reviewer")
        self.assertEqual(
            binding["app_bindings"],
            [
                "mastermind-steward",
                "mastermind-workbench-read",
                "mastermind-workspace-agent-return",
            ],
        )
        self.assertFalse(binding["live_source_write_allowed"])
        self.assertFalse(binding["production_release_allowed"])

    def test_activation_refuses_bad_provider_channel_and_version(self):
        with self.assertRaises(WorkspaceProfileError):
            self.build(provider_channel_ref="agt_bad")
        with self.assertRaises(WorkspaceProfileError):
            self.build(agent_version_ref="bad version")

    def test_activation_revalidation_catches_any_profile_or_economic_drift(self):
        binding = self.build()
        cases = []
        profile_drift = copy.deepcopy(binding)
        profile_drift["profile_digest"] = "0" * 64
        cases.append(profile_drift)
        app_drift = copy.deepcopy(binding)
        app_drift["app_bindings"].append("mastermind-workbench-read")
        cases.append(app_drift)
        budget_drift = copy.deepcopy(binding)
        budget_drift["economic_envelope"]["usage_cap_quantity"] += 1
        cases.append(budget_drift)
        privilege_drift = copy.deepcopy(binding)
        privilege_drift["production_release_allowed"] = True
        cases.append(privilege_drift)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(
                WorkspaceProfileError
            ):
                validate_activation_binding(
                    value,
                    catalog=load_catalog(),
                    now_ms=NOW + 1,
                )

    def test_expired_or_not_yet_current_economic_envelope_refuses_activation(self):
        binding = self.build()
        with self.assertRaisesRegex(
            WorkspaceProfileError, "ECONOMIC_ENVELOPE_NOT_CURRENT"
        ):
            validate_activation_binding(
                binding,
                catalog=load_catalog(),
                now_ms=NOW - 1,
            )
        with self.assertRaisesRegex(
            WorkspaceProfileError, "ECONOMIC_ENVELOPE_NOT_CURRENT"
        ):
            validate_activation_binding(
                binding,
                catalog=load_catalog(),
                now_ms=binding["economic_envelope"]["expires_at_ms"] + 1,
            )

    def test_binding_contains_no_token_or_secret_field(self):
        rendered = json.dumps(self.build(), sort_keys=True)
        for forbidden in (
            "access_token",
            "bearer",
            "secret",
            "password",
            "api_key",
            "slack_token",
        ):
            self.assertNotIn(forbidden, rendered.lower())


if __name__ == "__main__":
    unittest.main()

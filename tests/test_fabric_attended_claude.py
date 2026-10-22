"""Tests for the bounded attended Claude Code launch preparation contract."""
from __future__ import annotations

import dataclasses
import json
import os
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

from control_plane.claude_worker import _subprocess_sandbox_request
from control_plane.fabric_attended_claude import (
    ENVIRONMENT_KEYS,
    MAX_TURNS_LIMIT,
    REQUIRED_LAUNCH_PROOFS,
    SUPPORTED_HARNESS_ID,
    SUPPORTED_PROTOCOL,
    AttendedClaudeLaunchPreparation,
    AttendedClaudePreparationError,
    attended_profile_digest,
    prepare_attended_claude_launch,
)
from control_plane.subscription_harness_bindings import SubscriptionHarnessBinding, get_binding
from control_plane.subscription_provider_profiles import SubscriptionProviderProfile, get_profile
from control_plane.claude_subscription_worker import _usage_policy_satisfied
from control_plane.worker_execution_contract import BinaryAttestation, WorkerLaunchSpec

PROMPT = "FABRIC-ATTENDED-PROMPT-MARKER-7f3a: audit the login flow only."
BASE_URL = "https://glm-plan.example.invalid/v1"


def _binary(**over) -> BinaryAttestation:
    values = dict(
        path="/usr/local/bin/claude",
        real_path="/usr/local/bin/claude",
        version="2.0.14",
        sha256="ab" * 32,
        team_identifier=None,
        size=987654321,
        device=1,
        inode=2,
        mode=0o755,
        uid=0,
        gid=0,
        mtime_ns=1759999999000000000,
    )
    values.update(over)
    return BinaryAttestation(**values)


def _profile(**over) -> SubscriptionProviderProfile:
    values = dict(
        profile_id="glm-coding-plan",
        provider="glm",
        product="coding-plan",
        protocol="anthropic",
        base_url=BASE_URL,
        models={
            "routine": "glm-5.3",
            "hard": "glm-5.3",
            "fast": "glm-5.3-air",
            "subagent": "glm-5.3-air",
        },
        default_model_class="routine",
        supported_tool_only=True,
        autonomous_allowed=False,
        activation_gate="provider_realm_enrolled_and_capacity_known",
        quota_profile={"provider": "glm", "product": "coding-plan", "tier": "personal"},
        usage_policy={
            "supported_harness_required": True,
            "interactive_only": True,
            "unattended_background_allowed": False,
            "production_backend_allowed": False,
        },
    )
    values.update(over)
    return SubscriptionProviderProfile(**values)


def _binding(**over) -> SubscriptionHarnessBinding:
    values = dict(
        binding_id="glm-coding-plan.claude-code-anthropic",
        profile_id="glm-coding-plan",
        provider="glm",
        harness_id="claude-code",
        adapter_id="claude-compatible-subscription",
        protocol="anthropic",
        effective_base_url=BASE_URL,
        model_classes=("routine", "hard", "fast", "subagent"),
        implementation_state="SPEC_ONLY",
        autonomous_allowed=False,
        activation_gates=(
            "adapter_implemented",
            "provider_realm_enrolled",
            "capacity_known",
            "real_canary_passed",
            "usage_policy_satisfied",
        ),
    )
    values.update(over)
    return SubscriptionHarnessBinding(**values)


def _spec(**over) -> WorkerLaunchSpec:
    values = dict(
        run_id="run-1",
        job_id="job-1",
        worker_id="worker-1",
        workspace_path=Path("/srv/workspaces/repo"),
        run_dir=Path("/srv/runs/run-1"),
        prompt=PROMPT,
        result_schema_path=Path("/srv/runs/run-1/input/result.schema.json"),
        authorities=("READ",),
        model="glm-5.3",
    )
    values.update(over)
    return WorkerLaunchSpec(**values)


def _prepare(spec=None, **over) -> AttendedClaudeLaunchPreparation:
    return prepare_attended_claude_launch(
        spec=spec if spec is not None else _spec(),
        binary=over.pop("binary", _binary()),
        binding=over.pop("binding", _binding()),
        profile=over.pop("profile", _profile()),
        model_class=over.pop("model_class", "routine"),
        max_turns=over.pop("max_turns", 24),
        result_schema=over.pop("result_schema", {"type": "object"}),
        **over,
    )


def _unfreeze(value):
    if isinstance(value, Mapping):
        return {key: _unfreeze(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_unfreeze(item) for item in value]
    return value


def _argv_segment(argv: tuple[str, ...], flag: str) -> list[str]:
    index = argv.index(flag)
    values: list[str] = []
    for item in argv[index + 1:]:
        if item.startswith("--"):
            break
        values.append(item)
    return values


class AttendedClaudeLaunchPreparationTests(unittest.TestCase):
    def test_write_only_without_read_is_not_the_attended_contract(self):
        with self.assertRaises(AttendedClaudePreparationError):
            _prepare(spec=_spec(authorities=("WRITE_BRANCH",), allowed_artifact_paths=("src/a.py",)))

    def test_runtime_model_cannot_be_substituted_by_preparation(self):
        with self.assertRaises(AttendedClaudePreparationError):
            _prepare(spec=_spec(model="different-runtime-model"))

    def test_other_adapter_is_not_a_supported_claude_binding(self):
        with self.assertRaises(AttendedClaudePreparationError):
            _prepare(binding=_binding(adapter_id="unreviewed-http"))

    def test_remote_schema_must_be_in_the_bound_input_directory(self):
        with self.assertRaises(AttendedClaudePreparationError):
            _prepare(spec=_spec(result_schema_path=Path("/srv/runs/run-1/output/schema.json")))

    def test_read_only_descriptor_shape(self) -> None:
        descriptor = _prepare()
        self.assertEqual(descriptor.argv[0], "/usr/local/bin/claude")
        self.assertIn("--safe-mode", descriptor.argv)
        self.assertIn("-p", descriptor.argv)
        self.assertEqual(
            _argv_segment(descriptor.argv, "--model"), ["glm-5.3"]
        )
        self.assertEqual(
            _argv_segment(descriptor.argv, "--max-turns"), ["24"]
        )
        self.assertEqual(
            _argv_segment(descriptor.argv, "--permission-mode"), ["dontAsk"]
        )
        self.assertIn("--disable-slash-commands", descriptor.argv)
        self.assertIn("--no-chrome", descriptor.argv)
        self.assertIn("--no-session-persistence", descriptor.argv)
        self.assertIn("--strict-mcp-config", descriptor.argv)
        self.assertEqual(
            _argv_segment(descriptor.argv, "--mcp-config"), ['{"mcpServers":{}}']
        )
        self.assertEqual(descriptor.stdin_text, PROMPT)
        self.assertEqual(descriptor.model, "glm-5.3")
        self.assertEqual(descriptor.model_class, "routine")
        self.assertEqual(descriptor.endpoint, BASE_URL)
        self.assertEqual(descriptor.harness_id, SUPPORTED_HARNESS_ID)
        self.assertEqual(descriptor.protocol, SUPPORTED_PROTOCOL)
        self.assertEqual(descriptor.provider_home, "/srv/runs/run-1/home")
        self.assertEqual(descriptor.provider_tmp, "/srv/runs/run-1/tmp")
        self.assertEqual(descriptor.required_launch_proofs, REQUIRED_LAUNCH_PROOFS)
        self.assertEqual(tuple(sorted(descriptor.capabilities)), ("READ",))
        self.assertIs(descriptor.preparation_only, True)
        self.assertIs(descriptor.start_authorized, False)

    def test_prompt_travels_by_stdin_only(self) -> None:
        descriptor = _prepare()
        self.assertEqual(descriptor.stdin_text, PROMPT)
        self.assertNotIn(PROMPT, descriptor.argv)
        self.assertNotIn(PROMPT, descriptor.settings_json)
        self.assertNotIn(PROMPT, " ".join(descriptor.argv))
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", descriptor.environment)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", " ".join(descriptor.argv))

    def test_settings_policy_is_closed(self) -> None:
        descriptor = _prepare()
        settings = descriptor.settings
        permissions = settings["permissions"]
        self.assertEqual(permissions["defaultMode"], "dontAsk")
        self.assertIs(permissions["disableBypassPermissionsMode"], True)
        self.assertIs(settings["disableAllHooks"], True)
        self.assertIs(settings["enableAllProjectMcpServers"], False)
        self.assertEqual(
            json.dumps(_unfreeze(settings["sandbox"]), sort_keys=True),
            json.dumps(_subprocess_sandbox_request(), sort_keys=True),
        )
        allow = permissions["allow"]
        self.assertTrue(allow)
        for rule in allow:
            self.assertIn("(", rule, rule)
        deny = permissions["deny"]
        for tool in ("Read", "Glob", "Grep"):
            self.assertIn(f"{tool}(.git/**)", deny)
            self.assertIn(f"{tool}(.env)", deny)
        # Disabled tools are denied entirely; the actual compiler emits path
        # rules only for enabled file tools.
        for bare in ("Bash", "Edit", "Write", "Agent", "Task", "mcp__*"):
            self.assertIn(bare, deny)
        self.assertEqual(
            descriptor.settings_json,
            json.dumps(
                json.loads(descriptor.settings_json),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
        self.assertEqual(
            _argv_segment(descriptor.argv, "--settings")[0],
            descriptor.settings_json,
        )
        self.assertNotIn("--dangerously-skip-permissions", descriptor.argv)

    def test_allowed_tools_use_scoped_rules(self) -> None:
        descriptor = _prepare()
        allowed = _argv_segment(descriptor.argv, "--allowedTools")
        self.assertEqual(allowed, list(descriptor.settings["permissions"]["allow"]))
        for rule in allowed:
            self.assertIn("(", rule)
        self.assertNotIn("Read", allowed)

    def test_write_branch_is_scoped_to_declared_paths(self) -> None:
        descriptor = _prepare(
            spec=_spec(
                authorities=("READ", "WRITE_BRANCH"),
                allowed_artifact_paths=("src/app.py", "docs/guide.md"),
            ),
        )
        self.assertEqual(
            tuple(sorted(descriptor.capabilities)), ("READ", "WRITE_BRANCH")
        )
        allowed = _argv_segment(descriptor.argv, "--allowedTools")
        self.assertIn("Edit(./src/app.py)", allowed)
        self.assertIn("Write(./src/app.py)", allowed)
        self.assertIn("Edit(./docs/guide.md)", allowed)
        self.assertIn("Write(./docs/guide.md)", allowed)
        self.assertNotIn("Edit", allowed)
        self.assertNotIn("Write", allowed)
        self.assertNotIn("Edit", descriptor.settings["permissions"]["deny"])
        self.assertNotIn("Write", descriptor.settings["permissions"]["deny"])
        self.assertIn("Bash", descriptor.settings["permissions"]["deny"])

    def test_write_branch_requires_safe_paths(self) -> None:
        for paths in (
            (),
            ("config.toml",),
            (".env",),
            (".env.local",),
            (".git/config",),
            (".claude/settings.json",),
            ("../escape.py",),
            ("a//b.py",),
            ("has space.py",),
            ("a\\b.py",),
            ("same.py", "same.py"),
        ):
            with self.assertRaises(
                (AttendedClaudePreparationError, ValueError),
                msg=repr(paths),
            ):
                _prepare(
                    spec=_spec(
                        authorities=("READ", "WRITE_BRANCH"),
                        allowed_artifact_paths=paths,
                    ),
                )

    def test_unsupported_capabilities_are_rejected(self) -> None:
        for authorities in (
            (),
            ("RUN_TESTS",),
            ("READ", "RUN_TESTS"),
            ("RESEARCH",),
            ("READ", "RESEARCH"),
            ("FLY_TO_THE_MOON",),
        ):
            with self.assertRaises(
                (AttendedClaudePreparationError, ValueError),
                msg=repr(authorities),
            ):
                _prepare(spec=_spec(authorities=authorities))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(authority="RUN_TESTS"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(authorities=("READ", "WRITE_BRANCH")))

    def test_identity_and_provider_mismatch_is_rejected(self) -> None:
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(harness_id="codex-cli"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(protocol="responses"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(profile=_profile(protocol="openai-chat"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(provider="alibaba"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(profile=_profile(provider="alibaba"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(profile_id="other-plan"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(effective_base_url="https://drift.example.invalid/v1"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(effective_base_url="http://glm-plan.example.invalid/v1"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(model_class="ultraviolet")
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(
                binding=_binding(model_classes=("routine", "hard")),
                model_class="fast",
            )
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(model_class=True)

    def test_moving_model_alias_is_never_served(self) -> None:
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(profile=_profile(models={"routine": "opus"}))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(profile=_profile(models={"routine": "best"}))

    def test_model_alias_environment_pins_selected_model(self) -> None:
        descriptor = _prepare(spec=_spec(model="glm-5.3-air"), model_class="fast")
        self.assertEqual(descriptor.model, "glm-5.3-air")
        self.assertEqual(set(descriptor.environment), set(ENVIRONMENT_KEYS))
        for key in (
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "CLAUDE_CODE_SUBAGENT_MODEL",
        ):
            self.assertEqual(descriptor.environment[key], "glm-5.3-air", key)
        self.assertEqual(descriptor.environment["ANTHROPIC_BASE_URL"], BASE_URL)
        self.assertEqual(descriptor.environment["HOME"], "/srv/runs/run-1/home")
        self.assertEqual(descriptor.environment["TMPDIR"], "/srv/runs/run-1/tmp")
        self.assertEqual(descriptor.environment["CLAUDE_CODE_MAX_RETRIES"], "0")
        self.assertEqual(descriptor.environment["MAX_STRUCTURED_OUTPUT_RETRIES"], "0")
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", descriptor.environment)

    def test_no_inherited_environment(self) -> None:
        injected = {
            "FABRIC_INHERITED_MARKER": "1",
            "ANTHROPIC_AUTH_TOKEN": "sk-injected",
            "HTTP_PROXY": "http://injected.invalid",
        }
        with mock.patch.dict(os.environ, injected, clear=False):
            descriptor = _prepare()
        self.assertNotIn("FABRIC_INHERITED_MARKER", descriptor.environment)
        self.assertNotIn("HTTP_PROXY", descriptor.environment)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", descriptor.environment)
        self.assertEqual(set(descriptor.environment), set(ENVIRONMENT_KEYS))

    def test_max_turns_is_canonical_and_bounded(self) -> None:
        for bad in (0, -1, 65, MAX_TURNS_LIMIT + 1, True, False, "24", 24.0, None):
            with self.assertRaises(
                (AttendedClaudePreparationError, ValueError, TypeError),
                msg=repr(bad),
            ):
                _prepare(max_turns=bad)
        for good in (1, MAX_TURNS_LIMIT):
            self.assertEqual(_prepare(max_turns=good).max_turns, good)

    def test_lexical_paths_are_absolute_disjoint_and_contain_schema(self) -> None:
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(workspace_path=Path("relative/ws")))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(run_dir=Path("/srv/workspaces/repo/runs/r1")))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(workspace_path=Path("/srv/runs/run-1/ws")))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(run_dir=Path("/srv/workspaces/repo")))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(
                spec=_spec(
                    result_schema_path=Path("/srv/workspaces/repo/schema.json")
                )
            )
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(run_dir=Path("/srv/runs/../runs/run-1")))
        descriptor = _prepare()
        self.assertEqual(descriptor.workspace_path, "/srv/workspaces/repo")
        self.assertEqual(descriptor.run_dir, "/srv/runs/run-1")

    def test_result_schema_is_explicit_canonical_and_bounded(self) -> None:
        for good in (True, False, {"type": "object"}):
            descriptor = _prepare(result_schema=good)
            expected = json.dumps(
                good, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            self.assertEqual(descriptor.result_schema_json, expected)
            self.assertEqual(
                _argv_segment(descriptor.argv, "--json-schema"), [expected]
            )
        for bad in ("{\"type\": \"object\"}", 7, None, [1, 2]):
            with self.assertRaises(
                (AttendedClaudePreparationError, ValueError, TypeError),
                msg=repr(bad),
            ):
                _prepare(result_schema=bad)
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(result_schema={"type": "object", "blob": "x" * (1024 * 1024)})
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(result_schema={"k": float("nan")})

    def test_binary_attestation_is_bounded(self) -> None:
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary=_binary(real_path="claude"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary=_binary(real_path="/bin/sh -c 'evil'"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary=_binary(real_path="/usr/bin/claude;rm"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary=_binary(real_path="/usr/bin/$(echo x)"))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary=_binary(sha256="zz" * 32))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary=_binary(size=0))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binary="claude")
        self.assertEqual(_prepare().binary, _binary())

    def test_prompt_bounds(self) -> None:
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(prompt="   "))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(spec=_spec(prompt="x" * (1024 * 1024 + 1)))

    def test_usage_policy_and_autonomy_flags_are_preserved(self) -> None:
        profile = _profile()
        descriptor = _prepare(profile=profile)
        self.assertEqual(dict(descriptor.profile_usage_policy), profile.usage_policy)
        self.assertIs(descriptor.binding_autonomous_allowed, False)
        self.assertEqual(
            descriptor.profile_usage_policy["unattended_background_allowed"], False
        )
        self.assertEqual(
            descriptor.profile_usage_policy["production_backend_allowed"], False
        )
        with self.assertRaises(TypeError):
            descriptor.profile_usage_policy["interactive_only"] = False  # type: ignore[index]
        with self.assertRaises(TypeError):
            descriptor.environment["ANTHROPIC_MODEL"] = "opus"  # type: ignore[index]

    def test_spec_only_is_not_runtime_approval(self) -> None:
        descriptor = _prepare()
        self.assertEqual(descriptor.implementation_state, "SPEC_ONLY")
        self.assertIs(descriptor.preparation_only, True)
        self.assertIs(descriptor.start_authorized, False)
        self.assertIn("provider_realm_enrolled", descriptor.required_launch_proofs)
        self.assertIn("capacity_known", descriptor.required_launch_proofs)
        self.assertIn("isolation_verified", descriptor.required_launch_proofs)
        self.assertIn("attendance_confirmed", descriptor.required_launch_proofs)
        self.assertIn("full_launch_attestation", descriptor.required_launch_proofs)
        self.assertIn(
            "realm_credential_insertion_at_boundary", descriptor.caller_obligations
        )
        payload = descriptor.to_dict()
        joined = json.dumps(payload, sort_keys=True, default=str).lower()
        for marker in ("auth_token", "api_key", "secret"):
            self.assertNotIn(marker, joined)
        self.assertNotIn(
            "anthropic_auth_token",
            {str(key).lower() for key in payload["environment"]},
        )
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            dataclasses.replace(descriptor, start_authorized=True)
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            dataclasses.replace(descriptor, preparation_only=False)

    def test_byteplus_real_catalog_prepares_attended_only_without_credential(self) -> None:
        """Prove the actual BytePlus binding enters the existing Claude compiler.

        This is *preparation*, not authentication, provider execution, quota
        proof or an autonomous Fabric start.
        """
        profile = get_profile("byteplus-coding-plan-personal")
        binding = get_binding("byteplus-coding-plan-personal.claude-code-anthropic")
        spec = _spec(model=profile.model_for("routine"))
        prepared = _prepare(profile=profile, binding=binding, spec=spec, model_class="routine")
        self.assertEqual(prepared.endpoint, "https://ark.ap-southeast.bytepluses.com/api/coding")
        self.assertEqual(prepared.model, "glm-5.3-flash")
        self.assertEqual(prepared.implementation_state, "SPEC_ONLY")
        self.assertTrue(prepared.preparation_only)
        self.assertFalse(prepared.start_authorized)
        self.assertFalse(prepared.binding_autonomous_allowed)
        self.assertEqual(prepared.profile_usage_policy["interactive_only"], True)
        self.assertEqual(prepared.profile_usage_policy["single_user_only"], True)
        self.assertFalse(prepared.profile_usage_policy["unattended_background_allowed"])
        self.assertFalse(prepared.profile_usage_policy["production_backend_allowed"])
        self.assertTrue(_usage_policy_satisfied(profile, "interactive_canary"))
        self.assertFalse(_usage_policy_satisfied(profile, "executive_worker"))
        self.assertFalse(_usage_policy_satisfied(profile, "automated_fabric"))
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", prepared.environment)
        self.assertNotIn("ANTHROPIC_API_KEY", prepared.environment)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", prepared.to_dict())

    def test_byteplus_real_catalog_cannot_prepare_unreviewed_model(self) -> None:
        profile = get_profile("byteplus-coding-plan-personal")
        binding = get_binding("byteplus-coding-plan-personal.claude-code-anthropic")
        with self.assertRaises(AttendedClaudePreparationError):
            _prepare(
                profile=profile, binding=binding,
                spec=_spec(model="glm-5.3"),
                model_class="routine",
            )

    def test_profile_digest_is_stable_and_sensitive(self) -> None:
        first = attended_profile_digest(_profile())
        self.assertEqual(first, _prepare().profile_digest)
        self.assertEqual(first, attended_profile_digest(_profile()))
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, attended_profile_digest(_profile(provider="alibaba")))
        self.assertNotEqual(first, attended_profile_digest(_profile(base_url="https://other.example.invalid/v1")))
        with self.assertRaises((AttendedClaudePreparationError, ValueError)):
            _prepare(binding=_binding(effective_base_url="https://other.example.invalid/v1"))

    def test_descriptor_is_immutable_and_deterministic(self) -> None:
        descriptor = _prepare()
        again = _prepare()
        self.assertEqual(descriptor, again)
        self.assertEqual(descriptor.argv, again.argv)
        self.assertEqual(descriptor.settings_json, again.settings_json)
        self.assertEqual(descriptor.settings_sha256, again.settings_sha256)
        self.assertEqual(descriptor.profile_digest, again.profile_digest)
        self.assertIsInstance(descriptor.settings, Mapping)
        with self.assertRaises((TypeError, AttributeError)):
            descriptor.max_turns = 5  # type: ignore[misc]

    def test_binary_real_path_is_pinned_in_argv(self) -> None:
        descriptor = _prepare(binary=_binary(real_path="/opt/tools/claude"))
        self.assertEqual(descriptor.argv[0], "/opt/tools/claude")
        self.assertNotEqual(descriptor.argv[0], _binary().path)


if __name__ == "__main__":
    unittest.main()

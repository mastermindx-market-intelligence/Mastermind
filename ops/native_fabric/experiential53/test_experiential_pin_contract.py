#!/usr/bin/env python3
"""Contract tests for the Experiential Labs MANUAL-only pin (experiential53).

Hermetic and deterministic: no network, no provider call, no credential or
registry read, no host mutation.  Subprocess use is limited to this child's
own CLI and shell scaffold (pure refusals).  Run directly:

    python3 ops/native_fabric/experiential53/test_experiential_pin_contract.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import experiential_pin as pin  # noqa: E402

EXEC_SH = HERE / "experiential_exec.sh"
POOLBLOCK = HERE / "pools.yaml.experiential.poolblock.yaml"
PIN_PY = HERE / "experiential_pin.py"

REFUSED = pin.ExperientialPinRefused


class ExactManualPreviewTests(unittest.TestCase):
    def test_exact_pin_previews_without_effect(self):
        result = pin.preview("explabs-preview-01", "fix_build",
                             pool="experiential", model="glm-5.3-uncensored")
        self.assertEqual(result["state"], "PREVIEW_ONLY")
        self.assertIs(result["reserved"], False)
        self.assertEqual((result["pool"], result["model"]),
                         ("experiential", "glm-5.3-uncensored"))
        self.assertTrue(result["strict_pin_enforced_at_request"])
        self.assertTrue(result["selection_rechecked_at_request"])
        self.assertIsNone(result["escalate_to"])
        self.assertIsNone(result["fallback"])

    def test_exact_pin_is_case_exact_after_casefold_only(self):
        result = pin.preview("explabs-preview-02", "mechanical",
                             pool="Experiential", model="GLM-5.3-UNCENSORED")
        self.assertEqual(result["model"], "glm-5.3-uncensored")

    def test_wrong_model_slugs_refused(self):
        for bad in ("glm-5.3", "glm-5.3-flash", "glm-5.3-uncensored-v2",
                    "glm-5.3-uncensore", "uncensored"):
            with self.assertRaises(REFUSED) as caught:
                pin.preview("explabs-preview-03", "fix_build",
                            pool="experiential", model=bad)
            self.assertIn(caught.exception.reason, {
                "EXPERIENTIAL_MODEL_SLUG_MISMATCH",
                "EXPERIENTIAL_MODEL_DISTINCT"},
                f"unexpected refusal for {bad!r}")
        # Surrounding whitespace is selection noise, not a different slug.
        padded = pin.preview("explabs-preview-03b", "fix_build",
                             pool="experiential", model=" glm-5.3-uncensored ")
        self.assertEqual(padded["model"], "glm-5.3-uncensored")

    def test_missing_model_requires_exact_slug(self):
        with self.assertRaisesRegex(REFUSED, "MANUAL_MODEL_REQUIRED"):
            pin.preview("explabs-preview-04", "fix_build", pool="experiential",
                        model=None)
        # "auto" is never an explicit pin on a manual-only pool.
        with self.assertRaisesRegex(REFUSED, "MANUAL_MODEL_REQUIRED"):
            pin.preview("explabs-preview-05", "fix_build",
                        pool="experiential", model="auto")

    def test_missing_or_wrong_pool_refused(self):
        with self.assertRaisesRegex(REFUSED, "MANUAL_POOL_REQUIRED"):
            pin.preview("explabs-preview-06", "fix_build", pool=None,
                        model="glm-5.3-uncensored")
        with self.assertRaisesRegex(REFUSED, "EXPERIENTIAL_POOL_ONLY"):
            pin.preview("explabs-preview-07", "fix_build", pool="minimax",
                        model="glm-5.3-uncensored")

    def test_slug_cannot_ride_the_glm_pool(self):
        with self.assertRaisesRegex(REFUSED, "GLM_POOL_CARRIER_REFUSED"):
            pin.preview("explabs-preview-08", "fix_build", pool="glm",
                        model="glm-5.3-uncensored")
        # The canonical glm models are refused on THIS pool too.
        with self.assertRaisesRegex(REFUSED, "EXPERIENTIAL_MODEL_DISTINCT"):
            pin.preview("explabs-preview-09", "fix_build", pool="experiential",
                        model="glm-5.3")

    def test_slug_is_distinct_from_canonical_glm_tier(self):
        self.assertNotIn(pin.MODEL, pin.GLM_POOL_MODELS)
        self.assertEqual(pin.MODEL.count("uncensored"), 1)
        # Canonical tier stays canonical: this child defines no alias from
        # either Z.AI slug onto the uncensored slug.
        for canonical in pin.GLM_POOL_MODELS:
            with self.assertRaises(REFUSED):
                pin.enforce_pin("experiential", canonical)

    def test_selector_shape_is_bounded(self):
        for bad in ("experiential; rm -rf /", "experiential\nextra", 7,
                    "experiential$(id)"):
            with self.assertRaises(REFUSED):
                pin.preview("explabs-preview-10", "fix_build", pool=bad,
                            model="glm-5.3-uncensored")

    def test_task_class_bounds_survive_an_explicit_pin(self):
        for cls in ("review", "architecture", "adjudicate", "orchestration"):
            with self.assertRaisesRegex(
                    REFUSED, "EXPERIENTIAL_TASK_CLASS_FORBIDDEN"):
                pin.preview("explabs-preview-11", cls,
                            pool="experiential", model="glm-5.3-uncensored")
        with self.assertRaisesRegex(
                REFUSED, "EXPERIENTIAL_TASK_CLASS_NOT_ADMITTED"):
            pin.preview("explabs-preview-12", "unknown",
                        pool="experiential", model="glm-5.3-uncensored")


class NoDefaultPromotionTests(unittest.TestCase):
    def test_every_automatic_path_is_none(self):
        classes = ("execute", "fix_build", "review", "build", "audit",
                   "high_level", "unknown", "census", "mechanical",
                   "adjudicate", "orchestration")
        for cls in classes:
            verdict = pin.auto_selection_verdict(cls)
            self.assertEqual(verdict["state"], "NONE", cls)
            self.assertEqual(verdict["reason"], "experiential_manual_only")
            self.assertIsNone(verdict["pool"])
            self.assertIsNone(verdict["escalate_to"])
            self.assertIsNone(verdict["fallback"])

    def test_pool_is_structurally_manual_only(self):
        self.assertTrue(pin.MANUAL_ONLY)
        self.assertEqual(pin.ESCALATE_TARGETS, frozenset())
        # Empty task_class_fit in the registry block: no scoring hook exists.
        block = POOLBLOCK.read_text(encoding="utf-8")
        self.assertRegex(block, r"task_class_fit: \{\}\s*# EMPTY BY LAW")
        self.assertRegex(block, r"manual_only: true")


class NoFallbackTests(unittest.TestCase):
    def test_cross_provider_fallback_refused(self):
        for proposed in (("glm", "glm-5.3"), ("glm", "glm-5.3-flash"),
                         ("minimax", "MiniMax-M3"), ("go", "deepseek-v4.1-flash")):
            verdict = pin.fallback_refused(
                "experiential", "glm-5.3-uncensored", *proposed)
            self.assertEqual(verdict["reason"], "NO_CROSS_PROVIDER_FALLBACK")
            self.assertIsNone(verdict["escalate_to"])

    def test_same_slug_on_wrong_pool_is_not_a_fallback(self):
        verdict = pin.fallback_refused(
            "experiential", "glm-5.3-uncensored", "glm", "glm-5.3-uncensored")
        self.assertEqual(verdict["reason"], "NO_CROSS_PROVIDER_FALLBACK")

    def test_silent_retry_after_failure_refused(self):
        verdict = pin.fallback_refused(
            "experiential", "glm-5.3-uncensored", None, None)
        self.assertEqual(verdict["reason"], "FAILED_PIN_NOT_RETRIED")
        verdict = pin.fallback_refused(
            "experiential", "glm-5.3-uncensored",
            "experiential", "glm-5.3-uncensored")
        self.assertEqual(verdict["reason"], "FAILED_PIN_NOT_RETRIED")


class FailClosedAdmissionTests(unittest.TestCase):
    ALL_GATES = dict(
        pool="experiential", model="glm-5.3-uncensored", task_class="fix_build",
        registry_entry={"enabled": True}, entitlement={"verified": True},
        retention_acknowledged=True, sensitive_data_opt_in=True,
        account="b", quota_readback="authenticated",
    )

    def expect(self, reason, **overrides):
        kwargs = dict(self.ALL_GATES)
        kwargs.update(overrides)
        with self.assertRaises(REFUSED) as caught:
            pin.admit_execution(**kwargs)
        self.assertEqual(caught.exception.reason, reason)

    def test_missing_entitlement_refused(self):
        self.expect("ENTITLEMENT_UNVERIFIED", entitlement=None)
        self.expect("ENTITLEMENT_UNVERIFIED", entitlement={"verified": False})

    def test_disabled_provider_refused(self):
        self.expect("PROVIDER_DISABLED", registry_entry=None)
        self.expect("PROVIDER_DISABLED", registry_entry={})
        self.expect("PROVIDER_DISABLED", registry_entry={"enabled": False})
        self.expect("PROVIDER_DISABLED", registry_entry={"enabled": "true"})

    def test_sensitive_data_hold(self):
        self.expect("RETENTION_UNVERIFIED", retention_acknowledged=False)
        self.expect("SENSITIVE_DATA_DISCLOSURE_REQUIRED",
                    sensitive_data_opt_in=False)
        # Each opt-in is independent: no bundle implies the other.  The first
        # refusal follows the contract order (retention before disclosure).
        self.expect("RETENTION_UNVERIFIED",
                    retention_acknowledged=False, sensitive_data_opt_in=True)
        self.expect("SENSITIVE_DATA_DISCLOSURE_REQUIRED",
                    retention_acknowledged=True, sensitive_data_opt_in=False)

    def test_proprietary_code_never_exposed_automatically(self):
        self.expect("PROPRIETARY_CODE_EXPOSURE_REFUSED",
                    proprietary_code=True, code_exposure_opt_in=False)
        # Sensitive-data opt-in does NOT imply code-exposure opt-in.
        self.expect("PROPRIETARY_CODE_EXPOSURE_REFUSED",
                    proprietary_code=True, code_exposure_opt_in=False,
                    sensitive_data_opt_in=True)

    def test_account_a_denial_is_held(self):
        self.expect("ACCOUNT_A_HELD_HTTP403", account="a")
        self.expect("ACCOUNT_A_HELD_HTTP403", account="A")

    def test_account_b_unknown_quota_is_not_capacity(self):
        self.expect("QUOTA_READBACK_UNAUTHENTICATED",
                    account="b", quota_readback=None)
        self.expect("QUOTA_READBACK_UNAUTHENTICATED",
                    account="b", quota_readback="screenshot")
        self.assertIn("1", str(pin.ACCOUNT_B_DAILY_CAP_USD))

    def test_no_execution_without_verified_account_or_retention(self):
        self.expect("ACCOUNT_UNRESOLVED", account=None)
        self.expect("ACCOUNT_UNKNOWN", account="c")

    def test_transport_absence_is_the_final_no_false_admission_gate(self):
        # Every other gate satisfied: admission still refuses.  The transport
        # gate is a module constant, never a caller argument.
        self.expect("EXPERIENTIAL_TRANSPORT_NOT_INSTALLED")
        self.assertFalse(pin.TRANSPORT_INSTALLED)
        # Flipping the single owner-owned constant is the only admission path.
        with mock.patch.object(pin, "TRANSPORT_INSTALLED", True):
            admitted = pin.admit_execution(**self.ALL_GATES)
        self.assertEqual(admitted["state"], "ADMITTED")
        self.assertIsNone(admitted["escalate_to"])


class PoolBlockLawTests(unittest.TestCase):
    """Structural law checks on the declarative registry block."""

    BLOCK = POOLBLOCK.read_text(encoding="utf-8")

    @classmethod
    def setUpClass(cls):
        # Law statements live on non-comment lines; prose comments carry the
        # rationale, not the contract.
        cls.BODY = "\n".join(
            line for line in cls.BLOCK.splitlines()
            if line.strip() and not line.lstrip().startswith("#"))

    def lines(self, pattern):
        return re.findall(r"^.*" + pattern + r".*$", self.BODY, re.MULTILINE)

    def test_block_declares_manual_disabled_pool_with_exact_slug(self):
        self.assertRegex(self.BODY, r"(?m)^  experiential:$")
        self.assertRegex(self.BODY, r"(?m)^    enabled: false\s*(#.*)?$")
        self.assertRegex(self.BODY, r"(?m)^    manual_only: true$")
        self.assertIn("default: glm-5.3-uncensored", self.BODY)
        self.assertIn("default_model: glm-5.3-uncensored", self.BODY)

    def test_block_never_touches_the_glm_pool(self):
        self.assertNotRegex(self.BODY, r"(?m)^  glm:")
        self.assertRegex(self.BODY, r"distinct_from: \[glm-5.3, glm-5.3-flash\]")
        self.assertRegex(self.BODY, r"(?m)^      not_pool_glm: true$")

    def test_block_carries_account_and_retention_law(self):
        self.assertIn("status: HELD_HTTP403", self.BODY)
        self.assertIn("retry: forbidden", self.BODY)
        self.assertIn("daily_cap_usd: 1.0", self.BODY)
        self.assertIn("readback_authenticated: false", self.BODY)
        self.assertIn("provider retains prompt and response", self.BLOCK)
        self.assertIn("funded_by: platform_only", self.BODY)
        self.assertIn("sensitive_data_disclosure: required_opt_in", self.BODY)
        self.assertIn("no automatic exposure", self.BLOCK)

    def test_block_has_no_escalation_or_fallback_target(self):
        # On law lines (comments stripped), no promotion vocabulary exists.
        # A negation of the word (prohibition prose) is not a promotion.
        for forbidden in ("escalate", "fallback", "escalation_ladder",
                          "preferred", "default_task_routing"):
            hits = [line for line in self.lines(forbidden)
                    if not re.search(r"no [^.]*" + forbidden, line)]
            self.assertEqual(hits, [], f"unexpected {forbidden!r} promotion")

    def test_block_is_valid_yaml_when_parser_available(self):
        try:
            import yaml  # type: ignore
        except ImportError:
            self.skipTest("PyYAML unavailable; structural checks already ran")
        # Strip the leading comment block, then wrap as a mapping document.
        body = re.sub(r"^#.*\n", "", self.BLOCK, flags=re.MULTILINE)
        doc = ("pools:\n" + body) if not body.lstrip().startswith("pools:") else body
        parsed = yaml.safe_load(doc)
        entry = parsed["pools"]["experiential"]
        self.assertIs(entry["enabled"], False)
        self.assertIs(entry["manual_only"], True)
        self.assertEqual(entry["default_model"], "glm-5.3-uncensored")
        self.assertEqual(entry["task_class_fit"], {})
        self.assertEqual(entry["caps"]["concurrent"], 1)
        self.assertEqual(entry["accounts"]["a"]["status"], "HELD_HTTP403")
        self.assertIs(entry["accounts"]["b"]["readback_authenticated"], False)
        self.assertEqual(entry["model_distinctness"]["distinct_from"],
                         ["glm-5.3", "glm-5.3-flash"])


class ZeroEffectContractTests(unittest.TestCase):
    """No storage/queue/ledger, no network, no credential access, no writes."""

    MODULE = PIN_PY.read_text(encoding="utf-8")
    SCRIPT = EXEC_SH.read_text(encoding="utf-8")

    def test_module_has_no_network_storage_or_credential_surface(self):
        for forbidden in ("import socket", "import urllib", "import requests",
                          "import http", "urlopen", "requests.", "sqlite",
                          "open(", "os.remove", "subprocess", "getenv",
                          "environ", "boto3"):
            self.assertNotIn(forbidden, self.MODULE,
                             f"module must not reference {forbidden!r}")

    def test_script_has_no_network_write_or_ledger_surface(self):
        # Scan executable lines only; stderr redirection (>&2) and the pure
        # local case-fold pipe are the two allowed shapes.
        body = "\n".join(
            line for line in self.SCRIPT.splitlines()
            if line.strip() and not line.strip().startswith("#"))
        body = (body.replace(">&2", "")
                    .replace("| tr '[:upper:]' '[:lower:]'", ""))
        for forbidden in ("curl", "wget", " ssh", "nc ", "python", "http",
                          "mktemp", "tee ", "ledger", ">>", ">", "exec",
                          "$("):
            self.assertNotIn(forbidden, body,
                             f"script must not reference {forbidden!r}")

    def test_script_creates_nothing_and_always_refuses(self):
        with tempfile.TemporaryDirectory(prefix="explabs-pin-contract-") as tmp:
            cwd = Path(tmp)
            prompt = cwd / "packet.txt"
            prompt.write_text("bounded scaffold packet", encoding="utf-8")
            before = sorted(p.name for p in cwd.iterdir())
            env = {
                **{k: v for k, v in os.environ.items()
                   if not k.startswith("EXPERIENTIAL_")},
                "EXPERIENTIAL_MANUAL_PIN": "glm-5.3-uncensored",
                "EXPERIENTIAL_PROVIDER_ENABLED": "1",
                "EXPERIENTIAL_ENTITLEMENT_VERIFIED": "1",
                "EXPERIENTIAL_RETENTION_ACKNOWLEDGED": "1",
                "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN": "1",
                "EXPERIENTIAL_ACCOUNT": "b",
                "EXPERIENTIAL_QUOTA_READBACK": "authenticated",
                "EXPERIENTIAL_GATEWAY_VERIFIED": "1",
            }
            proc = subprocess.run(
                ["/bin/sh", str(EXEC_SH), str(cwd), "glm-5.3-uncensored",
                 str(prompt)],
                cwd=str(cwd), env=env, capture_output=True, text=True,
                timeout=30)
            self.assertEqual(proc.returncode, 78)
            self.assertIn("EXPERIENTIAL_TRANSPORT_NOT_INSTALLED", proc.stderr)
            after = sorted(p.name for p in cwd.iterdir())
            self.assertEqual(before, after, "scaffold must be zero-write")


class ExecScaffoldGateTests(unittest.TestCase):
    """Each missing gate maps to exactly one typed refusal."""

    def run_script(self, *extra_env, model="glm-5.3-uncensored", pin_value="glm-5.3-uncensored"):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("EXPERIENTIAL_")}
        env["EXPERIENTIAL_MANUAL_PIN"] = pin_value
        for item in extra_env:
            key, _, value = item.partition("=")
            env[key] = value
        with tempfile.TemporaryDirectory(prefix="explabs-gate-") as tmp:
            packet = Path(tmp) / "packet.txt"
            packet.write_text("x", encoding="utf-8")
            return subprocess.run(
                ["/bin/sh", str(EXEC_SH), tmp, model, str(packet)],
                env=env, capture_output=True, text=True, timeout=30)

    def expect_refusal(self, reason, *env, **kwargs):
        proc = self.run_script(*env, **kwargs)
        self.assertEqual(proc.returncode, 78, proc.stderr)
        self.assertIn(f"reason={reason}", proc.stderr)
        return proc

    def test_strict_pin_mismatch_refused(self):
        self.expect_refusal("EXPERIENTIAL_STRICT_PIN_MISSING",
                            model="glm-5.3-uncensored", pin_value="")
        self.expect_refusal("EXPERIENTIAL_STRICT_PIN_MISMATCH",
                            model="glm-5.3-uncensored", pin_value="glm-5.3-flashx")
        self.expect_refusal("EXPERIENTIAL_GLM_CARRIER_REFUSED",
                            model="glm-5.3-uncensored", pin_value="glm")
        # Canonical Z.AI slugs get the distinctness refusal, not a typo code.
        self.expect_refusal("EXPERIENTIAL_MODEL_DISTINCT",
                            model="glm-5.3-uncensored", pin_value="glm-5.3")
        self.expect_refusal("EXPERIENTIAL_MODEL_DISTINCT",
                            model="glm-5.3-uncensored", pin_value="glm-5.3-flash")
        self.expect_refusal("EXPERIENTIAL_MODEL_SLUG_MISMATCH",
                            model="glm-5.3-flash", pin_value="glm-5.3-uncensored")
        self.expect_refusal("EXPERIENTIAL_MODEL_SLUG_MISMATCH",
                            model="glm-5.3", pin_value="glm-5.3-uncensored")

    def test_disabled_provider_refused(self):
        self.expect_refusal("PROVIDER_DISABLED")

    def test_missing_entitlement_refused(self):
        self.expect_refusal("ENTITLEMENT_UNVERIFIED",
                            "EXPERIENTIAL_PROVIDER_ENABLED=1")

    def test_sensitive_data_hold(self):
        self.expect_refusal("RETENTION_UNVERIFIED",
                            "EXPERIENTIAL_PROVIDER_ENABLED=1",
                            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1")
        self.expect_refusal("SENSITIVE_DATA_DISCLOSURE_REQUIRED",
                            "EXPERIENTIAL_PROVIDER_ENABLED=1",
                            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
                            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1")

    def test_proprietary_code_opt_in_independent(self):
        self.expect_refusal(
            "PROPRIETARY_CODE_EXPOSURE_REFUSED",
            "EXPERIENTIAL_PROVIDER_ENABLED=1",
            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1",
            "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN=1",
            "EXPERIENTIAL_PROPRIETARY_CODE=1")
        proc = self.run_script(
            "EXPERIENTIAL_PROVIDER_ENABLED=1",
            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1",
            "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN=1",
            "EXPERIENTIAL_PROPRIETARY_CODE=1",
            "EXPERIENTIAL_CODE_EXPOSURE_OPT_IN=1",
            "EXPERIENTIAL_ACCOUNT=b")
        self.assertIn("QUOTA_READBACK_UNAUTHENTICATED", proc.stderr)

    def test_account_a_stays_held(self):
        self.expect_refusal(
            "ACCOUNT_A_HELD_HTTP403",
            "EXPERIENTIAL_PROVIDER_ENABLED=1",
            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1",
            "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN=1",
            "EXPERIENTIAL_ACCOUNT=a")

    def test_account_b_unknown_quota_blocks_execution(self):
        self.expect_refusal(
            "QUOTA_READBACK_UNAUTHENTICATED",
            "EXPERIENTIAL_PROVIDER_ENABLED=1",
            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1",
            "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN=1",
            "EXPERIENTIAL_ACCOUNT=b",
            "EXPERIENTIAL_QUOTA_READBACK=not_authenticated")

    def test_unverified_gateway_blocks_execution(self):
        self.expect_refusal(
            "EXPERIENTIAL_GATEWAY_UNVERIFIED",
            "EXPERIENTIAL_PROVIDER_ENABLED=1",
            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1",
            "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN=1",
            "EXPERIENTIAL_ACCOUNT=b",
            "EXPERIENTIAL_QUOTA_READBACK=authenticated")

    def test_transport_refusal_is_absolute(self):
        proc = self.expect_refusal(
            "EXPERIENTIAL_TRANSPORT_NOT_INSTALLED",
            "EXPERIENTIAL_PROVIDER_ENABLED=1",
            "EXPERIENTIAL_ENTITLEMENT_VERIFIED=1",
            "EXPERIENTIAL_RETENTION_ACKNOWLEDGED=1",
            "EXPERIENTIAL_SENSITIVE_DATA_OPT_IN=1",
            "EXPERIENTIAL_ACCOUNT=b",
            "EXPERIENTIAL_QUOTA_READBACK=authenticated",
            "EXPERIENTIAL_GATEWAY_VERIFIED=1")
        self.assertNotIn("key", proc.stdout.lower())
        self.assertNotIn("token", proc.stdout.lower())


class CliContractTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(PIN_PY), *args],
            capture_output=True, text=True, timeout=30)

    def test_preview_exact_pin(self):
        proc = self.cli("preview", "--id", "explabs-cli-01", "--class",
                        "fix_build", "--pool", "experiential", "--model",
                        "glm-5.3-uncensored")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("POOL=experiential", proc.stdout)
        self.assertIn("MODEL=glm-5.3-uncensored", proc.stdout)
        self.assertIn("STATE=PREVIEW_ONLY", proc.stdout)
        self.assertIn("KEY=-", proc.stdout)

    def test_preview_wrong_pin_refuses_with_exit_78(self):
        proc = self.cli("preview", "--id", "explabs-cli-02", "--class",
                        "fix_build", "--pool", "glm", "--model",
                        "glm-5.3-uncensored")
        self.assertEqual(proc.returncode, 78)
        self.assertIn("NONE reason=GLM_POOL_CARRIER_REFUSED", proc.stderr)

    def test_admit_all_gates_still_refuses_transport(self):
        proc = self.cli(
            "admit", "--pool", "experiential", "--model",
            "glm-5.3-uncensored", "--class", "fix_build",
            "--registry-enabled", "--entitlement-verified",
            "--retention-acknowledged", "--sensitive-data-opt-in",
            "--account", "b", "--quota-readback", "authenticated")
        self.assertEqual(proc.returncode, 78)
        self.assertIn("EXPERIENTIAL_TRANSPORT_NOT_INSTALLED", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_auto_path_is_none(self):
        proc = self.cli("auto", "--class", "fix_build")
        self.assertEqual(proc.returncode, 78)
        self.assertIn("NONE reason=experiential_manual_only", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

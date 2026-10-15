from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import control_plane.worker_craft as worker_craft
from control_plane.worker_craft import (
    CRAFT_BEGIN,
    CraftPromptError,
    apply_craft_to_prompt,
    extract_job_packet,
    load_craft_method,
    materialize_launch_spec,
    materialize_worker_commission,
    resolve_craft_role,
)
from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerProcessRef


ROOT = Path(__file__).resolve().parents[1]
CRAFT_ROOT = ROOT / "research" / "worker_craft" / "mastermind-craft"
COMMISSION_REQUEST = ROOT / "research" / "worker_craft" / "examples" / "ceo-commission-request.json"
COMMISSION_GOLDEN = ROOT / "research" / "worker_craft" / "examples" / "ceo-commission.md"
COMMISSION_RECEIPT = ROOT / "research" / "worker_craft" / "examples" / "ceo-commission-receipt.json"


def _prompt(
    *,
    department: str = "frontend",
    task_kind: str = "implementation",
    orchestration=None,
) -> str:
    packet = {
        "schema_version": "mastermind.executive_job_packet/v1",
        "job_id": "job-1",
        "run_id": "run-1",
        "worker_id": "worker-1",
        "objective": "bounded fixture objective",
        "department": department,
        "task_kind": task_kind,
        "authorities": ["READ"],
        "allowed_write_paths": [],
        "validation_commands": [],
    }
    if orchestration is not None:
        packet["orchestration"] = orchestration
    return "fixture preamble\n\n" + json.dumps(packet, sort_keys=True, indent=2)


def _spec(prompt: str | None = None) -> WorkerLaunchSpec:
    root = Path(tempfile.gettempdir())
    return WorkerLaunchSpec(
        run_id="run-1",
        job_id="job-1",
        worker_id="worker-1",
        workspace_path=root,
        run_dir=root,
        prompt=prompt or _prompt(),
        result_schema_path=root / "schema.json",
        authorities=("READ",),
        model="preselected-provider-neutral-model-value",
        reasoning_effort="medium",
        expected_base_sha="0" * 40,
    )


class _Adapter:
    """Minimal existing provider consumer; Craft never wraps or registers it."""

    adapter_id = "fixture-reviewed-adapter"

    def __init__(self) -> None:
        self.started: list[WorkerLaunchSpec] = []

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        self.started.append(spec)
        return WorkerProcessRef(
            run_id=spec.run_id,
            pid=123,
            pgid=123,
            process_start_identity="fixture",
            boot_session_id="fixture",
            launch_nonce="fixture",
            provider_session_id=None,
            stdout_path="out",
            stderr_path="err",
            result_path="result",
            started_at="2026-09-18T00:00:00Z",
            binary=None,  # type: ignore[arg-type]
            base_sha="0" * 40,
        )


class WorkerCraftTest(unittest.TestCase):
    def test_all_roles_load_exactly_one_role_method(self) -> None:
        roles = (
            "orchestrator",
            "designer",
            "frontend",
            "backend",
            "researcher",
            "data-scientist",
            "reviewer",
            "verifier",
        )
        for role in roles:
            text, receipt = load_craft_method(role, root=CRAFT_ROOT)
            self.assertEqual(receipt.role, role)
            self.assertFalse(receipt.native_skill_attested)
            self.assertIn("# Shared craft boundary", text)
            self.assertIn(CRAFT_BEGIN, text)
            self.assertEqual(len(receipt.method_digest), 64)
        frontend, _ = load_craft_method("frontend", root=CRAFT_ROOT)
        self.assertIn("# Frontend engineer", frontend)
        self.assertNotIn("# Backend/data engineer", frontend)

    def test_role_resolution_uses_structured_fields_not_objective(self) -> None:
        self.assertEqual(
            resolve_craft_role({"department": "product-design", "task_kind": "implementation"}),
            "designer",
        )
        self.assertEqual(
            resolve_craft_role({"department": "frontend", "task_kind": "implementation"}),
            "frontend",
        )
        self.assertEqual(
            resolve_craft_role({"department": "x", "task_kind": "research"}),
            "researcher",
        )
        self.assertEqual(
            resolve_craft_role({"department": "x", "task_kind": "tests"}),
            "verifier",
        )
        self.assertEqual(
            resolve_craft_role(
                {
                    "department": "frontend",
                    "task_kind": "implementation",
                    "orchestration": {"role": "plan"},
                }
            ),
            "orchestrator",
        )
        with self.assertRaisesRegex(CraftPromptError, "craft_role_invalid"):
            resolve_craft_role({"department": "frontend"}, fixed_role="anything")

    def test_prompt_materialization_preserves_job_packet(self) -> None:
        original = _prompt(department="frontend")
        original_packet, _, _ = extract_job_packet(original)
        crafted, application = apply_craft_to_prompt(original, root=CRAFT_ROOT)
        crafted_packet, _, _ = extract_job_packet(crafted)
        self.assertEqual(crafted_packet, original_packet)
        self.assertEqual(application.receipt.role, "frontend")
        self.assertIn("# Frontend engineer", crafted)
        self.assertLess(
            crafted.index(CRAFT_BEGIN),
            crafted.index('"schema_version": "mastermind.executive_job_packet/v1"'),
        )
        self.assertNotEqual(
            application.original_prompt_sha256,
            application.crafted_prompt_sha256,
        )

    def test_duplicate_and_missing_packet_refuse(self) -> None:
        crafted, _ = apply_craft_to_prompt(_prompt(), root=CRAFT_ROOT)
        with self.assertRaisesRegex(CraftPromptError, "already_materialized"):
            apply_craft_to_prompt(crafted, root=CRAFT_ROOT)
        with self.assertRaisesRegex(CraftPromptError, "job_packet_missing"):
            apply_craft_to_prompt("not a job packet", root=CRAFT_ROOT)

    def test_symlink_method_source_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "mastermind-craft"
            shutil.copytree(CRAFT_ROOT, root)
            role = root / "references" / "frontend.md"
            target = root / "references" / "backend.md"
            role.unlink()
            role.symlink_to(target.name)
            with self.assertRaisesRegex(CraftPromptError, "craft_source_invalid"):
                load_craft_method("frontend", root=root)

    def test_launch_materialization_is_pure_and_preserves_all_non_prompt_fields(self) -> None:
        spec = _spec()
        materialized = materialize_launch_spec(spec, root=CRAFT_ROOT)
        self.assertIsNot(materialized.launch_spec, spec)
        self.assertEqual(
            dataclasses.replace(materialized.launch_spec, prompt=spec.prompt),
            spec,
        )
        self.assertIn("# Frontend engineer", materialized.launch_spec.prompt)
        self.assertEqual(materialized.application.receipt.role, "frontend")
        self.assertFalse(hasattr(worker_craft, "CraftWorkerAdapter"))

    def test_fixed_role_materialization_uses_requested_method_only(self) -> None:
        materialized = materialize_launch_spec(
            _spec(),
            fixed_role="reviewer",
            root=CRAFT_ROOT,
        )
        self.assertIn("# Adversarial reviewer", materialized.launch_spec.prompt)
        self.assertNotIn("# Frontend engineer", materialized.launch_spec.prompt)

    def test_commission_materialization_matches_587_golden_exactly(self) -> None:
        request = json.loads(COMMISSION_REQUEST.read_text())
        receipt = json.loads(COMMISSION_RECEIPT.read_text())
        materialized = materialize_worker_commission(request, root=CRAFT_ROOT)
        self.assertEqual(materialized.commission_bytes, COMMISSION_GOLDEN.read_bytes())
        self.assertEqual(materialized.commission_sha256, receipt["commission_sha256"])
        self.assertEqual(
            materialized.compact_input_sha256,
            receipt["compact_input_sha256"],
        )
        self.assertEqual(
            materialized.normalized_brief_sha256,
            receipt["normalized_brief_sha256"],
        )
        self.assertEqual(materialized.method_sha256, receipt["method_sha256"])
        self.assertEqual(
            materialized.compiler_sha256,
            hashlib.sha256((CRAFT_ROOT / "scripts" / "brief.py").read_bytes()).hexdigest(),
        )

    def test_commission_materialization_does_not_mutate_request(self) -> None:
        request = json.loads(COMMISSION_REQUEST.read_text())
        before = deepcopy(request)
        materialize_worker_commission(request, root=CRAFT_ROOT)
        self.assertEqual(request, before)

    def test_commission_refusal_stays_closed(self) -> None:
        request = json.loads(COMMISSION_REQUEST.read_text())
        request["provider"] = "must-not-route-here"
        with self.assertRaisesRegex(
            CraftPromptError,
            r"craft_commission_refused:commission\.fields",
        ):
            materialize_worker_commission(request, root=CRAFT_ROOT)
        request = json.loads(COMMISSION_REQUEST.read_text())
        request["acceptance"] = []
        with self.assertRaisesRegex(
            CraftPromptError,
            r"craft_commission_refused:acceptance\.list",
        ):
            materialize_worker_commission(request, root=CRAFT_ROOT)

    def test_commission_receipt_carries_no_provider_or_account_route(self) -> None:
        request = json.loads(COMMISSION_REQUEST.read_text())
        materialized = materialize_worker_commission(request, root=CRAFT_ROOT)
        self.assertEqual(
            set(dataclasses.asdict(materialized)),
            {
                "role",
                "commission_bytes",
                "commission_sha256",
                "compact_input_sha256",
                "normalized_brief_sha256",
                "method_sha256",
                "compiler_sha256",
            },
        )

    def test_compiler_symlink_refuses_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "mastermind-craft"
            shutil.copytree(CRAFT_ROOT, root)
            compiler = root / "scripts" / "brief.py"
            compiler.unlink()
            compiler.symlink_to("../SKILL.md")
            request = json.loads(COMMISSION_REQUEST.read_text())
            with self.assertRaisesRegex(CraftPromptError, "craft_source_invalid"):
                materialize_worker_commission(request, root=root)

    def test_mutation_silent_provider_selection_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "mastermind-craft"
            shutil.copytree(CRAFT_ROOT, root)
            compiler = root / "scripts" / "brief.py"
            text = compiler.read_text()
            needle = '"provider_selection": "NOT_PERFORMED"'
            self.assertIn(needle, text)
            compiler.write_text(
                text.replace(needle, '"provider_selection": "SILENT_DEFAULT"', 1)
            )
            request = json.loads(COMMISSION_REQUEST.read_text())
            with self.assertRaisesRegex(
                CraftPromptError,
                "craft_commission_compiler_contract_invalid",
            ):
                materialize_worker_commission(request, root=root)


class WorkerCraftProviderConsumptionTest(unittest.IsolatedAsyncioTestCase):
    async def test_original_adapter_object_consumes_materialized_spec(self) -> None:
        adapter = _Adapter()
        identity = id(adapter)
        materialized = materialize_launch_spec(_spec(), root=CRAFT_ROOT)

        ref = await adapter.start(materialized.launch_spec)

        self.assertEqual(id(adapter), identity)
        self.assertEqual(ref.run_id, materialized.launch_spec.run_id)
        self.assertEqual(len(adapter.started), 1)
        self.assertIs(adapter.started[0], materialized.launch_spec)
        self.assertIn("# Frontend engineer", adapter.started[0].prompt)

    async def test_materialized_spec_is_snapshot_if_method_source_later_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "mastermind-craft"
            shutil.copytree(CRAFT_ROOT, root)
            first = materialize_launch_spec(_spec(), root=root)
            first_prompt = first.launch_spec.prompt
            frontend = root / "references" / "frontend.md"
            frontend.write_text(frontend.read_text() + "\nchanged\n")
            second = materialize_launch_spec(_spec(), root=root)
            self.assertEqual(first.launch_spec.prompt, first_prompt)
            self.assertNotEqual(
                first.application.receipt.method_digest,
                second.application.receipt.method_digest,
            )


if __name__ == "__main__":
    unittest.main()

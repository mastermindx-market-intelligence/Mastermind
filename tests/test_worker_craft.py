from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from control_plane.worker_craft import (
    CRAFT_BEGIN,
    CraftPromptError,
    CraftWorkerAdapter,
    apply_craft_to_prompt,
    extract_job_packet,
    load_craft_method,
    resolve_craft_role,
)
from control_plane.worker_execution_contract import (
    CancelReceipt,
    CollectionReceipt,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
)

CRAFT_ROOT = Path(__file__).resolve().parents[1] / "research" / "worker_craft" / "mastermind-craft"


def _prompt(*, department: str = "frontend", task_kind: str = "implementation", orchestration=None) -> str:
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
    )


class _Inspector:
    pass


class _Adapter:
    def __init__(self) -> None:
        self.inspector = _Inspector()
        self.started: list[WorkerLaunchSpec] = []
        self.validated: list[WorkerLaunchSpec] = []

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
            started_at="2026-09-13T00:00:00Z",
            binary=None,  # type: ignore[arg-type]
            base_sha="0" * 40,
        )

    async def collect_result(self, ref):
        return "collection"  # type: ignore[return-value]

    async def cancel(self, ref, reason):
        return "cancel"  # type: ignore[return-value]

    async def run_validation_argv(self, spec, argv, *, timeout_seconds=300.0):
        self.validated.append(spec)
        return "validation"  # type: ignore[return-value]

    async def status(self, ref):
        return "RUNNING"


class WorkerCraftTest(unittest.TestCase):
    def test_all_roles_load_exactly_one_role_method(self) -> None:
        roles = (
            "orchestrator", "designer", "frontend", "backend", "researcher",
            "data-scientist", "reviewer", "verifier",
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
        self.assertEqual(resolve_craft_role({"department": "product-design", "task_kind": "implementation"}), "designer")
        self.assertEqual(resolve_craft_role({"department": "frontend", "task_kind": "implementation"}), "frontend")
        self.assertEqual(resolve_craft_role({"department": "x", "task_kind": "research"}), "researcher")
        self.assertEqual(resolve_craft_role({"department": "x", "task_kind": "tests"}), "verifier")
        self.assertEqual(resolve_craft_role({"department": "x", "task_kind": "implementation"}), "backend")
        self.assertEqual(resolve_craft_role({"department": "frontend", "task_kind": "implementation", "orchestration": {"role": "plan"}}), "orchestrator")
        self.assertEqual(resolve_craft_role({"department": "frontend", "task_kind": "implementation"}, fixed_role="reviewer"), "reviewer")
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
        self.assertLess(crafted.index(CRAFT_BEGIN), crafted.index('"schema_version": "mastermind.executive_job_packet/v1"'))
        self.assertNotEqual(application.original_prompt_sha256, application.crafted_prompt_sha256)

    def test_duplicate_and_missing_packet_refuse(self) -> None:
        crafted, _ = apply_craft_to_prompt(_prompt(), root=CRAFT_ROOT)
        with self.assertRaisesRegex(CraftPromptError, "already_materialized"):
            apply_craft_to_prompt(crafted, root=CRAFT_ROOT)
        with self.assertRaisesRegex(CraftPromptError, "job_packet_missing"):
            apply_craft_to_prompt("not a job packet", root=CRAFT_ROOT)

    def test_symlink_source_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "mastermind-craft"
            shutil.copytree(CRAFT_ROOT, root)
            role = root / "references" / "frontend.md"
            target = root / "references" / "backend.md"
            role.unlink()
            role.symlink_to(target.name)
            with self.assertRaisesRegex(CraftPromptError, "craft_source_invalid"):
                load_craft_method("frontend", root=root)


class WorkerCraftAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_wrapper_delivers_method_to_underlying_adapter(self) -> None:
        underlying = _Adapter()
        wrapper = CraftWorkerAdapter(underlying, craft_root=CRAFT_ROOT)
        spec = _spec()
        ref = await wrapper.start(spec)
        self.assertEqual(ref.run_id, spec.run_id)
        self.assertEqual(len(underlying.started), 1)
        self.assertNotEqual(underlying.started[0].prompt, spec.prompt)
        self.assertIn("# Frontend engineer", underlying.started[0].prompt)
        self.assertEqual(wrapper.craft_application(spec.run_id).receipt.role, "frontend")
        self.assertEqual(await wrapper.status(ref), "RUNNING")
        await wrapper.run_validation_argv(spec, ("/usr/bin/true",))
        self.assertEqual(underlying.validated[0].prompt, underlying.started[0].prompt)

    async def test_fixed_role_and_duplicate_start_refuse(self) -> None:
        underlying = _Adapter()
        wrapper = CraftWorkerAdapter(underlying, role="reviewer", craft_root=CRAFT_ROOT)
        spec = _spec()
        await wrapper.start(spec)
        self.assertIn("# Adversarial reviewer", underlying.started[0].prompt)
        with self.assertRaisesRegex(CraftPromptError, "already_materialized"):
            await wrapper.start(spec)

    async def test_source_drift_after_start_refuses_validation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "mastermind-craft"
            shutil.copytree(CRAFT_ROOT, root)
            underlying = _Adapter()
            wrapper = CraftWorkerAdapter(underlying, craft_root=root)
            spec = _spec()
            await wrapper.start(spec)
            frontend = root / "references" / "frontend.md"
            frontend.write_text(frontend.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
            with self.assertRaisesRegex(CraftPromptError, "source_drifted"):
                await wrapper.run_validation_argv(spec, ("/usr/bin/true",))

    async def test_changed_launch_spec_refuses_validation(self) -> None:
        underlying = _Adapter()
        wrapper = CraftWorkerAdapter(underlying, craft_root=CRAFT_ROOT)
        spec = _spec()
        await wrapper.start(spec)
        changed = dataclasses.replace(spec, model="different")
        with self.assertRaisesRegex(CraftPromptError, "launch_spec_drifted"):
            await wrapper.run_validation_argv(changed, ("/usr/bin/true",))


if __name__ == "__main__":
    unittest.main()

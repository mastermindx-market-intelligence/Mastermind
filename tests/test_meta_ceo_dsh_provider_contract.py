"""Actual pinned DSH join proof. Missing donor is an explicit skip, never a pass."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from control_plane.paid_model_execution_contract import compile_request, descriptor

DONOR_SHA = "687f282e8625c6b8d11ff58211a90524be2e4317"
FIXTURE_DIR = ROOT / "integrations/deepseek_harness/provider_qualification"


def compiler_vectors():
    """Use incumbent compilers/validators, without any execution or admission."""
    source = ROOT / "ops/native_fabric/quota_continuity/candidate/paid_glm_model_client.py"
    spec = importlib.util.spec_from_file_location("dsh_fixture_model_client", source)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    vectors = []
    for model, prompt in [
        ("glm-5.3", "Analyze only this supplied fixture text."),
        ("glm-5.3-flash", "Fixture with Unicode: café / 東京 / 🧭.\nNo tools."),
    ]:
        payload = {
            "binding": {
                "root_id": "fixture-root", "job_id": "fixture-child",
                "attempt_id": "fixture-attempt",
                "effective_grant_digest": "1" * 64, "commission_sha256": "2" * 64,
            },
            "physical_binding_sha256": "3" * 64,
            "launch_spec": {
                "job_id": "fixture-child", "run_id": "fixture-attempt",
                "effective_grant_digest": "1" * 64, "model": model,
                "prompt": prompt, "timeout_seconds": 30,
                "authorities": ["READ"], "allowed_artifact_paths": [],
            },
            "validation_commands": [],
            "paid_route": {
                "provider": "glm", "host_ref": "fixture-host",
                "model": model, "parent_job_id": "fixture-root",
            },
            "paid_input": {
                "prompt": prompt,
                "result_schema": {
                    "type": "object", "required": ["answer"],
                    "properties": {"answer": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        }
        body = compile_request(payload)
        client.validate_body(body, model)
        output_text = json.dumps({"answer": "Complete fixture: café / 東京."}, ensure_ascii=False)
        response = {
            "status": "completed",
            "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": output_text}],
            }],
        }
        result = client.result_bytes(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        vectors.append({
            "schema": "mastermind.dsh_sealed_analysis_fixture/v1",
            "prompt": prompt, "requestBody": body.decode("utf-8"),
            "descriptor": descriptor(payload),
            "resultText": result.decode("utf-8"),
            "resultSha256": hashlib.sha256(result).hexdigest(),
        })
    return vectors


class NativeDshProviderContractTests(unittest.TestCase):
    def test_actual_pinned_dsh_boundary(self):
        supplied = os.environ.get("MMX_DSH_DONOR_ROOT")
        if not supplied:
            self.skipTest("MMX_DSH_DONOR_ROOT absent: actual DSH proof NOT RUN")
        donor = Path(supplied).resolve(strict=True)

        def git(*args):
            return subprocess.check_output(
                ["git", "--no-optional-locks", "-C", str(donor), *args],
                text=True, timeout=20,
            ).strip()

        self.assertEqual(git("rev-parse", "HEAD"), DONOR_SHA, "wrong full-app donor pin")
        before = git("status", "--porcelain", "--untracked-files=no")
        self.assertEqual(before, "", "donor tracked source must be clean")
        loader = donor / "node_modules/tsx/dist/loader.mjs"
        self.assertTrue(loader.is_file(), "use the already-built pinned donor dependency closure")
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node required for actual native fixture")
        command = [
            node, "--test-reporter=tap", "--import", str(loader),
            str(FIXTURE_DIR / "sealed_analysis_contract.test.mjs"), str(donor),
        ]
        result = subprocess.run(
            command, input=json.dumps(compiler_vectors(), ensure_ascii=False),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
            cwd=ROOT,
        )
        self.assertEqual(git("status", "--porcelain", "--untracked-files=no"), before)
        self.assertEqual(result.returncode, 0, result.stdout[:6500] + "\n...\n" + result.stdout[-1200:])
        self.assertIn("# fail 0", result.stdout)
        self.assertIn("# skipped 0", result.stdout)
        source_paths = [
            "packages/llm/llm/src/index.ts",
            "packages/llm/llm/src/assembler.ts",
            "packages/llm/llm/src/retry-policy.ts",
            "vendor/cordis/lib/index.js",
        ]
        evidence = {
            "claim": "SOURCE_CONTRACT_QUALIFIED / FIXTURE_ONLY",
            "donor_sha": DONOR_SHA,
            "entrypoint": "packages/llm/llm/src/index.ts",
            "source_and_cordis_sha256": {
                path: hashlib.sha256((donor / path).read_bytes()).hexdigest()
                for path in source_paths
            },
            "live_provider_calls": 0,
            "usage": None, "served_model": None,
            "admission": False, "parent_acceptance": False,
        }
        print(json.dumps(evidence, sort_keys=True))
        print("\n".join(result.stdout.splitlines()[-10:]))


if __name__ == "__main__":
    unittest.main()

"""Qualify a frozen app consumer against real temporary MCP/Unix/Runtime.

Run after installing the repository's test Python and npm dependencies:
  .venv/bin/python -B tests/fixtures/mastermind_os_launch_cross_layer_probe.py \
      --consumer-ref <exact Git SHA> --output <report.json>

An optional --consumer-patch is applied only to the temporary source snapshot.
The original manifest and patch digest remain in the report. A failed recovery
still produces its observed report and exits nonzero. This does not qualify the
installed client, host authentication composition, persistence, or execution.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import test_executive_mcp_launch_journey as journey

CONSUMER_PATHS = (
    "app/mastermind_os/src/orchestration/operation-key.ts",
    "app/mastermind_os/src/orchestration/executive-launch-command-port.ts",
    "app/mastermind_os/src/orchestration/operation-controller.ts",
    "app/mastermind_os/src/mission.ts",
    "app/mastermind_os/src/workspace-contract.ts",
)
PATCH_PATH = CONSUMER_PATHS[1]


def _read_message(process):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=10):
            raise AssertionError("consumer did not return a bounded protocol message")
    line = process.stdout.readline()
    if not line:
        raise AssertionError("consumer exited before its result: " + process.stderr.read())
    return json.loads(line)


def _case(profile, lose_reply, strict_v2, key, root, port, controller):
    scenario = "lost-reply" if lose_reply else "accepted"
    process = subprocess.Popen(
        [shutil.which("node"), str(ROOT / "tests/fixtures/mastermind_os_launch_client_probe.mjs"),
         str(port), str(controller), scenario],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    original_call, original_payload = journey._call, journey.PAYLOAD
    try:
        expected = _read_message(process)
        assert expected["type"] == "call" and expected["name"] == "submit_ceo_intent"
        journey.PAYLOAD = expected["args"]
        consumer_result = None
        producer_evidence = []

        async def forward(client, token, name, arguments):
            nonlocal expected, consumer_result
            result, envelope = await original_call(client, token, name, arguments)
            is_submit = name == "submit_ceo_intent" and envelope.get("status") in {
                "accepted", "effect_unknown"}
            is_status = name == "ceo_intent_status" and expected.get("type") == "call"
            if is_submit or is_status:
                assert expected["type"] == "call", expected
                assert (expected["name"], expected["args"]) == (name, arguments)
                receipt = envelope.get("receipt", envelope.get("data")) or {}
                producer_evidence.append({
                    "tool": name, "server_version": envelope.get("server_version"),
                    "receipt_schema": receipt.get("schema"), "work_ref": receipt.get("work_ref"),
                    "envelope_sha256": hashlib.sha256(
                        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                })
                process.stdin.write(json.dumps({"id": expected["id"], "envelope": envelope}) + "\n")
                process.stdin.flush()
                expected = await asyncio.to_thread(_read_message, process)
                if expected["type"] == "result":
                    consumer_result = expected
            return result, envelope

        journey._call = forward
        with tempfile.TemporaryDirectory(prefix="mmxl-", dir="/tmp") as socket_dir:
            journey.test_real_launch_survives_reopen_without_another_submit(
                profile, lose_reply, key, root, Path(socket_dir), strict_v2=strict_v2)
        process.stdin.close()
        assert process.wait(timeout=10) == 0, process.stderr.read()
        assert consumer_result is not None
        return {"profile": profile, "receipt_mode": "strict-v2" if strict_v2 else "legacy",
                **consumer_result, "actual_producer_envelopes": producer_evidence,
                "backend_jobs": 1, "backend_attempts": 0, "backend_workers": 0,
                "backend_submit_frames": 1}
    finally:
        journey._call, journey.PAYLOAD = original_call, original_payload
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def _apply_snapshot_patch(path, source):
    patch = path.read_text()
    headers = [line.split("\t", 1)[0] for line in patch.splitlines()
               if line.startswith(("--- ", "+++ "))]
    if headers != ["--- a/" + PATCH_PATH, "+++ b/" + PATCH_PATH]:
        raise ValueError("patch must modify only the frozen launch command port")
    subprocess.run(["git", "apply", "--check", str(path)], cwd=source,
                   check=True, capture_output=True, text=True, timeout=10)
    subprocess.run(["git", "apply", str(path)], cwd=source,
                   check=True, capture_output=True, text=True, timeout=10)
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "target": PATCH_PATH,
            "patched_source_sha256": hashlib.sha256((source / PATCH_PATH).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer-ref", required=True)
    parser.add_argument("--consumer-patch", type=Path)
    parser.add_argument("--receipt-mode", choices=("legacy", "strict-v2", "both"), default="both")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.consumer_ref) is None:
        parser.error("--consumer-ref must be an exact 40-character Git commit")
    bundler = ROOT / "app/mastermind_os/node_modules/.bin/rolldown"
    if not bundler.is_file() or shutil.which("node") is None:
        parser.error("run npm ci --include=dev --ignore-scripts in app/mastermind_os first")
    manifest, results, patch_evidence = {}, [], None
    with tempfile.TemporaryDirectory(prefix="mmx-app-contract-") as temp:
        scratch = Path(temp)
        source = scratch / "source"
        for relative in CONSUMER_PATHS:
            data = subprocess.check_output(["git", "show", args.consumer_ref + ":" + relative], cwd=ROOT)
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if args.consumer_patch:
            patch_evidence = _apply_snapshot_patch(args.consumer_patch.resolve(), source)
        modules = {}
        for name in ("executive-launch-command-port", "operation-controller"):
            entry = source / "app/mastermind_os/src/orchestration" / (name + ".ts")
            destination = scratch / (name + ".mjs")
            subprocess.run([str(bundler), str(entry), "--file", str(destination),
                            "--format", "esm", "--platform", "node"], check=True,
                           capture_output=True, text=True, timeout=30)
            modules[name] = destination
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        receipt_modes = (False, True) if args.receipt_mode == "both" else (args.receipt_mode == "strict-v2",)
        for strict_v2 in receipt_modes:
            for profile in ("web_ceo_v2", "web_ceo_v3"):
                for lose_reply in (False, True):
                    case_root = scratch / (profile + ("-v2" if strict_v2 else "-v1") +
                                           ("-lost" if lose_reply else "-accepted"))
                    case_root.mkdir()
                    result = _case(profile, lose_reply, strict_v2, key, case_root,
                        modules["executive-launch-command-port"], modules["operation-controller"])
                    results.append(result)
                    print(json.dumps({key: result[key] for key in (
                        "profile", "receipt_mode", "scenario", "final_state", "compatibility_passed"
                    )}), flush=True)
    passed = sum(case["compatibility_passed"] for case in results)
    report = {"scope": "temporary authenticated component integration; no production/provider effects",
              "consumer_ref": args.consumer_ref, "consumer_source": manifest,
              "consumer_patch": patch_evidence, "cases": results,
              "passed": passed, "failed": len(results) - passed,
              "positive_version_controls_passed": sum(
                  len(case.get("positive_version_controls", ())) for case in results
              ),
              "negative_controls_passed": sum(len(case["negative_controls"]) for case in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failed": len(results) - passed,
                      "report": str(args.output),
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

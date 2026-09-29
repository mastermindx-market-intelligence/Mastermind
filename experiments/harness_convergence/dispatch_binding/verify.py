"""Offline, provider-free RED/GREEN, compatibility and mutation verification."""
from __future__ import annotations

import datetime as dt
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from prepare import CACHE, MANIFEST, ROOT, digest, prepare

EXPECTED_RED = {
    "replace-before-body", "revoke-before-body",
    "replace-during-body-post-value", "replace-during-body-wrapper-value",
    "replace-before-body-name-only", "guard-throws-late", "queued-revocation",
    "remove-during-body-post-value",
    "strict binding rejects own-scope shadowing during the wrapper",
}
NODE = shutil.which("node")
if NODE is None:
    raise SystemExit("Node is required; this verifier never installs executables")
ENV = {
    "PATH": str(Path(NODE).parent) + ":/usr/bin:/bin", "CI": "1",
    "HOME": str(CACHE / "home"), "TMPDIR": str(CACHE / "tmp"),
}


def run(name: str, arguments: list[str], source: str = "1", timeout: int = 60) -> tuple[subprocess.CompletedProcess, dict]:
    result = subprocess.run([NODE, *arguments], cwd=ROOT,
                            env={**ENV, "MMX_DSH_SOURCE": source},
                            capture_output=True, text=True, timeout=timeout, check=False)
    output = result.stdout + result.stderr
    path = CACHE / f"{name}.log"
    path.write_text(output)
    return result, {"exit_code": result.returncode, "log": path.name,
                    "log_sha256": digest(output.encode()), "stderr_empty": not result.stderr}


def targeted(name: str, source: str, expected: set[str]) -> dict:
    result, receipt = run(name, ["--test", "--test-reporter=tap", "dispatch-binding.test.mjs"], source)
    cases = re.findall(r"^(ok|not ok) \d+ - (.+)$", result.stdout, re.MULTILINE)
    failed = {title for state, title in cases if state == "not ok"}
    assert len(cases) == 19, f"{name}: missing/extra cases: {len(cases)}"
    assert failed == expected, f"{name}: failure mismatch: {sorted(failed)}"
    assert result.returncode == (1 if expected else 0), f"{name}: unexpected test exit"
    assert not result.stderr, f"{name}: unexpected stderr"
    assert "# skipped 0" in result.stdout and "# cancelled 0" in result.stdout
    observed = json.loads((CACHE / f"observations-{source}.json").read_text())
    observations = {name: value for name, value in observed.items() if name in EXPECTED_RED}
    return {**receipt, "tests": len(cases), "passed": len(cases) - len(failed),
            "failed_cases": sorted(failed), "observations": observations}


def upstream(name: str, source: str) -> dict:
    target = CACHE / f"{name}.json"
    result, receipt = run(name, ["node_modules/vitest/vitest.mjs", "run", "--config",
                               "vitest.config.mjs", "--reporter=json", f"--outputFile={target}"], source)
    data = json.loads(target.read_text())
    assert result.returncode == 0 and data["success"], f"{name}: suite failed"
    assert data["numTotalTests"] == data["numPassedTests"] == 178
    assert data["numFailedTests"] == data["numPendingTests"] == 0
    assert not result.stderr
    return {**receipt, "tests": 178, "passed": 178, "failed": 0,
            "report_sha256": digest(target.read_bytes())}


def mutation(name: str, old: str, new: str, expected: set[str]) -> dict:
    original = (CACHE / "donor/index.ts").read_text()
    assert original.count(old) == 1, f"{name}: mutation target not unique"
    mutant = original.replace(old, new)
    destination = CACHE / "mutant"
    destination.mkdir(exist_ok=True)
    for path in (CACHE / "donor").glob("*.ts"):
        (destination / path.name).write_bytes(path.read_bytes())
    (destination / "index.ts").write_text(mutant)
    result = targeted(name, "mutant", expected)
    assert (CACHE / "donor/index.ts").read_text() == original
    return {**result, "mutant_sha256": digest(mutant.encode()), "killed": True}


def loaded_preflight() -> dict:
    """Exercise the actual runtime instance, including three partially broken patches."""
    original = (CACHE / "donor/index.ts").read_text()
    defects = {
        "guard": ("const reason = this.guardReason(exec)",
                  "const reason: string | undefined = undefined"),
        "definition": ("this.strictDispatchBinding && tool !== this.preparedDefinitions.get(exec)",
                       "false && tool !== this.preparedDefinitions.get(exec)"),
        "result": ("? this.preparedDefinitions.get(exec)",
                   "? this.resolveExecution(exec.name, exec.agent, exec.parent !== undefined)"),
    }
    hashes = {}
    for name, (old, new) in defects.items():
        assert original.count(old) == 1, f"Preflight defect target is not unique: {name}"
        destination = CACHE / "preflight-defects" / name
        destination.mkdir(parents=True, exist_ok=True)
        for path in (CACHE / "donor").glob("*.ts"):
            (destination / path.name).write_bytes(path.read_bytes())
        changed = original.replace(old, new).encode()
        (destination / "index.ts").write_bytes(changed)
        hashes[name] = digest(changed)
    result, receipt = run("loaded-preflight", ["--test", "--test-reporter=tap",
                                              "loaded-runtime-preflight.test.mjs"])
    cases = re.findall(r"^(ok|not ok) \d+ - (.+)$", result.stdout, re.MULTILINE)
    assert len(cases) == 17 and all(state == "ok" for state, _ in cases), "Loaded preflight failed"
    assert result.returncode == 0 and not result.stderr
    assert "# skipped 0" in result.stdout and "# cancelled 0" in result.stdout
    assert (CACHE / "donor/index.ts").read_text() == original
    return {**receipt, "tests": 17, "passed": 17, "defect_source_sha256": hashes,
            "cases": [name for _, name in cases],
            "scope": "Actual ToolRuntime instance, in-memory probes, not installed ACP qualification"}


def main() -> dict:
    supply = prepare(download=False)
    assert digest((ROOT / "package-lock.json").read_bytes()) == MANIFEST["npm_lock_sha256"]
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True, check=True, timeout=5, env=ENV).stdout.strip()
    report = {"schema": "mastermind.dsh_dispatch_verification.v1",
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "node": version, "node_sha256": digest(Path(NODE).resolve().read_bytes()),
              "platform": platform.system(), "architecture": platform.machine(), "python": sys.version.split()[0],
              "supply": supply, "provider_calls": 0, "test_leaf_effects": "IN_MEMORY_ONLY"}
    report["targeted"] = {
        "published_baseline": targeted("baseline-npm", "npm", EXPECTED_RED),
        "source_baseline": targeted("baseline-source", "pristine", EXPECTED_RED),
        "patched": targeted("patched-targeted", "1", set()),
    }
    report["loaded_runtime_preflight"] = loaded_preflight()
    report["upstream"] = {mode: upstream(f"upstream-{mode}", source)
                          for mode, source in [("pristine", "pristine"), ("patched", "1")]}
    result, receipt = run("typecheck", ["node_modules/typescript/bin/tsc", "-p", "tsconfig.json"])
    assert result.returncode == 0 and not result.stdout and not result.stderr, "Typecheck failed"
    report["typecheck"] = receipt
    report["mutants"] = {
        "remove_guard_recheck": mutation(
            "mutant-guard", "const reason = this.guardReason(exec)", "const reason: string | undefined = undefined",
            {"revoke-before-body", "guard-throws-late", "queued-revocation"}),
        "remove_definition_check": mutation(
            "mutant-definition", "this.strictDispatchBinding && tool !== this.preparedDefinitions.get(exec)",
            "false && tool !== this.preparedDefinitions.get(exec)",
            {"replace-before-body-name-only", "strict binding rejects own-scope shadowing during the wrapper"}),
        "remove_result_binding": mutation(
            "mutant-result", "? this.preparedDefinitions.get(exec)",
            "? this.resolveExecution(exec.name, exec.agent, exec.parent !== undefined)",
            {"replace-during-body-post-value", "replace-during-body-wrapper-value", "remove-during-body-post-value"}),
    }
    assert digest((CACHE / "donor/index.ts").read_bytes()) == MANIFEST["patched_index_sha256"]
    report["input_sha256"] = {name: digest((ROOT / name).read_bytes()) for name in [
        "dispatch-binding.test.mjs", "strict-dispatch-binding.patch", "package-lock.json",
        "donor-manifest.json", "prepare.py", "verify.py", "vitest.config.mjs", "tsconfig.json", "package.json",
        "qualify-loaded-runtime.mjs", "loaded-runtime-preflight.test.mjs"]}
    report["success"] = True
    return report


if __name__ == "__main__":
    report = main()
    destination = CACHE / "verification-report.json"
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"success": True, "targeted_passed": report["targeted"]["patched"]["passed"],
                      "upstream_passed": report["upstream"]["patched"]["passed"],
                      "loaded_preflight_passed": report["loaded_runtime_preflight"]["passed"],
                      "mutants_killed": len(report["mutants"]), "report": str(destination)}, indent=2))

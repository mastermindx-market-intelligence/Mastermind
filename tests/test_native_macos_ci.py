"""Source contracts for unsigned native CI; these do not prove a Mac build."""

from pathlib import Path
import re
import shlex

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ".github/workflows/mastermind-os.yml"
TEST_PATH = "tests/test_native_macos_ci.py"


def workflow():
    # BaseLoader preserves GitHub's YAML 1.2 `on` key as a string.
    return yaml.load((ROOT / WORKFLOW_PATH).read_text(), Loader=yaml.BaseLoader)


def native_job():
    jobs = workflow()["jobs"]
    assert "native-macos" in jobs, "native Rust/package coverage must not be frontend-only"
    return jobs["native-macos"]


def commands(job):
    return [step["run"] for step in job["steps"] if "run" in step]


def test_native_job_is_independent_and_failure_enforcing():
    job = native_job()
    assert job["runs-on"] == "macos-15"
    assert 1 <= int(job["timeout-minutes"]) <= 60
    assert job["defaults"]["run"]["working-directory"] == "app/mastermind_os"
    assert not any(key in job for key in ("needs", "if", "continue-on-error"))
    assert all("continue-on-error" not in step for step in job["steps"])


def test_existing_frontend_gate_is_preserved():
    job = workflow()["jobs"]["frontend"]
    assert job["runs-on"] == "ubuntu-latest"
    assert commands(job) == ["npm ci", "npm run typecheck", "npm test", "npm run build"]


def test_node_pin_supports_the_locked_dependency_engines():
    for job in workflow()["jobs"].values():
        setup = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/setup-node@"))
        assert setup["with"]["node-version"] == "22.23.3"


def test_trigger_paths_do_not_resemble_reserved_account_literals():
    for event in ("pull_request", "push"):
        for path in workflow()["on"][event]["paths"]:
            assert "_mastermind_" not in path


def test_workflow_and_test_changes_trigger_the_gate_without_write_permissions():
    config = workflow()
    assert config["permissions"] == {"contents": "read"}
    assert set(config["on"]) == {"pull_request", "merge_group", "push", "workflow_dispatch"}
    for event in ("pull_request", "push"):
        assert set(config["on"][event]["paths"]) == {
            "app/mastermind_os/**", WORKFLOW_PATH, TEST_PATH
        }
    assert config["on"]["push"]["branches"] == ["master"]
    assert config["on"]["merge_group"]["types"] == ["checks_requested"]


def test_build_identity_matches_checkout_and_toolchain_is_exact():
    job = native_job()
    env = job["env"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", env["RUSTUP_TOOLCHAIN"])
    assert env["MM_SOURCE_REVISION"] == "${{ github.sha }}"
    assert env["MM_BUILD_IDENTITY"] == "ci-native-${{ github.run_id }}-${{ github.run_attempt }}"
    assert "CARGO_TARGET_DIR" not in env
    assert 'echo "CARGO_TARGET_DIR=$RUNNER_TEMP/mastermind-os-target" >> "$GITHUB_ENV"' in commands(job)
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert "ref" not in checkout.get("with", {})
    assert 'rustup toolchain install "$RUSTUP_TOOLCHAIN" --profile minimal' in commands(job)


def test_job_environment_uses_only_admitted_expression_contexts():
    # runner is available to steps, but not jobs.<job_id>.env. Generic YAML
    # parsers accept that mistake while GitHub rejects the entire workflow.
    allowed = {"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"}
    for value in native_job()["env"].values():
        for context in re.findall(r"\$\{\{\s*(\w+)\.", value):
            assert context in allowed, f"{context} is unavailable in job-level env"


def test_native_assets_precede_locked_rust_checks_and_tests():
    runs = commands(native_job())
    assert "npm ci" in runs
    assets = runs.index("npm run build -- --mode native")
    for subcommand in ("check", "test"):
        command = next(run for run in runs if run.startswith(f"cargo {subcommand} "))
        tokens = shlex.split(command)
        assert "--locked" in tokens and "--all-targets" in tokens
        assert tokens[tokens.index("--manifest-path") + 1] == "src-tauri/Cargo.toml"
        assert assets < runs.index(command)


def test_package_is_unsigned_locked_verified_and_not_published():
    job = native_job()
    runs = commands(job)
    package = next(run for run in runs if run.startswith("./node_modules/.bin/tauri build "))
    assert shlex.split(package) == [
        "./node_modules/.bin/tauri", "build", "--ci", "--no-sign", "--bundles", "app", "--", "--locked"
    ]
    assert runs.index(package) > next(i for i, run in enumerate(runs) if run.startswith("cargo test "))
    verification = runs[-1]
    assert 'test -s "$bundle/Contents/Info.plist"' in verification
    assert 'test -x "$bundle/Contents/MacOS/mastermind-os"' in verification
    assert "git diff --exit-code -- package-lock.json src-tauri/Cargo.lock" in verification
    assert 'shasum -a 256 "$bundle/Contents/MacOS/mastermind-os"' in verification
    assert {step["uses"] for step in job["steps"] if "uses" in step} == {
        "actions/checkout@v4", "actions/setup-node@v4"
    }
    assert "permissions" not in job
    assert "MM_NATIVE_CLIENT_ID" not in job["env"]
    raw = (ROOT / WORKFLOW_PATH).read_text()
    assert "secrets." not in raw
    assert not any(token in raw for token in ("upload-artifact", "tauri-action", "gh release", "notarytool"))

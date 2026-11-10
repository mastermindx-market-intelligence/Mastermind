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
    assert commands(job)[:3] == ["npm ci", "npm run typecheck", "npm test"]
    assert "npm run build" in commands(job)[3]
    assert all("continue-on-error" not in step for step in job["steps"])


def test_frontend_build_uses_exact_app_only_production_source_closure():
    job = workflow()["jobs"]["frontend"]
    build = next(step for step in job["steps"]
                 if step.get("name") == "Build exact app-only release archive")
    assert build["working-directory"] == "."
    command = build["run"]
    for required in (
        'release_root="$(mktemp -d "$RUNNER_TEMP/mmos-release.XXXXXX")"',
        'git archive "$GITHUB_SHA" app/mastermind_os | tar -x -C "$release_root"',
        'cd "$release_root/app/mastermind_os"',
        "npm ci --ignore-scripts",
        "npm run build",
        'test -s "$release_root/app/mastermind_os/dist/index.html"',
        'PYTHONPATH="$GITHUB_WORKSPACE" python3 -c',
        'from ops.executive_os.executive_mcp_entry import build_os_asset_manifest',
        'build_os_asset_manifest(Path(sys.argv[1]))',
        'rm -rf "$GITHUB_WORKSPACE/app/mastermind_os/dist"',
        'cp -R "$release_root/app/mastermind_os/dist" "$GITHUB_WORKSPACE/app/mastermind_os/dist"',
    ):
        assert required in command
    assert command.index('test -s "$release_root/app/mastermind_os/dist/index.html"') < command.index(
        'build_os_asset_manifest(Path(sys.argv[1]))'
    ) < command.index('rm -rf "$GITHUB_WORKSPACE/app/mastermind_os/dist"')
    assert command.index('rm -rf "$GITHUB_WORKSPACE/app/mastermind_os/dist"') < command.index(
        'cp -R "$release_root/app/mastermind_os/dist" "$GITHUB_WORKSPACE/app/mastermind_os/dist"'
    )
    assert "|| true" not in command
    assert not any("continue-on-error" in step for step in job["steps"])


def test_compiled_browser_evidence_is_separate_bounded_and_source_bound():
    job = workflow()["jobs"]["frontend"]
    runs = commands(job)
    assert len(runs) == 7
    assert runs[4] == "npx vite build --config vite.browser-proof.config.ts"
    receipt = runs[6]
    for field in (
        'schema: "mastermind.os.compiled_test_receipt.v1"',
        "source_revision: process.env.GITHUB_SHA",
        "run_id: process.env.GITHUB_RUN_ID",
        "run_attempt: process.env.GITHUB_RUN_ATTEMPT",
        "live_acceptance: false",
        '["dist", "dist-browser-proof"]',
    ):
        assert field in receipt
    uploads = [step for step in job["steps"]
               if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert {step["with"]["path"] for step in uploads} == {
        "app/mastermind_os/dist", "app/mastermind_os/dist-browser-proof",
        "${{ runner.temp }}/mastermind-app-control-proof",
    }
    assert len(uploads) == 3
    receipt_index = next(i for i, step in enumerate(job["steps"])
                         if step.get("run") == receipt)
    for step in uploads:
        assert step["uses"] == "actions/upload-artifact@v4"
        assert step["with"]["name"].endswith("-${{ github.sha }}")
        assert step["with"]["if-no-files-found"] == "error"
        assert 1 <= int(step["with"]["retention-days"]) <= 7
        assert job["steps"].index(step) > receipt_index
        assert "if" not in step and "continue-on-error" not in step


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
            "app/mastermind_os/**", WORKFLOW_PATH, TEST_PATH,
            "integrations/worker_browser_runtime/app-control/**",
            "integrations/workbench_browser_mcp/**",
            "integrations/workbench_action_mcp/service.py",
            "control_plane/browser_resource_contract.py",
            "tests/test_os_app_control_profile.py",
            "tests/test_workbench_browser_port.py",
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


def test_native_rotation_executes_in_ci_and_package_builds_enabled():
    job = native_job()
    runs = commands(job)
    standard = "cargo test --locked --all-targets --manifest-path src-tauri/Cargo.toml"
    enabled_check = "MM_NATIVE_REFRESH_ENABLED=1 cargo check --locked --all-targets --manifest-path src-tauri/Cargo.toml"
    enabled_test = "MM_NATIVE_REFRESH_ENABLED=1 cargo test --locked --all-targets --manifest-path src-tauri/Cargo.toml"
    package = ("MM_NATIVE_REFRESH_ENABLED=1 ./node_modules/.bin/tauri build "
               "--ci --no-sign --bundles app -- --locked")
    assert runs.count(standard) == 1
    assert runs.count(enabled_check) == 1
    assert runs.count(enabled_test) == 1
    assert runs.count(package) == 1
    assert runs.index(standard) < runs.index(enabled_check) < runs.index(enabled_test) < runs.index(package)
    # The flag enables only the source path per-step; no registered client or
    # tenant credential may enter the CI environment.
    assert "MM_NATIVE_REFRESH_ENABLED" not in job["env"]
    assert "MM_NATIVE_CLIENT_ID" not in job["env"]


def test_package_is_unsigned_locked_verified_and_not_published():
    job = native_job()
    runs = commands(job)
    package = next(run for run in runs if "./node_modules/.bin/tauri build" in run)
    assert shlex.split(package) == [
        "MM_NATIVE_REFRESH_ENABLED=1",
        "./node_modules/.bin/tauri", "build", "--ci", "--no-sign", "--bundles", "app", "--", "--locked"
    ]
    assert runs.index(package) > next(i for i, run in enumerate(runs) if run.startswith("cargo test "))
    seal = next(step for step in job["steps"]
                if step.get("name") == "Ad-hoc seal the unsigned app and strictly verify")
    assert runs.index(seal["run"]) == runs.index(package) + 1
    assert '/usr/bin/codesign --force --deep --sign - --identifier com.mastermind.os "$bundle"' in seal["run"]
    assert '/usr/bin/codesign --verify --deep --strict --verbose=2 "$bundle"' in seal["run"]
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
    assert not any(token in raw for token in ("tauri-action", "gh release", "notarytool"))
    assert "upload-artifact" not in yaml.safe_dump(job)

from __future__ import annotations

import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
SCRIPT = OPS / "prepare-capacity-host.sh"
RUNBOOK = OPS / "HOST_PREREQUISITES.md"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_capacity_preparer_is_executable_and_shell_syntax_valid() -> None:
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & 0o111
    completed = subprocess.run(
        ["/bin/bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_capacity_preparer_inventory_renderer_is_native_and_executable() -> None:
    renderer_paths = []
    for line in _source().splitlines():
        if "expected_inventory=\"$(" in line or "EXPECTED_RUNTIME_BIN_INVENTORY=\"$(" in line:
            renderer_paths.append(line.split('"$(', 1)[1].split(" ", 1)[0])

    assert renderer_paths == ["/usr/bin/printf"] * 3
    completed = subprocess.run(
        [renderer_paths[0], "%s\\n", "z", "a"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "z\na\n"


def test_capacity_preparer_pins_exact_source_runtime_and_entrypoint_inputs() -> None:
    source = _source()
    for exact in (
        'MACRO_COMMIT="dcdd939c45b23abce5ba04f95e330ac914a3904b"',
        'MATERIAL_SOURCE_DIGEST="35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650"',
        'PYYAML_WHEEL="pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl"',
        'PYYAML_WHEEL_SHA256="fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0"',
        'PYYAML_RECORD_SHA256="715146d21711444bc73c3137d18cffb6e38ace40e8998c5a9dfa69bd7dc46e3e"',
        'RUNTIME_TREE_SHA256="79e1e4dc67c0fbefc266fcf2c27b98a7e0aeff5048e015fae11b20115ee864ee"',
        'CODEX_VERSION="0.147.0"',
        'CODEX_SHA256="19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"',
    ):
        assert exact in source
    assert "MACRO_ORIGIN" not in source


def test_capacity_preparer_closes_host_and_reviewed_mastermind_before_mutation() -> None:
    source = _source()
    mutation = source.index('MUTATION_STARTED="true"')
    for check in (
        '"$(/usr/bin/id -u)" -eq 0',
        '"$(/usr/bin/uname -s)" = "Darwin"',
        '/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse HEAD',
        '/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" status --porcelain=v1 --untracked-files=all',
        'Mastermind source contains a non-root-owned object',
        'Mastermind source contains a group/other-writable object',
        'Mastermind source contains a hard-linked file',
        'Mastermind source parent must be root:wheel',
        'assert_no_acl "$MASTERMIND_SOURCE_REPO"',
        'assert_no_unapproved_xattrs "$MASTERMIND_SOURCE_REPO"',
        'expected Mastermind SHA must contain exactly 40 lowercase hexadecimal characters',
        '"$PYTHON_PROVISIONER" --verify-only',
    ):
        assert source.index(check) < mutation
    assert 'SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && /bin/pwd)"' in source
    assert 'MASTERMIND_SOURCE_REPO="$(cd "$SCRIPT_DIR/../.." && /bin/pwd -P)"' in source


def test_capacity_preparer_accepts_only_two_closed_operator_files() -> None:
    source = _source()
    for exact in (
        "--macro-transport-sha256",
        "Macro transport must be one direct single-link file",
        "PyYAML wheel must be one direct single-link file",
        "Macro transport must be owned by the named operator",
        "PyYAML wheel must be owned by the named operator",
        "Macro transport must not be group/other writable",
        "PyYAML wheel must not be group/other writable",
        '"$ARTIFACTS" copy-closed-input',
        '--operator-uid "$OPERATOR_UID" --expected-sha256 "$MACRO_TRANSPORT_SHA256"',
        '--operator-uid "$OPERATOR_UID" --expected-sha256 "$PYYAML_WHEEL_SHA256"',
        "closed Macro transport metadata differs",
        "closed PyYAML wheel metadata differs",
        "Macro transport digest differs",
        "PyYAML wheel digest differs",
        "materialize-source-transport",
        "verify-materialized-source",
    ):
        assert exact in source
    for forbidden in ("ditto", "cp -R", "copytree", "MACRO_ORIGIN", "remote get-url"):
        assert forbidden not in source
    for material_path in (
        "config/capability_manifest.yml",
        "config/metabolism_budget.yml",
        "engine/codex_lane/runner.py",
        "engine/codex_provider.py",
        "engine/llm_auth.py",
        "engine/metabolism/budget_gate.py",
        "engine/neuralweb/key_pool.py",
        "engine/provider_capacity.py",
        "engine/provider_health.py",
        "lib/ai_costs.py",
        "scripts/build_provider_capacity.py",
    ):
        assert material_path in source


def test_capacity_preparer_builds_a_pip_free_content_closed_runtime() -> None:
    source = _source()
    assert '"$PYTHON_BINARY" -I -S -B -m venv --copies --without-pip "$RUNTIME_STAGE"' in source
    assert "EXPECTED_RUNTIME_BIN_INVENTORY=" in source
    assert '/bin/rmdir "$RUNTIME_STAGE/include/python3.12"' in source
    assert '/bin/rmdir "$RUNTIME_STAGE/include"' in source
    assert "extract-pyyaml-wheel" in source
    assert "verify-runtime-tree" in source
    assert '"$tree_digest" = "$RUNTIME_TREE_SHA256"' in source
    assert '"$record_digest" = "$PYYAML_RECORD_SHA256"' in source
    assert 'PYTHONNOUSERSITE=1 "$root/bin/python3.12" -I -B' in source
    assert "site.ENABLE_USER_SITE" in source
    assert "-m pip install" not in source
    assert "ensurepip" not in source


def test_capacity_preparer_uses_recoverable_staging_and_no_recursive_deletion() -> None:
    source = _source()
    assert 'STAGING_ROOT="$SYSTEM_ROOT/capacity-staging"' in source
    assert 'ARCHIVE_ROOT="$SYSTEM_ROOT/capacity-archive"' in source
    assert "trap cleanup EXIT" in source
    assert "archive_path()" in source
    assert 'NEW_VERSIONED_PATHS=()' in source
    assert 'NEW_TOPOLOGY_PATHS=()' in source
    assert '/bin/mv "$SOURCE_STAGE" "$SOURCE_ROOT"' in source
    assert '/bin/mv "$RUNTIME_STAGE" "$RUNTIME_ROOT"' in source
    assert "rm -rf" not in source
    assert "rm -R" not in source


def test_capacity_preparer_cleanup_guards_empty_arrays_for_macos_bash() -> None:
    cleanup = _source().split("cleanup() {", 1)[1].split("trap cleanup EXIT", 1)[0]
    topology_guard = 'if [ "${#NEW_TOPOLOGY_PATHS[@]}" -gt 0 ]; then'
    versioned_guard = 'if [ "${#NEW_VERSIONED_PATHS[@]}" -gt 0 ]; then'
    topology_loop = 'for path in "${NEW_TOPOLOGY_PATHS[@]}"; do'
    versioned_loop = 'for path in "${NEW_VERSIONED_PATHS[@]}"; do'
    assert topology_guard in cleanup
    assert versioned_guard in cleanup
    assert cleanup.index(topology_guard) < cleanup.index(topology_loop)
    assert cleanup.index(versioned_guard) < cleanup.index(versioned_loop)
    completed = subprocess.run(
        [
            "/bin/bash",
            "-uc",
            'paths=(); if [ "${#paths[@]}" -gt 0 ]; then '
            'for path in "${paths[@]}"; do :; done; fi',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "unbound variable" not in completed.stderr


def test_capacity_preparer_refuses_foreign_telemetry_without_mutating_it() -> None:
    source = _source()
    preflight = 'verify_telemetry_boundary || refuse "pre-existing Provider Control telemetry root is not the exact canonical absence boundary"'
    mutation = 'MUTATION_STARTED="true"'
    creation = '/usr/bin/install -d -o root -g wheel -m 0755 "$TELEMETRY_STAGE"'
    assert source.index(preflight) < source.index(mutation) < source.index(creation)
    telemetry_block = source.split('if [ "$CREATE_TELEMETRY_ROOT" = "true" ]; then', 1)[1].split("fi", 1)[0]
    assert creation in telemetry_block
    assert 'verify_telemetry_boundary "$TELEMETRY_STAGE"' in telemetry_block
    assert '/bin/mv "$TELEMETRY_STAGE" "$TELEMETRY_ROOT"' in telemetry_block
    verifier = source.split("verify_telemetry_boundary() {", 1)[1].split("\n}", 1)[0]
    assert '-mindepth 1 -type d' in verifier
    assert "-maxdepth" not in verifier


def test_capacity_preparer_recovers_interrupted_partial_topology_on_same_carrier() -> None:
    source = _source()
    artifacts_source = (OPS / "capacity_host_artifacts.py").read_text(encoding="utf-8")
    assert "/usr/bin/shlock" in source
    assert "collect_interrupted_h0_targets" in source
    assert "recover_interrupted_h0" in source
    assert "reconcile_recovery_archives" in source
    assert "create-recovery-intent" in source
    assert "resume-recovery-archive" in source
    assert ".recovery-intent.json.candidate" in source
    assert "PENDING_RECOVERY_INTENT_ARCHIVE" in source
    assert "INTERRUPTED_H0_PARTIAL_RECOVERED" in artifacts_source
    assert "same_carrier_preparation_resumed" in artifacts_source
    assert "_publish_resumable_canonical_file" in artifacts_source
    assert "_fsync_directory(source.parent)" in artifacts_source
    assert "_fsync_directory(archive)" in artifacts_source
    assert "interrupted H0 label could not be made disabled and unloaded" in source
    assert "interrupted H0 state contains a socket-path object" in source
    assert "an H0 topology target already exists without an accepted generation" not in source


def test_capacity_preparer_legacy_digest_ignores_unrelated_launchd_labels() -> None:
    source = _source()
    function = source.split("current_legacy_state_digest() {", 1)[1].split("\n}", 1)[0]
    assert 'for label in "${LEGACY_LABELS[@]}"' in function
    assert "label_persistently_disabled" in function
    assert "unrelated_launchd" not in function
    for slot_id in ("codex-pro-01", "codex-pro-02", "codex-pro-03"):
        assert slot_id not in function


def test_capacity_preparer_accepts_only_exact_launchctl_disabled_spellings() -> None:
    source = _source()
    helper = source.split("label_persistently_disabled() {", 1)[1].split("\n}", 1)[0]
    assert "print-disabled system" in helper
    assert "check-launchctl-disabled" in helper
    assert '=> true' not in source


def test_capacity_preparer_installs_exactly_three_inert_broker_definitions() -> None:
    source = _source()
    assert 'PERSONAL_PRO_SLOT_IDS=("codex-pro-01" "codex-pro-02" "codex-pro-03")' in source
    for slot_id in ("codex-pro-01", "codex-pro-02", "codex-pro-03"):
        assert f'"com.mastermind.executive.worker.{slot_id}"' in source
    for expected in (
        'slot_field "$slot_id" worker_user',
        'slot_field "$slot_id" worker_group',
        'slot_field "$slot_id" provider_home',
        '/usr/bin/sudo -u "$CONTROL_USER" /bin/test ! -r "$slot_home"',
        '/usr/bin/sudo -u "$CONTROL_USER" /bin/test ! -x "$slot_home"',
        '/bin/launchctl disable "system/$label"',
        '/bin/launchctl bootout "system/$label"',
        "/bin/launchctl print-disabled system",
        '/bin/launchctl print "system/$label"',
        'check-config --config "$config"',
    ):
        assert expected in source
    lowered = source.lower()
    for forbidden in (
        "launchctl enable",
        "launchctl bootstrap",
        "launchctl kickstart",
        "service-control.sh",
    ):
        assert forbidden not in lowered


def test_capacity_preparer_executes_and_binds_a_real_nine_artifact_rollback_drill() -> None:
    source = _source()
    assert 'ROLLBACK_DRILL_ROOT="$ARCHIVE_ROOT/rollback-drill-' in source
    assert 'for path in "${NEW_TOPOLOGY_PATHS[@]}"; do ROLLBACK_INDEX=$((ROLLBACK_INDEX + 1)); /bin/mv "$path"' in source
    assert '"moved_artifact_count": 9' in source
    assert '"outcome": "SHRINK_ONLY_ROLLBACK_PASS"' in source
    assert source.count("install_topology_artifacts") == 3
    assert "rollback-drill-receipt.json" in source
    assert "rollback_drill_receipt_digest" in source


def test_capacity_generation_is_self_contained_and_final_rename_is_commit_point() -> None:
    source = _source()
    for artifact in (
        "components.json",
        "source-config.json",
        "host-preparation-receipt.json",
        "broker-topology.json",
        "rollback-contract.json",
        "rollback-drill-receipt.json",
    ):
        assert artifact in source
    candidate_verify = source.rindex('verify_generation "$GENERATION_CANDIDATE" candidate')
    commit = source.rindex('/bin/mv "$GENERATION_CANDIDATE" "$GENERATION_TARGET"')
    assert candidate_verify < commit
    tail = source[commit:]
    assert "verify_" not in tail
    assert "refuse " not in tail
    assert "/bin/mv" not in tail.split("\n", 1)[1]
    assert 'COMMITTED="true"' in tail
    assert "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED" in tail


def test_capacity_preparer_holds_credentials_provider_calls_routing_and_cf2i() -> None:
    source = _source()
    lowered = source.lower()
    for forbidden in (
        "auth.json",
        "codex login",
        "claude login",
        "grok login",
        "cursor login",
        "capacity-observe/v1",
        "job_claimed",
        "curl ",
        "provider_capacity import",
        "sys.path.insert",
    ):
        assert forbidden not in lowered
    assert "OAuth, routing, worker execution, and CF2-I remain held" in source


def test_capacity_preparer_verify_only_reaches_read_only_host_verification() -> None:
    source = _source()
    branch = source.split('if [ "$VERIFY_ONLY" = "true" ]; then', 1)[1].split("fi", 1)[0]
    assert "verify_installed_host" in branch
    for forbidden in ("install -d", "git init", "ditto", "mv ", "bootstrap-host"):
        assert forbidden not in branch


def test_capacity_preparer_runbook_defers_privilege_until_merged_exact_master() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    section = runbook.split("## CF2-H0 — grounded capacity-source host preparation", 1)[1]
    assert "exact merged `origin/master`" in section
    assert "capacity_host_artifacts.py" in section
    assert "prepare-capacity-host.sh" in section
    assert "--expected-mastermind-sha" in section
    assert "--macro-transport-sha256" in section
    assert "--verify-only" in section
    assert "OAuth" in section
    assert "disabled" in section and "unloaded" in section
    assert "CF2-P0" in section

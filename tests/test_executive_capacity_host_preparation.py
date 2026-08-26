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
        ["/bin/bash", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_capacity_preparer_pins_exact_public_source_and_runtime_inputs() -> None:
    source = _source()
    for exact in (
        'MACRO_ORIGIN="https://github.com/mastermindx-market-intelligence/macro.git"',
        'MACRO_COMMIT="dcdd939c45b23abce5ba04f95e330ac914a3904b"',
        'PYTHON_VERSION="3.12.10"',
        'PYYAML_VERSION="6.0.3"',
        'PYYAML_WHEEL="pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl"',
        (
            'PYYAML_WHEEL_SHA256="fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0"'
        ),
        'SOURCE_CONFIG_SCHEMA="mastermind.executive_capacity_source_config/v1"',
        'HOST_RECEIPT_SCHEMA="mastermind.executive_capacity_host_preparation/v1"',
    ):
        assert exact in source


def test_capacity_preparer_refuses_wrong_host_and_mutable_mastermind_source_before_mutation() -> None:
    source = _source()
    mutation = source.index('MUTATION_STARTED="true"')
    for check in (
        '"$(/usr/bin/id -u)" -eq 0',
        '"$(/usr/bin/uname -s)" = "Darwin"',
        '/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse HEAD',
        '/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" status --porcelain=v1',
        'source tree contains a non-root-owned object',
        'source tree contains a group/other-writable object',
        'expected Mastermind SHA must contain exactly 40 lowercase hexadecimal characters',
    ):
        assert source.index(check) < mutation
    assert 'SCRIPT_DIR="$(/usr/bin/dirname "${BASH_SOURCE[0]}")"' in source
    assert 'MASTERMIND_SOURCE_REPO="$(cd "$SCRIPT_DIR/../.." && /bin/pwd -P)"' in source


def test_capacity_preparer_copies_and_closes_an_exact_sparse_transport_not_a_user_checkout() -> None:
    source = _source()
    assert '/usr/bin/ditto --noqtn "$MACRO_SOURCE_TRANSPORT" "$SOURCE_STAGE"' in source
    assert 'GIT_CONFIG_NOSYSTEM=1' in source
    assert 'GIT_TERMINAL_PROMPT=0' in source
    assert '/usr/bin/git -C "$SOURCE_STAGE" remote get-url origin' in source
    assert '/usr/bin/git -C "$SOURCE_STAGE" remote remove origin' in source
    assert '"$MACRO_ORIGIN"' in source
    assert '/bin/cp -R' not in source
    assert '/usr/bin/cp -R' not in source
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


def test_capacity_preparer_attests_wheel_before_install_and_contains_runtime_origins() -> None:
    source = _source()
    copy = '/usr/bin/ditto --noqtn "$WHEEL_SOURCE" "$WHEEL_STAGE"'
    wheel_hash = 'OBSERVED_WHEEL_SHA256="$(/usr/bin/shasum -a 256 "$WHEEL_STAGE"'
    install = '"$RUNTIME_STAGE/bin/python3.12" -I -B -m pip install'
    assert source.index(copy) < source.index(wheel_hash) < source.index(install)
    assert '"$PYTHON_BINARY" -I -S -B -m venv --copies "$RUNTIME_STAGE"' in source
    assert "--no-index" in source
    assert "--no-deps" in source
    assert "--no-compile" in source
    assert "PYTHONNOUSERSITE=1" in source
    assert "sys.prefix" in source
    assert 'importlib.metadata.distribution("PyYAML")' in source
    assert 'distribution.locate_file("PyYAML-6.0.3.dist-info/RECORD")' in source
    assert "resolve(strict=True)" in source
    assert 'PYYAML_RECORD_SHA256=' in source
    assert '/usr/bin/find "$inspected" ! -user root' in source
    assert '/usr/bin/find "$inspected" -perm +022' in source


def test_capacity_preparer_stages_and_archives_without_recursive_deletion() -> None:
    source = _source()
    assert 'STAGING_ROOT="$SYSTEM_ROOT/capacity-staging"' in source
    assert 'ARCHIVE_ROOT="$SYSTEM_ROOT/capacity-archive"' in source
    assert 'trap cleanup EXIT' in source
    assert 'archive_partial_stage' in source
    assert '/bin/mv "$SOURCE_STAGE" "$SOURCE_ROOT"' in source
    assert '/bin/mv "$RUNTIME_STAGE" "$RUNTIME_ROOT"' in source
    assert 'rm -rf' not in source
    assert 'rm -R' not in source
    assert 'CONFIG_INSTALLED="true"' in source
    assert 'RECEIPT_INSTALLED="true"' in source
    assert 'INSTALL_COMPLETE="true"' in source


def test_capacity_preparer_validates_candidates_before_bootstrap_and_receipt_is_last() -> None:
    source = _source()
    candidate_source = source.index("verify_source_candidate")
    candidate_runtime = source.index("verify_runtime_candidate")
    bootstrap = source.index('"$SCRIPT_DIR/bootstrap-host.sh" --operator-user "$OPERATOR_USER"')
    install_source = source.index('/bin/mv "$SOURCE_STAGE" "$SOURCE_ROOT"')
    receipt = source.index('"$CONTRACT" render')
    generation_move = source.index('/bin/mv "$GENERATION_STAGE" "$GENERATION_TARGET"')
    final_verify = source.rindex("verify_installed_host")
    assert candidate_source < bootstrap
    assert candidate_runtime < bootstrap
    assert bootstrap < install_source < receipt < generation_move < final_verify


def test_capacity_preparer_proves_isolated_empty_realms_and_control_negative_access() -> None:
    source = _source()
    assert 'PERSONAL_PRO_SLOT_IDS=("codex-pro-01" "codex-pro-02" "codex-pro-03")' in source
    assert 'slot_field "$slot_id" worker_user' in source
    assert 'slot_field "$slot_id" worker_group' in source
    assert 'slot_field "$slot_id" provider_home' in source
    assert 'assert_control_outside_group "$slot_group"' in source
    assert 'sudo -u "$CONTROL_USER" /usr/bin/test ! -r "$slot_home"' in source
    assert 'sudo -u "$CONTROL_USER" /usr/bin/test ! -x "$slot_home"' in source
    assert 'realm home contains pre-existing material' in source
    assert 'find "$slot_home" -mindepth 1 -print -quit' in source


def test_capacity_preparer_keeps_credentials_providers_services_and_cf2i_held() -> None:
    source = _source()
    lowered = source.lower()
    for forbidden in (
        "auth.json",
        "codex login",
        "claude login",
        "grok login",
        "cursor login",
        "launchctl bootstrap",
        "launchctl kickstart",
        "launchctl enable",
        "service-control.sh",
        "capacity-observe/v1",
        "job_claimed",
        "curl ",
    ):
        assert forbidden not in lowered
    assert "launchctl" not in lowered
    assert 'credential_state' not in source  # emitted only by the closed contract module


def test_capacity_preparer_verify_only_exits_without_mutation() -> None:
    source = _source()
    branch = source.split('if [ "$VERIFY_ONLY" = "true" ]; then', 1)[1].split("fi", 1)[0]
    assert "verify_installed_host" in branch
    for forbidden in ("install -d", "git init", "ditto", "mv ", "bootstrap-host"):
        assert forbidden not in branch


def test_capacity_preparer_runbook_defers_privilege_until_merged_exact_master() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    section = runbook.split("## CF2-H0 — grounded capacity-source host preparation", 1)[1]
    assert "exact merged `origin/master`" in section
    assert "prepare-capacity-host.sh" in section
    assert "--expected-mastermind-sha" in section
    assert "--verify-only" in section
    assert "OAuth" in section
    assert "services remain stopped" in section
    assert "CF2-P0" in section

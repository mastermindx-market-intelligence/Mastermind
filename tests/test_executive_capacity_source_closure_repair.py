from __future__ import annotations

import hashlib
import os
import select
import shlex
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "repair-capacity-source-closure.sh"
BOOTSTRAP = ROOT / "ops" / "executive_os" / "bootstrap-capacity-source-closure.sh"
RUNBOOK = ROOT / "ops" / "executive_os" / "HOST_PREREQUISITES.md"
DESIGN = (
    ROOT
    / "docs/superpowers/specs/2026-08-27-executive-capacity-cf2-h0-source-closure-repair-design.md"
)
PLAN = (
    ROOT
    / "docs/superpowers/plans/2026-08-27-executive-capacity-cf2-h0-source-closure-repair.md"
)
INVALID = (64, "INVALID_INVOCATION\n", "")
DARWIN_NATIVE = pytest.mark.skipif(
    sys.platform != "darwin", reason="native macOS bootstrap ceremony"
)

CLOSED_BOOTSTRAP_ENVIRONMENT = (
    "HOME=/var/empty",
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG=C",
    "LC_ALL=C",
)

REPAIR_CARRIER_PATHS = (
    "ops/executive_os/repair-capacity-source-closure.sh",
    "ops/executive_os/capacity_host_artifacts.py",
    "ops/executive_os/capacity_source_contract.py",
    "ops/executive_os/provider_worker_slots.py",
    "ops/executive_os/provider_identity_policy.py",
)

PROTECTED_REPAIR_MERGE = "d3499f8bd5dd4ecc0c172c82146acf4e8733ddec"
ACCEPTED_SOURCE_CLOSURE_REPAIR = "e53f524230ffc4e8730c844f6fc319d50a2050f3"
UNRELATED_PROTECTED_DESCENDANT = "f61ced39d47f935b1dea369bd3ed25e06c954d08"
UNRELATED_PROTECTED_DELTA = (
    "docs/sol_skills/WATCHER_ACTION_LOOP.md",
    "tests/test_sol_watcher_action_loop_skill.py",
)


def _run(*arguments: str, environment: dict[str, str] | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["/bin/bash", str(SCRIPT), *arguments],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _run_script(
    script: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["/bin/bash", str(script), *arguments],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    return completed.stdout.strip()


def _tracked_symlink_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "tracked-symlink-repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    vendor = repository / "vendor"
    vendor.mkdir()
    (vendor / "macro").symlink_to("macro_src")
    _git(repository, "add", "vendor/macro")
    _git(repository, "commit", "-qm", "tracked symlink fixture")
    commit = _git(repository, "rev-parse", "HEAD")
    _git(repository, "update-ref", "refs/remotes/origin/master", commit)
    return repository, commit


def _protected_repair_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "protected-repair-repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "fetch", "-q", "--no-tags", str(ROOT), PROTECTED_REPAIR_MERGE)
    _git(repository, "checkout", "-q", "--detach", PROTECTED_REPAIR_MERGE)
    _git(
        repository,
        "update-ref",
        "refs/remotes/origin/master",
        PROTECTED_REPAIR_MERGE,
    )
    return repository


def _two_pin_repository(
    tmp_path: Path,
    *,
    drift: str | None = None,
    protected_carrier: bool = True,
    repair_relation: str = "ancestor",
) -> tuple[Path, str, str]:
    repository = tmp_path / "two-pin-repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")

    for relative in REPAIR_CARRIER_PATHS:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
        destination.chmod(0o755 if relative.endswith(".sh") else 0o644)
    _git(repository, "add", *REPAIR_CARRIER_PATHS)
    _git(repository, "commit", "-qm", "accepted repair A")
    accepted_repair = _git(repository, "rev-parse", "HEAD")

    if drift == "blob":
        changed = repository / REPAIR_CARRIER_PATHS[-1]
        changed.write_bytes(changed.read_bytes() + b"\n# authenticated drift\n")
        _git(repository, "add", REPAIR_CARRIER_PATHS[-1])
    elif drift == "mode":
        changed = repository / REPAIR_CARRIER_PATHS[-1]
        changed.chmod(0o755)
        _git(repository, "add", REPAIR_CARRIER_PATHS[-1])
    else:
        unrelated = repository / "docs" / "unrelated-protected-change.md"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("unrelated protected change\n", encoding="utf-8")
        _git(repository, "add", "docs/unrelated-protected-change.md")
    _git(repository, "commit", "-qm", "protected descendant B")
    carrier_commit = _git(repository, "rev-parse", "HEAD")

    if protected_carrier:
        _git(
            repository,
            "update-ref",
            "refs/remotes/origin/master",
            carrier_commit,
        )
    else:
        _git(
            repository,
            "update-ref",
            "refs/remotes/origin/master",
            accepted_repair,
        )
        _git(repository, "update-ref", "refs/heads/pr-head", carrier_commit)

    if repair_relation == "ancestor":
        repair_commit = accepted_repair
    elif repair_relation == "nonancestor":
        repair_commit = _git(
            repository,
            "commit-tree",
            f"{accepted_repair}^{{tree}}",
            "-m",
            "non-ancestor repair candidate",
        )
        _git(repository, "update-ref", "refs/heads/repair-candidate", repair_commit)
    elif repair_relation == "unreachable":
        repair_commit = "f" * 40
    else:
        raise AssertionError(f"unsupported repair relation: {repair_relation}")
    return repository, repair_commit, carrier_commit


def _run_nonprivileged_checkout_block(
    repository: Path,
    repair_merge_sha: str,
    repair_parent: Path,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    block = next(
        candidate.split("```", 1)[0]
        for candidate in RUNBOOK.read_text(encoding="utf-8").split("```bash\n")[1:]
        if "REPAIR_CHECKOUT=\"$REPAIR_PARENT/mastermind\"" in candidate
    )
    checkout_block = block.split(
        'REPAIR_CARRIER="$REPAIR_PARENT/mastermind-exact-commit.bundle"', 1
    )[0]
    replacements = {
        "MACRO_REPOSITORY=/absolute/path/to/macro": (
            f"MACRO_REPOSITORY={shlex.quote(str(repository))}"
        ),
        "MASTERMIND_REPOSITORY=/absolute/path/to/Mastermind": (
            f"MASTERMIND_REPOSITORY={shlex.quote(str(repository))}"
        ),
        "MACRO_COMMIT=dcdd939c45b23abce5ba04f95e330ac914a3904b": (
            f"MACRO_COMMIT={repair_merge_sha}"
        ),
        "REPAIR_MERGE_SHA='<40-lower-hex-protected-repair-merge-sha>'": (
            f"REPAIR_MERGE_SHA={repair_merge_sha}"
        ),
        'REPAIR_PARENT="$(/usr/bin/mktemp -d '
        '/private/tmp/mastermind-h0-source-repair.XXXXXX)"': (
            f"REPAIR_PARENT={shlex.quote(str(repair_parent))}"
        ),
    }
    for original, replacement in replacements.items():
        assert original in checkout_block
        checkout_block = checkout_block.replace(original, replacement)
    repair_parent.mkdir()
    completed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            checkout_block
            + "/usr/bin/printf '%s\\n' RUNBOOK_CHECKOUT_MATERIALIZED_PASS\n",
        ],
        text=True,
        capture_output=True,
        check=False,
        env={
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    return completed, repair_parent / "mastermind"


def _run_split_nonprivileged_checkout_block(
    repository: Path,
    *,
    carrier_commit_sha: str,
    repair_merge_sha: str,
    repair_parent: Path,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    block = next(
        candidate.split("```", 1)[0]
        for candidate in RUNBOOK.read_text(encoding="utf-8").split("```bash\n")[1:]
        if 'REPAIR_CHECKOUT="$REPAIR_PARENT/mastermind"' in candidate
    )
    checkout_and_bundle_block = block.split('TRANSPORT_PARENT="', 1)[0]
    carrier_declaration = (
        "CARRIER_COMMIT_SHA='<40-lower-hex-current-protected-carrier-sha>'"
    )
    assert carrier_declaration in checkout_and_bundle_block
    checkout_and_bundle_block = checkout_and_bundle_block.replace(
        carrier_declaration,
        f"CARRIER_COMMIT_SHA={carrier_commit_sha}",
    )
    repair_declarations = (
        f"REPAIR_MERGE_SHA={ACCEPTED_SOURCE_CLOSURE_REPAIR}",
        "REPAIR_MERGE_SHA='<40-lower-hex-protected-repair-merge-sha>'",
    )
    repair_declaration = next(
        (
            candidate
            for candidate in repair_declarations
            if candidate in checkout_and_bundle_block
        ),
        None,
    )
    assert repair_declaration is not None
    replacements = {
        "MACRO_REPOSITORY=/absolute/path/to/macro": (
            f"MACRO_REPOSITORY={shlex.quote(str(repository))}"
        ),
        "MASTERMIND_REPOSITORY=/absolute/path/to/Mastermind": (
            f"MASTERMIND_REPOSITORY={shlex.quote(str(repository))}"
        ),
        "MACRO_COMMIT=dcdd939c45b23abce5ba04f95e330ac914a3904b": (
            f"MACRO_COMMIT={carrier_commit_sha}"
        ),
        repair_declaration: f"REPAIR_MERGE_SHA={repair_merge_sha}",
        'REPAIR_PARENT="$(/usr/bin/mktemp -d '
        '/private/tmp/mastermind-h0-source-repair.XXXXXX)"': (
            f"REPAIR_PARENT={shlex.quote(str(repair_parent))}"
        ),
    }
    for original, replacement in replacements.items():
        assert original in checkout_and_bundle_block
        checkout_and_bundle_block = checkout_and_bundle_block.replace(
            original, replacement
        )
    repair_parent.mkdir()
    completed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            checkout_and_bundle_block
            + "/usr/bin/printf '%s\\n' RUNBOOK_TWO_PIN_PASS\n",
        ],
        text=True,
        capture_output=True,
        check=False,
        env={
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    return (
        completed,
        repair_parent / "mastermind",
        repair_parent / "mastermind-exact-commit.bundle",
    )


def _assert_materialized_checkout_is_closed(
    checkout: Path,
    *,
    expected_symlink_blob: bytes,
) -> None:
    materialized_symlink = checkout / "vendor" / "macro"
    assert not materialized_symlink.is_symlink()
    assert materialized_symlink.is_file()
    assert materialized_symlink.read_bytes() == expected_symlink_blob
    assert materialized_symlink.stat().st_nlink == 1
    assert not any(candidate.is_symlink() for candidate in checkout.rglob("*"))
    assert not any(
        candidate.is_file() and candidate.stat().st_nlink > 1
        for candidate in checkout.rglob("*")
    )
    assert (
        _git(
            checkout,
            "-c",
            "core.symlinks=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        == ""
    )


def test_runbook_materializes_tracked_symlink_as_regular_clean_checkout(
    tmp_path: Path,
) -> None:
    repository, commit = _tracked_symlink_repository(tmp_path)

    completed, checkout = _run_nonprivileged_checkout_block(
        repository,
        commit,
        tmp_path / "repair-parent",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "RUNBOOK_CHECKOUT_MATERIALIZED_PASS\n"
    _assert_materialized_checkout_is_closed(
        checkout,
        expected_symlink_blob=b"macro_src",
    )


def test_runbook_materializes_exact_protected_tree_and_preserves_carrier_blobs(
    tmp_path: Path,
) -> None:
    repository = _protected_repair_repository(tmp_path)

    completed, checkout = _run_nonprivileged_checkout_block(
        repository,
        PROTECTED_REPAIR_MERGE,
        tmp_path / "protected-repair-parent",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "RUNBOOK_CHECKOUT_MATERIALIZED_PASS\n"
    _assert_materialized_checkout_is_closed(
        checkout,
        expected_symlink_blob=b"macro_src",
    )
    symlink_mode, _kind, symlink_oid, symlink_path = _git(
        repository,
        "ls-tree",
        PROTECTED_REPAIR_MERGE,
        "--",
        "vendor/macro",
    ).split()
    assert (symlink_mode, symlink_path) == ("120000", "vendor/macro")
    assert _git(checkout, "hash-object", "vendor/macro") == symlink_oid

    for relative in REPAIR_CARRIER_PATHS:
        mode, kind, expected_oid, observed_path = _git(
            repository,
            "ls-tree",
            PROTECTED_REPAIR_MERGE,
            "--",
            relative,
        ).split()
        assert (kind, observed_path) == ("blob", relative)
        assert mode in {"100644", "100755"}
        materialized = checkout / relative
        assert materialized.is_file() and not materialized.is_symlink()
        assert _git(checkout, "hash-object", relative) == expected_oid
        assert stat.S_IMODE(materialized.stat().st_mode) == (
            0o755 if mode == "100755" else 0o644
        )


def test_one_sha_runbook_contract_cannot_represent_current_descendant_and_repair(
    tmp_path: Path,
) -> None:
    repository, repair_commit, carrier_commit = _two_pin_repository(tmp_path)
    assert repair_commit != carrier_commit
    assert _git(repository, "rev-parse", "refs/remotes/origin/master") == carrier_commit

    completed, checkout = _run_nonprivileged_checkout_block(
        repository,
        repair_commit,
        tmp_path / "one-sha-repair-parent",
    )

    assert completed.returncode != 0
    assert not checkout.exists()


def test_two_pin_runbook_accepts_current_descendant_without_relabelling_repair(
    tmp_path: Path,
) -> None:
    repository, repair_commit, carrier_commit = _two_pin_repository(tmp_path)
    repair_parent = tmp_path / "two-pin-repair-parent"

    completed, checkout, carrier = _run_split_nonprivileged_checkout_block(
        repository,
        carrier_commit_sha=carrier_commit,
        repair_merge_sha=repair_commit,
        repair_parent=repair_parent,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.endswith("RUNBOOK_TWO_PIN_PASS\n")
    assert _git(checkout, "rev-parse", "HEAD") == carrier_commit
    assert _git(repository, "bundle", "list-heads", str(carrier)) == (
        f"{carrier_commit} refs/remotes/origin/master"
    )
    for relative in REPAIR_CARRIER_PATHS:
        repair_tree = _git(repository, "ls-tree", repair_commit, "--", relative)
        carrier_tree = _git(repository, "ls-tree", carrier_commit, "--", relative)
        assert carrier_tree == repair_tree
        _mode, _kind, expected_oid, _path = carrier_tree.split()
        assert _git(checkout, "hash-object", relative) == expected_oid


@pytest.mark.parametrize("drift", ("blob", "mode"))
def test_two_pin_runbook_refuses_authenticated_material_drift_before_bundle(
    tmp_path: Path,
    drift: str,
) -> None:
    repository, repair_commit, carrier_commit = _two_pin_repository(
        tmp_path,
        drift=drift,
    )
    drifted_path = REPAIR_CARRIER_PATHS[-1]
    assert _git(repository, "ls-tree", repair_commit, "--", drifted_path) != _git(
        repository,
        "ls-tree",
        carrier_commit,
        "--",
        drifted_path,
    )

    completed, _checkout, carrier = _run_split_nonprivileged_checkout_block(
        repository,
        carrier_commit_sha=carrier_commit,
        repair_merge_sha=repair_commit,
        repair_parent=tmp_path / f"{drift}-drift-repair-parent",
    )

    assert completed.returncode != 0
    assert not carrier.exists()


@pytest.mark.parametrize("repair_relation", ("nonancestor", "unreachable"))
def test_two_pin_runbook_refuses_nonancestor_or_unreachable_repair_before_bundle(
    tmp_path: Path,
    repair_relation: str,
) -> None:
    repository, repair_commit, carrier_commit = _two_pin_repository(
        tmp_path,
        repair_relation=repair_relation,
    )

    completed, _checkout, carrier = _run_split_nonprivileged_checkout_block(
        repository,
        carrier_commit_sha=carrier_commit,
        repair_merge_sha=repair_commit,
        repair_parent=tmp_path / f"{repair_relation}-repair-parent",
    )

    assert completed.returncode != 0
    assert not carrier.exists()


def test_two_pin_runbook_refuses_unprotected_carrier_substitution_before_bundle(
    tmp_path: Path,
) -> None:
    repository, repair_commit, carrier_commit = _two_pin_repository(
        tmp_path,
        protected_carrier=False,
    )
    assert _git(repository, "rev-parse", "refs/remotes/origin/master") == repair_commit
    assert carrier_commit != repair_commit

    completed, _checkout, carrier = _run_split_nonprivileged_checkout_block(
        repository,
        carrier_commit_sha=carrier_commit,
        repair_merge_sha=repair_commit,
        repair_parent=tmp_path / "unprotected-carrier-repair-parent",
    )

    assert completed.returncode != 0
    assert not carrier.exists()


def test_real_protected_pair_has_git_proven_non_h0_drift() -> None:
    _git(
        ROOT,
        "merge-base",
        "--is-ancestor",
        ACCEPTED_SOURCE_CLOSURE_REPAIR,
        UNRELATED_PROTECTED_DESCENDANT,
    )
    assert tuple(
        _git(
            ROOT,
            "diff",
            "--name-only",
            ACCEPTED_SOURCE_CLOSURE_REPAIR,
            UNRELATED_PROTECTED_DESCENDANT,
        ).splitlines()
    ) == UNRELATED_PROTECTED_DELTA
    for relative in REPAIR_CARRIER_PATHS:
        assert _git(
            ROOT,
            "ls-tree",
            ACCEPTED_SOURCE_CLOSURE_REPAIR,
            "--",
            relative,
        ) == _git(
            ROOT,
            "ls-tree",
            UNRELATED_PROTECTED_DESCENDANT,
            "--",
            relative,
        )


def _bootstrap_fixture(
    tmp_path: Path,
    *,
    repair_exit: int = 0,
    repair_output: str = "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED",
    mid_carrier_marker: Path | None = None,
    child_terminated_marker: Path | None = None,
    post_signal_sentinel: Path | None = None,
    post_return_descendant_marker: Path | None = None,
    post_return_mutation_marker: Path | None = None,
) -> tuple[Path, str, Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")

    executive_os = repository / "ops" / "executive_os"
    executive_os.mkdir(parents=True)
    fake_repair = executive_os / "repair-capacity-source-closure.sh"
    repair_body = (
        f"/usr/bin/printf '%s\\n' {shlex.quote(repair_output)}; "
        f"exit {repair_exit}"
    )
    if mid_carrier_marker is not None:
        assert child_terminated_marker is not None
        assert post_signal_sentinel is not None
        root_namespace = tmp_path / "bootstrap-root/mastermind-h0-root-carrier"
        repair_body = f"""
    on_signal() {{
      if [ -d {shlex.quote(str(root_namespace))} ]; then
        /usr/bin/touch {shlex.quote(str(child_terminated_marker))}
      fi
      exit 143
    }}
    trap on_signal HUP INT TERM
    (
      trap '' HUP INT TERM
      /bin/sleep 3
      /usr/bin/touch {shlex.quote(str(post_signal_sentinel))}
    ) &
    descendant_pid=$!
    /usr/bin/printf '%s %s\\n' "$$" "$descendant_pid" \
      > {shlex.quote(str(mid_carrier_marker))}
    wait "$descendant_pid"
    {repair_body}
"""
    if post_return_descendant_marker is not None:
        assert post_return_mutation_marker is not None
        repair_body = f"""
    (
      trap '' HUP INT TERM
      /bin/sleep 0.5
      /usr/bin/touch {shlex.quote(str(post_return_mutation_marker))}
    ) </dev/null >/dev/null 2>&1 &
    descendant_pid=$!
    carrier_group="$(/bin/ps -o pgid= -p "$$" | /usr/bin/tr -d ' ')"
    descendant_group="$(/bin/ps -o pgid= -p "$descendant_pid" | /usr/bin/tr -d ' ')"
    /usr/bin/printf '%s %s %s\n' \
      "$carrier_group" "$descendant_group" "$descendant_pid" \
      > {shlex.quote(str(post_return_descendant_marker))}
    /usr/bin/printf '%s\n' {shlex.quote(repair_output)}
    exit {repair_exit}
"""
    fake_repair.write_text(
        f"""#!/bin/bash
set -u
case "$1" in
  repair) {repair_body} ;;
  verify-only) /usr/bin/printf '%s\\n' H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED ;;
  *) exit 64 ;;
esac
""",
        encoding="utf-8",
    )
    fake_repair.chmod(0o755)
    for relative in REPAIR_CARRIER_PATHS[1:]:
        destination = repository / relative
        destination.write_bytes((ROOT / relative).read_bytes())
        destination.chmod(0o644)
    _git(repository, "add", *REPAIR_CARRIER_PATHS)
    _git(repository, "commit", "-qm", "fixture carrier")
    commit = _git(repository, "rev-parse", "HEAD")
    bundle = tmp_path / "repair.bundle"
    _git(repository, "bundle", "create", str(bundle), "HEAD")

    macro_transport = tmp_path / "macro-transport.zip"
    macro_transport.write_bytes(b"inert macro transport\n")
    return repository, commit, bundle, macro_transport


def _bootstrap_arguments(
    commit: str,
    bundle: Path,
    macro_transport: Path,
    *,
    operator_user: str | None = None,
) -> tuple[str, ...]:
    if operator_user is None:
        operator_user = subprocess.run(
            ["/usr/bin/id", "-un"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    return (
        commit,
        operator_user,
        str(macro_transport),
        hashlib.sha256(macro_transport.read_bytes()).hexdigest(),
        str(bundle),
        hashlib.sha256(bundle.read_bytes()).hexdigest(),
    )


def _bootstrap_split_arguments(
    carrier_commit: str,
    repair_commit: str,
    bundle: Path,
    macro_transport: Path,
    *,
    operator_user: str | None = None,
) -> tuple[str, ...]:
    return (
        carrier_commit,
        repair_commit,
        *_bootstrap_arguments(
            repair_commit,
            bundle,
            macro_transport,
            operator_user=operator_user,
        )[1:],
    )


def _run_bootstrap(
    *arguments: str,
    environment: dict[str, str],
    stdin: str = "",
    scheduler_probe: bool = False,
) -> tuple[int, str, str]:
    command = _test_bootstrap_command(
        arguments,
        environment,
        scheduler_probe=scheduler_probe,
    )
    completed = subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _test_bootstrap_command(
    arguments: tuple[str, ...],
    environment: dict[str, str],
    *,
    scheduler_probe: bool = False,
) -> list[str]:
    explicit_test_environment = {
        key: value
        for key, value in environment.items()
        if key.startswith("MMX_H0_BOOTSTRAP_TEST_")
        or (
            scheduler_probe
            and (key == "BASH_ENV" or key.startswith("MMX_H0_SIGNAL_"))
        )
    }
    return [
        "/usr/bin/env",
        "-i",
        *CLOSED_BOOTSTRAP_ENVIRONMENT,
        *(f"{key}={explicit_test_environment[key]}" for key in sorted(explicit_test_environment)),
        "/bin/bash",
        str(BOOTSTRAP),
        *arguments,
    ]


def _native_ceremony_command_from_runbook(
    *,
    repair_checkout: Path,
    repair_merge_sha: str,
    operator_user: str,
    macro_transport: Path,
    repair_carrier: Path,
) -> list[str]:
    command = next(
        block.split("```", 1)[0]
        for block in RUNBOOK.read_text(encoding="utf-8").split("```bash\n")[1:]
        if "bootstrap-capacity-source-closure.sh" in block
    )
    replacements = {
        "$REPAIR_CHECKOUT": str(repair_checkout),
        "$REPAIR_MERGE_SHA": repair_merge_sha,
        "$OPERATOR_USER": operator_user,
        "$MACRO_TRANSPORT": str(macro_transport),
        "$MACRO_TRANSPORT_SHA256": hashlib.sha256(
            macro_transport.read_bytes()
        ).hexdigest(),
        "$REPAIR_CARRIER": str(repair_carrier),
        "$REPAIR_CARRIER_SHA256": hashlib.sha256(
            repair_carrier.read_bytes()
        ).hexdigest(),
    }
    for variable in sorted(replacements, key=len, reverse=True):
        value = replacements[variable]
        command = command.replace(variable, value)
    return shlex.split(command.replace("\\\n", " "))


def _bootstrap_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    test_root = tmp_path / "bootstrap-root"
    test_root.mkdir()
    environment = dict(os.environ)
    environment["MMX_H0_BOOTSTRAP_TEST_ROOT"] = str(test_root)
    return environment, test_root / "mastermind-h0-root-carrier"


def _signal_registration_probe(tmp_path: Path) -> Path:
    probe = tmp_path / "signal-registration-probe.bash"
    probe.write_text(
        """set -T
__H0_DEBUG_ACTIVE=0
__H0_CHILD_TRAP_ARMED=0
__H0_CHECKPOINT_EMITTED=0

__h0_record_child_signal() {
  if [ -d "${ROOT_NAMESPACE:-/nonexistent}" ]; then
    /usr/bin/touch "$MMX_H0_SIGNAL_CHILD_TERMINATED_MARKER"
  fi
  exit 143
}

__h0_install_termination_proof_hold() {
  active_child_group_absent() {
    if [ -e "$MMX_H0_SIGNAL_TERMINATION_PROOF_HOLD" ]; then
      return 1
    fi
    /usr/bin/pgrep -a -q -g "$ACTIVE_CHILD_PGID" '.'
    [ "$?" -eq 1 ]
  }
}

__h0_debug_checkpoint() {
  local observed_command="$1" checkpoint_pid=""
  if [ "$__H0_DEBUG_ACTIVE" -eq 1 ]; then
    return 0
  fi
  __H0_DEBUG_ACTIVE=1

  if [ "${BASH_SUBSHELL:-0}" -gt 0 ]; then
    if [ "$__H0_CHILD_TRAP_ARMED" -eq 0 ]; then
      __H0_CHILD_TRAP_ARMED=1
      trap '__h0_record_child_signal' HUP INT TERM
    fi
    __H0_DEBUG_ACTIVE=0
    return 0
  fi

  case "$observed_command" in
    active_child_group_exists|active_child_group_absent)
      if [ -n "${MMX_H0_SIGNAL_TERMINATION_PROOF_HOLD:-}" ]; then
        __h0_install_termination_proof_hold
      fi
      ;;
  esac

  if [ "$observed_command" = 'wait "$ACTIVE_CHILD_PID"' ] \
    && [ -n "${MMX_H0_SIGNAL_WAIT_COUNT_MARKER:-}" ]; then
    /usr/bin/printf '%s\n' wait \
      >> "$MMX_H0_SIGNAL_WAIT_COUNT_MARKER"
  fi

  if [ "$__H0_CHECKPOINT_EMITTED" -eq 1 ]; then
    __H0_DEBUG_ACTIVE=0
    return 0
  fi

  case "$MMX_H0_SIGNAL_REGISTRATION_PHASE:$observed_command" in
    'after-spawn-before-pid:ACTIVE_CHILD_PID=$!')
      checkpoint_pid="$!"
      ;;
    'after-pid-before-pgid:ACTIVE_CHILD_PGID=$ACTIVE_CHILD_PID')
      checkpoint_pid="$ACTIVE_CHILD_PID"
      ;;
    'gate-release:CHILD_REGISTRATION_ACTIVE=0')
      checkpoint_pid="$ACTIVE_CHILD_PGID"
      ;;
    'steady-state:wait "$ACTIVE_CHILD_PID"')
      checkpoint_pid="$ACTIVE_CHILD_PGID"
      ;;
    'unexpected-exit:wait "$ACTIVE_CHILD_PID"')
      checkpoint_pid="$ACTIVE_CHILD_PGID"
      ;;
  esac
  if [ -n "$checkpoint_pid" ]; then
    if [ -n "${MMX_H0_SIGNAL_TERMINATION_PROOF_HOLD:-}" ]; then
      __h0_install_termination_proof_hold
    fi
    __H0_CHECKPOINT_EMITTED=1
    /usr/bin/printf '%s\n' "$checkpoint_pid" \
      > "$MMX_H0_SIGNAL_REGISTRATION_MARKER"
    while [ -e "$MMX_H0_SIGNAL_REGISTRATION_MARKER" ]; do
      /bin/sleep 0.01
    done
    if [ "$MMX_H0_SIGNAL_REGISTRATION_PHASE" = "unexpected-exit" ]; then
      __h0_install_termination_proof_hold
      trap - DEBUG
      exit 99
    fi
  fi
  __H0_DEBUG_ACTIVE=0
}

trap '__h0_debug_checkpoint "$BASH_COMMAND"' DEBUG
""",
        encoding="utf-8",
    )
    return probe


def _process_group_members(process_group: int) -> tuple[int, ...]:
    observed = subprocess.run(
        ["/bin/ps", "-axo", "pid=,pgid="],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(
        int(fields[0])
        for line in observed.splitlines()
        if len(fields := line.split()) == 2 and int(fields[1]) == process_group
    )


def test_bootstrap_refuses_root_identity_before_bundle_or_namespace_observation(
    tmp_path: Path,
) -> None:
    _repository, commit, bundle_target, macro_transport = _bootstrap_fixture(tmp_path)
    bundle = tmp_path / "operator-bundle-symlink"
    bundle.symlink_to(bundle_target)
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment["MMX_H0_BOOTSTRAP_TEST_CALLER_UID"] = "0"

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == INVALID
    assert bundle.is_symlink()
    assert not root_namespace.exists()


def test_bootstrap_refuses_operator_identity_mismatch_before_bundle_observation(
    tmp_path: Path,
) -> None:
    _repository, commit, bundle_target, macro_transport = _bootstrap_fixture(tmp_path)
    bundle = tmp_path / "operator-bundle-symlink"
    bundle.symlink_to(bundle_target)
    environment, root_namespace = _bootstrap_environment(tmp_path)

    result = _run_bootstrap(
        *_bootstrap_arguments(
            commit,
            bundle,
            macro_transport,
            operator_user="definitely_not_current_user",
        ),
        environment=environment,
    )

    assert result == INVALID
    assert bundle.is_symlink()
    assert not root_namespace.exists()


def test_bootstrap_two_pin_invocation_reaches_bundle_authentication_before_refusal(
    tmp_path: Path,
) -> None:
    bundle_target = tmp_path / "operator-bundle-target"
    bundle_target.write_bytes(b"inert bundle target\n")
    bundle = tmp_path / "operator-bundle-symlink"
    bundle.symlink_to(bundle_target)
    macro_transport = tmp_path / "macro-transport.zip"
    macro_transport.write_bytes(b"inert macro transport\n")

    result = _run_bootstrap(
        *_bootstrap_split_arguments(
            "b" * 40,
            "a" * 40,
            bundle,
            macro_transport,
        ),
        environment={},
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert bundle.is_symlink()
    assert bundle_target.read_bytes() == b"inert bundle target\n"


@DARWIN_NATIVE
def test_exact_disposable_carrier_inventory_runs_under_isolated_apple_python(
    tmp_path: Path,
) -> None:
    carrier = tmp_path / "carrier"
    for relative in REPAIR_CARRIER_PATHS:
        destination = carrier / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            str(carrier / "ops/executive_os/capacity_host_artifacts.py"),
            "--help",
        ],
        cwd="/",
        text=True,
        capture_output=True,
        check=False,
        env={
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    assert (completed.returncode, completed.stderr) == (0, "")
    assert "Build or inspect inert CF2-H0 artifacts" in completed.stdout


@DARWIN_NATIVE
def test_invalid_bundle_cannot_interpret_hostile_stdin_before_authentication(
    tmp_path: Path,
) -> None:
    environment, root_namespace = _bootstrap_environment(tmp_path)
    bundle = tmp_path / "malformed.bundle"
    bundle.write_bytes(b"not a git bundle\n")
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert\n")
    sentinel = tmp_path / "hostile-stdin-ran"
    hostile_stdin = f"/usr/bin/touch {sentinel}\n"

    result = _run_bootstrap(
        *_bootstrap_arguments("d" * 40, bundle, macro_transport),
        environment=environment,
        stdin=hostile_stdin,
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert not sentinel.exists()
    assert not root_namespace.exists()


def test_native_runbook_command_closes_ambient_bash_env_before_line_one(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "ambient-bash-env-ran"
    startup = tmp_path / "ambient-bash-env.bash"
    startup.write_text(
        f"/usr/bin/touch {shlex.quote(str(sentinel))}\n"
        "/usr/bin/printf '%s\\n' AMBIENT_STARTUP_RAN >&2\n",
        encoding="utf-8",
    )
    repair_checkout = tmp_path / "repair-checkout"
    bootstrap = repair_checkout / "ops/executive_os" / BOOTSTRAP.name
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_bytes(BOOTSTRAP.read_bytes())
    bootstrap.chmod(0o755)
    bundle_target = tmp_path / "bundle-target"
    bundle_target.write_bytes(b"inert bundle target\n")
    repair_carrier = tmp_path / "repair.bundle"
    repair_carrier.symlink_to(bundle_target)
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert macro transport\n")
    operator_user = subprocess.run(
        ["/usr/bin/id", "-un"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    command = _native_ceremony_command_from_runbook(
        repair_checkout=repair_checkout,
        repair_merge_sha="d" * 40,
        operator_user=operator_user,
        macro_transport=macro_transport,
        repair_carrier=repair_carrier,
    )
    environment = dict(os.environ)
    environment["BASH_ENV"] = str(startup)

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert (completed.returncode, completed.stdout, completed.stderr) == (
        65,
        "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n",
        "",
    )
    assert not sentinel.exists()


@DARWIN_NATIVE
def test_symlink_bundle_refuses_without_touching_target(
    tmp_path: Path,
) -> None:
    environment, root_namespace = _bootstrap_environment(tmp_path)
    target = tmp_path / "bundle-target"
    target.write_bytes(b"inert target\n")
    target.chmod(0o640)
    before = target.stat()
    before_xattrs = subprocess.run(
        ["/usr/bin/xattr", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    before_acl = subprocess.run(
        ["/bin/ls", "-lde", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    bundle = tmp_path / "repair.bundle"
    bundle.symlink_to(target)
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert\n")

    result = _run_bootstrap(
        *_bootstrap_arguments("d" * 40, bundle, macro_transport),
        environment=environment,
    )
    after = target.stat()

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert target.read_bytes() == b"inert target\n"
    assert (
        after.st_dev,
        after.st_ino,
        after.st_uid,
        after.st_gid,
        after.st_mode,
        getattr(after, "st_flags", 0),
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) == (
        before.st_dev,
        before.st_ino,
        before.st_uid,
        before.st_gid,
        before.st_mode,
        getattr(before, "st_flags", 0),
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    assert subprocess.run(
        ["/usr/bin/xattr", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == before_xattrs
    assert subprocess.run(
        ["/bin/ls", "-lde", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == before_acl
    assert not root_namespace.exists()


@DARWIN_NATIVE
def test_exact_bundle_runs_three_passes_and_removes_root_namespace(
    tmp_path: Path,
) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(tmp_path)
    environment, root_namespace = _bootstrap_environment(tmp_path)

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == (
        0,
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n"
        "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n"
        "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n",
        "",
    )
    assert not root_namespace.exists()


@DARWIN_NATIVE
def test_cleanup_failure_cannot_emit_clean_success(tmp_path: Path) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(tmp_path)
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment["MMX_H0_BOOTSTRAP_TEST_CLEANUP_FAIL"] = "1"

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert not root_namespace.exists()


@DARWIN_NATIVE
def test_gate_release_failure_reaps_gated_group_before_refusal_cleanup(
    tmp_path: Path,
) -> None:
    registration_marker = tmp_path / "gate-release-checkpoint"
    carrier_started = tmp_path / "carrier-started"
    child_terminated = tmp_path / "carrier-terminated-before-cleanup"
    gated_child_terminated = tmp_path / "gated-child-terminated-before-cleanup"
    post_signal_sentinel = tmp_path / "post-refusal-mutation"
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        mid_carrier_marker=carrier_started,
        child_terminated_marker=child_terminated,
        post_signal_sentinel=post_signal_sentinel,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment.update(
        {
            "BASH_ENV": str(_signal_registration_probe(tmp_path)),
            "MMX_H0_BOOTSTRAP_TEST_GATE_RELEASE_FAIL": "1",
            "MMX_H0_SIGNAL_REGISTRATION_PHASE": "gate-release",
            "MMX_H0_SIGNAL_REGISTRATION_MARKER": str(registration_marker),
            "MMX_H0_SIGNAL_CHILD_TERMINATED_MARKER": str(gated_child_terminated),
        }
    )
    process = subprocess.Popen(
        _test_bootstrap_command(
            _bootstrap_arguments(commit, bundle, macro_transport),
            environment,
            scheduler_probe=True,
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    registration_payload = ""
    while time.monotonic() < deadline and not registration_payload:
        if registration_marker.exists():
            registration_payload = registration_marker.read_text(
                encoding="utf-8"
            ).strip()
        time.sleep(0.01)
    assert registration_payload, process.communicate(timeout=1)
    process_group = int(registration_payload)
    registration_marker.unlink()

    stdout, stderr = process.communicate(timeout=15)

    assert (process.returncode, stdout, stderr) == (
        65,
        "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n",
        "",
    )
    time.sleep(3.2)
    assert gated_child_terminated.exists()
    assert _process_group_members(process_group) == ()
    assert not carrier_started.exists()
    assert not child_terminated.exists()
    assert not post_signal_sentinel.exists()
    assert not root_namespace.exists()


@pytest.mark.parametrize(
    "terminal_path,expected",
    (
        (
            "signal",
            (
                70,
                "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n",
                "",
            ),
        ),
        ("unexpected-exit", (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")),
    ),
)
@DARWIN_NATIVE
def test_post_spawn_terminal_receipt_waits_for_termination_proof(
    tmp_path: Path,
    terminal_path: str,
    expected: tuple[int, str, str],
) -> None:
    registration_marker = tmp_path / "terminal-checkpoint"
    termination_proof_hold = tmp_path / "hold-termination-proof"
    termination_proof_hold.touch()
    carrier_started = tmp_path / "carrier-started"
    child_terminated = tmp_path / "child-terminated-before-cleanup"
    post_signal_sentinel = tmp_path / "post-terminal-mutation"
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        mid_carrier_marker=carrier_started,
        child_terminated_marker=child_terminated,
        post_signal_sentinel=post_signal_sentinel,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment.update(
        {
            "BASH_ENV": str(_signal_registration_probe(tmp_path)),
            "MMX_H0_SIGNAL_REGISTRATION_PHASE": (
                "steady-state" if terminal_path == "signal" else "unexpected-exit"
            ),
            "MMX_H0_SIGNAL_REGISTRATION_MARKER": str(registration_marker),
            "MMX_H0_SIGNAL_CHILD_TERMINATED_MARKER": str(child_terminated),
            "MMX_H0_SIGNAL_TERMINATION_PROOF_HOLD": str(termination_proof_hold),
        }
    )
    process = subprocess.Popen(
        _test_bootstrap_command(
            _bootstrap_arguments(commit, bundle, macro_transport),
            environment,
            scheduler_probe=True,
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    registration_payload = ""
    carrier_payload = ""
    while time.monotonic() < deadline and (
        not registration_payload or not carrier_payload
    ):
        if registration_marker.exists():
            registration_payload = registration_marker.read_text(
                encoding="utf-8"
            ).strip()
        if carrier_started.exists():
            carrier_payload = carrier_started.read_text(encoding="utf-8").strip()
        time.sleep(0.01)
    assert registration_payload and carrier_payload, process.communicate(timeout=1)
    process_group = int(registration_payload)
    if terminal_path == "signal":
        process.send_signal(signal.SIGTERM)
    registration_marker.unlink()
    if terminal_path == "signal":
        time.sleep(0.2)
        process.send_signal(signal.SIGHUP)

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.05)
    assert process.poll() is None
    assert root_namespace.exists()

    termination_proof_hold.unlink()
    stdout, stderr = process.communicate(timeout=10)

    assert (process.returncode, stdout, stderr) == expected
    assert child_terminated.exists()
    assert _process_group_members(process_group) == ()
    time.sleep(3.2)
    assert not post_signal_sentinel.exists()
    assert not root_namespace.exists()


@pytest.mark.parametrize(
    "repair_exit,repair_output,expected,expected_wait_count",
    (
        (
            65,
            "H0_SOURCE_CLOSURE_REPAIR_REFUSED",
            (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", ""),
            1,
        ),
        (
            0,
            "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED",
            (
                0,
                "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n"
                "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n"
                "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n",
                "",
            ),
            3,
        ),
    ),
)
@DARWIN_NATIVE
def test_direct_carrier_return_retains_group_until_terminal_proof(
    tmp_path: Path,
    repair_exit: int,
    repair_output: str,
    expected: tuple[int, str, str],
    expected_wait_count: int,
) -> None:
    descendant_marker = tmp_path / "post-return-descendant"
    delayed_mutation = tmp_path / "post-return-mutation"
    wait_count_marker = tmp_path / "direct-wait-count"
    child_terminated = tmp_path / "tracked-child-terminated"
    termination_proof_hold = tmp_path / "hold-termination-proof"
    termination_proof_hold.touch()
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        repair_exit=repair_exit,
        repair_output=repair_output,
        post_return_descendant_marker=descendant_marker,
        post_return_mutation_marker=delayed_mutation,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment.update(
        {
            "BASH_ENV": str(_signal_registration_probe(tmp_path)),
            "MMX_H0_SIGNAL_REGISTRATION_PHASE": "typed-return",
            "MMX_H0_SIGNAL_CHILD_TERMINATED_MARKER": str(child_terminated),
            "MMX_H0_SIGNAL_TERMINATION_PROOF_HOLD": str(
                termination_proof_hold
            ),
            "MMX_H0_SIGNAL_WAIT_COUNT_MARKER": str(wait_count_marker),
        }
    )
    process = subprocess.Popen(
        _test_bootstrap_command(
            _bootstrap_arguments(commit, bundle, macro_transport),
            environment,
            scheduler_probe=True,
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        deadline = time.monotonic() + 10
        descendant_payload = ""
        while time.monotonic() < deadline and (
            not descendant_payload or not wait_count_marker.exists()
        ):
            if descendant_marker.exists():
                descendant_payload = descendant_marker.read_text(
                    encoding="utf-8"
                ).strip()
            time.sleep(0.01)
        assert descendant_payload and wait_count_marker.exists(), process.communicate(
            timeout=1
        )
        carrier_group, descendant_group, descendant_pid = (
            int(value) for value in descendant_payload.split()
        )
        assert carrier_group == descendant_group
        assert descendant_pid > 0

        time.sleep(0.2)
        assert process.poll() is None
        assert root_namespace.exists()
        assert select.select([process.stdout], [], [], 0)[0] == []

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _process_group_members(carrier_group):
            time.sleep(0.05)
        assert _process_group_members(carrier_group) == ()
        assert process.poll() is None
        assert root_namespace.exists()
        assert select.select([process.stdout], [], [], 0)[0] == []
    finally:
        termination_proof_hold.unlink(missing_ok=True)

    stdout, stderr = process.communicate(timeout=10)

    assert (process.returncode, stdout, stderr) == expected
    assert wait_count_marker.read_text(encoding="utf-8").splitlines() == [
        "wait"
    ] * expected_wait_count
    time.sleep(0.7)
    assert not delayed_mutation.exists()
    assert not root_namespace.exists()


@pytest.mark.parametrize(
    "repair_exit,repair_output",
    (
        (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED"),
        (70, "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"),
        (75, "H0_LOCK_HELD"),
    ),
)
@DARWIN_NATIVE
def test_bootstrap_preserves_authenticated_carrier_primary_failure(
    tmp_path: Path, repair_exit: int, repair_output: str
) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        repair_exit=repair_exit,
        repair_output=repair_output,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment["MMX_H0_BOOTSTRAP_TEST_CLEANUP_FAIL"] = "1"

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == (repair_exit, f"{repair_output}\n", "")
    assert not root_namespace.exists()


@DARWIN_NATIVE
def test_preexisting_fixed_namespace_refuses_without_deleting_unknown_residue(
    tmp_path: Path,
) -> None:
    environment, root_namespace = _bootstrap_environment(tmp_path)
    root_namespace.mkdir()
    residue = root_namespace / "unknown-residue"
    residue.write_bytes(b"must remain\n")
    bundle = tmp_path / "malformed.bundle"
    bundle.write_bytes(b"inert until namespace refusal\n")
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert\n")

    result = _run_bootstrap(
        *_bootstrap_arguments("d" * 40, bundle, macro_transport),
        environment=environment,
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert residue.read_bytes() == b"must remain\n"


@pytest.mark.parametrize("interrupt", (signal.SIGHUP, signal.SIGINT, signal.SIGTERM))
@DARWIN_NATIVE
def test_signal_removes_exclusive_root_namespace(
    tmp_path: Path, interrupt: signal.Signals
) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(tmp_path)
    environment, root_namespace = _bootstrap_environment(tmp_path)
    marker = tmp_path / "namespace-ready"
    environment["MMX_H0_BOOTSTRAP_TEST_PAUSE_MARKER"] = str(marker)
    process = subprocess.Popen(
        _test_bootstrap_command(
            _bootstrap_arguments(commit, bundle, macro_transport), environment
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.01)
    assert marker.exists(), process.communicate(timeout=1)
    process.send_signal(interrupt)
    stdout, stderr = process.communicate(timeout=5)

    assert (process.returncode, stdout, stderr) == (
        70,
        "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n",
        "",
    )
    assert not root_namespace.exists()


@pytest.mark.parametrize("interrupt", (signal.SIGHUP, signal.SIGINT, signal.SIGTERM))
@DARWIN_NATIVE
def test_signal_to_bootstrap_pid_terminates_active_carrier_tree_before_cleanup(
    tmp_path: Path, interrupt: signal.Signals
) -> None:
    carrier_started = tmp_path / "carrier-started"
    child_terminated = tmp_path / "child-terminated-before-cleanup"
    post_signal_sentinel = tmp_path / "post-signal-mutation"
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        mid_carrier_marker=carrier_started,
        child_terminated_marker=child_terminated,
        post_signal_sentinel=post_signal_sentinel,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    process = subprocess.Popen(
        _test_bootstrap_command(
            _bootstrap_arguments(commit, bundle, macro_transport), environment
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    carrier_payload = ""
    while time.monotonic() < deadline and not carrier_payload:
        if carrier_started.exists():
            carrier_payload = carrier_started.read_text(encoding="utf-8").strip()
        time.sleep(0.01)
    assert carrier_payload, process.communicate(timeout=1)
    carrier_pid, descendant_pid = (
        int(value) for value in carrier_payload.split()
    )

    process.send_signal(interrupt)
    stdout, stderr = process.communicate(timeout=10)

    assert (process.returncode, stdout, stderr) == (
        70,
        "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n",
        "",
    )
    assert child_terminated.exists()
    assert not root_namespace.exists()
    for child_pid in (carrier_pid, descendant_pid):
        observed_process = subprocess.run(
            ["/bin/ps", "-p", str(child_pid), "-o", "pid="],
            check=False,
            capture_output=True,
            text=True,
        )
        assert (observed_process.returncode, observed_process.stdout) == (1, "")
    time.sleep(3.2)
    assert not post_signal_sentinel.exists()


@pytest.mark.parametrize(
    "registration_phase",
    ("after-spawn-before-pid", "after-pid-before-pgid", "steady-state"),
)
@pytest.mark.parametrize("interrupt", (signal.SIGHUP, signal.SIGINT, signal.SIGTERM))
@DARWIN_NATIVE
def test_signal_registration_window_never_releases_untracked_carrier(
    tmp_path: Path, registration_phase: str, interrupt: signal.Signals
) -> None:
    registration_marker = tmp_path / "registration-checkpoint"
    carrier_started = tmp_path / "carrier-started"
    child_terminated = tmp_path / "carrier-terminated-before-cleanup"
    gated_child_terminated = tmp_path / "gated-child-terminated-before-cleanup"
    post_signal_sentinel = tmp_path / "post-signal-mutation"
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        mid_carrier_marker=carrier_started,
        child_terminated_marker=child_terminated,
        post_signal_sentinel=post_signal_sentinel,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment.update(
        {
            "BASH_ENV": str(_signal_registration_probe(tmp_path)),
            "MMX_H0_SIGNAL_REGISTRATION_PHASE": registration_phase,
            "MMX_H0_SIGNAL_REGISTRATION_MARKER": str(registration_marker),
            "MMX_H0_SIGNAL_CHILD_TERMINATED_MARKER": str(gated_child_terminated),
        }
    )
    process = subprocess.Popen(
        _test_bootstrap_command(
            _bootstrap_arguments(commit, bundle, macro_transport),
            environment,
            scheduler_probe=True,
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    registration_payload = ""
    while time.monotonic() < deadline and not registration_payload:
        if registration_marker.exists():
            registration_payload = registration_marker.read_text(
                encoding="utf-8"
            ).strip()
        time.sleep(0.01)
    assert registration_payload, process.communicate(timeout=1)
    process_group = int(registration_payload)
    if registration_phase == "steady-state":
        while time.monotonic() < deadline and not carrier_started.exists():
            time.sleep(0.01)
        assert carrier_started.exists(), process.communicate(timeout=1)

    process.send_signal(interrupt)
    time.sleep(0.05)
    registration_marker.unlink(missing_ok=True)
    stdout, stderr = process.communicate(timeout=15)

    assert (process.returncode, stdout, stderr) == (
        70,
        "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n",
        "",
    )
    time.sleep(3.2)
    assert not post_signal_sentinel.exists()
    assert gated_child_terminated.exists()
    assert _process_group_members(process_group) == ()
    assert not root_namespace.exists()
    if registration_phase == "steady-state":
        assert child_terminated.exists()
    else:
        assert not carrier_started.exists()


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--help",),
        ("repair",),
        ("verify-only",),
        ("VERIFY-ONLY", "--expected-source-closure-repair-commit", "d" * 40),
        ("verify-only", "--expected-source-closure-repair-commit", "D" * 40),
        ("verify-only", "--expected-source-closure-repair-commit", "d" * 40, "extra"),
        (
            "repair",
            "--operator-user",
            "operator",
            "--expected-source-closure-repair-commit",
            "d" * 40,
            "--macro-transport",
            "/tmp/carrier.zip",
            "--macro-transport-sha256",
            "a" * 64,
        ),
        (
            "repair",
            "--expected-source-closure-repair-commit",
            "d" * 40,
            "--operator-user",
            "operator",
            "--macro-transport",
            "relative.zip",
            "--macro-transport-sha256",
            "a" * 64,
        ),
    ),
)
def test_invalid_invocations_are_closed_before_host_adapter_read(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    unreadable = tmp_path / "must-not-read"
    environment = dict(os.environ)
    environment["MMX_CAPACITY_REPAIR_TEST_ROOT"] = str(unreadable)
    assert _run(*arguments, environment=environment) == INVALID
    assert not unreadable.exists()


def test_exact_cli_forms_cross_validation_before_preflight(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["MMX_CAPACITY_REPAIR_TEST_ROOT"] = str(tmp_path / "host")
    repair = _run(
        "repair",
        "--expected-source-closure-repair-commit",
        "d" * 40,
        "--operator-user",
        "operator",
        "--macro-transport",
        "/tmp/carrier.zip",
        "--macro-transport-sha256",
        "a" * 64,
        environment=environment,
    )
    verify = _run(
        "verify-only",
        "--expected-source-closure-repair-commit",
        "d" * 40,
        environment=environment,
    )
    assert repair[0] != 64
    assert verify[0] != 64


def test_runbook_freezes_alternative_b_build_and_one_offline_native_ceremony() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    required = (
        "Alternative B",
        "dcdd939c45b23abce5ba04f95e330ac914a3904b",
        "mastermind.capacity_source_transport/v3",
        "build-source-transport-v3",
        "32 GiB",
        "MACRO_TRANSPORT_SHA256",
        "REPAIR_MERGE_SHA='<40-lower-hex-protected-repair-merge-sha>'",
        "checkout --detach",
        "one native administrator dialog",
        "bootstrap-capacity-source-closure.sh",
        "root never receives a shell",
        "/private/var/root/mastermind-h0-root-carrier",
        "provider_worker_slots.py",
        "provider_identity_policy.py",
        "2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60",
        "02886a6c79f22534ac24234d8adb3224329976342393988541c2a50d7e297f29",
        "51c58d18869663d90c593e416c7fc7833b3725378870f576abd3647f62f40830",
        "981e880ba7d21a0003fe2dd8322c5793f2643b815d094374dd6fad3fed31e453",
        "18d83b0e164ac2e917d84c01fe1d53fc5c1ce0c33ac9580f11d684e16e495093",
        "7efba70495cbbf8bcad0c4e47e894a23f4b1618756d8c3e23cae85ad6b7250ba",
        "35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650",
        "/Library/Application Support/MastermindExecutive/locks/cf2-h0.lock",
        "one durable repair intent",
        "archive-only",
        "last semantic filesystem mutation",
    )
    for value in required:
        assert value in normalized

    bootstrap = """/usr/bin/env -i \\
  HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \\
  /bin/bash "$REPAIR_CHECKOUT/ops/executive_os/bootstrap-capacity-source-closure.sh" \\
  "$REPAIR_MERGE_SHA" "$OPERATOR_USER" "$MACRO_TRANSPORT" "$MACRO_TRANSPORT_SHA256" \\
  "$REPAIR_CARRIER" "$REPAIR_CARRIER_SHA256"""
    assert bootstrap in runbook
    for forbidden in ("/bin/bash -s", "<<'H0_SOURCE_REPAIR'", "one root shell"):
        assert forbidden not in runbook


def test_native_ceremony_materializes_one_digest_bound_root_created_carrier() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    required = (
        "git bundle create",
        "REPAIR_CARRIER_SHA256",
        "inert exact-commit carrier",
        "/usr/bin/env -i",
        "GIT_CONFIG_NOSYSTEM=1",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_CONFIG_LOCAL=/dev/null",
        "GIT_ATTR_NOSYSTEM=1",
        "GIT_NO_REPLACE_OBJECTS=1",
        "GIT_EXTERNAL_DIFF=/usr/bin/false",
        "GIT_ALLOW_PROTOCOL=file",
        "protocol.allow=never",
        "protocol.file.allow=always",
        "core.hooksPath=/dev/null",
        "core.fsmonitor=false",
        "core.attributesFile=/dev/null",
        "--no-ext-diff --no-textconv",
        "exclusive fixed literal",
        "Git blob OID",
        "buffered until the fixed root namespace has been removed",
        "No installed release executable or Python module is launched",
    )
    for value in required:
        assert value in normalized
    forbidden = (
        'cd "$REPAIR_CHECKOUT"',
        "/usr/sbin/chown -R root:wheel .",
        '/bin/bash ops/executive_os/repair-capacity-source-closure.sh repair',
    )
    for value in forbidden:
        assert value not in runbook


def test_root_carrier_wrapper_uses_no_git_and_requires_descriptor_verification() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "/usr/bin/git" not in script
    assert "verify-repair-carrier" in script
    assert "--repository" in script
    assert ".repair-carrier-commit" in script
    assert "/usr/bin/env -i" in script


def test_runbook_fixes_output_recovery_two_axis_proof_and_all_holds() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    required = (
        "0 H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED",
        "0 H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED",
        "64 INVALID_INVOCATION",
        "65 H0_SOURCE_CLOSURE_REPAIR_REFUSED",
        "70 H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER",
        "75 H0_LOCK_HELD",
        "77 ROOT_REQUIRED",
        "Stderr is empty",
        "same carrier",
        "parent `fsync`",
        "e4e44867ace335ac9208a3990a10c163e199492d",
        "topology-preparer/topology-release identity",
        "source-closure/generation-repair identity",
        "does not install a release",
        "does not rerender topology",
        "P0 re-pin",
        "provider-home",
        "credential",
        "OAuth",
        "service",
        "socket",
        "provider",
        "routing",
        "worker",
        "fan-out",
        "failover",
        "CF2-I",
    )
    for value in required:
        assert value in normalized


def test_runbook_design_and_plan_preserve_only_kernel_read_atime_exception() -> None:
    required = (
        "zero program-directed and zero semantic mutation",
        "Kernel-induced access-time advancement from required reads is the sole permitted observable metadata delta",
        "Atime is non-authoritative, may only remain equal or advance",
        "never set, restored, decreased, or used to conceal another change",
        "applies only to the fixed installed H0 root",
        "writable APFS",
        "not mounted `MNT_RDONLY`",
        "does not expose `MNT_NOATIME`",
        "mandatory full independent content verification",
        "does not apply to any other filesystem, root, provider, or worker surface",
        "Namespace",
        "bytes/digests",
        "device/inode identity",
        "type",
        "mode",
        "UID/GID",
        "links",
        "size",
        "flags",
        "ACLs",
        "xattrs",
        "mtime",
        "ctime",
        "topology/rollback evidence",
        "launchd state",
        "sockets",
        "legacy state",
    )
    for authority in (RUNBOOK, DESIGN, PLAN):
        content = " ".join(authority.read_text(encoding="utf-8").split())
        for value in required:
            assert value in content, f"{authority}: missing {value}"


def _runtime_wrapper_with_bounded_lower_carrier(tmp_path: Path) -> Path:
    script_dir = tmp_path / "ops" / "executive_os"
    script_dir.mkdir(parents=True)
    wrapper = script_dir / SCRIPT.name
    wrapper.write_bytes(SCRIPT.read_bytes())
    wrapper.chmod(0o755)
    (script_dir / "capacity_host_artifacts.py").write_text(
        """
import os
import sys

arguments = sys.argv[1:]
expected_mode = os.environ["MMX_CAPACITY_REPAIR_EXPECTED_MODE"]
if (
    not arguments
    or arguments[0] != "source-repair-host"
    or arguments[1:3] != ["--mode", expected_mode]
    or "--system-root" not in arguments
    or "--lock-file" not in arguments
    or "--expected-repair-commit" not in arguments
    or "--expected-source-commit" not in arguments
    or arguments[-1] != "--test-adapter"
):
    raise SystemExit(64)
repair_only = {"--operator-user", "--transport", "--transport-sha256"}
observed_repair_only = repair_only.intersection(arguments)
if (
    (expected_mode == "repair" and observed_repair_only != repair_only)
    or (expected_mode == "verify-only" and observed_repair_only)
):
    raise SystemExit(64)
raise SystemExit(int(os.environ["MMX_CAPACITY_REPAIR_FAKE_EXIT"]))
""",
        encoding="utf-8",
    )
    return wrapper


@pytest.mark.skipif(os.geteuid() == 0, reason="root-required is a non-root boundary")
def test_bash_wrapper_renders_root_required_runtime_tuple() -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "MMX_CAPACITY_REPAIR_TEST_ROOT"
    }
    assert _run(
        "verify-only",
        "--expected-source-closure-repair-commit",
        "d" * 40,
        environment=environment,
    ) == (77, "ROOT_REQUIRED\n", "")


@pytest.mark.skipif(os.geteuid() == 0, reason="test adapter is confined to non-root")
@pytest.mark.parametrize(
    "mode,lower_exit,expected",
    (
        ("refusal", 65, (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")),
        ("lock-held", 75, (75, "H0_LOCK_HELD\n", "")),
        (
            "incomplete",
            70,
            (70, "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n", ""),
        ),
        ("repair", 0, (0, "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n", "")),
        ("verify-only", 0, (0, "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n", "")),
    ),
)
def test_bash_wrapper_runtime_output_tuples_use_existing_adapter_boundary(
    tmp_path: Path,
    mode: str,
    lower_exit: int,
    expected: tuple[int, str, str],
) -> None:
    wrapper = _runtime_wrapper_with_bounded_lower_carrier(tmp_path)
    environment = dict(os.environ)
    environment["MMX_CAPACITY_REPAIR_TEST_ROOT"] = str(tmp_path / "host")
    environment["MMX_CAPACITY_REPAIR_FAKE_EXIT"] = str(lower_exit)
    environment["MMX_CAPACITY_REPAIR_EXPECTED_MODE"] = (
        "repair" if mode == "repair" else "verify-only"
    )
    arguments = (
        (
            "repair",
            "--expected-source-closure-repair-commit",
            "d" * 40,
            "--operator-user",
            "operator",
            "--macro-transport",
            "/tmp/carrier.zip",
            "--macro-transport-sha256",
            "a" * 64,
        )
        if mode == "repair"
        else (
            "verify-only",
            "--expected-source-closure-repair-commit",
            "d" * 40,
        )
    )
    assert _run_script(wrapper, *arguments, environment=environment) == expected


def test_bash32_empty_array_and_fixed_output_rendering() -> None:
    compatibility = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -u; values=(); if [ "${#values[@]}" -gt 0 ]; then '
            '/usr/bin/printf "%s\\n" "${values[@]}"; fi; '
            '/usr/bin/printf "%s\\n" EMPTY_ARRAY_PASS',
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert (compatibility.returncode, compatibility.stdout, compatibility.stderr) == (
        0,
        "EMPTY_ARRAY_PASS\n",
        "",
    )

    source = SCRIPT.read_text(encoding="utf-8")
    assert "/usr/bin/printf '%s\\n' \"$sentinel\"" in source
    for fixed_render in (
        'finish 64 "INVALID_INVOCATION"',
        'finish 65 "H0_SOURCE_CLOSURE_REPAIR_REFUSED"',
        'finish 70 "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"',
        'finish 75 "H0_LOCK_HELD"',
        'finish 77 "ROOT_REQUIRED"',
        'finish 0 "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"',
        'finish 0 "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"',
    ):
        assert fixed_render in source
    for bash4_only in ("declare -A", "mapfile", "readarray", "${value,,}"):
        assert bash4_only not in source
    assert _run("--help") == INVALID

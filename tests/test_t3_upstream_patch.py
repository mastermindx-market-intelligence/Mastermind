"""Verify the pinned T3 upstream admission patch, its MANIFEST, and patch bytes.

Covers:
  1. The MANIFEST sha256 digest matches the actual .patch bytes (always runs).
  2. Every file the manifest claims is exactly the set of files the diff touches
     (parsed from the diff headers).
  3. The patch contains no obvious secret literals.
  4. If a pinned T3 clone is present (env MMOS_T3_PINNED_SOURCE, default
     /Users/chriswong/.hermes/profiles/engineering/mmos/t3code-src):
     subprocess `git apply --check` succeeds there and the clone HEAD is the pin.
     Otherwise this test is skipped ("pinned T3 clone not present").
  5. The manifest states the pin 0770446869d247a8b28c27d7ed93f47f8ff0c1e4.
  6. Audit finding #2 (A3 rework): no decorator runs ``Layer.build`` (a nested
     build forks the effect 4.1.2 memo map and rebuilds shared singletons), and
     the colocated vitest suite pins the built-exactly-once composition.
"""

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

WORKTREE_ROOT = Path(__file__).resolve().parent.parent
PATCH_DIR = WORKTREE_ROOT / "integrations" / "t3" / "upstream_patches"
PATCH_PATH = PATCH_DIR / "mastermind_admission_0770446.patch"
MANIFEST_PATH = PATCH_DIR / "MANIFEST.md"

PIN = "0770446869d247a8b28c27d7ed93f47f8ff0c1e4"
#: sha256 of the A3-reworked patch bytes (audit finding #2 fix).  The
#: pre-rework bytes were f78413fb5364be4b7a382276d9207fc429cf235e9c3c477b2e627a82aa5caa87.
PATCH_SHA256 = "5785ac9525a852d0c19c3668f2ae4e9cb3fcd779a62b2a084affa2004f4e922f"
ADAPTER_FILE = "apps/server/src/mastermind/MastermindAdmissionAdapter.ts"
ADAPTER_TEST_FILE = "apps/server/src/mastermind/MastermindAdmissionAdapter.test.ts"
DEFAULT_PINNED_SOURCE = "/Users/chriswong/.hermes/profiles/engineering/mmos/t3code-src"


def _patch_bytes() -> bytes:
    return PATCH_PATH.read_bytes()


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text()


def _diff_touched_files(patch_text: str) -> set[str]:
    """Repo-relative paths the patch modifies, parsed from diff headers."""
    files = set(re.findall(r"^diff --git a/(.+?) b/(.+?)$", patch_text, re.MULTILINE))
    assert all(left == right for left, right in files), (
        f"rename detected in diff: {sorted(files)}"
    )
    return {right for _, right in files}


def _manifest_claimed_files(manifest_text: str) -> set[str]:
    """Repo-relative (apps/server/src/...) paths claimed in the manifest text."""
    return set(re.findall(r"`(apps/server/src/[A-Za-z0-9_./-]+\.ts)`", manifest_text))


# ---------------------------------------------------------------------------
# 1. DIGEST: manifest sha256 matches the actual patch bytes (always runs)
# ---------------------------------------------------------------------------


def test_manifest_digest_matches_patch_bytes() -> None:
    patch = _patch_bytes()
    digest = hashlib.sha256(patch).hexdigest()
    # The pin is 40 hex chars; a sha256 digest is the only 64-hex token in the manifest.
    recorded = re.findall(r"\b[a-f0-9]{64}\b", _manifest_text())
    assert recorded, "manifest must record a sha256 digest of the patch file"
    assert digest in recorded, (
        f"manifest digest(s) {recorded} do not match actual patch bytes digest {digest}"
    )


# ---------------------------------------------------------------------------
# 2. FILE SET: manifest claims == exactly the files the diff touches
# ---------------------------------------------------------------------------


def test_manifest_files_match_diff_headers() -> None:
    patch_text = _patch_bytes().decode()
    diff_files = _diff_touched_files(patch_text)
    assert diff_files, "patch must touch at least one file"
    claimed = _manifest_claimed_files(_manifest_text())
    assert claimed == diff_files, (
        f"manifest claims {sorted(claimed)} but diff touches {sorted(diff_files)}"
    )


def test_patch_headers_use_expected_files() -> None:
    patch_text = _patch_bytes().decode()
    files = _diff_touched_files(patch_text)
    assert (
        "apps/server/src/mastermind/MastermindAdmissionAdapter.ts" in files
    ), "the new MastermindAdmissionAdapter module must be part of the patch"
    assert (
        "apps/server/src/orchestration-v2/runtimeLayer.ts" in files
    ), "the composition edit in runtimeLayer.ts must be part of the patch"


# ---------------------------------------------------------------------------
# 3. SECRETS: no obvious secret literals in the patch
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    # sk- followed by 16+ alphanumerics (OpenAI-style API keys, wrapped or not)
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    # api key / secret / token / password assignment literals
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9_\-+/]{8,}['\"]"
    ),
]


def test_patch_contains_no_secret_literals() -> None:
    patch_text = _patch_bytes().decode()
    for pattern in _SECRET_PATTERNS:
        match = pattern.search(patch_text)
        assert match is None, f"potential secret literal in patch: {match!r}"


# ---------------------------------------------------------------------------
# 4. APPLY-CHECK against the pinned clone (skipped when clone absent)
# ---------------------------------------------------------------------------


def _pinned_source() -> Path:
    return Path(os.environ.get("MMOS_T3_PINNED_SOURCE", DEFAULT_PINNED_SOURCE))


def test_git_apply_check_against_pinned_clone() -> None:
    source = _pinned_source()
    if not source.is_dir():
        pytest.skip(f"pinned T3 clone not present: {source}")

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == PIN, f"pinned clone HEAD {head} is not the expected pin {PIN}"

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout.strip() == "", "pinned clone working tree must be clean"

    check = subprocess.run(
        ["git", "apply", "--check", str(PATCH_PATH)],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, (
        f"git apply --check failed in pinned clone {source}:\n"
        f"stdout: {check.stdout}\nstderr: {check.stderr}"
    )


# ---------------------------------------------------------------------------
# 5. PIN QUOTED IN MANIFEST
# ---------------------------------------------------------------------------


def test_manifest_states_the_pin() -> None:
    manifest = _manifest_text()
    assert PIN in manifest, f"manifest must state the pin {PIN}"
    assert "pingdotgg/t3code" in manifest, "manifest must name the donor repo"


def test_patch_carries_donor_attribution() -> None:
    patch_text = _patch_bytes().decode()
    assert "github.com/pingdotgg/t3code" in patch_text, "patch must name the donor repo"
    assert PIN in patch_text, "patch must carry the pin SHA in its attribution line"


# ---------------------------------------------------------------------------
# 6. Audit finding #2: decorators never nest Layer.build; composition pinned
# ---------------------------------------------------------------------------


def _added_file_lines(patch_text: str, path: str) -> list[str]:
    """The ``+`` lines the patch adds to one file (without the ``+``)."""
    lines: list[str] = []
    current = None
    for raw in patch_text.splitlines():
        if raw.startswith("diff --git "):
            current = raw.split(" b/", 1)[-1]
            continue
        if current == path and raw.startswith("+") and not raw.startswith("+++"):
            lines.append(raw[1:])
    return lines


def _code_only(lines: list[str]) -> list[str]:
    """Drop comment-only lines (``//``, ``/*``, `` * ``) — prose may name APIs."""
    code: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*")):
            continue
        code.append(line)
    return code


def test_patch_bytes_are_the_pinned_a3_rework() -> None:
    assert hashlib.sha256(_patch_bytes()).hexdigest() == PATCH_SHA256
    assert PATCH_SHA256 in _manifest_text()


def test_decorators_never_nest_layer_build() -> None:
    """A nested ``Layer.build`` inside a decorator forks the memo map (effect
    4.1.2) and rebuilds shared singletons — refuted passthrough (audit #2)."""
    code = _code_only(_added_file_lines(_patch_bytes().decode(), ADAPTER_FILE))
    assert code, "the adapter module must be part of the patch"
    offenders = [line for line in code if "Layer.build" in line]
    assert offenders == [], f"decorator code still builds layers: {offenders}"
    joined = "\n".join(code)
    # The incumbent is wired by Layer.provide through the SAME memo map.
    assert "Layer.provide(incumbent)" in joined


def test_colocated_suite_pins_built_exactly_once_composition() -> None:
    test_lines = _added_file_lines(_patch_bytes().decode(), ADAPTER_TEST_FILE)
    joined = "\n".join(test_lines)
    assert "shared dependency is built exactly once" in joined
    assert "Layer.mergeAll(decorated, siblingLayer)" in joined
    assert "Layer.mergeAll(siblingLayer, decorated)" in joined
    assert "expect(counts.sharedStore).toBe(1)" in joined

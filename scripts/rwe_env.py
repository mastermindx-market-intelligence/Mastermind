"""RWE-P0: hash-locked, receipted worker environment for the test gate.

This is a narrow, pilot-scope task interface over the existing hash-pinned
pip pattern already proven in-estate (macro ``requirements/*.lock``). It owns
exactly: picking the right platform lock, refusing on an unsupported
interpreter, realizing a fresh venv with ``--require-hashes
--only-binary=:all:``, and emitting a secret-free JSON receipt describing
what was built. It does NOT own Job/Attempt/Worker lifecycle, provider
accounts, secrets, or the repository's source-of-truth CI workflow — the
``gate`` subcommand runs the *existing* ``scripts/ci_pytest.py`` gate inside
the realized environment; it never redefines what the gate is.

Subcommands
-----------
``lock``
    Print the exact ``pip-compile`` regeneration command for the current
    platform. Never runs it — minting a lock is a deliberate, reviewed act.
``realize --dest DIR [--lock PATH] [--python PATH] [--force]``
    Create a fresh venv at ``DIR`` from the platform-appropriate hash lock
    and write ``DIR/rwe_receipt.json``.
``receipt --env DIR``
    Recompute and rewrite the receipt for an already-realized env.
``gate --env DIR [--subset PATH]``
    Run the repository test gate (or a bounded ``pytest`` subset) using
    ``DIR``'s interpreter, and append the outcome to the receipt.

Receipt schema: ``mastermind.worker_environment/v1`` (see ``build_receipt``).
Hard rule: the receipt never contains secrets, raw environment-variable
dumps, raw host names, raw user/home paths, or provider identity — only
path *classes* and content digests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "mastermind.worker_environment/v1"

RECEIPT_FILENAME = "rwe_receipt.json"
CI_WORKFLOW_RELATIVE = Path(".github") / "workflows" / "ci.yml"
VENDOR_RELATIVE = Path("vendor") / "macro_src"
VENDOR_REPO = "mastermindx-market-intelligence/macro"
GATE_SCRIPT_RELATIVE = Path("scripts") / "ci_pytest.py"

REQUIRED_PYTHON_VERSION = (3, 12)
REQUIRED_PYTHON_IMPLEMENTATION = "CPython"

# platform (os, arch) -> lock filename under requirements/
PLATFORM_LOCKS: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "gate-macos-arm64-py312.lock",
    ("linux", "x86_64"): "gate-linux-x86_64-py312.lock",
}

DEFAULT_INTERPRETERS: dict[str, str] = {
    "darwin": "/opt/homebrew/bin/python3.12",
    "linux": "python3.12",
}

# Pinned build-backend versions used for the editable project install
# (`pip install -e . --no-deps --no-build-isolation`). These are exact
# versions, not hash-locked entries -- see requirements/README.md for the
# scoping of the no-silent-drift guarantee. Verified current-stable via
# `pip index versions setuptools wheel` at authoring time.
PINNED_BUILD_BACKEND: dict[str, str] = {"setuptools": "84.0.0", "wheel": "0.48.0"}

_DISCOVERED_RE = re.compile(r"^discovered=(\d+)\s")
_COLLECTED_RE = re.compile(r"(\d+)\s+(?:tests?|items?)\s+collected|collected\s+(\d+)\s+item")
# Sums every "<N> <category>" group on a pytest summary line so a mixed
# outcome line (e.g. "1 failed, 36 passed in 1.23s") counts every test, not
# just the first category matched.
_SUMMARY_COUNTS_RE = re.compile(r"(\d+)\s+(?:passed|failed|errors?|skipped|xfailed|xpassed)")
# pytest's quiet dot-progress output (e.g. "...F..s.. [100%]"); used only as
# a last-resort discovered-count fallback when a repository's own pytest.ini
# addopts already sets -q and a second explicit -q collapses to -qq, which
# suppresses the usual "N passed in Ns" summary line entirely.
_RESULT_CHAR_RUN_RE = re.compile(r"[.\sFEsxX]+\[\s*\d+%\]")

# Absolute host-path tokens that must never survive into a receipt (case
# handled by callers matching case-insensitively where needed).
_ABS_PATH_TOKEN_RE = re.compile(r"(?:/Users/|/home/|/root/)\S*", re.IGNORECASE)

_LOCK_PYPROJECT_SHA_RE = re.compile(r"^#\s*pyproject\.toml sha256:\s*([0-9a-fA-F]+)\s*$")


def _count_result_chars(output: str) -> int | None:
    total = 0
    found = False
    for match in _RESULT_CHAR_RUN_RE.finditer(output):
        found = True
        total += sum(1 for ch in match.group(0) if ch in ".FEsxX")
    return total if found else None


_SUMMARY_ANCHOR_RE = re.compile(
    r"^=*\s*\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed)\b"
    r".*\bin\s+\d+(?:\.\d+)?s\b"
)


def _sum_summary_line_counts(line: str) -> int | None:
    # Anchored to a genuine pytest summary line (starts with a count-category
    # pair, carries an "in <N>s" duration) so a traceback or captured log line
    # containing "<N> errors"/"<N> skipped" can never masquerade as the summary.
    stripped = line.strip()
    if not _SUMMARY_ANCHOR_RE.match(stripped):
        return None
    matches = _SUMMARY_COUNTS_RE.findall(stripped)
    if not matches:
        return None
    return sum(int(value) for value in matches)


def _scrub_pip_check_detail(detail: str, *, max_len: int = 400) -> str:
    """Scrub absolute host paths and cap length before a pip-check message
    is ever written into a receipt."""

    scrubbed = _ABS_PATH_TOKEN_RE.sub("<path>", detail)
    if len(scrubbed) > max_len:
        scrubbed = scrubbed[:max_len] + "...<truncated>"
    return scrubbed


class EnvError(RuntimeError):
    """A refused, fail-closed operation (missing lock, wrong interpreter, ...)."""


# ---------------------------------------------------------------------------
# repo root
# ---------------------------------------------------------------------------


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "requirements").exists():
            return candidate
        if (candidate / "pyproject.toml").is_file() and (candidate / "scripts" / "rwe_env.py").is_file():
            return candidate
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise EnvError("could not resolve repository root from rwe_env.py")


# ---------------------------------------------------------------------------
# platform / interpreter selection
# ---------------------------------------------------------------------------


def detect_platform_key() -> tuple[str, str]:
    """Return the ``(os, architecture)`` pair used to select a lock file."""

    os_name = platform.system().lower()
    if os_name not in ("darwin", "linux"):
        raise EnvError(f"unsupported operating system: {os_name!r}")
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        arch = "arm64"
    elif machine in ("x86_64", "amd64"):
        arch = "x86_64"
    else:
        raise EnvError(f"unsupported architecture: {machine!r}")
    return os_name, arch


def select_lock(root: Path, *, lock_override: str | None = None,
                 platform_key: tuple[str, str] | None = None) -> Path:
    """Pick the platform lock file, or refuse fail-closed if it is absent."""

    if lock_override:
        candidate = Path(lock_override)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            raise EnvError(
                f"explicit --lock resolves outside the repository root: {resolved} "
                f"(repo root: {root_resolved})"
            ) from None
        if not candidate.is_file():
            raise EnvError(f"explicit --lock does not exist: {candidate}")
        return candidate

    os_name, arch = platform_key or detect_platform_key()
    name = PLATFORM_LOCKS.get((os_name, arch))
    if name is None:
        raise EnvError(
            f"no platform lock registered for {os_name}/{arch}; "
            "run `python scripts/rwe_env.py lock` and mint one first"
        )
    candidate = root / "requirements" / name
    if not candidate.is_file():
        raise EnvError(
            f"platform lock is absent: requirements/{name} "
            "(run `python scripts/rwe_env.py lock` for the regeneration command)"
        )
    return candidate


def default_python_for_platform(os_name: str) -> str:
    default = DEFAULT_INTERPRETERS.get(os_name)
    if default is None:
        raise EnvError(f"no default interpreter registered for {os_name!r}")
    if os_name == "linux":
        resolved = shutil.which(default)
        if resolved:
            return resolved
        return default
    return default


def resolve_python_executable(python_arg: str | None, os_name: str) -> str:
    return python_arg or default_python_for_platform(os_name)


def probe_interpreter(python_exe: str) -> tuple[str, tuple[int, int]]:
    """Run ``python_exe`` and return ``(implementation, (major, minor))``.

    Raises ``EnvError`` if the interpreter cannot be run at all.
    """

    try:
        completed = subprocess.run(
            [
                python_exe,
                "-c",
                "import platform,sys;print(platform.python_implementation());"
                "print(sys.version_info.major, sys.version_info.minor)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise EnvError(f"interpreter not found or not runnable: {python_exe} ({exc})") from exc
    if completed.returncode != 0:
        raise EnvError(f"interpreter probe failed for {python_exe}: {completed.stderr.strip()}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise EnvError(f"interpreter probe produced unexpected output for {python_exe}")
    implementation = lines[0].strip()
    major_str, minor_str = lines[1].split()
    return implementation, (int(major_str), int(minor_str))


def require_supported_interpreter(python_exe: str) -> None:
    implementation, version = probe_interpreter(python_exe)
    if implementation != REQUIRED_PYTHON_IMPLEMENTATION or version != REQUIRED_PYTHON_VERSION:
        raise EnvError(
            f"refusing unsupported interpreter {python_exe}: "
            f"got {implementation} {version[0]}.{version[1]}, "
            f"require {REQUIRED_PYTHON_IMPLEMENTATION} "
            f"{REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}"
        )


def classify_python_executable_path(path: str) -> str:
    """Classify an interpreter path into a provider-neutral class.

    Never store the raw path in a receipt -- only this class.
    """

    lowered = path.replace("\\", "/").lower()
    if "/homebrew/" in lowered or lowered.startswith("/opt/homebrew"):
        return "homebrew"
    if "framework" in lowered:
        return "framework"
    if "hostedtoolcache" in lowered or "toolcache" in lowered:
        return "toolcache"
    return "other"


def read_venv_home(dest: Path) -> str | None:
    cfg = dest / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().lower() == "home":
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# digests
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def compute_environment_id(*, lock_sha256: str, os_name: str, arch: str,
                            python_version: str = "3.12") -> str:
    """Deterministic id: sha256(lock digest + platform triple + FULL
    interpreter version), first 16 hex.

    ``python_version`` must be the venv interpreter's complete
    ``platform.python_version()`` (e.g. ``"3.12.13"``, incl. patch) so a
    minor patch-level interpreter change is a different environment id, not
    a silently-identical one. Callers building a real receipt always pass
    the full version queried from the realized venv's own interpreter, never
    the driver's.
    """

    payload = f"{lock_sha256}:{os_name}:{arch}:cpython{python_version}".encode("ascii")
    return sha256_bytes(payload)[:16]


def check_lock_digest_matches(existing: Mapping[str, Any], lock_path: Path) -> None:
    """Refuse fail-closed if the lock file's content no longer matches what
    a prior receipt recorded for this environment.

    A realized venv is only trustworthy for as long as the lock it was
    built from is unchanged on disk; if the lock file was edited/replaced
    after ``realize`` ran, the environment silently no longer reflects what
    ``receipt``/``gate`` would claim it does.
    """

    definition = existing.get("definition") if existing else None
    if not definition or "lock_sha256" not in definition:
        return
    recorded = definition["lock_sha256"]
    current = sha256_file(lock_path)
    if recorded != current:
        raise EnvError(
            "lock content changed since this environment was realized: "
            f"recorded lock_sha256={recorded} current lock_sha256={current}; "
            "re-realize the environment from the current lock"
        )


def read_lock_pyproject_sha256(lock_path: Path) -> str | None:
    """Read the ``# pyproject.toml sha256: <hex>`` header line a lock file
    was minted with. Returns ``None`` for a hand-built lock carrying no such
    header (warn-only case -- see ``check_pyproject_not_stale``)."""

    for line in lock_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            # header comments always precede the package list; once we hit
            # a non-comment line we've walked past the header.
            break
        match = _LOCK_PYPROJECT_SHA_RE.match(stripped)
        if match:
            return match.group(1)
    return None


def check_pyproject_not_stale(root: Path, lock_path: Path) -> None:
    """Refuse fail-closed if ``pyproject.toml`` has drifted from the digest
    a lock file's header was minted against (a stale lock silently installs
    dependencies for a pyproject.toml that no longer exists). Warn-only (no
    refusal) when the lock carries no such header -- a hand-built lock
    predates this check and should not hard-fail on that basis alone.
    """

    recorded = read_lock_pyproject_sha256(lock_path)
    if recorded is None:
        return
    current = sha256_file(root / "pyproject.toml")
    if recorded != current:
        raise EnvError(
            "stale lock -- regenerate: "
            f"lock's pyproject.toml sha256={recorded} "
            f"current pyproject.toml sha256={current}"
        )


def compute_packages_installed(freeze_text: str) -> dict[str, Any]:
    """Reduce ``pip freeze`` output to a count + digest -- never the raw list."""

    lines = sorted(line.strip() for line in freeze_text.splitlines() if line.strip())
    joined = "\n".join(lines)
    return {"count": len(lines), "freeze_sha256": sha256_bytes(joined.encode("utf-8"))}


# ---------------------------------------------------------------------------
# vendored macro ref parsing
# ---------------------------------------------------------------------------


def parse_pinned_ref(ci_yml_text: str, *, repo: str = VENDOR_REPO) -> str:
    """Read the pinned ``ref:`` for ``repo`` out of a ci.yml checkout step.

    Looks for the line naming ``repository: <repo>`` and then the nearest
    ``ref:`` line within the same step (bounded lookahead so an unrelated
    later step can never be mistaken for this one).
    """

    lines = ci_yml_text.splitlines()
    repo_line_re = re.compile(r"^\s*repository:\s*['\"]?" + re.escape(repo) + r"['\"]?\s*$")
    ref_line_re = re.compile(r"^\s*ref:\s*['\"]?(\S+?)['\"]?\s*$")
    for index, line in enumerate(lines):
        if not repo_line_re.match(line):
            continue
        for lookahead in lines[index + 1 : index + 15]:
            match = ref_line_re.match(lookahead)
            if match:
                return match.group(1)
            # a new top-level step boundary means we've walked past this step
            if lookahead.lstrip().startswith("- name:") or lookahead.lstrip().startswith("- uses:"):
                break
        raise EnvError(f"found repository: {repo} but no ref: within its checkout step")
    raise EnvError(f"no checkout step pins repository: {repo}")


def read_pinned_ref(root: Path) -> str | None:
    workflow = root / CI_WORKFLOW_RELATIVE
    if not workflow.is_file():
        return None
    try:
        return parse_pinned_ref(workflow.read_text(encoding="utf-8"))
    except EnvError:
        return None


def vendor_present(root: Path) -> bool:
    vendor_dir = root / VENDOR_RELATIVE
    if not vendor_dir.is_dir():
        return False
    try:
        return any(vendor_dir.iterdir())
    except OSError:
        return False


def resolved_vendor_ref(root: Path) -> str | None:
    """Return the vendored checkout's actual ``HEAD`` sha, or ``None`` when
    unavailable (no ``.git`` under the vendor dir, or the probe fails). This
    is the *measured* ref, distinct from ``read_pinned_ref``'s claimed one --
    ``build_receipt`` records both plus whether they agree."""

    vendor_git = root / VENDOR_RELATIVE / ".git"
    if not vendor_git.exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(root / VENDOR_RELATIVE), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def checkout_command_for(ref: str | None, repo: str = VENDOR_REPO) -> str:
    ref_display = ref or "<ref pinned in .github/workflows/ci.yml>"
    return (
        "git clone --no-checkout https://github.com/{repo}.git vendor/macro_src\n"
        "cd vendor/macro_src\n"
        "git sparse-checkout init --cone\n"
        "git sparse-checkout set engine lib\n"
        "git checkout {ref}\n"
        "cd -"
    ).format(repo=repo, ref=ref_display)


# ---------------------------------------------------------------------------
# receipt assembly
# ---------------------------------------------------------------------------

# NOTE: the receipt never records DIR (an operator-chosen, possibly
# user-specific path) or ROOT verbatim. Every command/path field written
# into a receipt uses the fixed placeholder "<env>" for the realized venv
# directory and repo-relative paths for anything under the repository.


def build_receipt(
    *,
    root: Path,
    env_dir: Path,
    lock_path: Path,
    os_name: str,
    arch: str,
    python_implementation: str,
    python_version: str,
    python_executable_class: str,
    packages_installed: Mapping[str, Any],
    realized_at: str,
    pip_check_ok: bool,
    pip_check_detail: str = "",
    degraded: Sequence[str] = (),
    build_backend: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    pyproject_sha256 = sha256_file(root / "pyproject.toml")
    lock_sha256 = sha256_file(lock_path)
    lock_relative = lock_path.resolve().relative_to(root.resolve()).as_posix()
    # environment_id folds in the FULL venv interpreter version (incl.
    # patch), not just major.minor -- a patch-level interpreter change is a
    # different environment, never silently identical (MAJOR-1).
    environment_id = compute_environment_id(
        lock_sha256=lock_sha256, os_name=os_name, arch=arch, python_version=python_version
    )
    ref = read_pinned_ref(root)
    resolved_ref = resolved_vendor_ref(root)
    ref_match: bool | None
    if ref is not None and resolved_ref is not None:
        ref_match = ref == resolved_ref
    else:
        ref_match = None
    pip_check_value = "ok" if pip_check_ok else (_scrub_pip_check_detail(pip_check_detail) or "error")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "environment_id": environment_id,
        "definition": {
            "kind": "pip-hash-lock",
            "pyproject_sha256": pyproject_sha256,
            "lock_path": lock_relative,
            "lock_sha256": lock_sha256,
        },
        "platform": {
            "os": os_name,
            "architecture": arch,
            "python_implementation": python_implementation,
            "python_version": python_version,
            "python_executable_class": python_executable_class,
        },
        "packages_installed": dict(packages_installed),
        "build_backend": dict(build_backend) if build_backend else {},
        "vendored_inputs": [
            {
                "repo": VENDOR_REPO,
                "ref": ref,
                "resolved_ref": resolved_ref,
                "match": ref_match,
                "dest": VENDOR_RELATIVE.as_posix(),
                "present": vendor_present(root),
            }
        ],
        "realized_at": realized_at,
        "proof": {
            "pip_check": pip_check_value,
        },
        "degraded": list(degraded),
    }
    return receipt


def load_receipt(env_dir: Path) -> dict[str, Any] | None:
    path = env_dir / RECEIPT_FILENAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_receipt(env_dir: Path, receipt: Mapping[str, Any]) -> Path:
    path = env_dir / RECEIPT_FILENAME
    path.write_text(json.dumps(receipt, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# subprocess helpers over the realized venv
# ---------------------------------------------------------------------------


def _venv_python(env_dir: Path) -> Path:
    candidate = env_dir / "bin" / "python"
    if candidate.is_file():
        return candidate
    candidate = env_dir / "Scripts" / "python.exe"
    return candidate


def _pip_freeze(venv_python: Path) -> str:
    completed = subprocess.run(
        [str(venv_python), "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout


def _pip_check(venv_python: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        [str(venv_python), "-m", "pip", "check"],
        capture_output=True,
        text=True,
        check=False,
    )
    ok = completed.returncode == 0
    detail = (completed.stdout + completed.stderr).strip()
    return ok, detail if not ok else ""


def probe_python_version_full(python_exe: str) -> str:
    """Return the interpreter's FULL ``platform.python_version()`` (incl.
    patch, e.g. ``"3.12.13"``), queried from ``python_exe`` itself -- never
    inferred from the driver's own version or truncated to major.minor."""

    try:
        completed = subprocess.run(
            [python_exe, "-c", "import platform;print(platform.python_version())"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise EnvError(f"python_version probe failed for {python_exe}: {exc}") from exc
    if completed.returncode != 0:
        raise EnvError(f"python_version probe failed for {python_exe}: {completed.stderr.strip()}")
    value = completed.stdout.strip()
    if not value:
        raise EnvError(f"python_version probe produced no output for {python_exe}")
    return value


def _venv_platform_info(venv_python: Path) -> tuple[str, str]:
    implementation, _ = probe_interpreter(str(venv_python))
    full_version = probe_python_version_full(str(venv_python))
    return implementation, full_version


# ---------------------------------------------------------------------------
# subcommand: lock
# ---------------------------------------------------------------------------


def cmd_lock(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    try:
        os_name, arch = detect_platform_key()
    except EnvError as exc:
        print(f"rwe_env lock refused: {exc}", file=sys.stderr)
        return 2
    name = PLATFORM_LOCKS.get((os_name, arch))
    if name is None:
        print(
            f"no platform lock is registered for {os_name}/{arch} in PLATFORM_LOCKS; "
            "add an entry before compiling one",
            file=sys.stderr,
        )
        return 2
    print(
        "pip-compile --quiet --generate-hashes --extra dev "
        f"--output-file requirements/{name} pyproject.toml"
    )
    print(f"# run from {root} with a pip-tools-equipped interpreter (network to PyPI required)")
    return 0


# ---------------------------------------------------------------------------
# subcommand: realize
# ---------------------------------------------------------------------------


def cmd_realize(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    try:
        os_name, arch = detect_platform_key()
        lock_path = select_lock(root, lock_override=args.lock, platform_key=(os_name, arch))
        check_pyproject_not_stale(root, lock_path)
        python_exe = resolve_python_executable(args.python, os_name)
        require_supported_interpreter(python_exe)
    except EnvError as exc:
        print(f"rwe_env realize refused: {exc}", file=sys.stderr)
        return 2

    dest = Path(args.dest).resolve()
    if dest.exists():
        if not args.force:
            print(
                f"rwe_env realize refused: destination already exists: {dest} "
                "(pass --force to replace it)",
                file=sys.stderr,
            )
            return 2
        shutil.rmtree(dest)

    print(f"creating venv at {dest} from {python_exe}")
    created = subprocess.run([python_exe, "-m", "venv", str(dest)], check=False)
    if created.returncode != 0:
        print("rwe_env realize refused: venv creation failed", file=sys.stderr)
        return created.returncode

    venv_python = _venv_python(dest)

    install_lock = subprocess.run(
        [
            str(venv_python), "-m", "pip", "install",
            "--require-hashes", "--only-binary=:all:",
            "-r", str(lock_path),
        ],
        cwd=root,
        check=False,
    )
    if install_lock.returncode != 0:
        print("rwe_env realize refused: hash-locked install failed", file=sys.stderr)
        return install_lock.returncode

    # The editable project install itself is not part of the hash lock (it
    # has no sdist/wheel to hash), so it runs with an explicit, pinned
    # build backend instead of resolving one from PyPI at install time --
    # --no-build-isolation makes pip use exactly the setuptools/wheel
    # installed into this venv, not whatever isolated build env pip would
    # otherwise construct (MINOR-5). Hashes are not required for these two
    # packages only; see requirements/README.md for the scoping.
    install_build_backend = subprocess.run(
        [
            str(venv_python), "-m", "pip", "install",
            f"setuptools=={PINNED_BUILD_BACKEND['setuptools']}",
            f"wheel=={PINNED_BUILD_BACKEND['wheel']}",
        ],
        cwd=root,
        check=False,
    )
    if install_build_backend.returncode != 0:
        print("rwe_env realize refused: pinned build-backend install failed", file=sys.stderr)
        return install_build_backend.returncode

    install_editable = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-e", ".", "--no-deps", "--no-build-isolation"],
        cwd=root,
        check=False,
    )
    if install_editable.returncode != 0:
        print("rwe_env realize refused: editable install of the project failed", file=sys.stderr)
        return install_editable.returncode

    pip_check_ok, pip_check_detail = _pip_check(venv_python)
    freeze_text = _pip_freeze(venv_python)
    packages_installed = compute_packages_installed(freeze_text)
    implementation, python_version = _venv_platform_info(venv_python)
    python_executable_class = classify_python_executable_path(python_exe)

    receipt = build_receipt(
        root=root,
        env_dir=dest,
        lock_path=lock_path,
        os_name=os_name,
        arch=arch,
        python_implementation=implementation,
        python_version=python_version,
        python_executable_class=python_executable_class,
        packages_installed=packages_installed,
        realized_at=_now_iso(),
        pip_check_ok=pip_check_ok,
        pip_check_detail=pip_check_detail,
        build_backend=PINNED_BUILD_BACKEND,
    )
    path = write_receipt(dest, receipt)
    print(f"pip check: {'ok' if pip_check_ok else pip_check_detail}")
    print(f"receipt written: {path}")
    print(f"environment_id={receipt['environment_id']}")
    return 0


# ---------------------------------------------------------------------------
# subcommand: receipt
# ---------------------------------------------------------------------------


def cmd_receipt(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    env_dir = Path(args.env).resolve()
    venv_python = _venv_python(env_dir)
    if not venv_python.is_file():
        print(f"rwe_env receipt refused: no interpreter found under {env_dir}", file=sys.stderr)
        return 2

    try:
        require_supported_interpreter(str(venv_python))
    except EnvError as exc:
        print(f"rwe_env receipt refused: {exc}", file=sys.stderr)
        return 2

    existing = load_receipt(env_dir)
    if existing is None or "definition" not in existing:
        print(
            "rwe_env receipt refused: no prior rwe_receipt.json to re-emit from; "
            "run `realize` first",
            file=sys.stderr,
        )
        return 2

    lock_relative = existing["definition"]["lock_path"]
    lock_path = root / lock_relative
    if not lock_path.is_file():
        print(f"rwe_env receipt refused: recorded lock is missing: {lock_relative}", file=sys.stderr)
        return 2

    try:
        check_lock_digest_matches(existing, lock_path)
        check_pyproject_not_stale(root, lock_path)
    except EnvError as exc:
        print(f"rwe_env receipt refused: {exc}", file=sys.stderr)
        return 2

    os_name = existing.get("platform", {}).get("os") or detect_platform_key()[0]
    arch = existing.get("platform", {}).get("architecture") or detect_platform_key()[1]

    pip_check_ok, pip_check_detail = _pip_check(venv_python)
    freeze_text = _pip_freeze(venv_python)
    packages_installed = compute_packages_installed(freeze_text)
    implementation, python_version = _venv_platform_info(venv_python)

    home = read_venv_home(env_dir)
    python_executable_class = (
        classify_python_executable_path(home)
        if home
        else existing.get("platform", {}).get("python_executable_class", "other")
    )

    receipt = build_receipt(
        root=root,
        env_dir=env_dir,
        lock_path=lock_path,
        os_name=os_name,
        arch=arch,
        python_implementation=implementation,
        python_version=python_version,
        python_executable_class=python_executable_class,
        packages_installed=packages_installed,
        realized_at=existing.get("realized_at") or _now_iso(),
        pip_check_ok=pip_check_ok,
        pip_check_detail=pip_check_detail,
        build_backend=existing.get("build_backend"),
    )
    # carry forward a prior gate proof, if any -- receipt does not re-run the gate
    prior_gate = existing.get("proof", {}).get("gate")
    if prior_gate is not None:
        receipt["proof"]["gate"] = prior_gate
    receipt["degraded"] = existing.get("degraded", [])

    path = write_receipt(env_dir, receipt)
    print(f"receipt re-emitted: {path}")
    print(f"environment_id={receipt['environment_id']}")
    return 0


# ---------------------------------------------------------------------------
# subcommand: gate
# ---------------------------------------------------------------------------


def _parse_discovered(output: str) -> int | None:
    last_summary: int | None = None
    for line in output.splitlines():
        match = _DISCOVERED_RE.match(line.strip())
        if match:
            return int(match.group(1))
        match = _COLLECTED_RE.search(line)
        if match:
            group = match.group(1) or match.group(2)
            if group:
                return int(group)
        # Sums every category on the pytest summary line (e.g. "1 failed,
        # 36 passed in 1.23s" -> 37), not just the first category matched.
        # The LAST anchored summary line wins: pytest prints its summary at
        # the end, after any output that could contain summary-shaped text.
        summed = _sum_summary_line_counts(line)
        if summed is not None:
            last_summary = summed
    if last_summary is not None:
        return last_summary
    return _count_result_chars(output)


def _display_subset_path(root: Path, subset: str) -> str:
    """Repo-relativize a ``--subset`` path for display/receipt purposes;
    replace it with the literal placeholder ``<subset>`` when it resolves
    outside the repository root. The real, unmodified ``subset`` is still
    used to actually invoke pytest -- only the receipt-bound display value
    is ever repo-relativized/placeholder'd, so an absolute out-of-repo host
    path (which may embed a username or home directory) never reaches the
    receipt (MAJOR-3)."""

    try:
        subset_path = Path(subset)
        root_resolved = root.resolve()
        # A relative subset is executed with cwd=root, so resolve it against
        # root (not the driver's cwd) so the displayed path is the one run.
        if not subset_path.is_absolute():
            subset_path = root_resolved / subset_path
        resolved = subset_path.resolve()
        relative = resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return "<subset>"
    return relative.as_posix()


def cmd_gate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    env_dir = Path(args.env).resolve()
    venv_python = _venv_python(env_dir)
    if not venv_python.is_file():
        print(f"rwe_env gate refused: no interpreter found under {env_dir}", file=sys.stderr)
        return 2

    try:
        require_supported_interpreter(str(venv_python))
    except EnvError as exc:
        print(f"rwe_env gate refused: {exc}", file=sys.stderr)
        return 2

    existing = load_receipt(env_dir)
    degraded: list[str] = list(dict.fromkeys(existing.get("degraded", []))) if existing else []

    if existing is not None and "definition" in existing:
        lock_relative = existing["definition"].get("lock_path")
        lock_path = root / lock_relative if lock_relative else None
        if lock_path is not None and not lock_path.is_file():
            print(f"rwe_env gate refused: recorded lock is missing: {lock_relative}", file=sys.stderr)
            return 2
        if lock_path is not None:
            try:
                check_lock_digest_matches(existing, lock_path)
            except EnvError as exc:
                print(f"rwe_env gate refused: {exc}", file=sys.stderr)
                return 2

    present = vendor_present(root)
    subset = args.subset

    if subset is None and not present:
        ref = read_pinned_ref(root)
        print(
            "rwe_env gate refused: vendor/macro_src is absent -- the full "
            "repository test gate needs it (checkout of the pinned macro "
            "engine/lib surface). Reproduce ci.yml's checkout step:\n",
            file=sys.stderr,
        )
        print(checkout_command_for(ref), file=sys.stderr)
        print(
            "\nThis version of rwe_env does not auto-clone the vendored "
            "input. Pass --subset PATH to run a bounded, vendor-independent "
            "probe instead.",
            file=sys.stderr,
        )
        return 2

    start = time.monotonic()
    if subset is not None:
        display_python = "<env>/bin/python"
        display_subset = _display_subset_path(root, subset)
        argv = [str(venv_python), "-m", "pytest", "-q", subset]
        display_argv = [display_python, "-m", "pytest", "-q", display_subset]
        completed = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=False)
        if not present and "full_gate_unavailable:vendor_absent" not in degraded:
            degraded.append("full_gate_unavailable:vendor_absent")
    else:
        display_python = "<env>/bin/python"
        argv = [str(venv_python), str(root / GATE_SCRIPT_RELATIVE)]
        display_argv = [display_python, GATE_SCRIPT_RELATIVE.as_posix()]
        completed = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=False)
        if completed.returncode == 0 and "full_gate_unavailable:vendor_absent" in degraded:
            # a full gate just ran successfully, so any stale degraded flag
            # from an earlier subset-only run no longer applies (MINOR-3).
            degraded.remove("full_gate_unavailable:vendor_absent")
    elapsed = time.monotonic() - start

    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)

    discovered = _parse_discovered(completed.stdout)
    if discovered is None:
        discovered = _parse_discovered(completed.stderr)

    gate_proof = {
        "command": " ".join(display_argv),
        "exit": completed.returncode,
        "discovered": discovered,
        "seconds": round(elapsed, 2),
    }

    # Build (or rebuild) the receipt so `gate` works standalone after `realize`.
    if existing is not None and "definition" in existing:
        receipt_args = argparse.Namespace(root=str(root), env=str(env_dir))
        rc = cmd_receipt(receipt_args)
        if rc != 0:
            print("rwe_env gate: warning -- could not refresh receipt", file=sys.stderr)
            receipt = existing
        else:
            receipt = load_receipt(env_dir) or existing
    else:
        print(
            "rwe_env gate: no prior receipt found; gate result will be recorded "
            "without full environment provenance",
            file=sys.stderr,
        )
        receipt = {"schema": SCHEMA, "proof": {}}

    receipt.setdefault("proof", {})["gate"] = gate_proof
    receipt["degraded"] = degraded
    write_receipt(env_dir, receipt)

    print(f"gate: {gate_proof}")
    return completed.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_lock = sub.add_parser("lock", help="print the pip-compile regeneration command")
    p_lock.add_argument("--root", default=None)
    p_lock.set_defaults(func=cmd_lock)

    p_realize = sub.add_parser("realize", help="build a fresh hash-locked venv + receipt")
    p_realize.add_argument("--dest", required=True)
    p_realize.add_argument("--lock", default=None)
    p_realize.add_argument("--python", default=None)
    p_realize.add_argument("--force", action="store_true")
    p_realize.add_argument("--root", default=None)
    p_realize.set_defaults(func=cmd_realize)

    p_receipt = sub.add_parser("receipt", help="re-emit the receipt for an existing env")
    p_receipt.add_argument("--env", required=True)
    p_receipt.add_argument("--root", default=None)
    p_receipt.set_defaults(func=cmd_receipt)

    p_gate = sub.add_parser("gate", help="run the repository test gate inside an env")
    p_gate.add_argument("--env", required=True)
    p_gate.add_argument("--subset", default=None)
    p_gate.add_argument("--root", default=None)
    p_gate.set_defaults(func=cmd_gate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except EnvError as exc:
        # Defense in depth: individual subcommands already catch the
        # EnvError cases they anticipate and print a clean refusal message.
        # This catches anything raised earlier (e.g. repo_root() itself)
        # so a refusal is always a one-line stderr message, never a
        # traceback.
        print(f"rwe_env refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

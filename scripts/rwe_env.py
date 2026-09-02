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

_DISCOVERED_RE = re.compile(r"^discovered=(\d+)\s")
_COLLECTED_RE = re.compile(r"(\d+)\s+(?:tests?|items?)\s+collected|collected\s+(\d+)\s+item")
_SUMMARY_LINE_RE = re.compile(r"^(\d+)\s+(?:passed|failed|error)")
# pytest's quiet dot-progress output (e.g. "...F..s.. [100%]"); used only as
# a last-resort discovered-count fallback when a repository's own pytest.ini
# addopts already sets -q and a second explicit -q collapses to -qq, which
# suppresses the usual "N passed in Ns" summary line entirely.
_RESULT_CHAR_RUN_RE = re.compile(r"[.\sFEsxX]+\[\s*\d+%\]")


def _count_result_chars(output: str) -> int | None:
    total = 0
    found = False
    for match in _RESULT_CHAR_RUN_RE.finditer(output):
        found = True
        total += sum(1 for ch in match.group(0) if ch in ".FEsxX")
    return total if found else None


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
    """Deterministic id: sha256(lock digest + platform triple), first 16 hex."""

    payload = f"{lock_sha256}:{os_name}:{arch}:cpython{python_version}".encode("ascii")
    return sha256_bytes(payload)[:16]


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
) -> dict[str, Any]:
    pyproject_sha256 = sha256_file(root / "pyproject.toml")
    lock_sha256 = sha256_file(lock_path)
    lock_relative = lock_path.resolve().relative_to(root.resolve()).as_posix()
    environment_id = compute_environment_id(
        lock_sha256=lock_sha256, os_name=os_name, arch=arch, python_version="3.12"
    )
    ref = read_pinned_ref(root)
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
        "vendored_inputs": [
            {
                "repo": VENDOR_REPO,
                "ref": ref,
                "dest": VENDOR_RELATIVE.as_posix(),
                "present": vendor_present(root),
            }
        ],
        "realized_at": realized_at,
        "proof": {
            "pip_check": "ok" if pip_check_ok else (pip_check_detail or "error"),
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


def _venv_platform_info(venv_python: Path) -> tuple[str, str]:
    implementation, version = probe_interpreter(str(venv_python))
    return implementation, f"{version[0]}.{version[1]}"


# ---------------------------------------------------------------------------
# subcommand: lock
# ---------------------------------------------------------------------------


def cmd_lock(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    os_name, arch = detect_platform_key()
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

    install_editable = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-e", ".", "--no-deps"],
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
    for line in output.splitlines():
        match = _DISCOVERED_RE.match(line.strip())
        if match:
            return int(match.group(1))
        match = _COLLECTED_RE.search(line)
        if match:
            group = match.group(1) or match.group(2)
            if group:
                return int(group)
        match = _SUMMARY_LINE_RE.match(line.strip())
        if match:
            return int(match.group(1))
    return _count_result_chars(output)


def cmd_gate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    env_dir = Path(args.env).resolve()
    venv_python = _venv_python(env_dir)
    if not venv_python.is_file():
        print(f"rwe_env gate refused: no interpreter found under {env_dir}", file=sys.stderr)
        return 2

    existing = load_receipt(env_dir)
    degraded: list[str] = list(dict.fromkeys(existing.get("degraded", []))) if existing else []

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
        argv = [str(venv_python), "-m", "pytest", "-q", subset]
        display_argv = [display_python, "-m", "pytest", "-q", subset]
        completed = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=False)
        if not present and "full_gate_unavailable:vendor_absent" not in degraded:
            degraded.append("full_gate_unavailable:vendor_absent")
    else:
        display_python = "<env>/bin/python"
        argv = [str(venv_python), str(root / GATE_SCRIPT_RELATIVE)]
        display_argv = [display_python, GATE_SCRIPT_RELATIVE.as_posix()]
        completed = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=False)
    elapsed = time.monotonic() - start

    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)

    discovered = _parse_discovered(completed.stdout) or _parse_discovered(completed.stderr)

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
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

"""Atomic installer for the pinned private Chrome DevTools MCP runtime.

This is an operator/host installation utility, not a model-facing tool. It
creates a versioned runtime directory only after npm's lock/integrity checks and
an exact CLI-version probe succeed. It never replaces an existing release.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Callable, Any

from .runtime import (
    CLI_RELATIVE_PATH,
    PACKAGE_NAME,
    PACKAGE_VERSION,
    RuntimePackageError,
    build_runtime_install_plan,
    validate_runtime_package,
)


class RuntimeInstallError(RuntimeError):
    """A runtime install or exact installed-release verification failed."""


@dataclass(frozen=True, slots=True)
class InstalledRuntime:
    final_root: Path
    cli_path: Path
    package_version: str
    installed_now: bool

    @property
    def is_admission(self) -> bool:
        return False


def _default_package_root() -> Path:
    return Path(__file__).resolve().parent.parent / "mastermind_browser_devtools_runtime"


def _load_json_file(path: Path) -> object:
    try:
        observed = path.lstat()
        if not stat.S_ISREG(observed.st_mode) or path.is_symlink():
            raise RuntimeInstallError("runtime package source must be a regular file")
        return json.loads(path.read_text(encoding="utf-8"))
    except RuntimeInstallError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeInstallError("runtime package source is unreadable") from exc


def _real_regular_file(path: Path, *, executable: bool) -> None:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise RuntimeInstallError("required runtime executable is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        raise RuntimeInstallError("required runtime executable is unsafe")
    if executable and not os.access(path, os.X_OK):
        raise RuntimeInstallError("required runtime executable is not executable")
    if not executable and not os.access(path, os.R_OK):
        raise RuntimeInstallError("required runtime file is unreadable")


def _ensure_real_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        try:
            observed = path.lstat()
        except OSError as exc:
            raise RuntimeInstallError("runtime directory is unavailable") from exc
        if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
            raise RuntimeInstallError("runtime directory is unsafe")
        return
    try:
        path.mkdir(parents=True, mode=0o700)
        os.chmod(path, 0o700)
    except OSError as exc:
        raise RuntimeInstallError("runtime directory cannot be created") from exc
    if path.is_symlink() or not path.is_dir():
        raise RuntimeInstallError("runtime directory identity changed")


def _validate_installed(
    root: Path,
    *,
    node_executable: Path,
    run_command: Callable[..., Any],
    env: dict[str, str],
) -> None:
    package_file = root / "node_modules" / PACKAGE_NAME / "package.json"
    cli = root / CLI_RELATIVE_PATH
    package = _load_json_file(package_file)
    if (
        type(package) is not dict
        or package.get("name") != PACKAGE_NAME
        or package.get("version") != PACKAGE_VERSION
    ):
        raise RuntimeInstallError("installed package identity mismatch")
    _real_regular_file(cli, executable=False)
    try:
        completed = run_command(
            [str(node_executable), str(cli), "--version"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
    except Exception as exc:
        raise RuntimeInstallError("installed CLI version probe failed") from exc
    if getattr(completed, "stdout", "").strip() != PACKAGE_VERSION:
        raise RuntimeInstallError("installed CLI version mismatch")


def install_devtools_runtime(
    *,
    runtime_parent: Path,
    cache_root: Path,
    node_executable: Path,
    node_version: str,
    npm_cli: Path,
    run_command: Callable[..., Any] = subprocess.run,
    package_root: Path | None = None,
) -> InstalledRuntime:
    """Install or validate one immutable versioned runtime release."""
    package_source = package_root if package_root is not None else _default_package_root()
    if type(package_source) is not Path:
        package_source = Path(package_source)

    package_json = _load_json_file(package_source / "package.json")
    package_lock = _load_json_file(package_source / "package-lock.json")
    try:
        validate_runtime_package(package_json, package_lock)
        # Pure syntax/version validation before any directory or subprocess effect.
        build_runtime_install_plan(
            runtime_root=str(runtime_parent / f"{PACKAGE_NAME}-{PACKAGE_VERSION}"),
            cache_root=str(cache_root),
            node_executable=str(node_executable),
            node_version=node_version,
            npm_cli=str(npm_cli),
        )
    except RuntimePackageError as exc:
        raise RuntimeInstallError("runtime install inputs refused") from exc

    _real_regular_file(node_executable, executable=True)
    _real_regular_file(npm_cli, executable=False)

    if runtime_parent.is_symlink() or cache_root.is_symlink():
        raise RuntimeInstallError("runtime directory boundary is symlinked")
    _ensure_real_directory(runtime_parent)
    _ensure_real_directory(cache_root)

    final_root = runtime_parent / f"{PACKAGE_NAME}-{PACKAGE_VERSION}"
    final_cli = final_root / CLI_RELATIVE_PATH
    base_env = {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"}

    if final_root.exists() or final_root.is_symlink():
        if final_root.is_symlink() or not final_root.is_dir():
            raise RuntimeInstallError("existing runtime release is unsafe")
        verify_env = dict(base_env)
        verify_env["HOME"] = str(final_root)
        _validate_installed(
            final_root,
            node_executable=node_executable,
            run_command=run_command,
            env=verify_env,
        )
        return InstalledRuntime(
            final_root=final_root,
            cli_path=final_cli,
            package_version=PACKAGE_VERSION,
            installed_now=False,
        )

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".install-{PACKAGE_NAME}-{PACKAGE_VERSION}-",
            dir=runtime_parent,
        )
    )
    try:
        if staging.is_symlink() or not staging.is_dir():
            raise RuntimeInstallError("staging runtime identity is unsafe")
        os.chmod(staging, 0o700)
        shutil.copyfile(package_source / "package.json", staging / "package.json")
        shutil.copyfile(package_source / "package-lock.json", staging / "package-lock.json")
        os.chmod(staging / "package.json", 0o600)
        os.chmod(staging / "package-lock.json", 0o600)

        home = staging / ".home"
        home.mkdir(mode=0o700)
        plan = build_runtime_install_plan(
            runtime_root=str(staging),
            cache_root=str(cache_root),
            node_executable=str(node_executable),
            node_version=node_version,
            npm_cli=str(npm_cli),
        )
        env = dict(base_env)
        env["HOME"] = str(home)
        try:
            run_command(
                [plan.command, *plan.argv],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                shell=False,
            )
        except Exception as exc:
            raise RuntimeInstallError("npm ci failed") from exc

        _validate_installed(
            staging,
            node_executable=node_executable,
            run_command=run_command,
            env=env,
        )
        shutil.rmtree(home, ignore_errors=False)

        try:
            os.rename(staging, final_root)
        except FileExistsError:
            # A concurrent installer won. Never replace it; validate and reuse.
            shutil.rmtree(staging)
            verify_env = dict(base_env)
            verify_env["HOME"] = str(final_root)
            _validate_installed(
                final_root,
                node_executable=node_executable,
                run_command=run_command,
                env=verify_env,
            )
            return InstalledRuntime(
                final_root=final_root,
                cli_path=final_cli,
                package_version=PACKAGE_VERSION,
                installed_now=False,
            )

        return InstalledRuntime(
            final_root=final_root,
            cli_path=final_cli,
            package_version=PACKAGE_VERSION,
            installed_now=True,
        )
    except RuntimeInstallError:
        if staging.exists() and staging != final_root:
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:
        if staging.exists() and staging != final_root:
            shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeInstallError("runtime installation failed") from exc

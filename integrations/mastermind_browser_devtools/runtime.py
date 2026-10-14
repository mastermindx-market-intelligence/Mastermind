"""Reproducible runtime-package contract for Chrome DevTools MCP.

This module plans an install but performs no filesystem, network, subprocess,
package-manager, Chrome, auth, scheduling or runtime effect. The installer or
host owner must validate actual paths/bytes and execute the plan separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

PACKAGE_NAME = "chrome-devtools-mcp"
PACKAGE_VERSION = "1.10.1"
PACKAGE_RESOLVED = (
    "https://registry.npmjs.org/chrome-devtools-mcp/-/"
    "chrome-devtools-mcp-1.10.1.tgz"
)
PACKAGE_INTEGRITY = (
    "sha512-Klw6HWDqHC/XS1JwZldd2r49aUhbUJN9m9Mvcx4SEueIPXtzuQX+"
    "QelxAViobv8YUkDZ7HWDrmViR6LeYK0wAw=="
)
CLI_RELATIVE_PATH = (
    "node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js"
)
RUNTIME_PACKAGE_NAME = "mastermind-browser-devtools-runtime"
RUNTIME_PACKAGE_VERSION = "0.1.0"
_NODE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class RuntimePackageError(ValueError):
    """The pinned runtime package or install projection drifted."""


@dataclass(frozen=True, slots=True)
class RuntimePackageIdentity:
    package_name: str
    package_version: str
    resolved: str
    integrity: str
    cli_relative_path: str

    @property
    def is_installation(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class RuntimeInstallPlan:
    command: str
    argv: tuple[str, ...]
    runtime_root: str
    cache_root: str
    node_version: str
    cli_path: str
    package_version: str

    @property
    def is_installation(self) -> bool:
        return False


def _absolute(value: object, name: str) -> str:
    if type(value) is not str or not value.startswith("/") or value == "/" or "\x00" in value:
        raise RuntimePackageError(f"{name} must be an absolute normalized path")
    path = PurePosixPath(value)
    if ".." in path.parts or "." in path.parts or str(path) != value.rstrip("/"):
        raise RuntimePackageError(f"{name} must be an absolute normalized path")
    return value


def _supported_node(value: object) -> str:
    if type(value) is not str:
        raise RuntimePackageError("node_version is invalid")
    match = _NODE_VERSION.fullmatch(value)
    if match is None:
        raise RuntimePackageError("node_version is invalid")
    major, minor, _patch = (int(part) for part in match.groups())
    if major >= 23 or (major == 22 and minor >= 12) or (major == 20 and minor >= 19):
        return value
    raise RuntimePackageError("node_version is unsupported")


def validate_runtime_package(
    package_json: object,
    lock_json: object,
) -> RuntimePackageIdentity:
    """Validate the exact committed npm package and lock contract."""
    expected_package = {
        "name": RUNTIME_PACKAGE_NAME,
        "private": True,
        "version": RUNTIME_PACKAGE_VERSION,
        "dependencies": {PACKAGE_NAME: PACKAGE_VERSION},
    }
    if package_json != expected_package or type(lock_json) is not dict:
        raise RuntimePackageError("runtime package manifest drift")

    if (
        lock_json.get("name") != RUNTIME_PACKAGE_NAME
        or lock_json.get("version") != RUNTIME_PACKAGE_VERSION
        or lock_json.get("lockfileVersion") != 3
        or lock_json.get("requires") is not True
    ):
        raise RuntimePackageError("runtime lock header drift")

    packages = lock_json.get("packages")
    if type(packages) is not dict or set(packages) != {"", f"node_modules/{PACKAGE_NAME}"}:
        raise RuntimePackageError("runtime lock package set drift")
    root = packages[""]
    if root != {
        "name": RUNTIME_PACKAGE_NAME,
        "version": RUNTIME_PACKAGE_VERSION,
        "dependencies": {PACKAGE_NAME: PACKAGE_VERSION},
    }:
        raise RuntimePackageError("runtime lock root drift")

    selected = packages[f"node_modules/{PACKAGE_NAME}"]
    if type(selected) is not dict:
        raise RuntimePackageError("runtime dependency lock drift")
    if (
        selected.get("version") != PACKAGE_VERSION
        or selected.get("resolved") != PACKAGE_RESOLVED
        or selected.get("integrity") != PACKAGE_INTEGRITY
        or selected.get("license") != "Apache-2.0"
        or selected.get("engines") != {"node": "^20.19.0 || ^22.12.0 || >=23"}
        or selected.get("bin") != {
            "chrome-devtools": "build/src/bin/chrome-devtools.js",
            "chrome-devtools-mcp": "build/src/bin/chrome-devtools-mcp.js",
        }
    ):
        raise RuntimePackageError("runtime dependency lock drift")

    return RuntimePackageIdentity(
        package_name=PACKAGE_NAME,
        package_version=PACKAGE_VERSION,
        resolved=PACKAGE_RESOLVED,
        integrity=PACKAGE_INTEGRITY,
        cli_relative_path=CLI_RELATIVE_PATH,
    )


def build_runtime_install_plan(
    *,
    runtime_root: object,
    cache_root: object,
    node_executable: object,
    node_version: object,
    npm_cli: object,
) -> RuntimeInstallPlan:
    """Return a no-scripts npm-ci plan; executing it remains a host-owner effect."""
    runtime = _absolute(runtime_root, "runtime_root")
    cache = _absolute(cache_root, "cache_root")
    node = _absolute(node_executable, "node_executable")
    npm = _absolute(npm_cli, "npm_cli")
    version = _supported_node(node_version)
    return RuntimeInstallPlan(
        command=node,
        argv=(
            npm,
            "ci",
            "--prefix", runtime,
            "--cache", cache,
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ),
        runtime_root=runtime,
        cache_root=cache,
        node_version=version,
        cli_path=f"{runtime}/{CLI_RELATIVE_PATH}",
        package_version=PACKAGE_VERSION,
    )

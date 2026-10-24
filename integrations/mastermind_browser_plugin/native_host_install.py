"""Pure installation contract for the Browser Link Chrome Native Messaging host.

This module renders exact host-owned files but performs no filesystem write,
Chrome policy change, extension distribution, process launch, grant, or Auth0
operation. Extension ID issuance/distribution remains an external release step.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

HOST_NAME = "com.mastermind.browser_link"
SCHEMA = "mastermind.browser_link.native_host_install_plan.v1"
_EXTENSION_ID = re.compile(r"^[a-p]{32}$")


class BrowserNativeHostInstallError(ValueError):
    """One Browser Link native-host installation plan is invalid."""


def _absolute(value: object, field: str, *, reject_whitespace: bool = False) -> str:
    if type(value) is not str or not value.startswith("/") or value == "/" or "\x00" in value:
        raise BrowserNativeHostInstallError(f"{field} must be an absolute normalized path")
    path = PurePosixPath(value)
    if ".." in path.parts or "." in path.parts or str(path) != value.rstrip("/"):
        raise BrowserNativeHostInstallError(f"{field} must be an absolute normalized path")
    if reject_whitespace and any(ch.isspace() for ch in value):
        raise BrowserNativeHostInstallError(f"{field} cannot contain whitespace")
    return value


@dataclass(frozen=True, slots=True)
class BrowserNativeHostInstallPlan:
    extension_id: str
    python_executable: str
    bridge_path: str
    enrollment_path: str
    owner_socket_path: str
    launcher_path: str
    launcher_source: str
    host_manifest: dict[str, object]
    enrollment: dict[str, object]
    launcher_mode: int = 0o700
    enrollment_mode: int = 0o600
    host_manifest_mode: int = 0o644
    requires_extension_distribution: bool = True

    @property
    def is_installation(self) -> bool:
        return False

    @property
    def requires_auth0(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "extension_id": self.extension_id,
            "python_executable": self.python_executable,
            "bridge_path": self.bridge_path,
            "enrollment_path": self.enrollment_path,
            "owner_socket_path": self.owner_socket_path,
            "launcher_path": self.launcher_path,
            "launcher_mode": self.launcher_mode,
            "enrollment_mode": self.enrollment_mode,
            "host_manifest_mode": self.host_manifest_mode,
            "host_manifest": dict(self.host_manifest),
            "enrollment": dict(self.enrollment),
            "requires_extension_distribution": True,
            "requires_auth0": False,
            "is_installation": False,
            "authority": {
                "install_plan_is_authority": False,
                "may_install_extension": False,
                "may_start_browser_owner": False,
                "may_mint_browser_grant": False,
                "may_link_auth0": False,
            },
        }


def build_native_host_install_plan(
    *,
    extension_id: object,
    python_executable: object,
    bridge_path: object,
    enrollment_path: object,
    owner_socket_path: object,
) -> BrowserNativeHostInstallPlan:
    if type(extension_id) is not str or _EXTENSION_ID.fullmatch(extension_id) is None:
        raise BrowserNativeHostInstallError("extension_id is invalid")

    python = _absolute(
        python_executable, "python_executable", reject_whitespace=True
    )
    bridge = _absolute(bridge_path, "bridge_path")
    enrollment_path_value = _absolute(enrollment_path, "enrollment_path")
    socket_path = _absolute(owner_socket_path, "owner_socket_path")

    enrollment_parent = str(PurePosixPath(enrollment_path_value).parent)
    if enrollment_parent == "/":
        raise BrowserNativeHostInstallError("enrollment_path parent is invalid")
    launcher_path = f"{enrollment_parent}/mastermind-browser-link-host"

    launcher_source = (
        f"#!{python}\n"
        "import os\n"
        "import sys\n"
        f"PYTHON = {python!r}\n"
        f"BRIDGE = {bridge!r}\n"
        f"CONFIG = {enrollment_path_value!r}\n"
        'os.execv(PYTHON, [PYTHON, BRIDGE, "--config", CONFIG, *sys.argv[1:]])\n'
    )

    host_manifest = {
        "name": HOST_NAME,
        "description": "Mastermind Browser Link native host",
        "path": launcher_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    enrollment = {
        "schema": "mastermind.browser_link.enrollment.v1",
        "extension_id": extension_id,
        "socket_path": socket_path,
    }
    return BrowserNativeHostInstallPlan(
        extension_id=extension_id,
        python_executable=python,
        bridge_path=bridge,
        enrollment_path=enrollment_path_value,
        owner_socket_path=socket_path,
        launcher_path=launcher_path,
        launcher_source=launcher_source,
        host_manifest=host_manifest,
        enrollment=enrollment,
    )

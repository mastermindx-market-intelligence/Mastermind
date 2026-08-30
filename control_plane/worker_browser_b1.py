"""Bounded Worker Browser B1 runner for the local Chairman Control Room.

This module is deliberately a resource adapter, not a lifecycle.  A caller
may request exactly one review of the already-running, exact loopback Control
Room origin.  The runner owns a fresh isolated Playwright MCP process group,
collects two fixed viewport screenshots plus bounded structured evidence, and
does not report success until the process group is proven absent.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import http.server
import json
import math
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import struct
import subprocess
import threading
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from control_plane.executive_agent_capabilities import (
    WORKER_BROWSER_MCP_ARGS,
    WORKER_BROWSER_MCP_COMMAND,
)
from control_plane.operator_harness_contract import (
    ObservedCapabilityIdentity,
    ProcessGenerationRef,
    RequestedExecutionProfile,
    SessionEpochRef,
    WorkspaceIdentity,
)


PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp"
PLAYWRIGHT_MCP_VERSION = "0.0.79"
DEFAULT_RUNTIME_ROOT = Path("/Volumes/Mastermind/worker-browser-b1/runtime")
DEFAULT_ARTIFACT_ROOT = Path("/Volumes/Mastermind/worker-browser-b1/artifacts")
RECEIPT_SCHEMA = "mastermind.browser_review_receipt/v1"
RUNTIME_INSTALL_SCHEMA = "mastermind.worker_browser_runtime_install/v1"
RUNTIME_INSTALL_MANIFEST_NAME = "worker-browser-b1-install-manifest.json"
RUNTIME_LAUNCHER_NAME = "worker-browser-b1-launcher"
RUNTIME_NODE_LIBRARY_NAME = "libnode.147.dylib"
RUNTIME_TMP_INSTALL_NAME = "tmp-install"
UNRATIFIED_RUNTIME_MANIFEST_DIGEST = "0" * 64
_RUNTIME_CONTAINER_FD_ENV = "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"
_ANCHORED_NODE_BOOTSTRAP = r'''import hashlib,json,os,stat,sys
F="MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"; N="worker-browser-b1-install-manifest.json"; d=-1; R=-1
P=lambda o:(o.st_dev,o.st_ino,o.st_mode,o.st_nlink,o.st_uid,o.st_gid,o.st_size,o.st_mtime_ns,o.st_ctime_ns)
def A(p,u,z):
 q=os.dup(R); f=-1; L=p.split("/")
 try:
  for C in L[:-1]:
   Q=os.open(C,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=q); os.close(q); q=Q; I=os.fstat(q)
   if not stat.S_ISDIR(I.st_mode) or I.st_uid!=os.geteuid() or stat.S_IMODE(I.st_mode)!=0o500: raise OSError()
  f=os.open(L[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=q)
  a=os.fstat(f); g=hashlib.sha256(); n=0
  while True:
   h=os.read(f,1048576)
   if not h: break
   n+=len(h); g.update(h)
  j=os.fstat(f); k=os.stat(L[-1],dir_fd=q,follow_symlinks=False)
 finally:
  if f>=0: os.close(f)
  os.close(q)
 if set(u)!={"gid","mode","path","sha256","uid"} or u["path"]!=z or not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid!=os.geteuid() or stat.S_IMODE(a.st_mode)!=0o500 or n!=a.st_size or P(a)!=P(j) or P(a)!=P(k) or u!={"gid":a.st_gid,"mode":0o500,"path":z,"sha256":g.hexdigest(),"uid":a.st_uid}: raise ValueError()
try:
 d=int(os.environ[F]); i=os.fstat(d); R=os.open("runtime",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=d); I=os.fstat(R); x=os.open(N,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=R)
 try:
  a=os.fstat(x); b=b""
  while len(b)<=4194304:
   h=os.read(x,65536)
   if not h: break
   b+=h
  j=os.fstat(x)
 finally: os.close(x)
 v=json.loads(b.decode("utf-8")); w=v["runtime_container"]
 if d<3 or len(b)>4194304 or not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid!=os.geteuid() or stat.S_IMODE(a.st_mode)!=0o400 or (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)!=(j.st_dev,j.st_ino,j.st_size,j.st_mtime_ns) or hashlib.sha256(b).hexdigest()!=os.environ["MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256"] or set(w)!={"device","gid","inode","mode","uid"} or any(type(w[k]) is not int for k in w) or w!={"device":i.st_dev,"gid":i.st_gid,"inode":i.st_ino,"mode":stat.S_IMODE(i.st_mode),"uid":i.st_uid} or i.st_uid!=os.geteuid() or stat.S_IMODE(i.st_mode)!=0o500: raise ValueError()
 r=v["runtime_root"]
 if not stat.S_ISDIR(I.st_mode) or I.st_uid!=os.geteuid() or stat.S_IMODE(I.st_mode)!=0o500: raise ValueError()
 A("bin/node",v["node"]["executable"],os.path.join(r,"bin","node")); A("node_modules/@playwright/mcp/cli.js",v["mcp"]["executable"],os.path.join(r,"node_modules","@playwright","mcp","cli.js"))
 if P(I)!=P(os.fstat(R)) or P(I)!=P(os.stat("runtime",dir_fd=d,follow_symlinks=False)): raise ValueError()
 os.close(R); R=-1
 e={k:os.environ[k] for k in ("HOME","LANG","LC_ALL","NO_COLOR","PATH","PLAYWRIGHT_BROWSERS_PATH","TMPDIR")}
 if e["PLAYWRIGHT_BROWSERS_PATH"]!="runtime/browsers": raise ValueError()
 os.fchdir(d); os.set_inheritable(d,False)
 os.execve("runtime/bin/node",["runtime/bin/node","runtime/node_modules/@playwright/mcp/cli.js",*sys.argv[1:]],e)
except (KeyError,OSError,TypeError,UnicodeError,ValueError):
 if R>=0:
  try: os.close(R)
  except OSError: pass
 raise SystemExit("anchored runtime launch refused")
'''

BROWSER_RESOURCE_ENV_KEYS = frozenset(
    {
        "MASTERMIND_BROWSER_ARTIFACT_DIR",
        "MASTERMIND_BROWSER_FIXTURE_A_URL",
        "MASTERMIND_BROWSER_FIXTURE_B_URL",
        "MASTERMIND_BROWSER_FIXTURE_NONCE",
        "MASTERMIND_BROWSER_ORIGIN",
        "MASTERMIND_BROWSER_PROXY_URL",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256",
        "MASTERMIND_BROWSER_RUNTIME_ROOT",
        "MASTERMIND_BROWSER_WORKSPACE_PATH",
        "PLAYWRIGHT_BROWSERS_PATH",
    }
)

ALLOWED_TOOLS = frozenset(
    {
        "browser_click",
        "browser_close",
        "browser_console_messages",
        "browser_fill_form",
        "browser_hover",
        "browser_navigate",
        "browser_network_requests",
        "browser_resize",
        "browser_snapshot",
        "browser_tabs",
        "browser_take_screenshot",
        "browser_wait_for",
    }
)
_BOUNDED_INTERACTION_TOOLS = frozenset(
    {"browser_click", "browser_fill_form", "browser_hover"}
)
_REQUIRED_MCP_SUCCESS_MINIMUMS = {
    "browser_console_messages": 1,
    "browser_navigate": 3,
    "browser_network_requests": 1,
    "browser_resize": 3,
    "browser_snapshot": 1,
}

_DESKTOP = {"width": 1440, "height": 900}
_MOBILE = {"width": 390, "height": 844}
_MAX_PROTOCOL_LINE_BYTES = 4 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
MAX_SCREENSHOTS = 4
MAX_TEXT_EVIDENCE_BYTES = 64 * 1024
MAX_CONSOLE_ROWS = 128
MAX_NETWORK_ROWS = 256
MAX_PROXY_RESPONSE_BYTES = MAX_TEXT_EVIDENCE_BYTES + MAX_SCREENSHOT_BYTES
MAX_RUNTIME_INSTALL_MANIFEST_BYTES = 4 * 1024 * 1024
_CLEANUP_GRACE_SECONDS = 3.0
_CLEANUP_PROOF_SECONDS = 3.0

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_EGRESS_FALSIFIERS = frozenset(
    {
        "external_fetch",
        "external_http",
        "external_https",
        "external_redirect",
        "external_subresource",
        "external_websocket",
        "file_url",
        "proxy_override",
    }
)
_REQUIRED_CLEANUP_KEYS = frozenset(
    {
        "browser_absent",
        "devserver_absent",
        "mcp_absent",
        "proxy_absent",
        "uid_sweep_digest",
        "uid_sweep_passed",
    }
)
_EGRESS_PROBE_HOSTS = {
    "external-http.invalid": "external_http",
    "external-https.invalid": "external_https",
    "redirect.invalid": "external_redirect",
    "subresource.invalid": "external_subresource",
    "fetch.invalid": "external_fetch",
    "websocket.invalid": "external_websocket",
}


class BrowserReviewError(RuntimeError):
    """A typed, sanitized B1 failure."""

    def __init__(self, state: str, detail: str):
        super().__init__(detail)
        self.state = state
        self.detail = detail


@dataclass(frozen=True)
class BrowserRunConfig:
    origin: str
    repo_root: Path
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    command_override: tuple[str, ...] | None = None


@dataclass(frozen=True)
class BrowserAttemptContext:
    """Attempt/generation binding for one browser resource receipt."""

    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    workspace: WorkspaceIdentity
    artifact_dir: Path
    devserver_manifest_digest: str
    capability_manifest_digest: str
    browser_profile_id: str
    browser_profile_digest: str
    playwright_mcp_identity: str
    playwright_mcp_version: str
    playwright_tool_schema_digest: str
    runtime_manifest_digest: str
    browser_revision: str
    browser_executable: str
    browser_executable_sha256: str


@dataclass(frozen=True)
class RuntimeInstallAttestation:
    """Closed, installer-produced identity for the executable browser runtime."""

    runtime_root: Path
    runtime_container_device: int
    runtime_container_inode: int
    runtime_container_uid: int
    runtime_container_gid: int
    runtime_container_mode: int
    manifest_path: Path
    manifest_digest: str
    launcher_path: Path
    launcher_sha256: str
    node_path: Path
    node_sha256: str
    node_library_path: Path
    node_library_sha256: str
    mcp_executable: Path
    mcp_executable_sha256: str
    package_lock_sha256: str
    closure_tree_digest: str
    closure_entry_count: int
    browser_executable: Path
    browser_executable_sha256: str
    browser_revision: str


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class BrowserReviewReceipt:
    """Closed immutable browser artifact carried by the normal Attempt result."""

    schema_version: str
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    workspace: WorkspaceIdentity
    devserver: Mapping[str, Any]
    capability: Mapping[str, Any]
    playwright_mcp: Mapping[str, Any]
    browser: Mapping[str, Any]
    viewports: tuple[Mapping[str, Any], ...]
    artifacts: Mapping[str, Any]
    egress_falsifiers: Mapping[str, str]
    external_egress_observed: bool
    visual_judgment: Mapping[str, Any]
    cleanup: Mapping[str, Any]
    tracked_workspace_changes_after_review: bool

    def __post_init__(self) -> None:
        for field in (
            "devserver",
            "capability",
            "playwright_mcp",
            "browser",
            "viewports",
            "artifacts",
            "egress_falsifiers",
            "visual_judgment",
            "cleanup",
        ):
            object.__setattr__(self, field, _freeze_json(getattr(self, field)))

    def to_wire(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "session_epoch_id": self.session_epoch_id,
            "process_generation_id": self.process_generation_id,
            "workspace": asdict(self.workspace),
            "devserver": _thaw_json(self.devserver),
            "capability": _thaw_json(self.capability),
            "playwright_mcp": _thaw_json(self.playwright_mcp),
            "browser": _thaw_json(self.browser),
            "viewports": _thaw_json(self.viewports),
            "artifacts": _thaw_json(self.artifacts),
            "egress_falsifiers": _thaw_json(self.egress_falsifiers),
            "external_egress_observed": self.external_egress_observed,
            "visual_judgment": _thaw_json(self.visual_judgment),
            "cleanup": _thaw_json(self.cleanup),
            "tracked_workspace_changes_after_review": (
                self.tracked_workspace_changes_after_review
            ),
        }
        # JSON round-trip prevents mutable nested aliases from escaping.
        return json.loads(_canonical_bytes(value).decode("ascii"))

    @property
    def digest(self) -> str:
        wire = self.to_wire()
        # A frozen dataclass does not freeze or validate nested mappings.  The
        # canonical digest boundary therefore re-parses the closed wire shape
        # before treating a typed receipt as authoritative.
        browser_review_receipt(wire)
        return _canonical_digest(wire)


_RECEIPT_TOP_LEVEL_KEYS = frozenset(
    {
        "artifacts",
        "attempt_id",
        "browser",
        "capability",
        "cleanup",
        "devserver",
        "egress_falsifiers",
        "external_egress_observed",
        "playwright_mcp",
        "process_generation_id",
        "schema_version",
        "session_epoch_id",
        "tracked_workspace_changes_after_review",
        "viewports",
        "visual_judgment",
        "workspace",
    }
)


def canonical_browser_review_receipt_digest(receipt: BrowserReviewReceipt) -> str:
    if not isinstance(receipt, BrowserReviewReceipt):
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "browser receipt is not typed")
    return receipt.digest


def _closed_mcp_guard_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "bytes",
        "relative_path",
        "schema_version",
        "sha256",
    }:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "MCP guard artifact summary is not closed"
        )
    if (
        value.get("relative_path") != _MCP_GUARD_EVIDENCE_FILE
        or value.get("schema_version") != _MCP_GUARD_EVIDENCE_SCHEMA
        or type(value.get("bytes")) is not int
        or not 0 < value["bytes"] <= MAX_TEXT_EVIDENCE_BYTES
    ):
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "MCP guard artifact summary is invalid"
        )
    _require_sha256(value.get("sha256"), field="artifacts.mcp_guard.sha256")
    return dict(value)


def browser_review_receipt(value: Any) -> BrowserReviewReceipt:
    """Parse one closed receipt; caller-authored digest fields are forbidden."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_TOP_LEVEL_KEYS:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "browser receipt fields are not closed")
    if value.get("schema_version") != RECEIPT_SCHEMA:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "browser receipt schema is unsupported")
    identities = (
        value.get("attempt_id"),
        value.get("session_epoch_id"),
        value.get("process_generation_id"),
    )
    if any(
        not isinstance(item, str)
        or not item
        or item != item.strip()
        or len(item.encode("utf-8")) > 256
        for item in identities
    ):
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "browser receipt identity is invalid")
    workspace = value.get("workspace")
    if not isinstance(workspace, Mapping) or set(workspace) != {
        "base_sha", "device", "gid", "inode", "uid", "workspace_path"
    }:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "workspace identity is not closed")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(workspace.get("base_sha") or "")) is None
        or not isinstance(workspace.get("workspace_path"), str)
        or not workspace.get("workspace_path")
        or any(type(workspace.get(key)) is not int for key in ("device", "gid", "inode", "uid"))
    ):
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "workspace identity is invalid")
    expected_nested = {
        "devserver": {"local_origin", "manifest_digest"},
        "capability": {"manifest_digest", "profile_digest", "profile_id"},
        "playwright_mcp": {"identity", "tool_schema_digest", "version"},
        "browser": {
            "executable",
            "executable_sha256",
            "revision",
            "runtime_manifest_digest",
        },
        "artifacts": {"console", "mcp_guard", "network", "screenshots"},
    }
    for field, keys in expected_nested.items():
        row = value.get(field)
        if not isinstance(row, Mapping) or set(row) != keys:
            raise BrowserReviewError("BROWSER_RECEIPT_INVALID", f"{field} receipt is not closed")
    for field in (
        "devserver.manifest_digest",
        "capability.manifest_digest",
        "capability.profile_digest",
        "playwright_mcp.tool_schema_digest",
        "browser.executable_sha256",
        "browser.runtime_manifest_digest",
    ):
        root, key = field.split(".")
        _require_sha256(value[root][key], field=field)
    guard_summary = _closed_mcp_guard_summary(
        value["artifacts"].get("mcp_guard")
    )
    try:
        _validate_origin(str(value["devserver"]["local_origin"]))
    except ValueError as exc:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "devserver origin is invalid") from exc
    if value["browser"].get("revision") != "1237":
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "browser revision is invalid")
    viewports = value.get("viewports")
    if not isinstance(viewports, list) or not 2 <= len(viewports) <= MAX_SCREENSHOTS:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "viewport evidence is incomplete")
    screenshots = value["artifacts"].get("screenshots")
    if not isinstance(screenshots, list) or len(screenshots) != len(viewports):
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "screenshot evidence is incomplete")
    normalized_viewports: list[dict[str, int]] = []
    for viewport in viewports:
        if (
            not isinstance(viewport, Mapping)
            or set(viewport) != {"height", "width"}
            or any(
                type(viewport.get(key)) is not int or viewport[key] <= 0
                for key in ("height", "width")
            )
        ):
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", "viewport evidence is not closed"
            )
        normalized_viewports.append(dict(viewport))
    total_screenshot_bytes = 0
    for index, screenshot in enumerate(screenshots):
        if not isinstance(screenshot, Mapping) or set(screenshot) != {
            "bytes", "relative_path", "sha256", "viewport"
        }:
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", "screenshot evidence is not closed"
            )
        relative_path = screenshot.get("relative_path")
        size = screenshot.get("bytes")
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or Path(relative_path).name != relative_path
            or type(size) is not int
            or not 0 < size <= MAX_SCREENSHOT_BYTES
            or screenshot.get("viewport") != normalized_viewports[index]
        ):
            raise BrowserReviewError(
                "BROWSER_ARTIFACT_OVERSIZE", "screenshot evidence is invalid"
            )
        _require_sha256(screenshot.get("sha256"), field="screenshot.sha256")
        total_screenshot_bytes += size
    if total_screenshot_bytes > MAX_SCREENSHOTS * MAX_SCREENSHOT_BYTES:
        raise BrowserReviewError(
            "BROWSER_ARTIFACT_OVERSIZE", "screenshot evidence exceeds the aggregate bound"
        )
    for field, maximum_rows in (
        ("console", MAX_CONSOLE_ROWS),
        ("network", MAX_NETWORK_ROWS),
    ):
        summary = value["artifacts"].get(field)
        if not isinstance(summary, Mapping) or set(summary) != {
            "bytes", "observed", "rows", "sha256"
        }:
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", f"{field} evidence is not closed"
            )
        if (
            summary.get("observed") is not True
            or type(summary.get("rows")) is not int
            or not 1 <= summary["rows"] <= maximum_rows
            or type(summary.get("bytes")) is not int
            or not 0 < summary["bytes"] <= MAX_TEXT_EVIDENCE_BYTES
        ):
            raise BrowserReviewError(
                "BROWSER_ARTIFACT_OVERSIZE", f"{field} evidence exceeds the reviewed bound"
            )
        _require_sha256(summary.get("sha256"), field=f"{field}.sha256")
    for root, key in (
        ("capability", "profile_id"),
        ("playwright_mcp", "identity"),
        ("playwright_mcp", "version"),
        ("browser", "executable"),
    ):
        token = value[root].get(key)
        if (
            not isinstance(token, str)
            or not token
            or token != token.strip()
            or len(token.encode("utf-8")) > 4096
        ):
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", f"{root}.{key} is invalid"
            )
    if not isinstance(value.get("egress_falsifiers"), Mapping) or set(value["egress_falsifiers"]) != _REQUIRED_EGRESS_FALSIFIERS:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "egress evidence is not closed")
    if any(item != "REFUSED" for item in value["egress_falsifiers"].values()):
        raise BrowserReviewError("BROWSER_NETWORK_ESCAPE", "egress falsifier did not refuse")
    if value.get("external_egress_observed") is not False:
        raise BrowserReviewError("BROWSER_NETWORK_ESCAPE", "external egress was observed")
    visual = value.get("visual_judgment")
    if not isinstance(visual, Mapping) or set(visual) != {
        "defective_variant", "fixture_nonce", "image_sha256", "reason", "source"
    }:
        raise BrowserReviewError("BROWSER_VISUAL_CAPABILITY_UNPROVEN", "visual judgment is not closed")
    images = visual.get("image_sha256")
    if (
        visual.get("source") != "model_image_content"
        or visual.get("defective_variant") not in {"A", "B"}
        or not isinstance(visual.get("fixture_nonce"), str)
        or not visual.get("fixture_nonce")
        or not isinstance(visual.get("reason"), str)
        or not visual.get("reason")
        or not isinstance(images, list)
        or len(images) != 2
        or len(set(images)) != 2
    ):
        raise BrowserReviewError("BROWSER_VISUAL_CAPABILITY_UNPROVEN", "model pixel judgment is incomplete")
    for image in images:
        _require_sha256(image, field="visual_judgment.image_sha256")
    cleanup = value.get("cleanup")
    if not isinstance(cleanup, Mapping) or set(cleanup) != _REQUIRED_CLEANUP_KEYS:
        raise BrowserReviewError("BROWSER_ORPHAN_PROCESS_UNCERTAIN", "cleanup receipt is not closed")
    if any(
        cleanup.get(key) is not True
        for key in _REQUIRED_CLEANUP_KEYS - {"uid_sweep_digest"}
    ):
        raise BrowserReviewError(
            "BROWSER_ORPHAN_PROCESS_UNCERTAIN", "cleanup receipt does not prove absence"
        )
    _require_sha256(cleanup.get("uid_sweep_digest"), field="cleanup.uid_sweep_digest")
    if value.get("tracked_workspace_changes_after_review") is not False:
        raise BrowserReviewError("BROWSER_WORKSPACE_MUTATION", "workspace mutation is not refused")
    normalized_artifacts = json.loads(
        _canonical_bytes(value["artifacts"]).decode("ascii")
    )
    normalized_artifacts["mcp_guard"] = guard_summary
    return BrowserReviewReceipt(
        schema_version=RECEIPT_SCHEMA,
        attempt_id=identities[0],
        session_epoch_id=identities[1],
        process_generation_id=identities[2],
        workspace=WorkspaceIdentity(**dict(workspace)),
        devserver=dict(value["devserver"]),
        capability=dict(value["capability"]),
        playwright_mcp=dict(value["playwright_mcp"]),
        browser=dict(value["browser"]),
        viewports=tuple(normalized_viewports),
        artifacts=normalized_artifacts,
        egress_falsifiers=dict(value["egress_falsifiers"]),
        external_egress_observed=False,
        visual_judgment=dict(visual),
        cleanup=dict(cleanup),
        tracked_workspace_changes_after_review=False,
    )


@dataclass(frozen=True)
class DevserverManifest:
    schema_version: str
    resource_id: str
    cwd: Path
    argv: tuple[str, ...]
    host: str
    readiness_path: str
    readiness_timeout_seconds: int
    shutdown_grace_seconds: int
    allowed_generated_paths: tuple[str, ...]
    digest: str

    def argv_for_port(self, port: int) -> tuple[str, ...]:
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "port is outside the reviewed range")
        return tuple(str(port) if value == "{port}" else value for value in self.argv)


@dataclass(frozen=True)
class _AttemptVisualFixture:
    """Opaque, pixel-only discriminating fixture kept inside one Attempt."""

    nonce: str
    path_a: str
    path_b: str
    defective_variant: str
    routes: Mapping[str, tuple[int, Mapping[str, str], bytes]]

    @classmethod
    def create(cls, origin: str) -> "_AttemptVisualFixture":
        _validate_origin(origin)
        nonce = secrets.token_hex(16)
        path_a = f"/__mastermind_browser_visual_fixture__/{secrets.token_hex(16)}"
        path_b = f"/__mastermind_browser_visual_fixture__/{secrets.token_hex(16)}"
        while path_b == path_a:
            path_b = f"/__mastermind_browser_visual_fixture__/{secrets.token_hex(16)}"
        defective = "A" if secrets.randbits(1) == 0 else "B"

        def page(*, clipped: bool) -> bytes:
            # Visible text and accessibility structure are byte-identical; only
            # the CSS pixels differ.  Probe URLs are inert evidence fixtures
            # whose attempted loads must all be observed as proxy refusals.
            defect_css = (
                ".critical{transform:translateX(780px)}"
                if clipped
                else ".critical{transform:translateX(0)}"
            )
            return (
                "<!doctype html><html><head><meta charset=utf-8>"
                "<title>Browser visual capability fixture</title><style>"
                "html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#111827;color:#f9fafb;font-family:system-ui}"
                ".stage{box-sizing:border-box;width:900px;height:600px;padding:72px;overflow:hidden}"
                ".critical{box-sizing:border-box;width:520px;padding:36px;border:4px solid #60a5fa;background:#1f2937}"
                + defect_css
                + "</style></head><body><main class=stage aria-label='Visual review fixture'>"
                "<section class=critical aria-label='Critical portfolio card'>"
                "<h1>Portfolio risk summary</h1><p>Exposure is within the reviewed limit.</p>"
                "</section>"
                f"<iframe hidden src='http://external-http.invalid/{nonce}'></iframe>"
                f"<iframe hidden src='https://external-https.invalid/{nonce}'></iframe>"
                f"<img hidden alt='' src='{origin}/__mastermind_browser_probe__/redirect/{nonce}'>"
                f"<img hidden alt='' src='http://subresource.invalid/{nonce}.png'>"
                "<script>"
                f"fetch('http://fetch.invalid/{nonce}').catch(()=>{{}});"
                f"try{{new WebSocket('ws://websocket.invalid/{nonce}')}}catch(_e){{}}"
                "</script></main></body></html>"
            ).encode("utf-8")

        common_headers = {"Content-Type": "text/html; charset=utf-8"}
        routes: dict[str, tuple[int, Mapping[str, str], bytes]] = {
            path_a: (200, common_headers, page(clipped=defective == "A")),
            path_b: (200, common_headers, page(clipped=defective == "B")),
            f"/__mastermind_browser_probe__/redirect/{nonce}": (
                302,
                {"Location": f"http://redirect.invalid/{nonce}"},
                b"",
            ),
        }
        return cls(
            nonce=nonce,
            path_a=path_a,
            path_b=path_b,
            defective_variant=defective,
            routes=routes,
        )

    def model_urls(self, origin: str) -> tuple[str, str]:
        return f"{origin}{self.path_a}", f"{origin}{self.path_b}"


def validate_request(data: dict[str, Any]) -> None:
    """Accept the one closed request shape: an empty JSON object."""
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    if data:
        key = next(iter(data))
        raise ValueError(f"unknown key: {key!r}")


def _validate_origin(origin: str) -> None:
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("origin must be an exact loopback origin") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("",)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("origin must be an exact loopback origin")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha256(value: Any, *, field: str) -> str:
    token = str(value or "").strip().lower()
    if _SHA256_RE.fullmatch(token) is None:
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", f"{field} must be a SHA-256 digest")
    return token


def load_devserver_manifest(path: Path, workspace: Path) -> DevserverManifest:
    """Load the one closed, worktree-bound Control Room manifest."""

    manifest_path = Path(path)
    workspace_path = Path(workspace)
    try:
        workspace_root = workspace_path.resolve(strict=True)
        if not workspace_root.is_dir() or workspace_path.is_symlink():
            raise OSError("workspace is not a real directory")
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise OSError("manifest is not a regular file")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise BrowserReviewError(
            "DEVSERVER_MANIFEST_INVALID", "devserver manifest is not readable closed JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver manifest must be an object")
    expected_keys = {
        "allowed_generated_paths",
        "argv",
        "cwd",
        "host",
        "readiness_path",
        "readiness_timeout_seconds",
        "resource_id",
        "schema_version",
        "shutdown_grace_seconds",
    }
    if set(raw) != expected_keys:
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver manifest fields are not closed")
    if raw.get("schema_version") != "mastermind.devserver_resource/v1":
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver manifest schema is unsupported")
    if raw.get("resource_id") != "chairman-control-room-local":
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver resource identity is not reviewed")
    if raw.get("cwd") != "." or raw.get("host") != "127.0.0.1":
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver cwd and host must be exact")
    if raw.get("readiness_path") != "/":
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver readiness path must be exact")
    if raw.get("readiness_timeout_seconds") != 300 or raw.get("shutdown_grace_seconds") != 5:
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver timing is not the reviewed bound")
    if raw.get("allowed_generated_paths") != []:
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "B1 Control Room declares no generated source paths")
    argv = raw.get("argv")
    expected_argv = [
        "/usr/bin/python3",
        "scripts/chairman_control_room.py",
        "--port",
        "{port}",
        "--repo-root",
        ".",
        "--compose-timeout",
        "240",
    ]
    if argv != expected_argv:
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "devserver argv is not the reviewed direct command")
    script = workspace_root / "scripts" / "chairman_control_room.py"
    try:
        resolved_script = script.resolve(strict=True)
    except OSError as exc:
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "reviewed devserver script is missing") from exc
    if script.is_symlink() or resolved_script.parent != workspace_root / "scripts":
        raise BrowserReviewError("DEVSERVER_MANIFEST_INVALID", "reviewed devserver script escapes the workspace")
    return DevserverManifest(
        schema_version=str(raw["schema_version"]),
        resource_id=str(raw["resource_id"]),
        cwd=workspace_root,
        argv=tuple(argv),
        host="127.0.0.1",
        readiness_path="/",
        readiness_timeout_seconds=300,
        shutdown_grace_seconds=5,
        allowed_generated_paths=(),
        digest=_canonical_digest(raw),
    )


class LoopbackEnforcingProxy:
    """Attempt-local HTTP proxy that can reach one exact loopback origin only."""

    def __init__(
        self,
        target_origin: str,
        *,
        fixture_routes: Mapping[
            str, tuple[int, Mapping[str, str], bytes]
        ] | None = None,
    ):
        _validate_origin(target_origin)
        parsed = urlsplit(target_origin)
        assert parsed.port is not None
        self.target_origin = target_origin
        self._target_port = parsed.port
        routes: dict[str, tuple[int, dict[str, str], bytes]] = {}
        for path, route in dict(fixture_routes or {}).items():
            if (
                not isinstance(path, str)
                or not path.startswith("/")
                or "?" in path
                or "#" in path
                or not isinstance(route, tuple)
                or len(route) != 3
            ):
                raise BrowserReviewError(
                    "BROWSER_RECEIPT_INVALID", "attempt fixture route is not closed"
                )
            status_code, headers, body = route
            if (
                type(status_code) is not int
                or status_code not in {200, 302}
                or not isinstance(headers, Mapping)
                or any(
                    not isinstance(name, str)
                    or not isinstance(value, str)
                    or "\r" in name + value
                    or "\n" in name + value
                    for name, value in headers.items()
                )
                or not isinstance(body, bytes)
                or len(body) > MAX_TEXT_EVIDENCE_BYTES
            ):
                raise BrowserReviewError(
                    "BROWSER_RECEIPT_INVALID", "attempt fixture response is not closed"
                )
            routes[path] = (
                status_code,
                {str(name): str(value) for name, value in headers.items()},
                body,
            )
        self._fixture_routes = routes
        self._lock = threading.Lock()
        self._allowed_requests = 0
        self._refused = {key: 0 for key in sorted(_REQUIRED_EGRESS_FALSIFIERS)}
        self._refused["write_method"] = 0
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def proxy_url(self) -> str:
        if self._server is None:
            raise BrowserReviewError("BROWSER_PROXY_NOT_STARTED", "network proxy is not running")
        return f"http://127.0.0.1:{self._server.server_port}"

    def _count_refusal(self, reason: str) -> None:
        with self._lock:
            self._refused[reason] += 1

    def _handler_type(self) -> type[http.server.BaseHTTPRequestHandler]:
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _refuse(self, reason: str) -> None:
                owner._count_refusal(reason)
                self.send_response(403, "Forbidden")
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            @staticmethod
            def _external_reason(hostname: str | None) -> str:
                return _EGRESS_PROBE_HOSTS.get(
                    str(hostname or "").lower(), "external_http"
                )

            def _dispatch(self) -> None:
                if self.command not in {"GET", "HEAD", "OPTIONS"}:
                    return self._refuse("write_method")
                connection = str(self.headers.get("Connection") or "").lower()
                upgrade = str(self.headers.get("Upgrade") or "").lower()
                if "upgrade" in connection or upgrade:
                    return self._refuse("external_websocket")
                parsed = urlsplit(self.path)
                if parsed.scheme == "file":
                    return self._refuse("file_url")
                try:
                    port = parsed.port
                except ValueError:
                    return self._refuse("external_http")
                if (
                    parsed.scheme != "http"
                    or parsed.hostname != "127.0.0.1"
                    or port != owner._target_port
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.fragment
                ):
                    return self._refuse(self._external_reason(parsed.hostname))
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                fixture = owner._fixture_routes.get(path)
                if fixture is not None:
                    status_code, headers, body = fixture
                    with owner._lock:
                        owner._allowed_requests += 1
                    self.send_response(status_code)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                    self.close_connection = True
                    return
                forwarded_headers = {
                    str(name): str(value)
                    for name, value in self.headers.items()
                    if str(name).lower()
                    not in {
                        "connection",
                        "content-length",
                        "host",
                        "proxy-connection",
                        "transfer-encoding",
                        "upgrade",
                    }
                }
                forwarded_headers["Host"] = f"127.0.0.1:{owner._target_port}"
                upstream = http.client.HTTPConnection(
                    "127.0.0.1", owner._target_port, timeout=10
                )
                try:
                    upstream.request(self.command, path, headers=forwarded_headers)
                    response = upstream.getresponse()
                    body = response.read(MAX_PROXY_RESPONSE_BYTES + 1)
                except (OSError, http.client.HTTPException):
                    self.send_response(502, "Bad Gateway")
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    return
                finally:
                    upstream.close()
                if len(body) > MAX_PROXY_RESPONSE_BYTES:
                    self.send_response(502, "Bad Gateway")
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    return
                with owner._lock:
                    owner._allowed_requests += 1
                self.send_response(response.status, response.reason)
                for name, value in response.getheaders():
                    if name.lower() not in {
                        "connection",
                        "content-length",
                        "keep-alive",
                        "proxy-authenticate",
                        "proxy-authorization",
                        "te",
                        "trailer",
                        "transfer-encoding",
                        "upgrade",
                    }:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                self.close_connection = True

            do_GET = _dispatch
            do_HEAD = _dispatch
            do_OPTIONS = _dispatch
            do_POST = _dispatch
            do_PUT = _dispatch
            do_PATCH = _dispatch
            do_DELETE = _dispatch

            def do_CONNECT(self) -> None:  # noqa: N802 - stdlib callback
                host = self.path.rsplit(":", 1)[0].strip("[]").lower()
                reason = self._external_reason(host)
                self._refuse(
                    "external_https" if reason == "external_http" else reason
                )

        return Handler

    def start(self) -> None:
        if self._server is not None:
            raise BrowserReviewError("BROWSER_PROXY_ALREADY_STARTED", "network proxy already owns a listener")
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), self._handler_type()
        )
        # server_close() must wait for request handlers; daemon handler threads
        # would make `proxy_absent` impossible to prove inside the broker PID.
        self._server.daemon_threads = False
        self._server.block_on_close = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="worker-browser-b1-proxy",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(5)
            if thread.is_alive():
                raise BrowserReviewError("BROWSER_ORPHAN_PROCESS_UNCERTAIN", "network proxy thread survived stop")
        self._server = None
        self._thread = None

    def receipt(self) -> dict[str, Any]:
        with self._lock:
            return {
                "allowed_requests": self._allowed_requests,
                "external_egress_observed": False,
                "refused": dict(self._refused),
            }


def build_mcp_argv(
    config: BrowserRunConfig,
    output_dir: Path,
    *,
    proxy_url: str | None = None,
) -> list[str]:
    """Build the immutable official-MCP launch envelope."""
    if proxy_url is not None:
        _validate_origin(proxy_url)
    command = list(config.command_override or (
        os.fspath(config.runtime_root / "node_modules" / ".bin" / "playwright-mcp"),
    ))
    values = command + [
        "--isolated",
        "--headless",
        "--browser",
        "chromium",
        "--sandbox",
        "--block-service-workers",
        "--image-responses",
        "allow",
        "--allowed-origins",
        config.origin,
        "--output-dir",
        os.fspath(output_dir),
    ]
    if proxy_url is not None:
        values.extend(("--proxy-server", proxy_url, "--proxy-bypass", "<-loopback>"))
    return values


def _write_private_bytes_once_at(
    directory_fd: int,
    name: str,
    payload: bytes,
) -> os.stat_result:
    """Create one private artifact through one already-bound directory."""

    if not isinstance(payload, bytes) or not payload:
        raise BrowserReviewError(
            "BROWSER_ARTIFACT_OVERSIZE", "attempt artifact payload is empty"
        )
    if (
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or PurePosixPath(name).parts != (name,)
    ):
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "attempt artifact name is not direct"
        )
    directory = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != os.geteuid()
        or stat.S_IMODE(directory.st_mode) != 0o700
    ):
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "attempt artifact directory is not exact"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short artifact write")
            view = view[written:]
        os.fsync(descriptor)
        created = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(created.st_mode)
            or created.st_uid != os.geteuid()
            or created.st_nlink != 1
            or stat.S_IMODE(created.st_mode) != 0o600
            or created.st_size != len(payload)
            or (
                created.st_dev,
                created.st_ino,
                created.st_mode,
                created.st_nlink,
                created.st_uid,
                created.st_gid,
                created.st_size,
            )
            != (
                named.st_dev,
                named.st_ino,
                named.st_mode,
                named.st_nlink,
                named.st_uid,
                named.st_gid,
                named.st_size,
            )
        ):
            raise OSError("created artifact identity is not exact")
        os.fsync(directory_fd)
        return created
    except FileExistsError as exc:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "attempt artifact is immutable and already exists"
        ) from exc
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "attempt artifact write did not complete"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_private_bytes_once(path: Path, payload: bytes) -> None:
    """Create one private attempt artifact through a bound parent descriptor."""

    candidate = Path(path)
    parent_fd = -1
    try:
        if (
            not candidate.is_absolute()
            or not candidate.name
            or candidate.parent / candidate.name != candidate
            or candidate.parent != candidate.parent.resolve(strict=True)
        ):
            raise OSError("artifact path is not absolute and direct")
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_fd = os.open(candidate.parent, directory_flags)
        before = os.fstat(parent_fd)
        named_before = candidate.parent.lstat()
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_gid,
        )
        if (
            identity
            != (
                named_before.st_dev,
                named_before.st_ino,
                named_before.st_mode,
                named_before.st_uid,
                named_before.st_gid,
            )
            or not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o700
        ):
            raise OSError("artifact parent identity is not exact")
        _write_private_bytes_once_at(parent_fd, candidate.name, payload)
        after = os.fstat(parent_fd)
        named_after = candidate.parent.lstat()
        if (
            identity
            != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_gid,
            )
            or identity
            != (
                named_after.st_dev,
                named_after.st_ino,
                named_after.st_mode,
                named_after.st_uid,
                named_after.st_gid,
            )
            or candidate.parent != candidate.parent.resolve(strict=True)
        ):
            raise OSError("artifact parent changed during write")
    except BrowserReviewError:
        raise
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "attempt artifact write did not complete"
        ) from exc
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


class BrowserMcpToolGuard:
    """Call-time authority guard in front of the pinned official MCP server."""

    _FIXTURE_PREFIX = "/__mastermind_browser_visual_fixture__"
    _VISUAL_VIEWPORT = {"width": 900, "height": 600}
    _SCREENSHOT_BINDINGS = {
        "desktop.png": ("product", _DESKTOP),
        "mobile.png": ("product", _MOBILE),
        "visual-a.png": ("fixture-a", _VISUAL_VIEWPORT),
        "visual-b.png": ("fixture-b", _VISUAL_VIEWPORT),
    }
    _SCREENSHOT_LINK_RE = re.compile(
        r"^- \[Screenshot of viewport\]"
        r"\((\./page-[0-9]{4}-[0-9]{2}-[0-9]{2}T"
        r"[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{3}Z\.png)\)$",
        re.MULTILINE,
    )
    def __init__(
        self,
        *,
        origin: str,
        artifact_dir: Path,
        fixture_urls: Mapping[str, str],
    ):
        _validate_origin(origin)
        if not isinstance(fixture_urls, Mapping) or set(fixture_urls) != {"A", "B"}:
            raise BrowserReviewError(
                "BROWSER_MCP_TOOL_REFUSED", "visual fixture URL set is not closed"
            )
        page_classes: dict[str, str] = {}
        for variant in ("A", "B"):
            url = fixture_urls[variant]
            if (
                not isinstance(url, str)
                or not url.startswith(f"{origin}{self._FIXTURE_PREFIX}/")
                or re.fullmatch(
                    rf"{re.escape(origin + self._FIXTURE_PREFIX)}/[0-9a-f]{{32}}",
                    url,
                )
                is None
            ):
                raise BrowserReviewError(
                    "BROWSER_MCP_TOOL_REFUSED", "visual fixture URL is not opaque and exact"
                )
            page_classes[url] = f"fixture-{variant.lower()}"
        if len(page_classes) != 2:
            raise BrowserReviewError(
                "BROWSER_MCP_TOOL_REFUSED", "visual fixture URLs are not distinct"
            )
        root = Path(artifact_dir)
        try:
            resolved = root.resolve(strict=True)
            observed = root.lstat()
        except OSError as exc:
            raise BrowserReviewError(
                "BROWSER_MCP_TOOL_REFUSED", "attempt artifact root is unavailable"
            ) from exc
        if (
            root.is_symlink()
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.geteuid()
            or stat.S_IMODE(observed.st_mode) != 0o700
        ):
            raise BrowserReviewError(
                "BROWSER_MCP_TOOL_REFUSED", "attempt artifact root is not exact"
            )
        self.origin = origin
        self.artifact_dir = resolved
        self._artifact_dir_identity = (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_uid,
            observed.st_gid,
        )
        self._fixture_urls = {key: fixture_urls[key] for key in ("A", "B")}
        self._page_classes = page_classes
        self._current_page: str | None = None
        self._viewport: dict[str, int] | None = None
        self._screenshots: set[str] = set()
        self._image_content_sha256: dict[str, str] = {}
        self._model_image_content_sha256: dict[str, str] = {}
        self._console_rows: list[dict[str, Any]] = []
        self._network_rows: list[dict[str, Any]] = []
        self._calls: dict[str, int] = {}
        self._successful_calls: dict[str, int] = {}
        self._navigation_epoch = 0
        self._snapshot_binding: tuple[str, int] | None = None
        self._pending_snapshot_binding: tuple[str, int] | None = None
        self._pending_state_call: tuple[
            str, bytes, dict[str, Any]
        ] | None = None
        self._pending_interaction_binding: tuple[str, int, str] | None = None
        self._interaction: dict[str, str] | None = None
        self._bounded_interaction_forwarded = False
        # There is no tool or request field that can alter the locked launch
        # envelope; every tools/call still passes this guard.
        self._egress_falsifiers = {"proxy_override": "REFUSED"}

    @staticmethod
    def _refuse(detail: str) -> None:
        raise BrowserReviewError("BROWSER_MCP_TOOL_REFUSED", detail)

    @staticmethod
    def _closed(arguments: Mapping[str, Any], *, allowed: set[str]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping) or not set(arguments).issubset(allowed):
            BrowserMcpToolGuard._refuse("MCP tool arguments are outside the closed shape")
        try:
            encoded = _canonical_bytes(dict(arguments))
        except (TypeError, ValueError, UnicodeError):
            BrowserMcpToolGuard._refuse("MCP tool arguments are not canonical JSON")
        if len(encoded) > 4096:
            BrowserMcpToolGuard._refuse("MCP tool arguments exceed the reviewed bound")
        return dict(arguments)

    @staticmethod
    def _bounded_token(value: Any, *, maximum: int = 256) -> bool:
        return (
            isinstance(value, str)
            and bool(value)
            and value == value.strip()
            and "\x00" not in value
            and len(value.encode("utf-8")) <= maximum
        )

    def _page_class(self, url: str) -> str | None:
        if url == f"{self.origin}/":
            return "product"
        return self._page_classes.get(url)

    @staticmethod
    def _state_call_key(name: str, arguments: Mapping[str, Any]) -> tuple[str, bytes]:
        return name, _canonical_bytes(dict(arguments))

    def _reserve_state_call(
        self,
        name: str,
        arguments: Mapping[str, Any],
        transition: Mapping[str, Any],
    ) -> None:
        """Invalidate optimistic state until one exact MCP result succeeds."""

        if (
            self._pending_state_call is not None
            or self._pending_snapshot_binding is not None
            or self._pending_interaction_binding is not None
        ):
            self._refuse("browser state transition is already pending")
        call_name, encoded = self._state_call_key(name, arguments)
        self._pending_state_call = (call_name, encoded, dict(transition))
        self._snapshot_binding = None
        if name in {"browser_navigate", "browser_close", "browser_tabs"}:
            self._current_page = None
        if name in {"browser_resize", "browser_close"}:
            self._viewport = None

    def _pending_transition(
        self, name: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        pending = self._pending_state_call
        if pending is None:
            return None
        call_name, encoded, transition = pending
        expected_name, expected_encoded = self._state_call_key(name, arguments)
        if (call_name, encoded) != (expected_name, expected_encoded):
            return None
        return transition

    @staticmethod
    def _stat_fingerprint(info: os.stat_result) -> tuple[int, ...]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_nlink,
            info.st_uid,
            info.st_gid,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    @staticmethod
    def _file_identity(info: os.stat_result) -> tuple[int, ...]:
        """Identity fields that remain stable when the same inode is renamed."""

        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_nlink,
            info.st_uid,
            info.st_gid,
            info.st_size,
        )

    @staticmethod
    def _directory_identity(info: os.stat_result) -> tuple[int, ...]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_uid,
            info.st_gid,
        )

    @staticmethod
    def _model_message_viewport(viewport: Mapping[str, int]) -> dict[str, int]:
        """Mirror the pinned MCP's reviewed scaleImageToFitMessage contract."""

        width = viewport["width"]
        height = viewport["height"]
        shrink = min(
            1568 / width,
            1568 / height,
            math.sqrt((1.15 * 1024 * 1024) / (width * height)),
        )
        if shrink > 1:
            return {"width": width, "height": height}
        return {"width": int(width * shrink), "height": int(height * shrink)}

    def _consume_full_viewport_artifact(
        self,
        *,
        link: str,
        filename: str,
        model_pixels: bytes,
        model_viewport: Mapping[str, int],
        viewport: Mapping[str, int],
    ) -> bytes:
        """Read, seal, and remove one exact upstream MCP screenshot by dirfd."""

        if (
            not isinstance(link, str)
            or not link.startswith("./")
            or PurePosixPath(link).parts != (link[2:],)
        ):
            self._refuse("screenshot result link is outside the direct artifact root")
        leaf = link[2:]
        if re.fullmatch(
            r"page-[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            r"[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{3}Z\.png",
            leaf,
        ) is None:
            self._refuse("screenshot result link is not the pinned MCP filename")

        root_fd = -1
        source_fd = -1
        try:
            root_fd = os.open(
                self.artifact_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            root_before = os.fstat(root_fd)
            root_named = self.artifact_dir.lstat()
            named_before = os.stat(leaf, dir_fd=root_fd, follow_symlinks=False)
            source_fd = os.open(
                leaf,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_fd,
            )
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISDIR(root_before.st_mode)
                or root_before.st_uid != os.geteuid()
                or stat.S_IMODE(root_before.st_mode) != 0o700
                or self._directory_identity(root_before)
                != self._artifact_dir_identity
                or self._directory_identity(root_named)
                != self._artifact_dir_identity
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) not in {0o600, 0o644}
                or not 0 < opened.st_size <= MAX_SCREENSHOT_BYTES
                or self._stat_fingerprint(named_before)
                != self._stat_fingerprint(opened)
            ):
                self._refuse("upstream screenshot artifact identity is not exact")

            chunks: list[bytes] = []
            observed_bytes = 0
            while True:
                chunk = os.read(source_fd, min(1024 * 1024, MAX_SCREENSHOT_BYTES + 1 - observed_bytes))
                if not chunk:
                    break
                chunks.append(chunk)
                observed_bytes += len(chunk)
                if observed_bytes > MAX_SCREENSHOT_BYTES:
                    self._refuse("upstream screenshot artifact exceeds the reviewed bound")
            payload = b"".join(chunks)
            opened_after = os.fstat(source_fd)
            named_after = os.stat(leaf, dir_fd=root_fd, follow_symlinks=False)
            root_after = os.fstat(root_fd)
            if (
                len(payload) != opened.st_size
                or self._stat_fingerprint(opened)
                != self._stat_fingerprint(opened_after)
                or self._stat_fingerprint(opened)
                != self._stat_fingerprint(named_after)
                or self._stat_fingerprint(root_before)
                != self._stat_fingerprint(root_after)
            ):
                self._refuse("upstream screenshot artifact changed during read")

            _validate_png_dimensions(payload, viewport=viewport)
            if dict(model_viewport) == dict(viewport) and model_pixels != payload:
                self._refuse("unscaled model image differs from the full screenshot")
            if self._stat_fingerprint(opened) != self._stat_fingerprint(
                os.stat(leaf, dir_fd=root_fd, follow_symlinks=False)
            ):
                self._refuse("upstream screenshot name changed before cleanup")

            tombstone = f".mcp-consume-{secrets.token_hex(16)}"
            try:
                os.stat(tombstone, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:  # pragma: no cover - collision-resistant fail-closed guard
                self._refuse("upstream screenshot cleanup tombstone already exists")
            os.rename(
                leaf,
                tombstone,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
            moved = os.stat(tombstone, dir_fd=root_fd, follow_symlinks=False)
            if self._file_identity(opened) != self._file_identity(moved):
                self._refuse("upstream screenshot name was replaced before cleanup")
            os.unlink(tombstone, dir_fd=root_fd)
            if os.fstat(source_fd).st_nlink != 0:
                self._refuse("upstream screenshot inode survived cleanup")
            for consumed_name in (leaf, tombstone):
                try:
                    os.stat(consumed_name, dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                self._refuse("upstream screenshot name survived cleanup")
            os.fsync(root_fd)

            destination_fd = -1
            destination: os.stat_result | None = None
            try:
                destination_fd = os.open(
                    filename,
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=root_fd,
                )
                view = memoryview(payload)
                while view:
                    written = os.write(destination_fd, view)
                    if written <= 0:
                        raise OSError("short screenshot artifact write")
                    view = view[written:]
                os.fsync(destination_fd)
                destination = os.fstat(destination_fd)
                os.lseek(destination_fd, 0, os.SEEK_SET)
                readback: list[bytes] = []
                while True:
                    chunk = os.read(destination_fd, 1024 * 1024)
                    if not chunk:
                        break
                    readback.append(chunk)
                destination_named = os.stat(
                    filename, dir_fd=root_fd, follow_symlinks=False
                )
                if (
                    not stat.S_ISREG(destination.st_mode)
                    or destination.st_uid != os.geteuid()
                    or destination.st_nlink != 1
                    or stat.S_IMODE(destination.st_mode) != 0o600
                    or destination.st_size != len(payload)
                    or b"".join(readback) != payload
                    or self._stat_fingerprint(destination)
                    != self._stat_fingerprint(destination_named)
                ):
                    self._refuse("sealed screenshot artifact identity is not exact")
            finally:
                if destination_fd >= 0:
                    os.close(destination_fd)
            os.fsync(root_fd)
            if destination is None:
                self._refuse("sealed screenshot artifact identity is unavailable")
            root_final = os.fstat(root_fd)
            root_named_final = self.artifact_dir.lstat()
            destination_final = os.stat(
                filename, dir_fd=root_fd, follow_symlinks=False
            )
            if (
                self._directory_identity(root_final)
                != self._artifact_dir_identity
                or self._directory_identity(root_named_final)
                != self._artifact_dir_identity
                or self._stat_fingerprint(destination)
                != self._stat_fingerprint(destination_final)
            ):
                self._refuse("sealed screenshot artifact root changed before completion")
            return payload
        except BrowserReviewError:
            raise
        except OSError as exc:
            raise BrowserReviewError(
                "BROWSER_MCP_TOOL_REFUSED",
                "upstream screenshot artifact could not be consumed safely",
            ) from exc
        finally:
            if source_fd >= 0:
                os.close(source_fd)
            if root_fd >= 0:
                os.close(root_fd)

    def rewrite_call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Validate one model-authored call and rewrite only confined filenames."""

        if name not in ALLOWED_TOOLS:
            self._refuse("MCP tool is outside the browser review allowlist")
        self._calls[name] = self._calls.get(name, 0) + 1
        if self._calls[name] > 16:
            self._refuse("MCP tool call count exceeds the reviewed bound")

        if name == "browser_navigate":
            values = self._closed(arguments, allowed={"url"})
            if set(values) != {"url"} or not self._bounded_token(
                values.get("url"), maximum=2048
            ):
                self._refuse("browser navigation URL is invalid")
            url = str(values["url"])
            if urlsplit(url).scheme == "file":
                self._egress_falsifiers["file_url"] = "REFUSED"
                self._refuse("file URL navigation is refused")
            page_class = self._page_class(url)
            if page_class is None:
                self._refuse("browser navigation is outside the exact review origin")
            self._reserve_state_call(
                name, values, {"current_page": page_class}
            )
            return values

        if name == "browser_resize":
            values = self._closed(arguments, allowed={"height", "width"})
            if set(values) != {"height", "width"} or values not in (
                _DESKTOP,
                _MOBILE,
                self._VISUAL_VIEWPORT,
            ):
                self._refuse("browser viewport is outside the reviewed proof set")
            self._reserve_state_call(
                name,
                values,
                {
                    "viewport": {
                        "width": int(values["width"]),
                        "height": int(values["height"]),
                    }
                },
            )
            return values

        if name == "browser_take_screenshot":
            values = self._closed(
                arguments,
                allowed={"element", "filename", "fullPage", "scale", "target", "type"},
            )
            if set(values) != {"filename", "fullPage", "scale", "type"}:
                self._refuse("screenshot arguments are not the exact page proof shape")
            filename = values.get("filename")
            binding = self._SCREENSHOT_BINDINGS.get(str(filename))
            if (
                binding is None
                or filename in self._screenshots
                or values.get("fullPage") is not False
                or values.get("scale") != "css"
                or values.get("type") != "png"
                or self._current_page != binding[0]
                or self._viewport != binding[1]
            ):
                self._refuse("screenshot is not bound to its exact page and viewport")
            self._screenshots.add(str(filename))
            rewritten = dict(values)
            # Omitting the upstream filename is deliberate: the pinned MCP then
            # returns an image content block instead of writing through its own
            # workspace-permitting file resolver.  This guard persists the
            # verified bytes itself under the fixed logical name.
            rewritten.pop("filename")
            return rewritten

        if name == "browser_console_messages":
            values = self._closed(arguments, allowed={"all", "level"})
            if (
                set(values) != {"all", "level"}
                or values.get("all") is not True
                or values.get("level") not in {"error", "warning", "info"}
            ):
                self._refuse("console capture is outside the bounded in-memory shape")
            return values

        if name == "browser_network_requests":
            values = self._closed(arguments, allowed={"static"})
            if values != {"static": True}:
                self._refuse("network capture is outside the bounded in-memory shape")
            return values

        if name in {"browser_close", "browser_snapshot"}:
            values = self._closed(arguments, allowed=set())
            if values:
                self._refuse("parameterless browser tool received arguments")
            if name == "browser_close":
                self._reserve_state_call(name, values, {"closed": True})
            else:
                if (
                    self._pending_state_call is not None
                    or self._pending_snapshot_binding is not None
                    or self._current_page is None
                ):
                    self._refuse(
                        "structured snapshot requires one successfully established page"
                    )
                self._pending_snapshot_binding = (
                    self._current_page,
                    self._navigation_epoch,
                )
            return values

        if name == "browser_wait_for":
            values = self._closed(arguments, allowed={"text", "textGone", "time"})
            if len(values) != 1:
                self._refuse("browser wait must use one bounded condition")
            if "time" in values:
                seconds = values["time"]
                if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 2:
                    self._refuse("browser wait exceeds two seconds")
            elif not self._bounded_token(next(iter(values.values())), maximum=128):
                self._refuse("browser wait text is invalid")
            return values

        if name == "browser_tabs":
            values = self._closed(arguments, allowed={"action", "index"})
            if values == {"action": "list"}:
                return values
            if (
                set(values) == {"action", "index"}
                and values.get("action") == "select"
                and type(values.get("index")) is int
                and 0 <= values["index"] <= 3
            ):
                self._reserve_state_call(name, values, {"selected_tab": True})
                return values
            self._refuse("browser tab operation is outside list/select")

        if name in {"browser_click", "browser_hover", "browser_fill_form"}:
            if name != "browser_hover" or self._current_page != "product":
                self._refuse(
                    "bounded browser interaction is product-page-only harmless hover"
                )
            if (
                self._pending_state_call is not None
                or self._pending_snapshot_binding is not None
                or self._pending_interaction_binding is not None
                or self._snapshot_binding
                != (self._current_page, self._navigation_epoch)
            ):
                self._refuse(
                    "structured snapshot must succeed before the bounded interaction"
                )
            if self._bounded_interaction_forwarded:
                self._refuse("bounded browser interaction is already exhausted")
            values = self._closed(arguments, allowed={"element", "target"})
            if set(values) not in ({"target"}, {"element", "target"}) or not self._bounded_token(values.get("target")):
                self._refuse("hover target is invalid")
            self._bounded_interaction_forwarded = True
            self._pending_interaction_binding = (
                self._current_page,
                self._navigation_epoch,
                name,
            )
            return values

        self._refuse("MCP tool lacks an enforcing argument policy")

    def record_result(
        self,
        name: str,
        original_arguments: Mapping[str, Any],
        response: Mapping[str, Any],
    ) -> None:
        """Bind observed tool output to the already-authorized call."""

        if name not in ALLOWED_TOOLS or not isinstance(response, Mapping):
            self._refuse("MCP tool response lacks an authorized call")
        transition = self._pending_transition(name, original_arguments)
        stateful_response = name in {
            "browser_close",
            "browser_navigate",
            "browser_resize",
        } or (
            name == "browser_tabs"
            and original_arguments.get("action") == "select"
        )
        if stateful_response and transition is None:
            self._refuse(
                "MCP state response lacks its exact pending transition"
            )
        snapshot_binding = (
            self._pending_snapshot_binding if name == "browser_snapshot" else None
        )
        interaction_binding = (
            self._pending_interaction_binding
            if name in _BOUNDED_INTERACTION_TOOLS
            else None
        )
        if name in _BOUNDED_INTERACTION_TOOLS and interaction_binding is None:
            self._refuse(
                "MCP interaction response lacks its exact pending product binding"
            )
        result = response.get("result")
        if (
            not isinstance(result, Mapping)
            or response.get("error") is not None
            or result.get("isError", False) is not False
        ):
            if transition is not None:
                self._pending_state_call = None
            if name == "browser_snapshot":
                self._pending_snapshot_binding = None
            if name in _BOUNDED_INTERACTION_TOOLS:
                self._pending_interaction_binding = None
            self._refuse("MCP tool response is not a successful result")
        content = result.get("content")
        if not isinstance(content, list):
            self._refuse("MCP tool response content is not an array")
        encoded = _canonical_bytes(content)
        if len(encoded) > MAX_TEXT_EVIDENCE_BYTES + (2 * MAX_SCREENSHOT_BYTES):
            self._refuse("MCP tool response exceeds the reviewed bound")

        if name == "browser_snapshot":
            if (
                not content
                or not any(
                    isinstance(block, Mapping)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                    and bool(block["text"].strip())
                    for block in content
                )
            ):
                self._pending_snapshot_binding = None
                self._refuse("structured snapshot result is empty")
            if (
                snapshot_binding is None
                or self._pending_state_call is not None
                or snapshot_binding
                != (self._current_page, self._navigation_epoch)
            ):
                self._pending_snapshot_binding = None
                self._refuse(
                    "structured snapshot result is not bound to the current page"
                )
            self._pending_snapshot_binding = None
            self._snapshot_binding = snapshot_binding

        if name in _BOUNDED_INTERACTION_TOOLS:
            if (
                interaction_binding
                != (self._current_page, self._navigation_epoch, "browser_hover")
                or self._snapshot_binding
                != (self._current_page, self._navigation_epoch)
            ):
                self._pending_interaction_binding = None
                self._refuse(
                    "successful interaction is not bound to the product snapshot"
                )
            self._pending_interaction_binding = None
            self._interaction = {
                "page_class": "product",
                "tool": "browser_hover",
            }

        if transition is not None:
            self._pending_state_call = None
            if name == "browser_navigate":
                self._current_page = str(transition["current_page"])
                self._navigation_epoch += 1
            elif name == "browser_resize":
                self._viewport = dict(transition["viewport"])
            elif name in {"browser_close", "browser_tabs"}:
                self._current_page = None
                self._snapshot_binding = None

        if name == "browser_take_screenshot":
            filename = str(original_arguments.get("filename") or "")
            texts = [
                block
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "text"
            ]
            images = [
                block
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "image"
            ]
            if (
                len(content) != 2
                or len(texts) != 1
                or len(images) != 1
                or filename not in self._screenshots
                or set(texts[0]) != {"text", "type"}
                or not isinstance(texts[0].get("text"), str)
            ):
                self._refuse("screenshot response lacks one bound file and image result")
            links = self._SCREENSHOT_LINK_RE.findall(texts[0]["text"])
            if len(links) != 1 or texts[0]["text"].count("](") != 1:
                self._refuse("screenshot response lacks one exact upstream artifact link")
            image = images[0]
            if (
                set(image) != {"data", "mimeType", "type"}
                or image.get("mimeType") != "image/png"
                or not isinstance(image.get("data"), str)
            ):
                self._refuse("screenshot response image content is not PNG")
            try:
                pixels = base64.b64decode(image["data"], validate=True)
            except (ValueError, UnicodeError) as exc:
                raise BrowserReviewError(
                    "BROWSER_MCP_TOOL_REFUSED", "screenshot image content is malformed"
                ) from exc
            if (
                not pixels.startswith(b"\x89PNG\r\n\x1a\n")
                or not 0 < len(pixels) <= MAX_SCREENSHOT_BYTES
            ):
                self._refuse("screenshot image content is outside the reviewed bound")
            viewport = self._SCREENSHOT_BINDINGS[filename][1]
            model_viewport = self._model_message_viewport(viewport)
            _validate_png_dimensions(
                pixels, viewport=model_viewport
            )
            full_viewport = self._consume_full_viewport_artifact(
                link=links[0],
                filename=filename,
                model_pixels=pixels,
                model_viewport=model_viewport,
                viewport=viewport,
            )
            self._image_content_sha256[filename] = hashlib.sha256(
                full_viewport
            ).hexdigest()
            self._model_image_content_sha256[filename] = hashlib.sha256(
                pixels
            ).hexdigest()
            self._successful_calls[name] = self._successful_calls.get(name, 0) + 1
            return

        if name in {"browser_console_messages", "browser_network_requests"}:
            row = {
                "bytes": len(encoded),
                "content_sha256": hashlib.sha256(encoded).hexdigest(),
                "tool": name,
            }
            target = (
                self._console_rows
                if name == "browser_console_messages"
                else self._network_rows
            )
            maximum = MAX_CONSOLE_ROWS if name == "browser_console_messages" else MAX_NETWORK_ROWS
            if len(target) >= maximum:
                self._refuse("MCP evidence row count exceeds the reviewed bound")
            target.append(row)
        self._successful_calls[name] = self._successful_calls.get(name, 0) + 1

    def evidence(self) -> dict[str, Any]:
        return {
            "calls": dict(sorted(self._successful_calls.items())),
            "console_rows": list(self._console_rows),
            "egress_falsifiers": dict(sorted(self._egress_falsifiers.items())),
            "image_content_sha256": dict(sorted(self._image_content_sha256.items())),
            "interaction": (
                dict(self._interaction) if self._interaction is not None else None
            ),
            "model_image_content_sha256": dict(
                sorted(self._model_image_content_sha256.items())
            ),
            "network_rows": list(self._network_rows),
            "screenshots": sorted(self._screenshots),
        }


class _GuardedMcpBridge:
    """Transparent JSON-lines MCP interposer with one fixed child process group."""

    _CLIENT_METHODS = frozenset(
        {
            "initialize",
            "notifications/cancelled",
            "notifications/initialized",
            "ping",
            "tools/call",
            "tools/list",
        }
    )
    _CLIENT_NOTIFICATIONS = frozenset(
        {"notifications/cancelled", "notifications/initialized"}
    )
    _SERVER_NOTIFICATIONS = frozenset(
        {
            "notifications/message",
            "notifications/progress",
            "notifications/resources/list_changed",
            "notifications/tools/list_changed",
        }
    )

    def __init__(
        self,
        *,
        process: subprocess.Popen[bytes],
        guard: BrowserMcpToolGuard,
        client_input: Any,
        client_output: Any,
    ) -> None:
        if process.stdin is None or process.stdout is None:
            raise BrowserReviewError(
                "BROWSER_MCP_START_FAILED", "guarded MCP pipes are unavailable"
            )
        self.process = process
        self.guard = guard
        self.client_input = client_input
        self.client_output = client_output
        self._pending: dict[
            Any, tuple[str, str | None, dict[str, Any] | None]
        ] = {}
        self._pending_lock = threading.Lock()
        self._output_lock = threading.Lock()
        self._client_error: Exception | None = None
        self._tool_call_in_flight = False

    def _write_client(self, payload: Mapping[str, Any]) -> None:
        encoded = _canonical_bytes(dict(payload)) + b"\n"
        with self._output_lock:
            self.client_output.write(encoded)
            self.client_output.flush()

    def _refusal(self, request_id: Any) -> None:
        self._write_client(
            {
                "error": {
                    "code": -32602,
                    "message": "browser MCP call refused by attempt policy",
                },
                "id": request_id,
                "jsonrpc": "2.0",
            }
        )

    @staticmethod
    def _decode_line(raw: bytes) -> dict[str, Any]:
        if not raw.endswith(b"\n") or not 1 <= len(raw) <= _MAX_PROTOCOL_LINE_BYTES:
            raise BrowserReviewError(
                "BROWSER_MCP_PROTOCOL_FAILED", "MCP frame is outside the reviewed bound"
            )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise BrowserReviewError(
                "BROWSER_MCP_PROTOCOL_FAILED", "MCP frame is not valid JSON"
            ) from exc
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise BrowserReviewError(
                "BROWSER_MCP_PROTOCOL_FAILED", "MCP frame is not a JSON-RPC object"
            )
        return value

    def _client_loop(self) -> None:
        assert self.process.stdin is not None
        try:
            for raw in self.client_input:
                request = self._decode_line(raw)
                method = request.get("method")
                request_id = request.get("id")
                if (
                    not isinstance(method, str)
                    or method not in self._CLIENT_METHODS
                    or set(request)
                    not in (
                        {"id", "jsonrpc", "method", "params"},
                        {"jsonrpc", "method", "params"},
                    )
                    or (method in self._CLIENT_NOTIFICATIONS) != (request_id is None)
                    or (method not in self._CLIENT_NOTIFICATIONS and request_id is None)
                ):
                    raise BrowserReviewError(
                        "BROWSER_MCP_PROTOCOL_FAILED",
                        "client MCP method or request shape is outside the reviewed protocol",
                    )
                if method == "tools/call":
                    params = request.get("params")
                    if (
                        not isinstance(params, Mapping)
                        or set(params) != {"arguments", "name"}
                        or not isinstance(params.get("name"), str)
                        or not isinstance(params.get("arguments"), Mapping)
                    ):
                        self._refusal(request_id)
                        continue
                    name = str(params["name"])
                    original = dict(params["arguments"])
                    with self._pending_lock:
                        if self._tool_call_in_flight:
                            busy = True
                        else:
                            self._tool_call_in_flight = True
                            busy = False
                    if busy:
                        self._refusal(request_id)
                        continue
                    try:
                        rewritten = self.guard.rewrite_call(name, original)
                    except BrowserReviewError:
                        with self._pending_lock:
                            self._tool_call_in_flight = False
                        self._refusal(request_id)
                        continue
                    forwarded = dict(request)
                    forwarded["params"] = {"arguments": rewritten, "name": name}
                    with self._pending_lock:
                        if request_id in self._pending:
                            raise BrowserReviewError(
                                "BROWSER_MCP_PROTOCOL_FAILED",
                                "MCP request id was reused while pending",
                            )
                        self._pending[request_id] = (method, name, original)
                    encoded = _canonical_bytes(forwarded) + b"\n"
                else:
                    params = request.get("params")
                    if not isinstance(params, Mapping):
                        raise BrowserReviewError(
                            "BROWSER_MCP_PROTOCOL_FAILED",
                            "client MCP control params are not an object",
                        )
                    if method in {"ping", "tools/list", "notifications/initialized"} and params:
                        raise BrowserReviewError(
                            "BROWSER_MCP_PROTOCOL_FAILED",
                            "client MCP control params are not the exact empty shape",
                        )
                    if request_id is not None:
                        with self._pending_lock:
                            if request_id in self._pending:
                                raise BrowserReviewError(
                                    "BROWSER_MCP_PROTOCOL_FAILED",
                                    "MCP request id was reused while pending",
                                )
                            self._pending[request_id] = (method, None, None)
                    encoded = _canonical_bytes(request) + b"\n"
                self.process.stdin.write(encoded)
                self.process.stdin.flush()
        except Exception as exc:  # noqa: BLE001 - converted to one fail-closed exit
            self._client_error = exc
            try:
                self.process.terminate()
            except OSError:
                pass
        finally:
            try:
                self.process.stdin.close()
            except OSError:
                pass

    def run(self) -> int:
        assert self.process.stdout is not None
        client_thread = threading.Thread(
            target=self._client_loop,
            name="worker-browser-b1-mcp-client-guard",
            daemon=False,
        )
        client_thread.start()
        server_error: Exception | None = None
        try:
            for raw in self.process.stdout:
                response = self._decode_line(raw)
                server_method = response.get("method")
                if server_method is not None:
                    if (
                        response.get("id") is not None
                        or server_method not in self._SERVER_NOTIFICATIONS
                        or set(response) != {"jsonrpc", "method", "params"}
                        or not isinstance(response.get("params"), Mapping)
                    ):
                        raise BrowserReviewError(
                            "BROWSER_MCP_PROTOCOL_FAILED",
                            "server initiated an unreviewed MCP request",
                        )
                    self._write_client(response)
                    continue
                request_id = response.get("id")
                if (
                    request_id is None
                    or set(response)
                    not in (
                        {"id", "jsonrpc", "result"},
                        {"error", "id", "jsonrpc"},
                    )
                ):
                    raise BrowserReviewError(
                        "BROWSER_MCP_PROTOCOL_FAILED",
                        "server MCP response shape is not closed",
                    )
                with self._pending_lock:
                    pending = self._pending.pop(request_id, None)
                if pending is None:
                    raise BrowserReviewError(
                        "BROWSER_MCP_PROTOCOL_FAILED",
                        "server MCP response id has no pending request",
                    )
                method, tool_name, original = pending
                if method == "initialize":
                    result = response.get("result")
                    server_info = (
                        result.get("serverInfo") if isinstance(result, Mapping) else None
                    )
                    if (
                        not isinstance(server_info, Mapping)
                        or str(server_info.get("name") or "").strip().lower()
                        != "playwright"
                        or server_info.get("version")
                        != "1.63.0-alpha-2026-08-05"
                    ):
                        raise BrowserReviewError(
                            "BROWSER_MCP_PROTOCOL_FAILED",
                            "pinned MCP server identity or version drifted",
                        )
                if method == "tools/list":
                    result = response.get("result")
                    tools = result.get("tools") if isinstance(result, Mapping) else None
                    if not isinstance(tools, list):
                        raise BrowserReviewError(
                            "BROWSER_MCP_PROTOCOL_FAILED", "MCP tool list is malformed"
                        )
                    selected = [
                        item
                        for item in tools
                        if isinstance(item, Mapping)
                        and item.get("name") in ALLOWED_TOOLS
                    ]
                    if (
                        len(selected) != len(ALLOWED_TOOLS)
                        or {item.get("name") for item in selected} != ALLOWED_TOOLS
                    ):
                        raise BrowserReviewError(
                            "BROWSER_MCP_PROTOCOL_FAILED",
                            "pinned MCP effective tool surface drifted",
                        )
                    filtered = dict(response)
                    filtered["result"] = dict(result)
                    filtered["result"]["tools"] = selected
                    response = filtered
                if method == "tools/call":
                    assert tool_name is not None and original is not None
                    try:
                        self.guard.record_result(tool_name, original, response)
                    except BrowserReviewError:
                        self._refusal(request_id)
                        with self._pending_lock:
                            self._tool_call_in_flight = False
                        continue
                    with self._pending_lock:
                        self._tool_call_in_flight = False
                self._write_client(response)
        except Exception as exc:  # noqa: BLE001 - converted to fail-closed exit
            server_error = exc
            try:
                self.process.terminate()
            except OSError:
                pass
        try:
            return_code = self.process.wait(timeout=_CLEANUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return_code = -1
        client_thread.join(_CLEANUP_GRACE_SECONDS)
        if client_thread.is_alive() or self._client_error is not None or server_error is not None:
            return 1
        with self._pending_lock:
            if self._pending:
                return 1
        return int(return_code)


_MCP_GUARD_EVIDENCE_FILE = "browser-mcp-guard-evidence.json"
_MCP_GUARD_EVIDENCE_SCHEMA = "mastermind.browser_mcp_guard_evidence/v2"


def _closed_mcp_guard_observations(
    calls: Any,
    *,
    console_rows: Any,
    interaction: Any,
    network_rows: Any,
) -> dict[str, int]:
    """Validate positive successful calls behind one guard-v2 receipt."""

    if not isinstance(calls, Mapping) or not calls:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "MCP guard evidence calls are incomplete"
        )
    normalized: dict[str, int] = {}
    for name, count in calls.items():
        if (
            not isinstance(name, str)
            or name not in ALLOWED_TOOLS
            or type(count) is not int
            or not 1 <= count <= 16
        ):
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID",
                "MCP guard evidence successful call count is invalid",
            )
        normalized[name] = count
    if any(
        normalized.get(name, 0) < minimum
        for name, minimum in _REQUIRED_MCP_SUCCESS_MINIMUMS.items()
    ) or normalized.get("browser_take_screenshot") != 4:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID",
            "MCP guard evidence required successful calls are incomplete",
        )
    if sum(normalized.get(name, 0) for name in _BOUNDED_INTERACTION_TOOLS) != 1:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID",
            "MCP guard evidence bounded interaction is not exact",
        )
    if (
        not isinstance(interaction, Mapping)
        or dict(interaction)
        != {"page_class": "product", "tool": "browser_hover"}
    ):
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID",
            "MCP guard evidence product interaction provenance is invalid",
        )

    for rows, tool, maximum in (
        (console_rows, "browser_console_messages", MAX_CONSOLE_ROWS),
        (network_rows, "browser_network_requests", MAX_NETWORK_ROWS),
    ):
        if (
            not isinstance(rows, list)
            or not 1 <= len(rows) <= maximum
            or normalized.get(tool) != len(rows)
        ):
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID",
                "MCP guard evidence result rows are incomplete",
            )
        for row in rows:
            if (
                not isinstance(row, Mapping)
                or set(row) != {"bytes", "content_sha256", "tool"}
                or row.get("tool") != tool
                or type(row.get("bytes")) is not int
                or not 0 < row["bytes"] <= MAX_TEXT_EVIDENCE_BYTES
                or _SHA256_RE.fullmatch(str(row.get("content_sha256") or ""))
                is None
            ):
                raise BrowserReviewError(
                    "BROWSER_RECEIPT_INVALID",
                    "MCP guard evidence result row is invalid",
                )
    return dict(sorted(normalized.items()))


def run_guarded_mcp_bridge(
    *,
    argv: Sequence[str],
    environment: Mapping[str, str],
    guard: BrowserMcpToolGuard,
    stdin: Any | None = None,
    stdout: Any | None = None,
    stderr: Any | None = None,
    pass_fds: Sequence[int] = (),
) -> int:
    """Run the official server behind the enforcing argument/evidence bridge."""

    input_stream = stdin if stdin is not None else os.sys.stdin.buffer
    output_stream = stdout if stdout is not None else os.sys.stdout.buffer
    error_stream = stderr if stderr is not None else os.sys.stderr.buffer
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=guard.artifact_dir,
            env=dict(environment),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_stream,
            shell=False,
            start_new_session=True,
            bufsize=0,
            pass_fds=tuple(pass_fds),
        )
        process_group = os.getpgid(process.pid)
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "pinned Playwright MCP could not start"
        ) from exc
    bridge = _GuardedMcpBridge(
        process=process,
        guard=guard,
        client_input=input_stream,
        client_output=output_stream,
    )
    return_code = 1
    cleanup_proven = False
    try:
        return_code = bridge.run()
    finally:
        cleanup_proven = _finish_process_group(process, process_group)
        evidence = guard.evidence()
        evidence.update(
            {
                "bridge_exit_code": return_code,
                "cleanup_proven": cleanup_proven,
                "schema_version": _MCP_GUARD_EVIDENCE_SCHEMA,
            }
        )
        payload = _canonical_bytes(evidence)
        if len(payload) > MAX_TEXT_EVIDENCE_BYTES:
            raise BrowserReviewError(
                "BROWSER_ARTIFACT_OVERSIZE", "MCP guard evidence exceeds the reviewed bound"
            )
        _write_private_bytes_once(
            guard.artifact_dir / _MCP_GUARD_EVIDENCE_FILE, payload
        )
    if not cleanup_proven:
        raise BrowserReviewError(
            "BROWSER_ORPHAN_PROCESS_UNCERTAIN", "MCP process group survived guard shutdown"
        )
    return return_code


def _validate_png_dimensions(
    raw: bytes, *, viewport: Mapping[str, int]
) -> tuple[int, int]:
    """Parse and inflate one bounded non-interlaced PNG before trusting it."""

    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot artifact is not PNG"
        )
    offset = 8
    width: int | None = None
    height: int | None = None
    bit_depth: int | None = None
    color_type: int | None = None
    compressed: list[bytes] = []
    saw_iend = False
    chunk_index = 0
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise BrowserReviewError(
                "BROWSER_SCREENSHOT_FAILED", "screenshot PNG framing is incomplete"
            )
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise BrowserReviewError(
                "BROWSER_SCREENSHOT_FAILED", "screenshot PNG chunk is incomplete"
            )
        payload = raw[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", raw[offset + 8 + length : end])[0]
        if (zlib.crc32(kind + payload) & 0xFFFFFFFF) != expected_crc:
            raise BrowserReviewError(
                "BROWSER_SCREENSHOT_FAILED", "screenshot PNG chunk checksum failed"
            )
        if kind == b"IHDR":
            if chunk_index != 0 or width is not None or length != 13:
                raise BrowserReviewError(
                    "BROWSER_SCREENSHOT_FAILED", "screenshot PNG header is not exact"
                )
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filtering,
                interlace,
            ) = struct.unpack(">IIBBBBB", payload)
            if (
                width <= 0
                or height <= 0
                or compression != 0
                or filtering != 0
                or interlace != 0
                or (color_type, bit_depth)
                not in {(0, 8), (2, 8), (4, 8), (6, 8)}
            ):
                raise BrowserReviewError(
                    "BROWSER_SCREENSHOT_FAILED", "screenshot PNG encoding is not reviewed"
                )
        elif kind == b"IDAT":
            if width is None or saw_iend:
                raise BrowserReviewError(
                    "BROWSER_SCREENSHOT_FAILED", "screenshot PNG image data is misplaced"
                )
            compressed.append(payload)
        elif kind == b"IEND":
            if length != 0 or not compressed or saw_iend:
                raise BrowserReviewError(
                    "BROWSER_SCREENSHOT_FAILED", "screenshot PNG terminator is invalid"
                )
            saw_iend = True
            if end != len(raw):
                raise BrowserReviewError(
                    "BROWSER_SCREENSHOT_FAILED", "screenshot PNG has trailing bytes"
                )
        elif kind[:1].isupper():
            raise BrowserReviewError(
                "BROWSER_SCREENSHOT_FAILED", "screenshot PNG has an unknown critical chunk"
            )
        offset = end
        chunk_index += 1

    if (
        width is None
        or height is None
        or bit_depth is None
        or color_type is None
        or not saw_iend
    ):
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot PNG is structurally incomplete"
        )
    if width != viewport["width"] or height != viewport["height"]:
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED",
            "screenshot dimensions do not match the bound viewport",
        )

    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    row_bytes = ((width * channels * bit_depth) + 7) // 8
    expected_bytes = height * (row_bytes + 1)
    if expected_bytes > (MAX_SCREENSHOT_BYTES * 4):
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot decoded pixels exceed the reviewed bound"
        )
    inflater = zlib.decompressobj()
    try:
        decoded = inflater.decompress(b"".join(compressed), expected_bytes + 1)
        if inflater.unconsumed_tail or len(decoded) > expected_bytes:
            raise ValueError("decoded image is oversized")
        decoded += inflater.flush((expected_bytes + 1) - len(decoded))
    except (ValueError, zlib.error) as exc:
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot PNG pixels are not decodable"
        ) from exc
    if (
        len(decoded) != expected_bytes
        or not inflater.eof
        or inflater.unused_data
        or any(decoded[row * (row_bytes + 1)] > 4 for row in range(height))
    ):
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot PNG pixels are not exact"
        )
    return width, height


def screenshot_artifact(
    artifact_dir: Path,
    relative_path: str,
    *,
    viewport: Mapping[str, int],
) -> dict[str, Any]:
    """Hash one direct screenshot artifact without following symlinks."""

    if set(viewport) != {"height", "width"} or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in viewport.values()
    ):
        raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "viewport is not closed positive pixels")
    if not isinstance(relative_path, str) or not relative_path or Path(relative_path).name != relative_path:
        raise BrowserReviewError("BROWSER_SCREENSHOT_FAILED", "screenshot path must be a direct artifact")
    root = Path(artifact_dir)
    candidate = root / relative_path
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        observed = resolved.lstat()
    except OSError as exc:
        raise BrowserReviewError("BROWSER_SCREENSHOT_FAILED", "screenshot artifact is unavailable") from exc
    if (
        candidate.is_symlink()
        or resolved.parent != resolved_root
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_size <= 0
        or observed.st_size > MAX_SCREENSHOT_BYTES
    ):
        raise BrowserReviewError("BROWSER_ARTIFACT_OVERSIZE", "screenshot artifact is outside the reviewed bound")
    raw = resolved.read_bytes()
    _validate_png_dimensions(raw, viewport=viewport)
    return {
        "relative_path": relative_path,
        "viewport": {"width": int(viewport["width"]), "height": int(viewport["height"])},
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _screenshot_artifact_at(
    directory_fd: int,
    relative_path: str,
    *,
    viewport: Mapping[str, int],
) -> dict[str, Any]:
    """Hash one screenshot through the already-bound Attempt directory."""

    if set(viewport) != {"height", "width"} or any(
        type(value) is not int or value <= 0 for value in viewport.values()
    ):
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "viewport is not closed positive pixels"
        )
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or Path(relative_path).name != relative_path
        or PurePosixPath(relative_path).parts != (relative_path,)
    ):
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot path must be a direct artifact"
        )
    descriptor = -1
    try:
        named_before = os.stat(
            relative_path, dir_fd=directory_fd, follow_symlinks=False
        )
        descriptor = os.open(
            relative_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 0 < before.st_size <= MAX_SCREENSHOT_BYTES
            or BrowserMcpToolGuard._stat_fingerprint(named_before)
            != BrowserMcpToolGuard._stat_fingerprint(before)
        ):
            raise OSError("screenshot identity is not exact")
        chunks: list[bytes] = []
        observed_bytes = 0
        while True:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, MAX_SCREENSHOT_BYTES + 1 - observed_bytes),
            )
            if not chunk:
                break
            chunks.append(chunk)
            observed_bytes += len(chunk)
            if observed_bytes > MAX_SCREENSHOT_BYTES:
                raise OSError("screenshot exceeds reviewed bound")
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        named_after = os.stat(
            relative_path, dir_fd=directory_fd, follow_symlinks=False
        )
        if (
            len(raw) != before.st_size
            or BrowserMcpToolGuard._stat_fingerprint(before)
            != BrowserMcpToolGuard._stat_fingerprint(after)
            or BrowserMcpToolGuard._stat_fingerprint(before)
            != BrowserMcpToolGuard._stat_fingerprint(named_after)
        ):
            raise OSError("screenshot changed during read")
        _validate_png_dimensions(raw, viewport=viewport)
        return {
            "relative_path": relative_path,
            "viewport": {
                "width": int(viewport["width"]),
                "height": int(viewport["height"]),
            },
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    except BrowserReviewError:
        raise
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_SCREENSHOT_FAILED", "screenshot artifact is unavailable"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _bounded_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    maximum_rows: int,
    field: str,
) -> dict[str, Any]:
    if (
        isinstance(rows, (str, bytes))
        or not 1 <= len(rows) <= maximum_rows
    ):
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID",
            f"{field} rows do not prove an explicit observation",
        )
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise BrowserReviewError("BROWSER_RECEIPT_INVALID", f"{field} evidence row is not an object")
        normalized.append({str(key): value for key, value in sorted(row.items(), key=lambda item: str(item[0]))})
    encoded = _canonical_bytes(normalized)
    if len(encoded) > MAX_TEXT_EVIDENCE_BYTES:
        raise BrowserReviewError("BROWSER_ARTIFACT_OVERSIZE", f"{field} evidence bytes exceed the reviewed bound")
    return {
        "observed": True,
        "rows": len(normalized),
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def seal_browser_review_receipt(
    context: BrowserAttemptContext,
    *,
    local_origin: str,
    mcp_guard: Mapping[str, Any],
    screenshots: Sequence[Mapping[str, Any]],
    console_rows: Sequence[Mapping[str, Any]],
    network_rows: Sequence[Mapping[str, Any]],
    egress_falsifiers: Mapping[str, str],
    visual_judgment: Mapping[str, Any],
    cleanup: Mapping[str, Any],
    tracked_workspace_changes_after_review: bool,
) -> dict[str, Any]:
    """Seal the closed F0 Attempt artifact or refuse incomplete evidence."""

    _validate_origin(local_origin)
    console = _bounded_rows(
        console_rows, maximum_rows=MAX_CONSOLE_ROWS, field="console"
    )
    network = _bounded_rows(
        network_rows, maximum_rows=MAX_NETWORK_ROWS, field="network"
    )
    guard_summary = _closed_mcp_guard_summary(mcp_guard)
    if not 2 <= len(screenshots) <= MAX_SCREENSHOTS:
        raise BrowserReviewError("BROWSER_VISUAL_CAPABILITY_UNPROVEN", "desktop and mobile screenshot evidence is required")
    screenshot_rows: list[dict[str, Any]] = []
    total_screenshot_bytes = 0
    for row in screenshots:
        if not isinstance(row, Mapping) or set(row) != {"bytes", "relative_path", "sha256", "viewport"}:
            raise BrowserReviewError("BROWSER_RECEIPT_INVALID", "screenshot receipt is not closed")
        size = row.get("bytes")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_SCREENSHOT_BYTES:
            raise BrowserReviewError("BROWSER_ARTIFACT_OVERSIZE", "screenshot bytes exceed the reviewed bound")
        total_screenshot_bytes += size
        _require_sha256(row.get("sha256"), field="screenshot.sha256")
        screenshot_rows.append(dict(row))
    if total_screenshot_bytes > MAX_SCREENSHOTS * MAX_SCREENSHOT_BYTES:
        raise BrowserReviewError("BROWSER_ARTIFACT_OVERSIZE", "screenshot evidence exceeds the aggregate bound")
    if set(egress_falsifiers) != _REQUIRED_EGRESS_FALSIFIERS or any(
        value != "REFUSED" for value in egress_falsifiers.values()
    ):
        raise BrowserReviewError("BROWSER_NETWORK_ESCAPE", "every hostile egress class must be refused")
    expected_visual_keys = {
        "defective_variant",
        "fixture_nonce",
        "image_sha256",
        "reason",
        "source",
    }
    if set(visual_judgment) != expected_visual_keys:
        raise BrowserReviewError("BROWSER_VISUAL_CAPABILITY_UNPROVEN", "visual judgment is not closed")
    if set(cleanup) != _REQUIRED_CLEANUP_KEYS:
        raise BrowserReviewError("BROWSER_ORPHAN_PROCESS_UNCERTAIN", "cleanup receipt is not closed")
    if any(cleanup.get(key) is not True for key in _REQUIRED_CLEANUP_KEYS - {"uid_sweep_digest"}):
        raise BrowserReviewError("BROWSER_ORPHAN_PROCESS_UNCERTAIN", "subordinate cleanup is not proven")
    _require_sha256(cleanup.get("uid_sweep_digest"), field="cleanup.uid_sweep_digest")
    if tracked_workspace_changes_after_review is not False:
        raise BrowserReviewError("BROWSER_WORKSPACE_MUTATION", "tracked workspace changed during review")
    for value, field in (
        (context.devserver_manifest_digest, "devserver_manifest_digest"),
        (context.capability_manifest_digest, "capability_manifest_digest"),
        (context.browser_profile_digest, "browser_profile_digest"),
        (context.playwright_tool_schema_digest, "playwright_tool_schema_digest"),
        (context.runtime_manifest_digest, "runtime_manifest_digest"),
        (context.browser_executable_sha256, "browser_executable_sha256"),
    ):
        _require_sha256(value, field=field)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "attempt_id": context.attempt_id,
        "session_epoch_id": context.session_epoch_id,
        "process_generation_id": context.process_generation_id,
        "workspace": asdict(context.workspace),
        "devserver": {
            "manifest_digest": context.devserver_manifest_digest,
            "local_origin": local_origin,
        },
        "capability": {
            "manifest_digest": context.capability_manifest_digest,
            "profile_id": context.browser_profile_id,
            "profile_digest": context.browser_profile_digest,
        },
        "playwright_mcp": {
            "identity": context.playwright_mcp_identity,
            "version": context.playwright_mcp_version,
            "tool_schema_digest": context.playwright_tool_schema_digest,
        },
        "browser": {
            "executable": context.browser_executable,
            "executable_sha256": context.browser_executable_sha256,
            "revision": context.browser_revision,
            "runtime_manifest_digest": context.runtime_manifest_digest,
        },
        "viewports": [dict(row["viewport"]) for row in screenshot_rows],
        "artifacts": {
            "screenshots": screenshot_rows,
            "console": console,
            "mcp_guard": guard_summary,
            "network": network,
        },
        "egress_falsifiers": dict(sorted(egress_falsifiers.items())),
        "external_egress_observed": False,
        "visual_judgment": dict(visual_judgment),
        "cleanup": dict(cleanup),
        "tracked_workspace_changes_after_review": False,
    }
    return browser_review_receipt(receipt)


_ATTEMPT_EVIDENCE_FILE = "browser-review-evidence.json"
_RECEIPT_FILE = "browser-review-receipt.json"
_BROWSER_ENV_KEYS = BROWSER_RESOURCE_ENV_KEYS
_BROWSER_LAUNCH_ENV_KEYS = _BROWSER_ENV_KEYS | {_RUNTIME_CONTAINER_FD_ENV}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_RUNTIME_MANIFEST_KEYS = frozenset(
    {
        "browser",
        "closure_inventory",
        "closure_tree_digest",
        "launcher",
        "mcp",
        "node",
        "runtime_container",
        "runtime_root",
        "schema_version",
        "tmp_install_postcondition",
    }
)
_RUNTIME_CONTAINER_IDENTITY_KEYS = frozenset(
    {"device", "gid", "inode", "mode", "uid"}
)
_RUNTIME_FILE_IDENTITY_KEYS = frozenset({"gid", "mode", "path", "sha256", "uid"})
_RUNTIME_NODE_KEYS = frozenset({"dynamic_library", "executable"})
_RUNTIME_CLOSURE_ENTRY_KEYS = frozenset(
    {"gid", "link", "mode", "path", "sha256", "size", "type", "uid"}
)
_RUNTIME_CLOSURE_ROOTS = (
    "node_modules",
    "browsers",
    "lib",
)
_TRUSTED_NODE_MACHO_PREFIXES = (
    "/opt/homebrew/opt/",
    "/System/Library/",
    "/usr/lib/",
)


def _runtime_attestation_invalid(detail: str) -> BrowserReviewError:
    return BrowserReviewError("BROWSER_RUNTIME_ATTESTATION_INVALID", detail)


def _otool_dependency_paths(payload: str, *, expected_header: Path) -> tuple[str, ...]:
    if not isinstance(payload, str):
        raise _runtime_attestation_invalid("Node Mach-O dependency output is invalid")
    lines = payload.splitlines()
    if not lines or lines[0].strip() != f"{expected_header}:":
        raise _runtime_attestation_invalid("Node Mach-O dependency header drifted")
    paths: list[str] = []
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if " (" not in line:
            raise _runtime_attestation_invalid("Node Mach-O dependency row is invalid")
        path, metadata = line.split(" (", 1)
        if not path or not metadata.endswith(")"):
            raise _runtime_attestation_invalid("Node Mach-O dependency row is invalid")
        paths.append(path)
    if not paths:
        raise _runtime_attestation_invalid("Node Mach-O dependency closure is empty")
    return tuple(paths)


def _otool_rpaths(payload: str) -> tuple[str, ...]:
    if not isinstance(payload, str):
        raise _runtime_attestation_invalid("Node Mach-O load commands are invalid")
    lines = [line.strip() for line in payload.splitlines()]
    rpaths: list[str] = []
    for index, line in enumerate(lines):
        if line != "cmd LC_RPATH":
            continue
        for candidate in lines[index + 1 : index + 4]:
            if candidate.startswith("path ") and " (offset " in candidate:
                path = candidate[5:].split(" (offset ", 1)[0]
                if not path:
                    break
                rpaths.append(path)
                break
        else:
            raise _runtime_attestation_invalid("Node Mach-O LC_RPATH is malformed")
    return tuple(rpaths)


def _trusted_node_macho_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return (
        "\x00" not in path
        and candidate.is_absolute()
        and ".." not in candidate.parts
        and path == candidate.as_posix()
        and path.startswith(_TRUSTED_NODE_MACHO_PREFIXES)
    )


def validate_node_macho_dependency_closure(
    *,
    node_path: Path,
    library_path: Path,
    node_dependencies: str,
    node_load_commands: str,
    library_dependencies: str,
) -> None:
    """Validate the one copied Node-relative dylib and its trusted-host leaves."""

    node = Path(node_path)
    library = Path(library_path)
    node_rows = _otool_dependency_paths(node_dependencies, expected_header=node)
    relative_node_rows = tuple(path for path in node_rows if not path.startswith("/"))
    if relative_node_rows != (f"@rpath/{RUNTIME_NODE_LIBRARY_NAME}",):
        raise _runtime_attestation_invalid("Node Mach-O relative dependency drifted")
    if any(
        not _trusted_node_macho_path(path)
        for path in node_rows
        if path.startswith("/")
    ):
        raise _runtime_attestation_invalid("Node Mach-O trusted-host dependency drifted")
    if _otool_rpaths(node_load_commands) != (
        "@loader_path",
        "@loader_path/../lib",
    ):
        raise _runtime_attestation_invalid("Node Mach-O loader paths drifted")

    library_rows = _otool_dependency_paths(
        library_dependencies,
        expected_header=library,
    )
    expected_install_name = f"/opt/homebrew/opt/node/lib/{RUNTIME_NODE_LIBRARY_NAME}"
    if library_rows[0] != expected_install_name:
        raise _runtime_attestation_invalid("Node Mach-O library install name drifted")
    if any(not _trusted_node_macho_path(path) for path in library_rows[1:]):
        raise _runtime_attestation_invalid("Node Mach-O library dependency drifted")


def _runtime_open_flags(*names: str) -> int:
    """Require every namespace-safety flag used by runtime attestation."""

    flags = 0
    for name in names:
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            raise _runtime_attestation_invalid(
                f"runtime attestation requires {name} support"
            )
        flags |= value
    return flags


def _runtime_parent_snapshot(path: Path) -> tuple[tuple[Path, int, int, int, int], ...]:
    current = Path(path.anchor)
    rows: list[tuple[Path, int, int, int, int]] = []
    try:
        for part in path.parts[1:-1]:
            current /= part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise OSError("symlinked or non-directory parent")
            rows.append(
                (current, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
            )
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime path parent is unsafe") from exc
    return tuple(rows)


def _stable_runtime_file(
    path: Path,
    *,
    capture: bool = False,
    maximum_bytes: int | None = None,
) -> tuple[os.stat_result, bytes | None, str]:
    """Hash one already-named file through the same no-follow descriptor."""

    candidate = Path(path)
    if not candidate.is_absolute():
        raise _runtime_attestation_invalid("runtime file path is not absolute")
    parents = _runtime_parent_snapshot(candidate)
    descriptor = -1
    try:
        descriptor = os.open(
            candidate,
            os.O_RDONLY | _runtime_open_flags("O_NOFOLLOW"),
        )
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        observed_size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_size += len(chunk)
            if maximum_bytes is not None and observed_size > maximum_bytes:
                raise OSError("runtime file exceeds bound")
            digest.update(chunk)
            if capture:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        leaf = candidate.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            any(getattr(before, field) != getattr(after, field) for field in stable_fields)
            or any(getattr(before, field) != getattr(leaf, field) for field in stable_fields)
            or observed_size != before.st_size
        ):
            raise OSError("runtime file changed while inspected")
        for parent, device, inode, _mtime_ns, _ctime_ns in parents:
            parent_info = parent.lstat()
            if (
                stat.S_ISLNK(parent_info.st_mode)
                or not stat.S_ISDIR(parent_info.st_mode)
                or (parent_info.st_dev, parent_info.st_ino) != (device, inode)
            ):
                raise OSError("runtime path parent changed while inspected")
        return before, (b"".join(chunks) if capture else None), digest.hexdigest()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime file is unavailable or unstable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _private_runtime_root(
    runtime_root: Path,
    *,
    expected_modes: frozenset[int],
) -> Path:
    candidate = Path(runtime_root)
    try:
        info = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        _runtime_parent_snapshot(candidate / "__runtime_child__")
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime root is unavailable") from exc
    if (
        not candidate.is_absolute()
        or resolved != candidate
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) not in expected_modes
    ):
        raise _runtime_attestation_invalid("runtime root ownership or mode drifted")
    return resolved


def prepare_runtime_install_tmp(runtime_root: Path) -> tuple[int, int]:
    """Create the one private installer TMPDIR without consulting ambient TMPDIR."""

    root = _private_runtime_root(runtime_root, expected_modes=frozenset({0o700}))
    temporary = root / RUNTIME_TMP_INSTALL_NAME
    if os.path.lexists(temporary):
        raise _runtime_attestation_invalid("runtime install TMPDIR already exists")
    try:
        temporary.mkdir(mode=0o700)
        info = temporary.lstat()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime install TMPDIR could not be created") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise _runtime_attestation_invalid("runtime install TMPDIR is not private")
    return info.st_dev, info.st_ino


def _same_runtime_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_uid,
        left.st_gid,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_uid,
        right.st_gid,
    )


def _runtime_cleanup_tombstone(descriptor: int) -> str:
    for _attempt in range(16):
        candidate = f".cleanup-{secrets.token_hex(16)}"
        try:
            os.stat(candidate, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return candidate
    raise OSError("could not reserve an installer cleanup tombstone")


def _remove_exact_runtime_entry(
    descriptor: int,
    name: str,
    expected: os.stat_result,
    *,
    directory: bool,
    opened_descriptor: int | None,
) -> None:
    """Atomically quarantine one observed inode before deleting that exact object."""

    current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    if not _same_runtime_object(expected, current):
        raise OSError("installer temporary entry changed before quarantine")
    tombstone = _runtime_cleanup_tombstone(descriptor)
    os.rename(
        name,
        tombstone,
        src_dir_fd=descriptor,
        dst_dir_fd=descriptor,
    )
    moved = os.stat(tombstone, dir_fd=descriptor, follow_symlinks=False)
    if not _same_runtime_object(expected, moved) or (
        opened_descriptor is not None
        and not _same_runtime_object(os.fstat(opened_descriptor), moved)
    ):
        try:
            os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            os.rename(
                tombstone,
                name,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
            )
        raise OSError("installer temporary entry changed during quarantine")
    if directory:
        os.rmdir(tombstone, dir_fd=descriptor)
    else:
        if moved.st_nlink != 1:
            raise OSError("installer temporary file has multiple links")
        os.unlink(tombstone, dir_fd=descriptor)
        if opened_descriptor is not None and os.fstat(opened_descriptor).st_nlink != 0:
            raise OSError("installer temporary file inode survived unlink")
    try:
        os.stat(tombstone, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise OSError("installer cleanup tombstone survived deletion")


def _clear_directory_descriptor(descriptor: int) -> None:
    for name in sorted(os.listdir(descriptor)):
        if not name or name in {".", ".."} or "/" in name or "\x00" in name:
            raise OSError("unsafe installer temporary entry")
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
            child = os.open(
                name,
                os.O_RDONLY
                | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
                dir_fd=descriptor,
            )
            try:
                opened = os.fstat(child)
                if not _same_runtime_object(opened, info):
                    raise OSError("installer temporary directory changed")
                _clear_directory_descriptor(child)
                _remove_exact_runtime_entry(
                    descriptor,
                    name,
                    opened,
                    directory=True,
                    opened_descriptor=child,
                )
            finally:
                os.close(child)
        else:
            child = -1
            try:
                if stat.S_ISREG(info.st_mode):
                    child = os.open(
                        name,
                        os.O_RDONLY | _runtime_open_flags("O_NOFOLLOW"),
                        dir_fd=descriptor,
                    )
                    if not _same_runtime_object(os.fstat(child), info):
                        raise OSError("installer temporary file changed")
                elif not stat.S_ISLNK(info.st_mode):
                    raise OSError("installer temporary entry is a special file")
                _remove_exact_runtime_entry(
                    descriptor,
                    name,
                    info,
                    directory=False,
                    opened_descriptor=child if child >= 0 else None,
                )
            finally:
                if child >= 0:
                    os.close(child)


def cleanup_runtime_install_tmp(
    runtime_root: Path,
    identity: tuple[int, int],
) -> None:
    """Remove only the exact TMPDIR inode created by prepare_runtime_install_tmp."""

    root = _private_runtime_root(
        runtime_root, expected_modes=frozenset({0o500, 0o700})
    )
    if (
        not isinstance(identity, tuple)
        or len(identity) != 2
        or any(type(item) is not int or item < 0 for item in identity)
    ):
        raise _runtime_attestation_invalid("runtime install TMPDIR identity is invalid")
    root_descriptor = os.open(
        root,
        os.O_RDONLY | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
    )
    temporary_descriptor = -1
    try:
        try:
            temporary_info = os.stat(
                RUNTIME_TMP_INSTALL_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            raise OSError("captured runtime install TMPDIR name is missing")
        if stat.S_IMODE(root.stat().st_mode) != 0o700:
            raise OSError("sealed runtime root unexpectedly retained install TMPDIR")
        if (
            stat.S_ISLNK(temporary_info.st_mode)
            or not stat.S_ISDIR(temporary_info.st_mode)
            or (temporary_info.st_dev, temporary_info.st_ino) != identity
            or temporary_info.st_uid != os.geteuid()
            or stat.S_IMODE(temporary_info.st_mode) != 0o700
        ):
            raise OSError("runtime install TMPDIR identity drifted")
        temporary_descriptor = os.open(
            RUNTIME_TMP_INSTALL_NAME,
            os.O_RDONLY
            | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
            dir_fd=root_descriptor,
        )
        opened = os.fstat(temporary_descriptor)
        if (opened.st_dev, opened.st_ino) != identity:
            raise OSError("runtime install TMPDIR path changed")
        _clear_directory_descriptor(temporary_descriptor)
        _remove_exact_runtime_entry(
            root_descriptor,
            RUNTIME_TMP_INSTALL_NAME,
            opened,
            directory=True,
            opened_descriptor=temporary_descriptor,
        )
        try:
            os.stat(
                RUNTIME_TMP_INSTALL_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        raise OSError("runtime install TMPDIR survived cleanup")
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime install TMPDIR cleanup failed") from exc
    finally:
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        os.close(root_descriptor)


def _stable_runtime_directory(path: Path) -> tuple[os.stat_result, tuple[str, ...]]:
    candidate = Path(path)
    parents = _runtime_parent_snapshot(candidate)
    descriptor = -1
    try:
        descriptor = os.open(
            candidate,
            os.O_RDONLY
            | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
        )
        before = os.fstat(descriptor)
        names = tuple(sorted(os.listdir(descriptor)))
        after = os.fstat(descriptor)
        leaf = candidate.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            any(getattr(before, field) != getattr(after, field) for field in stable_fields)
            or any(getattr(before, field) != getattr(leaf, field) for field in stable_fields)
            or not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
        ):
            raise OSError("runtime directory changed while listed")
        for parent, device, inode, _mtime_ns, _ctime_ns in parents:
            parent_info = parent.lstat()
            if (
                stat.S_ISLNK(parent_info.st_mode)
                or not stat.S_ISDIR(parent_info.st_mode)
                or (parent_info.st_dev, parent_info.st_ino) != (device, inode)
            ):
                raise OSError("runtime directory parent changed while listed")
        return before, names
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime closure directory is unstable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _safe_runtime_symlink(
    path: Path,
    *,
    closure_root: Path,
) -> tuple[os.stat_result, str, str]:
    candidate = Path(path)
    parents = _runtime_parent_snapshot(candidate)
    try:
        before = candidate.lstat()
        link = os.readlink(candidate)
        after = candidate.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            any(getattr(before, field) != getattr(after, field) for field in stable_fields)
            or not stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not link
            or Path(link).is_absolute()
            or "\x00" in link
        ):
            raise OSError("runtime closure symlink is unstable")
        resolved = (candidate.parent / link).resolve(strict=True)
        resolved.relative_to(closure_root)
        for parent, device, inode, _mtime_ns, _ctime_ns in parents:
            parent_info = parent.lstat()
            if (
                stat.S_ISLNK(parent_info.st_mode)
                or not stat.S_ISDIR(parent_info.st_mode)
                or (parent_info.st_dev, parent_info.st_ino) != (device, inode)
            ):
                raise OSError("runtime closure symlink parent changed")
    except (OSError, ValueError) as exc:
        raise _runtime_attestation_invalid("runtime closure symlink escaped") from exc
    return before, link, hashlib.sha256(link.encode("utf-8")).hexdigest()


def _closure_entry(
    *,
    runtime_root: Path,
    closure_root: Path,
    path: Path,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    relative = path.relative_to(runtime_root).as_posix()
    try:
        lexical = path.lstat()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime closure entry disappeared") from exc
    if lexical.st_uid != os.geteuid():
        raise _runtime_attestation_invalid("runtime closure entry owner drifted")
    if stat.S_ISDIR(lexical.st_mode) and not stat.S_ISLNK(lexical.st_mode):
        info, names = _stable_runtime_directory(path)
        mode = stat.S_IMODE(info.st_mode)
        if mode != 0o500:
            raise _runtime_attestation_invalid("runtime closure directory is writable")
        digest = hashlib.sha256(_canonical_bytes(list(names))).hexdigest()
        kind = "directory"
        link = ""
    elif stat.S_ISREG(lexical.st_mode):
        info, _payload, digest = _stable_runtime_file(path)
        mode = stat.S_IMODE(info.st_mode)
        if info.st_nlink != 1 or mode not in {0o400, 0o500}:
            raise _runtime_attestation_invalid("runtime closure file is writable or linked")
        names = ()
        kind = "file"
        link = ""
    elif stat.S_ISLNK(lexical.st_mode):
        info, link, digest = _safe_runtime_symlink(path, closure_root=closure_root)
        mode = stat.S_IMODE(info.st_mode)
        names = ()
        kind = "symlink"
    else:
        raise _runtime_attestation_invalid("runtime closure contains a special file")
    return (
        {
            "gid": info.st_gid,
            "link": link,
            "mode": mode,
            "path": relative,
            "sha256": digest,
            "size": info.st_size,
            "type": kind,
            "uid": info.st_uid,
        },
        names,
    )


def runtime_closure_inventory(runtime_root: Path) -> tuple[dict[str, Any], ...]:
    """Recompute the complete immutable package and Chromium revision closure."""

    root = _private_runtime_root(
        runtime_root, expected_modes=frozenset({0o500, 0o700})
    )
    inventory: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for relative_root in _RUNTIME_CLOSURE_ROOTS:
        closure_root = root / relative_root
        pending = [closure_root]
        while pending:
            candidate = pending.pop()
            if candidate in seen:
                raise _runtime_attestation_invalid("runtime closure paths overlap")
            seen.add(candidate)
            row, names = _closure_entry(
                runtime_root=root,
                closure_root=closure_root,
                path=candidate,
            )
            inventory.append(row)
            if row["type"] == "directory":
                pending.extend(candidate / name for name in reversed(names))
    normalized = tuple(sorted(inventory, key=lambda row: str(row["path"])))
    for row in normalized:
        if row["type"] == "symlink":
            _runtime_closure_symlink_terminal(normalized, str(row["path"]))
    return normalized


def _runtime_closure_symlink_target(link_path: str, raw_target: str) -> str:
    link = PurePosixPath(link_path)
    target = PurePosixPath(raw_target)
    if target.is_absolute() or not raw_target or "\x00" in raw_target:
        raise _runtime_attestation_invalid("runtime closure symlink target is unsafe")
    parts = list(link.parent.parts)
    closure_name = parts[0] if parts else ""
    for part in target.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if len(parts) <= 1:
                raise _runtime_attestation_invalid("runtime closure symlink escaped")
            parts.pop()
        else:
            parts.append(part)
    normalized = PurePosixPath(*parts).as_posix()
    if not closure_name or not (
        normalized == closure_name or normalized.startswith(f"{closure_name}/")
    ):
        raise _runtime_attestation_invalid("runtime closure symlink escaped")
    return normalized


def _runtime_closure_symlink_terminal(
    inventory: Sequence[Mapping[str, Any]],
    link_path: str,
) -> str:
    """Resolve a recorded link only through the already-observed closed inventory."""

    rows = {str(row["path"]): row for row in inventory}
    current = link_path
    visited: set[str] = set()
    for _depth in range(len(rows) + 1):
        if current in visited:
            raise _runtime_attestation_invalid("runtime closure symlink cycle detected")
        visited.add(current)
        row = rows.get(current)
        if row is not None and row.get("type") != "symlink":
            return current
        if row is not None:
            current = _runtime_closure_symlink_target(
                current, str(row.get("link") or "")
            )
            continue
        parts = PurePosixPath(current).parts
        for prefix_length in range(len(parts) - 1, 0, -1):
            prefix = PurePosixPath(*parts[:prefix_length]).as_posix()
            prefix_row = rows.get(prefix)
            if prefix_row is None or prefix_row.get("type") != "symlink":
                continue
            resolved_prefix = _runtime_closure_symlink_target(
                prefix,
                str(prefix_row.get("link") or ""),
            )
            current = PurePosixPath(
                resolved_prefix, *parts[prefix_length:]
            ).as_posix()
            break
        else:
            raise _runtime_attestation_invalid("runtime closure symlink is dangling")
    raise _runtime_attestation_invalid("runtime closure symlink chain is unbounded")


def runtime_closure_tree_digest(inventory: Sequence[Mapping[str, Any]]) -> str:
    return _canonical_digest([dict(row) for row in inventory])


def _require_exact_node_library_closure(
    inventory: Sequence[Mapping[str, Any]],
) -> None:
    rows = {
        str(row.get("path")): row
        for row in inventory
        if str(row.get("path")) == "lib"
        or str(row.get("path")).startswith("lib/")
    }
    library_path = f"lib/{RUNTIME_NODE_LIBRARY_NAME}"
    if set(rows) != {"lib", library_path}:
        raise _runtime_attestation_invalid("node dynamic library closure is not exact")
    if (
        rows["lib"].get("type") != "directory"
        or rows["lib"].get("mode") != 0o500
        or rows[library_path].get("type") != "file"
        or rows[library_path].get("mode") != 0o400
        or rows[library_path].get("link") != ""
    ):
        raise _runtime_attestation_invalid("node dynamic library closure is unsafe")


def normalize_runtime_closure_for_install(runtime_root: Path) -> None:
    """Make every runtime-controlled package/browser closure inode read-only."""

    root = _private_runtime_root(runtime_root, expected_modes=frozenset({0o700}))
    directories: list[Path] = []
    for relative_root in _RUNTIME_CLOSURE_ROOTS:
        closure_root = root / relative_root
        try:
            closure_root.relative_to(root)
            root_info = closure_root.lstat()
        except (OSError, ValueError) as exc:
            raise _runtime_attestation_invalid("runtime closure root is unavailable") from exc
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise _runtime_attestation_invalid("runtime closure root is unsafe")
        for current, names, files in os.walk(closure_root, topdown=True, followlinks=False):
            current_path = Path(current)
            current_info = current_path.lstat()
            if current_info.st_uid != os.geteuid() or stat.S_ISLNK(current_info.st_mode):
                raise _runtime_attestation_invalid("runtime closure directory owner drifted")
            directories.append(current_path)
            retained: list[str] = []
            for name in names:
                child = current_path / name
                child_info = child.lstat()
                if child_info.st_uid != os.geteuid():
                    raise _runtime_attestation_invalid("runtime closure entry owner drifted")
                if stat.S_ISLNK(child_info.st_mode):
                    _safe_runtime_symlink(child, closure_root=closure_root)
                elif stat.S_ISDIR(child_info.st_mode):
                    retained.append(name)
                else:
                    raise _runtime_attestation_invalid("runtime closure contains a special entry")
            names[:] = retained
            for name in files:
                child = current_path / name
                child_info = child.lstat()
                if child_info.st_uid != os.geteuid():
                    raise _runtime_attestation_invalid("runtime closure file owner drifted")
                if stat.S_ISLNK(child_info.st_mode):
                    _safe_runtime_symlink(child, closure_root=closure_root)
                    continue
                if not stat.S_ISREG(child_info.st_mode) or child_info.st_nlink != 1:
                    raise _runtime_attestation_invalid("runtime closure file is unsafe")
                os.chmod(child, 0o500 if child_info.st_mode & 0o111 else 0o400)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        os.chmod(directory, 0o500)


def _runtime_manifest_file_identity(path: Path) -> dict[str, Any]:
    candidate = Path(path)
    info, _payload, digest = _stable_runtime_file(candidate)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(info.st_mode) & 0o222
    ):
        raise _runtime_attestation_invalid("runtime manifest identity source is unsafe")
    return {
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "path": os.fspath(candidate),
        "sha256": digest,
        "uid": info.st_uid,
    }


def _runtime_container(runtime_root: Path, *, expected_mode: int) -> Path:
    container = Path(runtime_root).parent
    try:
        info = container.lstat()
        resolved = container.resolve(strict=True)
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime container is unavailable") from exc
    if (
        resolved != container
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != expected_mode
    ):
        raise _runtime_attestation_invalid("runtime container ownership or mode drifted")
    return container


def _runtime_container_manifest_identity(
    container: Path,
    *,
    expected_mode: int,
) -> dict[str, int]:
    """Return the inode identity bound by the independently pinned manifest."""

    candidate = Path(container)
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime container identity is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != expected_mode
    ):
        raise _runtime_attestation_invalid("runtime container identity drifted")
    return {
        "device": info.st_dev,
        "gid": info.st_gid,
        "inode": info.st_ino,
        "mode": expected_mode,
        "uid": info.st_uid,
    }


def _anchored_runtime_manifest(
    container_fd: int,
    *,
    expected_manifest_digest: str,
) -> Mapping[str, Any]:
    """Verify the pinned manifest and container through one inherited dir FD."""

    if (
        type(container_fd) is not int
        or container_fd < 3
        or _SHA256_RE.fullmatch(str(expected_manifest_digest or "")) is None
        or expected_manifest_digest == UNRATIFIED_RUNTIME_MANIFEST_DIGEST
    ):
        raise _runtime_attestation_invalid("runtime container descriptor binding is invalid")
    try:
        container_info = os.fstat(container_fd)
        descriptor = os.open(
            f"runtime/{RUNTIME_INSTALL_MANIFEST_NAME}",
            os.O_RDONLY | _runtime_open_flags("O_NOFOLLOW"),
            dir_fd=container_fd,
        )
        try:
            before = os.fstat(descriptor)
            payload = b""
            while len(payload) <= MAX_RUNTIME_INSTALL_MANIFEST_BYTES:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                payload += chunk
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise _runtime_attestation_invalid("anchored runtime manifest is unavailable") from exc
    if (
        not stat.S_ISDIR(container_info.st_mode)
        or container_info.st_uid != os.geteuid()
        or stat.S_IMODE(container_info.st_mode) != 0o500
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) != 0o400
        or not 0 < len(payload) <= MAX_RUNTIME_INSTALL_MANIFEST_BYTES
        or not _same_runtime_object(before, after)
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or hashlib.sha256(payload).hexdigest() != expected_manifest_digest
    ):
        raise _runtime_attestation_invalid("anchored runtime manifest drifted")
    try:
        value = json.loads(payload.decode("utf-8"))
        container_row = value["runtime_container"]
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        raise _runtime_attestation_invalid("anchored runtime manifest is invalid") from exc
    expected_container = {
        "device": container_info.st_dev,
        "gid": container_info.st_gid,
        "inode": container_info.st_ino,
        "mode": stat.S_IMODE(container_info.st_mode),
        "uid": container_info.st_uid,
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != _RUNTIME_MANIFEST_KEYS
        or payload != _canonical_bytes(dict(value)) + b"\n"
        or not isinstance(container_row, Mapping)
        or set(container_row) != _RUNTIME_CONTAINER_IDENTITY_KEYS
        or any(
            type(container_row.get(field)) is not int
            for field in _RUNTIME_CONTAINER_IDENTITY_KEYS
        )
        or dict(container_row) != expected_container
    ):
        raise _runtime_attestation_invalid("anchored runtime container identity drifted")
    return value


def _runtime_stat_fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _anchored_runtime_parent_descriptor(
    container_fd: int,
    relative_path: str,
) -> tuple[int, str]:
    """Open every parent below the held container without following links."""

    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise _runtime_attestation_invalid("anchored runtime path is invalid")
    descriptor = os.dup(container_fd)
    try:
        for part in relative.parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o222
            ):
                raise OSError("anchored runtime parent is unsafe")
        return descriptor, relative.parts[-1]
    except OSError as exc:
        os.close(descriptor)
        raise _runtime_attestation_invalid("anchored runtime parent is unavailable") from exc


def _anchored_runtime_file_digest(
    container_fd: int,
    *,
    relative_path: str,
    identity: Mapping[str, Any],
    expected_path: Path,
    expected_mode: int,
) -> str:
    """Hash one manifest-bound runtime file through the held container."""

    parent_fd = -1
    descriptor = -1
    try:
        parent_fd, leaf = _anchored_runtime_parent_descriptor(
            container_fd, relative_path
        )
        named_before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        descriptor = os.open(
            leaf,
            os.O_RDONLY | _runtime_open_flags("O_NOFOLLOW"),
            dir_fd=parent_fd,
        )
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        observed_size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_size += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise _runtime_attestation_invalid("anchored runtime file is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_fd >= 0:
            os.close(parent_fd)
    observed_digest = digest.hexdigest()
    if (
        not isinstance(identity, Mapping)
        or set(identity) != _RUNTIME_FILE_IDENTITY_KEYS
        or identity.get("path") != os.fspath(expected_path)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) != expected_mode
        or observed_size != before.st_size
        or _runtime_stat_fingerprint(named_before)
        != _runtime_stat_fingerprint(before)
        or _runtime_stat_fingerprint(before) != _runtime_stat_fingerprint(after)
        or _runtime_stat_fingerprint(before)
        != _runtime_stat_fingerprint(named_after)
        or dict(identity)
        != {
            "gid": before.st_gid,
            "mode": expected_mode,
            "path": os.fspath(expected_path),
            "sha256": observed_digest,
            "uid": before.st_uid,
        }
    ):
        raise _runtime_attestation_invalid("anchored runtime file identity drifted")
    return observed_digest


def _anchored_runtime_closure_inventory(
    container_fd: int,
) -> tuple[dict[str, Any], ...]:
    """Recompute the existing closure through one held runtime-container FD."""

    try:
        runtime_fd = os.open(
            "runtime",
            os.O_RDONLY | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
            dir_fd=container_fd,
        )
    except OSError as exc:
        raise _runtime_attestation_invalid("anchored runtime root is unavailable") from exc
    inventory: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(parent_fd: int, name: str, relative_path: str) -> None:
        if relative_path in seen or len(inventory) >= 50_000:
            raise _runtime_attestation_invalid("anchored runtime closure is unbounded")
        seen.add(relative_path)
        try:
            named_before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise _runtime_attestation_invalid(
                "anchored runtime closure entry is unavailable"
            ) from exc
        if named_before.st_uid != os.geteuid():
            raise _runtime_attestation_invalid("anchored runtime closure owner drifted")
        mode = stat.S_IMODE(named_before.st_mode)
        names: tuple[str, ...] = ()
        link = ""
        if stat.S_ISDIR(named_before.st_mode):
            descriptor = -1
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
                    dir_fd=parent_fd,
                )
                opened = os.fstat(descriptor)
                names = tuple(sorted(os.listdir(descriptor)))
                listed = os.fstat(descriptor)
                if (
                    mode != 0o500
                    or _runtime_stat_fingerprint(named_before)
                    != _runtime_stat_fingerprint(opened)
                    or _runtime_stat_fingerprint(opened)
                    != _runtime_stat_fingerprint(listed)
                ):
                    raise OSError("anchored runtime closure directory drifted")
                row = {
                    "gid": opened.st_gid,
                    "link": "",
                    "mode": mode,
                    "path": relative_path,
                    "sha256": hashlib.sha256(
                        _canonical_bytes(list(names))
                    ).hexdigest(),
                    "size": opened.st_size,
                    "type": "directory",
                    "uid": opened.st_uid,
                }
                inventory.append(row)
                for child in names:
                    visit(descriptor, child, f"{relative_path}/{child}")
                named_after = os.stat(
                    name, dir_fd=parent_fd, follow_symlinks=False
                )
                if _runtime_stat_fingerprint(named_before) != _runtime_stat_fingerprint(
                    named_after
                ):
                    raise OSError("anchored runtime closure directory was replaced")
            except OSError as exc:
                raise _runtime_attestation_invalid(
                    "anchored runtime closure directory is unstable"
                ) from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            return
        if stat.S_ISREG(named_before.st_mode):
            descriptor = -1
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | _runtime_open_flags("O_NOFOLLOW"),
                    dir_fd=parent_fd,
                )
                opened = os.fstat(descriptor)
                digest = hashlib.sha256()
                observed_size = 0
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    observed_size += len(chunk)
                    digest.update(chunk)
                read_after = os.fstat(descriptor)
                named_after = os.stat(
                    name, dir_fd=parent_fd, follow_symlinks=False
                )
            except OSError as exc:
                raise _runtime_attestation_invalid(
                    "anchored runtime closure file is unavailable"
                ) from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            if (
                opened.st_nlink != 1
                or mode not in {0o400, 0o500}
                or observed_size != opened.st_size
                or _runtime_stat_fingerprint(named_before)
                != _runtime_stat_fingerprint(opened)
                or _runtime_stat_fingerprint(opened)
                != _runtime_stat_fingerprint(read_after)
                or _runtime_stat_fingerprint(opened)
                != _runtime_stat_fingerprint(named_after)
            ):
                raise _runtime_attestation_invalid(
                    "anchored runtime closure file drifted"
                )
            inventory.append(
                {
                    "gid": opened.st_gid,
                    "link": "",
                    "mode": mode,
                    "path": relative_path,
                    "sha256": digest.hexdigest(),
                    "size": opened.st_size,
                    "type": "file",
                    "uid": opened.st_uid,
                }
            )
            return
        if stat.S_ISLNK(named_before.st_mode):
            try:
                link = os.readlink(name, dir_fd=parent_fd)
                named_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise _runtime_attestation_invalid(
                    "anchored runtime closure symlink is unavailable"
                ) from exc
            if (
                named_before.st_nlink != 1
                or not link
                or Path(link).is_absolute()
                or "\x00" in link
                or _runtime_stat_fingerprint(named_before)
                != _runtime_stat_fingerprint(named_after)
            ):
                raise _runtime_attestation_invalid(
                    "anchored runtime closure symlink drifted"
                )
            _runtime_closure_symlink_target(relative_path, link)
            inventory.append(
                {
                    "gid": named_before.st_gid,
                    "link": link,
                    "mode": mode,
                    "path": relative_path,
                    "sha256": hashlib.sha256(link.encode("utf-8")).hexdigest(),
                    "size": named_before.st_size,
                    "type": "symlink",
                    "uid": named_before.st_uid,
                }
            )
            return
        raise _runtime_attestation_invalid("anchored runtime closure contains a special file")

    try:
        runtime_info = os.fstat(runtime_fd)
        if (
            not stat.S_ISDIR(runtime_info.st_mode)
            or runtime_info.st_uid != os.geteuid()
            or stat.S_IMODE(runtime_info.st_mode) != 0o500
        ):
            raise _runtime_attestation_invalid("anchored runtime root identity drifted")
        for closure_root in _RUNTIME_CLOSURE_ROOTS:
            visit(runtime_fd, closure_root, closure_root)
        runtime_after = os.fstat(runtime_fd)
        runtime_named = os.stat(
            "runtime", dir_fd=container_fd, follow_symlinks=False
        )
        if (
            _runtime_stat_fingerprint(runtime_info)
            != _runtime_stat_fingerprint(runtime_after)
            or _runtime_stat_fingerprint(runtime_info)
            != _runtime_stat_fingerprint(runtime_named)
        ):
            raise _runtime_attestation_invalid("anchored runtime root was replaced")
    finally:
        os.close(runtime_fd)
    normalized = tuple(sorted(inventory, key=lambda row: str(row["path"])))
    for row in normalized:
        if row["type"] == "symlink":
            _runtime_closure_symlink_terminal(normalized, str(row["path"]))
    return normalized


def _attest_anchored_runtime_launch(
    container_fd: int,
    *,
    manifest: Mapping[str, Any],
    runtime_root: Path,
) -> None:
    """Re-attest direct executables and the existing closure before Popen."""

    raw_inventory = manifest.get("closure_inventory")
    closure_tree_digest = manifest.get("closure_tree_digest")
    if (
        manifest.get("schema_version") != RUNTIME_INSTALL_SCHEMA
        or manifest.get("runtime_root") != os.fspath(runtime_root)
        or not isinstance(raw_inventory, list)
        or not 1 <= len(raw_inventory) <= 50_000
        or _SHA256_RE.fullmatch(str(closure_tree_digest or "")) is None
    ):
        raise _runtime_attestation_invalid("anchored runtime launch manifest is invalid")
    normalized_inventory: list[dict[str, Any]] = []
    previous_path = ""
    for raw_entry in raw_inventory:
        if not isinstance(raw_entry, Mapping) or set(raw_entry) != _RUNTIME_CLOSURE_ENTRY_KEYS:
            raise _runtime_attestation_invalid("anchored runtime closure entry is not closed")
        path_value = raw_entry.get("path")
        if (
            not isinstance(path_value, str)
            or not path_value
            or Path(path_value).is_absolute()
            or ".." in Path(path_value).parts
            or path_value <= previous_path
            or raw_entry.get("type") not in {"directory", "file", "symlink"}
            or not isinstance(raw_entry.get("link"), str)
            or (raw_entry.get("type") == "symlink") != bool(raw_entry.get("link"))
            or _SHA256_RE.fullmatch(str(raw_entry.get("sha256") or "")) is None
            or any(
                type(raw_entry.get(field)) is not int or raw_entry[field] < 0
                for field in ("gid", "mode", "size", "uid")
            )
        ):
            raise _runtime_attestation_invalid("anchored runtime closure entry is invalid")
        previous_path = path_value
        normalized_inventory.append(dict(raw_entry))
    if runtime_closure_tree_digest(normalized_inventory) != closure_tree_digest:
        raise _runtime_attestation_invalid("anchored runtime closure tree digest drifted")
    _require_exact_node_library_closure(normalized_inventory)
    observed_inventory = _anchored_runtime_closure_inventory(container_fd)
    _require_exact_node_library_closure(observed_inventory)
    if tuple(normalized_inventory) != observed_inventory:
        raise _runtime_attestation_invalid("anchored runtime closure inventory drifted")

    node = manifest.get("node")
    mcp = manifest.get("mcp")
    browser = manifest.get("browser")
    expected_node = runtime_root / "bin" / "node"
    expected_mcp = runtime_root / "node_modules" / "@playwright" / "mcp" / "cli.js"
    if (
        not isinstance(node, Mapping)
        or set(node) != _RUNTIME_NODE_KEYS
        or not isinstance(mcp, Mapping)
        or set(mcp) != {"executable", "package", "package_lock", "version"}
        or mcp.get("package") != PLAYWRIGHT_MCP_PACKAGE
        or mcp.get("version") != PLAYWRIGHT_MCP_VERSION
        or not isinstance(browser, Mapping)
        or set(browser) != {"executable", "name", "revision"}
        or browser.get("name") != "chromium"
        or browser.get("revision") != "1237"
        or not isinstance(browser.get("executable"), Mapping)
    ):
        raise _runtime_attestation_invalid("anchored runtime executable identities are invalid")
    browser_path = Path(str(browser["executable"].get("path") or ""))
    try:
        browser_relative = browser_path.relative_to(runtime_root).as_posix()
        revision_relative = browser_path.relative_to(runtime_root / "browsers")
    except ValueError as exc:
        raise _runtime_attestation_invalid("anchored browser executable escaped") from exc
    if "chromium-1237" not in revision_relative.parts:
        raise _runtime_attestation_invalid("anchored browser revision path drifted")
    shadow_parent = -1
    try:
        shadow_parent, shadow_leaf = _anchored_runtime_parent_descriptor(
            container_fd,
            f"runtime/bin/{RUNTIME_NODE_LIBRARY_NAME}",
        )
        try:
            os.stat(shadow_leaf, dir_fd=shadow_parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise _runtime_attestation_invalid("node loader-path library shadow exists")
    finally:
        if shadow_parent >= 0:
            os.close(shadow_parent)
    _anchored_runtime_file_digest(
        container_fd,
        relative_path="runtime/bin/node",
        identity=node["executable"],
        expected_path=expected_node,
        expected_mode=0o500,
    )
    _anchored_runtime_file_digest(
        container_fd,
        relative_path="runtime/node_modules/@playwright/mcp/cli.js",
        identity=mcp["executable"],
        expected_path=expected_mcp,
        expected_mode=0o500,
    )
    _anchored_runtime_file_digest(
        container_fd,
        relative_path=f"runtime/{browser_relative}",
        identity=browser["executable"],
        expected_path=browser_path,
        expected_mode=0o500,
    )


def _seal_runtime_execution_parents(runtime_root: Path) -> None:
    """Make direct execution-bearing names non-replaceable after installation."""

    root = _private_runtime_root(runtime_root, expected_modes=frozenset({0o700}))
    container = _runtime_container(root, expected_mode=0o700)
    launcher_parent = root / "bin"
    library_root = root / "lib"
    artifact_root = container / "artifacts"
    try:
        parent_info = launcher_parent.lstat()
        library_info = library_root.lstat()
        artifact_info = artifact_root.lstat()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime launcher parent is unavailable") from exc
    if (
        stat.S_ISLNK(parent_info.st_mode)
        or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.geteuid()
        or stat.S_IMODE(parent_info.st_mode) != 0o700
        or stat.S_ISLNK(library_info.st_mode)
        or not stat.S_ISDIR(library_info.st_mode)
        or library_info.st_uid != os.geteuid()
        or stat.S_IMODE(library_info.st_mode) != 0o500
        or stat.S_ISLNK(artifact_info.st_mode)
        or not stat.S_ISDIR(artifact_info.st_mode)
        or artifact_info.st_uid != os.geteuid()
        or stat.S_IMODE(artifact_info.st_mode) != 0o700
    ):
        raise _runtime_attestation_invalid("runtime launcher parent is unsafe")
    try:
        os.chmod(launcher_parent, 0o500)
        os.chmod(root, 0o500)
        os.chmod(container, 0o500)
        sealed_root = root.lstat()
        sealed_parent = launcher_parent.lstat()
        sealed_library = library_root.lstat()
        sealed_container = container.lstat()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime execution parents could not be sealed") from exc
    if (
        stat.S_IMODE(sealed_root.st_mode) != 0o500
        or stat.S_IMODE(sealed_parent.st_mode) != 0o500
        or stat.S_IMODE(sealed_library.st_mode) != 0o500
        or stat.S_IMODE(sealed_container.st_mode) != 0o500
        or sealed_root.st_uid != os.geteuid()
        or sealed_parent.st_uid != os.geteuid()
        or sealed_library.st_uid != os.geteuid()
        or sealed_container.st_uid != os.geteuid()
    ):
        raise _runtime_attestation_invalid("runtime execution parent seal drifted")


def write_runtime_install_manifest(
    *,
    manifest_path: Path,
    runtime_root: Path,
    launcher: Path,
    node: Path,
    node_library: Path,
    mcp: Path,
    package_lock: Path,
    browser: Path,
    tmp_identity: tuple[int, int],
) -> str:
    """Normalize, close, and atomically persist the one v1 install receipt."""

    root = _private_runtime_root(runtime_root, expected_modes=frozenset({0o700}))
    container = _runtime_container(root, expected_mode=0o700)
    container_identity = _runtime_container_manifest_identity(
        container,
        expected_mode=0o700,
    )
    sealed_container_identity = {
        **container_identity,
        "mode": 0o500,
    }
    destination = Path(manifest_path)
    if destination != root / RUNTIME_INSTALL_MANIFEST_NAME:
        raise _runtime_attestation_invalid("runtime manifest destination drifted")
    if os.path.lexists(root / "bin" / RUNTIME_NODE_LIBRARY_NAME):
        raise _runtime_attestation_invalid("node loader-path library shadow exists")
    normalize_runtime_closure_for_install(root)
    cleanup_runtime_install_tmp(root, tmp_identity)
    if os.path.lexists(root / RUNTIME_TMP_INSTALL_NAME):
        raise _runtime_attestation_invalid("runtime install TMPDIR survived manifest seal")
    inventory = runtime_closure_inventory(root)
    _require_exact_node_library_closure(inventory)
    tree_digest = runtime_closure_tree_digest(inventory)
    launcher_identity = _runtime_manifest_file_identity(Path(launcher))
    node_identity = _runtime_manifest_file_identity(Path(node))
    node_library_identity = _runtime_manifest_file_identity(Path(node_library))
    mcp_identity = _runtime_manifest_file_identity(Path(mcp))
    lock_identity = _runtime_manifest_file_identity(Path(package_lock))
    browser_identity = _runtime_manifest_file_identity(Path(browser))
    if (
        launcher_identity["path"] != os.fspath(root / "bin" / RUNTIME_LAUNCHER_NAME)
        or launcher_identity["mode"] != 0o500
        or node_identity["path"] != os.fspath(root / "bin" / "node")
        or node_identity["mode"] != 0o500
        or node_library_identity["path"]
        != os.fspath(root / "lib" / RUNTIME_NODE_LIBRARY_NAME)
        or node_library_identity["mode"] != 0o400
        or mcp_identity["mode"] != 0o500
        or lock_identity["path"] != os.fspath(root / "package-lock.json")
        or lock_identity["mode"] != 0o400
        or browser_identity["mode"] != 0o500
    ):
        raise _runtime_attestation_invalid("runtime manifest identity mode or path drifted")
    value = {
        "browser": {
            "executable": browser_identity,
            "name": "chromium",
            "revision": "1237",
        },
        "closure_inventory": [dict(row) for row in inventory],
        "closure_tree_digest": tree_digest,
        "launcher": launcher_identity,
        "mcp": {
            "executable": mcp_identity,
            "package": PLAYWRIGHT_MCP_PACKAGE,
            "package_lock": lock_identity,
            "version": PLAYWRIGHT_MCP_VERSION,
        },
        "node": {
            "dynamic_library": node_library_identity,
            "executable": node_identity,
        },
        "runtime_container": sealed_container_identity,
        "runtime_root": os.fspath(root),
        "schema_version": RUNTIME_INSTALL_SCHEMA,
        "tmp_install_postcondition": "absent",
    }
    payload = _canonical_bytes(value) + b"\n"
    if not 1 <= len(payload) <= MAX_RUNTIME_INSTALL_MANIFEST_BYTES:
        raise _runtime_attestation_invalid("runtime install manifest exceeds its bound")
    if os.path.lexists(destination):
        existing = destination.lstat()
        if (
            stat.S_ISLNK(existing.st_mode)
            or not stat.S_ISREG(existing.st_mode)
            or existing.st_nlink != 1
            or existing.st_uid != os.geteuid()
            or stat.S_IMODE(existing.st_mode) != 0o400
        ):
            raise _runtime_attestation_invalid("existing runtime manifest is unsafe")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _runtime_open_flags("O_NOFOLLOW"),
            0o400,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o400)
        os.replace(temporary, destination)
        directory_descriptor = os.open(
            root,
            os.O_RDONLY
            | _runtime_open_flags("O_DIRECTORY", "O_NOFOLLOW"),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime manifest could not be persisted") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    digest = hashlib.sha256(payload).hexdigest()
    info, captured, observed = _stable_runtime_file(
        destination,
        capture=True,
        maximum_bytes=MAX_RUNTIME_INSTALL_MANIFEST_BYTES,
    )
    if (
        captured != payload
        or observed != digest
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o400
    ):
        raise _runtime_attestation_invalid("persisted runtime manifest drifted")
    _seal_runtime_execution_parents(root)
    if (
        _runtime_container_manifest_identity(container, expected_mode=0o500)
        != sealed_container_identity
    ):
        raise _runtime_attestation_invalid("sealed runtime container identity drifted")
    return digest


def _attested_runtime_file(
    value: Any,
    *,
    field: str,
    expected_path: Path | None = None,
    expected_mode: int | None = None,
    allowed_owners: frozenset[int] | None = None,
    executable: bool = False,
) -> tuple[Path, str]:
    if not isinstance(value, Mapping) or set(value) != _RUNTIME_FILE_IDENTITY_KEYS:
        raise _runtime_attestation_invalid(f"{field} identity is not closed")
    raw_path = value.get("path")
    digest = value.get("sha256")
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or not Path(raw_path).is_absolute()
        or _SHA256_RE.fullmatch(str(digest or "")) is None
        or any(type(value.get(key)) is not int for key in ("gid", "mode", "uid"))
    ):
        raise _runtime_attestation_invalid(f"{field} identity is invalid")
    candidate = Path(raw_path)
    if expected_path is not None and candidate != expected_path:
        raise _runtime_attestation_invalid(f"{field} path drifted")
    info, _payload, observed_digest = _stable_runtime_file(candidate)
    mode = stat.S_IMODE(info.st_mode)
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != value["uid"]
        or info.st_gid != value["gid"]
        or mode != value["mode"]
        or (expected_mode is not None and mode != expected_mode)
        or (allowed_owners is not None and info.st_uid not in allowed_owners)
        or (info.st_uid == os.geteuid() and mode & 0o222 != 0)
        or (executable and mode & 0o111 == 0)
    ):
        raise _runtime_attestation_invalid(f"{field} ownership or mode drifted")
    if observed_digest != digest:
        raise _runtime_attestation_invalid(f"{field} digest drifted")
    return candidate, observed_digest


def load_runtime_install_attestation(
    runtime_root: Path,
    *,
    manifest_path: Path | None = None,
    expected_manifest_digest: str,
) -> RuntimeInstallAttestation:
    """Verify the installer receipt without executing any runtime component."""

    root = _private_runtime_root(runtime_root, expected_modes=frozenset({0o500}))
    container = _runtime_container(root, expected_mode=0o500)
    observed_container_identity = _runtime_container_manifest_identity(
        container,
        expected_mode=0o500,
    )
    try:
        launcher_parent_info = (root / "bin").lstat()
        library_root_info = (root / "lib").lstat()
    except OSError as exc:
        raise _runtime_attestation_invalid("runtime execution parent is unavailable") from exc
    if (
        stat.S_ISLNK(launcher_parent_info.st_mode)
        or not stat.S_ISDIR(launcher_parent_info.st_mode)
        or launcher_parent_info.st_uid != os.geteuid()
        or stat.S_IMODE(launcher_parent_info.st_mode) != 0o500
        or stat.S_ISLNK(library_root_info.st_mode)
        or not stat.S_ISDIR(library_root_info.st_mode)
        or library_root_info.st_uid != os.geteuid()
        or stat.S_IMODE(library_root_info.st_mode) != 0o500
    ):
        raise _runtime_attestation_invalid("runtime execution parent seal drifted")
    if os.path.lexists(root / "bin" / RUNTIME_NODE_LIBRARY_NAME):
        raise _runtime_attestation_invalid("node loader-path library shadow exists")

    expected_manifest = root / RUNTIME_INSTALL_MANIFEST_NAME
    candidate_manifest = Path(manifest_path) if manifest_path is not None else expected_manifest
    if candidate_manifest != expected_manifest:
        raise _runtime_attestation_invalid("runtime manifest path drifted")
    if (
        _SHA256_RE.fullmatch(str(expected_manifest_digest or "")) is None
        or expected_manifest_digest == UNRATIFIED_RUNTIME_MANIFEST_DIGEST
    ):
        raise _runtime_attestation_invalid("runtime manifest is not ratified")
    manifest_info, captured_payload, observed_manifest_digest = _stable_runtime_file(
        candidate_manifest,
        capture=True,
        maximum_bytes=MAX_RUNTIME_INSTALL_MANIFEST_BYTES,
    )
    payload = captured_payload or b""
    if (
        not stat.S_ISREG(manifest_info.st_mode)
        or manifest_info.st_nlink != 1
        or manifest_info.st_uid != os.geteuid()
        or stat.S_IMODE(manifest_info.st_mode) != 0o400
        or manifest_info.st_size <= 0
    ):
        raise _runtime_attestation_invalid("runtime manifest ownership or mode drifted")
    if observed_manifest_digest != expected_manifest_digest:
        raise _runtime_attestation_invalid("runtime manifest digest drifted")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise _runtime_attestation_invalid("runtime manifest is not canonical JSON") from exc
    if (
        not isinstance(value, Mapping)
        or set(value) != _RUNTIME_MANIFEST_KEYS
        or value.get("schema_version") != RUNTIME_INSTALL_SCHEMA
        or value.get("runtime_root") != os.fspath(root)
        or not isinstance(value.get("runtime_container"), Mapping)
        or set(value["runtime_container"]) != _RUNTIME_CONTAINER_IDENTITY_KEYS
        or any(
            type(value["runtime_container"].get(field)) is not int
            for field in _RUNTIME_CONTAINER_IDENTITY_KEYS
        )
        or dict(value["runtime_container"]) != observed_container_identity
        or value.get("tmp_install_postcondition") != "absent"
        or os.path.lexists(root / RUNTIME_TMP_INSTALL_NAME)
        or payload != _canonical_bytes(value) + b"\n"
    ):
        raise _runtime_attestation_invalid("runtime manifest fields are not closed")

    raw_inventory = value.get("closure_inventory")
    closure_tree_digest = value.get("closure_tree_digest")
    if (
        not isinstance(raw_inventory, list)
        or not 1 <= len(raw_inventory) <= 50_000
        or _SHA256_RE.fullmatch(str(closure_tree_digest or "")) is None
    ):
        raise _runtime_attestation_invalid("runtime closure inventory is invalid")
    normalized_inventory: list[dict[str, Any]] = []
    previous_path = ""
    for raw_entry in raw_inventory:
        if not isinstance(raw_entry, Mapping) or set(raw_entry) != _RUNTIME_CLOSURE_ENTRY_KEYS:
            raise _runtime_attestation_invalid("runtime closure entry is not closed")
        path_value = raw_entry.get("path")
        kind = raw_entry.get("type")
        link = raw_entry.get("link")
        digest = raw_entry.get("sha256")
        if (
            not isinstance(path_value, str)
            or not path_value
            or Path(path_value).is_absolute()
            or ".." in Path(path_value).parts
            or path_value <= previous_path
            or kind not in {"directory", "file", "symlink"}
            or not isinstance(link, str)
            or (kind == "symlink") != bool(link)
            or _SHA256_RE.fullmatch(str(digest or "")) is None
            or any(
                type(raw_entry.get(field)) is not int or raw_entry[field] < 0
                for field in ("gid", "mode", "size", "uid")
            )
        ):
            raise _runtime_attestation_invalid("runtime closure entry is invalid")
        previous_path = path_value
        normalized_inventory.append(dict(raw_entry))
    if runtime_closure_tree_digest(normalized_inventory) != closure_tree_digest:
        raise _runtime_attestation_invalid("runtime closure tree digest drifted")
    _require_exact_node_library_closure(normalized_inventory)
    observed_inventory = runtime_closure_inventory(root)
    _require_exact_node_library_closure(observed_inventory)
    if tuple(normalized_inventory) != observed_inventory:
        raise _runtime_attestation_invalid("runtime closure inventory drifted")

    launcher, launcher_digest = _attested_runtime_file(
        value.get("launcher"),
        field="launcher",
        expected_path=root / "bin" / RUNTIME_LAUNCHER_NAME,
        expected_mode=0o500,
        allowed_owners=frozenset({os.geteuid()}),
        executable=True,
    )
    node = value.get("node")
    if not isinstance(node, Mapping) or set(node) != _RUNTIME_NODE_KEYS:
        raise _runtime_attestation_invalid("node identity is not closed")
    node_executable, node_digest = _attested_runtime_file(
        node.get("executable"),
        field="node",
        expected_path=root / "bin" / "node",
        expected_mode=0o500,
        allowed_owners=frozenset({os.geteuid()}),
        executable=True,
    )
    node_library, node_library_digest = _attested_runtime_file(
        node.get("dynamic_library"),
        field="node dynamic library",
        expected_path=root / "lib" / RUNTIME_NODE_LIBRARY_NAME,
        expected_mode=0o400,
        allowed_owners=frozenset({os.geteuid()}),
    )
    mcp = value.get("mcp")
    if (
        not isinstance(mcp, Mapping)
        or set(mcp) != {"executable", "package", "package_lock", "version"}
        or mcp.get("package") != PLAYWRIGHT_MCP_PACKAGE
        or mcp.get("version") != PLAYWRIGHT_MCP_VERSION
    ):
        raise _runtime_attestation_invalid("Playwright MCP identity is not closed")
    mcp_executable, mcp_digest = _attested_runtime_file(
        mcp.get("executable"),
        field="Playwright MCP executable",
        expected_mode=0o500,
        allowed_owners=frozenset({os.geteuid()}),
        executable=True,
    )
    try:
        mcp_relative = mcp_executable.relative_to(root).as_posix()
        if (
            not mcp_relative.startswith("node_modules/")
            or _runtime_closure_symlink_terminal(
                observed_inventory,
                "node_modules/.bin/playwright-mcp",
            )
            != mcp_relative
        ):
            raise ValueError("MCP entrypoint target drifted")
    except ValueError as exc:
        raise _runtime_attestation_invalid("Playwright MCP executable path drifted") from exc
    _package_lock, package_lock_digest = _attested_runtime_file(
        mcp.get("package_lock"),
        field="Playwright package lock",
        expected_path=root / "package-lock.json",
        expected_mode=0o400,
        allowed_owners=frozenset({os.geteuid()}),
    )

    browser = value.get("browser")
    if (
        not isinstance(browser, Mapping)
        or set(browser) != {"executable", "name", "revision"}
        or browser.get("name") != "chromium"
        or browser.get("revision") != "1237"
    ):
        raise _runtime_attestation_invalid("Chromium identity is not closed")
    browser_executable, browser_digest = _attested_runtime_file(
        browser.get("executable"),
        field="Chromium executable",
        expected_mode=0o500,
        allowed_owners=frozenset({os.geteuid()}),
        executable=True,
    )
    try:
        relative_browser = browser_executable.relative_to(root / "browsers")
    except ValueError as exc:
        raise _runtime_attestation_invalid("Chromium executable escaped its runtime") from exc
    if "chromium-1237" not in relative_browser.parts:
        raise _runtime_attestation_invalid("Chromium revision path drifted")

    return RuntimeInstallAttestation(
        runtime_root=root,
        runtime_container_device=observed_container_identity["device"],
        runtime_container_inode=observed_container_identity["inode"],
        runtime_container_uid=observed_container_identity["uid"],
        runtime_container_gid=observed_container_identity["gid"],
        runtime_container_mode=observed_container_identity["mode"],
        manifest_path=candidate_manifest,
        manifest_digest=observed_manifest_digest,
        launcher_path=launcher,
        launcher_sha256=launcher_digest,
        node_path=node_executable,
        node_sha256=node_digest,
        node_library_path=node_library,
        node_library_sha256=node_library_digest,
        mcp_executable=mcp_executable,
        mcp_executable_sha256=mcp_digest,
        package_lock_sha256=package_lock_digest,
        closure_tree_digest=closure_tree_digest,
        closure_entry_count=len(observed_inventory),
        browser_executable=browser_executable,
        browser_executable_sha256=browser_digest,
        browser_revision="1237",
    )


def _tracked_workspace_snapshot(workspace: Path) -> dict[str, str]:
    env = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    try:
        head = subprocess.run(
            ["git", "-C", os.fspath(workspace), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            env=env,
            timeout=10,
        ).stdout.strip().decode("ascii")
        status = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(workspace),
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
            ],
            check=True,
            capture_output=True,
            env=env,
            timeout=10,
        ).stdout
        working = subprocess.run(
            ["git", "-C", os.fspath(workspace), "diff", "--binary", "HEAD", "--"],
            check=True,
            capture_output=True,
            env=env,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise BrowserReviewError(
            "BROWSER_WORKSPACE_MUTATION", "tracked workspace identity is not observable"
        ) from exc
    return {
        "head": head,
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "diff_sha256": hashlib.sha256(working).hexdigest(),
    }


def _validate_workspace_identity(workspace: Path, identity: WorkspaceIdentity) -> Path:
    try:
        root = Path(workspace).resolve(strict=True)
        expected = Path(identity.workspace_path).resolve(strict=True)
        observed = root.stat()
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_WORKSPACE_MUTATION", "workspace identity is unavailable"
        ) from exc
    if (
        root != expected
        or root.is_symlink()
        or not root.is_dir()
        or observed.st_dev != identity.device
        or observed.st_ino != identity.inode
        or observed.st_uid != identity.uid
        or observed.st_gid != identity.gid
    ):
        raise BrowserReviewError(
            "BROWSER_WORKSPACE_MUTATION", "workspace identity differs from the Attempt"
        )
    snapshot = _tracked_workspace_snapshot(root)
    if snapshot["head"] != identity.base_sha:
        raise BrowserReviewError(
            "BROWSER_WORKSPACE_MUTATION", "workspace HEAD differs from the Attempt"
        )
    return root


def _generation_artifact_dir(root: Path, generation_id: str) -> Path:
    token = hashlib.sha256(generation_id.encode("utf-8")).hexdigest()[:32]
    return Path(root) / f"generation-{token}"


def resolve_pinned_chromium_executable(
    runtime_root: Path, *, expected_manifest_digest: str
) -> Path:
    """Resolve Chromium only through the non-executing installer receipt."""

    return load_runtime_install_attestation(
        runtime_root, expected_manifest_digest=expected_manifest_digest
    ).browser_executable


class BrowserGenerationResource:
    """One devserver/proxy resource subordinate to an existing OHF generation."""

    _LSOF_CANDIDATES = (Path("/usr/sbin/lsof"), Path("/usr/bin/lsof"))

    def __init__(
        self,
        *,
        workspace: Path,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        profile: Any,
    ) -> None:
        if (
            len(getattr(profile, "resource_grants", ())) != 1
            or len(
                [
                    grant
                    for grant in getattr(profile, "mcp_server_grants", ())
                    if getattr(grant, "capability_id", "")
                    == "playwright-worker-browser-b1"
                ]
            )
            != 1
        ):
            raise BrowserReviewError(
                "DEVSERVER_MANIFEST_INVALID", "browser profile resource composition is not exact"
            )
        self.workspace = Path(workspace)
        self.requested = requested
        self.epoch = epoch
        self.generation = generation
        self.profile = profile
        self.resource_grant = profile.resource_grants[0]
        self.mcp_grant = next(
            grant
            for grant in profile.mcp_server_grants
            if grant.capability_id == "playwright-worker-browser-b1"
        )
        self.attempt_id = epoch.attempt_id
        self.session_epoch_id = epoch.session_epoch_id
        self.process_generation_id = generation.process_generation_id
        self.network_state = "loopback-browser-only"
        self.observed_capability = ObservedCapabilityIdentity(
            kind="resource",
            name=self.resource_grant.resource_id,
            resource_contract_digest=self.resource_grant.grant_digest,
        )
        self._environment: dict[str, str] | None = None
        self._artifact_dir = _generation_artifact_dir(
            Path(self.resource_grant.artifact_root), self.process_generation_id
        )
        self._artifact_dir_identity: tuple[int, ...] | None = None
        self._manifest: DevserverManifest | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._process_group: int | None = None
        self._process_log: Any = None
        self._proxy: LoopbackEnforcingProxy | None = None
        self._proxy_receipt: dict[str, Any] | None = None
        self._visual_fixture: _AttemptVisualFixture | None = None
        self._visual_judgment: dict[str, Any] | None = None
        self._browser_executable: Path | None = None
        self._browser_executable_digest: str | None = None
        self._runtime_attestation: RuntimeInstallAttestation | None = None
        self._workspace_before: dict[str, str] | None = None
        self._workspace_after: dict[str, str] | None = None
        self._stopped = False

    @property
    def environment(self) -> Mapping[str, str]:
        if self._environment is None:
            raise BrowserReviewError(
                "BROWSER_MCP_START_FAILED", "browser resource is not ready"
            )
        return dict(self._environment)

    def _require_artifact_root_descriptor(self, descriptor: int) -> os.stat_result:
        try:
            held = os.fstat(descriptor)
            named = self._artifact_dir.lstat()
        except OSError as exc:
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", "Attempt artifact root is unavailable"
            ) from exc
        if (
            self._artifact_dir_identity is None
            or not stat.S_ISDIR(held.st_mode)
            or held.st_uid != os.geteuid()
            or stat.S_IMODE(held.st_mode) != 0o700
            or BrowserMcpToolGuard._directory_identity(held)
            != self._artifact_dir_identity
            or BrowserMcpToolGuard._directory_identity(named)
            != self._artifact_dir_identity
        ):
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", "Attempt artifact root identity changed"
            )
        return held

    def _open_artifact_root_descriptor(self) -> int:
        descriptor = -1
        try:
            descriptor = os.open(
                self._artifact_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            self._require_artifact_root_descriptor(descriptor)
            return descriptor
        except (OSError, BrowserReviewError):
            if descriptor >= 0:
                os.close(descriptor)
            raise

    def _candidate_ports(self) -> tuple[int, ...]:
        span = 65535 - 49152 - 16
        seed = int(
            hashlib.sha256(
                f"{self.attempt_id}\x00{self.resource_grant.resource_id}".encode()
            ).hexdigest()[:8],
            16,
        )
        start = 49152 + (seed % span)
        return tuple(start + offset for offset in range(16))

    @staticmethod
    def _port_available(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                return False
            return True

    @classmethod
    def _trusted_lsof_path(cls) -> Path:
        """Resolve lsof from the closed root-owned host locations we support."""

        for candidate in cls._LSOF_CANDIDATES:
            try:
                observed = candidate.lstat()
            except OSError:
                continue
            if (
                stat.S_ISREG(observed.st_mode)
                and observed.st_uid == 0
                and stat.S_IMODE(observed.st_mode) & 0o022 == 0
                and stat.S_IMODE(observed.st_mode) & 0o111 != 0
                and os.access(candidate, os.X_OK)
            ):
                return candidate
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED",
            "trusted lsof executable is unavailable",
        )

    @classmethod
    def _listener_owned_by_group(
        cls,
        port: int,
        process_group: int,
        *,
        lsof_path: Path | None = None,
    ) -> bool:
        """Bind the accepted listener to the launched private process group."""

        executable = lsof_path or cls._trusted_lsof_path()
        try:
            completed = subprocess.run(
                [
                    os.fspath(executable),
                    "-nP",
                    f"-iTCP:{port}",
                    "-sTCP:LISTEN",
                    "-t",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
                env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            )
        except (OSError, subprocess.SubprocessError):
            return False
        pids: list[int] = []
        for line in completed.stdout.splitlines():
            try:
                pid = int(line.strip())
            except ValueError:
                return False
            if pid <= 0:
                return False
            pids.append(pid)
        if not pids:
            return False
        try:
            return all(os.getpgid(pid) == process_group for pid in pids)
        except (OSError, ProcessLookupError):
            return False

    @classmethod
    def _readiness(
        cls,
        origin: str,
        *,
        timeout_seconds: int,
        process: subprocess.Popen[bytes],
        process_group: int,
        lsof_path: Path,
    ) -> bool:
        parsed = urlsplit(origin)
        assert parsed.port is not None
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            connection = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=2)
            try:
                connection.request("GET", "/")
                response = connection.getresponse()
                body = response.read(MAX_TEXT_EVIDENCE_BYTES + 1)
                if (
                    response.status == 200
                    and len(body) <= MAX_TEXT_EVIDENCE_BYTES
                    and b"<title>Chairman Control Room</title>" in body
                    and cls._listener_owned_by_group(
                        parsed.port,
                        process_group,
                        lsof_path=lsof_path,
                    )
                ):
                    return True
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(0.1)
        return False

    def start(self) -> None:
        if self._environment is not None:
            raise BrowserReviewError(
                "BROWSER_MCP_START_FAILED", "browser resource already started"
            )
        root = _validate_workspace_identity(self.workspace, self.requested.workspace)
        manifest_path = root / self.resource_grant.manifest_path
        manifest = load_devserver_manifest(manifest_path, root)
        if manifest.digest != self.resource_grant.manifest_digest:
            raise BrowserReviewError(
                "DEVSERVER_MANIFEST_INVALID", "devserver manifest digest drifted"
            )
        runtime_root = Path(self.resource_grant.runtime_root)
        attestation = load_runtime_install_attestation(
            runtime_root,
            manifest_path=Path(self.resource_grant.runtime_manifest_path),
            expected_manifest_digest=self.resource_grant.runtime_manifest_digest,
        )
        if (
            self.resource_grant.browser != "chromium"
            or self.resource_grant.browser_revision != attestation.browser_revision
            or self.mcp_grant.command != WORKER_BROWSER_MCP_COMMAND
            or tuple(self.mcp_grant.args) != WORKER_BROWSER_MCP_ARGS
        ):
            raise BrowserReviewError(
                "BROWSER_RUNTIME_ATTESTATION_INVALID",
                "runtime receipt does not match the reviewed capability grant",
            )
        lsof_path = self._trusted_lsof_path()
        executable = attestation.browser_executable
        _secure_directory(Path(self.resource_grant.artifact_root))
        try:
            self._artifact_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise BrowserReviewError(
                "BROWSER_ORPHAN_PROCESS_UNCERTAIN",
                "generation artifact directory already exists",
            ) from exc
        _secure_directory(self._artifact_dir)
        self._artifact_dir_identity = BrowserMcpToolGuard._directory_identity(
            self._artifact_dir.lstat()
        )
        private_home = self._artifact_dir / "home"
        _secure_directory(private_home)
        self._workspace_before = _tracked_workspace_snapshot(root)
        self._manifest = manifest
        self._browser_executable = executable
        self._browser_executable_digest = attestation.browser_executable_sha256
        self._runtime_attestation = attestation
        log_path = self._artifact_dir / "devserver.log"
        log_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        log_descriptor = os.open(log_path, log_flags, 0o600)
        self._process_log = os.fdopen(log_descriptor, "ab", buffering=0)
        last_failure = "DEVSERVER_PORT_EXHAUSTED"
        for port in self._candidate_ports():
            if not self._port_available(port):
                continue
            origin = f"http://127.0.0.1:{port}"
            env = {
                "HOME": os.fspath(private_home),
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONPATH": os.fspath(root),
                "TMPDIR": os.fspath(self._artifact_dir),
            }
            process: subprocess.Popen[bytes] | None = None
            try:
                process = subprocess.Popen(
                    manifest.argv_for_port(port),
                    cwd=root,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=self._process_log,
                    stderr=self._process_log,
                    shell=False,
                    start_new_session=True,
                )
                pgid = os.getpgid(process.pid)
            except OSError:
                if process is not None:
                    try:
                        os.kill(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=_CLEANUP_GRACE_SECONDS)
                    except subprocess.TimeoutExpired:
                        pass
                last_failure = "DEVSERVER_START_FAILED"
                continue
            if self._readiness(
                origin,
                timeout_seconds=manifest.readiness_timeout_seconds,
                process=process,
                process_group=pgid,
                lsof_path=lsof_path,
            ):
                self._process = process
                self._process_group = pgid
                fixture = _AttemptVisualFixture.create(origin)
                proxy = LoopbackEnforcingProxy(
                    origin, fixture_routes=fixture.routes
                )
                proxy.start()
                self._proxy = proxy
                self._visual_fixture = fixture
                fixture_a_url, fixture_b_url = fixture.model_urls(origin)
                self._environment = {
                    "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(self._artifact_dir),
                    "MASTERMIND_BROWSER_FIXTURE_A_URL": fixture_a_url,
                    "MASTERMIND_BROWSER_FIXTURE_B_URL": fixture_b_url,
                    "MASTERMIND_BROWSER_FIXTURE_NONCE": fixture.nonce,
                    "MASTERMIND_BROWSER_ORIGIN": origin,
                    "MASTERMIND_BROWSER_PROXY_URL": proxy.proxy_url,
                    "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(
                        attestation.manifest_path
                    ),
                    "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": (
                        attestation.manifest_digest
                    ),
                    "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(runtime_root),
                    "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(root),
                    "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
                }
                return
            last_failure = "DEVSERVER_READINESS_TIMEOUT"
            if not _finish_process_group(process, pgid):
                self._process = process
                self._process_group = pgid
                raise BrowserReviewError(
                    "BROWSER_ORPHAN_PROCESS_UNCERTAIN",
                    "timed-out devserver process group survived cleanup",
                )
        self.stop()
        raise BrowserReviewError(last_failure, "reviewed Control Room resource did not become ready")

    def stop(self) -> None:
        errors: list[str] = []
        if self._proxy is not None:
            try:
                self._proxy.stop()
                self._proxy_receipt = self._proxy.receipt()
            except BrowserReviewError:
                errors.append("proxy")
            self._proxy = None
        if self._process is not None and self._process_group is not None:
            if not _finish_process_group(self._process, self._process_group):
                errors.append("devserver")
        self._process = None
        self._process_group = None
        if self._process_log is not None:
            self._process_log.close()
            self._process_log = None
        if self._workspace_before is not None:
            self._workspace_after = _tracked_workspace_snapshot(
                Path(self.requested.workspace.workspace_path)
            )
        self._stopped = not errors
        if errors:
            raise BrowserReviewError(
                "BROWSER_ORPHAN_PROCESS_UNCERTAIN", "browser resource cleanup is not proven"
            )

    def turn_prompt_suffix(self) -> str:
        """Return the exact model-visible visual proof contract, never its truth."""

        if self._environment is None or self._visual_fixture is None:
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN", "visual fixture is not ready"
            )
        return (
            "\n\nBROWSER REVIEW RECEIPT CONTRACT (Executive-owned): use only the "
            "playwright-worker-browser-b1 MCP. Inspect the local product at "
            f"{self._environment['MASTERMIND_BROWSER_ORIGIN']}/. First take a "
            "structured snapshot and perform exactly one harmless browser_hover "
            "on the product Theme button using its exact snapshot target and "
            "reference. Then inspect the product at 1440x900 and 390x844, "
            "capturing desktop.png and mobile.png. Then inspect both "
            "opaque pixel fixtures at 900x600 and capture visual-a.png from "
            f"{self._environment['MASTERMIND_BROWSER_FIXTURE_A_URL']} and "
            "visual-b.png from "
            f"{self._environment['MASTERMIND_BROWSER_FIXTURE_B_URL']}. The two "
            "fixtures have intentionally identical text/accessibility semantics; "
            "judge pixels only. Attempt file:///etc/passwd once and confirm the "
            "guard refuses it. Capture bounded console and network evidence. Set "
            "the ordinary result current_state field to the canonical JSON string "
            "with exactly: schema_version=mastermind.browser_visual_judgment/v1, "
            f"fixture_nonce={self._visual_fixture.nonce}, defective_variant=A or B, "
            "a concise nonempty reason, and source=model_image_content. Do not "
            "claim any egress, cleanup, receipt, or security gate; the Executive "
            "derives those facts after provider shutdown."
        )

    def observe_canonical_result(self, canonical_result_json: str) -> None:
        """Bind one exact model pixel judgment from the private raw-result seam."""

        if self._visual_fixture is None or self._visual_judgment is not None:
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN", "visual judgment state is not fresh"
            )
        try:
            outer = json.loads(canonical_result_json)
            state_text = outer["current_state"]
            judgment = json.loads(state_text)
        except (KeyError, TypeError, ValueError) as exc:
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN",
                "canonical result lacks the closed pixel judgment",
            ) from exc
        expected_keys = {
            "defective_variant",
            "fixture_nonce",
            "reason",
            "schema_version",
            "source",
        }
        if (
            not isinstance(outer, Mapping)
            or not isinstance(state_text, str)
            or not isinstance(judgment, Mapping)
            or set(judgment) != expected_keys
            or _canonical_bytes(dict(judgment)).decode("utf-8") != state_text
            or judgment.get("schema_version")
            != "mastermind.browser_visual_judgment/v1"
            or judgment.get("fixture_nonce") != self._visual_fixture.nonce
            or judgment.get("defective_variant") not in {"A", "B"}
            or judgment.get("source") != "model_image_content"
            or not isinstance(judgment.get("reason"), str)
            or not judgment["reason"].strip()
            or judgment["reason"] != judgment["reason"].strip()
            or len(judgment["reason"].encode("utf-8")) > 512
        ):
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN", "model pixel judgment is not closed"
            )
        self._visual_judgment = dict(judgment)

    def _attempt_evidence(
        self, root_fd: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        evidence_fd = -1
        try:
            root_before = self._require_artifact_root_descriptor(root_fd)
            named_before = os.stat(
                _MCP_GUARD_EVIDENCE_FILE,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
            evidence_fd = os.open(
                _MCP_GUARD_EVIDENCE_FILE,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_fd,
            )
            info = os.fstat(evidence_fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size <= 0
                or info.st_size > MAX_TEXT_EVIDENCE_BYTES
                or BrowserMcpToolGuard._stat_fingerprint(named_before)
                != BrowserMcpToolGuard._stat_fingerprint(info)
            ):
                raise OSError("unsafe evidence")
            chunks: list[bytes] = []
            observed_bytes = 0
            while True:
                chunk = os.read(
                    evidence_fd,
                    min(
                        1024 * 1024,
                        MAX_TEXT_EVIDENCE_BYTES + 1 - observed_bytes,
                    ),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                observed_bytes += len(chunk)
                if observed_bytes > MAX_TEXT_EVIDENCE_BYTES:
                    raise OSError("evidence exceeds reviewed bound")
            raw = b"".join(chunks)
            info_after = os.fstat(evidence_fd)
            named_after = os.stat(
                _MCP_GUARD_EVIDENCE_FILE,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
            root_after = os.fstat(root_fd)
            self._require_artifact_root_descriptor(root_fd)
            if (
                len(raw) != info.st_size
                or BrowserMcpToolGuard._stat_fingerprint(info)
                != BrowserMcpToolGuard._stat_fingerprint(info_after)
                or BrowserMcpToolGuard._stat_fingerprint(info)
                != BrowserMcpToolGuard._stat_fingerprint(named_after)
                or BrowserMcpToolGuard._stat_fingerprint(root_before)
                != BrowserMcpToolGuard._stat_fingerprint(root_after)
                or BrowserMcpToolGuard._directory_identity(root_after)
                != self._artifact_dir_identity
            ):
                raise OSError("evidence changed during read")
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN", "closed MCP guard evidence is unavailable"
            ) from exc
        finally:
            if evidence_fd >= 0:
                os.close(evidence_fd)
        expected = {
            "bridge_exit_code",
            "calls",
            "cleanup_proven",
            "console_rows",
            "egress_falsifiers",
            "image_content_sha256",
            "interaction",
            "model_image_content_sha256",
            "network_rows",
            "schema_version",
            "screenshots",
        }
        if (
            not isinstance(value, dict)
            or set(value) != expected
            or value.get("schema_version") != _MCP_GUARD_EVIDENCE_SCHEMA
            or value.get("bridge_exit_code") != 0
            or value.get("cleanup_proven") is not True
            or not isinstance(value.get("calls"), Mapping)
            or not isinstance(value.get("console_rows"), list)
            or not isinstance(value.get("network_rows"), list)
            or value.get("screenshots")
            != ["desktop.png", "mobile.png", "visual-a.png", "visual-b.png"]
            or not isinstance(value.get("image_content_sha256"), Mapping)
            or set(value["image_content_sha256"])
            != {"desktop.png", "mobile.png", "visual-a.png", "visual-b.png"}
            or not isinstance(value.get("model_image_content_sha256"), Mapping)
            or set(value["model_image_content_sha256"])
            != {"desktop.png", "mobile.png", "visual-a.png", "visual-b.png"}
            or not isinstance(value.get("egress_falsifiers"), Mapping)
            or not isinstance(value.get("interaction"), Mapping)
        ):
            raise BrowserReviewError(
                "BROWSER_RECEIPT_INVALID", "MCP guard evidence fields are not closed"
            )
        for digest in value["image_content_sha256"].values():
            _require_sha256(digest, field="MCP guard image content")
        for digest in value["model_image_content_sha256"].values():
            _require_sha256(digest, field="MCP guard model image content")
        value["calls"] = _closed_mcp_guard_observations(
            value["calls"],
            console_rows=value["console_rows"],
            interaction=value["interaction"],
            network_rows=value["network_rows"],
        )
        summary = {
            "relative_path": _MCP_GUARD_EVIDENCE_FILE,
            "schema_version": _MCP_GUARD_EVIDENCE_SCHEMA,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        return value, summary

    def seal_after_uid_sweep(self, sweep: Any) -> BrowserReviewReceipt:
        root_fd = self._open_artifact_root_descriptor()
        try:
            return self._seal_after_uid_sweep_bound(sweep, root_fd)
        finally:
            os.close(root_fd)

    def _seal_after_uid_sweep_bound(
        self, sweep: Any, root_fd: int
    ) -> BrowserReviewReceipt:
        from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing

        if (
            not self._stopped
            or self._workspace_before is None
            or self._workspace_after != self._workspace_before
            or getattr(sweep, "reason", None) != "operator_terminal"
            or getattr(sweep, "worker_uid", None) != os.geteuid()
            or not uid_sweep_receipt_is_passing(sweep.to_dict())
            or self._manifest is None
            or self._browser_executable is None
            or self._browser_executable_digest is None
            or self._runtime_attestation is None
            or self._environment is None
            or self._proxy_receipt is None
            or self._visual_fixture is None
            or self._visual_judgment is None
        ):
            raise BrowserReviewError(
                "BROWSER_ORPHAN_PROCESS_UNCERTAIN", "post-generation cleanup is not exact"
            )
        evidence, mcp_guard = self._attempt_evidence(root_fd)
        seal_attestation = load_runtime_install_attestation(
            Path(self.resource_grant.runtime_root),
            manifest_path=Path(self.resource_grant.runtime_manifest_path),
            expected_manifest_digest=self.resource_grant.runtime_manifest_digest,
        )
        if seal_attestation != self._runtime_attestation:
            raise BrowserReviewError(
                "BROWSER_RUNTIME_ATTESTATION_INVALID",
                "runtime identity changed before receipt seal",
            )
        screenshots = [
            _screenshot_artifact_at(
                root_fd, "desktop.png", viewport=_DESKTOP
            ),
            _screenshot_artifact_at(
                root_fd, "mobile.png", viewport=_MOBILE
            ),
            _screenshot_artifact_at(
                root_fd,
                "visual-a.png",
                viewport=BrowserMcpToolGuard._VISUAL_VIEWPORT,
            ),
            _screenshot_artifact_at(
                root_fd,
                "visual-b.png",
                viewport=BrowserMcpToolGuard._VISUAL_VIEWPORT,
            ),
        ]
        observed_images = evidence["image_content_sha256"]
        model_images = evidence["model_image_content_sha256"]
        if any(
            observed_images[row["relative_path"]] != row["sha256"]
            for row in screenshots
        ):
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN",
                "guard image content does not match the sealed PNG artifacts",
            )
        expected_defective = self._visual_fixture.defective_variant
        if self._visual_judgment["defective_variant"] != expected_defective:
            raise BrowserReviewError(
                "BROWSER_VISUAL_CAPABILITY_UNPROVEN",
                "model did not identify the hidden pixel-only defect",
            )
        proxy_refused = self._proxy_receipt.get("refused")
        guard_egress = evidence["egress_falsifiers"]
        proxy_keys = _REQUIRED_EGRESS_FALSIFIERS - {"file_url", "proxy_override"}
        if (
            self._proxy_receipt.get("external_egress_observed") is not False
            or not isinstance(proxy_refused, Mapping)
            or any(type(proxy_refused.get(key)) is not int or proxy_refused[key] < 1 for key in proxy_keys)
            or guard_egress.get("file_url") != "REFUSED"
            or guard_egress.get("proxy_override") != "REFUSED"
        ):
            raise BrowserReviewError(
                "BROWSER_NETWORK_CONFINEMENT_UNPROVEN",
                "hostile egress observations are incomplete",
            )
        egress_falsifiers = {key: "REFUSED" for key in proxy_keys}
        egress_falsifiers.update({"file_url": "REFUSED", "proxy_override": "REFUSED"})
        visual_judgment = {
            "defective_variant": expected_defective,
            "fixture_nonce": self._visual_fixture.nonce,
            "image_sha256": [
                model_images["visual-a.png"],
                model_images["visual-b.png"],
            ],
            "reason": self._visual_judgment["reason"],
            "source": "model_image_content",
        }
        sweep_digest = _canonical_digest(sweep.to_dict())
        context = BrowserAttemptContext(
            attempt_id=self.attempt_id,
            session_epoch_id=self.session_epoch_id,
            process_generation_id=self.process_generation_id,
            workspace=self.requested.workspace,
            artifact_dir=self._artifact_dir,
            devserver_manifest_digest=self._manifest.digest,
            capability_manifest_digest=_canonical_digest(asdict(self.requested.capabilities)),
            browser_profile_id=self.profile.profile_id,
            browser_profile_digest=self.profile.profile_digest,
            playwright_mcp_identity=self.mcp_grant.server_identity,
            playwright_mcp_version=self.mcp_grant.server_version,
            playwright_tool_schema_digest=self.mcp_grant.tool_schema_digest,
            runtime_manifest_digest=self._runtime_attestation.manifest_digest,
            browser_revision=self._runtime_attestation.browser_revision,
            browser_executable=os.fspath(self._browser_executable),
            browser_executable_sha256=self._browser_executable_digest,
        )
        receipt = seal_browser_review_receipt(
            context,
            local_origin=self._environment["MASTERMIND_BROWSER_ORIGIN"],
            mcp_guard=mcp_guard,
            screenshots=screenshots,
            console_rows=evidence["console_rows"],
            network_rows=evidence["network_rows"],
            egress_falsifiers=egress_falsifiers,
            visual_judgment=visual_judgment,
            cleanup={
                "browser_absent": True,
                "devserver_absent": True,
                "mcp_absent": True,
                "proxy_absent": True,
                "uid_sweep_digest": sweep_digest,
                "uid_sweep_passed": True,
            },
            tracked_workspace_changes_after_review=False,
        )
        _write_private_receipt_at(root_fd, receipt)
        self._require_artifact_root_descriptor(root_fd)
        return receipt


def _write_private_receipt_at(
    directory_fd: int, receipt: BrowserReviewReceipt
) -> None:
    _write_private_bytes_once_at(
        directory_fd,
        _RECEIPT_FILE,
        _canonical_bytes(receipt.to_wire()) + b"\n",
    )


def load_persisted_browser_review_receipt(
    generation: ProcessGenerationRef,
    *,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> BrowserReviewReceipt | None:
    root_path = Path(artifact_root)
    generation_name = _generation_artifact_dir(
        Path(), generation.process_generation_id
    ).name
    root_fd = -1
    generation_fd = -1
    receipt_fd = -1
    try:
        root_fd = os.open(
            root_path,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        root_before = os.fstat(root_fd)
        root_named_before = root_path.lstat()
        if (
            not stat.S_ISDIR(root_before.st_mode)
            or root_before.st_uid != os.geteuid()
            or stat.S_IMODE(root_before.st_mode) != 0o700
            or BrowserMcpToolGuard._directory_identity(root_before)
            != BrowserMcpToolGuard._directory_identity(root_named_before)
        ):
            raise OSError("unsafe artifact root")

        generation_named_before = os.stat(
            generation_name, dir_fd=root_fd, follow_symlinks=False
        )
        generation_fd = os.open(
            generation_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_fd,
        )
        generation_before = os.fstat(generation_fd)
        if (
            not stat.S_ISDIR(generation_before.st_mode)
            or generation_before.st_uid != os.geteuid()
            or stat.S_IMODE(generation_before.st_mode) != 0o700
            or BrowserMcpToolGuard._stat_fingerprint(generation_before)
            != BrowserMcpToolGuard._stat_fingerprint(generation_named_before)
        ):
            raise OSError("unsafe generation artifact directory")

        named_before = os.stat(
            _RECEIPT_FILE, dir_fd=generation_fd, follow_symlinks=False
        )
        receipt_fd = os.open(
            _RECEIPT_FILE,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=generation_fd,
        )
        info = os.fstat(receipt_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size <= 0
            or info.st_size > MAX_TEXT_EVIDENCE_BYTES
            or BrowserMcpToolGuard._stat_fingerprint(info)
            != BrowserMcpToolGuard._stat_fingerprint(named_before)
        ):
            raise OSError("unsafe receipt")

        chunks: list[bytes] = []
        observed_bytes = 0
        while True:
            chunk = os.read(
                receipt_fd,
                min(
                    1024 * 1024,
                    MAX_TEXT_EVIDENCE_BYTES + 1 - observed_bytes,
                ),
            )
            if not chunk:
                break
            chunks.append(chunk)
            observed_bytes += len(chunk)
            if observed_bytes > MAX_TEXT_EVIDENCE_BYTES:
                raise OSError("persisted receipt exceeds reviewed bound")
        raw = b"".join(chunks)

        info_after = os.fstat(receipt_fd)
        named_after = os.stat(
            _RECEIPT_FILE, dir_fd=generation_fd, follow_symlinks=False
        )
        generation_after = os.fstat(generation_fd)
        generation_named_after = os.stat(
            generation_name, dir_fd=root_fd, follow_symlinks=False
        )
        root_after = os.fstat(root_fd)
        root_named_after = root_path.lstat()
        if (
            len(raw) != info.st_size
            or BrowserMcpToolGuard._stat_fingerprint(info)
            != BrowserMcpToolGuard._stat_fingerprint(info_after)
            or BrowserMcpToolGuard._stat_fingerprint(info)
            != BrowserMcpToolGuard._stat_fingerprint(named_after)
            or BrowserMcpToolGuard._stat_fingerprint(generation_before)
            != BrowserMcpToolGuard._stat_fingerprint(generation_after)
            or BrowserMcpToolGuard._stat_fingerprint(generation_before)
            != BrowserMcpToolGuard._stat_fingerprint(generation_named_after)
            or BrowserMcpToolGuard._stat_fingerprint(root_before)
            != BrowserMcpToolGuard._stat_fingerprint(root_after)
            or BrowserMcpToolGuard._directory_identity(root_before)
            != BrowserMcpToolGuard._directory_identity(root_named_after)
        ):
            raise OSError("persisted receipt changed during read")
        value = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        if receipt_fd < 0:
            return None
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "persisted browser receipt is unsafe"
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "persisted browser receipt is unsafe"
        ) from exc
    finally:
        if receipt_fd >= 0:
            os.close(receipt_fd)
        if generation_fd >= 0:
            os.close(generation_fd)
        if root_fd >= 0:
            os.close(root_fd)
    receipt = browser_review_receipt(value)
    if receipt.process_generation_id != generation.process_generation_id:
        raise BrowserReviewError(
            "BROWSER_RECEIPT_INVALID", "persisted browser receipt generation drifted"
        )
    return receipt


def launch_mcp_from_attempt_env(
    environment: Mapping[str, str] | None = None,
    *,
    bridge_runner: Any = run_guarded_mcp_bridge,
) -> int:
    """Fixed guarded stdio launcher; caller can supply no authority arguments."""

    values = dict(os.environ if environment is None else environment)
    if any(key not in values or not values[key] for key in _BROWSER_LAUNCH_ENV_KEYS):
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "attempt-local browser environment is incomplete"
        )
    artifact_dir = Path(values["MASTERMIND_BROWSER_ARTIFACT_DIR"])
    runtime_root = Path(values["MASTERMIND_BROWSER_RUNTIME_ROOT"])
    runtime_manifest = Path(values["MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH"])
    runtime_manifest_digest = values["MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256"]
    workspace = Path(values["MASTERMIND_BROWSER_WORKSPACE_PATH"])
    try:
        artifact = artifact_dir.resolve(strict=True)
        artifact_info = artifact.lstat()
        container_fd = int(values[_RUNTIME_CONTAINER_FD_ENV])
        if not os.get_inheritable(container_fd):
            raise OSError("runtime container descriptor is not inheritable")
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "attempt-local browser paths are unavailable"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "attempt-local runtime descriptor is invalid"
        ) from exc
    if (
        artifact_dir.is_symlink()
        or not artifact.is_dir()
        or artifact_info.st_uid != os.geteuid()
        or stat.S_IMODE(artifact_info.st_mode) != 0o700
        or not runtime_root.is_absolute()
        or runtime_root.name != "runtime"
        or runtime_manifest != runtime_root / RUNTIME_INSTALL_MANIFEST_NAME
        or values["PLAYWRIGHT_BROWSERS_PATH"] != "runtime/browsers"
    ):
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "attempt-local browser paths are not exact"
        )
    origin = values["MASTERMIND_BROWSER_ORIGIN"]
    proxy_url = values["MASTERMIND_BROWSER_PROXY_URL"]
    _validate_origin(origin)
    _validate_origin(proxy_url)
    try:
        resolved_workspace = workspace.resolve(strict=True)
    except OSError as exc:
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "Attempt workspace is unavailable"
        ) from exc
    if resolved_workspace != Path.cwd().resolve(strict=True):
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "Attempt workspace binding drifted"
        )
    anchored_manifest = _anchored_runtime_manifest(
        container_fd,
        expected_manifest_digest=runtime_manifest_digest,
    )
    expected_node = runtime_root / "bin" / "node"
    expected_mcp = (
        runtime_root / "node_modules" / "@playwright" / "mcp" / "cli.js"
    )
    if (
        anchored_manifest.get("runtime_root") != os.fspath(runtime_root)
        or not isinstance(anchored_manifest.get("node"), Mapping)
        or not isinstance(anchored_manifest["node"].get("executable"), Mapping)
        or anchored_manifest["node"]["executable"].get("path")
        != os.fspath(expected_node)
        or not isinstance(anchored_manifest.get("mcp"), Mapping)
        or not isinstance(anchored_manifest["mcp"].get("executable"), Mapping)
        or anchored_manifest["mcp"]["executable"].get("path")
        != os.fspath(expected_mcp)
    ):
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED",
            "anchored runtime executable identity drifted",
        )
    _attest_anchored_runtime_launch(
        container_fd,
        manifest=anchored_manifest,
        runtime_root=runtime_root,
    )
    private_home = artifact / "home"
    _secure_directory(private_home)
    config = BrowserRunConfig(
        origin=origin,
        repo_root=resolved_workspace,
        runtime_root=runtime_root,
        command_override=(
            WORKER_BROWSER_MCP_COMMAND,
            "-I",
            "-S",
            "-c",
            _ANCHORED_NODE_BOOTSTRAP,
        ),
    )
    argv = build_mcp_argv(config, artifact, proxy_url=proxy_url)
    if tuple(argv[:5]) != (
        WORKER_BROWSER_MCP_COMMAND,
        "-I",
        "-S",
        "-c",
        _ANCHORED_NODE_BOOTSTRAP,
    ):
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED",
            "anchored Playwright MCP launch envelope drifted",
        )
    safe_env = {
        "HOME": os.fspath(private_home),
        "LANG": "C",
        "LC_ALL": "C",
        _RUNTIME_CONTAINER_FD_ENV: str(container_fd),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": runtime_manifest_digest,
        "NO_COLOR": "1",
        "PATH": "/usr/bin:/bin",
        "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
        "TMPDIR": os.fspath(artifact),
    }
    nonce = values["MASTERMIND_BROWSER_FIXTURE_NONCE"]
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "visual fixture nonce is not opaque and exact"
        )
    guard = BrowserMcpToolGuard(
        origin=origin,
        artifact_dir=artifact,
        fixture_urls={
            "A": values["MASTERMIND_BROWSER_FIXTURE_A_URL"],
            "B": values["MASTERMIND_BROWSER_FIXTURE_B_URL"],
        },
    )
    return int(
        bridge_runner(
            argv=argv,
            environment=safe_env,
            guard=guard,
            pass_fds=(container_fd,),
        )
    )


def _secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    current = path.lstat()
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
        raise BrowserReviewError("ARTIFACT_ROOT_REFUSED", "artifact root is not a real directory")
    path.chmod(0o700)
    current = path.lstat()
    if not stat.S_ISDIR(current.st_mode) or current.st_uid != os.getuid():
        raise BrowserReviewError("ARTIFACT_ROOT_REFUSED", "artifact root is not an owned directory")
    if stat.S_IMODE(current.st_mode) != 0o700:
        raise BrowserReviewError("ARTIFACT_ROOT_REFUSED", "artifact root mode is not 0700")


def _process_group_absent(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _finish_process_group(process: subprocess.Popen[bytes], pgid: int) -> bool:
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass
    if process.poll() is None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=_CLEANUP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=_CLEANUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return False

    deadline = time.monotonic() + _CLEANUP_PROOF_SECONDS
    while not _process_group_absent(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def main(argv: Sequence[str] | None = None) -> int:
    values = tuple(argv if argv is not None else os.sys.argv[1:])
    if values != ("launch-mcp-from-attempt-env",):
        raise SystemExit(
            "usage: worker-browser-b1-launcher"
        )
    return launch_mcp_from_attempt_env()


if __name__ == "__main__":
    raise SystemExit(main())

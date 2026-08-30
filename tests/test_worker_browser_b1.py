"""Worker Browser B1: one isolated official-Playwright-MCP review vertical."""
from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import stat
import struct
import subprocess
import sys
import textwrap
import threading
import zlib
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import worker_browser_b1 as browser
from control_plane import executive_agent_capabilities as capabilities
from control_plane.executive_worker_broker import UIDSweepReceipt, UID_SWEEP_SCHEMA_VERSION
from control_plane.operator_harness_contract import (
    CapabilityManifest,
    ProcessGenerationRef,
    SessionEpochRef,
    WorkspaceIdentity,
)


def _png(width: int, height: int, *, color: bytes = b"\x00\x00\x00\xff") -> bytes:
    """Build a small, fully decodable RGBA PNG for receipt boundary tests."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    scanline = b"\x00" + (color * width)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
        )
        + chunk(b"IDAT", zlib.compress(scanline * height))
        + chunk(b"IEND", b"")
    )


def _config(tmp_path: Path, **overrides) -> browser.BrowserRunConfig:
    command_override = overrides.pop("command_override", None)
    values = {
        "origin": "http://127.0.0.1:8787",
        "repo_root": tmp_path,
        "runtime_root": tmp_path / "runtime",
        "artifact_root": tmp_path / "artifacts",
        "command_override": command_override,
    }
    values.update(overrides)
    return browser.BrowserRunConfig(**values)


def _fixture_urls(origin: str) -> dict[str, str]:
    return {
        "A": f"{origin}/__mastermind_browser_visual_fixture__/{'a' * 32}",
        "B": f"{origin}/__mastermind_browser_visual_fixture__/{'b' * 32}",
    }


def _record_guard_text_success(
    guard: browser.BrowserMcpToolGuard,
    name: str,
    arguments: dict,
    *,
    text: str = "ok",
) -> None:
    guard.record_result(
        name,
        arguments,
        {"result": {"content": [{"type": "text", "text": text}]}},
    )


def _guard_navigate(guard: browser.BrowserMcpToolGuard, url: str) -> None:
    arguments = {"url": url}
    guard.rewrite_call("browser_navigate", arguments)
    _record_guard_text_success(guard, "browser_navigate", arguments)


def test_listener_owner_uses_closed_usr_bin_lsof_fallback(tmp_path, monkeypatch):
    missing = tmp_path / "usr-sbin-lsof"
    fallback = tmp_path / "usr-bin-lsof"
    fallback.write_text("trusted fixture", encoding="utf-8")
    fallback.chmod(0o755)
    real_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == missing:
            raise FileNotFoundError(path)
        if path == fallback:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o755, st_uid=0)
        return real_lstat(path)

    observed: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        observed.append(list(argv))
        return SimpleNamespace(stdout=f"{os.getpid()}\n")

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(
        browser.BrowserGenerationResource,
        "_LSOF_CANDIDATES",
        (missing, fallback),
        raising=False,
    )
    monkeypatch.setattr(browser.subprocess, "run", fake_run)

    assert browser.BrowserGenerationResource._listener_owned_by_group(
        48101, os.getpgid(os.getpid())
    )
    assert observed == [
        [os.fspath(fallback), "-nP", "-iTCP:48101", "-sTCP:LISTEN", "-t"]
    ]


def test_listener_owner_refuses_without_closed_trusted_lsof(tmp_path, monkeypatch):
    symlink = tmp_path / "lsof-link"
    target = tmp_path / "lsof-target"
    target.write_text("fixture", encoding="utf-8")
    symlink.symlink_to(target)
    writable = tmp_path / "lsof-writable"
    writable.write_text("fixture", encoding="utf-8")
    non_executable = tmp_path / "lsof-non-executable"
    non_executable.write_text("fixture", encoding="utf-8")
    inaccessible = tmp_path / "lsof-inaccessible"
    inaccessible.write_text("fixture", encoding="utf-8")
    real_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == symlink:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0)
        if path == writable:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o777, st_uid=0)
        if path == non_executable:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0)
        if path == inaccessible:
            # The attested metadata claims execute bits, but the current worker
            # cannot execute this path. Both predicates are required.
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o755, st_uid=0)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(
        browser.BrowserGenerationResource,
        "_LSOF_CANDIDATES",
        (symlink, writable, non_executable, inaccessible),
        raising=False,
    )

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.BrowserGenerationResource._trusted_lsof_path()

    assert raised.value.state == "BROWSER_MCP_START_FAILED"


def test_generation_start_refuses_untrusted_lsof_before_artifact_or_process(
    tmp_path, monkeypatch
):
    artifact_root = tmp_path / "artifacts"
    resource_grant = SimpleNamespace(
        resource_id="worker-browser-b1-local",
        manifest_path="config/worker_browser_b1_control_room_devserver.json",
        manifest_digest="a" * 64,
        runtime_root=os.fspath(tmp_path / "runtime"),
        runtime_manifest_path=os.fspath(tmp_path / "runtime-manifest.json"),
        runtime_manifest_digest="b" * 64,
        artifact_root=os.fspath(artifact_root),
        browser="chromium",
        browser_revision="1237",
        grant_digest="c" * 64,
    )
    mcp_grant = SimpleNamespace(
        capability_id="playwright-worker-browser-b1",
        command=capabilities.WORKER_BROWSER_MCP_COMMAND,
        args=capabilities.WORKER_BROWSER_MCP_ARGS,
    )
    profile = SimpleNamespace(
        resource_grants=(resource_grant,),
        mcp_server_grants=(mcp_grant,),
    )
    requested = SimpleNamespace(workspace=SimpleNamespace())
    resource = browser.BrowserGenerationResource(
        workspace=tmp_path,
        requested=requested,
        epoch=SessionEpochRef("epoch-lsof", "attempt-lsof", "worker-a", 1),
        generation=ProcessGenerationRef(
            "generation-lsof", "epoch-lsof", 1, "worker-a"
        ),
        profile=profile,
    )
    monkeypatch.setattr(
        browser,
        "_validate_workspace_identity",
        lambda *_args, **_kwargs: tmp_path,
    )
    monkeypatch.setattr(
        browser,
        "load_devserver_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(digest=resource_grant.manifest_digest),
    )
    monkeypatch.setattr(
        browser,
        "load_runtime_install_attestation",
        lambda *_args, **_kwargs: SimpleNamespace(
            browser_revision="1237",
            browser_executable=tmp_path / "chromium",
            browser_executable_sha256="d" * 64,
        ),
    )

    def refuse_lsof(_self):
        raise browser.BrowserReviewError(
            "BROWSER_MCP_START_FAILED", "trusted lsof executable is unavailable"
        )

    monkeypatch.setattr(browser.BrowserGenerationResource, "_trusted_lsof_path", refuse_lsof)
    monkeypatch.setattr(
        browser,
        "_secure_directory",
        lambda *_args, **_kwargs: pytest.fail("artifact directory mutation occurred"),
    )
    monkeypatch.setattr(
        browser.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("devserver process launch occurred"),
    )

    with pytest.raises(browser.BrowserReviewError) as raised:
        resource.start()

    assert raised.value.state == "BROWSER_MCP_START_FAILED"
    assert not artifact_root.exists()


def _guard_resize(
    guard: browser.BrowserMcpToolGuard, *, width: int, height: int
) -> None:
    arguments = {"width": width, "height": height}
    guard.rewrite_call("browser_resize", arguments)
    _record_guard_text_success(guard, "browser_resize", arguments)


def _runtime_install_fixture(
    tmp_path: Path,
    *,
    node_payload: bytes = b"fixture node executable",
) -> tuple[Path, Path, dict[str, object]]:
    runtime_container = tmp_path / "worker-browser-b1"
    runtime_container.mkdir(mode=0o700)
    (runtime_container / "artifacts").mkdir(mode=0o700)
    runtime = runtime_container / "runtime"
    runtime.mkdir(mode=0o700)
    (runtime / "bin").mkdir(mode=0o700)
    (runtime / "lib").mkdir(mode=0o700)
    (runtime / "browsers" / "chromium-1237").mkdir(parents=True)
    (runtime / "node_modules" / "@playwright" / "mcp").mkdir(parents=True)

    launcher = runtime / "bin" / "worker-browser-b1-launcher"
    manifest_path = runtime / "worker-browser-b1-install-manifest.json"
    installer = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install_worker_browser_b1_runtime.sh"
    ).read_text(encoding="utf-8")
    launcher_generator = installer.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    subprocess.run(
        [sys.executable, "-", os.fspath(launcher), os.fspath(manifest_path)],
        input=launcher_generator,
        text=True,
        check=True,
    )
    node = runtime / "bin" / "node"
    node.write_bytes(node_payload)
    node.chmod(0o500)
    node_library = runtime / "lib" / "libnode.147.dylib"
    node_library.write_bytes(b"fixture node dynamic library")
    node_library.chmod(0o400)
    mcp = runtime / "node_modules" / "@playwright" / "mcp" / "cli.js"
    mcp.write_bytes(b"fixture locked playwright mcp")
    mcp.chmod(0o500)
    mcp_link = runtime / "node_modules" / ".bin" / "playwright-mcp"
    mcp_link.parent.mkdir()
    mcp_link.symlink_to(Path("../@playwright/mcp/cli.js"))
    package_lock = runtime / "package-lock.json"
    package_lock.write_bytes(b'{"lockfileVersion":3}\n')
    package_lock.chmod(0o400)
    chromium = runtime / "browsers" / "chromium-1237" / "Chromium"
    chromium.write_bytes(b"fixture locked chromium")
    chromium.chmod(0o500)

    _add_loaded_runtime_closure(runtime)
    browser.normalize_runtime_closure_for_install(runtime)
    closure_inventory = browser.runtime_closure_inventory(runtime)

    def identity(path: Path) -> dict[str, object]:
        info = path.stat()
        return {
            "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode),
            "path": os.fspath(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "uid": info.st_uid,
        }

    manifest: dict[str, object] = {
        "browser": {
            "executable": identity(chromium),
            "name": "chromium",
            "revision": "1237",
        },
        "closure_inventory": [dict(row) for row in closure_inventory],
        "closure_tree_digest": browser.runtime_closure_tree_digest(closure_inventory),
        "launcher": identity(launcher),
        "mcp": {
            "executable": identity(mcp),
            "package": "@playwright/mcp",
            "package_lock": identity(package_lock),
            "version": "0.0.79",
        },
        "node": {
            "dynamic_library": identity(node_library),
            "executable": identity(node),
        },
        "runtime_container": {
            "device": runtime_container.stat().st_dev,
            "gid": runtime_container.stat().st_gid,
            "inode": runtime_container.stat().st_ino,
            "mode": 0o500,
            "uid": runtime_container.stat().st_uid,
        },
        "runtime_root": os.fspath(runtime.resolve()),
        "schema_version": "mastermind.worker_browser_runtime_install/v1",
        "tmp_install_postcondition": "absent",
    }
    manifest_path.write_bytes(browser._canonical_bytes(manifest) + b"\n")
    manifest_path.chmod(0o400)
    (runtime / "bin").chmod(0o500)
    runtime.chmod(0o500)
    runtime_container.chmod(0o500)
    return runtime, manifest_path, manifest


def _attempt_launch_environment(
    *,
    workspace: Path,
    artifact: Path,
    runtime: Path,
    runtime_manifest: Path,
    container_fd: int | None = None,
) -> dict[str, str]:
    environment = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(artifact),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": (
            "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/"
            + "a" * 32
        ),
        "MASTERMIND_BROWSER_FIXTURE_B_URL": (
            "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/"
            + "b" * 32
        ),
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:48101",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:48102",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(runtime_manifest),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": hashlib.sha256(
            runtime_manifest.read_bytes()
        ).hexdigest(),
        "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(runtime),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(workspace),
        "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
    }
    if container_fd is not None:
        environment["MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"] = str(container_fd)
    return environment


def _add_loaded_runtime_closure(runtime: Path) -> dict[str, Path]:
    """Populate non-entrypoint bytes that the real MCP/browser process loads."""

    paths = {
        "mcp_core_bundle": runtime
        / "node_modules"
        / "@playwright"
        / "mcp"
        / "lib"
        / "coreBundle.js",
        "mcp_other": runtime
        / "node_modules"
        / "@playwright"
        / "mcp"
        / "lib"
        / "transport.js",
        "playwright": runtime / "node_modules" / "playwright" / "index.js",
        "utils_bundle": runtime
        / "node_modules"
        / "playwright-core"
        / "lib"
        / "utilsBundle.js",
        "playwright_core_other": runtime
        / "node_modules"
        / "playwright-core"
        / "lib"
        / "server"
        / "browserType.js",
        "chromium_framework": runtime
        / "browsers"
        / "chromium-1237"
        / "Chromium.app"
        / "Contents"
        / "Frameworks"
        / "Chromium Framework.framework"
        / "Versions"
        / "A"
        / "Chromium Framework",
        "chromium_helper": runtime
        / "browsers"
        / "chromium-1237"
        / "Chromium.app"
        / "Contents"
        / "Frameworks"
        / "Chromium Helper.app"
        / "Contents"
        / "MacOS"
        / "Chromium Helper",
        "headless_shell": runtime
        / "browsers"
        / "chromium_headless_shell-1237"
        / "chrome-headless-shell-mac-arm64"
        / "chrome-headless-shell",
        "ffmpeg": runtime / "browsers" / "ffmpeg-1011" / "ffmpeg-mac-arm64",
    }
    for label, path in paths.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"fixture closure byte {label}\n".encode("ascii"))
            path.chmod(
                0o500
                if label.startswith("chromium_")
                or label in {"headless_shell", "ffmpeg"}
                else 0o400
            )
    framework_root = paths["chromium_framework"].parents[2]
    current_version = framework_root / "Versions" / "Current"
    exposed_binary = framework_root / "Chromium Framework"
    if not os.path.lexists(current_version):
        current_version.symlink_to("A", target_is_directory=True)
    if not os.path.lexists(exposed_binary):
        exposed_binary.symlink_to("Versions/Current/Chromium Framework")
    return paths


def test_build_mcp_argv_is_exact_pinned_isolated_and_has_no_identity_import(tmp_path):
    config = _config(tmp_path, command_override=None)

    argv = browser.build_mcp_argv(config, tmp_path / "output")

    assert argv == [
        os.fspath(tmp_path / "runtime" / "node_modules" / ".bin" / "playwright-mcp"),
        "--isolated",
        "--headless",
        "--browser",
        "chromium",
        "--sandbox",
        "--block-service-workers",
        "--image-responses",
        "allow",
        "--allowed-origins",
        "http://127.0.0.1:8787",
        "--output-dir",
        os.fspath(tmp_path / "output"),
    ]
    joined = " ".join(argv)
    for forbidden in ("--storage-state", "--user-data-dir", "--extension", "--secrets", "--grant-permissions"):
        assert forbidden not in joined
    assert browser.PLAYWRIGHT_MCP_PACKAGE == "@playwright/mcp"
    assert browser.PLAYWRIGHT_MCP_VERSION == "0.0.79"


def test_tool_surface_contains_required_review_interactions_but_no_unsafe_code_or_upload():
    assert browser.ALLOWED_TOOLS == {
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
    assert browser.ALLOWED_TOOLS.isdisjoint(
        {
            "browser_evaluate",
            "browser_file_upload",
            "browser_run_code_unsafe",
            "browser_type",
        }
    )


def test_zero_length_screenshot_is_refused_before_receipt(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "desktop.png").write_bytes(b"")

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.screenshot_artifact(
            output_dir, "desktop.png", viewport={"width": 1440, "height": 900}
        )

    assert raised.value.state == "BROWSER_ARTIFACT_OVERSIZE"
    assert raised.value.detail == "screenshot artifact is outside the reviewed bound"


def test_oversized_screenshot_is_refused_before_reading_bytes(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    screenshot = output_dir / "desktop.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")
    with screenshot.open("r+b") as artifact:
        artifact.truncate(12 * 1024 * 1024)

    original_read_bytes = Path.read_bytes
    read_attempts = 0

    def fail_if_oversized_is_read(path):
        nonlocal read_attempts
        if path.resolve() == screenshot.resolve():
            read_attempts += 1
            raise AssertionError("oversized screenshot bytes were read")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_if_oversized_is_read)

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.screenshot_artifact(
            output_dir, "desktop.png", viewport={"width": 1440, "height": 900}
        )

    assert raised.value.state == "BROWSER_ARTIFACT_OVERSIZE"
    assert raised.value.detail == "screenshot artifact is outside the reviewed bound"
    assert read_attempts == 0
    assert browser.MAX_SCREENSHOT_BYTES > 202_184


def test_screenshot_refuses_png_signature_without_decodable_image(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "desktop.png").write_bytes(
        b"\x89PNG\r\n\x1a\nnot-a-decoded-image"
    )

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.screenshot_artifact(
            output_dir, "desktop.png", viewport={"width": 1440, "height": 900}
        )

    assert raised.value.state == "BROWSER_SCREENSHOT_FAILED"


def test_screenshot_refuses_decodable_png_with_wrong_viewport_dimensions(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "desktop.png").write_bytes(_png(390, 844))

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.screenshot_artifact(
            output_dir, "desktop.png", viewport={"width": 1440, "height": 900}
        )

    assert raised.value.state == "BROWSER_SCREENSHOT_FAILED"
    assert raised.value.detail == "screenshot dimensions do not match the bound viewport"


def test_chairman_process_cannot_own_the_retired_direct_browser_lifecycle():
    for forbidden in (
        "BrowserReviewCoordinator",
        "_JsonLineMcpClient",
        "run_browser_review",
    ):
        assert not hasattr(browser, forbidden)


def test_only_fixed_loopback_origin_is_accepted(tmp_path):
    for origin in (
        "https://mastermind-x.com",
        "http://localhost:8787",
        "http://127.0.0.1",
        "http://127.0.0.1:8787/path",
        "http://127.0.0.1:8787?query=1",
    ):
        with pytest.raises(ValueError, match="exact loopback origin"):
            browser._validate_origin(origin)


def test_caller_cannot_supply_url_command_profile_or_other_input(tmp_path):
    assert browser.validate_request({}) is None
    for body in (
        {"url": "https://example.com"},
        {"command": ["sh"]},
        {"profile": "/Users/chriswong/Library/Application Support/Google/Chrome"},
        {"storage_state": "cookies.json"},
    ):
        with pytest.raises(ValueError, match="unknown key"):
            browser.validate_request(body)


def test_package_manifest_and_lock_pin_exact_release():
    root = Path(__file__).resolve().parents[1] / "integrations" / "worker_browser_runtime"
    manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    assert manifest["private"] is True
    assert manifest["dependencies"] == {"@playwright/mcp": "0.0.79"}
    assert lock["packages"][""]["dependencies"] == {"@playwright/mcp": "0.0.79"}
    assert lock["packages"]["node_modules/@playwright/mcp"]["version"] == "0.0.79"
    assert lock["packages"]["node_modules/@playwright/mcp"]["integrity"] == (
        "sha512-VpqD4a3vFyGQMY9sh3UJiO6wjcurggkljKfAyCHL0QWGY5m6Ehr3MNsAAHPDHO//"
        "n13g0PCjpHatAOiulrqdZQ=="
    )


def test_installer_provisions_only_the_locked_chromium_revision_at_install_time():
    installer = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install_worker_browser_b1_runtime.sh"
    ).read_text(encoding="utf-8")

    assert 'PLAYWRIGHT_BROWSERS_PATH="$runtime_root/browsers"' in installer
    assert '"$node_executable" "$runtime_root/node_modules/playwright/cli.js" install chromium' in installer
    assert '"$node_executable" "$runtime_root/node_modules/@playwright/mcp/cli.js" --version' in installer
    assert '"$node_executable" "$npm_cli" ci' in installer
    assert "command -v node" not in installer
    assert "node_modules/.bin/playwright\" install" not in installer
    assert "node_modules/.bin/playwright-mcp --version" not in installer
    assert "\n  npm ci" not in installer
    assert '"$browser_root"/chromium-1237/*' in installer
    assert 'shasum -a 256 "$browser_executable"' in installer
    assert 'worker-browser-b1-launcher' in installer
    assert 'worker-browser-b1-install-manifest.json' in installer
    assert "exec /usr/bin/env -i" in installer
    assert 'runpy.run_module("control_plane.worker_browser_b1"' in installer
    assert installer.index("exec /usr/bin/env -i") < installer.index(
        'runpy.run_module("control_plane.worker_browser_b1"'
    )
    assert 'chmod 0400 "$runtime_root/package-lock.json"' in installer
    assert "install firefox" not in installer
    assert "install webkit" not in installer


def test_installer_uses_trusted_node_then_seals_copied_runtime_before_execution():
    installer = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install_worker_browser_b1_runtime.sh"
    ).read_text(encoding="utf-8")

    assert "validate_node_macho_pair()" in installer
    assert "validate_node_macho_dependency_closure" in installer
    assert (
        'validate_node_macho_pair "$node_executable" "$node_library_source"'
        in installer
    )
    assert (
        'validate_node_macho_pair "$runtime_root/bin/node" "$node_library"'
        in installer
    )
    assert '@rpath/libnode.147.dylib' in installer
    assert '"$runtime_root/lib/libnode.147.dylib"' in installer
    assert '/usr/bin/install -m 0400 "$node_library_source"' in installer
    assert '/usr/bin/cmp -s "$node_library_source" "$node_library"' in installer
    assert 'refusing loader-path Node dynamic library shadow' in installer
    assert 'node_executable="$runtime_root/bin/node"' not in installer
    assert "load_runtime_install_attestation" in installer
    external_install_execution = installer.index(
        '"$node_executable" "$npm_cli" ci'
    )
    launcher_start = installer.index(
        'launcher="$runtime_root/bin/worker-browser-b1-launcher"'
    )
    launcher_complete = installer.index("\nPY\n\nmcp_executable=")
    node_copy = installer.index(
        '/usr/bin/install -m 0500 "$node_executable" "$runtime_root/bin/node"'
    )
    library_copy = installer.index(
        '/usr/bin/install -m 0400 "$node_library_source"'
    )
    manifest_seal = installer.index("write_runtime_install_manifest(")
    trap_clear = installer.index("trap - EXIT", manifest_seal)
    copied_pair_post_seal = installer.index(
        'validate_node_macho_pair "$runtime_root/bin/node" "$node_library"'
    )
    post_seal_attestation = installer.index(
        "load_runtime_install_attestation(", manifest_seal
    )
    assert external_install_execution < launcher_start < launcher_complete
    assert launcher_complete < node_copy < library_copy < manifest_seal
    assert manifest_seal < trap_clear < copied_pair_post_seal < post_seal_attestation


def test_node_macho_parser_accepts_only_exact_relative_and_trusted_host_closure():
    node_dependencies = """/opt/homebrew/Cellar/node/26.5.0/bin/node:
\t@rpath/libnode.147.dylib (compatibility version 0.0.0, current version 0.0.0)
\t/opt/homebrew/opt/libuv/lib/libuv.1.dylib (compatibility version 1.0.0, current version 1.0.0)
\t/System/Library/Frameworks/Security.framework/Versions/A/Security (compatibility version 1.0.0, current version 1.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)
"""
    node_load_commands = """Load command 40
          cmd LC_RPATH
      cmdsize 32
         path @loader_path (offset 12)
Load command 41
          cmd LC_RPATH
      cmdsize 40
         path @loader_path/../lib (offset 12)
"""
    library_dependencies = """/opt/homebrew/Cellar/node/26.5.0/lib/libnode.147.dylib:
\t/opt/homebrew/opt/node/lib/libnode.147.dylib (compatibility version 0.0.0, current version 0.0.0)
\t/opt/homebrew/opt/libuv/lib/libuv.1.dylib (compatibility version 1.0.0, current version 1.0.0)
\t/System/Library/Frameworks/Security.framework/Versions/A/Security (compatibility version 1.0.0, current version 1.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)
"""

    node_path = Path("/opt/homebrew/Cellar/node/26.5.0/bin/node")
    library_path = Path(
        "/opt/homebrew/Cellar/node/26.5.0/lib/libnode.147.dylib"
    )
    browser.validate_node_macho_dependency_closure(
        node_path=node_path,
        library_path=library_path,
        node_dependencies=node_dependencies,
        node_load_commands=node_load_commands,
        library_dependencies=library_dependencies,
    )

    hostile_rows = {
        "relative_node_dependency": node_dependencies.replace(
            "/opt/homebrew/opt/libuv/lib/libuv.1.dylib", "libuv.1.dylib"
        ),
        "untrusted_absolute_node_dependency": node_dependencies.replace(
            "/opt/homebrew/opt/libuv/lib/libuv.1.dylib", "/tmp/libuv.1.dylib"
        ),
        "escaping_trusted_prefix_node_dependency": node_dependencies.replace(
            "/opt/homebrew/opt/libuv/lib/libuv.1.dylib",
            "/opt/homebrew/opt/../../tmp/libuv.1.dylib",
        ),
        "relative_library_id": library_dependencies.replace(
            "/opt/homebrew/opt/node/lib/libnode.147.dylib",
            "@rpath/libnode.147.dylib",
            1,
        ),
        "relative_library_dependency": library_dependencies.replace(
            "/opt/homebrew/opt/libuv/lib/libuv.1.dylib", "../lib/libuv.1.dylib"
        ),
        "untrusted_absolute_library_dependency": library_dependencies.replace(
            "/opt/homebrew/opt/libuv/lib/libuv.1.dylib", "/tmp/libuv.1.dylib"
        ),
    }
    for label, hostile in hostile_rows.items():
        node_payload = (
            hostile
            if label.endswith("node_dependency")
            else node_dependencies
        )
        library_payload = (
            hostile
            if "library" in label
            else library_dependencies
        )
        with pytest.raises(browser.BrowserReviewError, match="Mach-O"):
            browser.validate_node_macho_dependency_closure(
                node_path=node_path,
                library_path=library_path,
                node_dependencies=node_payload,
                node_load_commands=node_load_commands,
                library_dependencies=library_payload,
            )

    with pytest.raises(browser.BrowserReviewError, match="Mach-O"):
        browser.validate_node_macho_dependency_closure(
            node_path=node_path,
            library_path=library_path,
            node_dependencies=node_dependencies,
            node_load_commands=node_load_commands.replace(
                "@loader_path/../lib", "@loader_path/../untrusted"
            ),
            library_dependencies=library_dependencies,
        )


def test_installer_never_uses_ambient_tmpdir_and_declares_absent_postcondition():
    installer = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install_worker_browser_b1_runtime.sh"
    ).read_text(encoding="utf-8")

    assert 'tmp_install="$runtime_root/tmp-install"' in installer
    assert installer.count('TMPDIR="$tmp_install"') >= 7
    assert "${TMPDIR" not in installer
    assert "prepare_runtime_install_tmp" in installer
    assert "cleanup_runtime_install_tmp" in installer
    assert "tmp_install_postcondition" in installer
    assert 'runtime_container="/Volumes/Mastermind/worker-browser-b1"' in installer
    assert '/usr/bin/install -m 0500 "$node_executable" "$runtime_root/bin/node"' in installer
    assert 'node_executable="$runtime_root/bin/node"' not in installer


def test_runtime_tmp_install_is_exact_private_contained_and_absent_after_cleanup(
    tmp_path, monkeypatch
):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    ambient = tmp_path / "ambient-tmp"
    ambient.mkdir()
    marker = ambient / "must-survive"
    marker.write_text("ambient", encoding="utf-8")
    monkeypatch.setenv("TMPDIR", os.fspath(ambient))

    identity = browser.prepare_runtime_install_tmp(runtime)

    exact = runtime / "tmp-install"
    info = exact.lstat()
    assert identity == (info.st_dev, info.st_ino)
    assert not exact.is_symlink()
    assert info.st_uid == os.geteuid()
    assert stat.S_IMODE(info.st_mode) == 0o700
    (exact / "nested").mkdir()
    (exact / "nested" / "temporary").write_text("contained", encoding="utf-8")
    browser.cleanup_runtime_install_tmp(runtime, identity)
    assert not os.path.lexists(exact)
    assert marker.read_text(encoding="utf-8") == "ambient"

    exact.symlink_to(ambient, target_is_directory=True)
    with pytest.raises(browser.BrowserReviewError):
        browser.prepare_runtime_install_tmp(runtime)


def test_runtime_tmp_cleanup_refuses_path_swap_and_preserves_both_inodes(
    tmp_path, monkeypatch
):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    identity = browser.prepare_runtime_install_tmp(runtime)
    install_tmp = runtime / "tmp-install"
    (install_tmp / "temporary").write_text("contained", encoding="utf-8")
    captured = runtime / "captured-original"
    original_clear = browser._clear_directory_descriptor

    def swap_after_exact_clear(descriptor: int) -> None:
        original_clear(descriptor)
        install_tmp.rename(captured)
        install_tmp.mkdir(mode=0o700)

    monkeypatch.setattr(browser, "_clear_directory_descriptor", swap_after_exact_clear)

    with pytest.raises(browser.BrowserReviewError, match="cleanup failed"):
        browser.cleanup_runtime_install_tmp(runtime, identity)
    assert captured.is_dir()
    assert (captured.stat().st_dev, captured.stat().st_ino) == identity
    assert install_tmp.is_dir()
    assert (install_tmp.stat().st_dev, install_tmp.stat().st_ino) != identity


def test_runtime_tmp_cleanup_refuses_missing_name_when_captured_inode_survives(
    tmp_path,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    identity = browser.prepare_runtime_install_tmp(runtime)
    captured = runtime / "captured-original"
    (runtime / "tmp-install").rename(captured)

    with pytest.raises(browser.BrowserReviewError, match="cleanup failed"):
        browser.cleanup_runtime_install_tmp(runtime, identity)
    assert (captured.stat().st_dev, captured.stat().st_ino) == identity


@pytest.mark.parametrize("entry_kind", ["directory", "file"])
def test_runtime_tmp_cleanup_quarantines_recursive_entry_before_delete(
    tmp_path, monkeypatch, entry_kind
):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    identity = browser.prepare_runtime_install_tmp(runtime)
    install_tmp = runtime / "tmp-install"
    target = install_tmp / f"nested-{entry_kind}"
    if entry_kind == "directory":
        target.mkdir()
    else:
        target.write_text("original", encoding="utf-8")
    captured = install_tmp / f"captured-{entry_kind}"
    original_rename = browser.os.rename
    injected = False

    def swap_at_quarantine(src, dst, *args, **kwargs):
        nonlocal injected
        if not injected and src == target.name:
            injected = True
            original_rename(target, captured)
            if entry_kind == "directory":
                target.mkdir()
            else:
                target.write_text("replacement", encoding="utf-8")
        return original_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(browser.os, "rename", swap_at_quarantine)

    with pytest.raises(browser.BrowserReviewError, match="cleanup failed"):
        browser.cleanup_runtime_install_tmp(runtime, identity)
    assert injected is True
    assert captured.exists()
    assert target.exists()
    if entry_kind == "file":
        assert captured.read_text(encoding="utf-8") == "original"
        assert target.read_text(encoding="utf-8") == "replacement"


def test_runtime_manifest_writer_freezes_complete_closure_and_cleans_exact_tmpdir(
    tmp_path,
):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    runtime.parent.chmod(0o700)
    runtime.chmod(0o700)
    (runtime / "bin").chmod(0o700)
    manifest_path.unlink()
    tmp_identity = browser.prepare_runtime_install_tmp(runtime)
    install_tmp = runtime / "tmp-install"
    (install_tmp / "npm-temporary").write_text("temporary", encoding="utf-8")

    manifest_digest = browser.write_runtime_install_manifest(
        manifest_path=manifest_path,
        runtime_root=runtime,
        launcher=Path(manifest["launcher"]["path"]),
        node=Path(manifest["node"]["executable"]["path"]),
        node_library=Path(manifest["node"]["dynamic_library"]["path"]),
        mcp=Path(manifest["mcp"]["executable"]["path"]),
        package_lock=Path(manifest["mcp"]["package_lock"]["path"]),
        browser=Path(manifest["browser"]["executable"]["path"]),
        tmp_identity=tmp_identity,
    )

    assert not os.path.lexists(install_tmp)
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o500
    assert stat.S_IMODE((runtime / "bin").stat().st_mode) == 0o500
    assert stat.S_IMODE((runtime / "lib").stat().st_mode) == 0o500
    assert stat.S_IMODE(runtime.parent.stat().st_mode) == 0o500
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o400
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["tmp_install_postcondition"] == "absent"
    assert persisted["closure_inventory"] == sorted(
        persisted["closure_inventory"], key=lambda row: row["path"]
    )
    assert persisted["closure_tree_digest"] == browser.runtime_closure_tree_digest(
        persisted["closure_inventory"]
    )
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == manifest_digest
    assert browser.load_runtime_install_attestation(
        runtime, expected_manifest_digest=manifest_digest
    ).closure_entry_count == len(persisted["closure_inventory"])


def test_runtime_manifest_writer_refuses_unrequired_adjacent_node_library(tmp_path):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    runtime.parent.chmod(0o700)
    runtime.chmod(0o700)
    (runtime / "bin").chmod(0o700)
    (runtime / "lib").chmod(0o700)
    manifest_path.unlink()
    extra = runtime / "lib" / "libnode-unrequired.dylib"
    extra.write_bytes(b"not in the copied Node Mach-O closure")
    extra.chmod(0o400)
    tmp_identity = browser.prepare_runtime_install_tmp(runtime)

    with pytest.raises(browser.BrowserReviewError, match="dynamic library closure"):
        browser.write_runtime_install_manifest(
            manifest_path=manifest_path,
            runtime_root=runtime,
            launcher=Path(manifest["launcher"]["path"]),
            node=Path(manifest["node"]["executable"]["path"]),
            node_library=Path(manifest["node"]["dynamic_library"]["path"]),
            mcp=Path(manifest["mcp"]["executable"]["path"]),
            package_lock=Path(manifest["mcp"]["package_lock"]["path"]),
            browser=Path(manifest["browser"]["executable"]["path"]),
            tmp_identity=tmp_identity,
        )


def test_runtime_manifest_seals_execution_parents_against_swap_restore(tmp_path):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    browser.load_runtime_install_attestation(
        runtime, expected_manifest_digest=manifest_digest
    )

    assert stat.S_IMODE(runtime.parent.stat().st_mode) == 0o500
    assert Path(manifest["node"]["executable"]["path"]) == runtime / "bin" / "node"
    assert Path(manifest["node"]["dynamic_library"]["path"]) == (
        runtime / "lib" / "libnode.147.dylib"
    )
    with pytest.raises(PermissionError):
        runtime.rename(runtime.parent / "runtime.attested")
    with pytest.raises(PermissionError):
        (runtime / "node_modules").rename(runtime / "node_modules.attested")
    with pytest.raises(PermissionError):
        (runtime / "bin").rename(runtime / "bin.attested")
    with pytest.raises(PermissionError):
        (runtime / "bin" / "worker-browser-b1-launcher").rename(
            runtime / "bin" / "launcher.attested"
        )
    with pytest.raises(PermissionError):
        (runtime / "bin" / "node").rename(runtime / "bin" / "node.attested")
    with pytest.raises(PermissionError):
        (runtime / "lib").rename(runtime / "lib.attested")
    with pytest.raises(PermissionError):
        (runtime / "lib" / "libnode.147.dylib").rename(
            runtime / "lib" / "libnode.147.dylib.attested"
        )


def test_runtime_manifest_binds_exact_outer_container_identity(tmp_path):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    container = runtime.parent
    info = container.stat()
    expected = {
        "device": info.st_dev,
        "gid": info.st_gid,
        "inode": info.st_ino,
        "mode": 0o500,
        "uid": info.st_uid,
    }

    assert manifest["runtime_container"] == expected
    attestation = browser.load_runtime_install_attestation(
        runtime,
        expected_manifest_digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    assert attestation.runtime_container_device == info.st_dev
    assert attestation.runtime_container_inode == info.st_ino
    assert attestation.runtime_container_uid == info.st_uid
    assert attestation.runtime_container_gid == info.st_gid
    assert attestation.runtime_container_mode == 0o500


def test_outer_bootstrap_holds_opened_container_across_whole_name_swap(
    tmp_path, monkeypatch
):
    bootstrap = getattr(capabilities, "WORKER_BROWSER_MCP_BOOTSTRAP", "")
    assert bootstrap
    canonical = tmp_path / "worker-browser-b1"
    launcher = canonical / "runtime" / "bin" / browser.RUNTIME_LAUNCHER_NAME
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\nprintf 'ORIGINAL\\n'\n", encoding="utf-8")
    launcher.chmod(0o500)
    manifest_path = canonical / "runtime" / browser.RUNTIME_INSTALL_MANIFEST_NAME
    container_info = canonical.stat()
    launcher_info = launcher.stat()
    manifest_value = {
        "launcher": {
            "gid": launcher_info.st_gid,
            "mode": 0o500,
            "path": os.fspath(launcher),
            "sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
            "uid": launcher_info.st_uid,
        },
        "runtime_container": {
            "device": container_info.st_dev,
            "gid": container_info.st_gid,
            "inode": container_info.st_ino,
            "mode": 0o500,
            "uid": container_info.st_uid,
        }
    }
    manifest_path.write_bytes(browser._canonical_bytes(manifest_value) + b"\n")
    manifest_path.chmod(0o400)
    launcher.parent.chmod(0o500)
    launcher.parent.parent.chmod(0o500)
    canonical.chmod(0o500)
    replacement = tmp_path / "replacement"
    replacement_launcher = (
        replacement / "runtime" / "bin" / browser.RUNTIME_LAUNCHER_NAME
    )
    replacement_launcher.parent.mkdir(parents=True)
    replacement_launcher.write_text(
        "#!/bin/sh\nprintf 'REPLACEMENT\\n'\n", encoding="utf-8"
    )
    replacement_launcher.chmod(0o500)
    replacement.chmod(0o500)
    reviewed_env = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(tmp_path / "artifact"),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": "http://127.0.0.1:48101/a",
        "MASTERMIND_BROWSER_FIXTURE_B_URL": "http://127.0.0.1:48101/b",
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:48101",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:48102",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(manifest_path),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(canonical / "runtime"),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(tmp_path / "workspace"),
        "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
    }
    monkeypatch.setattr(os, "environ", reviewed_env)
    real_open = os.open
    swapped = False
    captured_exec: dict[str, object] = {}

    def swap_after_container_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if (
            not swapped
            and dir_fd is None
            and os.fspath(path) == os.fspath(canonical)
        ):
            swapped = True
            canonical.rename(tmp_path / "worker-browser-b1.attested")
            replacement.rename(canonical)
        return descriptor

    class ExecCaptured(RuntimeError):
        pass

    def capture_exec(path, argv, environment):
        captured_exec.update(
            path=path,
            argv=list(argv),
            environment=dict(environment),
            launcher=Path(path).read_text(encoding="utf-8"),
        )
        raise ExecCaptured

    monkeypatch.setattr(os, "open", swap_after_container_open)
    monkeypatch.setattr(os, "execve", capture_exec)
    cwd_fd = real_open(".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ExecCaptured):
            exec(bootstrap, {"__name__": "__main__"})
    finally:
        os.fchdir(cwd_fd)
        os.close(cwd_fd)

    assert swapped is True
    assert captured_exec["path"] == "runtime/bin/worker-browser-b1-launcher"
    assert captured_exec["argv"] == ["runtime/bin/worker-browser-b1-launcher"]
    assert "ORIGINAL" in captured_exec["launcher"]
    assert "REPLACEMENT" not in captured_exec["launcher"]
    assert (
        captured_exec["environment"]["MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"]
        .isdigit()
    )


def test_outer_bootstrap_refuses_complete_launcher_replacement_before_exec(tmp_path):
    """A replacement launcher may not act before manifest-bound verification."""

    runtime, runtime_manifest, manifest = _runtime_install_fixture(tmp_path)
    launcher = Path(manifest["launcher"]["path"])
    runtime.parent.chmod(0o700)
    runtime.chmod(0o700)
    launcher.parent.chmod(0o700)
    launcher.chmod(0o700)
    launcher.write_text(
        "#!/bin/sh\nprintf 'REPLACEMENT-LAUNCHER-EXECUTED\\n'\n",
        encoding="utf-8",
    )
    launcher.chmod(0o500)
    launcher.parent.chmod(0o500)
    runtime.chmod(0o500)
    runtime.parent.chmod(0o500)

    result = subprocess.run(
        [capabilities.WORKER_BROWSER_MCP_COMMAND, *capabilities.WORKER_BROWSER_MCP_ARGS],
        check=False,
        capture_output=True,
        text=True,
        env=_attempt_launch_environment(
            workspace=tmp_path,
            artifact=tmp_path / "artifact",
            runtime=runtime,
            runtime_manifest=runtime_manifest,
        ),
        timeout=10,
    )

    assert result.returncode != 0
    assert "runtime container bootstrap refused" in result.stderr
    assert "REPLACEMENT-LAUNCHER-EXECUTED" not in result.stdout


def test_runtime_install_attestation_binds_launcher_node_lock_mcp_and_browser(tmp_path):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    attestation = browser.load_runtime_install_attestation(
        runtime, expected_manifest_digest=manifest_digest
    )

    assert attestation.runtime_root == runtime.resolve()
    assert attestation.manifest_path == manifest_path.resolve()
    assert attestation.manifest_digest == hashlib.sha256(
        browser._canonical_bytes(manifest) + b"\n"
    ).hexdigest()
    assert attestation.launcher_path == runtime / "bin" / "worker-browser-b1-launcher"
    assert attestation.node_path == Path(manifest["node"]["executable"]["path"])
    assert attestation.node_library_path == Path(
        manifest["node"]["dynamic_library"]["path"]
    )
    assert attestation.node_library_sha256 == manifest["node"]["dynamic_library"][
        "sha256"
    ]
    assert attestation.mcp_executable == Path(manifest["mcp"]["executable"]["path"])
    assert attestation.package_lock_sha256 == manifest["mcp"]["package_lock"]["sha256"]
    assert attestation.closure_tree_digest == manifest["closure_tree_digest"]
    assert attestation.closure_entry_count == len(manifest["closure_inventory"])
    assert {
        row["link"]
        for row in manifest["closure_inventory"]
        if row["type"] == "symlink"
    } >= {
        "../@playwright/mcp/cli.js",
        "A",
        "Versions/Current/Chromium Framework",
    }
    assert attestation.browser_revision == "1237"
    assert attestation.browser_executable == Path(
        manifest["browser"]["executable"]["path"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "mode", "tamper", "swap"],
)
def test_runtime_attestation_refuses_node_dynamic_library_closure_drift(
    tmp_path, mutation
):
    """A copied Node is unusable unless its exact @rpath libnode is closed."""

    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    library = Path(manifest["node"]["dynamic_library"]["path"])
    library_root = library.parent
    runtime.parent.chmod(0o700)
    runtime.chmod(0o700)
    library_root.chmod(0o700)

    if mutation == "missing":
        library.unlink()
    elif mutation == "extra":
        extra = library_root / "libnode-unmanifested.dylib"
        extra.write_bytes(b"unmanifested adjacent Node library")
        extra.chmod(0o400)
    elif mutation == "mode":
        library.chmod(0o600)
    elif mutation == "tamper":
        library.chmod(0o600)
        library.write_bytes(library.read_bytes() + b" tampered")
        library.chmod(0o400)
    else:
        captured = library.with_suffix(".captured")
        library.rename(captured)
        library.write_bytes(b"replacement Node dynamic library")
        library.chmod(0o400)

    library_root.chmod(0o500)
    runtime.chmod(0o500)
    runtime.parent.chmod(0o500)
    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )
    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


def test_runtime_attestation_refuses_loader_path_shadow_before_runtime_lib(tmp_path):
    """The first @loader_path search slot may not shadow the attested ../lib copy."""

    runtime, manifest_path, _manifest = _runtime_install_fixture(tmp_path)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    runtime.parent.chmod(0o700)
    runtime.chmod(0o700)
    (runtime / "bin").chmod(0o700)
    shadow = runtime / "bin" / "libnode.147.dylib"
    shadow.write_bytes(b"unattested first-rpath shadow")
    shadow.chmod(0o400)
    (runtime / "bin").chmod(0o500)
    runtime.chmod(0o500)
    runtime.parent.chmod(0o500)

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )
    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


@pytest.mark.parametrize(
    "closure_label",
    [
        "mcp_core_bundle",
        "mcp_other",
        "playwright",
        "utils_bundle",
        "playwright_core_other",
        "chromium_framework",
        "chromium_helper",
        "headless_shell",
        "ffmpeg",
    ],
)
def test_runtime_attestation_refuses_any_loaded_closure_mutation(
    tmp_path, closure_label
):
    runtime, manifest_path, _manifest = _runtime_install_fixture(tmp_path)
    closure = _add_loaded_runtime_closure(runtime)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    target = closure[closure_label]
    prior_mode = stat.S_IMODE(target.stat().st_mode)
    target.chmod(0o700)
    target.write_bytes(target.read_bytes() + b"tampered")
    target.chmod(prior_mode)

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )
    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


def test_runtime_attestation_refuses_coordinated_closure_and_manifest_rewrite(
    tmp_path,
):
    """The independent grant digest wins over a self-consistent rewritten receipt."""

    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    target = _add_loaded_runtime_closure(runtime)["mcp_core_bundle"]
    target.chmod(0o700)
    target.write_bytes(target.read_bytes() + b" coordinated closure tamper")
    target.chmod(0o400)
    target_relative = target.relative_to(runtime).as_posix()
    row = next(
        item for item in manifest["closure_inventory"] if item["path"] == target_relative
    )
    row["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    row["size"] = target.stat().st_size
    manifest["closure_tree_digest"] = browser.runtime_closure_tree_digest(
        manifest["closure_inventory"]
    )
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(browser._canonical_bytes(manifest) + b"\n")
    manifest_path.chmod(0o400)

    with pytest.raises(browser.BrowserReviewError, match="manifest digest drifted"):
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )


def test_runtime_attestation_refuses_escaping_closure_symlink(tmp_path):
    runtime, manifest_path, _manifest = _runtime_install_fixture(tmp_path)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    package_root = runtime / "node_modules" / "playwright-core"
    package_root.chmod(0o700)
    (package_root / "escape").symlink_to(tmp_path / "node")
    package_root.chmod(0o500)

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )
    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


def test_runtime_attestation_refuses_missing_extra_and_unsafe_closure_entries(tmp_path):
    runtime, manifest_path, _manifest = _runtime_install_fixture(tmp_path)
    closure = _add_loaded_runtime_closure(runtime)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    mcp_lib = closure["mcp_other"].parent
    mcp_lib.chmod(0o700)
    closure["mcp_other"].unlink()
    mcp_lib.chmod(0o500)
    extra = runtime / "node_modules" / "playwright-core" / "lib" / "injected.js"
    extra.parent.chmod(0o700)
    extra.write_bytes(b"unmanifested")
    extra.chmod(0o400)
    extra.parent.chmod(0o500)
    closure["utils_bundle"].chmod(0o600)

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )
    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_manifest",
        "manifest_symlink",
        "manifest_mode",
        "manifest_extra_field",
        "wrong_owner",
        "launcher_hardlink",
        "launcher_symlink",
        "launcher_mode",
        "launcher_tamper",
        "node_tamper",
        "node_library_tamper",
        "mcp_tamper",
        "package_lock_tamper",
        "browser_tamper",
        "coordinated_node_and_manifest_tamper",
    ],
)
def test_runtime_install_attestation_refuses_every_identity_drift(
    tmp_path, monkeypatch, mutation
):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)
    expected_manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    if mutation == "missing_manifest":
        runtime.chmod(0o700)
        manifest_path.unlink()
    elif mutation == "manifest_symlink":
        payload = manifest_path.read_bytes()
        runtime.chmod(0o700)
        manifest_path.unlink()
        alternate = tmp_path / "alternate-manifest.json"
        alternate.write_bytes(payload)
        alternate.chmod(0o400)
        manifest_path.symlink_to(alternate)
    elif mutation == "manifest_mode":
        manifest_path.chmod(0o600)
    elif mutation == "manifest_extra_field":
        manifest["unexpected"] = True
        manifest_path.chmod(0o600)
        manifest_path.write_bytes(browser._canonical_bytes(manifest) + b"\n")
        manifest_path.chmod(0o400)
    elif mutation == "wrong_owner":
        actual_uid = os.geteuid()
        monkeypatch.setattr(browser.os, "geteuid", lambda: actual_uid + 1)
    else:
        targets = {
            "launcher_symlink": Path(manifest["launcher"]["path"]),
            "launcher_hardlink": Path(manifest["launcher"]["path"]),
            "launcher_mode": Path(manifest["launcher"]["path"]),
            "launcher_tamper": Path(manifest["launcher"]["path"]),
            "node_tamper": Path(manifest["node"]["executable"]["path"]),
            "node_library_tamper": Path(
                manifest["node"]["dynamic_library"]["path"]
            ),
            "mcp_tamper": Path(manifest["mcp"]["executable"]["path"]),
            "package_lock_tamper": Path(manifest["mcp"]["package_lock"]["path"]),
            "browser_tamper": Path(manifest["browser"]["executable"]["path"]),
            "coordinated_node_and_manifest_tamper": Path(
                manifest["node"]["executable"]["path"]
            ),
        }
        target = targets[mutation]
        if mutation == "launcher_hardlink":
            os.link(target, tmp_path / "launcher-hardlink")
        elif mutation == "launcher_symlink":
            payload = target.read_bytes()
            (runtime / "bin").chmod(0o700)
            target.unlink()
            alternate = tmp_path / "alternate-launcher"
            alternate.write_bytes(payload)
            alternate.chmod(0o500)
            target.symlink_to(alternate)
        elif mutation == "launcher_mode":
            target.chmod(0o700)
        else:
            prior_mode = stat.S_IMODE(target.stat().st_mode)
            target.chmod(0o700)
            target.write_bytes(target.read_bytes() + b" tampered")
            target.chmod(prior_mode)
            if mutation == "coordinated_node_and_manifest_tamper":
                manifest["node"]["executable"]["sha256"] = hashlib.sha256(
                    target.read_bytes()
                ).hexdigest()
                manifest_path.chmod(0o600)
                manifest_path.write_bytes(browser._canonical_bytes(manifest) + b"\n")
                manifest_path.chmod(0o400)

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=expected_manifest_digest
        )

    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


def test_runtime_attestation_refuses_unratified_parent_symlink_and_path_swap(
    tmp_path, monkeypatch
):
    runtime, manifest_path, manifest = _runtime_install_fixture(tmp_path)

    with pytest.raises(browser.BrowserReviewError, match="not ratified"):
        browser.load_runtime_install_attestation(
            runtime,
            expected_manifest_digest=browser.UNRATIFIED_RUNTIME_MANIFEST_DIGEST,
        )

    actual_parent = tmp_path / "external-node-parent"
    actual_parent.mkdir()
    node = actual_parent / "node"
    node.write_bytes(b"fixture node through symlinked parent")
    node.chmod(0o500)
    linked_parent = tmp_path / "linked-node-parent"
    linked_parent.symlink_to(actual_parent, target_is_directory=True)
    linked_node = linked_parent / "node"
    info = node.stat()
    manifest["node"]["executable"] = {
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "path": os.fspath(linked_node),
        "sha256": hashlib.sha256(node.read_bytes()).hexdigest(),
        "uid": info.st_uid,
    }
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(browser._canonical_bytes(manifest) + b"\n")
    manifest_path.chmod(0o400)
    symlinked_parent_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(browser.BrowserReviewError) as parent_error:
        browser.load_runtime_install_attestation(
            runtime, expected_manifest_digest=symlinked_parent_digest
        )
    assert parent_error.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"

    # Restore a direct path and replace that pathname after its descriptor is
    # opened.  Hashing the original descriptor cannot bless the swapped leaf.
    direct_node = tmp_path / "descriptor-swap-node"
    direct_node.write_bytes(b"descriptor-stable node fixture")
    direct_node.chmod(0o500)
    target_inode = direct_node.stat().st_ino
    original_read = browser.os.read
    swapped = False

    def read_then_swap(descriptor, size):
        nonlocal swapped
        chunk = original_read(descriptor, size)
        if not swapped and os.fstat(descriptor).st_ino == target_inode:
            swapped = True
            old = direct_node.with_name("node-open-descriptor")
            direct_node.rename(old)
            direct_node.write_bytes(old.read_bytes())
            direct_node.chmod(0o500)
        return chunk

    monkeypatch.setattr(browser.os, "read", read_then_swap)
    with pytest.raises(browser.BrowserReviewError) as swap_error:
        browser._stable_runtime_file(direct_node)
    assert swapped is True
    assert swap_error.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"


def test_external_launcher_scrubs_parent_before_worktree_import_and_rechecks_pin(
    tmp_path,
):
    runtime, manifest_path, _manifest = _runtime_install_fixture(tmp_path)
    launcher = runtime / "bin" / browser.RUNTIME_LAUNCHER_NAME
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    workspace = tmp_path / "workspace"
    package = workspace / "control_plane"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "worker_browser_b1.py").write_text(
        textwrap.dedent(
            """
            import json
            import os
            from pathlib import Path

            output = Path(os.environ["MASTERMIND_BROWSER_ARTIFACT_DIR"]) / "import-env.json"
            output.write_text(json.dumps(dict(os.environ), sort_keys=True), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    reviewed_env = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(artifact),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": "http://127.0.0.1:48101/a",
        "MASTERMIND_BROWSER_FIXTURE_B_URL": "http://127.0.0.1:48101/b",
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:48101",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:48102",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(manifest_path),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": manifest_digest,
        "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(runtime),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(workspace),
        "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
    }
    hostile_parent = {
        **reviewed_env,
        "AWS_ACCESS_KEY_ID": "must-not-cross",
        "AWS_SECRET_ACCESS_KEY": "must-not-cross",
        "CODEX_HOME": "/must/not/cross",
        "GH_TOKEN": "must-not-cross",
        "GITHUB_TOKEN": "must-not-cross",
        "NODE_OPTIONS": "--require=/malicious.js",
        "NPM_CONFIG_USERCONFIG": "/malicious/npmrc",
        "OPENAI_API_KEY": "must-not-cross",
        "PYTHONHOME": "/malicious/python-home",
        "PYTHONPATH": "/malicious/sitecustomize",
        "SLACK_BOT_TOKEN": "must-not-cross",
        "SSH_AUTH_SOCK": "/malicious/agent.sock",
    }

    accepted = subprocess.run(
        [
            capabilities.WORKER_BROWSER_MCP_COMMAND,
            *capabilities.WORKER_BROWSER_MCP_ARGS,
        ],
        cwd=workspace,
        env=hostile_parent,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert accepted.returncode == 0, accepted.stderr
    observed = json.loads((artifact / "import-env.json").read_text(encoding="utf-8"))
    for forbidden in hostile_parent.keys() - reviewed_env.keys():
        assert forbidden not in observed
    assert observed["MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256"] == manifest_digest
    assert "PYTHONPATH" not in observed
    assert "PYTHONHOME" not in observed

    (artifact / "import-env.json").unlink()
    wrong_pin = dict(reviewed_env)
    wrong_pin["MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256"] = "f" * 64
    refused_pin = subprocess.run(
        [
            capabilities.WORKER_BROWSER_MCP_COMMAND,
            *capabilities.WORKER_BROWSER_MCP_ARGS,
        ],
        cwd=workspace,
        env=wrong_pin,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused_pin.returncode != 0
    assert not (artifact / "import-env.json").exists()

    container_fd = os.open(
        runtime.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    direct_env = {
        **reviewed_env,
        "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD": str(container_fd),
    }
    try:
        refused_argument = subprocess.run(
            [os.fspath(launcher), "unexpected"],
            cwd=runtime.parent,
            env=direct_env,
            capture_output=True,
            text=True,
            pass_fds=(container_fd,),
            timeout=10,
        )
    finally:
        os.close(container_fd)
    assert refused_argument.returncode != 0
    assert not (artifact / "import-env.json").exists()

    launcher.chmod(0o700)
    launcher.write_bytes(launcher.read_bytes() + b"\n# tampered\n")
    launcher.chmod(0o500)
    refused_launcher = subprocess.run(
        [
            capabilities.WORKER_BROWSER_MCP_COMMAND,
            *capabilities.WORKER_BROWSER_MCP_ARGS,
        ],
        cwd=workspace,
        env=reviewed_env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused_launcher.returncode != 0
    assert not (artifact / "import-env.json").exists()


class _OriginHandler(BaseHTTPRequestHandler):
    hits: list[tuple[str, str]] = []

    def do_GET(self):  # noqa: N802 - stdlib callback
        type(self).hits.append((self.command, self.path))
        if self.path == "/redirect-external":
            self.send_response(302)
            self.send_header("Location", "https://example.com/escape")
            self.end_headers()
            return
        body = b"loopback-ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _raw_proxy_request(proxy_url: str, request: bytes) -> bytes:
    host, port_text = proxy_url.removeprefix("http://").split(":", 1)
    with socket.create_connection((host, int(port_text)), timeout=5) as client:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def test_attempt_local_proxy_allows_only_exact_origin_and_refuses_every_escape_class():
    """Removing any proxy refusal branch must make a hostile request observable."""

    _OriginHandler.hits = []
    origin_server = ThreadingHTTPServer(("127.0.0.1", 0), _OriginHandler)
    origin_thread = threading.Thread(target=origin_server.serve_forever, daemon=True)
    origin_thread.start()
    origin = f"http://127.0.0.1:{origin_server.server_port}"
    proxy = browser.LoopbackEnforcingProxy(origin)
    proxy.start()
    try:
        allowed = _raw_proxy_request(
            proxy.proxy_url,
            (
                f"GET {origin}/ok HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{origin_server.server_port}\r\nConnection: close\r\n\r\n"
            ).encode(),
        )
        redirect = _raw_proxy_request(
            proxy.proxy_url,
            (
                f"GET {origin}/redirect-external HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{origin_server.server_port}\r\nConnection: close\r\n\r\n"
            ).encode(),
        )
        hostile_requests = {
            "http": b"GET http://external-http.invalid/b1 HTTP/1.1\r\nHost: external-http.invalid\r\nConnection: close\r\n\r\n",
            "https": b"CONNECT external-https.invalid:443 HTTP/1.1\r\nHost: external-https.invalid:443\r\nConnection: close\r\n\r\n",
            "redirect": b"GET http://redirect.invalid/escape HTTP/1.1\r\nHost: redirect.invalid\r\nConnection: close\r\n\r\n",
            "subresource": b"GET http://subresource.invalid/app.js HTTP/1.1\r\nHost: subresource.invalid\r\nSec-Fetch-Dest: script\r\nConnection: close\r\n\r\n",
            "fetch": b"GET http://fetch.invalid/api HTTP/1.1\r\nHost: fetch.invalid\r\nSec-Fetch-Mode: cors\r\nConnection: close\r\n\r\n",
            "websocket": (
                "GET http://websocket.invalid/socket HTTP/1.1\r\n"
                "Host: websocket.invalid\r\n"
                "Connection: Upgrade\r\nUpgrade: websocket\r\n\r\n"
            ).encode(),
            "file": b"GET file:///etc/passwd HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
            "write": (
                f"POST {origin}/write HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{origin_server.server_port}\r\n"
                "Content-Length: 0\r\nConnection: close\r\n\r\n"
            ).encode(),
        }
        refused = {
            name: _raw_proxy_request(proxy.proxy_url, request)
            for name, request in hostile_requests.items()
        }
    finally:
        proxy.stop()
        origin_server.shutdown()
        origin_server.server_close()
        origin_thread.join(5)

    assert allowed.startswith(b"HTTP/1.1 200")
    assert allowed.endswith(b"loopback-ok")
    assert redirect.startswith(b"HTTP/1.1 302")
    assert b"Location: https://example.com/escape" in redirect
    assert set(refused) == {
        "http", "https", "redirect", "subresource", "fetch", "websocket", "file", "write"
    }
    assert all(response.startswith(b"HTTP/1.1 403") for response in refused.values())
    assert _OriginHandler.hits == [("GET", "/ok"), ("GET", "/redirect-external")]
    assert proxy.receipt() == {
        "allowed_requests": 2,
        "external_egress_observed": False,
        "refused": {
            "external_fetch": 1,
            "external_http": 1,
            "external_https": 1,
            "external_redirect": 1,
            "external_subresource": 1,
            "external_websocket": 1,
            "file_url": 1,
            "proxy_override": 0,
            "write_method": 1,
        },
    }


def test_mcp_launch_forces_locked_chromium_through_proxy_with_no_loopback_bypass(tmp_path):
    config = _config(tmp_path, command_override=None)

    argv = browser.build_mcp_argv(
        config,
        tmp_path / "output",
        proxy_url="http://127.0.0.1:48177",
    )

    assert argv[argv.index("--browser") + 1] == "chromium"
    assert argv[argv.index("--proxy-server") + 1] == "http://127.0.0.1:48177"
    assert argv[argv.index("--proxy-bypass") + 1] == "<-loopback>"
    assert argv[argv.index("--allowed-origins") + 1] == "http://127.0.0.1:8787"
    assert "--allow-unrestricted-file-access" not in argv


def test_mcp_tool_guard_confines_all_writes_and_rejects_unsafe_arguments(tmp_path):
    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )

    _guard_navigate(guard, "http://127.0.0.1:48101/")
    _guard_resize(guard, width=1440, height=900)
    screenshot = guard.rewrite_call(
        "browser_take_screenshot",
        {
            "filename": "desktop.png",
            "fullPage": False,
            "scale": "css",
            "type": "png",
        },
    )
    assert "filename" not in screenshot

    hostile_calls = (
        ("browser_take_screenshot", {"filename": "../../tracked.py", "fullPage": False, "scale": "css", "type": "png"}),
        ("browser_console_messages", {"level": "warning", "all": True, "filename": "tracked.py"}),
        ("browser_network_requests", {"static": True, "filename": "tracked.py"}),
        ("browser_tabs", {"action": "new", "url": "https://example.com"}),
        ("browser_click", {"target": "arbitrary-production-ref"}),
        ("browser_fill_form", {"fields": []}),
        ("browser_run_code_unsafe", {"code": "require('fs').writeFileSync('pwned','x')"}),
    )
    for name, arguments in hostile_calls:
        with pytest.raises(browser.BrowserReviewError) as raised:
            guard.rewrite_call(name, arguments)
        assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"


def test_mcp_tool_guard_requires_product_hover_and_records_file_refusal(tmp_path):
    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    fixture_a = _fixture_urls(origin)["A"]
    guard.rewrite_call("browser_navigate", {"url": fixture_a})
    guard.record_result(
        "browser_navigate",
        {"url": fixture_a},
        {"result": {"content": [{"type": "text", "text": "navigated"}]}},
    )
    guard.rewrite_call("browser_snapshot", {})
    guard.record_result(
        "browser_snapshot",
        {},
        {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "- region 'Visual review fixture'\n  - section 'Critical portfolio card'",
                    }
                ]
            }
        },
    )
    with pytest.raises(browser.BrowserReviewError, match="product-page-only"):
        guard.rewrite_call(
            "browser_hover",
            {"element": "visual fixture card", "target": "fixture-card"},
        )

    product = f"{origin}/"
    guard.rewrite_call("browser_navigate", {"url": product})
    _record_guard_text_success(
        guard, "browser_navigate", {"url": product}, text="navigated"
    )
    guard.rewrite_call("browser_snapshot", {})
    _record_guard_text_success(
        guard,
        "browser_snapshot",
        {},
        text="- banner 'Mastermind X Chairman Control Room'\n  - button 'Theme'",
    )
    hover = {"element": "Theme button", "target": "theme-ref"}
    assert guard.rewrite_call("browser_hover", hover) == hover
    _record_guard_text_success(guard, "browser_hover", hover, text="hovered")
    with pytest.raises(browser.BrowserReviewError):
        guard.rewrite_call(
            "browser_fill_form",
            {
                "fields": [
                    {
                        "name": "fixture input",
                        "target": "fixture-input",
                        "type": "textbox",
                        "value": "local-only",
                    }
                ]
            },
        )
    with pytest.raises(browser.BrowserReviewError):
        guard.rewrite_call("browser_navigate", {"url": "file:///etc/passwd"})
    assert guard.evidence()["egress_falsifiers"]["file_url"] == "REFUSED"
    assert guard.evidence()["egress_falsifiers"]["proxy_override"] == "REFUSED"
    assert guard.evidence()["interaction"] == {
        "page_class": "product",
        "tool": "browser_hover",
    }


def test_attempt_env_wrapper_runs_argument_guard_with_credential_free_child_env(
    tmp_path, monkeypatch
):
    runtime, runtime_manifest, manifest = _runtime_install_fixture(tmp_path)
    manifest_digest = hashlib.sha256(runtime_manifest.read_bytes()).hexdigest()
    node = Path(manifest["node"]["executable"]["path"])
    binary = Path(manifest["mcp"]["executable"]["path"])
    browsers = runtime / "browsers"
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    observed: dict[str, object] = {}

    def capture(**kwargs):
        observed.update(
            argv=list(kwargs["argv"]),
            environment=dict(kwargs["environment"]),
            guard=kwargs["guard"],
            pass_fds=tuple(kwargs["pass_fds"]),
        )
        return 0

    container_fd = os.open(
        runtime.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    os.set_inheritable(container_fd, True)
    try:
        assert browser.launch_mcp_from_attempt_env(
            {
                "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(artifact),
                "MASTERMIND_BROWSER_FIXTURE_A_URL": "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "MASTERMIND_BROWSER_FIXTURE_B_URL": "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
                "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:48101",
                "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:48102",
                "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD": str(container_fd),
                "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(runtime_manifest),
                "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": manifest_digest,
                "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(runtime),
                "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(tmp_path),
                "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
                "OPENAI_API_KEY": "must-not-cross-wrapper",
            },
            bridge_runner=capture,
        ) == 0
    finally:
        os.close(container_fd)

    argv = observed["argv"]
    assert argv[:5] == [
        "/usr/bin/python3",
        "-I",
        "-S",
        "-c",
        browser._ANCHORED_NODE_BOOTSTRAP,
    ]
    assert os.fspath(node) not in argv
    assert os.fspath(binary) not in argv
    assert argv[argv.index("--browser") + 1] == "chromium"
    assert argv[argv.index("--proxy-bypass") + 1] == "<-loopback>"
    assert observed["environment"] == {
        "HOME": os.fspath(artifact / "home"),
        "LANG": "C",
        "LC_ALL": "C",
        "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD": str(container_fd),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": manifest_digest,
        "NO_COLOR": "1",
        "PATH": "/usr/bin:/bin",
        "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
        "TMPDIR": os.fspath(artifact),
    }
    assert observed["pass_fds"] == (container_fd,)
    assert isinstance(observed["guard"], browser.BrowserMcpToolGuard)


def test_attempt_env_wrapper_executes_inner_anchor_not_outer_bootstrap(
    tmp_path, monkeypatch
):
    runtime, runtime_manifest, _manifest = _runtime_install_fixture(
        tmp_path,
        node_payload=(
            b"#!/bin/sh\n"
            b"printf 'INNER:%s:%s\\n' \"$1\" \"$PLAYWRIGHT_BROWSERS_PATH\"\n"
        ),
    )
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    container_fd = os.open(
        runtime.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    os.set_inheritable(container_fd, True)
    observed: dict[str, object] = {}

    def execute_selected_envelope(**kwargs):
        completed = subprocess.run(
            kwargs["argv"],
            cwd=kwargs["guard"].artifact_dir,
            env=kwargs["environment"],
            pass_fds=kwargs["pass_fds"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        observed.update(
            argv=list(kwargs["argv"]),
            stderr=completed.stderr,
            stdout=completed.stdout,
        )
        return completed.returncode

    try:
        return_code = browser.launch_mcp_from_attempt_env(
            {
                "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(artifact),
                "MASTERMIND_BROWSER_FIXTURE_A_URL": "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "MASTERMIND_BROWSER_FIXTURE_B_URL": "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
                "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:48101",
                "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:48102",
                "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD": str(container_fd),
                "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(runtime_manifest),
                "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": hashlib.sha256(
                    runtime_manifest.read_bytes()
                ).hexdigest(),
                "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(runtime),
                "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(tmp_path),
                "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
            },
            bridge_runner=execute_selected_envelope,
        )
    finally:
        os.close(container_fd)

    assert return_code == 0, observed.get("stderr")
    assert observed["argv"][:5] == [
        "/usr/bin/python3",
        "-I",
        "-S",
        "-c",
        browser._ANCHORED_NODE_BOOTSTRAP,
    ]
    assert observed["stdout"] == (
        "INNER:runtime/node_modules/@playwright/mcp/cli.js:runtime/browsers\n"
    )


@pytest.mark.parametrize("tampered_identity", ["node", "mcp"])
def test_inner_runtime_stub_refuses_post_manifest_direct_executable_tamper(
    tmp_path,
    monkeypatch,
    tampered_identity,
):
    """The last trusted Python boundary must reject stable Node/MCP drift."""

    runtime, runtime_manifest, manifest = _runtime_install_fixture(
        tmp_path,
        node_payload=(
            b"#!/bin/sh\n"
            b"printf 'ORIGINAL-NODE:%s\\n' \"$1\"\n"
        ),
    )
    target = Path(
        manifest["node"]["executable"]["path"]
        if tampered_identity == "node"
        else manifest["mcp"]["executable"]["path"]
    )
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    container_fd = os.open(
        runtime.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    os.set_inheritable(container_fd, True)
    observed: dict[str, object] = {}

    def tamper_then_execute(**kwargs):
        target.chmod(0o700)
        target.write_bytes(
            b"#!/bin/sh\nprintf 'TAMPERED-NODE\\n'\n"
            if tampered_identity == "node"
            else b"post-manifest direct MCP replacement\n"
        )
        target.chmod(0o500)
        completed = subprocess.run(
            kwargs["argv"],
            cwd=kwargs["guard"].artifact_dir,
            env=kwargs["environment"],
            pass_fds=kwargs["pass_fds"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        observed.update(stderr=completed.stderr, stdout=completed.stdout)
        return completed.returncode

    try:
        return_code = browser.launch_mcp_from_attempt_env(
            _attempt_launch_environment(
                workspace=tmp_path,
                artifact=artifact,
                runtime=runtime,
                runtime_manifest=runtime_manifest,
                container_fd=container_fd,
            ),
            bridge_runner=tamper_then_execute,
        )
    finally:
        os.close(container_fd)

    assert return_code != 0
    assert "anchored runtime launch refused" in observed["stderr"]
    assert "TAMPERED-NODE" not in observed["stdout"]
    assert "ORIGINAL-NODE" not in observed["stdout"]


def test_attempt_env_wrapper_refuses_post_manifest_browser_closure_tamper(
    tmp_path,
    monkeypatch,
):
    """The bridge may not start after one manifest-bound browser byte drifts."""

    runtime, runtime_manifest, _manifest = _runtime_install_fixture(tmp_path)
    target = (
        runtime
        / "browsers"
        / "chromium-1237"
        / "Chromium.app"
        / "Contents"
        / "Frameworks"
        / "Chromium Helper.app"
        / "Contents"
        / "MacOS"
        / "Chromium Helper"
    )
    target.chmod(0o700)
    target.write_bytes(target.read_bytes() + b"post-manifest browser closure tamper")
    target.chmod(0o500)
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    container_fd = os.open(
        runtime.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    os.set_inheritable(container_fd, True)
    bridge_called = False

    def must_not_start_bridge(**_kwargs):
        nonlocal bridge_called
        bridge_called = True
        return 0

    try:
        with pytest.raises(browser.BrowserReviewError) as raised:
            browser.launch_mcp_from_attempt_env(
                _attempt_launch_environment(
                    workspace=tmp_path,
                    artifact=artifact,
                    runtime=runtime,
                    runtime_manifest=runtime_manifest,
                    container_fd=container_fd,
                ),
                bridge_runner=must_not_start_bridge,
            )
    finally:
        os.close(container_fd)

    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"
    assert bridge_called is False


def test_attempt_env_wrapper_refuses_post_manifest_first_rpath_shadow(
    tmp_path,
    monkeypatch,
):
    """A late @loader_path shadow may not outrank the attested runtime library."""

    runtime, runtime_manifest, _manifest = _runtime_install_fixture(tmp_path)
    binary_root = runtime / "bin"
    binary_root.chmod(0o700)
    shadow = binary_root / browser.RUNTIME_NODE_LIBRARY_NAME
    shadow.write_bytes(b"post-manifest first-rpath shadow")
    shadow.chmod(0o400)
    binary_root.chmod(0o500)
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    container_fd = os.open(
        runtime.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    os.set_inheritable(container_fd, True)
    bridge_called = False

    def must_not_start_bridge(**_kwargs):
        nonlocal bridge_called
        bridge_called = True
        return 0

    try:
        with pytest.raises(browser.BrowserReviewError) as raised:
            browser.launch_mcp_from_attempt_env(
                _attempt_launch_environment(
                    workspace=tmp_path,
                    artifact=artifact,
                    runtime=runtime,
                    runtime_manifest=runtime_manifest,
                    container_fd=container_fd,
                ),
                bridge_runner=must_not_start_bridge,
            )
    finally:
        os.close(container_fd)

    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"
    assert bridge_called is False


@pytest.mark.parametrize("descriptor_case", ["missing", "closed", "not-inheritable", "wrong"])
def test_attempt_env_wrapper_refuses_unbound_runtime_container_descriptor(
    tmp_path, monkeypatch, descriptor_case
):
    runtime, runtime_manifest, _manifest = _runtime_install_fixture(tmp_path)
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    environment = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": os.fspath(artifact),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "MASTERMIND_BROWSER_FIXTURE_B_URL": "http://127.0.0.1:48101/__mastermind_browser_visual_fixture__/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:48101",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:48102",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": os.fspath(runtime_manifest),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": hashlib.sha256(
            runtime_manifest.read_bytes()
        ).hexdigest(),
        "MASTERMIND_BROWSER_RUNTIME_ROOT": os.fspath(runtime),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": os.fspath(tmp_path),
        "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
    }
    descriptor: int | None = None
    if descriptor_case != "missing":
        descriptor = os.open(
            tmp_path if descriptor_case == "wrong" else runtime.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        environment["MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"] = str(descriptor)
        if descriptor_case == "closed":
            os.close(descriptor)
            descriptor = None
        elif descriptor_case != "not-inheritable":
            os.set_inheritable(descriptor, True)
    try:
        with pytest.raises(browser.BrowserReviewError) as error:
            browser.launch_mcp_from_attempt_env(environment)
    finally:
        if descriptor is not None:
            os.close(descriptor)

    assert error.value.state in {
        "BROWSER_MCP_START_FAILED",
        "BROWSER_RUNTIME_ATTESTATION_INVALID",
    }


def test_inner_runtime_stub_executes_from_held_container_after_whole_name_swap(
    tmp_path,
):
    stub = getattr(browser, "_ANCHORED_NODE_BOOTSTRAP", "")
    assert stub
    canonical = tmp_path / "worker-browser-b1"
    node = canonical / "runtime" / "bin" / "node"
    mcp = canonical / "runtime" / "node_modules" / "@playwright" / "mcp" / "cli.js"
    mcp.parent.mkdir(parents=True)
    node.parent.mkdir(parents=True)
    node.write_text(
        "#!/bin/sh\nprintf 'ORIGINAL:%s\\n' \"$1\"\n",
        encoding="utf-8",
    )
    node.chmod(0o500)
    mcp.write_text("fixture", encoding="utf-8")
    mcp.chmod(0o500)
    manifest = canonical / "runtime" / browser.RUNTIME_INSTALL_MANIFEST_NAME
    container_info = canonical.stat()
    node_info = node.stat()
    mcp_info = mcp.stat()
    manifest.write_bytes(
        browser._canonical_bytes(
            {
                "mcp": {
                    "executable": {
                        "gid": mcp_info.st_gid,
                        "mode": stat.S_IMODE(mcp_info.st_mode),
                        "path": os.fspath(mcp),
                        "sha256": hashlib.sha256(mcp.read_bytes()).hexdigest(),
                        "uid": mcp_info.st_uid,
                    }
                },
                "node": {
                    "executable": {
                        "gid": node_info.st_gid,
                        "mode": stat.S_IMODE(node_info.st_mode),
                        "path": os.fspath(node),
                        "sha256": hashlib.sha256(node.read_bytes()).hexdigest(),
                        "uid": node_info.st_uid,
                    }
                },
                "runtime_root": os.fspath(canonical / "runtime"),
                "runtime_container": {
                    "device": container_info.st_dev,
                    "gid": container_info.st_gid,
                    "inode": container_info.st_ino,
                    "mode": 0o500,
                    "uid": container_info.st_uid,
                }
            }
        )
        + b"\n"
    )
    manifest.chmod(0o400)
    for directory in (
        mcp.parent,
        mcp.parent.parent,
        mcp.parent.parent.parent,
        node.parent,
        canonical / "runtime",
    ):
        directory.chmod(0o500)
    canonical.chmod(0o500)
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    container_fd = os.open(
        canonical,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        captured = tmp_path / "worker-browser-b1.attested"
        canonical.rename(captured)
        replacement_node = canonical / "runtime" / "bin" / "node"
        replacement_node.parent.mkdir(parents=True)
        replacement_node.write_text(
            "#!/bin/sh\nprintf 'REPLACEMENT\\n'\n",
            encoding="utf-8",
        )
        replacement_node.chmod(0o500)
        result = subprocess.run(
            ["/usr/bin/python3", "-I", "-S", "-c", stub, "--isolated"],
            check=False,
            capture_output=True,
            text=True,
            env={
                "HOME": os.fspath(tmp_path),
                "LANG": "C",
                "LC_ALL": "C",
                "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD": str(container_fd),
                "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": manifest_digest,
                "NO_COLOR": "1",
                "PATH": "/usr/bin:/bin",
                "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers",
                "TMPDIR": os.fspath(tmp_path),
            },
            pass_fds=(container_fd,),
            timeout=10,
        )
    finally:
        os.close(container_fd)

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "ORIGINAL:runtime/node_modules/@playwright/mcp/cli.js\n"
    )
    assert "REPLACEMENT" not in result.stdout


def test_guard_binds_image_content_hash_to_confined_screenshot_bytes(tmp_path):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, "http://127.0.0.1:48101/")
    _guard_resize(guard, width=390, height=844)
    original = {
        "filename": "mobile.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)
    pixels = _png(390, 844)
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    upstream.write_bytes(pixels)
    guard.record_result(
        "browser_take_screenshot",
        original,
        {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "### Result\n"
                            "- [Screenshot of viewport]"
                            "(./page-2026-08-30T12-34-56-789Z.png)"
                        ),
                    },
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": base64.b64encode(pixels).decode("ascii"),
                    }
                ]
            }
        },
    )

    assert guard.evidence()["image_content_sha256"]["mobile.png"] == hashlib.sha256(
        pixels
    ).hexdigest()
    assert guard.evidence()["model_image_content_sha256"]["mobile.png"] == hashlib.sha256(
        pixels
    ).hexdigest()
    assert (artifact / "mobile.png").read_bytes() == pixels
    assert not upstream.exists()


def test_guard_binds_full_viewport_artifact_when_pinned_mcp_scales_model_image(
    tmp_path,
):
    """The pinned MCP scales message pixels but leaves the exact viewport file."""

    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, "http://127.0.0.1:48101/")
    _guard_resize(guard, width=1440, height=900)
    original = {
        "filename": "desktop.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    full_viewport = _png(1440, 900)
    upstream.write_bytes(full_viewport)
    model_visible = _png(1389, 868, color=b"\x01\x02\x03\xff")

    guard.record_result(
        "browser_take_screenshot",
        original,
        {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "### Result\n"
                            "- [Screenshot of viewport]"
                            "(./page-2026-08-30T12-34-56-789Z.png)"
                        ),
                    },
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": base64.b64encode(model_visible).decode("ascii"),
                    },
                ]
            }
        },
    )

    evidence = guard.evidence()
    assert (artifact / "desktop.png").read_bytes() == full_viewport
    assert evidence["image_content_sha256"]["desktop.png"] == hashlib.sha256(
        full_viewport
    ).hexdigest()
    assert evidence["model_image_content_sha256"]["desktop.png"] == hashlib.sha256(
        model_visible
    ).hexdigest()
    assert not upstream.exists()


def test_guard_refuses_screenshot_artifact_link_outside_attempt_root(tmp_path):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    outside = tmp_path / "page-2026-08-30T12-34-56-789Z.png"
    outside.write_bytes(_png(1440, 900))
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=1440, height=900)
    original = {
        "filename": "desktop.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "### Result\n"
                                "- [Screenshot of viewport]"
                                "(../page-2026-08-30T12-34-56-789Z.png)"
                            ),
                        },
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(
                                _png(1389, 868)
                            ).decode("ascii"),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"
    assert outside.exists()
    assert not (artifact / "desktop.png").exists()


@pytest.mark.parametrize(
    "result_line",
    (
        "forged-prefix - [Screenshot of viewport]"
        "(./page-2026-08-30T12-34-56-789Z.png)",
        "- [Screenshot of viewport]"
        "(./page-2026-08-30T12-34-56-789Z.png) forged-suffix",
    ),
)
def test_guard_refuses_embedded_screenshot_artifact_link(tmp_path, result_line):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    upstream.write_bytes(_png(390, 844))
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=390, height=844)
    original = {
        "filename": "mobile.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {"type": "text", "text": f"### Result\n{result_line}"},
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(_png(390, 844)).decode(
                                "ascii"
                            ),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"
    assert upstream.exists()
    assert not (artifact / "mobile.png").exists()


def test_guard_refuses_symlinked_upstream_screenshot_artifact(tmp_path):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png(1440, 900))
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    upstream.symlink_to(outside)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=1440, height=900)
    original = {
        "filename": "desktop.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "### Result\n"
                                "- [Screenshot of viewport]"
                                "(./page-2026-08-30T12-34-56-789Z.png)"
                            ),
                        },
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(
                                _png(1389, 868)
                            ).decode("ascii"),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"
    assert upstream.is_symlink()
    assert outside.exists()
    assert not (artifact / "desktop.png").exists()


def test_guard_refuses_wrong_size_full_viewport_artifact(tmp_path):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    upstream.write_bytes(_png(1440, 899))
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=1440, height=900)
    original = {
        "filename": "desktop.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "### Result\n"
                                "- [Screenshot of viewport]"
                                "(./page-2026-08-30T12-34-56-789Z.png)"
                            ),
                        },
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(
                                _png(1389, 868)
                            ).decode("ascii"),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_SCREENSHOT_FAILED"
    assert upstream.exists()
    assert not (artifact / "desktop.png").exists()


def test_guard_refuses_unscaled_model_image_that_differs_from_full_artifact(tmp_path):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    upstream.write_bytes(_png(390, 844))
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=390, height=844)
    original = {
        "filename": "mobile.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "### Result\n"
                                "- [Screenshot of viewport]"
                                "(./page-2026-08-30T12-34-56-789Z.png)"
                            ),
                        },
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(
                                _png(390, 844, color=b"\x01\x02\x03\xff")
                            ).decode("ascii"),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"
    assert upstream.exists()
    assert not (artifact / "mobile.png").exists()


def test_guard_refuses_replaced_attempt_artifact_directory(tmp_path):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    original_artifact = tmp_path / "original-attempt"
    artifact.rename(original_artifact)
    artifact.mkdir(mode=0o700)
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    upstream.write_bytes(_png(390, 844))
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=390, height=844)
    original = {
        "filename": "mobile.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "### Result\n"
                                "- [Screenshot of viewport]"
                                "(./page-2026-08-30T12-34-56-789Z.png)"
                            ),
                        },
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(_png(390, 844)).decode(
                                "ascii"
                            ),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"
    assert upstream.exists()
    assert not (artifact / "mobile.png").exists()
    assert original_artifact.exists()


def test_guard_refuses_artifact_root_swap_after_descriptor_write(
    tmp_path, monkeypatch
):
    import base64

    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    upstream = artifact / "page-2026-08-30T12-34-56-789Z.png"
    pixels = _png(390, 844)
    upstream.write_bytes(pixels)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    _guard_navigate(guard, f"{origin}/")
    _guard_resize(guard, width=390, height=844)
    original = {
        "filename": "mobile.png",
        "fullPage": False,
        "scale": "css",
        "type": "png",
    }
    guard.rewrite_call("browser_take_screenshot", original)

    original_fsync = browser.os.fsync
    directory_fsyncs = 0
    displaced = tmp_path / "displaced-attempt"

    def swap_after_destination_write(descriptor):
        nonlocal directory_fsyncs
        original_fsync(descriptor)
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
            if directory_fsyncs == 2:
                artifact.rename(displaced)
                artifact.mkdir(mode=0o700)
                (artifact / "mobile.png").write_bytes(pixels)

    monkeypatch.setattr(browser.os, "fsync", swap_after_destination_write)

    with pytest.raises(browser.BrowserReviewError) as raised:
        guard.record_result(
            "browser_take_screenshot",
            original,
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "### Result\n"
                                "- [Screenshot of viewport]"
                                "(./page-2026-08-30T12-34-56-789Z.png)"
                            ),
                        },
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(pixels).decode("ascii"),
                        },
                    ]
                }
            },
        )

    assert raised.value.state == "BROWSER_MCP_TOOL_REFUSED"
    assert (artifact / "mobile.png").read_bytes() == pixels
    assert (displaced / "mobile.png").read_bytes() == pixels


def test_stdio_bridge_interposes_before_official_mcp_and_persists_control_plane_evidence(
    tmp_path,
):
    fake = tmp_path / "fake_mcp.py"
    fake.write_text(
        textwrap.dedent(
            """
            import base64
            import json
            import struct
            import sys
            import zlib
            from pathlib import Path

            def chunk(kind, payload):
                return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)

            def png(width, height):
                scanline = b'\\x00' + (b'\\x00\\x00\\x00\\xff' * width)
                return b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(scanline * height)) + chunk(b'IEND', b'')

            pixels = png(1440, 900)
            message_pixels = png(1389, 868)
            for raw in sys.stdin.buffer:
                request = json.loads(raw)
                if request.get('method') == 'tools/call':
                    params = request['params']
                    if params['name'] == 'browser_take_screenshot':
                        assert 'filename' not in params['arguments']
                        Path('page-2026-08-30T12-34-56-789Z.png').write_bytes(pixels)
                        content = [
                            {'type': 'text', 'text': '### Result\\n- [Screenshot of viewport](./page-2026-08-30T12-34-56-789Z.png)'},
                            {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(message_pixels).decode('ascii')},
                        ]
                    else:
                        content = [{'type': 'text', 'text': 'ok'}]
                    result = {'content': content}
                else:
                    result = {}
                sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}, separators=(',', ':')) + '\\n')
                sys.stdout.flush()
            """
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "attempt"
    artifact.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "browser_navigate", "arguments": {"url": f"{origin}/"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "browser_resize", "arguments": {"width": 1440, "height": 900}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "browser_take_screenshot", "arguments": {"filename": "desktop.png", "fullPage": False, "scale": "css", "type": "png"}}},
    ]
    client_output = io.BytesIO()
    guard = browser.BrowserMcpToolGuard(
        origin=origin, artifact_dir=artifact, fixture_urls=_fixture_urls(origin)
    )
    completed = {
        request["params"]["name"]: threading.Event() for request in requests
    }
    original_record_result = guard.record_result

    def record_result_and_release(name, original_arguments, response):
        original_record_result(name, original_arguments, response)
        completed[name].set()

    guard.record_result = record_result_and_release

    def sequential_client_input():
        for request in requests:
            yield browser._canonical_bytes(request) + b"\n"
            assert completed[request["params"]["name"]].wait(2)

    assert browser.run_guarded_mcp_bridge(
        argv=(sys.executable, os.fspath(fake)),
        environment={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        guard=guard,
        stdin=sequential_client_input(),
        stdout=client_output,
        stderr=subprocess.DEVNULL,
    ) == 0

    evidence = json.loads(
        (artifact / browser._MCP_GUARD_EVIDENCE_FILE).read_text(encoding="utf-8")
    )
    assert evidence["cleanup_proven"] is True
    assert evidence["image_content_sha256"]["desktop.png"] == hashlib.sha256(
        (artifact / "desktop.png").read_bytes()
    ).hexdigest()
    assert b'"id":3' in client_output.getvalue()


def test_closed_attempt_receipt_binds_generation_workspace_security_and_cleanup(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "attempt-1"
    artifact_dir.mkdir(parents=True)
    png = artifact_dir / "desktop.png"
    png.write_bytes(_png(1440, 900))
    mobile_png = artifact_dir / "mobile.png"
    mobile_png.write_bytes(_png(390, 844, color=b"\x01\x02\x03\xff"))
    context = browser.BrowserAttemptContext(
        attempt_id="attempt-1",
        session_epoch_id="epoch-1",
        process_generation_id="generation-1",
        workspace=WorkspaceIdentity(
            workspace_path=os.fspath(tmp_path / "workspace"),
            base_sha="1" * 40,
            device=11,
            inode=22,
            uid=os.getuid(),
            gid=os.getgid(),
        ),
        artifact_dir=artifact_dir,
        devserver_manifest_digest="a" * 64,
        capability_manifest_digest="b" * 64,
        browser_profile_id="operator.browser.local-review.v1",
        browser_profile_digest="c" * 64,
        playwright_mcp_identity="@playwright/mcp",
        playwright_mcp_version="0.0.79",
        playwright_tool_schema_digest="d" * 64,
        runtime_manifest_digest="6" * 64,
        browser_revision="1237",
        browser_executable=os.fspath(tmp_path / "runtime" / "chromium"),
        browser_executable_sha256="e" * 64,
    )

    receipt = browser.seal_browser_review_receipt(
        context,
        local_origin="http://127.0.0.1:8787",
        mcp_guard={
            "relative_path": browser._MCP_GUARD_EVIDENCE_FILE,
            "schema_version": browser._MCP_GUARD_EVIDENCE_SCHEMA,
            "bytes": 4096,
            "sha256": "7" * 64,
        },
        screenshots=[
            browser.screenshot_artifact(
                artifact_dir,
                "desktop.png",
                viewport={"width": 1440, "height": 900},
            ),
            browser.screenshot_artifact(
                artifact_dir,
                "mobile.png",
                viewport={"width": 390, "height": 844},
            ),
        ],
        console_rows=[{"type": "warning", "text": "fixture warning"}],
        network_rows=[{"method": "GET", "url": "http://127.0.0.1:8787/", "status": 200}],
        egress_falsifiers={
            "external_http": "REFUSED",
            "external_https": "REFUSED",
            "external_redirect": "REFUSED",
            "external_subresource": "REFUSED",
            "external_fetch": "REFUSED",
            "external_websocket": "REFUSED",
            "file_url": "REFUSED",
            "proxy_override": "REFUSED",
        },
        visual_judgment={
            "source": "model_image_content",
            "fixture_nonce": "opaque-4f5c",
            "defective_variant": "B",
            "reason": "critical card is clipped on its right edge",
            "image_sha256": ["f" * 64, "0" * 64],
        },
        cleanup={
            "browser_absent": True,
            "mcp_absent": True,
            "proxy_absent": True,
            "devserver_absent": True,
            "uid_sweep_passed": True,
            "uid_sweep_digest": "9" * 64,
        },
        tracked_workspace_changes_after_review=False,
    )

    assert isinstance(receipt, browser.BrowserReviewReceipt)
    wire = receipt.to_wire()
    assert "receipt_digest" not in wire
    assert browser.browser_review_receipt(wire) == receipt
    assert receipt.digest == browser.canonical_browser_review_receipt_digest(receipt)
    assert wire["schema_version"] == "mastermind.browser_review_receipt/v1"
    assert wire["attempt_id"] == "attempt-1"
    assert wire["session_epoch_id"] == "epoch-1"
    assert wire["process_generation_id"] == "generation-1"
    assert wire["workspace"] == {
        "workspace_path": os.fspath(tmp_path / "workspace"),
        "base_sha": "1" * 40,
        "device": 11,
        "inode": 22,
        "uid": os.getuid(),
        "gid": os.getgid(),
    }
    assert wire["devserver"] == {
        "manifest_digest": "a" * 64,
        "local_origin": "http://127.0.0.1:8787",
    }
    assert wire["capability"] == {
        "manifest_digest": "b" * 64,
        "profile_id": "operator.browser.local-review.v1",
        "profile_digest": "c" * 64,
    }
    assert wire["playwright_mcp"] == {
        "identity": "@playwright/mcp",
        "version": "0.0.79",
        "tool_schema_digest": "d" * 64,
    }
    assert wire["browser"] == {
        "executable": os.fspath(tmp_path / "runtime" / "chromium"),
        "executable_sha256": "e" * 64,
        "revision": "1237",
        "runtime_manifest_digest": "6" * 64,
    }
    assert wire["external_egress_observed"] is False
    assert wire["tracked_workspace_changes_after_review"] is False
    assert wire["cleanup"]["uid_sweep_passed"] is True
    assert wire["artifacts"]["screenshots"][0]["relative_path"] == "desktop.png"
    assert wire["artifacts"]["console"]["observed"] is True
    assert wire["artifacts"]["network"]["observed"] is True
    assert wire["artifacts"]["mcp_guard"] == {
        "relative_path": browser._MCP_GUARD_EVIDENCE_FILE,
        "schema_version": browser._MCP_GUARD_EVIDENCE_SCHEMA,
        "bytes": 4096,
        "sha256": "7" * 64,
    }
    for field in ("console", "network"):
        hostile_rows = receipt.to_wire()
        hostile_rows["artifacts"][field] = {
            "bytes": 2,
            "observed": True,
            "rows": 0,
            "sha256": hashlib.sha256(b"[]").hexdigest(),
        }
        with pytest.raises(
            browser.BrowserReviewError, match=f"{field} evidence"
        ):
            browser.browser_review_receipt(hostile_rows)
        with pytest.raises(
            browser.BrowserReviewError, match=f"{field} rows"
        ):
            browser._bounded_rows(
                [],
                maximum_rows=(
                    browser.MAX_CONSOLE_ROWS
                    if field == "console"
                    else browser.MAX_NETWORK_ROWS
                ),
                field=field,
            )

    changed_guard = dict(wire)
    changed_guard["artifacts"] = dict(wire["artifacts"])
    changed_guard["artifacts"]["mcp_guard"] = dict(
        wire["artifacts"]["mcp_guard"]
    )
    changed_guard["artifacts"]["mcp_guard"]["sha256"] = "8" * 64
    changed_receipt = browser.browser_review_receipt(changed_guard)
    assert changed_receipt.digest != receipt.digest

    caller_owned_wire = receipt.to_wire()
    detached_receipt = browser.browser_review_receipt(caller_owned_wire)
    detached_digest = detached_receipt.digest
    caller_owned_wire["artifacts"]["mcp_guard"]["sha256"] = "8" * 64
    assert detached_receipt.artifacts["mcp_guard"]["sha256"] == "7" * 64
    assert detached_receipt.digest == detached_digest

    nested_wire = receipt.to_wire()
    immutable_receipt = browser.browser_review_receipt(nested_wire)
    immutable_digest = immutable_receipt.digest
    nested_wire["visual_judgment"]["image_sha256"][0] = "8" * 64
    nested_wire["viewports"][0]["width"] = 1
    assert immutable_receipt.visual_judgment["image_sha256"][0] == "f" * 64
    assert immutable_receipt.viewports[0]["width"] == 1440
    assert immutable_receipt.digest == immutable_digest
    with pytest.raises(TypeError):
        immutable_receipt.visual_judgment["image_sha256"][0] = "8" * 64
    with pytest.raises(TypeError):
        immutable_receipt.artifacts["mcp_guard"]["sha256"] = "8" * 64
    with pytest.raises(TypeError):
        immutable_receipt.viewports[0]["width"] = 1

    invalid_typed_receipt = replace(
        receipt,
        artifacts={
            key: value
            for key, value in receipt.artifacts.items()
            if key != "mcp_guard"
        },
    )
    with pytest.raises(browser.BrowserReviewError, match="artifacts receipt is not closed"):
        browser.canonical_browser_review_receipt_digest(invalid_typed_receipt)

    legacy_v1 = receipt.to_wire()
    legacy_v1["artifacts"].pop("mcp_guard")
    with pytest.raises(browser.BrowserReviewError, match="artifacts receipt is not closed"):
        browser.browser_review_receipt(legacy_v1)

    valid_guard = receipt.to_wire()["artifacts"]["mcp_guard"]
    hostile_guard_summaries = (
        {**valid_guard, "relative_path": "../browser-mcp-guard-evidence.json"},
        {**valid_guard, "schema_version": "mastermind.browser_mcp_guard_evidence/v1"},
        {**valid_guard, "bytes": True},
        {**valid_guard, "bytes": 0},
        {**valid_guard, "bytes": browser.MAX_TEXT_EVIDENCE_BYTES + 1},
        {**valid_guard, "sha256": "not-a-digest"},
        {**valid_guard, "unexpected": "field"},
    )
    for hostile_guard in hostile_guard_summaries:
        hostile_wire = receipt.to_wire()
        hostile_wire["artifacts"]["mcp_guard"] = hostile_guard
        with pytest.raises(browser.BrowserReviewError):
            browser.browser_review_receipt(hostile_wire)

    hostile = dict(wire)
    hostile["receipt_digest"] = "0" * 64
    with pytest.raises(browser.BrowserReviewError, match="fields are not closed"):
        browser.browser_review_receipt(hostile)


def test_receipt_refuses_oversize_console_instead_of_truncating(tmp_path):
    context = browser.BrowserAttemptContext(
        attempt_id="attempt-oversize",
        session_epoch_id="epoch-oversize",
        process_generation_id="generation-oversize",
        workspace=WorkspaceIdentity(
            workspace_path=os.fspath(tmp_path / "workspace"),
            base_sha="1" * 40,
            device=1,
            inode=2,
            uid=os.getuid(),
            gid=os.getgid(),
        ),
        artifact_dir=tmp_path,
        devserver_manifest_digest="a" * 64,
        capability_manifest_digest="b" * 64,
        browser_profile_id="operator.browser.local-review.v1",
        browser_profile_digest="c" * 64,
        playwright_mcp_identity="@playwright/mcp",
        playwright_mcp_version="0.0.79",
        playwright_tool_schema_digest="d" * 64,
        runtime_manifest_digest="6" * 64,
        browser_revision="1237",
        browser_executable=os.fspath(tmp_path / "chromium"),
        browser_executable_sha256="e" * 64,
    )
    rows = [{"type": "warning", "text": "x" * (browser.MAX_TEXT_EVIDENCE_BYTES + 1)}]

    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.seal_browser_review_receipt(
            context,
            local_origin="http://127.0.0.1:8787",
            mcp_guard={
                "relative_path": browser._MCP_GUARD_EVIDENCE_FILE,
                "schema_version": browser._MCP_GUARD_EVIDENCE_SCHEMA,
                "bytes": 4096,
                "sha256": "7" * 64,
            },
            screenshots=[],
            console_rows=rows,
            network_rows=[],
            egress_falsifiers={
                "external_http": "REFUSED",
                "external_https": "REFUSED",
                "external_redirect": "REFUSED",
                "external_subresource": "REFUSED",
                "external_fetch": "REFUSED",
                "external_websocket": "REFUSED",
                "file_url": "REFUSED",
                "proxy_override": "REFUSED",
            },
            visual_judgment={
                "source": "model_image_content",
                "fixture_nonce": "opaque-oversize",
                "defective_variant": "A",
                "reason": "critical card is clipped",
                "image_sha256": ["f" * 64, "0" * 64],
            },
            cleanup={
                "browser_absent": True,
                "mcp_absent": True,
                "proxy_absent": True,
                "devserver_absent": True,
                "uid_sweep_passed": True,
                "uid_sweep_digest": "9" * 64,
            },
            tracked_workspace_changes_after_review=False,
        )

    assert raised.value.state == "BROWSER_ARTIFACT_OVERSIZE"


def test_private_artifact_writer_refuses_replaced_parent_during_create(
    tmp_path, monkeypatch
):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    displaced = tmp_path / "displaced-attempt"
    target = artifact_root / "evidence.json"
    original_open = browser.os.open
    swapped = False

    def swap_parent_before_file_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and flags & os.O_CREAT:
            artifact_root.rename(displaced)
            artifact_root.mkdir(mode=0o700)
            swapped = True
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(browser.os, "open", swap_parent_before_file_open)

    with pytest.raises(browser.BrowserReviewError, match="write did not complete"):
        browser._write_private_bytes_once(target, b"sealed evidence")

    assert swapped is True
    assert (displaced / target.name).read_bytes() == b"sealed evidence"
    assert not (artifact_root / target.name).exists()


def test_generation_resource_holds_original_artifact_root_across_seal_reads(
    tmp_path,
):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    original_pixels = _png(390, 844)
    screenshot = artifact_root / "mobile.png"
    screenshot.write_bytes(original_pixels)
    screenshot.chmod(0o600)

    resource = object.__new__(browser.BrowserGenerationResource)
    resource._artifact_dir = artifact_root
    resource._artifact_dir_identity = browser.BrowserMcpToolGuard._directory_identity(
        artifact_root.lstat()
    )
    root_fd = resource._open_artifact_root_descriptor()
    displaced = tmp_path / "displaced-attempt"
    try:
        artifact_root.rename(displaced)
        artifact_root.mkdir(mode=0o700)
        replacement = artifact_root / "mobile.png"
        replacement.write_bytes(_png(390, 844, color=b"\x01\x02\x03\xff"))
        replacement.chmod(0o600)

        row = browser._screenshot_artifact_at(
            root_fd, "mobile.png", viewport={"width": 390, "height": 844}
        )
        assert row["sha256"] == hashlib.sha256(original_pixels).hexdigest()
        with pytest.raises(
            browser.BrowserReviewError, match="artifact root identity changed"
        ):
            resource._require_artifact_root_descriptor(root_fd)
    finally:
        os.close(root_fd)


def test_guard_interaction_requires_a_successful_structured_snapshot(tmp_path):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin,
        artifact_dir=artifact_root,
        fixture_urls=_fixture_urls(origin),
    )
    product = f"{origin}/"
    guard.rewrite_call("browser_navigate", {"url": product})
    guard.record_result(
        "browser_navigate",
        {"url": product},
        {"result": {"content": [{"type": "text", "text": "navigated"}]}},
    )

    with pytest.raises(browser.BrowserReviewError, match="structured snapshot"):
        guard.rewrite_call(
            "browser_hover", {"target": "Critical portfolio card"}
        )

    guard.rewrite_call("browser_snapshot", {})
    guard.record_result(
        "browser_snapshot",
        {},
        {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "- banner 'Mastermind X Chairman Control Room'\n  - button 'Theme'",
                    }
                ]
            }
        },
    )
    assert guard.rewrite_call(
        "browser_hover", {"element": "Theme button", "target": "theme-ref"}
    ) == {"element": "Theme button", "target": "theme-ref"}
    guard.record_result(
        "browser_hover",
        {"element": "Theme button", "target": "theme-ref"},
        {"result": {"content": [{"type": "text", "text": "hovered"}]}},
    )
    assert guard.evidence()["calls"] == {
        "browser_hover": 1,
        "browser_navigate": 1,
        "browser_snapshot": 1,
    }


def test_guard_refuses_mcp_is_error_results_and_does_not_unlock_interaction(tmp_path):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin,
        artifact_dir=artifact_root,
        fixture_urls=_fixture_urls(origin),
    )
    product = f"{origin}/"
    fixture_a = _fixture_urls(origin)["A"]

    guard.rewrite_call("browser_navigate", {"url": product})
    guard.record_result(
        "browser_navigate",
        {"url": product},
        {
            "result": {
                "content": [{"type": "text", "text": "product navigated"}],
                "isError": False,
            }
        },
    )
    guard.rewrite_call("browser_navigate", {"url": fixture_a})
    with pytest.raises(browser.BrowserReviewError, match="successful result"):
        guard.record_result(
            "browser_navigate",
            {"url": fixture_a},
            {
                "result": {
                    "content": [{"type": "text", "text": "navigation failed"}],
                    "isError": True,
                }
            },
        )

    with pytest.raises(
        browser.BrowserReviewError,
        match="successfully established page",
    ):
        guard.rewrite_call("browser_snapshot", {})

    guard.rewrite_call("browser_navigate", {"url": product})
    guard.record_result(
        "browser_navigate",
        {"url": product},
        {"result": {"content": [{"type": "text", "text": "navigated"}]}},
    )
    guard.rewrite_call("browser_snapshot", {})
    guard.record_result(
        "browser_snapshot",
        {},
        {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "- region 'Product control room'",
                    }
                ],
                "isError": False,
            }
        },
    )

    hover = {"element": "Theme button", "target": "theme-ref"}
    assert guard.rewrite_call("browser_hover", hover) == hover
    _record_guard_text_success(guard, "browser_hover", hover, text="hovered")
    assert guard.evidence()["calls"] == {
        "browser_hover": 1,
        "browser_navigate": 2,
        "browser_snapshot": 1,
    }


def test_guard_does_not_commit_failed_or_pending_browser_state_transitions(tmp_path):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin,
        artifact_dir=artifact_root,
        fixture_urls=_fixture_urls(origin),
    )
    fixtures = _fixture_urls(origin)

    product = f"{origin}/"
    guard.rewrite_call("browser_navigate", {"url": product})
    guard.record_result(
        "browser_navigate",
        {"url": product},
        {"result": {"content": [{"type": "text", "text": "navigated"}]}},
    )
    guard.rewrite_call("browser_snapshot", {})
    guard.record_result(
        "browser_snapshot",
        {},
        {
            "result": {
                "content": [{"type": "text", "text": "- button 'Theme'"}]
            }
        },
    )

    # Merely forwarding a later navigation invalidates the snapshot binding;
    # the official MCP has not yet proven which page it actually established.
    guard.rewrite_call("browser_navigate", {"url": fixtures["B"]})
    with pytest.raises(browser.BrowserReviewError, match="product-page-only"):
        guard.rewrite_call(
            "browser_hover", {"target": "Critical portfolio card"}
        )
    guard.record_result(
        "browser_navigate",
        {"url": fixtures["B"]},
        {"result": {"content": [{"type": "text", "text": "navigated"}]}},
    )

    guard.rewrite_call("browser_resize", {"width": 1440, "height": 900})
    with pytest.raises(browser.BrowserReviewError, match="successful result"):
        guard.record_result(
            "browser_resize",
            {"width": 1440, "height": 900},
            {
                "result": {
                    "content": [{"type": "text", "text": "resize failed"}],
                    "isError": True,
                }
            },
        )
    with pytest.raises(browser.BrowserReviewError, match="exact page and viewport"):
        guard.rewrite_call(
            "browser_take_screenshot",
            {
                "filename": "desktop.png",
                "fullPage": False,
                "scale": "css",
                "type": "png",
            },
        )


def test_guard_binds_successful_snapshot_to_current_navigation_epoch(tmp_path):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    origin = "http://127.0.0.1:48101"
    guard = browser.BrowserMcpToolGuard(
        origin=origin,
        artifact_dir=artifact_root,
        fixture_urls=_fixture_urls(origin),
    )
    fixtures = _fixture_urls(origin)
    product = f"{origin}/"

    guard.rewrite_call("browser_navigate", {"url": product})
    _record_guard_text_success(
        guard, "browser_navigate", {"url": product}, text="navigated"
    )
    guard.rewrite_call("browser_snapshot", {})
    _record_guard_text_success(
        guard, "browser_snapshot", {}, text="- button 'Theme'"
    )
    guard.rewrite_call("browser_navigate", {"url": fixtures["B"]})
    _record_guard_text_success(
        guard,
        "browser_navigate",
        {"url": fixtures["B"]},
        text="navigated",
    )

    with pytest.raises(browser.BrowserReviewError, match="product-page-only"):
        guard.rewrite_call(
            "browser_hover", {"target": "Critical portfolio card"}
        )

    guard.rewrite_call("browser_navigate", {"url": product})
    _record_guard_text_success(
        guard, "browser_navigate", {"url": product}, text="navigated"
    )
    guard.rewrite_call("browser_snapshot", {})
    _record_guard_text_success(
        guard, "browser_snapshot", {}, text="- button 'Theme'"
    )
    assert guard.rewrite_call(
        "browser_hover", {"element": "Theme button", "target": "theme-ref"}
    ) == {"element": "Theme button", "target": "theme-ref"}


def test_mcp_guard_evidence_requires_positive_closed_review_observations(tmp_path):
    artifact_root = tmp_path / "attempt"
    artifact_root.mkdir(mode=0o700)
    resource = object.__new__(browser.BrowserGenerationResource)
    resource._artifact_dir = artifact_root
    resource._artifact_dir_identity = browser.BrowserMcpToolGuard._directory_identity(
        artifact_root.lstat()
    )
    required_calls = {
        "browser_console_messages": 1,
        "browser_hover": 1,
        "browser_navigate": 3,
        "browser_network_requests": 1,
        "browser_resize": 3,
        "browser_snapshot": 1,
        "browser_take_screenshot": 4,
    }
    evidence = {
        "bridge_exit_code": 0,
        "calls": required_calls,
        "cleanup_proven": True,
        "console_rows": [
            {
                "bytes": 2,
                "content_sha256": "a" * 64,
                "tool": "browser_console_messages",
            }
        ],
        "egress_falsifiers": {
            "file_url": "REFUSED",
            "proxy_override": "REFUSED",
        },
        "image_content_sha256": {
            name: "b" * 64
            for name in (
                "desktop.png",
                "mobile.png",
                "visual-a.png",
                "visual-b.png",
            )
        },
        "interaction": {"page_class": "product", "tool": "browser_hover"},
        "model_image_content_sha256": {
            name: "c" * 64
            for name in (
                "desktop.png",
                "mobile.png",
                "visual-a.png",
                "visual-b.png",
            )
        },
        "network_rows": [
            {
                "bytes": 2,
                "content_sha256": "d" * 64,
                "tool": "browser_network_requests",
            }
        ],
        "schema_version": browser._MCP_GUARD_EVIDENCE_SCHEMA,
        "screenshots": [
            "desktop.png",
            "mobile.png",
            "visual-a.png",
            "visual-b.png",
        ],
    }
    guard_path = artifact_root / browser._MCP_GUARD_EVIDENCE_FILE

    def write_guard(value):
        guard_path.write_bytes(browser._canonical_bytes(value))
        guard_path.chmod(0o600)

    root_fd = resource._open_artifact_root_descriptor()
    try:
        write_guard(evidence)
        observed, _summary = resource._attempt_evidence(root_fd)
        assert observed["calls"] == required_calls

        hostile_values = []
        for field in required_calls:
            missing = json.loads(json.dumps(evidence))
            missing["calls"].pop(field)
            hostile_values.append(missing)
        malformed = json.loads(json.dumps(evidence))
        malformed["calls"]["browser_snapshot"] = True
        hostile_values.append(malformed)
        no_console = json.loads(json.dumps(evidence))
        no_console["console_rows"] = []
        hostile_values.append(no_console)
        no_network = json.loads(json.dumps(evidence))
        no_network["network_rows"] = []
        hostile_values.append(no_network)
        extra_interaction = json.loads(json.dumps(evidence))
        extra_interaction["calls"]["browser_click"] = 1
        hostile_values.append(extra_interaction)
        fixture_interaction = json.loads(json.dumps(evidence))
        fixture_interaction["interaction"]["page_class"] = "fixture-a"
        hostile_values.append(fixture_interaction)
        click_interaction = json.loads(json.dumps(evidence))
        click_interaction["interaction"]["tool"] = "browser_click"
        hostile_values.append(click_interaction)

        for hostile in hostile_values:
            write_guard(hostile)
            with pytest.raises(
                browser.BrowserReviewError, match="MCP guard evidence"
            ):
                resource._attempt_evidence(root_fd)
    finally:
        os.close(root_fd)


def test_reviewed_control_room_manifest_is_closed_and_workspace_bound(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    (workspace / "scripts" / "chairman_control_room.py").write_text("# fixture\n")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "mastermind.devserver_resource/v1",
                "resource_id": "chairman-control-room-local",
                "cwd": ".",
                "argv": [
                    "/usr/bin/python3",
                    "scripts/chairman_control_room.py",
                    "--port",
                    "{port}",
                    "--repo-root",
                    ".",
                    "--compose-timeout",
                    "240",
                ],
                "host": "127.0.0.1",
                "readiness_path": "/",
                "readiness_timeout_seconds": 300,
                "shutdown_grace_seconds": 5,
                "allowed_generated_paths": [],
            }
        )
    )

    manifest = browser.load_devserver_manifest(manifest_path, workspace)

    assert manifest.cwd == workspace.resolve()
    assert manifest.argv_for_port(48123) == (
        "/usr/bin/python3",
        "scripts/chairman_control_room.py",
        "--port",
        "48123",
        "--repo-root",
        ".",
        "--compose-timeout",
        "240",
    )
    assert len(manifest.digest) == 64
    hostile = json.loads(manifest_path.read_text())
    hostile["command"] = "sh -c whoami"
    manifest_path.write_text(json.dumps(hostile))
    with pytest.raises(browser.BrowserReviewError) as raised:
        browser.load_devserver_manifest(manifest_path, workspace)
    assert raised.value.state == "DEVSERVER_MANIFEST_INVALID"


def test_generation_resource_owns_devserver_proxy_artifacts_and_post_sweep_receipt(
    tmp_path, monkeypatch,
):
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    (workspace / "config").mkdir()
    (workspace / "scripts" / "chairman_control_room.py").write_text(
        textwrap.dedent(
            """
            import argparse
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

            parser = argparse.ArgumentParser()
            parser.add_argument('--port', type=int, required=True)
            parser.add_argument('--repo-root')
            parser.add_argument('--compose-timeout')
            args = parser.parse_args()
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = b'<title>Chairman Control Room</title>'
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                def log_message(self, *_args):
                    pass
            ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
            """
        ),
        encoding="utf-8",
    )
    manifest_raw = {
        "schema_version": "mastermind.devserver_resource/v1",
        "resource_id": "chairman-control-room-local",
        "cwd": ".",
        "argv": [
            "/usr/bin/python3",
            "scripts/chairman_control_room.py",
            "--port",
            "{port}",
            "--repo-root",
            ".",
            "--compose-timeout",
            "240",
        ],
        "host": "127.0.0.1",
        "readiness_path": "/",
        "readiness_timeout_seconds": 300,
        "shutdown_grace_seconds": 5,
        "allowed_generated_paths": [],
    }
    manifest_path = workspace / "config" / "worker_browser_b1_control_room_devserver.json"
    manifest_path.write_text(json.dumps(manifest_raw), encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "fixture"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "scripts", "config"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=workspace, check=True, capture_output=True, text=True
    ).stdout.strip()
    info = workspace.stat()
    identity = WorkspaceIdentity(
        os.fspath(workspace.resolve()), head, info.st_dev, info.st_ino, info.st_uid, info.st_gid
    )
    runtime, runtime_manifest, runtime_identity = _runtime_install_fixture(tmp_path)
    chromium = Path(runtime_identity["browser"]["executable"]["path"])
    artifact_root = tmp_path / "artifacts"
    resource_grant = SimpleNamespace(
        resource_id="worker-browser-b1-local",
        manifest_path="config/worker_browser_b1_control_room_devserver.json",
        manifest_digest=browser._canonical_digest(manifest_raw),
        runtime_root=os.fspath(runtime),
        runtime_manifest_path=os.fspath(runtime_manifest),
        runtime_manifest_digest=hashlib.sha256(runtime_manifest.read_bytes()).hexdigest(),
        artifact_root=os.fspath(artifact_root),
        browser="chromium",
        browser_revision="1237",
        grant_digest="a" * 64,
    )
    mcp_grant = SimpleNamespace(
        capability_id="playwright-worker-browser-b1",
        server_identity="playwright",
        server_version="1.63.0-alpha-2026-08-05",
        tool_schema_digest="b" * 64,
        command=capabilities.WORKER_BROWSER_MCP_COMMAND,
        args=capabilities.WORKER_BROWSER_MCP_ARGS,
    )
    profile = SimpleNamespace(
        profile_id="operator.browser.local-review.v1",
        profile_digest="c" * 64,
        resource_grants=(resource_grant,),
        mcp_server_grants=(mcp_grant,),
    )
    requested = SimpleNamespace(workspace=identity, capabilities=CapabilityManifest())
    epoch = SessionEpochRef("epoch-resource", "attempt-resource", "worker-a", 1)
    generation = ProcessGenerationRef("generation-resource", "epoch-resource", 1, "worker-a")
    resource = browser.BrowserGenerationResource(
        workspace=workspace,
        requested=requested,
        epoch=epoch,
        generation=generation,
        profile=profile,
    )

    resource.start()
    environment = resource.environment
    prompt_suffix = resource.turn_prompt_suffix()
    assert "structured snapshot" in prompt_suffix
    assert "exactly one harmless browser_hover" in prompt_suffix
    assert "product Theme button" in prompt_suffix
    assert set(environment) == browser._BROWSER_ENV_KEYS
    proxy = browser.LoopbackEnforcingProxy  # explicit positive ownership control
    assert proxy is not None
    artifact_dir = Path(environment["MASTERMIND_BROWSER_ARTIFACT_DIR"])
    pngs = {
        "desktop.png": _png(1440, 900),
        "mobile.png": _png(390, 844, color=b"\x01\x02\x03\xff"),
        "visual-a.png": _png(900, 600, color=b"\x04\x05\x06\xff"),
        "visual-b.png": _png(900, 600, color=b"\x07\x08\x09\xff"),
    }
    for name, payload in pngs.items():
        screenshot = artifact_dir / name
        screenshot.write_bytes(payload)
        screenshot.chmod(0o600)

    # A model-authored convenience file is deliberately present and false.  It
    # cannot satisfy the resource; only guard-observed transport evidence can.
    (artifact_dir / browser._ATTEMPT_EVIDENCE_FILE).write_text(
        json.dumps({"visual_judgment": {"defective_variant": "WRONG"}}),
        encoding="utf-8",
    )
    guard_evidence = {
        "bridge_exit_code": 0,
        "calls": {
            "browser_console_messages": 1,
            "browser_hover": 1,
            "browser_navigate": 3,
            "browser_network_requests": 1,
            "browser_resize": 3,
            "browser_snapshot": 1,
            "browser_take_screenshot": 4,
        },
        "cleanup_proven": True,
        "console_rows": [{"bytes": 2, "content_sha256": "a" * 64, "tool": "browser_console_messages"}],
        "egress_falsifiers": {"file_url": "REFUSED", "proxy_override": "REFUSED"},
        "image_content_sha256": {
            name: hashlib.sha256(payload).hexdigest() for name, payload in pngs.items()
        },
        "interaction": {"page_class": "product", "tool": "browser_hover"},
        "model_image_content_sha256": {
            name: hashlib.sha256(payload).hexdigest() for name, payload in pngs.items()
        },
        "network_rows": [{"bytes": 2, "content_sha256": "b" * 64, "tool": "browser_network_requests"}],
        "schema_version": browser._MCP_GUARD_EVIDENCE_SCHEMA,
        "screenshots": sorted(pngs),
    }
    guard_path = artifact_dir / browser._MCP_GUARD_EVIDENCE_FILE
    guard_raw = b"\n " + browser._canonical_bytes(guard_evidence) + b" \n"
    guard_path.write_bytes(guard_raw)
    guard_path.chmod(0o600)

    hostile = {
        "external_http": b"GET http://external-http.invalid/b1 HTTP/1.1\r\nHost: external-http.invalid\r\nConnection: close\r\n\r\n",
        "external_https": b"CONNECT external-https.invalid:443 HTTP/1.1\r\nHost: external-https.invalid:443\r\nConnection: close\r\n\r\n",
        "external_redirect": b"GET http://redirect.invalid/b1 HTTP/1.1\r\nHost: redirect.invalid\r\nConnection: close\r\n\r\n",
        "external_subresource": b"GET http://subresource.invalid/b1 HTTP/1.1\r\nHost: subresource.invalid\r\nConnection: close\r\n\r\n",
        "external_fetch": b"GET http://fetch.invalid/b1 HTTP/1.1\r\nHost: fetch.invalid\r\nConnection: close\r\n\r\n",
        "external_websocket": b"GET http://websocket.invalid/b1 HTTP/1.1\r\nHost: websocket.invalid\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n",
    }
    for request in hostile.values():
        assert _raw_proxy_request(
            environment["MASTERMIND_BROWSER_PROXY_URL"], request
        ).startswith(b"HTTP/1.1 403")

    visual = {
        "defective_variant": resource._visual_fixture.defective_variant,
        "fixture_nonce": environment["MASTERMIND_BROWSER_FIXTURE_NONCE"],
        "reason": "the critical portfolio card is visibly clipped off canvas",
        "schema_version": "mastermind.browser_visual_judgment/v1",
        "source": "model_image_content",
    }
    resource.observe_canonical_result(
        browser._canonical_bytes(
            {"current_state": browser._canonical_bytes(visual).decode("utf-8")}
        ).decode("utf-8")
    )
    resource.stop()
    sweep = UIDSweepReceipt(
        schema_version=UID_SWEEP_SCHEMA_VERSION,
        observed_at="2026-08-29T00:00:00+00:00",
        reason="operator_terminal",
        worker_uid=os.geteuid(),
        broker_pid=os.getpid(),
        residual_pids_before=(),
        residual_pids_after=(),
        signal_name="SIGKILL",
        signal_sent=False,
        quiescent_observations=2,
    )

    receipt = resource.seal_after_uid_sweep(sweep)

    assert receipt.attempt_id == "attempt-resource"
    assert receipt.process_generation_id == "generation-resource"
    assert receipt.cleanup["uid_sweep_passed"] is True
    assert receipt.visual_judgment["defective_variant"] == visual["defective_variant"]
    assert len(receipt.artifacts["screenshots"]) == 4
    assert receipt.artifacts["mcp_guard"] == {
        "relative_path": browser._MCP_GUARD_EVIDENCE_FILE,
        "schema_version": browser._MCP_GUARD_EVIDENCE_SCHEMA,
        "bytes": len(guard_path.read_bytes()),
        "sha256": hashlib.sha256(guard_path.read_bytes()).hexdigest(),
    }
    changed_guard_evidence = json.loads(json.dumps(guard_evidence))
    changed_guard_evidence["model_image_content_sha256"]["desktop.png"] = "8" * 64
    changed_guard_bytes = browser._canonical_bytes(changed_guard_evidence)
    assert hashlib.sha256(changed_guard_bytes).hexdigest() != (
        receipt.artifacts["mcp_guard"]["sha256"]
    )
    changed_wire = receipt.to_wire()
    changed_wire["artifacts"]["mcp_guard"]["bytes"] = len(changed_guard_bytes)
    changed_wire["artifacts"]["mcp_guard"]["sha256"] = hashlib.sha256(
        changed_guard_bytes
    ).hexdigest()
    assert browser.browser_review_receipt(changed_wire).digest != receipt.digest
    assert receipt.browser["runtime_manifest_digest"] == (
        resource_grant.runtime_manifest_digest
    )
    assert receipt.browser["revision"] == "1237"
    persisted = browser.load_persisted_browser_review_receipt(
        generation, artifact_root=artifact_root
    )
    assert persisted == receipt
    assert persisted.digest == receipt.digest

    receipt_path = artifact_dir / browser._RECEIPT_FILE
    replacement_path = artifact_dir / "replacement-browser-review-receipt.json"
    replacement_wire = receipt.to_wire()
    replacement_wire["browser"]["executable_sha256"] = "e" * 64
    replacement_path.write_bytes(
        browser._canonical_bytes(replacement_wire) + b"\n"
    )
    replacement_path.chmod(0o600)
    original_lstat = Path.lstat
    original_stat = browser.os.stat
    swapped_receipt = False

    def swap_receipt_once():
        nonlocal swapped_receipt
        if not swapped_receipt:
            os.replace(replacement_path, receipt_path)
            swapped_receipt = True

    def lstat_then_swap(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if Path(path) == receipt_path:
            swap_receipt_once()
        return info

    def stat_then_swap(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        if (
            path == browser._RECEIPT_FILE
            and kwargs.get("dir_fd") is not None
            and kwargs.get("follow_symlinks") is False
        ):
            swap_receipt_once()
        return info

    monkeypatch.setattr(Path, "lstat", lstat_then_swap)
    monkeypatch.setattr(browser.os, "stat", stat_then_swap)
    with pytest.raises(
        browser.BrowserReviewError,
        match="persisted browser receipt is unsafe",
    ):
        browser.load_persisted_browser_review_receipt(
            generation, artifact_root=artifact_root
        )
    assert swapped_receipt is True

    # Seal performs a fresh use-time attestation.  Even a coordinated rewrite
    # of a runtime file plus its self-signed manifest remains outside the
    # independently reviewed ResourceGrant digest and must fail closed.
    node = Path(runtime_identity["node"]["executable"]["path"])
    node.chmod(0o700)
    node.write_bytes(node.read_bytes() + b" coordinated tamper")
    node.chmod(0o500)
    runtime_identity["node"]["executable"]["sha256"] = hashlib.sha256(
        node.read_bytes()
    ).hexdigest()
    runtime_manifest.chmod(0o600)
    runtime_manifest.write_bytes(browser._canonical_bytes(runtime_identity) + b"\n")
    runtime_manifest.chmod(0o400)
    with pytest.raises(browser.BrowserReviewError) as raised:
        resource.seal_after_uid_sweep(sweep)
    assert raised.value.state == "BROWSER_RUNTIME_ATTESTATION_INVALID"

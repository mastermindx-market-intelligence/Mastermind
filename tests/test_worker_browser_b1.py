"""Worker Browser B1: one isolated official-Playwright-MCP review vertical."""
from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from control_plane import worker_browser_b1 as browser


def _fake_mcp(
    tmp_path: Path,
    *,
    snapshot_bytes: int = 24,
    screenshots_follow_cwd: bool = False,
    create_profile: bool = False,
) -> tuple[str, ...]:
    script = tmp_path / "fake_playwright_mcp.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import base64
            import json
            import pathlib
            import sys

            args = sys.argv[1:]
            output_dir = pathlib.Path(args[args.index('--output-dir') + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            screenshot_dir = pathlib.Path.cwd() if {screenshots_follow_cwd!r} else output_dir
            if {create_profile!r}:
                profile = output_dir / 'playwright_fake_profile'
                profile.mkdir()
                (profile / 'Cookies').write_bytes(b'ephemeral')
            calls = []
            png = base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
            )

            def reply(request, result):
                print(json.dumps({{'jsonrpc': '2.0', 'id': request['id'], 'result': result}}, separators=(',', ':')), flush=True)

            for line in sys.stdin:
                request = json.loads(line)
                method = request.get('method')
                if method == 'initialize':
                    reply(request, {{'protocolVersion': '2025-06-18', 'capabilities': {{'tools': {{}}}}, 'serverInfo': {{'name': 'Playwright', 'version': '1.63.0-alpha-2026-08-05'}}}})
                elif method == 'tools/list':
                    reply(request, {{'tools': [{{'name': name}} for name in {sorted(browser.ALLOWED_TOOLS)!r}]}})
                elif method == 'tools/call':
                    name = request['params']['name']
                    arguments = request['params']['arguments']
                    calls.append({{'name': name, 'arguments': arguments}})
                    (output_dir / 'calls.json').write_text(json.dumps(calls), encoding='utf-8')
                    if name == 'browser_take_screenshot':
                        (screenshot_dir / arguments['filename']).write_bytes(png)
                        text = 'Saved screenshot to ' + arguments['filename']
                    elif name == 'browser_snapshot':
                        text = 'S' * {snapshot_bytes}
                    elif name == 'browser_console_messages':
                        text = 'console clean'
                    elif name == 'browser_network_requests':
                        text = '[GET] http://127.0.0.1:8787/ => [200] OK'
                    else:
                        text = 'ok'
                    reply(request, {{'content': [{{'type': 'text', 'text': text}}]}})
                    if name == 'browser_close':
                        break
            """
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return (sys.executable, os.fspath(script))


def _config(tmp_path: Path, **overrides) -> browser.BrowserRunConfig:
    has_command_override = "command_override" in overrides
    command_override = overrides.pop("command_override", None)
    values = {
        "origin": "http://127.0.0.1:8787",
        "repo_root": tmp_path,
        "runtime_root": tmp_path / "runtime",
        "artifact_root": tmp_path / "artifacts",
        "command_override": command_override if has_command_override else _fake_mcp(tmp_path),
        "timeout_seconds": 10.0,
        "max_text_bytes": 32,
    }
    values.update(overrides)
    return browser.BrowserRunConfig(**values)


def test_build_mcp_argv_is_exact_pinned_isolated_and_has_no_identity_import(tmp_path):
    config = _config(tmp_path, command_override=None)

    argv = browser.build_mcp_argv(config, tmp_path / "output")

    assert argv == [
        os.fspath(tmp_path / "runtime" / "node_modules" / ".bin" / "playwright-mcp"),
        "--isolated",
        "--headless",
        "--browser",
        "chrome",
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


def test_real_stdio_flow_is_closed_bounded_and_returns_two_hashed_screenshots(tmp_path):
    coordinator = browser.BrowserReviewCoordinator(_config(tmp_path, max_text_bytes=12))

    receipt = coordinator.run()

    assert receipt["schema"] == "mastermind.worker_browser_b1.receipt.v1"
    assert receipt["ok"] is True
    assert receipt["state"] == "COMPLETE"
    assert receipt["origin"] == "http://127.0.0.1:8787"
    assert receipt["runtime"]["package"] == "@playwright/mcp"
    assert receipt["runtime"]["version"] == "0.0.79"
    assert len(receipt["evidence"]["snapshot"].encode()) <= 12
    assert len(receipt["evidence"]["console"].encode()) <= 12
    assert len(receipt["evidence"]["network"].encode()) <= 12
    assert [(row["name"], row["viewport"]) for row in receipt["screenshots"]] == [
        ("desktop.png", {"width": 1440, "height": 900}),
        ("mobile.png", {"width": 390, "height": 844}),
    ]
    for screenshot in receipt["screenshots"]:
        assert screenshot["bytes"] > 0
        assert len(screenshot["sha256"]) == 64
        assert coordinator.read_artifact(screenshot["name"]).startswith(b"\x89PNG")
    assert receipt["cleanup"] == {
        "browser_close_requested": True,
        "process_group_absent": True,
        "profile_absent": True,
        "workspace_clean": True,
    }

    calls = json.loads((Path(receipt["artifact_dir"]) / "calls.json").read_text(encoding="utf-8"))
    assert [row["name"] for row in calls] == [
        "browser_navigate",
        "browser_snapshot",
        "browser_console_messages",
        "browser_network_requests",
        "browser_resize",
        "browser_take_screenshot",
        "browser_resize",
        "browser_take_screenshot",
        "browser_close",
    ]
    assert calls[0]["arguments"] == {"url": "http://127.0.0.1:8787"}
    assert calls[5]["arguments"] == {"filename": "desktop.png", "fullPage": True, "scale": "css", "type": "png"}
    assert calls[7]["arguments"] == {"filename": "mobile.png", "fullPage": True, "scale": "css", "type": "png"}
    assert all(row["name"] in browser.ALLOWED_TOOLS for row in calls)


def test_named_official_screenshots_resolve_inside_private_run_cwd_not_repo(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    config = _config(
        tmp_path,
        repo_root=repo_root,
        command_override=_fake_mcp(
            tmp_path, screenshots_follow_cwd=True, create_profile=True
        ),
    )

    receipt = browser.BrowserReviewCoordinator(config).run()

    assert receipt["state"] == "COMPLETE"
    assert not (repo_root / "desktop.png").exists()
    assert not (repo_root / "mobile.png").exists()
    artifact_dir = Path(receipt["artifact_dir"])
    assert not [path for path in artifact_dir.iterdir() if path.is_dir()]
    assert receipt["cleanup"]["profile_absent"] is True


def test_only_fixed_loopback_origin_is_accepted(tmp_path):
    for origin in (
        "https://mastermind-x.com",
        "http://localhost:8787",
        "http://127.0.0.1",
        "http://127.0.0.1:8787/path",
        "http://127.0.0.1:8787?query=1",
    ):
        with pytest.raises(ValueError, match="exact loopback origin"):
            browser.BrowserReviewCoordinator(_config(tmp_path, origin=origin))


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


def test_cleanup_uncertain_is_terminally_refused_and_blocks_second_launch(tmp_path):
    calls = 0

    def unclean(_config):
        nonlocal calls
        calls += 1
        return {
            "schema": "mastermind.worker_browser_b1.receipt.v1",
            "ok": False,
            "state": "CLEANUP_UNCERTAIN",
            "cleanup": {"process_group_absent": False},
        }

    coordinator = browser.BrowserReviewCoordinator(_config(tmp_path), run_fn=unclean)
    first = coordinator.run()
    second = coordinator.run()

    assert first["state"] == "CLEANUP_UNCERTAIN"
    assert second == {
        "schema": "mastermind.worker_browser_b1.receipt.v1",
        "ok": False,
        "state": "BLOCKED_CLEANUP_UNCERTAIN",
        "detail": "the prior browser process group is not proven absent",
    }
    assert calls == 1


def test_single_flight_refuses_concurrent_run(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def slow(_config):
        entered.set()
        assert release.wait(5)
        return {"schema": "mastermind.worker_browser_b1.receipt.v1", "ok": True, "state": "COMPLETE", "cleanup": {"process_group_absent": True}}

    coordinator = browser.BrowserReviewCoordinator(_config(tmp_path), run_fn=slow)
    result: list[dict] = []
    thread = threading.Thread(target=lambda: result.append(coordinator.run()))
    thread.start()
    assert entered.wait(5)
    refused = coordinator.run()
    release.set()
    thread.join(5)

    assert refused == {
        "schema": "mastermind.worker_browser_b1.receipt.v1",
        "ok": False,
        "state": "BUSY",
        "detail": "one browser review is already running",
    }
    assert result[0]["state"] == "COMPLETE"


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


def test_control_room_ui_exposes_one_bounded_review_and_two_exact_previews():
    root = Path(__file__).resolve().parents[1] / "app" / "static" / "chairman_control"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "control_room.js").read_text(encoding="utf-8")

    assert 'id="browser-review-run"' in html
    assert 'id="browser-review-result"' in html
    assert 'id="browser-review-desktop"' in html
    assert 'id="browser-review-mobile"' in html
    assert "fresh isolated browser" in html.lower()
    assert "does not use your browser profile" in html.lower()
    assert 'postJSON("/api/browser-review", {})' in js
    assert '"/api/browser-review/artifact/desktop.png"' in js
    assert '"/api/browser-review/artifact/mobile.png"' in js

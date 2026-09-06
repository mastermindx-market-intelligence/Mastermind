"""Executable tests for the local reader, not proof of a live ChatGPT account."""
import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "integrations/chairman_surfaces/web_sol_extension"


def test_manifest_exposes_the_reader_without_permission_widening():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest.get("action", {}).get("default_popup") == "census.html"
    assert set(manifest["permissions"]) == {"nativeMessaging", "alarms"}
    assert set(manifest["host_permissions"]) == {
        "https://chat.openai.com/*", "https://chatgpt.com/*"
    }
    assert manifest["background"] == {"service_worker": "background.js"}
    assert manifest["content_scripts"][0]["js"] == ["content.js"]
    assert "externally_connectable" not in manifest
    assert "web_accessible_resources" not in manifest


class _Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.ids = set()
        self.inline_script = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "script":
            if "src" not in values:
                self.inline_script = True
            self.scripts.append(values.get("src"))


def test_reader_is_a_real_local_consumer_with_no_remote_or_inline_scripts():
    assert (EXTENSION / "census.html").exists(), "the census needs a user-visible consumer"
    page = _Assets()
    page.feed((EXTENSION / "census.html").read_text())
    assert page.scripts == ["instance_config.js", "census_core.js", "census.js"]
    assert not page.inline_script
    assert {"refresh", "rows", "summary", "scope", "status", "timestamp"} <= page.ids
    source = (EXTENSION / "census.js").read_text()
    assert "MMXWebSolCensus.collect" in source
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "setInterval" not in source
    for forbidden in ("fetch(", "XMLHttpRequest", "connectNative", "chrome.storage", "localStorage",
                      "tabs.update", "tabs.create", "tabs.remove", "tabs.reload"):
        assert forbidden not in source
    assert (EXTENSION / "census.css").is_file()


def test_node_census_behavior_suite():
    node = shutil.which("node")
    assert node is not None, "Node is required; this behavior gate must not be skipped"
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests/web_sol_session_census.test.cjs")],
        cwd=ROOT, capture_output=True, text=True, timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


DISCARD_RECEIPT_SCHEMA = "mastermind.web_sol_census_discard_probe.v1"


def _fixture_pass_discard_receipt():
    return {
        "schema": DISCARD_RECEIPT_SCHEMA,
        "status": "PASS",
        "extension_source_hashes": {
            "census.html": "1" * 64,
            "census.css": "2" * 64,
            "census.js": "3" * 64,
            "census_core.js": "4" * 64,
            "content.js": "5" * 64,
            "manifest.json": "6" * 64,
        },
        "fixture_hashes": {
            "census.html": "1" * 64,
            "census.css": "2" * 64,
            "census.js": "3" * 64,
            "census_core.js": "4" * 64,
            "content.js": "5" * 64,
            "manifest.json": "7" * 64,
            "instance_config.js": "8" * 64,
        },
        "browser_executable_sha256": "9" * 64,
        "browser_version": "Synthetic Chromium 1",
        "extension_id": "a" * 32,
        "sandbox_enabled": True,
        "sandbox_process_verified": True,
        "profile_root_class": "TEMPORARY_DIRECTORY",
        "assertions": {
            "discard_call_returned_discarded_tab": True,
            "refresh_completed": True,
            "row_remained_visible_as_discarded": True,
            "no_content_probe_sent_to_discarded_row": True,
            "generation_cue_remained_unknown": True,
            "private_fixture_marker_absent": True,
        },
    }


def test_discard_probe_result_classifier_accepts_a_bound_pass_receipt(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_fixture_pass_discard_receipt()))
    result = classify_discard_probe_result(0, "", "", receipt)
    assert result["status"] == "PASS"
    assert result["exit_code"] == 0
    assert result["signal"] is None
    assert result["receipt_valid"] is True


def test_discard_probe_result_classifier_preserves_browser_crashes(tmp_path):
    import signal
    signaled = classify_discard_probe_result(-signal.SIGSEGV, "", "", tmp_path / "missing.json")
    assert signaled == {
        "status": "BROWSER_CRASH", "exit_code": None, "signal": "SIGSEGV",
        "receipt_valid": False, "receipt": None,
    }
    closed = classify_discard_probe_result(
        1, "", "TargetClosedError: target closed\nReceived signal 11 SEGV_ACCERR", tmp_path / "missing.json"
    )
    assert closed["status"] == "BROWSER_CRASH"
    assert closed["exit_code"] == 1
    assert closed["signal"] == "SIGSEGV"
    assert closed["receipt_valid"] is False


def test_discard_probe_result_classifier_preserves_closed_failure_receipts(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "schema": DISCARD_RECEIPT_SCHEMA,
        "status": "ASSERTION_FAILED",
        "reason": "ROW_NOT_DISCARDED",
    }))
    assertion = classify_discard_probe_result(2, "", "", receipt)
    assert assertion["status"] == "ASSERTION_FAILED"
    assert assertion["receipt_valid"] is True
    receipt.write_text(json.dumps({
        "schema": DISCARD_RECEIPT_SCHEMA,
        "status": "INFRA_UNAVAILABLE",
        "reason": "BROWSER_EXECUTABLE_UNAVAILABLE",
    }))
    infra = classify_discard_probe_result(3, "", "", receipt)
    assert infra["status"] == "INFRA_UNAVAILABLE"
    assert infra["receipt_valid"] is True


def test_discard_probe_result_classifier_refuses_missing_or_malformed_receipts(tmp_path):
    missing = classify_discard_probe_result(0, "", "", tmp_path / "missing.json")
    assert missing["status"] == "INVALID_PROOF_RECEIPT"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("not-json")
    assert classify_discard_probe_result(0, "", "", malformed)["status"] == "INVALID_PROOF_RECEIPT"
    malformed.write_text(json.dumps({"schema": DISCARD_RECEIPT_SCHEMA, "status": "PASS"}))
    assert classify_discard_probe_result(0, "", "", malformed)["status"] == "INVALID_PROOF_RECEIPT"


def test_parent_discard_runner_survives_a_signaled_child_and_writes_the_blocker(tmp_path):
    import signal
    import sys
    command = [sys.executable, "-c", "import os,signal; os.kill(os.getpid(), signal.SIGTERM)"]
    report = run_discard_probe_and_record(
        command, tmp_path, {"schema": "stable", "stable_matrix_pass": True}, timeout_seconds=5
    )
    assert report["stable_matrix_pass"] is True
    assert report["proof_class"] == "SYNTHETIC_BROWSER_PARTIAL_NOT_PROVIDER_PROOF"
    assert report["discard_probe_status"] == "BROWSER_CRASH"
    assert report["discard_probe_signal"] == "SIGTERM"
    assert report["full_matrix_pass"] is False
    assert json.loads((tmp_path / "synthetic-browser-proof.json").read_text()) == report



def _fixture_stable_report_for(receipt):
    return {
        "schema": "mastermind.web_sol_census_synthetic_stable_browser_proof.v1",
        "proof_class": "SYNTHETIC_BROWSER_STABLE_MATRIX_NOT_PROVIDER_PROOF",
        "stable_matrix_pass": True,
        "extension_source_hashes": dict(receipt["extension_source_hashes"]),
        "browser_executable_sha256": receipt["browser_executable_sha256"],
        "browser_version": receipt["browser_version"],
        "extension_id": receipt["extension_id"],
        "sandbox_enabled": True,
        "sandbox_process_verified": True,
        "profile_root_class": "TEMPORARY_DIRECTORY",
    }


def _receipt_writer_command(tmp_path, receipt):
    import sys
    script = tmp_path / "write_receipt.py"
    script.write_text(
        "import pathlib,sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2])\n"
    )
    return [
        sys.executable, str(script), str(tmp_path / "discard-probe-receipt.json"),
        json.dumps(receipt),
    ]


def test_parent_accepts_only_a_pass_receipt_bound_to_the_stable_matrix(tmp_path):
    receipt = _fixture_pass_discard_receipt()
    stable = _fixture_stable_report_for(receipt)
    report = run_discard_probe_and_record(
        _receipt_writer_command(tmp_path, receipt), tmp_path, stable, timeout_seconds=5
    )
    assert report["discard_probe_status"] == "PASS"
    assert report["discard_probe_receipt_valid"] is True
    assert report["discard_probe_binding_valid"] is True
    assert report["full_matrix_pass"] is True
    assert report["proof_class"] == "SYNTHETIC_BROWSER_FULL_MATRIX_NOT_PROVIDER_PROOF"


def test_parent_refuses_a_valid_pass_receipt_from_different_source_bytes(tmp_path):
    receipt = _fixture_pass_discard_receipt()
    stable = _fixture_stable_report_for(receipt)
    stable["extension_source_hashes"]["content.js"] = "f" * 64
    report = run_discard_probe_and_record(
        _receipt_writer_command(tmp_path, receipt), tmp_path, stable, timeout_seconds=5
    )
    assert report["discard_probe_status"] == "EVIDENCE_BINDING_MISMATCH"
    assert report["discard_probe_receipt_valid"] is True
    assert report["discard_probe_binding_valid"] is False
    assert report["full_matrix_pass"] is False


def test_parent_reports_child_timeout_as_its_own_closed_outcome(tmp_path):
    import sys
    report = run_discard_probe_and_record(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        tmp_path,
        {"schema": "stable", "stable_matrix_pass": True},
        timeout_seconds=0.05,
    )
    assert report["discard_probe_status"] == "CHILD_TIMEOUT"
    assert report["discard_probe_receipt_valid"] is False
    assert report["discard_probe_binding_valid"] is None
    assert report["full_matrix_pass"] is False


def test_staged_fixture_hashes_bind_every_loaded_source_asset(tmp_path):
    manifest, _ = _fixture_manifest_and_id()
    source_hashes = _extension_source_hashes()
    staged = _stage_fixture_extension(tmp_path / "extension", "a" * 64, manifest)
    expected = {
        "census.html", "census.css", "census.js", "census_core.js", "content.js",
        "manifest.json", "instance_config.js",
    }
    assert set(staged) == expected
    for name in expected - {"manifest.json", "instance_config.js"}:
        assert staged[name] == source_hashes[name]
    assert staged["manifest.json"] != source_hashes["manifest.json"]


def test_source_hash_fence_rejects_movement_during_browser_proof():
    import pytest
    expected = _extension_source_hashes()
    expected["content.js"] = "0" * 64
    with pytest.raises(_DiscardProofAssertion, match="SOURCE_CHANGED_DURING_PROOF"):
        _require_source_hashes_unchanged(expected)

def test_browser_proof_is_csp_safe_sandboxed_and_process_isolates_discard():
    import inspect
    parent = inspect.getsource(run_synthetic_browser_proof)
    child = inspect.getsource(run_discard_probe_child)
    stable = inspect.getsource(_stable_browser_matrix)
    launcher = inspect.getsource(_launch_fixture_context)
    assert "wait_for_function(" not in parent + child + stable
    assert '"--no-sandbox"' not in parent + child + stable + launcher
    assert "chromium_sandbox=True" in launcher
    assert "chrome.tabs.discard" not in parent
    assert "chrome.tabs.discard" in child
    assert "run_discard_probe_and_record" in parent


_PASS_ASSERTION_KEYS = {
    "discard_call_returned_discarded_tab",
    "refresh_completed",
    "row_remained_visible_as_discarded",
    "no_content_probe_sent_to_discarded_row",
    "generation_cue_remained_unknown",
    "private_fixture_marker_absent",
}
_PASS_SOURCE_KEYS = {"census.html", "census.css", "census.js", "census_core.js", "content.js", "manifest.json"}
_FIXTURE_COPIED_SOURCE_KEYS = {"census.html", "census.css", "census.js", "census_core.js", "content.js"}
_PASS_FIXTURE_KEYS = _FIXTURE_COPIED_SOURCE_KEYS | {"manifest.json", "instance_config.js"}
_ASSERTION_REASONS = {
    "DISCARD_TARGET_NOT_FOUND", "DISCARD_CALL_DID_NOT_RETURN_DISCARDED_TAB",
    "REFRESH_DID_NOT_COMPLETE", "ROW_NOT_DISCARDED", "CONTENT_PROBE_WAS_SENT",
    "GENERATION_CUE_NOT_UNKNOWN", "PRIVATE_FIXTURE_MARKER_RENDERED",
    "SANDBOX_PROCESS_NOT_VERIFIED", "STAGED_SOURCE_HASH_MISMATCH",
    "SOURCE_CHANGED_DURING_PROOF",
}
_INFRA_REASONS = {"PLAYWRIGHT_UNAVAILABLE", "BROWSER_EXECUTABLE_UNAVAILABLE", "BROWSER_LAUNCH_UNAVAILABLE"}


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _valid_discard_receipt(receipt):
    if not isinstance(receipt, dict) or receipt.get("schema") != DISCARD_RECEIPT_SCHEMA:
        return False
    status = receipt.get("status")
    if status == "PASS":
        expected = {
            "schema", "status", "extension_source_hashes", "fixture_hashes",
            "browser_executable_sha256", "browser_version", "extension_id",
            "sandbox_enabled", "sandbox_process_verified", "profile_root_class", "assertions",
        }
        if set(receipt) != expected:
            return False
        source_hashes = receipt["extension_source_hashes"]
        fixture_hashes = receipt["fixture_hashes"]
        assertions = receipt["assertions"]
        return (
            isinstance(source_hashes, dict) and set(source_hashes) == _PASS_SOURCE_KEYS
            and all(_is_sha256(value) for value in source_hashes.values())
            and isinstance(fixture_hashes, dict) and set(fixture_hashes) == _PASS_FIXTURE_KEYS
            and all(_is_sha256(value) for value in fixture_hashes.values())
            and all(fixture_hashes[name] == source_hashes[name] for name in _FIXTURE_COPIED_SOURCE_KEYS)
            and _is_sha256(receipt["browser_executable_sha256"])
            and isinstance(receipt["browser_version"], str) and 0 < len(receipt["browser_version"]) <= 200
            and isinstance(receipt["extension_id"], str) and len(receipt["extension_id"]) == 32
            and all("a" <= char <= "p" for char in receipt["extension_id"])
            and receipt["sandbox_enabled"] is True
            and receipt["sandbox_process_verified"] is True
            and receipt["profile_root_class"] == "TEMPORARY_DIRECTORY"
            and isinstance(assertions, dict) and set(assertions) == _PASS_ASSERTION_KEYS
            and all(value is True for value in assertions.values())
        )
    if status == "ASSERTION_FAILED":
        return set(receipt) == {"schema", "status", "reason"} and receipt.get("reason") in _ASSERTION_REASONS
    if status == "INFRA_UNAVAILABLE":
        return set(receipt) == {"schema", "status", "reason"} and receipt.get("reason") in _INFRA_REASONS
    return False


def _read_discard_receipt(path):
    try:
        receipt = json.loads(Path(path).read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return receipt if _valid_discard_receipt(receipt) else None


def _browser_signal(returncode, stderr):
    import re
    import signal
    if returncode < 0:
        try:
            return signal.Signals(-returncode).name
        except ValueError:
            return f"SIGNAL_{-returncode}"
    match = re.search(r"Received signal\s+(\d+)", stderr or "")
    if match:
        try:
            return signal.Signals(int(match.group(1))).name
        except ValueError:
            return f"SIGNAL_{match.group(1)}"
    if "SEGV_" in (stderr or ""):
        return "SIGSEGV"
    return None


def classify_discard_probe_result(returncode, stdout, stderr, receipt_path):
    receipt = _read_discard_receipt(receipt_path)
    exit_code = None if returncode < 0 else returncode
    if receipt is not None and receipt["status"] == "PASS" and returncode == 0:
        return {"status": "PASS", "exit_code": 0, "signal": None, "receipt_valid": True, "receipt": receipt}
    crash_signal = _browser_signal(returncode, stderr)
    closed = (
        "TargetClosedError" in (stderr or "")
        or "Target page, context or browser has been closed" in (stderr or "")
    )
    if returncode < 0 or crash_signal is not None or closed:
        return {
            "status": "BROWSER_CRASH", "exit_code": exit_code, "signal": crash_signal,
            "receipt_valid": False, "receipt": None,
        }
    if receipt is not None and receipt["status"] in {"ASSERTION_FAILED", "INFRA_UNAVAILABLE"} and returncode != 0:
        return {
            "status": receipt["status"], "exit_code": exit_code, "signal": None,
            "receipt_valid": True, "receipt": receipt,
        }
    return {
        "status": "INVALID_PROOF_RECEIPT", "exit_code": exit_code, "signal": None,
        "receipt_valid": False, "receipt": None,
    }



def _discard_pass_binding_valid(stable_report, result):
    if result.get("status") != "PASS" or result.get("receipt_valid") is not True:
        return None
    receipt = result["receipt"]
    source_hashes = stable_report.get("extension_source_hashes")
    valid_stable_identity = (
        stable_report.get("schema") == "mastermind.web_sol_census_synthetic_stable_browser_proof.v1"
        and stable_report.get("proof_class") == "SYNTHETIC_BROWSER_STABLE_MATRIX_NOT_PROVIDER_PROOF"
        and stable_report.get("stable_matrix_pass") is True
        and isinstance(source_hashes, dict)
        and set(source_hashes) == _PASS_SOURCE_KEYS
        and all(_is_sha256(value) for value in source_hashes.values())
        and _is_sha256(stable_report.get("browser_executable_sha256"))
        and isinstance(stable_report.get("browser_version"), str)
        and 0 < len(stable_report["browser_version"]) <= 200
        and isinstance(stable_report.get("extension_id"), str)
        and len(stable_report["extension_id"]) == 32
        and all("a" <= char <= "p" for char in stable_report["extension_id"])
        and stable_report.get("sandbox_enabled") is True
        and stable_report.get("sandbox_process_verified") is True
        and stable_report.get("profile_root_class") == "TEMPORARY_DIRECTORY"
    )
    if not valid_stable_identity:
        return False
    return (
        receipt["extension_source_hashes"] == source_hashes
        and receipt["browser_executable_sha256"] == stable_report["browser_executable_sha256"]
        and receipt["browser_version"] == stable_report["browser_version"]
        and receipt["extension_id"] == stable_report["extension_id"]
        and receipt["sandbox_enabled"] is stable_report["sandbox_enabled"]
        and receipt["sandbox_process_verified"] is stable_report["sandbox_process_verified"]
        and receipt["profile_root_class"] == stable_report["profile_root_class"]
    )


def _run_isolated_child(command, timeout_seconds):
    import os
    import signal
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        return None, stdout, stderr, True

def _text_sha256(value):
    import hashlib
    return hashlib.sha256((value or "").encode()).hexdigest()


def run_discard_probe_and_record(command, output_dir, stable_report, timeout_seconds=90):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "discard-probe-receipt.json"
    receipt_path.unlink(missing_ok=True)
    returncode, stdout, stderr, timed_out = _run_isolated_child(command, timeout_seconds)
    if timed_out:
        result = {
            "status": "CHILD_TIMEOUT", "exit_code": None, "signal": None,
            "receipt_valid": False, "receipt": None,
        }
    else:
        result = classify_discard_probe_result(returncode, stdout, stderr, receipt_path)
    binding_valid = _discard_pass_binding_valid(stable_report, result)
    if result["status"] == "PASS" and binding_valid is not True:
        result = dict(result)
        result["status"] = "EVIDENCE_BINDING_MISMATCH"
    (output / "discard-probe.stdout.log").write_text(stdout)
    (output / "discard-probe.stderr.log").write_text(stderr)
    report = dict(stable_report)
    full_matrix_pass = stable_report.get("stable_matrix_pass") is True and result["status"] == "PASS"
    report.update({
        "schema": "mastermind.web_sol_census_synthetic_browser_proof.v2",
        "proof_class": (
            "SYNTHETIC_BROWSER_FULL_MATRIX_NOT_PROVIDER_PROOF"
            if full_matrix_pass else "SYNTHETIC_BROWSER_PARTIAL_NOT_PROVIDER_PROOF"
        ),
        "discard_probe_status": result["status"],
        "discard_probe_exit_code": result["exit_code"],
        "discard_probe_signal": result["signal"],
        "discard_probe_receipt_valid": result["receipt_valid"],
        "discard_probe_binding_valid": binding_valid,
        "discard_probe_receipt": result["receipt"],
        "discard_probe_stdout_sha256": _text_sha256(stdout),
        "discard_probe_stderr_sha256": _text_sha256(stderr),
        "full_matrix_pass": full_matrix_pass,
    })
    (output / "synthetic-browser-proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


class _DiscardProofAssertion(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _ProofInfraUnavailable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extension_source_hashes():
    return {name: _sha256_file(EXTENSION / name) for name in sorted(_PASS_SOURCE_KEYS)}



def _require_source_hashes_unchanged(expected):
    if _extension_source_hashes() != expected:
        raise _DiscardProofAssertion("SOURCE_CHANGED_DURING_PROOF")


def _require_staged_source_hashes(fixture_hashes, source_hashes):
    if any(fixture_hashes.get(name) != source_hashes.get(name) for name in _FIXTURE_COPIED_SOURCE_KEYS):
        raise _DiscardProofAssertion("STAGED_SOURCE_HASH_MISMATCH")

def _fixture_manifest_and_id():
    import base64
    import hashlib
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    if manifest.pop("background", None) != {"service_worker": "background.js"}:
        raise AssertionError("fixture must omit exactly the production native background")
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).digest()[:16]
    extension_id = "".join(chr(97 + int(char, 16)) for char in digest.hex())
    return manifest, extension_id


def _stage_fixture_extension(directory, instance, manifest):
    directory.mkdir(parents=True)
    for name in ("census.html", "census.css", "census.js", "census_core.js", "content.js"):
        shutil.copyfile(EXTENSION / name, directory / name)
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    (directory / "instance_config.js").write_text(
        "globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze(" + json.dumps({"instanceId": instance}) + ");\n"
    )
    return {name: _sha256_file(directory / name) for name in sorted(_PASS_FIXTURE_KEYS)}


def _resolve_browser_executable(playwright):
    executable = shutil.which("chromium") or shutil.which("google-chrome") or playwright.chromium.executable_path
    if not executable or not Path(executable).is_file():
        raise _ProofInfraUnavailable("BROWSER_EXECUTABLE_UNAVAILABLE")
    return str(executable)


def _browser_version(executable):
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ProofInfraUnavailable("BROWSER_EXECUTABLE_UNAVAILABLE") from exc
    version = result.stdout.strip()
    if not version or len(version) > 200:
        raise _ProofInfraUnavailable("BROWSER_EXECUTABLE_UNAVAILABLE")
    return version


def _sandbox_process_verified(profile_dir):
    try:
        commands = subprocess.run(
            ["ps", "-axo", "command="], capture_output=True, text=True, timeout=10, check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return False
    marker = f"--user-data-dir={profile_dir}"
    browsers = [line for line in commands if marker in line and "--type=" not in line]
    return len(browsers) == 1 and "--no-sandbox" not in browsers[0]


def _fulfill_browser_fixture(route):
    from urllib.parse import urlparse
    parsed = urlparse(route.request.url)
    if parsed.scheme == "chrome-extension":
        route.continue_()
        return
    if parsed.scheme != "https" or parsed.hostname != "chatgpt.com":
        route.abort()
        return
    if parsed.path == "/favicon.ico":
        route.fulfill(status=204, body="")
        return
    composer = "" if "fixture-project" in parsed.path else (
        '<div id="prompt-textarea" contenteditable="true">PRIVATE_FIXTURE_SENTINEL</div>'
    )
    stop = '<button data-testid="stop-button">Stop</button>' if "fixture-active" in parsed.path else ""
    route.fulfill(status=200, content_type="text/html", body=(
        '<!doctype html><html><head><title>PRIVATE_FIXTURE_SENTINEL</title></head>'
        f'<body><main>{composer}{stop}</main></body></html>'
    ))


def _launch_fixture_context(playwright, executable, extension, profile, viewport):
    context = playwright.chromium.launch_persistent_context(
        str(profile), executable_path=executable, headless=True, chromium_sandbox=True,
        viewport=viewport,
        args=[
            f"--disable-extensions-except={extension}", f"--load-extension={extension}",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--no-first-run",
        ],
    )
    context.set_offline(True)
    context.route("**/*", _fulfill_browser_fixture)
    return context


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _write_discard_failure(receipt_path, status, reason):
    _atomic_json(receipt_path, {"schema": DISCARD_RECEIPT_SCHEMA, "status": status, "reason": reason})


def _require_proof(condition, reason):
    if not condition:
        raise _DiscardProofAssertion(reason)


def _expect_refresh_enabled(expect, popup):
    try:
        expect(popup.locator("#refresh")).to_be_enabled(timeout=5000)
    except Exception as exc:
        if exc.__class__.__name__ == "TargetClosedError":
            raise
        raise _DiscardProofAssertion("REFRESH_DID_NOT_COMPLETE") from exc


def _stable_browser_matrix(output):
    import tempfile
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError as exc:
        raise _ProofInfraUnavailable("PLAYWRIGHT_UNAVAILABLE") from exc

    manifest, extension_id = _fixture_manifest_and_id()
    source_hashes = _extension_source_hashes()
    page_errors = []
    with tempfile.TemporaryDirectory(prefix="mmx-census-stable-") as temporary, sync_playwright() as playwright:
        temporary = Path(temporary)
        executable = _resolve_browser_executable(playwright)
        fixtures = {
            "a": _stage_fixture_extension(temporary / "a", "a" * 64, manifest),
            "b": _stage_fixture_extension(temporary / "b", "b" * 64, manifest),
        }
        for fixture_hashes in fixtures.values():
            _require_staged_source_hashes(fixture_hashes, source_hashes)
        contexts = []
        sandbox_checks = []

        def launch(name):
            profile = temporary / f"profile-{name}"
            context = _launch_fixture_context(
                playwright, executable, temporary / name, profile, {"width": 760, "height": 680},
            )
            contexts.append(context)
            sandbox_checks.append(_sandbox_process_verified(profile))
            return context

        try:
            context = launch("a")
            pages = []
            for path in (
                "/c/fixture-active", "/c/fixture-active", "/c/fixture-idle",
                "/g/g-p-FIXTURE/c/fixture-project", "/", "/c/fixture-dormant",
            ):
                page = context.new_page()
                page.goto("https://chatgpt.com" + path, wait_until="load")
                pages.append(page)
            popup = context.new_page()
            popup.on("pageerror", lambda _: page_errors.append("POPUP_SCRIPT_ERROR"))
            popup.goto(f"chrome-extension://{extension_id}/census.html", wait_until="load")
            expect(popup.locator("#refresh")).to_be_enabled(timeout=5000)
            metrics = popup.locator(".metric strong").all_text_contents()
            assert metrics == ["6", "2", "2", "1"], metrics
            rows = popup.locator("#rows tr")
            assert rows.count() == 6
            rows.last.scroll_into_view_if_needed()
            expect(rows.last).to_be_in_viewport()
            popup.locator("main").evaluate("node => { node.scrollTop = 0; }")
            body = popup.locator("body").inner_text()
            assert "No conversation locator" in body
            assert "PRIVATE_FIXTURE_SENTINEL" not in body
            assert "Served model: unknown" in body
            popup.screenshot(path=str(output / "census-synthetic-wide.png"), full_page=True)
            popup.set_viewport_size({"width": 560, "height": 780})
            assert popup.evaluate("document.body.scrollWidth <= window.innerWidth"), "Narrow UI overflows"
            popup.screenshot(path=str(output / "census-synthetic-narrow.png"), full_page=True)
            popup.set_viewport_size({"width": 760, "height": 680})
            pages[0].evaluate("document.querySelector('[data-testid=stop-button]').remove()")
            popup.locator("#refresh").click()
            expect(popup.locator("#refresh")).to_be_enabled(timeout=5000)
            assert popup.locator(".metric strong").all_text_contents()[1] == "1"
            assert "Cue observations differ" in popup.locator("body").inner_text()
            second = launch("b")
            second.new_page().goto("https://chatgpt.com/c/fixture-idle", wait_until="load")
            second_popup = second.new_page()
            second_popup.goto(f"chrome-extension://{extension_id}/census.html", wait_until="load")
            expect(second_popup.locator("#refresh")).to_be_enabled(timeout=5000)
            assert second_popup.locator(".metric strong").all_text_contents()[0] == "1"
            assert popup.locator(".metric strong").all_text_contents()[0] == "6"
            assert second_popup.evaluate("MMX_WEB_SOL_INSTANCE.instanceId") == "b" * 64
            assert all(sandbox_checks), sandbox_checks
            assert not page_errors, page_errors
            _require_source_hashes_unchanged(source_hashes)
            return {
                "schema": "mastermind.web_sol_census_synthetic_stable_browser_proof.v1",
                "proof_class": "SYNTHETIC_BROWSER_STABLE_MATRIX_NOT_PROVIDER_PROOF",
                "native_background": "OMITTED_FROM_TEST_MANIFEST",
                "instance_config": "SYNTHETIC",
                "provider_network": "OFFLINE_CONTEXT_FIXTURE_RESPONSES_ONLY",
                "extension_source_hashes": source_hashes,
                "fixture_hashes_by_instance": fixtures,
                "browser_executable_sha256": _sha256_file(executable),
                "browser_version": _browser_version(executable),
                "extension_id": extension_id,
                "csp_unchanged": True,
                "sandbox_enabled": True,
                "sandbox_process_verified": True,
                "profile_root_class": "TEMPORARY_DIRECTORY",
                "fixture_tab_count": 6,
                "rendered_row_count": 6,
                "last_row_scroll_verified": True,
                "initial_metrics": metrics,
                "duplicate_cue_conflict_after_refresh": True,
                "profile_isolation_counts": [6, 1],
                "narrow_overflow": False,
                "private_fixture_marker_absent": True,
                "popup_script_errors": page_errors,
                "current_chatgpt_model_effort_proven": False,
                "stable_matrix_pass": True,
            }
        finally:
            for context in reversed(contexts):
                try:
                    context.close()
                except Exception:
                    pass


def run_discard_probe_child(receipt_path):
    import tempfile
    receipt_path = Path(receipt_path)
    receipt_path.unlink(missing_ok=True)
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        _write_discard_failure(receipt_path, "INFRA_UNAVAILABLE", "PLAYWRIGHT_UNAVAILABLE")
        return 3

    try:
        manifest, extension_id = _fixture_manifest_and_id()
        source_hashes = _extension_source_hashes()
        with tempfile.TemporaryDirectory(prefix="mmx-census-discard-") as temporary, sync_playwright() as playwright:
            temporary = Path(temporary)
            executable = _resolve_browser_executable(playwright)
            extension = temporary / "discard"
            fixture_hashes = _stage_fixture_extension(extension, "d" * 64, manifest)
            _require_staged_source_hashes(fixture_hashes, source_hashes)
            profile = temporary / "profile-discard"
            try:
                context = _launch_fixture_context(
                    playwright, executable, extension, profile, {"width": 760, "height": 680},
                )
            except Exception as exc:
                if exc.__class__.__name__ == "TargetClosedError":
                    raise
                raise _ProofInfraUnavailable("BROWSER_LAUNCH_UNAVAILABLE") from exc
            try:
                sandbox_verified = _sandbox_process_verified(profile)
                page = context.new_page()
                page.goto("https://chatgpt.com/c/fixture-dormant", wait_until="load")
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/census.html", wait_until="load")
                _expect_refresh_enabled(expect, popup)
                instrumented = popup.evaluate("""() => {
                    const original = chrome.tabs.sendMessage.bind(chrome.tabs);
                    let count = 0;
                    chrome.tabs.sendMessage = (...args) => { count += 1; return original(...args); };
                    globalThis.__mmxDiscardProbeCalls = () => count;
                    return typeof chrome.tabs.sendMessage === 'function';
                }""")
                _require_proof(instrumented is True, "CONTENT_PROBE_WAS_SENT")
                discarded = popup.evaluate("""async () => {
                    const tabs = await chrome.tabs.query({url: 'https://chatgpt.com/*'});
                    const target = tabs.find(tab => tab.url.endsWith('/c/fixture-dormant'));
                    if (!target) return {found: false, discarded: false};
                    const result = await chrome.tabs.discard(target.id);
                    return {found: true, discarded: Boolean(result && result.discarded === true)};
                }""")
                _require_proof(discarded.get("found") is True, "DISCARD_TARGET_NOT_FOUND")
                _require_proof(
                    discarded.get("discarded") is True,
                    "DISCARD_CALL_DID_NOT_RETURN_DISCARDED_TAB",
                )
                popup.locator("#refresh").click()
                _expect_refresh_enabled(expect, popup)
                metrics = popup.locator(".metric strong").all_text_contents()
                body = popup.locator("body").inner_text()
                probes = popup.evaluate("globalThis.__mmxDiscardProbeCalls()")
                _require_proof(metrics == ["1", "0", "1", "0"], "ROW_NOT_DISCARDED")
                _require_proof("Discarded" in body, "ROW_NOT_DISCARDED")
                _require_proof(probes == 0, "CONTENT_PROBE_WAS_SENT")
                _require_proof("Unknown" in body, "GENERATION_CUE_NOT_UNKNOWN")
                _require_proof("PRIVATE_FIXTURE_SENTINEL" not in body, "PRIVATE_FIXTURE_MARKER_RENDERED")
                _require_proof(sandbox_verified, "SANDBOX_PROCESS_NOT_VERIFIED")
                _require_source_hashes_unchanged(source_hashes)
                receipt = {
                    "schema": DISCARD_RECEIPT_SCHEMA,
                    "status": "PASS",
                    "extension_source_hashes": source_hashes,
                    "fixture_hashes": fixture_hashes,
                    "browser_executable_sha256": _sha256_file(executable),
                    "browser_version": _browser_version(executable),
                    "extension_id": extension_id,
                    "sandbox_enabled": True,
                    "sandbox_process_verified": True,
                    "profile_root_class": "TEMPORARY_DIRECTORY",
                    "assertions": {
                        "discard_call_returned_discarded_tab": True,
                        "refresh_completed": True,
                        "row_remained_visible_as_discarded": True,
                        "no_content_probe_sent_to_discarded_row": True,
                        "generation_cue_remained_unknown": True,
                        "private_fixture_marker_absent": True,
                    },
                }
                _atomic_json(receipt_path, receipt)
                return 0
            finally:
                try:
                    context.close()
                except Exception:
                    pass
    except _DiscardProofAssertion as exc:
        _write_discard_failure(receipt_path, "ASSERTION_FAILED", exc.reason)
        return 2
    except _ProofInfraUnavailable as exc:
        _write_discard_failure(receipt_path, "INFRA_UNAVAILABLE", exc.reason)
        return 3


def run_synthetic_browser_proof(output_dir):
    """Run stable synthetic proof and isolate the crash-prone discard probe.

    This excludes the production native background, provider accounts and existing profiles.
    A failed discard child remains an explicit blocker while stable evidence survives.
    """
    import sys
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stable_report = _stable_browser_matrix(output)
    _atomic_json(output / "stable-browser-proof.json", stable_report)
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--discard-probe-child", str(output / "discard-probe-receipt.json"),
    ]
    report = run_discard_probe_and_record(command, output, stable_report, timeout_seconds=90)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Optional offline Web-Sol census browser fixture proof")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--browser-proof", metavar="OUTPUT_DIR")
    group.add_argument("--discard-probe-child", metavar="RECEIPT_PATH")
    args = parser.parse_args()
    if args.discard_probe_child:
        raise SystemExit(run_discard_probe_child(args.discard_probe_child))
    result = run_synthetic_browser_proof(args.browser_proof)
    raise SystemExit(0 if result["full_matrix_pass"] else 1)

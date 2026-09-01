from __future__ import annotations

import io
import json
import subprocess

from scripts import verify_s0_fixture_metadata_from_keychain as helper


def test_verifier_child_uses_isolated_no_site_python_before_secret_stdin() -> None:
    argv = helper._verifier_argv()
    assert argv[:4] == [
        helper.sys.executable,
        "-I",
        "-S",
        str(helper._VERIFIER_SCRIPT),
    ]
    assert "-I" in argv
    assert "-S" in argv


def test_existing_verifier_boots_isolated_and_refuses_before_network() -> None:
    completed = subprocess.run(
        helper._verifier_argv(),
        input=b"not-a-token",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={},
        cwd=str(helper._REPO_ROOT),
        timeout=5.0,
        check=False,
        shell=False,
    )
    assert completed.returncode == 2
    assert completed.stderr == b""
    assert json.loads(completed.stdout) == {
        "error": "METADATA_INPUT_REFUSED",
        "schema": helper.verifier.RECEIPT_SCHEMA,
        "status": "ERROR",
    }


def test_keychain_failure_text_cannot_escape_in_visible_receipt() -> None:
    canary = "xoxb-KEYCHAIN-ERROR-LEAK-CANARY-1234567890"

    def failing_api_factory():
        raise RuntimeError(canary)

    out = io.StringIO()
    code = helper.main([], stdout=out, api_factory=failing_api_factory)
    assert code == 2
    assert json.loads(out.getvalue()) == {
        "error": "METADATA_RESPONSE_REFUSED",
        "schema": helper.verifier.RECEIPT_SCHEMA,
        "status": "ERROR",
    }
    assert canary not in out.getvalue()

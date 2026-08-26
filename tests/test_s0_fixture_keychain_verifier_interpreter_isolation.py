from __future__ import annotations

import io
import json

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

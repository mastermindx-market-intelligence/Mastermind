from __future__ import annotations

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

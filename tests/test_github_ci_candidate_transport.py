"""Fault checks for the bounded, GET-only installed-CLI transport."""
from __future__ import annotations

import sys

import pytest

from scripts.github_ci_candidate import (
    CandidateTransportError,
    GitHubCLIReader,
    _bounded_get,
)


def test_actual_child_stdout_is_collected_without_stderr_exposure():
    result = _bounded_get(
        [sys.executable, "-c", "import sys; sys.stderr.write('diagnostic detail'); print('{\"ok\":true}')"],
        5.0,
    )
    assert result.strip() == b'{"ok":true}'
    assert b"diagnostic" not in result


def test_actual_http_error_is_classified_without_returning_raw_detail():
    with pytest.raises(CandidateTransportError) as failure:
        _bounded_get(
            [sys.executable, "-c", "import sys; sys.stderr.write('private diagnostic: HTTP 403'); sys.exit(1)"],
            5.0,
        )
    assert str(failure.value) == "HTTP_403"
    assert "private" not in str(failure.value)


def test_actual_read_timeout_returns_bounded_error():
    with pytest.raises(CandidateTransportError, match="READ_TIMEOUT"):
        _bounded_get([sys.executable, "-c", "import time; time.sleep(3)"], 0.05)


def test_actual_stderr_limit_returns_no_raw_output():
    with pytest.raises(CandidateTransportError, match="READ_OUTPUT_LIMIT"):
        _bounded_get([sys.executable, "-c", "import sys; sys.stderr.write('x' * 70000)"], 5.0)


def test_cli_command_uses_only_fixed_host_get_and_known_projection(monkeypatch):
    from scripts import github_ci_candidate as module
    seen = []
    monkeypatch.setattr(module.shutil, "which", lambda name: "/approved/bin/gh")
    def bounded(arguments, timeout):
        seen.append((arguments, timeout))
        return b'{"number":1500}'
    monkeypatch.setattr(module, "_bounded_get", bounded)
    result = GitHubCLIReader().read("repos/mastermindx-market-intelligence/Mastermind/pulls/1500")
    arguments, timeout = seen[0]
    assert result == {"number": 1500}
    assert arguments[:7] == ["/approved/bin/gh", "api", "--hostname", "github.com", "--method", "GET", "--header"]
    assert "--jq" in arguments
    assert timeout == 15.0
    assert "--paginate" not in arguments
    assert len(seen) == 1


def test_invalid_json_from_existing_cli_is_not_accepted(monkeypatch):
    from scripts import github_ci_candidate as module
    monkeypatch.setattr(module.shutil, "which", lambda name: "/approved/bin/gh")
    monkeypatch.setattr(module, "_bounded_get", lambda *args: b"not json")
    with pytest.raises(CandidateTransportError, match="INVALID_GITHUB_JSON"):
        GitHubCLIReader().read("repos/mastermindx-market-intelligence/Mastermind/pulls/1500")


def test_missing_cli_does_not_choose_another_account_or_http_client(monkeypatch):
    from scripts import github_ci_candidate as module
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    with pytest.raises(CandidateTransportError, match="GITHUB_CLI_UNAVAILABLE"):
        GitHubCLIReader().read("repos/mastermindx-market-intelligence/Mastermind/pulls/1500")


def test_transport_failure_is_not_retried(monkeypatch):
    from scripts import github_ci_candidate as module
    calls = []
    monkeypatch.setattr(module.shutil, "which", lambda name: "/approved/bin/gh")
    def denied(arguments, timeout):
        calls.append(arguments)
        raise CandidateTransportError("HTTP_403")
    monkeypatch.setattr(module, "_bounded_get", denied)
    with pytest.raises(CandidateTransportError, match="HTTP_403"):
        GitHubCLIReader().read("repos/mastermindx-market-intelligence/Mastermind/pulls/1500")
    assert len(calls) == 1

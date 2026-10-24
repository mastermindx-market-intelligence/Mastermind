"""The existing control client exposes one bounded read, not a new service."""
import pytest

from scripts.executive_os_phase1c import _parser, _client_request


def test_session_recovery_client_builds_one_exact_original_root_read():
    args = _parser().parse_args(["--socket", "/tmp/test-only.sock", "session-recovery", "JOB-001"])
    assert _client_request(args) == ("session-recovery", {"root_job_id": "JOB-001", "limit": 100})


def test_session_recovery_client_accepts_explicit_bounded_limit():
    args = _parser().parse_args(["--socket", "/tmp/test-only.sock", "session-recovery", "JOB-001", "--limit", "30"])
    assert _client_request(args)[1] == {"root_job_id": "JOB-001", "limit": 30}


@pytest.mark.parametrize("value", ["0", "501", "-1", "garbage"])
def test_session_recovery_client_refuses_invalid_limits(value):
    with pytest.raises(SystemExit):
        _parser().parse_args(["session-recovery", "JOB-001", "--limit", value])


def test_session_recovery_client_can_request_the_next_worker_page():
    args = _parser().parse_args(["session-recovery", "JOB-001", "--limit", "30", "--after-job-id", "JOB-CHILD"])
    assert _client_request(args) == ("session-recovery", {
        "root_job_id": "JOB-001", "limit": 30, "after_job_id": "JOB-CHILD"})

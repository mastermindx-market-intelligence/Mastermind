"""The public maintenance CLI must not serialize private source metadata."""
import json
from unittest.mock import Mock

import pytest

from scripts import executive_os_incident_maintenance as entry


def report(**changes):
    return {
        "maintenance_state": "BROKER_STOPPED_OBSERVED",
        "release_sha": "a" * 40,
        "disable_attempted": True,
        "bootout_attempted": True,
        "socket_retirement_attempted": False,
        "origin_custody": False,
        "provider_called": False,
        **changes,
    }


@pytest.mark.parametrize("attempted", [False, True])
def test_success_output_excludes_private_metadata(monkeypatch, capsys, attempted):
    private = "fixture-private-source-metadata"
    operation = Mock(return_value=report(
        disable_attempted=attempted, bootout_attempted=attempted,
        release_sha=private, credentials={"secret": private},
    ))
    monkeypatch.setattr(entry, "_stop_incident_broker", operation)
    assert entry.main([]) == 0
    captured = capsys.readouterr()
    assert private not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "maintenance_state": "BROKER_STOPPED_OBSERVED",
        "disable_attempted": attempted,
        "bootout_attempted": attempted,
        "socket_retirement_attempted": False,
        "origin_custody": False,
        "provider_called": False,
    }
    operation.assert_called_once_with()


@pytest.mark.parametrize("value", [
    None, "fixture-private-source-metadata", {},
    report(maintenance_state="fixture-private-source-metadata"),
    report(disable_attempted="fixture-private-source-metadata"),
    report(bootout_attempted=1), report(origin_custody=True),
    report(socket_retirement_attempted=1),
    report(provider_called=True),
])
def test_invalid_report_preserves_uncertain_effect_without_logging_data(
    monkeypatch, capsys, value,
):
    operation = Mock(return_value=value)
    monkeypatch.setattr(entry, "_stop_incident_broker", operation)
    assert entry.main([]) == 75
    captured = capsys.readouterr()
    assert "fixture-private-source-metadata" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "maintenance_state": "REFUSED",
        "disable_attempted": None,
        "bootout_attempted": None,
        "socket_retirement_attempted": None,
        "origin_custody": False,
        "provider_called": None,
        "error": {"code": "BROKER_MAINTENANCE_REPORT_UNPROVEN"},
    }
    operation.assert_called_once_with()

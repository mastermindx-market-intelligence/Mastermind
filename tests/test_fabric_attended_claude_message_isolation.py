"""No native peer channel for a finite, one-parent Claude worker."""
import dataclasses
import json

import pytest

from control_plane.fabric_attended_claude import AttendedClaudePreparationError
from test_fabric_attended_claude import _prepare, _unfreeze


def test_finite_worker_has_receive_and_send_isolation_in_actual_argv_settings():
    descriptor = _prepare()
    settings = json.loads(descriptor.argv[descriptor.argv.index("--settings") + 1])
    assert settings["crossSessionInbound"] == "refuse"
    assert {"SendMessage", "ListAgents"} <= set(settings["permissions"]["deny"])
    assert descriptor.start_authorized is False
    assert descriptor.preparation_only is True


@pytest.mark.parametrize("value", ["accept", "hold", None, True])
def test_finite_worker_rejects_missing_or_widened_inbound_policy(value):
    descriptor = _prepare()
    settings = _unfreeze(descriptor.settings)
    if value is None:
        settings.pop("crossSessionInbound", None)
    else:
        settings["crossSessionInbound"] = value
    with pytest.raises(AttendedClaudePreparationError, match="peer messages"):
        dataclasses.replace(descriptor, settings=settings)


@pytest.mark.parametrize("removed", ["SendMessage", "ListAgents"])
def test_finite_worker_rejects_removed_outbound_native_deny(removed):
    descriptor = _prepare()
    settings = _unfreeze(descriptor.settings)
    settings["permissions"]["deny"] = [x for x in settings["permissions"]["deny"] if x != removed]
    with pytest.raises(AttendedClaudePreparationError, match="peer tools"):
        dataclasses.replace(descriptor, settings=settings)

"""Original-operation and expiry negatives shared with the actual TS consumer."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from control_plane.teamlink_contracts import (
    TeamLinkContractError, is_expired, is_ping_pong_echo, may_forward,
    validate_team_link_message, verify_duplicate,
)

CASES = json.loads((Path(__file__).parent / "fixtures/teamlink_envelopes.json").read_text())


def changed(message, path, value):
    result = deepcopy(message)
    target = result
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    return result


@pytest.mark.parametrize("case", CASES["immutableChanges"], ids=lambda case: case["path"])
def test_copied_id_cannot_hide_changed_immutable_envelope(case):
    original = CASES["message"]
    repeat = changed(original, case["path"], case["value"])
    assert verify_duplicate(original, repeat) == "refused_content_changed"


def test_observations_do_not_change_identity_or_rewind_the_original():
    original = deepcopy(CASES["message"])
    original.update(hop_count=2, delivery_state="replied")
    repeat = deepcopy(CASES["message"])
    assert verify_duplicate(original, repeat) == "same_message"
    assert original["hop_count"] == 2 and original["delivery_state"] == "replied"
    assert may_forward(original, datetime(2099, 11, 9, tzinfo=timezone.utc)) == (False, "hop_breach")


def test_optional_nulls_and_property_order_are_equivalent():
    original = deepcopy(CASES["message"])
    repeat = deepcopy(original)
    del repeat["reply_to"]
    del repeat["from"]["thread_ref"]
    repeat["correlation"] = {key: value for key, value in reversed(list(repeat["correlation"].items())) if value is not None}
    assert verify_duplicate(original, repeat) == "same_message"


def test_malformed_message_never_matches_copied_ids():
    original = CASES["message"]
    repeat = deepcopy(original)
    del repeat["to"]
    with pytest.raises(TeamLinkContractError):
        verify_duplicate(original, repeat)


def test_default_clock_and_exact_expiry_boundary():
    expired = changed(CASES["message"], "expires_at", "2000-01-01T00:00:00Z")
    assert may_forward(expired) == (False, "expired")
    assert may_forward(expired, datetime(2000, 1, 1, tzinfo=timezone.utc)) == (False, "expired")


@pytest.mark.parametrize("clock", [datetime(2026, 11, 9), "now", 0, False])
def test_invalid_clock_is_expired(clock):
    assert is_expired(CASES["message"], clock)
    assert may_forward(CASES["message"], clock) == (False, "expired")


@pytest.mark.parametrize("expiry", CASES["invalidDates"])
def test_invalid_calendar_date_never_gains_lifetime(expiry):
    message = changed(CASES["message"], "expires_at", expiry)
    with pytest.raises(TeamLinkContractError):
        validate_team_link_message(message)
    assert is_expired(message, datetime(2000, 1, 1, tzinfo=timezone.utc))


def test_exact_reversed_envelope_is_an_echo_without_message_id_equality():
    sent = CASES["message"]
    received = deepcopy(sent)
    received["from"], received["to"] = received["to"], received["from"]
    received["message_id"] = "tlm-" + "f" * 32
    received.update(hop_count=1, delivery_state="picked_up")
    assert is_ping_pong_echo(sent, received)
    for path, value in (("operation_key", "other-operation"), ("from.side", "hermes_profile"),
                        ("from.thread_ref", "another-thread"), ("to.id", "another-agent"),
                        ("body", "A new question"), ("correlation.root_run_ref", "other-root")):
        assert not is_ping_pong_echo(sent, changed(received, path, value)), path

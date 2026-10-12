import dataclasses

import pytest

from control_plane.dialogue_wake_canary_publication import (
    DialogueWakeCanaryPublicationReceipt, build_publication_receipt,
    verify_publication_receipt,
)
from tests.test_dialogue_wake_canary_activation import NOW, parsed, facts


def receipt(**changes):
    values = dict(
        grant=parsed(), current=facts(), transaction_id="autonomy-" + "1" * 12,
        control_config_sha256="2" * 64, worker_config_sha256="3" * 64,
        source_read_ref="session-reply-" + "4" * 64, source_event_sha256="5" * 64,
        published_epoch_seconds=NOW,
    )
    values.update(changes)
    return build_publication_receipt(**values)


def verify(value, **changes):
    values = dict(grant=parsed(), installed_release_sha="a" * 40,
                  control_config_sha256="2" * 64, worker_config_sha256="3" * 64)
    values.update(changes)
    return verify_publication_receipt(value, **values)


def test_publication_is_closed_deterministic_and_matches_postimage():
    value = receipt()
    assert value == receipt()
    assert DialogueWakeCanaryPublicationReceipt.from_dict(value.to_dict()) == value
    verify(value)


@pytest.mark.parametrize("change", ["missing", "extra", "bool_epoch", "invalid_digest", "wrong_operation"])
def test_publication_refuses_malformed_evidence(change):
    value = receipt().to_dict()
    if change == "missing":
        del value["source_read_ref"]
    elif change == "extra":
        value["armed"] = True
    elif change == "bool_epoch":
        value["published_epoch_seconds"] = True
    elif change == "invalid_digest":
        value["grant_digest"] = "g" * 64
    else:
        value["operation"] = "CEO_SUBMIT_ARM"
    with pytest.raises(ValueError):
        DialogueWakeCanaryPublicationReceipt.from_dict(value)


@pytest.mark.parametrize("change", [
    {"current": facts(binding_generation=8)},
    {"published_epoch_seconds": NOW - 61},
    {"published_epoch_seconds": NOW + 60},
    {"published_epoch_seconds": True},
])
def test_publication_cannot_bypass_current_match_or_grant_window(change):
    with pytest.raises(ValueError):
        receipt(**change)


@pytest.mark.parametrize("change", [
    {"installed_release_sha": "b" * 40},
    {"control_config_sha256": "6" * 64},
    {"worker_config_sha256": "7" * 64},
    {"grant": parsed(binding_generation=8)},
])
def test_publication_refuses_changed_installed_postimage(change):
    with pytest.raises(ValueError):
        verify(receipt(), **change)


@pytest.mark.parametrize("field", ["grant_digest", "facts_sha256"])
def test_publication_refuses_tampered_derived_digests(field):
    value = dataclasses.replace(receipt(), **{field: "6" * 64})
    with pytest.raises(ValueError):
        verify(value)

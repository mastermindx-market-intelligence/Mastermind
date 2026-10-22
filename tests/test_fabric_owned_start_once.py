"""Original-handle publication entry cannot be renewed by corrected inputs."""
import asyncio
import dataclasses

import pytest
from test_fabric_owned_start_assembly import lr, producer, world


def test_validation_refusal_cannot_republish_after_pin_correction(world):
    valid_pin = world.pin
    world.pin = dataclasses.replace(valid_pin, inode=valid_pin.inode + 1)
    with pytest.raises(producer.OwnedStartRefused, match='pinned_binary'):
        producer.publish_owned_start(**world.kwargs())
    assert world.holds == ['owned_start_validation_unconfirmed']
    assert world.owner._start_assembly_attempted
    assert not world.owner._start_publication_attempted
    assert not world.owner._original_start_receipt_path.exists()
    world.pin = valid_pin
    with pytest.raises(producer.OwnedStartRefused, match='already_attempted'):
        producer.publish_owned_start(**world.kwargs())
    assert world.holds == ['owned_start_validation_unconfirmed']
    assert not world.owner._original_start_receipt_path.exists()
    assert world.owner._finisher is world.finisher
    assert world.owner.process.poll() is None


def test_cancelled_validation_consumes_the_original_entry(world, monkeypatch):
    previous = producer._require_control_authority
    def cancel(authority, material):
        raise asyncio.CancelledError()
    monkeypatch.setattr(producer, '_require_control_authority', cancel)
    with pytest.raises(asyncio.CancelledError):
        producer.publish_owned_start(**world.kwargs())
    assert world.owner._start_assembly_attempted
    assert not world.owner._start_publication_attempted
    monkeypatch.setattr(producer, '_require_control_authority', previous)
    with pytest.raises(producer.OwnedStartRefused, match='already_attempted'):
        producer.publish_owned_start(**world.kwargs())
    assert world.holds == ['owned_start_validation_unconfirmed']
    assert not world.owner._original_start_receipt_path.exists()
    assert world.owner._finisher is world.finisher
    assert world.owner.process.poll() is None

"""Pure disabled-to-enabled release-owner registration activation contract."""
import dataclasses
import hashlib

import pytest

from control_plane import executive_release_factory as factory
from ops.executive_os import release_owner_registration_activation as subject
from ops.executive_os import release_owner_resident_inputs as resident
from tests.test_executive_release_controller_policy import inputs
from tests.test_executive_release_factory import image


def _disabled_registration(image) -> bytes:
    current = factory.registration(
        factory.file_document(image["files"][factory._REGISTRATION])
    )
    current["enabled"] = False
    return resident.canonical_file_bytes(current)


def test_plan_flips_only_enabled_and_preserves_exact_preimage(image):
    disabled = _disabled_registration(image)
    plan = subject.compile_registration_activation(disabled)

    assert plan.before_bytes == disabled
    before = factory.registration(factory.file_document(plan.before_bytes))
    after = factory.registration(factory.file_document(plan.after_bytes))
    assert before["enabled"] is False
    assert after["enabled"] is True
    assert {
        name: (before[name], after[name])
        for name in before
        if before[name] != after[name]
    } == {"enabled": (False, True)}
    for name in (
        "owner_installation_id",
        "target_ref",
        "key_id",
        "trust_generation",
        "app_generation",
        "registration_generation",
    ):
        assert type(after[name]) is type(before[name])
        assert after[name] == before[name]

    assert plan.before_sha256 == hashlib.sha256(plan.before_bytes).hexdigest()
    assert plan.after_sha256 == hashlib.sha256(plan.after_bytes).hexdigest()
    assert plan.before_sha256 != plan.after_sha256
    assert subject.compile_registration_activation(disabled) == plan

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        plan.after_bytes = b"changed"


def test_enabled_postimage_is_consumed_by_existing_factory(image):
    disabled = _disabled_registration(image)
    image["files"][factory._REGISTRATION] = disabled
    assert factory.build_release_owner(image["config"]) is None

    plan = subject.compile_registration_activation(disabled)
    image["files"][factory._REGISTRATION] = plan.after_bytes
    owner = factory.build_release_owner(image["config"])

    assert owner is not None
    snapshot = owner._snapshot(image["transition"])
    assert snapshot.effect.to_dict() == image["effect"]


def test_enabled_preimage_is_refused_without_rotation(image):
    enabled = image["files"][factory._REGISTRATION]
    parsed = factory.registration(factory.file_document(enabled))
    assert parsed["enabled"] is True

    with pytest.raises(
        subject.RegistrationActivationError,
        match="^ACTIVATION_PREIMAGE_NOT_DISABLED$",
    ):
        subject.compile_registration_activation(enabled)


@pytest.mark.parametrize("mutator", [
    lambda raw: raw + b" ",
    lambda raw: raw[:-1],
    lambda raw: b" " + raw,
    lambda raw: raw.replace(b'"enabled":false', b'"enabled":0'),
])
def test_noncanonical_or_wrong_type_registration_is_refused(image, mutator):
    disabled = _disabled_registration(image)
    changed = mutator(disabled)
    assert changed != disabled

    with pytest.raises(
        subject.RegistrationActivationError,
        match="^ACTIVATION_REGISTRATION_INVALID$",
    ):
        subject.compile_registration_activation(changed)


def test_extra_field_and_generation_rotation_are_refused(image):
    disabled = _disabled_registration(image)
    document = factory.file_document(disabled)

    extra = dict(document)
    extra["unexpected"] = "value"
    extra_raw = (
        factory.contract.canonical_release_bytes(extra) + b"\n"
    )
    with pytest.raises(
        subject.RegistrationActivationError,
        match="^ACTIVATION_REGISTRATION_INVALID$",
    ):
        subject.compile_registration_activation(extra_raw)

    wrong_generation = dict(document)
    wrong_generation["registration_generation"] = True
    wrong_raw = (
        factory.contract.canonical_release_bytes(wrong_generation) + b"\n"
    )
    with pytest.raises(
        subject.RegistrationActivationError,
        match="^ACTIVATION_REGISTRATION_INVALID$",
    ):
        subject.compile_registration_activation(wrong_raw)


def test_plan_has_no_ambient_effects(image, monkeypatch):
    import builtins
    import os
    from pathlib import Path
    import socket
    import subprocess
    import time
    import uuid

    disabled = _disabled_registration(image)

    def forbidden(*args, **kwargs):
        raise AssertionError("activation plan used ambient effect")

    with monkeypatch.context() as guard:
        for module, names in (
            (builtins, ("open",)),
            (os, ("open", "getenv", "urandom", "rename", "replace", "unlink")),
            (Path, ("read_bytes", "read_text", "write_bytes", "write_text")),
            (socket, ("socket", "create_connection")),
            (subprocess, ("Popen", "run", "check_output")),
            (time, ("time", "time_ns", "monotonic", "monotonic_ns")),
            (uuid, ("uuid4",)),
        ):
            for name in names:
                guard.setattr(module, name, forbidden)

        plan = subject.compile_registration_activation(disabled)

    assert factory.file_document(plan.before_bytes)["enabled"] is False
    assert factory.file_document(plan.after_bytes)["enabled"] is True

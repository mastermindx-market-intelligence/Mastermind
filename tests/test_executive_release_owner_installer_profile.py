"""Fixed installer-profile producer contract; source-only, no host proof."""
import hashlib

import pytest

from control_plane import executive_release_factory as factory
from ops.executive_os import release_owner_installer_profile as subject
from ops.executive_os import release_owner_staged_inputs as staged
from tests.test_executive_release_controller_policy import inputs
from tests.test_executive_release_factory import image, wire
from tests.test_executive_release_owner_staged_inputs import arguments


EXPECTED_DIGESTS = {
    ("executive.release.rollback", "exact_protected_master"):
        "0e9e4c865c28d012a36a7bb3b0dffb5d6baa6b3f8fa6329948dc6dec152b02ef",
    ("executive.release.rollback", "frozen_accepted_ancestor"):
        "08a53c2603938df72c4b8d6a1449accf03de29df4002f31bf5528e0643da95a0",
    ("executive.release.upgrade", "exact_protected_master"):
        "74afbb3f592ab5863d4ad6c482d9be7adf73b0e9fcc43a264b2fd0ecc078b1c3",
    ("executive.release.upgrade", "frozen_accepted_ancestor"):
        "732edde89f66acb4a0048c5d5a981d604417e4c431068013a593130397d6e18d",
}


@pytest.mark.parametrize("action,mode", sorted(EXPECTED_DIGESTS))
def test_all_closed_profiles_are_exact_canonical_and_digest_pinned(action, mode):
    raw = subject.compile_installer_profile(
        action=action,
        source_policy_mode=mode,
    )
    document = factory.file_document(raw)
    assert document == {
        "schema": "mastermind.executive_release_installer_profile/v1",
        "profile_id": "mastermind-executive-darwin-arm64",
        "profile_version": 1,
        "repository": "mastermindx-market-intelligence/Mastermind",
        "platform": "darwin",
        "architecture": "arm64",
        "source_policy_mode": mode,
        "action": action,
    }
    canonical = factory.contract.canonical_release_bytes(document)
    assert raw == canonical + b"\n"
    assert raw.count(b"\n") == 1
    digest = hashlib.sha256(canonical).hexdigest()
    assert digest == EXPECTED_DIGESTS[(action, mode)]
    assert subject.installer_profile_digest(
        action=action,
        source_policy_mode=mode,
    ) == digest
    assert subject.compile_installer_profile(
        action=action,
        source_policy_mode=mode,
    ) == raw


@pytest.mark.parametrize("field,value,code", [
    ("action", "executive.release.install", "INSTALLER_PROFILE_ACTION"),
    ("action", "", "INSTALLER_PROFILE_ACTION"),
    ("action", True, "INSTALLER_PROFILE_ACTION"),
    ("action", 1, "INSTALLER_PROFILE_ACTION"),
    ("source_policy_mode", "latest", "INSTALLER_PROFILE_SOURCE_MODE"),
    ("source_policy_mode", "", "INSTALLER_PROFILE_SOURCE_MODE"),
    ("source_policy_mode", True, "INSTALLER_PROFILE_SOURCE_MODE"),
    ("source_policy_mode", 1, "INSTALLER_PROFILE_SOURCE_MODE"),
])
def test_profile_refuses_any_value_outside_existing_contract(field, value, code):
    values = {
        "action": "executive.release.upgrade",
        "source_policy_mode": "exact_protected_master",
    }
    values[field] = value
    with pytest.raises(subject.InstallerProfileError, match=f"^{code}$"):
        subject.compile_installer_profile(**values)
    with pytest.raises(subject.InstallerProfileError, match=f"^{code}$"):
        subject.installer_profile_digest(**values)


def test_upgrade_profile_is_accepted_by_existing_staged_compiler(image):
    values = arguments(image)
    profile = subject.compile_installer_profile(
        action="executive.release.upgrade",
        source_policy_mode="exact_protected_master",
    )
    profile_digest = subject.installer_profile_digest(
        action="executive.release.upgrade",
        source_policy_mode="exact_protected_master",
    )
    values["installer_profile"] = profile
    compatibility = factory.file_document(values["compatibility_proof"])
    compatibility["installer_profile_digest"] = profile_digest
    values["compatibility_proof"] = wire(compatibility)

    result = staged.compile_staged_inputs(**values)
    files = dict(result.files)
    assert files["installer-profile.json"] == profile
    effect = factory.file_document(files["effect.json"])
    assert effect["installer_profile_digest"] == profile_digest
    assert effect["action"] == "executive.release.upgrade"
    assert effect["source_policy_mode"] == "exact_protected_master"


def test_compiler_and_digest_have_no_ambient_effects(monkeypatch):
    import builtins
    import os
    from pathlib import Path
    import socket
    import subprocess
    import time
    import uuid

    def forbidden(*args, **kwargs):
        raise AssertionError("installer profile compiler used ambient effect")

    with monkeypatch.context() as guard:
        for module, names in (
            (builtins, ("open",)),
            (os, ("open", "getenv", "urandom")),
            (Path, ("read_bytes", "read_text", "write_bytes", "write_text")),
            (socket, ("socket", "create_connection")),
            (subprocess, ("Popen", "run", "check_output")),
            (time, ("time", "time_ns", "monotonic", "monotonic_ns")),
            (uuid, ("uuid4",)),
        ):
            for name in names:
                guard.setattr(module, name, forbidden)

        raw = subject.compile_installer_profile(
            action="executive.release.rollback",
            source_policy_mode="frozen_accepted_ancestor",
        )
        digest = subject.installer_profile_digest(
            action="executive.release.rollback",
            source_policy_mode="frozen_accepted_ancestor",
        )

    assert factory.file_document(raw)["action"] == "executive.release.rollback"
    assert digest == EXPECTED_DIGESTS[
        ("executive.release.rollback", "frozen_accepted_ancestor")
    ]

"""Fail-closed tests for the recovered, unarmed GitHub review host policy."""
import dataclasses

import pytest

from control_plane.github_review_host_config import (
    ReviewHostConfigError,
    ReviewHostGateRefused,
    ReviewHostSettings,
    closed_pull_number,
)


def _valid(**changes):
    values = dict(
        expected_host="127.0.0.1",
        require_https=False,
        installation_id=123,
        installation_ids=frozenset({123}),
        repositories=frozenset({"example/repo"}),
        configured_reviewer="review-bot",
        authorized_actors=frozenset({"alice"}),
    )
    values.update(changes)
    return ReviewHostSettings(**values)


def test_host_policy_is_disabled_even_when_other_settings_valid():
    settings = _valid()
    assert settings.enabled is False
    assert settings.publication_enabled is False
    with pytest.raises(ReviewHostGateRefused):
        settings.require_enabled()
    with pytest.raises(ReviewHostGateRefused):
        settings.require_publication_enabled()


def test_host_can_enable_private_binding_without_publication():
    settings = _valid(enabled=True)
    settings.require_enabled()
    with pytest.raises(ReviewHostGateRefused):
        settings.require_publication_enabled()


def test_publication_requires_explicit_separate_gate():
    settings = _valid(enabled=True, publication_enabled=True)
    settings.require_enabled()
    settings.require_publication_enabled()


def test_secret_is_absent_from_configuration_receipt():
    settings = _valid()
    rendered = repr(settings) + repr(settings.to_dict())
    assert "webhook_secret" not in rendered
    assert "token" not in rendered
    assert "123" in rendered


@pytest.mark.parametrize("changes", [
    {"installation_id": 999},
    {"require_https": True},
    {"max_body_bytes": (1 << 20) + 1},
    {"minimum_actor_permission": "read"},
    {"job_priority": True},
    {"job_authority_level": "A7"},
    {"delivery_path": "/bad/"},
])
def test_invalid_configuration_refused(changes):
    with pytest.raises(ReviewHostConfigError):
        _valid(**changes)


def test_signed_pr_payload_number_must_be_exact():
    payload = {"pull_request": {"number": 1741}}
    assert closed_pull_number(payload, event="pull_request") == 1741
    assert closed_pull_number({"pull_request": {"number": True}}, event="pull_request") is None
    assert closed_pull_number({"pull_request": {"number": "1741"}}, event="pull_request") is None


def test_issue_comment_cannot_use_plain_issue():
    assert closed_pull_number({"issue": {"number": 1741}}, event="issue_comment") is None
    assert closed_pull_number(
        {"issue": {"number": 1741, "pull_request": {}}}, event="issue_comment"
    ) == 1741


def test_default_constructor_requires_explicit_host_enrollment():
    with pytest.raises(ReviewHostConfigError):
        ReviewHostSettings()

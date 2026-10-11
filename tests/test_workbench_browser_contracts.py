from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from control_plane.browser_resource_contract import BrowserMode
from integrations.workbench_browser_mcp.contracts import (
    BrowserContractError,
    BrowserRefCodec,
    BrowserResourceRef,
    PreparedBrowserAction,
    PreparedBrowserStart,
    canonical_browser_arguments,
    validate_browser_resource_ref,
    validate_prepared_browser_action,
    validate_prepared_browser_start,
)


def _start(**overrides):
    values = dict(
        schema="mastermind.workbench_browser_start.v1",
        action_id="1" * 32,
        subject_digest="2" * 64,
        client_ref="client:abc",
        resource="https://workbench.example/browser",
        project_ref="project:browser",
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:1",
        root_device=1,
        root_inode=2,
        store_device=3,
        store_inode=4,
        host_id="5" * 64,
        boot_session_id="boot:abc",
        mode=BrowserMode.ISOLATED.value,
        profile_ref=None,
        issued_at_ms=1000,
        expires_at_ms=2000,
        resource_expires_at_ms=8000,
    )
    values.update(overrides)
    return PreparedBrowserStart(**values)


def _resource(**overrides):
    values = dict(
        schema="mastermind.workbench_browser_ref.v1",
        start_action_id="1" * 32,
        subject_digest="2" * 64,
        client_ref="client:abc",
        resource="https://workbench.example/browser",
        project_ref="project:browser",
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:1",
        host_id="5" * 64,
        boot_session_id="boot:abc",
        relay_pid=1234,
        relay_start_identity="1700000000.000001",
        relay_pgid=1234,
        relay_session_id=1234,
        mode=BrowserMode.ISOLATED.value,
        profile_ref=None,
        tool_schema_digest="6" * 64,
        issued_at_ms=1100,
        expires_at_ms=2000,
    )
    values.update(overrides)
    return BrowserResourceRef(**values)


def _action(browser_ref: str, **overrides):
    values = dict(
        schema="mastermind.workbench_browser_action.v1",
        action_id="7" * 32,
        browser_ref_sha256=hashlib.sha256(browser_ref.encode()).hexdigest(),
        subject_digest="2" * 64,
        client_ref="client:abc",
        resource="https://workbench.example/browser",
        project_ref="project:browser",
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:1",
        host_id="5" * 64,
        boot_session_id="boot:abc",
        tool_name="browser_click",
        arguments_json=canonical_browser_arguments({"target": "button"}),
        issued_at_ms=1200,
        expires_at_ms=1900,
    )
    values.update(overrides)
    return PreparedBrowserAction(**values)


def test_start_mode_profile_contract():
    validate_prepared_browser_start(_start(), now_ms=1000)
    validate_prepared_browser_start(
        _start(mode=BrowserMode.PERSISTENT.value, profile_ref="web-identity-01"),
        now_ms=1000,
    )
    with pytest.raises(BrowserContractError):
        validate_prepared_browser_start(
            _start(mode=BrowserMode.PERSISTENT.value, profile_ref=None), now_ms=1000
        )
    with pytest.raises(BrowserContractError):
        validate_prepared_browser_start(
            _start(mode=BrowserMode.ISOLATED.value, profile_ref="wrong"), now_ms=1000
        )


def test_resource_ref_requires_owned_process_identity():
    validate_browser_resource_ref(_resource(), now_ms=1100)
    for field, value in (
        ("relay_pid", 0),
        ("relay_pgid", -1),
        ("relay_session_id", 0),
        ("relay_start_identity", ""),
        ("tool_schema_digest", "x" * 64),
    ):
        with pytest.raises(BrowserContractError):
            validate_browser_resource_ref(
                dataclasses.replace(_resource(), **{field: value}), now_ms=1100
            )


def test_browser_arguments_are_canonical_and_bounded():
    encoded = canonical_browser_arguments({"b": 2, "a": [1, True, None]})
    assert encoded == '{"a":[1,true,null],"b":2}'
    assert json.loads(encoded) == {"a": [1, True, None], "b": 2}
    with pytest.raises(BrowserContractError):
        canonical_browser_arguments(["not", "an", "object"])
    with pytest.raises(BrowserContractError):
        canonical_browser_arguments({"x": float("nan")})


def test_codec_round_trips_all_three_domain_separated_refs():
    codec = BrowserRefCodec(b"k" * 32)
    start = _start()
    start_ref = codec.encode_start(start)
    assert codec.decode_start(start_ref, now_ms=1500) == start

    resource = _resource()
    browser_ref = codec.encode_resource(resource)
    assert codec.decode_resource(browser_ref, now_ms=1500) == resource

    action = _action(browser_ref)
    action_ref = codec.encode_action(action)
    assert codec.decode_action(action_ref, now_ms=1500) == action

    assert len({start_ref, browser_ref, action_ref}) == 3


def test_tamper_wrong_purpose_and_expiry_refuse():
    codec = BrowserRefCodec(b"k" * 32)
    start_ref = codec.encode_start(_start())
    browser_ref = codec.encode_resource(_resource())
    action_ref = codec.encode_action(_action(browser_ref))

    with pytest.raises(BrowserContractError):
        codec.decode_resource(start_ref, now_ms=1500)
    with pytest.raises(BrowserContractError):
        codec.decode_action(browser_ref, now_ms=1500)
    with pytest.raises(BrowserContractError):
        codec.decode_start(start_ref[:-1] + ("A" if start_ref[-1] != "A" else "B"), now_ms=1500)
    with pytest.raises(BrowserContractError):
        codec.decode_action(action_ref, now_ms=2000)


def test_action_binds_exact_browser_ref_and_allowed_tool():
    codec = BrowserRefCodec(b"k" * 32)
    browser_ref = codec.encode_resource(_resource())
    action = _action(browser_ref)
    validate_prepared_browser_action(action, now_ms=1500)
    assert action.browser_ref_sha256 == hashlib.sha256(browser_ref.encode()).hexdigest()

    with pytest.raises(BrowserContractError):
        validate_prepared_browser_action(
            dataclasses.replace(action, tool_name="browser_evaluate"), now_ms=1500
        )
    with pytest.raises(BrowserContractError):
        validate_prepared_browser_action(
            dataclasses.replace(action, arguments_json='{"a":1, "b":2}'), now_ms=1500
        )

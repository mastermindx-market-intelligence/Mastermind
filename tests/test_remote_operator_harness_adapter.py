from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from control_plane.executive_worker_broker import BrokerProtocolError
from control_plane.operator_harness_contract import (
    HarnessAdapterCapabilities,
    OPERATOR_HARNESS_INTERFACE_VERSION,
)
from control_plane.remote_codex_operator_adapter import (
    RemoteCodexOperatorAdapter,
    codex_remote_capabilities,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter


_REQUIRED = (
    "start_session",
    "begin_turn",
    "read_events",
    "interrupt_turn",
    "collect_candidate_result",
    "graceful_stop",
    "cancel",
    "reconcile",
)


def _capabilities(**changes) -> HarnessAdapterCapabilities:
    values = dict(
        interface_version=OPERATOR_HARNESS_INTERFACE_VERSION,
        supported_required_operations=_REQUIRED,
        supported_optional_operations=("resume_session",),
        supports_native_resume=True,
        supports_native_fork=False,
        supports_steering=False,
        supports_approval_response=False,
        supports_checkpoint=False,
        supports_config_staging=False,
        supports_subagent_capability_ceiling=True,
        supports_structured_events=True,
        supports_provider_native_idempotency=False,
        provider_capability_ids=("synthetic-rich-harness",),
    )
    values.update(changes)
    return HarnessAdapterCapabilities(**values)


class _Client:
    def request_sync(self, *_args, **_kwargs):  # pragma: no cover - constructor tests only
        raise AssertionError("provider/broker I/O was not expected")


def test_generic_proxy_accepts_reviewed_provider_neutral_capabilities():
    capabilities = _capabilities()
    adapter = RemoteOperatorHarnessAdapter(
        _Client(), turn_input_loader=lambda _turn: "", capabilities=capabilities
    )
    assert adapter.describe_capabilities() is capabilities


def test_codex_wrapper_is_only_a_compatibility_composition_layer():
    adapter = RemoteCodexOperatorAdapter(_Client(), turn_input_loader=lambda _turn: "")
    assert isinstance(adapter, RemoteOperatorHarnessAdapter)
    defined_methods = {
        name
        for name, value in RemoteCodexOperatorAdapter.__dict__.items()
        if inspect.isfunction(value)
    }
    assert defined_methods == {"__init__"}
    capabilities = adapter.describe_capabilities()
    assert capabilities == codex_remote_capabilities()
    assert capabilities.supported_required_operations == _REQUIRED
    assert capabilities.supported_optional_operations == ("resume_session",)
    assert capabilities.provider_capability_ids == ("codex-app-server-stdio",)


def test_generic_proxy_owns_the_current_typed_broker_operation_vocabulary():
    source = inspect.getsource(RemoteOperatorHarnessAdapter)
    for operation in (
        "ohf-validate",
        "ohf-start",
        "ohf-resume",
        "ohf-materialization-status",
        "ohf-begin-turn",
        "ohf-deliver-attention",
        "ohf-collect-turn",
        "ohf-interrupt",
        "ohf-stop",
        "ohf-cancel",
        "ohf-reconcile",
        "ohf-reconcile-absence",
    ):
        assert f'"{operation}"' in source


def test_generic_proxy_source_has_no_provider_selector_or_codex_identity():
    source = Path(inspect.getsourcefile(RemoteOperatorHarnessAdapter)).read_text()
    lowered = source.lower()
    assert "codex" not in lowered
    for forbidden in (
        "fallback_provider",
        "provider_registry",
        "factory_name",
        "provider_module",
    ):
        assert forbidden not in lowered


def test_wrong_interface_version_refuses_before_any_broker_call():
    with pytest.raises(BrokerProtocolError, match="interface version"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(interface_version="mastermind.operator_harness.v999"),
        )


def test_required_operation_profile_must_be_exact():
    with pytest.raises(BrokerProtocolError, match="required-operation"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(supported_required_operations=_REQUIRED[:-1]),
        )


def test_unimplemented_optional_capability_refuses_closed():
    with pytest.raises(BrokerProtocolError, match="unsupported optional capability"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(supports_checkpoint=True),
        )


def test_resume_operation_and_boolean_must_match_current_proxy_contract():
    with pytest.raises(BrokerProtocolError, match="optional-operation"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(
                supported_optional_operations=(),
                supports_native_resume=False,
            ),
        )
    with pytest.raises(BrokerProtocolError, match="resume capability"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(supports_native_resume=False),
        )


def test_structured_events_are_required_by_current_proxy():
    with pytest.raises(BrokerProtocolError, match="structured event"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(supports_structured_events=False),
        )

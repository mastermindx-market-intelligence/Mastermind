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


@pytest.mark.parametrize("version", ["mastermind.operator_harness/v1", "mastermind.operator_harness.v999"])
def test_wrong_interface_version_refuses_before_any_broker_call(version):
    with pytest.raises(BrokerProtocolError, match="interface version"):
        RemoteOperatorHarnessAdapter(
            _Client(),
            turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(interface_version=version),
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
                supported_optional_operations=("fork_session",),
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


# Native capability declarations are source facts, not installed admission.
def _native_claude_capabilities():
    from control_plane.claude_operator_adapter import ClaudeOperatorAdapter
    # describe_capabilities reads only the interface constant, not provider state.
    return ClaudeOperatorAdapter.describe_capabilities(object.__new__(ClaudeOperatorAdapter))


def test_native_claude_declaration_composes_without_fabricated_resume():
    capabilities = _native_claude_capabilities()
    assert capabilities.supports_native_resume is False
    assert capabilities.supported_optional_operations == ()
    adapter = RemoteOperatorHarnessAdapter(
        _Client(), turn_input_loader=lambda _turn: "", capabilities=capabilities
    )
    assert adapter.describe_capabilities() is capabilities
    assert adapter.describe_capabilities().supports_subagent_capability_ceiling is False


def test_native_no_resume_refuses_before_any_request_or_materialization():
    adapter = RemoteOperatorHarnessAdapter(
        _Client(), turn_input_loader=lambda _turn: "", capabilities=_native_claude_capabilities()
    )
    with pytest.raises(BrokerProtocolError, match="does not support native resume"):
        adapter.resume_session(operation_id=None, epoch=None, generation=None,
                               provider_session=None, requested=None)
    assert adapter._start_receipts == {}
    assert adapter._turn_results == {}


@pytest.mark.parametrize("value", [None, 0, 1, "false"])
def test_native_resume_claim_must_be_an_actual_boolean(value):
    with pytest.raises(BrokerProtocolError, match="resume capability"):
        RemoteOperatorHarnessAdapter(
            _Client(), turn_input_loader=lambda _turn: "",
            capabilities=_capabilities(supports_native_resume=value),
        )


@pytest.mark.parametrize("introspected", [False, True])
@pytest.mark.parametrize("resume", [False, True])
def test_closed_operation_shapes_preserve_actual_resume_claim(introspected, resume):
    required = (("describe_capabilities", "validate_requested_profile") if introspected else ()) + _REQUIRED
    capabilities = _capabilities(supported_required_operations=required,
                                supported_optional_operations=("resume_session",) if resume else (),
                                supports_native_resume=resume)
    adapter = RemoteOperatorHarnessAdapter(_Client(), turn_input_loader=lambda _turn: "",
                                           capabilities=capabilities)
    assert adapter.describe_capabilities() is capabilities


@pytest.mark.parametrize("required", [
    ("describe_capabilities",) + _REQUIRED,
    ("validate_requested_profile", "describe_capabilities") + _REQUIRED,
    ("describe_capabilities", "validate_requested_profile") + _REQUIRED + ("invented",),
    _REQUIRED + ("start_session",),
])
def test_extra_partial_or_reordered_required_operations_remain_closed(required):
    with pytest.raises(BrokerProtocolError, match="required-operation"):
        RemoteOperatorHarnessAdapter(_Client(), turn_input_loader=lambda _turn: "",
                                     capabilities=_capabilities(supported_required_operations=required))


def test_missing_resume_operation_cannot_advertise_resume_support():
    with pytest.raises(BrokerProtocolError, match="resume capability"):
        RemoteOperatorHarnessAdapter(_Client(), turn_input_loader=lambda _turn: "",
                                     capabilities=_capabilities(supported_optional_operations=()))


def test_protected_consultation_removal_is_not_resurrected_by_refactor():
    import control_plane.remote_codex_operator_adapter as compatibility
    for name in ("CodexConsultationIngress", "ConsultationIngressUnavailable", "ConsultationIngressRefused"):
        assert not hasattr(compatibility, name)

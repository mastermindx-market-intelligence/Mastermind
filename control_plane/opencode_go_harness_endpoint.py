"""OpenCode Go adapter for the attempt-owned loopback inference endpoint.

Go account/credential/request-policy semantics stay owned by the existing Go
transport modules.  The provider-neutral local HTTP/auth/fail-stop boundary lives
in :mod:`control_plane.attempt_inference_endpoint` so later admitted providers
can reuse that boundary without pretending to be OpenCode Go accounts.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

from control_plane.attempt_inference_endpoint import (
    AttemptInferenceBinding,
    AttemptInferenceEndpoint,
    EndpointCloseUncertain,
    InferenceEffectUnknown,
    InferenceEndpointContractError,
    InferenceForwardReceipt,
    InferenceForwardRefused,
)
from control_plane.opencode_go_pooled_transport import (
    AccountChoice,
    OpenCodeGoEffectUnknown,
    OpenCodeGoTransportContractError,
    _choice,
)
from control_plane.opencode_go_stream import StreamReceipt, stream_single_account


@dataclass(frozen=True)
class HarnessBinding:
    session_id: str
    model_id: str
    protocol: str
    account: AccountChoice
    # Supplied from the existing worker-private boundary, not generated here.
    client_capability: str = field(repr=False)


class GoHarnessEndpoint:
    """Compatibility adapter for one existing OpenCode Go account binding.

    No automatic restart, model/account changes, credential creation or retry.
    Provider key loading and request-time Go admission remain in the existing Go
    transport.  The coding child receives only the private loopback capability.
    """

    def __init__(
        self,
        binding: HarnessBinding,
        *,
        credential_loader: Callable,
        request_check: Callable,
        on_terminal_failure: Callable,
        cancel: threading.Event,
        stream: Callable = stream_single_account,
    ) -> None:
        if not isinstance(binding, HarnessBinding):
            raise OpenCodeGoTransportContractError("unsupported harness binding")
        if not isinstance(cancel, threading.Event) or not all(
            callable(value)
            for value in (credential_loader, request_check, on_terminal_failure, stream)
        ):
            raise OpenCodeGoTransportContractError("invalid endpoint dependencies")
        try:
            canonical = _choice(binding.account, pool_id=binding.account.pool_id)
        except Exception as exc:
            raise OpenCodeGoTransportContractError("account identity must be canonical") from exc
        if canonical != binding.account:
            raise OpenCodeGoTransportContractError("account identity must be canonical")

        core_binding = AttemptInferenceBinding(
            session_id=binding.session_id,
            model_id=binding.model_id,
            protocol=binding.protocol,
            route_id=binding.account.account_id,
            route_generation=binding.account.pool_generation,
            client_capability=binding.client_capability,
        )

        def forward(request, *, on_chunk, cancel):  # noqa: ANN001
            try:
                result = stream(
                    request,
                    choice=binding.account,
                    credential_loader=credential_loader,
                    request_check=request_check,
                    on_chunk=on_chunk,
                    cancel=cancel,
                )
            except OpenCodeGoEffectUnknown as exc:
                raise InferenceEffectUnknown("OpenCode Go provider effect is unresolved") from exc
            except OpenCodeGoTransportContractError as exc:
                raise InferenceForwardRefused("OpenCode Go request admission refused") from exc
            except Exception as exc:
                raise InferenceEffectUnknown("OpenCode Go forwarding failed") from exc
            if not isinstance(result, StreamReceipt):
                raise InferenceEffectUnknown("OpenCode Go returned an unsupported receipt")
            return InferenceForwardReceipt(
                route_id=result.account_id,
                route_generation=result.pool_generation,
                http_status=result.http_status,
                bytes_forwarded=result.bytes_forwarded,
                terminal_observed=result.terminal_observed,
            )

        try:
            self._core = AttemptInferenceEndpoint(
                core_binding,
                forward=forward,
                on_terminal_failure=on_terminal_failure,
                cancel=cancel,
                thread_prefix="go",
            )
        except InferenceEndpointContractError as exc:
            raise OpenCodeGoTransportContractError(str(exc)) from None
        self.binding = binding

    @property
    def base_url(self) -> str:
        try:
            return self._core.base_url
        except InferenceEndpointContractError as exc:
            raise OpenCodeGoTransportContractError(str(exc)) from None

    @property
    def stopped_forwarding(self) -> bool:
        return self._core.stopped_forwarding

    @property
    def failure_notification_failed(self) -> bool:
        return self._core.failure_notification_failed

    def __enter__(self) -> "GoHarnessEndpoint":
        try:
            self._core.__enter__()
        except InferenceEndpointContractError as exc:
            raise OpenCodeGoTransportContractError(str(exc)) from None
        return self

    def __exit__(self, *error) -> None:  # noqa: ANN002
        self.close()

    def close(self) -> None:
        self._core.close()

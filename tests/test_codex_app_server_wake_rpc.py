from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass, field
from typing import Any, Mapping

import pytest

from control_plane.wake_dispatcher import WakePreSubmitError
from integrations.executive_wake.codex_app_server import CODEX_WAKE_INSTRUCTION
from integrations.executive_wake.codex_app_server_rpc import CodexAppServerRpcWakeClient


NATIVE_HANDLE = "019cafe0-1111-7222-8333-abcdefabcdef"
NUDGE_ID = "nudge-123"
OPAQUE_IDS = ("WAKE-123", "WAKE-123:ATTEMPT:1")


@dataclass
class FakeAppServerClient:
    resume_id: str = NATIVE_HANDLE
    turn_id: str = "turn-456"
    fail_method: str | None = None
    completion: Mapping[str, Any] | None = None
    calls: list[tuple[str, object]] = field(default_factory=list)

    def start(self) -> None:
        self.calls.append(("start", None))
        if self.fail_method == "start":
            raise RuntimeError("start failed")

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        self.calls.append((method, dict(params or {})))
        if self.fail_method == method:
            raise RuntimeError(f"{method} failed")
        if method == "initialize":
            return {}
        if method == "thread/resume":
            return {"thread": {"id": self.resume_id}}
        if method == "turn/start":
            return {"turn": {"id": self.turn_id}}
        raise AssertionError(f"unexpected request method {method}")

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self.calls.append((method, dict(params or {})))
        if self.fail_method == method:
            raise RuntimeError(f"{method} failed")

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]:
        self.calls.append((f"wait:{method}", timeout))
        if self.fail_method == f"wait:{method}":
            raise queue.Empty()
        if self.fail_method == "wait:turn/completed-transport":
            raise RuntimeError(f"app-server exited before {method}")
        if self.completion is not None:
            return dict(self.completion)
        return {
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": self.turn_id, "status": "completed"},
            },
        }

    def close(self) -> None:
        self.calls.append(("close", None))


def _deliver(fake: FakeAppServerClient):
    client = CodexAppServerRpcWakeClient(
        client_factory=lambda: fake,
        request_timeout_seconds=2.0,
        completion_timeout_seconds=3.0,
    )
    return asyncio.run(
        client.deliver_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
        )
    )


def _method_names(fake: FakeAppServerClient) -> list[str]:
    return [name for name, _payload in fake.calls]


def test_exact_running_thread_is_resumed_then_started_once() -> None:
    fake = FakeAppServerClient()

    observation = _deliver(fake)

    assert observation.native_handle == NATIVE_HANDLE
    assert observation.nudge_id == NUDGE_ID
    assert observation.accepted is True
    assert observation.delivered is True
    assert _method_names(fake) == [
        "start",
        "initialize",
        "initialized",
        "thread/resume",
        "turn/start",
        "wait:turn/completed",
        "close",
    ]
    requests = {name: payload for name, payload in fake.calls if isinstance(payload, dict)}
    assert requests["thread/resume"] == {"threadId": NATIVE_HANDLE}
    assert requests["turn/start"]["threadId"] == NATIVE_HANDLE
    assert requests["turn/start"]["clientUserMessageId"] == NUDGE_ID
    assert requests["turn/start"]["input"][0]["type"] == "text"
    assert requests["turn/start"]["input"][0]["text_elements"] == []
    text = requests["turn/start"]["input"][0]["text"]
    assert CODEX_WAKE_INSTRUCTION in text
    for opaque_id in OPAQUE_IDS:
        assert opaque_id in text
    assert "thread/start" not in _method_names(fake)
    assert "thread/fork" not in _method_names(fake)


@pytest.mark.parametrize("failure", ["start", "initialize", "initialized", "thread/resume"])
def test_failure_before_turn_start_is_definite_pre_submit_refusal(failure: str) -> None:
    fake = FakeAppServerClient(fail_method=failure)

    with pytest.raises(WakePreSubmitError) as error:
        _deliver(fake)

    assert error.value.outcome.value == "TARGET_UNAVAILABLE"
    assert error.value.reason_code == "target_unavailable"
    assert "turn/start" not in _method_names(fake)
    assert _method_names(fake)[-1] == "close"


def test_resume_identity_mismatch_refuses_before_turn_start() -> None:
    fake = FakeAppServerClient(resume_id="019cafe0-9999-7222-8333-abcdefabcdef")

    with pytest.raises(WakePreSubmitError):
        _deliver(fake)

    assert "turn/start" not in _method_names(fake)
    assert _method_names(fake)[-1] == "close"


def test_turn_start_failure_is_post_submit_uncertainty_not_safe_refusal() -> None:
    fake = FakeAppServerClient(fail_method="turn/start")

    with pytest.raises(RuntimeError, match="turn/start failed") as error:
        _deliver(fake)

    assert not isinstance(error.value, WakePreSubmitError)
    assert _method_names(fake)[-1] == "close"


def test_completion_timeout_is_accepted_but_not_delivered() -> None:
    fake = FakeAppServerClient(fail_method="wait:turn/completed")

    observation = _deliver(fake)

    assert observation.accepted is True
    assert observation.delivered is False
    assert _method_names(fake).count("turn/start") == 1
    assert _method_names(fake)[-1] == "close"


def test_post_submit_transport_loss_is_effect_unknown_not_accepted() -> None:
    fake = FakeAppServerClient(fail_method="wait:turn/completed-transport")

    with pytest.raises(RuntimeError, match="app-server exited") as error:
        _deliver(fake)

    assert not isinstance(error.value, WakePreSubmitError)
    assert _method_names(fake).count("turn/start") == 1
    assert _method_names(fake)[-1] == "close"


@pytest.mark.parametrize(
    "completion",
    [
        {
            "method": "turn/completed",
            "params": {
                "threadId": "019cafe0-9999-7222-8333-abcdefabcdef",
                "turn": {"id": "turn-456", "status": "completed"},
            },
        },
        {
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": "turn-foreign", "status": "completed"},
            },
        },
    ],
)
def test_foreign_completion_identity_is_effect_unknown(completion: Mapping[str, Any]) -> None:
    fake = FakeAppServerClient(completion=completion)

    with pytest.raises(RuntimeError, match="completion identity") as error:
        _deliver(fake)

    assert not isinstance(error.value, WakePreSubmitError)
    assert _method_names(fake).count("turn/start") == 1
    assert _method_names(fake)[-1] == "close"

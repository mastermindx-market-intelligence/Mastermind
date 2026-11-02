"""Offline acceptance checks for the opt-in Experiential Labs gateway."""
import json

import httpx
import pytest

from brain import client, explabs_client, explabs_pool


def test_minimal_wire_body_auth_and_exact_model(monkeypatch):
    monkeypatch.setenv("EXPLABS_API_KEY", "example-not-a-real-key")
    monkeypatch.setenv("EXPLABS_BASE_URL", explabs_client.BASE_URL)
    monkeypatch.setenv("EXPLABS_MODEL", "deepseek-v4.1-flash")
    requests = []

    def serve(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == explabs_client.BASE_URL + "/chat/completions"
        assert request.headers["Authorization"] == "Bearer example-not-a-real-key"
        assert json.loads(request.content) == {
            "model": "deepseek-v4.1-flash",
            "messages": [{"role": "user", "content": "Reply OK"}],
        }
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4.1-flash",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 2, "cost": 0.000004},
                "provider": "experiential_cloud",
                "is_byok": False,
            },
            headers={"x-request-id": "test-request-id"},
        )

    with httpx.Client(transport=httpx.MockTransport(serve)) as test_http:
        reply = explabs_client.complete("", "Reply OK", client=test_http)
    assert len(requests) == 1
    assert reply.text == "OK"
    assert reply.cost_usd == pytest.approx(0.000004)
    assert reply.input_tokens == 7
    assert reply.output_tokens == 2
    assert reply.provider == "experiential_cloud"
    assert not reply.is_byok
    assert reply.request_id == "test-request-id"


def test_no_key_fails_before_network(monkeypatch):
    monkeypatch.delenv("EXPLABS_API_KEY", raising=False)
    assert not explabs_client.available()
    with pytest.raises(explabs_client.ExperientialError, match="explabs_missing_key"):
        explabs_client.complete("", "Hello")


def test_noncanonical_base_url_fails_before_network(monkeypatch):
    monkeypatch.setenv("EXPLABS_API_KEY", "example-not-a-real-key")
    monkeypatch.setenv("EXPLABS_BASE_URL", "https://other.example/v1")
    with pytest.raises(explabs_client.ExperientialError, match="explabs_invalid_base_url"):
        explabs_client.complete("", "Hello")


@pytest.mark.parametrize("status, code", [(401, "invalid_key"), (403, "model_not_granted")])
def test_http_error_is_sanitized(monkeypatch, status, code):
    monkeypatch.setenv("EXPLABS_API_KEY", "example-not-a-real-key")
    monkeypatch.setenv("EXPLABS_BASE_URL", explabs_client.BASE_URL)

    def fail(request):
        return httpx.Response(
            status,
            json={"error": {"message": "private-secret-must-not-escape", "code": code}},
        )

    with httpx.Client(transport=httpx.MockTransport(fail)) as test_http:
        with pytest.raises(explabs_client.ExperientialError) as caught:
            explabs_client.complete("", "Hello", client=test_http)
    assert str(caught.value) == f"explabs_http_{status}:{code}"
    assert "private-secret-must-not-escape" not in str(caught.value)


def test_explicit_backend_records_reported_cost(monkeypatch):
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    monkeypatch.setenv("EXPLABS_API_KEY", "example-not-a-real-key")
    monkeypatch.setattr(explabs_pool, "available", lambda: True)
    monkeypatch.setattr(
        explabs_pool,
        "complete",
        lambda system, user: explabs_client.Completion(
            text="OK",
            model="deepseek-v4.1-flash",
            input_tokens=7,
            output_tokens=2,
            cost_usd=0.000004,
            provider="experiential_cloud",
            is_byok=False,
            request_id="fixture",
            account_slot="1",
        ),
    )
    from brain import cost_guard

    received = []
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: received.append((args, kwargs)))
    assert client.backend() == "explabs"
    assert client.available()
    assert client.call_model("system", "user", role="analyst") == ("OK", None)
    assert len(received) == 1
    assert received[0][0][1] == pytest.approx(0.000004)
    assert received[0][1]["model"] == "deepseek-v4.1-flash"
    assert received[0][1]["key_id"] == "explabs_account_1"


def test_default_remains_unmodified(monkeypatch):
    monkeypatch.delenv("BOT_LLM_BACKEND", raising=False)
    assert client.backend() == "waterfall"

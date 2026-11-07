"""Wire-level bounds and recovery: no mutation replay or credential rerouting."""
import json

import httpx
import pytest

from control_plane.github_review_intent_ingress import PublicationEffectUnknown
from integrations.github_review_api import (
    GitHubReviewAPI, GitHubReviewAPIUnavailable, GitHubReviewReadDeferred,
)
from test_github_review_api import REPO, SHA, PUBLISHER_USER_ID, Tokens, pr


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks, clock=None):
        self.chunks = chunks
        self.consumed = 0
        self.closed = False
        self.clock = clock

    def __iter__(self):
        for chunk in self.chunks:
            self.consumed += 1
            if self.clock:
                self.clock.now += 1.1
            yield chunk

    def close(self):
        self.closed = True


def adapter(wire, *, tokens=None, clock=None):
    tick = clock or Clock()
    return GitHubReviewAPI(
        repository=REPO, installation_id=4242,
        publisher_login="reviewer-bot[bot]", publisher_user_id=PUBLISHER_USER_ID,
        token_source=tokens or Tokens(),
        client=httpx.Client(transport=httpx.MockTransport(wire)),
        clock=tick, sleep=tick.sleep, wall_clock=lambda: 1000.0,
    )


def read(api):
    return api.read_pull_request(repository=REPO, pull_number=42)


@pytest.mark.parametrize("failure", ["timeout", 500, 502, 503, 504])
def test_one_transient_get_failure_recovers_with_same_token_and_route(failure):
    calls, token, clock = [], Tokens(), Clock()

    def wire(req):
        calls.append(req)
        if len(calls) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("private endpoint detail", request=req)
            return httpx.Response(failure)
        return httpx.Response(200, json=pr())

    assert read(adapter(wire, tokens=token, clock=clock)).head_sha == SHA
    assert len(calls) == 2 and token.calls == 1 and clock.now == 0.1
    assert calls[0].url == calls[1].url
    assert calls[0].headers["authorization"] == calls[1].headers["authorization"]
    assert calls[0].headers["accept-encoding"] == "identity"
    assert calls[1].extensions["timeout"]["read"] < calls[0].extensions["timeout"]["read"]


def test_get_recovery_is_bounded_to_two_attempts_and_one_budget():
    calls, clock = [], Clock()

    def wire(req):
        calls.append(req)
        return httpx.Response(503)

    with pytest.raises(GitHubReviewAPIUnavailable, match="READ_UNAVAILABLE"):
        read(adapter(wire, clock=clock))
    assert len(calls) == 2 and clock.now == 0.1
    calls.clear()

    def slow(req):
        calls.append(req)
        clock.now += 3.0
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(GitHubReviewAPIUnavailable, match="BUDGET_EXHAUSTED"):
        read(adapter(slow, clock=clock))
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 403, 404, 302, 422])
def test_auth_missing_source_schema_and_redirect_failures_are_not_retried(status):
    calls = []

    def wire(req):
        calls.append(req)
        return httpx.Response(status, headers={"location": "https://untrusted.example"})

    with pytest.raises(GitHubReviewAPIUnavailable):
        read(adapter(wire))
    assert len(calls) == 1 and calls[0].url.host == "api.github.com"


@pytest.mark.parametrize("status,headers,delay", [
    (429, {}, 60), (429, {"retry-after": "10"}, 10),
    (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1120"}, 120),
    (503, {"retry-after": "7"}, 7),
    (429, {"retry-after": "Thu, 01 Jan 1970 00:18:20 GMT"}, 100),
])
def test_server_deferral_stops_network_without_sleeping_or_spending_another_token(status, headers, delay):
    calls, token, clock = [], Tokens(), Clock()

    def wire(req):
        calls.append(req)
        return httpx.Response(status, headers=headers)

    api = adapter(wire, tokens=token, clock=clock)
    for _ in range(2):
        with pytest.raises(GitHubReviewReadDeferred) as error:
            read(api)
        assert error.value.retry_after_seconds == delay
    assert len(calls) == token.calls == 1 and clock.now == 0.0
    clock.now = delay + 1
    with pytest.raises(GitHubReviewReadDeferred):
        read(api)
    assert len(calls) == token.calls == 2


@pytest.mark.parametrize("headers", [
    {"content-length": str((1 << 20) + 1)}, {"content-encoding": "gzip"},
])
def test_unacceptable_response_headers_close_before_consuming_body(headers):
    stream = Stream([b"x" * 16384] * 1000)
    api = adapter(lambda req: httpx.Response(200, headers=headers, stream=stream))
    with pytest.raises(GitHubReviewAPIUnavailable):
        read(api)
    assert stream.closed and stream.consumed == 0


def test_unadvertised_large_body_is_stopped_at_limit_instead_of_fully_buffered():
    stream = Stream([b"x" * 16384] * 1000)
    api = adapter(lambda req: httpx.Response(200, stream=stream))
    with pytest.raises(GitHubReviewAPIUnavailable, match="OVER_BOUND"):
        read(api)
    assert stream.closed and stream.consumed == 65


@pytest.mark.parametrize("chunk", [b"x", b"x" * 16384])
def test_drip_stream_cannot_keep_operation_alive_between_chunks(chunk):
    clock = Clock()
    stream = Stream([chunk] * 1000, clock=clock)
    api = adapter(lambda req: httpx.Response(200, stream=stream), clock=clock)
    with pytest.raises(GitHubReviewAPIUnavailable, match="BUDGET_EXHAUSTED"):
        read(api)
    assert stream.closed and stream.consumed == 3


def test_valid_chunked_json_is_decoded_without_buffered_response_access():
    raw = json.dumps(pr()).encode()
    stream = Stream([raw[:30], raw[30:]])
    assert read(adapter(lambda req: httpx.Response(200, stream=stream))).head_sha == SHA
    assert stream.closed and stream.consumed == 2


@pytest.mark.parametrize("failure", ["timeout", "invalid", "overbound", 503])
def test_uncertain_post_is_one_attempt_for_every_transport_failure(failure):
    calls = []

    def wire(req):
        calls.append(req)
        if failure == "timeout":
            raise httpx.ReadTimeout("lost receipt", request=req)
        if failure == "invalid":
            return httpx.Response(201, content=b"not-json")
        if failure == "overbound":
            return httpx.Response(201, stream=Stream([b"x" * 16384] * 1000))
        return httpx.Response(failure)

    with pytest.raises(PublicationEffectUnknown):
        adapter(wire).submit_review(repository=REPO, pull_number=42,
                                   commit_id=SHA, event="COMMENT", body="Review")
    assert len(calls) == 1


def test_credential_source_exception_is_opaque_and_never_retried():
    class Unavailable:
        calls = 0
        def token_for_installation(self, **kwargs):
            self.calls += 1
            raise RuntimeError("SENSITIVE_TOKEN_DETAIL")

    token = Unavailable()
    with pytest.raises(GitHubReviewAPIUnavailable) as error:
        read(adapter(lambda _: pytest.fail("network must be inert"), tokens=token))
    assert str(error.value) == "REVIEW_SOURCE_AUTH_UNAVAILABLE"
    assert token.calls == 1


def test_concurrent_rate_limit_during_backoff_suppresses_second_get():
    calls, clock = [], Clock()

    def wire(req):
        calls.append(req)
        return httpx.Response(503)

    api = adapter(wire, clock=clock)

    def other_call_observes_limit(delay):
        clock.sleep(delay)
        try:
            api._defer(httpx.Response(429, headers={"retry-after": "30"}), limited=True)
        except GitHubReviewReadDeferred:
            pass

    api._sleep = other_call_observes_limit
    with pytest.raises(GitHubReviewReadDeferred, match="RATE_LIMITED"):
        read(api)
    assert len(calls) == 1

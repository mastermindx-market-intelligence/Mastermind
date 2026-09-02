"""Pinned HTTP/JSON boundary tests for the host-injected local Zoekt client."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from experiments.code_discovery.processes import LoopbackEndpoint
from experiments.code_discovery.zoekt_client import (
    ZoektClient,
    ZoektClientError,
    ZoektResponseTooLarge,
    ZoektResponseTimeout,
    ZoektResponseValidationError,
)


@contextmanager
def _server(
    payload: bytes, *, status: int = 200, delay_seconds: float = 0.0, location: str = ""
):
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen.append(self.path)
            if delay_seconds:
                time.sleep(delay_seconds)
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield LoopbackEndpoint("127.0.0.1", httpd.server_port), seen
    finally:
        httpd.shutdown()
        worker.join(timeout=1)
        httpd.server_close()


def _fixture_payload() -> bytes:
    fixture = (
        Path(__file__).parent.parent
        / "fixtures"
        / "code_discovery"
        / "zoekt-search-response.json"
    )
    return fixture.read_bytes()


def test_pinned_search_json_is_requested_once_and_normalized() -> None:
    """The internal client uses the exact local search route and fixed bounds."""

    with _server(_fixture_payload()) as (endpoint, seen):
        result = ZoektClient(endpoint, timeout_seconds=1).search(
            "SENTINEL", limit=3, context_lines=1, case_sensitive=False, regex=False
        )

    assert len(seen) == 1
    parsed = urlsplit(seen[0])
    assert parsed.path == "/search"
    assert parse_qs(parsed.query) == {
        "format": ["json"],
        "q": ['case:no content:"SENTINEL"'],
        "num": ["3"],
        "ctx": ["1"],
    }
    assert result.query_completed is True
    assert result.truncated is False
    assert result.total_match_count == 1
    assert result.matches[0].repository_name == "mastermindx-market-intelligence/Mastermind"
    assert result.matches[0].path == "engine/core.py"
    assert result.matches[0].line_start == 3
    assert result.matches[0].preview == "VALUE = 'SENTINEL'"


@pytest.mark.parametrize(
    "payload",
    [
        b"{not json}",
        b'{"result":{"unexpected":true}}',
        b'{"result":{"Last":{},"QueryStr":"","Query":"","Stats":{},"Duration":0,"FileMatches":[{"FileName":"x","Repo":"repo/name","ResultID":"","Language":"","DuplicateID":"","Branches":[],"Matches":[],"URL":"","IndexedSha":"bad"}]}}',
    ],
)
def test_malformed_or_semantically_drifting_response_fails_closed(payload: bytes) -> None:
    """Unknown shape is not silently coerced into an apparently valid empty search."""

    with _server(payload) as (endpoint, _):
        with pytest.raises(ZoektResponseValidationError):
            ZoektClient(endpoint, timeout_seconds=1).search(
                "SENTINEL", limit=3, context_lines=1, case_sensitive=False, regex=False
            )


def test_non_200_redirect_oversized_and_timeout_responses_are_not_retried() -> None:
    """One local request either yields the frozen shape or a typed failure."""

    with _server(b"failure", status=500) as (endpoint, seen):
        with pytest.raises(ZoektClientError, match="status 500"):
            ZoektClient(endpoint, timeout_seconds=1).search(
                "SENTINEL", limit=3, context_lines=1, case_sensitive=False, regex=False
            )
        assert len(seen) == 1

    with _server(b"", status=302, location="http://example.invalid") as (endpoint, _):
        with pytest.raises(ZoektClientError, match="redirect"):
            ZoektClient(endpoint, timeout_seconds=1).search(
                "SENTINEL", limit=3, context_lines=1, case_sensitive=False, regex=False
            )

    with _server(b"x" * (8 * 1024 * 1024 + 1)) as (endpoint, _):
        with pytest.raises(ZoektResponseTooLarge):
            ZoektClient(endpoint, timeout_seconds=1).search(
                "SENTINEL", limit=3, context_lines=1, case_sensitive=False, regex=False
            )

    with _server(_fixture_payload(), delay_seconds=0.2) as (endpoint, _):
        with pytest.raises(ZoektResponseTimeout):
            ZoektClient(endpoint, timeout_seconds=0.02).search(
                "SENTINEL", limit=3, context_lines=1, case_sensitive=False, regex=False
            )


def test_engine_match_count_beyond_the_caller_bound_is_explicitly_truncated() -> None:
    """A broad query cannot look complete merely because one page parsed cleanly."""

    payload = json.loads(_fixture_payload())
    payload["result"]["Stats"]["MatchCount"] = 101
    with _server(json.dumps(payload).encode("utf-8")) as (endpoint, _):
        result = ZoektClient(endpoint, timeout_seconds=1).search(
            "SENTINEL", limit=100, context_lines=0, case_sensitive=False, regex=False
        )

    assert result.total_match_count == 101
    assert result.truncated is True

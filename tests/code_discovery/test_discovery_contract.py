"""Behavioral contract for the production-inert CodeIntel Z0 facade.

Each test names a surface that would become unsafe if a future change widened
model-authored authority or made request validation ambiguous.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from experiments.code_discovery.discovery_contract import (
    DISCOVERY_TOOL_SCHEMAS,
    DiscoveryRequestError,
    discovery_tool_schema_digest,
    validate_discovery_request,
)


def _search_arguments(**overrides: object) -> dict[str, object]:
    """Return a complete, hand-authored valid search request."""

    arguments: dict[str, object] = {
        "query": "workspace_status",
        "repositories": ["mastermind"],
        "path_prefixes": ["control_plane"],
        "languages": ["python"],
        "refs": ["master"],
        "case_sensitive": False,
        "regex": False,
        "limit": 25,
        "context_lines": 2,
    }
    arguments.update(overrides)
    return arguments


def test_closed_tool_census_has_no_model_facing_administration_surface() -> None:
    """Adding a reindex/admin tool or model-authored host field must fail."""

    assert tuple(schema["name"] for schema in DISCOVERY_TOOL_SCHEMAS) == (
        "search_code",
        "list_repositories",
        "index_status",
    )

    serialized = json.dumps(DISCOVERY_TOOL_SCHEMAS, sort_keys=True).lower()
    for forbidden in (
        "admin",
        "reindex",
        "index_path",
        "repository_url",
        "credential",
        "executable",
        "command",
        "host",
        "port",
    ):
        assert forbidden not in serialized


def test_schema_digest_is_the_hand_checked_canonical_json_sha256() -> None:
    """Changing serialization or leaving NaN handling ambiguous must fail."""

    expected = hashlib.sha256(
        json.dumps(
            DISCOVERY_TOOL_SCHEMAS,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()

    assert discovery_tool_schema_digest() == expected


def test_search_request_preserves_only_the_closed_safe_contract() -> None:
    """A valid bounded query must remain immutable after validation."""

    request = validate_discovery_request("search_code", _search_arguments())

    assert request.tool == "search_code"
    assert dict(request.arguments) == {
        **_search_arguments(),
        "repositories": ("mastermind",),
        "path_prefixes": ("control_plane",),
        "languages": ("python",),
        "refs": ("master",),
    }
    with pytest.raises(TypeError):
        request.arguments["limit"] = 100  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("index_path", "/tmp/shards"),
        ("repository_url", "https://example.invalid/repository.git"),
        ("credential", "secret"),
        ("executable", "/usr/local/bin/zoekt-webserver"),
        ("command", "zoekt-git-index"),
        ("host", "127.0.0.1"),
        ("port", 6070),
    ],
)
def test_search_rejects_every_model_authored_administration_escape(
    field: str, value: object
) -> None:
    """Adding an authority-bearing request field must fail closed."""

    with pytest.raises(DiscoveryRequestError, match="unknown"):
        validate_discovery_request("search_code", _search_arguments(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("query", "", "empty query"),
        ("query", "x" * 513, "oversized query"),
        ("query", "safe\x00unsafe", "NUL query"),
        ("repositories", ["mastermind"] * 13, "too many repositories"),
        ("path_prefixes", ["../outside"], "traversal prefix"),
        ("path_prefixes", ["/absolute"], "absolute prefix"),
        ("languages", ["python"] * 13, "too many languages"),
        ("refs", ["master"] * 13, "too many refs"),
        ("limit", 101, "oversized result limit"),
        ("limit", 0, "zero result limit"),
        ("context_lines", 9, "oversized context"),
        ("context_lines", -1, "negative context"),
        ("case_sensitive", "yes", "nonboolean case flag"),
        ("regex", "false", "nonboolean regex flag"),
    ],
)
def test_search_rejects_every_unsafe_or_unbounded_value(
    field: str, value: object, reason: str
) -> None:
    """Dropping a concrete query boundary must fail this test."""

    assert reason
    with pytest.raises(DiscoveryRequestError):
        validate_discovery_request("search_code", _search_arguments(**{field: value}))


@pytest.mark.parametrize(
    "query",
    [
        "x" * 257,
        "(?<=secret)token",
        "(?P<name>token)",
    ],
)
def test_regex_mode_rejects_expensive_or_policy_forbidden_forms(query: str) -> None:
    """Relaxing regex safety must not turn a bounded request into a DoS path."""

    with pytest.raises(DiscoveryRequestError):
        validate_discovery_request(
            "search_code", _search_arguments(query=query, regex=True)
        )


def test_non_search_tools_are_closed_and_unknown_tools_fail() -> None:
    """Tool drift must not create a hidden generic request channel."""

    assert validate_discovery_request("list_repositories", {}).tool == "list_repositories"
    assert validate_discovery_request("index_status", {}).tool == "index_status"
    with pytest.raises(DiscoveryRequestError):
        validate_discovery_request("raw_zoekt_admin", {})
    with pytest.raises(DiscoveryRequestError, match="unknown"):
        validate_discovery_request("index_status", {"repository_url": "https://bad"})

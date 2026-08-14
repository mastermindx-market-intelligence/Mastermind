"""Externally-produced error text must be redacted before it reaches a client or a log.

Three live paths forward text this process did not produce:

* ``app.account._sb_err``      — Supabase's own error body -> HTTP response body
* ``brain.cli_bridge._reason`` — the Agent SDK's exception repr -> response + run log
* ``data_layer.polygon``       — ``requests`` exceptions carrying the key-bearing URL
                                 (latent: nothing logs them today, pinned so a future
                                 logger has a proven sanitizer to reach for)

The gate these tests exist for is ORDER: redaction must complete before the
length bound.  Truncating first can cut a secret-shaped run below the
32-character match threshold, leaving its prefix to print verbatim.
"""
from __future__ import annotations

import asyncio

import pytest

from common.redaction import (
    DEFAULT_LIMIT,
    REDACTION,
    TRUNCATION_MARKER,
    environment_secrets,
    sanitize_external_text,
)

# A real-shaped Supabase service-role JWT (header.payload.signature, base64url).
FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJzZXJ2aWNlX3JvbGUiLCJleHAiOjE5ODM4MTI5OTZ9"
    ".7Hn4KpQmVxLbTdRfWzYcJaEuNgSoIvBkMlPrXyZtDqA"
)
FAKE_SB_SECRET = "sb_secret_9RtKmZq4WvXpLbNcHdEgAy7Uj2Fs6TiO"
FAKE_HEX_KEY = "a3f19c8e5d7b402168fa9c3e5d7b8021a3f19c8e5d7b402168fa9c3e5d7b8021"
FAKE_POLYGON_KEY = "pQ7vNz2XmKdR8sLbWjY4tHcAeGf6UiOp"


def _filler(n: int) -> str:
    """``n`` characters of harmless prose.

    Deliberately NOT ``"x" * n``: a long single-character run is itself
    secret-shaped, so padding with one would be redacted and every length
    assertion below would pass for the wrong reason.
    """
    return ("abcd " * (n // 5 + 1))[:n]


def test_filler_is_not_itself_secret_shaped():
    """Guards the guard — if this drifts, the length tests stop meaning anything."""
    assert sanitize_external_text(_filler(120), include_environment=False) == _filler(120).strip()


# --------------------------------------------------------------- order gate ----

def test_redaction_completes_before_truncation():
    """THE load-bearing invariant, and the one a refactor is most likely to break.

    The secret is positioned so that truncating FIRST would leave only a
    20-character residue -- below the 32-character shape threshold -- which would
    then survive redaction and print verbatim.  Correct order redacts the whole
    run before the bound is ever applied.
    """
    filler = _filler(280)
    text = filler + FAKE_HEX_KEY
    assert len(FAKE_HEX_KEY) == 64
    residue = FAKE_HEX_KEY[: DEFAULT_LIMIT - len(filler)]
    assert len(residue) == 20, "test fixture drifted: residue must be under 32 chars"

    out = sanitize_external_text(text, include_environment=False)

    assert residue not in out
    assert FAKE_HEX_KEY not in out
    assert out.endswith(REDACTION)
    assert TRUNCATION_MARKER not in out


def test_truncation_still_applies_after_redaction():
    out = sanitize_external_text(_filler(500), include_environment=False)
    assert out.endswith(TRUNCATION_MARKER)
    assert len(out) == DEFAULT_LIMIT + len(TRUNCATION_MARKER)


def test_exact_secret_beats_the_shape_threshold():
    """An exact secret is redacted even when it is far too short to be shape-matched."""
    short_secret = "hunter2xy"  # 9 chars — no shape rule can see this
    text = f"upstream said: {short_secret} rejected"
    assert sanitize_external_text(text, include_environment=False) == text
    out = sanitize_external_text(
        text, extra_secrets=[short_secret], include_environment=False
    )
    assert short_secret not in out
    assert REDACTION in out


def test_longest_secret_redacted_first():
    """A short secret that prefixes a longer one must not leave the longer one's tail."""
    short = "abcdefgh"
    long = "abcdefghIJKLMNOP"
    out = sanitize_external_text(
        f"key={long}", extra_secrets=[short, long], include_environment=False
    )
    assert "IJKLMNOP" not in out
    assert out == f"key={REDACTION}"


# ------------------------------------------------------------- secret shapes ----

def test_jwt_collapses_to_a_single_marker():
    out = sanitize_external_text(
        f"Invalid API key: {FAKE_JWT}", include_environment=False
    )
    assert FAKE_JWT not in out
    for segment in FAKE_JWT.split("."):
        assert segment not in out
    assert out == f"Invalid API key: {REDACTION}"


def test_prefixed_secret_below_the_shape_threshold_is_redacted():
    """``sb_secret_`` + a 12-char tail is 22 chars — under the 32-char shape rule."""
    short_key = "sb_secret_ZmQ4Yx2Kp1Rt"
    assert len(short_key) < 32
    out = sanitize_external_text(f"bad key {short_key}", include_environment=False)
    assert short_key not in out
    assert out == f"bad key {REDACTION}"


@pytest.mark.parametrize(
    "prefixed",
    ["sk-abcdefghij", "sb_secret_ZmQ4Yx2Kp1Rt", "ghp_AbCdEfGhIjKl"],
)
@pytest.mark.parametrize("lead", ["apiKey=", "token=", "?key=", '"', "Bearer "])
def test_short_prefixed_secret_is_redacted_after_a_delimiter(lead, prefixed):
    """A credential's commonest position in error text is straight after ``=``.

    These are all under the 32-character shape threshold, so if the prefix rule
    declined to fire here nothing else would catch them: the surrounding run
    (``apiKey=sk-abcdefghij`` is 20 chars) is itself too short to shape-match.
    """
    assert len(f"{lead}{prefixed}") < 32
    out = sanitize_external_text(f"upstream said {lead}{prefixed} rejected",
                                 include_environment=False)
    assert prefixed not in out
    assert REDACTION in out


def test_jwt_is_redacted_after_a_delimiter():
    out = sanitize_external_text(f"apikey={FAKE_JWT} rejected", include_environment=False)
    assert FAKE_JWT not in out
    for segment in FAKE_JWT.split("."):
        assert segment not in out
    assert out == f"apikey={REDACTION} rejected"


@pytest.mark.parametrize(
    "secret",
    [FAKE_SB_SECRET, FAKE_HEX_KEY, FAKE_POLYGON_KEY, "sk-ant-oat01-QmZx4TvNpLbRdKcWjYs2Ae"],
)
def test_secret_shaped_runs_are_redacted(secret):
    out = sanitize_external_text(f"upstream rejected {secret} here", include_environment=False)
    assert secret not in out
    assert REDACTION in out


def test_git_object_id_is_redacted_here():
    """Deliberate divergence from the acceptance-path reference.

    ``ops/executive_os/acceptance.py`` exempts exactly-40 lowercase hex because
    its proof premise is an exact-SHA comparison.  No client-facing error needs
    to print a SHA, so exempting that shape here would only be a hole.
    """
    sha = "a" * 40
    out = sanitize_external_text(f"at commit {sha}", include_environment=False)
    assert sha not in out
    assert out == f"at commit {REDACTION}"


def test_control_characters_and_newlines_collapse_to_one_line():
    out = sanitize_external_text(
        "line one\nline\ttwo\x00\x1b[31m  three", include_environment=False
    )
    assert out == "line one line two [31m three"
    assert "\n" not in out and "\x00" not in out


def test_ordinary_upstream_message_survives_intact():
    """Over-redaction has a real cost: the message is what makes the error useful."""
    message = "New password should be different from the old password."
    assert sanitize_external_text(message, include_environment=False) == message


@pytest.mark.parametrize(
    "value,expected",
    [(None, ""), (123, "123"), ({"a": 1}, "{'a': 1}"), ("", "")],
)
def test_non_string_inputs_are_coerced(value, expected):
    assert sanitize_external_text(value, include_environment=False) == expected


# ------------------------------------------------------- environment secrets ----

def test_environment_secrets_collected_by_name_marker(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", FAKE_JWT)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", FAKE_SB_SECRET)
    monkeypatch.setenv("POLYGON_API_KEY", FAKE_POLYGON_KEY)
    monkeypatch.setenv("MASTERMIND_PUBLIC_URL", "https://app.mastermind-x.com")

    collected = environment_secrets()

    assert FAKE_JWT in collected
    assert FAKE_SB_SECRET in collected
    assert FAKE_POLYGON_KEY in collected
    assert "https://app.mastermind-x.com" not in collected
    assert list(collected) == sorted(collected, key=len, reverse=True)


def test_environment_secrets_read_at_call_time_not_cached(monkeypatch):
    monkeypatch.setenv("ROTATION_TEST_KEY", "first-value-long-enough")
    assert "first-value-long-enough" in environment_secrets()
    monkeypatch.setenv("ROTATION_TEST_KEY", "second-value-long-enough")
    collected = environment_secrets()
    assert "second-value-long-enough" in collected
    assert "first-value-long-enough" not in collected


def test_environment_secret_redacted_by_identity(monkeypatch):
    """A credential is removed because it IS the key, not because it looks like one."""
    plain = "plainenglishvalue"  # no secret shape at all
    monkeypatch.setenv("SOME_SERVICE_TOKEN", plain)
    out = sanitize_external_text(f"upstream said {plain}")
    assert plain not in out
    assert REDACTION in out


# ----------------------------------------------- app/account.py: _sb_err path ----

class _FakeResponse:
    """Minimal stand-in for the httpx response ``_sb_err`` receives."""

    def __init__(self, payload, status_code=400):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_sb_err_redacts_the_service_role_key_from_an_upstream_body(monkeypatch):
    from app import account

    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", FAKE_JWT)
    body = {"msg": f"Invalid authentication credentials for key {FAKE_JWT}"}

    out = account._sb_err(_FakeResponse(body))

    assert FAKE_JWT not in out
    assert "eyJ" not in out
    assert REDACTION in out
    assert "Invalid authentication credentials" in out


@pytest.mark.parametrize("field", ["msg", "error_description", "message", "error"])
def test_sb_err_redacts_every_forwarded_field(field):
    from app import account

    out = account._sb_err(_FakeResponse({field: f"bad key {FAKE_SB_SECRET}"}))
    assert FAKE_SB_SECRET not in out
    assert REDACTION in out


def test_sb_err_falls_back_when_the_message_redacts_to_nothing():
    """A body that is ONLY a secret must not become an empty error string."""
    from app import account

    out = account._sb_err(_FakeResponse({"msg": FAKE_JWT}, status_code=401))
    assert out == "Request failed (401)."


@pytest.mark.parametrize(
    "payload",
    [ValueError("not json"), {}, {"msg": ""}, ["unexpected", "list"], "a bare string"],
)
def test_sb_err_falls_back_on_an_unusable_body(payload):
    from app import account

    assert account._sb_err(_FakeResponse(payload, status_code=500)) == "Request failed (500)."


def test_sb_err_preserves_an_ordinary_upstream_message():
    from app import account

    message = "New password should be different from the old password."
    assert account._sb_err(_FakeResponse({"msg": message})) == message


def test_sb_err_bounds_an_oversized_upstream_body():
    from app import account

    out = account._sb_err(_FakeResponse({"msg": _filler(5000)}))
    assert out.endswith(TRUNCATION_MARKER)
    assert len(out) == DEFAULT_LIMIT + len(TRUNCATION_MARKER)


# --------------------------------------------- brain/cli_bridge.py: sdk_error ----

def _arm_cli_bridge(monkeypatch):
    """Make ``_reason`` reach its SDK call without a real Claude Code install.

    ``_reason`` returns early when ``cli_path()`` is empty, which is the state on
    CI -- without this the SDK-failure branch is never entered and every
    assertion below would pass vacuously.
    """
    from brain import cli_bridge

    monkeypatch.setenv("BOT_LLM_BACKEND", "cli")
    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/local/bin/claude")
    return cli_bridge


def _run_reason_with_sdk_exception(monkeypatch, exc):
    """Drive the real ``_reason`` SDK-failure path with an empty rotation pool."""
    cli_bridge = _arm_cli_bridge(monkeypatch)

    async def _boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(cli_bridge, "_via_sdk", _boom)
    result = asyncio.run(
        cli_bridge._reason("hello", arm=True, log_run=False, _oauth_candidates=[])
    )
    assert "sdk_error" in result, "never reached the SDK-failure branch"
    return result


def test_cli_bridge_sdk_error_is_redacted(monkeypatch):
    exc = RuntimeError(f"claude auth failed: CLAUDE_CODE_OAUTH_TOKEN={FAKE_SB_SECRET}")

    result = _run_reason_with_sdk_exception(monkeypatch, exc)

    assert FAKE_SB_SECRET not in result["sdk_error"]
    assert FAKE_SB_SECRET not in (result.get("error") or "")
    assert REDACTION in result["sdk_error"]
    assert "claude auth failed" in result["sdk_error"]


def test_cli_bridge_redacts_a_token_sitting_past_the_200_char_bound(monkeypatch):
    """The call site's own instance of the order gate.

    ``sdk_error`` is bounded at 200 characters.  Bounding the repr BEFORE
    redacting -- the shape this code had -- would leave a sub-threshold prefix of
    the token to print verbatim.

    ``repr(RuntimeError(msg))`` prefixes 14 characters, so a 175-character
    message body puts the token at index 189: past enough of the 200-char bound
    that only an 11-character residue would have survived the old order.
    """
    exc = RuntimeError(_filler(175) + FAKE_HEX_KEY)
    residue = FAKE_HEX_KEY[: 200 - (len("RuntimeError('") + 175)]
    assert len(residue) == 11, "test fixture drifted: residue must be under 32 chars"

    result = _run_reason_with_sdk_exception(monkeypatch, exc)

    assert FAKE_HEX_KEY not in result["sdk_error"]
    assert residue not in result["sdk_error"]
    assert REDACTION in result["sdk_error"]


def test_cli_bridge_still_cools_a_key_on_a_long_classifiable_failure(monkeypatch):
    """Key rotation must keep seeing the 200-char slice, not the full repr.

    ``key_rotor.classify_failure`` returns None outright for text longer than 600
    characters ("long legitimate analysis -- don't cool on it").  Feeding it the
    whole repr instead of the established ``repr(e)[:200]`` slice would silently
    stop cooling keys on any verbose auth failure, so this pins the seam the
    redaction split runs alongside.
    """
    cli_bridge = _arm_cli_bridge(monkeypatch)
    from brain import key_rotor

    cooled: list[str] = []
    monkeypatch.setattr(key_rotor, "mark_cooling",
                        lambda key_id, cool_kind=None: cooled.append(f"{key_id}:{cool_kind}"))

    async def _boom(*args, **kwargs):
        raise RuntimeError("401 Unauthorized: invalid token. " + _filler(700))

    monkeypatch.setattr(cli_bridge, "_via_sdk", _boom)
    asyncio.run(
        cli_bridge._reason(
            "hello", arm=True, log_run=False,
            _oauth_candidates=[{"key_id": "k1", "env_name": "CLAUDE_CODE_OAUTH_TOKEN"}],
        )
    )

    assert cooled == ["k1:auth"], "SDK auth failure no longer cools the key"


# --------------------------------------------- data_layer/polygon.py (latent) ----

def test_requests_style_url_exception_is_redacted(monkeypatch):
    """Pinned by name from ``data_layer/polygon.py``'s secret-handling note.

    ``requests`` embeds the full request URL in its exception messages, and every
    Polygon call passes the key as an ``apiKey`` query parameter.  Nothing logs
    these today; this proves the sanitizer a future logger must use.
    """
    monkeypatch.setenv("POLYGON_API_KEY", FAKE_POLYGON_KEY)
    diagnosis = (
        "HTTPSConnectionPool(host='api.polygon.io', port=443): Max retries exceeded "
        "with url: /v2/aggs/ticker/AAPL/range/1/day/2026-01-01/2026-08-14"
        "?adjusted=true&sort=asc&limit=50000&apiKey="
    )

    out = sanitize_external_text(diagnosis + FAKE_POLYGON_KEY)

    assert FAKE_POLYGON_KEY not in out
    # Asserted by equality rather than by probing for a surviving substring: this
    # pins that the key is the ONLY thing removed, so an over-redacting rule change
    # that ate the host or the request path fails here too.  (A substring probe for
    # the hostname would also read to CodeQL as incomplete URL sanitization.)
    assert out == diagnosis + REDACTION


def test_massive_api_key_is_covered_too(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.setenv("MASSIVE_API_KEY", "shortkey1")  # under every shape threshold
    out = sanitize_external_text("failed with url: ...&apiKey=shortkey1")
    assert "shortkey1" not in out
    assert REDACTION in out

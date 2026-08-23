from __future__ import annotations

import io
import json
from dataclasses import dataclass

import pytest

from integrations.slack_agent_dialogue.metadata_verifier import (
    HttpResult,
    MAX_RESPONSE_BYTES,
    MAX_TOKEN_BYTES,
    MetadataExpectation,
    MetadataVerificationError,
    RECEIPT_SCHEMA,
    SLACK_AUTH_TEST_URL,
    assert_secret_surfaces_clean,
    read_token_from_stdin,
    run,
    verify_metadata,
)

TOKEN = "".join(("xo", "xb-", "123456789012-", "abcdefghijklmnopqrstuvwxyz"))
EXPECTATION = MetadataExpectation(
    team_id="T0BRD2AQXQV",
    bot_user_id="U0BST4WG996",
    bot_id="B0BST4WG996",
    scopes=("groups:history", "chat:write"),
)


@dataclass
class FakeTransport:
    result: HttpResult | None = None
    error: Exception | None = None
    seen_token: str | None = None

    def request(self, *, token: str) -> HttpResult:
        self.seen_token = token
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def result(
    *,
    body: object | bytes | None = None,
    scopes: str = "groups:history, chat:write",
    status_code: int = 200,
    final_url: str = SLACK_AUTH_TEST_URL,
) -> HttpResult:
    if body is None:
        body = {
            "ok": True,
            "team_id": EXPECTATION.team_id,
            "user_id": EXPECTATION.bot_user_id,
            "bot_id": EXPECTATION.bot_id,
            "team": "must not escape",
            "user": "must not escape",
            "url": "https://example.invalid/",
        }
    encoded = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    return HttpResult(
        status_code=status_code,
        final_url=final_url,
        headers={"X-OAuth-Scopes": scopes, "x-ignored-secret": TOKEN},
        body=encoded,
    )


def error_code(exc: pytest.ExceptionInfo[MetadataVerificationError]) -> str:
    return exc.value.code


def test_success_emits_only_allowlisted_non_secret_metadata() -> None:
    transport = FakeTransport(result=result())
    receipt = verify_metadata(token=TOKEN, expectation=EXPECTATION, transport=transport)
    assert transport.seen_token == TOKEN
    assert receipt == {
        "bot_id": EXPECTATION.bot_id,
        "bot_user_id": EXPECTATION.bot_user_id,
        "schema": RECEIPT_SCHEMA,
        "scopes": ["chat:write", "groups:history"],
        "status": "PASS",
        "team_id": EXPECTATION.team_id,
    }
    rendered = json.dumps(receipt, sort_keys=True)
    assert TOKEN not in rendered
    assert "must not escape" not in rendered
    assert "example.invalid" not in rendered
    assert "x-ignored-secret" not in rendered


def test_unknown_secret_shaped_response_field_is_never_emitted() -> None:
    payload = {
        "ok": True,
        "team_id": EXPECTATION.team_id,
        "user_id": EXPECTATION.bot_user_id,
        "bot_id": EXPECTATION.bot_id,
        "access_token": TOKEN,
    }
    receipt = verify_metadata(
        token=TOKEN,
        expectation=EXPECTATION,
        transport=FakeTransport(result=result(body=payload)),
    )
    assert TOKEN not in json.dumps(receipt)
    assert "access_token" not in receipt


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"team_id": "T0000000000"}, "METADATA_IDENTITY_MISMATCH"),
        ({"user_id": "U0000000000"}, "METADATA_IDENTITY_MISMATCH"),
        ({"bot_id": "B0000000000"}, "METADATA_IDENTITY_MISMATCH"),
        ({"ok": False, "error": TOKEN}, "SLACK_AUTH_REFUSED"),
    ],
)
def test_identity_and_auth_fail_closed_without_echo(
    mutation: dict[str, object], expected: str
) -> None:
    payload: dict[str, object] = {
        "ok": True,
        "team_id": EXPECTATION.team_id,
        "user_id": EXPECTATION.bot_user_id,
        "bot_id": EXPECTATION.bot_id,
    }
    payload.update(mutation)
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=EXPECTATION,
            transport=FakeTransport(result=result(body=payload)),
        )
    assert error_code(exc) == expected
    assert TOKEN not in str(exc.value)


@pytest.mark.parametrize(
    "scopes",
    [
        "groups:history",
        "groups:history, chat:write, users:read",
        "groups:history, groups:history, chat:write",
        "",
        "groups:history, INVALID SCOPE",
    ],
)
def test_scope_mismatch_or_malformed_header_refuses(scopes: str) -> None:
    expected = (
        "METADATA_RESPONSE_REFUSED"
        if scopes
        in {
            "groups:history, groups:history, chat:write",
            "",
            "groups:history, INVALID SCOPE",
        }
        else "METADATA_SCOPE_MISMATCH"
    )
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=EXPECTATION,
            transport=FakeTransport(result=result(scopes=scopes)),
        )
    assert error_code(exc) == expected


def test_missing_scope_header_refuses() -> None:
    base = result()
    no_header = HttpResult(
        status_code=base.status_code,
        final_url=base.final_url,
        headers={},
        body=base.body,
    )
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=EXPECTATION,
            transport=FakeTransport(result=no_header),
        )
    assert error_code(exc) == "METADATA_RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "bad_result",
    [
        result(status_code=500),
        result(final_url="https://evil.invalid/api/auth.test"),
        result(body=b"not-json"),
        result(body=[]),
        result(body={"ok": True}),
        HttpResult(
            status_code=200,
            final_url=SLACK_AUTH_TEST_URL,
            headers={"x-oauth-scopes": "groups:history, chat:write"},
            body=b"x" * (MAX_RESPONSE_BYTES + 1),
        ),
    ],
)
def test_response_shape_and_transport_refuse(bad_result: HttpResult) -> None:
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=EXPECTATION,
            transport=FakeTransport(result=bad_result),
        )
    assert error_code(exc) == "METADATA_RESPONSE_REFUSED"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not-a-token\n",
        b"xox" + b"p-123456789012-abcdefghijklmnopqrstuvwxyz\n",
        TOKEN.encode() + b"\nsecond-line\n",
        TOKEN.encode() + b" ",
        b"x" * (MAX_TOKEN_BYTES + 1),
        ("xox" + "b-123456789012-\N{SNOWMAN}").encode("utf-8"),
    ],
)
def test_stdin_token_input_is_single_line_bounded_bot_token(raw: bytes) -> None:
    with pytest.raises(MetadataVerificationError) as exc:
        read_token_from_stdin(io.BytesIO(raw))
    assert error_code(exc) == "METADATA_INPUT_REFUSED"


def test_stdin_allows_one_terminal_newline() -> None:
    assert read_token_from_stdin(io.BytesIO((TOKEN + "\n").encode())) == TOKEN
    assert read_token_from_stdin(io.BytesIO((TOKEN + "\r\n").encode())) == TOKEN


@pytest.mark.parametrize(
    ("argv", "environ"),
    [
        (["--token", TOKEN], {}),
        ([], {"SLACK_TOKEN": TOKEN}),
        ([f"prefix={TOKEN}"], {}),
    ],
)
def test_token_shaped_argv_or_environment_refuses(
    argv: list[str], environ: dict[str, str]
) -> None:
    with pytest.raises(MetadataVerificationError) as exc:
        assert_secret_surfaces_clean(argv=argv, environ=environ)
    assert error_code(exc) == "SECRET_SURFACE_REFUSED"
    assert TOKEN not in str(exc.value)


def test_cli_success_is_canonical_and_secret_free() -> None:
    stdout = io.StringIO()
    transport = FakeTransport(result=result())
    code = run(
        [
            "--expected-team-id",
            EXPECTATION.team_id,
            "--expected-bot-user-id",
            EXPECTATION.bot_user_id,
            "--expected-bot-id",
            EXPECTATION.bot_id,
            "--expected-scope",
            "groups:history",
            "--expected-scope",
            "chat:write",
        ],
        stdin=io.BytesIO((TOKEN + "\n").encode()),
        stdout=stdout,
        environ={},
        transport=transport,
    )
    assert code == 0
    output = stdout.getvalue()
    assert output.endswith("\n")
    assert TOKEN not in output
    document = json.loads(output)
    assert document["status"] == "PASS"
    assert document["scopes"] == ["chat:write", "groups:history"]


def test_cli_failure_forwards_only_fixed_error_code() -> None:
    stdout = io.StringIO()
    transport = FakeTransport(error=RuntimeError(f"network leaked {TOKEN}"))
    code = run(
        [
            "--expected-team-id",
            EXPECTATION.team_id,
            "--expected-bot-user-id",
            EXPECTATION.bot_user_id,
            "--expected-bot-id",
            EXPECTATION.bot_id,
            "--expected-scope",
            "groups:history",
            "--expected-scope",
            "chat:write",
        ],
        stdin=io.BytesIO((TOKEN + "\n").encode()),
        stdout=stdout,
        environ={},
        transport=transport,
    )
    assert code == 2
    assert TOKEN not in stdout.getvalue()
    assert json.loads(stdout.getvalue()) == {
        "error": "METADATA_RESPONSE_REFUSED",
        "schema": RECEIPT_SCHEMA,
        "status": "ERROR",
    }


def test_cli_rejects_token_in_unknown_argument_without_argparse_echo() -> None:
    stdout = io.StringIO()
    code = run(
        ["--accidental-secret", TOKEN],
        stdin=io.BytesIO(b""),
        stdout=stdout,
        environ={},
        transport=FakeTransport(result=result()),
    )
    assert code == 2
    assert TOKEN not in stdout.getvalue()
    assert json.loads(stdout.getvalue())["error"] == "SECRET_SURFACE_REFUSED"


def test_expectation_is_closed_and_exact() -> None:
    malformed = MetadataExpectation(
        team_id="not-team",
        bot_user_id=EXPECTATION.bot_user_id,
        bot_id=EXPECTATION.bot_id,
        scopes=EXPECTATION.scopes,
    )
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=malformed,
            transport=FakeTransport(result=result()),
        )
    assert error_code(exc) == "METADATA_EXPECTATION_REFUSED"


def test_duplicate_expected_scope_refuses() -> None:
    duplicate = MetadataExpectation(
        team_id=EXPECTATION.team_id,
        bot_user_id=EXPECTATION.bot_user_id,
        bot_id=EXPECTATION.bot_id,
        scopes=("chat:write", "chat:write"),
    )
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=duplicate,
            transport=FakeTransport(result=result()),
        )
    assert error_code(exc) == "METADATA_EXPECTATION_REFUSED"

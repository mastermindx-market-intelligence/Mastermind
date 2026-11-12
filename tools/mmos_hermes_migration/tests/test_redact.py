"""Tests for redact.py — synthetic strings only, no real credentials."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from redact import redact  # noqa: E402

SECRETS = {
    "sk_key": "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF000011112222",
    "sk_short_prefix": "sk-proj-AAAABBBBCCCCDDDDEEEEFFFF000011112222",
    "sk_plain": "sk-AAAABBBBCCCCDDDDEEEEFFFF000011112222",
    "github": "ghp_" + "A1b2C3d4E5f6G7h8I9j0" * 2,
    "github_pat": "github_pat_" + "A1b2C3d4E5f6G7h8I9j0" * 2,
    "github_gho": "gho_" + "A1b2C3d4E5f6G7h8I9j0" * 2,
    "slack": "xoxb-123456789012-1234567890123-AbCdEfGhIjKl",
    "slack_app": "xapp-1-A0123456789-1234567890123-abcdefabcdef",
    "aws": "AKIAIOSFODNN7EXAMPLE",
    "aws_asia": "ASIAIOSFODNN7EXAMPLE",
    "google": "AIza" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "bearer": "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
    "url_password": "https://user:SuperSecretPass99@host.example/path",
    "kv_password": "password=Sup3rSecretValue!",
    "kv_colon": "api_key: abcdef1234567890abcdef",
    "kv_secret": "secret='QuotedSecretValue123'",
    "kv_token": "token = 0123456789abcdef0123456789abcdef01234567",
    "kv_auth": "auth: longauthvalue123456",
    "kv_long_hex": "api_key=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "kv_long_b64": "secret=QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU2Nzg5",
}
PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEA7sFakeKeyBytesHereForTestingOnly1234567890\n"
    "-----END RSA PRIVATE KEY-----"
)
SAFE_TEXTS = [
    "The quick brown fox jumps over the lazy dog.",
    "Commit 0123456789abcdef0123456789abcdef01234567 fixed the bug.",
    "git checkout a94a8fe5ccb19ba61c4c0873d391e987982fbbd3 done",
    "Session 123e4567-e89b-12d3-a456-426614174000 started.",
    "UUID f47ac10b-58cc-4372-a567-0e02b2c3d479 is fine.",
    "A 40-hex sha 0123456789abcdef0123456789abcdef01234567 on its own.",
    "The author: Jane wrote the token bucket algorithm.",
    "passwords are hashed; the secret sauce is patience.",
    "short=abc123",  # value < 8 chars: untouched
]


def test_every_kind_redacted_and_counted():
    text = " ".join(SECRETS.values()) + "\n" + PEM
    out, counts = redact(text)
    for kind, secret in SECRETS.items():
        if kind == "url_password":
            assert "SuperSecretPass99" not in out
            assert "https://user:" in out and "@host.example" in out
        elif kind == "bearer":
            assert "abcdefghijklmnopqrstuvwxyz0123456789" not in out
        elif kind.startswith("kv_"):
            value = secret.split("=", 1)[-1].split(":", 1)[-1].strip().strip("'\"")
            assert value not in out, kind
        else:
            assert secret not in out, kind
    assert PEM not in out
    assert "BEGIN RSA PRIVATE KEY" not in out
    assert sum(counts.values()) >= len(SECRETS) + 1
    assert counts, "Counter must not be empty"


def test_marker_format():
    out, counts = redact("key sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF000011112222")
    import re
    assert re.search(r"\[REDACTED:[a-z_]+:[0-9a-f]{8}\]", out)
    assert sum(counts.values()) == 1


def test_idempotent():
    text = " ".join(SECRETS.values()) + "\n" + PEM + "\npassword=AnotherSecret123"
    once, counts1 = redact(text)
    twice, counts2 = redact(once)
    assert once == twice
    assert sum(counts2.values()) == 0  # nothing new on second pass


def test_safe_texts_untouched():
    for text in SAFE_TEXTS:
        out, counts = redact(text)
        assert out == text, text
        assert sum(counts.values()) == 0, text


def test_none_and_empty():
    assert redact("") == ("", {})
    out, counts = redact(None)
    assert out is None and sum(counts.values()) == 0


def test_hash_is_sha256_prefix():
    import hashlib
    secret = SECRETS["sk_plain"]
    out, _ = redact(secret)
    expect = hashlib.sha256(secret.encode()).hexdigest()[:8]
    assert expect in out


def test_kv_redacts_value_only():
    out, _ = redact("password=Sup3rSecretValue!")
    assert out.startswith("password=")
    assert "Sup3rSecretValue!" not in out


def test_git_sha_after_keyword_is_redacted():
    sha = "0123456789abcdef0123456789abcdef01234567"
    out, counts = redact(f"token={sha}")
    assert sha not in out
    assert sum(counts.values()) == 1


def test_mixed_prose_with_secrets():
    text = (
        "Please run git show a94a8fe5ccb19ba61c4c0873d391e987982fbbd3 "
        "then set api_key: abcdef1234567890abcdef and report back."
    )
    out, counts = redact(text)
    assert "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3" in out
    assert "abcdef1234567890abcdef" not in out
    assert sum(counts.values()) == 1


def test_unterminated_pem_header_with_partial_body_is_redacted():
    # A debug print of a truncated key: header plus some body, no END line.
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"
    text = f"KEY len=119 val_prefix='-----BEGIN PRIVATE KEY-----\\n{body}'"
    out, counts = redact(text)
    assert body not in out
    assert counts["pem"] == 1
    assert "len=119" in out


def test_bare_pem_header_mention_without_body_is_kept_safe():
    out, counts = redact("look for a -----BEGIN PRIVATE KEY----- line")
    assert "MII" not in out
    assert counts["pem"] in (0, 1)

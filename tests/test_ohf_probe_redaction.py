from __future__ import annotations

import json

from scripts.ohf.redaction import (
    REDACTED,
    evidence_contains_secret,
    redact_evidence,
    redact_untrusted,
    redact_value,
)

STDERR_SECRET = "sk-ohf-probe-fixture-" + ("A" * 24)
HARNESS_ERROR = "ghp_" + ("b" * 36)
MCP_ERROR = "github_pat_" + ("c" * 40)
ENV_VALUE = "sk-proj-OHFPROBEFIXTURESECRETVALUE123456"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvaGYifQ.signaturepaddingxx"


def test_redacts_injected_secret_fixtures():
    payload = {
        "stderr": f"codex failed {STDERR_SECRET}",
        "harness_error": f"initialize failed {HARNESS_ERROR}",
        "mcp_error": f"ohf_probe_echo crashed {MCP_ERROR}",
        "environment": {
            "MASTERMIND_AUTH_TOKEN": ENV_VALUE,
            "OPENAI_API_KEY": ENV_VALUE,
            "authorization": f"Bearer {JWT}",
        },
    }
    redacted = redact_value(payload)
    blob = json.dumps(redacted)
    for secret in (STDERR_SECRET, HARNESS_ERROR, MCP_ERROR, ENV_VALUE, JWT):
        assert secret not in blob
    assert REDACTED in blob
    assert not evidence_contains_secret(redact_evidence(redacted))


def test_untrusted_stream_uses_house_token_sanitizer():
    token = "A" * 40
    assert token not in redact_untrusted(f"leaked {token} from stderr")


def test_evidence_redaction_preserves_sha256_digests():
    digest = "a" * 64
    probe = {
        "harness": {"binary_digest": digest, "effective_config_digest": digest},
        "notes": [f"stderr leaked {STDERR_SECRET}"],
    }
    redacted = redact_evidence(probe)
    assert redacted["harness"]["binary_digest"] == digest
    assert STDERR_SECRET not in json.dumps(redacted)

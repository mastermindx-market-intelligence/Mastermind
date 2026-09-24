from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "integrations" / "claude_executive_mcp" / "adapter.mjs"
RUNBOOK = ROOT / "docs" / "runbooks" / "claude-executive-mcp-client.md"


def test_adapter_is_loopback_only_and_reuses_production_executive():
    text = ADAPTER.read_text()
    assert 'const LISTEN_HOST = "127.0.0.1"' in text
    assert "const LISTEN_PORT = 8444" in text
    assert 'const UPSTREAM_HOST = "127.0.0.1"' in text
    assert "const UPSTREAM_PORT = 8443" in text
    assert "/Library/Application Support/MastermindExecutive/config/executive-mcp.json" in text


def test_adapter_is_translation_only_not_a_credential_or_lifecycle_plane():
    text = ADAPTER.read_text().lower()
    for forbidden in (
        "writefilesync",
        "appendfilesync",
        "keychain",
        "sqlite",
        "jobregistry",
        "attemptregistry",
        "dispatch",
    ):
        assert forbidden not in text
    assert 'const allowed_proxy_paths = new set(["/mcp", metadata_path]);' in text
    assert 'settimeout' not in text
    assert 'client_id_metadata_document_supported = true' not in text


def test_claude_enrollment_is_public_pkce_and_separate_from_codex_effect_unknown():
    text = RUNBOOK.read_text()
    assert "http://localhost:8774/callback" in text
    assert "--client-id <PUBLIC_AUTH0_CLIENT_ID>" in text
    assert "--callback-port 8774" in text
    assert "PKCE S256" in text
    assert "PR #633" in text
    assert "EFFECT_UNKNOWN" in text
    assert "client secret" in text.lower()


def test_acceptance_keeps_admission_distinct_from_worker_start():
    text = RUNBOOK.read_text()
    assert "`QUEUED`, `dispatched=false`" in text
    assert "`QUEUED` is admission only" in text
    assert "Fable remains parent/coordinator" in text
    assert "Capacity/Model Router" in text

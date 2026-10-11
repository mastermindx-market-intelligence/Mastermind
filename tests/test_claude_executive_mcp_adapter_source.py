from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "integrations" / "claude_executive_mcp" / "adapter.mjs"
README = ROOT / "integrations" / "claude_executive_mcp" / "README.md"
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
    assert "settimeout" not in text
    assert "client_id_metadata_document_supported = true" not in text


def test_claude_transport_remains_public_pkce_and_separate_from_codex_effect_unknown():
    text = RUNBOOK.read_text()
    assert "http://localhost:8774/callback" in text
    assert "--client-id <PUBLIC_AUTH0_CLIENT_ID>" in text
    assert "--callback-port 8774" in text
    assert "PKCE S256" in text
    assert "PR #633" in text
    assert "EFFECT_UNKNOWN" in text
    assert "client secret" in text.lower()


def test_fable_enrollment_is_held_until_role_correct_coo_policy_exists():
    readme = README.read_text()
    runbook = RUNBOOK.read_text()
    combined = readme + "\n" + runbook

    assert "ENROLLMENT HELD" in combined
    assert "DO NOT enroll the production Claude/Fable client yet." in runbook
    assert "Do not enroll Fable with" in readme
    assert "mastermind.executive.intent.submit" in readme
    assert "mastermind.executive.coo.act" in combined
    assert "SPEC_ONLY" in combined
    assert "must not be provisioned" in combined
    assert "CEO-specific" in runbook
    assert "not a Fable enrollment permission" in runbook
    assert "submit_ceo_intent" not in combined


def test_acceptance_keeps_admission_distinct_from_worker_start():
    text = RUNBOOK.read_text()
    assert "QUEUED" in text and "dispatched=false" in text
    assert "admission only" in text
    assert "Fable-parent -> Executive child" in text
    assert "Capacity/Model Router" in text
    assert "No step may substitute a CEO intent for the COO request." in text


def test_current_transport_source_grants_no_current_coo_mutation():
    combined = README.read_text() + "\n" + RUNBOOK.read_text()
    assert "NO COO MUTATION AUTHORITY" in combined
    assert "COO mutation is unavailable" in combined
    assert "role-correct principal admission" in combined
    assert "alternate client" in combined
    assert "public Executive endpoint" in combined

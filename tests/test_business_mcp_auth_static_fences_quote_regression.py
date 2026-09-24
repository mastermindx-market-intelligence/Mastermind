from __future__ import annotations

from pathlib import Path


def test_jwt_verifier_keeps_signature_verification_enabled() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "integrations" / "business_mcp_auth" / "jwt_verifier.py"
    ).read_text(encoding="utf-8")
    assert '"verify_signature": True' in text
    assert 'algorithms=["RS256"]' in text
    assert 'algorithm="RS256"' in text

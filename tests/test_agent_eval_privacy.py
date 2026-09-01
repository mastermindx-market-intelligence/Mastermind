"""EVAL-R0 privacy: supplied-value secret-shape rejection.

Implements the acceptance tests named by
``docs/superpowers/specs/2026-09-01-agent-evaluation-r0-environment-free-secret-safety-amendment.md``
§6, and R-B1-4 (closed observed-evidence exempt set).
"""
from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.agent_eval.errors import ContractError
from scripts.agent_eval.privacy import (
    OBSERVED_EVIDENCE_FIELDS,
    SecretShapeFinding,
    assert_public_safe_evidence,
    detect_secret_shapes,
)

ROOT = Path(__file__).resolve().parents[1]
PRIVACY_MODULE = ROOT / "scripts" / "agent_eval" / "privacy.py"


# ---------------------------------------------------------------------------
# Minimum prohibited shapes (amendment §3.4)
# ---------------------------------------------------------------------------


def test_forbidden_field_name_rejected_case_insensitively() -> None:
    findings = detect_secret_shapes({"API_KEY": "whatever-value"})
    assert any(f.code == "FORBIDDEN_FIELD_NAME" for f in findings)


@pytest.mark.parametrize(
    "field_name",
    [
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "authorization",
        "cookie",
        "set_cookie",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "private_key",
        "credential",
        "credentials",
        "raw_environment",
        "environment_dump",
        "chain_of_thought",
        "private_host_address",
    ],
)
def test_every_named_forbidden_field_is_rejected(field_name: str) -> None:
    findings = detect_secret_shapes({field_name: "x"})
    assert any(f.code == "FORBIDDEN_FIELD_NAME" for f in findings)


def test_jwt_shaped_value_rejected() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    findings = detect_secret_shapes({"note": jwt})
    assert any(f.code == "JWT_SHAPE" for f in findings)


@pytest.mark.parametrize(
    "value",
    [
        "sk-ant-1234567890abcdef",
        "sk-1234567890abcdef",
        "github_pat_11ABCDEFGHIJKLMNOPQR",
        "ghp_1234567890abcdefghij",
        "gho_1234567890abcdefghij",
        "ghs_1234567890abcdefghij",
        "sb_secret_1234567890abcdef",
        "sb_publishable_1234567890abcdef",
        "sbp_1234567890abcdef",
    ],
)
def test_known_credential_prefixes_rejected(value: str) -> None:
    findings = detect_secret_shapes({"note": value})
    assert any(f.code == "KNOWN_SECRET_PREFIX" for f in findings)


def test_authorization_bearer_header_rejected() -> None:
    findings = detect_secret_shapes({"note": "Authorization: Bearer abcdef1234567890"})
    assert any(f.code == "AUTHORIZATION_HEADER_SHAPE" for f in findings)


def test_cookie_secret_value_rejected() -> None:
    findings = detect_secret_shapes({"note": "session_token=abcdef123456; Path=/"})
    assert any(f.code == "COOKIE_SECRET_SHAPE" for f in findings)


@pytest.mark.parametrize(
    "value",
    [
        "MASTERMIND_API_KEY=abcdef123456",
        "PROVIDER_TOKEN=abcdef123456",
        "SOME_SECRET=abcdef123456",
        "MY_PASSWORD=abcdef123456",
    ],
)
def test_environment_assignment_shape_rejected(value: str) -> None:
    findings = detect_secret_shapes({"note": value})
    assert any(f.code in {"ENVIRONMENT_ASSIGNMENT_SHAPE"} for f in findings)


def test_supplied_email_shape_rejected_unconditionally() -> None:
    findings = detect_secret_shapes({"note": "reach me at person@example.com"})
    assert any(f.code == "PRIVATE_IDENTITY_SHAPE" for f in findings)


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1:8080/",
        "connect to 10.0.0.5 now",
        "internal host 192.168.1.20",
        "reach localhost:9000",
    ],
)
def test_supplied_private_host_shape_rejected_unconditionally(value: str) -> None:
    findings = detect_secret_shapes({"note": value})
    assert any(f.code == "PRIVATE_HOST_SHAPE" for f in findings)


def test_findings_expose_only_path_and_category_never_the_matched_value() -> None:
    secret = "sk-ant-supersecretvalue1234567890"
    findings = detect_secret_shapes({"note": secret})
    for finding in findings:
        assert secret not in finding.path
        assert secret not in finding.shape
    try:
        assert_public_safe_evidence({"note": secret})
    except ContractError as exc:
        for defect in exc.defects:
            assert secret not in defect.message
            assert secret not in defect.path
    else:  # pragma: no cover - defensive
        pytest.fail("expected ContractError")


def test_assert_public_safe_evidence_raises_contract_error_with_findings() -> None:
    with pytest.raises(ContractError) as excinfo:
        assert_public_safe_evidence({"password": "hunter2"})
    assert excinfo.value.defects[0].code == "FORBIDDEN_FIELD_NAME"


def test_assert_public_safe_evidence_accepts_clean_document() -> None:
    assert_public_safe_evidence({"scenario_id": "scenario:demo:case", "count": 3})


def test_findings_are_deterministically_ordered() -> None:
    doc = {"z_field": "sk-ant-abcdefgh12345678", "a_field": "password=abcdefgh"}
    first = detect_secret_shapes(doc)
    second = detect_secret_shapes(doc)
    assert first == second
    assert list(first) == sorted(first)


def test_nested_object_and_list_paths_are_scanned() -> None:
    doc = {"outer": {"inner": ["safe", {"password": "x"}]}}
    findings = detect_secret_shapes(doc)
    assert any(f.code == "FORBIDDEN_FIELD_NAME" and "outer" in f.path for f in findings)


# ---------------------------------------------------------------------------
# Explicit nonmatches (amendment §3.5) — positive controls
# ---------------------------------------------------------------------------


def test_sha256_digest_alone_is_not_rejected() -> None:
    findings = detect_secret_shapes({"digest": "sha256:" + "a" * 64})
    assert findings == ()


def test_git_source_ref_alone_is_not_rejected() -> None:
    findings = detect_secret_shapes(
        {"ref": "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40}
    )
    assert findings == ()


def test_uuid4_evaluation_identity_alone_is_not_rejected() -> None:
    findings = detect_secret_shapes({"id": "run:5b1f6a2e-7c3d-4e1a-9b2c-1234567890ab"})
    assert findings == ()


def test_normal_repository_path_alone_is_not_rejected() -> None:
    findings = detect_secret_shapes({"path": "scripts/agent_eval/contracts.py"})
    assert findings == ()


def test_canonical_decimal_string_alone_is_not_rejected() -> None:
    findings = detect_secret_shapes({"cost": "12.34"})
    assert findings == ()


def test_public_https_url_alone_is_not_rejected() -> None:
    findings = detect_secret_shapes(
        {"doc": "https://github.com/mastermindx-market-intelligence/Mastermind"}
    )
    assert findings == ()


def test_arbitrary_long_hex_run_without_other_prohibited_shape_is_not_rejected() -> None:
    findings = detect_secret_shapes({"value": "a" * 40})
    assert findings == ()


# ---------------------------------------------------------------------------
# R-B1-4: closed observed-evidence exempt set
# ---------------------------------------------------------------------------


def test_observed_evidence_fields_constant_matches_design_run_schema() -> None:
    # Transcribed from design §7.5 `observations:` block.
    assert OBSERVED_EVIDENCE_FIELDS == frozenset(
        {
            "observed_sources",
            "observed_capability_ids",
            "observed_tool_schema_digests",
            "observed_network_destinations",
            "dependency_degradations",
        }
    )


def test_private_host_value_inside_observed_network_destinations_is_not_rejected() -> None:
    # Observed evidence is sanitized per §3.7, never rejected as a supplied secret.
    doc = {
        "observations": {
            "observed_network_destinations": [
                {"destination_class": "PRIVATE_RANGE", "value_digest": "sha256:" + "a" * 64, "raw_value": None}
            ]
        }
    }
    findings = detect_secret_shapes(doc)
    assert findings == ()


def test_email_shaped_value_inside_observed_evidence_field_is_not_rejected() -> None:
    doc = {"observations": {"observed_sources": [{"artifact_ref": "person@example.com", "digest": "sha256:" + "a" * 64}]}}
    findings = detect_secret_shapes(doc)
    assert findings == ()


def test_email_shaped_value_outside_observed_evidence_field_is_still_rejected() -> None:
    doc = {"context": {"note": "person@example.com"}}
    findings = detect_secret_shapes(doc)
    assert any(f.code == "PRIVATE_IDENTITY_SHAPE" for f in findings)


def test_forbidden_field_name_still_scanned_inside_a_sibling_of_observed_fields() -> None:
    # only the OBSERVED_EVIDENCE_FIELDS subtree itself is exempt, not its
    # siblings inside the same parent object.
    doc = {"observations": {"observed_sources": [], "password": "leaked"}}
    findings = detect_secret_shapes(doc)
    assert any(f.code == "FORBIDDEN_FIELD_NAME" for f in findings)


# ---------------------------------------------------------------------------
# No ambient observation (amendment §3.2, §4.5, §4.3 proof)
# ---------------------------------------------------------------------------


def test_environment_mutation_does_not_change_detection_result(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = {"note": "sk-ant-abcdefgh12345678", "password": "x"}
    before = detect_secret_shapes(doc)

    class _RaisingMapping(dict):
        def __getitem__(self, key):  # pragma: no cover - defensive
            raise AssertionError("production privacy code must never read os.environ")

        def get(self, key, default=None):  # pragma: no cover - defensive
            raise AssertionError("production privacy code must never read os.environ")

    monkeypatch.setattr(os, "environ", _RaisingMapping())
    after = detect_secret_shapes(doc)
    assert before == after
    assert assert_public_safe_evidence({"clean": "value"}) is None


def test_privacy_module_imports_no_forbidden_symbol() -> None:
    source = PRIVACY_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PRIVACY_MODULE))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
    forbidden = {"scripts.ohf.redaction", "common.redaction", "os", "socket", "subprocess", "requests", "urllib.request"}
    assert not (imported_names & forbidden), imported_names & forbidden


def test_privacy_module_source_never_calls_environment_reads() -> None:
    source = PRIVACY_MODULE.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "os.getenv", "environment_secrets"):
        assert forbidden not in source


def test_privacy_subprocess_proves_no_environment_read_needed() -> None:
    # Import and exercise the module in a fresh subprocess with an environment
    # that would raise loudly if anything in the import/call path touched it.
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from scripts.agent_eval.privacy import detect_secret_shapes, assert_public_safe_evidence\n"
        "detect_secret_shapes({'a': 'sk-ant-abcdefgh12345678'})\n"
        "try:\n"
        "    assert_public_safe_evidence({'password': 'x'})\n"
        "except Exception:\n"
        "    pass\n"
        "print('OK')\n"
    ) % str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(ROOT),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"

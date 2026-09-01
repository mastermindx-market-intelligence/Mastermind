"""EVAL-R0 supplied-value secret-shape rejection (reject-only, no ambient reads).

Implements the binding amendment
``docs/superpowers/specs/2026-09-01-agent-evaluation-r0-environment-free-secret-safety-amendment.md``
§3. This module is NOT a general redaction service, credential inventory,
DLP system, security-event sink, policy engine, or environment scanner, and
it is not a replacement for ``common.redaction`` / ``scripts.ohf.redaction``
(deliberately not imported here — see the amendment §2 defect and §3.2).

It has one job: refuse a proposed canonical evaluation document or run draft
when the supplied JSON value itself contains a prohibited field name or an
explicitly recognized credential/private-identity shape. It never rewrites,
redacts, truncates, normalizes, logs, persists, or transmits the supplied
value, and it never reads the process environment or any other ambient host
state — findings are a pure function of the caller-supplied ``value``
argument and this module's own closed pattern constants.

R-B1-4 (binding B1 opening ruling): the observed-evidence exemption below
applies to EXACTLY the frozen ``OBSERVED_EVIDENCE_FIELDS`` set, transcribed
from the design's run schema §7.5 (``observations.*``). Any field outside
that set is supplied-value territory and is scanned/rejected normally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any

from scripts.agent_eval.errors import ContractDefect, ContractError

# ---------------------------------------------------------------------------
# R-B1-4: closed observed-evidence exempt set (transcribed from design §7.5)
# ---------------------------------------------------------------------------
#
# These are the run receipt's ``observations.*`` fields: runner-OBSERVED
# capability evidence, not caller-supplied values. They are governed by the
# observed-evidence sanitization law (amendment §3.7) instead of this
# module's reject-on-match scan. A test pins this constant against the
# design's field list so drift fails loudly (R-B1-4).
OBSERVED_EVIDENCE_FIELDS = frozenset(
    {
        "observed_sources",
        "observed_capability_ids",
        "observed_tool_schema_digests",
        "observed_network_destinations",
        "dependency_degradations",
    }
)


@dataclass(frozen=True, order=True)
class SecretShapeFinding:
    """One deterministic supplied-value finding: where, what category."""

    path: str
    code: str
    shape: str


# ---------------------------------------------------------------------------
# Closed pattern constants (amendment §3.4). No ambient state, ever.
# ---------------------------------------------------------------------------

FORBIDDEN_FIELD_NAMES = frozenset(
    {
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
    }
)

_JWT_RE = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$")

_KNOWN_SECRET_PREFIXES = (
    "sk-ant-",
    "sk-",
    "github_pat_",
    "ghp_",
    "gho_",
    "ghs_",
    "sb_secret_",
    "sb_publishable_",
    "sbp_",
)

_BEARER_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_COOKIE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:session|auth|token|secret)[a-z_]*=[^;\s]{6,}"
)
_COOKIE_HEADER_RE = re.compile(r"(?i)\bcookie\s*:\s*\S")
_ENV_ASSIGNMENT_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_(?:TOKEN|KEY|SECRET|PASSWORD)=\S+")
_MASTERMIND_ENV_RE = re.compile(r"\bMASTERMIND_[A-Z0-9_]*=\S+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LOCALHOST_RE = re.compile(r"(?i)\blocalhost\b")
_IPV4_RE = re.compile(
    r"\b((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?::\d{1,5})?\b"
)


def _known_prefix_finding(text: str) -> bool:
    for prefix in _KNOWN_SECRET_PREFIXES:
        idx = text.find(prefix)
        if idx == -1:
            continue
        rest = text[idx + len(prefix):]
        # require a nontrivial token body immediately following the prefix
        body_match = re.match(r"[A-Za-z0-9_-]{8,}", rest)
        if body_match:
            return True
    return False


def _private_host_finding(text: str) -> bool:
    if _LOCALHOST_RE.search(text):
        return True
    for match in _IPV4_RE.finditer(text):
        candidate = match.group(1)
        try:
            addr = ip_address(candidate)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved:
            return True
    return False


def _string_findings(text: str, path: str) -> list[SecretShapeFinding]:
    found: list[SecretShapeFinding] = []
    if text.count(".") == 2 and _JWT_RE.match(text):
        found.append(SecretShapeFinding(path, "JWT_SHAPE", "jwt_shape"))
    if _known_prefix_finding(text):
        found.append(SecretShapeFinding(path, "KNOWN_SECRET_PREFIX", "known_secret_prefix"))
    if _BEARER_RE.search(text):
        found.append(SecretShapeFinding(path, "AUTHORIZATION_HEADER_SHAPE", "authorization_header_shape"))
    if _COOKIE_ASSIGNMENT_RE.search(text) or _COOKIE_HEADER_RE.search(text):
        found.append(SecretShapeFinding(path, "COOKIE_SECRET_SHAPE", "cookie_secret_shape"))
    if _MASTERMIND_ENV_RE.search(text) or _ENV_ASSIGNMENT_RE.search(text):
        found.append(SecretShapeFinding(path, "ENVIRONMENT_ASSIGNMENT_SHAPE", "environment_assignment_shape"))
    if _EMAIL_RE.search(text):
        found.append(SecretShapeFinding(path, "PRIVATE_IDENTITY_SHAPE", "private_identity_shape"))
    if _private_host_finding(text):
        found.append(SecretShapeFinding(path, "PRIVATE_HOST_SHAPE", "private_host_shape"))
    return found


def _walk(value: Any, path: str, findings: list[SecretShapeFinding], *, exempt: bool) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_str = key if isinstance(key, str) else None
            key_path = f"{path}.{key_str}" if key_str is not None else f"{path}.<key>"
            child_exempt = exempt or (key_str in OBSERVED_EVIDENCE_FIELDS)
            if key_str is not None and not exempt and key_str.strip().lower() in FORBIDDEN_FIELD_NAMES:
                findings.append(SecretShapeFinding(key_path, "FORBIDDEN_FIELD_NAME", "forbidden_field_name"))
            _walk(item, key_path, findings, exempt=child_exempt)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]", findings, exempt=exempt)
        return
    if isinstance(value, str) and not exempt:
        findings.extend(_string_findings(value, path))
        return


def detect_secret_shapes(value: Any, path: str = "$") -> tuple[SecretShapeFinding, ...]:
    """Return deterministic supplied-value findings without reading ambient state.

    A subtree rooted at a key in :data:`OBSERVED_EVIDENCE_FIELDS` (R-B1-4) is
    exempt from field-name and string-shape scanning: it is runner-observed
    evidence governed by the amendment's §3.7 sanitization law, not a
    caller-supplied value.
    """
    findings: list[SecretShapeFinding] = []
    _walk(value, path, findings, exempt=False)
    return tuple(sorted(set(findings)))


def assert_public_safe_evidence(value: Any, path: str = "$") -> None:
    """Raise :class:`ContractError` if any supplied-value finding is present."""
    findings = detect_secret_shapes(value, path)
    if findings:
        defects = tuple(
            ContractDefect(finding.path, finding.code, f"rejected supplied value: {finding.shape}")
            for finding in findings
        )
        raise ContractError(defects)

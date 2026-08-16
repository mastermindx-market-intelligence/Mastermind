"""Provider-neutral OHF-P0 harness probe evidence schema.

The JSON document is the canonical machine-readable artifact.  Markdown is a
lossy human interpretation of the same observations.  Neither may guess.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "mastermind.ohf_harness_probe/v1"

CAPABILITY_KEYS = (
    "persistent_session",
    "resume",
    "fork",
    "structured_events",
    "mcp",
    "skills",
    "native_subagents",
    "approvals",
    "usage_telemetry",
    "quota_telemetry",
    "human_attach",
    "checkpoint",
)

RECOVERY_KEYS = (
    "process_restart",
    "session_resume",
    "workspace_continuity",
    "orphan_cleanup",
)

VERDICTS = frozenset({"pass", "fail", "unknown"})
OBSERVATION_STATUSES = frozenset(
    {"VERIFIED", "NOT_SUPPORTED", "NOT_TESTED", "DEGRADED", "UNKNOWN"}
)
USAGE_CLASSES = frozenset({"exact", "provider_reported", "estimated", "unknown"})

P0_QUESTIONS = (
    ("launch", "Can we launch the native harness?"),
    ("durable_session", "Can we create a durable session?"),
    ("identify", "Can we identify it?"),
    ("process_restart", "Can we restart the local process?"),
    ("resume", "Can we resume the session?"),
    ("fork", "Can we fork it?"),
    ("attest_skills", "Can we attest skills?"),
    ("attest_mcp", "Can we attest MCP?"),
    ("usage_quota", "Can we observe usage/quota?"),
    ("config_drift", "Can we detect configuration drift?"),
    ("cleanup", "Can we clean up?"),
    ("inert", "Can we do all that without touching Executive lifecycle state?"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_digest(value: Any) -> str:
    """Stable SHA-256 of a JSON-canonical value.  Secrets must already be gone."""
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def empty_capabilities() -> dict[str, str]:
    return {key: "unknown" for key in CAPABILITY_KEYS}


def empty_recovery() -> dict[str, str]:
    return {key: "unknown" for key in RECOVERY_KEYS}


def new_probe(*, probe_id: str, harness_kind: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "probe_id": probe_id,
        "observed_at": utc_now(),
        "host": {
            "platform": "",
            "architecture": "",
            "principal": "uid-unresolved",
        },
        "harness": {
            "kind": harness_kind,
            "version": "",
            "binary_digest": "",
            "protocol": "json-rpc-stdio",
            "effective_config_digest": "",
        },
        "provider": {
            "provider": "openai",
            "account_label": "unknown",
            "requested_model": "",
            "served_model_observed": "",
        },
        "capabilities": empty_capabilities(),
        "recovery": empty_recovery(),
        "security": {
            "credential_exposure": False,
            "config_attested": False,
            "unexpected_tools": [],
            "unexpected_mcp": [],
            "unexpected_plugins": [],
            "unexpected_skills": [],
            "unexpected_model_override": False,
            "unexpected_config_source": [],
        },
        "usage": {
            "classification": "unknown",
            "source": "",
            "used_percent": None,
            "input_tokens": None,
            "output_tokens": None,
        },
        "observations": [],
        "notes": [],
    }


def add_observation(
    probe: dict[str, Any],
    *,
    question_id: str,
    status: str,
    summary: str,
    evidence: str = "",
) -> None:
    if status not in OBSERVATION_STATUSES:
        raise ValueError(f"invalid observation status {status!r}")
    probe.setdefault("observations", []).append(
        {
            "id": question_id,
            "status": status,
            "summary": summary,
            "evidence": evidence,
        }
    )


def observation_status(probe: Mapping[str, Any], question_id: str) -> str:
    for row in probe.get("observations") or []:
        if row.get("id") == question_id:
            return str(row.get("status") or "UNKNOWN")
    return "UNKNOWN"


def validate_probe(probe: Mapping[str, Any]) -> list[str]:
    """Return schema defects.  Empty means the document is structurally valid."""
    errors: list[str] = []
    if probe.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if not str(probe.get("probe_id") or "").strip():
        errors.append("probe_id")
    if not str(probe.get("observed_at") or "").strip():
        errors.append("observed_at")
    for section, keys in (("capabilities", CAPABILITY_KEYS), ("recovery", RECOVERY_KEYS)):
        block = probe.get(section)
        if not isinstance(block, dict):
            errors.append(section)
            continue
        for key in keys:
            verdict = block.get(key)
            if verdict not in VERDICTS:
                errors.append(f"{section}.{key}")
    usage = probe.get("usage") or {}
    if usage.get("classification") not in USAGE_CLASSES:
        errors.append("usage.classification")
    if usage.get("used_percent") is not None and usage.get("classification") not in {
        "exact",
        "provider_reported",
    }:
        errors.append("usage.used_percent_without_provider_source")
    for row in probe.get("observations") or []:
        if not isinstance(row, dict) or row.get("status") not in OBSERVATION_STATUSES:
            errors.append("observations.status")
            break
        if not str(row.get("id") or "").strip() or not str(row.get("summary") or "").strip():
            errors.append("observations.fields")
            break
    security = probe.get("security") or {}
    if not isinstance(security, dict):
        errors.append("security")
    elif security.get("credential_exposure") is True:
        errors.append("security.credential_exposure")
    blob = json.dumps(probe, default=str).lower()
    for token in ("access_token", "refresh_token", "id_token", "auth.json"):
        if token in blob:
            errors.append(f"forbidden_token:{token}")
    return errors


def render_markdown(probe: Mapping[str, Any]) -> str:
    """Human-readable interpretation.  Status labels are never inferred."""
    lines: list[str] = [
        f"# OHF-P0 harness probe `{probe.get('probe_id', '')}`",
        "",
        f"- schema: `{probe.get('schema_version', '')}`",
        f"- observed_at: `{probe.get('observed_at', '')}`",
        f"- harness: `{((probe.get('harness') or {}).get('kind') or '')}`",
        f"- protocol: `{((probe.get('harness') or {}).get('protocol') or '')}`",
        "",
        "## P0 questions",
        "",
    ]
    by_id = {row.get("id"): row for row in probe.get("observations") or []}
    for question_id, question in P0_QUESTIONS:
        row = by_id.get(question_id) or {
            "status": "NOT_TESTED",
            "summary": "No observation recorded.",
            "evidence": "",
        }
        lines.append(f"### {question}")
        lines.append("")
        lines.append(f"- status: **{row.get('status', 'UNKNOWN')}**")
        lines.append(f"- {row.get('summary', '').strip()}")
        evidence = str(row.get("evidence") or "").strip()
        if evidence:
            lines.append(f"- evidence: `{evidence}`")
        lines.append("")
    lines.extend(["## Capabilities", ""])
    for key, verdict in (probe.get("capabilities") or {}).items():
        lines.append(f"- `{key}`: {verdict}")
    lines.extend(["", "## Recovery", ""])
    for key, verdict in (probe.get("recovery") or {}).items():
        lines.append(f"- `{key}`: {verdict}")
    usage = probe.get("usage") or {}
    lines.extend(
        [
            "",
            "## Usage / quota",
            "",
            f"- classification: `{usage.get('classification', 'unknown')}`",
            f"- source: `{usage.get('source') or 'none'}`",
            f"- used_percent: `{usage.get('used_percent')}`",
            "",
            "## Security",
            "",
        ]
    )
    security = probe.get("security") or {}
    lines.append(f"- credential_exposure: `{security.get('credential_exposure')}`")
    lines.append(f"- config_attested: `{security.get('config_attested')}`")
    for field in (
        "unexpected_tools",
        "unexpected_mcp",
        "unexpected_plugins",
        "unexpected_skills",
        "unexpected_config_source",
    ):
        values = security.get(field) or []
        rendered = ", ".join(str(item) for item in values) or "(none)"
        lines.append(f"- {field}: {rendered}")
    notes = [str(note) for note in (probe.get("notes") or []) if str(note).strip()]
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    lines.append("")
    return "\n".join(lines)


def write_evidence(probe: Mapping[str, Any], out_dir) -> tuple[Any, Any]:
    from pathlib import Path

    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    json_path = path / "probe.json"
    md_path = path / "probe.md"
    json_path.write_text(
        json.dumps(probe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(probe), encoding="utf-8")
    return json_path, md_path


def iter_question_ids() -> Iterable[str]:
    return (question_id for question_id, _ in P0_QUESTIONS)

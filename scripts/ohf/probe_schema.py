"""Provider-neutral OHF-P0 harness probe evidence schema.

The JSON document is the canonical machine-readable artifact.  Markdown is a
lossy human interpretation of the same observations.  Neither may guess.
Essential acceptance evidence must live in structured JSON fields, not notes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "mastermind.ohf_harness_probe/v1.1"

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
    "process_sigkill_resume",
    "process_sigterm_resume",
    "malformed_rpc_recovery",
    "missing_session_fail_closed",
    "workspace_missing_fail_closed",
    "config_drift_detected",
    "mcp_disappearance_detected",
    "main_process_cleanup",
    "transitive_orphan_cleanup",
)

VERDICTS = frozenset({"pass", "fail", "unknown"})
OBSERVATION_STATUSES = frozenset(
    {"VERIFIED", "NOT_SUPPORTED", "NOT_TESTED", "DEGRADED", "UNKNOWN"}
)
USAGE_CLASSES = frozenset({"exact", "provider_reported", "estimated", "unknown"})
TRI_BOOL = frozenset({True, False, "UNKNOWN"})

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

LOAD_BEARING_DIMENSIONS = ("model", "skills", "mcp")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_digest(value: Any) -> str:
    """Stable SHA-256 of a JSON-canonical value.  Secrets must already be gone."""
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def empty_capabilities() -> dict[str, str]:
    return {key: "unknown" for key in CAPABILITY_KEYS}


def empty_recovery() -> dict[str, str]:
    return {key: "UNKNOWN" for key in RECOVERY_KEYS}


def requested_capability_manifest(
    *,
    model: str,
    skills: Iterable[str],
    mcp_servers: Iterable[str],
    mcp_tools: Iterable[str],
    plugins: Iterable[str],
    approval_policy: str,
    sandbox_mode: str,
    permissions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "skills": sorted({str(item) for item in skills if str(item).strip()}),
        "mcp_servers": sorted({str(item) for item in mcp_servers if str(item).strip()}),
        "mcp_tools": sorted({str(item) for item in mcp_tools if str(item).strip()}),
        "plugins": sorted({str(item) for item in plugins if str(item).strip()}),
        "approval_policy": approval_policy,
        "sandbox_mode": sandbox_mode,
        "permissions": dict(permissions or {}),
    }


def observed_capability_manifest(
    *,
    model: str | None,
    skills: Iterable[str],
    mcp_servers: Iterable[str],
    mcp_tools: Iterable[str],
    plugins: Iterable[str],
    approval_policy: str | None,
    sandbox_mode: str | None,
    harness_version: str,
) -> dict[str, Any]:
    return {
        "model": model or "",
        "skills": sorted({str(item) for item in skills if str(item).strip()}),
        "mcp_servers": sorted({str(item) for item in mcp_servers if str(item).strip()}),
        "mcp_tools": sorted({str(item) for item in mcp_tools if str(item).strip()}),
        "plugins": sorted({str(item) for item in plugins if str(item).strip()}),
        "approval_policy": approval_policy or "",
        "sandbox_mode": sandbox_mode or "",
        "harness_version": harness_version,
    }


def attest_manifests(
    requested: Mapping[str, Any],
    observed: Mapping[str, Any],
    unobservable: Iterable[str] = (),
) -> dict[str, Any]:
    """Compare requested vs observed.  Unobservable dimensions are UNKNOWN, not accepted."""
    unobs = sorted({str(item) for item in unobservable if str(item).strip()})
    req_skills = set(requested.get("skills") or [])
    obs_skills = set(observed.get("skills") or [])
    req_mcp = set(requested.get("mcp_servers") or [])
    obs_mcp = set(observed.get("mcp_servers") or [])
    req_plugins = set(requested.get("plugins") or [])
    obs_plugins = set(observed.get("plugins") or [])
    missing_required_skills = sorted(req_skills - obs_skills)
    missing_required_mcp = sorted(req_mcp - obs_mcp)
    missing_required_plugins = sorted(req_plugins - obs_plugins)
    unexpected_skills = sorted(obs_skills - req_skills)
    unexpected_mcp = sorted(obs_mcp - req_mcp)
    unexpected_plugins = sorted(obs_plugins - req_plugins)
    req_model = str(requested.get("model") or "")
    obs_model = str(observed.get("model") or "")
    if "model" in unobs or not obs_model:
        model_match: bool | str = "UNKNOWN"
        unexpected_model_override = False
    else:
        model_match = obs_model == req_model
        unexpected_model_override = bool(obs_model and obs_model != req_model)

    load_bearing_unobservable = [key for key in LOAD_BEARING_DIMENSIONS if key in unobs]
    attested = (
        model_match is True
        and not missing_required_skills
        and not missing_required_mcp
        and not missing_required_plugins
        and not unexpected_skills
        and not unexpected_mcp
        and not unexpected_plugins
        and not unexpected_model_override
        and not load_bearing_unobservable
    )
    return {
        "model_match": model_match,
        "missing_required_skills": missing_required_skills,
        "missing_required_mcp": missing_required_mcp,
        "missing_required_plugins": missing_required_plugins,
        "unexpected_skills": unexpected_skills,
        "unexpected_mcp": unexpected_mcp,
        "unexpected_plugins": unexpected_plugins,
        "unexpected_model_override": unexpected_model_override,
        "unobservable_dimensions": unobs,
        "config_attested": attested,
    }


def new_probe(*, probe_id: str, harness_kind: str) -> dict[str, Any]:
    requested = requested_capability_manifest(
        model="",
        skills=[],
        mcp_servers=[],
        mcp_tools=[],
        plugins=[],
        approval_policy="never",
        sandbox_mode="read-only",
    )
    observed = observed_capability_manifest(
        model="",
        skills=[],
        mcp_servers=[],
        mcp_tools=[],
        plugins=[],
        approval_policy="",
        sandbox_mode="",
        harness_version="",
    )
    attestation = attest_manifests(requested, observed, unobservable=LOAD_BEARING_DIMENSIONS)
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
            "requested_manifest_digest": "",
            "observed_manifest_digest": "",
        },
        "provider": {
            "provider": "openai",
            "auth_type": "UNKNOWN",
            "plan_type": "UNKNOWN",
            "requires_openai_auth": None,
            "requested_model": "",
            "served_model_observed": "",
        },
        "auth_isolation": {
            "auth_json_copied": False,
            "auth_json_symlinked": False,
            "implicit_default_home_fallback": False,
            "dedicated_home_authenticated_independently": False,
            "codex_home_used": "",
        },
        "requested_manifest": requested,
        "observed_manifest": observed,
        "attestation": attestation,
        "session_continuity": {
            "initial_pid": None,
            "replacement_pid": None,
            "sigkill_replacement_pid": None,
            "sigterm_replacement_pid": None,
            "initial_thread_id": "",
            "resumed_thread_id": "",
            "sigkill_resume_thread_id": "",
            "sigterm_resume_thread_id": "",
            "process_identity_changed": "UNKNOWN",
            "native_thread_survived": "UNKNOWN",
            "workspace_survived": "UNKNOWN",
            "process_generations": [],
        },
        "fork_proof": {
            "parent_thread_id": "",
            "fork_thread_id": "",
            "fork_source_thread": "",
            "parent_neq_fork": "UNKNOWN",
            "inherited_earlier_state": "UNKNOWN",
            "parent_continuation_isolated": "UNKNOWN",
            "fork_continuation_isolated": "UNKNOWN",
            "independent_continuation_proven": "UNKNOWN",
        },
        "skill_attestation": {
            "requested_present": False,
            "discovered": False,
            "invokable": "UNKNOWN",
            "invoked_successfully": False,
            "removal": {
                "reloadable_without_restart": "UNKNOWN",
                "status": "NOT_TESTED",
            },
        },
        "mcp_attestation": {
            "configured": False,
            "server_visible": False,
            "tool_visible": False,
            "tool_callable": False,
            "structured_event_visible": False,
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
            "redaction_failures": [],
        },
        "usage": {
            "classification": "unknown",
            "source": "",
            "used_percent": None,
            "input_tokens": None,
            "output_tokens": None,
        },
        "quota": {
            "classification": "unknown",
            "source": "",
        },
        "cleanup_proof": {
            "main_pid_exited": False,
            "descendant_census": False,
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


def apply_attestation(probe: dict[str, Any], attestation: Mapping[str, Any]) -> None:
    probe["attestation"] = dict(attestation)
    security = probe.setdefault("security", {})
    security["config_attested"] = bool(attestation.get("config_attested"))
    security["unexpected_skills"] = list(attestation.get("unexpected_skills") or [])
    security["unexpected_mcp"] = list(attestation.get("unexpected_mcp") or [])
    security["unexpected_plugins"] = list(attestation.get("unexpected_plugins") or [])
    security["unexpected_model_override"] = bool(attestation.get("unexpected_model_override"))
    if not attestation.get("config_attested"):
        sources = security.setdefault("unexpected_config_source", [])
        if "manifest_mismatch" not in sources:
            sources.append("manifest_mismatch")


def validate_probe(probe: Mapping[str, Any]) -> list[str]:
    """Return schema defects.  Empty means the document is structurally valid."""
    errors: list[str] = []
    if probe.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if not str(probe.get("probe_id") or "").strip():
        errors.append("probe_id")
    if not str(probe.get("observed_at") or "").strip():
        errors.append("observed_at")
    capabilities = probe.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("capabilities")
    else:
        for key in CAPABILITY_KEYS:
            if capabilities.get(key) not in VERDICTS:
                errors.append(f"capabilities.{key}")
    recovery = probe.get("recovery")
    if not isinstance(recovery, dict):
        errors.append("recovery")
    else:
        for key in RECOVERY_KEYS:
            if recovery.get(key) not in OBSERVATION_STATUSES:
                errors.append(f"recovery.{key}")
        if recovery.get("transitive_orphan_cleanup") == "VERIFIED":
            proof = probe.get("cleanup_proof") or {}
            if not proof.get("descendant_census"):
                errors.append("recovery.transitive_orphan_cleanup_unproven")
        if recovery.get("main_process_cleanup") == "VERIFIED":
            proof = probe.get("cleanup_proof") or {}
            if not proof.get("main_pid_exited"):
                errors.append("recovery.main_process_cleanup_unproven")
    usage = probe.get("usage") or {}
    if usage.get("classification") not in USAGE_CLASSES:
        errors.append("usage.classification")
    if usage.get("used_percent") is not None and usage.get("classification") not in {
        "exact",
        "provider_reported",
    }:
        errors.append("usage.used_percent_without_provider_source")
    quota = probe.get("quota") or {}
    if quota.get("classification") not in USAGE_CLASSES:
        errors.append("quota.classification")
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
    attestation = probe.get("attestation")
    if not isinstance(attestation, dict):
        errors.append("attestation")
    elif "config_attested" not in attestation:
        errors.append("attestation.config_attested")
    blob = json.dumps(probe, default=str).lower()
    for token in ("access_token", "refresh_token", "id_token", "auth.json"):
        if token in blob:
            errors.append(f"forbidden_token:{token}")
    if "copy_auth" in blob or "shutil.copy2" in blob:
        errors.append("forbidden_auth_copy_evidence")
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
    harness = probe.get("harness") or {}
    lines.extend(
        [
            "## Capability manifests",
            "",
            f"- requested_manifest_digest: `{harness.get('requested_manifest_digest') or ''}`",
            f"- observed_manifest_digest: `{harness.get('observed_manifest_digest') or ''}`",
            "",
        ]
    )
    attestation = probe.get("attestation") or {}
    lines.append(f"- model_match: `{attestation.get('model_match')}`")
    lines.append(f"- config_attested: `{attestation.get('config_attested')}`")
    for field in (
        "missing_required_skills",
        "missing_required_mcp",
        "missing_required_plugins",
        "unexpected_skills",
        "unexpected_mcp",
        "unexpected_plugins",
        "unobservable_dimensions",
    ):
        values = attestation.get(field) or []
        rendered = ", ".join(str(item) for item in values) or "(none)"
        lines.append(f"- {field}: {rendered}")
    lines.append("")
    session = probe.get("session_continuity") or {}
    lines.extend(
        [
            "## Session continuity",
            "",
            f"- initial_pid: `{session.get('initial_pid')}`",
            f"- replacement_pid: `{session.get('replacement_pid')}`",
            f"- sigkill_replacement_pid: `{session.get('sigkill_replacement_pid')}`",
            f"- sigterm_replacement_pid: `{session.get('sigterm_replacement_pid')}`",
            f"- initial_thread_id: `{session.get('initial_thread_id') or ''}`",
            f"- resumed_thread_id: `{session.get('resumed_thread_id') or ''}`",
            f"- sigkill_resume_thread_id: `{session.get('sigkill_resume_thread_id') or ''}`",
            f"- sigterm_resume_thread_id: `{session.get('sigterm_resume_thread_id') or ''}`",
            f"- process_identity_changed: `{session.get('process_identity_changed')}`",
            f"- native_thread_survived: `{session.get('native_thread_survived')}`",
            f"- workspace_survived: `{session.get('workspace_survived')}`",
            "",
            "## Fork proof",
            "",
        ]
    )
    fork = probe.get("fork_proof") or {}
    for field in (
        "parent_thread_id",
        "fork_thread_id",
        "fork_source_thread",
        "parent_neq_fork",
        "inherited_earlier_state",
        "parent_continuation_isolated",
        "fork_continuation_isolated",
        "independent_continuation_proven",
    ):
        lines.append(f"- {field}: `{fork.get(field)}`")
    lines.extend(["", "## Capabilities", ""])
    for key, verdict in (probe.get("capabilities") or {}).items():
        lines.append(f"- `{key}`: {verdict}")
    lines.extend(["", "## Recovery", ""])
    for key, verdict in (probe.get("recovery") or {}).items():
        lines.append(f"- `{key}`: {verdict}")
    usage = probe.get("usage") or {}
    quota = probe.get("quota") or {}
    lines.extend(
        [
            "",
            "## Usage / quota",
            "",
            f"- usage.classification: `{usage.get('classification', 'unknown')}`",
            f"- usage.source: `{usage.get('source') or 'none'}`",
            f"- quota.classification: `{quota.get('classification', 'unknown')}`",
            f"- quota.source: `{quota.get('source') or 'none'}`",
        ]
    )
    for window in ("primary", "secondary"):
        block = quota.get(window)
        if isinstance(block, dict):
            lines.append(
                f"- quota.{window}: used_percent=`{block.get('used_percent')}` "
                f"window_duration_minutes=`{block.get('window_duration_minutes')}` "
                f"resets_at=`{block.get('resets_at')}`"
            )
    if quota.get("rate_limit_reached_type") is not None:
        lines.append(f"- rate_limit_reached_type: `{quota.get('rate_limit_reached_type')}`")
    auth = probe.get("auth_isolation") or {}
    lines.extend(
        [
            "",
            "## Auth isolation",
            "",
            f"- auth_json_copied: `{auth.get('auth_json_copied')}`",
            f"- auth_json_symlinked: `{auth.get('auth_json_symlinked')}`",
            f"- implicit_default_home_fallback: `{auth.get('implicit_default_home_fallback')}`",
            f"- dedicated_home_authenticated_independently: `{auth.get('dedicated_home_authenticated_independently')}`",
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
        "redaction_failures",
    ):
        values = security.get(field) or []
        rendered = ", ".join(str(item) for item in values) or "(none)"
        lines.append(f"- {field}: {rendered}")
    cleanup = probe.get("cleanup_proof") or {}
    lines.extend(
        [
            "",
            "## Cleanup proof",
            "",
            f"- main_pid_exited: `{cleanup.get('main_pid_exited')}`",
            f"- descendant_census: `{cleanup.get('descendant_census')}`",
        ]
    )
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

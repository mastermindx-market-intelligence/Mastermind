"""Source-pinned preparation for adopting an EXISTING Hermes bot in Paperclip.

This module is mounted in the company inspector. It never patches a live agent,
spawns a runtime, copies credentials or claims an atomic configuration hold.
The pinned donor's general agent PATCH has no expected-revision field; a
preflight digest is not compare-and-swap or exclusive writer ownership.
"""
from __future__ import annotations

from .contract import DONOR_REVISION, PaperclipError, digest, identifier
from .installed import HermesBinding


def prepare_existing_runtime(agent: object, *, company_id: str, binding: HermesBinding | None,
                             work_owner: str, wake_owner: str) -> dict:
    if type(agent) is not dict or agent.get("companyId") != company_id:
        raise PaperclipError("SOURCE_SCOPE_MISMATCH")
    agent_id = identifier(agent.get("id"))
    if binding is not None and binding.agent_id != agent_id:
        raise PaperclipError("SOURCE_SCOPE_MISMATCH")
    adapter = agent.get("adapterType")
    if not isinstance(adapter, str) or len(adapter) > 96:
        raise PaperclipError("SOURCE_RESPONSE_INVALID")
    runtime = agent.get("runtimeConfig")
    heartbeat = runtime.get("heartbeat") if type(runtime) is dict else None
    enabled = heartbeat.get("enabled") if type(heartbeat) is dict else None
    concurrency = heartbeat.get("maxConcurrentRuns") if type(heartbeat) is dict else None
    enabled = enabled if type(enabled) is bool else None
    concurrency = concurrency if type(concurrency) is int and 0 <= concurrency <= 1000 else None
    status = agent.get("status") if isinstance(agent.get("status"), str) else "unknown"
    observed = {"agentId": agent_id, "companyId": company_id, "adapterType": adapter,
                "status": status, "heartbeatEnabled": enabled, "configuredConcurrency": concurrency,
                "updatedAt": agent.get("updatedAt") if isinstance(agent.get("updatedAt"), str) else None}
    requirements = ["EXCLUSIVE_CONFIGURATION_WRITER", "ORIGINAL_RUNS_AND_EFFECTS_RECONCILED",
                    "QUALIFIED_EXISTING_HTTP_SSE_GATEWAY", "EXISTING_SECRET_BINDING",
                    "EXECUTIVE_AND_CAPACITY_CONSUMER_BINDINGS"]
    if binding is None:
        requirements.append("EXISTING_HERMES_PROFILE_REFERENCE")
    if binding is not None and binding.supervisor_session_ref is None:
        requirements.append("ORIGINAL_SUPERVISOR_RETURN_REFERENCE")
    if adapter not in {"hermes_local", "hermes_gateway"}:
        requirements.append("DONOR_RUNTIME_MISMATCH")
    if work_owner != "paperclip":
        requirements.append("WORK_OWNER_CUTOVER")
    if wake_owner != "paperclip":
        requirements.append("WAKE_OWNER_CUTOVER")
    return {
        "schema": "mastermind.paperclip_hermes_migration.v1", "state": "PREPARED_NOT_APPLIED",
        "agentId": agent_id, "companyId": company_id, "sourceRevision": DONOR_REVISION,
        "observed": observed, "observedDigest": digest(observed),
        "profileRef": binding.profile_ref if binding else None,
        "gatewayRef": binding.gateway_ref if binding else None,
        "supervisorSessionRef": binding.supervisor_session_ref if binding else None,
        "targetAdapter": "hermes_gateway", "package": "@paperclipai/hermes-paperclip-adapter",
        "packageVersion": "2026.1106.0", "workSessionStrategy": "issue",
        "supervisorUse": "RETAIN_FOR_DIRECT_STEERING_AND_ORIGINAL_RETURN",
        "plannedRuntimeState": "KEEP_PAUSED_AND_HEARTBEAT_DISABLED_UNTIL_CUTOVER",
        "configurationCas": "NOT_SUPPORTED_BY_PINNED_AGENT_PATCH",
        "credentialMode": "EXISTING_PAPERCLIP_OR_HERMES_SECRET_OWNER_ONLY",
        "privateNativeProtocol": "hermes-gateway-v1",
        "targetProtocol": "HERMES_HTTP_SSE",
        "requirements": requirements, "applyAvailable": False, "executionRequested": False,
        "retain": ["agent_id", "company_id", "Hermes_profile", "native_supervisor_session", "memory",
                   "skills", "tool_permissions", "provider_configuration", "project_context", "original_return"],
        "replace": ["bespoke_company_directory", "bespoke_work_board", "bespoke_goal_project_management",
                    "bespoke_company_attention_views", "legacy_business_wake_scheduler_after_cutover"],
    }

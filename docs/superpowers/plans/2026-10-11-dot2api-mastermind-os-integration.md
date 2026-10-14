# Dot2API Mastermind OS Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a production-disarmed but source-complete READ/RESEARCH Executive worker adapter for one OpenAI Dot through Dot2API, reusing the existing Executive lifecycle, broker, routing, capability, recovery, and Session Bridge owners.

**Architecture:** A strict no-retry Dot2API client is wrapped by an attested local transport subprocess and the existing `WorkerExecutionAdapter` contract. Provider-local task state is subordinate transport evidence; exact task identity is persisted in the existing `WorkerProcessRef`, while existing remote-broker and capability/routing seams remain the only placement path.

**Tech Stack:** Python 3.11+, stdlib HTTP/JSON/asyncio/subprocess, existing Executive Runtime/Supervisor/WorkerBroker, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-dot2api-mastermind-os-integration.md`

## Global Constraints

- Protected basis is `1f5befa44487ffb7ac2a0ca44ccd85c7c9da1355`; preserve later current-source semantics during integration.
- Upstream contract basis is `Pluviobyte/dot2api@66a761505ff73c5dca730260efcaeb5697db81ad` under MIT; do not vendor its task store or copy credentials.
- Executive OS remains the only Mastermind lifecycle/retry authority.
- One Attempt submits at most one provider task and sets `max_attempts=1`.
- READ/RESEARCH only; no workspace writes, artifacts, validation commands, skills, MCP, plugins, native helpers, or connected-app grants.
- Worker egress is loopback only; public Dot ingress is a separate deployment owner.
- Source release stays production disarmed and does not claim a live Dot.

## Review Focus

- Mutating HTTP failures that occur after the provider may have committed must remain effect-unknown, not known-safe failures.
- Cancel-vs-completion races must preserve the provider's actual terminal state.
- Duplicate JSON keys and NaN/Infinity must not enter accepted Executive results.
- Transport-script or Python drift between construction and spawn must refuse before provider I/O.
- Restart recovery must use the exact persisted task id and never submit again.

---

### Task 1: Strict Dot2API client and effect model

**Files:**
- Create/modify: `integrations/dot2api/client.py`
- Create/modify: `integrations/dot2api/__init__.py`
- Test: `tests/test_dot2api_worker.py`

**Interfaces:**
- Produces: `Dot2ApiClient`, `Dot2ApiTask`, `Dot2ApiClientError`, `Dot2ApiEffectUnknown`, `Dot2ApiProtocolError`.
- Consumes: Dot2API `/readyz`, `/v1/tasks`, `/v1/tasks/{id}`, and `/v1/tools/cancel_task` contracts.

- [ ] Add RED tests for duplicate/non-finite JSON, mismatched queue/attempt ceiling, redirect refusal, HTTP 5xx mutation uncertainty, and no ambiguous-submit retry.
- [ ] Run the focused tests and confirm each fails for the intended missing contract.
- [ ] Implement strict bounded parsing, exact task binding, and method/status-aware effect classification.
- [ ] Run the focused client tests to GREEN.

### Task 2: Worker lifecycle, recovery, and cancellation truth

**Files:**
- Create/modify: `control_plane/dot2api_worker.py`
- Create/modify: `ops/executive_os/dot2api_transport_worker.py`
- Test: `tests/test_dot2api_worker.py`

**Interfaces:**
- Consumes: Task 1 client and existing `WorkerLaunchSpec`, `WorkerProcessRef`, `CollectionReceipt`, `WorkerRecoveryBinding`.
- Produces: `Dot2ApiWorkerAdapter` implementing the existing worker adapter protocol.

- [ ] Add RED tests for READ+RESEARCH, loopback-only egress, secret-canary enforcement, binary/script drift, cancel/completion races, strict result parsing, and recovery without resubmission.
- [ ] Run each discriminator and verify RED for the intended reason.
- [ ] Implement the smallest lifecycle repairs while preserving one-submit/no-retry semantics.
- [ ] Run the Dot2API worker suite to GREEN and verify no credential bytes exist in durable files or attestations.

### Task 3: Executive broker, capability, and routing composition

**Files:**
- Modify: `control_plane/worker_adapter.py`
- Modify: `control_plane/executive_worker_broker.py`
- Modify: `control_plane/remote_attempt_transport.py`
- Modify: `control_plane/executive_agent_capabilities.py`
- Modify: `config/executive_agent_capabilities.json`
- Modify: `config/executive_worker_routes.json`
- Test: `tests/test_worker_adapter.py`
- Test: `tests/test_executive_agent_capabilities.py`
- Test: `tests/test_executive_model_router.py`
- Test: `tests/test_remote_attempt_transport.py`
- Test: `tests/test_executive_worker_broker.py`

**Interfaces:**
- Consumes: `Dot2ApiWorkerAdapter` and existing remote-broker facade contract.
- Produces: registered but unqualified `dot2api` adapter, `dot` provider alias, read-only profile, remote endpoint/fleet identity, and unchanged active routing outcomes.

- [ ] Add/retain RED coverage for adapter identity, remote provider/adapter matching, read-only capability ceiling, prior policy digest reconstruction, and default routing non-selection.
- [ ] Implement only additive closed identities; keep descriptor/provider/alias production gates disabled.
- [ ] Restore minimal JSON diffs rather than formatting unrelated routing policy.
- [ ] Run focused composition suites; classify unchanged environmental failures against protected base.

### Task 4: Durable design, provenance, and verification

**Files:**
- Create: `docs/superpowers/specs/2026-10-11-dot2api-mastermind-os-integration.md`
- Create: `docs/superpowers/plans/2026-10-11-dot2api-mastermind-os-integration.md`
- Create: `docs/runbooks/dot2api-worker.md`
- Create: `THIRD_PARTY_NOTICES/dot2api.txt` if source copying crosses the substantial-portion threshold; otherwise record upstream provenance in the runbook.

**Interfaces:**
- Produces: exact source/installation boundary, operator setup, canary, recovery, rollback, and acceptance proof checklist.

- [ ] Document upstream commit/license and the no-vendoring decision.
- [ ] Document host configuration without credentials, public-Dot versus loopback-worker endpoints, and the production-disarmed selector state.
- [ ] Run compileall, focused suites, relevant repository contract guards, `git diff --check`, and secret/path scans.
- [ ] Commit coherent source increments, publish one branch, open one Draft PR, and request independent exact-head review without claiming installation or production proof.

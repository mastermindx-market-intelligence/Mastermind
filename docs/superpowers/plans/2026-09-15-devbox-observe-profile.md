# DevBox Observe Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the four-tool DevBox execution surface for supported ChatGPT plans while adding a deployment-owned, OAuth-scoped two-tool observation surface that Personal Pro can lawfully traverse.

**Architecture:** Reuse the existing resource policy, stable lease, authenticated MCP server, bound port, Codespace runtime, and Auth0 resource server. The exact singleton scope selects a closed tool profile: `workbench.execute` exposes all four tools; `workbench.observe` exposes only `devbox_status` and `read_devbox_process`. The model cannot select or widen the profile, and both MCP edge and bound port fail closed.

**Tech Stack:** Python 3.12+, MCP Python SDK, pytest/unittest, existing `integrations.business_mcp_auth` and `integrations.devbox_mcp` modules.

**Spec:** `docs/superpowers/specs/2026-09-12-codespaces-devbox-workbench-design.md`

## Global Constraints

- Do not create a second target, process, OAuth, credential, audit, lifecycle, retry, or source-publication plane.
- Do not modify shared Business MCP auth files overlapped by PRs #269 and #291.
- `workbench.observe` may expose only `devbox_status` and `read_devbox_process`.
- `workbench.execute` must preserve the exact existing four-tool behavior.
- The scope/profile mapping is deployment-owned; no request argument may select it.
- Personal Pro observation proof and full four-tool execution proof are separate capability rulings.
- No `PROVEN_LIVE` claim without real ChatGPT-to-OAuth-to-public-endpoint-to-Codespace traversal.

---
### Task 1: Scope-derived closed tool profiles

**Files:**
- Modify: `integrations/devbox_mcp/contracts.py`
- Test: `tests/devbox_mcp/test_contracts.py`

**Interfaces:**
- Produces: `OBSERVE_SCOPE`, `EXECUTE_SCOPE`, `tools_for_scope(scope: tuple[str, ...]) -> tuple[str, ...]`.
- `tools_for_scope(("workbench.observe",))` returns status/read; execute returns all four; every other scope tuple raises `ValueError`.

- [x] Add failing tests for both exact profiles and unknown/multiple-scope refusal.
- [x] Run the focused contract tests and confirm the new tests fail because the profile API is absent.
- [x] Implement immutable constants and the minimal exact-scope selector.
- [x] Run the focused contract tests and confirm green.

### Task 2: MCP edge and bound-port enforcement

**Files:**
- Modify: `integrations/devbox_mcp/app.py`
- Modify: `integrations/devbox_mcp/deployment.py`
- Modify: `integrations/devbox_mcp/port.py` (register the profile-refusal code)
- Test: `tests/devbox_mcp/test_app.py`
- Test: `tests/devbox_mcp/test_deployment.py`

**Interfaces:**
- Consumes: `tools_for_scope` from Task 1.
- Produces: scope-selected tool discovery and independent port-side call refusal.

- [x] Add failing app tests proving observe discovery lists exactly status/read and a direct start/cancel RPC never reaches the port.
- [x] Add failing deployment tests proving an observe lease accepts only observe tools while execute behavior is unchanged.
- [x] Run both focused files and verify expected failures.
- [x] Filter MCP schemas, discovery, validation, and calls by the selected scope.
- [x] Enforce the same allowed-tool tuple in `BoundDevBoxPort.call`.
- [x] Run both focused files and confirm green.
### Task 3: End-to-end service composition

**Files:**
- Modify: `ops/devbox/run_codespace_devbox.py` only if profile selection is not already implied by policy/lease.
- Test: `tests/devbox_mcp/test_entrypoint.py`

**Interfaces:**
- Consumes: exact policy and lease scopes.
- Produces: a Codespace service whose advertised and callable tools match the scope without a second configuration switch.

- [x] Parameterize policy/lease fixtures by exact scope and add an observe-service composition test.
- [x] Run the focused entrypoint test and verify it fails before implementation.
- [x] Make only the minimal composition change required; do not add a new profile file or CLI flag.
- [x] Run the focused entrypoint tests and confirm green.

### Task 4: Correct product and acceptance truth

**Files:**
- Modify: `docs/superpowers/specs/2026-09-12-codespaces-devbox-workbench-design.md`
- Modify: `docs/runbooks/codespaces-devbox-canary.md`

- [x] Replace the stale Personal Pro write assertion with the current supported-plan boundary.
- [x] Define `OBSERVE_ONLY` and `EXECUTE` profiles, exact scopes, tools, and fail-closed behavior.
- [x] Split acceptance into Personal Pro observation proof and full supported-plan four-tool proof.
- [x] Keep the parent capability `BUILT_NOT_PROVEN` until the full write traversal is completed.
- [x] Document canary cleanup and Auth0 scope repair without creating a new tenant/application/resource server.

### Task 5: Verification, publication, and live proof

- [x] Run all DevBox tests, compile checks, and `git diff --check`.
- [x] Review the diff against the updated spec and protected-master collisions.
- [ ] Commit and push the exact canonical PR #574 branch; verify remote head and hosted checks.
- [ ] Reconcile and reuse the retained disposable Codespace; do not create a third canary.
- [ ] Configure the existing Auth0 resource server with `workbench.observe` alongside `workbench.execute` only when the exact endpoint is known.
- [ ] Prove a real Personal Pro `devbox_status` call and, when a pre-existing process reference exists, `read_devbox_process`.
- [ ] Record the observation slice separately; do not promote the four-tool parent capability.
- [ ] Re-private the port, stop the service, remove the exact disposable canaries after reconciliation, and update durable GitHub/Agent OS records.
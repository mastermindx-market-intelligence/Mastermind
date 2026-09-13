# Codespaces DevBox Workbench Implementation Plan

> **For execution:** follow TDD red-green-refactor, verify fresh evidence before every completion claim, and preserve the protected no-rebuild boundary in the paired design.

**Goal:** Add one first-party DevBox MCP vertical that runs inside an explicitly bound GitHub Codespace, provides authenticated attended shell/process control to ChatGPT Web, survives model turns through durable provider-local process receipts, and proves the real cloud execution path without making Codespaces a second lifecycle/source authority.

**Architecture:** A closed MCP facade depends on an injected `DevBoxPort`. `CodespaceDevBoxRuntime` implements that port locally inside a Codespace with exact startup-bound repo/state identities, sanitized subprocess environment, at-most-once operation keys, detached supervisors, independent stdout/stderr cursors, exact process-generation cancellation, and explicit effect uncertainty. Existing `business_mcp_auth` supplies bearer verification/audit. GitHub owns Codespace creation/start/stop; GitHub publication remains outside the shell profile.

**Tech Stack:** Python 3.12, FastMCP / MCP SDK already pinned by Mastermind, `jsonschema`, Starlette/ASGI, Linux subprocess/process groups, pytest, Git/GitHub CLI for canary provisioning only.

---

## Task 1 — Freeze the pure DevBox contract

**Files:**
- Create `integrations/devbox_mcp/__init__.py`
- Create `integrations/devbox_mcp/contracts.py`
- Test `tests/devbox_mcp/test_contracts.py`

**RED:** tests require exactly four tool names; closed schemas; bounded operation/process refs; no target/cwd/env/host/credential fields; effect vocabulary `NOT_APPLIED|APPLIED|EFFECT_UNKNOWN`; cursor and terminal result invariants; schema digest changes under authority widening.

**GREEN:** implement immutable dataclasses/validators/schema snapshot helpers only. No I/O or MCP SDK imports.

**Verify:** `python -m pytest tests/devbox_mcp/test_contracts.py -q`.

## Task 2 — Build the Codespace-local process runtime

**Files:**
- Create `integrations/devbox_mcp/port.py`
- Create `integrations/devbox_mcp/codespace_runtime.py`
- Test `tests/devbox_mcp/test_codespace_runtime.py`

**RED behaviors:** startup refuses non-Linux/unqualified shell or unsafe repo/state roots; root identity is stable; child env strips GitHub/cloud/SSH credential variables and Git credential helper configuration; start persists a pre-effect receipt before spawn; identical operation reuses one process; changed payload conflicts; stdout/stderr are separate and independently cursor-read; exit 0 and exit 7 preserved; timeout terminal truth; cancel verifies boot/PID start identity before process-group signal; stale/unknown process refuses; output bounds/gaps explicit.

**GREEN:** implement an injected-clock/runtime-root `CodespaceDevBoxRuntime`. Use a detached supervisor process for commands expected to outlive the request. Store provider-local execution receipts in private deployment-owned state outside the repo; fsync atomic JSON transitions. Never create Executive lifecycle rows or Git remotes.

**Verify:** `python -m pytest tests/devbox_mcp/test_codespace_runtime.py -q` and targeted mutation controls for duplicate-start, credential-env leak, PID-reuse check and stdout/stderr merge.

## Task 3 — Compose authenticated DevBox MCP

**Files:**
- Create `integrations/devbox_mcp/app.py`
- Create `integrations/devbox_mcp/deployment.py`
- Create `config/business_mcp/devbox_policy.example.json`
- Test `tests/devbox_mcp/test_app.py`
- Test `tests/devbox_mcp/test_deployment.py`

**RED:** dedicated exact `workbench.execute` scope; four static tools only; closed inputs; bearer principal cannot author target/binding/root; write tools carry modifying annotations; no subprocess/network/GitHub import in app layer; auth is revalidated across awaited calls; failures are fixed bounded codes; server has no resource/prompt/sampling/root/session registry surfaces.

**GREEN:** reuse `MastermindTokenVerifier`, `ResourcePolicy`, and audit sink. Convert verified access into a request-local caller and dispatch only through injected `DevBoxPort`. Deployment binds one exact target/generation/repo identity and transport allowlist.

**Verify:** `python -m pytest tests/devbox_mcp/test_app.py tests/devbox_mcp/test_deployment.py -q` plus existing business-auth tests touched by composition.

## Task 4 — Add Codespace entrypoint and qualification harness

**Files:**
- Create `ops/devbox/run_codespace_devbox.py`
- Create `ops/devbox/codespace_preflight.py`
- Create `docs/runbooks/codespaces-devbox-canary.md`
- Test `tests/devbox_mcp/test_codespace_preflight.py`

**RED:** preflight requires Linux, `/bin/bash`, a real Git worktree, exact committed baseline, writable private state root outside `.git`, no unsafe env inheritance, exact policy/resource host binding and explicit allowed host; no wildcard/public unauthenticated configuration.

**GREEN:** entrypoint consumes only operator/deployment configuration, opens the runtime, composes MCP, and serves Streamable HTTP. It does not create/start/stop Codespaces or mint OAuth credentials.

**Verify:** targeted pytest plus `python -m compileall integrations/devbox_mcp ops/devbox` and `git diff --check`.

## Task 5 — Prove the local contract before spending a Codespace

Run the full new suite, then adjacent Workbench/business-auth suites. Exercise a temporary local Linux-compatible fixture where platform-independent; preserve platform-specific Codespace checks as explicit held canary evidence rather than faking them on macOS.

**Verify:**
`python -m pytest tests/devbox_mcp tests/workbench_read_mcp tests/test_business_mcp_auth_audit.py tests/test_business_mcp_auth_mcp_adapter.py -q`.

## Task 6 — Acquire the GitHub Codespaces action gate and run the real cloud canary

**External gate:** current `gh` token on the authorized Mac lacks `codespace` scope. Refresh the existing GitHub CLI authorization for scope `codespace`; do not create a new credential plane. Read back scope/capability before any create.

Create one disposable Codespace from this exact branch on the smallest available machine and aggressive idle timeout. Run the preflight and the Task-2 behavioral canary inside that Codespace. Prove exit-0, exit-7, detached continuation/readback, duplicate same-operation reconciliation, conflict refusal, exact cancellation and credential-env stripping. Do not push/merge from the DevBox shell.

Stop the Codespace after evidence capture unless the next MCP canary immediately requires it.

## Task 7 — Connect the real Personal Pro custom MCP path

Use the Chairman’s already-proven Personal Pro custom-MCP write capability. Publish/route the Codespace-hosted authenticated `/mcp` endpoint through the existing approved app/tunnel mechanism; do not add a second tunnel/permission store. Connect only the dedicated DevBox resource and exact policy generation.

From the real Personal Pro Sol conversation, invoke `devbox_status`, start an exit-0 command, observe it, make one disposable file change through a command, read exact Git evidence, run exit-7, and verify same-operation replay does not spawn process two. Disconnect/stop control must become unavailable/unknown, not silently fall back to the Mac.

This is the first point the DevBox vertical may be classified `PROVEN_LIVE` for the Personal Pro seat.

## Task 8 — Source delivery and durable closeout

Run full fresh verification required by the changed paths. Commit to `codex/codespaces-devbox-sol-20260912a`, push non-force, open a draft PR, record exact canary receipts and remaining release gates. Independent source review, merge, installed endpoint/app proof, and Chairman final acceptance remain distinct. Update the owning durable Workbench/Personal-MCP records with the exact capability state and next action; do not rewrite Executive OS lifecycle from chat.

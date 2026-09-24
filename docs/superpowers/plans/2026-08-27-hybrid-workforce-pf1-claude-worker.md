# PF1 Claude Worker Vertical Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove one real subscription-backed Claude Code Worker can execute one bounded Executive child Job through the same provider-neutral Worker Harness/Job/Attempt/Worker/Event lifecycle as Codex, without provider-side orchestration, hidden retries, credential exposure, or general autonomous enablement.

**Architecture:** PF1 implements a `claude-code` `WorkerExecutionAdapter` over the already-frozen foreground non-interactive Claude Code surface. The adapter is configured with an exact absolute binary and dedicated worker OS principal; authentication remains in that principal's macOS Keychain and is never read by Mastermind. The adapter compiles an existing Executive capability grant into a fail-closed Claude invocation, runs one foreground process, parses bounded structured output, and returns the common HF1 receipts. Provider Control remains capacity/auth-readiness owner; Executive OS remains lifecycle owner. The first proof uses no resumable provider session and no provider-native background/multiagent system.

**Tech Stack:** Python 3.11+, asyncio subprocess, Claude Code CLI, macOS Keychain owned by Claude itself, existing Executive Runtime/Worker Harness, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`

**Provider source law:** `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`

## Global Constraints

- Execute only after RF1 and HF1 are accepted; the plan may be staged earlier.
- Refresh protected Skillpack, current accepted Claude source law, current HF1 interfaces, Macro Provider Control and open provider PRs before first write.
- First V1 backend is foreground `claude -p`; no Claude background agents, `claude agents` dispatcher, cloud sessions, Remote Control, Managed Agents, provider-native multiagent, provider retries, or scheduled deployments.
- Preferred auth is the dedicated worker OS principal's native Claude subscription login/Keychain. Do not read/copy/export credentials and do not create environment-token shortcuts.
- No `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `setup-token`, token-in-argv, token-in-env, temp credential file, Slack credential transport, or model-visible Keychain inspection.
- Exact model selection; no provider fallback chain or silent automatic model switching.
- `--safe-mode`, no Chrome/browser capability, no session persistence, bounded turn count, explicit tool allow/deny and fail-closed permissions for the first proof.
- Browser/devserver/computer-use remains governed by the separate resource fabric.
- Production provider routing remains disabled until real host proof is accepted.

---

### Task 1: Freeze the Claude adapter contract and command compiler

**Files:**
- Create: `control_plane/claude_worker.py`
- Modify: `control_plane/worker_adapter.py`
- Create: `tests/test_executive_claude_worker.py`

**Interfaces:**
- Adapter id: `claude-code`.
- `ClaudeCodeWorkerAdapter` implements the accepted HF1 `WorkerExecutionAdapter` protocol.
- `ClaudeAuthObservation` contains only allowlisted non-secret readiness facts.
- Provider-private configuration belongs to adapter construction, never `WorkerLaunchSpec`.

- [ ] **Step 1: Write RED-first adapter descriptor tests**

Add tests asserting:

```python
assert adapter_descriptor("claude-code").implemented is False
```

before implementation and a separate final task will flip the descriptor only after the complete adapter/tests exist. Unknown `claude-*` aliases remain refused.

- [ ] **Step 2: Write command-compiler tests**

Construct a `WorkerLaunchSpec` with read-only and write/test grants and assert the rendered invocation contains the semantic equivalent of:

```text
absolute claude binary
-p
--output-format json
--safe-mode
--no-chrome
--no-session-persistence
--max-turns <bounded integer>
--model <exact configured model id>
fail-closed permission mode
explicit tool allow-set derived from the accepted execution profile
explicit MCP/customization denial unless separately granted
```

Assert the invocation and environment do **not** contain any secret variable names/values or arbitrary ambient environment inheritance.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/test_executive_claude_worker.py -q
```

- [ ] **Step 4: Implement the adapter skeleton and exact binary configuration**

`ClaudeCodeWorkerAdapter` constructor must take:

```python
ClaudeCodeWorkerAdapter(
    claude_binary: Path,
    *,
    allowed_versions: frozenset[str],
    exact_model: str,
    max_turns: int,
)
```

Resolve/attest the absolute binary using provider-appropriate path/stat/version checks. Do not assume the OpenAI code-signing team identifier. Provider binary identity is recorded as non-secret evidence under the common binary-attestation contract.

- [ ] **Step 5: Implement grant-to-command compilation**

Map only the existing requested execution profile/capabilities into Claude flags. Missing capability mapping is a hard refusal; do not broaden tools because Claude supports them. Explicitly deny browser/Chrome and MCP unless the profile grants a separately accepted capability.

- [ ] **Step 6: Run GREEN command/compiler tests**

```bash
python -m pytest tests/test_executive_claude_worker.py -q
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/claude_worker.py control_plane/worker_adapter.py tests/test_executive_claude_worker.py
git commit -m "feat(exec): add bounded Claude worker adapter"
```

---

### Task 2: Add non-secret host/auth readiness and provider-result parsing

**Files:**
- Modify: `control_plane/claude_worker.py`
- Modify: `tests/test_executive_claude_worker.py`

**Interfaces:**
- `observe_auth_status() -> ClaudeAuthObservation` executes only the provider-documented auth-status command and parses a closed allowlist.
- `start()/collect_result()` use the common HF1 process/result contract.

- [ ] **Step 1: Write auth-status hostile tests**

Synthetic auth output fixtures must cover:

```text
authenticated -> non-secret ready observation
unauthenticated exit -> typed unavailable
malformed JSON -> unknown/refusal
extra credential/token-shaped fields -> reject rather than serialize
unexpected plan/account fields -> ignore or reject unless explicitly allowlisted by the frozen host contract
```

No test fixture may contain a real token; use obvious fake sentinel strings and assert redaction/refusal.

- [ ] **Step 2: Implement auth observation**

Invoke the installed provider's documented JSON auth status path with a bounded timeout. Persist/return only fields explicitly proven non-secret on the installed version, plus command exit status/version/time. Authentication success is readiness evidence, not Executive Worker claim or provider-capacity truth.

- [ ] **Step 3: Write structured-result tests**

Use synthetic JSON/stdout files to prove one accepted structured result, provider refusal, malformed output, model mismatch, timeout, cancellation, and secret-shaped output. The adapter must never turn parse failure/provider refusal into `SUCCEEDED`.

- [ ] **Step 4: Implement foreground start/collect**

Run one new POSIX process group/session under the dedicated worker principal and the common HF1 process identity contract. Environment is constructed from an allowlist/empty base; do not inherit Chairman/provider token variables. Bound stdout/stderr/result sizes. Store only hash/size/safe structured evidence in receipts.

- [ ] **Step 5: Implement cancellation/reconciliation parity**

Use the same identity-safe process-group termination semantics consumed by the common supervisor. A missing/ambiguous process after restart cannot become success. Provider CLI exit or timeout does not authorize a new provider Attempt.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest \
  tests/test_executive_claude_worker.py \
  tests/test_worker_execution_contract.py \
  tests/test_executive_operator_supervisor.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/claude_worker.py tests/test_executive_claude_worker.py
git commit -m "feat(exec): validate Claude auth and structured results"
```

---

### Task 3: Bind Claude through the same broker/supervisor lifecycle

**Files:**
- Modify: `control_plane/worker_adapter.py`
- Modify: `control_plane/executive_worker_broker.py`
- Modify: `tests/test_worker_adapter_broker_contract.py`
- Modify: `tests/test_executive_operator_supervisor.py`
- Modify: `tests/test_executive_claude_worker.py`

**Interfaces:**
- The reviewed broker service is configured with `adapter_id="claude-code"` and one `ClaudeCodeWorkerAdapter` instance.
- No request payload can switch the broker to another adapter/provider.

- [ ] **Step 1: Add broker lifecycle test**

Run a fixture Claude adapter through exact `start -> status -> collect` and `start -> cancel` broker paths and assert response schema/operation identities are the same common broker family used by Codex.

- [ ] **Step 2: Add Executive Attempt vertical test**

Create one bounded child Job and Claude Worker fixture in the existing Runtime, claim the Job, launch through `ExecutiveSupervisor`, collect, validate and complete the same Attempt/Job. Assert no Claude-specific table/event aggregate/lifecycle exists.

- [ ] **Step 3: Run RED then make only composition changes**

```bash
python -m pytest \
  tests/test_executive_claude_worker.py \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_operator_supervisor.py \
  -q
```

- [ ] **Step 4: Flip the adapter descriptor only after the path exists**

Change:

```python
"claude-code": AdapterDescriptor(adapter_id="claude-code", implemented=True)
```

Do not enable autonomous production routing in `executive_worker_routes.json` in this task.

- [ ] **Step 5: Run Codex + Claude regression matrix**

```bash
python -m pytest \
  tests/test_executive_claude_worker.py \
  tests/test_executive_codex_worker.py \
  tests/test_executive_worker_broker.py \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_operator_supervisor.py \
  -q
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/worker_adapter.py control_plane/executive_worker_broker.py tests/test_worker_adapter_broker_contract.py tests/test_executive_operator_supervisor.py tests/test_executive_claude_worker.py
git commit -m "feat(exec): compose Claude through common worker lifecycle"
```

---

### Task 4: Host preflight and native login gate

**Files:**
- Create: `ops/executive_os/claude-worker-preflight.py`
- Create: `tests/test_claude_worker_preflight.py`

**Interfaces:**
- Read-only preflight emits `mastermind.claude_worker_preflight/v1` with allowlisted non-secret metadata.
- It does not perform login and never owns credentials.

- [ ] **Step 1: Write preflight tests**

Pin receipt fields to:

```text
schema, observed_at, binary_path_digest, binary_version,
worker_uid, auth_ready, requested_model, safe_mode_supported,
no_chrome_supported, no_session_persistence_supported,
structured_output_supported, result
```

Do not include username, email, token/keychain label, home path, private host name, or raw CLI output.

- [ ] **Step 2: Implement read-only probes**

Probe exact binary/version/help capability and non-secret `auth status`. Missing capability/auth is a typed blocker. Do not run login, modify config, read Keychain, or infer subscription plan from binary presence.

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/test_claude_worker_preflight.py -q
```

- [ ] **Step 4: Commit**

```bash
git add ops/executive_os/claude-worker-preflight.py tests/test_claude_worker_preflight.py
git commit -m "feat(exec): add secret-free Claude worker preflight"
```

- [ ] **Step 5: Run preflight on the intended worker host**

If `auth_ready=false`, STOP at `CLAUDE_NATIVE_LOGIN_REQUIRED`. Chairman/admin performs the provider-native login under the dedicated worker OS principal; the model does not observe password/device/SSO/OTP/token material. Rerun only the read-only preflight after the ceremony.

---

### Task 5: One real Claude child Job canary

**Files:**
- No code changes during the canary unless the canary exposes a reproducible adapter defect; repair stays on the same PF1 carrier and reruns the full gates.
- Sanitized evidence may be written under the repository's existing `review_evidence/` convention.

- [ ] **Step 1: Re-pin and prove provider capacity eligibility**

Read current Macro `mastermind.provider_capacity.v1` / Provider Control evidence through the accepted CF2 acquisition seam. The intended Claude slot must be present/enabled/healthy enough under current policy; unknown quota remains unknown and does not become unlimited.

- [ ] **Step 2: Create one bounded real child Job**

Use a low-risk, independently verifiable implementation/research task whose authority is a strict subset of the parent program. Require an exact worktree/base SHA, explicit capability profile, result schema and validation. Do not use the Chairman's live project state as a test target.

- [ ] **Step 3: Claim exactly one Claude Worker and run once**

The real path must prove:

```text
Executive child Job
→ one Attempt
→ one Claude Worker claim
→ common broker/supervisor
→ foreground Claude Code invocation
→ structured result
→ existing validation/review path
→ terminal result
```

No provider-side retry/fallback/multiagent. If process/result effect is ambiguous, remain uncertain and reconcile the same Attempt.

- [ ] **Step 4: Independent review**

Use a different Worker/provider realm where current independence law requires it. Review must inspect the actual PR/result evidence, not merely the Claude receipt.

- [ ] **Step 5: Capture sanitized production proof**

Receipt must include only safe identities: Job/Attempt/Worker ids, adapter id, binary version/digest, requested/served model if safely exposed, auth-ready boolean, result/validation hashes, timestamps, and terminal Executive states. No credential/account PII/raw provider home.

- [ ] **Step 6: Hosted code gates**

```bash
python -m pytest \
  tests/test_executive_claude_worker.py \
  tests/test_claude_worker_preflight.py \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_codex_worker.py \
  tests/test_executive_worker_broker.py \
  tests/test_executive_operator_supervisor.py \
  -q
python -m compileall -q control_plane ops/executive_os

git diff --check
```

Require exact-head CI/CodeQL after any repair.

- [ ] **Step 7: Return to Sol**

Return exact head/base, host-preflight receipt, native-login gate outcome, real Job/Attempt/Worker identifiers, provider/adapter evidence, real result/validation/review proof, hosted gates, collisions, and explicit `GENERAL CLAUDE AUTONOMOUS ROUTING STILL DISARMED`.

## Stop Condition

PF1 stops after one real Claude Executive child Job is accepted through the common lifecycle with secret-safe host/auth proof and independent review. It does not generally enable Claude routing, provider-native background agents, Fable session wake, or cheaper-provider expansion.

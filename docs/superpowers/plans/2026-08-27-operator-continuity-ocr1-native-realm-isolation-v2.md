# OCR-1 V2 — Native Claude Realm Isolation Falsifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, without exposing provider account PII or credentials or executing a model turn, which accepted host/OS-principal combinations can serve as distinct native subscription-backed Claude execution realms and whether the current machine topology can support the intended five-subscription pool under existing Claude V1 provider law.

**Architecture:** OCR-1 observes realm readiness only. It does not mint host/principal identity, execute provider work, or normalize capacity. The preflight consumes already-approved opaque host/principal references from Capacity Fabric / Executive worker-principal ownership, executes only exact read-only Claude metadata/auth commands inside the candidate execution context, and returns a closed secret-free receipt. A storeless verifier compares accepted realm receipts. Native login/provisioning remains a Chairman/admin ceremony; PF1 owns the first real Claude model/Worker call; Shared AI Provider Control remains the canonical capacity owner.

**Tech Stack:** Python 3.11+, existing Capacity Fabric host identity, existing Executive worker/principal evidence, Claude Code CLI read-only metadata/auth commands, subprocess, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-preflight-no-model-call-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-identity-owner-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-worker-context-auth-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-native-claude-capacity-identity-amendment.md`
- `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`

**Supersedes:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-claude-realm-isolation.md`. The earlier token-injection plan is historical only and MUST NOT be implemented.

## Global Constraints

- Preferred first V1 auth remains native `claude auth login` under a dedicated Worker OS principal, with provider-owned native credential storage.
- Do not run `claude setup-token`; do not read/inject `CLAUDE_CODE_OAUTH_TOKEN(_N)`; do not use `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`; do not inspect Keychain values.
- `CLAUDE_CONFIG_DIR` is not credential-isolation evidence on macOS.
- OCR-1 may not execute `-p`, `--print`, a prompt, Agent SDK query/connect, session creation, tools, MCP, browser or any equivalent model-work path. PF1 owns first real provider work.
- OCR-1 does not mint `host_ref` or OS-principal identity. It reuses exact approved opaque identities or returns `HOST_IDENTITY_SEAM_UNAVAILABLE` / `PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE`.
- A realm may be `SLOT_BOUND_V1`; provider-reported account identity is optional and must not be fabricated or persisted as PII.
- Native login is a separate Chairman/admin ceremony. The probe reports `LOGIN_REQUIRED` and stops; it never performs login.
- Host/principal/native-login readiness is necessary but not sufficient for routing. PF1/OCR-4 require a fresh `WORKER_CONTEXT_AUTH_READY` receipt from the actual worker service/broker execution-context class before provider work.
- Native auth readiness is not quota truth. OCR-1 does not join `claude-pro-*` to Macro `claude_code_oauth_*`; OCR-2C owns canonical capacity identity.
- No Executive Job/Attempt/Worker, CF2 placement, Wake, Slack, provider retry, long-running probe daemon, new host registry or new capacity store is created by this wave.
- Sanitized evidence never publishes private hostname, raw username/home, provider email/account/organization, credential values, auth files, raw stdout/stderr or secret-shaped material.

---

### Task 1: Add a closed provider-work-free per-principal realm preflight contract

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**
- Create: `ops/executive_os/claude-native-realm-preflight.py`
- Create: `tests/test_claude_native_realm_preflight.py`

**Interfaces:**
- CLI inputs: `--realm-label <opaque-reviewed-label>`, `--host-ref <accepted-opaque-host-ref>`, `--os-principal-ref <accepted-opaque-principal-ref>`.
- The references come from trusted process composition/operator tooling, never model text and never local fallback hashing.
- Output schema: `mastermind.claude_native_realm_preflight.v1`.

- [ ] **Step 1: Write the failing closed-wire tests**

Accepted public receipt shape:

```python
{
    "schema": "mastermind.claude_native_realm_preflight.v1",
    "realm_label": "claude-pro-01",
    "host_ref": "host-<opaque>",
    "os_principal_ref": "principal-<opaque>",
    "observed_at": "2026-08-27T23:30:00Z",
    "claude_binary_sha256": "a" * 64,
    "claude_version": "2.x.y",
    "auth_ready": True,
    "auth_method": "claudeai",
    "auth_identity_confidence": "SLOT_ONLY",
    "macos_credential_isolation_basis": "OS_PRINCIPAL_KEYCHAIN",
    "execution_context": "INTERACTIVE_PRINCIPAL",
    "verdict": "INTERACTIVE_AUTH_READY",
    "reason_codes": [],
}
```

Tests must also require refusal when trusted host/principal references are absent or malformed and reject any public key containing:

```text
email, account_id, organization, token, keychain_item, secret, credential_value,
home_path, username, raw_auth, stdout, stderr
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_native_realm_preflight.py
```

Expected: module/script missing.

- [ ] **Step 3: Bind to existing host/principal identity owners**

Implementation must resolve/reuse the current approved read-only host/principal evidence seam discovered in archaeology. It verifies that the running process context matches the supplied accepted principal identity using the same Executive/broker observation law. It may not derive a competing `host_ref` or principal reference from hostname, machine UUID, UID, username, home path or local hashing.

If an accepted seam is unavailable, emit only the appropriate bounded refusal:

```text
HOST_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_CONTEXT_MISMATCH
```

- [ ] **Step 4: Implement exact provider-work-free Claude observation**

Resolve the reviewed Claude executable path; require an absolute regular executable; hash its bytes; execute only an allowlisted installed-version set whose V1 minimum is:

```text
claude --version
claude auth status
```

Bound every subprocess by a fixed timeout. `auth status` parsing is allowlist-only: retain only the login/readiness boolean and a documented low-cardinality auth method when safely available. Discard provider identity/organization fields before constructing the receipt.

The subprocess command builder must refuse `-p`, `--print`, prompt strings, session/resume/fork/respawn, Agent SDK calls and all non-allowlisted argv before process creation.

- [ ] **Step 5: Add zero-provider-work and hostile-output tests**

Tests must prove:

```python
assert "workspace_probe_ok" not in receipt
assert no_model_turn_subprocess_was_invoked
assert all(argv in allowed_read_only_argv for argv in observed_argv)
```

Cover missing binary, malformed auth output, auth refusal, timeout, nonzero exit, provider output containing email/organization/token-shaped strings, caller attempts to pass config/account/credential inputs, and hostile argv containing `-p`, `--print`, `--resume`, `--fork-session`, `respawn` or prompt text. Raw provider prose must never escape into the receipt.

- [ ] **Step 6: Run focused tests and compile**

```bash
pytest -q tests/test_claude_native_realm_preflight.py
python3 -m compileall -q ops/executive_os/claude-native-realm-preflight.py
```

- [ ] **Step 7: Commit**

```bash
git add ops/executive_os/claude-native-realm-preflight.py tests/test_claude_native_realm_preflight.py
git commit -m "feat(exec): add provider-work-free Claude realm preflight"
```

---

### Task 2: Add a storeless realm-set verifier

**Files:**
- Create: `ops/executive_os/claude-realm-set-verify.py`
- Create: `tests/test_claude_realm_set_verify.py`

**Interfaces:**
- Input: 1..7 sanitized `mastermind.claude_native_realm_preflight.v1` receipts supplied explicitly.
- Output schema: `mastermind.claude_realm_set_verification.v1`.
- No credential/account PII, raw host/user identity, config path or provider-capacity capability ID is accepted.

- [ ] **Step 1: Write RED-first set tests**

```python
receipt = verify_realm_set([realm_a, realm_b])
assert receipt["verdict"] == "DISTINCT_NATIVE_REALMS"
assert receipt["realm_count"] == 2
```

Refuse duplicate `realm_label`, duplicate `(host_ref, os_principal_ref)`, stale/malformed receipt, missing auth readiness, non-accepted verdict, or a receipt whose identity confidence is outside the closed vocabulary. Duplicate Claude binary identity is allowed across distinct accepted principals/hosts and is not itself a realm collision.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_realm_set_verify.py
```

- [ ] **Step 3: Implement pure verification**

Public output is exactly:

```text
schema
verified_at
realm_count
realm_labels[]
unique_host_principal_pairs
all_auth_ready
identity_confidence_floor
verdict
reason_codes[]
```

The collector has no filesystem discovery, user switching, Keychain access, process launch, persistence, provider call or network call.

- [ ] **Step 4: Add the five-realm boundary tests**

Prove five distinct realm labels on five distinct accepted host/principal pairs can pass. Prove five labels on one accepted host/principal pair fail. `CLAUDE_CONFIG_DIR` cannot be supplied to the verifier and therefore cannot manufacture distinction.

- [ ] **Step 5: Run focused tests**

```bash
pytest -q tests/test_claude_native_realm_preflight.py tests/test_claude_realm_set_verify.py
```

- [ ] **Step 6: Commit**

```bash
git add ops/executive_os/claude-realm-set-verify.py tests/test_claude_realm_set_verify.py
git commit -m "feat(exec): verify distinct native Claude realms"
```

---

### Task 3: Pin macOS credential-isolation semantics without reading credentials

**Files:**
- Modify: `ops/executive_os/claude-native-realm-preflight.py`
- Modify: `tests/test_claude_native_realm_preflight.py`

**Interfaces:**
- `macos_credential_isolation_basis` is closed to:
  - `OS_PRINCIPAL_KEYCHAIN`
  - `NON_MACOS_PROVIDER_PATH`
  - `UNKNOWN`

- [ ] **Step 1: Write platform behavior tests**

On Darwin, `CLAUDE_CONFIG_DIR` is not accepted as a realm-identity input and changing it cannot change `host_ref`, `os_principal_ref` or create a second credential realm in the receipt model.

- [ ] **Step 2: Implement metadata classification**

Use platform + accepted provider-source-law facts only. Do not inspect Keychain contents or run a second login. This field describes the accepted isolation basis, not credential state.

- [ ] **Step 3: Run tests and commit**

```bash
pytest -q tests/test_claude_native_realm_preflight.py

git add ops/executive_os/claude-native-realm-preflight.py tests/test_claude_native_realm_preflight.py
git commit -m "test(exec): pin Claude realm isolation basis"
```

---

### Task 4: Add the actual-worker-context auth-readiness preflight

**Dependency:** The relevant existing worker broker/service composition for the candidate realm must exist. This task may be implemented only through that existing service/broker boundary; it may not create a Claude auth daemon or alternative worker service.

**Files:**
- Modify only the current provider-neutral worker broker/preflight seam identified by action-time archaeology.
- Test the same seam in its existing test module; do not invent a parallel broker merely to satisfy this plan.

**Interfaces:**
- Input identity: exact already-provisioned Worker/quota realm + accepted host/principal + exact Claude binary/profile.
- Output schema: `mastermind.claude_worker_context_auth.v1`.
- Verdicts:
  - `WORKER_CONTEXT_AUTH_READY`
  - `WORKER_CONTEXT_AUTH_UNAVAILABLE`
  - `EXECUTION_CONTEXT_UNPROVEN`

- [ ] **Step 1: Write RED-first service-context tests**

Prove the preflight executes in the exact Worker execution-context class and accepts only version/auth-status capability. A shell-level `INTERACTIVE_AUTH_READY` receipt must be insufficient for this wire.

- [ ] **Step 2: Implement reviewed non-secret environment composition**

Preserve the existing worker secret-isolation boundary while allowing only current-source-reviewed non-secret identity/runtime variables required by the installed provider, such as exact worker-derived `HOME`, `USER`, `LOGNAME`, `TMPDIR`, a fixed reviewed `PATH`, and required locale values. Model/caller text may not supply them.

Explicitly remove/refuse provider-secret variables:

```text
ANTHROPIC_API_KEY
ANTHROPIC_AUTH_TOKEN
CLAUDE_CODE_OAUTH_TOKEN
```

plus existing Slack/GitHub/Executive secret families.

- [ ] **Step 3: Execute only the same provider-work-free command allowlist**

No `-p`, Agent SDK, session creation or model turn. The service-context receipt binds exact Worker/quota realm, host/principal, Claude binary/version/profile and execution-context identity.

- [ ] **Step 4: Test interactive-ready / worker-unavailable divergence**

A fixture where interactive auth is ready but the actual worker context reports unavailable must return `WORKER_CONTEXT_AUTH_UNAVAILABLE`; it may not fall back to the Chairman shell, copy credentials or switch auth mechanisms.

- [ ] **Step 5: Run the existing broker suite plus focused tests and commit**

Run the exact action-time current broker test suite plus `tests/test_claude_native_realm_preflight.py`; record the resolved filenames in the return packet. Commit only the bounded existing-broker/preflight paths and tests.

---

### Task 5: Real native-login realm census

**Files:**
- No source modification during the census unless a reproducible probe defect is found.
- Sanitized receipts may be preserved under the existing review-evidence convention only after Sol verifies zero account PII/private host identity leakage.

- [ ] **Step 1: Inventory intended topology privately at the admin boundary**

For each intended realm, record only in the human/admin ceremony:

```text
opaque realm label
physical host
accepted Worker OS principal
whether native Claude login has already been completed
```

Do not treat existing Claude Desktop application-support directories under one macOS user as CLI/Worker realms.

- [ ] **Step 2: Require existing accepted host/principal identities**

If the accepted `host_ref` or worker/principal identity seam is unavailable, classify that candidate with `HOST_IDENTITY_SEAM_UNAVAILABLE` / `PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE`. Do not derive replacements locally.

- [ ] **Step 3: Run interactive-principal preflight for each already-provisioned candidate**

The exact candidate principal launches the read-only probe. Do not use model-generated `sudo`, credential copying, Keychain reads or another user's environment. If `LOGIN_REQUIRED`, stop; the Chairman/admin performs native login in that user's session and confirms the intended subscription before the same read-only probe is repeated.

- [ ] **Step 4: Run worker-context auth preflight before calling a realm executable-capable**

Where the accepted worker service/broker exists, require a fresh `WORKER_CONTEXT_AUTH_READY` receipt. If not yet built, retain the realm as `INTERACTIVE_AUTH_READY / EXECUTION_CONTEXT_UNPROVEN`; do not count it as PF1-routable.

- [ ] **Step 5: Verify the realm set**

Run the pure storeless verifier over accepted sanitized receipts. Possible truthful outcomes include:

```text
DISTINCT_NATIVE_REALMS(count=N)
INSUFFICIENT_NATIVE_REALMS(count=N,target=5)
REALM_COLLISION
LOGIN_REQUIRED
HOST_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE
WORKER_CONTEXT_AUTH_UNAVAILABLE
EXECUTION_CONTEXT_UNPROVEN
```

`N < 5` is an exact estate/provisioning fact, not permission to weaken auth isolation.

- [ ] **Step 6: Restart stability proof**

For every realm intended for later production, restart the worker session/process in the supported pattern and require the same accepted host/principal realm identity. Where worker-context preflight exists, require it remains `WORKER_CONTEXT_AUTH_READY`.

- [ ] **Step 7: Return to Sol**

Return exactly:

```text
current protected Skillpack pin + Mastermind carrier base/head
changed files
Claude binary versions/digests
opaque realm labels only
count of distinct accepted host/principal realms
interactive auth readiness by realm
worker-context auth readiness by realm
identity confidence floor
restart stability verdict
admin/provisioning gates still owed
zero model-turn / zero token / zero PII proof
capacity identity status = UNBOUND_TO_PROVIDER_CONTROL | REVIEWED_BOUND
exact current maximum native Claude realm count
```

`capacity identity status` remains `UNBOUND_TO_PROVIDER_CONTROL` until OCR-2C separately proves the realm belongs to a canonical Shared AI Provider Control capacity identity. OCR-1 never invents that join.

## Stop Condition

OCR-1 V2 stops when Sol knows the exact number and topology of distinct native Claude realms and the actual Worker-context auth readiness that current canonical evidence can prove. It does not create missing macOS users, perform native login, modify Macro provider-capacity normalization, implement PF1, route Executive Jobs, add Wake/Slack/OpenClaw, execute a model turn or introduce a token fallback. Five real native identities without OCR-2C capacity identity are not yet a five-realm automatic capacity pool.
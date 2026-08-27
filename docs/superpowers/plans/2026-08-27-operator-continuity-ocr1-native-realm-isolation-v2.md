# OCR-1 V2 — Native Claude Realm Isolation Falsifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, without exposing provider account PII or credentials, which real host/OS-principal combinations can serve as distinct native subscription-backed Claude execution realms and whether the available machine topology can support the intended five-subscription pool under the existing Claude V1 provider secret law.

**Architecture:** A realm is not a config directory or Slack username. It is an opaque account label bound to one exact host + OS principal + provider-native Keychain/login realm. The probe runs inside each candidate worker principal, observes exact Claude binary/version and secret-free `claude auth status`, and returns only slot-bound identity evidence. A separate collector compares host/principal identities, not provider email/account strings. Native login/provisioning is a Chairman/admin ceremony. No token values are read, generated, copied or injected.

**Tech Stack:** Python 3.11+, existing Executive host/principal observation patterns, Claude Code CLI, subprocess, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`
- `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`

**Supersedes:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-claude-realm-isolation.md`. The earlier token-injection plan is historical only and MUST NOT be implemented.

## Global Constraints

- Preferred first V1 auth remains native `claude auth login` under a dedicated worker OS principal, with Claude-owned macOS Keychain storage.
- Do not run `claude setup-token`; do not read/inject `CLAUDE_CODE_OAUTH_TOKEN(_N)`; do not use `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`; do not inspect Keychain values.
- `CLAUDE_CONFIG_DIR` is not credential-isolation evidence on macOS.
- A realm may be `SLOT_BOUND_V1`; provider-reported account identity is optional and must not be fabricated or persisted as PII.
- Native login is a separate Chairman/admin ceremony. The probe only reports `LOGIN_REQUIRED` and stops.
- No Executive Job/Attempt/Worker, CF2 placement, Wake, Slack, provider retry or daemon is created by this wave.
- The probe must run as the candidate OS principal whose native Claude login it is validating; root/sudo impersonation does not prove that user's interactive Keychain can be accessed by the eventual worker service.
- Host and principal references in committed/sanitized proof are opaque/hashes where current source law requires them; never publish a private hostname, user home path or account email.

---

### Task 1: Add a closed per-principal realm preflight contract

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**
- Create: `ops/executive_os/claude-native-realm-preflight.py`
- Create: `tests/test_claude_native_realm_preflight.py`

**Interfaces:**
- CLI input: `--realm-label <opaque-reviewed-label>` only. No caller-supplied credential/account id.
- Output schema: `mastermind.claude_native_realm_preflight.v1`.

- [ ] **Step 1: Write failing closed-wire tests**

Expected public receipt:

```python
{
    "schema": "mastermind.claude_native_realm_preflight.v1",
    "realm_label": "claude-pro-01",
    "host_ref": "host-<opaque>",
    "os_principal_ref": "uid-<opaque>",
    "observed_at": "2026-08-27T23:30:00Z",
    "claude_binary_sha256": "a" * 64,
    "claude_version": "2.x.y",
    "auth_ready": True,
    "auth_method": "claudeai",
    "auth_identity_confidence": "SLOT_ONLY",
    "workspace_probe_ok": True,
    "verdict": "READY_SLOT_BOUND",
    "reason_codes": [],
}
```

Reject any public field named or containing:

```text
email, account_id, organization, token, keychain, secret, credential_value,
home_path, username, raw_auth, stdout, stderr
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_native_realm_preflight.py
```

Expected: module/script missing.

- [ ] **Step 3: Implement opaque host/principal references**

Reuse an existing approved host-ref/OS-principal helper if current archaeology finds one. If no reviewed helper exists, derive only from non-secret machine/UID identity inside the probe using a versioned local projection function and return the digest/reference, never the raw hostname or username.

Do not create a host registry.

- [ ] **Step 4: Implement exact binary observation**

Resolve the configured/system Claude executable using the existing provider-source-law path; require an absolute regular executable, hash its bytes, and execute only:

```text
claude --version
claude auth status
```

with fixed timeouts.

`auth status` parsing is allowlist-only. Normalize only:

```text
logged_in/auth_ready boolean
auth method category when safely documented/observed
```

All provider identity/organization fields are discarded before the receipt exists.

- [ ] **Step 5: Implement harmless local workspace health turn**

Only when `auth_ready=true`, run one bounded read-only/no-tools health turn in a temporary empty owner-only directory using the first-proof safe provider posture. It must not inherit repository customizations or browser/MCP capability and must not mutate a real worktree.

The output is reduced to `workspace_probe_ok` plus a low-cardinality error class. Raw model text is discarded.

- [ ] **Step 6: Add hostile output tests**

Cover malformed auth JSON, provider output containing email/organization/token-shaped strings, missing binary, auth refusal, quota/rate limit, timeout and nonzero exit. No raw provider prose may escape into the public receipt.

- [ ] **Step 7: Run focused tests + compile**

```bash
pytest -q tests/test_claude_native_realm_preflight.py
python3 -m compileall -q ops/executive_os/claude-native-realm-preflight.py
```

- [ ] **Step 8: Commit**

```bash
git add ops/executive_os/claude-native-realm-preflight.py tests/test_claude_native_realm_preflight.py
git commit -m "feat(exec): add native Claude realm preflight"
```

---

### Task 2: Add a storeless realm-set collector

**Files:**
- Create: `ops/executive_os/claude-realm-set-verify.py`
- Create: `tests/test_claude_realm_set_verify.py`

**Interfaces:**
- Input: 1..7 sanitized per-principal preflight receipts supplied explicitly by the operator/test harness.
- Output schema: `mastermind.claude_realm_set_verification.v1`.
- No credential/account identity is accepted as input.

- [ ] **Step 1: Write RED-first set tests**

Positive example:

```python
receipt = verify_realm_set([realm_a, realm_b])
assert receipt["verdict"] == "DISTINCT_NATIVE_REALMS"
assert receipt["realm_count"] == 2
```

Refuse:

- duplicate `realm_label`;
- same `(host_ref, os_principal_ref)` used for two realm labels;
- any member with `auth_ready=false`;
- any member not `READY_SLOT_BOUND`/accepted future stronger identity;
- malformed/stale receipt;
- duplicate Claude binary identity is allowed on different principals/hosts and is not itself realm collision.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_realm_set_verify.py
```

- [ ] **Step 3: Implement pure verification**

Public output:

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

The collector has no filesystem discovery, user switching, Keychain access, process launch, persistence or network call.

- [ ] **Step 4: Add five-realm boundary tests**

Prove five distinct realm labels on five distinct host/principal pairs can pass. Prove five labels on one host + one principal fails even if the caller supplies different `CLAUDE_CONFIG_DIR` strings; config paths are not accepted in the contract.

- [ ] **Step 5: Run tests**

```bash
pytest -q tests/test_claude_native_realm_preflight.py tests/test_claude_realm_set_verify.py
```

- [ ] **Step 6: Commit**

```bash
git add ops/executive_os/claude-realm-set-verify.py tests/test_claude_realm_set_verify.py
git commit -m "feat(exec): verify distinct native Claude realms"
```

---

### Task 3: Prove one current-user config-directory falsifier without touching credentials

**Files:**
- Modify: `ops/executive_os/claude-native-realm-preflight.py`
- Modify: `tests/test_claude_native_realm_preflight.py`

**Interfaces:**
- Adds only a read-only metadata field `macos_credential_isolation_basis` with closed values:
  - `OS_PRINCIPAL_KEYCHAIN`
  - `NON_MACOS_PROVIDER_PATH`
  - `UNKNOWN`

- [ ] **Step 1: Write platform behavior tests**

On Darwin, changing `CLAUDE_CONFIG_DIR` must never change `os_principal_ref` or create a second credential realm in the probe model.

- [ ] **Step 2: Implement metadata classification**

Use platform + current provider-source-law facts only. Do **not** inspect the Keychain or test a second login. The result states the isolation basis, not credential contents.

- [ ] **Step 3: Run tests and commit**

```bash
pytest -q tests/test_claude_native_realm_preflight.py

git add ops/executive_os/claude-native-realm-preflight.py tests/test_claude_native_realm_preflight.py
git commit -m "test(exec): pin Claude realm isolation basis"
```

---

### Task 4: Real native-login realm census

**Files:**
- No source modification during the census unless a reproducible probe defect is found.
- Sanitized receipts may be preserved under the existing review-evidence convention only after Sol verifies they contain no account PII/private host identifiers.

- [ ] **Step 1: Inventory intended realm topology without logging credentials**

For each intended realm, record privately/operator-side:

```text
opaque realm label
physical host
OS principal that will own Claude Code
whether native Claude login has already been completed
```

Do not treat the five existing Claude desktop application-support directories under one macOS user as five CLI realms.

- [ ] **Step 2: Run preflight as each already-provisioned principal**

The exact candidate principal launches the probe itself. Do not use model-generated `sudo`, credential copying, `security` Keychain reads or another user's environment.

If the receipt says `LOGIN_REQUIRED`, STOP that realm. The Chairman/admin performs native `claude auth login` in that user's session and confirms the intended subscription. Then rerun the same read-only probe.

- [ ] **Step 3: Collect only sanitized receipts**

Run the storeless realm-set verifier over the accepted receipts.

- [ ] **Step 4: Require truthful capacity result**

Possible outcomes:

```text
DISTINCT_NATIVE_REALMS(count=N)
INSUFFICIENT_NATIVE_REALMS(count=N,target=5)
REALM_COLLISION
LOGIN_REQUIRED
HOST_PRINCIPAL_UNAVAILABLE
```

`N < 5` is not a failed implementation; it is the exact current estate truth and a provisioning gate for the eventual five-account pool.

- [ ] **Step 5: Restart/relogin stability proof**

For every realm intended for production, restart the worker session/process (not the machine unless operationally safe), rerun the preflight as the same principal and require the same opaque host/principal realm identity and `auth_ready=true`.

- [ ] **Step 6: Return to Sol**

Return:

```text
Mastermind base/head
changed files
Claude binary versions/digests
opaque realm labels only
count of distinct host/principal realms
per-realm auth-ready boolean
identity confidence floor (SLOT_ONLY or stronger)
restart stability verdict
admin gates still owed
zero-token/zero-PII proof
exact current maximum native Claude realm count
```

## Stop Condition

OCR-1 V2 stops when Sol knows the exact number and topology of distinct native Claude realms that can be safely addressed under current source law. It does not create missing macOS users, perform native login, change Macro provider slots, implement PF1, route Executive Jobs, add Wake/Slack/OpenClaw, or introduce a token-based fallback. If fewer than five realms exist, the next action is an explicit host/OS-principal provisioning decision, not a hidden auth downgrade.

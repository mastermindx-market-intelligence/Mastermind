# OCR-1 V3 — Canonical Claude Realm Isolation & Worker Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the one canonical provider-work-free Claude Worker preflight and a pure realm-set verifier so Mastermind can truthfully determine which native Claude subscription realms exist, which exact worker execution contexts are auth-ready, and which identity/provisioning gates remain before PF1—without a model turn, credential/PII exposure, duplicate provider preflight, capacity normalization or worker routing.

**Architecture:** OCR-1 advances the pre-existing PF1-reserved `ops/executive_os/claude-worker-preflight.py` seam; it does **not** create `claude-native-realm-preflight.py`. The preflight has one closed `mastermind.claude_worker_preflight.v1` wire with `execution_context=INTERACTIVE_PRINCIPAL|WORKER_BROKER`. It consumes already-approved opaque host/principal identity, proves the exact Claude binary and selected auth source using only `claude --version` and `claude auth status`, and fails closed when current Mastermind cannot supply a concrete host/principal seam. A separate storeless verifier compares sanitized receipts. Native login remains a Chairman/admin ceremony, Shared AI Provider Control remains capacity owner, OCR-2C owns native-realm capacity identity, and PF1 remains the first real Claude model/Worker call.

**Tech Stack:** Python 3.11+, current Mastermind Executive/broker identity seams, Claude Code CLI read-only metadata/auth commands, subprocess, canonical JSON/SHA-256, pytest.

**Specs / current owner law:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-preflight-owner-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-preflight-no-model-call-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-identity-owner-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-worker-context-auth-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-native-claude-capacity-identity-amendment.md`
- `docs/superpowers/plans/2026-08-27-hybrid-workforce-pf1-claude-worker.md`
- `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`

**Supersedes before implementation:**
- `docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-claude-realm-isolation.md`
- `docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-native-realm-isolation-v2.md`

Both remain historical design evidence only. Do not commission their token path, second preflight path/schema, or any provider-work step.

## Global Constraints

- Canonical executable: `ops/executive_os/claude-worker-preflight.py`.
- Canonical focused test: `tests/test_claude_worker_preflight.py`.
- Canonical schema: `mastermind.claude_worker_preflight.v1`.
- Realm-set verifier: `ops/executive_os/claude-realm-set-verify.py` + `tests/test_claude_realm_set_verify.py`.
- Preferred V1 auth is native `claude auth login` under a dedicated Worker OS principal with Claude-owned native credential storage. The probe never performs login.
- Do not run `claude setup-token`; do not read/inject `CLAUDE_CODE_OAUTH_TOKEN(_N)`; do not use `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`; do not inspect Keychain values.
- `CLAUDE_CONFIG_DIR` is not credential-isolation evidence on macOS.
- The actual production worker environment must not silently select a higher-precedence Claude auth source. Current-source validation must cover gateway/cloud-provider modes, auth token/API key, `apiKeyHelper`, setup-token OAuth, profile/federation and equivalent configured sources. A preflight cannot pass by sanitizing differently from the later worker process.
- OCR-1 may execute only the installed-version allowlist whose V1 floor is `claude --version` and `claude auth status`. No `-p`, `--print`, prompt, session/resume/fork/respawn, Agent SDK query/connect, tool, MCP, browser or model inference call. PF1 owns first real provider work.
- `claude auth status` output is untrusted provider metadata. Retain only allowlisted readiness/auth-source facts required to establish the selected native subscription path; discard email, organization/account IDs, raw provider prose and other PII before constructing a receipt.
- OCR-1 does not mint `host_ref` or OS-principal identity. It consumes exact accepted opaque identity from existing owners or returns `HOST_IDENTITY_SEAM_UNAVAILABLE` / `PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE` / `PRINCIPAL_CONTEXT_MISMATCH`.
- Current estate archaeology has observed Macro Provider Capacity `host_ref=local-unbound` and no general concrete `host_ref` in Mastermind `control_plane/`. That is a likely real OCR-1 host gate, not permission to hash hostname/machine UUID locally.
- `INTERACTIVE_AUTH_READY` is provisioning evidence only. PF1/OCR-4 require fresh `WORKER_CONTEXT_AUTH_READY` from the exact worker service/broker execution-context class.
- Native auth readiness is not quota/capacity truth. OCR-1 never joins `claude-pro-*` to Macro `claude_code_oauth_*`; OCR-2C owns canonical capacity identity.
- No Executive Job/Attempt/Worker, CF2 placement, Wake, Slack, provider retry, long-lived probe daemon, host registry, readiness database or capacity store is created by this wave.
- Sanitized evidence never publishes private hostname, raw username/home, provider email/account/organization, credential values, auth files, raw stdout/stderr or secret-shaped material.

---

### Task 1: Implement the closed canonical preflight contract and command allowlist

**Files:**
- Create: `ops/executive_os/claude-worker-preflight.py`
- Create: `tests/test_claude_worker_preflight.py`

**Interfaces:**

CLI inputs are trusted operator/composition identity only:

```text
--realm-label <opaque-reviewed-label>
--host-ref <accepted-opaque-host-ref>
--os-principal-ref <accepted-opaque-principal-ref>
--execution-context INTERACTIVE_PRINCIPAL|WORKER_BROKER
--worker-id <required only for WORKER_BROKER>
--quota-class <required only for WORKER_BROKER>
--claude-binary <absolute reviewed path or trusted composition default>
```

The caller may not supply credential source, provider account, raw username/home, model, auth token/key or arbitrary subprocess argv.

Closed public receipt:

```python
{
    "schema": "mastermind.claude_worker_preflight.v1",
    "realm_label": "claude-pro-01",
    "host_ref": "host-<opaque>",
    "os_principal_ref": "principal-<opaque>",
    "observed_at": "2026-08-27T23:30:00Z",
    "claude_binary_sha256": "a" * 64,
    "claude_version": "2.x.y",
    "auth_ready": True,
    "auth_method": "claudeai",
    "api_provider": "first_party",
    "auth_identity_confidence": "SLOT_ONLY",
    "macos_credential_isolation_basis": "OS_PRINCIPAL_KEYCHAIN",
    "execution_context": "INTERACTIVE_PRINCIPAL",
    "worker_id": None,
    "quota_class": None,
    "verdict": "INTERACTIVE_AUTH_READY",
    "reason_codes": [],
}
```

Exact provider field names/values are installed-version evidence. The public normalized vocabulary is low-cardinality and closed; do not expose raw provider values beyond reviewed non-secret categories.

- [ ] **Step 1: Write the failing closed-wire tests**

Pin exact key set, schema, UTC timestamp, bounded identity formats, lowercase SHA-256 binary digest, execution-context cross-field rules, closed verdict/reason vocabulary and secret-shaped leaf rejection.

`INTERACTIVE_PRINCIPAL` requires `worker_id=None`, `quota_class=None`. `WORKER_BROKER` requires exact nonempty Worker/quota identity.

Reject any public key/value shaped like:

```text
email, account_id, organization, token, keychain_item, secret, credential_value,
home_path, username, raw_auth, stdout, stderr
```

- [ ] **Step 2: Write RED-first command-allowlist tests**

Only these semantic command forms are permitted:

```text
<absolute claude> --version
<absolute claude> auth status
```

Reject before process creation any attempted `-p`, `--print`, prompt, `--resume`, `--continue`, `--fork-session`, `agents`, `respawn`, `daemon`, Agent SDK path, MCP/tool/browser flag, caller-selected environment credential or arbitrary extra argv.

- [ ] **Step 3: Run RED and observe the intended failures**

```bash
pytest -q tests/test_claude_worker_preflight.py
```

Expected: module/script missing. Record the RED receipt in the implementation return.

- [ ] **Step 4: Implement strict canonical/CLI validation only**

Before adding subprocess execution, implement the receipt/value validators, argv builder and bounded error/verdict types. Run the focused tests until only subprocess-observation tests remain red.

- [ ] **Step 5: Implement exact binary observation**

Require an absolute regular executable, no symlink/path escape according to the current provider-binary policy, bounded file hashing and `--version` timeout. Do not assume OpenAI code-signing identity for Claude.

- [ ] **Step 6: Implement `auth status` observation and selected-auth normalization**

Invoke only `claude auth status` with a bounded timeout. Parse strict JSON according to the action-time installed Claude version. Normalize only:

```text
logged-in boolean
selected auth method category
selected provider category when safely exposed
```

For the first V1 realm, `auth_ready=True` only when selected method/provider establishes the intended native claude.ai subscription path. A logged-in result via API key/token/cloud/gateway/profile/federation is a typed refusal, not native subscription readiness. Unknown/new provider fields fail closed.

Discard provider account PII before any receipt object is built.

- [ ] **Step 7: Add hostile-output/auth-precedence tests**

Cover:

```text
missing binary
malformed JSON
loggedIn=false
unknown authMethod/apiProvider
API-key/token/cloud/gateway/profile-selected auth
provider output containing email/org/account/token-shaped fields
nonzero exit
timeout
raw stderr/stdout containing secrets or PII
```

Prove no raw provider prose survives into the public receipt.

- [ ] **Step 8: Run focused tests/compile and commit**

```bash
pytest -q tests/test_claude_worker_preflight.py
python3 -m compileall -q ops/executive_os/claude-worker-preflight.py

git add ops/executive_os/claude-worker-preflight.py tests/test_claude_worker_preflight.py
git commit -m "feat(exec): add canonical Claude worker preflight"
```

---

### Task 2: Bind the preflight to accepted host/principal ownership and honest refusal

**Files:**
- Modify: `ops/executive_os/claude-worker-preflight.py`
- Modify: `tests/test_claude_worker_preflight.py`

**Interfaces:**
- Trusted identity resolver/validator reuses the current accepted host/principal evidence seam discovered at action time.
- It never derives competing opaque IDs from hostname, UID, username, home path or machine UUID.

- [ ] **Step 1: Write RED-first identity-owner tests**

Fixtures must prove:

```text
accepted host/principal refs + matching current execution context -> continue
missing concrete host owner -> HOST_IDENTITY_SEAM_UNAVAILABLE
missing principal owner -> PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE
principal mismatch -> PRINCIPAL_CONTEXT_MISMATCH
host_ref local-unbound/unknown when concrete identity is required -> refusal
```

- [ ] **Step 2: Reconcile current owner seams before implementation**

Read current protected Capacity Fabric host identity and Executive worker/principal source law. If no accepted concrete host identity exists, implement the bounded refusal path only; do not invent one inside OCR-1.

- [ ] **Step 3: Implement current-context comparison**

Use only already-owned observations required to establish the executing principal matches the supplied trusted opaque identity. Private username/UID/home may be inspected locally by the trusted helper when current owner law requires it, but public receipt retains only the opaque accepted reference.

- [ ] **Step 4: Pin macOS credential-isolation basis**

On Darwin, accepted native V1 credential isolation basis is `OS_PRINCIPAL_KEYCHAIN` only when the exact accepted principal/host seam is available. `CLAUDE_CONFIG_DIR` cannot change realm identity. Do not inspect Keychain contents.

- [ ] **Step 5: Run focused tests and commit**

```bash
pytest -q tests/test_claude_worker_preflight.py

git add ops/executive_os/claude-worker-preflight.py tests/test_claude_worker_preflight.py
git commit -m "feat(exec): bind Claude preflight to canonical principal"
```

---

### Task 3: Implement actual Worker-broker execution-context auth readiness through the same preflight

**Dependency:** The relevant existing worker broker/service composition for the candidate realm exists. This task may extend only that current broker/preflight seam; no Claude auth daemon or second worker service.

**Files:**
- Modify: `ops/executive_os/claude-worker-preflight.py`
- Modify: `control_plane/executive_worker_broker.py` only if the current broker lacks a bounded preflight operation required to execute the same helper in the worker principal context.
- Modify: the current worker-broker wire/CLI test modules identified by action-time archaeology only as necessary.
- Modify: `tests/test_claude_worker_preflight.py`

**Interfaces:**
- `WORKER_BROKER` receipt binds exact Worker/quota realm, accepted host/principal, Claude binary/version and selected native auth source.
- Verdicts include `WORKER_CONTEXT_AUTH_READY`, `WORKER_CONTEXT_AUTH_UNAVAILABLE`, `EXECUTION_CONTEXT_UNPROVEN`.

- [ ] **Step 1: Write RED-first worker-context tests**

Prove the preflight executes in the exact dedicated Worker service context. A shell-level `INTERACTIVE_AUTH_READY` receipt must be insufficient for this wire.

- [ ] **Step 2: Pin the real worker environment-composition law**

The Worker preflight and later PF1 Claude process must share the same reviewed non-secret environment composition. Allow only identity/runtime variables actually required by the installed provider, such as worker-derived `HOME`, `USER`, `LOGNAME`, `TMPDIR`, fixed reviewed `PATH`, locale values and other action-time reviewed non-secret settings.

Explicitly refuse/strip higher-precedence credential/provider switches from the actual Worker realm according to current source law, including at minimum:

```text
CLAUDE_CODE_USE_BEDROCK
CLAUDE_CODE_USE_VERTEX
CLAUDE_CODE_USE_FOUNDRY
ANTHROPIC_AUTH_TOKEN
ANTHROPIC_API_KEY
CLAUDE_CODE_OAUTH_TOKEN
ANTHROPIC_PROFILE
ANTHROPIC_FEDERATION_RULE_ID
ANTHROPIC_ORGANIZATION_ID
```

Also reconcile configured `apiKeyHelper`, gateway/profile/provider settings. Do not merely clear them for the preflight while retaining them for PF1 runtime.

- [ ] **Step 3: Add the smallest provider-work-free broker operation only if missing**

If current broker has no lawful way to run the exact allowlisted preflight in its dedicated OS principal context, extend the existing broker wire with one closed preflight operation. It accepts no arbitrary argv, shell, env, provider/account selector or credential input. It returns only the canonical sanitized receipt/typed refusal.

- [ ] **Step 4: Prove interactive-ready / worker-unavailable divergence**

Fixture: interactive principal returns native subscription readiness but actual Worker environment has wrong/missing native auth or a higher-precedence credential source. Required result: `WORKER_CONTEXT_AUTH_UNAVAILABLE`; no fallback to Chairman shell, copied credentials, token path or another provider.

- [ ] **Step 5: Prove worker-ready selected-auth identity**

A positive Worker receipt requires the actual broker context itself to report native selected auth with all exact host/principal/Worker/quota identity gates satisfied.

- [ ] **Step 6: Run focused + broker security regression and commit**

Resolve the exact current broker test filenames at action time, then require at minimum:

```bash
pytest -q tests/test_claude_worker_preflight.py tests/test_executive_operator_broker.py tests/test_worker_adapter_broker_contract.py
```

If a listed historical filename has moved, use the current exact equivalent and record it in the return packet rather than inventing another test module.

Commit only the canonical preflight + minimum existing broker/wire/test paths.

---

### Task 4: Add a pure storeless realm-set verifier

**Files:**
- Create: `ops/executive_os/claude-realm-set-verify.py`
- Create: `tests/test_claude_realm_set_verify.py`

**Interfaces:**
- Input: 1..7 sanitized `mastermind.claude_worker_preflight.v1` receipts supplied explicitly.
- Output schema: `mastermind.claude_realm_set_verification.v1`.
- No credential/account PII, raw host/user identity, config path or provider-capacity capability ID is accepted.

- [ ] **Step 1: Write RED-first set tests**

```python
receipt = verify_realm_set([realm_a, realm_b])
assert receipt["verdict"] == "DISTINCT_NATIVE_REALMS"
assert receipt["realm_count"] == 2
```

Refuse duplicate `realm_label`, duplicate `(host_ref, os_principal_ref)`, stale/malformed receipt, non-native selected auth, unaccepted verdict or invalid identity confidence.

Count a realm as PF1-executable only when its current receipt has `execution_context=WORKER_BROKER` and `verdict=WORKER_CONTEXT_AUTH_READY`. Interactive-only readiness may be reported separately as provisioning evidence but never counted as executable capacity.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_realm_set_verify.py
```

- [ ] **Step 3: Implement pure verification**

Public output is exactly:

```text
schema
verified_at
observed_realm_count
worker_ready_realm_count
realm_labels[]
worker_ready_realm_labels[]
unique_host_principal_pairs
identity_confidence_floor
verdict
reason_codes[]
```

The verifier has no filesystem discovery, user switching, Keychain access, process launch, persistence, provider call or network call.

- [ ] **Step 4: Add five-realm and degraded-boundary tests**

Prove five distinct current Worker-broker receipts on five distinct accepted host/principal pairs can pass. Prove five labels on one pair fail. Prove five interactive-only receipts return `EXECUTION_CONTEXT_UNPROVEN`/insufficient worker-ready realms. `CLAUDE_CONFIG_DIR` cannot manufacture distinction.

- [ ] **Step 5: Run focused tests/compile and commit**

```bash
pytest -q tests/test_claude_worker_preflight.py tests/test_claude_realm_set_verify.py
python3 -m compileall -q ops/executive_os/claude-worker-preflight.py ops/executive_os/claude-realm-set-verify.py

git add ops/executive_os/claude-realm-set-verify.py tests/test_claude_realm_set_verify.py
git commit -m "feat(exec): verify distinct Claude worker realms"
```

---

### Task 5: Real native-login realm census and restart-stability proof

**Files:**
- No source modification during the census unless a reproducible preflight defect is found.
- Sanitized receipts may be preserved under the existing review-evidence convention only after Sol verifies zero account PII/private host identity leakage.

- [ ] **Step 1: Inventory intended topology privately at the admin boundary**

For each intended realm, the human/admin ceremony records privately:

```text
opaque realm label
physical host
accepted Worker OS principal
whether native Claude login has already been completed
```

Do not treat current Claude Desktop application-support directories under one macOS user as CLI/Worker realms.

- [ ] **Step 2: Require existing accepted host/principal identities**

If accepted concrete `host_ref` or Worker/principal identity is unavailable, return the exact identity-seam refusal. Do not derive replacements locally.

- [ ] **Step 3: Run interactive-principal preflight for already-provisioned candidates**

The exact candidate principal runs the canonical provider-work-free preflight. If `LOGIN_REQUIRED`, stop; Chairman/admin performs native `claude auth login` in that user's session and confirms the intended subscription. The model never observes password/device/SSO/OTP/token material.

- [ ] **Step 4: Run Worker-broker preflight before calling a realm executable-capable**

Require fresh `WORKER_CONTEXT_AUTH_READY`. Interactive-only realms remain `EXECUTION_CONTEXT_UNPROVEN`; do not call them PF1-routable.

- [ ] **Step 5: Verify the realm set**

Run the pure verifier over sanitized receipts. Possible truthful outcomes include:

```text
DISTINCT_NATIVE_REALMS(count=N)
INSUFFICIENT_NATIVE_REALMS(count=N,target=5)
REALM_COLLISION
LOGIN_REQUIRED
HOST_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_CONTEXT_MISMATCH
NATIVE_AUTH_NOT_SELECTED
WORKER_CONTEXT_AUTH_UNAVAILABLE
EXECUTION_CONTEXT_UNPROVEN
```

`N < 5` is an estate/provisioning fact, not permission to weaken auth isolation.

- [ ] **Step 6: Restart stability proof**

For every realm intended for later production, restart the supported worker session/process and require the same accepted host/principal realm identity plus fresh `WORKER_CONTEXT_AUTH_READY`. A restart that changes selected auth source or realm identity fails closed.

- [ ] **Step 7: Return exact evidence to Sol**

Return:

```text
current protected Skillpack + carrier base/head
changed files
Claude binary versions/digests
opaque realm labels only
count of distinct accepted host/principal realms
interactive auth readiness by realm
worker-context auth readiness by realm
selected native-auth proof by realm
identity confidence floor
restart stability verdict
admin/provisioning gates still owed
zero model-turn / zero token / zero PII proof
capacity identity status = UNBOUND_TO_PROVIDER_CONTROL | REVIEWED_BOUND
exact current maximum native Claude Worker realm count
```

`capacity identity status` remains `UNBOUND_TO_PROVIDER_CONTROL` until OCR-2C separately proves the realm belongs to canonical Shared AI Provider Control capacity identity.

## Stop Condition

OCR-1 V3 stops when the canonical single preflight exists test-first, no second Claude preflight exists, Sol knows the exact native realm/Worker-context readiness current evidence can prove, selected auth is demonstrably the intended native subscription path, and any missing host/principal/provisioning seam is returned truthfully. It does not create missing macOS users, perform login, modify Macro provider-capacity normalization, implement PF1, route Executive Jobs, add Wake/Slack/OpenClaw, execute a model turn or introduce a token fallback. Five worker-ready identities without OCR-2C capacity identity are still not a five-realm automatic capacity pool.
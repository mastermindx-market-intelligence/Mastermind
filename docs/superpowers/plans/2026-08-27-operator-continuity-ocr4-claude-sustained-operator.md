# OCR-4 Sustained Claude Operator Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one real sustained Claude Code operator backend to the existing rich `OperatorHarnessAdapter` contract so a single Executive Attempt can run an exact provider session for multiple bounded turns, survive safe same-realm process replacement, and expose truthful process/session/result evidence without creating a Claude lifecycle service or weakening the existing PF1/Operator Harness security model.

**Architecture:** OCR-4 does **not** replace the existing PF1 foreground sealed-worker vertical. PF1 first proves one-shot `claude -p` behind the common sealed-worker adapter. OCR-4 is a later additive rich-operator adapter. It uses the already-installed `claude-agent-sdk` only inside one **transient provider-private generation helper process** per Operator Harness `ProcessGeneration`. The Executive worker broker/adapter launches that helper as an isolated process group with a minimal allowlisted environment under the already-provisioned native Claude realm/OS principal. The helper owns one `ClaudeSDKClient`, forces the exact system Claude CLI path, disables ambient filesystem settings/MCP/plugins/hooks/skills, and exchanges a closed framed JSON protocol with `ClaudeOperatorAdapter`. It owns no database, retry, Worker selection, Job/Attempt state, Slack, Wake or memory. Cross-realm continuation remains OCR-5; OCR-4 only proves one realm and same-provider-session recovery.

**Tech Stack:** Python 3.12, existing `control_plane.operator_harness_contract`, existing Executive Operator Harness/Event plane, `claude-agent-sdk` pinned/attested at implementation time, exact installed Claude Code CLI, asyncio/subprocess, JSON lines, pytest.

**Specs / predecessor law:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`
- `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`
- `docs/superpowers/plans/2026-08-27-hybrid-workforce-pf1-claude-worker.md`
- current accepted `control_plane/operator_harness_contract.py`.

## Dependency Gate

Do not implement OCR-4 until all of the following are accepted on current heads:

```text
CF2-I
RF1
HF1
PF1 one-real-Claude sealed-worker proof
OCR-1 V2 native realm isolation for the target realm
```

OCR-4 planning may merge earlier. Wake PR #174 remains the sole current Wake transport carrier and is not widened by this plan.

## Global Constraints

- `OperatorHarnessAdapter` and Executive Runtime remain the only rich-operator lifecycle boundary. No `claude_session_manager`, daemon, per-provider SQLite, retry loop or queue.
- Exactly one helper process exists per `ProcessGeneration`. Helper exit is generation exit; a later same-Attempt resume uses a **new** helper/ProcessGeneration through existing TX-10/TX-11 law.
- Native Claude authentication remains inside the candidate OS principal's Claude-owned Keychain. The helper receives no credential value, OAuth token, API key or auth file path.
- The helper process environment is built from an allowlist, not from a secret-rich parent process. This is load-bearing because current Claude Agent SDK subprocess transport inherits the helper's environment by default.
- The helper forces the exact reviewed system Claude CLI path (`ClaudeAgentOptions.cli_path` or current accepted equivalent), exact model, exact cwd/workspace, and reviewed client capability settings. No PATH-selected provider binary after attestation.
- Do not rely on private Agent SDK process/PID attributes. The Executive-visible process is the helper process group that it launches itself. The child Claude Code process must remain in that process group; whole-group death/writer-release is required before Executive reports `ProviderWriterState.RELEASED`.
- No work turn may occur before TX-4 `LaunchDecision.ALLOW`. OCR-4 therefore has a mandatory installed-version falsifier proving `ClaudeSDKClient.connect(prompt=None)` can establish one provider session/configuration and expose enough public initialization/session evidence **without sending a user/model work turn**. If this cannot be proven, STOP and return to Sol; do not send a bootstrap model prompt before attestation.
- Same-realm resume must preserve the exact bound `provider_session_id`; if Claude silently starts a different session, refuse and record `EFFECT_UNKNOWN`/`SESSION_MISSING` under existing law. Never treat “new chat with similar context” as resume.
- Ambient Claude settings, `CLAUDE.md`, auto memory, plugins, hooks, agents, MCP, browser/Chrome and provider-native background-agent features remain disabled unless an exact separately accepted capability profile grants them.
- Current Agent SDK callback hooks are not the sole security boundary. Security-relevant permissions/settings must be present at process start and observable in TX-4 attestation; host/workspace/resource enforcement remains Executive-owned.
- A provider rate limit is an adapter failure observation. It cannot create a new Attempt or choose another realm. OCR-5/Executive law owns cross-realm continuation after exact terminalization/requeue.

---

### Task 1: Freeze a provider-private helper wire and process boundary

**Files:**
- Create: `control_plane/claude_operator_helper_protocol.py`
- Create: `scripts/claude_operator_generation_helper.py`
- Create: `tests/test_claude_operator_helper_protocol.py`
- Create: `tests/test_claude_operator_generation_helper.py`

**Interfaces:**
- Helper wire schema: `mastermind.claude_operator_helper.v1`.
- Requests: `initialize`, `begin_turn`, `interrupt_turn`, `collect_candidate`, `reconcile`, `disconnect`.
- Responses/events are closed, bounded and secret-redacted.
- The helper never receives Executive lease token, Job authority to mutate Executive state, provider credentials, Slack/Wake identities or Worker-selection inputs.

- [ ] **Step 1: Write RED-first closed protocol tests**

Pin request shape conceptually:

```python
{
    "schema": "mastermind.claude_operator_helper.v1",
    "request_id": "helper-req-001",
    "operation": "initialize",
    "attempt_id": "ATT-...",
    "session_epoch_id": "ohf-epoch-...",
    "process_generation_id": "ohf-generation-...",
    "provider_session_id": None,
    "configuration": {
        "workspace_path": "/exact/worktree",
        "claude_binary": "/exact/claude",
        "claude_binary_sha256": "a" * 64,
        "claude_version": "2.x.y",
        "agent_sdk_version": "x.y.z",
        "requested_model": "exact-model-id",
        "permission_mode": "dontAsk",
        "sandbox_policy": "...",
        "network_policy": "...",
        "setting_sources": [],
        "mcp_servers": {},
        "allowed_tools": [],
        "disallowed_tools": [],
        "extra_args": {"strict-mcp-config": None},
    },
}
```

Reject unknown fields, duplicate request IDs, secret-shaped configuration values, arbitrary `env`, model-authored process/session ids, absolute paths outside the already-approved workspace/binary surfaces, and any `operation` not on the closed list.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_operator_helper_protocol.py
```

- [ ] **Step 3: Implement canonical serializer/validator and bounded response types**

Response types include only:

```text
initialized
turn_acknowledged
normalized_event
candidate_result
reconcile_observation
disconnected
refused
error
```

Raw Claude SDK message objects, stack traces, complete server-info payloads and provider account identity must never cross the helper boundary.

- [ ] **Step 4: Add a minimal-environment builder**

`build_helper_environment(...)` starts from an empty mapping and copies only reviewed non-secret OS/process necessities required for the native worker principal and Keychain/provider operation, for example locale, `HOME`/`TMPDIR`, the exact safe `PATH` if needed by allowed tools, and fixed Mastermind helper metadata. Explicitly omit provider API/OAuth token env variables and unrelated Executive/control secrets.

The exact allowlist must be host-proven; tests must fail if `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, Slack tokens, GitHub tokens or the Executive lease token are present.

- [ ] **Step 5: Implement the helper main loop with dependency injection**

The script may import `claude_agent_sdk` only inside its generation process. For unit tests inject a fake SDK client factory. It maintains exactly one client and one bound provider session for its process lifetime. It has no reconnect/retry loop beyond handling one explicit Executive request at a time.

- [ ] **Step 6: Run tests**

```bash
pytest -q tests/test_claude_operator_helper_protocol.py tests/test_claude_operator_generation_helper.py
python3 -m compileall -q control_plane/claude_operator_helper_protocol.py scripts/claude_operator_generation_helper.py
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/claude_operator_helper_protocol.py scripts/claude_operator_generation_helper.py tests/test_claude_operator_helper_protocol.py tests/test_claude_operator_generation_helper.py
git commit -m "feat(exec): add transient Claude operator generation helper"
```

---

### Task 2: Prove pre-work session initialization on the installed Agent SDK/CLI

**Files:**
- Modify: `scripts/claude_operator_generation_helper.py`
- Create: `ops/executive_os/claude-operator-sdk-preflight.py`
- Create: `tests/test_claude_operator_sdk_preflight.py`
- Modify: `tests/test_claude_operator_generation_helper.py`

**Interfaces:**
- Read-only/pre-work probe schema: `mastermind.claude_operator_sdk_preflight.v1`.
- No Executive lifecycle mutation and no real work prompt.

- [ ] **Step 1: Write RED-first initialization tests using a fake SDK client**

The helper must be capable of:

```python
client = ClaudeSDKClient(options=options)
await client.connect(prompt=None)
info = await client.get_server_info()
```

and return a sanitized `initialized` observation **before** any `client.query(...)` call.

Test spies must assert `query_calls == []` at initialization return.

- [ ] **Step 2: Pin public initialization evidence contract**

The adapter needs enough secret-free evidence to bind the provider session and attest configuration. Accept only fields actually exposed by the installed public SDK/CLI path after host proof. At minimum the real preflight must establish:

```text
connect succeeded
zero user/model work turn was sent
one exact provider session id can be observed or preselected and verified
served/current model is observable or the requested model can be verified before first turn
effective MCP census is empty except reviewed grants
effective settings/customization state matches requested profile
exact CLI + Agent SDK version/digest identity
```

If the public initialization result cannot establish provider session identity before a turn, `verdict=UNSUPPORTED_PREWORK_SESSION_ID` and OCR-4 stops. Do not reach into private `_query`, `_transport` or `_process` attributes as a production workaround.

- [ ] **Step 3: Construct deterministic Agent SDK options**

At implementation time pin the current SDK API. The target semantic configuration is:

```python
ClaudeAgentOptions(
    cwd=workspace,
    model=exact_model,
    permission_mode="dontAsk",
    setting_sources=[],
    mcp_servers={},
    plugins=[],
    hooks={},
    agents={},
    skills=[],
    cli_path=exact_claude_binary,
    env={},  # only safe fixed overrides; helper parent env is already clean
    extra_args={
        "strict-mcp-config": None,
        "no-chrome": None,
        "safe-mode": None,
        "switch-models-on-flag": "false",
    },
)
```

Use only arguments confirmed by the installed SDK/CLI. Unknown or changed flag behavior is `UNSUPPORTED_CONFIG_CONTRACT`, not a silent fallback.

- [ ] **Step 4: Add live-safe preflight command**

The script runs as the already-provisioned Claude worker principal and:

1. attests exact system Claude binary and Agent SDK package version/source;
2. constructs the clean helper environment;
3. connects with `prompt=None` in a temporary safe workspace;
4. obtains public server/session/config evidence;
5. confirms no model turn/result/user message occurred;
6. disconnects and proves helper/process group cleanup;
7. emits only a sanitized verdict.

- [ ] **Step 5: Unit/falsifier tests**

Cover missing session id, multiple/changed session IDs, unexpected MCP server, unexpected memory/settings/agent/plugin, wrong model, timeout, process-group leak and raw server-info secret-shaped output. All refuse.

- [ ] **Step 6: Run focused tests**

```bash
pytest -q tests/test_claude_operator_sdk_preflight.py tests/test_claude_operator_generation_helper.py
```

- [ ] **Step 7: Real host preflight**

Run exactly once per candidate SDK/CLI version on a safe native realm. A PASS is a predecessor to implementing `ClaudeOperatorAdapter.start_session`. A refusal returns to Sol before provider adapter implementation.

- [ ] **Step 8: Commit source/test changes**

```bash
git add scripts/claude_operator_generation_helper.py ops/executive_os/claude-operator-sdk-preflight.py tests/test_claude_operator_sdk_preflight.py tests/test_claude_operator_generation_helper.py
git commit -m "test(exec): prove Claude pre-work operator initialization"
```

---

### Task 3: Implement `ClaudeOperatorAdapter` over the existing OHF protocol

**Files:**
- Create: `control_plane/claude_operator_adapter.py`
- Modify only if generic composition requires it: `control_plane/executive_worker_broker.py`
- Create: `tests/test_claude_operator_adapter.py`
- Modify: `tests/test_operator_harness_contract.py`

**Interfaces:**
- `ClaudeOperatorAdapter` implements `OperatorHarnessAdapter`.
- Optional protocol support initially: `SupportsProbe`, `SupportsSessionResume` only if Task 2/5 proofs support it; `SupportsSteering` only if independently proven and required.
- No new Executive schema/table.

- [ ] **Step 1: Write RED-first capability and profile tests**

Expected descriptor semantics:

```text
interface_version = mastermind.operator_harness/v1
provider = claude
supports_structured_events = true
supports_native_resume = host-proven boolean
supports_native_fork = false initially
supports_steering = false unless explicitly proven
supports_checkpoint = false initially unless separately proven
supports_provider_native_idempotency = false unless provider proof exists
```

`validate_requested_profile()` must require:

- `provider == "claude"`;
- exact supported `harness_kind` for this adapter;
- exact helper/CLI/SDK binary/version/digest contract;
- accepted workspace identity;
- `AuthRealmRequirement.SLOT_BOUND_V1` or a stronger verified provider-account requirement only when actual evidence supports it;
- exact supported sandbox/approval/network/capability manifest;
- no ambient MCP/plugins/skills/agents/browser capability beyond grant.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_operator_adapter.py
```

- [ ] **Step 3: Implement helper process start without provider work**

`start_session(...)`:

1. receives Executive-allocated epoch/generation/OperationId;
2. launches exactly one helper as a new process group from an absolute reviewed Python/helper path with the clean environment;
3. sends `initialize` request;
4. receives the exact pre-work initialized observation;
5. verifies helper/provider session identity and configuration against `RequestedExecutionProfile`;
6. returns `SessionStartObservation(provider_session_id=<exact>, process=<helper process identity>, ...)`.

It performs no Executive write; caller applies TX-3.

- [ ] **Step 4: Implement observed TX-4 attestation material**

Map sanitized helper/server observations into `ObservedHarnessAttestation` including:

```text
served_model
harness_version = pinned Agent SDK + Claude CLI composition
harness_binary_digest = reviewed composition digest
capabilities/effective settings
effective MCP/plugins/apps = exact empty/reviewed set
sandbox/approval/network state
auth = slot-bound `AuthRealmFact` for current Worker/provider
workspace identity
unknown_fields
```

Any field not actually observable stays unknown and causes `compare_launch()` refusal when required. The adapter never authors `LaunchDecision`.

- [ ] **Step 5: Implement `begin_turn`**

Only after caller supplies the TX-4 `LaunchComparison` with `ALLOW`, send the already-allocated turn plus fixed prompt/input to the helper. Helper calls `client.query(...)` exactly once for that OHF turn and returns a public provider acknowledgement if available. The adapter converts it to `TurnStartObservation`; no acknowledgement evidence means no TX-5 APPLIED.

- [ ] **Step 6: Implement normalized event stream and candidate collection**

Map provider SDK messages into existing `NormalizedEvent` with bounded redacted payload. Preserve provider event/native tool ids only as opaque evidence. `collect_candidate_result()` returns `CandidateResult(complete_job_permitted=False)` and never performs Executive validation/completion.

- [ ] **Step 7: Implement interrupt/cancel/graceful-stop/reconcile**

- `interrupt_turn` uses the provider client interrupt path via helper and remains effect-unknown on lost response.
- `graceful_stop` requests SDK disconnect/helper exit, waits boundedly, and observes the **whole helper process group**. `provider_writer_state=RELEASED` only when the provider client is disconnected and no group member can still write the session.
- `cancel` follows the same exact generation/process identity; no lock deletion or new session.
- `reconcile` is observational only and never kills/resumes/marks LOST/selects provider.

- [ ] **Step 8: Run focused OHF regressions**

```bash
pytest -q \
  tests/test_claude_operator_adapter.py \
  tests/test_operator_harness_contract.py \
  tests/test_executive_operator_harness_port.py \
  tests/test_operator_harness_orchestrator.py
```

- [ ] **Step 9: Commit**

```bash
git add control_plane/claude_operator_adapter.py control_plane/executive_worker_broker.py tests/test_claude_operator_adapter.py tests/test_operator_harness_contract.py
git commit -m "feat(exec): add sustained Claude operator adapter"
```

---

### Task 4: Prove multiple turns stay on one provider session inside one Attempt

**Files:**
- Create: `tests/test_claude_operator_sustained_integration.py`
- Modify only a current generic orchestration/OHF seam if a real falsifier requires it; do not widen Phase 1F-C role-result cardinality casually.

**Interfaces:**
- Test first against a role-null/fixture OHF Job unless current accepted orchestration law explicitly supports sustained multi-turn Fable execution inside one role Attempt.

- [ ] **Step 1: Build a hermetic role-null OHF Attempt fixture**

Use existing Runtime/Operator Harness transactions:

```text
claim Attempt
TX-1 seal profile
TX-2 start INTENT
adapter.start_session
TX-3 bind
TX-4 attestation/ALLOW
TX-5 turn 1
read/collect
TX-5 turn 2 with a distinct OperationId/TurnRef
read/collect
```

Assert the same `attempt_id`, `session_epoch_id`, current `process_generation_id`, Worker and `provider_session_id` remain bound across turns.

- [ ] **Step 2: Prove no turn before attestation**

A mutation that calls `begin_turn` before `LaunchDecision.ALLOW` must fail without helper provider work.

- [ ] **Step 3: Prove rate-limit and transport failure are observations only**

A helper response classified `QUOTA_OR_RATE_LIMIT` or lost turn ACK must not call `requeue_job`, claim another Worker or start another helper. It returns to the Executive supervisor for terminal/reconcile law.

- [ ] **Step 4: Preserve Phase 1F-C orchestration invariants**

Run the full current orchestration OHF tests unchanged. If sustained Fable requires more turn cardinality than the accepted orchestration-role G1/G2 contract permits, STOP and record a separate architecture falsifier. Do not edit the cardinality limit merely to make this test pass.

- [ ] **Step 5: Run integration/regression suite**

```bash
pytest -q \
  tests/test_claude_operator_sustained_integration.py \
  tests/test_executive_runtime.py \
  tests/test_operator_harness_orchestrator.py \
  tests/test_executive_os_phase1fc.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_claude_operator_sustained_integration.py
git commit -m "test(exec): prove sustained Claude session within one Attempt"
```

---

### Task 5: Prove exact same-realm session resume through TX-10/TX-11

**Files:**
- Modify: `control_plane/claude_operator_adapter.py`
- Modify: `scripts/claude_operator_generation_helper.py`
- Modify: `tests/test_claude_operator_adapter.py`
- Create: `tests/test_claude_operator_same_realm_resume.py`

**Interfaces:**
- Implements `SupportsSessionResume` only if the installed SDK/CLI preflight proves exact resume.

- [ ] **Step 1: Write RED-first exact-session resume tests**

Given `ProviderSessionHandoff(provider_session_id=S1, worker_id=W1)`, the new helper must configure the provider-supported exact session resume path and return **exactly S1**.

Refuse:

```text
new provider session S2 returned
session missing
active writer still holds S1
resume response ambiguous/timeout
workspace/profile/auth realm changed
provider says resume succeeded but public initialized identity is unavailable
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_claude_operator_same_realm_resume.py
```

- [ ] **Step 3: Implement exact resume through current public SDK options**

Use only current supported `session_id`/`resume` semantics proven by the installed version. Do not implement transcript copying, manual JSONL editing or `--resume` shell fallback that races a current writer.

The helper connects with no work prompt, verifies the returned initialized provider session identity equals `ProviderSessionHandoff.provider_session_id`, and only then returns `SessionStartObservation`. Caller applies existing TX-11.

- [ ] **Step 4: Prove whole-writer release before resume**

The old generation must be `PROVEN_DEAD` with `ProviderWriterState.RELEASED` under existing TX-10 preconditions. Killing only the helper PID is insufficient if another process in the group remains.

- [ ] **Step 5: Run existing TX-10/TX-11 mutation matrix**

```bash
pytest -q \
  tests/test_claude_operator_same_realm_resume.py \
  tests/test_operator_harness_contract.py \
  tests/test_executive_runtime.py \
  tests/test_executive_operator_harness_port.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/claude_operator_adapter.py scripts/claude_operator_generation_helper.py tests/test_claude_operator_adapter.py tests/test_claude_operator_same_realm_resume.py
git commit -m "feat(exec): resume exact Claude provider session safely"
```

---

### Task 6: One real native-realm sustained canary

**Files:**
- No source modification unless a reproducible defect is found on the same carrier.
- Sanitized review evidence only.

- [ ] **Step 1: Re-pin all predecessors and current Claude realm proof**

Require current protected Skillpack, CF2/RF1/HF1/PF1 accepted heads, OCR-1 target realm `READY_SLOT_BOUND`, exact Claude Code + Agent SDK versions/digests, and no colliding OHF provider PR.

- [ ] **Step 2: Create one harmless role-null/specially approved operator canary Attempt**

The canary must not widen a business program or use a real modifying repo branch unless a separately bounded production proof specifically requires it. Its goal is session mechanics.

- [ ] **Step 3: Prove start without work**

Capture sanitized evidence:

```text
TX-2 committed
helper process group launched
provider session S1 observed
zero model work before TX-4
TX-3 APPLIED
TX-4 ALLOW
```

- [ ] **Step 4: Prove two real turns**

Send two harmless bounded turns after ALLOW. Both must use S1 and the same Attempt/generation. Capture provider event/result hashes, not raw private transcript.

- [ ] **Step 5: Prove same-realm process replacement if supported**

Gracefully stop G1, prove writer release, TX-10 allocate G2, resume S1, TX-11 APPLIED, then one harmless turn on G2. If installed provider cannot prove exact resume, classify `SAME_REALM_RESUME_UNSUPPORTED` and keep cross-realm continuity separately possible via new Attempt/OCR-5.

- [ ] **Step 6: Full hosted gates + adversarial review**

Require exact-head CI/CodeQL plus explicit attacks on:

- environment secret inheritance;
- pre-attestation work;
- changed provider session on resume;
- leaked helper child process;
- unreviewed MCP/setting/plugin/tool;
- helper retry/daemon behavior;
- provider rate limit causing hidden requeue;
- raw provider text/credential in Event receipts.

- [ ] **Step 7: Return to Sol**

Return exact head, target realm, helper/CLI/SDK identities, session/generation/turn ids, zero-prework proof, multi-turn proof, same-realm resume verdict, hosted gates and explicit `CROSS_REALM_ROLLOVER NOT YET PROVEN`.

## Stop Condition

OCR-4 stops when one real native Claude realm can run a sustained exact provider session through the existing rich Operator Harness with at least two bounded turns after TX-4 ALLOW and truthful same-realm resume capability classification. It does not implement capacity-driven account switching, Job requeue across realms, Slack rebound, Steward, Wake ACK, or multi-host routing.

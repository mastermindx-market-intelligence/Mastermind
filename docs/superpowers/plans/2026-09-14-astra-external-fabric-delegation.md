# Astra External Fabric Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an Executive-owned Astra/Codex orchestrator offload bounded execution to the existing Mastermind Agent Fabric through the existing five-tool Executive MCP, complete one real external-provider work/review/result round trip, resume the exact Astra parent, and prove at least a 50% reduction in Astra + internal-Codex usage versus a comparable Codex-heavy baseline.

**Architecture:** Preserve the frozen five-tool MCP and its existing authenticated Executive App admission path. `submit_ceo_intent` remains the model-facing bounded intent surface; the App converts it to CeoIngress v2. Executive Runtime/COO/Capacity own lifecycle, planning, continuation, and placement. Qualified worker adapters own execution. The existing Codex `RuntimeBinding`/Wake path owns exact parent continuation. Codex configuration and instructions only make Astra a client of those owners; they do not create a scheduler, lifecycle store, provider selector, retry plane, or result bus.

**Tech Stack:** Python 3.12, Mastermind Executive Runtime/CeoIngress/COO/Capacity, `integrations.executive_mcp`, `integrations.mastermind_executive_app`, Streamable HTTP MCP, Codex CLI MCP registration/OAuth, `CodexOperatorAdapter`, RuntimeBinding/Wake, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-astra-external-fabric-delegation-design.md`

## Global Constraints

- Freshly reconcile the implementation branch with protected `master` before source work. The design freeze was authored against `cf4c082d83fffe35daee81aa3d30bd27450bacf1`; that SHA is an evidence pin, not a permanent implementation base.
- Keep the five public Executive MCP tool names and schemas unchanged for this vertical.
- Reuse `integrations.mastermind_executive_app.admission.compose_admission`; no new Codex-facing mutation sink may call `ceo_intent.submit_intent` directly.
- Preserve `dispatched=false` on the admission receipt. Later COO execution is a distinct canonical transition.
- Astra may author only the existing high-level business fields. It may not supply provider, model, account, provider home, credential, endpoint, host, UID/GID, socket, worker ID, branch, worktree, raw authority, or validation argv.
- One logical modifying operation keeps one stable `operation_key` and derived `request_ref`. `effect_unknown` is reconciled on that identity before any further modification; no blind retry or carrier/provider/internal-agent failover.
- Worker transcripts are not normal Astra return context. Use canonical bounded Job/result/review projections; fetch more evidence only for a specific review or acceptance question.
- Keep the existing repo-local internal Codex fallback at Terra/medium and maximum concurrency 3 unless a separate reviewed policy change amends it.
- Do not edit #583-owned provider-binding files until #583 or its accepted successor is protected and source ownership is reconciled.
- Do not arm operational continuation beyond current accepted source law; #612 or an accepted successor must cover the intended autonomous interval before the real canary.
- Do not introduce another Job/Attempt store, task queue, provider/account registry, auth store, retry journal, transcript store, Wake bus, raw provider-spawn tool, or generic shell execution surface.
- Every modifying worker uses the workspace assigned by its current harness; attended Web/host work uses the current `mmx-workspace` path.
- A manually opened arbitrary Codex tab is not accepted parent proof. End-to-end completion requires the exact Astra native session/generation to be the current Executive `RuntimeBinding` target.
- Unit tests are not production acceptance. Final proof requires a real external provider call, canonical result/review evidence, exact Astra-parent consumption, and measured usage reduction.

## First-Vertical Source Surface

The client-side source PR should remain narrow:

- Create `ops/codex_fabric/register_executive_mcp.py`.
- Create `tests/test_codex_fabric_registration.py`.
- Create `tests/test_astra_external_fabric_contract.py`.
- Modify `AGENTS.md` with a concise Astra delegation policy.
- Create `docs/runbooks/codex-astra-fabric-delegation.md`.
- Create `tests/test_astra_delegation_source_policy.py`.
- Extend `tests/test_codex_app_server_wake_rpc.py` only if one exact-parent discriminator is genuinely absent from the current suite.

Do not modify `integrations/executive_mcp/schemas.py`, `control_plane/ceo_intent.py`, `control_plane/executive_runtime.py`, `control_plane/executive_coo_cycle.py`, provider-binding files, or Capacity policy in this first client PR. If a discriminating test proves one of those current owners cannot support the frozen design, stop at the owner boundary and return the exact blocker; do not broaden the PR by convenience.

---

### Task 1: Pin the Existing Five-Tool -> CeoIngress-v2 Contract

**Files:**
- Create: `tests/test_astra_external_fabric_contract.py`
- Read only: `integrations/executive_mcp/schemas.py`
- Read only: `integrations/mastermind_executive_app/admission.py`
- Read only: `control_plane/executive_ceo_ingress.py`
- Read only: `control_plane/ceo_request.py`

**Interfaces:**
- `validate_tool_arguments("submit_ceo_intent", payload)` remains the caller validator.
- `compose_admission(AdmissionRequest)` remains the modifying App composition.
- `ceo_request.app_request_ref(operation_key)` remains the stable outer identity derivation.
- The App must emit `ceo_ingress.SUBMIT_SCHEMA_V2` and omit `operation_key` from the semantic v2 request.

- [ ] **Step 1: Write the cross-layer contract tests before any production change**

Implement these exact tests in `tests/test_astra_external_fabric_contract.py`:

1. `test_submit_shape_refuses_physical_routing_fields`
   - Start from a valid `research_only` five-tool payload.
   - Add each forbidden field independently: `provider`, `model`, `account`, `provider_home`, `endpoint`, `host`, `worker_id`, `socket_path`.
   - Require `GatewayError` from `validate_tool_arguments` for every mutation.

2. `test_app_converts_five_tool_submit_to_v2_automated_frame`
   - Construct `VerifiedPrincipal` with the exact submit+read scope tuple using the field pattern already present in `tests/test_mastermind_executive_app_admission.py`.
   - Use a recording fake `CeoIngressClient` returning a canonical accepted receipt with `dispatched=False`.
   - Monkeypatch only `observe_trusted_grounding` to return a valid exact three-field grounding document.
   - Call `compose_admission` once.
   - Assert exactly one frame was sent.
   - Assert `frame["schema"] == ceo_ingress.SUBMIT_SCHEMA_V2`.
   - Assert `frame["request_ref"] == ceo_request.app_request_ref(operation_key)`.
   - Assert `operation_key` is absent from `frame["request"]`.
   - Assert the semantic objective/profile fields are unchanged.
   - Assert the returned receipt reports `dispatched is False`.

3. `test_request_ref_is_stable_for_same_operation_key`
   - Require two calls to `app_request_ref` with the same key to be byte-identical and match `AUTOMATED_REQUEST_REF_RE`.

4. `test_effect_unknown_reconciles_by_same_request_ref_without_second_submit`
   - Script the fake client to return `TRANSPORT_SENT_UNKNOWN` for the first submit and a canonical status result for the next status call.
   - Require `compose_admission` to return `STATUS_EFFECT_UNKNOWN` after exactly one submit frame.
   - Call `reconcile_by_request_ref` with that exact `request_ref`.
   - Assert the second frame uses `STATUS_SCHEMA_V2` and the same `request_ref`.
   - Assert no second `SUBMIT_SCHEMA_V2` frame exists.

- [ ] **Step 2: Run the contract set**

```bash
python3 -m pytest -q \
  tests/test_astra_external_fabric_contract.py \
  tests/test_mastermind_executive_app_admission.py \
  tests/test_executive_mcp_app_composition.py
```

Expected: green on current architecture. If the five-tool App no longer emits CeoIngress v2, stop and return to architecture review; do not add a sixth tool.

- [ ] **Step 3: Mutation-proof the caller-authority fence**

Temporarily alter the new test fixture so `provider` is removed from the forbidden-field loop. Confirm the mutation makes the test incapable of detecting provider injection, restore the original test, then confirm green. Record the mutation receipt in the PR body; do not leave the mutant in source.

- [ ] **Step 4: Commit**

```bash
git add tests/test_astra_external_fabric_contract.py
git commit -m "test: pin Astra external Fabric admission contract"
```

---

### Task 2: Add an Idempotent, Non-Secret Codex MCP Registration Helper

**Files:**
- Create: `ops/codex_fabric/register_executive_mcp.py`
- Create: `tests/test_codex_fabric_registration.py`

**Interfaces:**
- Fixed server name: `mastermind-executive`.
- Input: one explicit loopback Streamable HTTP URL taken from the accepted Executive MCP installation receipt.
- Codex commands used: `codex mcp get mastermind-executive --json` and, only when absent, `codex mcp add mastermind-executive --url <exact normalized URL>`.
- Output: immutable `RegistrationReceipt(server_name, url, created, login_required)` containing no secret value.

The helper does not read root-owned Executive config, guess a port, perform OAuth login, or store an access token. OAuth enrollment remains a separate attended installation action using Codex's supported credential flow.

- [ ] **Step 1: Write hermetic fake-Codex tests**

Create an executable fake `codex` program under `tmp_path` that records argv in a JSON-lines file and serves scripted JSON from a second fixture file. Implement these tests:

- `test_new_registration_adds_exact_streamable_http_url_once`
  - Initial `mcp get` returns the same nonzero/not-found behavior produced by the fake for an absent server.
  - Require exactly one `mcp add` call with argv `["mcp", "add", "mastermind-executive", "--url", expected_url]`.
  - Require the verification `mcp get` to return enabled `streamable_http` with the exact URL.
  - Require `created is True` and `login_required is True`.

- `test_matching_registration_is_idempotent`
  - Initial `mcp get` returns enabled `streamable_http` with the exact URL.
  - Require no `mcp add` call.
  - Require `created is False`.

- `test_existing_different_url_refuses_without_overwrite`
  - Existing server returns a different URL.
  - Require `RegistrationError` and zero mutation calls.

- `test_non_loopback_or_wrong_path_refuses_before_codex_process`
  - Exercise `https://example.com/mcp`, `http://127.0.0.1:9123/not-mcp`, userinfo, query, fragment, and port below 1024.
  - Require `RegistrationError` and no fake-Codex invocation.

- `test_registration_never_places_secret_material_on_argv`
  - Scan every recorded argv element for `Bearer`, `sk-`, `access_token`, `provider-credential`, and `Authorization`.
  - Require none are present.

- `test_missing_codex_binary_refuses_closed`
  - Point `codex_bin` at a nonexistent path and require opaque `RegistrationError`.

- `test_effect_unknown_add_reconciles_with_get_before_retry`
  - First `mcp get` reports absent.
  - Fake `mcp add` times out after recording the mutation.
  - The helper must issue one `mcp get` reconciliation.
  - If that read shows the exact server present, return success without a second add.
  - Assert exactly one `mcp add` mutation occurred.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q tests/test_codex_fabric_registration.py
```

Expected: import/collection failure because the helper does not yet exist.

- [ ] **Step 3: Implement the minimal helper**

Implement:

```text
RegistrationReceipt: frozen dataclass with server_name, url, created, login_required
RegistrationError: closed RuntimeError subclass
normalize_loopback_mcp_url(value: str) -> str
register(server_url: str, *, codex_bin: str = "codex") -> RegistrationReceipt
```

`normalize_loopback_mcp_url` must use `urllib.parse.urlsplit` and require:

```text
scheme: http
hostname: 127.0.0.1, localhost, or ::1
explicit port: 1024..65535
path: exactly /mcp
username/password/query/fragment: absent
```

`register` must:

1. normalize before spawning a process;
2. run `mcp get` with `stdin=DEVNULL`, captured stdout/stderr, and a bounded timeout;
3. accept an existing server only when transport type is `streamable_http`, URL matches exactly, and the entry is enabled;
4. refuse a conflicting existing entry instead of overwriting it;
5. add only when the initial read proves absence;
6. after add success or ambiguous add timeout, re-read with `mcp get` before deciding state;
7. never issue `mcp add` twice inside one call;
8. return `login_required=True` because auth enrollment is not performed here;
9. never inherit or inject a token-specific environment variable in this helper.

- [ ] **Step 4: Run RED-to-GREEN and a mutation check**

```bash
python3 -m pytest -q tests/test_codex_fabric_registration.py
python3 -m compileall -q ops/codex_fabric
```

Then locally mutate the conflicting-URL branch to overwrite the entry, prove `test_existing_different_url_refuses_without_overwrite` fails, restore the implementation, and rerun green.

- [ ] **Step 5: Commit**

```bash
git add ops/codex_fabric/register_executive_mcp.py tests/test_codex_fabric_registration.py
git commit -m "feat: register Executive MCP for Codex safely"
```

---

### Task 3: Make External Fabric Delegation the Astra Default

**Files:**
- Modify: `AGENTS.md`
- Create: `docs/runbooks/codex-astra-fabric-delegation.md`
- Create: `tests/test_astra_delegation_source_policy.py`
- Read only: `.codex/config.toml`

**Interfaces:**
- Uses the existing Executive tools only.
- Produces source-visible operating instructions; it does not create authority or runtime state.

- [ ] **Step 1: Write source-policy tests**

`tests/test_astra_delegation_source_policy.py` must read `AGENTS.md` and `.codex/config.toml` and require:

```text
AGENTS contains heading/text "External Fabric delegation"
AGENTS names submit_ceo_intent
AGENTS says Astra must never choose a provider
AGENTS names effect_unknown same-identity reconciliation
AGENTS prohibits normal full worker transcript replay
AGENTS identifies internal Codex as pre-effect fallback
.codex/config.toml still has max_concurrent_threads_per_session = 3
.codex/config.toml still has default_subagent_model = "gpt-5.6-terra"
.codex/config.toml still has default_subagent_reasoning_effort = "medium"
```

The new AGENTS section must not contain direct-spawn instructions for `pool run`, `spawn_minimax`, `spawn_glm`, provider-home assignment, or account-number selection.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q tests/test_astra_delegation_source_policy.py
```

Expected: failure because the source-policy section is absent.

- [ ] **Step 3: Add the `External Fabric delegation` section to `AGENTS.md`**

The section must state all of the following without changing the existing hierarchy/authority sections:

- Astra keeps intent recovery, architecture, cross-return judgment, exception adjudication, and final acceptance.
- For bounded independently executable research, implementation, tests, repair, or independent review, Astra uses the existing Executive Fabric via `submit_ceo_intent` before opening internal Codex subagents.
- Astra authors objective/profile/write/test constraints only and never chooses provider, model, account, credential home, endpoint, host, or worker identity.
- `dispatched=false` after admission is normal; the COO cycle owns later execution.
- On `effect_unknown`, Astra reconciles the same request identity and does not mint a new key or switch carrier/provider/internal agent until canonical settlement.
- Astra consumes bounded Executive Job/result/review evidence and does not replay a full worker transcript into parent context unless a specific acceptance contradiction requires it.
- Internal Codex agents are pre-effect fallback only when Fabric is unavailable or lacks the required capability, with a named fallback reason.

- [ ] **Step 4: Write the operator runbook**

`docs/runbooks/codex-astra-fabric-delegation.md` must define the first-vertical procedure exactly:

1. fresh-pin protected Mastermind Skillpack and reconcile source collisions;
2. obtain the installed Executive MCP loopback URL from the current accepted installation receipt;
3. run `python3 ops/codex_fabric/register_executive_mcp.py --url "$MMX_EXECUTIVE_MCP_URL"`, where the environment variable is populated from that non-secret installation coordinate;
4. run `codex mcp get mastermind-executive --json` and require enabled Streamable HTTP with the exact URL;
5. run the supported OAuth enrollment command `codex mcp login mastermind-executive` once under the currently approved resource/scopes; credentials remain in Codex's supported credential store;
6. start a fresh Codex/Astra session after registration/auth changes and inspect the current MCP tool census;
7. require the five expected Executive tools and no caller-controlled provider field;
8. prove the Astra orchestrator is the exact current Executive-owned Codex `RuntimeBinding` before unattended return is claimed;
9. execute the baseline and delegated canaries in Task 6;
10. on `effect_unknown`, reconcile the original `request_ref` and stop other modifying work until settled.

The runbook must explicitly state: a manually opened arbitrary Codex tab may prove MCP connectivity, but it is not accepted exact-parent proof unless Runtime evidence binds that native session/generation.

- [ ] **Step 5: Re-run and commit**

```bash
python3 -m pytest -q tests/test_astra_delegation_source_policy.py
git diff --check
git add AGENTS.md docs/runbooks/codex-astra-fabric-delegation.md tests/test_astra_delegation_source_policy.py
git commit -m "docs: make Executive Fabric Astra's default worker path"
```

---

### Task 4: Qualify Exact Astra Parent Return Without Model Polling

**Files:**
- Read/verify: `control_plane/codex_operator_adapter.py`
- Read/verify: `control_plane/session_targets.py`
- Read/verify: `control_plane/runtime_binding_projection.py`
- Read/verify: `integrations/executive_wake/codex_app_server_rpc.py`
- Extend only if needed: `tests/test_codex_app_server_wake_rpc.py`

**Interfaces:**
- Input: Executive-owned current Codex `RuntimeBinding` with `reasoning_surface="codex"`, exact process generation, and exact provider-native handle.
- Output: evidence that Wake delivers attention only to that current Astra generation and cannot select another Codex session.

- [ ] **Step 1: Run current exact-session regressions**

```bash
python3 -m pytest -q \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_runtime_binding_projection.py \
  tests/test_wake_ack_ingress.py
```

- [ ] **Step 2: Verify the four discriminators in existing tests**

The suite must demonstrably pin all four facts:

```text
reasoning_surface == codex
native handle/thread id agrees with RuntimeBinding
binding_generation and process_generation agree
attention uses the current writer's turn/start and never discovers/resumes/forks a neighboring session
```

If all four already have discriminating coverage, make no source/test change and record exact test names in the PR evidence.

If one fact lacks discriminating coverage, add one focused test to `tests/test_codex_app_server_wake_rpc.py` using the existing `RuntimeBinding`, `CodexCurrentWriterWakeClient`, and adapter fixtures. Do not add a session registry or new resolver.

- [ ] **Step 3: Prove wrong-parent refusal**

Exercise a mismatched native handle or binding generation. Require the current owner to refuse or preserve uncertainty; delivery to another Codex thread is a test failure.

- [ ] **Step 4: Apply the parent-binding stop condition**

For the real canary, require the Astra orchestrator to be materialized/bound through the existing Executive Codex Operator path. If that exact native generation cannot be represented as the current `RuntimeBinding`, stop the program at `BLOCKED_PARENT_BINDING`. Do not add latest-tab discovery, window automation, title matching, or model polling.

- [ ] **Step 5: Commit only when a test discriminator was added**

When a test changed:

```bash
git add tests/test_codex_app_server_wake_rpc.py
git commit -m "test: pin exact Astra parent wake binding"
```

When current tests already cover the required behavior, create no empty commit.

---

### Task 5: Consume the First External Provider Lane From Its Existing Owner

**Files:**
- Dependency/read: PR #583 or its protected successor.
- Dependency/read: `config/subscription_provider_profiles.v1.json`.
- Dependency/read after protection: `config/subscription_harness_bindings.v1.json` and `control_plane/subscription_harness_bindings.py`.
- Capacity/worker files remain with their current owner; this plan does not preclaim them.

**Interfaces:**
- Required activation facts: `adapter_implemented`, `provider_realm_enrolled`, `capacity_known`, `real_canary_passed`, `usage_policy_satisfied`.
- Preferred first canary lane: Alibaba Codex Responses only if current Capacity says it is eligible.

- [ ] **Step 1: Reconcile #583 at execution time**

All must be true before this task advances:

```text
#583 or its accepted successor is protected/merged
its binding source is on current protected master
no active writer still owns the same binding files
Alibaba Codex Responses is at least BUILT_NOT_PROVEN
autonomous_allowed remains false before the real provider canary
```

If any condition fails, return `BLOCKED_PROVIDER_BINDING_SOURCE`; do not reimplement the binding in this plan.

- [ ] **Step 2: Have the current provider/Capacity owner establish pre-canary facts**

Before the one-shot real canary, require:

```text
adapter_implemented = true
provider_realm_enrolled = true
capacity_known = true
usage_policy_satisfied = true
real_canary_passed = false
```

Credential material stays in the existing provider-home/host trust boundary. It must never enter prompts, Codex config, PR text, logs, or Git history.

- [ ] **Step 3: Run one harmless real external provider canary through the common worker path**

Use `research_only` with no write paths. The provider call must be reached through Executive admission -> COO/Capacity -> common worker/broker. Direct provider CLI invocation from Astra is not proof.

Pass requires canonical evidence of:

```text
exact Job/Attempt/worker identity
exact source/workspace identity
reviewed binding/provider realm
bounded useful output
clean process/session settlement
no effect uncertainty
no provider/account selected by Astra
```

- [ ] **Step 4: Complete the existing activation ceremony**

Only the existing provider/Capacity owner may advance the lane after the real canary and every current activation gate passes. Any binding/worker activation source change remains in that owner's PR, not the Codex client PR.

- [ ] **Step 5: Negative placement proof**

Exercise one stale/unknown-capacity or missing-capability case. Require a named park/refusal state and no automatic internal-Codex/provider failover after worker effect begins.

---

### Task 6: Run the End-to-End Token-Relief Canary

**Files:**
- Use canonical Executive Job/Attempt/result state and PR/canary evidence.
- If current procedure requires repository evidence, store only bounded non-secret proof under the existing `review_evidence/` convention; do not create a lifecycle or results authority there.

**Interfaces:**
- Inputs: registered/authenticated Executive MCP, strict-v2 host admission, exact Astra RuntimeBinding/Wake, one qualified external provider lane.
- Outputs: accepted real project result + independent review + exact parent consumption + baseline/delegated usage comparison.

- [ ] **Step 1: Freeze one representative acceptance contract before either run**

Record:

```text
objective
source base SHA
allowed write paths (empty for the first research canary is preferred)
validation/review requirement
acceptance evidence
one usage unit available in both baseline and delegated runs
```

Do not modify the acceptance contract after observing one run's usage.

- [ ] **Step 2: Capture the Codex-heavy baseline**

Run the same class of objective with External Fabric delegation intentionally disabled for this baseline only, using the current bounded internal-Codex policy. Capture the best common usage measure available in both runs:

```text
Astra input/output/reasoning tokens when exposed
internal Codex subagent count and usage when exposed
otherwise one documented common provider/harness usage proxy
```

Capture accepted output and independent review evidence. Wall-clock duration is secondary and never substitutes for token/usage accounting.

- [ ] **Step 3: Start a fresh exact-bound Astra session for the delegated run**

Before modifying work, require:

```text
mastermind-executive MCP registered and enabled
five expected tools visible
auth valid for read + submit
exact Astra native session/generation has the current RuntimeBinding
selected external lane is currently eligible through Capacity
no unresolved EFFECT_UNKNOWN operation exists for the chosen operation key
```

- [ ] **Step 4: Submit through the existing `submit_ceo_intent` tool**

Use one stable operation key and the frozen five-tool business fields only. Immediate success is a canonical accepted admission with `dispatched=false` and stable job/request identity. Astra must not open an internal subagent merely because the new root is initially queued.

- [ ] **Step 5: Let the existing COO/Capacity fabric execute**

The strict-v2 cycle owns planning and dispatch. At least one substantive work child must execute on the qualified external lane. Required independent review must use a distinct eligible reviewer under current review policy.

Do not keep Astra in a model polling loop. Existing exact RuntimeBinding/Wake should trigger result-driven continuation. If provider work completes but the exact parent cannot be resumed, stop at `BLOCKED_PARENT_RETURN`; provider success alone is not end-to-end success.

- [ ] **Step 6: Consume the compact canonical return**

Normal parent context must contain only the bounded identity/state, exact source/artifact revision or digest, bounded result summary, validation evidence, review verdict/state, unresolved blocker/next-decision data, and any canonical bounding receipts. Full worker transcripts and shell logs are excluded unless Astra explicitly requests a specific artifact to adjudicate a contradiction.

- [ ] **Step 7: Perform final Astra acceptance**

Accept only when the original user job is complete and the required independent review/validation passes. A worker success with a rejecting review routes through the existing bounded repair/re-review path; Astra does not self-approve it.

- [ ] **Step 8: Calculate the token-economics gate**

Use the common unit frozen in Step 1:

```text
reduction = 1 - delegated_astra_plus_internal_codex_usage / baseline_astra_plus_internal_codex_usage
```

Pass requires all of:

```text
reduction >= 0.50
equivalent acceptance quality
at least one substantive external work unit
zero routine Chairman account-selection actions
zero Chairman message shuttling between admission and returned candidate
no normal worker-transcript replay into Astra
exact bound Astra parent consumption
```

If exact token counters are unavailable, label the common measure `USAGE_PROXY`; never call it token count.

- [ ] **Step 9: Exercise duplicate/restart/effect-negative proof**

Prove:

```text
same operation identity does not create a duplicate root
lost submit response reconciles by the same request_ref
runtime/reasoning restart preserves accepted result and owed parent action
wrong/stale Astra RuntimeBinding cannot consume the continuation
```

No blind retry or provider switch is permitted for the effect-unknown case.

- [ ] **Step 10: Record capability state precisely**

Only when the complete real path passes may this first vertical be recorded `PROVEN_LIVE`. Do not claim ready-frontier parity, provider-fleet completion, multi-host completion, or Web closed-tab autonomy.

If the path stops earlier, record the exact sub-capability as `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, or `BROKEN` and leave the exact next action.

---

### Task 7: Current-Base Review, Release, and Durable Closeout

**Files:**
- No new feature scope.
- Update only the correct current durable records after acceptance.

- [ ] **Step 1: Reconcile with current protected master and collision-check again**

Do not force-push over another source owner. If current master materially changes `AGENTS.md`, Executive MCP/App admission, Codex Wake, or the registration path, re-run the corresponding contract tests before proceeding.

- [ ] **Step 2: Run the focused regression set**

```bash
python3 -m pytest -q \
  tests/test_astra_external_fabric_contract.py \
  tests/test_codex_fabric_registration.py \
  tests/test_astra_delegation_source_policy.py \
  tests/test_mastermind_executive_app_admission.py \
  tests/test_executive_mcp_app_composition.py \
  tests/test_executive_ceo_ingress.py \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_runtime_binding_projection.py \
  tests/test_wake_ack_ingress.py
python3 -m compileall -q ops/codex_fabric
git diff --check
```

Then run the repository's current required protected CI gate. Focused tests do not replace protected CI.

- [ ] **Step 3: Adversarial review against the frozen outcome**

Reviewer must answer yes/no with evidence:

```text
Five-tool public contract preserved?
Astra unable to name provider/account/credential/host?
Lost response unable to trigger blind retry/failover?
Arbitrary Codex tab unable to receive another session's Wake?
No new durable scheduler/lifecycle/result store?
No normal full-worker-transcript replay into Astra?
Real external lane performed substantive work through canonical path?
Result independently reviewed and consumed by exact Astra parent?
Measured Astra + internal-Codex usage reduced at least 50% in the common unit?
```

Any required negative answer blocks acceptance.

- [ ] **Step 4: Publish the scoped source PR**

Push the source branch, open/update the PR, wait for required checks, and merge only after review. Provider/Capacity activation changes stay with their existing owners rather than being folded into the Codex client PR.

- [ ] **Step 5: Update durable truth in the correct owners**

After accepted real proof:

- Executive OS remains the Job/Attempt/runtime evidence owner.
- Agent OS current workstream/handoff records the proven capability, important discoveries, and exact next action through its existing writer.
- GitHub records implementation/test/canary evidence.
- Linear/Control Room may project status but do not become authority.
- Slack, if used, remains transport only.

- [ ] **Step 6: Hold the next independent program explicitly**

After this vertical, the next planned capability is the existing-owner ready-frontier/dependency-parallelism wave from #600, followed by provider-matrix expansion. Neither starts implicitly from this PR.

## Plan Self-Review

### Requirement coverage

- Reuse existing five-tool MCP: Tasks 1-3.
- Preserve CeoIngress v2 / strict-v2 ownership: Tasks 1 and 6.
- No provider/account choice by Astra: Tasks 1, 3, 5, 7.
- Effect-unknown same-identity reconciliation: Tasks 1, 3, 6, 7.
- Exact Codex parent return: Tasks 4 and 6.
- External first lane without duplicating #583: Task 5.
- Compact result / no transcript replay: Tasks 3 and 6.
- Bounded internal Codex fallback: Task 3.
- Measured token/usage reduction: Task 6.
- No duplicate control plane: Global Constraints and Task 7.
- Production proof and durable closeout: Tasks 6-7.

### Scope check

This plan stops after the first independently useful external-delegation/token-relief loop. Ready-frontier parallelism, deeper child budgets, GLM/MiniMax activation, broader multi-host recovery, and Live Fabric UI work are separate follow-on plans so the first source PR cannot expand into a platform rewrite.

### Type/interface consistency

The plan reuses existing identities and types: model-facing `operation_key` -> App-owned `app_request_ref` -> CeoIngress v2 `request_ref`; `submit_ceo_intent` remains the modifying tool; `RuntimeBinding`/Codex Wake own exact parent return; provider selection remains outside the caller request. No second serialized lifecycle type is introduced.

### Placeholder scan

This plan contains no `TBD`, `TODO`, unfinished function body, fake return constant, unbound `<port>` token, or implementation placeholder. Runtime-specific values such as the installed MCP URL, current branch SHA, and canary operation key are obtained from their canonical owner at execution time and validated before use.
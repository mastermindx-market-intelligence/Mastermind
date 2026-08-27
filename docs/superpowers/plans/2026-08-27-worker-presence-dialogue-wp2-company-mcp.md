# Worker Presence & Dialogue WP-2 — Bounded Company Dialogue MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one production-inert Mastermind company-dialogue MCP facade whose exact six worker-facing tools can operate only on an already-bound Agent Dialogue V2 context, while reusing the existing Executive MCP capability-attestation law and exposing no generic Slack authority.

**Architecture:** Follow the hardened `integrations/executive_mcp` pattern: schemas and adapter remain stdlib/first-party only; exactly one `server.py` imports the MCP SDK; tool census and schema digest are static and mutation-tested. The adapter talks only to the existing Agent Dialogue AF_UNIX client/service and obtains identity/thread/context from an injected `DialogueBindingResolver`; none of those privileged fields exists in MCP tool input. WP-2 proves the facade and the existing `ExecutionCapabilityRegistry`/`McpServerGrant` compatibility using a production-inert fixture policy. It deliberately does **not** invent a long-lived token, actor registry, default production endpoint or runtime binding store. If no already-accepted host-owned exact Attempt/session binding seam exists at implementation time, that live binding remains `NOT_BUILT` and is returned to Sol as the WP-3 prerequisite rather than bypassed.

**Tech Stack:** Python 3.11+, existing MCP SDK dev dependency, existing `integrations.executive_mcp` security pattern, existing `integrations.slack_agent_dialogue.service.call_service`, existing `ExecutionCapabilityRegistry` / `McpServerGrant`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md`

## Global Constraints

- Protected pickup/source-law basis for planning: `Mastermind@8affa1c0403f4400825371bea0257f360a4814f2`; implementation MUST re-pin current protected `master`, the merged WP-0 spec, and the accepted WP-1 state before first code write and before push.
- WP-2 is production-inert. No Slack app install, token, OAuth enrollment, app-level token, new Slack scope, live Slack message, persistent service install, or production arming.
- Workers receive only six company-dialogue tools: `read_thread`, `ack`, `progress`, `blocked`, `request_decision`, `result`. No generic Slack search/post/channel/member/admin tool.
- MCP input contains no `job_id`, `attempt_id`, `worker_id`, executive seat, workstream, commission ref, session ref, Slack channel, Slack thread, display name, authority class, provider account, host, or runtime handle.
- Trusted actor/context/thread identity comes from `DialogueBindingResolver`, injected by host/runtime composition outside model arguments.
- WP-2 MUST NOT create a Worker/Attempt/session/actor database, cache, registry, cursor, queue, scheduler, replay ledger or credential service.
- Existing Agent Dialogue AF_UNIX service remains the downstream dialogue boundary; do not call Slack directly from the MCP package.
- Existing `ExecutionCapabilityRegistry` / `McpServerGrant` remains the only Executive capability-policy owner. Do not create `company_mcp_capabilities.json` or another policy registry.
- Existing `integrations/executive_mcp` remains the CEO Executive-state/intent gateway; do not add company-dialogue tools to that gateway or widen its tool census.
- **Sister-session collision fence:** no Wake #174 changes, no ASD-A2 production Relay installation/credentials, no C1/B2/C2, no CF2 claim/placement, no HF1 Worker Harness refactor, no PF1/MH1 provider/multi-host work, no Session Truth #170.
- If a current sibling carrier begins modifying an expected WP-2 path, STOP and return to Sol rather than stacking changes.

---

## File Structure

- Create `integrations/mastermind_company_mcp/__init__.py` — package boundary; re-export only stable non-SDK contracts.
- Create `integrations/mastermind_company_mcp/schemas.py` — static six-tool table, strict input schemas, output/error envelope, server/tool schema digest.
- Create `integrations/mastermind_company_mcp/adapter.py` — `DialogueBinding`, `DialogueBindingResolver`, Agent Dialogue service client seam, trusted V2 frame composition and six tool handlers.
- Create `integrations/mastermind_company_mcp/server.py` — the only module in this package importing `mcp`; tools-only low-level MCP server.
- Create `tests/test_mastermind_company_mcp.py` — tool census, schema snapshot, SDK isolation, no-privileged-input, binding injection, service-call, redaction/bounds and no-generic-Slack tests.
- Create `tests/test_mastermind_company_mcp_mutation.py` — authority/persistence/tool-widening mutation kills.
- Modify `tests/test_executive_agent_capabilities.py` only to prove an exact **fixture policy** containing the future company-dialogue MCP server/profile compiles through the existing registry; do not add a dead/placeholder server to production `config/executive_agent_capabilities.json` without a real reviewed endpoint/transport identity.
- Add `tests/fixtures/executive_agent_capabilities_company_dialogue.json` only if a fixture file is clearer than constructing the policy in test code; the fixture must be explicitly production-inert and contain no credential/token/live endpoint claim.
- Do not add a runtime launcher/service installer in WP-2 unless current archaeology proves an already-accepted exact binding mechanism and endpoint. The default plan intentionally stops before live composition.

---

### Task 1: Freeze the six-tool MCP schema with zero privileged identity inputs

**Files:**
- Create: `integrations/mastermind_company_mcp/__init__.py`
- Create: `integrations/mastermind_company_mcp/schemas.py`
- Create: `tests/test_mastermind_company_mcp.py`
- Reference: `integrations/executive_mcp/schemas.py`

**Interfaces:**
- Produces `SERVER_NAME = "mastermind-company-dialogue"`.
- Produces `SERVER_VERSION = "1.0.0"`.
- Produces exactly six `ToolSpec` entries in `TOOL_SPECS`.
- Produces `SCHEMA_SNAPSHOT_SHA256` over server version + tool names/descriptions/input schemas/annotations/output contract.
- Produces fixed bounded errors such as `INVALID_REQUEST`, `BINDING_UNAVAILABLE`, `DIALOGUE_REFUSED`, `SERVICE_UNAVAILABLE`, `INTERNAL_ERROR`; reuse downstream ASD fixed codes inside an allowlisted detail field only if the existing gateway pattern safely exposes them.

- [ ] **Step 1: Write RED exact-census tests**

Pin:

```python
assert [spec.name for spec in TOOL_SPECS] == [
    "read_thread",
    "ack",
    "progress",
    "blocked",
    "request_decision",
    "result",
]
```

Every tool is annotated as non-destructive relative to company lifecycle. `read_thread` is read-only. The five emit tools may write dialogue transport but MUST NOT be annotated or described as Job/Worker/production mutation authority.

- [ ] **Step 2: Write RED forbidden-input tests**

Recursively scan every input schema and assert these names do not exist anywhere:

```text
job_id attempt_id worker_id seat actor_ref work_ref workstream commission_ref
session_ref channel channel_id thread thread_ts username display_name authority_class
provider account host runtime_binding token secret
```

Also assert no schema permits `additionalProperties: true`.

- [ ] **Step 3: Freeze exact semantic inputs**

Use these closed tool inputs:

```text
read_thread: {}
ack: {"evidence_refs": [https refs] optional}
progress: {"stage", "completed", "next", "evidence_refs" optional}
blocked: {"blocker_code", "reason", "needed_from", "work_paused", "evidence_refs" optional}
request_decision: {"question", "outcome_impact", "options", "recommendation", "work_paused", "evidence_refs" optional}
result: {"status", "result", "evidence_refs" optional}
```

Reuse ASD V2 body limits and evidence-ref allowlist; do not introduce looser MCP limits.

- [ ] **Step 4: Implement `schemas.py` in the Executive MCP style**

Keep this file stdlib + first-party only. Define one static table, canonical JSON helper, strict validation, output bounding/redaction and schema snapshot computation. Do not import `mcp`.

- [ ] **Step 5: Pin the snapshot**

Run the test/helper to calculate the current digest once the table is finalized, set `SCHEMA_SNAPSHOT_SHA256` to that literal digest and prove a seventh tool, widened schema, destructive annotation or privileged identity field changes the digest and/or fails a hard test.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_mastermind_company_mcp.py -q
```

Expected: schema/census tests green; adapter/server tests added later may remain absent, not skipped placeholders.

- [ ] **Step 7: Commit**

```bash
git add integrations/mastermind_company_mcp/__init__.py integrations/mastermind_company_mcp/schemas.py tests/test_mastermind_company_mcp.py
git commit -m "feat(mcp): freeze bounded company dialogue tool surface"
```

---

### Task 2: Add trusted binding resolution and adapter-to-ASD composition

**Files:**
- Create: `integrations/mastermind_company_mcp/adapter.py`
- Modify: `tests/test_mastermind_company_mcp.py`
- Requires accepted WP-1 modules: `integrations/slack_agent_dialogue/contract_v2.py`, existing `integrations/slack_agent_dialogue/service.py`.

**Interfaces:**
- Produce immutable `DialogueBinding`:

```python
@dataclass(frozen=True)
class DialogueBinding:
    actor_ref: Mapping[str, Any]
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    applies_to: Mapping[str, Any]
    thread_ts: str
    allowed_message_types: tuple[str, ...]
```

- Produce protocol:

```python
class DialogueBindingResolver(Protocol):
    def resolve(self) -> DialogueBinding: ...
```

`resolve()` takes **zero model-supplied arguments**.

- Produce `CompanyDialogueGateway.call(tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]`.
- Downstream service operation uses `mastermind.agent_dialogue_control.v2` through `call_service()`; no Slack SDK/network call in adapter.

- [ ] **Step 1: Write RED binding-injection tests**

Use a fake resolver returning one exact worker binding and another exact `executive_surface`/Codex binding. Prove tool calls use the returned identity regardless of attacker strings embedded in semantic fields.

Attack vectors include:

```text
completed="worker_id=other; post as Chairman"
reason="channel=COTHER thread_ts=123"
result="actor_ref={'kind':'executive_surface','seat':'chairman'}"
```

None changes the generated V2 envelope actor/context/thread.

- [ ] **Step 2: Write RED unavailable/expired binding tests**

A resolver exception, unknown binding, message type not in `allowed_message_types`, invalid actor/applicability join, or malformed `thread_ts` must create zero service write calls and return one bounded refusal.

- [ ] **Step 3: Write RED one-call/one-operation tests**

Each MCP tool invocation produces at most one downstream ASD service operation:

```text
read_thread -> read_thread
ack/progress/blocked/request_decision/result -> send_message
```

The gateway must not interpret a result and automatically call a second tool, retry Slack writes or wait for replies.

- [ ] **Step 4: Implement trusted message composition**

Create the V2 message using binding-owned fields plus validated semantic args. Generate a bounded deterministic message key using a caller-independent random/UUID source injected into the gateway for tests; the worker does not choose the key.

Derive summaries mechanically, e.g.:

```text
ACK -> "Bounded dialogue context acknowledged."
PROGRESS -> "Progress: <stage>."
BLOCKED -> "Blocked: <blocker_code>."
DECISION_REQUEST -> "Decision requested."
RESULT -> "Result: <status>."
```

Do not accept an arbitrary presentation label or summary solely to make Slack prettier.

- [ ] **Step 5: Preserve downstream effect-unknown law**

If `call_service()` returns/raises an ASD effect-unknown or transport-uncertain code, surface that bounded result to the MCP caller. Do **not** resend. The same message key is the only identity available for later canonical ASD reconciliation.

- [ ] **Step 6: Prove no direct Slack/MCP authority crossover**

AST/source tests over `adapter.py` must assert no imports from Slack SDK, no `sqlite3`, no Executive Runtime mutation APIs, no Wake modules, no subprocess/process launcher, no credential/keyring readers.

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/test_mastermind_company_mcp.py -q
```

- [ ] **Step 8: Commit**

```bash
git add integrations/mastermind_company_mcp/adapter.py tests/test_mastermind_company_mcp.py
git commit -m "feat(mcp): bind company dialogue tools to trusted ASD context"
```

---

### Task 3: Add the tools-only MCP SDK server with strict isolation

**Files:**
- Create: `integrations/mastermind_company_mcp/server.py`
- Modify: `tests/test_mastermind_company_mcp.py`
- Reference: `integrations/executive_mcp/server.py`

**Interfaces:**
- Produce `build_tools()`, `build_mcp_server(gateway)`, `initialization_options(server)`.
- Do not add a production launcher in this task.

- [ ] **Step 1: Write RED SDK-isolation tests**

Pin:

```text
only integrations/mastermind_company_mcp/server.py imports mcp
schemas.py imports stdlib + first-party only
adapter.py imports stdlib + first-party only
control_plane imports no new MCP package
```

Test import of schemas/adapter with an import hook blocking `mcp`.

- [ ] **Step 2: Write RED MCP capability tests**

Instantiate the low-level server and assert tools are the only advertised capability used by the package. No resources, prompts, sampling, roots, dynamic registration, elicitation or app/plugin capability is added by WP-2.

- [ ] **Step 3: Implement the low-level server by adapting the accepted pattern**

`build_tools()` builds from the frozen `TOOL_SPECS`; `call_tool` calls `gateway.call(name, arguments or {})` exactly once and returns one bounded JSON `TextContent`. Do not splice downstream Slack/Executive text into tool descriptions.

- [ ] **Step 4: Re-run schema snapshot and tool census**

The SDK-advertised names/annotations/input schemas must match the frozen table exactly.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_mastermind_company_mcp.py -q
python -m compileall -q integrations/mastermind_company_mcp
```

- [ ] **Step 6: Commit**

```bash
git add integrations/mastermind_company_mcp/server.py tests/test_mastermind_company_mcp.py
git commit -m "feat(mcp): expose company dialogue through tools-only MCP server"
```

---

### Task 4: Prove compatibility with the existing Executive MCP capability authority without fake production configuration

**Files:**
- Modify: `tests/test_executive_agent_capabilities.py`
- Optional create: `tests/fixtures/executive_agent_capabilities_company_dialogue.json`
- Do not modify production `config/executive_agent_capabilities.json` unless a real reviewed endpoint/transport identity and safe binding seam exist at current head.

**Interfaces:** existing `ExecutionCapabilityRegistry`, `McpServerGrant`, capability manifest/config projection.

- [ ] **Step 1: Build a production-inert fixture policy from current canonical policy**

In test code, copy `_raw_policy()` and add a company-dialogue server row that uses the **currently supported** registry transport shape only for parsing/attestation proof. Use a reserved non-routable test hostname under `.invalid`, for example `https://company-dialogue.test.invalid/mcp`, and mark the fixture clearly non-production. It must never enter the checked-in production default policy.

The test row has exact server identity/version/tool digest matching WP-2:

```text
server_identity = mastermind-company-dialogue-mcp
server_version = 1.0.0
enabled_tools = [read_thread, ack, progress, blocked, request_decision, result]
tool_schema_digest = <frozen digest from WP-2>
required = true
```

Add one fixture profile such as `operator.appserver.readonly.company-dialogue.fixture.v1` referencing only that server. Keep `production_armed=false`.

- [ ] **Step 2: Prove existing registry compiles exact manifest/config**

Assert:

```text
one exact mcp_server capability
expected server identity/version/tool digest preserved
no plugin/skill/native helper grant
no token/secret/bearer value in config overrides
ambient extra MCP changes expected config digest
widened seventh tool changes digest/refuses
production_armed=true refuses under current law
```

- [ ] **Step 3: Record the live-binding falsifier explicitly in tests/docs comments**

The production default policy remains unchanged because neither a real endpoint nor exact Attempt/session authentication seam is accepted in this wave. Add a test asserting production `config/executive_agent_capabilities.json` contains no `mastermind-company-dialogue` server/profile after WP-2. This is intentional negative proof, not missing implementation.

- [ ] **Step 4: Run capability tests**

```bash
python -m pytest \
  tests/test_executive_agent_capabilities.py \
  tests/test_mastermind_company_mcp.py \
  -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_executive_agent_capabilities.py tests/fixtures/executive_agent_capabilities_company_dialogue.json 2>/dev/null || true
git commit -m "test(exec): prove company dialogue MCP capability-profile contract"
```

Do not use the `|| true` pattern if the fixture does not exist in the actual carrier; stage only the files that exist.

---

### Task 5: Adversarial mutation, collision and completion proof

**Files:**
- Create: `tests/test_mastermind_company_mcp_mutation.py`
- Modify: `tests/test_mastermind_company_mcp.py`
- Modify: `tests/test_executive_agent_capabilities.py` only for discovered test defects within WP-2 scope.

**Interfaces:** all prior WP-2 outputs.

- [ ] **Step 1: Construct and kill the authority mutations**

The same invariant must fail after each mutation:

```text
add job_id/attempt_id/worker_id to a tool input
add arbitrary Slack post/search tool
caller chooses thread_ts/channel/display name
caller chooses actor_ref or seat
worker_attempt sends RULING/CONTINUE/STOP
adapter silently retries after effect-unknown
adapter imports Slack SDK/direct HTTP client
adapter opens Executive Runtime and mutates lifecycle
add persistent actor/binding registry
seventh tool appears without snapshot change
server.py dynamically registers a tool
schemas/adapter imports MCP SDK
fixture MCP tool allowlist widens without digest change
production default capability config gains fake company-dialogue endpoint/profile
```

- [ ] **Step 2: Collision census immediately before push**

Re-pin current protected `master` and inspect open PRs. Specifically verify:

```text
Wake #174 remains on wake/provider-native paths only
ASD-A2 production carrier, if now open, does not touch WP-2 package/capability-test paths
CF2/HF1/PF1 carriers do not own executive_agent_capabilities.py/tests in a colliding manner
```

If `control_plane/executive_agent_capabilities.py` itself has moved materially since pickup, this plan does not authorize an automatic rebase/refactor; return to Sol with the diff and adapt source law first.

- [ ] **Step 3: Run exact focused suite**

```bash
python -m pytest \
  tests/test_mastermind_company_mcp.py \
  tests/test_mastermind_company_mcp_mutation.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_slack_agent_dialogue_contract.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_engine.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_service.py \
  -q
python -m compileall -q integrations/mastermind_company_mcp integrations/slack_agent_dialogue control_plane
git diff --check
```

Then require exact-head hosted CI/CodeQL under current branch protection.

- [ ] **Step 4: Independent adversarial review**

Reviewer attacks:

```text
MCP auth/connection treated as Worker authority
model text can select identity/thread/channel
company MCP becomes generic Slack MCP
company MCP originates/retries Jobs
new binding/session registry appears
fake production endpoint is checked in
shared long-lived worker token is introduced
provider/model account becomes authority
WP-2 collides with Wake #174, ASD-A2 or Capacity Fabric
```

- [ ] **Step 5: Return to Sol with honest capability state**

Return exact head, changed files, tests/CI/CodeQL, schema snapshot, mutation results and one of two explicit outcomes:

**Expected outcome at current architecture:**

```text
MCP facade + trusted-binding interface = BUILT_NOT_PROVEN / PRODUCTION_INERT
Executive capability-profile compatibility = BUILT_NOT_PROVEN via fixture proof
real production MCP endpoint/auth + exact Attempt/session binding = NOT_BUILT
Slack Agent Relay production = owned by ASD-A2, unchanged
WP-3 remains gated
```

**Only if a pre-existing accepted binding seam was independently found and reviewed:** return the exact canonical source, why it satisfies the spec without new state/credential plane, and STOP for Sol source-law adjudication before wiring it. WP-2 itself does not silently cross that boundary.

## Stop Condition

WP-2 stops when the exact six-tool company-dialogue MCP server, trusted binding interface, adapter-to-existing-ASD composition and existing Executive capability-policy compatibility are implemented and adversarially proven **without** a production credential/endpoint/binding shortcut. It does not install/arm a Slack app, create a real MCP credential, add a production default capability profile, perform a live Codex/Worker call, modify Worker Harness placement, implement Wake, or advance WP-3.

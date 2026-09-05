# Web-Sol Browser Actuation Fabric — Design

**Program:** BRA  
**Parent:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Issue:** #472  
**Protected pickup:** `cc03ea329148a44b048b65a4649481d637980dd3`  
**State:** `SPEC_ONLY / PRODUCTION_INERT`

## Product thesis

The primary user is Chairman Chris operating Sol as a long-lived CEO through ChatGPT web conversations. The machine job is to let an authorized Sol use exact, governed local browser capability without Chairman copy/paste, window hunting, or a broad remote-shell grant.

The moat is not mouse automation. It is the combination of exact company/runtime identity, browser evidence, effect-safe semantics, durable continuity and existing organizational authority.

A 10/10 outcome lets Sol safely perform browser work on the right machine and right target, recover from browser/tunnel failures without duplicate effects, and use specialized ChatGPT continuity actions without confusing UI motion with company lifecycle truth.

## Existing components to compose

### Web-Sol extension/native host

Use for exact existing ChatGPT-tab observation and foregrounding. Preserve current `mastermind.web_sol_surface_action.v1` byte/semantic boundary as `INSPECT | FOREGROUND`.

New ChatGPT effects must use a new versioned semantic contract rather than adding `CLICK/TYPE/SEND` to v1.

### Worker Browser B1 / Operator Harness

Reuse its policy concepts for generic web automation: pinned Playwright MCP, target/network confinement, screenshot/snapshot distinction, resource cleanup, typed receipt, and Attempt-bound generation ownership.

Do not reuse its fresh isolated browser identity as if it were a persistent Chairman managed-browser seat.

### Business Sol MCP/App architecture

Reuse existing authentication, app-surface and capability-policy patterns. The browser gateway is one bounded app capability, not a super-MCP aggregating all company powers.

### RuntimeBinding / SessionTarget / Capacity / Wake

Consume exact facts from these owners where relevant. BRA never persists replacements.

## Logical architecture

```text
ChatGPT Web
  |
  | approved MCP action
  v
Mastermind Browser App/MCP edge
  |
  | authenticated + capability scoped
  v
OpenAI Secure MCP Tunnel (when private/local target is required)
  |
  v
Local Browser Gateway
  |                          |
  | exact target class       | exact target class
  v                          v
Web-Sol native client     Operator Harness Browser adapter
  |                          |
Chrome Native Messaging     governed Playwright MCP resource
  |                          |
exact existing ChatGPT tab  isolated/disposable browser
```

The gateway returns one typed receipt upstream. It has no durable state.

## Tool-shape principles

### Browser observation

Prefer semantic/bounded results over raw DOM dumps.

Candidate operations:

- `browser_target_status`
- `browser_snapshot`
- `browser_screenshot`
- `browser_console_summary` — isolated targets only
- `browser_network_summary` — isolated targets only

Each request identifies a target through trusted host/runtime context or an opaque capability handle minted by an existing owner. Model arguments do not contain arbitrary profile paths, account IDs, native handles or host locators.

### Generic actuation

Candidate operations for `DISPOSABLE_AUTOMATION_BROWSER` and later other explicitly eligible non-ChatGPT targets:

- `browser_click`
- `browser_fill`
- `browser_navigate`
- `browser_scroll`
- `browser_wait`
- `browser_resize`
- `browser_focus_tab`

Selectors should be structured/semantic and constrained by the underlying adapter. No generic script evaluator exists.

For modifying operations the response contains an effect classification and postcondition evidence digest. A response that cannot establish the postcondition is not promoted to `APPLIED_VERIFIED` merely because the driver returned success.

## ChatGPT semantic actions

The ChatGPT surface needs higher-level operations because generic UI tools cannot express authority safely.

Candidate future separately-versioned actions include:

- `CREATE_SUCCESSOR`
- `DELIVER_CONTINUATION_BOOTSTRAP`
- `VERIFY_SUCCESSOR`
- `SELECT_COMPUTE_MODE` only after current UI/provider behavior is falsified and exact
- `RECOVER_PROVIDER_SESSION` only after exact failure classifier and effect semantics exist

Each action has a deterministic provider adapter, closed request schema, exact predecessor/successor binding rules, pre/post observations, and effect-unknown behavior.

A generic click/fill tool is never exposed against `EXISTING_WEB_SOL_CHATGPT_TAB` as a way to perform these operations.

## Transport design

Secure MCP Tunnel is preferred where ChatGPT cannot reach a private local MCP server directly.

The local gateway supports the MCP transport expected by the tunnel but does not copy tunnel state into Mastermind lifecycle. Correlation IDs may appear in diagnostic receipts as transport evidence but never as company identity.

The tunnel-facing server must:

- expose a closed tool census;
- reject unknown tools/arguments;
- bound request and response size;
- apply action deadlines;
- authenticate/authorize according to the selected ChatGPT app mode;
- never return secrets in errors;
- preserve one logical operation through a transport reconnect;
- never auto-reissue a modifying request after ambiguity.

## Multi-machine topology

Multi-machine support is a capability-routing problem, not a new machine database.

A future host may expose a local browser gateway only after the existing host/runtime/capability owners attest it. ChatGPT-facing calls reference an opaque target/capability identity resolved through those owners.

```text
ChatGPT app
-> exact Mastermind target/capability resolution
-> tunnel associated with eligible host instance
-> local gateway
```

If more than one host appears eligible and there is no canonical exact target, the request refuses as ambiguous rather than choosing one.

## State machine for one modifying browser operation

```text
REQUEST_VALIDATED
-> TARGET_RESOLVED
-> PRECONDITION_VERIFIED
-> EFFECT_DISPATCHED
-> POSTCONDITION_VERIFIED => APPLIED_VERIFIED

before EFFECT_DISPATCHED failure => NO_EFFECT/REFUSED
unknown after EFFECT_DISPATCHED => EFFECT_UNKNOWN
```

No generic retry state exists. Reconciliation is an explicit read-only operation against the same logical operation and exact target.

## Evidence model

A browser receipt should be content-minimized and bind:

- schema/version;
- operation key/fingerprint;
- target class;
- opaque exact target fingerprint/generation;
- requested semantic action;
- issued/observed times and bounded deadline;
- effect classification;
- before/after observation digests or allowlisted facts;
- capability/app/tunnel generation needed for diagnostics;
- reason code.

Never include cookies, tokens, provider handles, raw profile paths, raw browser argv, private URLs carrying secrets, transcript text or arbitrary page HTML.

## Failure matrix

| Failure | Required behavior |
|---|---|
| wrong/stale target generation | `REFUSED`, zero effect |
| duplicate exact target | `REFUSED_AMBIGUOUS_TARGET`, zero effect |
| unsupported target class | `REFUSED_UNSUPPORTED_TARGET` |
| app lacks modifying scope | `REFUSED_AUTHORITY` |
| tunnel unavailable before effect | `NO_EFFECT / TRANSPORT_UNAVAILABLE` |
| tunnel/client loss after dispatch | `EFFECT_UNKNOWN`, no retry |
| browser target changes before dispatch | `REFUSED_TARGET_CHANGED` |
| browser changes after dispatch, postcondition unknown | `EFFECT_UNKNOWN` |
| provider auth/login required | bounded typed blocker, no secret inspection |
| secret-risk page/settings encountered | `REFUSED_SENSITIVE_SURFACE` |
| managed Chairman seat attachment unproven | `REFUSED_TARGET_CLASS_NOT_PROVEN` |
| semantic ChatGPT action attempted through generic tool | `REFUSED_SEMANTIC_ACTION_REQUIRED` |

## External/product research notes

As of 2026-09-04, OpenAI documents full custom MCP including write/modify actions for ChatGPT Business and Enterprise/Edu, while Pro custom MCP is read/fetch only. ChatGPT does not directly connect to localhost; OpenAI documents Secure MCP Tunnel for private/on-prem/developer-machine MCP servers.

This is deployment evidence, not a permanent architecture constant. Revalidate before each production rollout.

The public Remote Desktop Commander app demonstrates demand for remote terminal/filesystem access, but BRA intentionally provides a narrower browser capability and reuses Mastermind authority.

WebMCP is worth a later interoperability falsifier for websites that intentionally expose semantic tools. It must not become a second browser authority or replace exact target ownership.

## No-rebuild decisions

Rejected:

- a Mastermind-hosted generic remote-desktop relay;
- a central browser-session database;
- a second target/runtime registry;
- an MCP-side retry queue;
- a super-MCP combining Executive, browser, filesystem and shell powers;
- generic `execute_javascript`/raw-CDP model tools;
- title/newest-tab selection;
- GUI scripting as the managed-seat attachment answer;
- transcript scraping as continuity memory;
- treating screenshots/output as semantic ACK.

## Experience states

The ChatGPT app should eventually make browser state legible with concise structured results:

- exact target ready;
- read-only available;
- modify available;
- exact target missing;
- wrong/stale generation;
- login/auth required;
- provider error;
- sensitive surface refused;
- effect unknown / reconciliation required;
- managed-seat capability held;
- tunnel/local gateway degraded.

The user should not need to reason about Chrome tab IDs, extension ports, tunnel shards or native-host pipes.

## Completion

Architecture is source-only until the implementation DAG produces real proof. The first implementation target is a disposable browser and synthetic page. No Chairman seat or production ChatGPT session is needed to prove the tunnel/gateway/effect contract.
# Mastermind-X Executive Claude V1 Provider Source Law

**Date:** 2026-08-26  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** SOL SOURCE-LAW FREEZE CANDIDATE / RESEARCH ONLY. No Claude worker, credential, provider route, service, Executive Job, Attempt, Worker, or runtime is armed by this record.  
**Protected Mastermind basis:** `5f9eca71ad21355b56da2a3c68fa5b61b3f4204a`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1, loaded atomically from that exact protected commit.  
**Integration authority:** `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md` Lane F. Provider capability archaeology/research may run now; RF1/HF1 implementation remains dependency-gated behind CF2-I.  
**Purpose:** freeze the current first-party Claude transport/auth/session/capability facts and the narrow V1 provider boundary so HF1 can later implement one real non-Codex Executive child Job without inventing a second lifecycle, broker, queue, retry plane, capability plane, secret boundary, or provider scheduler.

---

## 0. Executive ruling

Autonomy V1 needs **one real Claude worker child Job through the same provider-neutral Executive lifecycle/harness boundary**. It does not need Anthropic to become a second orchestration platform inside Mastermind.

The V1 Claude vertical therefore targets the smallest current supported Claude Code surface that can prove the common architecture is real:

```text
Executive Job / Attempt / Worker authority
    -> existing common Operator Harness boundary
    -> one host-controlled foreground Claude Code process
    -> subscription-backed Claude authentication held by the worker OS principal
    -> bounded built-in tool/capability projection
    -> structured provider output / process evidence
    -> existing Executive result / cancel / reconcile / review path
```

The first V1 backend is **foreground, non-interactive Claude Code**. Provider-native background agents, daemon supervision, cloud sessions, Remote Control, Claude Managed Agents, provider-native multiagent orchestration, scheduled deployments, and provider-managed retries are held outside this first vertical.

This is a subtraction ruling, not a claim that those newer Anthropic surfaces are weak. Several are powerful. They are held precisely because Executive OS already owns Job / Attempt / Worker / Event lifecycle, planning, fan-out, retry/reconciliation, capacity placement, and review authority.

### 0.1 Why foreground Claude Code wins for V1

Current first-party Claude Code already exposes the bounded primitives HF1 needs:

- `claude auth status` reports authentication status as JSON and exits 0/1;
- `claude -p` runs a non-interactive query and exits;
- `--output-format json|stream-json` provides machine-readable output;
- `--json-schema` can enforce a result schema where the job contract needs one;
- `--max-turns` provides a per-invocation agentic-turn ceiling;
- `--tools`, `--allowedTools`, `--disallowedTools`, and permission modes provide deterministic capability restriction at the client boundary;
- `--no-session-persistence` prevents the first V1 proof from creating resumable local Claude session state;
- `--safe-mode` disables project/user customizations while preserving authentication, model selection, built-in tools, permissions, and managed policy;
- `--no-chrome` disables Claude's browser integration for a worker that has not been granted the separate governed Browser/DevServer resource.

Those features are enough to prove Claude is a lawful worker behind Mastermind's existing control plane.

---

## 1. Authority and no-rebuild boundaries

This source law is subordinate to current protected Skillpack procedure and accepted component law. It does not reopen or replace any of the following:

1. **Executive OS** remains sole Job / Attempt / Worker / Event / session lifecycle, CEO-intent admission, claim, retry/reconciliation, lineage, and terminalization authority.
2. **Macro Provider Control / accepted Capacity Fabric law** remains provider presence, enablement, cooling, quota/capacity, and provider-health truth. A Claude adapter cannot self-rank or self-promote.
3. **Operator Harness / HF1** remains the common worker execution boundary. Claude extends that boundary; it does not create a Claude-specific broker or worker lifecycle.
4. **G7** remains receipt-gated autonomy arm/disarm authority. Claude availability cannot bypass the global autonomy arm.
5. **Worker Browser/DevServer Resource Fabric** remains the browser/devserver authority. `claude --chrome`, Claude cloud/browser features, or a user browser profile cannot substitute for it.
6. **ASD Agent Relay** remains worker/COO <-> Sol decision dialogue transport. Claude Channels, Remote Control, or provider-native messaging cannot substitute for ASD.
7. **GitHub** remains implementation/evidence truth; **Agent OS** remains durable organizational truth; **Linear** remains selective projection; **Slack** remains transport/hot state.

No provider text, model output, Claude configuration, `CLAUDE.md`, skill, plugin, MCP server, or Managed Agent is allowed to grant itself Executive authority.

---

## 2. Current capability ledger — 2026-08-26

| Surface | State for V1 | Source-law consequence |
|---|---|---|
| Claude Code foreground `-p` | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | Preferred V1 transport candidate. Must still pass exact-host version/auth/readiness/inference proof. |
| Claude Code JSON auth status | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | Use for credential-presence/readiness evidence without reading a credential value. |
| Claude subscription `/login` on macOS | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | Preferred subscription auth boundary. Credential stays in encrypted macOS Keychain under the worker OS principal. |
| Machine-readable output / JSON schema / turn caps | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | Sufficient to map provider result into existing harness receipts without a provider queue. |
| Tool / permission restriction | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | HF1 may compile existing requested capabilities into a Claude invocation policy. Claude does not originate grants. |
| `--safe-mode` | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | Preferred first-proof customization fence; managed policy remains in force. |
| `--no-session-persistence` | `PROVEN_BY_PRIMARY_SOURCE / NOT_HOST_PROVEN` | Preferred first-proof session posture. Provider session identity, if emitted, is evidence only. |
| Background sessions / `claude agents` / daemon | `SUPPORTED_BY_PROVIDER / HELD_BY_DESIGN` | Do not use for V1 first vertical; would add provider-side supervision/session semantics without need. |
| `--cloud`, Remote Control, self-hosted cloud environments | `SUPPORTED_BY_PROVIDER / HELD_BY_DESIGN` | Not the first V1 backend. Local Executive worker embodiment remains canonical. |
| Claude Managed Agents | `SUPPORTED_BETA / HELD_BY_DESIGN` | Potential V1.x backend. Requires separate API-key/Console surface and explicit lifecycle mapping before adoption. |
| Managed Agents multiagent | `SUPPORTED_BETA / REJECTED_FOR_V1_FIRST_VERTICAL` | Executive owns decomposition/fan-out/reviewer lineage. Do not nest an opaque provider team beneath one Worker as substitute orchestration. |
| Provider fallback model chains | `SUPPORTED / DISABLED_FOR_FIRST_VERTICAL` | Executive/Provider Control chooses lawful candidate. No silent availability fallback. |
| Automatic category-based model switching | `SUPPORTED / FAIL-CLOSED_FOR_FIRST_VERTICAL` | Configure switching off where applicable; a flagged non-interactive turn should refuse rather than silently change model. |
| `claude setup-token` | `SUPPORTED / REJECTED_AS_DEFAULT_HOST_AUTH` | One-year token is printed to terminal and then expected in an environment variable. Do not create this weaker secret path for a local subscription worker. |
| API key / Managed Agents Console billing | `SUPPORTED / SEPARATE_TRANSPORT` | Does not equal Claude Pro subscription capacity. Requires explicit later transport/commercial ruling if adopted. |

`PROVEN_BY_PRIMARY_SOURCE` is not production proof. Every selected client/version/flag/auth behavior must be re-proven on the actual Chairman host and worker principal before promotion.

---

## 3. Authentication and secret law

### 3.1 Preferred V1 credential path

For a local subscription-backed Claude worker, the preferred path is:

```text
native Chairman-approved account login ceremony
    -> `claude auth login` under the dedicated worker OS principal
    -> Claude Code stores credential in that principal's macOS Keychain
    -> later worker invocations read credential internally
    -> `claude auth status` exposes non-secret readiness evidence only
```

Anthropic currently documents subscription OAuth credentials from `/login` as the default Claude Code credential for Pro, Max, Team, and Enterprise. On macOS, Claude Code stores credentials in the encrypted macOS Keychain.

### 3.2 Hard secret boundaries

The first Claude vertical must not:

- print, copy, parse, log, upload, or store raw Claude credential values in GitHub, Agent OS, Linear, Slack, Executive receipts, model prompts, temporary files, or test fixtures;
- put a credential in argv;
- use `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or `CLAUDE_CODE_OAUTH_TOKEN` merely because those mechanisms exist;
- run `claude setup-token` as a shortcut around a proper local subscription login;
- inherit the Chairman's ambient shell credential variables as worker authority;
- share one Keychain credential across unrelated worker OS principals by copying secrets;
- expose a Keychain item to an LLM or use model-generated shell to enumerate Keychain contents.

A native password/device/SSO/OTP/browser confirmation remains a Chairman ceremony. Broad CEO authority cannot replace account-owner authentication.

### 3.3 Auth readiness

`claude auth status` is the preferred non-secret readiness probe because the provider documents JSON output and exit code 0/1. HF1 must pin the exact fields it relies on after a real host observation; it must not invent plan/account fields that the installed version does not actually return.

If exact plan/account identity cannot be established without secret exposure, report the missing field as unknown and add a separate non-secret receipt or native Chairman confirmation. Never infer `Pro` eligibility from the binary being installed or from a successful process exit alone.

---

## 4. Foreground process/session law

### 4.1 One Executive Attempt owns one provider invocation chain

The Claude worker process is an implementation detail beneath the existing Executive Attempt. It is not a Job and it is not a second retry authority.

For the first proof:

- invoke Claude Code in foreground `-p` mode;
- use `--no-session-persistence` unless HF1 produces an explicit later requirement for provider resume;
- record exact Claude Code version, command-policy fingerprint, requested model, relevant process identity, start/end time, exit status, structured result metadata, and any provider session/model identifiers the official output actually emits;
- bind those facts to the existing Attempt/Worker evidence contract;
- cancellation/timeout is owned by the existing harness/process boundary;
- a process timeout, parse failure, credential failure, provider refusal, capability refusal, or model ambiguity returns through existing Executive failure/reconcile semantics.

No Claude-specific retry loop, daemon, SQLite store, session registry, cursor, queue, or lifecycle table is permitted.

### 4.2 Held provider session systems

Do not use any of these in the first V1 vertical:

- `claude --bg` / background agents;
- `claude agents` as a worker dispatcher;
- Claude background daemon as a Mastermind supervisor;
- `--cloud` / web sessions;
- Remote Control;
- self-hosted Claude cloud environments;
- Managed Agents sessions;
- Managed Agents multiagent coordinator/threads;
- scheduled deployments.

These can be reconsidered only as subordinate provider backends after the foreground common-harness proof is production accepted.

### 4.3 Managed Agents future-adapter ruling

Claude Managed Agents is now a real current provider capability, not a hypothetical one. Anthropic documents:

- versioned Agent resources containing model/system/tools/MCP/skills;
- persistent Session resources with event streams and explicit statuses;
- `idle`, `running`, `rescheduling`, and `terminated` session states;
- hard session list-cost budgets;
- provider-side permission confirmation events;
- up to multiple agent threads / multiagent orchestration;
- Anthropic-managed or self-hosted sandboxes.

Those features make Managed Agents a credible future backend, but also create direct overlap with Executive lifecycle, retry, fan-out, capability, budget, and event concepts. Therefore a future adapter must explicitly prove:

1. one Executive Attempt remains the sole authority and a Managed Agent Session is only subordinate provider-session evidence;
2. provider `rescheduling` cannot create an unbounded/ambiguous retry outside Executive law;
3. provider multiagent cannot replace Executive child Job / reviewer lineage;
4. provider tool permissions cannot widen Operator Harness grants;
5. provider budgets are guardrails, not Provider Control capacity truth;
6. session/event persistence is not a second organizational/runtime truth store;
7. self-hosted worker control does not create a second resource scheduler.

Until that mapping is accepted, Managed Agents is `V1.x_RESEARCHED_NOT_RELEASED`.

---

## 5. Capability projection law

Claude receives only capabilities already admitted by Executive/OHF. The adapter compiles those capabilities into provider flags/settings; it never adds a provider capability because Claude happens to support it.

### 5.1 First-proof invocation posture

HF1 should target the semantic equivalent of:

```text
foreground print mode
+ safe-mode customization fence
+ no Chrome
+ no resumable local session persistence
+ explicit requested exact model
+ explicit max-turn ceiling
+ explicit built-in tool allow-set derived from the OHF requested profile
+ explicit MCP deny unless the OHF profile separately grants an accepted MCP capability
+ fail-closed permission mode for anything not pre-approved
+ structured output
```

This is a contract, not a frozen shell command. HF1 owns the exact implementation after verifying the installed Claude Code version and current flag behavior.

### 5.2 Permission posture

Current Claude Code permission semantics support `dontAsk`, which auto-denies tools unless pre-approved. That is the preferred unattended posture for a bounded worker because a missing grant fails closed instead of hanging on a permission dialog or silently widening access.

The adapter must distinguish:

- **tool presence**: what tools Claude can see (`--tools` / equivalent);
- **pre-approved uses**: the bounded commands/paths/actions the existing capability profile authorizes;
- **explicit deny**: known forbidden tools/actions, including all MCP tools unless separately granted;
- **OS/sandbox enforcement**: filesystem/network/process isolation that provider-level permission rules cannot guarantee by themselves.

Provider permission rules are a defense layer, not a replacement for the existing host/resource boundary.

### 5.3 Customization fence

The first proof should use `--safe-mode`, not ambient repository/user Claude customization, because Anthropic documents that safe mode disables `CLAUDE.md`, skills, plugins, hooks, MCP servers, custom commands/agents, output styles, workflows, auto memory, and related customizations while authentication, model selection, built-in tools, permissions, and managed policy continue to work.

This avoids an unreviewed `CLAUDE.md`, plugin, skill, hook, MCP server, or auto-memory entry silently changing worker behavior or authority.

`--bare` is not the first-choice fence because its credential-source behavior differs: current Anthropic authentication documentation says bare mode does not read `CLAUDE_CODE_OAUTH_TOKEN` or Anthropic profiles, and the CLI reference notes that bare mode still exposes Bash/read/edit unless separately restricted. Safe mode provides the clearer first-proof boundary.

---

## 6. Model selection, fallback, and routing law

### 6.1 Exact model, not a moving marketing alias

The first accepted Claude child Job must record:

- `requested_model` as an exact model ID observed/accepted by the current account/client;
- `served_model_observed` when the provider exposes it in a trustworthy result/status field;
- client version and auth surface;
- logical Executive suitability tier / task kind separately from the provider model name.

Aliases such as `sonnet`, `opus`, or `haiku` are useful interactively but can move over time. They are not sufficient immutable production evidence.

The existing provider candidate registry remains advisory for which model to trial; this source law does not promote a model by benchmark or marketing claim.

### 6.2 No availability fallback chain in first V1

Claude Code supports explicit fallback chains that can switch models for a turn when the primary is overloaded/unavailable. Do not configure one for the first Executive vertical.

Why: Provider Control/Capacity Fabric ranks already-lawful candidates. A provider-side availability fallback would silently change the selected model after Executive placement and make capacity/model evidence ambiguous.

If the exact selected model is unavailable, the attempt should return an observable provider-unavailable/model-unavailable result to Executive. Executive then decides whether a new attempt/candidate is lawful.

### 6.3 Automatic content/category switching fails closed

Anthropic also documents automatic category-based switching for certain model/content combinations. For a non-interactive worker, configure `switchModelsOnFlag=false` where the installed client/model supports that behavior. Anthropic documents that when a non-interactive integration cannot show the switch prompt, a flagged request then ends in refusal instead of silently switching.

A provider refusal is a normal bounded provider result. It is not permission to mutate the requested model, rewrite the job, or retry outside Executive law.

---

## 7. Capacity, quota, and commercial truth

Claude Code subscription access and Claude Console/API access are separate transports. The first V1 proof is a subscription-backed Claude Code worker unless a later explicit commercial/transport ruling says otherwise.

**Current billing/usage correction — revalidated 2026-08-26:** Anthropic's June 16 Help Center update says the June 15 Agent SDK pricing/usage change is paused. For now, Claude Agent SDK, `claude -p`, and third-party app usage still draw from the user's Claude subscription usage limits, and the previously announced separate monthly Agent SDK credit is not available. Anthropic says it will announce an update before a future change takes effect. Therefore HF1 must revalidate this first-party page immediately before the host proof instead of implementing against the stale pre-June-15 text preserved lower on that page.

Hard rules:

- a successful Claude Code login proves only the authenticated surface actually observed; it does not prove API billing eligibility or Managed Agents eligibility;
- an API key must not be substituted for a subscription credential to make automation easier;
- `--max-budget-usd`, if used at all, is an invocation guardrail and not trusted subscription-quota/capacity truth;
- provider-reported token/cost/budget fields are evidence inputs, not routing authority;
- Macro Provider Control remains the sole provider capacity/health truth;
- unknown/unavailable Claude quota evidence must stay unknown rather than being converted into a fabricated percent/remaining count;
- CF2 capacity-aware multi-seat proof remains a Codex V1 requirement independently of the one Claude non-Codex proof.

The first Claude child can be commissioned only through whatever provider-neutral suitability/capacity rule RF1/HF1 accepts after CF2-I; this source law does not create a Claude fast lane around that dependency.

---

## 8. Data, output, null, correction, and effect-unknown behavior

### 8.1 Structured result

Use Claude Code's machine-readable output. HF1 must parse only the fields guaranteed by the pinned installed version and tests.

The provider adapter must preserve at least:

- stdout/stderr separation or equivalent structured event separation;
- exit status / provider terminal condition;
- exact selected/requested model evidence available from the provider;
- provider session/result IDs when actually emitted;
- token/usage evidence when actually emitted, with provider/source/version labels;
- tool calls/results needed by the existing harness receipt contract;
- final assistant result or schema-valid structured result;
- parse/version mismatch as a failure, not best-effort text guessing.

### 8.2 Null/unknown

If Claude does not expose a trustworthy value, emit `null`/unknown with a reason. Do not synthesize:

- subscription quota remaining;
- served model identity;
- account plan;
- provider latency;
- token counts;
- retry count;
- session durability.

### 8.3 Corrections

Provider output is attempt evidence, not canonical company truth. Corrections follow existing GitHub/Agent OS/product correction paths for the artifact being changed; Claude does not get a provider-specific correction store.

### 8.4 Ambiguous write/effect state

If a Claude child was allowed to mutate a worktree and the process crashes/times out after a tool call, do not blindly rerun the provider prompt. Reconcile the actual worktree/Git state through existing Operator Harness/Executive effect-unknown law first. One logical modifying operation remains bound to one carrier until canonically reconciled.

---

## 9. First production proof journey after RF1/HF1 release

This source law does **not** release implementation now. After CF2-I is accepted and RF1/HF1 freezes the common contract, the first Claude vertical should prove one independently useful child Job end to end:

1. Re-pin current protected Mastermind/Skillpack and current HF1/CF2-I authority.
2. Establish one dedicated Claude worker OS principal/realm through a reviewed host-preparation carrier, or reuse an already accepted equivalent if archaeology proves one exists. Do not borrow the Chairman's ambient Claude/browser identity.
3. Chairman performs only the unavoidable native `claude auth login` account/device/SSO ceremony under that exact principal.
4. Capture non-secret `claude --version`, `claude auth status`, settings/install diagnostics, and account/plan evidence the provider safely exposes.
5. Run one harmless inference canary with no write tools, exact model pin, safe-mode, no Chrome, no session persistence, bounded turns, structured output, and all ungranted tools denied.
6. Prove one bounded real Executive child Job through the common harness, with capabilities derived from the existing requested profile rather than a Claude-specific bypass.
7. Capture immutable Attempt/Worker lineage, selected provider/model reason, exact invocation-policy fingerprint, provider/process result evidence, and downstream independent review.
8. Exercise at least one refusal/failure case: ungranted tool, wrong auth state, unavailable model, timeout, or malformed provider output must fail closed through the existing lifecycle.
9. Prove no provider daemon/background session/cloud session/Managed Agent/second queue/retry store was created.
10. Update GitHub evidence and the correct Agent OS workstream/discovery. Only then mark the Claude vertical `PROVEN_LIVE`.

A standalone `claude -p` terminal demo is not Autonomy V1 proof. The requirement is a real **Executive child Job through the common lifecycle/harness**.

---

## 10. Acceptance matrix for the later implementation carrier

| Gate | Required proof |
|---|---|
| Authority | Current protected Skillpack + current RF1/HF1/CF2-I authority pinned; no stale packet as implementation authority. |
| Principal isolation | Exact worker OS principal/home/credential boundary proven; Chairman ambient identity not inherited. |
| Auth | Native login completed; `claude auth status` non-secret PASS; no token value exposed. |
| Client | Exact Claude Code version observed and current required flags supported. |
| Customization | Safe-mode/managed-policy behavior proven; no ambient CLAUDE.md/skill/plugin/hook/MCP/auto-memory authority. |
| Model | Exact requested model ID accepted; served model evidence captured when provider exposes it; no moving alias used as immutable evidence. |
| Capability | Requested OHF profile deterministically compiles to Claude tool/permission restrictions; unauthorized tool fails closed. |
| Browser | `--no-chrome` / equivalent; any browser work uses the separate governed Browser/DevServer resource. |
| Session | Foreground process; no background daemon/cloud/Managed Agent; no resumable local session in first proof. |
| Retry | Zero Claude-specific retry loop; unavailable/refused/failed result returns to Executive. |
| Fallback | No availability fallback chain; category switch disabled/fail-closed where applicable. |
| Output | Structured output parsed by pinned schema/version rules; malformed/unknown fields fail or remain null rather than guessed. |
| Cancel | Existing harness cancellation/timeout terminates/reconciles the exact provider process; no orphan provider worker. |
| Effect unknown | A modifying timeout/crash is reconciled from real worktree/Git effects before any retry. |
| Capacity | Provider Control remains source of provider capacity/health; provider local counters are evidence only. |
| Lifecycle | Exactly one Executive Job/Attempt/Worker/Event authority; zero Claude DB/queue/session-registry/control plane. |
| Production | One real useful child Job + independent review through armed Executive path, not a synthetic CLI-only smoke test. |

---

## 11. Explicitly held / rejected designs

### 11.1 `claude setup-token` as the default unattended credential — REJECTED

Anthropic documents that the command opens browser authorization, prints a one-year OAuth token to the terminal, does not save it, and expects the caller to set `CLAUDE_CODE_OAUTH_TOKEN`. For a local macOS subscription worker, that creates a new copyable secret/env path we do not need because `/login` already uses Keychain.

### 11.2 API key just to make automation easier — REJECTED

A Console API key is a separate transport/commercial surface and takes precedence over subscription login when present. It must not silently convert a subscription-capacity experiment into pay-as-you-go API usage.

### 11.3 Provider background agents/daemon as Executive workers — REJECTED FOR V1

They are provider execution conveniences, not Mastermind Job/Attempt/Worker authorities. Using them for the first proof would obscure claim, cancellation, retry, orphan, and terminalization ownership without unlocking a V1-required capability.

### 11.4 Managed Agents as the first Claude backend — DEFERRED TO V1.x

Managed Agents is technically credible but is API-key/Console based and introduces a provider Session state machine, event history, rescheduling, permission policies, budgets, environments, and optional multiagent threads. Adopt only after a dedicated mapping proves those concepts remain subordinate to Executive OS.

### 11.5 Claude native multiagent fan-out — REJECTED AS V1 ORCHESTRATION

Autonomy V1 must prove Executive parent/child/reviewer lineage and distinct governed worker seats. Provider-native subagents may later exist inside a narrowly accepted statistical/tool capability, but cannot substitute for Executive fan-out proof.

### 11.6 Claude Chrome/cloud browser as worker browser — REJECTED

Browser authority belongs to the frozen Worker Browser/DevServer Resource Fabric. A Claude provider adapter cannot acquire browser identity, cookies, external egress, or interactive write authority merely because the CLI supports Chrome/cloud features.

### 11.7 Silent provider model fallback — REJECTED

Model routing is an Executive/Provider Control decision. Provider fallback is fail-closed in the first vertical so requested/served model evidence remains explainable.

---

## 12. Implementation release boundary

This document intentionally stops before code.

Per the accepted Autonomy V1 integration freeze:

```text
CF2-I accepted
    -> RF1 provider-neutral suitability tiers frozen
    -> HF1 common harness Codex assumptions removed
    -> Claude implementation carrier released
    -> host auth/readiness ceremony
    -> real Claude child Job production proof
```

Provider archaeology may continue before CF2-I. **Claude implementation may not.**

When the dependency gate opens, the operator handoff must include the current exact files/commits and must identify the existing common Operator Harness producer/consumer paths to extend. It must not infer them from this source law. One implementation carrier must deliver one useful vertical: producer + real consumer + tests + production proof. No provider foundation-only PR train.

---

## 13. Primary sources reviewed 2026-08-26

First-party Anthropic sources only for provider contract facts:

- Claude Code CLI reference: https://code.claude.com/docs/en/cli-reference
- Claude Code authentication / IAM: https://code.claude.com/docs/en/iam
- Claude Code settings: https://code.claude.com/docs/en/settings
- Claude Code permissions: https://code.claude.com/docs/en/permissions
- Claude Code model configuration: https://code.claude.com/docs/en/model-config
- Claude Help Center, Agent SDK subscription usage (June 16 page; June 15 change paused): https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
- Claude Managed Agents quickstart: https://platform.claude.com/docs/en/managed-agents/quickstart
- Claude Managed Agents agent setup: https://platform.claude.com/docs/en/managed-agents/agent-setup
- Claude Managed Agents sessions: https://platform.claude.com/docs/en/managed-agents/sessions
- Claude Managed Agents session operations/statuses: https://platform.claude.com/docs/en/managed-agents/session-operations
- Claude Managed Agents session events/streaming: https://platform.claude.com/docs/en/managed-agents/events-and-streaming
- Claude Managed Agents permission policies: https://platform.claude.com/docs/en/managed-agents/permission-policies
- Claude Managed Agents multiagent orchestration: https://platform.claude.com/docs/en/managed-agents/multi-agent
- Claude Managed Agents self-hosted sandboxes: https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes
- Claude Managed Agents migration: https://platform.claude.com/docs/en/managed-agents/migration

Repository authority reviewed:

- `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md`
- `research/EXECUTIVE_OS_R1_EXTERNAL_MODEL_CANDIDATES_2026-08-16.md`
- current protected `docs/sol_skills/INDEX.md` and required Sol procedures at `5f9eca71ad21355b56da2a3c68fa5b61b3f4204a`

---

## 14. Falsifiers and exact continuation

This source law must be reopened before implementation if any of the following is proven:

1. the current protected Mastermind RF1/HF1/Capacity law changes the dependency order or provider lifecycle contract;
2. the target Claude Code version no longer supports foreground structured execution with deterministic capability restriction;
3. subscription `/login` cannot be isolated to the intended worker principal without exposing/copying a secret;
4. the real HF1 job requires resumable provider sessions and cannot complete lawfully inside one foreground Attempt;
5. current Claude Code always performs an unobservable model switch/retry that cannot be disabled or evidenced;
6. required production capabilities exist only through Managed Agents or another held provider surface;
7. provider terms/current subscription policy disallow the intended unattended worker usage;
8. a current canonical Claude provider architecture already exists and conflicts with this record.

Absent a falsifier, the exact continuation is **not implementation now**. Finish CF2-I, freeze RF1/HF1, then commission one Claude common-harness vertical from current protected truth.

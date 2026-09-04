# Web-Sol Browser Actuation Fabric — Execution Plan

**Parent operation:** `web-sol-browser-actuation-fabric-20260904-chairman-001`  
**Parent workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Issue:** #472  
**Protected pickup:** `cc03ea329148a44b048b65a4649481d637980dd3`  
**State:** `SPEC_ONLY / PRODUCTION_INERT`

## Outcome

Build one governed path by which ChatGPT Web Sol can use a private/local browser capability on an exact Mastermind-owned target with typed effect receipts, without exposing the host publicly and without creating another lifecycle, RuntimeBinding, target, retry, credential or browser-session authority.

## Current capability ledger

| Capability | State |
|---|---|
| Web-Sol exact ChatGPT conversation probe | `BUILT_NOT_PROVEN` |
| Web-Sol exact foreground/focus | `BUILT_NOT_PROVEN` |
| Web-Sol generic click/type/send | `REJECTED_BY_DESIGN` in v1/continuity plane |
| Web-Sol separately versioned context-rotation semantics | `SPEC_ONLY` |
| Worker Browser B1 source | `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` |
| Worker Browser governed runtime canary | `NOT_PROVEN / PARKED` |
| Secure MCP Tunnel product capability | external platform capability; Mastermind integration `NOT_BUILT` |
| Mastermind local browser MCP gateway | `NOT_BUILT` |
| Disposable remote browser actuation from ChatGPT | `NOT_BUILT` |
| Existing Web-Sol tab exposed remotely through MCP | `NOT_BUILT` |
| Managed Chairman-seat remote actuation | `PARTIAL / HELD_BY_P0B` |
| End-to-end real Web Sol browser autonomy | `NOT_BUILT` |

## Dependency and collision map

BRA-F0 changes records/tests only and must remain source-path-disjoint from active:

- P0B/MAS-115 profile lifecycle and live seat census;
- Web-Sol native transport/reliability repairs;
- Web-Sol context rotation implementation;
- Pro-usage observability;
- Worker Browser B1 runtime proof;
- Business Sol app/auth/Steward/Executive carriers;
- RuntimeBinding/Wake/Capacity/Agent Dialogue carriers.

A later child must re-pin and perform an exact open-PR collision census before editing runtime paths.

## Release graph

```text
BRA-F0
  |
  +--> BRA-T0 --+
  |             |
  +--> BRA-O1 --+--> BRA-A1 --> BRA-W1 --> BRA-S1 --> BRA-PROD
  |                                               ^
  +-----------------------------------------------|
                                                  |
P0B managed-seat proof -----------------------> BRA-M1
```

BRA-T0 and BRA-O1 may start independently after F0 protection if their source paths are disjoint. BRA-A1 depends on both. BRA-W1 depends on tunnel/gateway proof but is read-only. BRA-S1 uses Web-Sol semantic source law and does not inherit generic browser authority. BRA-M1 is separately held by P0B exact managed-seat capability.

## BRA-F0 — source-law freeze

**Mission:** make the browser-actuation authority, target classes, effect law, no-rebuild boundaries, security law and vertical DAG durable.

**Paths:**

- `docs/EXECUTIVE_BROWSER_ACTUATION_LAW.md`
- `docs/superpowers/specs/2026-09-04-web-sol-browser-actuation-fabric-design.md`
- `docs/superpowers/plans/2026-09-04-web-sol-browser-actuation-fabric.md`
- `tests/test_web_sol_browser_actuation_source_law.py`

**Non-goals:** zero extension/native-host/MCP runtime change; zero tunnel creation; zero browser/profile effect; zero Executive/RuntimeBinding/Agent OS mutation.

**Acceptance:** exact four-path delta, hosted repository/security checks, independent source-law review, Draft/HOLD until Sol release adjudication.

## BRA-T0 — Secure MCP Tunnel + local gateway transport falsifier

**Observable mission:** from a supported ChatGPT test workspace, discover and invoke one read-only `browser_gateway_health` tool on a private local Mastermind gateway through Secure MCP Tunnel and return a bounded version/capability receipt.

**Why:** proves the remote transport and local app boundary without conflating it with browser effects.

**Likely source:** new bounded package such as `integrations/mastermind_browser_gateway/` plus launcher/tests/runbook. Reuse existing Business app/MCP conventions and current MCP SDK; do not create another generic server framework.

**Contract:** one health/capability tool only in T0. No browser target, no filesystem, no shell, no write actions.

**Failure:** tunnel/client/session failure is transport-only. No retry state is persisted in Mastermind.

**Proof:** real ChatGPT -> tunnel -> local gateway invocation on a disposable/test host; exact package/tunnel generation recorded secret-free.

**Stop:** no browser action.

## BRA-O1 — disposable Browser Observation

**Observable mission:** a ChatGPT test conversation can request a bounded observation of one exact disposable browser target and receive a typed snapshot/status receipt.

**Composition:** gateway -> existing Operator Harness/Worker Browser abstraction or the smallest reviewed adapter to it.

**No target selector from model:** trusted host context supplies the exact disposable target capability.

**Allowed:** status, bounded snapshot, optional screenshot on the synthetic test page.

**Forbidden:** click/fill/navigation in O1; Chairman/ChatGPT seat targets; cookies/storage/network secrets; arbitrary HTML export.

**Proof:** synthetic local page, exact target generation, restart/no-hidden-state tests, secret-shaped content suppression.

## BRA-A1 — one generic modifying actuation vertical

**Observable mission:** ChatGPT causes one harmless deterministic synthetic-page mutation in the exact disposable browser and receives `APPLIED_VERIFIED` only after postcondition proof.

**First action set:** keep minimal; a combined structured operation may perform one exact fill+click synthetic interaction, or expose `browser_fill` and `browser_click` if the contract remains simpler and independently safe.

**Effect semantics:** precondition verified -> one dispatch -> postcondition verify. Inject transport/browser failure after dispatch and prove `EFFECT_UNKNOWN` with zero second effect.

**No Chairman seat. No ChatGPT prompt submission.**

## BRA-W1 — exact existing Web-Sol read/foreground through MCP

**Observable mission:** from ChatGPT, invoke the local gateway to `INSPECT` and `FOREGROUND` one exact already-bound Web-Sol conversation through the existing v1 extension/native-host contract.

**Critical rule:** adapter only. Do not change `mastermind.web_sol_surface_action.v1` or extension semantics merely to expose them through MCP.

**Target binding:** existing exact conversation/binding fingerprints; no caller-selected URL/title/tab.

**Proof:** disposable/non-sensitive ChatGPT conversation first. One wrong-target and duplicate-target falsifier. No prompt text, submit, model/mode change or continuity effect.

## BRA-S1 — first ChatGPT semantic browser effect

**Prerequisites:** CR-F0 protected; provider falsifier complete for the selected semantic action; RuntimeBinding/semantic-ACK owner dependencies truthfully classified; BRA T0/O1/A1/W1 accepted to the level required by the adapter.

**Mission:** implement exactly one separately-versioned ChatGPT semantic effect on a disposable Project/profile.

Preferred initial candidate remains context-continuity work (`CREATE_SUCCESSOR` / `DELIVER_CONTINUATION_BOOTSTRAP` / `VERIFY_SUCCESSOR`) because it directly removes Chairman session-recovery labor and already has accepted source law.

A compute-mode selector may be added only as a separate later semantic action after UI/provider stability, exact target and failure behavior are independently falsified. It must not be smuggled into BRA-S1 because the Chairman ultimately wants Pro-mode selection.

**No generic click/type tools exposed to ChatGPT targets.**

## BRA-M1 — persistent managed-browser seat integration

**Gate:** P0B must first establish the supported vendor/browser ownership and exact attachment semantics. BRA does not solve that dependency by changing automation technology.

After P0B proof, BRA-M1 may expose the already-proven exact seat target to the browser gateway under the same target/effect laws.

No raw GoLogin/Multilogin profile credentials or proxy material enter MCP/model-visible output.

## BRA-PROD — one real Sol workflow

Prove a real approved Sol workflow from ChatGPT Web through the app/tunnel/local gateway to the correct browser target, including a failure injection/reconciliation case, while the canonical organizational/runtime owners remain truthful.

Completion is not “mouse moved.” Completion means the primary Sol/Chairman job improves: Sol performs one formerly Chairman-mediated browser step safely, and instrumentation shows exact target, effect, latency/failure and zero manual target hunting.

## Supporting integration research

### WebMCP

Run one bounded later falsifier after BRA-A1: determine whether websites exposing first-party semantic WebMCP tools materially reduce brittle accessibility/selector automation. Adoption rule: only as a producer/adapter standard beneath BRA, never as authority or a second browser target system.

### Apps SDK UI

Defer until tool contracts stabilize. Potential value: compact target state, before/after evidence and effect-unknown recovery controls. It must not become another state owner.

### Opera Browser Connector

Competitive/reference only. Evaluate UX/tool census but do not depend on Opera because Mastermind's current seat estate and Web-Sol extension are Chrome/managed-browser based.

### Remote Desktop Commander

No dependency. Its broad machine/terminal/filesystem reach is unnecessary for the first browser-actuation mission. If a future Mastermind worker needs remote shell/filesystem, that should extend the existing governed host/operator capability plane rather than be bundled into BRA.

## Routing

Sol owns F0 architecture, integration boundaries, adversarial review and final acceptance.

For implementation after F0:

```text
BRA-T0  PREFERRED_AVENUE: Terra
BRA-O1  PREFERRED_AVENUE: Terra
BRA-A1  PREFERRED_AVENUE: CTO Sol
BRA-W1  PREFERRED_AVENUE: CTO Sol
BRA-S1  PREFERRED_AVENUE: CTO Sol
BRA-M1  PREFERRED_AVENUE: CTO Sol or Fable only if P0B/vendor ambiguity remains principal-level
```

For ordinary new implementation use `RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE`. If current automated placement is unavailable, represent `WAITING_CAPACITY / needs_placement`; do not make the Chairman select a numbered account.

**WHY NOT FABLE for T0/O1/A1/W1/S1:** once F0 and the action-specific provider law are frozen, each is a bounded engineering mission with explicit target/effect/security contracts. Principal capacity is not the default.

## Review questions for every child

- Did the child create an independently useful capability, not just infrastructure?
- Is the exact target selected by canonical facts rather than UI heuristics?
- Can any secret-bearing browser state reach the model?
- Is `EFFECT_UNKNOWN` preserved after ambiguous modifying dispatch?
- Did a generic browser tool accidentally gain ChatGPT semantic authority?
- Did the child create a new store/registry/queue/retry plane?
- Does proof use a real ChatGPT/tunnel/browser path where owed?
- What user/CEO labor disappeared after this wave?

## Final stop condition

This plan ends only when BRA-PROD proves one real supported Sol workflow or a current official platform/vendor boundary makes that end-state impossible. External impossibility must be recorded as a typed blocker with the exact missing capability; do not fabricate completion or silently substitute GUI scripting.
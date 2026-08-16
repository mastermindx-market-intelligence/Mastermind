# Executive OS Phase 1G — X0-A Workspace capability matrix

**Date opened:** 2026-08-15  
**Status:** evidence matrix initialized; live Business-workspace canaries still required  
**Scope:** zero-production-write capability evidence only  
**Rule:** no row in this matrix creates production modifying authority.

---

## 0. Evidence vocabulary

Status:

```text
PROVED
REFUTED
STILL_UNKNOWN
```

Evidence class:

```text
OFFICIAL_DOC
LIVE_ACCOUNT_CANARY
OPERATOR_OBSERVED
ARCHITECTURE_INFERENCE
```

`PROVED/OFFICIAL_DOC` means only that the current primary documentation makes the stated generic product claim. It does **not** prove the capability is enabled, configured, or identity-safe on the actual Mastermind Business workspace.

Any load-bearing account-specific capability remains `STILL_UNKNOWN` until a live zero-write canary or equivalent direct account evidence resolves it.

Primary documentation snapshot consulted on 2026-08-15:

- OpenAI Help Center — **ChatGPT Workspace Agents for Enterprise and Business**
- OpenAI Help Center — **Developer mode and MCP apps in ChatGPT**
- OpenAI API docs — **Secure MCP Tunnel**
- OpenAI `tunnel-client` repository documentation — `docs/onboarding.md`, `docs/configuration.md`, `docs/connectors.md`, `docs/permissions.md`

Volatile provider behavior is re-checked at execution time.

---

## 1. Matrix

| ID | claim being tested | status | evidence class | current evidence / canary | architecture consequence | load-bearing |
|---|---|---|---|---|---|---|
| X0A-01 | Workspace Agents are enabled in the actual Mastermind Business workspace | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | inspect/create/test in actual workspace | no CEO trigger route until proved | yes |
| X0A-02 | A Workspace Agent can be published and assigned an API trigger in the actual workspace | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | publish a no-write test agent/trigger | X3 trigger design cannot assume account availability | yes |
| X0A-03 | Current generic Workspace Agent API-trigger contract queues a run and returns `202 Accepted` with no response body/run id | PROVED | OFFICIAL_DOC | current OpenAI Workspace Agents Help Center states this explicitly | canonical completion cannot depend on immediate trigger metadata | yes |
| X0A-04 | The final Workspace Agent response is retrievable through the trigger API | REFUTED | OFFICIAL_DOC | current Help Center states final response cannot currently be retrieved through the API | durable Executive outcome must come through canonical state/action path | yes |
| X0A-05 | Exact trigger response on the actual Mastermind workspace matches the documented `202`/empty-body contract | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | invoke a no-write test trigger and record raw status/headers/body | richer metadata remains advisory until proved | yes |
| X0A-06 | Stable trigger idempotency behavior available on the actual endpoint is known and reproducible | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | repeat identical trigger identity under controlled no-write input | duplicate wake recovery cannot be finalized without evidence | yes |
| X0A-07 | Conversation continuity mechanism and exact `conversation_key` behavior are known on the actual endpoint | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | controlled continuation test | conversation reuse remains governed conservatively | yes |
| X0A-08 | Concurrent/distinct triggers sharing one conversation key have safe/understood behavior | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | no-write concurrency canary | policy forbids overlapping activation ownership of a key until proved | yes |
| X0A-09 | Workspace Agent access tokens are scoped to Workspace Agents API operations | PROVED | OFFICIAL_DOC | current Workspace Agents Help Center | trigger credential is separate from Platform/tunnel credentials | yes |
| X0A-10 | Actual trigger-token owner/principal, sharing dependency, lifetime, rotation, and revocation behavior are known | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | create/rotate/revoke no-write token and record account relationship | dispatcher credential lifecycle remains unarmed until understood | yes |
| X0A-11 | Permission/share loss produces a distinguishable access refusal on the actual workspace | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | remove test-agent access from token principal, observe result, restore | authorization drift must not be treated as transient rate limit | yes |
| X0A-12 | Workspace Agent builder supports model and reasoning-effort configuration | PROVED | OFFICIAL_DOC | current Workspace Agents Help Center | logical reasoning routes can be designed around published configuration | yes |
| X0A-13 | Deterministic external routing to Mastermind logical `R0_FAST/R1_DEEP/R2_PRO` can be proved on this workspace | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | prove effective route/config receipts for each class | autonomous R2 remains unavailable if not proved | yes |
| X0A-14 | Current trigger request itself provides a documented per-trigger model/reasoning selector | STILL_UNKNOWN | OFFICIAL_DOC | current primary docs reviewed do not establish a load-bearing dynamic selector; verify exact trigger reference at canary time | prefer separate published routes unless stronger evidence emerges | yes |
| X0A-15 | Published agent/config identity is observable strongly enough to detect republish/config drift | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | record before/after publication identifiers and observable metadata | otherwise require operator publication receipts | yes |
| X0A-16 | Workspace Agents support custom MCP apps/tools | PROVED | OFFICIAL_DOC | current Workspace Agents Help Center | X1-A is product-plausible | yes |
| X0A-17 | Full custom MCP modify/write support is available to ChatGPT Business in current product | PROVED | OFFICIAL_DOC | current Developer mode/MCP Help Center says full MCP including modify/write is rolling out in beta to Business/Enterprise/Edu | availability does not equal Mastermind authorization | yes |
| X0A-18 | Modify/write approval behavior on the actual Business workspace is known | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | test a harmless fixture/no-op action with workspace controls | unattended CEO path must handle product approval blocking | yes |
| X0A-19 | Business-published custom MCP app update/tool-snapshot behavior is known | PROVED | OFFICIAL_DOC | current Help Center states Business apps cannot be updated after publishing at launch; changes require recreate/republish | publication/config receipt is a deployment artifact | yes |
| X0A-20 | Secure MCP Tunnel keeps the private MCP origin behind an outbound-only tunnel path | PROVED | OFFICIAL_DOC | current Secure MCP Tunnel docs | X1-A private reachability is product-plausible | yes |
| X0A-21 | Tunnel permissions are organization-level and runtime use is distinct from tunnel management | PROVED | OFFICIAL_DOC | current Secure MCP Tunnel docs and official tunnel-client permissions docs | runtime/admin tunnel credentials must be separate | yes |
| X0A-22 | Tunnel runtime itself exposes a trustworthy per-Workspace-Agent/per-human Executive principal to the local MCP server | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | architecture assumes **no**; inspect actual app/tunnel request identity evidence | tunnel identity is never load-bearing for X5 without proof/review | yes |
| X0A-23 | OAuth connector `Authorization` reaches the private MCP server through the tunnel path | PROVED | OFFICIAL_DOC | official OpenAI `tunnel-client` docs state inbound Authorization is forwarded to the MCP server | X1-B OAuth application identity is technically plausible | yes |
| X0A-24 | Connector-forwarded custom request headers reach the configured MCP origin through tunnel-client subject to transport exclusions | PROVED | OFFICIAL_DOC | official `tunnel-client` onboarding/configuration docs | bounded non-OAuth canary is technically plausible but not automatically acceptable | no |
| X0A-25 | OAuth/application identity can be proved as distinct for autonomous Sol versus interactive human use in the actual workspace | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | compare actual authenticated subjects/connection modes | no production modifying CEO identity until proved | yes |
| X0A-26 | Workspace Agent apps support end-user versus agent-owned connection modes generically | PROVED | OFFICIAL_DOC | current Workspace Agents Help Center | enables candidate identity designs; account-specific safety still unknown | yes |
| X0A-27 | An agent-owned connection on the planned Sol route is unavailable to ordinary human-started execution of that same route | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | verify actual sharing/launch/connection behavior | if false or ambiguous, `CEO_AGENT` modifying mode is unavailable | yes |
| X0A-28 | Another reachable OpenAI execution surface can use the same tunnel but cannot obtain the Executive application principal | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | controlled cross-surface identity-isolation canary | X1-B must prove application principal, not tunnel reachability | yes |
| X0A-29 | Static local tunnel-client MCP headers are distinct from connector-forwarded caller identity | PROVED | OFFICIAL_DOC | official tunnel-client configuration docs distinguish static MCP headers from connector-forwarded headers, with connector values applied last | static runtime header cannot be the CEO/Chairman principal | yes |
| X0A-30 | Executive tunnel profile has zero Harpoon targets and Harpoon is disabled when target count is zero | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | official tunnel-client docs say zero targets disables the channel; inspect effective Mastermind profile when X1-A is run | nonzero targets invalidate Executive tunnel acceptance | yes |
| X0A-31 | Generic tunnel-client Harpoon capability exists when targets are configured | PROVED | OFFICIAL_DOC | current Secure MCP Tunnel docs and tunnel-client config docs | tunnel is not treated as semantically pure transport unless Harpoon=0 is proved | yes |
| X0A-32 | Tunnel runtime key and tunnel administration key can be operated as distinct least-privilege credentials | PROVED | OFFICIAL_DOC | official tunnel-client permissions docs: runtime Read+Use, admin Read+Manage | required X1-A credential-domain separation | yes |
| X0A-33 | Optional provider run id/status telemetry is available on the actual Workspace Agent trigger route | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | observe actual trigger/beta surfaces without making it canonical | absence must not break correctness | no |
| X0A-34 | Approval-blocked runs expose a useful negative diagnostic such as suspension/waiting state on the actual route | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | harmless fixture action if supported | may shorten failure diagnosis but never declare completion | no |
| X0A-35 | App/connector secrets remain absent from model-visible context, normal tool arguments, and acceptance logs on the chosen identity path | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | verify chosen OAuth/connection configuration and redacted evidence | modifying identity unavailable if secret isolation cannot be proved | yes |
| X0A-36 | Rotation/revocation of the Executive application principal is independently observable and immediately effective enough for the reviewed threat model | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | rotate/revoke test identity in fixture environment | X1-B cannot PASS without lifecycle proof | yes |
| X0A-37 | `CHAIRMAN_INTERACTIVE` can be strongly authenticated as a distinct human principal on the chosen MCP path | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | prove stable end-user identity or retain a separately authenticated Chairman channel | direct Chairman MCP action unavailable until proved | yes |
| X0A-38 | Workspace Agent Slack support exists generically | PROVED | OFFICIAL_DOC | current Workspace Agents Help Center | Slack remains notification/discussion transport only | no |
| X0A-39 | Slack can produce the strong typed human identity required for a canonical Chairman decision in the actual architecture | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | separate identity review/canary if Slack is selected | until proved, Slack cannot commit Chairman decisions | yes |
| X0A-40 | Global/product limits materially affecting retry, schedule, continuation, or concurrency have been enumerated for the actual account | STILL_UNKNOWN | LIVE_ACCOUNT_CANARY | record observed/documented account limits at execution time | dispatcher bounds must reflect real limits rather than stale constants | yes |

---

## 2. Current evidence summary

The primary documentation is sufficient to establish several **generic** facts:

- Workspace Agents support API triggers, custom MCPs, model/reasoning configuration, Slack, and end-user versus agent-owned app connections.
- The current Help Center contract for API triggering is conservative: queue the run, return `202 Accepted` with no response body/run id, and do not expose final-response retrieval through that API.
- Full MCP modify/write support exists in beta for Business/Enterprise/Edu, with product-side permissions/confirmations that can independently block an action.
- Secure MCP Tunnel is outbound/private connectivity; its runtime/admin permissions are separate.
- OpenAI's official `tunnel-client` documentation supports OAuth-protected MCP forwarding, including connector Authorization forwarding, and distinguishes connector-forwarded headers from static local MCP headers.
- Harpoon is a separate embedded allowlisted HTTP-callout channel and is disabled when zero targets are registered.

These are **not** substitutes for account-level evidence. The load-bearing unknowns are principally identity separation, route/config identity, trigger credential lifecycle, live retry/continuation behavior, reasoning-route proof, and the actual approval/status behavior on the Mastermind Business workspace.

---

## 3. Execution rule

When X0-A is executed, update this file append-only or by a reviewed revision that preserves the previous observation and records:

```text
observed_at
workspace/account context
agent/config identity
canary method
raw bounded result or receipt reference
status change
architecture consequence
reviewer
```

Do not overwrite an inconvenient observation to make a later gate pass.

If product behavior changes after X0-A, the affected row becomes stale and any acceptance that depends on it is invalid until re-proved.
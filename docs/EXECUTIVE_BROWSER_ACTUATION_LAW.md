# Executive Browser Actuation Law

**Program:** BRA / Governed Remote Browser Actuation  
**Parent:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Chairman operation:** `web-sol-browser-actuation-fabric-20260904-chairman-001`  
**Issue:** Mastermind #472  
**Status:** source law only / `SPEC_ONLY / PRODUCTION_INERT`

## 1. Purpose

Mastermind may expose bounded browser observation and actuation to an authorized ChatGPT Web Sol without creating a second lifecycle, target registry, browser-session authority, session database, retry ledger, device database, remote-desktop relay, or authority plane.

The canonical composition is:

```text
approved ChatGPT MCP/App action
-> remote/private MCP transport
-> local browser capability gateway
-> an already-owned exact target adapter
-> typed browser receipt
-> existing canonical owners consume evidence
```

Transport, browser actuation, ChatGPT semantic continuity, and company lifecycle are separate layers.

## 2. Canonical owners remain unchanged

- Executive OS owns Job / Attempt / Worker / Event lifecycle and CEO admission.
- RuntimeBinding / SessionTarget owners determine exact actionable runtime targets.
- Agent OS owns durable organizational workstreams, decisions, discoveries and handoffs.
- GitHub owns implementation and evidence truth.
- Web-Sol owns its exact ChatGPT surface adapter semantics.
- Operator Harness owns governed Attempt-local browser resources.
- Surface bindings remain navigation-only.
- Secure MCP Tunnel, when used, is transport only.

A browser tool result grants none of those authorities.

## 3. Target classes are closed

V1 recognizes exactly four conceptual target classes.

### `DISPOSABLE_AUTOMATION_BROWSER`

A fresh, isolated browser controlled by an already-governed Operator Harness browser resource. This is the first allowed target for generic modifying browser proof.

### `EXISTING_WEB_SOL_CHATGPT_TAB`

An exact ChatGPT conversation already identified by the Web-Sol extension/native-host path. Existing `mastermind.web_sol_surface_action.v1` remains closed to `INSPECT | FOREGROUND`.

Generic browser actuation must not be used to smuggle ChatGPT prompt submission, model/mode selection, successor creation, continuation bootstrap, account switching, recovery, semantic ACK or RuntimeBinding succession around the separately versioned Web-Sol semantic protocol.

### `PERSISTENT_AUTHENTICATED_BROWSER_PROFILE`

A dedicated automation Chrome profile retained on one stable home host for one approved web identity. It is not the user's default Chrome profile, and the system must not copy the user's default Chrome profile, cookie database, storage-state export, or Application Support tree to create it. The admitted controller may use a reviewed persistent Playwright/browser-resource profile or a profile-specific extension/native bridge, but raw CDP/DevTools, undocumented remote-debug attachment, and model-visible cookie/storage APIs remain forbidden.

Existing Fleet/browser-resource owners bind `home_host_id`, `profile_generation`, `browser_process_generation`, `web_identity_ref`, and one active mutating controller. Each action additionally binds the exact tab/document target fingerprint and navigation epoch. Chrome's profile lock is last-resort evidence, not company authority. The production path refuses newest-tab, title, window-order, or screen-coordinate targeting.

Login state is readiness, not a credential or execution grant. The closed readiness vocabulary is `READY | LOGIN_REQUIRED | MFA_REQUIRED | HUMAN_CHALLENGE_REQUIRED | PROFILE_LOCKED | PROFILE_IN_USE | HOST_OFFLINE | STALE_GENERATION`. Credential use/save belongs to the existing credential-owning helper; the model receives only a non-secret outcome. Initial enrollment, OS unlock, MFA/passkey approval, or an anti-bot challenge may require attended human action. BRA does not automate CAPTCHA solving or bypass a provider challenge.

An existing human Chrome window is an attended enrollment or recovery surface, not production target identity. It may help a human establish or recover the dedicated profile, but its cookies/profile directory are never copied into the automation resource and its current window/tab geometry never becomes the durable selector.

### `CHAIRMAN_MANAGED_BROWSER_SEAT`

A persistent GoLogin/Multilogin Chairman seat. This class remains held until the existing P0B/MAS-115 program independently proves a supported exact attachment/ownership/foreground path on the required disposable and seat canaries. It remains distinct from the dedicated `PERSISTENT_AUTHENTICATED_BROWSER_PROFILE`; BRA supplies no GUI-scripting, newest-window, title-matching or undocumented remote-debug fallback.

Unknown target classes refuse before effect.

## 4. Capability families are separate

### `mastermind.browser_observation.v1`

Read-only, bounded evidence over an exact eligible target. It may include target health, bounded URL/origin classification, a policy-safe accessibility projection, and screenshots where the target policy expressly permits them.

Observation on Chairman/ChatGPT surfaces must never expose cookies, local/session storage, credentials, password managers, hidden provider APIs, account settings containing secrets, full transcript exports or raw browser-profile data.

### `mastermind.browser_actuation.v1`

Bounded generic web interaction for eligible non-ChatGPT semantic targets. The first BRA-A1 slice permits only its separately admitted synthetic click/fill interaction on an owner-loaded page. Navigation, scroll, resize and tab-management capabilities are later possibilities, not A1 grants. The exact first-vertical policy is in §6; no model-visible generic navigation is admitted by F0.

It never exposes arbitrary JavaScript, shell, filesystem access, raw CDP/DevTools, browser extension management, cookie/storage APIs, password managers, arbitrary upload paths or browser-profile mutation.

### `mastermind.web_sol_semantic_action.v2+`

ChatGPT-specific modifying semantics remain separately versioned and separately reviewed. Examples may include `CREATE_SUCCESSOR`, `DELIVER_CONTINUATION_BOOTSTRAP`, `VERIFY_SUCCESSOR`, and later bounded compute-mode/session-recovery actions only after their own provider falsifiers and owner gates pass.

A generic browser primitive is never authority-equivalent to a semantic Web-Sol action.

## 5. Effect law

This section resolves reviews [5125853519](https://github.com/mastermindx-market-intelligence/Mastermind/pull/473#pullrequestreview-5125853519) and [5126242660](https://github.com/mastermindx-market-intelligence/Mastermind/pull/473#pullrequestreview-5126242660) at the architecture layer. It does not implement their future runtime extension or authorize an invocation.

### 5.1 BRA-A1 existing owner

The first `DISPOSABLE_AUTOMATION_BROWSER` is a subordinate resource of one already-admitted Operator Harness Attempt/process generation. Its modifying-effect owner is fixed below.

| Property | Required value |
|---|---|
| Durable owner | Executive OS immutable Event plane |
| Aggregate type | `operator_operation` |
| Aggregate identity | owner-minted OperationId.command_id |
| Browser operation kind | future additive BROWSER_ACTION-equivalent; NOT_IMPLEMENTED_BY_F0 |
| Gateway and browser receipts | EVIDENCE_ONLY |
| Gateway durable effect store | FORBIDDEN |

The existing receipt family is `OPERATOR_OPERATION_INTENT`, `OPERATOR_OPERATION_APPLIED`, `OPERATOR_OPERATION_REFUSED`, `OPERATOR_OPERATION_EFFECT_UNKNOWN`, and `OPERATOR_OPERATION_RECONCILED`. BRA-A1 must extend the existing OHF/Executive operation contract by the smallest closed versioned browser-action kind; current start/resume/begin-turn operations must not be mislabeled as already accepting browser actuation. No sidecar table, app-local operation registry, retry journal or gateway ledger is created.

This selection is Attempt-local, not a universal owner for every target. BRA-W1 remains at its existing observation/foreground contract. BRA-S1 must name its own existing semantic effect owner before any ChatGPT effect. BRA-M1 does not inherit this Attempt-local owner for a persistent managed seat whose ownership is still unproved.

### 5.2 Owner-minted action reference and issuance

The owner-minted browser action reference binds all of the following, using existing identity and permission owners rather than caller assertions:

- `attempt_id`, `worker_id`, `session_epoch_id`, `process_generation_id`;
- exact browser resource `target_fingerprint` and `target_generation`;
- `action_version` and `normalized_arguments`;
- `capability_generation`, `app_generation`, `tool_schema_generation`;
- `network_policy_generation` and `network_policy_digest`;
- `issued_at`, `deadline`, `precondition_digest`;
- `principal` and `authority_policy_hash`;
- `logical_operation_key` and `normalized_effect_digest`.

The caller cannot mint or substitute this reference, choose another target, or upgrade its authority by copying the expected values. The following is documentation of required ordering, not a new wire/state-machine implementation:

```text
OWNER_VALIDATES_ACTION_AND_PRIOR_EFFECT
-> OPERATOR_OPERATION_INTENT_COMMITTED_IN_BEGIN_IMMEDIATE
-> REREAD_ATTEMPT_AUTHORITY_WRITER_GENERATION_TARGET_POLICY_PRIOR_EFFECT
-> EXISTING_OWNER_AT_MOST_ONCE_ISSUANCE
-> ONE_NATIVE_ADAPTER_DISPATCH
-> OWNER_VALIDATES_POSTCONDITION_AND_APPENDS_RECEIPT
```

The durable INTENT must commit in the existing Executive transaction before any modifying dispatch. Its immediate post-commit, pre-dispatch fence revalidates the current Attempt grant, held writer, process/target generation, exact target, policy and prior effect. The existing owner must discriminate a new issuance from reconciliation of an existing command. Re-entering an existing INTENT never grants another dispatch. Concurrent matching requests cannot both issue. A stateless gateway restart does not create a fresh issuance right. The later implementation must prove that actual owner-native behavior, not merely log this diagram.

### 5.3 Replay and reconciliation

| Condition | Owner disposition | Second dispatch |
|---|---|---|
| Same action with terminal receipt | RETURN_EXISTING_EVIDENCE | ZERO |
| Changed action, target, policy or precondition | CONFLICT_BEFORE_EFFECT | ZERO |
| INTENT with possible dispatch and no terminal proof | EFFECT_UNKNOWN | ZERO |
| Unresolved EFFECT_UNKNOWN | READ_ONLY_SAME_COMMAND_RECONCILIATION | ZERO |
| Positive canonical postcondition | APPEND_RECONCILED_TO_SAME_COMMAND | ZERO |
| Missing evidence or retention loss | EFFECT_UNKNOWN | ZERO |

`EFFECT_UNKNOWN` keeps the same logical operation/carrier binding, permits read-only reconciliation only, blocks blind retry, and blocks target/session/account failover. It also blocks host, tunnel and gateway failover, a second dispatch under another gateway, and a replacement operation that would repeat the uncertain action. A changed payload conflicts, rather than spending the old key on changed work. Restart cannot reset the Executive Event history. A `RECONCILED` receipt resolves, or explicitly cannot resolve, the original owner-native command; it does not authorize compensation, replay or another operation. Compensation needs its own later explicit grant.

An absent target, expired execution permission, lost receipt or timeout cannot manufacture proof that an effect never occurred. Historical effect lookup remains under its own current read permission; neither reading historical evidence nor finding a completed command renews execution authority.

### 5.4 Response status and common effect truth

Common effect truth remains exactly `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`. Browser response statuses are distinct:

| Response status | effect_state | Evidence requirement |
|---|---|---|
| REFUSED | NOT_APPLIED | authoritative proof of no dispatch/effect |
| NO_EFFECT | NOT_APPLIED | authoritative proof of no effect |
| APPLIED_VERIFIED | APPLIED | exact canonical postcondition |
| AMBIGUOUS_AFTER_POSSIBLE_DISPATCH | EFFECT_UNKNOWN | missing authoritative terminal proof |

REFUSED here describes refusal before any possible effect of this action; a late refusal of a repeat request cannot downgrade an earlier unknown effect. RECONCILED is a receipt/lineage status, not a fourth effect_state. Its evidence may resolve the same command to an existing common state or preserve uncertainty. Driver success without the required postcondition is not APPLIED. A transport timeout, browser crash, gateway loss or tunnel disconnect after dispatch might have started remains EFFECT_UNKNOWN until authoritative evidence resolves that same action. None of these receipts implies Executive completion, retry permission or RuntimeBinding succession.

## 6. Exact-target law

When exactness is required, target selection may not use:

- newest or most recently active tab;
- browser/window order;
- title similarity;
- page-text similarity;
- visible model output;
- model-selected account/profile/project;
- remembered prior-session UI state.

A missing, stale, duplicate, conflicting or unresolvable exact target refuses before effect. For `PERSISTENT_AUTHENTICATED_BROWSER_PROFILE`, exact target evidence includes the owner-bound stable home host, `profile_generation`, `browser_process_generation`, web-identity reference, exact tab/document fingerprint, policy generation, and navigation epoch. A currently visible existing human Chrome window can be used only as an attended enrollment or recovery surface; it is not production target identity and does not replace those facts.

### 6.1 First-vertical target policy

BRA-A1 uses one synthetic page loaded by the browser-resource owner before minting any capability/action reference. This table is a documentation selection, not model-supplied policy or loadable runtime configuration.

| Boundary | Required disposition |
|---|---|
| A1 target | owner-created and owner-loaded synthetic page before reference minting |
| A1 allowed origin | http://127.0.0.1:<leased-port> selected by the owner |
| A1 model-visible browser_navigate | FORBIDDEN |
| O1 navigation | FORBIDDEN |
| W1 generic navigation and network inspection | FORBIDDEN |
| Model-selected scheme, host, port, proxy, DNS, path root or allowlist | FORBIDDEN |
| Enforcement boundary | resource/process/network boundary |
| Playwright allowedOrigins alone | DEFENSE_IN_DEPTH_NOT_SECURITY_BOUNDARY |

The literal owner-derived origin is exact, including the leased port. It is not a pattern allowing arbitrary loopback. The first observation sees only an already-created, exact target; neither O1 nor a generic W1 tool can load a different page. A1's mutation is confined to the already-loaded page under the admitted resource policy. Missing enforcement or unproven target/resource ownership refuses the later canary rather than broadening browser reach.

### 6.2 Closed egress and local-surface refusals

All destinations and capabilities outside the exact admitted origin/action are refused. In particular:

| Destination or capability family | Disposition |
|---|---|
| other loopback ports; IPv6; hostnames/DNS; private; link-local; public; DNS rebinding | REFUSED |
| cross-origin redirects; frames; popups; new windows; subresources | REFUSED |
| service workers; WebSockets | REFUSED |
| file:; data:; blob:; javascript:; about:; chrome:; chrome-extension:; devtools: | REFUSED |
| downloads; uploads; file chooser; clipboard transfer | REFUSED |
| auth challenges; credential-bearing URLs; proxy/network setting changes | REFUSED |
| model-selected raw URL; arbitrary fetch; unrestricted console/network payloads; secret headers/bodies | REFUSED |

Equivalent browser-internal/local schemes are also refused. The allowlist is enforced at the resource/process/network boundary; adapter interception and Playwright origin settings are defense in depth only. No public browser tool can weaken the resource policy, request an exception, choose a proxy or install a new allowlist. Returning a safe-looking screenshot cannot prove egress confinement.

### 6.3 Later navigation is a different admitted policy

Broader company/public origins or any later model-visible navigation require a separately reviewed policy generation and real canary. Any later permitted navigation increments the canonical navigation/target epoch and invalidates prior element handles, preconditions and capability references. The existing target owner must supply fresh exact-target and policy evidence before another action. A1 does not gain navigation merely because a later contract may define it. BRA-W1 never receives generic navigation/network inspection against ChatGPT.

## 7. Local gateway boundary

The local browser gateway is a stateless capability adapter. It may route one request to an existing Web-Sol or Operator Harness adapter using trusted target facts supplied by existing owners.

It must not persist or own:

- Job / Attempt / Worker lifecycle;
- RuntimeBinding or SessionTarget identity;
- browser session identity;
- device inventory authority;
- retries or replay cursors;
- work queues;
- credentials;
- organizational memory;
- completion state.

Restarting the gateway cannot lose company truth because it owns none.

## 8. Remote transport boundary

When OpenAI Secure MCP Tunnel is used, it transports MCP traffic from ChatGPT to the private/local MCP server. Tunnel identity, tunnel-client process identity, MCP session IDs, Cloudflare material or connection state are transport evidence only.

They must never elect or replace RuntimeBinding, target, actor, Job, Attempt, account/profile, retry or permission policy.

Do not build a Mastermind-hosted Remote Desktop Commander-style relay while Secure MCP Tunnel can satisfy the transport job.

## 9. Plan capability is runtime evidence

Current platform support for custom MCP read/write actions is time-sensitive. ChatGPT plan/workspace capability must be observed at deployment time.

The initial modifying canary targets a supported Business full-MCP/developer-mode surface. Personal-Pro write support must remain `UNKNOWN/UNAVAILABLE` unless current official product evidence proves it at action time. No architecture constant may permanently encode a commercial-plan assumption.

## 10. Secret and privacy boundary

The model-facing browser plane must not read or return:

- cookies or storage values;
- auth/session/OAuth tokens;
- password-manager values;
- raw browser profile contents;
- credential-bearing settings or extension pages;
- proxy credentials;
- arbitrary local files;
- private provider network payloads;
- bulk ChatGPT transcripts/model outputs.

Existing Mastermind credential-safe helpers and secret-screening laws remain controlling. Browser screenshots/snapshots are allowed only where target policy and proof needs make them safe.

## 11. No authority from visible UI

A clicked button, visible confirmation, generated ChatGPT response, successful navigation or screenshot is evidence of a browser state only.

It does not create `PICKUP_ACK`, `START`, `TARGET_ACKNOWLEDGED`, `SOURCE_RESOLVED`, Job completion, RuntimeBinding succession, merge/release authority or Chairman approval.

Those remain owned by their canonical systems.

## 12. Release sequence

```text
BRA-F0 source law
-> BRA-T0 tunnel/local-gateway transport falsifier
-> BRA-O1 disposable read-only observation
-> BRA-A1 one disposable generic modifying actuation
-> BRA-W1 exact existing Web-Sol observation/foreground via MCP
-> BRA-S1 separately versioned ChatGPT semantic effect on disposable Project/profile
-> BRA-M1 managed-seat integration after P0B exact supported attachment proof
-> BRA-PROD approved real Sol workflow proof
```

Children may proceed in parallel only when target class, authority and source paths are genuinely disjoint. No child inherits START from this law.

## 13. Production acceptance

The program remains below `PROVEN_LIVE` until a real supported path proves all of:

1. exact target identity with no title/newest-tab fallback;
2. read and modifying scopes remain separable;
3. one harmless modifying effect returns `APPLIED_VERIFIED`;
4. post-effect transport ambiguity returns `EFFECT_UNKNOWN` with zero retry;
5. wrong/stale target generation refuses before effect;
6. bounded browser evidence does not expose protected secrets;
7. local gateway restart creates no hidden state loss;
8. Web-Sol semantic actions cannot be reached through unrestricted generic tools;
9. existing Executive/RuntimeBinding/Agent OS owners remain authoritative;
10. one approved real Sol workflow succeeds through the production path.

Green source CI, tunnel connection, MCP discovery, Chrome focus, or a disposable-browser canary alone is not final production acceptance.

These source-law tests prove documentation consistency, not runtime enforcement. A passing F0 test suite or this owner selection does not commit an Executive Event, connect a tunnel, start a browser or authorize any child.

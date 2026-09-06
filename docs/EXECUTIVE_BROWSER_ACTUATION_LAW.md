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

V1 recognizes exactly three conceptual target classes.

### `DISPOSABLE_AUTOMATION_BROWSER`

A fresh, isolated browser controlled by an already-governed Operator Harness browser resource. This is the first allowed target for generic modifying browser proof.

### `EXISTING_WEB_SOL_CHATGPT_TAB`

An exact ChatGPT conversation already identified by the Web-Sol extension/native-host path. Existing `mastermind.web_sol_surface_action.v1` remains closed to `INSPECT | FOREGROUND`.

Generic browser actuation must not be used to smuggle ChatGPT prompt submission, model/mode selection, successor creation, continuation bootstrap, account switching, recovery, semantic ACK or RuntimeBinding succession around the separately versioned Web-Sol semantic protocol.

### `CHAIRMAN_MANAGED_BROWSER_SEAT`

A persistent GoLogin/Multilogin Chairman seat. This class remains held until the existing P0B/MAS-115 program independently proves a supported exact attachment/ownership/foreground path on the required disposable and seat canaries. BRA supplies no GUI-scripting, newest-window, title-matching or undocumented remote-debug fallback.

Unknown target classes refuse before effect.

## 4. Capability families are separate

### `mastermind.browser_observation.v1`

Read-only, bounded evidence over an exact eligible target. It may include target health, bounded URL/origin classification, a policy-safe accessibility projection, and screenshots where the target policy expressly permits them.

Observation on Chairman/ChatGPT surfaces must never expose cookies, local/session storage, credentials, password managers, hidden provider APIs, account settings containing secrets, full transcript exports or raw browser-profile data.

### `mastermind.browser_actuation.v1`

Bounded generic web interaction for eligible non-ChatGPT semantic targets. Candidate primitives include click, fill, navigate, scroll, wait, resize and tab focus.

It never exposes arbitrary JavaScript, shell, filesystem access, raw CDP/DevTools, browser extension management, cookie/storage APIs, password managers, arbitrary upload paths or browser-profile mutation.

### `mastermind.web_sol_semantic_action.v2+`

ChatGPT-specific modifying semantics remain separately versioned and separately reviewed. Examples may include `CREATE_SUCCESSOR`, `DELIVER_CONTINUATION_BOOTSTRAP`, `VERIFY_SUCCESSOR`, and later bounded compute-mode/session-recovery actions only after their own provider falsifiers and owner gates pass.

A generic browser primitive is never authority-equivalent to a semantic Web-Sol action.

## 5. Effect law and durable owner-native command lineage

The existing **Attempt-local Operator Harness effect owner** on Executive OS's
`operator_operation` Event plane owns durable effect truth for every modifying
browser operation. Executive OS continues to own Attempt authority and lifecycle.
The MCP edge, Secure MCP Tunnel, local gateway, target adapter and browser receipt
remain evidence carriers only. BRA adds no gateway ledger, retry table or second
effect owner.

Before any modifying dispatch, that existing owner mints one owner-native
`OperationId`. The model-facing command calls this opaque value
`operation_command_id`; it is the required `action_ref`, not a tunnel/MCP/browser
correlation ID. The owner binds it to all of:

- current Attempt ID, lease/fence and authority generation;
- stable logical operation fingerprint and normalized action-argument digest;
- exact target class, opaque target identity, target generation and
  `navigation_epoch`;
- semantic action plus capability, schema, app and target-policy generations;
- issue/expiry window or equivalent bounded deadline;
- precondition/observation digest sufficient to prove target identity.

The required pre-dispatch order is closed:

1. the existing effect owner commits `INTENT` before any adapter call;
2. immediately before mutation, that owner rereads current authority, exact target, and prior effect for the same
   `operation_command_id`;
3. any lease/fence, authority, target, generation, policy, deadline,
   precondition or prior-effect mismatch refuses before effect;
4. only that owner may dispatch the bound action exactly once;
5. postcondition evidence is returned to that owner for a terminal or
   reconciled owner-local history.

Closed conceptual outcomes remain:

```text
NO_EFFECT
APPLIED_VERIFIED
EFFECT_UNKNOWN
REFUSED
```

Closed owner-local histories are:

```text
INTENT -> APPLIED_VERIFIED
INTENT -> NO_EFFECT
INTENT -> REFUSED
INTENT -> EFFECT_UNKNOWN -> RECONCILED
```

The histories reuse the existing owner-native `OPERATOR_OPERATION_INTENT`,
`OPERATOR_OPERATION_APPLIED`, `OPERATOR_OPERATION_EFFECT_UNKNOWN` and
`OPERATOR_OPERATION_RECONCILED` Events. `APPLIED_VERIFIED` is the browser outcome carried by existing `OPERATOR_OPERATION_APPLIED`
only after the bound postcondition is proven; normalized `NO_EFFECT` and
`REFUSED` remain payload outcomes on that same Event plane. No browser Event
store or parallel operation ledger is created.

`RECONCILED` records a closed resolution such as `APPLIED_VERIFIED`,
`NO_EFFECT` or `REFUSED`; it never appends a fresh `APPLIED_VERIFIED` after the
unknown edge. A timeout, disconnect, browser crash, tunnel loss or local gateway
loss after an effect may have started is `EFFECT_UNKNOWN` unless same-command
read-only evidence closes that history.

`EFFECT_UNKNOWN`:

- keeps the same logical operation, `operation_command_id`, Attempt, exact target
  and carrier binding;
- permits read-only reconciliation only against that same command and target;
- blocks blind retry;
- blocks target/session/account failover;
- blocks every resend and receiver/host/gateway change until reconciled;
- does not imply Executive failure or completion.

Matching replay is evidence-only: the owner returns the existing sanitized
history/receipt and performs no second browser effect. Changed replay is a conflict and refuses before adapter I/O. A gateway receipt is evidence only; tunnel and browser receipts are likewise
evidence only. None can grant retry, completion, RuntimeBinding, Executive
authority or a new action target.

## 6. Exact-target law

When exactness is required, target selection may not use:

- newest or most recently active tab;
- browser/window order;
- title similarity;
- page-text similarity;
- visible model output;
- model-selected account/profile/project;
- remembered prior-session UI state.

A missing, stale, duplicate, conflicting or unresolvable exact target refuses before effect.

## 6A. Closed navigation and network policy

Observation and actuation use separate closed target-policy generations.
`BRA-O1` cannot navigate, open a new browsing context, issue a generic network
inspection call or cause a modifying page action. `BRA-A1` may navigate only
under `DISPOSABLE_SYNTHETIC_ORIGIN_V1`, an owner-attested policy containing an
exact disposable synthetic origin allowlist, allowed scheme, resolved
host/address/port, action set and policy digest. The caller cannot supply or
expand that policy.

For `DISPOSABLE_SYNTHETIC_ORIGIN_V1`:

- every requested URL and every URL in a redirect chain must stay on the exact
  attested origin and scheme; cross-origin or scheme-changing redirects refuse;
- main frames, subframes and subresources, fetch/XHR, workers and WebSockets are
  confined to that exact origin; popups, new windows and external opener targets
  refuse;
- DNS rebinding is refused by checking the resolved address at admission and
  again before each connect/redirect; a hostname may not resolve outside its
  attested address set;
- any other private, loopback, or link-local destination refuses. The sole
  exception is an exact owner-attested loopback synthetic origin whose literal
  address and ephemeral port are already in the policy;
- credential-bearing URLs and userinfo refuse. Query/fragment values are allowed
  only when the exact owner-minted URL set classifies them as non-secret;
- downloads and uploads refuse, including file chooser, drag/drop and arbitrary
  upload-path flows;
- browser/local/opaque schemes are closed: `file:` / `data:` / `chrome:`,
  `chrome-extension:`, `javascript:`, `blob:` and unreviewed `about:` targets
  refuse;
- console/network evidence remains bounded, sanitized and unavailable to
  Chairman/ChatGPT target classes.

A navigation invalidates the prior observation and target precondition before
dispatch. Only a successful same-policy postcondition advances
`navigation_epoch`; ambiguous navigation leaves the effect/epoch unresolved and
requires same-command reconciliation. Every subsequent read or actuation
requires fresh exact-target and postcondition evidence bound to the new epoch.

BRA-W1 receives no generic navigation or network-inspection authority against
ChatGPT. A broader origin, scheme, redirect, subresource, popup, download,
upload, private-network or evidence policy requires a separately versioned
source-law review and canary; implementation convenience cannot widen V1.

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

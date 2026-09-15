# OCR-2C Family B — Native Claude Realm Capacity Architecture

**Date:** 2026-09-14  
**Owner:** Sol, AI CEO  
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `CHAIRMAN-APPROVED DIRECTION / ARCHITECTURE CANDIDATE / RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Protected basis:** `Mastermind@36f74c02edc938f7f5c41f38743f93ee34be2b2b`, Skillpack `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1.  
**Organizational owner:** existing `WS:EXECUTIVE-CAPACITY-FABRIC`; no new workstream.  
**Parent source law:** protected Operator Continuity architecture from PR #181 plus the existing OCR-2C plan and native-Claude-capacity-identity amendment.

## 1. Outcome

The Chairman owns multiple direct Claude Max subscriptions and wants Claude/Fable orchestration to leave cloned macOS applications and become a routable Agent Fabric capability. The end state is not “four Claude processes.” It is:

```text
Chairman/CEO intent
-> Executive Job / Attempt
-> provider-neutral Model Router suitability
-> canonical Capacity placement
-> one exact native Claude execution realm
-> provider-neutral Worker or Operator Harness
-> useful result through the existing Executive path
```

Routine work must not require the Chairman to select a Claude account, foreground an application, repair a cloned app permission, or manually move a task after a quota event. Provider/account/auth-home changes remain new Attempt + fresh provider-native session where current effect law permits; `EFFECT_UNKNOWN` never becomes failover permission.

The first independently useful capability is narrower: **make direct `claude.ai` CLI realms canonical, rotation-safe company execution/capacity realms without pretending that a config directory is an Anthropic account identity or rebuilding Provider Control inside Mastermind.**

## 2. Current-source findings that this candidate consumes

1. OCR-2C Family A already failed safely: current native Claude evidence cannot prove an existing native realm is the same paid subscription as a numbered Macro `claude_code_oauth_N` slot with a provider-supported, secret-free, rotation-safe equality witness. The refusal remains authoritative. No ordinal, app name, plan name, reset time, quota percentage, environment variable, account email, account id, token fingerprint, or human intuition may resurrect Family A.
2. `mastermind.provider_capacity.v1` remains the accepted secret-free Macro projection for its current source family. It is not widened in place for native Claude.
3. The current Claude preflight family already proves bounded binary/auth readiness and preserves provider PII as discard-only input. It is not a capacity normalizer.
4. HF1-B/C/D and the subscription-harness binding work have landed. The common broker and harness boundary is provider-neutral enough that realm identity does not need to become execution lifecycle.
5. OCR-4A is independently generalizing rich Operator Harness control. This candidate must remain identity/capacity-only and must not absorb persistent session, browser, GUI, background-agent, or operator-control semantics.
6. Current Claude Code documentation establishes a useful custody fact: `CLAUDE_CONFIG_DIR` changes both the credential-file location and, on macOS, the Keychain entry selected by Claude Code. A different config directory therefore selects a different native credential custody entry. This is an isolation/custody primitive, **not** a stable Anthropic account identifier.

## 3. Frozen ownership ruling

Family B extends existing owners only:

| Fact / action | Canonical owner |
|---|---|
| Job / Attempt / Worker / Event lifecycle and effect reconciliation | Executive OS |
| acceptable model/execution class | Model Router |
| provider availability, health, cooling, quota evidence and normalized capacity projection | Macro Shared AI Provider Control |
| native Claude realm enrollment generation and local credential-custody binding | existing provider-realm owner, generalized/versioned rather than duplicated |
| provider-work-free Claude binary/auth readiness | existing Claude preflight family |
| actual CLI process/tool mechanics | HF1 provider adapter / Worker Harness |
| persistent rich provider session control | OCR-4A / Operator Harness |
| exact started provider/host/session binding | RuntimeBinding |
| browser and native GUI exclusivity | existing BrowserResource / host resource owners, not Provider Control |
| durable organizational continuity | Agent OS |

No `ClaudeAccount` database, `claude_capacity.json`, quota ledger, provider scheduler, retry daemon, provider-specific Executive lifecycle, second session registry, or browser/computer control plane is authorized.

## 4. Three identities that must not be collapsed

Family B deliberately separates:

```text
A. company realm identity
   “which governed execution/custody realm is this?”

B. provider subscription identity
   “which Anthropic account/subscription is behind it?”

C. capacity evidence identity
   “which fresh Provider Control observations may rank this realm now?”
```

A is company-owned and may be made durable without provider PII. B may remain opaque/unknown. C is versioned Provider Control evidence. A realm can be executable even when exact remaining quota and provider-account identity are unknown; it may not manufacture B or quota from A.

This distinction also handles a subtle duplicate-account case safely. Two native realm custodies can be proven distinct while accidentally using the same Anthropic subscription. Until a provider-supported or separately accepted proof establishes independent quota realms, Provider Control must **not add their quotas together or claim N-times aggregate capacity**. They may still be separate execution realms and may be fairly sampled while health/cooling evidence remains truthful.

## 5. Native realm enrollment v2

The existing `ProviderRealmEnrollmentReceipt` pattern is retained as the architectural predecessor. Family B requires a provider-neutral successor/extraction rather than a parallel native-Claude registry.

Proposed closed wire:

```text
schema = mastermind.provider_realm_enrollment/v2
realm_id
realm_generation
provider_family = anthropic
product = claude-code
execution_surface = native_cli
auth_family = claudeai_subscription
host_ref
os_principal_ref
config_custody_ref
enrollment_state = enrolled | unenrolled
source_receipt_digest
receipt_id
receipt_digest
```

### 5.1 `realm_id`

`realm_id` is an opaque company realm key minted by the provider-realm owner. It is not an Anthropic account id, email, organization id, token id, Slack identity, app clone name, human account number, or ordinal mapping to `claude_code_oauth_N`.

### 5.2 `realm_generation`

Every deliberate enrollment/re-enrollment/custody replacement produces a new generation. A receipt for generation G cannot authorize generation G+1. Logout/re-provision, account replacement, moving the realm to a different trusted custody, or changing its accepted host/principal binding invalidates the old generation.

Normal provider token refresh inside the same accepted `claude.ai` login does not itself create a new company generation.

### 5.3 `config_custody_ref`

`CLAUDE_CONFIG_DIR` is provider-private launch configuration. Its raw path does not enter Executive state, Agent OS, GitHub evidence, Capacity projection, Slack, or model-visible receipts.

The provider-realm owner binds the exact local absolute config root to an opaque `config_custody_ref` through the existing host/provider configuration owner. `config_custody_ref` is not a hash of the path and must not be reversible to it. The adapter resolves the local path only inside its admitted host/principal boundary.

For the initial production lane, prefer **one dedicated OS principal + one config custody + one Max login per realm**. Same-principal/multi-config operation is a later optimization and cannot weaken the first production isolation proof merely because Claude Code supports different Keychain entries per `CLAUDE_CONFIG_DIR`.

### 5.4 Enrollment does not prove provider-account identity

An `enrolled` receipt means Mastermind has a governed native Claude credential custody at an exact company realm generation. It does not assert a specific Anthropic email/id or independent paid quota pool.

If future provider-supported non-sensitive evidence can prove subscription independence, that evidence belongs in Provider Control source observations and may upgrade `capacity_independence`. It does not redefine the realm id.

## 6. Out-of-band credential mutation boundary

Current provider surfaces do not expose a safe stable account identity that lets Mastermind detect every possible human login swap behind an unchanged custody root. Family B therefore does not make a false claim.

Production enrollment assumes the dedicated worker principal/config custody is **managed**: login/logout/account replacement is an explicit provisioning action owned by the realm owner and must mint a new generation. Ordinary Worker/Operator tasks cannot invoke auth-changing commands. A privileged human or external process that bypasses that owner creates unsupported custody drift; the realm is no longer entitled to an accepted generation until re-enrolled.

This is a trust-boundary statement, not a claim that `auth status` can identify the Anthropic account. If a future provider-supported non-secret enrollment generation becomes available, it can strengthen this contract through a reviewed successor.

## 7. Native realm observation wire into Shared AI Provider Control

Mastermind may supply **source observations** about one exact native realm. Macro remains the only normalizer.

Proposed wire:

```text
schema = mastermind.provider_native_realm_observation/v1
realm_id
realm_generation
host_ref
provider_family = anthropic
product = claude-code
execution_surface = native_cli
auth_state = ready | not_ready | unknown
auth_method = claudeai | non_native | unknown
health_state = available | degraded | unavailable | unknown
health_error_class
last_provider_outcome_class
last_provider_outcome_at
cooling.active
cooling.kind
cooling.reset_at
quota_horizons[]
observed_at
stale_after
source_quality
source_receipt_digest
```

Every nullable/unobserved field stays null/unknown. No field may contain provider account PII, token/key material or fingerprints, Keychain labels, config paths, Worker prompt/content, Executive Job/Attempt ids, Slack identities, provider conversation ids, or browser/GUI state.

The observation producer may report only its own exact realm generation. It cannot rank realms or set another realm’s health/cooling.

## 8. `mastermind.provider_capacity.v2`

Family B proposes a versioned successor projection from Macro Shared AI Provider Control. **`mastermind.provider_capacity.v1` remains byte/semantic compatible with its accepted source law.** Native Claude is not silently appended to v1.

V2 retains all v1 laws:

```text
unknown != false
unknown quota != unlimited
stale != fresh
presence != authentication success
provider outcome != Executive completion
host matters
corrections do not erase historical evidence
semantic snapshot identity is secret-free
source quality is explicit
```

V2 additionally permits a capacity row to carry the accepted opaque native realm identity/generation and its host binding. It may normalize health/cooling/outcomes and any genuinely observed quota horizons beside existing provider sources.

Exact remaining Max quota may remain unknown. No percentage is converted to absolute remaining capacity without an authoritative denominator. No aggregate “4 Max accounts = 4x capacity” claim is allowed solely from four enrolled realm ids.

V1 and V2 coexist until a separately accepted consumer migration closes; v1 users are not silently upgraded.

## 9. Mastermind consumer boundary

A later bounded consumer validates the exact accepted V2 projection through a reviewed acquisition seam. It exports only owner-minted Capacity facts to placement. Executive OS does not import Macro implementation modules or read provider credentials as fallback.

Current CF2-H0/P0/CF2-I remains unchanged for its frozen inventory. Native Claude capacity admission is a separate successor/extension path built only after this architecture is protected and its producer contract is implemented.

Current FPH0 host `work_placement_union` may express that a host composition admits a Claude provider realm/quota class. That is a **host admission constraint**, not provider enrollment or Capacity truth. A placement union member cannot self-prove realm generation, auth readiness, health, or available capacity.

## 10. Selection law for four Claude realms

Once four native realm generations are enrolled and visible through accepted Provider Control V2 evidence, selection remains provider-neutral:

```text
hard Executive/authority/capability eligibility
-> first lawful Model Router equivalence tier
-> exact enrolled realm generation
-> fresh native auth/health eligibility
-> host/resource eligibility
-> provider cooling/quota evidence when known
-> existing Capacity concurrency/reservation/fairness policy
-> deterministic tie break
```

Unknown quota does not block an otherwise accepted realm merely because a number is absent, unless current route policy requires known quota. It also does not rank as infinite/full. With equivalent healthy realms and unknown quota, the Capacity owner may use its accepted deterministic fair-share/least-active policy; the adapter itself never load-balances.

Before `START`, lawful Capacity rebinding can choose another eligible realm when no effect/effect uncertainty exists. After `START`, RuntimeBinding is sticky. Provider/account/host changes require current reconciliation/retry law; a modifying or `EFFECT_UNKNOWN` Attempt never transparently rolls over.

## 11. Required failure semantics

The implementation must discriminate at least:

```text
old realm generation after re-enrollment       -> START refused
wrong host/principal/custody binding            -> realm admission refused
non-native auth precedence wins                 -> NATIVE_AUTH_NOT_SELECTED / ineligible
logged-out or expired auth                      -> not_ready/unavailable, no guessed replacement
stale observation                               -> stale/unknown, not fresh capacity
rate limit before START                         -> cooling/unavailable for new placement
rate limit after modifying START                -> no transparent failover
transport loss after possible side effect       -> EFFECT_UNKNOWN / reconcile same binding
same account behind two custodies                -> independence unknown; no aggregate quota multiplication
forged realm/capacity receipt                    -> refused
provider PII/secret/path in public evidence      -> evidence rejected
provider background restart                     -> cannot mint Executive lifecycle or retry authority
```

## 12. Tool/browser/computer boundary

Family B does **not** define Claude tool parity, Chrome automation, native computer use, persistent background agents, remote control, session resumption or MCP package realization. Those consume the realm after core admission:

- HF1 owns bounded CLI Worker execution.
- OCR-4A owns rich persistent Operator Harness mechanics.
- BrowserResource owns browser exclusivity/custody.
- host computer-use resource owns native GUI exclusivity.

Browser/GUI support must not hold core headless realm/capacity admission hostage, and their scarcity must not contaminate Provider Control quota identity.

## 13. Acceptance ladder

The architecture is not operationally complete when this record merges. Capability advances separately:

```text
FAMILY_B_ARCHITECTURE_FROZEN
-> provider-neutral realm-enrollment v2 contract implemented/accepted
-> Macro native-realm observation + provider_capacity.v2 implemented/accepted
-> Mastermind V2 consumer implemented/accepted
-> one real managed native realm enrollment + logout/re-enrollment generation invalidation proof
-> one bounded real PF1 Claude CLI Worker Job
-> four enrolled realm canaries with one real bounded provider turn each
-> canonical Capacity selects new pre-START work among the four without Chairman account selection
-> sustained Fable/Opus Operator Harness proof
-> separate browser proof
-> separate computer-use proof
```

No step inherits production acceptance from the previous step.

## 14. Completion ruler

The Claude CLI migration reaches its core production end state only when a real request can go:

```text
Executive Job
-> provider-neutral model tier
-> Capacity-selected exact Claude realm generation
-> native CLI execution with admitted Mastermind tools
-> canonical result/effect receipts
```

across the multi-realm pool without Chairman account/app selection, while logout/rotation/rate-limit and effect-unknown cases fail safely. Browser and GUI completion remain separately proven capabilities.

## 15. No-rebuild / non-goals

This candidate authorizes no login/logout, credential read/copy, provider call, route activation, runtime mutation, worker launch, browser action, GUI action, daemon/service install, Mac permission change, quota database, second scheduler, retry plane, provider-specific Executive lifecycle, second host identity, second session registry or production deployment.

It also does not self-accept `FAMILY_B_ARCHITECTURE_FROZEN`. That gate requires current-source independent review and protected source release of the cross-repository producer/consumer architecture.
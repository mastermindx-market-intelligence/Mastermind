# Executive provider expansion — Cursor and Grok auth/ACP source law

**Date:** 2026-08-25
**Owner:** Sol, AI CEO
**Chairman:** Chris
**Status:** **SOL SOURCE-LAW FREEZE / RECORDS ONLY / NO LOGIN OR PROVIDER ENABLEMENT**
**Protected Mastermind basis:** `cdfecc6f6b382862238c15fe1d5bd646eb62213c`
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1, loaded atomically from that exact commit.
**Integration parent:** `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md`
**Capacity dependency:** CF2-F -> CF2-I
**Execution dependencies:** RF1 provider-neutral suitability -> HF1 provider-neutral harness

The basis advanced from the Autonomy V1 freeze only through the disjoint Worker Browser/DevServer
F0 records carrier and the MAS-112 Slack metadata-verifier repair. The Skillpack schema/version and
every Cursor/Grok material execution/auth seam named below remain compatible at this exact basis.

---

## 0. Observable outcome and ruling

Mastermind must eventually be able to assign one already-admitted Executive Job to Cursor or Grok
without the Chairman selecting a provider session, copying credentials between apps, relaying
prompts, supervising renewals, or inventing a second agent lifecycle.

The source-law ruling is:

> Cursor and Grok plug into one provider-neutral ACP execution adapter behind the existing
> Executive Worker/Attempt/Operator-Harness lifecycle. Authentication belongs to isolated
> provider realms and a broker-owned child boundary. Provider-native sessions, MCP servers,
> plugins and subagents are subordinate capabilities of one Executive Attempt, never new Jobs,
> queues, retry ledgers, lifecycle databases or organizational memory planes.

The two provider auth paths are not symmetrical:

- **Cursor:** consumer browser OAuth is not a supported unattended worker credential. V1 automation
  uses `CURSOR_API_KEY` from a dedicated service/worker realm. Enterprise may later use a service
  account and short-lived worker token under the documented contract.
- **Grok Build:** an isolated worker realm may use one-time browser/device OIDC enrollment and the
  provider's documented refresh behavior. Enterprise may use PKCE OIDC or a reviewed external
  `auth_provider_command`. The xAI inference API remains a separate API-key route.

This record does not authenticate either provider, install a CLI, create an OS principal, enable a
route, start a service, grant MCP/plugin authority, or claim that provider capacity is observable.
Its merge state is `SPEC_ONLY`.

---

## 1. Current capability ledger

| Capability | Cursor | Grok/xAI | Estate state |
|---|---|---|---|
| Interactive account login | Browser `agent login` | Browser OIDC `grok login` | Provider-supported; not installed/proven here |
| Device OAuth | No documented consumer device-code flow | RFC 8628 `grok login --device-auth` | Cursor unsupported; Grok `SPEC_ONLY` |
| Unattended base credential | User API key; Enterprise service-account key | `XAI_API_KEY` for API/inference | Provider-supported; estate `NOT_BUILT` |
| Refreshable worker auth | Enterprise service account can mint one-hour user worker tokens | OIDC/device refresh or external auth command | Provider-supported; estate `NOT_BUILT` |
| ACP | `agent acp` | `grok --no-auto-update agent stdio` | Provider-supported; estate adapter `NOT_BUILT` |
| Structured headless result | JSON / stream JSON / stable session identity | JSON / streaming JSON / named sessions | Provider-supported; estate `NOT_BUILT` |
| MCP | ACP/project/user and Cloud Agent MCP contracts | HTTP/stdio MCP and remote OAuth | `NOT_BUILT`; held after base canaries |
| Plugins/skills/subagents | Supported by Cursor product surfaces | Supported by Grok Build | `REJECTED_BY_DESIGN` for first canary |
| Per-run consumed usage | Cloud Agent/SDK usage where that surface is used | API response/console usage where that surface is used | Descriptive only until adapter exists |
| Consumer subscription remaining | No documented machine endpoint | No documented machine endpoint | `DARK_OR_DISCONNECTED`; must remain null |
| Current Mastermind adapter | `acp` descriptor unimplemented; no alias | `xai` disabled on unimplemented `openai-compatible` | `NOT_BUILT` |

No official-support claim upgrades the estate. A provider documentation page is not an installed
realm, accepted adapter or live Executive receipt.

---

## 2. Current canonical implementation boundary

At the protected basis:

- `control_plane/worker_adapter.py` owns the single
  `mastermind.worker_adapter/v1` lifecycle interface. Its source law already names future xAI, ACP
  and cloud implementations as plugins to that interface, not another queue or lease model.
- adapter descriptors `openai-compatible` and `acp` are deliberately unimplemented;
- `control_plane/model_router.py` refuses an enabled provider whose adapter is unimplemented and
  requires `production_armed=false` while routing is not accepted;
- worker-eligible aliases and `control_plane/executive_agent_capabilities.py` currently allow only
  the reviewed Codex execution surfaces;
- `config/executive_worker_routes.json` keeps xAI disabled and contains no Cursor alias;
- `docs/EXECUTIVE_WORKER_ROUTING.md` requires credential isolation, structured output, session
  identity, cancellation, checkpoint/handoff and quota evidence before external providers enable;
- Executive OS remains Job/Attempt/Worker/Event and atomic-claim authority;
- Operator Harness generation/epoch and process fencing remain session/reconciliation authority;
- Model Router remains task/model suitability authority;
- Agent OS remains durable organizational workstream/decision/handoff authority.

Provider-native agent/session IDs may be persisted only as bounded evidence on the existing
Attempt/harness epoch. They never become a competing job identity or session database.

---

## 3. Authentication ownership and isolation law

### 3.1 Common rules

Every accepted provider realm must have:

- one dedicated non-interactive OS principal or an equivalently reviewed isolated service
  principal;
- one provider-owned configuration/session home inaccessible to the Chairman's normal app/home;
- one immutable provider alias and credential realm binding in root-owned installed config;
- provider-manifest-specific authentication at the exact broker-owned child boundary: a worker-local
  broker may inject an allowed static/short-lived credential only when the accepted descendant-
  environment falsifier proves that model-spawned commands cannot read it; a provider-managed home
  remains provider-managed and is never re-exported as a token;
- no secret in argv, process title, logs, Events, Slack, result, exception, checkpoint, receipt,
  workspace file, Git, clipboard or model context;
- no credential-byte inspection as readiness or capacity evidence;
- native provider renewal only inside the dedicated realm, or an already-owned, reviewed one-way
  worker-local operation that returns a token directly to the provider child without persistence in
  Executive state;
- sanitized readiness based on metadata, command success and bounded provider response, never raw
  credential content.

The Chairman's ordinary Codex app, Cursor app, Chrome profile, shell home and Keychain items are
out of scope for worker authentication. A normal desktop login must never be reused as an
automation shortcut.

### 3.2 Human ceremonies are bounded administration

Some initial credential issuance remains inherently human:

- issuing a Cursor user API key when no Enterprise service account exists;
- approving Grok browser/device authorization for a new consumer worker realm;
- granting an MCP OAuth connection where the MCP has no service credential;
- exceptional rotation/revocation or ambiguous destructive approval.

These ceremonies occur once per dedicated realm through a native masked/provider flow. Afterward,
normal Job routing, session start, renewal, result collection, cancellation and reconciliation are
machine-owned. Human ceremony does not make the Chairman an MCP bus or prompt relay.

---

## 4. Cursor authentication ruling

### 4.1 Conditional V1 candidate

The first Cursor candidate uses a manually issued user API key stored in root-provisioned,
worker-private secret storage and made available by the existing worker-local broker as
`CURSOR_API_KEY` to the exact `agent acp` child. The route is not accepted until **Cursor-C0** proves
both the credential boundary and the effective configuration boundary on the exact installed
binary. It runs under a dedicated OS principal whose normal provider configuration/cache
directories are isolated by that principal's private home.

Rules:

- use the environment mechanism, never the `--api-key` argv form;
- do not run `agent login` in the Chairman's ordinary Mac account as an automation solution;
- do not copy a Cursor desktop/browser login, cookie, local auth cache or refresh material;
- do not treat `CURSOR_AUTH_TOKEN` as a consumer OAuth broker: the ACP documentation exposes the
  input but does not freeze a public consumer issuance/renewal contract;
- do not claim Personal subscription remaining capacity; absent a documented endpoint the value
  is null with an explicit unknown reason;
- do not claim a closed Cursor ACP profile merely from a private home. The documented CLI loads
  project/user instructions and MCP configuration, including repository `AGENTS.md`/`CLAUDE.md`;
  exact effective-config census and reliable suppression of every unapproved user/team/plugin/
  project MCP, hook, rule and subagent surface must be proven by Cursor-C0 on the installed binary;
- bind the protected-basis SHA-256 digests of intentionally allowed repository instructions:
  `AGENTS.md=b7878cdec9567af693209ce7548c1da558bd4e8933e8d5baf094bada47521aaf` and
  `CLAUDE.md=65e7e526dd09abc933e57c4c5de8ef69d6c4f4b5b4c400e9d172d6591e7b099f`.
  A changed digest or any additional effective instruction/configuration source fails closed;
- a 401/403 is an auth outcome; a 429 is cooling/rate evidence. Neither proves another account is
  free or authorizes blind failover.

If Cursor-C0 finds no supported, reliable census and suppression path for all ambient authority,
the local ACP route returns to Sol. A later Cursor SDK profile is a separate reviewed route: it must
use `setting_sources=[]`, an empty inline MCP configuration and a closed tool surface, and it must
still enter through the existing `WorkerExecutionAdapter` and Executive Attempt lifecycle.

Browser-cookie or cached-refresh-token scraping is `REJECTED_BY_DESIGN`.

### 4.2 Enterprise route — held pending credential-owner freeze

Cursor documents one-hour user-scoped worker tokens minted with an agent-scoped team service-account
key for an active team member. This route remains `SPEC_ONLY` and held until a bounded credential-
owner micro-freeze proves that an existing canonical worker-local secret owner can hold the service-
account key, mint the token and deliver it one-way to the exact child. No new control credential
service, token database or renewal plane is authorized.

The worker token:

- is short-lived;
- cannot mint another worker token;
- cannot refresh itself;
- must be replaced only by the accepted existing worker-local credential owner;
- is injected only into the exact child and is not persisted in Executive events/state.

Service-account execution cannot silently inherit a human user's MCP OAuth grants. Every MCP
credential used by a service worker must have its own reviewed service-safe authorization.

### 4.3 Cloud Agents are a later execution profile

Cursor Cloud Agents, the local CLI/ACP surface and the Cursor SDK are different provider surfaces.
The first vertical proves local ACP. Cloud Agents may become a later provider manifest using its
documented API, worker tokens and usage endpoint, but may not bypass the accepted Attempt,
authority, branch/worktree, cancellation and receipt law.

Official primary sources:

- <https://cursor.com/docs/cli/reference/authentication>
- <https://cursor.com/docs/account/enterprise/service-accounts>
- <https://cursor.com/docs/cloud-agent/api/endpoints>
- <https://cursor.com/docs/cli/acp>
- <https://cursor.com/docs/sdk/python>
- <https://cursor.com/docs/cli/reference/output-format>
- <https://cursor.com/docs/cloud-agent/capabilities>
- <https://cursor.com/docs/plugins>
- <https://cursor.com/docs/account/teams/admin-api>

---

## 5. Grok/xAI authentication ruling

### 5.1 Keep the credential planes separate

Grok Build agent authentication and xAI inference API authentication are different planes:

- xAI inference uses `XAI_API_KEY` as a static API-key path;
- Grok Build documents browser OIDC, RFC 8628 device authorization, Enterprise OIDC/external auth
  and API-key operation;
- API-key QPS/QPM/TPM limits must never be represented as Grok consumer-subscription remaining
  headroom;
- a disabled future direct-inference alias remains distinct from the Grok Build ACP worker alias.

### 5.2 Conditional consumer OAuth candidate

The first Grok Build worker candidate uses:

- one dedicated OS principal;
- one private, dedicated `GROK_HOME`;
- one one-time `grok login --device-auth` ceremony under that principal;
- one dedicated browser profile and provider-account identity used only for that worker realm;
- the provider's built-in refresh behavior inside that realm;
- exact pinned Grok Build binary/version/digest;
- `grok --no-auto-update agent stdio` for deterministic ACP execution.

The broker supplies only the fixed private-home binding required by the reviewed manifest. It never
opens, copies, parses or injects Grok auth files or token bytes; Grok alone manages persisted auth
and renewal inside that home.

The route is not accepted until **Grok-B0** proves the browser/account identity boundary before and
after enrollment. `GROK_HOME` isolates provider files; it does not by itself isolate the browser
session or provider account selected during authorization. The enrollment page/code may therefore
be shown only through the dedicated browser profile/session. The token, refresh token and auth files
are never copied to chat, clipboard, Executive state or another user, and the Chairman's normal
browser/app account state must remain untouched. If Grok exposes a non-secret team/account/realm
identifier, Grok-B0 binds it in sanitized installed configuration and readiness evidence. If it does
not, identity remains explicitly unknown and concurrent multi-account Grok routing stays disabled.

### 5.3 Enterprise alternatives

Enterprise may use:

- PKCE OIDC with the documented issuer/client configuration and refresh-token grant; or
- `auth_provider_command` returning either a bare access token or the documented JSON object with
  `access_token`, optional `refresh_token` and optional `expires_in`.

The external command is accepted only if:

- its path/digest/argv are root-owned and fixed by the provider manifest;
- it receives no model/caller-authored input;
- Grok itself receives its stdout through an uncaptured one-way channel; Executive and the worker
  broker never capture, parse, copy or persist that credential stream;
- logs/events never receive its output;
- when `GROK_AUTH_EXPIRED=1`, it refreshes silently and quickly or fails closed;
- it never opens an interactive window during background renewal.

### 5.4 Capacity limits

Consumer weekly remaining is visible in provider product UI, but no official machine endpoint is
frozen here. It remains null/unknown in Capacity Fabric. xAI Management API key ceilings and
inference 429 outcomes may provide API-key-specific evidence only. No UI scraping is authorized.

Official primary sources:

- <https://docs.x.ai/build/enterprise>
- <https://docs.x.ai/build/settings>
- <https://docs.x.ai/build/cli/headless-scripting>
- <https://docs.x.ai/build/cli/reference>
- <https://docs.x.ai/build/features/mcp-servers>
- <https://docs.x.ai/build/features/skills-plugins-marketplaces>
- <https://docs.x.ai/developers/rate-limits>
- <https://docs.x.ai/developers/rest-api-reference/management>
- <https://docs.x.ai/developers/management-api-guide>
- <https://docs.x.ai/developers/rest-api-reference/management/auth>
- <https://docs.x.ai/grok/faq>

---

## 6. One provider-neutral ACP adapter

The implementation target is:

```text
Executive Job
  -> existing atomic Worker/quota claim
  -> existing Attempt + authority/effective grant/placement
  -> existing Operator Harness epoch and process generation
  -> existing distinct-UID worker broker
  -> one reviewed ACP adapter
       -> secret-free Cursor provider manifest
       -> secret-free Grok Build provider manifest
  -> provider session ID attached to the existing Attempt/epoch
  -> normalized terminal result/cancel/reconcile evidence
```

The shared ACP adapter implements only the existing `WorkerExecutionAdapter` operations:

- **start:** launch one exact allowlisted binary under the already-selected worker principal,
  initialize ACP, apply only the provider manifest's accepted authentication mode, create/load a
  session only when advertised and persist only the non-secret provider session ID on the existing
  Attempt/harness epoch;
- **collect_result:** consume bounded protocol updates, enforce permission/profile policy and
  normalize one terminal result plus redacted evidence;
- **cancel:** send the advertised ACP cancellation operation, then apply the existing broker
  process/UID/epoch fencing and absence proof; ambiguous cancellation remains effect-unknown;
- **run_validation_argv:** execute only the exact reviewed non-secret validation command through
  the existing validation law.

Provider manifests, not separate adapters, bind:

```text
provider alias
exact executable path, digest and version
ACP command
auth mode and credential realm
isolated provider home policy
model enumeration/selection
advertised session operations
permission vocabulary
expected MCP/plugin/skill/subagent census
typed provider error map
capacity observation map
```

The adapter must probe advertised ACP capabilities. Cursor documents `session/load`. The current
Grok ACP documentation does not freeze equivalent load semantics. If the shipped Grok server does
not advertise a resumable operation, the adapter fails closed and returns to Sol; it may not infer
ACP resume from Grok's separate headless `--session-id`/`--resume` feature.

Required core/provider changes are released only after CF2-I, RF1 and HF1 are accepted **and** the
Autonomy V1 parent has proven one real Claude worker child Job through the common harness with
terminal receipt, cancellation/absence, replay and restart-reconciliation evidence:

- add one reviewed `acp-agent` execution surface to the existing capability registry;
- implement the currently false `acp` descriptor;
- extend current router surface admission only for reviewed disabled ACP aliases;
- add disabled, secret-free Cursor and Grok provider/model manifests;
- keep `production_armed=false` through fixture/contract work;
- add no ACP session table, credential API, provider queue or provider retry ledger.

---

## 7. RF1 and HF1 boundaries

RF1 owns suitability only:

- task kind, risk, ambiguity, required capabilities, model/provider equivalence tier and permitted
  execution profile;
- it does not select accounts, inspect credentials, manage renewal, interpret live quota or create
  provider sessions.

HF1 owns execution harness only:

- exact binary launch, ACP protocol, permission mediation, session start/load identity,
  cancellation, process absence, restart reconciliation, attestation and secret isolation;
- it does not create Jobs, choose models/accounts, own retry policy, persist organizational memory
  or create provider-specific lifecycle state.

CF2/Capacity Fabric remains availability evidence and deterministic eligible-seat ranking. It may
not declare Cursor/Grok model suitability or treat unknown subscription headroom as free.

---

## 8. Provider verticals

Cursor-C0, Grok-B0 and all real provider verticals below remain executable-work held until that
Claude common-harness proof is accepted. Official-source research and deterministic fake fixtures
may proceed in parallel; they cannot install/authenticate/enable a provider or claim the gate passed.

### 8.1 Cursor ACP — generic-core proof

Observable mission:

> One bounded read-only Executive review/research Job runs through the shared ACP adapter on one
> dedicated Cursor worker, returns a typed result, and reconciles or cancels without a duplicate
> Attempt.

Prerequisite Cursor-C0 installed-binary probe:

1. enumerate the exact Cursor Agent path, digest and version;
2. discover and record every effective user/team/plugin/project MCP, hook, rule, instruction and
   subagent source without reading any credential bytes;
3. prove supported suppression of every unapproved source and bind the exact protected-basis
   instruction digests frozen in Section 4.1;
4. run hostile user/team/project fixtures and fail closed on any uncensused or unsuppressed source;
5. prove that `CURSOR_API_KEY` is unavailable to model-spawned command, tool and subagent
   descendants; otherwise reject local ACP and return to Sol.

Only after Cursor-C0 passes, scope is:

1. implement the generic adapter against a deterministic hostile fake ACP server;
2. add disabled `cursor` provider/model aliases;
3. install one dedicated worker principal and exact Cursor Agent binary;
4. make `CURSOR_API_KEY` available only through the accepted broker/child boundary;
5. enforce the Cursor-C0 effective-config allowlist; the expected extension census is empty, while
   only the exact-digest protected-basis `AGENTS.md`/`CLAUDE.md` instructions are allowed;
6. handle initialize, authentication, session/new, prompt/update stream, permission requests,
   cancellation and advertised session/load;
7. bind the provider session ID to the existing harness epoch;
8. run one harmless read-only canary only after independent review and provider readiness.

Explicit non-goals: Cursor Cloud Agents, dynamic plugins, MCP, subagents, write mode, browser-login
automation, auto-created PRs and production enablement.

### 8.2 Grok Build ACP/OIDC — adapter reuse proof

Observable mission:

> One bounded read-only Executive review/research Job uses a dedicated Grok Build OAuth realm
> through the already-accepted ACP adapter, proving the second provider required no new lifecycle
> or broker.

Scope:

1. reuse the accepted adapter and add only a Grok manifest/error map;
2. install one dedicated worker principal, private `GROK_HOME` and exact Grok Build binary;
3. pass Grok-B0, then complete the one-time device ceremony through the dedicated browser profile
   and provider identity without touching the Chairman's normal browser/app/home/account state;
4. launch `grok --no-auto-update agent stdio` through the broker;
5. verify sanitized effective configuration through `grok inspect --json`;
6. deny MCP, plugins, skills, hooks, subagents, write mode and auto-approval; expected extension
   census is empty;
7. probe ACP capabilities and fail closed if required lifecycle/cancel semantics are absent;
8. run one harmless read-only canary, cancellation/absence proof and restart reconciliation.

Explicit non-goals: direct xAI inference, API-key limit routing, MCP/plugin enablement, inferred ACP
resume, dynamic extension installation and production enablement.

---

## 9. MCP, plugin and subagent capability wave

Only after both base provider verticals pass may one separate shared capability-profile wave grant:

1. one exact reviewed MCP server;
2. then one exact reviewed provider plugin/skill bundle;
3. then bounded provider-native subagents if their lifecycle can remain subordinate to one
   Executive Attempt.

Every granted profile freezes:

- MCP URL/command, transport, OAuth/service-auth mode and exact tool schema;
- plugin/skill manifest, installed file digests and hook/command inventory;
- expected effective extension census;
- permitted workspace/root and network/resource authority;
- timeout, permission, cancellation and redaction behavior;
- whether provider-native child agents may spawn and how their IDs/events map to the parent Attempt.

Administrative installation/configuration happens before the Job. The model may not install,
upgrade, authorize or discover extra extensions dynamically. Missing, extra or changed extension
state fails closed. A provider-native subagent cannot satisfy independent review of its own parent
Attempt; cross-provider/account independent review requires another Executive Attempt.

---

## 10. Acceptance and security tests

The common ACP implementation must prove:

- deterministic fake-server contracts for initialize, auth, new/load, prompt/update, permission,
  cancel, terminal result, malformed frames, oversize frames, hangs and disconnects;
- secret can never reach argv, sanitized environment census, logs, events, exceptions, checkpoints,
  receipts, result payloads, Git/workspace files, sibling processes or model-spawned descendants;
- provider session ID maps to exactly one existing Attempt and harness epoch;
- restart reconciliation never creates a second provider turn for an effect-unknown operation;
- permission requests outside the frozen profile fail closed;
- cancellation yields protocol acknowledgement plus broker process/UID/generation absence proof;
- provider auto-update is disabled or version drift is refused;
- an exact closed effective-extension census is required for base canaries; Cursor additionally
  binds the exact allowed repository-instruction digests discovered by Cursor-C0;
- 401/403, 429, context exhaustion, permission denial, protocol violation and provider outage map to
  typed bounded outcomes without raw provider bodies;
- consumed usage is descriptive evidence only;
- consumer subscription remaining stays null when no official endpoint exists;
- no schema migration, provider session table, queue, retry ledger, credential API or duplicate
  lifecycle is added.

Cursor-specific falsifiers:

- no browser/desktop cookie or refresh cache is read;
- Cursor-C0 proves every effective configuration/instruction source or rejects the local ACP route;
- hostile user/team/project MCP, hook, rule, instruction and subagent fixtures fail closed;
- the key is unavailable to model-spawned command/tool/subagent descendants;
- `--api-key` is rejected by the manifest;
- absent/rotated key fails safely without affecting the Chairman's normal Cursor app;
- service-account worker token cannot self-refresh or mint another token;
- service workers cannot inherit human MCP OAuth grants.

Grok-specific falsifiers:

- dedicated `GROK_HOME` is private and separate from every interactive home;
- Grok-B0 proves a dedicated browser profile/session and intended provider-account identity before
  and after authorization;
- device enrollment affects only the dedicated filesystem and browser/account realm;
- no raw auth file/token inspection occurs;
- built-in refresh stays within the realm;
- external auth background refresh honors `GROK_AUTH_EXPIRED=1` without UI or log output, and its
  credential stream is consumed only by Grok;
- missing ACP resume/load capability fails closed;
- Grok consumer weekly usage is never replaced by xAI API-key QPS/QPM/TPM evidence.

---

## 11. Real proof and promotion sequence

Green CI is not acceptance. Each provider vertical requires one exact installed-host packet:

1. exact Mastermind release and provider binary path/digest/version;
2. sanitized dedicated-principal/home ownership and mode receipt;
3. sanitized auth-readiness result with no secret contents;
4. disabled route/config before canary;
5. one Chairman-authorized harmless Job and one canonical command identity;
6. one Worker/quota claim, one Attempt and one harness epoch;
7. provider session identity recorded only on that Attempt/epoch;
8. terminal typed result or bounded cancellation with process absence proof;
9. same-command replay creates zero second provider turn/Attempt;
10. before/after extension census and secret/PII scan;
11. consumed-usage evidence where officially available and explicit null remaining capacity;
12. disarm/rearm/restart reconciliation.

Promotion order:

```text
CF2-F accepted
  -> CF2-I same-provider Codex capacity proven
  -> RF1 suitability accepted
  -> HF1 common harness accepted
  -> one real Claude worker child Job proves the common harness, receipts, cancel, replay and recovery
  -> Cursor-C0 installed-binary config and credential-boundary probe
  -> Cursor ACP base vertical only if Cursor-C0 passes
  -> Grok-B0 dedicated browser/account identity probe
  -> Grok Build ACP/OIDC reuse vertical only if Grok-B0 passes
  -> one shared MCP capability
  -> one shared plugin/skill capability
  -> bounded provider-native subagents
  -> quota-aware heterogeneous fan-out only after evidence exists
```

No base provider vertical may hold the earlier Codex-only capacity canary. Research and fixture work
may proceed in parallel; provider enablement and real auth ceremonies remain dependency-gated.

---

## 12. Explicit non-goals and stop conditions

This source-law carrier does not include:

- Cursor or Grok login;
- CLI installation or OS-user creation;
- CF2 implementation, account selection or quota scraping;
- RF1/HF1 implementation;
- live provider routing, production arming or automatic failover;
- MCP/plugin installation or authorization;
- provider-native subagent enablement;
- browser-cookie/token/cache copying;
- VPS/multi-host transport;
- another Agent OS/Executive OS/router/memory/lifecycle plane.

Stop and return to Sol if implementation would require:

- exporting consumer browser cookies/refresh caches;
- reusing the Chairman's ordinary app/home/session;
- persisting a raw credential in Executive state;
- an undocumented token renewal or subscription-remaining endpoint;
- a second queue/session database/retry ledger;
- provider-native session semantics the shipped ACP server does not advertise;
- dynamic model-controlled installation/authorization;
- treating a provider child agent as independent review;
- weakening the dedicated-principal boundary;
- accepting local Cursor ACP without a reliable effective-config census, supported suppression and
  descendant-environment credential proof;
- authorizing Grok device/OIDC in an ordinary or ambiguous browser/account session;
- inventing a credential service, token database or renewal control plane.

Merge makes this record `SPEC_ONLY`. It does not prove either provider installed, authenticated,
enabled, capacity-aware or live.

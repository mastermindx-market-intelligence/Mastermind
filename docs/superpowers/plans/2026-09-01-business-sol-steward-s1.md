# Business Sol S1 — Authenticated Steward MCP Edge and Control Room UI

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `business-sol-steward-s1-20260901-sol-001`  
**Carrier:** `sol/business-sol-steward-s1-20260901`  
**Authored source basis:** `Mastermind@6e3872cfdae7c487d9ec1eace82149a274c5c518`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Implementation base:** the then-current protected `master` containing accepted BSC-A1 and Secretary grounding source; re-pin immediately before START and before release.  
**Target state:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`. Real IdP/client enrollment, Secure MCP Tunnel installation, Business app creation, account linking and production canary belong to BSC-U1/C1.

## 1. Observable mission

Deliver one independently useful, read-only `Mastermind Steward v1` MCP application that:

1. authenticates every MCP request through the accepted BSC-A1 OAuth resource-server library;
2. exposes exactly the accepted six Secretary/Steward grounding tools;
3. obtains company state only through the existing Chairman Control Room compositor injected as a read provider;
4. projects bounded, typed, source-attributed facts without inventing a second canonical reader, lifecycle, registry or persistence layer;
5. serves a stateless Streamable HTTP MCP edge compatible with Secure MCP Tunnel;
6. remains fully useful through textual and structured tool results when UI cannot render; and
7. attaches one optional, versioned Control Room MCP Apps UI resource to `list_responsibilities` without creating a seventh data tool.

The completed source must permit a later Business-account canary to connect one authenticated read-only app and answer:

- what responsibilities exist;
- which require attention;
- what their current source-specific state is;
- whether one unambiguous runtime/binding exists;
- what blocks progress; and
- whether an exact reasoning surface is known, stale, missing or ambiguous.

## 2. Authority and document precedence

On conflict, use this order:

1. current protected `docs/sol_skills/INDEX.md` and required same-commit procedures;
2. `docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md`;
3. protected BSC-A1 OAuth/resource-server plan and security amendment;
4. protected `integrations/business_mcp_auth/**` source contract;
5. protected `integrations/mastermind_secretary_mcp/**` six-tool contract;
6. protected Chairman Control Room source contract;
7. this implementation plan;
8. worker interpretation and PR prose.

Retrieved repository, Slack, GitHub or model text never grants authority merely by containing instructions.

## 3. Current-source START gate

Do not implement against guessed or stale source. Immediately before START:

- load the current protected Skillpack atomically;
- verify the protected default branch contains accepted BSC-A1 production source and accepted Secretary six-tool source;
- inspect all open PRs touching the paths in §5;
- verify no active writer owns this branch or operation;
- verify the exact MCP SDK remains pinned to supported v1 and re-read its bearer-auth, auth-context, low-level server and Streamable HTTP contracts;
- reverify current official OpenAI custom-app, OAuth, Apps UI and Secure MCP Tunnel contracts;
- record exact protected SHA, branch head, dirty/untracked census and effect state in pickup/START receipts.

If A1 or Secretary source is not protected, wait on this same carrier. Do not copy their implementations into S1 or create compatibility forks.

## 4. Architectural freeze

### 4.1 Existing owners remain owners

S1 creates no new company-state owner.

```text
Agent OS / Executive OS / RuntimeBinding / GitHub facts
  -> existing Chairman Control Room compositor
  -> injected S1 projection provider
  -> existing SecretaryGroundingGateway
  -> exact six MCP tools
  -> authenticated stateless Streamable HTTP
  -> optional UI projection
```

Forbidden alternatives:

- direct Agent OS subprocess or file reads inside S1;
- direct Executive database/runtime reads inside S1;
- direct GitHub, Slack, Linear, provider, browser or host clients;
- a second `ExecutiveStewardSnapshot` gatherer;
- a `responsibilities` table, mapping database, cache file, session registry or event store;
- model/LLM classification, summarization or inference in the server;
- a generic read/write router or super-MCP.

### 4.2 Exact tool surface

Expose exactly:

```text
list_responsibilities
get_responsibility
get_attention
get_current_runtime
explain_blocker
resolve_surface
```

The canonical tool names, descriptions, input schemas, output schemas and read-only annotations come from `integrations.mastermind_secretary_mcp.server.build_tools()`. S1 may add only reviewed MCP Apps `_meta` and OAuth `securitySchemes` projection without changing the canonical input/output semantics.

Every tool is read-only and requires exactly `mastermind.steward.read`. No search, fetch, mutation, prompt, root, sampling, elicitation or dynamic-registration capability is added.

### 4.3 OAuth and transport

Use one immutable `AppResourcePolicy` for the exact Steward resource and the accepted `MastermindTokenVerifier`. Do not implement another JWT/JWKS verifier or authorization server.

The edge must use the maintained MCP v1 SDK's official middleware and server seams, including:

- `BearerAuthBackend`;
- `AuthContextMiddleware`;
- the low-level MCP server/tool handlers; and
- `StreamableHTTPSessionManager` in stateless mode with no event store.

Unauthenticated protected-resource metadata remains reachable. The MCP resource itself must challenge missing/invalid bearer access through the accepted A1 challenge generator. Successful tool calls must carry the verified principal supplied by the auth context; model arguments never select subject, issuer, client, resource or scopes.

No authorization endpoint, token endpoint, consent screen, DCR service, refresh-token store, login UI, cookie session, API key fallback or tunnel credential belongs in this wave.

### 4.4 UI is optional projection

Register one immutable UI resource such as:

```text
ui://mastermind/steward/control-room-v1.html
```

with the current supported MCP Apps HTML profile MIME. Attach it only to `list_responsibilities` through the reviewed tool metadata field. Do not add a seventh tool merely to open the UI.

The component:

- renders only bounded sanitized structured content returned by the tool;
- uses inert text rendering (`textContent` or equivalent), never HTML interpolation;
- has no external scripts, fonts, stylesheets, images, analytics or network domains;
- creates no state authority, action control, hidden write, background polling or credential access;
- clearly renders `FACTS`, `UNKNOWN`, `DEGRADED`, `REFUSED`, stale, ambiguous and empty states; and
- may fail completely without preventing normal textual/structured tool use.

## 5. Exact implementation surface

Expected new paths:

```text
docs/superpowers/plans/2026-09-01-business-sol-steward-s1.md
integrations/mastermind_steward_app/__init__.py
integrations/mastermind_steward_app/projection.py
integrations/mastermind_steward_app/server.py
integrations/mastermind_steward_app/ui.py
integrations/mastermind_steward_app/app.py
scripts/mastermind_steward_app.py
tests/test_mastermind_steward_projection.py
tests/test_mastermind_steward_server.py
tests/test_mastermind_steward_http.py
tests/test_mastermind_steward_ui.py
tests/test_mastermind_steward_static_fences.py
```

A small manifest/dependency adjustment is permitted only if required by the already-pinned MCP v1 transport and current installed Starlette stack. Do not widen or repin unrelated dependencies.

Frozen existing paths—consume, do not edit without a separately proven blocker and Sol ruling:

```text
integrations/business_mcp_auth/**
integrations/mastermind_secretary_mcp/**
control_plane/chairman_control_room.py
control_plane/executive_steward.py
control_plane/executive_runtime.py
control_plane/surface_bindings.py
```

## 6. Public responsibility identity

A public `responsibility_ref` is a deterministic, opaque, snapshot-reconstructable projection. It is not a new identity registry.

Use exactly one versioned derivation function:

```text
responsibility_ref =
  "responsibility:" + sha256(
      b"mastermind-steward-responsibility-v1\x00" + utf8(work_ref)
  ).hexdigest()
```

Rules:

- `work_ref` must be an exact existing Control Room work-card key;
- the adapter reconstructs the map from the current snapshot on every call;
- no mapping is persisted, cached to disk or accepted from model input;
- duplicate derived refs or duplicate work cards fail closed with `AMBIGUOUS_JOIN`;
- an unknown ref returns `UNKNOWN / RESPONSIBILITY_UNKNOWN`;
- raw `WS:` values may appear only as approved, attributed `agent_os` source refs, never as tool arguments or UI control coordinates.

## 7. Deterministic projection contract

`projection.py` is pure except for calling one injected snapshot provider. It imports no MCP SDK, HTTP framework, filesystem, subprocess, database, network client or environment API.

### 7.1 Source references

Only namespaces accepted by the Secretary contract may leave the adapter:

- Agent OS responsibility: exact `WS:<KEY>` when already canonical;
- Executive attention/job: `MAS:` plus a domain-separated SHA-256 digest of the internal identifier;
- runtime binding: `RUNTIME:` plus a domain-separated SHA-256 digest;
- surface binding: `SURFACE:` plus a domain-separated SHA-256 digest;
- no attributable source: bounded `UNKNOWN:` digest.

Never expose raw Job IDs, attention IDs, binding IDs, provider account names, host paths, URLs, channel/thread IDs, session handles, credentials or arbitrary upstream text as source references.

### 7.2 Time and freshness

- inject `now` for tests; production uses UTC;
- normalize accepted timestamps to UTC whole-second `Z` form;
- reject non-finite, malformed or future-skewed timestamps instead of repairing them heuristically;
- use source-specific observation time when the existing projection provides one;
- otherwise use the Control Room `generated_at` only as compositor observation time;
- stale facts are never emitted as `FACTS`; use `DEGRADED` with `STALE_SOURCE`;
- missing time remains `UNKNOWN`, not freshly timestamped by wrapper creation.

### 7.3 Responsibility state

Map only explicit accepted source values through a closed table to:

```text
ACTIVE | BLOCKED | COMPLETE | WAITING | UNKNOWN
```

Unrecognized or conflicting source states produce `UNKNOWN`/`DEGRADED`; do not vote, average or let GitHub merge state override Agent OS organizational state.

Emit `responsibility.requires_attention` from exact joined attention IDs. Do not emit `responsibility.priority` unless the current canonical source supplies an accepted numeric priority; S1 must not invent one from list order, age or model judgment.

### 7.4 Attention

- no joined attention -> `attention.state = NONE`;
- exactly one unambiguous target maps mechanically to `CHAIRMAN_REQUIRED`, `SOL_REQUIRED`, `COO_REQUIRED` or `EXTERNAL_REQUIRED`;
- conflicting simultaneous targets or ambiguous joins -> `DEGRADED / AMBIGUOUS_JOIN`, without a synthetic winner;
- arbitrary reason/summary prose never becomes authority or a new enum.

### 7.5 Runtime

- exactly one unambiguous active Executive job may map mechanically to `RUNNING` or `PAUSED`;
- no active job and no contradictory evidence may map to `IDLE` or `STOPPED` only when source semantics support it;
- multiple current jobs, disagreement or missing runtime source -> `DEGRADED`/`UNKNOWN`, never a fabricated overall status;
- `runtime.continuity` derives only from exact current bindings: zero `UNBOUND`, one accepted binding `BOUND` or `STALE`, multiple conflicting bindings `AMBIGUOUS`, unavailable source `UNAVAILABLE/UNKNOWN`;
- `runtime.age_seconds` is emitted only from a valid exact observation time and bounded by the Secretary contract.

### 7.6 Blocker

Always prefer truthful absence/unknown over a confident invented kind.

- explicit no-blocker source -> `blocker.present=false`, `blocker.kind=NONE`;
- unmet dependency list -> `EXTERNAL_DEPENDENCY`;
- exact Chairman/Sol authority gate -> `AUTHORITY_REQUIRED`;
- source ambiguity/staleness/unavailability -> corresponding `SOURCE_*` or `RUNTIME_UNAVAILABLE` value;
- unrecognized prose -> `UNKNOWN`.

### 7.7 Surface

The current Control Room binding proves routing evidence, not provider responsiveness.

- zero exact bindings -> `TARGET_MISSING` or typed unknown;
- multiple/conflicting bindings -> `AMBIGUOUS` and `surface.repair_required=true`;
- one binding without accepted live-health evidence -> `UNKNOWN`, not `RESPONSIVE`;
- stale observation -> `DEGRADED`/`STALE_SOURCE` and repair required;
- emit observation age only from a valid source timestamp.

### 7.8 Bounds and truncation

Respect the Secretary contract's request, response, fact, source and reason-code limits. Deterministic truncation is allowed only at a documented stable sort boundary and must return `DEGRADED / STEWARD_DEGRADED`; silent truncation is forbidden.

## 8. Ordered TDD implementation

### Task 1 — Freeze plan and RED projection fixtures

Files:

```text
docs/superpowers/plans/2026-09-01-business-sol-steward-s1.md
tests/test_mastermind_steward_projection.py
```

Write fixtures for:

- one healthy responsibility;
- unknown responsibility ref;
- duplicate/colliding work card;
- Agent OS/GitHub disagreement;
- missing Executive runtime;
- multiple current jobs;
- no/one/multiple bindings;
- stale/future/malformed timestamps;
- more than 64 responsibilities;
- adversarial text and credential/path-shaped internal IDs.

Run the focused test and capture RED because `integrations.mastermind_steward_app.projection` does not exist. Commit RED separately.

### Task 2 — Implement pure Control Room projection

Files:

```text
integrations/mastermind_steward_app/__init__.py
integrations/mastermind_steward_app/projection.py
```

Implement one injected asynchronous snapshot provider and a `StewardReadPort` implementation. No source gathering. Make Task 1 GREEN, add mutation-style tests for ref derivation, ambiguity, stale-state refusal, no-synthetic-priority and no-responsive-without-health.

### Task 3 — Freeze exact MCP tool/resource projection

Files:

```text
tests/test_mastermind_steward_server.py
integrations/mastermind_steward_app/server.py
integrations/mastermind_steward_app/ui.py
```

RED first for:

- exactly six tools;
- canonical input/output schemas preserved;
- every tool read-only and scoped to `mastermind.steward.read`;
- no roots/prompts/sampling/elicitation/dynamic registration;
- `list_responsibilities` alone references one versioned UI resource;
- tool calls delegate exactly once through `SecretaryGroundingGateway`;
- text fallback and structured result are equivalent;
- fixed opaque errors; no upstream exception text.

Implement with the pinned MCP v1 low-level server. Do not duplicate Secretary validation.

### Task 4 — Implement optional inert Control Room UI

Files:

```text
integrations/mastermind_steward_app/ui.py
tests/test_mastermind_steward_ui.py
```

RED first for exact resource URI/MIME, no external origins, no dynamic HTML interpolation, no action controls, and visible FACTS/UNKNOWN/DEGRADED/REFUSED/empty states. Implement one self-contained static HTML document. UI output must remain bounded and secret-free.

### Task 5 — Implement authenticated stateless Streamable HTTP app

Files:

```text
integrations/mastermind_steward_app/app.py
tests/test_mastermind_steward_http.py
```

RED first for:

- protected-resource metadata available without bearer access;
- missing/invalid token gets the exact A1 challenge and zero tool/provider call;
- wrong issuer/resource/scope/subject/client is refused;
- Steward token succeeds;
- Executive/Dialogue token is refused cross-resource;
- auth context contains only the bounded verified principal;
- MCP manager is stateless and has no event store;
- GET/POST/DELETE transport behavior matches the pinned SDK;
- oversized/malformed request fails closed;
- server restart remembers no bearer token, grant, session or responsibility map.

Compose the official MCP bearer/auth-context middleware with the accepted `MastermindTokenVerifier`; do not reparse JWTs in S1.

### Task 6 — Add production-inert launcher and closed configuration

Files:

```text
scripts/mastermind_steward_app.py
```

Use a closed trusted configuration object or exact environment names for deployment-supplied issuer, resource, JWKS URL, authorization-server metadata and subject policy. No CLI/model argument selects host, issuer, JWKS URL, resource, scope or subject. The launcher creates no daemon/service install, credential, tunnel or account effect.

Errors are fixed and opaque. Logs may contain only server generation, bounded pseudonymous principal/audit values and typed reason codes—never bearer tokens, raw subjects, cookies, headers, environment dumps, source paths or arbitrary exception text.

### Task 7 — Static authority/security fences and integration proof

Files:

```text
tests/test_mastermind_steward_static_fences.py
```

Prove:

- projection core has no direct canonical-store/network/filesystem/subprocess imports;
- S1 has no database/session/event-store implementation;
- no Slack/GitHub/Linear/provider/browser clients;
- no authorization/token/login/consent/DCR endpoints;
- no mutation tools or write annotations;
- exact six-tool digest is stable;
- UI contains no external domains, form/action control or credential access;
- credential markers and private paths never appear in serialized results/errors;
- existing Secretary, Executive MCP, Company Dialogue, Chairman Control Room and A1 auth suites remain green.

Run focused S1 tests, all adjacent regressions, compile, `git diff --check`, secret scan and the repository test gate.

### Task 8 — Hosted proof and release return

Push non-force to the same branch and open/update one PR. Require:

- current protected-base join;
- exact changed-path census;
- hosted repository CI;
- CodeQL/security analyses;
- separate exact-head adversarial review;
- text fallback proof;
- ASGI-level authenticated canary with ephemeral keys and zero external account effect;
- capability state `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

Return `RESULT / HOLD-FOR-SOL`; do not merge, deploy, install a service/tunnel, create an OAuth client, mutate Business workspace settings or run the real account canary.

## 9. Acceptance tests

Minimum focused commands, adjusted only for actual accepted filenames:

```bash
python -m pytest -q \
  tests/test_mastermind_steward_projection.py \
  tests/test_mastermind_steward_server.py \
  tests/test_mastermind_steward_http.py \
  tests/test_mastermind_steward_ui.py \
  tests/test_mastermind_steward_static_fences.py

python -m pytest -q \
  tests/test_mastermind_secretary_mcp.py \
  tests/test_mastermind_secretary_mcp_gateway.py \
  tests/test_mastermind_secretary_mcp_static_fences.py \
  tests/test_business_mcp_auth_*.py \
  tests/test_chairman_control_room.py \
  tests/test_executive_mcp_sdk_pin.py

python -m compileall -q integrations/mastermind_steward_app scripts/mastermind_steward_app.py
python scripts/ci_pytest.py
git diff --check
```

A passing suite must demonstrate the actual authenticated ASGI/MCP path with ephemeral signing keys; mocks that bypass the bearer middleware do not satisfy the vertical.

## 10. Failure-state matrix

| Condition | Required result |
|---|---|
| Control Room provider raises/times out | fixed `STEWARD_UNAVAILABLE`; no stale-file fallback |
| snapshot schema wrong | `STEWARD_UNAVAILABLE` or `RESPONSE_REFUSED`; no heuristic parsing |
| unknown public responsibility ref | `UNKNOWN / RESPONSIBILITY_UNKNOWN` |
| duplicate/colliding ref or work card | `DEGRADED/UNKNOWN / AMBIGUOUS_JOIN` |
| source unavailable | typed unknown/degraded; absence never rendered healthy |
| source stale | `DEGRADED / STALE_SOURCE` |
| source disagreement | preserve as degraded/ambiguous; never choose a winner silently |
| missing bearer token | exact A1 401 challenge; zero tool/provider call |
| wrong app token | refuse cross-resource; zero tool/provider call |
| malformed/oversized request | fixed refusal; no exception/body/header echo |
| UI resource fails | text and structured tool result still complete |
| server restarts | no remembered session, token, grant or ref map |
| breaking tool/UI metadata change | new immutable server/app generation, not silent drift |

## 11. Explicit non-goals

No Executive write tool, CEO intent, dialogue write, RuntimeBinding mutation, Wake operation, GitHub/Slack/Linear action, Agent OS write, provider call, browser automation, authorization server, IdP tenant, OAuth client registration, user directory, session/token/refresh store, Secure MCP Tunnel install, DNS/TLS deployment, Business workspace/app creation, plugin import, account authentication or production claim.

## 12. Production-proof boundary and continuation

Source acceptance only establishes:

```text
Mastermind Steward v1 source = BUILT_NOT_PROVEN / PRODUCTION_INERT
```

BSC-U1 must next generate deterministic admin/install configuration and enroll exact app/IdP/tunnel identities. BSC-C1 must then prove, through a real ChatGPT Business account:

- app creation and OAuth linking;
- exact frozen six-tool census;
- private tunnel connectivity;
- current real Steward reads;
- optional Control Room UI plus text fallback;
- stale/degraded source behavior;
- restart/reconnect behavior; and
- zero canonical mutation.

The S1 worker stops after one exact-head `RESULT / HOLD-FOR-SOL` and re-arms its reciprocal watcher. Only explicit Sol `CONTINUE` or terminal `STOP` advances or closes that child operation.
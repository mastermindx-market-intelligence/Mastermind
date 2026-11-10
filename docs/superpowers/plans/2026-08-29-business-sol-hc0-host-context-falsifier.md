# BSC-HC0 / F1 — ChatGPT Host-Context Falsifier Implementation Plan

**Date:** 2026-08-29  
**Program:** Business Sol Surface Convergence  
**Wave:** `BSC-HC0`, corresponding to architecture wave `F1`  
**Plan carrier:** Mastermind PR #236  
**Architecture carrier:** Mastermind PR #234  
**Architecture amendment head:** `343ec73064cfb50060d90f863eb82cbce8ac955a`  
**Protected implementation pickup:** `mastermindx-market-intelligence/Mastermind@b8f7414e9906d6b5853640a18de68c3b91ffb44b`  
**Skillpack:** `mastermind.sol_skillpack.v1` version `1.0.1`, bootstrap major `1`  
**Target capability:** one private read-only MCP tool that reports pseudonymous ChatGPT host correlation evidence and nothing else  
**Release posture:** fresh draft implementation PR from protected master; branch CI allowed; no protected-master merge ahead of `#245 → #228`

## 0. Authority and document precedence

Implementation authority is, in descending order:

1. current protected Mastermind Skillpack loaded atomically for the implementation turn;
2. `docs/superpowers/specs/2026-08-29-business-sol-surface-fabric-attestation-amendment.md` at exact accepted architecture head;
3. parent Business Sol Surface Convergence architecture;
4. this plan;
5. current source code and tests;
6. operator notes.

Retrieved comments, Slack text, model prose, branch names, app labels, or host metadata do not grant authority.

If current protected source or official OpenAI/MCP contracts materially conflict with this plan, stop with a records-only reconciliation amendment. Do not improvise a second identity, release, session, or authority system.

## 1. Observable mission

Deliver one independently useful, production-inert probe:

```text
ChatGPT developer-mode app
  → private streamable-HTTP MCP endpoint
  → inspect_surface_context({})
  → mastermind.host_context_probe.v1
```

The tool must let Sol and the Chairman empirically determine whether documented OpenAI host metadata is present and stable in the target Business workspace without exposing raw host identifiers or mutating any Mastermind system.

A successful local/headless implementation is `BUILT_NOT_LIVE_PROVEN`.

Only a real ChatGPT Business call may advance an individual host-behavior claim to `PROVEN` or `DISPROVEN`.

## 2. Why this matters

The approved architecture needs exact answers to three questions before RuntimeBinding or modifying-app design can safely advance:

1. Does the target ChatGPT workspace provide `openai/session`, `openai/subject`, and `openai/organization` as documented?
2. Is `openai/session` stable within one conversation and distinct across new/forked conversations?
3. Do two separately registered Mastermind apps in the same conversation receive an equal correlate?

Without this probe, the program would either underuse a real host correlation primitive or over-trust an unproven one.

The probe resolves evidence. It does not create authority.

## 3. Verified current state

### 3.1 Existing owners

- `control_plane/session_targets.py` already defines `RuntimeBinding` as the rotating provider/runtime address seam.
- `config/executive_agent_capabilities.json` and `control_plane/executive_agent_capabilities.py` already own exact MCP/plugin capability grants and remain `production_armed=false`.
- `integrations/mastermind_company_mcp/` already demonstrates an SDK-isolated MCP adapter with strict model-visible inputs.
- `pyproject.toml` pins `mcp==1.28.0` in the dev dependency set.
- MCP Python SDK `1.28.0` preserves request `_meta` extension fields through `RequestParams.Meta(extra="allow")`.
- Company Dialogue, Executive, Steward, RuntimeBinding, Wake, Agent Relay, and Agent OS already exist as owners and must not be absorbed.

### 3.2 Related carriers

- #234 — Business architecture, draft/hold;
- #236 — program plans, draft/hold;
- #237 — OAuth resource-server plan, records only;
- #243 — historical plugin implementation closed unmerged and branch reset; not current implementation truth;
- #245 — watcher-continuity release procedure, current serialized predecessor;
- #228 — Steward release carrier, follows #245;
- #240 — canonical Project Workroom architecture.

### 3.3 Collision ruling

HC0 may use a fresh branch from current protected master because its implementation paths are disjoint from #245 and #228 and it performs no protected-master merge.

HC0 must not edit:

- `control_plane/session_targets.py`;
- `config/executive_agent_capabilities.json`;
- `control_plane/executive_agent_capabilities.py`;
- Executive, Steward, Company Dialogue, Wake, Agent Relay, Slack, Linear, or Agent OS runtime paths;
- plugin marketplace or plugin package paths;
- OAuth code or credentials.

## 4. Exact scope

Repository: `mastermindx-market-intelligence/Mastermind` only.

Fresh branch:

`sol/business-sol-hc0-host-context-probe-20260829`

Expected implementation files:

```text
integrations/mastermind_surface_probe/__init__.py
integrations/mastermind_surface_probe/schemas.py
integrations/mastermind_surface_probe/probe.py
integrations/mastermind_surface_probe/server.py
docs/runbooks/business-sol-host-context-probe.md
tests/test_mastermind_surface_probe.py
tests/test_mastermind_surface_probe_mcp.py
```

`pyproject.toml` remains unchanged unless the exact protected dependency cannot support the required request-context and structured-output behavior. A dependency change requires an explicit plan amendment and collision review with #237.

## 5. Explicit non-goals

HC0 does not:

- publish an app to production;
- enroll OAuth;
- create a public endpoint;
- create a plugin package;
- change any capability registry;
- create a RuntimeBinding;
- create or administer a lease/fence;
- infer Chairman, Sol, worker, Job, Attempt, or operation identity;
- admit an Executive Job;
- write to Company Dialogue, Slack, Linear, GitHub, Agent OS, or Executive OS;
- persist a session or host identifier;
- create a Business-session database;
- create a signed bearer receipt;
- expose raw `_meta` values;
- use userAgent or location as authorization;
- classify cross-app stability from unit tests;
- auto-retry a modifying effect, because no modifying effect exists in this wave.

## 6. Complete user journey

### 6.1 Local/headless journey

1. An operator starts the probe on loopback with an explicit immutable app realm, app generation, HMAC key ID, HMAC key, and fingerprint scope.
2. Startup fails closed if configuration is malformed, secret material is absent/weak, or the app generation is not bounded.
3. An MCP client lists exactly one tool: `inspect_surface_context`.
4. The listed tool has an empty closed input schema, exact output schema, read-only/idempotent/non-destructive/closed-world annotations, and no resources/prompts/sampling/elicitation.
5. A synthetic request `_meta` map is passed only through the MCP request context, never model arguments.
6. The response contains field presence and keyed fingerprints, never raw values.
7. Missing optional host fields produce explicit degradations without guessing.
8. Malformed values fail closed or produce the exact documented degradation according to the contract.
9. No file, database, network target other than the MCP response, or canonical system changes.

### 6.2 Business beta journey

1. The Chairman upgrades one designated Sol account to ChatGPT Business Premium.
2. A workspace owner creates a private developer-mode app pointing through Secure MCP Tunnel to the local probe endpoint.
3. The app invokes `inspect_surface_context` in one conversation.
4. The returned fingerprints and presence flags are copied into a bounded experiment receipt; raw host IDs never leave the server process.
5. The matrix is repeated for same chat, new chat, forked chat, refresh, reconnect, republish, reauthentication, and a second probe app registration.
6. Each claim is recorded as `PROVEN`, `DISPROVEN`, or `UNKNOWN`, with app generation, server digest, HMAC key ID/scope, observation time, and exact test condition.
7. HC0 stops. No RuntimeBinding or write authority is created.

## 7. Data contract

### 7.1 Tool input

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

The model cannot supply identity, session, organization, subject, app generation, HMAC configuration, OAuth state, or transport state.

### 7.2 Tool output

Schema identity:

`mastermind.host_context_probe.v1`

Required top-level fields:

```text
schema
server_identity
server_version
app_realm
app_generation
contract_digest
transport_profile
fingerprint_key_id
fingerprint_key_version
fingerprint_scope
observed_at
correlation_only
host_context
oauth_posture
degradations
```

`host_context` has exact fixed keys:

```text
openai_session
openai_subject
openai_organization
openai_widget_session
user_agent_hint
user_location_hint
```

Each row contains:

```text
present: boolean
fingerprint: bounded string or null
usable_for_authorization: false
```

Only the four identifier-like fields may have fingerprints. User-agent and location rows report presence only and never values or fingerprints.

`oauth_posture` in HC0 contains:

```text
configured: false
resource: null
scopes: []
principal_fingerprint: null
```

HC0 must not pretend anonymous/no-OAuth transport is authenticated.

`degradations` is a unique, sorted bounded list selected from a closed enum.

### 7.3 Candidate degradation codes

```text
OPENAI_SESSION_ABSENT
OPENAI_SUBJECT_ABSENT
OPENAI_ORGANIZATION_ABSENT
OPENAI_WIDGET_SESSION_ABSENT
USER_AGENT_HINT_ABSENT
USER_LOCATION_HINT_ABSENT
UNKNOWN_HOST_META_IGNORED
TUNNEL_ATTESTATION_UNAVAILABLE
OAUTH_NOT_CONFIGURED
```

Malformed present values are not silently converted to absent. They raise one bounded MCP/tool error and no fingerprint response is returned.

## 8. Configuration contract

The pure core receives an immutable configuration object with:

```text
app_realm
app_generation
transport_profile
fingerprint_key_id
fingerprint_key_version
fingerprint_scope
fingerprint_secret
```

Validation:

- identifiers use bounded lowercase ASCII slugs;
- app generation is immutable and bounded;
- HMAC secret is bytes and at least 32 bytes;
- key ID/version/scope are non-secret bounded identifiers;
- transport profile is descriptive only and cannot imply authentication;
- no default or development fallback secret;
- secret values are excluded from repr, dataclass conversion, logs, output, exceptions, and schema snapshots.

The runnable server loads configuration from explicit environment variables only. It binds loopback by default. Non-loopback bind is refused in HC0.

Suggested variables:

```text
MASTERMIND_SURFACE_PROBE_APP_REALM
MASTERMIND_SURFACE_PROBE_APP_GENERATION
MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE
MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID
MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION
MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE
MASTERMIND_SURFACE_PROBE_HMAC_KEY
MASTERMIND_SURFACE_PROBE_HOST
MASTERMIND_SURFACE_PROBE_PORT
```

The runbook must instruct operators to supply secrets out of band and never paste them into chat, Slack, GitHub, Linear, logs, or receipts.

## 9. Fingerprint method

For every identifier-like host field:

```text
HMAC-SHA-256(
  secret,
  canonical_utf8(
    schema,
    app_realm,
    app_generation,
    field_name,
    raw_value
  )
)
```

Requirements:

- explicit domain separation;
- unambiguous length-prefixed or canonical JSON encoding;
- UTF-8 only;
- input length bounded before hashing;
- lowercase hex or unpadded base64url output with exact regex;
- constant-time operations where comparison is performed;
- no raw value in error strings;
- same input/config yields same fingerprint;
- field name, realm, or generation changes the result;
- absent value yields `null`, not an HMAC of an empty string.

The HMAC is a correlation label, not encryption and not reversible by design. Low-entropy input risk is mitigated by a secret key, but the output still must not be treated as a credential.

## 10. Time, null, correction, and replay behavior

- `observed_at` is injected as an aware UTC datetime in the pure core and serialized as canonical RFC 3339 with `Z`.
- Production server obtains the time once per call.
- Unit tests use fixed times.
- Missing optional metadata is explicit null + degradation.
- Unknown metadata keys are ignored and reported only as `UNKNOWN_HOST_META_IGNORED`; key names and values are not echoed.
- Repeating the same request is read-only and deterministic except for `observed_at`.
- The probe persists no prior observation, so there is no correction or replay store.
- Experiment receipts are separate records-only evidence and must include the exact app/server generation and key scope used.

## 11. Deterministic versus empirical methods

### 11.1 Deterministic

- configuration validation;
- model-visible input closure;
- host metadata extraction;
- strict scalar/string validation;
- length/control-character validation;
- HMAC derivation;
- response schema and digest;
- annotations;
- raw-value exclusion;
- no-persistence/no-authority path census;
- exact tool inventory;
- loopback-only launcher.

### 11.2 Empirical

- actual metadata presence in ChatGPT Business;
- repeat-call stability;
- new/forked conversation distinction;
- cross-app equality;
- refresh/reconnect/reauth behavior;
- organization/device behavior;
- app republish/generation behavior.

Empirical claims require real Business receipts. Synthetic tests only prove parser and fingerprint mechanics.

## 12. Failure states

| Failure | Required behavior |
|---|---|
| Missing HMAC secret | server startup fails closed |
| Weak HMAC secret | server startup fails closed |
| Invalid generation/realm/key identifiers | server startup fails closed |
| Non-loopback host | server startup fails closed |
| Model supplies any argument | `INVALID_REQUEST`, no data |
| `_meta` missing | valid response with all host rows absent and exact degradations |
| Host value non-string | bounded refusal, no raw value |
| Host value empty/oversized/control-character | bounded refusal, no raw value |
| Unknown `_meta` key | ignored; one bounded degradation; never echoed |
| HMAC/core exception | fixed internal error; no stack/secret/raw value in response |
| OAuth absent | explicit unauthenticated posture; no auth inference |
| Tunnel evidence unavailable | explicit degradation; transport profile remains descriptive |
| Output exceeds bound | fixed internal error |
| Second tool/resource/prompt appears | tests and CI fail |
| File/DB/network write introduced | adversarial path tests/review fail |
| Live cross-app result inconsistent | record `DISPROVEN` or `UNKNOWN`; do not create fallback DB |

## 13. Ordered TDD implementation sequence

### Task 1 — RED: pure output and raw-value exclusion

Create `tests/test_mastermind_surface_probe.py` first.

First discriminating tests:

1. same host values + same config produce stable fingerprints;
2. response never contains any raw session/subject/organization/widget value;
3. field/realm/generation domain separation changes fingerprints;
4. missing values are explicit nulls with sorted degradations;
5. malformed values fail without echoing raw content;
6. secret/config never appears in repr or output;
7. time is canonical and injected.

Run exact test file and record failure caused by missing module, not syntax/import corruption.

### Task 2 — GREEN: SDK-free schema and probe core

Implement:

- `integrations/mastermind_surface_probe/schemas.py`
- `integrations/mastermind_surface_probe/probe.py`
- package `__init__.py`

The pure modules must not import `mcp`, FastAPI, Starlette, Uvicorn, Slack, Linear, GitHub, Executive, Agent OS, SessionTarget, RuntimeBinding, or any persistence library.

Run Task-1 tests to green.

### Task 3 — RED: exact MCP surface

Create `tests/test_mastermind_surface_probe_mcp.py`.

Tests must prove:

- exactly one listed tool;
- exact name, title, description, closed input schema, output schema, and annotations;
- no resource, prompt, sampling, elicitation, or dynamic registration surface;
- request `_meta` is read from MCP request context, not arguments;
- unknown arguments are refused;
- structured result matches the pure core;
- server can expose a stateless streamable-HTTP ASGI app;
- default launcher is loopback only;
- no raw values appear in MCP content, structured output, or errors.

Run exact test and witness RED.

### Task 4 — GREEN: MCP adapter and loopback launcher

Implement `integrations/mastermind_surface_probe/server.py` as the only package module that imports the MCP SDK.

Use the pinned SDK contract. Prefer FastMCP only where it preserves:

- exact annotations;
- exact output schema;
- request-context `_meta` access;
- stateless streamable HTTP;
- no additional model-visible primitives.

The adapter must normalize `RequestParams.Meta` through a bounded mapping without serializing unrelated values.

The launcher must:

- require explicit configuration;
- bind `127.0.0.1` or `::1` only;
- expose `/mcp` streamable HTTP;
- enable stateless HTTP and JSON response when compatible with the target ChatGPT client;
- emit no secret or host identifier in logs.

Run exact MCP tests to green.

### Task 5 — Adversarial contract and runbook

Create `docs/runbooks/business-sol-host-context-probe.md` with:

- prerequisites;
- secret-safe configuration;
- local launch command;
- health/list-tools/call smoke procedure;
- Secure MCP Tunnel setup boundary;
- private developer-mode app creation checklist;
- live experiment matrix;
- exact receipt template;
- stop and cleanup procedure;
- prohibition on raw-ID capture and authority inference.

Add adversarial tests or static census proving:

- no persistence imports/paths;
- no authority-owner imports;
- no second tool;
- no plugin/registry/runtime changes;
- no secret-shaped fixtures.

### Task 6 — Verification and PR closeout

Run fresh:

```text
pytest -q tests/test_mastermind_surface_probe.py
pytest -q tests/test_mastermind_surface_probe_mcp.py
pytest -q
```

Then verify:

- current protected master and Skillpack still compatible;
- exact branch diff and file census;
- no unrelated changes;
- no raw IDs/secrets/tokens/private keys;
- hosted CI on exact head;
- CodeQL/security checks if configured;
- PR remains draft/hold;
- capability state remains `BUILT_NOT_LIVE_PROVEN`.

## 14. Acceptance tests

HC0 implementation is accepted for branch-level completion only if:

1. one and only one model-visible tool exists;
2. tool input is empty and closed;
3. tool output is exact and structured;
4. raw documented host identifiers are absent from all output/error/log fixtures;
5. HMAC derivation is deterministic and domain-separated;
6. malformed metadata is refused safely;
7. missing metadata is explicit and non-fatal;
8. OAuth absence is explicit;
9. no persistence or canonical-owner mutation exists;
10. launcher is loopback only and fail-closed on configuration;
11. exact tests and full suite pass on the exact head;
12. hosted CI is green on that exact head;
13. implementation PR remains draft and unmerged under the active serialization gate.

## 15. Real production proof

Production/live proof requires all of the following through the actual ChatGPT Business path:

```text
private published/developer app generation
→ Secure MCP Tunnel or approved private transport
→ real ChatGPT tool call
→ exact mastermind.host_context_probe.v1 response
→ no raw host identifier exposure
→ experiment receipt committed to the canonical research/architecture carrier
```

Minimum live matrix:

| Claim | Condition | Required classification |
|---|---|---|
| Same-app repeat stability | two calls, same conversation/app generation | PROVEN / DISPROVEN / UNKNOWN |
| New-chat distinction | same app, new conversation | PROVEN / DISPROVEN / UNKNOWN |
| Fork behavior | same app, forked conversation | PROVEN / DISPROVEN / UNKNOWN |
| Cross-app equality | two separate probe app registrations, same conversation, controlled cohort key | PROVEN / DISPROVEN / UNKNOWN |
| Refresh stability | page refresh, same conversation | PROVEN / DISPROVEN / UNKNOWN |
| Reconnect stability | tunnel/server reconnect | PROVEN / DISPROVEN / UNKNOWN |
| Generation behavior | new app/server generation | PROVEN / DISPROVEN / UNKNOWN |
| Reauth behavior | OAuth reconnect when later configured | PROVEN / DISPROVEN / UNKNOWN |
| Organization behavior | another authorized organization if available | PROVEN / DISPROVEN / UNKNOWN |
| Missing-field behavior | host omits optional field | PROVEN / DISPROVEN / UNKNOWN |

No claim can be inferred from the documentation alone when the question is target-workspace behavior.

## 16. Stop condition

Stop the wave when:

- the draft implementation PR is green and branch-reviewed;
- the local probe is runnable;
- the beta upgrade/app-creation checklist is ready;
- or a material platform/source conflict is found and recorded.

Do not proceed within the same carrier to:

- plugin attestation;
- OAuth;
- registry mutation;
- RuntimeBinding;
- Executive write;
- Company Dialogue write;
- production publication;
- protected-master merge.

## 17. Required continuation handoff

The HC0 closeout must contain:

- exact protected pickup SHA and Skillpack;
- exact implementation branch/head/PR;
- exact file census;
- exact schema and contract digest;
- MCP SDK version actually tested;
- exact local commands and outputs;
- hosted CI run identity/status;
- capability classification;
- unresolved platform facts;
- whether the account should now upgrade for beta testing;
- exact next carrier: live Business experiment if runnable, otherwise one named blocker;
- explicit statement that no authority, binding, Job, or durable session state was created.

## 18. Chairman-facing subscription decision

When Tasks 1–6 are green and the private endpoint is runnable, recommend upgrading the designated Sol account immediately for **beta development**.

Do not wait for the entire Mastermind OS or full plugin suite to finish before the beta upgrade, because HC0, app-generation testing, OAuth enrollment, and in-chat experience design require the real Business host.

Do not call that upgrade an operational cutover. Operational cutover remains governed by the architecture amendment’s F2–F10 proof gates.
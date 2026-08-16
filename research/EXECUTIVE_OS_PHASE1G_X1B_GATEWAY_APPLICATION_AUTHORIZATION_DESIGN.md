# Executive OS Phase 1G — X1-B gateway application authorization design

**Status:** commissioned design; no production write arming  
**Date:** 2026-08-15  
**Prerequisites:** X0-A evidence, X1-A private READONLY tunnel reachability, PR #64 READONLY/FIXTURE gateway contract  
**Blocks:** X5 production write arm, X6 autonomous continuation, X7 autonomous improvement

---

## 0. Objective

Authenticate the **Executive caller** at the private Mastermind MCP gateway even when Secure MCP Tunnel supplies only private connectivity and tunnel-runtime authentication.

The architecture must distinguish at least:

```text
READONLY
CEO_AGENT
CHAIRMAN_INTERACTIVE
ADMIN_OPERATOR
```

without trusting model text, tool arguments, Slack text, actor labels, tunnel id, conversation id, activation id, or source IP as identity.

---

## 1. Security invariant

A modifying call is authorized only if:

```text
transport reachable
AND app principal authenticated
AND app principal active/not revoked
AND principal class permits the operation family
AND canonical decision category permits the executive altitude
AND current activation/intent/request fence permits the exact operation
AND operation idempotency permits the exact replay state
```

The first failure returns a typed refusal and performs zero mutation.

No authentication claim carried inside the MCP tool arguments changes `authenticated_principal`.

---

## 2. Threat model

Treat as hostile or untrusted:

- a valid OpenAI-side caller that can reach the same tunnel;
- an ordinary ChatGPT conversation in the same organization;
- another Workspace Agent;
- a Codex session;
- a Responses/API client;
- a stale Sol activation;
- a model that fabricates `actor=chairman`;
- a prompt-injected model that copies a credential-looking string from evidence;
- a replay of a previously valid MCP call;
- a leaked/rotated connector credential;
- a tunnel runtime compromise that has the tunnel runtime key but not the Executive application credential;
- a connector/config republish that changes authentication behavior;
- approval/config drift after acceptance;
- duplicate request delivery and ambiguous response loss.

Assume the tunnel is honest-but-not-sufficient for Executive identity. If X0-A proves a stronger property, treat it only as defense in depth unless separately promoted by review.

---

## 3. Trust boundaries

### T1 — Workspace trigger

Credential: Workspace Agent access token.  
Purpose: Executive OS -> Workspace Agent wake.  
Not accepted by Executive MCP gateway as caller auth.

### T2 — Tunnel runtime

Credential: OpenAI Platform runtime API key with minimum Tunnels Read + Use.  
Purpose: outbound tunnel daemon / poll / response.  
Not mapped to CEO or Chairman.

### T3 — Tunnel administration

Credential: separate admin/manage key.  
Purpose: create/update/delete tunnel configuration.  
Never installed in long-lived runtime.

### T4 — Executive MCP application principal

Credential: OAuth bearer or reviewed connector-bound secret.  
Purpose: prove the application principal to the private MCP gateway.  
This is the only remote identity input that may map to `CEO_AGENT`, `CHAIRMAN_INTERACTIVE`, or `READONLY`.

### T5 — Executive activation/decision state

Credential-like correlation: activation id/generation/request id/operation key.  
Purpose: freshness, scope, idempotency, exact decision binding.  
Never substitutes for T4 authentication.

---

## 4. Preferred protocol: OAuth-protected Executive MCP

### 4.1 Protected resource

The Executive MCP endpoint advertises OAuth Protected Resource Metadata according to the MCP/OpenAI-supported flow.

Logical audience:

```text
mastermind-executive-mcp
```

### 4.2 Required validated token claims

Minimum server validation:

```text
issuer allowlist exact match
signature/algorithm allowlist
exp present and valid
nbf valid if present
aud includes mastermind-executive-mcp
sub present, stable, mapped server-side
scope contains only reviewed capability class
jti/replay handling where issuer supports it
```

Reject:

- unsigned tokens;
- algorithm confusion;
- wildcard issuer/audience;
- missing subject;
- expired/not-yet-valid tokens;
- unknown principal;
- client-supplied role not bound by issuer/server mapping.

### 4.3 Principal registry

Logical server-side registry, not model-visible:

```text
principal_id: workspace-sol-service
principal_class: CEO_AGENT
status: active
credential_version: ...
allowed_tool_families: [read, ceo_bounded_write]

principal_id: chairman-chris
principal_class: CHAIRMAN_INTERACTIVE
status: active
allowed_tool_families: [read, chairman_decision]
```

A principal registry confers only access to reviewed tool families; operation-specific authority remains downstream of decision-category and fence checks.

### 4.4 Agent-owned versus end-user connection

Desired live shape:

- autonomous Workspace Sol: agent-owned/shared service connection authenticated as `workspace-sol-service`;
- Chairman interactive surface: end-user identity authenticated as `chairman-chris`.

X0-A must prove the actual Business Workspace can express this. If not, production direct Chairman action remains unavailable and Chairman decisions use another separately authenticated typed channel.

---

## 5. Interim protocol: connector-bound bearer secret

Allowed only as an X1-B canary if OAuth is unavailable or operationally incomplete.

### 5.1 Secret construction

- >=256 bits cryptographic randomness;
- one secret per principal/configuration;
- never reused between CEO_AGENT and Chairman;
- versioned (`kid`/credential version) outside the secret;
- stored in product connector secret configuration and a server secret store;
- never checked into Git.

### 5.2 Transport

Use a connector-configured header such as:

```text
Authorization: Bearer <opaque-principal-secret>
```

or a reviewed nonreserved custom auth header when product constraints require it.

The header name is not security. The secret is.

### 5.3 Verification

Server:

- exact endpoint only;
- constant-time verifier;
- no secret echo in logs/errors;
- unknown/revoked/expired credential => 401-style typed MCP auth refusal;
- principal identity derived from matched credential, not a sibling header;
- current and previous credential may overlap only during a bounded rotation window;
- replay still constrained by activation/request/operation idempotency.

### 5.4 Canary acceptance bar

Must prove:

- secret absent from model-visible prompt/context;
- secret absent from normal connector/tool schema introspection;
- secret absent from support/log exports used in acceptance;
- another OpenAI-side caller without the secret cannot invoke modifying tools;
- another connector cannot guess/select a principal with labels;
- rotation invalidates the old secret after the overlap window;
- static tunnel runtime header cannot be substituted for the principal secret.

Failure of any item rejects this mode for production.

---

## 6. Authorization pipeline

Pseudo-order, deliberately before tool execution:

```text
request arrives
  -> validate HTTP/MCP framing
  -> authenticate application credential
  -> map to immutable principal_id + principal_class
  -> enforce principal status + credential version
  -> select reviewed MCP tool spec
  -> parse strict tool args
  -> derive operation family and decision category server-side
  -> enforce principal-class ceiling
  -> load canonical activation/intent/chairman-request state
  -> verify generation/scope/request freshness
  -> enforce ExecutiveAuthorityPolicy/requested authorities/write paths
  -> verify operation_key/idempotency state
  -> execute one typed operation
  -> commit durable receipt
  -> return bounded/redacted response
```

No later stage may replace the principal produced by the authentication stage.

---

## 7. Principal ceilings

### READONLY

- Executive state/inbox/job/intent reads only;
- zero modifying tools;
- cannot create activation, intent, project, Chairman request, or decision.

### CEO_AGENT

May request only reviewed CEO tool families. Each operation is then mapped to `executive_decision_policy`.

When minimum seat is Chairman:

```text
CEO_AGENT -> may create/update canonical Chairman request
CEO_AGENT -> cannot execute reserved operation
```

### CHAIRMAN_INTERACTIVE

May act on reviewed Chairman tool family only. V1 should prefer:

```text
read pending Chairman request
approve exact request
reject exact request
```

rather than a broad arbitrary Chairman mutation tool.

### ADMIN_OPERATOR

Local/offline maintenance only. Not exposed to model routes and not carried through the Workspace Agent connector.

---

## 8. Chairman request anti-replay

Approval input does not contain mutable operation content. It names the canonical request:

```text
chairman_request_id
request_generation
operation_key
decision = approve|reject
```

Server re-loads:

- exact request body;
- immutable commission/project refs;
- current state;
- expiry;
- supersession pointer;
- required authority.

Refuse when:

- request unknown;
- not PENDING;
- generation mismatch;
- expired;
- superseded/cancelled;
- principal != CHAIRMAN_INTERACTIVE;
- operation key conflicts.

A Slack message or ChatGPT prose cannot be parsed as the decision.

---

## 9. Activation fence remains mandatory

Authentication answers **who may ask**. Activation fencing answers **whether this autonomous run is still current for this exact action**.

CEO modifying call requires:

```text
principal == CEO_AGENT
activation_id current
activation_generation current
claim state allows cognition owner
root/affected scope includes operation
activation not drained/cancelled/expired/superseded
operation_key idempotent
```

A stolen CEO application credential without the current activation state cannot fabricate a fresh generation from arguments; generation validity is loaded from canonical Executive state.

---

## 10. Credential rotation and revocation

For every remote application principal:

- server registry has `credential_version` and status;
- rotation is a typed operator procedure;
- acceptance proves old credential rejected after cutoff;
- emergency revoke is immediate and does not require Workspace Agent cooperation;
- revocation does not revoke tunnel runtime key unless incident scope requires it;
- tunnel key rotation does not silently rotate the Executive application principal.

Compartmentalization is the objective.

---

## 11. Config/version drift

A production acceptance receipt binds at least:

```text
published Workspace Agent/config identity if observable
approved custom MCP app identity
app action/tool snapshot hash
authentication mode
principal credential version/timestamp (never secret)
tunnel id
tunnel-client version/effective profile digest
Harpoon target count = 0
Executive MCP schema snapshot hash
gateway code SHA
```

Any unverified change that can alter caller identity, tool census, or approval behavior invalidates production acceptance until re-proved.

---

## 12. Harpoon prohibition

X1-B uses only the reviewed MCP channel. The Executive tunnel profile must contain zero Harpoon targets.

Acceptance mutation:

1. baseline zero targets => `harpoon` request refused;
2. test-only profile adds one target => invariant test must fail;
3. restore zero-target profile.

No production acceptance may be generated from a profile that has ever been modified without re-hashing/revalidating its effective configuration.

---

## 13. Approval interaction

OpenAI-side write confirmation is an additional product safety control, not Mastermind authorization.

Four cases:

```text
Mastermind denies + OpenAI allows  -> DENY
Mastermind allows + OpenAI denies  -> no mutation / diagnostic
Mastermind denies + OpenAI denies  -> DENY
Mastermind allows + OpenAI allows  -> operation may proceed
```

OpenAI approval state may never override the local principal/authority/fence decision.

---

## 14. Failure taxonomy

Suggested typed gateway failures:

```text
AUTH_MISSING
AUTH_INVALID
AUTH_EXPIRED
AUTH_REVOKED
AUTH_PRINCIPAL_UNKNOWN
AUTH_PRINCIPAL_CLASS_REFUSED
AUTH_CREDENTIAL_VERSION_STALE
AUTH_DECISION_CATEGORY_REFUSED
AUTH_ACTIVATION_STALE
AUTH_SCOPE_REFUSED
AUTH_REQUEST_STALE
AUTH_OPERATION_CONFLICT
APPROVAL_BLOCKED
```

No raw secret/token/error stack is returned.

---

## 15. Acceptance tests

### A. Authentication

- no credential => refuse, zero mutation;
- random credential => refuse;
- revoked credential => refuse;
- CEO credential => CEO read/bounded write allowed where policy permits;
- CEO credential => Chairman operation refused;
- Chairman credential => exact pending request decision allowed;
- Chairman credential => stale/superseded request refused;
- READONLY credential => every modifying tool refused.

### B. Confusion attacks

- `actor=chairman` with CEO credential remains CEO;
- `principal_class=CHAIRMAN_INTERACTIVE` in tool args ignored/refused;
- tunnel id or runtime header without app credential refused;
- valid Codex/other tunnel caller without app credential refused;
- prompt-injected text containing a fake bearer token does nothing unless it is the real transport credential.

### C. Replay/freshness

- same operation key/same body => idempotent same receipt;
- same key/different body => conflict;
- stale activation generation => refused;
- superseded Chairman request => refused;
- old rotated credential after cutoff => refused.

### D. Secret hygiene

- logs redact auth headers;
- exceptions redact auth headers;
- schema/tool descriptions contain no secret;
- fixture/support export contains no secret;
- Git grep finds no test production secret.

### E. Tunnel separation

- daemon runtime key alone cannot call modifying gateway endpoint successfully;
- tunnel admin key is absent from daemon environment/config;
- zero Harpoon targets;
- tunnel-client cannot read Executive DB/worker provider credentials by OS permissions.

---

## 16. Mutation/falsification battery

At minimum kill mutants that:

- trust `actor` argument;
- trust `principal_class` argument;
- skip audience verification;
- skip issuer verification;
- accept expired token;
- accept revoked credential;
- map unknown subject to CEO;
- let CEO call Chairman decision;
- let tunnel runtime header become CEO;
- skip activation generation check;
- skip request supersession check;
- disable constant-time secret compare path where applicable;
- log Authorization header;
- permit nonzero Harpoon target;
- allow old credential after rotation cutoff;
- let approval-provider success bypass local denial.

Every security invariant needs a mutant that proves the test can see its removal.

---

## 17. X1-B PASS criteria

X1-B can PASS only when:

1. a live/faithful private-tunnel path reaches the gateway;
2. at least CEO_AGENT and READONLY are cryptographically distinguishable at the gateway;
3. a wrong OpenAI-side principal cannot use the same tunnel to gain CEO write authority;
4. the principal is derived from transport/application auth, not tool arguments;
5. rotation/revocation works;
6. Harpoon is zero-target and drift-detected;
7. the gateway remains least privilege and cannot directly control deploy/merge/service/credentials;
8. tests + mutation battery prove the boundary;
9. independent security review accepts the authentication model.

`CHAIRMAN_INTERACTIVE` may remain unavailable while X5 starts with CEO-only bounded operations plus canonical Chairman requests delivered through a separately authenticated human path. Direct Chairman MCP action does not become a prerequisite unless the chosen workflow requires it.

---

## 18. Non-goals

X1-B does not:

- make Secure MCP Tunnel an authority source;
- create a generic remote shell;
- expose Executive SQLite directly;
- add production writes by itself;
- let OAuth scope replace operation-specific authority;
- let Workspace Agent ownership replace activation fencing;
- authorize Slack free text;
- authorize model-supplied identity;
- enable autonomous merge/deploy/service control/live capital;
- create a new lifecycle database or scheduler.

The result is a narrow identity layer underneath the existing typed Executive MCP contract, not a second control plane.
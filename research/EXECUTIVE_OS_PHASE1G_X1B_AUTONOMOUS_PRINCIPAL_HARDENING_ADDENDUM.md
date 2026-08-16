# Phase 1G X1-B — autonomous principal hardening addendum

**Status:** binding addendum to `EXECUTIVE_OS_PHASE1G_X1B_GATEWAY_APPLICATION_AUTHORIZATION_DESIGN.md`  
**Date:** 2026-08-15  
**Purpose:** close the identity-confusion case where an agent-owned MCP connection authenticates the published agent but does not distinguish autonomous API-triggered use from a human manually running the same published agent.

---

## 0. Additional threat

Application-layer authentication is necessary but not sufficient if the same authenticated application principal is reachable from more than one execution surface.

Example failure:

```text
published Workspace Agent = Sol
custom MCP connection = agent-owned principal -> CEO_AGENT

Executive OS API trigger -> Sol -> CEO_AGENT          # intended
human manually opens same published Sol agent
                     -> same agent-owned connection
                     -> CEO_AGENT                     # unintended identity collision
```

The activation fence still protects freshness and idempotency, but it is not caller authentication. A human-started run that can read enough canonical activation state must not inherit autonomous CEO modifying authority merely because it launched the same published agent.

---

## 1. New production invariant

A production `CEO_AGENT` modifying principal must be bound to an **autonomous-only execution route** whose application credential is not available to ordinary human-started sessions.

Required proof is one of:

1. the Business workspace/product provides a route/share/account configuration that prevents human interactive invocation from using the autonomous agent-owned connection; or
2. the autonomous route is published under a dedicated service-like workspace principal/audience that human interactive accounts cannot launch; or
3. a separately reviewed application-auth mechanism produces a cryptographically distinct autonomous principal for API-triggered execution and the local gateway can verify it.

If none can be proved:

```text
CEO_AGENT modifying mode = UNAVAILABLE
```

READONLY use may still proceed.

---

## 2. What does not solve this

The following are explicitly insufficient to distinguish autonomous Sol from an interactive run:

- `activation_id`;
- `activation_generation`;
- `conversation_key`;
- trigger input fields;
- model text saying "I was API-triggered";
- Workspace Agent name/config label;
- tunnel id;
- tunnel runtime API key;
- source IP;
- a static tunnel-client header;
- an `actor=sol` or `execution_mode=autonomous` MCP argument.

Those remain correlation/evidence, not caller authentication.

Do not add a model-visible per-activation "secret" to the trigger prompt and treat it as authentication. A prompt-visible capability can be disclosed or redirected by the model and would violate the separation between cognition and credential authority.

---

## 3. Preferred account/connection shape

Subject to X0-A proving actual product support:

```text
AUTONOMOUS SOL ROUTE
  published agent/config: sol-autonomous-<version>
  trigger access: dedicated service-like workspace principal/audience
  MCP connection: agent-owned/service identity
  gateway principal: CEO_AGENT
  human interactive launch with same connection: prohibited / proved unavailable

CHAIRMAN / DESIGN-ROOM INTERACTIVE ROUTE
  normal ChatGPT / reviewed interactive app
  MCP connection: end-user identity
  gateway principal: CHAIRMAN_INTERACTIVE or READONLY
  never inherits CEO_AGENT merely by invoking Sol-shaped instructions
```

The logical CEO mission may be shared as versioned prompt/mission content where appropriate, but the authenticated connections and publication receipts are separate deployment artifacts.

---

## 4. X0-A required falsification canaries

Add all of these to X0-A:

1. Manually open/run the exact published autonomous Sol agent, if the UI permits it, and determine which MCP application principal reaches Mastermind.
2. Attempt to use the same custom MCP app from an ordinary human-started ChatGPT session.
3. Attempt to use it from a different Workspace Agent in the same workspace.
4. Attempt to reach the same tunnel/MCP origin from Codex/Responses/API surfaces available to the organization without the Executive application credential.
5. Change the agent sharing/audience and observe whether a newly authorized human can inherit the agent-owned MCP connection.
6. Prove whether agent-owned connections are scoped to the published agent, workspace, sharing audience, or broader app installation.
7. Revoke the autonomous agent/service connection and verify CEO modifying calls fail immediately while tunnel connectivity remains healthy.
8. Verify an end-user interactive OAuth connection yields a different stable subject/principal from the autonomous agent-owned connection.

Each canary records `PROVED | REFUTED | STILL_UNKNOWN`; any ambiguous identity result fails closed for modifying authority.

---

## 5. Gateway rule

The gateway principal registry must distinguish **deployment identity** from **seat identity**:

```text
authenticated application subject -> principal_id -> principal_class
principal_class + canonical policy -> allowed operation family
seat/decision policy -> minimum executive altitude
activation/request state -> current scope/freshness/idempotency
```

No arrow runs backward from seat/model/prompt to authenticated application subject.

If the authenticated subject is a generic shared-agent identity whose execution surface cannot be bounded, map it to `READONLY`, not `CEO_AGENT`.

---

## 6. Relationship to Chairman direct action

`CHAIRMAN_INTERACTIVE` must be a distinct authenticated end-user/human principal or another separately reviewed strongly bound human channel.

The autonomous agent-owned identity can never approve a Chairman request, even when the content of the run came from Chris or the model claims Chris is present.

Likewise, Chris manually launching the autonomous Sol agent does not turn its agent-owned `CEO_AGENT` connection into `CHAIRMAN_INTERACTIVE`.

---

## 7. Acceptance consequence

X1-B may pass for production modifying authority only when:

- a cryptographically authenticated application principal reaches the gateway;
- `CEO_AGENT` cannot be obtained by an ordinary human-started or other OpenAI-side execution surface;
- `CHAIRMAN_INTERACTIVE`, if enabled, is cryptographically distinct;
- cross-surface negative canaries are included in the acceptance receipt;
- publication/share/config drift that could widen access invalidates acceptance.

This is additive to all activation, scope, authority, protected-path, and idempotency fences. It does not replace them.
# Phase 1G Workspace CEO evidence addendum — post independent review

**Date:** 2026-08-15  
**Status:** primary-source reconciliation; supplements `EXECUTIVE_OS_PHASE1G_WORKSPACE_CEO_EVIDENCE_REGISTER.md`  
**Rule:** where this addendum is more specific about Secure MCP Tunnel identity, Harpoon, application authentication, or Workspace Agent trigger behavior, it governs until the base register is rewritten.

---

## 1. API-trigger response: conservative contract remains load-bearing

Current OpenAI Workspace Agent Help Center documentation states that an API trigger queues the agent run and returns HTTP `202 Accepted` with no response body/run id, and that the final agent response cannot currently be retrieved through the trigger API.

Architecture consequence:

- no canonical invariant depends on a provider run id, response URL, or final-response retrieval;
- any richer beta/developer-reference metadata remains optional telemetry until X0-A proves it on this exact Business workspace;
- the durable Executive OS outcome is the completion authority.

---

## 2. Workspace Agent app authentication modes

Current OpenAI Workspace Agent documentation states that app connections can be configured as:

- **end-user account** — each person running the agent authenticates with their own account; or
- **agent-owned account** — the agent uses one shared connection, with a service account recommended when possible.

Architecture consequence:

- a production Executive MCP design may be able to distinguish an autonomous Sol service principal from an interactive human principal at the **application layer**;
- this is a capability to prove, not an assumption;
- X0-A must determine whether the custom MCP app on this actual Business workspace can use the needed agent-owned/end-user identity shape and whether the identity reaches Mastermind in a verifiable form.

---

## 3. Secure MCP Tunnel identity is not Executive identity

Current OpenAI `tunnel-client` documentation describes:

- a tunnel id;
- a long-lived runtime API key used by the tunnel daemon;
- a separate admin key for tunnel CRUD;
- Tunnels Read + Use for runtime users versus Read + Manage for tunnel CRUD;
- the same tunnel mechanism serving supported OpenAI product surfaces.

The tunnel wire protocol identifies tunnel commands by tunnel/request/shard fields. These are transport/routing fields, not a documented per-Workspace-Agent or per-human executive principal.

**Reclassification:**

```text
trusted per-caller Executive identity supplied by tunnel itself:
LIKELY_REFUTED / NOT LOAD-BEARING
```

X0-A still probes it. Production design does not wait for a favorable answer.

---

## 4. Positive capability: application auth headers survive the tunnel

Current OpenAI tunnel documentation explicitly states that:

- OAuth `Authorization` headers are forwarded through the tunnel to the private MCP server;
- custom MCP request headers configured on the connector/app are forwarded, subject to documented transport-header exclusions;
- OAuth discovery is supported, while the authorization server itself is not automatically tunneled.

Architecture consequence:

**X1-B gateway-level application authentication is technically plausible without making the Executive MCP server public.**

Preferred design:

```text
OpenAI product / Workspace Agent
  -> OAuth or connector-bound application credential
  -> Secure MCP Tunnel (connectivity only)
  -> private Executive MCP gateway
  -> validate application principal
  -> activation/intent + authority + idempotency fences
```

The tunnel runtime key is never the CEO/Chairman credential.

---

## 5. Static tunnel-client MCP headers do not solve caller identity

`tunnel-client` also supports static MCP headers configured on the local runtime. Those headers authenticate or label the tunnel runtime's outbound connection to the MCP origin.

They are common to traffic handled by that runtime and therefore cannot, by themselves, distinguish:

- autonomous Sol;
- an interactive ChatGPT caller;
- another OpenAI product surface that can address the same tunnel.

A static local header may be an additional transport-integrity check, but it is not the Executive principal.

---

## 6. Harpoon is a real additional channel and must be zero-target

Current OpenAI `tunnel-client` architecture/configuration documents an embedded `harpoon` channel/server for configured HTTP targets. With zero registered targets, the Harpoon channel is intentionally unroutable/unsupported.

Mastermind ruling:

```text
Executive tunnel effective Harpoon target count = 0
```

X1-A acceptance must record the effective profile and prove that a Harpoon channel request is refused. Any nonzero Harpoon target invalidates the Executive tunnel acceptance until separately reviewed.

---

## 7. Credential domains now evidenced separately

| domain | current evidence | architecture role |
|---|---|---|
| Workspace Agent trigger token | ChatGPT Workspace Agent access token / Workspace Agents scope | wake credential; exact user/principal lifecycle proved in X0-A |
| Tunnel runtime key | OpenAI Platform Runtime API key, Tunnels Read + Use | long-lived outbound tunnel daemon |
| Tunnel admin key | OpenAI Platform admin/tunnel management credential | offline CRUD/admin; never daemon-installed |
| Executive MCP application principal | OAuth bearer or proved connector-bound secret | CEO_AGENT / CHAIRMAN_INTERACTIVE / READONLY identity at gateway |

No domain is allowed to substitute for another.

---

## 8. Workspace trigger-principal dependency

OpenAI documentation describes Workspace Agent access tokens and access/sharing controls separately from Platform API keys. The architecture therefore treats the trigger token as a ChatGPT-workspace identity dependency, not as a generic inference key.

X0-A must prove:

- who/what owns the token on this workspace;
- agent sharing/access dependency;
- rotation/revocation/lifetime behavior;
- exact `401` and `403` behavior under revoked token versus lost agent access;
- whether a dedicated service-like workspace principal is supported/appropriate.

Mastermind policy: permission/share refusal is not retried as though it were provider rate limiting.

---

## 9. Model/reasoning routing

Current Workspace Agent documentation supports builder-selected model and reasoning effort, but the documented API-trigger body exposed by current evidence does not establish per-trigger dynamic model/effort selection.

Therefore X4 continues to require one of:

1. live proof of deterministic trigger-time selection;
2. separate published, reviewed Sol route/configurations for logical reasoning classes; or
3. autonomous `R2_PRO` remains unavailable.

No UI picker observation alone satisfies the production routing proof.

---

## 10. Provider run-status asymmetry

If a beta/live surface exposes run status, it is allowed to improve **negative diagnosis only**:

- `suspended`/approval waiting may surface `APPROVAL_BLOCKED` and shorten claim reconciliation;
- dispatch/run failure may trigger bounded reconciliation;
- provider `completed` may never commit the canonical Executive outcome.

If the live Business account exposes no run id/status, this diagnostic path simply remains unavailable; correctness still rests on Executive activation deadlines, claims, idempotent MCP outcomes, and reconciliation.

---

## 11. X0-A added falsification cases

X0-A must actively attempt, not merely inspect configuration:

1. non-Sol principal reaches same tunnel without Executive application credential;
2. wrong connector/application credential reaches modifying tool;
3. valid CEO_AGENT credential attempts Chairman operation;
4. valid Chairman identity attempts stale/superseded request approval;
5. connector credential/header appears in model-visible context/log export/tool args;
6. connector/application credential replay after rotation/revocation;
7. two distinct trigger events share one `conversation_key` concurrently;
8. published agent share/access change produces trigger refusal;
9. write approval causes a suspended/blocked unattended run if that telemetry exists;
10. Harpoon channel invocation with zero targets.

A production-write gate passes only on falsification evidence, not on the fact that a happy-path tool call worked.
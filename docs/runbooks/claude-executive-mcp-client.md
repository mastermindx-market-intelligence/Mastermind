# Claude Code -> Mastermind Executive MCP authenticated client

## Scope

This runbook enrolls Claude Code as a first-class OAuth public client of the **existing** Mastermind Executive HTTP MCP. It reuses the production Executive MCP, A1 resource-server policy, dedicated CeoIngress, Executive Job/admission lifecycle, Capacity/Model Router, and worker fabric.

It does **not** create another Executive app, queue, broker, scheduler, auth server, credential store, retry plane, identity plane, or capacity plane.

## Fixed topology

- Executive MCP: existing production listener on `127.0.0.1:8443`.
- Claude localhost translation edge: `127.0.0.1:8444` from `integrations/claude_executive_mcp/adapter.mjs`.
- Claude MCP resource: `http://127.0.0.1:8444/mcp`.
- Claude OAuth callback: `http://localhost:8774/callback`.
- OAuth client type: distinct public/native client, authorization-code + PKCE S256, no client secret.
- OAuth issuer/resource authority remains the installed Executive policy and its existing Auth0 tenant/API.

The callback port is intentionally not the Codex PR #633 callback. PR #633's Auth0 DCR operation remains `EFFECT_UNKNOWN` and must not be retried, cleared, reused, or inferred absent by this Claude vertical.

## Required Auth0 enrollment ceremony

An authorized Auth0 tenant administrator creates exactly one public/native application for Claude Code with the exact callback `http://localhost:8774/callback`. Enable authorization code and refresh-token use for a public client; require PKCE S256; do not create or copy a client secret into Claude.

Record only the public client ID as the enrollment output. The Executive API/resource policy stays unchanged.

## Claude registration

After the public client exists, replace the current unauthenticated `mastermind-executive` user-scope MCP registration with the same local MCP URL plus the public client ID and fixed callback port:

```text
claude mcp add --transport http --scope user --client-id <PUBLIC_AUTH0_CLIENT_ID> --callback-port 8774 mastermind-executive http://127.0.0.1:8444/mcp
claude mcp login mastermind-executive
```

Complete the interactive Auth0 sign-in/consent in the browser as the already-approved Executive subject. Do not paste tokens, cookies, JWTs, or secrets into prompts or config.

## Acceptance sequence

1. `claude mcp list` reports `mastermind-executive` connected/authenticated.
2. From the actual Claude Code surface, call only harmless Executive reads first and prove the real backend plus authenticated principal/resource policy.
3. Verify the exposed tool set is the existing five-tool Executive MCP and no extra mutation surface exists.
4. Only after read proof, submit exactly one harmless strict-v2 CEO intent under current Chairman authority.
5. Require admission `QUEUED`, `dispatched=false`, and same-carrier intent/Job readback.
6. `QUEUED` is admission only. Do not call it Worker START, execution, or end-to-end acceptance.
7. Only after carrier acceptance, run one bounded fabric proof where Fable remains parent/coordinator, lifecycle-significant routine work is canonical Executive child work, and Capacity/Model Router retains concrete provider/model/host placement. Opus remains exceptional orchestration/audit, not default labor.

If any modifying admission response is ambiguous, preserve `EFFECT_UNKNOWN` and reconcile the same request/carrier. Never resend, fail over, or mint a replacement identity.

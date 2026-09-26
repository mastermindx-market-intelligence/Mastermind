# Claude Code -> Mastermind Executive MCP authenticated client

## Status

**TRANSPORT BUILT / ENROLLMENT HELD / PRODUCTION MUTATION UNAVAILABLE**

This runbook owns the Claude Code transport and OAuth-client ceremony for the **existing** Mastermind Executive HTTP MCP. It does not grant the caller an organizational seat.

Chairman authority now requires Claude/Fable to operate as a broad COO principal, not as the CEO. The earlier version of this runbook proposed the existing CEO submit scope for Claude. That authorization is superseded and MUST NOT be provisioned from this carrier.

## Scope

The transport reuses:
- the installed Executive MCP;
- its existing OAuth resource/issuer authority;
- the dedicated CeoIngress and Executive Runtime;
- Workspace/Fabric reads;
- Capacity/Model Router and the worker fabric.

It does **not** create another Executive app, queue, broker, scheduler, auth server, credential store, retry plane, identity plane, or capacity plane.

## Fixed topology

- Executive MCP: existing production listener on `127.0.0.1:8443`.
- Claude localhost translation edge: `127.0.0.1:8444` from `integrations/claude_executive_mcp/adapter.mjs`.
- Claude MCP resource: `http://127.0.0.1:8444/mcp`.
- Claude OAuth callback: `http://localhost:8774/callback`.
- OAuth client type: public/native, authorization-code + PKCE S256, no client secret.
- OAuth issuer/resource authority remains the installed Executive policy and its existing Auth0 tenant/API.

The callback port is intentionally not the Codex PR #633 callback. PR #633's Auth0 DCR operation remains `EFFECT_UNKNOWN` and must not be retried, cleared, reused, or inferred absent by this Claude vertical.

## Current authority hold

**DO NOT enroll the production Claude/Fable client yet.**

The installed Executive App currently has a CEO-specific modifying policy. Fable must not receive that scope merely because the transport can reach it.

The future Claude/Fable client requires all of these source gates first:

1. the accepted COO Principal Mandate contract (#957);
2. the role-correct principal request/admission path;
3. the static COO Executive MCP profile inside the existing installed Executive process;
4. a distinct COO OAuth action policy on the same resource/issuer;
5. exact tool-schema proof showing the COO profile contains no CEO mutation surface.

The proposed scope spelling `mastermind.executive.coo.act` is **SPEC_ONLY** until that implementation is accepted. Do not create the Auth0 scope or client from this runbook.

The CEO-specific `mastermind.executive.intent.submit` scope is not a Fable enrollment permission.

## Future Auth0 enrollment ceremony

Only after the role-correct COO action policy is accepted, an authorized Auth0 tenant administrator may create exactly one public/native application for Claude Code with callback `http://localhost:8774/callback`.

At that future boundary:
- authorization code + refresh-token use may be enabled for the public client;
- PKCE S256 is required;
- no client secret is created or copied into Claude;
- only the accepted Executive read + COO action scopes are authorized;
- record only the public client ID as the enrollment output.

Until those gates are met, this section is procedure for a future ceremony, not current permission to perform it.

## Future Claude registration

After the authorized public client exists, the current unauthenticated `mastermind-executive` user-scope registration can be replaced with the same local MCP URL plus that public client ID and fixed callback port:

```text
claude mcp add --transport http --scope user --client-id <PUBLIC_AUTH0_CLIENT_ID> --callback-port 8774 mastermind-executive http://127.0.0.1:8444/mcp
claude mcp login mastermind-executive
```

Complete the interactive Auth0 sign-in/consent in the browser as the enrolled COO-capable Executive subject. Do not paste tokens, cookies, JWTs, or secrets into prompts or config.

## Acceptance sequence

### Transport acceptance

1. `claude mcp list` reports `mastermind-executive` connected/authenticated.
2. From the actual Claude Code surface, call harmless Executive reads and prove the real backend plus authenticated principal/resource policy.
3. Verify the exact role profile/tool schema; no ambient or CEO-specific mutation may be accepted as COO authority.
4. Prove restart/re-login behavior on the exact deployed Claude Code version.

Transport acceptance stops here while COO mutation is unavailable.

### Future COO admission acceptance

Only after the role-correct principal admission and COO MCP profile are source-accepted and installed:

1. recover the current COO mandate/mission through canonical reads;
2. submit one harmless bounded **COO principal** request under an exact current mission;
3. require one stable request identity and same-carrier status/reconciliation;
4. require admission `QUEUED`, `dispatched=false`, and canonical Job readback;
5. preserve `QUEUED` as admission only, never Worker START;
6. run one bounded Fable-parent -> Executive child -> Capacity/Model Router -> Worker START -> returned result -> Fable consumption vertical.

No step may substitute a CEO intent for the COO request.

If any modifying admission response is ambiguous, preserve `EFFECT_UNKNOWN` and reconcile the same request/carrier. Never resend, fail over, or mint a replacement identity.

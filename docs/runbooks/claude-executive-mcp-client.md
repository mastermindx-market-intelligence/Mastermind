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

## Role-route convergence and scoped native registration

The source adapter now translates local `/mcp` to the fixed upstream `/mcp/coo`, never to the CEO route. It requires the existing installed `coo.policy` to share Executive resource/issuer/metadata identity and require exactly Executive read plus COO action. Missing role configuration refuses startup; missing upstream COO service is not permission to fall back.
The local protected-resource document uses the installed metadata path and exposes only those two role scopes. A CEO or foreign-scope challenge is rejected rather than triggering an authority upgrade. Claude's native callback remains fixed at `http://localhost:8774/callback`; for the upstream authorization-code flow only, the adapter rewrites `redirect_uri` to `http://127.0.0.1:8444/oauth/callback`. That callback requires exactly one authorization-response `iss` equal to the configured canonical issuer on success and error responses, then translates the response issuer to the local facade issuer before returning to Claude. The token exchange uses the same adapter callback upstream. PKCE challenge/verifier, state, client ID, resource and role scopes remain otherwise unchanged. A lost upstream response is uncertain and must be reconciled under the original operation, never blindly retried.

The earlier SPEC_ONLY status was a source-freeze boundary, not a permanent reason to stop implementation. Draft backend sources now exist (#1064/#1066/#1068/#1073); independent acceptance, exact installation, capability profile/delegation and actual native authentication remain owed. This adapter change alone grants none of them. The live installed adapter is not automatically changed by merging this source.

After those source and installation gates, use a single native registration with explicit scopes rather than asking the provider to infer them from a combined server catalog. The equivalent public-client fields are `--client-id <PUBLIC_AUTH0_CLIENT_ID>` and `--callback-port 8774`; use this JSON form to carry the scope restriction as well, not both registration commands:

```text
claude mcp add-json mastermind-executive '{"type":"http","url":"http://127.0.0.1:8444/mcp","oauth":{"clientId":"<PUBLIC_AUTH0_CLIENT_ID>","callbackPort":8774,"scopes":"mastermind.executive.read mastermind.executive.coo.act"}}' --scope user
```

Inspect and reconcile the existing registration before any replacement. Never clear an existing token or remove/recreate a client as a retry for an uncertain operation. No client secret is supplied. Claude may add `offline_access` when the issuer advertises refresh support; it is not a modifying resource permission.

Native acceptance must still verify issuer handling through the real current Claude/IdP ceremony before authentication is called proven. The source adapter now closes the prior issuer-consistency defect without stripping `iss` or suppressing client validation: it advertises the local facade issuer, terminates the upstream authorization response at the adapter callback, validates the canonical upstream `iss`, and emits the corresponding local issuer to Claude. Source fixtures prove positive/error translation plus missing/foreign/duplicate-issuer refusal, but they do not prove the installed IdP/native-client ceremony, login state or token storage. Any real refusal remains a canary failure to reconcile, not permission to weaken issuer validation.

Primary references verified during this source unit: Claude Code MCP documentation, sections preconfigured OAuth credentials, fixed callback port and restrict OAuth scopes (`https://code.claude.com/docs/en/mcp`); MCP2026-07-28 Authorization, scope selection and authorization-response validation (`https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization`).

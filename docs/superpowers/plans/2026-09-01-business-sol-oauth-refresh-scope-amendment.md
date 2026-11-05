# Business Sol OAuth Resource Server — Refresh-Scope Compatibility Amendment

**Date:** 2026-09-01  
**Protected source at ruling:** `Mastermind@fc407e1638a26932c8615c98c7732d7f3202b3b1`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Parent plan:** `docs/superpowers/plans/2026-08-29-business-sol-oauth-resource-server.md`  
**Prior current-contract amendment:** `docs/superpowers/plans/2026-08-29-business-sol-oauth-resource-server-current-contract-amendment.md`

## Purpose

Close one current ChatGPT OAuth compatibility gap before BSC-A1 protection without widening the resource server into an authorization server, credential owner, session store, app registry, or organizational authority plane.

Current OpenAI guidance for custom MCP apps says OAuth/OIDC providers should issue refresh tokens to maintain connectivity. For OIDC providers, the standard request includes `offline_access`, the provider should advertise that capability in discovery metadata, and an app without it may lose access after the original authorization expires:

- `https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt`

A representative external IdP contract also requires `offline_access` plus API-level offline access to issue a refresh token:

- `https://auth0.com/docs/secure/tokens/refresh-tokens/get-refresh-tokens`
- `https://auth0.com/docs/get-started/apis/api-settings`

The original A1 scope parser preserved every granted token scope in `VerifiedPrincipal.scopes`, while the final MCP adapter correctly required that tuple to equal the exact app resource policy. An issuer that includes `offline_access` in the access-token scope claim could therefore be rejected even though that scope grants no Mastermind tool action and exists only to support refresh continuity.

This is a material platform-contract correction under the parent plan's current-contract re-verification gate. A1 must close it before release rather than pushing it into BSC-S1 or discovering it during Business enrollment.

## Frozen scope law

A1 distinguishes **resource-authorizing scopes** from one closed **non-authorizing OAuth session scope**.

```text
resource-authorizing scopes = exact policy.required_scopes
accepted non-authorizing session scopes = {offline_access}
```

The post-signature claims validator must:

1. Parse the bounded space-delimited `scope` claim under the existing syntax, duplicate, control-character, size, count, and deterministic-order rules.
2. Require every exact `policy.required_scopes` value.
3. Refuse any granted scope outside:

```text
set(policy.required_scopes) union {offline_access}
```

4. Return `VerifiedPrincipal.scopes == policy.required_scopes` exactly.
5. Consume `offline_access` at the claims boundary and never project it into MCP `AccessToken.scopes`, per-tool `securitySchemes`, tool descriptions, insufficient-scope challenges, audit authority, or backend authorization.
6. Refuse a token containing only `offline_access`.
7. Refuse `openid`, `profile`, `email`, another Mastermind app's scope, and every unknown extra scope unless a later separately reviewed platform generation changes this closed law.
8. Continue to refuse duplicate scope tokens, leading/trailing spaces, repeated spaces, invalid characters, and excessive scope count.
9. Continue to verify issuer, exact string resource/audience, time, subject, pseudonymous client identity, RS256 signature, JWK identity, and every other A1 policy condition on every request.

`offline_access` is not Mastermind authority. It cannot satisfy `mastermind.steward.read`, `mastermind.executive.read`, `mastermind.executive.intent.submit`, or any Dialogue scope. A valid token remains usable only for the exact resource and exact required scopes of its configured app policy.

## Credential and lifecycle boundary

A1 never receives, stores, rotates, logs, persists, or revokes a refresh token. ChatGPT and the selected authorization server own authorization codes, client authentication, access-token renewal, and refresh-token custody. The MCP resource server receives only the renewed bearer access token and verifies it from first principles on each request.

No token cache, refresh-token store, login session, nonce database, user directory, scheduler, retry loop, authorization endpoint, token endpoint, consent UI, DCR service, or predefined-client secret belongs in this amendment.

## BSC-U1 provider proof still required

This source hardening does not select Auth0 or any other IdP. U1 must prove the chosen provider's real wire contract before production enrollment, including:

- discovery metadata advertises `offline_access` or an exact equivalent accepted by current ChatGPT;
- authorization-code plus PKCE flow issues a refresh token;
- custom-API access tokens use RS256;
- `iss` is the exact configured canonical issuer;
- `aud` is the exact A1 resource string, not an unexpected array;
- access-token lifetime is at or below the configured A1 maximum;
- the access-token scope claim is either the exact required resource scopes or those scopes plus exact `offline_access`;
- `client_id` / `azp` behavior is compatible with A1's pseudonymous client binding;
- JWK `n` and `e` use the canonical positive unpadded Base64urlUInt representation already enforced by A1.

For an Auth0 custom API, do not request `openid` during the first compatibility canary: Auth0 documents that a custom API audience plus `openid` can produce a multi-valued `aud`, while the current A1 contract deliberately requires one exact string resource. This is a canary constraint, not a general claim about every provider.

## Required discriminating proof

The exact A1 candidate must prove:

```text
required resource scope only                         -> ACCEPT
required resource scope + offline_access             -> ACCEPT
same two scopes in reverse wire order                -> ACCEPT
accepted principal scopes                            -> exact policy.required_scopes
MCP AccessToken scopes                               -> exact policy.required_scopes
offline_access only                                  -> SCOPE_REFUSED
required scope + unknown extra                       -> SCOPE_REFUSED
required Steward scope + Executive scope             -> SCOPE_REFUSED
required scope + openid/profile/email                -> SCOPE_REFUSED
required scope + offline_access + openid             -> SCOPE_REFUSED
```

A mutation that returns every normalized token scope, treats `offline_access` as satisfying resource authorization, or accepts arbitrary extras must fail the focused test suite.

## Completion truth

This amendment keeps BSC-A1 at:

```text
BUILT_NOT_PROVEN / PRODUCTION_INERT
```

Even after protection, real authorization-server selection, client registration, refresh-token issuance, ChatGPT linking, remote endpoint reachability, app creation, workspace enablement, and sustained expiry/refresh behavior remain BSC-U1/C1 production proof. Green repository CI proves only the closed library contract.

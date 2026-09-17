# Business Sol S1/U1 — Public HTTPS Endpoint and IdP Canary Acceleration Amendment

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `business-sol-steward-s1-public-endpoint-idp-amendment-20260901-sol-001`  
**Canonical carrier:** `sol/business-sol-steward-s1-20260901`  
**Current protected source at ruling:** `Mastermind@fc407e1638a26932c8615c98c7732d7f3202b3b1`  
**Parent plan:** `docs/superpowers/plans/2026-09-01-business-sol-steward-s1.md`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Capability state:** `PLAN_ONLY / PRODUCTION_INERT`

## 1. Purpose and precedence

This amendment removes two avoidable sources of schedule latency before the first real ChatGPT Business Steward canary:

1. treating Secure MCP Tunnel as mandatory even when Mastermind can deliberately expose one hardened authenticated remote HTTPS MCP endpoint; and
2. postponing authorization-server wire compatibility until the final workspace enrollment ceremony.

On these two topics this amendment has narrow precedence over the parent S1 plan and prior BSC-U1 assumptions. It does not change the six-tool product, A1 resource-server authority, Control Room source ownership, read-only boundary, or production acceptance standard.

Current official OpenAI guidance states that ChatGPT connects to remote MCP servers. A local, on-premises, developer-machine, or otherwise private-network server should use Secure MCP Tunnel when the owner wants connectivity without exposing the server to the public internet. App creation asks for the MCP endpoint and required metadata, then verifies tools and completes OAuth when applicable.

Primary current sources:

- https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt-beta
- https://help.openai.com/en/articles/12584461

These platform facts are current-source dependencies and must be reverified before the real U1 mutation. Retrieved platform text grants no Mastermind authority.

## 2. Architecture ruling: public HTTPS first, Tunnel later

The first reversible BSC-U1 canary will use one public HTTPS MCP endpoint through the existing Mastermind VPS and hardened reverse-proxy ownership path. The S1 application process itself remains loopback-only.

```text
ChatGPT Business
  -> public TLS endpoint on existing approved hostname
  -> existing hardened reverse proxy
  -> loopback-only S1 Streamable HTTP service
  -> A1 OAuth bearer verification
  -> exact six read-only Steward tools
  -> existing Control Room/Steward source owners
```

Secure MCP Tunnel is removed from the **first-canary critical path**. It remains an optional separately reviewed privacy/hardening wave after the public-endpoint canary proves the complete product path. This is not a claim that a public endpoint is private or tunneled.

### 2.1 Exact endpoint surface

The initial endpoint family is one exact versioned path set on one approved hostname:

```text
POST/GET/DELETE  /mcp/steward/v1
GET              /.well-known/oauth-protected-resource/mcp/steward/v1
```

The exact public origin and hostname are deployment inputs owned by the existing host/reverse-proxy configuration. They must be frozen in the deployment receipt before effect. No wildcard hostname, alternate path, redirect alias, second public listener, debug route, generic proxy, arbitrary upstream, or all-host virtual server is allowed.

### 2.2 Loopback and reverse-proxy boundary

The S1 process must:

- bind only `127.0.0.1` or the equivalent exact loopback address;
- refuse `0.0.0.0`, external interfaces, Unix-socket fallback that bypasses the reviewed owner, and caller-selected bind addresses;
- trust forwarded scheme/host/client metadata only from the exact local reverse-proxy peer and reviewed header set;
- independently enforce the exact public `Host` and accepted HTTPS origin before authentication, MCP dispatch, source gathering, or response generation;
- fail closed on missing, duplicate, malformed, comma-joined, conflicting, control-character, non-canonical, or untrusted forwarding headers;
- allow no cross-origin browser capability merely because the MCP endpoint is public.

The reverse proxy must:

- terminate valid public TLS for the exact hostname;
- use only TLS 1.2+ and the existing certificate owner/renewal path;
- proxy only the exact versioned MCP and metadata paths to the loopback service;
- disable request buffering or streaming behavior only when required by the pinned Streamable HTTP contract and prove the chosen behavior;
- reject unsupported methods, paths, hosts, origins, request bodies, content types, transfer encodings, and header shapes before upstream dispatch;
- impose bounded request-body, header, concurrent-request, idle, connect, read, and total-response limits;
- preserve no bearer token or response body in access/error logs;
- expose no directory listing, server banner, stack trace, health detail, metrics detail, environment, filesystem coordinate, provider identity, or internal upstream address.

A separate operator-only readiness path may exist only on loopback or an already-governed internal monitoring surface. It is not an MCP tool and is never reachable through the public app endpoint.

### 2.3 Public endpoint threat controls

Required negative proof includes:

- wrong Host;
- missing, null-like, duplicate, mixed-case-conflicting, or overlong Host;
- unapproved Origin and `Origin: null`;
- DNS-rebinding-shaped host;
- direct upstream/loopback bypass attempt;
- HTTP-to-HTTPS downgrade or unexpected redirect;
- path normalization, encoded separator, dot-segment, alternate slash, suffix and query confusion;
- oversized/chunked/malformed request body;
- unsupported method/content type;
- missing, malformed, expired, wrong-resource, wrong-scope, wrong-subject and cross-app bearer token;
- forwarded-header spoofing from any non-proxy peer;
- log/response leakage of Authorization, cookies, subjects, client IDs, account email, local paths, internal hostnames, tokens, keys or exception text.

All pre-auth routing and boundary refusals must cause zero A1 verifier, tool, Control Room gatherer, provider, Executive, RuntimeBinding, Slack, Linear, GitHub or other backend action.

## 3. Deployment and rollback law

The public endpoint wave reuses existing VPS, reverse-proxy, release-artifact, service-manager, certificate and rollback owners. It creates no second deployer, daemon supervisor, certificate manager, host inventory, DNS owner, configuration database or service registry.

Ordered effect boundary:

1. produce an immutable reviewed S1 release artifact and manifest;
2. stage it inertly on the target host;
3. install/verify the loopback service while the public route remains disabled;
4. prove loopback metadata, auth negatives and six-tool census;
5. stage the exact reverse-proxy route and validate configuration without reload;
6. perform one atomic owner-governed proxy reload;
7. prove public TLS, routing, auth negatives and no-secret logs;
8. conduct the separately authorized Business app canary;
9. either retain the disabled-by-default reviewed generation or roll back exactly once to the prior proxy/service generation.

Ambiguous service install, proxy reload, DNS/certificate transition, OAuth request, or app-creation effect becomes `EFFECT_UNKNOWN`. No blind retry, alternate hostname, second service, second proxy route or Tunnel failover is allowed. Canonical owner readback must reconcile the same operation first.

## 4. Provider-neutral authorization-server compatibility gate

A1 is only the OAuth resource server. The authorization server/IdP remains an external credential and login owner. U1 must select an IdP by observed wire compatibility, not vendor reputation or documentation alone.

Before any tenant, API, application or client mutation, one read-only contract packet must bind:

- exact provider and deployment/region class;
- issuer canonicalization behavior;
- authorization-server metadata URL and exact issuer equality;
- authorization, token and JWKS endpoint behavior;
- PKCE S256 support;
- client registration mode accepted by current ChatGPT app setup;
- RS256 access-token support;
- exact custom-resource audience behavior;
- access-token lifetime controls;
- subject stability/pseudonymity;
- `client_id` and `azp` claim behavior;
- exact scope claim representation;
- refresh-token issuance and rotation behavior;
- JWKS key representation, rotation, cache headers and outage behavior;
- test-user, consent, logout, revocation and rollback boundaries;
- account/admin/2FA ceremony required from the Chairman.

No provider is selected until all load-bearing fields are either directly observed or explicitly deferred to a bounded disposable canary with fail-closed acceptance.

## 5. Auth0 as the first bounded candidate, not a committed dependency

Auth0 is the preferred first compatibility candidate because its documented custom API flow supports RS256 JWT access tokens, custom API audiences and refresh-token issuance when `offline_access` and API-level offline access are enabled. It is not yet accepted, installed or authoritative.

Current primary vendor references:

- https://auth0.com/docs/secure/tokens/refresh-tokens/get-refresh-tokens
- https://auth0.com/docs/get-started/apis/api-settings
- https://auth0.com/docs/secure/tokens/access-tokens/access-token-profiles
- https://auth0.com/docs/secure/tokens/json-web-tokens/json-web-key-sets

Vendor documentation is a hypothesis source. Real U1 acceptance requires direct canary receipts from the exact tenant/API/application generation.

### 5.1 Exact Auth0 preflight questions

The first candidate must prove all of the following:

1. The custom API signs access tokens with RS256.
2. `iss` exactly equals the configured canonical A1 issuer.
3. `aud` is one exact string equal to the Steward resource:

```text
https://<approved-mastermind-host>/mcp/steward/v1
```

4. The access-token lifetime is positive and at or below the A1 configured maximum.
5. The token contains every required resource scope.
6. The only permitted extra scope is exact `offline_access`; A1 consumes it as non-authorizing session capability and projects only the resource scopes.
7. `sub` is stable for the authorized test user and is converted only to the configured issuer-bound digest.
8. `client_id` and/or `azp` behavior matches A1's exact pseudonymous client-binding law.
9. The JWKS uses one acceptable RSA signing key with canonical positive unpadded Base64urlUInt `n` and `e` and no duplicate/ambiguous members.
10. Key rotation and old-key removal produce the expected A1 cache/refresh/refusal behavior.
11. The authorization-code + PKCE flow actually issues a refresh token and later obtains a new valid access token without exposing it to Mastermind logs or source.
12. Revocation or user/app deauthorization stops future access without rewriting prior immutable receipts.

### 5.2 First-canary scope restriction

Do not request `openid`, `profile` or `email` in the first custom-API canary. The first canary requires only:

```text
mastermind.steward.read offline_access
```

This avoids OIDC identity-profile scope expansion and prevents an unexpected multi-valued audience from entering a resource-server contract that deliberately requires one exact string audience. If the selected provider or current ChatGPT setup requires OIDC scopes, stop and issue a source-law decision request rather than widening A1 silently.

### 5.3 One Chairman ceremony

Source, deployment and read-only platform work should prepare every non-secret value in advance so the Chairman performs one bounded admin ceremony only:

1. create or select the exact IdP tenant;
2. enable required security/2FA controls;
3. create one custom Steward resource/API;
4. create one ChatGPT OAuth application/client using the current supported registration path;
5. apply exact callback/redirect URIs shown by the current ChatGPT flow;
6. enable only the exact test user and resource scopes;
7. securely enter any client credential directly into the owning IdP/ChatGPT surface;
8. complete one authorization and consent flow.

No secret is pasted into Slack, GitHub, Linear, Agent OS, a model prompt, terminal history, repository file, test fixture, screenshot, application log or public receipt.

## 6. Accelerated canary sequence

### Stage 0 — source and endpoint proof

- A1 and Secretary source protected.
- S1 source merged only after exact-head review/proof.
- immutable release artifact built and verified;
- loopback S1 service proves metadata, six tools, text fallback and all auth/source adverse states;
- public reverse-proxy route proves TLS, exact boundary refusals and secret-free logs;
- no Business app or IdP mutation yet.

### Stage 1 — disposable IdP wire canary

- one test tenant/resource/application generation;
- one test subject;
- one exact resource scope plus `offline_access`;
- one access token observed only by the authorized canary harness;
- A1 accepts the correct token and refuses wrong issuer/audience/scope/subject/client/algorithm/key/lifetime cases;
- token expiry followed by refresh yields a second valid access token;
- no refresh token enters Mastermind custody;
- cleanup/revocation is proven or the retained test generation is explicitly recorded.

### Stage 2 — ChatGPT Business draft app

Using the current workspace admin/developer surface:

1. provide the exact public MCP endpoint and OAuth mechanism;
2. complete authorization as the one approved test member;
3. run Verify tools;
4. require exactly six read-only tools with exact immutable schemas and no seventh/debug/write tool;
5. keep the app in draft/test state;
6. do not publish workspace-wide or migrate any Personal workspace.

A frozen ChatGPT tool snapshot is a separate receipt. Any source/tool change after approval requires recreation/republication under current platform behavior; it is not silently assumed to auto-update.

### Stage 3 — real read-only product canary

From one designated Business cockpit:

- ask one real current-state responsibility question;
- require a valid OAuth-authenticated call through the public endpoint;
- require one fresh Control Room snapshot generation;
- require source-attributed `FACTS`, or truthful `UNKNOWN`/`DEGRADED`/`REFUSED`;
- verify text fallback and structured result agree;
- verify two retained Personal Pro cockpits remain unchanged controls;
- verify zero Executive Job, RuntimeBinding, Wake, provider, Slack, Linear, GitHub or other write effect.

### Stage 4 — expiry/refresh continuity

Do not accept connectivity based only on the first access token. Hold or advance controlled time until the original access token is no longer valid, then prove ChatGPT obtains and uses a renewed access token without user reauthorization when the provider contract promises refresh continuity. A new valid tool read must still satisfy every A1 policy check.

Failure to refresh keeps the app `BUILT_NOT_PROVEN / AUTH_CONTINUITY_BLOCKED`; it does not trigger a weaker token lifetime, API-key fallback, cookie session, broad scope, disabled subject policy or manual token copy.

### Stage 5 — rollback/readback

At the canary stop boundary:

- disable or delete the draft app under a separately declared effect;
- revoke the test authorization/client/refresh grant as planned;
- disable the public proxy route if continued exposure is not explicitly accepted;
- stop or retain the loopback service according to the exact receipt;
- verify the endpoint is unreachable or remains in the explicitly accepted production-disabled state;
- preserve immutable sanitized evidence and exact remaining effects.

## 7. Acceptance ruler

The public-endpoint path is accepted for the first canary only when all are true:

```text
1 exact public HTTPS MCP hostname
1 exact versioned Steward endpoint
1 loopback-only S1 process
1 existing reverse-proxy/TLS/service owner chain
0 alternate public routes
0 redirects or host/origin ambiguity
0 bearer/credential/PII/internal-path log leakage
6 exact read-only tools
1 exact Steward resource scope
optional offline_access projected as 0 tool authority
1 test subject
1 successful initial access-token read
1 successful post-expiry refreshed-token read
0 Executive/RuntimeBinding/Wake/provider/company writes
0 unresolved EFFECT_UNKNOWN
```

A public endpoint, successful OAuth login, tool discovery, or green CI alone is not production acceptance. The capability remains `BUILT_NOT_PROVEN` until the full real read and refresh sequence passes through the actual ChatGPT Business path.

## 8. No-rebuild and non-goals

This amendment creates no:

- authorization server, token endpoint or login UI;
- refresh-token, access-token, cookie or user session store;
- second OAuth policy/JWT/JWKS owner;
- second MCP service, reverse proxy, deployer, certificate owner or host registry;
- Secure MCP Tunnel installation or tunnel credential;
- generic public API, super-MCP, shell, SQL, filesystem, browser or HTTP actuator;
- Executive, Agent OS, RuntimeBinding, Wake, Capacity, Slack, Linear, GitHub or provider write tool;
- workspace publication, member migration or Personal-to-Business merge;
- provider commitment before real wire compatibility;
- production arming, cutover or final Autonomy claim.

## 9. Immediate next action

After BSC-A1 protects:

1. assign the canonical S1 implementation carrier to one concrete available worker;
2. build the source vertical through an immutable DRAFT/HOLD PR;
3. in parallel, run the provider-neutral/Auth0 read-only contract preflight and prepare the one-chairman-ceremony packet;
4. after S1 source acceptance, deploy loopback + public HTTPS through the existing host owners;
5. conduct the disposable IdP wire canary;
6. create one Business draft app and prove initial plus post-expiry read continuity;
7. only then decide whether Secure MCP Tunnel materially improves the accepted deployment and deserves a separate migration wave.

No child inherits START from this amendment.

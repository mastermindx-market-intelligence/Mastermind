# Product Access MCP — M1 source contract and admission

Operation: product-access-browser-mcp-20261009-c1-001.
Parent: https://github.com/mastermindx-market-intelligence/Mastermind/issues/1303
Commission: October 9, 2026.
Status: BUILT_NOT_PROVEN, source-only. MISSION_COMPLETE=false.

## First consumer

An authorized Web CEO requests a canonical Macro or Terminal observation and
receives separately qualified transport, source, freshness and content, not a
claim that HTTP 200 or the word "ok" proves correct market intelligence.

This is the structured-data half of the selected hybrid Product + Browser
architecture. It does not create another product API, identity authority,
browser scheduler, artifact store, retry owner or signal producer.

## New code and existing owners

- integrations/product_access_mcp/contracts.py: static closed schemas and sources.
- integrations/product_access_mcp/observer.py: bounded, redirect-free public
  GETs with explicit representation validation and source-owned fields.
- integrations/product_access_mcp/runtime.py: injected existing
  common.bounded_sync_executor.BoundedSyncExecutor; no new executor or daemon.
- integrations/product_access_mcp/app.py: constructor-only MCP edge reusing
  existing Business JWT verifier, ResourcePolicy and audit sink; no default
  allow-all product grant or credential.
- tests/test_product_access_mcp.py: source, source-clock and negative tests.
- tests/test_product_access_mcp_runtime.py: actual bounded executor tests.
- tests/test_product_access_mcp_sdk.py: actual MCP SDK / ASGI and disposable
  signed JWT tests with simulated product grants and upstreams.

Host owners must supply the exact resource server policy, user-product grant,
audit, bounded executor, listener, credential custody, shutdown and rollout.

## Static read-only catalog

product_manifest accepts an exact empty object and lists supported public
source IDs without consulting their contents.

product_observe accepts only these product/view pairs:
- macro/status -> macro.public_status
- terminal/market_risk -> terminal.public_risk_projection

There is no model-selected URL, host, method, header, token, cookie, query,
principal or arbitrary network destination. Endpoints are exact canonical HTTPS
owner URLs; upstream browser/user credentials are not forwarded.

The mastermind.product_observation.v1 result preserves:
- status: OK, PARTIAL, STALE, MISSING, INVALID, UNAUTHORIZED, FORBIDDEN or
  DEPENDENCY_UNAVAILABLE (observation only, not a Job lifecycle state)
- pseudonymous MCP caller, requested source ID and public-upstream classification
- original HTTP status, body digest/byte count, ETag/cache age and representation
- observation timestamp; original source clocks, owner expiry and reasons
- bounded safe published data, explicit nulls and sanitized error code

Macro status is PARTIAL until component-specific producer/cadence rules qualify
it; producer ages remain visible. Terminal risk checks schema/verdict/score/
session, future clocks, owner stale flag and expiry. Unknown expiry is PARTIAL.
Zero-byte JSON with HTTP 200 is INVALID with the original raw empty digest,
never RISK_ON/zero/reconstructed stale data.

## Authentication and source isolation

- Existing Business MCP policy verifies exact issuer/audience/scope/signature,
  subject allowlist, client and expiry. Dedicated read scope:
  mastermind.product.read when the issuer supports custom scopes, or exactly
  openid when Supabase OAuth 2.1 is the issuer. Supabase does not presently
  offer custom OAuth scopes. Neither scope independently grants product-user
  access: the separate current product-identity/entitlement check is mandatory.
  Resource audience, consent, client and session identity remain release gates.
  **Provider incompatibility:** Supabase OAuth access-token documentation states
  the default aud claim is the literal `authenticated`, whereas this existing
  Business MCP resource policy requires an exact HTTPS audience. An ordinary
  Supabase access token therefore correctly receives HTTP 401 in the MCP
  boundary, even if its scope is `openid`. Do not relax resource validation,
  treat `authenticated` as the Product audience, or assume an OAuth hook is
  installed. A separately qualified issuer/resource policy or existing
  identity-owner-approved audience/consent integration must close this gate.
  Source: https://supabase.com/docs/guides/auth/oauth-server/token-security
- Required injected product-user grant is checked before I/O and rechecked
  after SDK credential verification, immediately before the buffered result.
  A revoked grant never becomes a public-user fallback.
- Original source identity is bound to the requested product/view across
  await/return. Cross-source data substitution is refused.
- Tool schemas reject extra URL, root, credential, tenant or mutation keys.
- Body cap 64 KiB; result cap 16 KiB; closed error vocabulary. No source
  secrets or third-party exception detail enters tool output.
- Read-only. No Executive Job, browser action, user mutation, refresh,
  live trading or production deploy is issued by this source.

## Verification

From the admitted Mastermind worktree, with a qualified MCP SDK:

  python -m pytest -q tests/test_product_access_mcp.py
  python -m pytest -q tests/test_product_access_mcp_runtime.py
  python -m pytest -q tests/test_product_access_mcp_sdk.py
  python -m compileall -q integrations/product_access_mcp
  git diff --check

Native SDK tests use ephemeral RSA test credentials and synthetic product grants.
They do NOT prove real OAuth consent, product identity/entitlements, an
installed listener, a real Web CEO plugin invocation or screenshots.

An additional opt-in test (`tests/test_product_access_mcp_public_canary.py`)
would compose signed fixture MCP/ASGI requests through the existing bounded
executor to the two exact public product endpoints; it is OFF by default and
is **NOT_RUN**. The original live opt-in execution was refused before dispatch
by the platform on October 10, 2026. No retry/alternate-carrier execution was
attempted. Offline suite executes only the skip declaration. This held canary
is an explicit network-integration acceptance obligation, not proof of M1.

## Remain held

Terminal #894: observed October 9 risk JSON publication returned HTTP200
with zero bytes; installed writer and origin/cache cause unproven. Do not
overwrite generated runtime data or silently patch the deployed bundle.

Before accepting M1: owner-qualified product-user link, admitted listener and
tunnel, selected MCP resource, real Web CEO read, live invalid/revoked login
and grant tests, authenticated source/provenance comparison.

M2–M5: existing Browser Fabric/profile/screenshot recovery, real protected
Macro/Terminal UI, exact PR-preview fix and screenshot comparison, one
independently admitted reversible app action, hosted CI, independent review,
approved release, multi-account installation/rollback and real production
end-to-end acceptance.

PR #1259's original attached-tab upload refusal remains fenced. This Product
source branch is disjoint; it does not take custody or grant a retry. Preserve
#1071 recovery and #838 artifact-return ownership.

Implementation source != merged != installed != selected != live/accepted.


## M1 follow-on: host composition and revocation-safe product authorization

New module: integrations/product_access_mcp/deployment.py.

create_product_deployment(ProductDeploymentServices(...)) now constructs the
read-only authenticated MCP/ASGI server with a **mandatory incumbent owner**
permission resolver, existing OAuth/JWKS authenticator, existing audit sink,
caller clock, bounded read port and exact Host/Origin policies. It allocates
**no socket, daemon, login, secret, browser process, custom user database or
worker lifecycle**. Running or installing the returned ASGI object is an
independent host-authorized operation.

The injected resolver returns a ProductReadBinding, an immutable projection of
a separately verified **existing** grant, containing the same verified OAuth
caller, product/view/source ID, owner reference, grant generation and deadline.
The edge snapshots this specific binding before awaiting the read, then
synchronously re-resolves and compares it after OAuth revalidation and after
the read, with no additional await before returning buffered output. If a
grant was revoked, replaced, retargeted or expired, the request returns
PRODUCT_GRANT_CHANGED instead of the previously read product data.
Manifest calls also require an explicit owner grant for catalog/manifest;
they do not silently bypass product authorization.

This contract is NOT a new grant issuer. The installing identity/product owner
must provide the actual product-user mapping and current grant resolver.
A callback that simply returns an unconditional ProductReadBinding is **not**
acceptable production evidence: proper real-user entitlement, client binding,
session/revocation and denial tests are still required. The factory validates
structural compatibility, not business authorization authority.

The composition rejects a different authenticator resource policy and
wildcard Host/Origin configuration. Tests cover same-grant acceptance,
cross-product/source mismatches, changed product grant generation, owner
revocation during an awaited read, token and grant expiry, malformed binding,
and actual MCP/ASGI signed synthetic token flows with two distinct users.

The real installation owner must explicitly own socket selection, runtime
resource allocation, TLS/tunnel routing, ASGI lifespan and graceful shutdown.
Do not mount this service at an unapproved public port, accept a broad
audience such as Supabase's generic authenticated claim, mint new tokens,
register a Web CEO plugin or grant access to private product data from this
source-only package. Source tests are not installed-service or product-account
acceptance. Existing Browser Fabric and Workbench process owners remain
unchanged.

A future consumer may import:

    from integrations.product_access_mcp.deployment import (
        ProductDeploymentServices, ProductReadBinding,
        create_product_deployment,
    )

The host must supply every constructor field, including its existing
read_port and resolve_binding. Missing values fail closed; there is no
unconditional product permission adapter or default credentials.

Review before release: tests/test_product_access_mcp_deployment.py and the
deployment/late-revocation test in tests/test_product_access_mcp_sdk.py.

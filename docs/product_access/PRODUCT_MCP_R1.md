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
- macro/overlay -> macro.public_live_overlay (published intraday context only)
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


## M1 follow-on: mountable ASGI boundary and process readiness

New module: integrations/product_access_mcp/mount.py.

The existing admitted service owner can compose
create_product_asgi_app(server=..., owner_ready=...) with the separately
constructed authenticated Product server. It exposes GET /healthz (process
liveness only), GET /readyz (explicit owner-supplied current readiness)
and the existing FastMCP HTTP routes. The SDK session manager runs within the
mount's ASGI lifespan and is not represented as a new Executive Job, worker,
account, socket or browser resource. This module DOES NOT start a listener.

The owner readiness callback must be a fast, synchronous check of the actual
incumbent listener/identity/grant/capacity installation; no default True.
If it returns anything other than literal True or raises, readyz returns 503.
A failing readiness check also gates all MCP HTTP requests at the mount
boundary with a generic 503. A request that entered while ready is still
subject to the late existing OAuth and product-grant authorization fence.
Neither a healthy liveness route nor an isolated ASGI suite is proof that the
real Web CEO plugin is connected or the user can access protected data.

Red-first tests established that an SDK server can be running while its
host is unready; without an admission gate, the SDK still processed the
request. The mount now refuses these calls until the existing owner declares
readiness. Positive tests use disposable signed JWTs and synthetic upstream
data, with revocation and two-user isolation intact.

Tests: tests/test_product_access_mcp_mount.py, and the composed
deployment/SDK test in tests/test_product_access_mcp_sdk.py.

Production gate remains held: no listener/TLS/OAuth consent/client/product
authorization/grants/selected ChatGPT plugin or real Chrome/Browser Fabric
profile has been installed by adding this source. Do not use a dummy
owner_ready=lambda: True in real deployment, expose health endpoints through
an unreviewed public ingress, or call a source constructor PROVEN_LIVE.


## M1 public Macro live overlay: source-owned intraday context

Macro read-only source pinned at
mastermindx-market-intelligence/macro@f5321bb68ca43310d72a58f8c4f583e3abbee1ca.
Its app/main.py exposes a GET /api/overlay route that directly reads the
existing live/overlay.json owner artifact without invoking user authorization.
The current producer in scripts/build_live_overlay.py emits
schema live.overlay.v2, a producer build clock, delayed_min, per-region session
status, market context and contributor/quote counts. The fast intraday overlay
must NOT be confused with the separate nightly regime/GTAA decision spine.

The static Product catalog now includes macro/overlay under the existing
read-only product_observe tool. This is a *public* owner source, not an
authenticated private-product or user-entitlement endpoint. No new data
producer, quote signing, market state classifier, GTAA score, trading action
or vendor entitlement authority is introduced.

The adapter allocates a distinct bounded 512 KiB upstream representation cap
for this source (existing Macro status and Terminal risk remain at 64 KiB),
while retaining the unchanged 16 KiB entire MCP result cap. It forwards
ONLY selected published source observations: schema, built timestamp, producer
count fields, declared quote delay/realtime flag (as *unverified source claim*),
and minimal stale/calendar/session context for selected SPY/QQQ/VIX and
US/China/Hong Kong/Canada venue records.

It does NOT return any raw licensed quote price, raw options-flow row,
contract/strike/ticker tape, vendor key/diagnostic, stock allocation, raw
per-symbol snapshot, secret or bulk source JSON. A large source response
retains its original body digest and byte count, but only the safe bounded
summary becomes a Web CEO tool result.

The overlay is PARTIAL by design: producer built time and per-session
freshness are not proof of current live risk-on/off regime or true real-time
data. Invalid/future built clocks, inconsistent counts, unknown schema and
unqualified delay produce explicit invalid/partial states. A feed reporting
real-time alongside a nonzero delay is explicitly contradicted, never
silently promoted to true real-time.

Local tests use synthetic owner-compatible live.overlay.v2 fixtures only:
no previously denied public-network canary was run or retried, and no live
production overlay/market claim is made here. The installed producer, current
source runtime and actual availability must be independently verified by its
existing product/release owner after lawful source and identity admission.


## OAuth resource discovery: genuine pinned-SDK wire contract

With the repository-maintained MCP SDK pin 1.28.1 (and PyJWT
2.13.0), the authenticated Product edge advertises the official
RFC 9728 protected-resource metadata at:

    /.well-known/oauth-protected-resource/mcp

for the resource URI configured in the external ResourcePolicy. The SDK
advertises the host owner-selected authorization server and exact policy
scope (and normalizes a bare HTTPS issuer origin with a terminal slash).
A missing bearer token receives HTTP 401 and WWW-Authenticate with the
resource_metadata location. The same discovery contract works when
the SDK is mounted behind create_product_asgi_app, after an explicitly
qualified owner readiness predicate allows the request.

Native SDK/ASGI tests exercise these HTTP responses without a real
login, listener, user-product entitlement, tunnel or external network
call. Resource discovery does not establish the presence of an OAuth
authorization UI, registered ChatGPT client, user consent, matching JWT
audience or installed resource; it is merely the production-relevant
MCP transport/discovery contract needed before those gates can close.

Read-only reference: tests/test_product_access_mcp_sdk.py method
test_oauth_resource_metadata_and_missing_token_challenge and the
mounted deployment positive/revocation test.


## Output assurance: a healthy market verdict must be actually qualified

Adversarial RED fixtures demonstrated the prior response validator could
accept status OK with an empty or incomplete risk payload, or allow a stale
result to be relabeled OK, if a future borrowed read port returned a
mismatched response. The observer itself selected fields correctly, but
the final OAuth/MCP transport cannot assume a borrowed port is infallible.

The response envelope now rejects:
- any Macro status projection presented as fully healthy/qualified; its
  individual producer cadences remain independent, so it is PARTIAL;
- the Macro fast overlay promoted to a complete regime/market OK;
- Terminal risk OK without explicit schema market_risk/v1, supported verdict,
  valid session, stale=False, display_only=True, nonempty source evidence and
  a finite score between 0 and 100;
- changed freshness claiming qualified=True while risk is stale/partial;
- owner risk responses lacking a score being rendered fully qualified.
  Missing score remains available as an explicit PARTIAL with
  score_unavailable, not a synthetic numeric zero or recovered last score.

Tests establish the original invalid response is now refused both by the
pure contract and by a native signed-test-JWT MCP call; output details are
withheld from the authenticated caller on contract failure. The tests use
owned synthetic source data and do not imply positive production access.


## Risk projection producer-semantic hardening — October 10 continuation

Read-only current Terminal source inspected at:
mastermindx-market-intelligence/mastermind-terminal@1148477475dbff4ab49397e2ecfc10f7e98ab70a
in ingest/pull_macro_risk.py (build_market_risk). It emits
market_risk/v1 with both is_display_only=true and an independently qualified
freshness object (qualified/reasons), as well as its existing stale flag,
source session, built timestamp and optional quote expiry.

The first Product MCP adapter projected display_only=true without verifying
the owner's is_display_only field and could label a source with
freshness.qualified=false as OK if the other clocks were plausible. This
would give a Web CEO overstated trust in incomplete risk observations.
A first RED run of source-faithful tests proved the misclassification.

The Product reader now requires literal is_display_only=true before returning
any accepted numeric/word risk projection. A missing or false source authority
flag returns INVALID with no market verdict. The reader also cross-checks
the original producer's freshness.qualified and reasons against the observed
source clocks/stale flag. Missing, inconsistent or explicitly unqualified
freshness is never promoted to OK. Malformed source built/event/expiry clocks
produce a bounded unqualified reason; genuine future/expired clocks remain
STALE as previously accepted. Source-supplied reason values must be single
safe identifiers before they can enter the Web CEO result; free-form strings
or attempted instruction/credential text are replaced by a closed marker
rather than being echoed.

This does NOT re-evaluate market regime, rewrite producer freshness, infer
an absent exchange calendar, or claim independent source admission. It
preserves the original owner's status and reduces the reader's trust level
when necessary. The producer, release and market-risk classification owner
remain Terminal. Synthetic fixtures are matched to the actual current
producer's emitted schema; the platform-denied live signed-network MCP
canary remains NOT_RUN. The source-only tests do not prove installed
producer/result accuracy or live browser state.

Relevant negative/positive cases:
- tests/test_product_access_mcp.py owner display-only/freshness cases
- tests/test_product_access_mcp_runtime.py bounded read port current shape
- tests/test_product_access_mcp_sdk.py signed synthetic MCP/ASGI current shape

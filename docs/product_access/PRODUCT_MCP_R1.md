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

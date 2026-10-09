# Product Access and Browser MCP — qualification and production gates

This record is not production acceptance. MISSION_COMPLETE remains false. The source candidate is an inert, public-observation resource, not private product login or browser access.

## Source qualification contract

The code uses the repository's pinned MCP 1.28.1 and PyJWT 2.13.0. Reproduce the isolated suite with `python -m pytest tests/product_access_mcp -o addopts='' -q`. Existing auth/Workbench qualification: `tests/test_business_mcp_auth_mcp_adapter.py` and `tests/workbench_read_mcp/test_app.py`. Test counts and immutable candidate IDs belong in CHECKPOINT.md; do not add historical checkpoint counts together.

The tests exercise actual MCP initialize/list/call and protected-resource metadata over ASGI, cryptographically signed ephemeral RSA JWTs, existing Business token verification/audit, the real ProductReader, PublicTransport and a real loopback HTTP server. A test bridge maps fixed URLs to loopback without resolving production DNS. That proves local component integration, not public TLS, a deployed listener or a real account. Specific timeout, malformed-stream and constructor-policy tests use deterministic synthetic transports. Their coverage is not represented as real-network proof.

Negative cases include wrong issuer/audience/scope/subject/signature/expiry, policy revocation before and during reads, expiry during a read, auth-audit failure, forbidden user/header/URL/action arguments, host/origin refusal, nested unexpected output, private failure text, duplicate/nonfinite JSON, source-owner/view/schema drift, mismatched symbols/counts, missing/future timestamps, missing or partial quotes, source revisions and no false drift from matching abbreviations. Transport tests cover no credential or cookie forwarding, redirects without retry, disconnect, timeout, content type, size, TLS-environment isolation and refusing compression before decoding.

Catalog schema is separately versioned and pinned by digest. It must remain compact and equal to the actual advertised tools. A schema change requires an intentional snapshot update and profile/version assessment, not silent mutation of an installed legacy profile.

## Existing-owner deployment composition

No config file, auth tenant, token database, service listener, tunnel, plugin or browser installation is created by this source. An authorized deployment owner supplies:

- An existing Business `ResourcePolicy` with **only** `product.observe`, a separately admitted product resource audience, current subject allowlist, exact issuer, JWKS and metadata URL. The SDK's normalized URL representation must equal the admitted literal issuer and audience; the factory refuses mismatches.
- The existing `JwtAuthenticator`/JWKS mechanism and `AuthAuditSink`, using the same policy and trusted clock. No fixture keys, fixture transport, dummy authority or .env copied from a different owner.
- Exact allowed ingress hosts/origins and existing resource/listener lifecycle. The default PublicTransport, never a test bridge. Existing ingress must cap HTTP bodies and slow uploads before SDK JSON parsing; decoded tool arguments are independently limited to 4 KiB and returned JSON to 64 KiB. Confirm these raw-ingress controls before production admission.
- Existing CI/review/merge/release and rollback approval; a pushed branch or draft PR is not installable production authority.

The inert composition is `ProductReader(transport=PublicTransport(), now=trusted_utc_clock)` passed to `create_product_server(authenticator=..., policy=..., now=trusted_epoch_clock, audit_sink=..., reader=..., allowed_hosts=..., allowed_origins=...)`. This returns the existing SDK server for the deployment owner's explicitly admitted ASGI lifecycle. No automatic startup or generic environment-selected endpoint exists.

The public profile never needs a product-user bearer or website cookie. Private scopes are not included. If any target endpoint becomes personalized, disable its profile path and re-adjudicate through application authorization rather than forwarding credentials.

## Real-account acceptance — each row needs independent evidence

| Gate | Evidence required | Present state |
|---|---|---|
| Source + dependencies | Exact accepted commit, immutable catalog digest, pinned dependency environment, required CI and independent review | Source candidate; review/release pending |
| Listener | Existing owner's process identity and exact loaded code, bounded health/readiness | NOT PROVEN |
| HTTPS/tunnel | Exact resource URL, no redirect, valid TLS, host/origin enforcement, resource routing to that listener | NOT PROVEN |
| OAuth resource | Discovery metadata equals policy, real consent/account binding, exact audience/scope; invalid/expired/revoked tokens denied | Local fixtures only |
| Plugin | Exact registered plugin and catalog; registration separate from installation | NOT CREATED by this operation |
| Account selection | Actual selected account/profile invokes each exact tool; scope and catalog match | NOT PROVEN |
| Public product reads | Real health/status and market pulse receipts, truthful errors/freshness/source ownership; compare independently with same product owner | BLOCKED production probe; no observation obtained |
| Private product reads | Current Macro/Terminal application identity and entitlements, cross-user isolation, revoked access, no MCP-token passthrough | NOT BUILT in this profile |
| Browser resource | Existing managed isolated/persistent profile, exact RuntimeBinding/process identity, eligible host, exclusive mutation, cleanup/revocation and lost-action reconciliation | Existing Browser owner; not proven here |
| Visual inspection | Protected Macro and Terminal pages, desktop/tablet/mobile, genuine screenshots/snapshots/diagnostics returned with complete verified bytes | NOT PROVEN |
| Defect/fix/preview | Real product defect, exact deployed revision, owning-repo PR, exact preview, independent before/after visual and behavioral assertions | NOT PROVEN |
| Application action | One specifically authorized existing prepare/execute/reconcile path, exactly-once business result, audit and reversal where supported | NOT ADVERTISED; write capabilities off |
| Production release | All required checks/review/approvals, exact loaded release, safe rollback and production canary | HELD |
| Multi-account adoption | Separate install/link/select/call evidence for each claimed account | NOT PROVEN |

Public target labels in fixture receipts are endpoint definitions, not proof that production was contacted. Source `status: ok` is not proof every feed is healthy; source-reported quote freshness is not restamped current by the adapter. Unknown deployed revisions block exact-preview acceptance.

## Browser consumer contract and adversarial acceptance

The existing Browser/Capacity/Workbench/Operator Harness owners must provide approved navigation, snapshots, screenshots and bounded logs. Preserve the distinction between isolated preview sessions and persistent human-authenticated production profiles. Avoid screenshotting login credentials and secret-bearing fields; sanitized console/network diagnostics must not return cookies, Authorization headers, storage or raw debugging sockets.

Required negative journey: unapproved origin/redirect; URL change invalidating element handles; concurrent mutation of a shared profile; form submission without current authority; revoked/expired profile grant; browser/host/network death after dispatch; lost response or restart with original action identity; screenshot digest/length/media-type/revision mismatch; stale screenshot substituted for current preview. Reconcile the original action through its existing owner; never replay an ambiguous mutation. A resource appearing in inventory does not prove Ubuntu/browser/profile eligibility.

#1259's denied source upload and administrator-controlled extension installation remain on their original owners. This program does not clear those restrictions or take over that branch. #838 is the candidate artifact-return owner; require real conversation-delivered content and digest confirmation before claiming screenshot support. Do not create another artifact service, browser/session database, cookie service or scheduler.

## Rollback and incident behavior

Before rollout, the existing release owner records the previous accepted resource/profile version and its actual listener binding. On a security or entitlement failure, withdraw the product scope/profile using that same owner, stop new reads, discard in-flight results that fail final auth checks, and roll back the adapter through the normal release mechanism. Do not touch unrelated Executive or Browser profiles, clear another owner's session, replace credentials, or delete evidence.

The public adapter has no material application mutations to reverse. Source rollback is a Git-governed release operation; profile withdrawal is an identity/resource-owner action. Neither is performed by this candidate. For future application mutations, capability admission must supply the existing operation identity, reconciliation, audit and supported reversal before the tool is advertised.

## Explicit holds and next actions

The current-session production HTTPS probe was refused before dispatch by the tool safety layer, and has not been retried by code, another host, another tool or another identity. Its results remain unknown. Only the appropriate permission owner can resolve that gate. Separately, the existing Browser candidate still requires its original source-publication and human installation approvals.

Finish independent source qualification and publish the exact candidate. Obtain independent review and existing release-owner admission. Then, only when the original production probe gate is explicitly resolved, execute the real-account rows above on the selected installed resource. Do not request passwords, raw cookies or private keys in chat. Human consent/login and protected release approvals remain human actions. No automatic watcher, scheduler, worker launch or background continuation is implied by this checklist.

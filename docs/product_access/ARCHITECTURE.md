# Product Access and Browser MCP Fabric — architecture

2026-10-09. Candidate decision under the current Chairman commission; not protected law. MISSION_COMPLETE: false.

## Outcome and grounding

An authorized Web CEO must read meaningful live Macro and Terminal intelligence, inspect authenticated pages, receive genuine screenshots, diagnose an actual defect, relate its source fix to an exact preview revision, and verify an approved release. Public diagnostics are the first independent slice, not a substitute for the complete outcome.

Protected procedure: Mastermind `326c8469a21d7f50fc9ecb1848196bf1c6e66685`, skillpack `mastermind.sol_skillpack.v1` / 1.0.1 / bootstrap 1. Source census: Macro `3d90aad6d83152dfeeaf8345bc995826ac9d3139`; Terminal `4d6a9ac81d01ac9f14c22fd3180f5d00f0239000`. The installed Executive read reported the protected Mastermind SHA and Macro grounding `88804ed7079700c598bb8e04aa64307d1335402d`; organizational grounding is not product freshness.

## Selected architecture

Hybrid: a narrow versioned Product MCP resource projects existing application observations; the existing separately governed Browser MCP handles browser resources and actions. Reuse Business MCP authentication, metadata and JWT validation. The product adapter owns no credential store, session database, scheduler, retry queue, identity mapping, effect ledger, browser registry or evidence service. Its factory is inert; the existing deployment owner supplies lifecycle and admitted resource policy.

First implementation: an authenticated **public-observation** profile with exactly `product_diagnostics` and `product_market_pulse`, both read-only. It sends no Authorization header or cookies upstream. It consumes explicitly public Macro health/status and the Intelligence Hub regular-session quote projection owned by Terminal market data. It does not equate the MCP principal with a signed-in product user. Private Terminal state, private Macro intelligence, refresh, application mutation, portfolio operations and trades are not advertised.

Private access is an identity-dependent next slice, not a hidden fallback. Prefer the existing Supabase identity owner as product OAuth issuer where an OAuth server and product-specific audience can be explicitly admitted. Call same-resource domain methods under verified application authorization, or use independently audience-correct, owner-issued upstream authorization. Never forward the incoming Executive/MCP token to a different API. Do not create an Auth0-to-Supabase credential database. If the existing identity owner cannot support this contract, return that specific design decision before arming private access.

## Required alternatives

| Alternative | Security / ownership | Complexity / latency / tool efficiency | Maintenance / OAuth / registration / deployment | Decision |
|---|---|---|---|---|
| Dedicated Product MCP on VPS | Resource isolation is useful only with existing auth and domain owners | Fast structured reads; one extra service and VPS failure domain | New listener/plugin/consent; lifecycle must stay existing deployment owner | Possible transport placement, not a new OS |
| Product static profiles in Executive/Workbench | Reuse auth infrastructure, but do not couple product and Executive privileges | Few calls and low extra hop; frozen legacy catalogs cannot be changed silently | Separately versioned profile and independent account selection proof | Reuse machinery, not legacy contracts |
| Existing separate Browser Fabric MCP | Correct browser, process, effect and resource boundaries | Necessary for visual proof; expensive for bulk intelligence | Reuse merged #1071 and existing Browser/Capacity/Workbench ownership | Required browser lane |
| Application APIs plus thin MCP adapter | Data authority stays with applications; caller and upstream identities separated | Smallest structured-read implementation; fixed efficient calls | Existing auth/deployment infrastructure, new resource profile; fail on source drift | Selected structured-data lane |
| Browser-first alone | App login helps, but UI prompt injection and interaction effects remain | Slow and brittle for many freshness/provenance reads | Browser installation/login gates block even nonvisual audits | Rejected as sole architecture |
| Hybrid thin Product + existing Browser | Separate read/interaction capabilities and shared canonical owners | Structured checks first; browser where visual evidence matters | Independently qualify both catalogs; shared tunnel still shares outages | Selected complete direction |

Long-term extensibility is by reviewed domain tools, not generic HTTP, filesystem, SQL, SSH, process or CDP access. Ubuntu is a placement preference, not an eligibility receipt. This slice places no Chrome process on the VPS.

## First consumer and contracts

Consumer: a Web CEO checks backend process/checkout drift, published-feed observations and Terminal-owned regular-session quote freshness without hand-copied JSON. Macro source explicitly declares `/api/health` public; the market-pulse source justifies deliberate public regular-quote redistribution. `/api/status` is the existing operational projection. Its top-level `status: ok` must never override degraded checks.

Fixed server-side endpoint table: HTTPS `www.mastermind-x.com` at `/api/health`, `/api/status`, `/api/intelligence-hub/market-pulse`. Model input cannot select URL, host, path, headers, identity, tenant, environment or arbitrary query. Symbols are unique, validated and limited to 12. Every redirect is refused. Transport disables ambient proxy/credential use, sends no cookies, bounds bytes/deadlines, and never retries or substitutes static GitHub artifacts.

Response schema: `mastermind.product_observation.v1`. Preserve source owner, endpoint identifier, access class `public`, environment `production`, observation time, raw-body SHA-256, HTTP status, explicit availability and provenance limitations. Process build, checkout revision, publication timestamp, quote observation and transport time are distinct. Short Git IDs remain short; do not invent full deployment identities. Missing timestamps mean unknown, never current. Finite zero is valid; booleans are not numbers. Partial/stale states survive. Owner revision markers are not asserted correction events.

Upstream content is untrusted data. Return only reviewed fields, not arbitrary backend exceptions, private paths, bearer tokens or unknown fields. Refuse quote `ext*` leakage and incompatible projection schema/owner/view instead of silently sanitizing unauthorized extended-session content into an accepted regular quote. No adapter cache or history rewrites freshness. No model-generated trading decisions are produced.

## Authentication and entitlement

The inert factory requires existing `ResourcePolicy`, `JwtAuthenticator`, `MastermindTokenVerifier`, clock, audit sink and explicit host/origin policy. Dedicated scope: `product.observe`. Missing/wrong issuer, audience, subject, scope, expired tokens and policy drift refuse access. Revalidate the exact original MCP credential after awaited reads; discard buffered output on authorization change. Raw tokens never reach the reader. Existing authorization owners retain policy/revocation publication; no new registry is added.

Public upstream observations may be identical across authorized MCP users; they contain no private tenant state. That does not prove private tenant isolation. Private product reads must separately test actual product identity, current entitlements, revocation and cross-user denials. Signature validity alone is not a subscription or application authorization decision.

## Existing browser and artifact work

#1071 is merged, source head `688c52ac0307fa2721bbaf01a42bb672d8e4b023`. #940/#993/#1051/#1057 remain draft/stacked; do not repeat their merged integration. #1217 Studio/Paper is an adjacent incumbent. #1259 Browser plan remains draft at `e790afb35f055c9ff0a95e3aa214a41e7a1974eb`; its attached-tab source is not published. #838 artifact return is draft at `75434f2dee94c298d6eb094f65decc04e109053c`; #1212 Context MCP is draft at `d9ca947bb460ff89499650c748f2f78f3a2d087e`.

Preserve #1259's pre-dispatch denied `native/framing.py` upload and original permission owner. Preserve Chrome policy refusing unpacked extensions. Do not re-upload through another carrier, change policy, use a different browser to evade it, rebuild the denied implementation, or seize its workspace. Synthetic tests do not resolve those holds.

Screenshots, snapshots and logs must return through the existing artifact owner when accepted, binding artifact/action identity, digest, media type, complete byte count, capture time, environment, viewport and deployment revision. A local path or thumbnail is not proof of a complete returned screenshot. BrowserResource/Capacity/RuntimeBinding/Workbench/Operator Harness retain grants, generation, exclusive mutation, stale references, cleanup and ambiguous-action reconciliation.

Code/QA chain: observed defect → exact deployed source → authorized owning-repo PR → exact preview → authenticated before/after visual and behavioral assertions → required CI/review → approved release → production verification. Layouts/watchlists/preferences remain application-managed state; source/configuration stays Git-governed. Published intelligence keeps its existing producer, correction and publication semantics.

## Dependency graph and rollout

1. Public profile source plus real SDK/JWT/ASGI/transport integration tests → reviewable candidate.
2. Existing release owner and exact dependencies → listener/resource/tunnel/plugin registration → actual account selection → authorized production public-read canary. Verify each independently.
3. Existing product identity owner, explicit consent and product resource audience → native private read → actual invalid/revoked/cross-user/entitlement tests for Macro and Terminal.
4. Browser source permission/install/admission and eligible host/profile → protected Macro/Terminal page inspection → genuine returned screenshots/diagnostics.
5. Exact source/preview identity plus artifact return → one actual defect fixed and verified through the new access and approved release.
6. Only after read/browser credibility: one authorized application mutation using existing prepare/execute/reconcile, double-submit defense, ambiguous-effect recovery, revocation, audit and owner business-result proof. Trading and unrestricted admin remain off.

No merge automatically crosses these arrows. A production probe gate does not block isolated new-source tests; offline tests do not establish production acceptance.

## Threat assessment and falsifiers

Main risks: confusing identities, reflecting credentials, stale-as-current data, redirect exfiltration, cross-user response reuse, forged deployment claims, shared-profile races, corrupt screenshots, and false-green rollout. Fixed paths, no upstream credentials, reviewed projections, timestamp validation, digests and final auth rechecks address the initial read slice. Private identity and browser risks remain unproven until their real integration tests pass.

Revise the design if the selected public endpoint ceases to permit the intended redistribution, returns personalized data, omits material source freshness/error semantics, or needs a new credential authority. Revise browser evidence integration if the existing artifact owner cannot safely deliver complete content. Missing deployment identity blocks exact-preview acceptance; never fill it with GitHub HEAD.

## Current holds and scope

Executive read succeeded, version 1.5.0, readonly, no degraded inputs. Workbench exposed only canary files/recipes, not product or browser capabilities. No worker was dispatched. Direct first-slice work is retained for principal integration/security decisions and because the exposed Executive ingress is readonly; this is not a claim that the whole Fabric is down.

A Studio HTTPS probe covering production health/status/public quotes/private Terminal denial/OAuth metadata was blocked by the tool safety layer before execution. No PID or HTTP results were produced. The exact probe is not retried or rerouted. Its production/OAuth observations remain UNKNOWN. Independent source edits and offline tests remain permitted. Existing browser publication and installation denials are separate.

Private access, login/linking, selected plugin, live screenshots, Ubuntu eligibility, preview defect proof, release and multi-account adoption remain incomplete. This commission is PARTIAL until all ten declared acceptance requirements are independently proved.

## Primary external references

- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- https://developers.openai.com/plugins/build/auth
- https://supabase.com/docs/guides/auth/oauth-server
- https://supabase.com/docs/guides/auth/oauth-server/token-security
- https://playwright.dev/docs/auth

These establish upstream mechanisms, not their enrollment or production authorization in Mastermind.

# Experiential Labs shared-gateway integration — task tree

Owner / source: `mastermindx-market-intelligence/Mastermind`, PR #1918, `sol/explabs-gateway-smoke-20261101`
Related source lanes: #1849 (one org-shared Fabric gateway), #1934 (System One ingress stacked on #1849), #1851 (native Jev), #1920 (Attempt-owned Fabric SDK consumer).
Protected procedure pin: `ae3fc6fce8f704b32b01664f1b0d1c0d52a1c8ed`, `mastermind.sol_skillpack.v1` 1.0.1.
This is the repository task tree, not an Executive Job/Attempt ledger, Agent OS workstream, approval, or release receipt. Publication of a draft PR does not establish deployment.

## Mission and acceptance

Ship an explicitly opt-in intelligent active-active Experiential Labs backend for Mastermind, with safe organization isolation, health/utilization/headroom/observed-cost-aware admission for **new independent calls only**, without changing the default Brain waterfall or creating a new global ModelRouter/Capacity/Executive authority.

The existing two-organization implementation (#1918, candidate `f0706957690d008c1e998e232a037de8f3118ad7`) passes offline Brain tests but is **BUILT_NOT_PROVEN**. Its Brain POST currently goes straight to the provider, bypassing #1849's durable SQLite shared-RPM accounting. This is a PRE-ACTIVATION BLOCKER. Never turn on concurrent Brain B + native Fabric B + Jev B on separate admission paths.

**DONE_WHEN:** On the accepted protected release, a new admitted B-only Brain request, native Fabric Responses request, and Jev System One request for the same **verified** Experiential organization all traverse the *same* scoped credential-owning gateway and the *same* persistent per-org rolling-RPM admission ledger. A fourth request above a controlled quota is refused locally without reaching the provider. A independently verified second organization uses a different, isolated quota and provider-key namespace. No denied, failed, timeout or unknown request is retried or cross-routed. The $1/day B provider key cap is proven by an authorized original-carrier readback and real model-serving/usage receipts. Real consumer-path checks and independent non-author review, exact-head CI, protected merge and authorized activation must independently pass.

## Plan nodes

| ID | Status | Goal / dependency | Required evidence |
|---|---|---|---|
| P1 | implementation_complete | Source baseline: optional Brain pool and provider identity/cap checks on #1918; default OFF. | `f0706957` with 50-pass read-only remote test receipt; neither provider proof nor current CI completion implied |
| P2 | implementation_complete | Gateway base on #1849: local bearer, host-owned upstream keys, durable SQLite per-key and `SAFE_RPM_SHARED` admission. | Exact immutable candidate, tests and independent source review; still unmerged |
| P3 | implementation_complete | System One POST through that same gateway, stacked #1934. | Mock Jev/Responses admission shared on one gateway; still unmerged |
| P4 | ready | Build **Brain shared-gateway transport**: use one per-org pinned localhost/tunnel route and scoped client token, *not* direct provider POST; preserve exact model and no retry. No unchecked URL override or raw key leakage. | New immutable code candidate with negative tests: route/org mismatch, off/held A, disabled gateway, auth failure, 402/403/429/timeout, no direct fallback |
| P5 | blocked | Move provider identity/model/cap/funding read-only probes to the gateway's authenticated metadata bridge (or existing authorized secret custodian), so the provider key stays on the hosting gateway. Depends on P2/P4. | Exact identity/slug, provider key daily cap & non-null remaining and real cost-lane receipts, without secrets in client |
| P6 | blocked | Compose Brain B Chat + Fabric Responses + Jev System One through one shared B SQLite RPM admission domain; independently configured A must never share B ledger or key. Depends on P3/P4/P5 and candidate #1920/#1851 route binding. | Hermetic orchestrated cross-consumer local test (1+1+1 admitted, fourth local 504, zero fourth vendor transmissions); separate A/B domain test |
| P7 | blocked | Release gates and live smoke: exact-head CI, non-author independent review of all changed heads, authorized B-only key cap and serving proof, protected merge, real consumer ledger and opt-in activation. Depends on P4-P6 and provider/account gates. | Real `deepseek-v4.1-flash` B-only request id, model, non-BYOK usage.cost, settled accounting, gate/disable rollback, no A requests |

## Fixed guards / non-goals

- `mastermindx6031` / B: Chairman selected included usage first; after included eligible model usage, up to **$1/day additional wallet usage**, with provider-enforced key cap. User's dashboard Save confirmation is valuable UI evidence but **not** proof of authenticated key-cap readback; the earlier credential-bound readback was explicitly safety-denied. Never repeat/bypass that denied action.
- `chriswong6031` / A stays disabled after original independent HTTP 403. Never replay that denied request, switch key/model/region to evade it, or infer second organization simply from two keys.
- Preserve `EXPLABS_POOL_ENABLED=0`, both account ENABLED=0 and SERVING_VERIFIED=0 as safe defaults through proof.
- No live provider requests, payments, account changes, secret copying, native Fabric worker authority, unreviewed merge, or production enablement is authorized by source-plan publication.
- A local Brain scoring function is **not** an Executive model/account selection authority; where an Attempt route is already bound, consume that binding and retain its fail-stop ownership.

## Current blocking evidence / source references

- #1918 `brain/explabs_pool.py` dispatch calls `brain.explabs_client.complete(api_key=...)` and `brain/explabs_client.py` pins the vendor API host.
- #1849 gateway `ops/native_fabric/experiential_proxy/gateway.py` admits only callers through its local instance and maintains separate persistent shared RPM history; #1934 adds System One path.
- #1918 GitHub discussion cross-consumer findings: issue comments 6570509597 and 6570779974.
- Provider/permission held: original A 403, B cap key API readback safety denial; B account dashboard UI confirmation alone cannot release the hold.

Next source slice: P4 + a focused P6 compatibility seam, without changing any live account, host, or provider state. Code and tests need their own reviewed immutable commit.
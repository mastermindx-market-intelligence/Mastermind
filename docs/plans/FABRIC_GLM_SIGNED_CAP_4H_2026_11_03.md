# Signed GLM capability — qualified 4-hour candidate

Operation: `fabric-glm-four-hour-capability-20261103-sol-002`
Repository: `mastermindx-market-intelligence/Mastermind`
Base: protected `master@910803421beca53ca25145392725ab2d84c7a8e9`
Dedicated branch: `sol/web-fabric-glm-four-hour-capability-20261103-sol-002`
Parent source upgrade: PR #2019 (`3505ab7785610df347fd6c0ceba6a97f92ad1e15`), which keeps installed signed GLM routes at their qualified 2h window.

## Observed blocker
GLM's separate signed lease capability issuer and verifier (`ops/native_fabric/paid_canonical_glm/candidate/glm_lease_capability.py`, `glm_lease_gateway.py`) still reject TTL above 7,500 seconds in both legacy and canonical code paths. The native runtime cannot safely launch signed-capability GLM work for four hours until both sides and the issuer are source-qualified, installed as one immutable generation, and proven against the broker lease.

## Required outcome
1. Increase *only* the finite TTL upper bound to 15,000 seconds in legacy and canonical signed GLM token mint/verification/HTTP issuance. Retain signatures, lease identity, original root, account/model/host, PID/heartbeat, expiry and immutable v1 token schema. Keep the source predecessor immutable.
2. Demonstrate exact-old-source plus narrow changed source (only four TTL comparisons in codec + two in issuer), including 7,500/15,000 boundary and 15,001 rejection, released/expired/rebound lease refusal, tamper/host/model/canonical scope refusal and no secrets in test artifacts.
3. Separate gate: source tests and independent security review; then current native PR #2019 merge/release and service-generation installation without disrupting running sessions. Only *after* installed cap service proof may the native route's visible 2h narrowing be removed and its parent-child token turn validated with 4h start/result/acceptance.

## Holds and non-goals
No live service config write, no provider token generation outside fixture, no owner switch, no new credential, grant, queue or retry plane. The present runtime 2h GLM safety cap in #2019 must remain until true installed gateway + verifier proof. Do not self-approve or self-merge.

## Source-stage evidence (2026-11-03)

- Exact predecessor codec SHA-256: `eb473e0ebe5c2cdf67fd8f1a2f689a5d2218a6a33e7ce7c9a32ff50fc868062f`. Candidate SHA: `3e4e2ad4dbdfd2ead14ef764adb0e134d6d73e907ef0edebe1d692d1b155a48c`. Only four `7500` -> `15000` TTL comparator replacements; immutable source file unchanged.
- Exact predecessor gateway SHA-256: `f70e233fae56590e51b0431d2f1b8f833ffb072c404b9ba9285eb335b65d0710`. Candidate SHA: `3ab7ae015d8093f81ab41d8ae73dd849572c8718530750d70ffe551aa719e258`. Only two comparator replacements; original v1 schema and error envelopes preserved.
- `tests/test_paid_glm_canonical.py`: all cases passing including new legacy v1 and canonical v2 signed 15,000-second token round trips, 15,001 refusal, HTTP gateway issuance and lease/account/model/host/expiry failures. No user credentials or provider calls.
- `tests/test_canonical_paid_definition.py` and `tests/test_session_bridge_web_reply_subscription_owner.py`: passing on candidate.
- **Production remains old 7,500-second issuer.** No installed service/host/token readback, cross-gen compatibility or live 4h start/parent acceptance has been claimed. The original 2h GLM narrowing in native PR #2019 must remain armed until this separate service source is reviewed, merged and installed through original owners.

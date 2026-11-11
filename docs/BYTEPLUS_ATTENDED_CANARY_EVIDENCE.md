# BytePlus supported-tool canary evidence — non-authoritative collection

**Status:** source-only evidence template/validator. It does not run Claude
Code, call BytePlus, capture subscriber credentials, attest provider origin,
issue Capacity facts, arm a model route, or authorize unattended Fabric workers.
It complements the existing BytePlus source preflight script
(scripts/byteplus_coding_plan_preflight.py) and the existing
BytePlus policy/runbook (docs/BYTEPLUS_CODING_PLAN_FOLLOWUP_PREFLIGHT.md).
The verified Personal Coding Plan is for an **individual attended supported
coding client**; a commercial generic ModelArk API entitlement is separate.

## Use

Copy the blank template from examples/byteplus_attended_canary_template.json
to a private operator-owned path **outside the repository**, populate only
nonsecret fields with evidence already lawfully collected for a single
attended Claude Code operation, then run from the repository root:

    python -m scripts.byteplus_attended_canary_evidence /private/path/to/redacted-evidence.json

The validator accepts only whitelisted keys and emits a non-sensitive
completeness report. **Do not commit filled input evidence**, viewer
data, provider response JSON, emails, account IDs, real operation transcripts,
raw request IDs, access tokens or Secret/Keychain contents to GitHub.
The presence of a SHA-256 digest is not evidence of issuer authenticity;
the output always keeps provider_origin_attested=false,
individual_request_debit_proven=false, capacity_fact_issued=false
and autonomous_start_authorized=false. If the input is incomplete, the
output identifies which operator evidence categories are still absent
without printing raw field values.

The supporting code and tests are pure offline validation; no new
scheduler, admission plane, account registry, or subscription watcher exists.

## Attended canary evidence steps

1. Subscriber verifies Personal Pro entitlement and approved supported
   Claude Code use, the client signature, selected Coding Plan model,
   isolated endpoint https://ark.ap-southeast.bytepluses.com/api/coding,
   and absence of PAYG fallback. Prior client auth status was not logged
   in; client authentication and a live response remain unproven.
2. Using the existing authenticated *management* CLI, note a **before**
   snapshot's provider measurement time, rounded used percentages and
   reset windows. Redact every account/user/tenant field before copying.
3. Subscriber, physically attending the supported coding client, performs
   one bounded deterministic coding task. Record the attempt identity,
   intended model, separately observed served model, run boundary,
   terminal result and tested artifact SHA-256. Never replay an uncertain
   effect merely to force a pass.
4. Obtain a matching **after** management snapshot; compare the same
   plan/window. The vendor may omit the session reset in BOTH before/after
   snapshots; in that case, the validator permits a syntactically complete
   operator candidate when weekly/monthly windows match, but reports
   session_window_comparable=false and session_reset_not_reported as an
   explicit caveat. A single missing or inconsistent session reset is
   inconclusive and fails completeness. Integer percentages (including
   0% to 0% or 0% to 1%) never establish a single request's debit/model.
5. Existing ProviderRealm/Capacity/Executive owners, not this script,
   decide whether issuer-bound account/realm, model, use-rights,
   Capacity and audited production lifecycle proofs exist. Coding Plan
   requests must not be used as generic autonomous API inference,
   irrespective of Team versus Personal seat.

The most this local validator can say is that a *syntactically complete
operator-supplied candidate* exists. It cannot authenticate subscriber
presence, match BytePlus's billing record, issue a real plan transaction
receipt, or prove current available worker concurrency. If usage
attribution is impossible from the provider's available interfaces,
record it as **unknown** and preserve the source as BUILT_NOT_PROVEN.

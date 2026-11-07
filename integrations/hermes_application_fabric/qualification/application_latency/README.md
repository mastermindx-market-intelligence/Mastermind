# Expected latency through the existing APPLICATION owner

This is a source-qualified contribution for [original APPLICATION #2175](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2175). It is packaged separately because its Broker/Gateway/picker/Go-handler paths remain under the incumbent APPLICATION and H6 writers. It does not install source, publish a grant, select a release, contact a real provider, or activate a Hermes session.

The first eligible fixed/exact Secretary conversation remains independent of this optional latency qualification. Its live account, role/session, entitlement, funding, release and original-effect predicates still belong to the existing owners.

## Gap closed

The incumbent picker already uses task complexity, capability, eligible models, physical account headroom and economic pool/default/catalogue policy. It had no expected-latency input. The patch adds one trusted-purpose field, `max_expected_latency_ms`, and consumes qualified performance evidence in the existing owner document. It does not create a model router, broker, account store, performance database, polling service, retry plane or spending ledger.

The limit applies to expected completion time for one bounded nonstream model request. It is not a promise of wall-clock completion, time to first token, a whole tool conversation, or authority to cancel/replay a provider call. Existing Hermes buffering, cancellation, tool execution, structured-output validation and attribution remain in their existing owners.

## Integration surface

The patch changes exactly four existing production files and adds one disjoint test file:

| Existing owner | Change |
| --- | --- |
| `candidate/pick.py` | Validate the optional task ceiling and per-model facts; exclude unknown/too-slow recipes; resolve only a unique fastest recipe within the best existing catalogue rank. |
| `candidate/lease_broker.py` | Validate relevant qualification, preserve authorization digests, bind qualification separately, and recheck the actual payload/cohort at new admission and each new dispatch. |
| `candidate/go_lease_gateway.py` | Carry host purpose, actual payload and transport binding through existing selection/admission/dispatch; freeze the qualification commitment. |
| `candidate/go_shim.py` | Publish an opaque owner binding on authenticated `/status`, carry it through the existing handler, and verify/freeze actual endpoint/account bytes at the single send boundary. |
| `tests/test_hermes_application_latency_qualification.py` | 28 focused cases using the original picker/Broker/Gateway/handler and loopback-only provider fixture. |

Paths are relative to `ops/native_fabric/quota_continuity/`. No protected Hermes/Brain source, native entry, installer, release manifest, worker delegation, accounting schema, or existing CI workflow is changed by this proposal.

The existing installer preserves complete grant documents and delegates permission validation to the Broker. No second enrollment flow is introduced. A malformed optional performance annotation is unusable for constrained selection; it does not revoke unrelated permission. The grant's authorization digest excludes only this new annotation. A constrained selection separately freezes its complete SHA256 in the existing immutable selection commitments. Changing a qualification therefore requires a new constrained selection; original pending/terminal/unknown recovery still returns before current qualification checks.

## Trusted inputs and qualification

The existing host-owned selection purpose may add `max_expected_latency_ms`, an integer from 1 through 86,400,000. A latency-constrained purpose must explicitly provide `task_complexity`; no complexity is inferred. HTTP payloads cannot supply latency authority, an account, a grant or a transport binding. Host-authorized exact model and pool selections retain their current contracts.

An optional `latency_qualification` annotation in an existing APPLICATION grant has the following closed shape. All illustrated identities and numbers are synthetic; this is not an enrollment document:

```json
{
  "schema": "mastermind.application_latency_qualification.v1",
  "metric": "request_completion_ms",
  "evidence_ref": "owner:existing-qualification-evidence",
  "observed_at": 1000,
  "expires_at": 1100,
  "source_profile_digest": "<SHA256 of the actual source profile>",
  "provider_config_digest": "<SHA256 of the existing provider row>",
  "transport_binding": {
    "schema": "mastermind.application_latency_binding.v1",
    "pool": "go",
    "instance_id": "<actual existing gateway instance>",
    "configuration_digest": "<actual opaque owner HMAC>"
  },
  "accounts": ["fixture-account-a", "fixture-account-b"],
  "models": {
    "fixture-model": {
      "served_model": "fixture-model",
      "expected_ms": 250,
      "sample_count": 5,
      "max_request_bytes": 4096,
      "max_output_tokens": 128,
      "task_classes": ["mechanical"],
      "task_complexities": ["C1_ROUTINE_BOUNDED"],
      "capabilities": ["tools"]
    }
  }
}
```

The qualification owner must substantiate the exact served model and the complete sorted grant-account cohort under the declared workload, capability, request-size and output bounds. A fast sample from one physical account cannot qualify another admissible account. Evidence must be current, source/configuration-bound and supported by its retained owner reference; failed requests, 429s, timeouts, unknown serving models and unrelated historical request sizes are not successful latency samples. This code consumes that owner qualification and does not manufacture a measured estimate from names, prices, timeouts or legacy receipts.

Validity is bounded by the grant and at most 24 hours after observation. The request must carry an explicit positive `max_tokens` within the qualified maximum, and its canonical UTF-8 body excluding only the model label must fit `max_request_bytes`. History, tools and sampling controls count toward that envelope. The record's supported task/capability set is checked for every new dispatch.

The Go transport binding uses an HMAC with the existing private controller token over the actual loaded account credential map, endpoint, wire compatibility and concurrency configuration. Only the opaque digest and already-existing gateway instance identifier leave that owner. No credential value or new key is stored in the grant or exposed to Hermes. The existing authenticated `/status` surface supplies the binding; unauthenticated `/health` and application pool-view schemas are unchanged. Restart, account-key, endpoint, wire or concurrency changes invalidate prior evidence. Refresh belongs to the existing owner publication path, not repeated service enrollment or an adapter watcher.

Only Go has an actual transport-binding producer in this bounded patch. Other transports remain unknown for latency-constrained selection until their own owners provide an independently qualified binding. Their existing unconstrained/fixed behavior remains available under its original permissions.

## Selection and effects

Latency does not move a model ahead of an eligible incumbent economic pool/default/catalogue preference. It removes recipes that cannot meet the trusted expectation. Only a remaining tie at the best catalogue rank can be resolved by a unique faster qualified recipe. Equal fastest recipes, including the same model with different sources, remain ambiguous. Exact-model requests never silently choose another model.

The model-to-account relationship remains many-to-many in the existing Broker. The timing qualification covers the entire admissible grant cohort; it does not create per-model copies of account capacity, reserve quota twice, or change worker/APPLICATION competition for the same physical slot. Unknown monetary cost remains unknown. Existing included, prepaid or free funding policies remain valid when the actual owner permits them; no new universal dollar ledger or provisioning-key requirement is introduced.

The new-turn transaction checks qualification before acquisition and again before inserting the turn, so expiry rolls back its lease. Every new dispatch checks the original payload digest and frozen qualification. The permit cannot outlive qualification. Immediately before the one provider POST, the transport checks the binding and freezes the actual endpoint and credential under its existing lock; it releases that lock before I/O.

Original request recovery remains ahead of all current latency/configuration checks. A post-intent configuration drift uses the incumbent retained pending/unknown handling and never creates an alternate account call. Fixture proof observes zero upstream POSTs in that case; the retained dispatch is not relabeled as a settled no-effect result or silently retried. No new failover authority is introduced.

## Exact source and verification

`contract.json` records all preimage/postimage Git blob and SHA256 values. Production preimages match both original `bd119dfd25db6e9b5b48ab461407faf29cb0725d` and its published successor `0d8174951141b1790e6121e13202e4036d1bdc20`. Nineteen public source/test/dependency blobs were materialized and independently Git-blob verified. No held J/private-J implementation, installed source, production credential or provider endpoint was read for this qualification.

The clean isolated patch roundtrip passed `git apply --check`, applied without conflict, and reproduced every declared postimage while preserving every unchanged test input. The exact candidate passed:

- **28 new latency cases**, zero failures/errors/skips, including authenticated handler AUTO selection, native tool history, strict intent, qualification freshness and cohort changes, atomic rollback, direct-token continuation bounds, unchanged unconstrained grant identity, and original-effect recovery.
- **117 existing owner cases**, zero failures/errors/skips: `test_application_turn_pick`, `test_application_turn_admission`, `test_application_turn_selection_admission`, `test_application_turn_pick_go_composition`, and `test_go_application_handler_composition`.

The raw logs and `local-proof.json` retain these exact executions. Pure tests use the existing offline boundary; handler cases use the incumbent numeric-loopback-only fixture with real Broker/Gateway/SQLite and synthetic lifecycle helpers. These are source/contract results, not live provider, spend, installed-release or Hermes operational acceptance.

The incumbent APPLICATION/H6 writer should reconcile its current four preimages, incorporate this delta into its active composition, and update its existing source/release identity declarations through that same owner. Do not apply over a changed preimage, overwrite concurrent Phase C work, or downgrade the current native entry to an older pin. The existing fixed/exact Secretary acceptance continues independently while this optional owner contribution is composed.

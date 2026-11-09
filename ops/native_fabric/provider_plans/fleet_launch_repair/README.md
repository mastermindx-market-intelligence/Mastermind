# Fleet launch repair over the selected 119-member generation

The incumbent composer exposes the fixed `terminal119-fleet-launch-repair` profile.
It consumes only the complete 119-member public-code predecessor
`8404cb15c5322690a8b805140e9f987710881e8ac020f2eee4f6cafa41fdee03` (observed
CURRENT sequence42) and changes exactly four members:

- `ext/support_bundle.py`: the idle-only policy refresh treats five retained
  settlement kinds in `ext/active` as metadata, not live lanes. Each record must be
  owner-custodied (no group/other write, O_NOFOLLOW, flock, unique-key JSON) and
  match its exact writer shape. A held marker counts only when a valid sibling seat
  settlement names it (`marker_moved_to`, `marker_sha256`, `hold`). Anything else,
  including a non-dot lane marker, still refuses with
  `SUPPORT_POLICY_STALE_ACTIVE_REFUSED`.
- `ext/fabric_task.py`: the `support-policy-status` qualified-source pin follows
  the new `support_bundle.py` hash.
- `ext/lease_broker.py`: `pool status` renders YAML timestamps (`parked_until`,
  usage) as UTC `Z` strings instead of crashing `json.dump`; a
  `host_account_unavailable` refusal carries a closed snake_case detail.
- `ext/remote_sub.sh`: `LEASE_REFUSED rc=75` logs the broker's closed
  `reason=`/`detail=` tokens.

```sh
python3 ops/native_fabric/provider_plans/compose.py --profile terminal119-fleet-launch-repair --base <owned-exact-8404cb15-source> --output <fresh-owned-source-output>
```

This is a prospective source descriptor, not publication, CURRENT, permission or
deployment. Root must qualify the protected source and run a fresh
`native_generation select --expect 8404cb15…` CAS at adoption; any other CURRENT
refuses and needs a separately qualified rebind. No classification here clears
EFFECT_UNKNOWN, deletes or rewrites another run's settlement, or edits pool policy
content. Existing profiles, source guards and the default are unchanged.

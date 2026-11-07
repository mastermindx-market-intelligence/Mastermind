# H2 — GLM reset cards and automatic recovery

Scope: Chairman's November 7 extension of
[the original H2 assignment](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6705878207).
Source carrier: [PR #2215](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2215).
Continuity: [same H2 return](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6706283300).
The existing #983 / C0–C5 programme and final #2175 / Macro #10740 composition remain.

## Decision and evidence

Use the provider's manual reset controls after a useful marathon when weekly
allowance is the binding limit. The implementation automatically discovers fresh
allowance through the existing on-demand reader and safely reopens the existing
quota circuit. Autonomous redemption is **not enabled**: the checked public API
specification documents no reset-card operation, and current provider instructions
describe clicking Reset. This is a bounded supported-contract finding, not a claim
that an internal console endpoint cannot exist.

Official facts checked November 7:

- A weekly quota card restores both weekly and five-hour quota, without spending
  a separate five-hour card. The corresponding cycle restarts at redemption; the
  weekly period is seven days. Cards have individual expiry dates.
  [Z.ai FAQ](https://docs.z.ai/devpack/faq).
- ZCode documents manual redemption, automatic issuance of some off-peak five-hour
  cards, and expiry. Issuance depends on sign-in, plan connection and dynamic
  conditions. Automatic issuance does not establish automatic redemption.
  [ZCode usage statistics](https://zcode.z.ai/en/docs/usage-stats).
- No reset/voucher operation appeared in the checked
  [public OpenAPI specification](https://docs.z.ai/openapi.json) or
  [documentation index](https://docs.z.ai/llms.txt).

The Chairman's screenshots display three unused weekly resets, each expiring
`2026-12-22 23:59:59`. Their account identity and display timezone are not established;
this information is not loaded into an account ledger or treated as live capacity.
The exact companion five-hour deadline after a weekly card is taken from the
provider response, not calculated locally. No voucher has been consumed for this work.

## What was wrong

The original reader can observe replenishment, but a broker `quota_exhausted`
cooldown retains its old deadline. The picker consults that cooldown before reaching
quota refresh. This can both hide a manual refill and keep the account blocked
after its updated counters are available. Separately, replacing the entire GLM
account map after one refresh can erase another concurrent account's newer failure.

## Implemented path

1. The normal picker and host-account eligibility path call the original GLM
   refresh owner before excluding the pool. Its existing 300-second on-demand
   interval applies. A request that encounters a due observation can discover a
   refill even when the old weekly deadline is days away. There is no timer daemon.
2. Refresh publishes only the touched account, under one short cache-publication
   lock with a bounded acquisition wait. It saves a unique pending attempt before
   the provider GET, then replaces only that matching attempt with its result.
   Network I/O occurs outside the lock. Old positive observations cannot admit work
   while publication is pending. A failed initial publication performs no GET; a
   failed final publication retains an uncertainty fence in the original cache.
   TTL, force and configuration changes do not replay an unresolved attempt.
   Request-start ordering keeps a late older result from replacing newer evidence;
   terminal permission refusals remain retained even if another read succeeded.
3. Both required windows stay attached to the same configured account, endpoint
   and local configuration generation. Their actual counters and reset timestamps
   replace the old observation. Null clocks remain null. An optional `quota_change`
   projection describes increases/clock changes with cause `UNDETERMINED`; it does
   not label a natural refill as voucher redemption. Completion-time evaluation
   prevents an honestly later provider response being mistaken for a future clock.
4. The broker's original lease captures `quota_config_generation`. Its existing
   quota-cooldown row captures the generation of the actual failed lease. A newer
   fresh read, started strictly after that failure, with both windows above the
   existing 5% reserve can permit the original **half-open** recovery probe.
5. The SQL cooldown is unchanged by observation. Its read projection can show
   `HALF_OPEN`, while the incumbent broker lock and allowance-scope reservation
   allow at most one outstanding probe across models/pool aliases. The lease's
   `quota_recovery_json` binds the exact cooldown revision and qualifying evidence.
6. Only the original qualified successful-work receipt can clear that revision.
   A newer failure between projection, claim or settlement wins. A rate-limit
   component retains its own deadline when quota failures overlap it; replenishment
   cannot bypass that component. The final lease timestamp follows qualification
   and precedes the unchanged deadline/authorization checks. No quota read
   grants inference, dispatches a task, spends a reset, deletes a cooldown or clears
   a separate authentication, rate, administrative or economic hold.

The new fields extend existing `leases` and `quota_cooldowns` tables through the
incumbent schema owner; no additional database, identity store, queue or scheduler
is created. Existing legacy cooldowns without a captured generation and declared
shared allowance scopes retain their original expiry/settlement behavior. A local
configuration generation is not provider identity attestation; broader shared-account
membership and whole-operation financial ceilings remain the H3/H4 contract.

## Manual operation after a marathon

Choose the intended account in the provider UI and consume one weekly reset only
when its immediate value exceeds waiting for the ordinary reset. A weekly card
reanchors the cycle: it does not add a second replenishment at the old deadline.
If only the five-hour window is tight, a weekly card may be unnecessarily costly.
Do not redeem multiple full-refill cards consecutively as additive capacity.

After redemption, normal new-work routing rechecks on its next due owner read.
For immediate readback, the accepted successor also supports:

```sh
python quota_remote.py reconcile-reset --account <configured-account-name>
```

Run this through the existing selected runtime owner after composition; the command
name here does not authorize executing an unselected source file against production.
It refreshes only that configured account and prints qualified paired windows.
Exit 0 means current quota evidence is ready; exit 2 means it remains unqualified.
Output explicitly reports `redemption=NOT_PERFORMED`, `broker_hold=NOT_MUTATED`
and the actual observation. `--force`/this command never overrides a retained
terminal refusal. If the reset has not appeared upstream, no allowance is invented.
An unresolved `REFRESH_IN_PROGRESS` record means the original observation's final
publication needs owner reconciliation. It is not proof of a persisted refusal,
and this command cannot erase it or issue another request around it.

Use accepted, useful tasks under current capability, concurrency, reserve and
Fabric budget limits. A reset does not raise those limits. No filler work, duplicate
completed tasks or enlarged contexts are generated to empty an account. No new
automatic early-week burn schedule is installed. The user's manual-after-marathon
preference is the operational default until a supported redemption contract with
account binding, exact-effect reconciliation and independent authorization exists.

## Qualification and deployment boundary

Final host qualification passed **66 focused tests**: 43 account/quota regressions,
16 real broker/picker recovery journeys and 7 existing Grok billing cases. The same
16 journeys also passed against isolated copies of the actually selected native
generation `ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46`
(selection sequence 35). The [byte-bound predecessor receipt](evidence/hermes-pool-h2-glm-reset-predecessor-2026-11-07.json)
records the original source hashes, all four successor hashes, test hash, Python
version and unchanged selection at 13:19:20 UTC. No provider request or reset-card
redemption occurred in that fixture qualification.

Focused tests exercise the serialized cache, real patched original Broker, original
provider-outcome validation, SQL cooldowns, actual atomic claim and successful
settlement. They cover manual weekly plus five-hour refill, five-hour-only refill,
changed/null clocks, the ordinary blocked-picker refresh path, host eligibility,
same-account/generation/endpoint fences, stale/missing/duplicate/future windows,
request-start ordering, two concurrent contenders, newer failures, terminal refusal,
legacy/shared-scope holds, disabled providers, cross-account cache races, overlapping
rate/quota holds, refresh during claim, and refusal-publication contention/failure.

The provider responses and worker outcomes in these tests are isolated fixtures.
They are not a live exhausted-account or voucher-redemption acceptance claim.
The earlier real natural replenishment remains in
[the original-owner receipt](evidence/hermes-pool-h2-original-refresh-reset-2026-11-07.json).

The existing publisher must compose these together against its exact current
predecessor: `ext/quota_remote.py`, `ext/quota_circuit.py`, and the two bounded
broker/picker patches. Frozen quota-continuity candidates, native manifests and
selected generations are not modified in this source change. Mixed old/new quota
writers are not a supported installation: original release/drain procedures must
ensure all active publishers of the shared cache use the same serialization.

Protected source acceptance, final native composition/selection, and live recovery
remain separate receipts. The existing branch-protection administrative-read403 is
preserved; it is not retried through another carrier. The actually active #2175 /
Macro #10740 composer and original runtime effects retain custody. Source and fixture
success alone do not make the installed system complete.

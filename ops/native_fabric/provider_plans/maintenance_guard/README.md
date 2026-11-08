# Sequence-39 maintenance guard and sparse-Git compatibility

This version of the existing closed maintenance profile starts from the complete
sequence-39 generation
`774f98693ec805f5e37fe99c94e5e2d2789c7255210274750da4816ace6347ea`
(previous `296e522f…`, sequence 38). The picker correction is already present.
All five newer provider-plan payloads stay intact.

Exactly two payloads change: Broker `a841230c…` to `4072c76f…` adds the two
reviewed static qualification/maintenance guard methods; executor `bb036914…`
to `e13c8147…` carries the reviewed command-scoped
`advice.sparseIndexExpanded=false` setting. Both fixed-parent patches are
byte-identical to their protected PR2241 versions. The other 114 payloads remain
byte-identical to sequence 39, including every newer provider-plan file and the
already corrected picker. Incumbent application methods, main entrypoints,
strict stderr/configuration/currentness guards and source ownership remain intact.

The composer, its closed profile names, CLI, source validators and ordinary/default
profile do not change. No caller supplies a profile path, parent override, policy,
account or dynamic approval. Both the exact generation and entire predecessor
manifest must qualify before any output is created. A sequence-37 or sequence-38
parent is refused. The original sequence-37 maintenance profile remains immutable
in protected PR2241 commit `efab46368e13e9553e489cb61a58ca28055df175`;
its `e032…`/`e895…` prospective stages must not replace a newer selected cohort.

## Source qualification

The inert fixture reconstructs sequence 37 from the existing sealed public source,
uses the actual default composer for sequence 38, then uses the actual remote
placement profile for sequence 39. All 116 hashes are checked before the maintenance
profile is applied. Fixture source descriptors are comparison data, not installed
selection, admission, caller permission or provider receipts. Tests do not import
Broker or exercise its database/lock methods. Existing reviewed guard and executor
logic is reused unchanged; the new checks qualify this exact parent and preservation.

## Compose and adoption boundary

```sh
python3 ops/native_fabric/provider_plans/compose.py \
  --profile current116-maintenance-guard --base VERIFIED_SEQUENCE39 \
  --output NEW_PRIVATE_SOURCE_STAGE
```

This builds regular public code and FILES.json only. It neither copies runtime
links nor reads their targets; no Broker construction, database, lock, policy,
host, provider, publication or selection operation occurs.

The incumbent `native_generation.py` remains the sole artifact publication and
exact-current-generation CAS selection owner. Root must reconcile actual current
source, selection and live-writer custody before any separately authorized adoption.
If current moves, this fixed-parent profile refuses rather than rolling it back.
Host maintenance, policy qualification and any genuinely new worker admission are
separate effects. No original refused or uncertain operation is retried.

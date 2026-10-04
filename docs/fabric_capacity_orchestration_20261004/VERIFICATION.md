# Capacity projection source verification

Operation: `fabric-capacity-orchestration-upgrade-20261004-sol-001`.

## Proven source increment

The existing `control_plane/capacity_economics_projection.py` now provides an additive, preview-only owner-envelope composition. It separates parallel-job headroom from cumulative job-start bounds; requires all declared quota windows and intermediate ancestors; binds option/provider/model, root, operation, quota domain and workload; checks observation and preview freshness; treats unknown and zero bounds distinctly; and intersects all ceilings without summing shared allowances. It does not alter provider quota accounting, the live broker, Model Router's lawful tier, Executive claims, native launchers or active workers.

The v1 API and output schema remain present. Its expiry-pressure scalar now rejects nonfinite, negative and nonnumeric values, and its options scan is bounded. The new v2 projection requires explicit caller-supplied scope, clock and freshness policy. Its result continues to declare `NONE_PREVIEW_ONLY`, `binding_verification=NOT_PERFORMED`, `live_admission=false`, `selection_is_commitment=false`, and `claim_time_revalidation_required=true`.

This is NOT an authentication mechanism. The independent scope and every normalized bound must come from the existing canonical owners. Model-written capacity estimates are not valid producer evidence. Runtime adoption and actual claim-time revalidation remain integration gates.

## Test evidence

Execution environment: offline conversation verification container, Python 3.13.5. This was not a native-host installation or a provider call. Only the selected module and focused tests were reconstructed; a whole-repository test run is not claimed.

Before editing, Git blob hashes of the reconstructed baseline matched GitHub exactly:

- Module: `57624155a30aa3217e66727be64b1e30733c7201`.
- Existing test file, preserved unchanged: `64a966af37e30012393288d4322e6d86413f79a2`.

Regression run against the original source: **7 failed, 14 passed**. The failing cases demonstrated acceptance of `NaN`, `sNaN`, positive/negative infinity, negative pressure, a nonnumeric string, and an oversized options list. The new scalar-test fixture was subsequently made self-contained; the assertions are preserved.

Focused final command:

```sh
PYTHONPATH=. pytest -q tests/test_capacity_economics_projection.py \
  tests/test_capacity_economics_scalar_hardening.py \
  tests/test_capacity_economics_owner_envelope.py
```

Result: **121 passed in 0.15 seconds**. One property test executes **500 seeded cases**, checking every budget bound and monotonicity after lowering an arbitrary constraint. These are model/contract checks, not measured production throughput.

Covered cases include: GLM Flash model ceiling versus a tighter shared account ceiling; a distinct full-model ceiling; zero and unknown evidence in every required dimension; root/domain/operation conservation; omitted quota windows and ancestors; cross-account/workload/operation transplantation; reset-epoch substitution; stale/future/expired observations; future forecasts and TTL not replenishing present capacity; immutable results; unchanged lawful suitability tier; and advisory-only output in all result states.

## Exact tested objects

| Path | Git blob SHA | SHA-256 |
| --- | --- | --- |
| `control_plane/capacity_economics_projection.py` | `60a99622818ec704c8b18454a4c416140eb349c4` | `494b6cd12462bc24ebd80ce81eb40950bb7e35f52067291c62f9a7068ef9349e` |
| `tests/test_capacity_economics_scalar_hardening.py` | `c43b90c3c6e4835951ed10ab7b51cc711cc637bc` | `774ea50fd4d707039969fab408e6be542c409e08f26f032e5ada609a8890fec5` |
| `tests/test_capacity_economics_owner_envelope.py` | `6d0fc2248a1e15a25bc4306dac675d58014db61e` | `c09f87cd2aafffc7f9afe33638b4c661ebece874ca8bdd18d0ac234fede2d396` |

The GitHub `create_blob` receipts matched each tested blob hash before the tree was assembled.

## Still unproven / release held

Required whole-repository CI, independent review, protected merge, owner-envelope producer adoption, actual atomic concurrent claims, native parent/child return, provider entitlement, installed selection, live account qualification and measured throughput improvement are not proven by this test suite. No active worker was changed or spawned. The native-host lane remains held at the previously recorded precheck/platform blocks; those requests were not replayed.

Next source work: finish the orchestration amendment and exact incumbent-owner integration contract, then request review and attach this candidate to the existing Fabric/hierarchy/native-projection intake. Do not create a second scheduler or replacement Fable principal.

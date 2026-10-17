# Capacity projection source verification

Operation: `fabric-capacity-orchestration-upgrade-20261004-sol-001`; source PR #1247. Protected baseline: `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`.

## Proven increment and limits

The existing `control_plane/capacity_economics_projection.py` now provides an additive, preview-only owner-envelope composition. It separates parallel-job headroom from cumulative start bounds; requires all declared quota windows and intermediate ancestors; binds option/provider/model, root, operation, quota domain, workload, host and reviewer pool; checks outer observation and preview freshness; treats unknown and zero bounds distinctly; and intersects ceilings without summing shared allowances.

It does not change native quota accounting, live broker behavior, Model Router's lawful tier, Executive claims, native launchers or active workers. It does not authenticate facts, prove an inner evidence reference fresh, provide a distributed snapshot, reserve capacity, or guarantee global conservation across concurrent claims. Those remain explicit producer and canonical claim-owner responsibilities in NATIVE_INTEGRATION.md.

The v1 API/schema remain. Its expiry-pressure scalar now rejects nonfinite, negative and nonnumeric values, and its options scan is bounded. The additive v2 requires explicit caller-supplied scope, clock and freshness policy. Every v2 output continues to declare `NONE_PREVIEW_ONLY`, `binding_verification=NOT_PERFORMED`, `live_admission=false`, `selection_is_commitment=false`, and `claim_time_revalidation_required=true`.

## Causal test evidence

Environment: offline conversation verification container, Python 3.13.5. Only the selected module and focused tests were reconstructed. No native-host installation, provider call or whole-repository test execution is claimed.

Reconstructed protected objects matched GitHub before editing:

- Original module: Git blob `57624155a30aa3217e66727be64b1e30733c7201`.
- Existing test file, preserved unchanged: `64a966af37e30012393288d4322e6d86413f79a2`.

First RED run against the original module: **7 failed, 14 passed**. It demonstrated acceptance of NaN/sNaN, positive/negative infinity, negative pressure, a nonnumeric string and an oversized option list. The initial source candidate at `644166101fbe656ca5a216e6573395016ce4b53a` then passed **121 tests**, including 500 seeded budget checks.

Further adversarial inspection identified that host and reviewer constraint references were not independently bound. The two new transplantation tests both failed against that first candidate. The repair adds `host_ref` and `review_pool_ref` to the independent scope and envelope, and validates the matching constraints. Additional cases cover header transplantation, owner-confirmed replacement of retired quota windows and a root projection without intermediate ancestors.

Final focused command:

```sh
PYTHONPATH=. pytest -q tests/test_capacity_economics_projection.py \
  tests/test_capacity_economics_scalar_hardening.py \
  tests/test_capacity_economics_owner_envelope.py
```

Result: **127 passed in 0.16 seconds**. One test executes **500 seeded cases**, verifying every supplied budget bound and monotonicity after lowering an arbitrary constraint. These are source/contract tests, not measured production throughput or independent external review.

Coverage includes GLM Flash ceiling versus tighter shared-account headroom; distinct full-model limits; zero and unknown evidence on every required axis; missing windows/ancestors; account/model/root/operation/workload/host/reviewer substitution; reset-epoch substitution; stale/future/expired timestamps; forecasts and TTL not replenishing present capacity; immutable results; unchanged lawful tier; and preview-only output in all states.

## Exact tested objects

| Path | Git blob SHA | SHA-256 |
| --- | --- | --- |
| `control_plane/capacity_economics_projection.py` | `bf48193419272c78a8d10a179a1c6e2ee2381e0f` | `14881f56d888b88debf5f7a0bfd1267b42401f2c135e7694bd2fe52526356a8c` |
| `tests/test_capacity_economics_owner_envelope.py` | `fbd163e54814cb660cfc696c13157710fae51cf2` | `4b6c85cac924c5569b0ad463d553aba8c2b9afc6ed441c60c86c3fce429984f8` |
| `tests/test_capacity_economics_scalar_hardening.py` | `c43b90c3c6e4835951ed10ab7b51cc711cc637bc` | `774ea50fd4d707039969fab408e6be542c409e08f26f032e5ada609a8890fec5` |
| Unchanged `tests/test_capacity_economics_projection.py` | `64a966af37e30012393288d4322e6d86413f79a2` | `6608fc32f1ed274e6ba35cd66b584250825083afab8564a187cdbae69896cd05` |

GitHub blob-creation receipts matched the tested module and test objects before tree assembly. No hash is inferred from a display name.

## Routing-law preservation

The complete pre-existing `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md` was reconstructed and byte-verified against blob `5bfb9bbc91177e2400da596b45ec809d294a3242` (22,436 bytes). The default branch was re-read at the decision boundary and still reported that blob. The proposed file appends only Section 12 (1,229 bytes), referencing the new amendment; all earlier content remains unchanged.

- Appended routing document: `73f2055f4c7d8b2b73a826c32a2b26e50b722d2e`.
- New amendment: `c6351941829e251f981ec76c81cce54f16f73b13`.
- Native integration contract: `e76b981a51700d45084aa4bb3a1a2d9b3c6587e9`.

These document blob receipts also matched their inspected local objects. Branch/PR law text is not protected law until accepted; an accepted link is not proof of current-session loading or installation.

## Release held

Required full-repository CI, independent review, protected merge, producer adoption, actual concurrent claims, native parent/child return, plan entitlement, installed selection, live account qualification and measured throughput improvement remain unproven by this suite. Native host gates and the original managed workspace are preserved in README.md. No active worker was modified or spawned.

Next action: exact-head source review/CI and fixed-candidate incumbent intake, followed by the staged actual-consumer acceptance in NATIVE_INTEGRATION.md. No second scheduler, replacement Fable, new watcher or unapproved provider spill is part of this increment.

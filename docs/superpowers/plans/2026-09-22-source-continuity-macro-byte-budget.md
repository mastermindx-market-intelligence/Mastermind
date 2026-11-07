# Source Continuity Macro byte-budget successor

Operation: `source-continuity-macro-byte-budget-successor-20260922-sol-001`

## Outcome

Restore remote-complete census headroom for the current Macro open-PR estate without
changing collision cardinality, call count, wall-clock, per-response, authentication,
retry, transport, or authority semantics.

The predecessor failed closed after **103,190,504 normalized bytes**. A sizing-only
probe with a 128 MiB ceiling completed the same class of census at **104,630,037
normalized bytes**. Both measurements are below 128 MiB and above the incumbent
96 MiB ceiling.

## Frozen production change

Exactly one production definition changes:

```python
_MAX_HTTP_NORMALIZED_BYTES = 128 * 1024 * 1024
```

These ceilings remain unchanged:

- open collision PRs: 450;
- logical HTTP calls: 1152;
- invocation read budget: 300 seconds;
- one HTTP response body: 5,000,000 bytes;
- foreign-file probe/page and worker bounds.

No caller knob, alternate verifier, retry lane, cache, queue, auth path, or publication
plane is added.

## TDD acceptance

Before changing production source, the protected 96 MiB implementation must fail tests
that require:

1. the measured 104,630,037-byte Macro estate to fit;
2. exactly 128 MiB to remain admissible;
3. 128 MiB plus one byte to fail closed.

After the one-line source change require:

1. the four frozen budget/scale files green;
2. the complete `tests/test_source_continuity*.py` family green;
3. explicit 450/451 PR, exact-call/one-under, exact-byte/one-under, and deadline
   discriminators green;
4. D8 identity/topology scan empty on the real diff;
5. Python compile, `git diff --check`, and exact six-path scope proof;
6. current protected-base collision/integration reconciliation;
7. one independent exact-head review;
8. canonical Source Continuity remote-complete;
9. a real held Macro consumer census reaching proof instead of the byte-budget refusal.

## Exact source scope

- `scripts/source_continuity.py`
- `tests/test_source_continuity_macro_scale.py`
- `tests/test_source_continuity_census_budget.py`
- `tests/test_source_continuity_saturated_foreign_pr.py`
- `tests/test_source_continuity_base_branch_semantics.py`
- this plan

No merge, protected release, consumer merge, deployment, or writer release is implied by
local qualification or a passing remote-complete receipt.

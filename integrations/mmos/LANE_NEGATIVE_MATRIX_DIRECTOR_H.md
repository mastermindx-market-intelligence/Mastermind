# Lane ledger — Director H: §6 negative-case matrix (V1)

Branch `t3/negative-matrix-v1` (from 7bbac9278). No push, no PR. Full matrix
with citations and designs: `integrations/mmos/NEGATIVE_MATRIX_V1.md` (this
file is the lane summary + hand-off list).

## Totals

| Status | Count | Rows |
|---|---|---|
| PROVEN_BY_TEST | 6 | NM-04, NM-05, NM-12, NM-13, NM-18, NM-20 |
| PARTIAL | 5 | NM-06, NM-09, NM-16, NM-17, NM-19 |
| GAP | 1 | NM-10 (no in-repo boundary; gateway-owned) |
| OWNED_BY_RUNNING_DIRECTOR | 8 | NM-01, NM-02, NM-03 (A3) · NM-07, NM-14, NM-15 (C) · NM-08 (A3) · NM-11 (lane A) |

20 rows total (17 §6 rows, splits: restart before/after ACK; gateway
busy/disconnected/stopped).

New tests: `tests/test_mmos_negative_matrix.py` — **5 passed, 1 xfailed
(strict)** (`test_nm06_gateway_stopped_needs_a_label_distinct_from_busy_and_disconnected`;
strict XPASS will flag the day a distinct stopped-state lands).
No new vitest file: the only free non-React TS boundary
(`auth-navigation-guard.test.ts`) already has an adversarial suite — run and
verified (3 passed); remaining TS surfaces are D/B-owned.

## Source fixes

**None.** No production source was modified by this lane. The one candidate
(429 → a dedicated `RATE_LIMITED` reason code in
`provider_quota_observation.REASON_CODES`) was deliberately NOT made: the
closed vocabulary is pinned by an existing assertion
(`test_reason_codes_are_the_typed_unknown_vocabulary`), and the current
`NOT_EXPOSED` typing is honest (no numbers, evidence retained) — recorded as
a labeling refinement in NEGATIVE_MATRIX_V1 NM-09 instead.

## Exact commands (all run in this session, this worktree)

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_workspace_lease.py tests/test_fabric_placement_policy.py
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_t3_environment_projection.py tests/test_team_roster_projection.py \
  tests/test_session_bridge_native_continuity.py tests/test_github_review_result_reader.py \
  tests/test_github_pr_lifecycle.py
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_fabric_stop_return.py tests/test_fabric_stop_subscriptions.py \
  tests/test_fabric_reject_outcome.py tests/test_hermes_primary_session_return.py \
  tests/test_mastermind_os_native_role_transport.py tests/test_t3_adapter_durability.py
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_provider_quota_observation.py tests/test_paid_fabric_capacity.py \
  tests/test_executive_host_capacity.py tests/test_provider_orchestrator_policy.py
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q tests/test_mmos_negative_matrix.py
cd app/mastermind_os && npm ci --no-audit --no-fund   # once (node_modules absent)
cd app/mastermind_os && npx vitest run src/auth-navigation-guard.test.ts
```

Results: batches 1–3 and the new file fully green (34, 129, 234, 6
respectively); batch 4: 198 passed + **1 pre-existing failure**
`tests/test_provider_quota_observation.py::test_producer_without_observations_path_is_byte_identical_to_before`
(golden drift, fails on the clean branch before any Director H edit; none of
my citations point at it). Vitest: 3 passed.

## Hand-offs to running directors (row → design; details in NEGATIVE_MATRIX_V1.md)

- **Director A3** (`control_plane/t3_execution_adapter.py` + `integrations/t3/**`):
  - NM-01 restart-before-ACK: two-connection race test (audit #1 BLOCKER) —
    exactly one gateway launch, loser replays winner's thread, ledger 1.
  - NM-02 restart-after-ACK: same race in the post-ACK window — replay, not
    second start; existing single-process tests already green.
  - NM-03 cursor: backwards-offset replay must refuse/no-op; cancel replay
    idempotent (audit #8).
  - NM-08 OAuth client/namespace: non-attesting port must fail CLOSED (audit
    inv2/#3); same logical_child_key under two clients never collides;
    typed re-auth label, never silent merge.
- **Director C** (`executive_runtime.py`, `worker_adapter.py`, #2329):
  - NM-07 admission-timeout: receipt lookup by triple, replay not duplicate
    Job; digest-conflict typed refusal; concurrent double-submit → one Job;
    after EFFECT_UNKNOWN no cross-account re-route (closes NM-09's remaining
    clause).
  - NM-14 duplicate/concurrent admissions: same design, atomic counters —
    replicate the proven `WorkspaceLeaseStore` barrier pattern.
  - NM-15 #2329: novel shell shape → structural refusal (no nearest-allowlist
    match); normalization-equivalence bypass refused; no runtime allowlist
    mutation path.
- **Lane A** (`control_plane/dsh_acp_runtime.py`):
  - NM-11 DSH envelope: 9th concurrent child at 8-active/depth-1 refused;
    depth-2 refused; child carrying its own envelope slots (counterfeit
    independent placement) ignored/refused — must match the proven
    placement-policy law.
- **Director D** (`app/mastermind_os/src/**/*.tsx`):
  - NM-16: stage renderer must show NOT_INTEGRATED/UNKNOWN as unknown — never
    green/installed vocabulary from a green check-run.
  - NM-19: mid-turn sign-out fence — queued previous-principal output dropped
    or labeled, never attributed to the new principal; storage-error fences.
  - NM-17 (TS half): profile switch A→B with in-flight turn — no A-session
    handle/memory/cached answer reachable from B.
- **B** (hermes-native TS mirror) + A3:
  - NM-06: add a distinct gateway-stopped state to the TS mirror and the
    adapter code table; python vocabulary + label test land with it (the
    strict xfail in `tests/test_mmos_negative_matrix.py` flips to XPASS-red
    until the test's label assertion is satisfied — remove the xfail then).
  - NM-10: update_paused typed label with zero reconnect/restart attempts
    (boundary lives in gateway/desktop, not this repo).

## Not done, and why

- No adversarial test for `update_paused` (NM-10): no in-repo mutation
  boundary exists (`update_paused` absent from the tree); design handed to
  A3/B. Recorded as GAP, unknown stays unknown.
- No source fix for the 429 label or the pre-existing golden drift: both are
  honest-but-imprecise, not safety failures; the golden belongs to another
  lane; the reason-code vocabulary is pinned by an existing assertion I will
  not weaken.
- Two delegated census leaves (glm-5.3-flash, deepseek-v4.1-flash via
  capacity_fabric) supplied read-only inventories only; every claim used here
  was re-verified by running the tests myself in this session.

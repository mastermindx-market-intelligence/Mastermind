# Integration worker historical return (source-pinned)

> This copy records the independent worker's observations against #1796's **older** 15-test candidate. Its two confirmed defects (symlinked ancestor and concurrent publication) have since been repaired in #1796, and coverage increased to 24 focused tests. A third fixed-run CLI identity check was added to the proposed integration patch. **Do not execute the historical source patch from the original Ubuntu1 scratch location**; use the currently retained, separately verified `review03_integration/review03-into-fabric_task.patch`. Still source-only, not installed.

---

# Review-03 reconciliation hook — source-only integration proposal

**Verdict: FIX_REQUIRED (pre-integration) + BLOCKED_OWNERSHIP (integration file).**
Source-only. No branch, push, PR, review, approval, merge, lease write, or
installed-state change was performed by this worker.

## Source of record

| Item | Value |
|---|---|
| Protected Mastermind master | `b6a6946ee35d61299caa7a9a884a168032367b65` |
| PR #1796 head | `2a11d585a85fe7e80b3eb0b5f7bafa967c669956` (verified, DRAFT, OPEN) |
| PR #1796 author | `mastermindxryan` |
| `native_watchlist_review03_reconcile.py` | sha256 `c85a9bdf368c8ca87e819c3e3ca7315e7655ea2a70a50acfbaf0db20da1e5fdc` |
| `fabric_task.py` @ protected master | sha256 `8f28799dc4f2d0b815fa467dab1dee5c5a9781d220199a5358be49773a74b686` |
| Integration patch | `integration/review03-into-fabric_task.patch`, sha256 `cc77e7d9af02f1c17b474529bd453f7ad21bf755d8a1e82a7d8bab822328a7bc` |
| Integration tests | `integration/tests/test_review03_integration_contract.py`, sha256 `65b50409b198552cbc9d3e4e61be534fa33f446069b42eee7af2a210e1e98304` |

## Findings

### F1 — The 15 hermetic tests do not exercise the qualification core (BLOCKING for "semantically valid")

`coverage run --branch` over the PR's own suite:

```
166 stmts, 55 missed, 18 branch, 65% coverage
Missing: 91-151, 220-226, 279-281, 306-325, 328
```

- **91–151 = `source_snapshot()`** — all 61 lines: the 8 pinned SHA-256 digests,
  request/launch/return/transport/continuation binding, the log effect-hold
  counters, ledger uniqueness, and the read-only broker lease check. **Never executed.**
- **220–226 = `observe_original_host()`** — the `ssh ubuntu1` observation. **Never executed.**
- **306–325 = `main()`** — the entire CLI, including `check`/`reconcile` and
  `--expected-proof-sha256` validation. **Never executed.**

Cause: the `original` fixture does `monkeypatch.setattr(r, "qualification", ...)`.
Every test that calls `reconcile_original()` or `status_from_receipt()` therefore
runs against a **fabricated** proof. The suite validates the receipt
write/read/tamper/idempotency shell, not the evidence reader. `15 passed` is
arithmetically correct and CI is green, but the green is shallow.

`test_no_provider_dispatch_or_lease_mutation_in_reconciliation_source` is a
substring grep over `Path(r.__file__).read_text()`. It asserts `"fabric_request"
not in source` and `"subprocess.Popen" not in source`, yet the module *does* call
`subprocess.run(["ssh", ...])`. It would not catch a provider dispatch expressed
differently. Weak negative test; should be replaced with an AST assertion on the
call graph.

### F2 — Directory-chain symlink is followed on both read and publish (FIX, in the #1796-owned file)

`read_owned` and the exclusive-create writer apply `O_NOFOLLOW` to the **final
path component only**. `receipt_path()` resolves through `HERE/"state"/"remote_sub"`.
Neither side validates the directory chain, so a symlinked `state/` or
`remote_sub/` is transparently followed for both receipt read and receipt write.

Proven, not theorised — `test_directory_component_symlink_is_not_rejected`
publishes a valid receipt *outside* the owner directory with no error raised.
This must be fixed before release; it is squarely in scope for
"race-free no-follow publish/readback". The PR's own symlink test only covers a
final-component symlink.

### F3 — Concurrent-publish race is reported as evidence failure (minor, FIX)

The incumbent precedent `native_host_review_controller_reconcile.py:225` catches
`FileExistsError` and re-reads, so two callers converge. The #1796 module lets
`FileExistsError` propagate; `main()` maps it to
`{"state":"REFUSED","reason":"original_review03_evidence_unqualified"}` rc=78. A
benign race is indistinguishable from disqualification. Adopt the precedent's
`except FileExistsError: saved = _read_sidecar()` shape.

### F4 — Tampered and absent receipts are indistinguishable (design note, not a blocker)

`_saved()` raises `NotQualified` on a forged receipt; `status_from_receipt()`
catches it and returns `None`. A forged receipt is therefore indistinguishable
from no receipt, and the integration correctly falls through to the original
`EFFECT_UNKNOWN` projection — the safe direction. Worth an explicit log line so
operators can distinguish "never reconciled" from "reconciliation receipt
rejected".

### F5 — `root_verified` is a self-asserted echo (house-wide; report, do not block)

`integrations/studio_direct_mcp/fabric-backend.mjs:294`:

```js
root_verified: s.root_id === args.root_id
```

It compares a returned value against caller input; it attests nothing
independently. Both the incumbent reconciler
(`native_host_review_controller_reconcile.py:189`) and #1796 return the module
`ROOT` constant, so #1796 is consistent with the incumbent pattern — this is not
a defect introduced by #1796. What actually binds `ROOT` to evidence is
`source_snapshot()`, which checks `obj.get("root_id") == ROOT` against the
original request/launch/return/continuation artifacts. That is F1's untested
path, which is why F1 matters. A caller that passes the literal root string is
"verified" trivially.

### F6 — Runtime evidence is absent on this carrier; the "live PASS" is unreproducible here

| Precondition | State on this host |
|---|---|
| `state/remote_sub/` for the run | **does not exist anywhere on the host** |
| Ledger row for `terminal-colw-pr1127-independent-review-03` | **0 rows in every ledger.jsonl on the host** |
| Broker lease `037d4f680550` in `/home/longr/lanes/ext/broker/leases.sqlite` | **row is `None`** (lease table has no such id) |
| Installed adapter status for the run | `state: NOT_FOUND`, not `EFFECT_UNKNOWN` |
| `ubuntu1` | not an SSH config alias; resolves as bare hostname |

Consequences:

1. The candidate MD's "Live read-only qualification against the original M2 +
   Ubuntu1 + broker: **PASS**, proof `6e22cfa3…`" is **not verifiable on this
   carrier** and no receipt or artifact evidencing it is present in PR #1796.
   Treat it as an unverifiable claim.
2. The module's evidence paths are relative to its own install location
   (`HERE/"state/remote_sub"`, `HERE/"broker/leases.sqlite"`,
   `HERE.parent/"orch/fabric/ledger.jsonl"`). **The committed layout does not
   match any real layout on this host** — the committed PR cannot be run in
   place. Deployment must establish that layout explicitly.
3. The installed adapter here (`/home/longr/lanes/ext/fabric_task.py`, 557 lines,
   dated Oct 9) is **494 lines behind** protected master (1051 lines) and lacks
   the `terminal_reconcile` / `completion_reconcile` /
   `native_review_reconcile` hooks entirely. There is no installed M2 target on
   this host that matches the integration seam.
4. Fail-safe direction: because the run is `NOT_FOUND` here, not
   `EFFECT_UNKNOWN`, the proposed guard would simply never fire on this carrier.
   Installing it here is a no-op, not a corruption.

## Integration patch (verified, not applied anywhere)

`integration/review03-into-fabric_task.patch` — 4 seams, +31/−0, modelled exactly
on the incumbent `native_review_reconcile` pattern:

1. `import native_watchlist_review03_reconcile as original_review_reconcile`
2. In `inspect_run`, an `EFFECT_UNKNOWN`-scoped fixed-run guard placed **after**
   the three existing reconcilers and **before** the acceptance projection:
   ```python
   if state == "EFFECT_UNKNOWN" and rid == original_review_reconcile.RUN:
       verified = original_review_reconcile.status_from_receipt()
       if verified is not None:
           return verified
   ```
3. CLI subcommand `reconcile-original-review03 <run_id> --root R
   [--action check|reconcile] [--expected-proof-sha256 HEX]`
4. Dispatch: read-only `check` by default (calls `qualification()`); `reconcile`
   requires a `[0-9a-f]{64}` proof digest and returns the projection.

`status: TERMINAL_FAILURE` is already in the adapter's allowed state tuple
(`fabric_task.py:740`). No new control plane, no lease mutation, no generic
reset. The `check` path calls `qualification()` directly rather than
`main()` — `main()` already prints, and `_json(main(...))` would double-print.

Verified:

- `git apply --check` → OK; `git apply` → OK against protected master.
- `py_compile` → OK.
- PR #1796's 15 tests + 15 integration contract tests → **30 passed**.
- Negative control: same suite against **unpatched** protected-master
  `fabric_task.py` → 2 expected failures
  (`test_guard_is_present_and_scoped_to_the_single_original_run`,
  `test_cli_branch_is_present_and_gated`). The wiring tests are not vacuous.

## Ownership blocker

The integration patch modifies `ops/native_fabric/quota_continuity/source/fabric_task.py`.

PR #1796 itself is file-disjoint (it adds three new files). **But the integration
is not**: PR #1648 (DRAFT, OPEN, head `43ca6b388fb0c0b450fa4480c6a2a13a9591f56b`)
owns exactly that file with a live `+3/−1` edit plus
`tests/test_fabric_remote_cwd_default_20261020.py`.

Two open DRAFT PRs must not both edit `fabric_task.py`. No source-custody
reconciliation with the #1648 owner was available to this worker, so **the patch
was deliberately not applied, branched, or pushed anywhere.**

`integration/tests/test_review03_integration_contract.py` is a **new filename** in
a shared directory — it adds no conflict with either PR, but it should land in
whichever PR carries the integration.

## Release requirements not met by PR #1796

- Qualification core untested (F1) — needs fixture-backed tests for
  `source_snapshot()`, `observe_original_host()`, and `main()`.
- Directory-chain no-follow (F2) — must be fixed in the #1796-owned module.
- Race convergence (F3) — match the incumbent precedent.
- CI is green (pytest 3 shards, Analyze, CodeQL all pass) but the shard runs do
  not exercise the untested paths.
- Independent review and sealed-publisher installation remain outstanding.
- Terminal PR #1127 stays DRAFT/HOLD; a new non-Qwen reviewer may only be
  commissioned after the installed facade returns a root-verified terminal
  failure for the exact -03 run **and** that receipt is read back.

## Exact next lawful action

1. **PR #1796 owner** (`mastermindxryan`): fix F2 (directory-chain no-follow),
   F3 (FileExistsError convergence), and add fixture-backed tests covering
   `source_snapshot`, `observe_original_host`, `main` — closing the 65% coverage
   gap on lines 91–151 / 220–226 / 306–325. Replace the substring-grep negative
   test with an AST call-graph assertion.
2. **#1648 owner + native Fabric source owner**: reconcile custody of
   `source/fabric_task.py`, land #1648 (or rebase it onto the integration), then
   apply `integration/review03-into-fabric_task.patch` and add
   `integration/tests/test_review03_integration_contract.py` in the same PR.
3. Run: `pytest -q ops/native_fabric/quota_continuity/tests/` → expect 30 passed.
4. Only after that, via the sealed native publisher and the installed M2 owner:
   `fabric_task.py reconcile-original-review03 <RUN> --root <ROOT> --action check`,
   echo the proof digest into `--action reconcile`, then read back
   `fabric_status` and confirm `state=TERMINAL_FAILURE`,
   `acceptance_state=UNVERIFIED`, `retry_allowed=false`.

## Not claimed

**review-03 is NOT reconciled.** No canonical Fabric status was obtained. The
installed adapter on this carrier returns `NOT_FOUND`; the ledger has no row for
the run; the broker has no such lease. No root-qualified terminal evidence exists
here, so no reconciliation may be asserted.
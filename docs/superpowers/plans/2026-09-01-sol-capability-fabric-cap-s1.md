# Sol Capability Fabric — CAP-S1 Implementation Record

**Date started:** 2026-09-02
**Owner:** Sol, AI CEO — implementation by the bound receiver
**Operation:** `mastermind-cap-s1-complete-vertical-20260901-sol-001`
**Receiver:** `claude-fable-5 / sol-control-room-handoff-cap-s1-0f4208` (Chairman-placed; Sol reconciliation PR #325 comment 5503701467)
**Carrier:** Mastermind PR #350 / `fable/cap-s1-complete-vertical-20260901` (sole nonterminal CAP-S1 carrier)
**Pickup base:** protected master `821e90f8f0f01dd1ed7bf11a6c548a5f410c2a32` (ACK1 merge); history-preserving join of `9ed1a202` at `c78da361`
**Governing law:** protected convergence index + ordered amendments; Sol seam map (#350 comment 5505314616); reviews 5085454178 + 5086177855; clarification 5505160491
**State:** `IN PROGRESS — phases 1-12 of 15 complete; phase 13 (one real canary) next`

This is the implementation plan/proof ledger required by convergence-index §5. It grants no authority,
arms nothing, and is superseded on any conflict by the protected specs it cites.

---

## 1. Phase ledger (commit heads on the carrier branch)

| Phase | Content | RED head | GREEN head |
|---|---|---|---|
| 1 | SCOPE_MAP / pickup / START (#317 c5503682503, #325 c5503766100) | — | — |
| 2-3 | `executive_capability_packages.py` + hostile suite | — | `bc69f8fb` / `2a64da0e` |
| repair r1 | review 5085454178 (five findings) | `4bfc36ad` | `12c4c5cc` |
| repair r2 | clarification 5505160491 / review 5086177855 | `4697b585` | `206ceaa1` |
| base join | merge of protected `9ed1a202` (no rebase/reset/force) | — | `c78da361` |
| 4-5 | V4 registry + exact fixture + V3 pins | — | `0c0618ec` / `b8d6630e` / `2f452e63` |
| 6-7 | exactly-one comparator (function-scope diff proof) | `ddd295bd` | `073cfee5` |
| 8+10 | strict skills parser + row-faithful fake server | `7a734d81` | `306b4191` |
| 9 | attempt-local projection + ephemeral archive origin | `627208b8` | `e63dc89b` |
| adapter | binding-gated causal launch + closed skill envelope | `73989279` | `f4eaf1ea` |
| 11 | canary runner, schema attestation, four-turn journey | `ac7835f5` | `961bb163` |
| config gate | observed `skills.bundled` + re-armed REFUSE_CONFIG_DRIFT | `8182bd6d` | `557d59d5` |
| 12 | ceilings/stop-code coverage + live CLI wiring + this record | — | `4d4298a3` + this commit |
| 13 | exactly one real read-only Codex canary | — | _pending_ |
| 14 | exact-head hosted CI + independent adversarial review | — | _pending_ |
| 15 | current-base expected-head source-only release | — | _pending_ |

## 2. Frozen identities (verified against protected bytes; three-way reconciled with Sol's #350 c5505333173)

```text
package                mastermind-operator.p1 @ 12c2cb8993f78e81c6cb9e9a75a9829f9b194dab
package tree           783ae81b44e9606baf13e2402a75a2130df9758a
content digest         a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306
package_source_digest  16a19d7399b8ff737b59c959cffbc9bedabee7a5fe0d6f05ced8172fd9870852
generation digest      37836a5986c916a58217b95d1976220eae8827e4e588a50677011c2543e43b97
closures               escalate ca621a8c… / finish 3e689aea… / receive d7953504… / return 510be1ed…
V3 pins (unchanged)    policy 0d025d2728c7… / docs-mcp-helper profile 028fce73ff8c…
no-bundled projection  16f3a01790a8… (pre/post-change byte-identity pin)
```

## 3. Phase-12 gate evidence (2026-09-02)

- Focused suites at `4d4298a3`: packages+canary 186 passed / 1 licensed skip (AF_UNIX sun_path in
  tmpdir); adapter 56; contract 58; protocol fidelity 35; registry V3+V4 27+47 — all green.
- Full feasible local gate (`scripts/ci_pytest.py`): 457 discovered; 16 collection errors, ALL
  `ModuleNotFoundError: lib` from the uninitialized `vendor/macro` submodule in this worktree
  (business/loop/research files disjoint from CAP-S1). Authoritative full gate = hosted exact-head
  CI, green on every pushed head to date. Local wrapper exits 0 despite the collection interruption —
  flagged for Sol as an observation, out of CAP-S1 scope.
- Whitespace gate (`git diff --check origin/master...HEAD`): clean. Secret grep over the branch
  delta: clean.
- Mutation gate (remove each load-bearing repair in turn; tree restored clean after each):
  comparator exactly-one → 2 discriminating tests fail; round-2 hardening → 4 fail; round-1 repair
  → 2 fail; V4 registry → suite collection error; adapter seam → suite collection error; observed
  bundled projection → drift falsifier fails; surgical `fullmatch→match` → 8 fail. ALL GUARDS BITE.
- Ceiling/stop-code gaps closed with per-test bite proofs (`4d4298a3`), including the discovery that
  both census ceilings are defense-in-depth double-enforced (declared-shape gate + in-walk check).

## 4. Review/repair record

- Review 5085454178 (CHANGES_REQUESTED @ 2a64da0e): terminal-newline token leakage; directory-blind
  census; verifier trusting hand-built generations; census-to-open FIFO block; unbounded provenance
  grammar. Repaired r1. ACK #350 c5504860932; RETURN c5505509121.
- Clarification 5505160491 + review 5086177855 (@ 12c4c5cc): exact-type boundary (dataclass `__eq__`
  subclass spoof), streaming budget-stopped census, census-to-open identity binding, mid-read growth
  bound, surrogate/TypeError hygiene. Repaired r2; wrong-type inputs refuse
  `untrusted_generation_refused`.
- Self-found (phase 11 packet deviation escalated by the receiver): observed-side security-config
  projection lacked `skills.bundled`, structurally disarming the V4 canary's REFUSE_CONFIG_DRIFT
  gate; repaired at `557d59d5` (conditional-on-presence projection; absent key byte-identical —
  pinned). Whether the real binary echoes the overridden `skills.bundled` table is phase-13 evidence;
  a non-echo yields an honest CONFIG_DRIFT refusal for Sol to adjudicate — no live special-casing.

## 5. Realm facts (phase-13 preflight)

```text
binary        /opt/homebrew/bin/codex  (codex-cli 0.147.0; generate-json-schema supported)
codex home    /Users/chriswong/.codex-ohf-p0  (dedicated, independently authenticated, non-default,
              user-owned OHF laboratory probe realm; root-only codex-pro realms untouched)
invocation    python3 -m scripts.ohf.cap_s1_mastermind_operator_canary --backend live
              --binary-path /opt/homebrew/bin/codex --codex-home /Users/chriswong/.codex-ohf-p0
              --scratch <fresh tmp> --operation-id mastermind-cap-s1-complete-vertical-20260901-sol-001
law           exactly one attempt; timeout/uncertainty = EFFECT_UNKNOWN, reconcile same identity,
              never blind-retry, never fail over to another account/realm
```

## 6. Capability honesty (current)

```text
package/registry/comparator/adapter/projection/runner source   BUILT_NOT_PROVEN / PRODUCTION_INERT
checked-in default policy                                      V3, byte-identical (pinned digests)
Codex profile/route/host receipt/production                    NONE armed; CAP-PROMOTE1 separate
real provider proof                                            NOT YET (phase 13)
```

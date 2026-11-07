# experiential_picker — manual-only Experiential Labs native picker route

Child `explabs-manual-20261103-picker01` under root `explabs-manual-20261103-root`.
Source pin: protected master `703060ee2640d2014304f658df80bab15fd2ab4a`
(mastermindx-market-intelligence/Mastermind), Skillpack `mastermind.sol_skillpack.v1`
1.0.1. Sibling children: incumbent picker PR #2029 (head `085026d9…`, owns only
`ops/native_fabric/grok47/qualify_cursor46_current.py` +
`test_cursor46_manual_pin.py` — untouched here), native transport child
`explabs-manual-20261103-transport01` (owns `ops/native_fabric/experiential53/` —
untouched here), Web #2032, native scaffold #2031.

## What this child delivers

A sealed, additive, **single-file** (`ext/pick.py`) current-generation overlay
that admits exactly one manual-only route — `pool=experiential` with the exact,
case-sensitive `model=glm-5.3-uncensored` — and nothing else:

- **Manual-only identity.** The pool refuses any other spelling (`GLM-5.3-Uncensored`,
  whitespace, `glm-5.3`, `glm-5.3-flash`, Z.AI slugs), refuses pool selection
  without the exact pin, refuses the model pin on any other pool, and refuses
  judgment classes (`review`, `audit`, `verify`, architecture) and any\n  task class outside `mechanical` and `fix_build`. No default model emission for the pool.
- **Owner-verified witnesses, fail closed.** Admission requires
  `orch/fabric/experiential_witnesses.json` (beside `pools.yaml`, under the
  existing root-bound `orch` binding) carrying `schema`
  `mastermind.experiential.manual_route_witnesses.v1` with
  `entitlement_verified_by_owner`, `local_gateway_healthy`, `transport_admitted`,
  `cap_authenticated`, `provider_retains_data_disclosed`, `platform_funded_only`,
  all four consents (`retention_opt_in`, `sensitive_data_opt_in`,
  `proprietary_code_opt_in`, `code_exposure_opt_in` — the Web #2032 flags), and a
  bounded TTL. The file is re-read with a nofollow bounded read on **every**
  preview/emission/launch decision, so a `request --strict-manual-pin` recheck
  observes fresh state. Caller flags can never assert the owner fields; a
  symlinked, stale, malformed, partial or unknown witness document fails closed
  before any worker launch.
- **AUTO unchanged / no pool promotion.** `policy_allows` refuses
  `experiential` unless the exact pin is present, and both AUTO scoring loops
  skip the pool outright — even adversarially when routing config lists it or
  the pool is registered. Test-proven byte-identical AUTO output versus the
  sealed baseline.
- **No substitution.** When the route is unavailable the picker returns
  `NONE reason=…`; it never falls back to `glm-5.3-flash`, any Z.AI glm model,
  or any other pool.
- **Distinct provider slug.** The route emits `POOL=experiential` and reaches
  the economic guard as mode `experiential` (never `glm`/`glm-codex`); mode
  `experiential` is **removed** from the `outside_economic_guard_scope` bypass:
  it admits only the exact pinned model with fresh witnesses.
- **Strict subject role (R33).** `pool_family("experiential")` folds to
  `glm` for reviewer-independence only, so the uncensored GLM derivative can
  never review GLM-authored work, while `canonical_pool` stays a distinct slug.
- **All existing gates stay binding.** Pool registration policy, R32 capability,
  R33 subject, R22 quality floor, quota/hard filter and the economic guard run
  unchanged after the identity/witness intercept; owner pool registration in
  `pools.yaml` is still required (absent registration keeps the route closed).

## Files

| File | Purpose |
|---|---|
| `experiential_manual_route.py` | Sealed exact-once hunks (9) over the incumbent picker, seal tables, witness contract, pure transform. |
| `qualify_experiential_current.py` | Qualification runner: snapshot-seal + manifest integrity, sealed-preimage gate, single-file delta proof, scratch fake-owner publish/select/CAS via the incumbent `native_generation.py` publisher, optional `--installed-store` dynamic discovery, optional `--compose-overlay`, optional `--witness-draft` lint, optional `--release-stage`. |
| `test_experiential_manual_pin.py` | 31 hermetic offline tests (no provider, key, spend, network, or hidden skips). |
| `README.md` | This file. |

## Seals

- Sealed predecessors (generation → `ext/pick.py` preimage), as recorded by the
  reviewed incumbent qualification: `9eec6f73…` → `4311200a…`,
  `8cefc4b2…` → `747a55a5…`. The in-repo
  `ops/native_fabric/quota_continuity/candidate/pick.py` **is** the sealed
  current-generation (`8cefc4b2…`) picker preimage — byte-verified.
- Snapshot seals: candidate `747a55a5…`, source `0f5cbc32…` (equal to
  `quota_continuity/rollout/native-preimages.json` `pick.py`), grok47 overlay
  `02afff09…`. `source/fabric_task.py` (`8f28799d…`) and `source/model_tier.py`
  (`507a8aa6…`) are likewise manifest-sealed. Historical pinned files are read
  only; nothing outside `ops/native_fabric/experiential_picker/` is modified.

## Verification (normal workflow, no hidden CI skip)

```
python3 -m pytest ops/native_fabric/experiential_picker/test_experiential_manual_pin.py -q
python3 ops/native_fabric/experiential_picker/qualify_experiential_current.py
```

Qualification (source-only) result facts: `state=QUALIFIED_SOURCE_ONLY_NOT_INSTALLED`,
`changed_files=["ext/pick.py"]`, installed predecessor `8cefc4b2…`,
candidate pick sha256 `5de4a92b8327c53407ccffb723cb00cba0d23743d814a6e7c0754be50117daf9`,
scratch closure manifest sha256 `72299a9d6707ec205e98ceca9439c8ea3e08fbbae847b71d15d5ce9031141d46`,
scratch previous/verify/CAS-select PASS, stale-CAS refusal PASS,
witness gate `FAIL_CLOSED_BEFORE_ANY_WORKER_LAUNCH`.

## Exact dry-run / installed limitation

- The installed native store and the gen27 `ext/fabric_task.py` / `pool` CLI
  files live on the Fabric host; the host read capability was unavailable in
  this environment (fleet status `FLEET_STATUS_FABRIC_UNAVAILABLE`; the local
  `/home/ubuntu3/lanes` kit is a stale Oct 9-13 snapshot with no generation
  store and no `experiential` pool). Per commission, qualification therefore
  gates against the explicit sealed preimages with **dynamic installed-store
  discovery preserved**: re-running with `--installed-store <native-code-releases>`
  binds the discovered generation read-only and refuses any unknown generation
  (`installed_native_predecessor_changed`).
- The `preview`/`request` CLI JSON contract lives in the host generation's
  `fabric_task.py`/`pool` (added by the reviewed 20261022 manual-preview patch;
  inputs are not reconstructible from the repo). This child qualifies the
  picker admission layer those CLIs consult; preview with the pin returns the
  no-reservation strict-recheck result only when fresh owner witnesses exist
  and otherwise fails closed before reservation. CLI-level verification is a
  native owner action below.

## Native / runtime owner integration actions

1. **Native generation owner**: run `qualify_experiential_current.py
   --installed-store <native-code-releases>` on the host (read-only), then take
   the single-file `ext/pick.py` candidate through the existing reviewed
   publication path (review-stage builder + CAS publisher). Protected merge
   with independent review; never self-merge, self-review or install here.
2. **Pool owner**: register `experiential` in `orch/fabric/pools.yaml`
   (role, task_classes, `default_model: glm-5.3-uncensored`, caps). Until then
   the route stays fail-closed even with witnesses.
3. **Native request owner**: consume/recheck the four consent flags forwarded
   by Web #2032 (`--experiential-retention-acknowledged`,
   `--experiential-sensitive-data-opt-in`, `--experiential-proprietary-code`,
   `--experiential-code-exposure-opt-in`) in `request --help`/argparse, and
   write/update the owner witness file only after owner verification of
   entitlement, local gateway health, transport admission and an authenticated
   account cap. Account A's original 403 hold and Account B's unauthenticated
   cap stand; no denied key-cap readback is replayed or rerouted. No provider
   key use and no paid model calls happen in this child.
4. **Transport/gateway owner** (`explabs-manual-20261103-transport01`,
   #1849/#1934/#1945): admitted transportation remains a precondition; no
   worker START before the original native transportation and gateway are
   admitted.
5. **Composition with the incumbent picker PR #2029**: both transforms are
   single-file `ext/pick.py` deltas with disjoint anchors and both orders
   compose (mechanism tested; run `qualify_experiential_current.py
   --compose-overlay ops/native_fabric/grok47/qualify_cursor46_current.py`
   once both are on master to prove it against the merged partner).

## Boundaries kept

No new publication, quota, model, registry, router or ledger authority. No
installed-release change, no automatic-routing change, no pool promotion, no
provider key use, no paid calls, no caller-assertable entitlement, no edits to
#2029/#2031/#2032/#1849/#1934/#1945/#1920/#1918/#1946 files or the
`experiential53` workspace, no hidden CI skip, no manifest relaxation.

## Observed installed Linux picker compatibility

The original sealed current-generation picker fixture `747a55a5…` is no
longer the source installed on Ubuntu0/Ubuntu3. The exact installed preimage
there is `bab2bcc1d71d7b8b2a7d5b78247326d5057815c6ed063143c451990b577e13d8`.
A dedicated source-only forward-port
`qualify_linux_installed_picker.py` handles that one precise generation,
retaining the existing GLM provider and legacy routing semantics while
restricting the Experiential model to the exact manual pin and owner witnesses.
This is **not** permission to publish to the installed kit, modify
`pools.yaml`, or start workers. Unknown generations (including Ubuntu1's
different picker) refuse before output. A sealed source-only fixture under
`fixtures/` permits offline CI and the 15 new deterministic tests in
`test_qualify_linux_installed_picker.py`. Repeated real-host qualification
produced `postimage_sha256=414e4fc73e865480ea19a52ea96207c400eb9b599fbece28a7063d6de30dfa30`
without changing installed bytes. Native publication and owner-authenticated
entitlement/cap/transport remain separate exact gates.

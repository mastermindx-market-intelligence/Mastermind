# Mastermind identity gate: exact committed repair review

## Decision

**PASS for the bounded identity repair at commit `24ae789308bf5b9c417b1f8bd5c7e74938b11a7e`.** The unchanged D8 classifier returns zero findings for the actual committed source changes from the original source base. All 45 relocated verification files retain every byte from the failing source head. The only production change replaces the explicit HTTPS port literal with Python's standard `HTTPS_PORT` constant, preserving URL validation behavior.

This independent review made no repository changes. Root owns the source commit, actual pytest gate, native/API tests, browser verification, publication and Draft HOLD status. The committed-tree classifier result is separate from those acceptance results.

## Exact binding and failure

| Item | Exact value |
|---|---|
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Failed run / job | `37863107904` / `113603641782` |
| Failing source head | `55198ba62ff47d2a371397567418cb43fd98892c` |
| Original source base | `c7e47c859eb2925c5626931fd511800773ba09ac` |
| Reviewed repair commit | `24ae789308bf5b9c417b1f8bd5c7e74938b11a7e` |
| Failed assertion | `tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults`, line 1980 |

The exact-head scanner reproduced the CI failure's **58 findings** against the original source base: `443` once, `_mastermind_ui` 51 times and `_mastermind_static_assets` six times. Attribution therefore does not depend on stale local `origin/master` or an inferred upstream base. The scoped CI excerpt and per-file reproduction are retained in `exact_ci_context.raw.json`, `exact_original_scan.raw.json` and `per_file_findings.json`.

| Origin | Findings | Explanation |
|---|---:|---|
| Production URL validator | 1 | The line containing `parts.port` puts literal 443 in the scanner's topology context. |
| Eleven verification JSON files | 53 | Recorded harness filenames, browser diagnostics, source inventories and archival paths contain the reserved spelling. |
| Two historical patch files | 3 | Original file headers contain the verification filenames. |
| Live browser verifier | 1 | Its missing-argument help text names `README_mastermind_ui.md`. |
| Total | **58** | All findings reproduced at the exact source head. |

These verification findings describe files and recorded diagnostics, rather than new operating-system identities or account allocations. The scanner intentionally treats the reserved spelling strictly.

## Ownership and preservation

The unchanged test already selects changed source paths with `:!tests/` at line 1953. The existing `tests/fixtures/` owner contains probe harnesses, fixture applications and historical patches, including `mastermind_os_launch_cross_layer_probe.py`, `ohf_raw_app_server.py` and `mastermind_os_v3_recovery_compat.patch`. The relocated auction files serve the same bounded verification role.

Root moved all non-Markdown files in these source locations to identical relative tails under `tests/fixtures/sovereign_auction_context/`:

- `research/sovereign_auction_context/verification/**`
- `research/sovereign_auction_context/presentation_final/**`
- `research/sovereign_auction_context/VERIFIED_SOURCE_MANIFEST.json`

**Independent postimage verification confirms 45 moves, 2,107,800 preserved bytes, identical old/new Git blobs, and absence of all 45 old paths.** Every original receipt, preimage record, screenshot and patch in this set retains its content. `relocation_plan.json` supplies every old/new path, byte count, SHA256 and exact source Git blob.

Architecture and explanatory Markdown stay in research. In particular, the existing layout repair report, browser README and security candidate README remain there. Root added `EVIDENCE_LOCATION.md`, a fixture-owned relocation receipt and an additional immutable copy of the source-head manifest. Embedded old paths in historical records retain their historical meaning.

The full applicable root `AGENTS.md` and `CLAUDE.md` were read. No additional test/fixture/research-evidence directory instructions were found in the inspected parent paths. The laws permit explicitly assigned engineering source/test maintenance, require preservation of authority and evidence boundaries, and require the stated acceptance evidence. They do not mandate a bespoke directory for this auction's receipts. The relocation is a scoped ownership correction under the current assignment and existing test ownership; it does not create a new rule or override higher authority.

Routing the JSON alone into `research/evidence/` would not preserve the existing contract: the historical PREIMAGES record is an array while that classifier requires an object, and browser geometry beneath `groups` is interpreted as identity context. No schema conversion, historical-content rewrite, extension masking, token encoding, scanner waiver or registry change was used.

## Production behavior and exact hashes

The production reader stays at `brain/sovereign_auction_context.py`, inside the source scan. Its complete committed delta is:

```python
from http.client import HTTPS_PORT
# Existing validation expression:
parts.port in (None, HTTPS_PORT)
```

The runtime standard-library constant equals 443. The actual old and new URL validator functions produced identical outcomes on 23 cases: ordinary HTTPS and explicit :443, wrong ports, malformed ports and hosts, userinfo, whitespace/control characters and invalid text types. The check made zero network requests. See `url_equivalence.json`.

| Reader state | Bytes | SHA256 |
|---|---:|---|
| Exact failing head 55198 | 22,613 | `7e9930bc77c1aafed2d8a3406e57af3558822c29cdb60c49d327c5685c6aac8e` |
| Exact repair commit 24ae789 | 22,655 | `1b2c11d38628b13f8ba5439f90f8ef9eefabf564cea5c3ed517398b1a4b5f276` |

The initial plan captured the working reader after root had already applied the constant change. Its corrected `brain_preimage` and separate `brain_postimage` now distinguish these revisions. The original capture is retained as a raw intermediate; all 45 move preimages were exact-head verified from the outset.

The D8 scanner, identity review helper, control template, root laws and `config/contracts.yml` are byte-identical between 55198 and 24ae789. Scanner SHA256 is `211137a1f9c39d1fbe02e431f56044b9847d196bb9bcd85e9ff4aa95155813b3`.

## Verification and remaining integration detail

`committed_postimage_review.json` records the exact 24ae789 classifier result: **0 findings**, with the production reader and other production changes still scanned. The complete diff has the 45 exact renames, the narrow reader edit and the three explanatory/history additions listed above.

The live browser runner locates the Python helper with `__dirname`; the static-assets test imports its sibling helper. The harness receives explicit Mastermind and Macro roots. Keeping the verification subtree together preserves those dependencies. The retained browser README's run example still demonstrates an optional copy into `/tmp/sovereign-auction-ui-tools/`; current documentation may point directly to the new fixture location or explain the copy source. Historical receipts and patch headers should continue to describe their recorded runs.

Root is running the actual D8 pytest gate, native auction/static tests, renderer test and full 48-case browser matrix against the repair. This review is bound to 24ae789; later metadata/documentation commits need their own final-head binding. No full CI, merge or deployment clearance is asserted here.


# MAS-120 / PR #124 — scope disposition and qualified carve-out (2026-10-13)

Workstream: `WS:GLOBAL-LIQUIDITY-TRANSMISSION` (macro Agent OS), task T02 of W-LIQ.7.
Machine-readable companion: `MAS120_PR124_SCOPE_DISPOSITION_2026-10-13.json`
(schema `mas120_pr124_scope_disposition.v1`, one row per path, 1,239 rows).

## 1. Finding

PR #124 (`codex/mas120-wliq3-20260822`, head `23f97360131d`) shows **1,239 changed paths**.
That is the diff against its **stale original base** `db0bac5fe3f7` (2026-08-22, #116).
Merge commit `e9310c71cb15` pulled master `8de062fb3b5a` (2026-09-15, #667) into the branch.

- **1,220 paths are master's own changes.** Every one has PR-head bytes equal to `8de062fb3`.
  All 1,220 are already on `origin/master`. None was authored by the W-LIQ.3 work.
- **The owned delta is exactly 19 GLT paths.** That is `brain/liquidity_lab/*` and its tests,
  fixture, and research notes, measured against the true merge-base `8de062fb3`.
- **Merging the PR tree wholesale would be destructive.** 304 of the 1,220 master-carried paths
  changed on master after `8de062fb3`. A blind merge or replay of the old tree would revert them
  (tests 111, control_plane 52, integrations 37, ops 31, docs 28, scripts 17, plugins 8, config 5,
  root 3, common 3, requirements 3, app 2, research 2, .agents 1, .github 1).

The qualified candidate therefore carries only the 19 in-scope paths. They land as three NEW
commits on fresh `origin/master` `28e3c692b3d9`, one per source commit. Each names its
`Source-Commit:` and keeps the original `Co-authored-by:` trailer. The candidate does not merge,
reset, force-push or replay anything, and it changes no permission or setting.

| Carve commit | Source commit | Author of source | Paths |
|---|---|---|---:|
| `b32cf1f17` | `7bd6dbbc8d93` feat(liquidity): build W-LIQ.3 quant foundation | Chris Wong, 2026-08-22 | 13 |
| `560294282` | `e9310c71cb15` fix(liquidity): bind repaired producer and trusted episode history | chriswong6031-creator, 2026-09-15 | 9 |
| `348ef2fef` | `23f97360131d` fix(liquidity): reject contradictory same-clock research observations | chriswong6031-creator | 3 |

`git diff refs/glt/pr124 HEAD -- <the 19 paths>` is empty: the carved bytes are identical to the PR head.

## 2. Category rules (first match wins)

| Category | Rule |
|---|---|
| `glt_in_scope` | the 19 paths in §4 (the GLT-owned delta vs the true merge-base) |
| `control_plane_or_settings` | `control_plane/ ops/ config/ .github/ .codex/ .claude/ .agents/ .superpowers/ plugins/ requirements/`, root `AGENTS.md CLAUDE.md pyproject.toml` |
| `excluded_programme` | `integrations/ scripts/ corpus/ app/ brain/ common/ portfolio/ experiments/` (other programmes' code) |
| `docs_or_research_out_of_scope` | `docs/ research/ review_evidence/` |
| `test_out_of_scope` | `tests/` |

Census command: `git diff --name-status db0bac5fe 23f97360131d05123acc440da15780b0bb200e82`.
It returns 1,096 A, 142 M and 1 D; the only deletion is `.github/PULL_REQUEST_TEMPLATE.md`.
The sha256 of the sorted path list, newline-joined with no trailing newline, is
`486b0de58e2d06775c421d747d1fae8238faa660e596dda764c188457e5c5d45`.

## 3. Reconciliation

The six top levels named by the commission reconcile exactly:

| control_plane | integrations | docs | tests | scripts | research | other | total |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 94 | 117 | 247 | 416 | 77 | 81 | 207 | **1,239** |

Top level × category:

| top level | total | glt_in_scope | excluded_programme | control_plane_or_settings | docs_or_research_out_of_scope | test_out_of_scope |
|---|---:|---:|---:|---:|---:|---:|
| `tests` | 416 | 8 |  |  |  | 408 |
| `docs` | 247 |  |  |  | 247 |  |
| `integrations` | 117 |  | 117 |  |  |  |
| `control_plane` | 94 |  |  | 94 |  |  |
| `research` | 81 | 4 |  |  | 77 |  |
| `scripts` | 77 |  | 77 |  |  |  |
| `ops` | 53 |  |  | 53 |  |  |
| `review_evidence` | 38 |  |  |  | 38 |  |
| `corpus` | 31 |  | 31 |  |  |  |
| `plugins` | 22 |  |  | 22 |  |  |
| `config` | 12 |  |  | 12 |  |  |
| `brain` | 9 | 7 | 2 |  |  |  |
| `.codex` | 7 |  |  | 7 |  |  |
| `app` | 7 |  | 7 |  |  |  |
| `common` | 6 |  | 6 |  |  |  |
| `requirements` | 6 |  |  | 6 |  |  |
| `.github` | 5 |  |  | 5 |  |  |
| `.superpowers` | 4 |  |  | 4 |  |  |
| `(root)` | 3 |  |  | 3 |  |  |
| `.agents` | 1 |  |  | 1 |  |  |
| `.claude` | 1 |  |  | 1 |  |  |
| `experiments` | 1 |  | 1 |  |  |  |
| `portfolio` | 1 |  | 1 |  |  |  |
| **total** | **1239** | **19** | **242** | **208** | **362** | **408** |

## 4. The 19 GLT in-scope paths

None of these paths existed on `origin/master` before the carve.

| path | source commit(s) | on origin/master before carve |
|---|---|---|
| `brain/liquidity_lab/__init__.py` | `7bd6dbbc8d93` | no |
| `brain/liquidity_lab/adapter.py` | `e9310c71cb15` | no |
| `brain/liquidity_lab/contracts.py` | `7bd6dbbc8d93`, `e9310c71cb15` | no |
| `brain/liquidity_lab/estimator.py` | `7bd6dbbc8d93` | no |
| `brain/liquidity_lab/eventization.py` | `7bd6dbbc8d93`, `e9310c71cb15`, `23f97360131d` | no |
| `brain/liquidity_lab/ledger.py` | `7bd6dbbc8d93` | no |
| `brain/liquidity_lab/validation.py` | `7bd6dbbc8d93` | no |
| `research/liquidity_transmission/W_LIQ_3_ADAPTER_PLAN_2026-09-15.md` | `e9310c71cb15` | no |
| `research/liquidity_transmission/W_LIQ_3_ADAPTER_RECOVERY_2026-09-15.md` | `e9310c71cb15`, `23f97360131d` | no |
| `research/liquidity_transmission/W_LIQ_3_FOUNDATION_SPEC_2026-08-22.md` | `7bd6dbbc8d93` | no |
| `research/liquidity_transmission/btc_china_protocol.v1.json` | `7bd6dbbc8d93` | no |
| `tests/fixtures/liquidity_lab/README.md` | `e9310c71cb15` | no |
| `tests/fixtures/liquidity_lab/glt_producer_20260904.json` | `e9310c71cb15` | no |
| `tests/test_liquidity_lab_adapter.py` | `e9310c71cb15` | no |
| `tests/test_liquidity_lab_contracts.py` | `7bd6dbbc8d93` | no |
| `tests/test_liquidity_lab_estimator.py` | `7bd6dbbc8d93` | no |
| `tests/test_liquidity_lab_eventization.py` | `7bd6dbbc8d93`, `e9310c71cb15`, `23f97360131d` | no |
| `tests/test_liquidity_lab_ledgers.py` | `7bd6dbbc8d93` | no |
| `tests/test_liquidity_lab_validation.py` | `7bd6dbbc8d93` | no |

## 5. Scope-validation discriminator

The same scope check (any path outside the 19 = FAIL) is applied to the candidate and to two controls:

| Diff | Paths | Outside GLT scope | Control-plane/settings | Verdict |
|---|---:|---:|---:|---|
| candidate `origin/master..HEAD` | 19 | 0 | 0 | **PASS** |
| control: #124 vs stale base `db0bac5fe..23f97360` | 1,239 | 1,220 | 208 | FAIL |
| control: wholesale old tree `origin/master..23f97360` | 1,922 | 1,903 | 271 | FAIL |

The check rejects both broad shapes, so a PASS on the candidate actually discriminates.

Reproduce:

```
git fetch origin pull/124/head:refs/glt/pr124
git merge-base origin/master refs/glt/pr124          # 8de062fb3b5a327466cd98cda0dc7d44b8fd229d
git diff --name-status db0bac5fe refs/glt/pr124 | wc -l   # 1239
git diff --name-only 8de062fb3 refs/glt/pr124             # the 19 GLT paths
git diff --name-only origin/master HEAD                   # candidate: the same 19 (+ this record)
git diff refs/glt/pr124 HEAD -- brain/liquidity_lab tests/test_liquidity_lab_*.py \
  tests/fixtures/liquidity_lab research/liquidity_transmission   # empty
```

## 6. Tests on the candidate

Command: `python3 -m pytest <suite> -p no:cacheprovider -o addopts= -q`, run at `348ef2fef` under Python 3.14 and again under Python 3.12 (the CI interpreter); identical results.

| Suite | Result |
|---|---|
| `tests/test_liquidity_lab_adapter.py` | 61 passed |
| `tests/test_liquidity_lab_contracts.py` | 4 passed |
| `tests/test_liquidity_lab_estimator.py` | 3 passed |
| `tests/test_liquidity_lab_eventization.py` | 18 passed |
| `tests/test_liquidity_lab_ledgers.py` | 3 passed |
| `tests/test_liquidity_lab_validation.py` | 7 passed |
| `tests/test_liquidity_transmission.py` (master's existing reader suite) | 79 passed |

Total: 175 passed, 0 failed. No assertion was edited.

## 7. Secrets and licensed data

- The lab imports only the standard library, `numpy`, `pandas`, `pytest` and `brain.liquidity_lab`.
  It does not import `control_plane`, settings, network clients or environment readers.
- A grep of the 19 paths for keys, tokens, `Authorization`, `api_key`, passwords and private-key
  headers returns nothing.
- The only data file is the fixture `tests/fixtures/liquidity_lab/glt_producer_20260904.json`
  (31,180 B). It is the unchanged public Macro sample `site/liquiditydata/global_liquidity_transmission.json`
  at macro `67c0fc15` (blob `89a1ac14`, state date 2026-08-28), with top-level keys
  `freshness/meta/quality/state`. It holds a derived public display artifact, not raw licensed
  history.

## 8. Disposition of the failed `test` check on #124

The failing check:

| Field | Value |
|---|---|
| Check-run | 104651188845 |
| Job | `test` (workflow CI, `.github/workflows/ci.yml`) |
| Run | 35051016157 (`pull_request` event) |
| Head | `23f97360` |
| Time | 2026-09-16 03:14:05Z → 03:34:59Z |
| Conclusion | failure |

**What failed.** `tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults`
asserted `['512', '611'] == []` at line 463. That test is a protected identity-propagation scan of
non-test additions since `git merge-base origin/master HEAD`. At #124's head it flagged every
literal from 400 to 999. The two literals it found come from GLT files:

- `512` from `brain/liquidity_lab/contracts.py:497`, a `forecast_key` length bound;
- `611` from `research/liquidity_transmission/W_LIQ_3_ADAPTER_RECOVERY_2026-09-15.md:72`, "discovered 611 modules".

Neither literal is an identity value such as a uid, port or account.

**Why it is not re-diagnosed here.** On 2026-09-21, master `8204d24c7` (#906, "fix(ci): scope D8 identity
propagation by binding") narrowed the scan:

- `docs/` and `research/` `.md` files are exempt;
- a 400–999 number is flagged only in identity context (identity words, a tainted alias, or an
  identity path).

#124's head predates #906, so its red came from the scanner it carried, not from current law. The commission
forbids re-running that check anywhere, and this disposition does not re-run it locally either.

**What the carve-out's CI should show.** The candidate is based on `origin/master`, which includes #906. The
`.md` that carries `611` is exempt under that version. The only non-test, non-markdown 400–999
literal the candidate adds is the `512` above, and its line carries no identity word, alias or
identity path. The static prediction is that this assertion passes. The authoritative evidence is
the carve-out PR's own CI at its exact head. A red there is a new finding to diagnose on its own
merits; this prediction is not a waiver. The protected assertion is not weakened.

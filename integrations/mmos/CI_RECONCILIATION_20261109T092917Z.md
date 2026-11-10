# MMOS CI reconciliation — PR #2338 head (Director E)

- **Branch**: `t3/mmos-ci-reconciliation` (worktree of `bbfad42da` = `feat/mmos-v1-integration` @`2f3deba20` + `origin/master` @`ff6d5ab67` merged + descriptor dedupe)
- **Reconciliation commits** (this branch, on top of `bbfad42da`):
  - `257136645` fix(executive_mcp): admit the composed Capacity Fabric READ in the Executive transport fence (behavior fix)
  - `4b44a9734` test(pins): move reviewed pins to the composed MMOS source; normalize quota golden interpreter noise (pin moves + golden normalization)
  - `978dc8ff6` fix(browser-proof): open the navigation drawer before mobile display-preferences acts (proof-code fix)
  - `30c9fdd31` test(hermes): pin a synthetic fabric owner so route-preview proofs are hermetic (test-hermeticity fix)
  - (this report commit)
- **Runner**: `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <files>`; frontend `app/mastermind_os` with `npm run typecheck`, `npx vitest run`, `npx vite build`, `npx vite build --config vite.browser-proof.config.ts`.

## Outcome

All 29 originally-failing python tests, the full #2338 union list, the frontend typecheck, the full vitest suite, both production builds, `adapter.test.cjs` and `browser-proof.cjs` are green on the final SHA of this branch. The two `test_hermes_omh_native.py` CI `ValueError` failures were reproduced exactly under an empty-`HOME` simulation, root-caused as non-hermetic tests (host-home fabric-owner file dependency) and fixed with a hermetic owner pin plus an explicit owner-absent refusal test.

## Per-test root cause and fix type

| Failing test (base commit) | Root cause | Fix type |
| --- | --- | --- |
| `tests/test_workspace_capacity_fabric.py` (5 cases incl. the 2 named) | #2351 registered `/workspace/resources/fabric/current` in the Workspace App inner dispatcher but never in the composed Executive transport `_ExecutivePathFence`; mounted signed HTTP read got outer 404 `unknown Executive transport route` (and the expiry matrix expected 403/503) | **Behavior fix** `257136645`: added the route to `_WORKSPACE_ADDITIONAL_GET_ROUTES` in `integrations/executive_mcp/server.py` |
| `tests/test_ceo_submit_armed_composition.py::test_d7_exact_event_loop_only_and_foreign_scope_refused` | Full-file pin on `scripts/executive_os_phase1c.py` stale after `d7558be03` (+lines, no semantic change to the reviewed loop); anchor AST digest verified unchanged (`060525ac…`) | **Pin move** (full-file sha only) |
| `tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults` | D8 identity scan tripped on `900` literals in NEW reviewed source from #2351: `control_plane/workspace_capacity_fabric.py` (2×900-second freshness bounds, alias-tainted) and `app/mastermind_os/src/resources/capacity-fabric.css` (1×900px breakpoint) | **New reviewed pins** (elapsed-time-bounds precedent, cf. quota_continuity 900 sites) |
| `tests/test_executive_mcp_web_ceo_v3.py::test_v3_is_additive_and_prior_snapshot_hashes_remain_frozen` | `565cff9c2` added the `t3` target kind to `bridge.TARGET_KINDS` → V3 schema snapshot digest moved | **Pin move** `WEB_CEO_V3_SCHEMA_SNAPSHOT_SHA256`; test now removes both promoted kinds (`hermes_meta`, `t3`) and still reproduces the frozen prior hash `5c157d1d…` |
| `tests/test_company_consultation_identity_review.py::test_company_review_pins_only_three_mode_sites` (3 == 6) | Anchor `_handle_ceo_ingress_connection` (`control_plane/executive_service.py`) grew by one statement under `3838b8b82`/`2f3deba20`; relative AST site paths shifted (`'body', 58` → `'body', 59`); spellings unchanged | **Pin move** (anchor digests + relative site paths; shared with `tests/executive_company_identity_review.py`) |
| `tests/test_discovery_correction_identity_review.py` (`auth.rs`) | `3838b8b82` (+30 lines) moved the three `503` sites | **Pin move** (sha + sites) |
| `tests/test_next_mounted_identity_pins.py` (`workspace_read_service.py`) | Consumes the shared `REVIEWED_FILES` dict; the `403` sites moved under `3838b8b82` (+4 lines) | **Pin move** (shared dict, see below) |
| `tests/test_executive_reviewed_site_identity_tokens.py` (3 files) | Same shared `REVIEWED_FILES` dict | **Pin move** (shared dict, see below) |
| `tests/test_workspace_fabric_review_pins.py` (5 cases) | Catalog/status sites in `integrations/mastermind_workspace_app/app.py` moved (+1 line, `3838b8b82`); backend sites in `control_plane/paid_fabric_backend.py` moved (+106 lines, `a751d78cc` #2316 WO-05) | **Pin move** (`STATUS_SITES`, `BACKEND_SITES`) |
| `tests/test_executive_fabric_release_identity_review.py` (8 cases) | Source of truth of the shared `REVIEWED_FILES` dict; 4 reviewed files changed on the branch | **Pin move** (4 entries) + **2 new entries** |
| `tests/test_workspace_control_room_review_pins.py::test_exact_nine_response_literals_only_are_qualified[app.py]` | Same `app.py` +1-line shift | **Pin move** (`EXPECTED[HTTP_PATH]` sites) |
| `tests/test_provider_quota_observation.py::test_producer_without_observations_path_is_byte_identical_to_before` | Golden compares producer digests; `provider_binary_identity_digest` (sha256 of `sys.executable`) differs between the recorded golden and any other interpreter — machine noise, like the already-normalized path component | **Golden normalization** (pop the interpreter digest on both sides and recompute `source_config_digest` via the factory's own canonical bytes) |
| `tests/test_hermes_omh_native.py::test_fabric_route_preview_merges_the_shared_law_composition`, `::test_fabric_route_preview_frontier_is_downgraded_by_the_shared_law` (CI shard 4, `ValueError: FABRIC_OWNER_UNAVAILABLE`) | Non-hermetic tests: they monkeypatch `bridge.catalog` and `bridge.subprocess.run` but not the module-level `FABRIC` host path (`~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py`), which exists on the development Mac but not on a clean CI runner → the owner-file guard fired before the code under test. **Reproduced exactly locally** by running with `HOME` pointed at an empty directory (only these two tests fail, same `ValueError` at `integrations/hermes_omh/capacity_bridge.py:139`) | **Test-hermeticity fix** `30c9fdd31`: the two composition tests pin a synthetic `tmp_path` owner file via `monkeypatch.setattr(bridge,'FABRIC',…)`; a new `test_fabric_route_preview_refuses_when_the_owner_file_is_absent` keeps direct coverage of the production owner-absent refusal. Green under both the normal HOME and the empty-HOME CI simulation |
| Frontend `AssertionError: Expected one 显示设置; observed: 跳至工作区, 打开导航, 来源与访问, …` (`browser-proof.cjs:61`) | #2351's new capacity-variants proof (`4d9ec1a3c`) drives the Display settings disclosure at 390×844, where it renders inside the navigation drawer that defaults closed below the 960px breakpoint → `act('显示设置')` matched zero enumerated controls; the step had never been green | **Proof-code fix** `978dc8ff6`: open the drawer through the always-rendered navigation toggle when the disclosure is not enumerated, then re-read the current locale's toggle spelling to close it (the language select changes its live accessible name) before each variant's layout checks |

## Pin moves requiring distinct CRITICAL review

All moved pins go to the exact new reviewed bytes/sites of the same reviewed tokens; the source-changing commit is named at each pin. No pin was deleted, skipped, xfailed or weakened.

1. `tests/executive_fabric_release_identity_review.py` `REVIEWED_FILES`:
   - `control_plane/paid_fabric_backend.py` → sha256 `27a074b96871beb70900c0590d7dd6d99fb1bd318896596da68232ebdaf37bde`; sites `((226,73,76,'int','501'),(416,78,81,'int','450'),(511,83,86,'int','501'))`. Source commit `a751d78cc` (#2316 WO-05, +106 lines above the pinned sites).
   - `integrations/mastermind_workspace_app/app.py` → sha256 `78985a75fb22a41c1261a82399b44ef884b3b5ba0b0cfb6f35adc9406c815b9b`; sites rows 927/938/946/952/961/971/976/982 (same columns). Source commit `3838b8b82` (#2351, +1 line).
   - `control_plane/workspace_read_service.py` → sha256 `ecac40b3e1bc54ad965a2dfa900378bc24a363c134bcbc9723d8d393870ef724`; sites `((719,93,96),(721,56,59),(728,46,49),(729,56,59))` all `'403'`. Source commit `3838b8b82` (+4 lines).
   - `app/mastermind_os/src-tauri/src/auth.rs` → sha256 `ace408ab1b186d614086923fef677000247a1074361c61a5578e78bbc5571844`; sites `((3769,68,71),(3774,69,72),(3778,67,70))` all `'503'`. Source commit `3838b8b82` (+30 lines).
   - **NEW** `control_plane/workspace_capacity_fabric.py` → sha256 `f48347aa98d894368e7e175263427c55f79c066cb3c7dfd7f32ea4253db53892`; sites `((234,66,69,'int','900'),(277,106,109,'int','900'))` — elapsed-time freshness bounds (same reviewed-token class as the incumbent 900-second quota-continuity sites).
   - **NEW** `app/mastermind_os/src/resources/capacity-fabric.css` → sha256 `e75e39ac6eba0344f4a3133d3c875976d342b7db9b69e6010c6d29f0ffc8f1bf`; site `((49,19,22,'int','900'))` — 900px responsive breakpoint.
2. `tests/executive_company_identity_review.py` anchor `_handle_ceo_ingress_connection`: `source_sha256` → `21754f04ff0d5571ace5be199e23e20c9b91c2ca5ddc493c6821109cf4546646`; `ast_sha256` → `27f53e5690ad71c86f01f2ad657535aa022e0565472fef95ee773fc8c7837eaf`; relative site paths `'body', 58` → `'body', 59` (spellings `403/403/503` unchanged). Source commits `3838b8b82` composed by `2f3deba20`. This anchor is shared by `tests/test_company_consultation_identity_review.py`.
3. `tests/test_workspace_fabric_review_pins.py`: `STATUS_SITES` → `((6048,66,69,'int'),(6061,74,77,'int'),(6063,75,78,'int'))` (the three `workspace_error` catalog operands, `app.py` rows above); `BACKEND_SITES` → the `paid_fabric_backend.py` sites in (1).
4. `tests/test_workspace_control_room_review_pins.py`: `EXPECTED[HTTP_PATH]` → `((927,71,74),(938,71,74),(946,71,74),(952,79,82),(961,71,74),(971,71,74),(976,76,79),(982,71,74))`.
5. `tests/test_discovery_correction_identity_review.py`: `auth.rs` RECORDS sha + sites as in (1).
6. `tests/test_ceo_submit_armed_composition.py` (d7): full-file pin `dd09c1cf…` → `eb33b3f4982f8248515dd03e0842a58ade6e624628272945ca0c8d088f876bdf` on `scripts/executive_os_phase1c.py`; source commit `d7558be03`; the reviewed anchor AST digest `060525ac…` verified unchanged.
7. `integrations/executive_mcp/web_ceo_v3.py`: `WEB_CEO_V3_SCHEMA_SNAPSHOT_SHA256` → `98117956ba511d06b3f2c5685bb50865e451be56cfac0aa2c2b45e414a1a5565`; source commit `565cff9c2` (`t3` target kind). `tests/test_executive_mcp_web_ceo_v3.py` now removes both promoted kinds and still reproduces the frozen prior snapshot `5c157d1de43d6efef99f6ba9e27e851f0243bbb18d38c23551b94a5c2a4ba2c0`; all legacy/v1/v2 frozen hashes unchanged.

## Complete CI failure inventory at 2f3deba20 (from the actual shard logs)

Retrieved via `gh` from the five failed jobs (frontend + shards 0, 2, 3, 4, 5; shard 1 was green). Every CI-red test is accounted for:

- Shard 3 — `test_workspace_capacity_fabric.py` (5): fixed here by `257136645` (behavior fix).
- Shard 4 — `test_ceo_submit_armed_composition.py` d7/d8, `test_company_consultation_identity_review.py`, `test_executive_mcp_web_ceo_v3.py`, `test_executive_reviewed_site_identity_tokens.py` (3), `test_workspace_fabric_review_pins.py` (5), `test_hermes_omh_native.py` (2): all fixed here (pin moves / golden normalization / hermeticity fix).
- Shard 2 — `test_discovery_correction_identity_review.py`, `test_next_mounted_identity_pins.py`: fixed here (shared pin moves).
- Shard 5 — `test_executive_fabric_release_identity_review.py` (8), `test_workspace_control_room_review_pins.py`: fixed here (pin moves).
- Shard 0 — `test_provider_quota_observation.py` (fixed here, golden normalization); `test_rev5_contracts_v1_1.py` ×2 (`dsh-acp: … not declared`, `'' == 'dsh-acp'`), `test_worker_adapter.py` ×1, `test_t3_execution_adapter.py` ×3 (shard 3; `worker adapter 't3-native' is not implemented`): these were the descriptor/lane-merge failures **already fixed in this worktree's base commit `bbfad42da`** ("fix(mmos): dedupe t3-native/dsh-acp descriptor rows after lane merges"); the corresponding files pass green in the union-list run on this head.

## Master comparison (pre-existing failures)

`/tmp/master-check` worktree at `origin/master` (`3652d8907`):

- `tests/test_executive_mcp_web_ceo_v3.py` — passes on master (snapshot matches master's `TARGET_KINDS`).
- `tests/test_hermes_omh_native.py` — passes on master (45/45).
- All 8 pin-test files (`test_company_consultation_identity_review.py`, `test_discovery_correction_identity_review.py`, `test_next_mounted_identity_pins.py`, `test_executive_reviewed_site_identity_tokens.py`, `test_workspace_fabric_review_pins.py`, `tests/executive_fabric_release_identity_review.py`, `test_workspace_control_room_review_pins.py`, `test_ceo_submit_armed_composition.py`) — **rc=0 green on master**.
- `tests/test_workspace_capacity_fabric.py` and `tests/test_provider_quota_observation.py` do not exist on master (branch-new files).

**Conclusion: no pre-existing-on-master failures among the reconciled set.** Every red test on this head was introduced by the branch composition itself (behavior gap, moved reviewed source, or new proof code).

## Verification commands and counts (final SHA)

- Originally-failing 12 files: `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <12 files>` → rc=0, **379 passed**.
- Union list (32 files): same runner → rc=0, **1153 passed**.
- Full vitest: `npx vitest run --maxWorkers=4` → rc=0, **414/414 test files, 7005 passed, 12 skipped**. (A default full-parallel run under external load average 55–61 produced 93 five-second jsdom timeouts; all 27 affected files pass sequentially with `--maxWorkers=2 --isolate=false` — 329 passed, 2 skipped — and the reduced-worker full run is green. Load-induced, not regressions; my diff touches no app source.)
- `npm run typecheck` → green. `npx vite build` → green. `npx vite build --config vite.browser-proof.config.ts` → green.
- `node --test integrations/worker_browser_runtime/app-control/adapter.test.cjs` → 7/7 pass.
- `browser-proof.cjs` (local chromium via `MM_APP_CONTROL_CHROMIUM`, cache `chromium-1234`) against the fresh `dist-browser-proof` build → `{"passed":true,"live_acceptance":false,"calls":131}`.

### CI shard reproduction (6 shards)

Command per CI (`.github/workflows/ci.yml` "Run repository test shard"): `python -m scripts.ci_parallel_shard --jobs 6 --index N` for N=0..5, run sequentially. Local environment parity with the CI job (which runs `pip install -e ".[dev]"` and checks out the pinned Macro engine):

- venv `/tmp/ci-shard-venv` = `/opt/homebrew/bin/python3.12 -m venv --system-site-packages` + `pip install claude-agent-sdk pillow reportlab` (the dev machine's python3.12 user site lacks these three; a bare run interrupts collection with `ModuleNotFoundError` in 9 files — an environment gap, not a source regression; CI installs them via the project dependency set);
- `vendor/macro_src` → sparse clone of `mastermindx-market-intelligence/macro` at the workflow pin `268a89e3828d848848c77dfe69191c3fa7319361` (engine/lib/config), exactly as the CI "Checkout pinned Macro engine" step does (`vendor/macro` is the tracked symlink to it); the path is gitignored, no branch pollution;
- with that parity the whole `tests/` tree collects with **rc=0, zero errors**.

**Shard results: NOT COMPLETED in this lane.** The six-shard sequential run was started in
the lane worktree but the director's turn ended before any shard finished; no shard result
log exists (only the shard-0 header line). The integrator records this honestly rather than
inferring green. The verifier for the whole-tree shard matrix is the GitHub CI run on the
pushed integration head; the targeted evidence above (12 originally-failing files, 32-file
union list, frontend typecheck/vitest/builds, browser-proof) was run and is green.

## Shared-path proposals

None. No fix required editing `control_plane/executive_runtime.py`, `control_plane/worker_adapter.py`, t3/dsh adapter modules or app React views: the transport-route fix landed in the sanctioned `integrations/executive_mcp/**` route table, and the 显示设置 fix is browser-proof test code (`integrations/worker_browser_runtime/app-control/browser-proof.cjs`), both explicitly permitted surfaces.

## Still red / not reproduced

Nothing is still red. The two `test_hermes_omh_native.py` CI failures were reproduced exactly (empty-`HOME` simulation → `FABRIC_OWNER_UNAVAILABLE`), root-caused as non-hermetic tests, and fixed hermetically in `30c9fdd31`; they now pass under both the normal and the CI-simulated HOME. Note for the reviewer: those two proofs exercise the composition logic only; the production owner-absent refusal keeps its own explicit test. The remaining environment dependence in `integrations/hermes_omh/capacity_bridge.py` (module-level host-home `ROOT`/`FABRIC` paths) is production behavior outside this reconciliation's edit surface and is unchanged.

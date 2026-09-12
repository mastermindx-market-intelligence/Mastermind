# Connected Office R0 — canonical recorded-lane reader

> For agentic workers: apply executing-plans and test-driven-development. This is a bounded source proposal, not an installed Runtime or MCP release.

**Goal:** Read a root Job and its parallel Executive child Jobs, including exact current Attempt references, in one bounded read transaction and display the result through a working local consumer.

**Architecture:** Extend the Executive read owner with an additive stateless module. Reuse the existing RuntimeStore read transaction; do not use its multi-transaction debug snapshot. Keep every existing writer, singular Steward query, MCP profile and Control Room schema unchanged.

**Tech Stack:** Existing Python Runtime, SQLite and pytest; standard-library CLI. No dependency changes.

**Spec:** Mastermind PR #505, head `1547821bd42f014520938647356b7149b25daca0`, `research/MASTERMIND_CONNECTED_OFFICE_DELIVERY_CONTRACT_2026-09-06.md`. R0 is an earlier source-only reader, not completion of that contract's V1 native-parent/child Web journey.

## Authority and exact scope

Current Chairman instruction: "Continue working, mac should be restored", following explicit approval of the connected-office outcome. Operation: `connected-office-lane-observation-r0-20260906-sol-001`. Source proposal author: this continuing Web Sol, using the authorized Mac. No assignment, takeover or release of another worker follows.

Protected Mastermind/Skillpack pin: `467a81e84b08a7f1c3cdb9a410b2f7857816675d`, compatible `mastermind.sol_skillpack.v1` / 1.0.1 / bootstrap 1. Existing Integration/Runtime/Cockpit owners retain integration and production admission. Their four-read source and PR #469 release are not modified or delayed by this proposal.

Exactly four new paths:
- `control_plane/executive_lane_observation.py`: canonical read-only SQL projection, within the Executive owner.
- `scripts/executive_lane_observation.py`: fixture-only CLI demonstration and text consumer.
- `tests/test_executive_lane_observation.py`: real temporary Runtime tests and adverse controls.
- This plan and evidence record.

All 48 open PR changed-file sets and 176 registered local worktrees were checked: none contained these paths. The isolated branch is `codex/connected-office-lane-observation-20260906-websol`. Existing source is not edited. No new lifecycle, queue, identity, authentication, memory or transcript store is introduced.

## Contract

`observe_root_lanes(runtime: Runtime, root_job_id: str, *, max_rows: int = 64) -> dict` accepts an already-authorized internal caller and a Runtime opened with `create=False`, `existing_writable=False`. It is NOT an authorization service. No network route or installed database selector is exposed by the CLI.

The wire schema is `mastermind.executive_lane_observation.v1`. `status` is OBSERVED, PARTIAL, REFUSED or UNAVAILABLE; these are read-result states, never Job states. Failure returns `lanes: null`, not a quiet empty office. Coverage names ROOT_JOB_AND_EXECUTIVE_DESCENDANTS, completeness/truncation and returned count. It makes no fleet-enrollment or native-helper completeness claim.

A lane carries source-owned Job identity, parent/root/depth, owner seat, Job status and update time; a nullable current Attempt carries exact identity, Worker reference, status, fence generation, heartbeat/lease times and checkpoint sequence. Follow ONLY `jobs.current_attempt_id`, never maximum attempt number or timestamp. Verify Attempt/Job/Worker/quota joins. Missing or inconsistent current Attempt facts remain explicit gaps without selecting another Attempt.

Validate the returned root/parent/depth graph. A malformed graph refuses rather than disclosing a foreign parent. Source dates remain dates: no freshness, liveness, progress, idle-capacity or effect-safety inference. RuntimeBinding, account enrollment, host, provider activity, effect state and current permission are explicitly unprojected. No objective/prompt, result/error body, arbitrary metadata, path, process handle, native session identifier, credential or lease token is selected.

Bounds: 1–128 rows, one extra row only to detect truncation, bounded scalar identifiers, a fixed SQL VM-step ceiling and a 128 KiB encoded response ceiling. No background polling or retry. Canonical Runtime connection-opening/schema/lock budgets remain unchanged; this does not repair or claim to repair the installed per-connection identity defect.

The CLI has only `demo --format text|json`. It creates a disposable genuine Runtime, seeds synthetic Jobs/Workers through their existing public write APIs, opens its reader with `create=False`, prints the actual observer output and removes the fixture. No arbitrary runtime-root, socket, provider or installed-path option exists. The demo is clearly labelled FIXTURE_ONLY_NO_PROVIDER_EXECUTION.

## Implementation sequence

- [x] Write genuine temporary Runtime tests before implementation. The first test must fail because the new observer is absent, not because a runtime fixture is malformed.
- [x] Implement the bounded rooted reader over one `RuntimeStore.read()` context. Keep SQL in that Executive-owned module and no raw SQL in the CLI.
- [x] Prove two parallel child Jobs remain visible, exact current Attempt selection, wrong-root refusal, truncation, unavailable-source nulls, bounded errors and excluded sensitive fields.
- [x] Prove the observer uses one read transaction and a concurrent canonical writer cannot tear parent/child observations. Observe the later commit only on the next read.
- [x] Add and execute the fixture-only CLI consumer. Capture exact JSON plus readable tree; fixture claims are not provider execution.
- [ ] Run adjacent Runtime/Steward suites and current source checks. Publish one Draft/Hold source candidate, preserving PR #505's frozen two-file scope.

Commands from the isolated repository root:
```sh
python3 -B -m pytest -p no:cacheprovider -o addopts= -q tests/test_executive_lane_observation.py
python3 -B -m pytest -p no:cacheprovider -o addopts= -q tests/test_executive_os_phase1fb.py tests/test_executive_steward.py tests/test_executive_os_sqlite.py
python3 -B -m scripts.executive_lane_observation demo --format json
python3 -B -m scripts.executive_lane_observation demo --format text
```

## Executed evidence and honest release ceiling

The isolated protected-base baseline passed 53 Runtime hierarchy/Steward tests. The first three observer tests then failed on the absent observer. Two fixture authoring mistakes were corrected without changing Runtime: canonical account labels are lowercase, and AttemptLease exposes its Attempt through `.attempt`. Observer cases passed; the CLI test independently failed on its absent module before CLI implementation.

The final selected native suite passed **128 tests** across the new observer, existing hierarchy, Steward and SQLite modules. The new file contains 27 collected cases. The real CLI ran successfully and printed a root with two child Jobs, one current CLAIMED Attempt and one child with no current Attempt. CLAIMED is not provider execution. The fixture is labelled and no installed runtime path is accepted by this CLI.

Three in-memory source mutants were each killed by their discriminating tests: removing the Attempt-to-Job equality exposed a foreign root's Attempt; removing the extra limit row hid truncation; committing between the two SELECTs exposed the concurrent fourth child in the earlier snapshot. The actual source file was unchanged by mutation execution. This is not an independent code review.

Before final source publication, rerun the focused cases and syntax/diff checks against the exact candidate. Hosted CI, independent review, Runtime-owner adoption, installed identity qualification, authenticated MCP integration, actual native-helper observation and real Web/browser proof remain separate gates. Neither R0's green tests nor its genuine temporary database creates an installed or complete connected office.

**Source-only continuation:** existing Runtime/Cockpit/Integration owners review this finite four-path reader/consumer proposal and decide its integration into their canonical read boundary. Do not add it as an unversioned tool, merge on this document, widen the occupied Personal four-read slice, or treat its caller-supplied Runtime as authentication. Keep #505's singular-query protections and the original C1/W3C holds. No new worker, provider, watcher or memory plane was started.

PREFERRED_AVENUE for independent bounded technical review: CTO Sol, placed by the existing owner. WHY NOT FABLE: the source and tests are finite and disjoint; a new principal is unnecessary. No reviewer assignment or ACK is implied by this preference.

### Protected movement during verification

Protected master advanced to `cd297f1079bf5a44b520697a096096000f64efdd` (tree `c0bbf8cf5510c6d1ec89a4038efe9deb9438206c`), whose sole parent is the original `467a81e...` base. Direct GitHub commit read shows only #503's `content.js` and its observation-epoch test changed. Runtime, this reader's dependencies, workflow and governing procedure are unchanged. INDEX and each required procedure/law were re-resolved at the new commit with unchanged blob identities and compatible headers; the previously full-read contents therefore remain byte-identical.

A combined host source-comparison/fetch request was blocked by the tool safety gate. That fetch was not retried. Subsequent connected GitHub reads established the new protected source without modifying the local checkout. Keep the tested source on its original base; do not manufacture an ancestry-only join. Current-base integration proof remains the later actual PR merge-candidate CI, not the earlier native test run.

## B1 review correction — qualify every read snapshot

Review `5125728864` on original head `d5301d65df5f2ed6565a0635aa8f51d668f53000` found that the existing read-only Runtime constructor only checks whether `schema_migrations` is queryable. The original observer therefore labelled foreign look-alike tables and a genuine v4 database with tampered migration metadata as OBSERVED. Earlier positive test/review observations remain historical evidence, not acceptance of this missing guard.

The same source-author session continued under the Chairman's direct instruction; receipt `5560234370` is on the original PR508. Local and remote heads were exact/clean and no replacement writer, release or uncertain source effect was observed. Scope remains the original four paths, with this correction changing only reader, tests and this plan.

The repair calls the existing `RuntimeStore._verify_current_schema(connection)` inside the SAME `RuntimeStore.read()` transaction, under the existing SQL-step budget, before either projection query. Runtime alone owns exact migration vector/name/checksum/DDL policy. No schema-policy copy, Runtime modification, new public tool, installed source selector or side-effect channel was added. Read-only initialization's cached `_schema_ready` is not reused as current qualification.

Seven new regressions were first observed failing on the old source for the actual missing-qualification behavior, then passing after the correction: foreign look-alike schema; four independently tampered current-schema variants (checksum, name, vector and DDL); tampering after a successful read; and canonical qualification on the exact active transaction before projection. The concurrency test now counts the two projection SELECTs separately from canonical schema queries, preserving its one-transaction and concurrent-child assertions.

Focused suite: **34 passed**. Selected observer/hierarchy/Steward/SQLite regression: **135 passed** on Python3.14.7. Removing only the new canonical verification call in memory caused all seven new cases to fail again; source bytes stayed unchanged. Further interpreter and hosted results belong in dated PR evidence rather than being inferred here.

Database-integrity assertions compare main-file bytes, mode and modification time. The first test draft also compared directory inventory and exposed that SQLite's existing read-only WAL path may materialize WAL/SHM sidecars; that assertion was corrected before implementation so the RED cases discriminate the actual schema defect. No no-filesystem-effects claim is made. No journaling configuration, immutable-mode workaround or installed database was changed.

This fixes schema qualification only, not the separately owned installed file-handle identity requirement. The source remains Draft/Hold pending genuine non-author review of the repaired immutable head and current-base CI. Existing native-provider, RuntimeBinding, authenticated MCP and Web consumer proof remain owed under the original connected-office contract.

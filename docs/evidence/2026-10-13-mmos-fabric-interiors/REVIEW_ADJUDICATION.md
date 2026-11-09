# Exact-source review adjudication

Parent mission remains incomplete. This record adjudicates a source-review deliverable, not production permission, worker-result content acceptance or deployment.

## First independent read

Child `mmos-fabric-interiors-review-20261013-c4-01` used the normally admitted MiniMax/ubuntu1 route; original root/parent `mmos-fabric-interiors-20261013-c4`. Reviewed head `6289b6ac9030f1c75511136d868be2b7b21b7604`. Terminal rc0/ok; result7,731bytes. Exact return SHA-256 `5be361a0006101082a156a32c6c1d7b6cd92de6eee4dacfa072ae08149c0dec8`. The retained return is `independent-review-first.md`. The reviewer did not re-run the tests and explicitly said so.

Its headline PASS is not adopted blindly: the report contains inconsistent major labels and some proposals contradict actual owner contracts.

| Finding | Parent disposition and source evidence |
| --- | --- |
| M1: RUNNING/WAITING root-resolution states | Rejected. `mission.ts:147` defines resolution as RESOLVED, CONFLICT or UNKNOWN. Job execution status is a separate field. The proposed RUNNING resolution fixture is outside the decoded contract. Existing lineage test already proves two running jobs remain counted under a resolved root. |
| M2: terminal success with NOT_ACCEPTED | Rejected. This is required behavior, not inconsistency. The real incumbent run and `attended-status.test.tsx` explicitly establish terminal rc0/ok with result and no acceptance. Adding the proposed restriction would falsely promote or reject valid unaccepted results. |
| m3: false result availability with a positive byte count | Accepted and repaired. The installed adapter assigns result_bytes only when its result file is available, otherwise null. Decoder now rejects false availability with non-null bytes; the malformed-metadata test includes that discriminating case. |
| m1: duplicate-map overwrite | Nonblocking. Duplicate IDs are rejected before the map entry is followed; no winner is presented as authoritative. |
| m2/m6: duplicate runtime/type enum declarations | Nonblocking style; no contract change warranted. |
| m4: rc/signal observation mismatch | No promotion occurs. Values are source observations; accepted=true still requires terminal rc0/ok. Do not overwrite owner-observed execution metadata with a new lifecycle rule. |
| m5: immediate parent must equal root | Rejected. Supported nesting requires actual immediate parents, not flattening every child under the original root. |

The review also overstates what an optional client port enforces. Opt-in plus browser auth checks do **not** implement server authorization. Existing production principal/grant and source binding remain explicitly unimplemented and gated, as in the mission plan.

## Repair verification

After m3, the complete app suite again passed **1,395 tests, one skipped, zero failed, 57 files** and the TypeScript/Vite build passed. No tests were removed or waived. Source hashes and exact log hashes are in `verification.json`. UI/CSS/host/office integration did not change; the existing browser receipt is reused only for that unchanged presentation and its unchanged valid retained payload, not claimed as a new run.

The repaired decoder changes a candidate-owned semantic blob. Consequently the original read alone does not close exact-head review: a follow-up independent review must bind the repaired immutable head before normal release. No source/binding/install/acceptance state is advanced by this record.

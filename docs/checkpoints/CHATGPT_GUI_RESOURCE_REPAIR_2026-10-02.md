# ChatGPT GUI resource review repair — 2026-10-02

Carrier: PR #1136; operation `grok-chatgpt-gui-resource-20261002-sol-001`.
Mission: #1141 / #1143. State: architecture candidate, source repaired; native acceptance remains open.

The explicit mission handoff reused the existing Studio operation workspace through `mmx-workspace acquire`; no replacement checkout, branch, registry, scheduler, or runtime owner was created. The published identity repair from #1134 (`dd79074546d571ae8ce43bfc083139f324a84593`) is incorporated as a functional dependency.

## Three review findings repaired

1. A GUI mutation receipt carries and validates the prepared payload digest and original plan preimage ID/digest. Submit checks the exact APPLIED preparation receipt before calling the helper. The helper's immediate `before_snapshot_id` remains distinct from the original plan preimage, permitting the mandatory fresh observation.
2. Composer preparation obtains a new exact-session semantic observation and checks it against the existing `verify_pre_dispatch` reducer using an authoritative clock before any mutation. Missing, stale, future, incomplete, changed, blocked, drafted, generating, or retargeted evidence refuses. The closed helper protocol still owes a final adjacent check at its native effect boundary.
3. A missing artifact is accepted only for the explicitly requested GUI resource contract, with matching typed capability and digest in the resource and persisted materialization attestation, plus the exact requested-profile digest. Browser and unadmitted resources cannot finish without their typed artifact; existing closed-schema and generation checks remain.

## Evidence

Repair commit: `d745c8be` (four scoped source/test files).
Integrated source candidate: `65bdd19999471e7bd291096bebd5d92284bce7a4`.

- GUI resource and broker focused tests: 97 passed.
- Expanded nine-file suite before parent update: 486 passed.
- Actual merge-tree proof of integrated candidate plus protected master `af5a22eb4b67f88f092ebd2f2452877caa7cfc73`: 517 passed in 21.97s.
- Merge tree: `3f943d6393c884a03be3038a50d77d6317d00002`.
- Archive SHA256: `4468d5655c2f65f6123d69dd5bdde2cbb46ab07ca4edda7601621a02106f95c0`.
- Test-log SHA256: `b361b43ce044ea440d6c219fa5a29ae336472dd39e6a9169f9c1ce262add0280`.
- Studio evidence: `/Volumes/Mastermind/evidence/exact-session-interconnect-20261002/gui-resource-current-base/PROOF.json`.
- Independent read-only review of all four repair files: PASS, source-only.
- `git diff --check`: clean.

Hosted checks and external release review remain separate gates. The final documentation-only commit does not alter the tested source tree.

## Economical fabric delegation

The user-authorized direct m2 `pool` route supplied bounded patch-return labor; it was not an Executive SUMMON acceptance demonstration. Existing Go gateway controller was started with worker lease capabilities after checking the installed seat-operator contract. No credentials were copied or exposed and no GUI/runtime target was armed.

- `rs_20261002T082037Z_92995`, ubuntu1, `deepseek-v4.1-flash`: COMPLETE. Worker and transport cleanup proven. Returned receipt-binding patch independently reviewed and tested (27 GUI tests at that frontier) before integration.
- `rs_20261002T083503Z_41785`, same host/model, lease `0c4e0e5ddf50`: timed-out text-only test proposal, no usable returned patch. Worker rc124 and cleanup proven; transport SSH rc255, `EFFECT_UNKNOWN`, lease preserved. Installed tooling has no post-hoc settlement route. Do not replay, release, or rewrite receipts. Root completed the independent local test work manually; no replacement provider job was launched.

Exact run receipts remain in the existing fabric state directory; this checkpoint is evidence, not a second result/lease store. The Go service must not be stopped or the held lease altered merely to produce a clean dashboard.

## Remaining acceptance boundary

No physical GUI-seat helper is implemented or installed by this repair, and no native send, mode change, runtime target enablement, merge, deployment, or original-parent return is proved. The existing Peekaboo `AGENT_EXECUTION_POLICY_REFUSAL` remains binding; generic shell typing, AX mutation, or another host/provider must not be used to route around it. The exact provider-native causal join remains required. #1112 held source/comparison and historical effect-unknown canary lanes remain frozen.

Continue from the existing PRs and carriers under #1143; preserve the distinction between source validation, provider delivery, target consumption, and mission acceptance.

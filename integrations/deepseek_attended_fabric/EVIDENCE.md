# F3.U2 source qualification — 2026-11-07

## Exact custody

- Protected law/base: `93861e9ab2e75176108bb357bd9e81b54307981d`.
- Managed source operation: `unified-workforce-20261107-c2-01`.
- Branch: `sol/web-unified-workforce-20261107-c2-01`.
- Architecture/plan parent commit: `19dc1d6c7c3496d98d1b42faf7ae41b939711d1d`.
- Native donor: clean `687f282e8625c6b8d11ff58211a90524be2e4317`;
  test configuration verifies both exact HEAD and clean Git status.
- Application/ACP/launcher carrier #2177, APPLICATION publishers #2175/#2194 and
  Hermes gateway/enrollment carriers #2166/#2186 remain untouched.

## Executed test receipts

Studio Direct process **97773** ran the native Vitest suite against the adopted
donor on the isolated source workspace, with one worker:

```text
native.test.ts: 5 passed
core.test.ts:   34 passed
Test Files:    2 passed
Tests:         39 passed
Duration:      4.53 seconds
TEST_EXIT=0
```

The process also read back source HEAD
`19dc1d6c7c3496d98d1b42faf7ae41b939711d1d` before publication.
An earlier 35-test run (process 88978) passed; the final run adds retained
prelaunch refusal, foreign grants, malformed admission and native interruption
recovery coverage.

The five native tests use actual adopted Cordis, Tools, AgentLoop,
AgentRegistry and Session source. They verify:

1. The real native parent calls the tool, submits once, retrieves a
   digest-verified result and carries that result into its next scripted model
   request and its own native session history.
2. An unrelated real native Agent has neither tool visibility nor execution
   access; disposing the original registration removes it.
3. Disposal during an owner read withholds the response and creates no remote
   cancellation operation.
4. A forged/global Context cannot install a global fallback.
5. Native cancellation represents an interrupted tool call honestly; a later
   observation recovers the same Fabric identity without another request.

All provider outputs and Fabric responses are **fixtures**. These results prove
native source composition and contract behavior, not live dispatch, physical
placement, provider usage, persisted process-restart recovery or production
acceptance.

An additional ad hoc TypeScript scan with the donor's source aliases reported
**zero diagnostics in core.ts/native.ts** and **70 diagnostics elsewhere in the
expanded donor graph** (process 93209). It exited 1; this is not recorded as a
full graph typecheck pass. Native runtime tests above are the passing gate.
No unrelated donor source was modified to silence that diagnostic.

## Material behavior established

- Exact native Agent/session identity and current host-issued scalar grant.
- Stable profile/session/task-key run identity across process generations.
- Existing original owner remains the sole atomic new-run admission fence.
- Simultaneous same-key fixture calls create only one request when the existing
  owner provides its required atomic claim.
- Lost or malformed post-send responses remain EFFECT_UNKNOWN.
- A control receipt never becomes worker-start proof.
- Canonical root/parent and original/effective run identity are checked.
- Results are bounded, byte-counted, SHA-256 verified and withheld after lineage
  changes or permission revocation.
- No retry, provider failover, acceptance, remote cancellation, polling,
  background continuation, credential source or new job ledger exists here.

## Installed execution observations and remaining gates

The original bounded paid source-census request
`unified-workforce-hermes-seam-20261107-c2-01` remains on its original root
`unified-workforce-20261107-c2-01` and controller PID **34659**.
Its one status observation was REQUEST_REFUSED_BEFORE_LAUNCH with
EXECUTION_NOT_ELIGIBLE / UNCLASSIFIED_PRELAUNCH_REFUSAL, no result and no replay
authority. Its one bounded controller diagnostic ended MMX_FABRIC_EXIT=75.
A controller handle was obtained; worker START was not proven. No retry,
replacement provider, changed host or duplicate task was dispatched.

The installed Executive V3 reader reported backend_unavailable. The fleet
projection was advisory and did not establish executable Ubuntu eligibility.
Those observations do not authorize activating a disabled control service.

F3.U2 remains BUILT_NOT_PROVEN until the original native application owner
supplies authenticated session enrollment, currentness, durable original-run
admission and the enrolled MCP transport, followed by an actually admitted
remote worker and exact native-parent result consumption. A real installed
journey must separately prove native history across restart, app display,
account settlement and host/process identity.

A managed DeepSeek SubagentProvider remains held for the incumbent cancel
owner's exact-run cancellation and settled cleanup contract. No stand-in
cancel operation is introduced.

MISSION_COMPLETE: false.

## Principal semantic review

A distinct native principal judgment context (`/root/architecture_assessment`)
reviewed immutable commit `4d6e53e2f037fb241805966d8d439207e77f6c4d` read-only.
The parent accepted its return: no blocking core/native source defect found.
This was optional architecture scrutiny, not a formal GitHub approval or a new
mandatory release stage. The reviewer did not run the tests or claim runtime
qualification.

The parent accepted its P3 precision finding and renamed the new output flag to
`result_transfer_verified`: verified transfer does not prove worker assertions,
referenced artifacts, acceptance or an atomic owner seal. The README now also
names incumbent recovery of a claimed-but-unsent request and bounded settlement
of the original transport call. The tracked local dependency symlink found in
parent readback was removed at `ab4685679ac3cf0660523d313e329258b2e57907`; the
corrected ignore rule handles both symlinks and directories.

After the flag clarification, Studio Direct process **22859** reran both suites:
**39 passed / 2 files / 1.74 seconds / TEST_EXIT=0**. The actual native history
assertion now checks `result_transfer_verified`. `git check-ignore -v` proved
the dependency symlink ignored, and `git diff --check` exited 0.

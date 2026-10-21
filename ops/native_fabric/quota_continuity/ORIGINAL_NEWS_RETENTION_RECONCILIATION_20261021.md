# Original News retention reconciliation — source and release contract

## Scope and disposition

This source adds the missing incumbent-owner check and explicit reconciliation for the original News review `news-9612-exact-3a663-release-review-20261021`, rooted and parented at `news-cockpit-rebuild-20261018-astra-01`. Its immutable review subject remains `3a663ae70ecbd8a4130de9c95dbb6d940d181e04`, even though News PR #9612 has subsequently integrated main at `81df0f97de259457a6a93f90e726240a98d20b82`.

The result is a historical failure disposition, `TERMINAL_FAILURE_RECONCILED_NO_REPLAY`. It is not a worker result, acceptance, successful review, replay permission, quota continuation, or admission of another request. The original packet and all original records remain in place. The separately failed repair reviewer `news-1665-73eefe48-source-review-20261021` is outside this exact case.

At source qualification, no live reconciliation receipt was written and no native generation was selected. This document is not evidence of rollout or production acceptance.

## Retained evidence and historical control flow

`candidate/native_plain_packet_check.py` fixes the run, root, old review subject, eight artifact digests, two historical generation identities, and nine relevant executable source digests. It validates the original request/launch/return chain, packet length and digest, exact route, failed controller return, continuation records, and successful local routing-process settlement. The original packet content is not reproduced here.

The retained log has only the original run reservation and `PLAIN_PACKET_RETENTION_REFUSED rc=78 before_lease=1`. The return record binds that log, the launch and request; the launch binds the original request and packet. No new interpretation is obtained from the log marker alone.

Historical source at Mastermind `b66e64ad57b50f77253eeacf62ac72dc165a50aa` and the retained immutable generations establishes these boundaries:

- The request owner rejects an existing request identity before routing or dispatch. The original route is concrete `ubuntu0`, `qwen3.8-max`, `bailian`; the earlier optional auto-host refresh branch is not reached for that concrete route.
- Routing receives task metadata, not the task packet, and the retained routing receipt proves normal local-process settlement. Policy, account and host telemetry remain possible; there is no claim of zero telemetry transport.
- `remote_sub.sh` initially has empty lease and orchestrator identities. Original plain-packet retention fails its exclusive-create operation and exits 78 before the local worker-dispatch branch, lease acquisition, support transfer and remote launch.
- Cleanup can remove local temporary lease metadata. Its release path is conditional on a nonempty lease identity, which this failed path never obtains. It does not acquire or dispatch work.
- The deadline helper supplies timing arithmetic. The retained continuation finishes on the same original run with `continuation_evidence_unqualified`; it creates no successful successor.

The two compatible retained generations are `4cf603706381969f2a784adb38ed9e6ace2b14188444e5bbb8085d2c31c472ec` and `bb80e3793f116f43ef73d56f60d71edde7b1773d70dc5444973d019c3e66132c`. Their 83-file manifests differ only in `ext/current_source_observation.py`, outside this request's relevant call path; the other 82 files, entrypoints, links and stable owner binding agree. The checker verifies both canonical generation descriptors and the nine required source files. It does not invent which generation was selected at the original invocation.

The operator-continuation environment was not recorded. The existing-run guard and reviewed fixed unrelated continuation case exclude the known operator path for this case, but the checker does not claim that environment variables were absent. This proof relies on retained native-owner records within the incumbent same-OS-principal trust model; it does not establish protection against fabrication by a malicious holder of that same principal.

## Read-only evidence contract

All directory ancestors are traversed through the existing no-follow `DirectoryChain` owner. Every evidence descriptor stays open until final revalidation. Artifact files must be bounded regular files, current-user owned, mode 0600, with one link. The native generation store must remain mode 0700, generation and executable directories mode 0555, source files mode 0555, and release descriptors mode 0444. Both visible paths and open descriptors are checked, including device, inode, owner, group, mode, link count, size, modification time and change time for files.

Duplicate JSON keys, non-finite numbers, weak integer types, unknown or contradictory run artifacts, changed historical bytes, a visible original result, directory substitutions, late permission changes and cross-record replacement invalidate the check. The positive conclusion comes from the bound records and reviewed historical control flow. Absence of an extra artifact is only a contradiction check.

The read-only command is:

```text
fabric_task.py check-plain-packet-retention news-9612-exact-3a663-release-review-20261021 --root news-cockpit-rebuild-20261018-astra-01
```

Its successful predicate is `QUALIFIED_PRELEASE_WORKER_ABSENCE`; it reports no reconciliation, canonical mutation, retry, acceptance or review result. It deliberately refuses the case once a reconciliation receipt exists; the normal status owner then validates that receipt independently.

## Explicit reconciliation and status projection

After protected release and qualified rollout, the incumbent owner may invoke:

```text
fabric_task.py reconcile-plain-packet-retention news-9612-exact-3a663-release-review-20261021 --root news-cockpit-rebuild-20261018-astra-01 --expected-proof-sha256 <fresh-verified-proof-digest>
```

The modifying command performs fresh proof validation and requires the exact proof digest. It creates only `<original-run>.plain-packet-reconciliation.json` in the original owner's `state/remote_sub` directory, using exclusive no-follow creation at mode 0600 through a held directory descriptor. The fixed canonical receipt binds the original run/root/parent/subject, artifact and historical source digests, both compatible generation descriptor digests, failure code 78, scoped worker/provider absence, and the no-replay/no-acceptance disposition.

It checks new-file custody, completes bounded writes, fsyncs the file, checks writer versus path identity, revalidates all original evidence, fsyncs the directory, reads the same visible receipt, and performs final identity and inventory checks. It never rewrites or deletes an original record. A valid existing receipt is read-only `ALREADY_RECORDED`; an incomplete, contradictory or unsafe receipt is preserved and refused. There is no repair-in-place or delete-and-retry path.

The canonical status projection applies only to this exact original terminal failure. It freshly validates historical evidence and the receipt; it exposes the bound root and scoped execution absence while retaining `TERMINAL_FAILURE`, `rc=78`, `signal=prelaunch_failure`, no result, unverified acceptance, no same-run replay and no retry. Invalid proof or receipt yields unreadable status rather than a qualified root. The ordinary request existing-ID guard, acceptance gate and quota-successor eligibility remain unchanged.

The Studio facade's general outer `execution_absence_proven: false` behavior is unchanged. This source does not make a generic facade retry permission. New work must still pass ordinary admission and applicable review/release gates; the original failed review cannot be transformed into a review of the newer News head.

### Interrupted publication and acknowledgment

A failure before receipt creation is attempted is `NOT_APPLIED`. Once creation is attempted, any publication or retained-descriptor cleanup exception is `EFFECT_UNKNOWN`. This conservative scope includes exclusive-create races, short writes, fsync failures, readback failures, identity changes and context cleanup.

After the operation returns, successful response delivery requires JSON serialization, the stdout write and an explicit stdout flush to complete inside the response-delivery handler. A buffered write alone does not establish delivery. Failure is `RETURN_UNDELIVERED` with `EFFECT_UNKNOWN`; it cannot be relabeled `NOT_APPLIED` or followed by another success response. Failed stdout is disarmed before returning so ordinary interpreter shutdown does not retry delivery to that channel. This does not undo a receipt that may already exist. Fresh canonical status remains the supported way to establish the currently visible receipt and original evidence.

A subsequent fresh read through the same canonical status owner may settle a complete, exact, currently safe receipt together with freshly validated original evidence. That later observation does not prove that the earlier failed call completed fsync, readback, acknowledgment delivery or durable storage. A partial or changed receipt never qualifies. A same-byte replacement can correctly cause the original writer's inode fence to refuse while a later independent reader qualifies the currently visible receipt under the same contract. No blind mutation retry or extra journal is introduced.

## Source qualification evidence

The focused fixture suite passed 28 tests on 2026-10-21. These use private disposable evidence and inert historical source bytes; fixture allowlist substitutions do not modify production constants. Coverage includes custody and source falsifiers, late directory permission changes, original-result contradictions, full failure-state isolation, no acceptance/replay/quota continuation, exclusive publication, partial writes, same-byte replacement, changed original evidence, unsafe receipt schemas, fsync ambiguity, descriptor cleanup failure and acknowledgment output failure.

The last two acknowledgment cases were first reproduced failing on the prior source, then passed with the outer creation-attempt scope and separate response-delivery handling. The final existing adapter, foreground continuation and prelease-cooldown regression run passed 14 tests against the final adapter source, separately from the 28 focused tests.

At `2026-10-21T10:39:22.631586+00:00`, a read-only diagnostic used production checker SHA256 `d93ac70ecd26cc4265fa511f4aaeb8715d0ab38fe3f2a12479086ec352af5edd` against the actual original retained records and both immutable generations. It returned proof SHA256 `7f0ea70b4cc7ab028a311d41b24fc883b6fc7d29401f1f2b46d6537c90785167`. All eight original artifact hashes and full file identities matched before and after. The reconciliation receipt was absent both times. This is read-only source qualification, not installed command or recovery completion evidence.

The reviewed 85-file source stage has manifest SHA256 `13c7336b6d34a37cce4a7c99734b51e58808d787299adac00fcd96389c6981f7` and source inventory SHA256 `68acab1d73c0d17ab4819803dd9e84d864e1e055bfc76f7ce87a7284504ff419`. The canonical stage builder regenerated both records; all 85 staged file digests matched. The composition test now derives its reported file count from the actual inventory and expects 85, while retaining independent executor/support/donor identities.

## Release dependency and remaining gates

This source branch starts at protected Mastermind `2151a89f7ea3a340ec04932cbcfdf6a838df79b1`, the merged old #1661 head. Its base helper is `ca28c22c060588436a593d6ba42f66ebe2be6c0093c5c68a14e9ee070788031b`. It does not yet contain the combined provenance and private transport-observation repair in draft [PR #1665](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1665), head `73eefe48d3ca0acf56fbcf6a015c90ba54492ac2`, helper `737744a8f04d6d6331d9aa541dfa2d0b40bf6360a8d36ef53dea958527d36767`.

Do not select this source stage over the current native generation. Release must compose the protected merged #1665 repair, this recovery owner and any intervening material protected source changes, rebuild the explicit native closure, qualify the resulting exact source and runtime, and use the incumbent immutable-generation publish/verify/select owner with its expected-current-generation fence. The source stage above is review evidence only.

Required remaining gates are exact-source review and CI, applicable protected merges, composed generation qualification and selection, a fresh installed read-only check, the explicit original-case reconciliation, and canonical readback proving the original failure and no-retry/no-acceptance limits remain. Only then can the separate current-head News review and production release gates advance according to ordinary admission. Neither this source nor historical absence qualifies the unrelated repair review's later M1 transport refusal.

Principal C3 performed this exact historical evidence and recovery-boundary work as `PRINCIPAL_JUDGMENT`. An independent native C3 architecture assessment identified the late-directory and acknowledgment gaps addressed here. The final read-only architecture assessment found no remaining must-fix findings in reconciliation SHA256 `0bd35e8f9256e34881fe6a47b5a9698bbf8d36cc415c110a4c6228ed1f59f0a0` and adapter SHA256 `91d93adbb2f4fa5caca9b9f04409c037721ceea67fcb819b358158ed827b9046`. That advisory is not either frozen paid review result or a formal GitHub approval. Paid-worker source reviews, actual protected release, native rollout and signed-in production News acceptance remain separate evidence requirements.

## Combined source with the physical-owner repair

The original recovery branch now materially composes published repair commit
`5f9fa66158691fd1a0a1e1464f9e7a60fde7ca5c` from PR #1665 with the recovery source
at `d7736aea141d42eea21088c31a9ab363916869be`. Both original managed branches and
failed-review identities remain in place. This is source integration only.

The production source files, manifest and inventory combined without conflict.
The sole merge conflict was the composition test's explanatory comment and
manifest pin. Resolution retains `EXPECTED_NATIVE_FILES = 85`, the exact
recovery checker/reconciler/adapter bytes, and all final repair controller,
helper and Qwen bytes. The canonical stage builder reproduces both declarations;
all 85 hashes match. The other 80 repair-generation files are unchanged, and the
three recovery-owned entries are exact `d7736aea` bytes.

- Combined manifest SHA-256:
  `8ac0048aa2f40a19bddb30792a64b33b61a5409d2f62b8906acc211ae0f62fe0`.
- Combined inventory SHA-256:
  `1dcf91f81aa49453a08f391a2bc19d61e62771e426e710977904cdab04693883`.
- Controller:
  `2cb93138d446c5fe7cfaf42cfa8f8e731882eb726108a0eacf2ddd6fcbef9f7f`.
- Helper:
  `81fff3ccc471c972d29926b2a10020ef4856d2c6585d4dc30e41633ed65a25df`.
- Qwen:
  `033bf388c4b3ea4cd5e4161c3c558b39a3a9d9bc80a5d7bce85b8b85a29ec1dd`.

The combined source passes **41 tests**: all 28 historical-proof/reconciliation
tests and all 13 physical-owner tests. The recovery adapter's preceding 14
regressions and repair's preceding 12 controller/retention plus 17 credential
regressions refer to identical component bytes. Syntax, staged and unstaged
diff-whitespace checks also pass. No production receipt or native generation
selection was changed by these tests.

The old standalone 85-file stage and its green CI are historical qualifications.
The combined commit requires its own exact-head CI and full independent review.
The initial dependency description above is retained as history; source
composition is now complete, while protected merge and rollout remain pending.
Do not install a review stage. Release requires protected reviewed source,
fresh current-generation and host preflight, immutable publish/verify/select,
then the installed original-owner check and explicit reconciliation. Neither
this composition nor a new review of its genuinely changed source alters either
frozen historical reviewer or supplies a review result for its old subject.

## Follow-up acknowledgment and acquisition qualification

The composed candidate also includes the acquisition-tag correction described in
`PLAIN_PACKET_SAME_PATH_REPAIR_20261021.md`. That section records the final
85-file manifest, inventory and changed-member identities. Earlier hashes and
test results above remain evidence for their named historical bytes.

The success-response boundary now includes an explicit stdout flush. A real
closed-pipe subprocess demonstrated that catching the flush failure alone is
insufficient: `main()` returned 78, but Python retried buffered output during
shutdown and the process exited 120. The failure handler now disarms the failed
stdout channel before returning. For a descriptor-backed stream it redirects that
descriptor to the null device; for a stream without a usable descriptor it clears
the current stdout reference without closing the caller's retained object or
assuming another descriptor belongs to it. This is best-effort failed-stream
cleanup, not another reconciliation or another success response. The real-pipe
qualification assumes usable stderr and does not guarantee arbitrary simultaneous
standard-stream or OS cleanup failures.

The final `test_native_plain_packet_check` suite passes **30 tests in 3.611
seconds**. The real subprocess regression first failed with the observed
`120 != 78`, then passed with this cleanup. It proves both healthy and broken
stdout controls, one actual reconciliation call, one completed real JSON write,
normal interpreter shutdown, preserved receipt digest and full identity, and fresh
status retaining failure 78, no result, unverified acceptance, no replay and no
retry. The existing no-fileno flush-failure control keeps its retained stream
inspectable and receipt unchanged.

The evidence records are
`/tmp/news-1674-stdout-child-before-20261021.json` and
`/tmp/news-1674-stdout-disarm-qualified-20261021.json`.
No live original receipt was created by these tests. Test allowlist substitutions
exist only within disposable fixtures and leave production case constants intact.

The artifact-observation CI wrapper now invokes the original collector
compatibility script against the explicitly built staged `ext` path. This makes
current consumer and preserved historical evidence checks part of the same
required source gate. The historical proposal source is unchanged.

Exact-head independent source review and CI must qualify the published follow-up.
The source holds on earlier d151/b301/5f9 bytes are not discharged by local tests.
No rollout, original-case reconciliation, lease settlement, frozen review result
or production News acceptance is established here.

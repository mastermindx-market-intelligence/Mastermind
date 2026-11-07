# Clean linked sparse donor — security repair, 2026-10-18

STATE: REPAIRED_SOURCE_FOR_REVIEW / LOCAL_TESTS_PASS / NOT_MERGED / NOT_DEPLOYED.
MISSION_COMPLETE: false.

This record supersedes the earlier candidate and isolation claims in this file.
PR [#1404](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1404)
and its existing branch remain the source carrier. No worker, provider, lease,
cleanup owner, source writer or runtime binding is transferred by this document.

## Original independent review consumed

The retained result of `ghost-parent-fabric-linked-donor-review-ba3938-20261017-02`
was read through the installed original `fabric_task.read_result` mechanism.
Its SHA-256 was verified as
`157b2bf2a767e3264af3c40469ea1d31a2d55989aedf375361730ab5948feea2`.
Original root and parent remain
`ghost-parent-handoff-validation-20261017-sol-001`.
The run is TERMINAL, rc0, with retained bytes; its source verdict is
**CHANGES_REQUIRED**. It was not restarted or duplicated.

Reading a result does not accept it. At recovery the original ledger projection
was **NOT_ACCEPTED / NO_OUTCOME**. On October 18 the assigned continuation CEO
Integrator reverified all 14,371 retained bytes and the verified terminal
root/parent identity, then adjudicated this review deliverable through the
incumbent `pool_ledger.record_outcome` with strict durable acknowledgement.
The same-run readback is **ACCEPTED / VALIDATED_OUTCOME**, `accepted_by=reviewer`,
with the original root and parent unchanged. This accepts the useful returned
review; **CHANGES_REQUIRED** remains its verdict on the old source. No worker
operation was restarted, reparented or duplicated. The local ledger projection
does not authenticate an original-parent callback or itself attest result bytes;
the delegated CEO adjudication and independent byte verification are stated
separately. It is not source, deployment or real-worker acceptance.

The reviewer identified controller-side Git configuration execution, hidden
working-policy changes through assume-unchanged, missing real workspace-function
coverage, an unreachable donor-drift branch, and misleading provenance/isolation
claims. The old source head `ba3938c79eedbb8f590dfed106b8e0876ee88e91` and its
passing CI are not acceptance evidence for this repair.

## Exact source contract

| Item | Immutable identity |
| --- | --- |
| Source parent for this repair | `ba3938c79eedbb8f590dfed106b8e0876ee88e91` |
| Immediate parent of the Gitlink follow-up | `ae58437d2ad6520f7413223fa17a35fd6cc64f4d` |
| Sealed executor preimage, M2 carrier | SHA-256 `a29798abb84294b1d8a67c53ef2b45137db4517f960598e51c8da21796d6cf61` |
| Repaired executor postimage | SHA-256 `131f56a4c26915d9e6a5fc6501f930b3aeeb5e4c4501eb730b080e0c6dde5772` |
| Shipped one-file patch | SHA-256 `dbcc9b8938781cc18f3da0fdfe5bad8ee5693c89873f68260e33a8c44339ce95` |
| Eligible old helper | Git blob `296e47bab2d28f9a019e81b5aef76eeea62a6cc3` |
| Reviewed helper | Git blob `75297acb10d0cef4d01730a59fdcad19c7cfd3e6` |
| Reviewed working policy | Git blob `46b4d13bb5302a68b437a257eebe066d07bdc7ff` |
| Dedicated donor HEAD | `6ee058b0491a3f67e843f25d4379b94e98880e8b` |
| Dedicated donor path | `~/lanes/repos/macro-fabric-pinned-20261016` |

The helper and policy identities were independently fetched from
[the pinned Macro source](https://github.com/mastermindx-market-intelligence/macro/tree/6ee058b0491a3f67e843f25d4379b94e98880e8b).
The old `macro-fabric-reviewed` / `40abd9bd...` alternate was a superseded
candidate assumption and is not selected.

### What the patch changes

The controller resolves Git metadata through bounded stable file reads before
its first donor Git invocation. It verifies ownership, regular-file/directory
shape, non-symlink ancestry, linked-worktree backpointers and the original common
Git directory. Group/world-writable paths refuse; validation never changes their
permissions or source bytes.

A strict, data-only Git config subset is accepted. Common and worktree config are
both checked, including an inactive worktree config. Includes, aliases, fsmonitor,
hooks, pager, editor, SSH commands, filters, protocol settings, repository
redirection and unsupported or ambiguous syntax refuse before Git. The existing
partial-clone metadata, multiple fetch refspecs, branch bindings, and inert LFS
repository-format marker are recognized as data. No actual fetch is authorized.

Controller Git uses the fixed system executable and explicit fsmonitor/hooks
neutralization. Its environment removes inherited `GIT_*` and loader overrides,
suppresses system/global Git config, disables replacement objects, and denies
every transport. The empty `GIT_ALLOW_PROTOCOL` allow-list also protects Git
versions predating `GIT_NO_LAZY_FETCH`; missing local objects must refuse.
Those older versions may first create an internal Git fetch child
([Git 2.43 source](https://github.com/git/git/blob/v2.43.0/promisor-remote.c));
transport denial does not prove that no child process was created.
The same protections and fixed system search path reach the actual mint
invocation, whose pinned helper uses bare Git subprocesses. Original root,
parent, provider and lease values are retained; the subsequent worker environment
is not rewritten by the mint helper.

Both consumed inputs must match their independent pins in HEAD, a stage-zero
index entry with neither hidden flag, and a stable no-follow working-file read.
A clean-looking status is insufficient. Helper and policy identities are checked
again after mint; drift preserves an uncertain effect.

The follow-up independent native semantic assessment of `ae58437d...` identified
another configuration boundary: ordinary status can enter an initialized
submodule with separate, unqualified local configuration. The repaired index
qualification refuses an observed Gitlink (mode `160000`) before status,
including staged entries. A collapsed sparse-index directory is allowed only
when its complete path is provably absent; a materialized child cannot qualify
through that exception. This refusal does not recursively trust child repository
configuration. Two inert actual-workspace-function cases cover direct and linked
donors and fail immediately if status or mint is reached.

Requalification failure now reaches `FABRIC_SPARSE_REVIEWED_DONOR_DRIFT` with its
original cause and effect-unknown flag. Unconfirmed Git-process cleanup and a
forced observation abort are typed uncertain effects: reaping the direct PID
alone does not prove settlement of possible internal children. The executor's
existing `_execute` section—including
physical lease acquisition, provider launch and hold-for-reconciliation—is
byte-identical to the sealed preimage.

### Explicit disposition required: sparse index flags

The review's blanket wording to reject every skip-worktree flag conflicts with
the intended sparse donor: [Git uses that flag for omitted files](https://git-scm.com/docs/git-sparse-checkout).
This repair proposes the following narrower, explicit invariant for renewed
independent review. It does **not** claim literal compliance with the old wording.

| Observed condition | Admission |
| --- | --- |
| Any assume-unchanged tag, including combined lowercase `s` | Refuse |
| Observed Gitlink entry (mode `160000`), including a staged entry | Refuse before status |
| Helper or policy has either flag, wrong stage, or mismatched HEAD/index/disk bytes | Refuse |
| Uppercase `S` on a materialized object, required-cone path, or uncertain absence | Refuse |
| Uppercase `S` on a provably absent path outside the independently fixed donor cone | Permit |
| Sparse-index directory entry | Apply the same excluded-and-absent rule to the directory |

The dedicated donor cone is exactly `.claude`, `.codex`, `config`, `scripts`,
plus Git's top-level-file semantics. The complete canonical rules were observed
on both Ubuntu1 and Ubuntu3 through a read-only original-M2 metadata probe:
[retained metadata receipt](CLEAN_LINKED_DONOR_METADATA_20261018.json).
The helper's pinned JSON policy instead excludes `data`, `site`, `mockups`,
`verify_shots` from **new worker worktrees**. These are distinct profiles.
Validation neither broadens nor rewrites either donor.

The direct reviewed-helper path also qualifies its config, input pins and index.
A full original donor has no permitted skipped entries. A sparse original donor
must match the pinned worker-policy profile. Existing unknown or dirty source
refuses; only the exact earlier helper selects the separately qualified donor.

## Scope of isolation

[Python `-I`](https://docs.python.org/3/using/cmdline.html#cmdoption-I) excludes the
script directory and user site and ignores Python environment variables.
It does not exclude interpreter-wide site-packages or sitecustomize, and it
does not establish an OS sandbox. This patch assumes a trusted system Git,
interpreter and OS account boundary. Stable reads, config rechecks and byte pins
harden admission of pre-existing donor contents; they are not an atomic lock
against a concurrent adversarial same-UID writer. Such a stronger threat model
requires an independently approved isolation boundary.

## Reproducible tests and limits

[The portable suite](../../../tests/test_fabric_clean_linked_donor_20261017.py)
applies the shipped patch to
[the exact test-only preimage](../../../tests/fixtures/fabric_executor_m2_a29798ab.py.txt),
checks the postimage hash, compiles the applied source and calls its actual
`_new_macro_workspace`. It no longer tests only an extracted donor selector.

**66 behavioral/source-contract cases passed**, and **90 tests passed** across
the six affected root test modules on Linux, Python 3.12.14, with Git 2.43.0
and Git 2.55.0. The latter uses an isolated build of the official Git tag with a
test-process executable remap; production retains the fixed system Git path.
Coverage includes full/sparse indexes, direct/fallback source paths, inert
configuration refusals before Git, Gitlink refusal before status, independent policy/index/byte pins, actual
`-I` arguments and Git environment at the owned-process boundary, second-pass
helper mismatch, reachable drift, duplicate-effect refusal and uncertain cleanup.

The owned-process runner is a stub that creates a genuine disposable linked
sparse Git worktree. This tests controller behavior and Git postconditions;
it does not prove the actual Macro helper process, physical admission, production
receipt, provider START or accepted worker result. No executable security payload
is run. Protected CI and independent review must bind the newly published head.

The historical [actual Macro mint script](tests/test_actual_macro_mint.py) exists
under this integration directory, not root `tests/`. It requires privately
staged executor/helper files and installed M2 dependencies, so it is not a
self-contained checkout test. Prior M2/Ubuntu3 7/7 observations belong to older
candidates and must not be presented as execution proof for this repaired head.

## Correct runtime provenance and release frontier

`a29798ab...` identifies the **sealed support-release executor preimage carried
by M2**, also read back from the incumbent M2 executor. It does not identify
Ubuntu3's legacy `~/lanes/ext/remote_sub_exec.py`. The independent review observed
that flat copy at `98407dbd...`, without the sparse-mint section; this patch
does not apply there. The actual launcher uses
`~/lanes/support-releases/$SUPPORT_DIGEST/ext/remote_sub_exec.py`.
Release must use the existing publisher and full 31-file dependency closure,
with exact preimage qualification and a new immutable generation.

The old postimage `49862414...`, patch `32773b36...`, and private offline
generation `303b4455972fb0541efbbb6ce09934d3a7a0dc4cfc4e294d9be6a4f559303676`
are superseded for this repair. Earlier generations `93901a25...` and
`8eeb04e0...` remain historical evidence. None may be relabeled as repaired.
The subsequent private `e377f8e4...` generation `9dd98999...` and positive actual
helper proof cover its earlier production bytes; the Gitlink follow-up changes
the executor again and requires a new generation and proof before deployment.

The old statement that Ubuntu3 currently had staged security-master edits was
stale: the reviewer observed its legacy feature donor clean at `bf5b534c...`.
That observation grants no overwrite, reset or branch-conversion permission.
Ubuntu1's original dirty source and all other incumbents remain preserved.

The October 18 metadata read also found group-writable source inputs on
Ubuntu0/1/2. The candidate correctly refuses those paths until their original
custody permits qualification; no permission normalization was performed.
Subsequent data-only ancestry reads found additional directory holds on
Ubuntu1/2 and Ubuntu3 (`~/lanes` mode `0775`), so all four hosts have recorded
qualification holds. That separate receipt is retained on M2 as
`/Volumes/Mastermind/evidence/ubuntu-fabric-audit-20261015-sol-web-01/DONOR_DIRECTORY_QUALIFICATION_E377F8E4_20261018.json`.
The read-only receipt is not an all-host admission or deployment claim.

Required next evidence remains: independent semantic approval of the repaired
immutable head, explicitly covering the sparse
exception and threat boundary; protected CI and merge; a newly published and
verified support generation; host binding; and real admitted original-worker
START/result/acceptance witnesses. The installed Session Bridge was unavailable
during recovery, and Executive visibility reported new CEO submission unarmed.
Those observations do not authorize an alternative queue, worker root or
shell-based worker submission.

Configured ceilings remain **12/18/12/12**, with Ubuntu2/3 **80°C** new-job
temperature admission and existing disk/load/PSI/provider protections. The
accepted 13-file registry-hardening patch and its 259-test historical proof are
preserved. No old thermal, sparse or combined patch is replayed. The earlier
rc78 review and Ubuntu1's platform-blocked security-patch staging remain
nonretryable. Unaccepted worker data and uncertain effects remain with their
original owners. Macro GC #9430 and Web MCP #1457 retain separate ownership.

# Plain packet same-path retention repair

## Named consumer and observed defect

Macro News Dashboard PR #9612 requires independent review of immutable source
`3a663ae70ecbd8a4130de9c95dbb6d940d181e04`. The existing original Fabric request
`news-9612-exact-3a663-release-review-20261021`, rooted at
`news-cockpit-rebuild-20261018-astra-01`, returned controller rc78 before the
reported lease phase. The request owner had already retained its original
`<run>.request.packet`; the native plain Qwen/GLM retention block then attempted
exclusive creation of that same pathname and raised `FileExistsError`.

The observed installed helper and protected candidate agreed at SHA-256
`f6ae11dc1e320506efc950fc4bc7a352af34e52b67887d901b35274034dcf48b`.
The original request packet was not removed or rewritten, and no replacement
reviewer was dispatched. Canonical status reported no result, unverified root,
`execution_absence_proven=false` and `retry_allowed=false`; the local before-lease
trace does not override those classifications.

## Bounded correction in the existing owner

Only `candidate/remote_sub.sh` changes production behavior. A source path that is
also the exact absolute retained path may be reused without writing, but only
when it remains a same-user regular file with mode `0600`, one link, bounded
length and the exact observed bytes. Device, inode, size, mtime and ctime must
match the initial source observation, both verification fstats and the final
non-following path stat. The verification descriptor retains `O_NOFOLLOW` and
`O_NONBLOCK`.

A different destination still requires exclusive creation. An existing distinct
file is refused even if its bytes match. Source/destination symlinks, permissive
permissions, hard links, empty/oversized input and detected replacement/content
races remain refused. The new branch does not authorize any request retry,
change root/run identity, create another retention owner or relax acquisition,
transport verification, lease, capacity, provider, deadline or acceptance rules.
The declared manifest and source inventory update the same one helper; installed
preimage identities and the other generation members remain unchanged.

## Verification boundary

The new actual-Bash controller regression reproduces the wrapper's retained
pathname. It failed on the original candidate with the observed `FileExistsError`.
The repaired candidate must preserve the packet inode/mtime/hash and complete
exactly one inert acquisition/transport/launch sequence in the established test
harness. These harness executables never invoke a provider or real SSH transport.

The actual heredoc also has a thirteen-case matrix, including successful fresh
and same-path reads, untouched refused pre-existing files, and deterministic
post-source-read replacement/content-change faults. The prior standalone
proposal exercised original and proposed code in 26 isolated executions and
passed `bash -n`; this is not a substitute for the canonical controller suite.

The initial local suite under the external-volume test directory exposed the
existing strict directory-custody rejection and wall-clock deadline failures.
They are retained in the delivery evidence rather than weakening directory
checks or timing assertions. The existing `NATIVE_ROLLOUT_TEST_ROOT` hook allows
a private fixture root under the current user's home; it changes test placement,
not runtime permissions. Exact final test results belong in the PR receipt.

## Installation and recovery hold

This is source-only until protected review/CI/merge and the existing immutable
native-generation rollout are qualified. Do not patch the installed generation
in place, change its selector, delete the original packet, replay the failed
request, invent a completed review, or use a new run ID to bypass its recovery
state. After a qualified rollout, the original runtime owner must reconcile that
same failed request through its supported recovery authority before retry.

The News source stays on its original clean branch and its successful hosted CI
is not production acceptance. Actual signed-in News behavior remains a separate
release proof, including the Browser connector's originating-context requirement.

## Source qualification on 21 October 2026

The retained-request controller regression, ordinary distinct-packet controller,
mutated-transport refusal, thirteen-case retention matrix and existing content
observer reconciliation suite passed: **10 tests and 13 subtests**, using Python
3.12 and the existing private test-root option. The actual canonical review-stage
builder succeeded; all **83** staged files matched their declared hashes, and
both generated manifest/inventory files were byte-identical to the committed
source declarations. `bash -n` and `git diff --check` passed.

The wider local three-module run is **not green**: 54 passed, 34 failed and one
setup error before refreshing the exact manifest pin, with 29 passing subtests.
The new packet-retention cases passed. Two real-clock deadline assertions failed
on the local host. The separate donor/executor suite encountered the existing
`FABRIC_SPARSE_GIT_OBSERVATION_UNQUALIFIED` boundary: the selected local Git emits
a sparse-index-expansion advisory on stderr, which its unchanged strict reader
rejects. The immutable manifest pin was then updated to the actual new declared
manifest. A final targeted run including that executor seam yielded 10 passed /
13 subtests passed and one remaining donor/executor failure with the same Git
observation refusal. Neither the Git stderr guard nor the deadline assertions
were relaxed, and the executor/transport source bytes are unchanged.

The first standalone stage verifier incorrectly checked `output/name`; the
existing builder emits `output/native-code-stage/name`. The corrected verifier
passed all 83 identities without any product change. These failed/local controls
are kept in the retained diagnostic directory; they are not omitted from the
candidate's qualification. Hosted checks and independent source/security review
remain necessary before protected merge and any installed rollout.

Source manifest SHA-256:
`e327073b35955ae88d6c78514f6d097c77a4356c4719e9fa9e7a8226b9d56bdf`.
Source inventory SHA-256:
`b55e4160a863989f0b74df8c5f0c5df95bec5353c319c00c151ff55bdca9dc17`.
New helper SHA-256:
`ca28c22c060588436a593d6ba42f66ebe2be6c0093c5c68a14e9ee070788031b`.

The first typed source acquisition returned NOT_APPLIED with a bounded local
Git-observation failure. After the same owner's read recovered and confirmed no
registered workspace, the same operation was acquired again. Its incomplete
return was reconciled through the original owner's status: clean expected base
`b66e64ad57b50f77253eeacf62ac72dc165a50aa`, original operation
`news-review-packet-retention-20261021`, derived branch and canonical workspace.
No replacement acquisition, raw clone/worktree or source-binding override was
used. That acquisition uncertainty is reconciled; the failed News reviewer
request remains terminal and is not retried by this source repair.


## Combined provenance and transport correction — 21 October 2026

The later release hold in PR #1661 comments 6311037384, 6311165775 and
6311299356 superseded the first candidate's merge eligibility. Emergency selected
generation `4f0f6055f8c03321acbbfad41675135ea6e4ac50012f8d13435acbb4c52d4fbe`
(sequence 11) contained positive request/launch provenance and a private
transport-observation path that the original PR did not. The source integration
uses its observed helper SHA-256
`d3a019db361fcebb7d92b40d65c4624d2baad0868f1d33e1570885fee7e9a1c0`
as a comparison input, not protected release authority.

The combined candidate retains the original packet inode/content protections
and exclusive distinct-destination creation. Same-path reuse now also requires
the original request and launch reservation, exact run/root/parent identities,
packet name/length/digest, request digest, and reserved launch state. Root and
parent must be nonempty identifiers matching the incumbent grammar. Both JSON
records must have unique keys; packet length must be an integer, not a boolean.
Metadata files must be same-user private single-link regular files. Descriptor
and visible-path identity are compared immediately after each read and again
after the complete joint provenance and packet validation, including mode,
owner, links, inode, size, mtime and ctime.

The transport-observation temporary file moves from the ambient temporary
directory into the original controller run-state directory. Unique creation,
controller cleanup and the unchanged strict transport reader remain in force.
No lease, route, provider, deadline, executor or acceptance behavior is relaxed.

Focused qualification includes the original 13 custody cases plus 35
provenance falsifiers, actual Bash refusal before acquisition without original
reservations, valid same-path preservation, and a replaced transport-observation
refusal before launch. The external-volume test root exposed its existing
group-writable ancestor rejection. With the existing private-home test-root
option, the four negative/matrix tests passed; two successful-controller cases
reached verified transport but exhausted their unchanged eight-second deadlines
on this host. The repository deadline assertions were not changed.

A separate, explicitly labeled 20-second functional control passed the ordinary
plain controller, same-path retained controller and replaced-observation
refusal. A first supplemental assertion incorrectly assumed the inert SSH
process's stdout was the observation file; the owned runner actually captures
a pipe and forwards its output. That test-only assumption was corrected. The
successful retained path verifies its original inode/mtime/hash, one inert
acquire and launch, a mode-0600 observation under the original state directory,
strict transport verification and temporary-file cleanup. These controls do
not turn the eight-second local run green; hosted exact-head CI remains owed.

The canonical stage builder verified all 83 declared files. Only
`ext/remote_sub.sh` differs from the original PR generation; the other 82
identities and installed preimages remain unchanged.

- Helper SHA-256: `737744a8f04d6d6331d9aa541dfa2d0b40bf6360a8d36ef53dea958527d36767`.
- Manifest SHA-256: `ac2b2272980341788f51ea3d374a9b1bd4a69a92f63690de994babfc48d30933`.
- Inventory SHA-256: `0354255324bf0a238fd761e5a3d28376c479df26941045134dce8f9f51a91ccc`.

### Source carrier after concurrent landing

Fresh GitHub evidence reports original PR #1661 merged at 09:29:50 UTC as
`2151a89f7ea3a340ec04932cbcfdf6a838df79b1`, retaining old head `9188c6ab...`;
its remote branch was then deleted. That landing does not contain this combined
delta. The original local operation, workspace and branch preserve the new
source for a follow-up protected PR; no source re-homing is needed.

This candidate still needs independent source/security review, hosted checks,
protected merge and canonical immutable rollout. The selected generation was
not modified. Original News reviewer `news-9612-exact-3a663-release-review-20261021`
remains terminal with no accepted result and no retry authority. No supported
historical reconciliation edge has yet been qualified for that failure; this
source repair grants neither same-run replay nor a replacement News review.

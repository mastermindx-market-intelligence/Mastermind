# Plain packet same-path retention repair

This document retains the successive source qualifications. The final physical
publisher-owner follow-up below is the current proposed contract for PR #1665;
earlier identities and test results are preserved as history.

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

## Physical publisher-owner binding — final follow-up in PR #1665

### Original transport evidence and scope

The paid review of immutable head
`73eefe48d3ca0acf56fbcf6a015c90ba54492ac2`,
run `news-1665-73eefe48-source-review-20261021` under the original News root,
failed with `TRANSPORT_READBACK_REFUSED rc=1 before_launch=1`.
Its original controller receipts show successful setup, packet/support uploads
and support publication, then a strict directory-reader failure:
`NotADirectoryError: lanes`. There is no launch-binding or launch process row.
This does not by itself prove complete effect absence or lease settlement.

The unchanged publisher already returns a resolved physical release path. Its
observed stdout named
`/Volumes/STORAGE/Offloaded/m1-20260917/lanes/support-releases/3d98030cf7f7b11336b43105591e618e9bfc8c39272b978a03b4d5e7029a56a7/ext`.
The old controller discarded that return and reconstructed the readback path
through the home-directory `lanes` alias, which the strict reader correctly
refused. The source correction belongs to that controller path binding.

Original evidence remains immutable: packet SHA-256
`e589b278572636d78d4c1cee4549beece5fe20636dea048e8db10a9bf2999733`
(15,367 bytes); controller-process SHA-256
`60f5ecd886cd9d49ceb188899593d687723789bbebe417d1e230f65a11adc086`;
log SHA-256
`3ffa9683a4995b01e3f6361103b09081a8ef16f04a364811b32ba55ed4dc5bbc`.
The observed launch bound installed helper `d3a019db...`, not the new candidate.
The broker acquire return was not retained, and its exact lease settlement is
unestablished. The failed review stays frozen with no result or retry authority.

### Forward source correction

For a newly admitted, parented ordinary plain GLM/Qwen run, the controller now
captures the complete publisher return in an original-state-directory private
temporary file. The helper requires one bounded UTF-8 newline-terminated
absolute normalized path, the exact support digest and final `ext` component.
Traversal, duplicate/noisy/truncated output, controls, a root owner and colon
spellings are refused. Colon cannot be a literal single entry in the required
PATH prefix. This parser supplies path data, never executable shell input or
admission authority.

The physical owner is quoted once and fixed through strict readback, executor
selection, host environment, launch cwd, retained packet/control paths, polling,
collection and cleanup. Requested task `REMOTE_CWD` is unchanged. The existing
`DirectoryChain`, receipt v1 schemas, lease/account and launch-binding gates
remain unchanged. There is no generic symlink-following exception or alias
fallback after binding.

Qwen previously replaced its release-relative provider configuration with the
home alias on every leased call. Only the new bound Qwen route now retains
`$HERE/../codex_bailian`; the incumbent publisher already binds and verifies
that link. A literal controller-owned scalar distinguishes this route, is
explicitly zero on other paths, and is consumed/unset before the provider child.
The exact leased account, credential owner and private per-run config/session
copy remain unchanged. GLM's existing release-relative configuration home is
unchanged.

Collection uses `--rsync-path` to enter the same fixed quoted physical owner
with `cd ... && exec rsync`, then requests ordinary relative artifact names.
Default rsync argument and sender checks stay enabled. Actual local protocol
tests found that upstream rsync 3.2.7 preserves the command text while Studio's
openrsync (protocol 29, 2.6.9 compatible) removes an extra quotation layer.
The same local rsync executable therefore supplies bounded private whole-output
version evidence through the existing commission deadline. Exactly one known
identity on the first line selects the tested quoting convention; openrsync
receives one additional quote around the complete command. Unknown, empty,
ambiguous, malformed or failed version observations refuse before launch.
This is dialect selection, not binary authentication. No alternative executable,
network probe or `--old-args` downgrade is used.

Legacy modes retain their existing paths. Every optional array expansion uses
the existing Bash 3.2/`set -u` compatible guarded convention.

### Qualification and limitations

- Exact old `73eefe48` controller bytes
  (`737744a8f04d6d6331d9aa541dfa2d0b40bf6360a8d36ef53dea958527d36767`)
  reproduce strict readback refusal with zero worker launches in the private
  fixture.
- **13 new tests pass**. The actual controller and strict reader exercise flat
  owners, symlinked home aliases, alias retargeting after publication and before
  launch, unsafe packet/parent/code evidence, malformed publication, and
  unqualified rsync versions. Transfer uses the actual installed rsync protocol
  through an inert local remote shell. Paths include spaces, apostrophe and
  shell-substitution-looking text; decoy artifacts remain untouched.
- The actual Qwen selection and private copy path consumes owner A's harmless
  configuration after the legacy alias points at B. Marker absent/zero preserves
  legacy B selection. Its private file is mode 0600, exact fixture account is
  preserved, and the marker does not enter the provider child.
- Separate actual openrsync and rsync 3.2.7 protocol controls pass literal
  apostrophe/space/`$()`/backtick owner paths and refuse a missing owner without
  creating a destination. No real SSH host, model, provider or lease is used.
- **12 existing controller/retention tests pass** on the final source, including
  the unchanged original timing budgets. The 13 custody and 35 provenance
  falsifiers remain included. **17 existing credential-custody tests pass** with
  the final unchanged Qwen wrapper bytes.
- All **83** staged files match their declarations. Relative to `73eefe48`,
  only `remote_sub.sh`, `remote_sub_helpers.py` and `qwen_exec.sh` change executable
  identity; the other 80 files and installed preimages are unchanged. Bash
  syntax, Python syntax and diff-whitespace checks pass.

Failed interim controls are retained. Before the final corrections, two real
openrsync cases failed at collection because the first implementation lost a
quotation layer. A concurrent 29-test existing-regression run had three failures:
legacy empty-array collection plus two host timing/admission failures. The final
guarded array and sequential 12-test run pass without relaxing timing or custody.
Earlier wider local qualification failures documented above remain historical;
this focused result does not assert that every wider local suite has passed.

The physical binding defeats home-alias retargeting. It does not claim protection
against a trusted owner replacing the physical ancestor between phases.
Host-owned `HOST_ENV`, legitimate credential-config overrides and executable
resolution still require bounded nonsecret qualification during the actual
rollout. No `HOME`, `GLM_CONFIG`, credential or profile owner is remapped here.

### Frozen source identities and release obligations

- Controller SHA-256:
  `2cb93138d446c5fe7cfaf42cfa8f8e731882eb726108a0eacf2ddd6fcbef9f7f`.
- Helper SHA-256:
  `81fff3ccc471c972d29926b2a10020ef4856d2c6585d4dc30e41633ed65a25df`.
- Qwen wrapper SHA-256:
  `033bf388c4b3ea4cd5e4161c3c558b39a3a9d9bc80a5d7bce85b8b85a29ec1dd`.
- Manifest SHA-256:
  `1ac452a986ba33f1d238d8874956451b6a9fc04fe0cbcc1da1db70110498bb2d`.
- Inventory SHA-256:
  `a59c69e88dc537213e3f80bfcbcdb3c5f662f5513401db96ec39ddc92804a32a`.

Principal architecture/security review found no remaining concrete must-fix in
these final bytes. It is source advice, not a replacement result from the held
paid reviewer and not a formal GitHub approval. New-head CI and applicable
independent review remain required before protected merge.

This PR stays on operation `news-review-packet-retention-20261021` and its
original managed workspace/branch. Do not use the concurrently published
standalone transport branch as a replacement carrier for this combined source.
No native generation was installed or selected by this qualification.

Recovery PR #1674 separately proposes the exact original News failure's
supported reconciliation owner. Its generation must compose with this protected
repair before any rollout; neither standalone review stage is install authority.
Neither held review is replayed, renamed, re-homed or declared accepted here.
News PR #9612's exact integrated head and actual signed-in production acceptance
remain separate release obligations.

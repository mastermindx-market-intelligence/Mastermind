# Clean linked sparse donor candidate, 2026-10-16

STATE: SOURCE_PUBLISHED_FOR_REVIEW / REAL-GIT-TESTED / NOT_INSTALLED / NOT_MERGED.
DO_NOT_INSTALL_UNREVIEWED_CANDIDATE.
Additive compatibility candidate for fleet PR #1404, not another worker,
queue, provider, broker, release owner or credential plane.

## Blocker
Ubuntu0 and Ubuntu2 donor repos have reviewed helper blob 75297acb at Macro
merge 40abd9bd and are clean. Ubuntu1 is on feature branch lane/lr-meas-b3
with uncommitted engine/research_vault/ingest.py. Ubuntu3 is on feature branch
claude/mi-skyd-identity-rename-20261011 with staged security-master edits.
Their helper blob is 296e47ba and neither feature branch is proven an
ancestor of the merged Macro source. Dirty paths overlap. DO NOT force-reset,
merge-forward, overlay, replace or re-sparsify existing donor/worktree source.

## Candidate
Keep original incoming CWD and original LaneLease/provider/root/parent. Only
when the original helper matches the exact known old Git blob, select a
separately pre-provisioned clean linked checkout at
~/lanes/repos/macro-fabric-reviewed. Require owned non-symlink directory and
gitfile, exact same original Git common dir, exact reviewed Macro merge
40abd9bd2291997cc066f30b408a1e670124cec4, reviewed helper Git blob,
no staged or untracked changes, and core.sparseCheckout=true. Validate
the minted child Git dir under the original shared Git common dir. Unknown
source, missing donor, dirty donor, unreviewed HEAD or tampering refuse
before mint. Existing effect-unknown lease retention is unchanged.

This does not create that alternate linked donor or dispatch a worker.
Provisioning remains with the original qualified Macro/Fabric worktree owner
AFTER reviewed release and active source-custody verification.

## Tests
- Exact M2 source preimage and proposed postimage in the attached manifest.
- Six real-Git fixture cases pass, including mint by the ACTUAL merged Macro
  helper from a clean linked donor while original dirty source stays intact;
  missing, dirty, unreviewed and unknown-source inputs refuse.
- git apply --check and exact postimage replay passed against the live-source
  preimage in an isolated scratch target.
- This one-file candidate composes with the original #1404 receipt-retention
  patch that affects remote_sub.sh, not remote_sub_exec.py. Combined Bash and
  Python syntax checks passed in isolation.
- No host limits, thermal gates, provider qualifications or live leases were
  modified. No load test or paid worker was run.

## Source custody and next step
The original fleet PR #1404 branch advanced concurrently (commit 3fdafc02,
source writer active). Do not push an uncoordinated concurrent source change.
Original writer should integrate the exact-hash one-file delta on that same
branch after one scoped source-trust review. Then separately qualify the
actual clean donor on Ubuntu1/3 and obtain immutable support-generation and
original-worker proof before claiming deployment/acceptance. Prior OS
AccessDenied, uncertain effects, and user-attended BIOS controls are not
overridden by this candidate.

## October 17 portable release contract
The source review branch also carries tests/test_fabric_clean_linked_donor_20261017.py. Its seven portable real-Git tests passed in a hermetic Mac scratch checkout (2.48 s; only unrelated historical pytest-temp cleanup warnings). They execute the patched donor selection function against a clean linked Git worktree and confirm missing/dirty/unreviewed/unrelated donors refuse. The original six-test M2 integration separately exercised the true reviewed Macro helper mint, not merely a mock source selector. CI/review and physical rollout are separate gates. All source and test artifacts are owned by existing PR #1404.

## October 17 source security review repair (supersedes preceding candidate)
The independent reviewer requested changes at exact head `ab1722503a55` for an ignored `scripts/json.py` module-shadow attack. Git status does not reveal ignored files, and the original ordinary Python helper invocation included the scripts directory in sys.path. The revised single-file source patch SHA-256 is `354134d103a0cd04f838985e7cce2f291b92bf0a0786e857df004dd9c6be15ef`; the repaired executor postimage SHA-256 is `cb5926c24a51ba4bd1dd99ff195a15cceb9a6512bb5a9fda4938caca3e4f8172` against the same original installed preimage `a29798ab...`.

The repair explicitly refuses Git-ignored objects in the dedicated linked donor, uses `python -I` for real mint to isolate script directory from stdlib imports, and reruns the donor Git/head/helper and file stat/content checks immediately before launch. No preflight snapshot is claimed to provide an atomic filesystem lock. Existing original physical lease, provider, capacity, root/parent and effect-unknown handling remain unchanged. Linux runtime installation is **not** authorized by this source update; old donor feature branches are untouched.

Revised tests: **9/9 portable** and **7/7 actual reviewed Macro helper mint** passed on M2; **9/9 portable** and **7/7 actual helper mint** passed on Ubuntu3 in separate scratch, including deliberate post-preflight malicious Python module injection that never executed under `-I`. The equivalent new patch-file staging write on Ubuntu1 was specifically blocked by platform safety checks and not retried or rerouted; earlier 7+6 Ubuntu1 tests concern the preceding now-superseded candidate only. Previous scratch release digest `8eeb04e027b56858d9975987d88c9153cf1738993c611e2670d37990a27fecbe` is **superseded**. The real 31-file private offline publisher passed again for repaired digest `93901a25095cc553df274f3f1d4cefa97e85bb2bf2f2aaa48cb0dfaa7f80685f`, with the installed M2 executor unchanged. Original safety reviewer must requalify exact new source head and final mandatory CI before release.

## October 17 pre-provisioned donor selection (newer source candidate; supersedes hardcoded reviewed checkout name)
The previously recorded `macro-fabric-reviewed` directory and `40abd9bd...` donor HEAD were **candidate-only assumptions**. Fresh direct host readback on *both* Ubuntu1 and Ubuntu3 verifies the already provisioned `~/lanes/repos/macro-fabric-pinned-20261016`: detached commit `6ee058b0491a3f67e843f25d4379b94e98880e8b`, original shared Git common dir, clean staged/untracked/ignored inventory, `core.sparseCheckout=true`, tracked + working reviewed helper Git blob `75297acb10d0cef4d01730a59fdcad19c7cfd3e6`, and tracked + working sparse config blob `46b4d13bb5302a68b437a257eebe066d07bdc7ff`. Protected Macro main has this exact commit as an ancestor, and its helper/config blobs match directly fetched GitHub source. Original Ubuntu1/3 feature-branch donors remain untouched.

This PR source patch now selects that exact pre-existing pinned path and commit while preserving the October 17 security fix: `python -I`, `git ls-files --others --ignored --exclude-standard -z`, final donor/bytes check, and unchanged original admission/lease/unknown-effect ownership. The pinned source patch SHA256 is `32773b3642d47579b1794878db48e4993f7114995d729ef203c93993c74a7ee3`, expected patched executor SHA256 `49862414e67b6b4919046a553e424d89d994dfbf15d1f0aad372ae9f1c6bfa20` from unchanged installed executor `a29798ab...`. **No host or controller source was installed.**

Proof: M2 **10/10 portable and 7/7 actual reviewed Macro-helper mint** tests; Ubuntu3 **10/10 portable, 7/7 actual helper mint**, and read-only invocation of the patched validator against Ubuntu3's *real pre-existing pinned worktree* returned the exact qualified path. Ubuntu1 direct Git read-only checks all matched, but previous explicit platform safety refusal to stage the patched executor on Ubuntu1 remains respected (no cross-carrier replay). This is a source qualification, not a paid worker START, actual provider admission, accepted task result, or sustained 54-way thermal proof. Exact new PR-head CI and a fresh independent semantic review are still required. The earlier private support release digest `93901a25...` describes the **superseded** prior patch and must not be installed as this new source revision.

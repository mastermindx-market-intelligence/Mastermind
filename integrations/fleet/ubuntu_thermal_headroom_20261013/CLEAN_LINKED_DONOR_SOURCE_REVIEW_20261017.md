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

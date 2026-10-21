# Studio typed-Git destination and ref qualification

Operation: `studio-typed-git-destination-repair-20260917-sol-001`.
Parent PR: #696 at `42d50bf67e2d3ae02cd0ea22723a316b8169cf0e`.
Review being repaired: `5242168925`; parent continuation: `5722415125`.
Protected procedure: `320f586126b7c82c843ef17612f12d40d20a42e0`, Skillpack 1.0.1.
State: `BUILT_NOT_PROVEN`. No production service, provider, Project setting or protected branch was modified by this qualification.

## Capability and boundary
The incumbent publisher qualifies exactly one complete effective push destination before remote observation, checks it against host policy, and pins origin's fetch/push URL lists to that captured destination for push and readback. Multiple destinations and unsupported rewrite composition refuse without a network command. The exact expected commit and branch remain fenced. Explicit non-follow-tags, non-force and non-mirror controls prevent ambient ref widening. The origin identity, mandatory pre-push hook, credentials and non-pushing submodule checks remain effective; a policy that would push submodules is refused instead of silently disabled. No alternate publisher, workspace manager, credential store or retry plane is introduced.

This repair addresses the reviewed Git configuration boundary. It is not a sandbox against a hostile operating-system principal that can replace Git, edit hooks or modify arbitrary host files concurrently. It does not claim unconditional atomicity across unrelated host configuration writers.

## Executed discrimination and integration
Recovered the original dirty workspace after interruption without resetting, replacing or discarding source. The current focused suite completed successfully; the full adjacent source package also exited zero. Then ran the same 30 focused tests against a disposable copy of the immutable parent publisher: 19 passed and 11 failed at intended destination/ref/policy assertions, with zero cancelled or skipped tests. The original 16 regressions all remained green.

Copied immutable output-paging child #785 (`042418ca76830e45f8877da92467a5415533b964`) into a disposable qualification directory and overlaid only this repair's two implementation/test files. All **119 tests passed**, zero failures/cancellations/skips. These include local real-MCP gateway paths, exact-result paging and incumbent transport regressions. The copied candidate is compatibility evidence, not a branch composition, independent review or native ChatGPT proof. All Git destinations used by the regression tests are disposable local bare repositories, never company publication remotes.

Code SHA-256: `5949022aaa5a0bd8a3381987320396781ef4089c12b23475eeda324a0a5ff332`.
Test SHA-256: `5e19bdd310f9d324431a285b97ce5759b9219c3b0b85792991d59a7a94f79272`.
Baseline log SHA-256: `4746176067a14485949e72503bddacaf30ae38b5a6562207abf373fa5970bc13`.
Integrated log SHA-256: `2f1226ccbc0842e69a9a9f9b449f8d93368acbed1711bebb12b6448d7e3fcddd`.
Logs remain under the existing operation's `/private/tmp/studio-typed-git-destination-repair-20260917-sol-001/resume-verification/run.VcbDXa/` on Studio; the committed tests are the reproducible durable evidence.

## Release and continuation
Publish one stacked repair on the original operation branch. Obtain independent exact-head review, required checks and current source-custody proof before composing into #696. Refresh #785 compatibility after composition without replacing its source carrier. Then follow protected release and governed installation/native acceptance; do not install this unreviewed candidate. Keep #706's preserved dirty workspace untouched. A reviewer request is not START, a green test is not merge, and merge is not production acceptance.

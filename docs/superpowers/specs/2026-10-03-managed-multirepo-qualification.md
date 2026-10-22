# Managed repositories: first source qualification, 2026-10-03

Operation: `agent-environment-storage-admission-20260915-sol-001`; existing #685.
Protected integration parent: `bdf2a972e68a70270c24d4b5d61a4d60edc4f288`.
Published predecessor: `63f3c980956ed12b6ab133a23d0f4c4393d31165`.

## Observed source capability

The existing installed-owner implementation now accepts closed Mastermind/Macro/Terminal bindings, reports unenrolled/unavailable targets, separates per-repository worktrees, and retains legacy Mastermind paths and v1 invocations. Explicit selections emit v2 repository context. Installer-only binding inputs are validated against canonical source/common-directory/origin before installation; shell-quoted wrapper literals override ambient mappings. Sparse construction and storage admission reuse the current owners; storage checks the original host root.

The three original integration conflicts were reconciled to exact current protected blobs before the extension. Their resolved index tree was identical to protected775dbbf5; no original storage behavior or accepted #929/#1099 fixes were discarded. The source branch and original custody lock remain.

## Executed tests, not inferred success

- Current protected workspace/storage/sparse baseline: passed.
- Initial repository tests: 14 intended failures / 3 controls passed (missing selected-repository CLI).
- Initial installer tests: 4 intended failures (old installer ignored registration arguments).
- First repository implementation: 21 passed.
- Broad first compatibility: 6 failed / 141 passed. The six existing installer fixtures had no origin; they now include a canonical synthetic origin while preserving every shell/argv/mount assertion.
- Broader adverse-input campaign: 1 failed / 152 passed. An unavailable exact base created an empty workspace directory before refusal; selected-repository prevalidation closes that gap without editing the core owner.
- Final current-source campaign: **153 passed in 53.85 seconds**, exit0, under child umask022. Files: tests/test_mastermind_workspace_repositories.py, tests/test_mastermind_workspace_cli.py, tests/test_executive_workspace.py, tests/test_workspace_sparse_materialization.py, tests/test_secondary_host_enrollment.py.
- Shell syntax, Python compile and git diff whitespace: PASS.

Tests use real synthetic Git repositories and installer fixtures, not production working trees or network pushes. Host source mapping was separately read-only verified for all three canonical checkouts and sparse worktreeConfig enrollment. This is not an actual installed multi-repository acquisition or publication receipt.

## Retained log digests

Evidence remains under the existing operation evidence owner, `multirepo-20261003/`:

- `baseline.log`: `1e4ea318dc8d7d919a3ee028c8a7470cec31c209a53ca3565d057d410fd546ea`
- `repositories-red.log`: `f17d9197bbf22036a1bb105e1704a7e4baa6e13a9968c1110b11d469aaa9d40d`
- `installer-red.log`: `c379d3f15047002b159f6c9e0a61a4af47646280c7dd9972ceb6893ee7fd041c`
- `compatibility1.log`: `9b96b9f8a7d0f03dc718df267cbd49128c11cfa116378366c42b6d37c4e811c8`
- `compatibility2.log`: `f4a8e75401b9d4512956ee529fb561e62262907035a536e817224bcc9af947dc`
- `cli-qualified.log`: `b3eb57aaa1ffc2e67fe28f1df3bec17afacad09b4119ae72d19c653e47eb757e`

## Ceiling and next phase

**BUILT_NOT_PROVEN / DRAFT / NOT INSTALLED.** Studio Direct acquisition/repository-aware publication and actual Workbench binding remain unfinished. No review, release, installation, fleet rollout, runtime dispatch, production write or foreign worktree cleanup is claimed. #1014's additional published-branch evidence remains a separate existing source dependency; default-core preservation is conservative. Continue on this carrier with Studio composition, independent exact-head review, required checks and installed consumer proof. Do not recreate this tested selector/installer.

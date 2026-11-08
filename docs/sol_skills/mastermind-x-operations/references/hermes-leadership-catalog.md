# Hermes leadership catalog changes

Use this reference when an authorized source assignment changes the existing leadership catalog. Read its current implementation and tests at the task's immutable source. Catalog metadata is advisory; adding a row does not enroll a native profile, grant authority or prove worker execution.

## Inspect the coupled surfaces

The existing integration joins:

- integrations/hermes_leadership/charters.py: charter keys and their rows.
- integrations/hermes_leadership/organization.py: reporting relationships and the rendered organization context.
- docs/hermes/EXECUTIVE_TEAM_CONTEXT.md: the human-readable seat enumeration and count.
- Existing consumer tests that enumerate keys, reporting relations, source truth and serialization limits.

Search one current member across source, tests and prose before editing. Inspect the actual schema, allowed roles/modes, inherited limits and rendering contract rather than copying a dated list. Keep every affected surface in one coherent source change. Do not introduce a parallel catalog or role authority.

## Bound and verify the source change

1. Recover source custody and reuse the original operation. Authorized GitHub-native editing uses immutable preimages and expected-head checks. Actual host-local work uses the installed workspace owner; raw worktree creation is not its substitute.
2. Update the existing key set, matching row, reporting relation and prose enumeration together. Preserve current inherited limits, advisory status and unobserved-enrollment facts.
3. Measure the actual rendered context with the incumbent serializer and fixtures. Preserve its MAX_BYTES ceiling; do not rely on an estimated per-seat size, omit rows or raise the cap to conceal an overflow.
4. Update the relevant existing key/count assertions and run meaningful package consumers. If a prose guard exists, preserve it. If a real documentation drift risk lacks coverage, add only the necessary contract check.
5. Inspect the complete diff, source hashes and current receiving composition. A stacked child's history and unique work must survive subsequent edits; coordinate actual source changes rather than assuming every child should rebase.
6. Publish through the original protected-delivery path and independently read back the exact source and eventual merge. Follow the PR/CI reference and governing delivery owner; no direct/admin merge or repeated admission command.

Use the actual test fixtures and their dependency chain. A missing dependency or fixture setup error is not a passing test. Determine whether the candidate changed the declared dependency contract before classifying the failure as environmental. Compare a suspected inherited failure on the appropriate original source in an approved isolated fixture; do not discard or stash another writer's work.

Profile creation, role-memory distribution, selected-runtime changes and live enrollment are separate existing-owner operations. Source acceptance alone authorizes none of them.

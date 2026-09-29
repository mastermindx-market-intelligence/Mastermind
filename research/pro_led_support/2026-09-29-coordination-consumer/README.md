# Direct Pro-led build: coordination briefing and candidate review

This #1056 contribution is implemented in source, not another handoff to the base team.
The initiating Web principal owns the implementation and withdrew the premature native
assignment. The existing base App/Runtime/installer/source owners remain untouched.

Two functions extend the existing Chairman Cognition consumer:
- `render_coordination_brief`: consumes the complete existing Agent OS compiled bundle,
  binds the actual project/intent/plan/source identities, preserves omissions and
  exclusions, and emits a fixed instruction, evidence and closed model response schema.
- `evaluate_coordination_candidate`: checks a proposed next step against those inputs
  and the unchanged original policy verdict. It cannot override that verdict or grant
  execution/acceptance. Structural eligibility still requires semantic review and fresh
  owner revalidation.

Both are reachable through optional flags on the existing `scripts/chairman_cognition.py`.
No-mode output remains unchanged. Fixtures and runnable examples are in
`tests/fixtures/chairman_coordination/`; every example is fictional, not a live grant.
The full contract and trust limitations are in
`docs/superpowers/specs/2026-09-29-pro-led-coordination-consumer.md`.

## Executed evidence

All six cognition/coordination test files: **264 passed, zero failed or skipped**.
The initial new-implementation discriminator had44FAIL/1PASS; briefing14FAIL before
implementation; source binding4FAIL; timestamp3FAIL; output schema2FAIL. Final suites
are green. The exact upstream Macro compiler was executed on isolated fixture records;
its complete output was consumed unchanged and its record tree remained unchanged.
Both documented CLI examples run successfully. Source compilation passes.

The full repository pytest invocation was attempted. It stopped during collection at
`tests/mastermind_window_reader/test_mission_association.py` because this interpreter
lacks `jwt`; the rest of the repository is **not qualified**. No global environment or
base-builder dependency installation was changed to hide that gap.

The first manually authored fixture used the wrong upstream source-digest convention;
the actual compiler emits `sha256:<digest>`. A failing real-shape discriminator preceded
the consumer correction. A test initially snapshotted the framework's _runlog directory
as a file; its input snapshot was corrected to the test-owned input directory.

## Current release boundary

The full open-PR file census found one historical path overlap: #124 contains the same
CLI preimage as current protected source, blob445eb0c8b2254c88219f9b12b7bd94171a64306f.
Its1239-file list was fully paged, not inferred from the first100 paths. This does not
show a competing CLI implementation, but the path-conservative release hold remains.
No foreign branch is changed and no Ready, merge, deployment or installed acceptance
is claimed. Continued independent development stays with this Web principal.

This is not a running Meta-CEO or an automatic Web Pro continuation demonstration.
Model judgment, current authenticated source acquisition and existing runtime/transport
integration remain separately qualified boundaries. No new lifecycle, memory compiler,
scheduler, credential store, watcher or worker was created.

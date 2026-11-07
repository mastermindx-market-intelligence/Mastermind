# Validation and remaining evidence limits

## Source and design scope

This continuation deepens planning for the existing #1236 / PR #1240 initiative. It does not
activate a native profile, install a plugin, enroll an account, dispatch a worker, allocate a
browser or merge/deploy code. Detailed H1–H6 packets are prepared; H7 remains at its original
handoff acceptance baseline because its detailed file write was blocked before dispatch.

Current protected analysis pin: `17b9fa1363db6071d338be3373a4fdb11fc0076d`.
The loaded required procedures and relevant implementation paths were byte-identical to the
prior protected base `521720b09be2921e996d9396b522b1c4ca62041c`. The original operation workspace
was reacquired with `reused: true`; no incumbent checkout or source lease was replaced.

## Actual test run: broader selection did not collect

Python 3.14.7, plugin autoload disabled, AnyIO plugin explicitly enabled. The initial ten-module
selection included the two additional tests below and stopped with **two collection errors**:

- `tests/test_executive_coo_mcp.py`: `ModuleNotFoundError: No module named 'jwt'`.
- `tests/test_executive_coo_host_roundtrip.py`: `ModuleNotFoundError: No module named 'mcp'`.

Exit status 2. No application change or test weakening hid those errors, and no global dependency
installation was attempted. This is not a full native/backend integration PASS.

## Actual available-contract run

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p anyio.pytest_plugin \
  tests/test_coo_principal_request.py \
  tests/test_coo_principal_envelope.py \
  tests/test_coo_principal_mandate.py \
  tests/test_executive_coo_host.py \
  tests/test_native_claude_operator_supervisor.py \
  tests/test_mastermind_company_mcp.py \
  tests/test_mastermind_company_mcp_mutation.py \
  tests/test_company_dialogue_runtime_binding.py \
  -q -rs --tb=short -o addopts='' \
  --junitxml=.pytest_cache/claude-hardening-available-contract-audit.xml
```

Result: **334 passed, three skipped**, 7.20 seconds, exit 0.
The three skipped cases are in `test_mastermind_company_mcp.py` at lines 735, 767 and 805,
all because the optional `mcp` dependency could not be imported. Those cases are unproven.
The local JUnit artifact is a test-run output, not an installation or live OAuth receipt.

The previous H2-A candidate's **345 passed / two skipped** result belongs to commit
`0c29b4af70e0ed1d42e6e271610aa46295075e77`; it is not added to this run's count or claimed as a
new run. Its source remains unchanged in this design-only continuation.

## Executed policy arithmetic

Loaded the canonical `CooCyclePolicy` and called its reservation calculation. Current values:
maximum 16 children; two repair rounds; two review attempts per work revision; one planner slot.
`reserved_children_total((True, True))` refused with capacity exceeded (19 reserved slots).
`reserved_children_total((True, False))` returned 11. This is an actual pure-policy observation,
not a live worker admission or authority to change the cap.

## Planned acceptance cases are not executed tests

`ACCEPTANCE_CASES.json` contains 80 planned scenarios: twelve each for H1–H6 and eight mappings of
the original H7 requirements. All carry `execution_result: NOT_RUN`. The H7 entries deliberately
do not substitute for the blocked detailed browser packet. `EXECUTION_GRAPH.json` is a 16-node
review dependency graph and explicitly grants no runtime/dispatch authority.

## Structural verification

Run `python3 docs/claude_capability_hardening_20261004/verify_design_package.py` from this
checkout. It verifies the 36 accepted source-register entries against local immutable Git blobs,
the original brief digest, local links, explicit H7 hold, case IDs/coverage and an acyclic work
package graph. It performs no provider, network, credential or runtime operation.

Executed structural result: **PASS_WITH_EXPLICIT_HOLDS**. Verified 36 source anchors, 80 planned
case identities/coverage, 16 dependency nodes, the original brief digest and local document links.
Eight in-memory negative tests also passed: wrong source pin, source hash drift, a false execution
claim, fabricated case PASS, duplicate case identity, dependency cycle, fictitious dispatch
authority and a missing joint-proof predecessor all refused as expected. No source file was
mutated to inject those test cases. Results are retained in `DESIGN_VALIDATION.json`.

These checks cannot make the design complete, supply independent review or establish any native
acceptance. The published milestone records the exact candidate identity separately. A consistency
review also corrected the sequence so the reciprocal loop runs during the live child-work proof;
the later evidence review cannot revive a terminal child.

## Action-scoped tool refusals

Two continuation writes were blocked before dispatch by the platform's safety-status evaluation:

1. The attempted two-entry extension of SOURCE_REGISTER.json/Markdown for the additional neutral
   dialogue/facade ranges. The prior 36 entries remain; no S37/S38 entries are claimed.
2. The detailed `H7_BROWSER.md` file write. No detailed H7 file is claimed persisted.

Neither action was retried, rephrased or rerouted. No modifying effect from those blocked calls
is observed; all acknowledged independent file writes are retained. A general provider/permission
cause is not established, and this is not evidence that all file writes are unavailable.
The earlier denied incumbent PR bodies/comments read also remains unreplayed.

Current remaining planning gate: a legitimate recovery condition for the exact denied writes,
followed by normal same-target reconciliation. A new chat, mode, carrier, account or repeated
Continue is not itself permission to obtain the denied effect. Do not recreate the H7 packet
under a different filename or fabricate a source-register receipt.

## Release and production limits

Exact-head hosted CI and independent review are separate pending release obligations; this design
pass does not claim either from its local test results. Prior observed in-progress CI is not a
terminal verdict. The current final candidate and latest bounded CI observation belong in the
issue/PR milestone, not a permanently stale claim in this document.

No native SDK/CLI version was measured in this continuation. Provider documentation is separated
in EXTERNAL_NOTES.md. No customer/production data, personal browser, provider account or credential
was used to manufacture positive or negative evidence. Source publication will not imply
installation, selection, authentication, native qualification or program completion.

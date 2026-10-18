# Native Fabric quota continuity

Source candidate for operation `fabric-quota-continuity-20261018-web-001`.
Protected Mastermind law/source baseline: `e77631490e5bddca7d40c8cf039ae7763ce17b99`.

## Observed incident and installed gap

The supplied Fable screenshot describes a native Claude parent stopping before
WP31 workers were submitted. Its text does not establish an actual provider
quota failure. Fabric cannot resume an unsubmitted native-parent task.

The inspected native Fabric selected a route once, reduced most nonzero provider
returns to `remote_nonzero`, deleted the submitted stdin packet, and removed
private Codex homes on failed or incomplete exits. Existing draft PR1367 contains
Executive continuation work; it explicitly does not establish installed native
Fabric or original-parent wake. PR1441 is a separate quota-router source proposal.
Neither draft was adopted or modified by this operation. Their specifically held
proof/installation operations remain held and are not used as this patch's tests.

## Candidate behavior

* The current attempt emits bounded typed provider diagnostics from CLI-owned
  fields. Assistant prose, stderr text, tool results and private reasoning are
  not quota classification inputs.
* The existing broker stores account/shared-allowance cooldowns in its own SQLite
  database. Both picker exclusion and locked reservation consult those rows.
  Expiry allows one lease across the shared allowance to probe; its qualified
  success clears the row. Old successes do not clear newer exhaustion.
* Model aliases share their account's allowance. Existing provider/account
  metadata may declare `quota_scope` to join products or accounts known to share
  a subscription. This patch does not invent a Cursor/Grok entitlement mapping
  or edit account configuration. Unknown cross-product sharing remains unproven.
* Task packets remain in existing private per-run artifacts even when no route
  is available. Failed, interrupted, incomplete and blocked Codex sessions remain
  in their original private homes. Completed terminal sessions retain the
  incumbent cleanup behavior. These files are not queued work or permission to
  resume an old process.
* `request --quota-fallback` permits at most three sequential attempts within the
  existing commission wall-clock fuse, only after a typed **initial** capacity
  rejection, verified process cleanup, strict terminal publication and actual
  release of the original provider lease. Every successor has its own run ID,
  original root/parent, frozen task digest and immutable predecessor link.
* Exact-run status/result/acceptance remain exact. `status --follow` and bounded
  `wait --follow` expose the actual successor plus earlier failed attempts. The
  MCP facade uses this resolved view and returns `effective_run_id` and
  `accept_run_id`. Acceptance through a failed origin is refused; the caller
  reviews and accepts the actual successful successor.
* A crash or missing final controller receipt is unconfirmed execution. Reading
  it never starts another worker. There is no new background scheduler or queue.

## Limits that remain explicit

Quota failure after task/tool activity does not authorize replay. Context, output,
turn and configured spend limits are distinct from provider allowance exhaustion.
Authentication, billing, permission refusal, missing output and uncertain effects
do not trigger model migration. Unsupported/malformed telemetry stays unknown.

Artifact-producing, new-worktree, native-return, operator-child and fixed-model
requests retain their incumbent contracts; they need separately qualified
continuation behavior before automatic migration. Native parent restart and
automatic wake after the submitting process ends require the existing native
conversation/lifecycle owner. This candidate does not supply that owner.

## Source and validation layout

`candidate/` contains the proposed native files. `source/lane_runtime.py` is the
unchanged inspected cleanup-receipt dependency used by offline tests, not a new
runtime owner. `baseline.json` records exact preimage hashes. The MCP facade
change belongs to `integrations/studio_direct_mcp/fabric-backend.mjs` in the same PR.

Run the offline tests with `python3 -m unittest discover -s tests -v` from this
directory. Run the facade tests with `node --test fabric-backend.test.mjs` in its
incumbent integration directory. Fixtures use isolated databases and inert CLI
processes; they do not spend provider quota, read real credentials or exercise
the held Executive proof operations.

Claude result/error enums were checked against the official published
`@anthropic-ai/claude-agent-sdk` 0.3.301 declarations and the official CLI reference:
https://app.unpkg.com/@anthropic-ai/claude-agent-sdk@0.3.301/files/sdk.d.ts
https://code.claude.com/docs/en/cli-reference

Publication, independent review, protected merge, installed native bytes, facade
restart and an observed native canary are separate gates. This source checkpoint
alone is not a production installation or proof of automatic native-parent wake.

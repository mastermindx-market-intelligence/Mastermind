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
* Model aliases conservatively share a short account cooldown. This is a backoff
  decision, not proof that every model allowance is exhausted. Existing
  provider/account metadata may declare `quota_scope` to join products or accounts known to share
  a subscription. This patch does not invent a Cursor/Grok entitlement mapping
  or edit account configuration. Unknown cross-product sharing remains unproven.
* Task packets remain in existing private per-run artifacts even when no route
  is available. Failed, interrupted, incomplete and blocked Codex sessions remain
  in their original private homes. Completed terminal sessions retain the
  incumbent cleanup behavior. These files are not queued work or permission to
  resume an old process.
* `request --quota-fallback` permits at most three sequential attempts within the
  existing commission wall-clock fuse, only after a typed **pre-task** capacity
  rejection, verified process cleanup, strict terminal publication and actual
  release of the original provider lease. A CLI's first visible rejection alone
  does not establish that startup hooks or MCP servers had no effects. Every successor has its own run ID,
  original root/parent, frozen task digest and immutable predecessor link.
* Exact-run status/result/acceptance remain exact. `status --follow` and bounded
  `wait --follow` expose the actual successor plus earlier failed attempts. The
  MCP facade uses this resolved view and returns `effective_run_id` and
  `accept_run_id`. Acceptance through a failed origin is refused; the caller
  reviews and accepts the actual successful successor.
* A crash or missing final controller receipt is unconfirmed execution. Reading
  it never starts another worker. There is no new background scheduler or queue.

## Pre-task capacity check

For eligible MiniMax and GLM Claude attempts, the existing admitted wrapper makes
one small request after binding its exact leased account, endpoint and model, but
before starting the task CLI. It submits a fixed prompt with `max_tokens: 1` and
no task bytes, tools, MCP servers or system prompt. It does not discover keys,
change credentials, redirect requests, add a provider, or raise a spending limit.

The check has a 20-second whole-response deadline, a 64-KiB response limit, no
redirects and no retries. It remains inside the original commission timeout.
Success, timeout, server errors and unrecognized responses let the original CLI
proceed. Success reserves no capacity; the subsequent task can still hit a limit.
The extra request consumes input and up to one generated token and can increase
request-count usage noticeably for very small tasks.

Only a documented typed capacity rejection causes the wrapper to return before
CLI execution. GLM's numeric API codes distinguish quota/rate limits from its
other HTTP 429 responses, including billing, plan restrictions and policy
restrictions. Known denials stop without migration; unknown codes remain unknown.
No code is extracted from an error message or assistant prose.

Continuation verifies the probe's request digest, control-flow source hashes,
immutable remote support digest, exact run/account/lease/model/process receipt,
strict ledger outcome, released lease, and frozen packet digest. A task-start
reservation prevents conversion of a later CLI error into pre-task evidence.
Each failed attempt remains independently observable and auditable.

## Credential custody in the published generation

The Qwen wrapper loads its selected account through a fixed `exec-codex` helper.
The helper places the value directly into the Codex child's environment and
replaces its own process with `codex exec`. The shell handles account names only;
it never receives a credential through command substitution or `eval`. Shell
tracing is disabled before wrapper setup, and an inherited credential is cleared.
The local silent `check-key` preserves the existing key-wait and slot-release
behavior. The exact account is checked again immediately before execution.

This preserves existing initial/resume arguments, stdin, parent-owned slots,
outer leases, same-thread continuation and final process statuses. It adds no
provider request or account migration authority. The new generation explicitly
retires `bailian_keys.py env`; a mismatched old wrapper receives a refusal before
that command reads any credential. Account-name/status output remains public
metadata. The scoped source-flow adjudication is in `SECURITY_REVIEW.md`.

The original helper remains byte-for-byte evidence in
`source/bailian_keys.py.preimage`. It is non-importable and cannot be selected as
a deployable fallback. The stage builder requires the secure candidate and
verifies the original preimage hash before overlaying it. Existing flat and
historical source retains its prior contract while its old controllers finish.

## Retention and reclamation

An interrupted or incomplete Codex home remains private on its original host.
Creation and retention indexes identify its run, root, parent, account, lease,
model, original inode and path. The controller copies only those small indexes;
session contents stay on the worker. Status describes the reference as unprobed
and does not grant resume or deletion authority.

`recovery_artifacts.py plan` is read-only. Explicit `reclaim --abandon` requires
the reviewed index digest, original identities, proven process cleanup and no
active marker. It rechecks these under the existing admission lock, deletes only
the exact private home with safe file-descriptor traversal, and preserves an
intent and completion receipt. It never kills a process, releases a lease,
replays a task, or expires all retained sessions by age. A missing final retention
index can use the bound creation index after cleanup has actually been proven.

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

`candidate/` contains the proposed native files. `source/` contains inspected
preimages and the unchanged native dependency closure, including the explicitly
non-importable retired helper described above. `baseline.json` records
exact preimage hashes for overlaid source. The rollout manifest names every
published native file explicitly; state and credential contents are excluded.
`rollout/` contains the finite native artifact publisher and ingress installer.
The MCP facade and its existing service owner remain in
`integrations/studio_direct_mcp/` in the same PR.

Run the offline tests with `python3 -m unittest discover -s tests -v` from this
directory. Run the facade tests with `node fabric-backend.test.mjs` in its
incumbent integration directory. Fixtures use isolated databases and inert CLI
processes; they do not spend provider quota, read real credentials or exercise
the held Executive proof operations. The wrapper integration test runs the actual
remote executor, physical process owner, MiniMax/GLM wrappers and broker observer
against an isolated loopback provider. Its receipts are produced by those owners,
including the actual stdout hash and cleanup evidence.
The repository's canonical `tests/test_native_fabric_quota_continuity.py` entry
runs both native suites in isolated, bounded subprocesses under required CI.

Claude result/error enums were checked against the official published
`@anthropic-ai/claude-agent-sdk` 0.3.301 declarations and the official CLI reference:
https://app.unpkg.com/@anthropic-ai/claude-agent-sdk@0.3.301/files/sdk.d.ts
https://code.claude.com/docs/en/cli-reference

The bounded Messages request and vendor error classifications use primary docs:
https://platform.minimax.io/docs/api-reference/text-anthropic-api
https://platform.minimax.io/docs/api-reference/errorcode
https://docs.z.ai/devpack/tool/others
https://docs.z.ai/api-reference/api-code
Codex rollout enums were checked against its official protocol source:
https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs

## Deployment order

Install the complete native source group from the actual merged immutable
release before upgrading the same existing Fabric facade account. The facade
checks that the adapter supports both quota fallback and successor-following
before creating a controller; an older adapter produces
`ADAPTER_CONTINUITY_UNAVAILABLE`. Preserve the account, port, tunnel, installed
protocol selection and current runtime owner.

Publish the complete reviewed native code closure as one immutable generation.
The original broker, state, lanes, configuration and credential owners remain on
their current paths through a fixed, declared binding map. Strict custody readers
map only those declared prefixes back to the original owner before applying their
existing file and directory checks; symlinks inside state are still rejected.
The atomic quota-cache writer uses its original canonical destination so it
cannot replace a generation's fixed alias.

Bootstrap the public entry points in two phases. First, the existing `pool`
launcher and the CLI branch of `fabric_task.py` select the generation once and
exec an absolute immutable path. Imported flat APIs keep their prior bodies;
old flat controllers keep all their original helper files. After the original
owner reconciles the finite inventory of legacy parent/launcher processes and
imported mutating callers, the second phase bridges `remote_sub.sh`. The phase-two
receipt is bound to the exact bootstrap plan and epoch. Neither an empty lease
table nor elapsed time substitutes for that reconciliation.

Phase 1 activates the versioned code for standard pool commands, native task CLI
requests and the existing Fabric facade's CLI adapter. The production facade
enables eligible automatic continuation by default; direct task CLI commissions
use `--quota-fallback`. Direct pool runs retain their existing run contracts.
The separate phase-two retirement of flat `remote_sub.sh` remains gated on the
complete existing-owner reconciliation record. Until that record exists, leave
that compatibility entry and its old helpers intact and report it as legacy.

Future generation selection uses an atomic compare-and-swap under an artifact
publication lock. Running controllers retain their selected code and remote
support closure; broker heartbeat and lease release remain on their own existing
lock. Bootstrap rollback restores exact future-ingress preimages, preserves all
running attempts and state, and ends that bootstrap epoch. It never kills work.

Advance the already enrolled `subagent-fabric-c3` backend with
`private_service.py fabric-backend-release`, after the native rollout. The normal
generic `upgrade` requires an unchanged backend path and cannot perform this
selection. The new command belongs to the same private service owner: its
read-only preview binds the existing manifest, complete runtime seal, exact
merged Git blob, released backend hash and proposed plan. Once the original
service is safely stopped, apply changes only `config.args[0]` and manifest
`backend`, `backendHash`, `configHash`. The existing gateway, dependencies, Node,
port, tunnel and protocol choice stay sealed. Private intent/backup/result
evidence records the transition; uncertain results require same-owner inspection.
Start the original account through that owner's normal command and consume the
actual bounded native canary result before reporting installation complete.

Publication, independent review, protected merge, installed native bytes, facade
restart and an observed native canary are separate gates. This source checkpoint
alone is not a production installation or proof of automatic native-parent wake.

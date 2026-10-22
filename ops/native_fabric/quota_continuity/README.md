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

## Conservative host disk telemetry

The collector floors available disk space to one decimal GiB before publishing
host state. Both Linux and Darwin keep the existing disk measurement and volume
selection. This prevents a host below its configured base floor plus checkout
reserve from becoming eligible solely because telemetry rounded upward. For
example, 330253288 available KiB becomes 314.9 GiB and remains below a 315 GiB
requirement; exactly 315 GiB remains eligible. The locked physical admission
check still uses current capacity and may refuse a host after concurrent usage.

The regression tests execute both actual disk-probe blocks and pass their output
through the real host picker, including the original rounding failure, exact
boundary controls and selection of another healthy host. When deploying a new
generation, rebind the existing host-pull collector to that same generation and
verify fresh host state: its probe template is loaded once at process startup.

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

The original-parent artifact observer recognizes the current exact 37-file
support closure emitted by this producer. Earlier observation shapes retain
their existing admission; arbitrary extensions and subsets remain refused.
Packet, root, assigning parent, broker, support digest, code hash and filesystem
custody checks still apply before observation. This compatibility repair grants
no worker replay, result acceptance, legacy-run adoption or permission bypass.
Its staged-runtime tests exercise both the prior and current producer contracts.

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

The original-result collector generates a portable directory reader. Its remote
paths are already bound to the original host; the Mac generation's `owner_path`
adapter must remain local. Embedding that adapter without its native globals
caused the generated helper to raise `NameError` before opening a directory.
The portable export changes only that path normalization line and retains every
ownership, mode, no-follow and directory-edge check. It grants no new recovery
scope, worker replay, lease mutation or alternate result carrier. Regression
checks execute the actual generated helper against inert local directories.

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

## Contention handoff and commission deadlines

An eligible foreground commission can continue after a broker-confirmed pre-lease capacity refusal as well as the existing provider-confirmed pre-task rejection. This closes the race in which routing selected a pool before another run placed its shared allowance on cooldown. Under its existing lock, the broker requires every relevant configured account to be otherwise enabled and covered by a valid active recorded capacity cooldown. It grants no lease to that acquire. Disabled or parked accounts, independent usable accounts, non-capacity failures, expired cooldowns, and busy half-open probes do not qualify this handoff.

The foreground owner waits for its actual one-shot controller return. Its refusal proof binds the frozen request, packet, selected route, original run/root/parent, and exact controller/broker/circuit source. Contradictory effect-unknown markers, lease or launch evidence, and retained execution artifacts remain disqualifying even when their bytes match recorded hashes. A fresh successor keeps the original packet and lineage, the existing three-attempt bound, and exact-leaf acceptance. This path reports `prelease_quota_cooldown`; it does not claim that the contender received a new provider rejection.

One origin monotonic deadline governs routing, provider-lease acquisition, controller staging, new launch attempts, and successors. The existing picker runs with routing metadata only under the incumbent process owner. Broker flock/SQLite waits and controller commands consume the same remaining budget. Each remote launch receives a remaining duration and subtracts its own local preparation time; monotonic clock values never cross hosts. Once launch effects are possible, expiration prevents new attempts while the existing owner completes settlement or preserves uncertain custody. Cleanup, terminal collection, and transit ambiguity may extend observed return time.

Deadline routing excludes only the local `m2` slot transport, whose slot wait and child lifetime do not yet consume this commission deadline. Remote Darwin hosts remain eligible through all ordinary economic, readiness, and placement gates. Direct deadline-bearing `m2` calls refuse before slot acquisition or task creation. Local calls without commission metadata retain their incumbent behavior.

Automatic continuation applies to eligible ordinary C3 commissions and explicitly opted-in native CLI requests. It does not add a background scheduler, wake an ended native parent conversation, replay uncertain task effects, or bypass context, output, turn, resource, or time limits. Exhausting all authorized routes or the commission budget still returns retained evidence for the existing owner. A healthy canary validates normal dispatch and settlement; it does not establish that a real provider returned HTTP 429 or that quota failover occurred.

## Registry-bound physical roots for new ordinary runs

The optional `physical_lane_root` field belongs to the existing host entry in
the original `ext/hosts.json` registry. This source capability does not enroll a
host. When the field is present, that original registry owns path selection;
publisher output may confirm the frozen path but cannot replace it. Task text,
environment overrides and a resolved home-directory alias cannot select this
configured root. No live registry value is changed by this source repair.
Installing the protected release and admitting a real host root remain separate
owner actions.

The first supported shape is one **new explicit-ID ordinary plain GLM or Qwen
remote run**, with an original root and assigning parent, `cwd=~`, no artifact
contract, no operator child/budget or continuation, and no Macro workspace or
CPU-scope extension. Configured unsupported shapes refuse before a provider
lease or remote transfer; local reservation and packet retention may already
exist. The local m2 shortcut also refuses a configured field before worker
invocation. When the field is absent, eligible ordinary plain runs retain the
separate publisher-owned transport repair: the strictly parsed publication
return freezes the physical owner for readback, launch, polling, collection and
cleanup. That path carries no registry-origin layout attestation and does not
inherit the configured-root protocol's exclusive leaves or recovery guarantees.
Configured-root failure or publisher disagreement never selects this fallback.
Other run shapes retain their incumbent transport contract.

On both eligible ordinary branches, host initialization may prepend its own
home-relative or host CLI paths. After sourcing the physical owner's HOST_ENV,
the controller prepends only that frozen owner's venv/bin again before GLM
account readiness and launch. Other host PATH entries keep their relative order.
Legacy/nonplain initialization is unchanged. This guarantees the intended path
precedence, not authenticated virtual-environment bytes or arbitrary host setup.

The field must name an absolute physical path using ASCII letters, digits,
`_`, `-`, `.`, and `/`, with no empty, dot, or dot-dot components. The owner must
already provide the root plus `tmp`, `ext`, `ext/active`, `ext/lanes`, `orch`,
`orch/fabric`, and `support-releases`. The unchanged `DirectoryChain` checks
every ancestor for permitted ownership, directory type, safe mode and no-follow
custody. A pre-upload observation pins device, inode, UID and mode for this
fixed layout. Later checks compare with that observation; replacement at the
same pathname does not refresh the pin. These checks use the existing commission
supervisor and deadline.

Only this shape adds `artifact_delivery.py` to the exact remote support closure
(38 files); default and historical 37-file or earlier generations retain their
existing membership. The publisher still checks closed file sets. Transport,
executor and collector check the immutable code manifest and the publisher's
fixed state-link map against the same physical root. Bound executor reads
require owned regular files, one link, no group/other write, stable identities,
and exact sealed modes for code and release metadata. The generic legacy file
reader and `DirectoryChain` body are unchanged.

Bound packet transfer uses the existing SSH channel with a bounded stdin
receiver and exclusive no-follow creation. Existing packet, output or receipt
leaves refuse; they are never adopted, overwritten or removed. The bound launch
reserves stdout and RC with exclusive opens and keeps their descriptors through
the original executor entry. A strictly qualified empty reserved RC is pending
only under the physical result contract v2; malformed nonempty content remains
refused. It makes exactly one
launch attempt, including when physical admission refuses. This avoids inventing a second attempt outside
the retained evidence contract.

The current producer combines acquisition evidence and optional physical-layout
evidence in strict v3 receipts and plain launch bindings. Versions have one
closed meaning each:

| Record family | Preserved history | Current producer |
| --- | --- | --- |
| Transport observation | v1 unbound; v2 with validated non-null layout | Same v1/v2 shapes |
| Transport verification | v1 original; protected v2 with layout and no acquisition field | v3 requires acquisition tag and explicit layout value |
| Plain launch binding | v1 original; protected v2 retains original top-level fields and nested layout | v3 requires top-level and matching nested acquisition tag plus explicit nested layout |
| Plain result contract | v1 unbound; v2 with validated layout | Selected from validated layout, not launch-binding version |
| Artifact launch binding | v1 original; v2 acquisition-aware | Unchanged; no physical-root artifact extension |

For v3, `lane_root` is either a validated layout or explicit `null`; omission is
invalid. The configured branch emits a layout, while the unconfigured publisher
branch emits `null`. A v3/null binding retains result-contract v1 and cannot
interpret an empty RC as a physical reservation. New plain producers require
their exact v3 transport receipt; they cannot promote historical receipts by
inferring missing evidence. Mixed historical shapes and unknown fields refuse.

`pool` remains the canonical accounting family (`glm` or `bailian`). The separate
`acquisition_pool` records the successful controller acquisition and must match
the unique original lease event. It permits `glm-frontier` only with exact
`glm-5.3`; ordinary GLM and Qwen keep their finite existing tuples. Historical
v1 and protected v2 retain their original logical-pool interpretation and cannot
acquire frontier qualification from a model name or current routing metadata.

Physical collection checks current original registry agreement and reads the
retained physical path. Old v1 records and historical scopes cannot acquire a
root retrospectively. Authentication, producer packet-consumption attestation,
served-model/physical-host authentication, and business acceptance remain
unproven by these records.

`rollout/test_remote_lane_root.py` exercises the actual publisher, portable
transport reader, retained binding, generated collector, exclusive packet and
launch entries, and executor boundaries with inert fixtures. It covers alias
retargeting, same-path directory substitution, link/mode/hash changes, existing
leaf preservation, incompatible schemas, unsupported carriers, single-attempt
admission and supervised deadline expiry. No test starts a provider worker or
alters a live host/configuration owner. Passing these tests is source
qualification, not live installation, worker START, result acceptance, or
permission to replay any held operation.

## Composed native-closure qualification

After changing any file in the explicit native closure, rebuild the manifest and
source inventory, compare the complete closure against the selected generation,
and update the current `NATIVE_MANIFEST_SHA` binding in
`tests/test_fabric_native_security_composition_20261018.py` to the reviewed
manifest. Do not repin its historical executor, donor, quota, deadline or physical
root transformations merely to clear a test. The current manifest pin is distinct
from those preserved security preimages and transformations.

Run the composed regression before publishing a PR, not only the isolated
`ops/native_fabric` tests:

```sh
python3 -m pytest -q tests/test_fabric_native_security_composition_20261018.py
```

That test builds the exact closure, selects it through the existing publisher,
and exercises the remote-support/executor/outcome-binding seam using an inert
fixture. It does not contact a provider, acquire a host lease, or authorize a
production selection. The OPT-007 outcome correction changes only
`ext/provider_outcome.py` within the 85-file closure; its composed-manifest check
must move with that reviewed change.

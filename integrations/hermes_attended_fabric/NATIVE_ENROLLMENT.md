# Native attended-worker enrollment

## Current native configuration contract

The native host patch now contains **20 files**, with patch SHA256
`631d202a736dc511b359b518dc74ab9b9b84566b05d74bafb2bab7763ed94541`.
Its previous 15 postimages are unchanged. Worker runtime SHA256 is
`c3ce3f07017224947ea9ce28ac6744172c1fa08e767210bfbab23277d39205ee`.

The worker requires native `load_config_observational()`; an older native tree
without that API refuses enrollment. This reads current local configuration,
applies the existing user normalization and managed policy, and detects file,
symlink and deployment-selection changes. It does not initialize the home, make
backups, use a cached/worker snapshot or last-known-good fallback, boot a remote
backend, load external secrets, or repair dependencies.

The backend preserves only the existing process selectors `HERMES_HOME`,
`HERMES_CONFIG_BACKEND` and `HERMES_MANAGED_DIR` when starting its isolated
checker. The process deployment selects the backend and managed scope; the bound
served home selects the current document and the native PM dependency owner.
Arbitrary parent variables and credentials are not forwarded.

Enrollment permission lists must be actual lists of nonempty strings with
resolved values. An unresolved reference in enabled, disabled or MCP allowlist
policy refuses enrollment; unrelated credential placeholders are unaffected.
Malformed current YAML, malformed managed policy, unreadable inputs, dangling
policy links and current remote-backend selection all refuse without exiting
the Hermes agent.

Focused qualification: **16 native current-configuration checks, 17 fresh
process cases and all 25 real native worker-owner cases passed**, including
the actual Node backend, native MCP formatter and request-to-retained-result path.
The private dependency selection was produced by the real native PM with its
MCP feature; 74 offline worker, 78 Node backend and 7 preimage-safety checks also
passed. The cold checker
effect audit permits reads and rejects filesystem mutation, subprocess launch
and network contact. Worker install metadata and the final command engine remain
explicit fixtures; this is source qualification, not live activation.

## Source and custody

This contribution is developed in operation
`hermes-native-worker-binding-20261107-c2`, branch
`sol/web-hermes-native-worker-binding-20261107-c2`, from protected Mastermind
pin `4fb0d3825b5b4b4439e65e7382660112b7c2ef8c`.

The observed native ABI is Hermes v0.23.0 at
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Native checkout, profile,
gateway and existing live TUI writers retain their original custody.
This source change does not edit the native checkout or installed profile.

[#2175](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2175)
remains the application composition carrier, paired with Macro #10740.
[#2186](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2186)
and its H4 install lane own the current primary-inference/native activation.
Apply this contribution into those release inputs using their normal source
and writer fences. Do not publish a replacement application or native runtime.

The November 7 source milestone and original refused Fabric attempt are recorded
in [the program](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6707665917).
That original request remains on its own carrier. It is not a live worker and
must not be replayed by this plugin or used as an enrollment canary.

## Qualified release contents

The release must contain this complete package, including `plugin.yaml`,
`__init__.py`, `native_session.py`, `native_evidence.py`,
`enrollment_check.py`, the typed native port and the native MCP client.

The same release must contain the existing
`integrations/studio_direct_mcp/fabric-backend.mjs` and its incumbent dependencies.
The native JavaScript admission verifier is contained in that existing sealed
backend blob, preserving ordinary operator deployment. Native mode derives its
checker from `<HERMES_HOME>/plugins/mastermind-fabric-worker/enrollment_check.py`.
It verifies the existing native install record and the closed runtime file digest
before starting that checker, and rechecks after its return. Both the backend
blob and plugin pin must come from the same selected protected release.

The backend starts this fixed checker with Python `-I -B`. The checker loads
its private `__init__.py`, `native.py` and `native_evidence.py` directly from
those named source files, without sibling-package discovery or cached bytecode.
Its private package has an empty discovery path; the required modules retain
normal module identities and are registered before their source executes.
The native source and committed dependency environment keep their existing
explicit loading path. These checks do not install or activate the plugin.

The closed runtime file projection consists of `__init__.py`, `plugin.yaml`,
`native.py`, `facade_port.py`, `hermes_mcp_client.py`, `native_session.py`,
`native_evidence.py` and `enrollment_check.py`. `package_fingerprint()` in
`native_evidence.py` computes the digest from exact bytes in sorted filename
order. This is a projection of the selected release; no additional installation
record or publication owner is created.

Publish through the existing protected source and release workflow. Before
worker enrollment, select the native **MCP feature** in the same installation and
qualified profile through its existing PM:

```sh
HERMES_HOME="$HERMES_PROFILE_HOME" "$HERMES_NATIVE_LAUNCHER" pm install --extra mcp
```

Read back that owner's committed environment and recorded `mcp` extra, then let
the existing H4 activation/reload lifecycle use that generation. Minimal native
core environments do not contain the MCP SDK. Plugin publication by itself does
not select this optional native feature. Preserve any frozen feature policy and
previous explicit feature decisions; do not install packages during an agent
call or add a second dependency owner.

The native installation owner accepts the source
`mastermindx-market-intelligence/Mastermind#integrations/hermes_attended_fabric`
with `--ref <full-40-character-selected-release-SHA>` under `hermes plugins install`.
Use that existing installer in the qualified profile and H4 activation window.
It holds `plugin_update_lock`, uses `plugins_transaction.publish_plugin` and
`pm.client.sync_venv(StagedUpdate)`, and retains its existing rollback and target
digest checks. Do not copy live plugin files or write its metadata independently.

Read back `<HERMES_HOME>/plugins/.install-metadata.json`: the
`mastermind-fabric-worker` entry must contain source
`https://github.com/mastermindx-market-intelligence/Mastermind.git#integrations/hermes_attended_fabric`,
the selected exact `revision`, and `pinned: true`. Verify the installed runtime
file digest against the same release projection. A valid-looking native pin
alone is not proof of unchanged installed bytes. Preserve native active turns
and H4 gateway custody; source verification does not authorize a forced reload.

## Existing profile configuration

Merge these fields into the selected Hermes profile's existing configuration.
Preserve other plugins, MCP servers, settings, credentials and native files.
Paths below are placeholders resolved by the incumbent installer from its
qualified release and actual installed runtime.

```yaml
plugins:
  enabled:
    - mastermind-fabric-worker
  entries:
    mastermind-fabric-worker:
      mcp_allowlist:
        - mastermind-fabric-exec
        - mastermind-fabric-capacity
      native_origin:
        schema: mastermind.hermes_native_enrollment.v1
        enabled: true
        namespace: hermes-m2-default
      manual_routes: []

mcp_servers:
  mastermind-fabric-exec:
    lazy: false
    command: /absolute/path/to/qualified/node
    args:
      - /absolute/path/to/qualified-release/integrations/studio_direct_mcp/fabric-backend.mjs
    env:
      MMX_FABRIC_HERMES_HOME: /absolute/path/to/native-profile
      MMX_FABRIC_HERMES_SOURCE: /absolute/path/to/native-hermes-source
      MMX_FABRIC_HERMES_PYTHON: /absolute/path/to/native-python
      MMX_FABRIC_HERMES_REVISION: <full-selected-protected-release-SHA>
      MMX_FABRIC_HERMES_PACKAGE_SHA256: <closed-runtime-package-SHA256>
      MMX_FABRIC_ADAPTER_PATH: /absolute/path/to/incumbent/fabric_task.py
    tools:
      include: []
```

Merge `mmx_fabric` into the profile's existing `platform_toolsets.cli` list,
retaining every other intended selection. The ordinary native CLI, TUI and
Desktop gateway use that same `cli` policy. Newly discovered plugin toolsets
are normally enabled automatically, but an existing known-and-omitted selection
can hide this tool. Preserve intentional `agent.disabled_toolsets`,
`HERMES_TUI_TOOLSETS` and coding-focus restrictions; qualify the actual selected
user path instead of replacing its policy with a broader default.

The stable namespace is an enrollment identity. Retain it across ordinary
restarts, compression and source upgrades so original task identities remain
recoverable. Changing namespace or moving a profile requires reconciling
existing tasks before a new origin is used.

The five `MMX_FABRIC_HERMES_*` values are all-or-none. The first three are
absolute installed paths; `REVISION` is the selected full 40-character commit,
and `PACKAGE_SHA256` is the selected release's closed runtime digest. These
are source/deployment identity fields, not credentials or model arguments.

Compute the package digest from the exact qualified release with
`package_fingerprint(Path("integrations/hermes_attended_fabric"))`, imported
from its `integrations.hermes_attended_fabric.native_evidence` module. The
backend independently computes the same closed file map before helper execution.
It rejects replaced plugin-slot links, foreign/missing install records, revision
mismatch and changed runtime bytes. The helper imports the installed directory
as a private package; it does not require an ambient repository checkout.

The existing release owner supplies these identities together with the backend's
existing blob seal. Native enrollment also refuses inherited operator-child,
operator-capability, canonical-paid-control or prelease-handoff context and a
nonzero operator-child budget. It never clears or borrows another operation's
identity. The existing request owner receives an ordinary WORKER request with
the explicit native root/parent; no Executive Job or `--native-return` identity
is invented. A native-scoped backend never falls back to broad operator authority
if the package, enrollment or database is unavailable.

`tools.include: []` uses Hermes's existing MCP inventory filter to keep raw
Fabric tools out of ordinary model discovery. Keep `lazy: false`: eager native
discovery retains the connected server before applying this filter, whereas a
cached lazy server with no registered tools can lose its connection definition.
The native plugin uses `PluginContext.call_mcp` through its existing per-server
allowlist, independently of model-visible raw tools. Server-side origin
enforcement applies even if a raw call is attempted. The native default trust
policy needs no additional enrollment flag; preserve any explicit existing
untrusted-server or spending policy rather than overriding it.

The existing read-only capacity server may remain for preview. It is optional
in this plugin's allowlist and must retain its own qualified configuration.
Its presence does not grant execution.

`manual_routes: []` leaves AUTO routing available. To grant manual selection,
the incumbent installer can add exact existing pool/model pairs permitted by
the current native route policy and user assignment. The Fabric adapter still
checks current quota, capability, consent and strict pinning. No provider
credentials are copied into this plugin or checker.

Register the plugin through the normal native owner and verify its actual
loaded entry and `mmx_fabric_worker` schema. Local enrollment is checked during
discovery without opening MCP. After native MCP startup, the first persisted,
current invocation attests the same enrollment through the existing client
before any operation. Missing local enrollment prevents registration; missing
or changed remote enrollment prevents dispatch. No watcher, separate client,
registration retry loop, or forced startup order is introduced. Successful
import alone is not a mount receipt.

## Native source qualification

Run against the exact composed release and actual native dependency selection.
Do not invoke native bootstrap or dependency repair merely to import the
qualification code.

```sh
python3 -m unittest discover -s integrations/hermes_attended_fabric/tests -p 'test_*.py' -q
node --test integrations/studio_direct_mcp/fabric-backend.test.mjs integrations/studio_direct_mcp/fabric-backend-capacity.test.mjs integrations/studio_direct_mcp/fabric-diagnostics.test.mjs
```

Use a private source fixture made from the exact pinned native base and current
20-file patch. Prepare a **new, empty qualification home** through the original
native PM, selecting its declared MCP feature:

```sh
python3 -I -B integrations/hermes_attended_fabric/tests/prepare_native_qualification.py --native-source "$HERMES_NATIVE_FIXTURE" --fixture-home "$HERMES_QUALIFICATION_HOME" --runtime-dir "$HERMES_PM_TOOL_STORE"
```

The helper refuses an existing home and records a fixture marker only after the
native PM commits its real dependency selection. Reconcile a failed preparation
before another attempt. Use the interpreter under the returned
`dependency_environment` as `HERMES_QUALIFIED_PYTHON`:

```sh
"$HERMES_QUALIFIED_PYTHON" -I -B integrations/hermes_attended_fabric/tests/run_native_owner_qualification.py --native-source "$HERMES_NATIVE_FIXTURE" --fixture-home "$HERMES_QUALIFICATION_HOME"
"$HERMES_QUALIFIED_PYTHON" -I -B integrations/hermes_attended_fabric/tests/observational_native_qualification.py --native-source "$HERMES_NATIVE_FIXTURE" --fixture-home "$HERMES_QUALIFICATION_HOME" --node "$HERMES_QUALIFIED_NODE"
```

The wrapper establishes the fixture home before the first native import and
explicitly fences startup recovery, launcher preparation and dependency
activation in the test process. Actual SessionDB, turn leases, PluginContext,
middleware, registry, native source, committed dependencies, Node facade and
cold checker execute. The worker installation record and final Fabric command
engine are fixtures. The cold checker does not inherit parent monkeypatches.

Do not run the test module directly against a live checkout. Adding a dependency
site directory before importing `run_agent` does not prevent native bootstrap
from replacing the interpreter or publishing startup state.

Record the exact source head, native head, suite totals and exit codes in the
existing release proof. The ordinary protected CI remains required on the
composed release; the explicit native ABI suite supplements it.

## Installed acceptance

The current source evidence is not installed acceptance. The qualified H4
activation must produce the following receipts on the actual native path:

1. Actual release and native identity, effective profile enrollment, execution
   MCP capabilities, loaded plugin entry and model-visible schema.
2. One fresh native attended turn with its own bounded task key and packet;
   AUTO decision, native admission, actual worker START and chosen pool/model.
3. Terminal retained output, exact digest, original native parent consumption,
   and the existing acceptance owner's conclusion.
4. An authorized exact manual route when one is granted, with the selected
   pool/model held to that pin and any unavailable model refused.
5. Original-run status/result recovery after native interruption or restart,
   stale-turn refusal and no duplicate request effects. Recovery reads the
   original run; it does not resubmit an uncertain task.
6. Capacity/account refusal and switching behavior governed by the incumbent
   router. Pre-task rejection may use existing admitted continuation; an
   ambiguous or started task never silently switches carriers.

For each receipt distinguish controller creation, worker START, terminal
result, delivery, acceptance and deployment. Preserve existing unknown effects
and active native writers throughout activation.

Rollback uses existing owner configuration and native registration disposal:
disable this plugin's native-origin enrollment, let existing sessions reconcile,
then remove only its exact native registration through the incumbent lifecycle.
A configuration rollback does not cancel or erase already admitted Fabric runs.

## Source qualification recorded on November 7

The current contribution passed these focused checks on M2 after the startup
ordering fix and after folding the JavaScript verifier into the incumbent
backend blob:

| Check | Observed result |
| --- | --- |
| Existing package unittest discovery | 68 passed; exit 0 |
| Existing Fabric backend, capacity and diagnostic Node suites | 135 passed; 0 failed/skipped; exit 0 |
| Explicit native owner, installed layout, actual MCP formatter and server-verifier suite | 22 passed; 0 failed/skipped; exit 0 |
| Selected canonical pytest package and exact identity-review cases | Command completed; exit 0 |
| Compile, whitespace and the unchanged escalation-limit source review pin | Passed; exit 0 |

The selected pytest command was
`python3 -m pytest tests/test_hermes_attended_fabric.py tests/test_executive_fabric_release_identity_review.py -q -k 'hermes or native'`.
The repository's quiet pytest settings did not emit a final case count, so none
is inferred here.

The native suite includes actual directory-plugin loading before MCP readiness,
first-use attestation, the installed MCP formatter and JSON-text envelope,
read-only capacity preview, unpersisted calls, duplicate tasks, interruption,
response loss, compression, lease loss, foreign origin, result recovery and
revocation during async preflight. It also rejects mismatched installed source
pins, changed runtime bytes and replaced plugin-slot links. The Node suite
independently proves that an unsealed helper cannot execute, using a real child
process as its positive control.

These checks use temporary profiles, a copied runtime package and fixture native
install metadata. They exercise the real native loader and APIs; they do not
claim that the native installer transaction ran. The final paid execution
boundary remains a fixture. The qualified runtime file projection is
`c099a74d4ec0f68a4623ba56191e93c0a64e7d3384e6bdd9773793887e7de927`.

This is author source qualification with focused principal integration
judgment. It is not a formal GitHub APPROVED review, protected merged-source
proof, a native install, or a provider/worker acceptance receipt.

### Hosted baseline repair retained from its original source

The first contribution head13b5 hit the existing
`ComposedPreservingMigrationTests.test_composed_preserving_migration_imports_then_observes_once`
failure in [CI shard0](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42381586802/job/128430824459).
That run reported684 Studio cases with one failure; it is not counted as green.

The original H6/C2 fix is adopted unchanged from primary contribution
`c40f58b42383684e0ded1db7a7cb48741ddb7abf` as a coherent pair:

- `control_bundle_closure_test.py`: Git blob `dc17d077a6a0f787db857a6c1f66f0ad354ea857`.
- `private_service_original_delivery_test.py`: Git blob `41dae1f1e0f29b542137ebf53f01a3e16b7f473d`.

[The existing hosted observation job](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42381637919/job/128430305746)
shows that exact case passing in three contexts. That diagnostic job remains red
because other full-discovery fixtures lacked their historical Git inputs; it
is not relabeled as a passing whole job.

The pair requires the current application target's original service API.
Running it alone on the older protected parent reports missing
`ORIGINAL_COLLECTION_LEGACY_SCHEMA`, so it must be qualified on the actual
composed target. The production guard and original assertions are preserved;
no new parallel fixture repair, skip, or runtime relaxation is introduced.

### Current verified successor projection

The successor-identity extension preserves the original logical run and projects
`effective_run_id` only from a qualified incumbent status/result. Nested status
and continuation identities must agree; an absent successor never authorizes a
replacement submit of the original task. Result currentness is checked again
after retrieval, including the effective leaf.

The current eight-file runtime projection is
`e010d6366c8142e977ffab2f591656e6ea17fe6725d262c937abf065365a51b9`.
The earlier `c099a74d` projection above belongs to the previous milestone.
The updated source passes74 worker contract cases and22 actual native owner
cases with zero failures/errors/skips. The native MCP status double now carries
the same original/effective IDs as the existing wire contract; the production
absence/currentness checks were retained. The package/identity gate also passes.
This remains source qualification; the actual native install and paid worker
START/result-consumption path still require their own receipts.

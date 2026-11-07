# Native attended-worker enrollment

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
backend blob, preserving ordinary operator deployment. Native mode additionally
requires the complete Python package above; the checker resolves it from that
same release. Mixing package files from unrelated heads is unsupported.

Publish through the existing protected source and release workflow. Install
the plugin directory using the existing Hermes plugin lifecycle after its
release identity has been verified. Preserve native active turns and the H4
gateway custody; source verification is not authorization to force a reload.

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
    command: /absolute/path/to/qualified/node
    args:
      - /absolute/path/to/qualified-release/integrations/studio_direct_mcp/fabric-backend.mjs
    env:
      MMX_FABRIC_HERMES_HOME: /absolute/path/to/native-profile
      MMX_FABRIC_HERMES_SOURCE: /absolute/path/to/native-hermes-source
      MMX_FABRIC_HERMES_PYTHON: /absolute/path/to/native-python
      MMX_FABRIC_ADAPTER_PATH: /absolute/path/to/incumbent/fabric_task.py
    tools:
      include: []
```

The stable namespace is an enrollment identity. Retain it across ordinary
restarts, compression and source upgrades so original task identities remain
recoverable. Changing namespace or moving a profile requires reconciling
existing tasks before a new origin is used.

The three `MMX_FABRIC_HERMES_*` values are all-or-none and must be absolute.
They select the existing native owner; no model input can change them. A
native-scoped backend never falls back to broad operator authority if native
enrollment or the database is unavailable.

`tools.include: []` uses Hermes's existing MCP inventory filter to keep raw
Fabric tools out of ordinary model discovery. The native plugin uses
`PluginContext.call_mcp` through its existing per-server allowlist. Server-side
origin enforcement applies even if a raw call is attempted.

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

On the observed M2, use the installed native Python with its already committed
dependency environment to run the explicit native owner suite:

```python
import runpy
import site
import sys
from pathlib import Path

native = Path("/Users/chriswong/.hermes/hermes-agent")
sys.path.insert(0, str(native))
from pm.environments import committed_venv, site_packages

site.addsitedir(str(site_packages(committed_venv(native))))
sys.path.insert(0, str(Path.cwd()))
runpy.run_path(
    "integrations/hermes_attended_fabric/tests/native_owner_qualification.py",
    run_name="__main__",
)
```

The native suite uses temporary profiles and the actual installed SessionDB,
turn lease, PluginContext, middleware and tool registry. It does not alter the
live profile, install the package, contact a provider, or run a paid worker.
The server wire cases invoke the actual Node facade and read-only native checker;
the final Fabric command engine remains a fixture.

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
| Existing package unittest discovery | 67 passed; exit 0 |
| Existing Fabric backend, capacity and diagnostic Node suites | 132 passed; 0 failed/skipped; exit 0 |
| Explicit native owner and actual server-verifier suite | 18 passed; 0 failed/skipped; exit 0 |
| Selected canonical pytest package and exact identity-review cases | Command completed; exit 0 |
| Compile, whitespace and the unchanged escalation-limit source review pin | Passed; exit 0 |

The selected pytest command was
`python3 -m pytest tests/test_hermes_attended_fabric.py tests/test_executive_fabric_release_identity_review.py -q -k 'hermes or native'`.
The repository's quiet pytest settings did not emit a final case count, so none
is inferred here.

The native suite includes cold discovery before MCP readiness, first-use
attestation, unpersisted calls, duplicate logical tasks, interruption, response
loss, compression lineage, current lease loss, server rejection of missing or
foreign origin, original result recovery, and policy revocation during async
preflight. It uses real native owners with temporary profiles and a fixture
at the final Fabric execution boundary.

This is author source qualification with focused principal integration
judgment. It is not a formal GitHub APPROVED review, protected merged-source
proof, a native install, or a provider/worker acceptance receipt.

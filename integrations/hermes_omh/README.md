# OMH graph planning for Mastermind

This package reuses the pinned MIT **Oh My Hermes v4.0.6 DAG core**, not the OMH
plugin, persisted DAG runner, memory provider, installer or dispatch machinery.
It turns a bounded graph definition into a plan proposal accepted by the existing
Executive v4 parser. It does not execute the plan.

## Try the complete local consumer path

From the Mastermind repository, with its normal Python environment:

```sh
python -m integrations.hermes_omh --input integrations/hermes_omh/example.json
# Equivalent bounded stdin path:
python -m integrations.hermes_omh < integrations/hermes_omh/example.json
python -m pytest -q -o addopts='' tests/test_hermes_omh.py
```

Success is one JSON object with `state: PREPARED_NOT_ADMITTED`, `admitted: false`
and `dispatched: false`. Its `plan` is `mastermind.execution_plan/v4`, validated
by the original `control_plane.executive_orchestration_result._validate_plan`.
`plan_sha256` hashes that proposal through the original canonical serializer;
it is **not** a Runtime receipt, permission grant, result seal or acceptance.

The example uses illustrative identity strings, not live Jobs or Attempts.
The output contains supplied objective text; handle stdout as task content and
do not redirect private plans into public logs. Nothing is saved automatically.
Errors return only `{"state":"REFUSED","reason":"<closed code>"}` and exit 2.

## Python API

```python
from integrations.hermes_omh import prepare_execution_plan

proposal = prepare_execution_plan(
    nodes,
    policies=policies,
    root_job_id=expected_root,
    plan_attempt_id=expected_planner_attempt,
)
```

The graph uses **definition-node fields**, not a serialized `omh_dag/v1` runtime
record: `id`, `label`, `category`, `prompt`, `depends_on`, `write_scope`, `role`.
All seven are required here, including an explicit `role` from `build`,
`baseline`, `verify`, `review`. IDs follow the donor's lowercase 32-character
format. Prompts are at most 3,000 characters, labels 80 and categories 64.
There must be 1–8 nodes, matching the existing v4 plan limit. No implicit split,
new root or descendant grant is created for larger graphs.

`policies` must cover exactly those IDs. Every policy explicitly supplies:
`business_impact`, `review_required`, `requested_authorities`,
`allowed_write_paths`, `validation_ids`, `attempt_limit`, `cost_class`.
The incumbent parser validates these values. A node's write scope must be a
lexical subset of the supplied policy and narrows the corresponding proposal.
Neither categories nor roles choose models, providers, cost, permissions or
review requirements. A node named `verify` never proves a check ran.

**All inputs are proposal data.** The function does not authenticate a caller,
establish that a policy was issued, or prove that an ID names a real current
operation. A host-integrated planner must supply its actual expected identity
and authorized policy through its existing binding. It must then return the
prepared `plan` as the normal planner role result through the existing
orchestration envelope/sealing/admission path. This package neither constructs
an authoritative result envelope nor submits to Executive or Fabric. The
selected-child and attended-Fabric ingress remain unchanged.

## Topology and scope semantics

The wrapper rejects duplicate IDs/edges, unknown dependencies, self-edges and
cycles **before** invoking the donor. Stable dependency-layer ordering preserves
input order within a layer and emits only lower-ordinal prerequisites. The
critical path is an **unweighted node-count path**, not a duration estimate.
Bottlenecks count transitive dependents; these are explanations, not scheduling
or readiness decisions.

Scopes must be relative POSIX literal paths. Absolute/traversal/glob/drive/UNC,
control or format characters, ambiguous path components and reserved DOS names
are refused. No path resolution, file inspection or filesystem mutation occurs
in the pure API. Directory ancestry and conservative case/Unicode aliases
count as overlaps. Unordered overlapping writers refuse; a transitive dependency
order permits sequential writers. Case/Unicode folding is used only to detect
conflicts, **never to widen policy containment**.

Lexical validation is not symlink isolation, a filesystem lease or enforcement
of what a future worker actually writes. Existing workspace, Runtime, grant and
worker controls must enforce those boundaries. No restart re-offer, repair loop,
quota fallback or uncertain-effect retry is imported from OMH.

## Bounded local transport

Input and output are capped at 131,072 bytes; in-memory validation bounds depth
at 12 and visited values at 4,096 before copying/serialization. JSON duplicate
keys, nonfinite values, non-UTF-8 data and excessive nesting refuse. Only exact
plain Python data is accepted; hostile Mapping subclasses are not inspected.

`--input` is an operator-selected local path, not a model-facing filesystem
capability. The CLI requires a regular file, rejects a final-component symlink
using `O_NOFOLLOW`, checks the open descriptor and reads at most the byte budget
plus one. Parent-directory symlinks are not an isolation boundary. Where the OS
cannot provide `O_NOFOLLOW`, use stdin rather than weakening the file check.
No Hermes/OMH home, provider configuration or credential is discovered or read.

## Provenance and qualification

Donor commit: `5ead1032360edadd4b3a749f234f3830324de3b2`.
The unmodified `vendor/dag_core.py` is Git blob
`e4bdf90bb03206b0eed806396196762cb5daa091`; its SHA-256 is
`790c6d717e3e5bed54aec45662c9affa6006634aa7e6619d0af143789da53854`.
`vendor/PROVENANCE.json` records both copied files. The upstream MIT notice is
retained in `vendor/LICENSE` and in the package initializer so Python-package
copies retain it without requiring an implicit data-file packaging rule.

Tests live in `tests/test_hermes_omh.py`, where the existing main CI test gate
actually discovers them. The suite tests canonical parser interoperability,
path/scope refusals, malformed transport, detached results, no-IO preparation,
donor integrity and all 1,536 permutations of four-node forward-edge DAGs.
These are deterministic compatibility/safety checks, **not** a measured claim of
better model task success, lower cost or production adoption.

No native tool is registered or role profile changed by import, CLI execution,
or source publication. Live Hermes enrollment and the broader memory/skill/
verification adoption remain separate work in the existing Hermes programme.

## Native bridge and existing OMH recommendations

`bridge_cli.py` accepts `status`, `plan` (the existing proposal object), or `recommend` (message plus explicit OMH category). A host supplies an absolute OMH routing home; model arguments cannot select a path, provider or account. Recommendations use the installed OMH package's own ranker and chain parser. Invalid override documents refuse rather than silently falling back. Only `routing/model-chains.json` is read; auth and memory stores are not consulted.

The dependency-free `plugin/` payload registers `mmx_omh` through the real Hermes `PluginContext`. Its operator-generated `_runtime.json` binds one profile, immutable source closure, hashes, approved Python executable and routing home. It invokes only the fixed bounded CLI, without shell expansion, ambient API keys, retries or external inference. The native registry and registration leases remain responsible for tool scope/unload. It does not provide a memory provider, scheduler or alternate worker entry point.

`qualification/native_canary.py` exercises real installed Hermes plugin discovery and registry dispatch with a temporary profile, the actual OMH package, canonical parser and cross-profile negative. This is native integration qualification, not a production conversation, worker admission, entitlement or serving-model proof.

Source publication alone does not install the descriptor or enable the tool. Install from the exact protected release using Hermes' existing plugin installer with `--no-enable`, populate the reviewed descriptor and immutable local source artifact, then enable through the native plugin control. Never overwrite an existing unrelated install or replace the selected OMH memory provider.

### Existing conversations

After native activation, use `/mmx-omh status` or `/mmx-omh quick Inspect the failing test`. These commands use the existing gateway command registry and the same read-only bridge, so they do not require resetting an ongoing conversation. The Python `mmx_omh` tool becomes available to the model in a fresh session according to Hermes' prompt-cache contract. An activated command is not a worker start or provider call; all outputs retain the proposal/advice boundary.

### Canonical Capacity routing preview

The native `mmx_omh` tool also accepts `action: route`, with `message`,
`category`, `task_class` and `complexity`. For example:

```json
{"action":"route","category":"quick","message":"Inspect the existing capacity contracts","task_class":"census","complexity":"C1_ROUTINE_BOUNDED"}
```

The existing command offers the same path:

```text
/mmx-omh route census C1_ROUTINE_BOUNDED quick Inspect the existing capacity contracts
```

This runs OMH's existing recommendation and calls
`mastermind-fabric-capacity/fabric_route_preview` once through Hermes'
`PluginContext.call_mcp`. The host must already enroll that read-only MCP server
and authorize it in `plugins.entries.mastermind-omh.mcp_allowlist`. The plugin
does not edit that grant or create another client, connection manager, selector,
account ledger or execution endpoint.

Task class and complexity are explicit requirements in the incumbent Capacity
wire schema. An OMH category such as `quick` is **not** evidence that work is
mechanical or low risk, so there is no invented category-to-complexity mapping.
OMH aliases and reasoning efforts remain advice; they are never forwarded as a
model, pool, account, fallback or entitlement. Only the two task requirements
are sent to the capacity preview. The prompt itself is not sent.

A successful result is `ROUTE_PREVIEW_NOT_ADMITTED`, with separate
`recommendation`, `routing_requirements` and `capacity_preview` fields.
The canonical preview must say `PREVIEW_ONLY`, `reserved: false` and
`selection_rechecked_at_request: true`. The outer result retains
`selected_model: null`, `admitted: false` and `dispatched: false`.
The preview may disagree with OMH; that does not authorize an OMH fallback.

Missing MCP permission, owner refusal, missing capacity, malformed/truncated
output, or profile/source/registration drift produces a closed refusal without
returning a locally selected model. A closed canonical refusal code is preserved
as `capacity_reason` when supplied. The adapter makes no additional retry;
native MCP trust, transport recovery and uncertain-effect rules remain owned by
Hermes.

This completes the native advisory-to-canonical-preview connection. Actual
delegated work still uses the existing `mmx_fabric_worker` or Executive-selected
`mmx_delegate` under its real native admission. Primary conversation inference
uses the separate APPLICATION integration. Ordinary Hermes `delegate_task`
creates another agent/model-call loop and does not inherit an authorized
APPLICATION child binding merely by copying a provider name. Neither a preview,
a local child-count setting nor an estimated subscription allowance proves that
concurrent calls share the accepted physical-account ledger.

For native qualification, the existing `qualification/native_canary.py` accepts
`--capacity-config /Users/chriswong/.hermes/config.yaml`. It reuses only the
observed M2 read-only MCP declaration in an isolated profile, exercises the real
native loader/registry/client and verifies forced-pool refusal. No production
profile, provider credential, admission or worker request is changed by the
canary.

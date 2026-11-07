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

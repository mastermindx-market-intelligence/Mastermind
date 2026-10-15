# Worker launch preparation

Prepare complete worker inputs without replacing the existing Craft compiler,
Agent OS memory, provider adapters, pool leases, or Executive lifecycle.

## What this installs and what it does not

This source provides preparation commands, read-only observations, candidate skill
packages, and a thin input adapter to the existing pool dispatcher. It does not
supply credentials or make a provider inherit ChatGPT's connected apps. It does not
install native CapabilityPackage grants or enable Executive child submission.

Use the exact reviewed source checkout or immutable staged release. The inherited
Craft compiler and `control_plane/worker_craft.py` must be present. Do not substitute
an independently rewritten brief compiler when those dependencies are missing.

The examples below invoke the source CLI directly. `pool context`, `pool doctor`,
`pool prepare` and `pool render` are aliases only after the existing owner's wrapper
rollout is complete. Merely generating a wrapper candidate does not install them.

## Prepare one real assignment

First recover the current assignment, exact source refs, permitted workspace/paths,
acceptance criteria, original return path, and existing execution grant. A complete
example of the underlying commission shape is already supplied by the Craft owner:
`research/worker_craft/examples/ceo-commission-request.json`. Its fixture assignment
and source refs are examples, not a current worker authorization.

### Observe the intended execution scope

On the host where the eventual worker will run, make bounded harmless observations:

```bash
python3 ops/fabric_launch/cli.py doctor \
  --mission-ref assigned-operation-ref \
  --workspace /absolute/assigned/workspace \
  --output /absolute/new-tool-observations.json
```

Optional `--repository owner/repo` checks a real `gh` read. Optional
`--service studio-read` or `--service openai-docs` checks the fixed existing read
endpoint with a real read action, not just a server list. Do not supply secrets.

A successful host-side observation is not a claim about the future model's actual
exposed tool set, write rights or native Skill loading. Those are checked again in
the admitted native execution. Missing or denied tools remain explicit states.

### Retrieve current project context

Where the existing Macro Agent OS owner is installed on the controlling host:

```bash
python3 ops/fabric_launch/cli.py context \
  --workstream EXISTING-WORKSTREAM-KEY \
  --budget 4000 \
  --output /absolute/new-context-bundle.json
```

This passes through `compile-context` without rewriting, re-ranking or hiding its
accounting. It requires an exact existing workstream. An unavailable owner or
unresolved workstream is not replaced by fabricated memory. Preserve the bundle's
no-answer, degraded, excluded and omitted information. Do not drop mandatory
constraints when the owner's bundle exceeds its requested budget.

Select only facts needed by the assignment, each with canonical owner, reference,
revision, observed_at, content and required flag. The launch supplement has bounded
inline space; larger assigned documents can remain exact tool-readable references.

### Compile through the existing Craft owner

Create the `mastermind.fabric_launch_input.v1` object described in
`skills/mastermind-worker-bootstrap/references/launch-input.md`. Its `commission`
field is the existing complete Craft request, not a new shortened task format.
Use the same assignment reference in commission, context and observations. Required
tools must have fresh evidence for the intended scope; optional gaps remain visible.

```bash
python3 ops/fabric_launch/cli.py prepare launch-input.json \
  --output /absolute/new-launch-packet.json
python3 ops/fabric_launch/cli.py render /absolute/new-launch-packet.json
```

Outputs are exclusive new files. `render` recomputes the packet through the same
compiler and refuses expired evidence, source-method drift and tampering. Preparation
always returns PREPARED_NOT_ADMITTED and grants no execution authority.

### Deliver through the original dispatcher

Only after the existing model, account, host, capacity, workspace and effect gates
are clear, use the original pool path. The explicit adapter below changes input
preparation only; it calls the same `remote_sub.sh` exactly once:

```bash
python3 ops/fabric_launch/pool_entry.py \
  --kit /absolute/existing/fabric-kit remote \
  admitted-host admitted-mode /absolute/new-launch-packet.json \
  /absolute/assigned/workspace admitted-model \
  --out /absolute/result.stdout
```

The model/host/mode values come from the existing placement owner, not this module.
Full prepared packets require exact bound scope and do not preselect an automatic
host. `--dry-run` remains effect-free. Plain legacy prompts receive the small
bootstrap plus one known class method; no structured project context is invented.

The parent consumes and independently verifies the returned artifact and proof.
On error, retained input belongs with the existing carrier's evidence. Never replay
an uncertain dispatch, switch providers, or relax policy to obtain a refused effect.

## Candidate package and wrapper release

```bash
python3 ops/fabric_launch/plugin.py --source-sha EXACT_COMMIT \
  --output /absolute/new-workforce.zip
```

The optional `--with-public-docs` variant adds only the public OpenAI documentation
MCP endpoint. Both variants preserve the existing Craft skill bytes, use a
source-specific version, and are PACKAGED_NOT_INSTALLED. The bootstrap-only private
ChatGPT plugin is a separate distribution of that one unchanged skill; it is not an
all-worker or all-account installation claim.

`install.py` stages immutable source content. `--candidate-output` prepares a
reviewable wrapper candidate. It checks existing Studio pins and does not edit them.
An ordinary activation refuses when enabled Studio consumers expect different bytes.
Use the existing Studio publication owner's coordinated stopped-service upgrade and
verification process; do not edit pin hashes manually or weaken the refusal.

Native Skill/profile admission, authenticated app enrollment, global wrapper rollout
and exact-provider live proof are separate release conditions. Source CI or one
successful worker never grants all of them.

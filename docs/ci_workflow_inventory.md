# Offline workflow inventory

## Purpose

Produce a reproducible, reporting-only inventory of workflow execution dependencies
before changing a runner image, routing label, repository access, or deployment
environment. It complements `scripts/ci_run_profile.py`: that tool measures a
captured run; this tool describes source configuration. Neither grants execution
or release authority.

## Delivery scope

Operation: `ci-workflow-inventory-20261112-c3`.
Source baseline: `81c08810fbacad1391a0dde32893e18fc5207272`.
Source author: assigned engineering session; isolated GitHub-native branch.
Direct implementation rationale: small, coupled offline utility and acceptance
fixtures have lower total overhead in the principal session.

The source paths are `scripts/ci_workflow_inventory.py`,
`tests/test_ci_workflow_inventory.py`, and this document. No workflow, check
name, release controller, runtime service, credential, or repository setting is
part of this change. Existing CI timing and runner-routing work keeps its own
source ownership.

| Step | Dependency | Acceptance |
| --- | --- | --- |
| I1: source reader | Exact workflow bytes | Bounded local reads, SHA-256 per file, explicit parse/read errors |
| I2: derived inventory | I1 | Triggers, job IDs, runner selectors, matrix context, dependencies, action references and relevant capability flags |
| I3: negative qualification | I2 | Malformed YAML, ambiguous mapping keys, dynamic selectors, missing directories and symlink boundaries remain explicit |
| I4: real-input proof | I3 | Report current workflows without executing source or changing any routing |
| I5: source delivery | I4 | Exact-head diff, focused tests and existing protected release checks |

## Interface

```bash
python -B -m scripts.ci_workflow_inventory --root /path/to/repository
```

The command reads the immediate `.github/workflows/*.yml` and `*.yaml`
files and prints JSON to stdout. It uses the project's existing PyYAML dependency,
does not call GitHub, spawn a process, execute workflow expressions, write files,
follow symlinked workflow paths, or inspect local credential stores.
Use `-B` to suppress Python's implicit bytecode-cache writes as well.
Shell redirection is an operator's optional output choice. Exit status 0 means all
discovered files were inspected; status 2 means coverage is incomplete. Neither
status is a migration or release verdict.

The parser preserves the `on` key, detects duplicate keys, bounds file and alias
sizes, and reports malformed scalar construction without echoing source text.
Plain step shell names are retained; custom command templates are represented by
SHA-256 digests. General scripts, environment payloads and checkout credentials
are omitted. Selected names and selectors still come from source, so the report
is not a credential sanitizer and needs review before publication.

Static labels are configuration facts, not proof that any runner exists, is
online, is eligible for a repository/group, has spare capacity, or can run the
job. Dynamic expressions are not evaluated. Nested matrix expressions are marked
as dynamic, literal dot/bracket axis references retain routing choices, and
unsupported or missing routing alternatives are marked unresolved. Matrices are
reported as declared dimensions; the inventory does not infer actual event-time
expansion, conditional execution, peak concurrency, or billing.

The report does not certify readiness, isolation, private access, correct
permissions, complete dependency closure, or deployment safety. Missing/invalid
input must not produce a success-shaped empty inventory. The command is not a
new CI gate and is not wired into workflows.

## Consumer verification still required

Use authenticated existing GitHub readers to pair source selectors with actual
runner/group access, workflow enablement, required check contexts, plan
entitlements, app permissions and real run evidence. Reusable workflows and local
actions need their own source inspection. Repository-level tokens do not prove
cross-repository access. Inspect Pages, packages, releases, anonymous byte URLs,
submodules and real machine consumers separately.

Keep untrusted PR jobs separated from credentialed deployment/production hosts.
Preserve required check names, existing trust controls and release holds when a
later, independently qualified routing change is proposed.

## Qualification

The focused unit suite covers valid and incomplete inputs, permission inheritance,
checkout capability shape, matrix routing, malformed scalar constructors, output
minimization and local filesystem boundaries. It uses `unittest` and is also
collectable by the existing pytest suite:

```bash
python -m unittest discover -s tests -p test_ci_workflow_inventory.py -v
```

Real-input verification used 186 exact workflow files across six repository
snapshots, with 388 declared jobs and no inspection errors. Source files were
checked against their Git blob IDs before the CLI was run. This demonstrates a
consumer path for the inventory; it does not certify runtime enablement,
transitive dependencies, runner eligibility or capacity. Matrix instances are
not expanded into job counts. The tool performs partial structural inspection,
not full GitHub Actions schema validation. Filesystem checks assume a stable
snapshot and are not a defense against a concurrent hostile filesystem writer.


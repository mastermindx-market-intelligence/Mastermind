# Mastermind Craft: role methods and complete briefs

This is an independently usable **authoring** slice of the existing workforce
capability program. It does not install a fleet capability or introduce a new
registry, router, source owner, native package materializer, tool gateway or runtime.
The wider integration is in [MASTER_PLAN.md](MASTER_PLAN.md).

## What it does

One Skill provides eight progressive-loading playbooks: orchestrator, designer,
frontend, backend, researcher, data-scientist, reviewer and verifier. A small
standard-library Python compiler checks a complete assignment brief and loads only
the common method plus the selected role. The result is ordinary task content,
not an installed Skill or authorization receipt.

## Run it

Python 3.9+ is the intended language baseline; the evidence record states the actual
interpreter tested. No dependencies or network are required.

```sh
python3 mastermind-craft/scripts/brief.py compile examples/program-brief.json --format markdown
python3 mastermind-craft/scripts/brief.py compile examples/design-brief.json
python3 mastermind-craft/scripts/brief.py compile-commission examples/ceo-commission-request.json --format markdown
python3 -B -m unittest discover -s tests -v
```

The compiler reads the explicitly supplied non-secret file and fixed local method
files, then writes to stdout. Redirect output only to your own permitted authoring
location. It never starts a process, connects to an app, changes provider config,
selects an account/host or writes an output file itself. Tests invoke its CLI in
local subprocesses; they do not invoke model providers.

The JSON output includes input/method/Markdown hashes for reproducibility,
`execution_authority: false`, `runtime_admission: NOT_REQUESTED`, and
`source_verification: NOT_PERFORMED`. Supplying an assignment/workspace/host reference
does not make it valid. Null references remain explicitly unbound authoring.

The illustrative design brief assigns no actual screen or Paper mutation. The
program brief records this source-authoring outcome, not an Executive Job.

## Compact CEO commission input

Schema `mastermind.craft_commission_request.v1` is normalized through this same
compiler into the existing complete brief; it is not a second brief system. Its closed
top-level contract is: `schema_version`, `role`, `authority_ref`, `source`,
`outcome`, `scope`, `inputs`, `data`, `method`, `deliverables`,
`acceptance`, `failure`, `constraints`, and `continuation`.

`source` carries an exact repository/base commit plus exact governing source refs.
`method` separates deterministic work, model work, and ordered implementation.
`failure` separates refusals from terminal stop conditions. Authority, source and
acceptance are mandatory; the shape is closed so routing/control-plane selectors are
not silently accepted or defaulted. Normalized compact input is capped at 16 KiB.

The compilation receipt records compact-input, normalized-brief, method, and exact
commission digests. The checked-in `examples/ceo-commission.md` and receipt are the
golden provider-neutral bytes intended for the existing fixed
`research/executive_commissions/COMMISSION.md` publication seam.

## Adopt it without bypassing the existing system

Use the compiled document as task content only after checking current intent and
source facts. The normal caller still owns its current WorkerLaunchSpec, authority,
source/workspace custody, tool grants, and result contracts. This utility does not
replace Macro's context compiler or the Operator commission/dialogue skills.

For native Skill enrollment, have the current package/capability owner inventory
all reachable files and compute the existing canonical generation and effective
closure. HF1 and the provider adapter own native realization and observed capability
comparison. Do not reuse the authoring hashes as CapabilityIdentity digests, inject
an extra Skill into the exact four-Skill canary, or edit an active provider home.

Source lives here under research to avoid racing the shared plugin marketplace,
validator, bootstrap, Paper bridge, Workbench, and HF1 owners. Admission into the
approved catalog is a later reviewed owner operation, not hidden installation.

## Proof limits

A passing compiler test proves document behavior, not model skill adherence, live
tool access, production readiness, provider entitlement, host isolation, or accepted
user capability. See the evidence file for exact observed checks and omissions.

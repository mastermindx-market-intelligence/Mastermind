# CEO boot packet — Executive OS Phase 1D-A

A read-only bridge from **Agent OS** into **Executive OS**.

Agent OS is the organization's durable *knowledge* plane: the `agentos/` record store
plus `scripts/agentos.py`, both living in the **Macro** repository (merged as Macro
PR #5472, merge SHA `431fb2b846b693c13fb6654901f0747e79f82534`). Executive OS — this
repository — is the *execution* plane. The boot packet is the read-only bridge from
the former into the latter: one deterministic document that lets the AI CEO seat (Sol)
reconstruct organizational state from canonical stores instead of from chat memory.

Module: `control_plane/ceo_boot_packet.py` · CLI: `scripts/ceo_boot_packet.py` ·
tests: `tests/test_ceo_boot_packet.py` (wired into the hermetic governance gate in
`.github/workflows/ci.yml`).

## Invocation

```bash
# Human-readable packet (default)
python3 scripts/ceo_boot_packet.py

# The mastermind.ceo_boot_packet.v1 document
python3 scripts/ceo_boot_packet.py --json

# Point at a specific Macro checkout
python3 scripts/ceo_boot_packet.py --macro-root ~/Documents/Cluade/"Macro Dashboard"

# Widen the brief window (passed straight through to Agent OS)
python3 scripts/ceo_boot_packet.py --since 7d
python3 scripts/ceo_boot_packet.py --since overnight

# Freeze the clock — reproducible output, byte-identical across runs
python3 scripts/ceo_boot_packet.py --json --now 2026-08-13T00:00:00Z

# Shorten the budget for the Agent OS subprocess (default 60s)
python3 scripts/ceo_boot_packet.py --timeout 15
```

`--now` is applied to the packet's own `generated_at` **and** forwarded to the brief,
so a frozen-clock run is deterministic end to end. That is what the determinism test
asserts.

## Resolution ladder

The Macro checkout to read is chosen by this ladder; the first **usable** candidate
wins. A candidate is usable only when the directory exists *and* carries both
`scripts/agentos.py` and an `agentos/` store.

| Order | `resolved_via` | Source |
|---|---|---|
| 1 | `flag` | `--macro-root PATH` |
| 2 | `env` | `$MASTERMIND_MACRO_ROOT` |
| 3 | `sibling` | `<repo>/../Macro Dashboard` |
| 4 | `vendor` | `<repo>/vendor/macro` (symlink resolved) |

**Why the sibling outranks `vendor/macro`.** The vendor pin exists so app code can
import a *fixed* Macro engine revision — CI checks out an exact SHA into
`vendor/macro_src`. It is stale by design; that is its entire job. Organizational
STATE must be fresh, so a live sibling working copy beats a pinned engine mirror every
time. `vendor/macro` stays last so a machine with no sibling still has a chance of
answering.

Every candidate tried is recorded in `macro.candidates_tried` with the path and why it
was rejected (`missing`, `no scripts/agentos.py`, `no agentos/ store`), so an
unresolved packet is diagnosable without re-running anything.

## JSON schema — `mastermind.ceo_boot_packet.v1`

| Key | Type | Meaning |
|---|---|---|
| `schema` | `str` | Always `mastermind.ceo_boot_packet.v1`. A bump means a migration. |
| `generated_at` | `str` | ISO-8601 Z. `--now` when given, else current UTC. |
| `mastermind` | `dict` | `{root, sha, branch}` for this Executive OS checkout. `sha`/`branch` are `null` when git cannot answer. |
| `macro` | `dict` | `{root, sha, resolved_via, candidates_tried}`. `root`/`sha`/`resolved_via` are `null` when nothing resolved. |
| `strategic_state` | `dict \| null` | Projection of `config/strategic_state.yml`: `{schema, company_phase, north_star[], p0[{id,department,objective,status}], constraints{name: level}}`. `null` when the reader raised. |
| `brief` | `dict \| null` | Macro's `ceo_brief.v1`, **embedded verbatim**. `null` when the store is unreachable or the subprocess failed. |
| `handoffs` | `list` | Up to 5 `{name, path}`, newest first by **filename**. |
| `degraded` | `list[str]` | Bridge-level warnings only (see below). |
| `next_recommended_act` | `str` | The one thing to do next (ladder below). |

`brief` embeds Macro's `ceo_brief.v1` **verbatim** — its keys (`counts`, `inputs`,
`needs_ceo`, `blocked`, `finished`, `running`, `unblocked`, `unblocked_scope`,
`warnings`) are never re-derived, re-sorted, or re-scored here. That contract is owned
by Macro `scripts/agentos.py` at merge SHA
`431fb2b846b693c13fb6654901f0747e79f82534` (Macro PR #5472). One generator, many
renderers: if the projection is wrong, it is fixed in Agent OS, not patched here.

Handoffs are ordered by **filename descending, never by mtime**. Handoff filenames
embed their date, and file mtimes in this organization are observer-stamped — a status
sweep, a Finder walk, or a sparse-checkout materialization restamps whole trees, so an
mtime sort silently reports whichever file was last *looked at*.

## Degraded semantics

**The command always exits 0 once its arguments parse.** A missing or stale Macro
checkout is an orientation gap, not a control-plane fault. This is the deliberate
inverse of `control_plane/strategic_state.py`, which fails loud: a CEO who cannot read
the org must still be *told that*, loudly, rather than handed a traceback.

Every failure lands as a string in `degraded`:

- the Macro root did not resolve (one entry naming every candidate and its reason);
- the Agent OS brief timed out, exited non-zero, or emitted unparseable output;
- the brief's schema was not `ceo_brief.v1` (it is still embedded as-is);
- `agentos/handoffs/` is missing;
- a `git rev-parse` failed for either checkout;
- the strategic state was unreadable.

`degraded` carries **bridge-level** warnings only. The embedded brief's own
`inputs.degraded` and `warnings` stay nested inside `brief` — the packet displays
Agent OS, it does not re-derive it. The text renderer shows both, prefixing the
nested ones with `brief:`, and never suppresses the DEGRADED block.

Today's live workstation state is itself a degraded case, by design: the sibling
`../Macro Dashboard` checkout may legitimately predate the #5472 merge and therefore
carry no `scripts/agentos.py` and no `agentos/` store, while `vendor/macro` is a stale
sparse engine pin. The default run degrades, names both candidates, exits 0, and tells
the reader to pass `--macro-root` at a worktree that has pulled past #5472. That is
correct behavior, not a bug to fix.

## The `next_recommended_act` ladder

Deterministic and explainable on purpose: the same packet always yields the same act,
and the rung that produced it is readable off the sentence. Repairs outrank rulings,
rulings outrank unblocking, unblocking outranks starting new work.

1. **Strategic state unreadable** → `Repair config/strategic_state.yml — <err>. The
   company is running without a declared objective set.` A company with no readable
   objective set cannot correctly prioritize anything else, so this outranks even a
   pending ruling.
2. **No brief** → `Restore the Agent OS read path — <first degraded entry>. Sol has no
   organizational state until then.`
3. **`needs_ceo` non-empty** → `Rule on <n> pending CEO decision(s). First:
   WS:<workstream> — <question>`
4. **`blocked` non-empty** → `Clear <n> blocked workstream(s). First: WS:<workstream>
   (blocked by: <reasons>)`
5. **`unblocked` non-empty** → `Start the top ready item: WS:<workstream> wave <wave> —
   <next_action or title>`
6. **Otherwise** → `No rulings pending, nothing blocked, nothing queued. Review
   finished work and the improvement agenda for the next objective.`

## Boundary (invariant I1)

**Executive OS READS Agent OS. There is no write path in the other direction.**

- The only contact with the Macro checkout is one `subprocess` call to
  `scripts/agentos.py brief --json --no-remember`, plus directory listings and
  `git rev-parse`.
- `--no-remember` is **load-bearing on every invocation**. Without it the Macro-side
  `cmd_brief` records a check-in marker at `data/governance/.ceo_brief_last` *inside
  the Macro checkout*, which would make this reader a writer.
  `tests/test_ceo_boot_packet.py::test_no_write_into_macro_checkout` sha256-snapshots
  the entire fixture tree around a CLI run and fails on any byte that moves — and the
  test's Agent OS stub creates that exact marker whenever the flag is omitted, so
  dropping it reds CI.
- No dispatch, no scheduler, no session tracking, no auto-arming, no leasing. The
  module imports nothing that executes — not `control_plane.worker_runtime`, not
  `control_plane.executive_runtime` — and an AST test pins that. This is the same
  `constraints.duplicate_control_planes` prohibition
  `control_plane/strategic_state.py` states, for the same reason.
- Import-time stdlib only, so importing the module pulls in no third-party code.

## What Sol can now do

Boot a cold session with no conversational memory and still answer, from canonical
stores:

- **What is the company trying to do** — phase, north star, active P0 objectives, and
  the standing constraints, straight from `config/strategic_state.yml`.
- **What is running** — workstream counts, active/awaiting-CI/blocked, open PRs, live
  claims, and what finished inside the window.
- **What is blocked** — which workstreams, and by what.
- **What needs Chris** — pending CEO decisions with the question, options,
  recommendation, and how many waves each one blocks.
- **What to do next** — one sentence, derived by a fixed ladder rather than by
  whatever the last conversation happened to be about.
- **What is unknown** — every gap named explicitly in `degraded`, so a partial read
  is never mistaken for a quiet org.

# EXECUTIVE OS — STRATEGIC STATE + WORKER CONTRACT BOOTSTRAP

**Date:** 2026-08-11 · **Phase:** Executive OS Phase 1 (organizational layer) ·
**Scope:** the non-runtime organizational layer only. Phase 1B's durable worker
runtime — `control_plane/worker_runtime.py`, SQLite lifecycle, adapters, leases,
supervisors, provider execution — was **not touched by this work**.

**Predecessor:** `research/EXECUTIVE_OS_PHASE0_CENSUS.md` in the **Macro** repo
(PR #5356, open at time of writing — it is not yet on Macro `main`). Its §5 item 2
specified this artifact: *"the one net-new file … schema-versioned … loader ~40 LOC …
Not a control plane: no runtime behavior keys off it."* This document records what
was built against that specification and, more importantly, the contract Phase 1B
must honor when it later reads the state.

---

## §0 What shipped

| File | Status | Purpose |
|---|---|---|
| `config/strategic_state.yml` | **new** | The machine-readable answer to "what is the company trying to accomplish right now" — phase, north star, P0 objectives, resource policy, standing constraints, review triggers. |
| `control_plane/strategic_state.py` | **new** | The only supported reader. Validates and caches; raises `StrategicStateError` on anything malformed. |
| `tests/test_strategic_state.py` | **new** | 42 tests: the checked-in state is well-formed, the reader fails loud on every malformation class, and the reader stays decoupled from the Phase 1B runtime. |
| `AGENTS.md` § "Executive contract" | extended | Hierarchy, source-of-truth order, worker behavior, completion rule. |
| `CLAUDE.md` § "Executive contract" | extended | Same contract, compact; the two files are deliberate near-duplicates in this repo. |
| `.github/workflows/ci.yml` | extended | One path added to the existing *hermetic governance gate* step. |

No new package, daemon, scheduler, queue, service, or control plane.

---

## §1 Placement ruling — why this landed in Mastermind, not Macro

The commissioning brief said `config/strategic_state.yml` "unless repository
conventions indicate a better existing location." They do, decisively:

- **Every named reuse target lives here.** Charter V2 (`research/MASTERMIND_CHARTER_V2.md`),
  doctrine (`DOCTRINE.md`, `config/doctrine.yml`), authority map
  (`config/authority_map.yml`), agents config (`config/agents.yml`), improvement
  agenda (`brain/improvement_agenda.py`), governance ledger
  (`control_plane/governance.py`) are all Mastermind. Only "existing fleet law"
  (ship loop, model routing, merge-on-green) is Macro's, and it is unchanged.
- **The future consumer lives here.** Phase 1A's `control_plane/worker_runtime.py`
  is on Mastermind `master`; Phase 1B extends it in this repo.
- **The Phase 0 census already ruled it** — §5 item 2 names
  `Mastermind/config/strategic_state.yml` explicitly.
- **The alternative is the prohibited outcome.** A strategic state in Macro read by
  a runtime in Mastermind is a cross-repo authority hop — the literal shape of
  `constraints.duplicate_control_planes: prohibited`.

Macro's `CLAUDE.md`/`AGENTS.md` get a short cross-reference pointing here, per census
§5 item 10. The state itself is not duplicated; charter P7 (one source of truth per
concept) is the whole point of this file existing.

---

## §2 What was reused (adopt, don't build)

| Existing mechanism | How it was reused |
|---|---|
| **Charter V2** (`research/MASTERMIND_CHARTER_V2.md`) | Kept as the constitution *above* the strategic state. The YAML header states the charter wins on conflict; the contract's source-of-truth order puts it at layer 1. No new constitution was written. |
| **`config/authority_map.yml`** | Its **DOCUMENTATION-AS-CONFIG** pattern was copied wholesale: a long explanatory header, declared vocabularies, and a conformance test that reds when the file drifts. It remains the sole owner of the A0–A7 authority ladder — the strategic state declares *objectives*, never authority. |
| **`config/agents.yml`** | The AI-CEO seat (`codex.model: gpt-5.6-sol`) already existed. The contract **cites** it rather than restating seats, so there is one seat registry. |
| **`bot/doctrine_config.py`** | The house's tiny config-reader shape (module-level path constant + process cache + `yaml.safe_load`) is the skeleton of the new reader. |
| **`control_plane/contracts.py`** | Its **lazy `import yaml` inside the load function** was copied, which keeps `control_plane` free of third-party imports at module-import time. Its *never-raises* law was deliberately **inverted** — see §3. |
| **`control_plane/governance.py`** + `data/governance/` | Remains the decision ledger. The strategic state is state, not a ledger; objective changes are recorded as commits/PRs and (later, if wanted) governance events. No second event store. |
| **`brain/improvement_agenda.py`** | Remains the ranked work queue. It is the designated future machine consumer (census §5 item 3) and was **not** wired in this pass — the brief scoped that out. |
| **`tests/test_governance_ledger.py`** | The conformance-test precedent (config file validated by a test rather than by a runtime schema service). |
| **`tests/test_system_census.py`** | The precedent for asserting over checked-in Markdown, which is how the doc-contract tests work. |
| **`AGENTS.md` / `CLAUDE.md`** | Extended in place. No new worker-facing doc surface was created. |
| **`.github/workflows/ci.yml`** *hermetic governance gate* | Extended by one path. This repo's CI runs an **explicit test-file list with no catch-all `pytest tests/`**, so a new suite that is not registered there never runs in CI. |
| **Macro fleet law** | Untouched and still binding: worktree-per-session, ship loop, model routing, merge-on-green. |

---

## §3 What is genuinely new (and why so little)

1. **The YAML file.** 118 lines, much of it header comments that state what the file
   is *not*.
2. **The reader**, 256 lines including validation and docstrings. It is not 40 LOC as
   the census estimated because validation is the product: the brief required it to
   "fail loudly on malformed strategic state rather than silently treating it as empty."
3. **Three declared vocabularies** (`departments`, `statuses`, `constraint_levels`).
   These make a typo a red test instead of a silently-invented department.

**The one deliberate departure from a sibling's design law.**
`control_plane/contracts.py` declares *never-raises*: a missing artifact contract must
never abort a build. The strategic-state reader inverts that, on purpose. The failure
modes are not symmetric — a missing artifact contract degrades one lookup, whereas a
strategic state that reads as empty produces a session with **no company objectives**,
which is exactly the condition under which a worker invents its own roadmap. That is
the failure this whole layer exists to prevent, so it must be loud. Both behaviors are
documented in their own module docstrings so neither reads as an accident.

---

## §4 How Phase 1B should consume the state — without creating a duplicate authority system

The state is **advisory and orientation-only** (`meta.authority`). The line that keeps
it from becoming a second control plane is precise:

> The strategic state may **describe and label** work. It may never **decide** whether
> work runs, or **grant** authority to run it.

**Dependency direction is one-way and test-pinned.**
`control_plane.strategic_state` must never import `control_plane.worker_runtime`;
`tests/test_strategic_state.py::test_reader_does_not_import_the_worker_runtime`
enforces this over the AST. The reverse — runtime reading state — is permitted when
Phase 1B wants it. Keep it that way: state must stay independently testable and
importable without dragging the runtime in.

**Read it through the reader, never by re-parsing the YAML.**

```python
from control_plane.strategic_state import load_strategic_state, p0_objectives

state = load_strategic_state()          # validated, cached, raises on malformed
active = p0_objectives()                # status == "active"
```

A second parse site is a second schema, and drift follows. If Phase 1B needs a field
the reader does not expose, add an accessor there.

**Permitted couplings (all inert / descriptive):**

- **Stamp `p0_id` on a Job as provenance metadata**, exactly as Phase 1A already
  stores `authority_level` as "inert classification metadata." It answers *which
  objective was this job for* on later review. It must not be read back to change
  behavior.
- **Surface `company_phase` and active P0s on a status/report surface** so an operator
  or a CEO packet can see what the fleet is working toward.
- **Rank or group** an existing queue by P0 — ordering already-eligible work is
  descriptive; the queue still decides eligibility.

**Forbidden couplings (each one is the duplicate authority system):**

- **A dispatcher that reads `p0` to choose the next job.** That makes the YAML a
  scheduler. Census §6.4 already prohibits new schedulers/queues.
- **Gating execution on `constraints`.** The constraints are stated for *humans and
  sessions*, and are enforced by the charter, the authority map, `packet_gate`, and
  the fleet guards. A runtime that enforces them itself becomes a second governor
  whose verdicts can disagree with `authority_map.yml`.
- **Deriving authority from `department` or `p0_id`.** Authority comes only from
  `config/authority_map.yml`. A department is not a permission.
- **Runtime writes back to the YAML.** Objective changes are Chairman/CEO decisions
  that land as PRs. A runtime writer would also be able to emit a state that the
  fail-loud reader then refuses — breaking every other reader at once.

**The id-stability contract.** `p0[].id` is the join key for any provenance stamp.
Ids are **appended and retired, never renamed** — retire by setting
`status: retired`, keeping the row. A rename silently orphans every historical
reference to it.

**Schema evolution.** `SCHEMA` is pinned in the reader and asserted in the test; a
version bump is a migration with a code change, not a warning. Additive fields need no
bump. Adding a required constraint means adding it to both the YAML and
`REQUIRED_CONSTRAINTS`, which is intentional friction — dropping a constraint from the
YAML must not silently un-prohibit it.

---

## §5 Verification evidence

- `tests/test_strategic_state.py` — 42 passed.
- **Mutation-checked** (the tests are not vacuous): breaking the resource weights,
  duplicating a P0 id, and removing the contract heading from `CLAUDE.md` each red the
  suite; restoring each returns it to green.
- The **exact CI hermetic-gate command** with the new path added: 140 passed, 1 skipped.
- `python -m compileall -q app bot brain bridge control_plane data_layer loop portfolio scripts` — clean.
- Every negative test mutates a **copy of the real document**, so no assertion can pass
  because the fixture happened to be malformed in some other way.
- Collateral check: no test or module globs `config/*.yml` or reads `AGENTS.md` /
  `CLAUDE.md`, so the two new config/doc files cannot red an existing suite.

---

## §6 Deliberate non-goals

Carried forward from census §6, plus what this pass declined:

1. **No wiring into `brain/improvement_agenda.py`.** Census §5 item 3's fusion-source
   work is a separate, larger change; the brief scoped it out ("do not connect it to
   the Phase 1B runtime yet").
2. **No CEO write surface** (`submit_executive_packet`). Census sequencing puts it last
   and shadow-first.
3. **No `control_plane/__init__.py` edit.** That package docstring already indexes only
   6 of its 10 modules, so adding one line would not have made it an index — and it is
   a file Phase 1B is actively editing. Zero conflict surface was worth more.
4. **No per-objective owner seats or review dates.** The census sketched them; the
   Chairman supplied a specific initial state and inventing owners/dates it did not
   specify would put fabricated commitments into the company's strategy file.
5. **No governance event types** for objective changes. Census §5 item 4 lists
   `objective_set/retired`; it needs an `authority_map.yml` `events:` row and belongs
   with that change, not this one.

---

## §7 Open items for the next session

- **Macro cross-reference** — `CLAUDE.md`/`AGENTS.md` in the Macro repo point here
  (shipped alongside this PR as a separate Macro change; the artifact is not duplicated).
- **Phase 0 census is still unmerged** (Macro PR #5356). This document cites it as the
  specification; if that PR changes materially before merging, re-check §1 and §2.
- **`improvement_agenda` fusion source** is the natural next increment, and is the
  first time anything machine-reads the state for ranking.
- **Review triggers are not instrumented.** `review_triggers` is a list a human reads.
  Wiring detection for `first_10_paying_users` would need a revenue signal that does
  not exist yet — deliberately left as prose.

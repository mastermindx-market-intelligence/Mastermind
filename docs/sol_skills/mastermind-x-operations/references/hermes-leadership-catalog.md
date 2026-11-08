# Hermes leadership catalog — extending a closed seat/role set

Use when adding (or changing) a seat in `integrations/hermes_leadership/charters.py` or anything else that enumerates a closed catalog whose members are consumed across code, tests, and prose.

## The three coupled surfaces

A new charter key is NOT a one-file docs change. All three surfaces must land in the same PR:

1. **`charters.py`** — append the key to `CHARTER_KEYS` AND a matching row to `_ROWS` (fields: key, title, responsibility role, execution mode, objective, wake triggers, completion evidence, limits, routing guidance). Valid `ResponsibilityIntent` roles: `principal` / `sub_orchestrator` / `operator` / `worker`; modes: `execute` / `coordinate` (`worker` must execute). `charter_for()` appends the reuse-first guidance limit automatically — do not hand-add it.
2. **`organization.py`** — `_REPORTS_TO[key]` MUST gain the parent line. The seats view does `_REPORTS_TO[key]` for every `CHARTER_KEYS` entry, so a catalog row without a reporting line is a runtime `KeyError` in `organization_context`, not a doc gap.
3. **`docs/hermes/EXECUTIVE_TEAM_CONTEXT.md`** — prose seat enumeration plus the "*N* existing charter keys" sentence. Unguarded by tests; the only durable defense is the doc-enumeration guard test (below). If it exists at your pin, keep count and names in sync; if it does not yet, treat the doc as a hand-maintained surface and flag the drift.

## Constraints to check before writing

- **Byte budget:** `organization_context` renders ALL seats and hard-fails over `MAX_BYTES` (8192). Each serialized seat costs ~130 B; measure current usage before promising seat additions (a temp pytest that renders the view and prints `len(json.dumps(view).encode())` — see fixture rule below). Headroom is a real cap on catalog growth.
- **Count-asserting test:** the leadership test module asserts the exact key set (dynamically elsewhere, hard-coded here). Grep the test tree for an existing member key (e.g. `grok_adviser`) to find every list that enumerates the set; update the assertion rather than adding a parallel test.
- **Doc guard:** the durable fix for prose drift is a test asserting the doc's count word equals `len(CHARTER_KEYS)`. Merge-order independent if written against the count sentence only — it stays green at every legitimate intermediate state (each surface-synced head) and red on any drifted tree.

## Procedure

1. `git worktree add -b <branch> <path> origin/master` (lane law: never from the active checkout).
2. Grep the tree for one existing member key across code, tests, AND docs to enumerate all surfaces first.
3. Patch all three surfaces + the key-set test; measure the org-view byte budget before/after.
4. Run every test file that imports the package (grep `hermes_leadership` in `tests/`, `--include=*.py` only — a pyc-inclusive list breaks pytest collection).
5. Push, `gh pr create --head <branch>`, read back `headRefOid`/`mergeable`.
6. Admit via `gh pr merge <n> --squash` once checks are green (see merge-queue law in SKILL.md).

## Pitfalls

- **Stacked siblings:** if another PR stacks on your branch head and you then amend your PR (especially a prose doc line), steer the stacked child to rebase onto your NEW head before it pushes — same-line prose conflicts are the default outcome, and mergeable-state of the child flips CONFLICTING until rebased.
- **Fixture-chained temp tests:** fixtures defined in another test module (e.g. `mission_body` ← `result_owner`) do NOT auto-resolve — import each into the temp test module's namespace (`from tests.test_workspace_result_service import result_owner`) or setup fails with 'fixture not found'. Never call a fixture function directly; pytest hard-fails it.
- **Interpreter deps before red-classification:** collection-time `ModuleNotFoundError` (jwt, numpy) is an environment gap, not a code red. Probe interpreters for the needed modules first — CI-mirror venvs under `/tmp` usually carry the full matrix; the system python may not. Only a red that survives on a dep-complete interpreter counts against the change.

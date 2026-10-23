# Executive acceptance maintenance: unstarted pre-proof supersession

## Purpose

`ops/executive_os/acceptance_maintenance.py` already retires three shapes of
interrupted release. This change adds one more, source-only admission for a
shape the existing selectors intentionally refuse: an installed
`supersede_preproof_v1` release whose own maintenance preparation was
published but never started.

Concretely, a host can hold a release whose bundle is the intact six-entry
preparation (`descriptor.json`, `preparing.json`, `baseline.json`,
`inventory.json`, `prior-secret-canary.json`, `prestate.sqlite3`) with the
`supersede_preproof_v1` schema, while the runtime acceptance leaf for that
release was never created and no `run-started.json` was ever written. The
incumbent `supersede_unstarted_v1` selector refuses that selected schema
today, and it keeps refusing it; the new mode is the only way to admit the
shape, and it never replays the interrupted acceptance.

## Contract

- Schema: `mastermind.executive_acceptance_maintenance/supersede_unstarted_preproof_v1`
  (`SCHEMA_UNSTARTED_PREPROOF`).
- Descriptor keys: `_DESCRIPTOR_V2_KEYS` plus exactly
  `superseded_unstarted_preproof_sha` and `superseded_descriptor_sha256`.
  The key set is closed; `descriptor_for` refuses any other shape and
  validates the selected SHA identity against the successor and predecessor.
- CLI: `--supersede-unstarted-preproof-sha`, mutually exclusive with the
  three existing selectors (`select one supersession mode`), and bound to the
  exact `--superseded-descriptor-sha256` of the selected release.
- Membership in `_TERMINAL_CARRY_SCHEMAS`: the mode carries the same terminal
  dispatch evidence as the other V2-family modes (frozen base, prior PASS
  material, template proof, terminal Job/Attempt/marker/state, assignment
  seal, predecessor quota) and grants no predecessor recovery.

## Selected-bundle law

The selected `supersede_preproof_v1` release must still be the untouched
preparation:

- exact six-entry bundle namespace, plus the already-supported strictly safe
  legacy sealed empty-WAL/SHM pair where present; any extra entry, run
  marker, carry receipt or partial directory refuses with
  "superseded bundle contains acceptance or partial state";
- `preparing.json` is exactly `{"schema_version": "mastermind.executive_acceptance_maintenance/supersede_preproof_v1"}`;
- the runtime acceptance leaf
  `<runtime>/control/acceptance/<selected>` must be absent. Absence is
  decided by the existing canonical-parent/exact-leaf `lstat` absence check
  with its explicit trusted-`/var` alias bracket
  (`_require_runtime_acceptance_absent`); this incumbent function does not
  retain a parent descriptor. A present, empty, symlinked, dangling or
  unobservable leaf refuses;
- the sealed `baseline.json`, `inventory.json` and `prior-secret-canary.json`
  must still digest to the selected descriptor's own values, the sealed
  prestate must still snapshot to the sealed baseline, and on a strict call
  (preparation and acceptance start) the live prestate, inventory and live
  secret-canary receipt must equal them;
- the outer `prior_canary_sha256` equals the selected sealed prior canary:
  the shared V2 field equality keeps `prior_canary_sha256` bound (unlike the
  started pre-proof link, which binds the envelope digest instead), so the
  live receipt at the new preparation must be the same envelope the selected
  bundle sealed.

## Lineage walk

`validate_superseded_binding` admits the new schema and walks the real
lineage without flattening it:

1. the new descriptor selects exactly an original `supersede_preproof_v1`
   descriptor (`allowed = {SCHEMA_PREPROOF}`); no V2, PREJOB or newtype
   selection is admitted, and no other mode may select a newtype descriptor,
2. the selected pre-proof link re-asserts the started bcf-shaped prefix
   below it exactly as today: run marker bound to the selected descriptor's
   own schema and digest, the eight pre-proof receipts plus exactly one
   probe, the pre-proof evidence digest, and the envelope canary binding,
3. cycle and depth guards (`_MAX_SUPERSEDE_DEPTH`) apply to the whole walk,
4. after a pre-proof-family link validates with a provided canary, the
   selected bundle's sealed prior canary is re-read and propagated, so every
   deeper link expects that exact canary.

Future accepted carry is unchanged: `Maintenance.finish` writes the PASS
receipt with the descriptor's own schema, `validate_carry_receipt` requires
that schema on the receipt, and `validate_prior_carry_binding` re-enters the
retained newtype lineage (historically) on every later predecessor walk.

## Non-goals

No provider, network, credential, process or service fallback; no replay of
the selected or deeper acceptance; no schema translation; no broadening of
the existing selectors' allowlists; no new publication outside the existing
disposable preparation flow.

## Tests

`tests/test_executive_acceptance_supersede_unstarted_preproof.py` drives the
real owner end to end:

- the walk descends newtype -> started pre-proof prefix -> accepted V2 and
  leaves every selected byte untouched;
- the descriptor key set stays closed and the incumbent
  `supersede_unstarted_v1` refusal of this shape is preserved;
- the full negative matrix: shared binding drift, sealed baseline/inventory/
  canary/backup drift and unsafe forms, extra/started/partial selected
  bundles, present/symlinked/denied acceptance leaves, deeper evidence,
  canary and marker drift, live prestate drift, cycles and depth;
- actual `prepare()` against a real Runtime, SQLite prestate and inventory
  publishes one new descriptor, then actual `Maintenance.__init__`
  revalidates the whole selected lineage before writing the run marker, and
  a future accepted carry validates the retained lineage and refuses deeper
  drift;
- late faults during candidate sealing or after terminal evidence validation
  refuse before the final bundle or run marker. Failed private `.preparing-*`
  directories remain evidence under the incumbent operation; they are not
  automatically deleted or retried. Production does not alter selected bytes
  or the Runtime database, including when a test deliberately injects drift.


## Publication boundary and custody

This operation requires exclusive administrative Root custody of its inputs.
An actual concurrent writer is a stop condition. No new global lock or authority
is introduced. Only the new mode retains no-follow, nonblocking descriptors for
the selected and deeper supersession bundles and every existing admitted file,
including metadata-only SQLite sidecars, and the PREPROOF/PREJOB receipt
namespaces actually traversed. It records each sorted namespace and brackets
the original semantic reads with held/named identity checks. Backup bytes are
not parsed by this identity guard; the existing sealed backup reader remains
authoritative. Inventory retains its existing 64 MiB limit and other semantic
JSON readers retain their existing 16 MiB limit.

The new guard anchors traversal from `/`, refuses symlink traversal, and retains
the actual parent descriptor for the absent selected acceptance leaf. Only the
already admitted Runtime `/var` alias is mapped to its explicit physical target;
its original link identity and target remain pinned. It also retains the actual
live canary file identity. Ancestor inode/type/owner/mode checks allow the
operation's own creation of a sibling private preparation, while full identities
and exact namespaces remain fixed for the admitted bundles and receipt leaves.
Existing readers enforce ownership, ACL, schema and payload rules; identity
retention does not replace them or impose Root ownership on Control receipts.

Immediately before the existing atomic final rename or exclusive run-marker
creation, the new mode re-reads the current SQLite snapshot, re-observes the
actual artifact inventory (including new entries), reads the current canary,
runs the complete selected lineage validation and actual terminal carry
validation, checks the live snapshot again, and checks all retained identities,
namespaces, aliases and absences. The guard closes every retained descriptor on
success and failure. Failed preparation evidence remains on the original path.

These per-object checks and the final atomic namespace write are not a
cross-object transaction. External Root mutation after the last semantic reads
or final checks can still race the write. Accepted-ancestor summary/carry and
terminal assignment paths continue to use their unchanged guarded readers and
digest validators at the final boundary; they are not recursively retained by
the new guard. The exclusive-custody precondition remains necessary after those
readers close their descriptors. No repeat check is claimed to remove that
residual race.

The producer/consumer tests use actual Runtime SQLite, `prepare()`,
`Maintenance.__init__`, the selected/deeper PREPROOF walk and actual
`terminal_carry_fields`. Their inherited accepted-ancestor, proof-template,
assignment and host identity/stopped boundaries are synthetic fixture inputs;
they are source-composition proof, not live historical authority, installed
acceptance or permission to execute maintenance. Separate existing substantive
tests cover the preserved terminal assignment and prior-carry validators.

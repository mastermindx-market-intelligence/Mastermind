## Review: mmos-fabric-interiors-20261013-c4 / c4-01 (source-only wave)

**Scope reviewed:** mission-interiors.ts, FabricMissionInspector.tsx, attended-status.ts, AttendedFabricInspector.tsx, fabric-inspector.css, host.ts diff, MetaCeoOffice.tsx diff.

**Server-side port: explicitly gated per submission ("NOT connected"). PR1359 remains the machine-owner facade. Browser selectors cannot grant access — this is enforced by the host diff, which makes `readAttendedFabric` opt-in (`...(client.readAttendedFabric && client.invalidationGeneration ? {...} : {})`).**

---

### Verdict

**PASS — bounded source-only delivery.** No BLOCKER or MAJOR correctness/privilege findings in the consumer + source-contract surface. Caveats below.

---

### BLOCKER

None.

---

### MAJOR findings

**M1 — `usable` gate is restrictive (mission-interiors.ts:27–29).**
`usable = !!root && runtime_root_state === "RESOLVED" && !root_job_ambiguous && read_state.state !== "UNAVAILABLE" && children.state !== "UNAVAILABLE"`. Any mission whose root is RUNNING/WAITING flags all children `ROOT_NOT_QUALIFIED`, so `running`/`results`/`problems` are computed only on the ASSOCIATED subset (none in those missions). The `available` UI gate (FabricMissionInspector.tsx:47) is independent and correctly renders "Unknown", but `usable` short-circuits the model counts. Defensive, but worth confirming against product intent. *Discriminating test:* feed a fixture mission with `runtime_root_state="RUNNING"` and ≥1 child with `status="RUNNING"` — UI must render "Observed running: Unknown" (per `available`), not the underlying count.

**M2 — `accepted=true` acceptance tuple has no symmetric `accepted=false` sanity (attended-status.ts:46–47).**
The asymmetric invariant (`accepted=true ⇒ TERMINAL ∧ rc=0 ∧ signal="ok" ∧ result_available ∧ accepted_by∈{deterministic,reviewer} ∧ root_id≠null`) is correct. There is no constraint that `accepted=false` cannot be paired with `state=TERMINAL ∧ rc=0 ∧ signal="ok" ∧ result_available` — a producer could emit "ACCEPTED ingredients but NOT_ACCEPTED verdict" without rejection. Source-only decoder; flag for the upstream producer contract. *Discriminating test:* `decodeAttendedStatus({…accepted:false, state:"TERMINAL", rc:0, signal:"ok", result_available:true, accepted_by:"none", root_id:"r1", run_id:"x", schema:"…v1", root_id:"r1", parent_run_id:null, result_bytes:10, acceptance_state:"NOT_ACCEPTED", acceptance_reason:"reason"}, {rootId:"r1", runId:"x"})` — returns NOT_ACCEPTED (currently accepted). Verify against spec.

---

### MINOR findings

**m1 — Comment drift (mission-interiors.ts:21).** `// Include the complete decoded set for duplicate detection, never silently pick a winner.` — `byId.set(child.job_id, child)` at L24 *does* overwrite (last write wins). Duplicates are still flagged via `duplicates.has(...)` at L38 before lookup, so this is functionally safe; comment should say "the lineage walk rejects via IDENTITY_CONFLICT before any winner is consulted."

**m2 — Duplicate regex (attended-status.ts:19–20).** `idPattern` and `codePattern` are character-for-character identical. Collapse to one or differentiate per actual constraint.

**m3 — `result_available`/`result_bytes` logical gap (attended-status.ts:39).** `result_available:false` and `result_bytes:100` is accepted. `result_bytes===null` is required when `result_available===false` would be a stricter contract; not enforced.

**m4 — `rc`/`signal` consistency (attended-status.ts:38).** `rc:1, signal:"ok"` is accepted. Only the `accepted=true` branch enforces `rc===0 ∧ signal==="ok"`.

**m5 — `parent_run_id` vs `root_id` relationship not validated (attended-status.ts:36–37).** Decoder does not enforce that root-status `parent_run_id` is `null` or that child-status `parent_run_id === root_id`. Depends on producer spec.

**m6 — `accepted_by` enumeration redundancy (attended-status.ts:40).** Hand-listed `[null, "deterministic", "reviewer", "none"]` duplicates the type literal; consider deriving.

---

### Confirmed-correct invariants (per review questions)

- **Stale detail prevention** — FabricMissionInspector.tsx:40 (`selected?.identity === identity`) and AttendedFabricInspector.tsx:32 (`result.host===host && result.epoch===epoch && result.rootId===rootId && result.runId===runId`) close the stale-detail paths on mission swap, host reassignment, auth change, and identity drift.
- **Auth observer lifecycle** — AttendedFabricInspector.tsx:21–28: subscription installed only when `host?.readAttendedFabric && typeof host.invalidationGeneration === "function"`. Cleanup increments `serial.current` and aborts. The candidate's note ("An unmounted source must not install an extra authentication observer") is honored.
- **Auth double-check** — host.ts diff checks `signed_in + acquisition` before AND after the read, plus epoch `check` between.
- **Count gating** — FabricMissionInspector.tsx:75–77: `available ? model.running : "Unknown"`; prevents false-zero readings when source is UNAVAILABLE.
- **Inputs bounded** — AttendedFabricInspector.tsx:65,67: `maxLength={128}` consistent with `idPattern`0–128.
- **Closed disclosure** — MetaCeoOffice.tsx wraps both inspectors in `<details className="fi-disclosure">`. Source fields only; no fake provider/host/log strings.
- **Mission vs child acceptance** — FabricMissionInspector.tsx:22 text and footer explicitly disambiguate "completed attempt or present result is not product acceptance."
- **Latest ≠ current attempt** — FabricMissionInspector.tsx:97–98 surfaces the divergence with a notice when `attempt.attempt_id !== child.current_attempt_id`.
- **Selective serialization** — `missionInteriors` (L18) slices to `MAX_INSPECTED_CHILDREN=256` and reports `locallyOmitted` (L56); UI warns at L71. Bounded complexity.
- **Decode error mapping** — AttendedFabricInspector.tsx:49 maps `FABRIC_STATUS_INVALID`, `FABRIC_ROOT_MISMATCH`, `FABRIC_ACCEPTANCE_CONFLICT`, `FABRIC_READ_UNAUTHORIZED` to user-visible codes; everything else maps to `FABRIC_SOURCE_UNAVAILABLE`. Good.
- **Decoder schema/version gate** — `v.schema === "mastermind.fabric_task_status.v1"` is checked first; older/newer schemas refused.
- **Selector guard** — `attendedSelection` rejects empty/non-pattern ids; `decodeAttendedStatus` cross-checks `v.root_id` vs `selected.rootId` (FABRIC_ROOT_MISMATCH) and `v.run_id` vs `selected.runId`.

---

### Caveats / unverified claims

The following are **candidate-asserted, not independently re-run by this reviewer** (per instructions, "Do not claim tests you haven't run"):

- "Complete app suite 1395 pass / 1 skip / 0 fail, 57 files."
- "npm build pass."
- "actualcomponents browserfixture desktop/mobile/theme/focus no overflow/errors."
- "retained realstatus NOT_ACCEPTED distinctfromterminal."
- "Initial regression extra authsubscription when readerabsent fixed."
- "current originalApp reopen 25 cases pass."
- "Published screenshots prominentlylabel fixture/retained, notlive."

The source-only invariants above are confirmed by reading the diff; behavioral coverage of the gating corner cases (M1's RUNNING state, M2's NOT_ACCEPTED+TERMINAL collision, m3/m4 logical gaps) is not. Recommend the candidate add discriminating unit tests for M1 and M2 before promoting this wave.

---

### Recommendation

Promote as **source-only readiness PASS**. Server-side port and authentication remain explicitly gated; do not merge downstream consumers expecting real Fabric reads until the gated port is live and PR1359's authorization path is verified end-to-end. No unsafe dark wiring or inflated acceptance claims observed in this delivery's surface.

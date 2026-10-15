# Latent Pressure & Predictive Rotation research

## Latest continuation: recovery replay integrity

See [replay_integrity/REPORT.md](replay_integrity/REPORT.md) and [replay_integrity/FRONTIER.md](replay_integrity/FRONTIER.md). The normalized synthetic recovery engine now uses transactional atomic observations, explicit coverage and lossless clock/identity output. 48 new tests, 34 affected regression tests, four CLI cutoffs and a JavaScript round-trip were verified. These are research correctness results, not validated market forecasts. The real DEEP+ mapping, prior worker-return verification and legacy timestamp-label impact audit remain unresolved at their recorded boundaries. Earlier research reports below are immutable phase evidence, not a claim that the broader early-warning capability is complete.

**Research verdict: NO-GO for promotion of the tested daily proxies; CONDITIONAL for genuinely new information. No production changes or trade authority.**

Start with [DECISION_DOSSIER.md](DECISION_DOSSIER.md), which covers all six commission deliverables and H1–H9. The expanded user-facing dossier contains the longer discussion and presentation; these research files own the executable pilot, safe aggregate evidence and durable decision.

- `PILOT_PREREGISTRATION.json` and `pilot.py`: fixed experiment, committed before first outcomes.
- `PUBLIC_RESULTS.json`, `INPUT_MANIFEST.json`, `FIT_RECEIPTS.json`: aggregate metrics, source hashes and model receipts.
- `PRIVATE_RUN_MANIFEST.json`: hashes of unchanged private originals; raw vendor bars and per-date predictions/returns are NOT redistributed.
- `RESEARCH_REVIEW.md`, `DIAGNOSTIC_QUALIFICATION.json`, `qualify_diagnostics.py`: independent review, principal corrections and outcome-boundary qualification without model refits.
- `FIXTURE_AUDIT.json`: later-vintage June/July defensive-versus-semiconductor replay and unit discrepancy.
- `AUDIT_AND_SCOPE.md`: protected source and actual-data audit.

Reproduction requires the same authorized input hashes, Python, NumPy, pandas, SciPy and PyArrow:

```sh
python3 pilot.py --data /authorized/yahoo --out /new/empty/results
```

The script refuses nonempty output directories. Changed input hashes require a new run, not an exact replication claim. The optional diagnostic qualification reads the existing private `results/predictions.csv.gz` and is run with `python3 qualify_diagnostics.py --data /authorized/yahoo`.

The first next implementation is source-qualified signed-flow/impact replay on an already authorized archive, not a duplicate flow score. Predictive promotion requires a separate, successful forward-value test and the existing acceptance path.

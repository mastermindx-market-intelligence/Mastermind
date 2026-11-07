# W1 candidate transition composition — development result

**Capability state: BUILT_NOT_PROVEN / DEVELOPMENT ONLY.** This is executable composition of the unregistered `issuer_state_transition.v1` candidate over frozen AAPL FIF evidence. It is not a registered runtime contract, source-owner admission, product publication, trial registration, alert, or signal.

## What is now executable

The composer creates exactly three deterministic, schema-valid transition candidates without inventing missing semantics:

- **first_availability_revenue** — `i3devtransition_first_availability_revenue_4b6391d341039fcc593f8c23`; baseline `missing`; comparison `not_evaluable`; refusal `first system admission changes availability, not economic state`.
- **unchanged_revenue** — `i3devtransition_unchanged_revenue_2b9ebedf100e71e5d87c8d51`; baseline `unchanged`; comparison `not_evaluable`; refusal `owner value is unchanged but the I3 comparison definition remains unadmitted`.
- **assets_cross_filing_refusal** — `i3devtransition_assets_cross_filing_refusal_5afd849e287ef4d23315e7a6`; baseline `available`; comparison `not_evaluable`; refusal `unlinked source vintages require an explicit typed revision lineage`.

All three preserve:

- exact FIF response/cell/source references and hashes;
- separate public-support and system-admission clocks;
- `development_golden` maturity and `development_reconstruction` mode;
- `emitted_at=null`;
- `rights.state=not_admitted` with no decision/purpose refs;
- empty mechanism and materiality arrays;
- all action/Prophet authority booleans false;
- `comparison.state=not_evaluable` and `admission_ref=null`.

## Semantic boundaries

The first-availability case does not treat a missing→available value as economic growth. The unchanged-revenue case retains the owner value but does not self-admit the comparison definition. The cross-filing asset case preserves the historical exact refusal `unlinked source vintages require an explicit typed revision lineage`; it does not consume the later merged FIF lineage disclosure because the current owner disclosure still fails the forged-provenance adversarial probe documented in `FIF_LINEAGE_POST_MERGE_ADMISSION.md`.

The composer commits no generated transition-result JSON. Its machine object is deterministically regenerated from the already-committed owner evidence and exercised by `test_development_transition.py`; this avoids creating another owner/evidence store or another raw-response copy.

## Verification

- `test_development_transition.py`: **10 passed** before integration;
- every produced object validates against the current candidate JSON schema;
- transition identity is the hash of the semantic projection with the identity field removed and projection digest zeroed;
- caller mutation does not affect later composition;
- the normal repository I3 consumer wrapper executes this suite beside baseline, source-binding, reader, and equal-duration suites.

This is the first executable full transition-object composition in W1, but **full W1 is still not accepted**. Owner admissions, trusted lineage, rights, trial registration, Company Intelligence publication/recompose, Terminal integration, browser proof, and production user/machine proof remain open.

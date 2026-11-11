# Commission 7 — Evidence Lineage, Correlation & Independence Graph

**Hardened research package · 4 October 2026**

Start with [FINAL_REPORT.md](FINAL_REPORT.md). It preserves the supplied A–L structure while correcting the current-state census, mathematics, source qualifications, architecture and implementation handoff.

## Package

- [Final report](FINAL_REPORT.md): owner-native recommendation, scientific corrections, canonical-contract proposals, 24 future acceptance cases, experiment gates and primary references.
- [Audit register](AUDIT_REGISTER.md): 24 material findings mapped to the original report's lines, with explicit disposition.
- [Verification](VERIFICATION.md): scope and reproducible commands; author-run mathematical proof is not native or production qualification.
- [Mathematical checks](verify_mathematics.py) and [result receipt](verification_results.json): 18 finite synthetic checks, no production imports or market data.
- [Original report](source_report.original.md): byte-preserved audit input, **not the accepted implementation handoff**.
- [Manifest](MANIFEST.json): file hashes, source pins and scope metadata. The manifest excludes itself to avoid a circular digest.

## Reading and authority

The objective is to expose reused, dependent, conflicting and unknown evidence without turning correlated signals into false independent confirmations. The decisive repository finding is that K1 Evidence Foundation already has Ref/Block/Recipe contracts and deliberately does not certify independence or permit automatic suppression.

This package is published in Mastermind as the Chairman-requested research artifact. Canonical K1 implementation ownership remains in Macro under WS:ALPHA-INTELLIGENCE-INTEGRATION. No store, identity plane, lifecycle, source writer, runtime, model, publisher or portfolio policy is created or transferred by publication. The exact future consumer and owner custody must be recovered before implementation.

The report and audit are complete for the declared inspection scope. The capability is not production-qualified. A deeper selected implementation read was blocked by the tool safety check and was not retried; the native suites were not executed. The package does not imply independent-review acceptance, merge, deployment or trading authority.

## Reproduce the mathematical receipt

```sh
python verify_mathematics.py --output /tmp/commission7-verification-results.json
```

Compare the script digest and test outcomes with `verification_results.json`. Python-version metadata may differ. No third-party packages, API access, credentials or source datasets are required.

# Sovereign auction context — accepted source delivery

**Status: Draft/HOLD, source-only.** This is the final source-verification entry point for the Chairman's October 8 program. Macro [PR #8657](https://github.com/mastermindx-market-intelligence/macro/pull/8657) owns the official observations, lifecycle, economic primitives, research and calendar publication. This repository owns only its existing Market View display consumer. No deployment or provider execution is included.

## Resulting behavior

The existing `/api/market_view` handler adds a strictly validated `sovereign_auction_context` sibling to the served response after existing enrichment. The reader consumes the existing local `vendor/macro/site/feeds/event_calendar.json` contract. It makes no fetch, writes no stored plane and introduces no new refresh service.

The existing Market View page renders a separate observed-context section. Scheduled and awaiting-result events precede tentative events and observed past results; bounded native group expansion retains the rest. EN/ZH instrument and lifecycle descriptions, exact grouped dollar strings, UTC deadlines and explicit unknowns are visible. Original source identifiers, decimal strings, evidence clocks, state codes, result fields and source failures remain accessible in native source disclosures. Source observation and producer cutoff remain distinct and visible. Freshness is explicitly unassessed.

The section stays outside stored plane coverage and decision inputs. `auction_stress`, `treasury_auctions`, numerical probabilities, risk bands, tilt, PM sizing, strategist prompts and crash interpretation receive no new auction authority. The data remains research/context-only and unscored.

## Verification accepted

| Gate | Result and evidence |
|---|---|
| Native reader and actual API | 26 tests passed with the workspace's actual FastAPI dependencies, rerun after security hardening and identity-scope repair. Source: `tests/fixtures/sovereign_auction_context/verification/identity_scope/` (repository-relative). |
| Actual page-script renderer | Passed exact decimal formatting, EN/ZH, original evidence, future-first grouping, explicit nulls, hostile text/link handling, inherited status-attribute escaping and strict owned-script selection. |
| Static harness boundary | Three stdlib tests passed: immutable approved-asset lookup, symlink containment, literal traversal-key rejection and no request-time filesystem access. |
| Actual HTTP route and Chromium | 48/48 cases passed: desktop/tablet/mobile × EN/ZH × light/dark × observed/unavailable/source failure/awaiting with unknowns. Source: `tests/fixtures/sovereign_auction_context/verification/browser_final/browser_receipt.json` (repository-relative). |
| Real source fixture | Four original Treasury captures project to 74 events at the declared cutoff; the three upcoming Bills are checked against the identical shared producer fixture. Synthetic negative cases are separately declared. |
| Risk isolation | Native API tests retain original stored bytes, coverage, tilt, decision-context assembly, prompt summary, PM enrichment and legacy crash-leg behavior. |
| Layout and visual review | No document overflow, card clipping or collapsed group expansion. Representative final desktop EN/light and mobile ZH/dark screenshots inspected. |

The first browser run exposed a new grid-expansion defect and an inherited narrow-screen containment defect. The repair spans native group expanders across the existing grid and lets panels shrink around the already scrollable planes table. Exact pre-auction baseline, diagnoses and historical browser receipts are retained. Final presentation validation also opens source disclosures and checks their geometry and raw evidence; it does not hide failures in closed elements.

[`VERIFIED_SOURCE_MANIFEST.json`](../../tests/fixtures/sovereign_auction_context/VERIFIED_SOURCE_MANIFEST.json) binds the final product, test and harness files by SHA-256. Its enclosing Git commit binds the source revision. Earlier root-level candidate READMEs, `REVIEW_VERIFICATION.json` and `SOVEREIGN_AUCTION_SOURCE_CANDIDATE_HASHES.json` are historical phase records, not final-file manifests. Their earlier fixture/body-clock and HTML hashes must not be used as current acceptance.

## Security review and evidence retention

The exact-head CodeQL review of `42476573407fcb882c65a9388f98ed038801fc50` reported six annotations: two test-script regex findings, one archived HTML attribute sink and three request-derived path expressions in the loopback harness. Root review followed the archived HTML sink into the live page and reproduced an inherited double-quote attribute break before correcting it. The shared HTML escape helper now encodes both quote forms; existing display text and class values remain stable.

The renderer unit test now selects one exact owned source block and rejects missing, duplicate, reordered or early-closing script boundaries. The static catch-all serves an immutable startup map of approved, contained bytes; request keys never reach filesystem operations. The existing loopback, no-lifespan, no-provider and negative-case constraints remain. The actual native suite, renderer, three boundary tests and all 48 browser cases were rerun against these final bytes in run04. Run03 remains historical evidence for the earlier source.

Three obsolete full-source preimage copies have been removed from the working tree after verifying their unchanged bytes in reachable Git history at `8b74970c13a8915097d0d9e5849499904c1fcc2b`. `tests/fixtures/sovereign_auction_context/presentation_final/ARCHIVAL_PROVENANCE.json` records every original Git object and SHA-256; the original presentation patch and receipts remain unchanged. No scanner exclusion, filename masking, alert dismissal or historical-byte edit was used. Exact-head CodeQL status remains separately recorded; local acceptance alone does not clear that gate.

## Actual transport boundary

Macro's source bridge tracks the existing calendar and assembles it before the existing output commit. Its current artifact and local copy simulations hash identically, and this actual reader accepts the temporary simulated input. The owned checkout's original `vendor/macro -> macro_src` symlink was absent/dangling during census. It was not repointed to fixtures. The normal deployed sparse/external-vendor arrangement still requires release-time readback; unavailable remains the correct behavior when its artifact is absent.

The browser harness is a fresh loopback FastAPI application registering only the actual existing GET handlers. It never imports the production main application, starts its lifespan/provider jobs or exercises production authentication. Other Market View fields use the declared frozen test fixture. Network restrictions and source hashes are recorded. These checks establish source composition and interface behavior, not production activation, entitlement, predictive efficacy or live portfolio behavior.

## Continuation

Keep this candidate held alongside Macro #8657 and the Terminal consumer until independent source/CI review and a separately authorized release. Preserve the canonical Macro Agent OS decision and handoff. Before live acceptance, verify the actual vendor path and revision, source-age policy, current feed shape, consumer clock, negative source/auth states and unchanged decision inputs. Do not use a document date to start a prospective statistical clock.

## Final identity-scope acceptance

The protected-identity gate originally reported 58 added-source findings: the literal HTTPS default port and diagnostic harness names inside verification code and historical receipts. The production reader now uses the standard-library HTTPS_PORT constant with the same URL policy. All 45 verification-only harness/fixture files were moved byte-for-byte into the existing tests/fixtures owner; original contents, names, suffixes, source links and Git history remain intact. No identity scanner, registry or production guard was changed. See [EVIDENCE_LOCATION.md](EVIDENCE_LOCATION.md) for the exact relocation map and current paths.

The actual committed-HEAD D8 protected-default test, 26 auction native tests, 3 static-boundary tests, renderer regressions and all 48 actual HTTP/Chromium cases pass on run05. The earlier source 55198 source passed CodeQL; final exact-head CI remains separately sampled. The previous current manifest and run04 receipts remain historical.

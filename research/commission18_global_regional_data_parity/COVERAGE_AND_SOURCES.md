# C-D — Coverage Matrix and Source Landscape

## C. Evidence-family coverage matrix

Grades describe **upstream richness → current Mastermind decision-path readiness**.

- **A:** substantial evidence with credible PIT/history for intended use.
- **B:** useful but partial, context-only or historically incomplete.
- **C:** thin, snapshot-only, proxy-heavy or materially disconnected from the consumer.
- **Ø:** no canonical current path observed.

| Evidence family | United States | Hong Kong | Mainland China |
|---|---|---|---|
| Fundamentals | **A → A** | **B → C** | **B → C** |
| Estimates / revisions | **B → B**; historical PIT revisions immature | **C → C**; current consensus, weak revision history | **C → Ø/C** |
| Filings / disclosures | **A → A** | **B/C → C** | **B/C → C** |
| News | **A → A** | **B → C** | **B → C** |
| Government / policy | **B/A → B** | **B → C** | **A/B → B** |
| Insider / management ownership | **B/A → B** | **C → Ø/C** | **C → Ø/C** |
| Institutional ownership / positioning | **B → B** via 13F/funds | **B → C** via southbound/A-H; CCASS is distinct | **B/C → C** via local ownership/financing context |
| Options / derivatives | **B → B** | **C/B → Ø/C** | **C → Ø/C** |
| Short positioning | **B → B** | **C/B → Ø/C**; SFC weekly data exists | **Structurally different → C/Ø** |
| Theme membership | **B → B**; fine-grained dynamic PIT identity still missing | **B → B/C** | **B → B** |
| Macro | **A → A** | **A/B upstream → C/B consumer** | **A/B → B** |
| Corporate actions | **B → B** | **C → C** | **B/C → C** |
| Credit | **C → C** | **C → Ø/C** | **C → Ø/C** |
| Market microstructure | **B → B** | **B → B/C** | **A/B → B** |
| Alternative data | **B/A → B** | **B/C → C** | **B → B/C** |

Canada appears in adjacent Prophet research but no active Mastermind Canada book was verified. This commission should not invent Europe/Japan/India roadmaps without a separate current-source census.

### Interpretation

**Fundamentals are not the main Asia gap anymore.** HK and mainland China can produce useful current fundamental context. The gap is historical decision-time vintage reconstruction and direct Mastermind consumption.

**Expectations are the highest-information parity gap.** Current research warns against fabricating historical analyst-revision persistence because no mature historical series exists. A current consensus snapshot cannot reconstruct historical revision sequences.

**China microstructure is different, not inferior.** Mainland session state, lunch break, daily price limits, suspensions, delayed-quote freshness and basis mismatches are local facts that should survive normalization.

**HK positioning must not be forced into a 13F template.** Southbound capital, A/H dislocation, CCASS participant holdings and Part XV disclosures answer related but distinct questions.

| US evidence | HK equivalent set | Mainland equivalent set | Correct semantic treatment |
|---|---|---|---|
| 13F holdings | CCASS participant holdings + Part XV + southbound flows | major-holder/public-fund/shareholder structure + financing context | same broad family, different subtypes |
| Form 4 | director/substantial-holder disclosures | director/major-holder share changes | normalize event semantics; retain jurisdiction |
| US short interest | SFC reportable short positions | margin/securities-lending framework where available | never use one denominator |
| US single-stock options | HK equity/index derivatives where liquid | mainland ETF/index options where applicable | instrument-specific expectation evidence |

The parity model is **source availability × historical PIT quality × downstream consumption**.

## D. Source landscape

Cost classes are qualitative only: $ public/open; $$ specialist/exchange; $$$ institutional; $$$$ broad global enterprise.

| Source | Coverage / history | PIT and corrections | Rights / cost | Best use |
|---|---|---|---|---|
| SEC EDGAR/XBRL | US filings/facts; strong modern history | high if acceptance time preserved; amendments explicit | public / $ | US filing/fundamental events |
| SEC Forms 3/4/5 | US insider; official bulk from 2006 | high as filed; amendments preserved | public / $ | insider events/clusters |
| SEC 13F | US institutional; structured 2013+ | high for filed state; intrinsically lagged | public / $ | positioning context |
| USAspending | US federal awards | good if publication time retained | public API / $ | government-contract exposure |
| HKEX disclosures / DI | HK issuer and substantial-interest events | potentially high with publication timestamps | terms must be checked / $–$$ | filings/holder events |
| HKEX CCASS | participant custody positions | high for participant holdings, not beneficial ownership | production rights required / $$–$$$ | positioning/concentration proxy |
| SFC reportable short positions | HK specified shares; weekly history | good official PIT if publication dates captured | public / $ | HK short-positioning |
| HKEX historical/full book | HK exchange microstructure | very high source fidelity | licensed / $$$ | only after incremental value proof |
| SSE/SZSE disclosures | mainland issuer/market events | potentially high; amendments must remain distinct | service-specific / $–$$ | filings/corporate actions |
| Existing AkShare-based collectors | CN/HK current context | weak historical collector-vintage replay | endpoint rights review / $ | current context + prospective PIT capture |
| LSEG I/B/E/S | global estimates; long advertised history | potentially very high; exact vintage contract must be proven | commercial / $$$$ | global PIT-estimates benchmark |
| LSEG StarMine revisions | global derived revision factors | useful but derived; model/version changes matter | commercial / $$$$ | secondary benchmark |
| FactSet Estimates | global estimates; 20+ years advertised | historical-vintage semantics must be proven | commercial / $$$$ | bake-off alternative |
| Visible Alpha | granular KPI consensus | PIT depth must be proven | commercial / $$$–$$$$ | driver-level expectations |
| IMF Data | cross-country macro | release/revision handling required | public / $ | comparative macro |

### Vendor ruling

The commercial-estimates recommendation is a **bake-off, not a purchase recommendation**. A vendor must prove:
- exact historical consensus vintage at timestamp T;
- revision sequence;
- correction lineage;
- stable record identity;
- cross-listing identity behavior;
- available_at/known_at semantics;
- retention, derived-data and model-use rights.

A feed that supplies only today's cleaned historical consensus fails the PIT gate for predictive backtesting.

### Country-specific legal/licensing posture

**United States:** SEC and federal-government datasets can form a broad public spine. Filing acceptance/publication timestamps must be preserved; fiscal-period end is not information availability.

**Hong Kong:** public visibility does not imply unrestricted commercial ingestion. CCASS is the clearest example. Production use requires an explicit rights decision rather than scraper assumptions.

**Mainland China:** official/native endpoints require accessibility, rights and data-classification review. Personal information should be segregated for applicable privacy/cross-border analysis. This is a legal-review trigger, not a conclusion that public securities filings are prohibited.

### Kill conditions for a source

Reject or keep context-only when:
- historical available_at cannot be reconstructed for the intended backtest;
- corrections are opaque;
- identifier joins are unreliable;
- rights prohibit required storage/model use/derived output;
- the source requires prohibited login-cookie scraping;
- operational fragility cannot meet the decision-time SLA;
- an expensive commercial source fails to beat a public/current baseline after controls.

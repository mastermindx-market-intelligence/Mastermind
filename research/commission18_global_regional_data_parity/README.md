# Commission 18 — Global / Regional Data Parity & Coverage Confidence

**Research date:** 2026-10-04  
**Status:** Research conclusion; implementation not authorized  
**Protected Mastermind pin:** a2646f458f9ff41ddcedd89b338be4a4349e6cd6  
**Skillpack:** mastermind.sol_skillpack.v1 v1.0.1

> Research only. This package does not authorize production code, live-pipeline changes, data purchases, deployment, portfolio/trading changes, or new data-source decision authority.

## A. Executive conclusion

Mastermind should build a **Regional Evidence Coverage and Equivalence Layer**, not force the United States, Hong Kong, mainland China and future regions into identical schemas or signal sets. At every decision timestamp it must make explicit: what evidence was available; whether it was direct, local-equivalent, proxy, stale, structurally unavailable, rights-blocked or missing; its point-in-time quality; and the confidence ceiling implied by the observed evidence set.

Priority order:

**P0 observability/PIT semantics → P0 historical expectations/revisions parity → P0 HK/CN filing and fundamental vintage capture → P1 region-native positioning/disclosure equivalents → P2 alternative-data and microstructure expansion.**

The investigation rejects the simplistic idea that HK/CN are now merely price-signal regions. The Macro estate contains substantial China regime, microstructure, live-Prophet, fundamental and news machinery. Hong Kong has market-native Prophet work, southbound/A-H/global-beta evidence, fundamentals and current analyst-consensus context.

The material asymmetry is now concentrated in:
- stronger US historical PIT support and richer direct Mastermind consumption;
- newer Asia intelligence that often remains upstream in Macro rather than reaching Mastermind's decision path;
- current HK/CN snapshots where the US has reconstructable historical vintages;
- no mature global historical PIT analyst-revision series;
- no first-class decision object for evidence coverage;
- Portfolio V3 correction-safe Decision Snapshot/evidence-independence machinery that is not yet generally live.

Governing principle:

> **Equivalent evidence where equivalent evidence exists; explicit non-equivalence where it does not; missing data is never neutral evidence.**

For Prophet, the highest-impact parity gap is historical expectations. China's rev_z is reversal, not analyst revisions.

## B. Current-state census

The commission's preliminary SHA d1594f3c7ae750db3f14b4eebf0de3460f84267a was treated as a clue. Protected Mastermind master was independently pinned at **a2646f458f9ff41ddcedd89b338be4a4349e6cd6**.

Observed adjacent research pins:
- Macro: 818d1bcea9f878a3872d341b6ee355441fd620cf
- mastermind-terminal: 1c708450187755160e1a5889b69598a2fcb1f0d1
- executive-dr-vault: ea422c92bd29800d1f7fb3ae850236cc44d8c890

Any implementation owner must re-bootstrap; these are research pins only.

The static data/census/CENSUS.md was generated 2026-07-16 against SHA 131290a, materially older than the October tree. Census freshness is itself a P0 observability gap.

US-facing Mastermind is comparatively rich. portfolio.lenses consumes price, valuation/growth, 13F, news/intelligence, political/insider/government-contract and alternative-data surfaces. portfolio.held_risk separates earnings expectations, solvency/dilution, ownership flow, macro sensitivity and sector rotation, including coverage_missing/stale states. loop/fundamentals.py performs PIT SEC-EDGAR selection; loop/single_name_panel.py includes active/delisted names and PIT S&P membership.

Asia upstream is stronger than the old census suggests. China has live Prophet/session/limit/suspension logic, regime/microstructure, fundamentals and native news/policy context. Hong Kong has southbound flow, A/H relative value, beta-neutral relative strength, regime fit, fundamentals and current consensus/targets.

The Asia weakness is historical replay: current HK/CN fundamental collectors largely maintain per-ticker cache records rather than complete decision-time vintages. Existing China/HK research already calls for append-only PIT capture, forbids treating gaps as zero and identifies last-mile consumption as a binding constraint.

**Current-state conclusion:** the regional problem is partly source scarcity, but equally **consumption, PIT history and observability**.

## Report package

The durable report is split into bounded files so source evidence, architecture and the exact implementation handoff remain independently reviewable:

- [COVERAGE_AND_SOURCES.md](COVERAGE_AND_SOURCES.md) — Sections C-D: evidence-family matrix, source landscape, rights posture.
- [DATA_MODEL_AND_INTEGRATION.md](DATA_MODEL_AND_INTEGRATION.md) — Sections E-G: canonical contracts, deterministic intelligence, integration map.
- [VALIDATION_AND_PRIORITY.md](VALIDATION_AND_PRIORITY.md) — Sections H-K: empirical validation, risks, build priority and phased recommendation.
- [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md) — Section L: exact bounded follow-on implementation commission.
- [SOURCES.md](SOURCES.md) — primary external references and internal source basis.

## Core ruling

Regional parity should mean **parity of decision questions, not parity of raw field names**.

Examples that must remain explicit:

- CCASS ≠ 13F.
- Southbound flow ≠ beneficial ownership.
- Mainland margin financing ≠ US short interest.
- Analyst target upside ≠ analyst revision momentum.
- China reversal rev_z ≠ analyst revision z-score.
- Missing ≠ neutral.
- Stale ≠ missing.
- Structurally unavailable ≠ adapter failure.

The correct parity model is:

**Source availability × historical PIT quality × downstream consumption.**

A region should not receive a high coverage grade simply because an upstream script can fetch a current value.

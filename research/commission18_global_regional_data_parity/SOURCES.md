# Commission 18 — Source Basis

This file records the durable source basis for the regional parity research. It is not a substitute for re-bootstrap at implementation time.

## Protected Mastermind source

Research pin:

**mastermindx-market-intelligence/Mastermind@a2646f458f9ff41ddcedd89b338be4a4349e6cd6**

Core internal starting points included:
- docs/sol_skills/INDEX.md
- data/census/CENSUS.md
- portfolio/lenses.py
- portfolio/held_risk.py
- brain/research_desk.py
- brain/bottleneck.py
- brain/china_intake.py
- loop/fundamentals.py
- loop/single_name_panel.py
- portfolio/prophet_feed.py
- research/TREND_PERSISTENCE_PROTOCOL.md
- docs/source_thematic_rotation_framework.md
- docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md
- current Macro HK/CN Prophet, fundamentals, regime, microstructure and native-data research artifacts

Observed adjacent research pins:
- Macro: 818d1bcea9f878a3872d341b6ee355441fd620cf
- mastermind-terminal: 1c708450187755160e1a5889b69598a2fcb1f0d1
- executive-dr-vault: ea422c92bd29800d1f7fb3ae850236cc44d8c890

These are research-time pins only.

## Primary external sources

### United States

SEC EDGAR APIs  
https://www.sec.gov/search-filings/edgar-application-programming-interfaces

SEC Insider Transactions Data Sets  
https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets

SEC Form 13F Data Sets  
https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets

USAspending API  
https://api.usaspending.gov/docs/

### Hong Kong

HKEX CCASS overview  
https://www.hkex.com.hk/Services/Clearing/Securities/Overview?sc_lang=en

HKEX CCASS Shareholding Search  
https://www3.hkexnews.hk/sdw/search/searchsdw.aspx

HKEX Disclosure of Interests  
https://www2.hkexnews.hk/Shareholding-Disclosures/Disclosure-of-Interests?sc_lang=en

SFC Aggregated Reportable Short Positions  
https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares

HKEX Data Marketplace  
https://www.hkex.com.hk/Services/Market-Data-Services/Historical-Data-Services/HKEX-Data-Marketplace?sc_lang=en

### Mainland China

Shanghai Stock Exchange  
https://www.sse.com.cn/

Shanghai Stock Exchange English site  
https://english.sse.com.cn/

The implementation phase should independently resolve current official SSE/SZSE/CNINFO endpoints and their production rights rather than treating aggregator accessibility as licensing authority.

### Global estimates vendors

LSEG I/B/E/S Estimates  
https://www.lseg.com/en/data-analytics/financial-data/company-data/ibes-estimates

LSEG StarMine Analyst Revisions Model  
https://www.lseg.com/en/data-catalogue/analytics/quantitative-analytics/starmine-analyst-revisions-model

FactSet Marketplace / Estimates  
https://www.factset.com/marketplace/catalog

Visible Alpha  
https://www.visiblealpha.com/products/

These vendor pages establish observed product claims, not the exact historical-vintage, correction, retention, redistribution or model-use rights Mastermind would receive under a specific contract. A sample bake-off and contract review are mandatory before procurement or PIT backtesting.

### Cross-border/privacy context

Hong Kong PCPD — Mainland Personal Information Protection Law resources  
https://www.pcpd.org.hk/english/data_privacy_law/mainland_law/mainland_law.html

This is a legal-review trigger for relevant personal/cross-border data, not a blanket conclusion about ordinary public securities filings.

## Research integrity notes

- No proprietary dataset, code, corpus or vendor research text is reproduced in this report.
- Marketing claims are not treated as proof of exact historical PIT capability.
- Public web visibility is not treated as proof of commercial ingestion rights.
- Historical backtests must gate observations by available_at/known_at, not by fiscal/event date alone.
- Corrections/restatements must remain generation-aware.
- Missing data must remain explicit and must never be converted to neutral evidence.
